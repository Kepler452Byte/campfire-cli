from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from campfire_cli.app.document.service.document_rule_service import DocumentRuleService
from campfire_cli.app.document.service.document_scanner import exempt_document
from campfire_cli.app.document.service.frontmatter_formatter import format_text
from campfire_cli.app.document.service.kanban_service import (
    check_kanban_renderability,
    renderability_result,
)
from campfire_cli.app.document.service.profile_registry import ProfileRegistry
from campfire_cli.common.documents.document_types import prefixed_name
from campfire_cli.common.documents.markdown import parse_document, render_document
from campfire_cli.common.exceptions import ConfigurationError, GovernanceBlockedError
from campfire_cli.common.filesystem import atomic_write, safe_path
from campfire_cli.common.governance import capture_snapshot, optimistic_write_lock
from campfire_cli.common.hashing import file_sha256
from campfire_cli.config.settings import WorkspaceSettings


class DocumentService:
    def __init__(self, settings: WorkspaceSettings) -> None:
        self._settings = settings
        self._rules = DocumentRuleService(settings.document_types, settings.frontmatter_schema)
        self._profiles = ProfileRegistry(settings.document_types, settings.frontmatter_schema)

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
        parsed = parse_document(path.read_text(encoding="utf-8"))
        document_type = parsed.frontmatter.get("type")
        profile = self._profiles.resolve(document_type, parsed.frontmatter, path)
        domain_id: str | None = None
        current = path.parent
        while current == self._settings.vault_root or self._settings.vault_root in current.parents:
            marker = current / "_领域.md"
            if marker.is_file():
                value = parse_document(marker.read_text(encoding="utf-8")).frontmatter.get(
                    "domain_id"
                )
                domain_id = value if isinstance(value, str) else None
                break
            if current == self._settings.vault_root:
                break
            current = current.parent
        issues = self._rules.check_document(self._settings.vault_root, path)
        return {
            "status": "ok" if not issues else "needs-review",
            "workspace_id": self._settings.workspace_id,
            "path": relative_path,
            "domain_id": domain_id,
            "type": document_type if isinstance(document_type, str) else None,
            "profile": profile.model_dump(),
            "issues": issues,
        }

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

    def upsert(
        self,
        relative_path: str,
        *,
        document_type: str | None = None,
        values: dict[str, Any] | None = None,
        body: str | None = None,
        append_section: str | None = None,
        replace_body: bool = False,
        expected_hash: str | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Create or patch one document using its effective Profile contract."""
        path = safe_path(self._settings.vault_root, relative_path)
        if path.suffix.lower() != ".md":
            raise ConfigurationError("document upsert 目标必须是 Markdown 文件")
        exists = path.is_file()
        original = path.read_text(encoding="utf-8") if exists else ""
        parsed = parse_document(original)
        if exists and not parsed.has_frontmatter:
            raise GovernanceBlockedError("已有文档缺少 Frontmatter，不能安全 upsert")
        current_type = parsed.frontmatter.get("type")
        resolved_type = document_type or (current_type if isinstance(current_type, str) else None)
        if not resolved_type:
            raise ConfigurationError("创建文档时必须提供 --type")
        if resolved_type not in self._settings.document_types.get("types", {}):
            raise ConfigurationError(f"未知文档类型：{resolved_type}")
        if exists and document_type and current_type != document_type:
            raise GovernanceBlockedError("不允许通过 upsert 改变已有文档的 type")
        expected_name = prefixed_name(path.name, resolved_type, self._settings.document_types)
        if expected_name != path.name:
            raise ConfigurationError(f"文件名应为：{expected_name}")

        patch = dict(values or {})
        if exists and any(
            key in patch and patch[key] != parsed.frontmatter.get(key)
            for key in ("type", "project", "domain")
        ):
            raise GovernanceBlockedError("不允许通过 upsert 改变 type、project 或 domain")
        today = date.today().isoformat()
        frontmatter = dict(parsed.frontmatter)
        if not exists:
            frontmatter.update(self._creation_defaults(path, resolved_type, today))
        frontmatter.update(patch)
        frontmatter["type"] = resolved_type
        frontmatter["updated"] = today
        profile = self._profiles.resolve(resolved_type, frontmatter, path)
        unknown = sorted(set(patch) - set(profile.allowed))
        if unknown:
            return {
                "status": "blocked",
                "workspace_id": self._settings.workspace_id,
                "action": "update" if exists else "create",
                "path": relative_path,
                "profile": profile.name,
                "expected_hash": file_sha256(path) if exists else "missing",
                "write_performed": False,
                "issues": [
                    {"code": "frontmatter-field-not-allowed", "path": relative_path, "field": key}
                    for key in unknown
                ],
                "missing_fields": [],
            }

        if exists and body is not None and not append_section and not replace_body:
            raise ConfigurationError(
                "更新时 --body-file 必须与 --append-section 或 --replace-body 同时使用"
            )
        next_body = parsed.body if exists else (body or "")
        if exists and replace_body and body is not None:
            next_body = body
        if append_section:
            if body is None:
                raise ConfigurationError("--append-section 必须与 --body-file 同时使用")
            next_body = self._append_to_section(parsed.body, append_section, body)
        rendered = render_document(frontmatter, next_body, list(profile.field_order))
        issues = self._rules.check_content(self._settings.vault_root, path, rendered)
        missing_codes = {"frontmatter-field-missing", "frontmatter-field-empty"}
        missing = [item for item in issues if item["code"] in missing_codes]
        status = "needs-input" if missing else "blocked" if issues else "planned"
        actual_hash = file_sha256(path) if exists else "missing"
        result: dict[str, Any] = {
            "status": status,
            "workspace_id": self._settings.workspace_id,
            "action": "update" if exists else "create",
            "path": relative_path,
            "profile": profile.name,
            "expected_hash": actual_hash,
            "write_performed": False,
            "issues": issues,
            "missing_fields": [item.get("field") or item.get("detail") for item in missing],
        }
        if issues or not confirm:
            return result
        if expected_hash is not None and expected_hash != actual_hash:
            return {
                **result,
                "status": "blocked",
                "issues": [{"code": "concurrent-change", "path": relative_path}],
            }
        snapshot = capture_snapshot(self._settings.vault_root, [path])
        with optimistic_write_lock(
            self._settings.state_root, snapshot, self._settings.vault_root
        ) as concurrent:
            if concurrent:
                raise GovernanceBlockedError("文档在 upsert 期间发生变化：" + ", ".join(concurrent))
            atomic_write(path, rendered)
        return {**result, "status": "applied", "write_performed": True}

    def _creation_defaults(self, path: Path, document_type: str, today: str) -> dict[str, Any]:
        stem = path.stem
        prefix = self._settings.document_types["types"][document_type]["prefix"]
        values: dict[str, Any] = {
            "name": stem[len(prefix) :] if stem.startswith(prefix) else stem,
            "type": document_type,
            "status": "current" if document_type == "task" else "draft",
            "created": today,
            "updated": today,
            "tags": [],
        }
        current = path.parent
        marker_name = self._settings.governance.get("domain_marker", "_领域.md")
        found_domain = False
        while current == self._settings.vault_root or self._settings.vault_root in current.parents:
            marker = current / marker_name
            if marker.is_file():
                found_domain = True
                domain = parse_document(marker.read_text(encoding="utf-8")).frontmatter
                if domain.get("domain_id"):
                    values["domain"] = domain["domain_id"]
                project = domain.get("project_id") or domain.get("project")
                if project:
                    values["project"] = project
                break
            if current == self._settings.vault_root:
                break
            current = current.parent
        if not found_domain:
            raise ConfigurationError("正式文档必须位于已声明的 Domain 内")
        return values

    @staticmethod
    def _append_to_section(current: str, heading: str, content: str) -> str:
        heading_line = f"## {heading.strip().lstrip('#').strip()}"
        suffix = f"\n\n{heading_line}\n\n{content.strip()}\n"
        return current.rstrip() + suffix

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
