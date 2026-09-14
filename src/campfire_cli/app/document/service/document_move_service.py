from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from campfire_cli.app.document.schema import DocumentFollowUp, DocumentMoveResult
from campfire_cli.app.document.service.document_rule_service import DocumentRuleService
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


class DocumentMoveService:
    """Move one document inside its Domain and update deterministic references."""

    def __init__(self, settings: WorkspaceSettings, rules: DocumentRuleService) -> None:
        self._settings = settings
        self._rules = rules
        self._executor = FileChangeExecutor(settings.vault_root, settings.state_root)

    def move(
        self,
        source_name: str,
        target_name: str,
        *,
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
        issues: list[dict[str, object]] = []
        if target.exists():
            issues.append({"code": "target-exists", "path": target_name})
        source_domain = self._domain_root(source)
        if source_domain is None or source_domain != self._domain_root(target):
            issues.append(
                {
                    "code": "cross-domain-move",
                    "path": source_name,
                    "detail": target_name,
                }
            )
        parsed = parse_document(source.read_text(encoding="utf-8"))
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
        else:
            issues.extend(
                self._rules.check_content(
                    self._settings.vault_root,
                    target,
                    source.read_text(encoding="utf-8"),
                )
            )
        if expected_hash is not None and expected_hash != actual_hash:
            issues.append({"code": "concurrent-change", "path": source_name})

        result = DocumentMoveResult(
            status="blocked" if issues else "ready",
            workspace_id=self._settings.workspace_id,
            source=source_name,
            target=target_name,
            expected_hash=actual_hash,
            issues=issues,
            follow_up=[
                DocumentFollowUp(
                    command="maintenance sync",
                    workspace=self._settings.workspace_id,
                    scope=target.parent.relative_to(self._settings.vault_root).as_posix(),
                ),
                DocumentFollowUp(
                    command="maintenance check",
                    workspace=self._settings.workspace_id,
                    scope=target.parent.relative_to(self._settings.vault_root).as_posix(),
                ),
            ],
        )
        if issues or not confirm:
            return result

        writes, updated_references, expected = self._prepare_writes(source, target)
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
        self, source: Path, target: Path
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
            text = reference.read_text(encoding="utf-8")
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

    def _domain_root(self, path: Path) -> Path | None:
        marker_name = self._settings.governance.get("domain_marker", "_领域.md")
        current = path.parent
        while current == self._settings.vault_root or self._settings.vault_root in current.parents:
            if (current / marker_name).is_file():
                return current
            if current == self._settings.vault_root:
                break
            current = current.parent
        return None

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
