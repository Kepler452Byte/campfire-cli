from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from campfire_cli.app.base.schema.operation_schema import maintenance_sync_follow_up
from campfire_cli.app.document.schema import DocumentMoveResult
from campfire_cli.app.document.service.document_relocation import prepare_document_relocation
from campfire_cli.app.document.service.document_rule_service import DocumentRuleService
from campfire_cli.app.document.service.frontmatter_formatter import render_patch
from campfire_cli.app.document.service.profile_registry import ProfileRegistry
from campfire_cli.common.documents.document_types import prefixed_name
from campfire_cli.common.documents.domain_context import (
    DomainContext,
    DomainContextError,
    resolve_domain_context,
)
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem import FileChangeExecutor, FileChangeSet, safe_path
from campfire_cli.common.hashing import file_sha256
from campfire_cli.config.settings import WorkspaceSettings

STRUCTURAL_FIELDS = {"domain", "project", "updated"}


class DocumentMoveService:
    """Move one document between declared Domains and preserve document invariants."""

    def __init__(
        self,
        settings: WorkspaceSettings,
        rules: DocumentRuleService,
        profiles: ProfileRegistry,
    ) -> None:
        self._settings = settings
        self._rules = rules
        self._profiles = profiles
        self._executor = FileChangeExecutor(settings.vault_root, settings.state_root)

    def move(
        self,
        source_name: str,
        target_name: str,
        *,
        values: dict[str, Any],
        unset_fields: tuple[str, ...],
        expected_hash: str | None = None,
        confirm: bool = False,
    ) -> DocumentMoveResult:
        source = safe_path(self._settings.vault_root, source_name)
        target = safe_path(self._settings.vault_root, target_name)
        if source == target:
            raise ConfigurationError("document move 的源路径和目标路径不能相同")
        if not source.is_file():
            raise ConfigurationError(f"Markdown 文档不存在：{source_name}")
        if source.suffix.lower() != ".md" or target.suffix.lower() != ".md":
            raise ConfigurationError("document move 只支持 Markdown 文档")

        actual_hash = file_sha256(source)
        original = source.read_text(encoding="utf-8")
        parsed = parse_document(original)
        source_domain, source_domain_issue = self._domain_context(source)
        target_domain, target_domain_issue = self._domain_context(target)
        issues: list[dict[str, Any]] = []
        if target.exists():
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
            issues.append({"code": "document-move-type-owned", "path": source_name})
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
            patch = dict(values)
            removed = set(unset_fields)
            if parsed.frontmatter.get("domain") != target_domain.domain_id:
                patch["domain"] = target_domain.domain_id
            if (
                target_domain.project_id
                and parsed.frontmatter.get("project") != target_domain.project_id
            ):
                patch["project"] = target_domain.project_id
            elif not target_domain.project_id and "project" in parsed.frontmatter:
                removed.add("project")
            if source_domain != target_domain or values or unset_fields:
                patch["updated"] = date.today().isoformat()

            next_frontmatter = dict(parsed.frontmatter)
            for field in removed:
                next_frontmatter.pop(field, None)
            next_frontmatter.update(patch)
            profile = self._profiles.resolve(document_type, next_frontmatter, target)
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
            if not render_errors and not unknown:
                issues.extend(
                    self._rules.check_content(self._settings.vault_root, target, rendered)
                )
            missing_codes = {"frontmatter-field-missing", "frontmatter-field-empty"}
            for issue in issues:
                field = issue.get("field")
                if issue["code"] not in missing_codes or not isinstance(field, str):
                    continue
                if field in profile.enums:
                    issue["allowed"] = list(profile.enums[field])
                elif field in profile.lists:
                    issue["allowed"] = ["list"]
                elif field in profile.dates:
                    issue["allowed"] = ["YYYY-MM-DD"]
                elif field in profile.value_types:
                    issue["allowed"] = [profile.value_types[field]]
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
        follow_up = maintenance_sync_follow_up(
            self._settings.workspace_id,
            (
                context.root.relative_to(self._settings.vault_root).as_posix()
                for context in (source_domain, target_domain)
                if context is not None
            ),
        )
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
        if issues or not confirm:
            return result

        writes, updated_references, expected = prepare_document_relocation(
            self._settings.vault_root, source, target, rendered
        )
        expected[source] = actual_hash
        expected[target] = None
        self._executor.execute(
            FileChangeSet(
                writes=tuple(writes),
                deletes=(source,),
                label="document move",
                expected=expected,
            )
        )
        return result.model_copy(
            update={
                "status": "moved",
                "write_performed": True,
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
