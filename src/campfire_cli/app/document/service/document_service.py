from __future__ import annotations

from pathlib import Path
from typing import Any

from campfire_cli.app.document.schema import (
    DocumentApplyRequest,
    DocumentApplyResult,
    DocumentIndexResult,
    DocumentListResult,
    DocumentMoveResult,
)
from campfire_cli.app.document.service.document_apply_service import DocumentApplyService
from campfire_cli.app.document.service.document_index_service import DocumentIndexService
from campfire_cli.app.document.service.document_move_service import DocumentMoveService
from campfire_cli.app.document.service.document_rule_service import DocumentRuleService
from campfire_cli.app.document.service.document_scanner import exempt_document
from campfire_cli.app.document.service.kanban_service import (
    check_kanban_renderability,
    renderability_result,
)
from campfire_cli.app.document.service.profile_registry import ProfileRegistry
from campfire_cli.common.documents.domain_context import (
    DomainContextError,
    resolve_domain_by_id,
    resolve_domain_context,
)
from campfire_cli.common.documents.frontmatter_format import format_text
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.exceptions import ConfigurationError, GovernanceBlockedError
from campfire_cli.common.filesystem import atomic_write, safe_path
from campfire_cli.common.governance import capture_snapshot, optimistic_write_lock
from campfire_cli.config.settings import WorkspaceSettings


class DocumentService:
    def __init__(
        self,
        settings: WorkspaceSettings,
        index: DocumentIndexService,
        project_roots: dict[str, str],
    ) -> None:
        self._settings = settings
        self._index = index
        self._rules = DocumentRuleService(settings.document_types, settings.frontmatter_schema)
        self._profiles = ProfileRegistry(settings.document_types, settings.frontmatter_schema)
        self._project_roots = project_roots
        self._application = DocumentApplyService(
            settings, self._rules, self._profiles, project_roots
        )
        self._movement = DocumentMoveService(settings, self._rules, self._profiles, project_roots)

    def check(self, relative_path: str) -> dict[str, Any]:
        path = self._document_path(relative_path)
        if self._is_exempt(path):
            return self._not_applicable(relative_path, path)
        issues = self._rules.check_document(self._settings.vault_root, path)
        return {
            "status": "ok" if not issues else "needs-review",
            "workspace_id": self._settings.workspace_id,
            "path": relative_path,
            "issue_count": len(issues),
            "issues": issues,
        }

    def kanban_check(self, relative_path: str) -> dict[str, Any]:
        path = self._document_path(relative_path)
        if self._is_exempt(path):
            return self._not_applicable(relative_path, path)
        issues = check_kanban_renderability(path.read_text(encoding="utf-8"))
        return {
            **renderability_result(relative_path, issues),
            "workspace_id": self._settings.workspace_id,
        }

    def inspect(self, relative_path: str) -> dict[str, Any]:
        path = self._document_path(relative_path)
        if self._is_exempt(path):
            return self._not_applicable(relative_path, path)
        normalized = path.relative_to(self._settings.vault_root).as_posix()
        parsed = parse_document(path.read_text(encoding="utf-8"))
        document_type = parsed.frontmatter.get("type")
        profile = self._profiles.resolve(document_type, parsed.frontmatter, path)
        context = resolve_domain_context(
            self._settings.vault_root,
            path,
            self._project_roots,
            self._settings.governance.get("domain_marker", "_领域.md"),
        )
        issues = self._rules.check_document(self._settings.vault_root, path)
        generation, relations = self._index.relations(normalized)
        issues.extend(
            {
                "code": f"document-reference-{item['resolution']}",
                "path": normalized,
                "detail": item["raw_target"],
                "actual": item["candidates"],
            }
            for item in relations["unresolved"]
        )
        return {
            "status": "ok" if not issues else "needs-review",
            "workspace_id": self._settings.workspace_id,
            "path": normalized,
            "domain_id": context.domain_id,
            "project_id": context.project_id,
            "type": document_type if isinstance(document_type, str) else None,
            "profile": profile.model_dump(),
            "index_generation": generation,
            "relations": relations,
            "issues": issues,
        }

    def list(
        self,
        *,
        project: str | None = None,
        domain: str | None = None,
        document_type: str | None = None,
        document_status: str | None = None,
        lifecycle: str | None = None,
        task_status: str | None = None,
        limit: int | None = None,
    ) -> DocumentListResult:
        return self._index.list_documents(
            project=project,
            domain=domain,
            document_type=document_type,
            document_status=document_status,
            lifecycle=lifecycle,
            task_status=task_status,
            limit=limit,
        )

    def rebuild_index(self) -> DocumentIndexResult:
        return self._index.rebuild()

    def format(self, relative_path: str, confirm: bool = False) -> dict[str, Any]:
        path = self._document_path(relative_path)
        if self._is_exempt(path):
            return self._not_applicable(relative_path, path)
        original = path.read_text(encoding="utf-8")
        parsed = parse_document(original)
        if not parsed.has_frontmatter:
            return {
                "status": "blocked",
                "workspace_id": self._settings.workspace_id,
                "path": relative_path,
                "write_performed": False,
                "issues": [{"code": "frontmatter-missing", "path": relative_path}],
            }
        profile = self._profiles.resolve(parsed.frontmatter.get("type"), parsed.frontmatter, path)
        formatted, errors = format_text(original, list(profile.field_order))
        if errors:
            return {
                "status": "blocked",
                "workspace_id": self._settings.workspace_id,
                "path": relative_path,
                "write_performed": False,
                "issues": [{"code": code, "path": relative_path} for code in errors],
            }
        changed = formatted != original
        if changed and confirm:
            snapshot = capture_snapshot(self._settings.vault_root, [path])
            with optimistic_write_lock(
                self._settings.state_root, snapshot, self._settings.vault_root
            ) as concurrent:
                if concurrent:
                    raise GovernanceBlockedError(
                        "文档在格式化期间发生变化：" + ", ".join(concurrent)
                    )
                atomic_write(path, formatted)
        return {
            "status": "formatted" if changed and confirm else "planned" if changed else "current",
            "workspace_id": self._settings.workspace_id,
            "path": relative_path,
            "profile": profile.name,
            "write_performed": changed and confirm,
        }

    def apply(self, request: DocumentApplyRequest) -> DocumentApplyResult:
        """Create or patch exactly one document using its effective Profile contract."""
        return self._application.apply(request)

    def move(
        self,
        source: str,
        target_domain: str,
        *,
        name: str | None = None,
        values: dict[str, str] | None = None,
        unset_fields: tuple[str, ...] = (),
        expected_hash: str | None = None,
        confirm: bool = False,
    ) -> DocumentMoveResult:
        source_path = safe_path(self._settings.vault_root, source)
        target_name = name or source_path.name
        if Path(target_name).name != target_name or not target_name.endswith(".md"):
            raise ConfigurationError("document move 的 --name 必须是 Markdown 文件名")
        try:
            domain = resolve_domain_by_id(
                self._settings.vault_root, target_domain, self._project_roots
            )
        except DomainContextError as exc:
            raise exc
        target = (domain.root / target_name).relative_to(self._settings.vault_root).as_posix()
        return self._movement.move(
            source,
            target,
            values=values or {},
            unset_fields=unset_fields,
            expected_hash=expected_hash,
            confirm=confirm,
        )

    def _document_path(self, relative_path: str) -> Path:
        path = safe_path(self._settings.vault_root, relative_path)
        if not path.is_file() or path.suffix.lower() != ".md":
            raise ConfigurationError(f"Markdown 文档不存在：{relative_path}")
        return path

    def _not_applicable(self, relative_path: str, path: Path) -> dict[str, Any]:
        marker_commands = {
            self._settings.governance.get("space_marker", "_空间.md"): "workspace space check",
            self._settings.governance.get("domain_marker", "_领域.md"): "workspace domain check",
        }
        return {
            "status": "not-applicable",
            "workspace_id": self._settings.workspace_id,
            "path": relative_path,
            "reason": "document-exempt",
            "owner_command": marker_commands.get(path.name),
            "issues": [],
        }

    def _is_exempt(self, path: Path) -> bool:
        relative = path.relative_to(self._settings.vault_root)
        collaboration_root = self._settings.governance.get("collaboration_root", "_协作")
        if relative.parts and relative.parts[0] == collaboration_root:
            return True
        markers = {
            self._settings.governance.get("space_marker", "_空间.md"),
            self._settings.governance.get("domain_marker", "_领域.md"),
        }
        return path.name in markers or exempt_document(path, self._settings.document_types)
