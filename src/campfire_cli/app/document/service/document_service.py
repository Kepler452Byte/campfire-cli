from __future__ import annotations

from pathlib import Path
from typing import Any

from campfire_cli.app.document.service.document_rule_service import DocumentRuleService
from campfire_cli.app.document.service.frontmatter_formatter import format_text
from campfire_cli.app.document.service.profile_registry import ProfileRegistry
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.exceptions import ConfigurationError, GovernanceBlockedError
from campfire_cli.common.filesystem import atomic_write, safe_path, workspace_write_lock
from campfire_cli.common.governance import capture_snapshot, snapshot_changes
from campfire_cli.config.settings import WorkspaceSettings


class DocumentService:
    def __init__(self, settings: WorkspaceSettings) -> None:
        self._settings = settings
        self._rules = DocumentRuleService(settings.document_types, settings.frontmatter_schema)
        self._profiles = ProfileRegistry(settings.document_types, settings.frontmatter_schema)

    def check(self, relative_path: str) -> dict[str, Any]:
        path = self._document_path(relative_path)
        issues = self._rules.check_document(self._settings.vault_root, path)
        return {
            "status": "ok" if not issues else "needs-review",
            "workspace_id": self._settings.workspace_id,
            "path": relative_path,
            "issue_count": len(issues),
            "issues": issues,
        }

    def format(self, relative_path: str, confirm: bool = False) -> dict[str, Any]:
        path = self._document_path(relative_path)
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
            with workspace_write_lock(self._settings.state_root):
                concurrent = snapshot_changes(self._settings.vault_root, snapshot)
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

    def _document_path(self, relative_path: str) -> Path:
        path = safe_path(self._settings.vault_root, relative_path)
        if not path.is_file() or path.suffix.lower() != ".md":
            raise ConfigurationError(f"Markdown 文档不存在：{relative_path}")
        return path
