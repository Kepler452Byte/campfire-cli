from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

from campfire_cli.app.base.schema.operation_schema import maintenance_follow_up
from campfire_cli.app.document.schema import DocumentMoveResult
from campfire_cli.app.document.service.document_rule_service import DocumentRuleService
from campfire_cli.app.document.service.frontmatter_formatter import render_patch
from campfire_cli.app.document.service.profile_registry import ProfileRegistry
from campfire_cli.app.document.service.type_apply import (
    rebase_markdown_links,
    rewrite_markdown_links,
    rewrite_wikilinks,
)
from campfire_cli.common.documents.document_types import prefixed_name
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem import FileChangeExecutor, FileChangeSet, FileWrite, safe_path
from campfire_cli.common.hashing import file_sha256
from campfire_cli.config.settings import WorkspaceSettings

STRUCTURAL_FIELDS = {"domain", "project", "updated"}


@dataclass(frozen=True)
class DomainContext:
    root: Path
    domain_id: str
    project_id: str | None


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
        source_domain = self._domain_context(source)
        target_domain = self._domain_context(target)
        issues: list[dict[str, Any]] = []
        if target.exists():
            issues.append({"code": "target-exists", "path": target_name})
        if source_domain is None:
            issues.append({"code": "source-domain-missing", "path": source_name})
        if target_domain is None:
            issues.append({"code": "target-domain-missing", "path": target_name})
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
            follow_up=maintenance_follow_up(
                self._settings.workspace_id,
                (
                    context.root.relative_to(self._settings.vault_root).as_posix()
                    for context in (source_domain, target_domain)
                    if context is not None
                ),
            ),
        )
        if issues or not confirm:
            return result

        writes, updated_references, expected = self._prepare_writes(source, target, rendered)
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
            }
        )

    def _prepare_writes(
        self, source: Path, target: Path, moved_text: str
    ) -> tuple[list[FileWrite], list[str], dict[Path, str | None]]:
        references = self._reference_files()
        unique_stem = (
            sum(path.stem == source.stem for path in references if path.suffix == ".md") == 1
        )
        source_relative = source.relative_to(self._settings.vault_root).as_posix()
        target_relative = target.relative_to(self._settings.vault_root).as_posix()
        writes: dict[Path, str] = {}
        changed: list[str] = []
        expected = {path: file_sha256(path) for path in references}
        for reference in references:
            text = moved_text if reference == source else reference.read_text(encoding="utf-8")
            updated = text.replace(source_relative, target_relative).replace(
                quote(source_relative), quote(target_relative)
            )
            if unique_stem and source.stem != target.stem:
                updated = rewrite_wikilinks(updated, source.stem, target.stem)
            if reference.suffix.lower() == ".md":
                updated = rewrite_markdown_links(updated, reference, source, target)
                if reference == source and source.parent != target.parent:
                    updated = rebase_markdown_links(updated, source, target)
            output = target if reference == source else reference
            if reference == source or updated != text:
                writes[output] = updated
            if reference != source and updated != text:
                changed.append(reference.relative_to(self._settings.vault_root).as_posix())
        return [FileWrite(path, text) for path, text in writes.items()], changed, expected

    def _domain_context(self, path: Path) -> DomainContext | None:
        marker_name = self._settings.governance.get("domain_marker", "_领域.md")
        current = path.parent
        while current == self._settings.vault_root or self._settings.vault_root in current.parents:
            marker = current / marker_name
            if marker.is_file():
                values = parse_document(marker.read_text(encoding="utf-8")).frontmatter
                domain_id = values.get("domain_id")
                if not isinstance(domain_id, str) or not domain_id:
                    return None
                project = values.get("project_id") or values.get("project")
                return DomainContext(
                    root=current,
                    domain_id=domain_id,
                    project_id=project if isinstance(project, str) and project else None,
                )
            if current == self._settings.vault_root:
                break
            current = current.parent
        return None

    def _is_reserved_target(self, context: DomainContext, target: Path) -> bool:
        relative = target.parent.relative_to(context.root)
        reserved = {
            *self._settings.document_types.get("ignored_directories", []),
            *self._settings.governance.get("project_reserved_directories", []),
        }
        return any(part in reserved or part.startswith(".") for part in relative.parts)

    def _reference_files(self) -> list[Path]:
        ignored = {".git", ".campfire"}
        return sorted(
            path
            for path in self._settings.vault_root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".md", ".canvas"}
            and not any(
                part in ignored for part in path.relative_to(self._settings.vault_root).parts
            )
        )
