from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

from campfire_cli.app.document.schema import DocumentMoveResult
from campfire_cli.app.document.service.index.document_index_service import DocumentIndexService
from campfire_cli.app.document.service.mutation.document_relocation import (
    prepare_document_relocation,
    refresh_after_write,
    relationship_follow_up,
)
from campfire_cli.app.document.service.rules.document_patch_values import (
    decode_patch_values,
    enrich_profile_issues,
)
from campfire_cli.app.document.service.rules.document_rule_service import DocumentRuleService
from campfire_cli.app.document.service.rules.profile_candidates import workspace_candidate_sets
from campfire_cli.app.document.service.rules.profile_registry import ProfileRegistry
from campfire_cli.common.documents.document_types import prefixed_name
from campfire_cli.common.documents.domain_context import (
    DomainContext,
    DomainContextError,
    resolve_domain_context,
)
from campfire_cli.common.documents.frontmatter_format import render_patch
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem import FileChangeExecutor, FileChangeSet, FileWrite, safe_path
from campfire_cli.common.filesystem.plan import plan_digest
from campfire_cli.common.hashing import text_sha256
from campfire_cli.config.settings import WorkspaceSettings

STRUCTURAL_FIELDS = {"updated"}


class DocumentMoveService:
    """Relocate or rename one document while preserving document invariants."""

    def __init__(
        self,
        settings: WorkspaceSettings,
        rules: DocumentRuleService,
        profiles: ProfileRegistry,
        index: DocumentIndexService,
        project_roots: dict[str, str] | None = None,
    ) -> None:
        self._settings = settings
        self._rules = rules
        self._profiles = profiles
        self._index = index
        self._project_roots = project_roots or {}
        self._executor = FileChangeExecutor(settings.vault_root, settings.state_root)

    def move(
        self,
        source_name: str,
        target_name: str,
        *,
        values: dict[str, str],
        unset_fields: tuple[str, ...],
        expected_hash: str | None = None,
        expected_plan: str | None = None,
        confirm: bool = False,
    ) -> DocumentMoveResult:
        return self._relocate(
            source_name,
            target_name,
            values=values,
            unset_fields=unset_fields,
            expected_hash=expected_hash,
            expected_plan=expected_plan,
            confirm=confirm,
            operation="move",
        )

    def rename(
        self,
        source_name: str,
        name: str,
        *,
        expected_hash: str | None = None,
        expected_plan: str | None = None,
        confirm: bool = False,
    ) -> DocumentMoveResult:
        """Rename one document in place from a logical title."""
        title = name.strip()
        if not title or Path(title).name != title or title.endswith(".md"):
            raise ConfigurationError("document rename 的 --name 必须是不含路径和 .md 后缀的标题")
        source = safe_path(self._settings.vault_root, source_name)
        if not source.is_file() or source.suffix.lower() != ".md":
            raise ConfigurationError(f"Markdown 文档不存在：{source_name}")
        document_type = parse_document(source.read_bytes().decode("utf-8")).frontmatter.get("type")
        target_name = f"{title}.md"
        normalized_title = title
        if (
            isinstance(document_type, str)
            and document_type in self._settings.document_types["types"]
        ):
            target_name = prefixed_name(target_name, document_type, self._settings.document_types)
            prefix = self._settings.document_types["types"][document_type]["prefix"]
            normalized_title = Path(target_name).stem.removeprefix(prefix)
        target = source.with_name(target_name).relative_to(self._settings.vault_root).as_posix()
        return self._relocate(
            source_name,
            target,
            values={"name": normalized_title},
            unset_fields=(),
            expected_hash=expected_hash,
            expected_plan=expected_plan,
            confirm=confirm,
            operation="rename",
        )

    def _relocate(
        self,
        source_name: str,
        target_name: str,
        *,
        values: dict[str, str],
        unset_fields: tuple[str, ...],
        expected_hash: str | None,
        expected_plan: str | None,
        confirm: bool,
        operation: Literal["move", "rename"],
    ) -> DocumentMoveResult:
        source = safe_path(self._settings.vault_root, source_name)
        target = safe_path(self._settings.vault_root, target_name)
        if source == target and operation == "move":
            raise ConfigurationError("document move 的源路径和目标路径不能相同")
        if not source.is_file():
            raise ConfigurationError(f"Markdown 文档不存在：{source_name}")
        if source.suffix.lower() != ".md" or target.suffix.lower() != ".md":
            raise ConfigurationError("document move 只支持 Markdown 文档")

        original = source.read_bytes().decode("utf-8")
        actual_hash = text_sha256(original)
        parsed = parse_document(original)
        source_domain, source_domain_issue = self._domain_context(source)
        target_domain, target_domain_issue = self._domain_context(target)
        issues: list[dict[str, Any]] = []
        if target.exists() and target != source:
            issues.append({"code": "target-exists", "path": target_name})
        if source_domain is None:
            issues.append(
                {"code": source_domain_issue or "source-domain-missing", "path": source_name}
            )
        if target_domain is None:
            issues.append(
                {"code": target_domain_issue or "target-domain-missing", "path": target_name}
            )
        elif self._is_reserved_target(target_domain, target):
            issues.append({"code": "target-directory-reserved", "path": target_name})
        if not parsed.has_frontmatter:
            issues.append({"code": "frontmatter-missing", "path": source_name})

        document_type = parsed.frontmatter.get("type")
        if not isinstance(document_type, str):
            issues.append({"code": "document-type-missing", "path": source_name})
        elif document_type not in self._settings.document_types.get("types", {}):
            issues.append(
                {"code": "document-type-invalid", "path": source_name, "detail": document_type}
            )
        elif document_type == "moc":
            issues.append({"code": f"document-{operation}-type-owned", "path": source_name})
        elif (
            prefixed_name(target.name, document_type, self._settings.document_types) != target.name
        ):
            issues.append(
                {
                    "code": "document-prefix-mismatch",
                    "path": target_name,
                    "detail": self._settings.document_types["types"][document_type]["prefix"],
                }
            )

        explicit_fields = set(values) | set(unset_fields)
        for field in sorted(explicit_fields & STRUCTURAL_FIELDS):
            issues.append(
                {
                    "code": "document-move-field-owned",
                    "path": target_name,
                    "field": field,
                }
            )
        for field in sorted(set(values) & set(unset_fields)):
            issues.append(
                {"code": "document-move-field-conflict", "path": target_name, "field": field}
            )
        if "type" in explicit_fields:
            issues.append(
                {"code": "document-move-type-change", "path": target_name, "field": "type"}
            )
        if expected_hash is not None and expected_hash != actual_hash:
            issues.append({"code": "concurrent-change", "path": source_name})

        rendered = original
        profile_name: str | None = None
        frontmatter_changes: dict[str, Any] = {}
        missing_fields: list[str] = []
        if not issues and target_domain is not None:
            removed = set(unset_fields)
            structural_patch: dict[str, Any] = {}
            removed.update({"project", "domain"} & set(parsed.frontmatter))
            if source_domain != target_domain or values or unset_fields:
                structural_patch["updated"] = date.today().isoformat()

            profile_frontmatter = dict(parsed.frontmatter)
            for field in removed:
                profile_frontmatter.pop(field, None)
            profile_frontmatter.update(structural_patch)
            profile = self._profiles.resolve(document_type, profile_frontmatter, target)
            profile_name = profile.name
            unknown = sorted(set(values) - set(profile.allowed))
            if unknown:
                issues.extend(
                    {
                        "code": "frontmatter-field-not-allowed",
                        "path": target_name,
                        "field": field,
                    }
                    for field in unknown
                )
            decoded: dict[str, Any] = {}
            if not unknown:
                decoded, input_issues = decode_patch_values(
                    profile,
                    values,
                    target_name,
                    workspace_candidate_sets(self._settings.vault_root),
                )
                issues.extend(input_issues)
            patch = {**decoded, **structural_patch}
            next_frontmatter = dict(profile_frontmatter)
            next_frontmatter.update(decoded)
            render_errors: list[str] = []
            if not issues:
                rendered, render_errors = (
                    render_patch(
                        original,
                        patch,
                        parsed.body,
                        list(profile.field_order),
                        tuple(sorted(removed)),
                    )
                    if patch or removed
                    else (original, [])
                )
            issues.extend({"code": code, "path": target_name} for code in render_errors)
            if not issues:
                issues.extend(
                    self._rules.check_content(self._settings.vault_root, target, rendered, profile)
                )
            enrich_profile_issues(
                issues, profile, workspace_candidate_sets(self._settings.vault_root)
            )
            missing_codes = {"frontmatter-field-missing", "frontmatter-field-empty"}
            missing_fields = [
                str(item.get("field") or item.get("detail"))
                for item in issues
                if item["code"] in missing_codes
            ]
            for field in sorted(set(patch) | removed):
                before = parsed.frontmatter.get(field)
                after = next_frontmatter.get(field)
                if before != after:
                    frontmatter_changes[field] = after

        status = "needs-input" if missing_fields else "blocked" if issues else "ready"
        result = DocumentMoveResult(
            status=status,
            workspace_id=self._settings.workspace_id,
            source=source_name,
            target=target_name,
            expected_hash=actual_hash,
            source_domain=source_domain.domain_id if source_domain else None,
            target_domain=target_domain.domain_id if target_domain else None,
            profile=profile_name,
            frontmatter_changes=frontmatter_changes,
            issues=issues,
            missing_fields=missing_fields,
        )
        if issues:
            return result

        if source == target and rendered == original:
            return result.model_copy(update={"status": "up-to-date"})

        self._index.reconcile()
        if source == target:
            writes = [FileWrite(source, rendered)]
            updated_references: list[str] = []
            expected = {source: actual_hash}
            deletes: tuple[Path, ...] = ()
        else:
            writes, updated_references, expected = prepare_document_relocation(
                self._settings.vault_root, source, target, rendered, self._index
            )
            expected[source] = actual_hash
            expected[target] = None
            deletes = (source,)
        changes = FileChangeSet(
            writes=tuple(writes),
            deletes=deletes,
            label=f"document {operation}",
            expected=expected,
        )
        generation = self._index.generation()
        digest = plan_digest(self._settings.vault_root, changes)
        result = result.model_copy(
            update={"expected_plan": digest, "updated_references": updated_references}
        )
        if not confirm:
            return result
        if expected_plan != digest:
            return result.model_copy(
                update={
                    "status": "blocked",
                    "issues": [
                        {
                            "code": "document-plan-changed"
                            if expected_plan
                            else "document-plan-required",
                            "hint": "重新预览，并传入返回的 --expected-plan 和 --expected-hash。",
                        }
                    ],
                }
            )
        self._executor.execute(changes, before_write=lambda: self._index.prepare_write(generation))
        index_issues = refresh_after_write(
            self._index,
            {
                source_name,
                target_name,
                *updated_references,
            },
        )
        follow_up = relationship_follow_up(
            self._settings, {source_name, target_name, *updated_references}, [original, rendered]
        )
        return result.model_copy(
            update={
                "status": "renamed" if operation == "rename" else "moved",
                "write_performed": True,
                "issues": index_issues,
                "updated_references": updated_references,
                "follow_up": follow_up,
            }
        )

    def _domain_context(self, path: Path) -> tuple[DomainContext | None, str | None]:
        try:
            return (
                resolve_domain_context(
                    self._settings.vault_root,
                    path,
                    self._project_roots,
                    self._settings.governance.get("domain_marker", "_领域.md"),
                ),
                None,
            )
        except DomainContextError as exc:
            return None, exc.code

    def _is_reserved_target(self, context: DomainContext, target: Path) -> bool:
        relative = target.parent.relative_to(context.root)
        reserved = {
            *self._settings.document_types.get("ignored_directories", []),
            *self._settings.governance.get("project_reserved_directories", []),
        }
        return any(part in reserved or part.startswith(".") for part in relative.parts)
