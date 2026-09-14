from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from campfire_cli.app.base.schema.operation_schema import maintenance_follow_up
from campfire_cli.app.document.schema import (
    DocumentApplyRequest,
    DocumentApplyResult,
)
from campfire_cli.app.document.service.document_rule_service import DocumentRuleService
from campfire_cli.app.document.service.frontmatter_formatter import render_patch
from campfire_cli.app.document.service.profile_registry import ProfileRegistry
from campfire_cli.common.documents.document_types import prefixed_name
from campfire_cli.common.documents.markdown import parse_document, render_document
from campfire_cli.common.exceptions import ConfigurationError, GovernanceBlockedError
from campfire_cli.common.filesystem import FileChangeExecutor, FileChangeSet, FileWrite, safe_path
from campfire_cli.common.hashing import file_sha256
from campfire_cli.config.settings import WorkspaceSettings


class DocumentApplyService:
    """Plan and atomically apply one Profile-valid document change."""

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

    def apply(self, request: DocumentApplyRequest) -> DocumentApplyResult:
        path = safe_path(self._settings.vault_root, request.path)
        if path.suffix.lower() != ".md":
            raise ConfigurationError("document apply 目标必须是 Markdown 文件")
        exists = path.is_file()
        original = path.read_text(encoding="utf-8") if exists else ""
        parsed = parse_document(original)
        if exists and not parsed.has_frontmatter:
            raise GovernanceBlockedError("已有文档缺少 Frontmatter，不能安全 apply")

        current_type = parsed.frontmatter.get("type")
        document_type = request.document_type or (
            current_type if isinstance(current_type, str) else None
        )
        if not document_type:
            raise ConfigurationError("创建文档时必须提供 --type")
        if document_type not in self._settings.document_types.get("types", {}):
            raise ConfigurationError(f"未知文档类型：{document_type}")
        if exists and request.document_type and current_type != request.document_type:
            raise GovernanceBlockedError("不允许通过 document apply 改变已有文档的 type")

        expected_name = prefixed_name(path.name, document_type, self._settings.document_types)
        if expected_name != path.name:
            raise ConfigurationError(f"文件名应为：{expected_name}")
        if request.values.get("type", document_type) != document_type:
            raise GovernanceBlockedError("--set type 与有效文档类型不一致；请使用专用重构命令")

        today = date.today().isoformat()
        frontmatter = dict(parsed.frontmatter)
        if not exists:
            frontmatter.update(self._creation_defaults(path, document_type, today))
        for key in ("project", "domain"):
            if key in request.values and request.values[key] != frontmatter.get(key):
                raise GovernanceBlockedError(
                    f"--set {key} 与目标 Domain 上下文不一致；请使用专用重构命令"
                )
        frontmatter.update(request.values)
        frontmatter["type"] = document_type
        frontmatter["updated"] = today
        profile = self._profiles.resolve(document_type, frontmatter, path)
        actual_hash = file_sha256(path) if exists else "missing"

        unknown = sorted(set(request.values) - set(profile.allowed))
        if unknown:
            return self._result(
                request,
                exists,
                profile.name,
                actual_hash,
                "blocked",
                [
                    {
                        "code": "frontmatter-field-not-allowed",
                        "path": request.path,
                        "field": key,
                    }
                    for key in unknown
                ],
            )

        next_body = self._next_body(request, parsed.body, exists)
        if exists:
            rendered, render_errors = render_patch(
                original,
                {**request.values, "updated": today},
                next_body,
                list(profile.field_order),
            )
            if render_errors:
                return self._result(
                    request,
                    exists,
                    profile.name,
                    actual_hash,
                    "blocked",
                    [{"code": code, "path": request.path} for code in render_errors],
                )
        else:
            rendered = render_document(frontmatter, next_body, list(profile.field_order))
        issues = self._rules.check_content(self._settings.vault_root, path, rendered)
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
        missing = [item for item in issues if item["code"] in missing_codes]
        status = "needs-input" if missing else "blocked" if issues else "planned"
        result = self._result(
            request,
            exists,
            profile.name,
            actual_hash,
            status,
            issues,
            [str(item.get("field") or item.get("detail")) for item in missing],
        )
        if issues or not request.confirm:
            return result
        if request.expected_hash is not None and request.expected_hash != actual_hash:
            return result.model_copy(
                update={
                    "status": "blocked",
                    "issues": [{"code": "concurrent-change", "path": request.path}],
                }
            )

        self._executor.execute(
            FileChangeSet(
                writes=(FileWrite(path, rendered),),
                label="document apply",
                expected={path: None if actual_hash == "missing" else actual_hash},
            )
        )
        return result.model_copy(update={"status": "applied", "write_performed": True})

    def _creation_defaults(self, path: Path, document_type: str, today: str) -> dict[str, Any]:
        prefix = self._settings.document_types["types"][document_type]["prefix"]
        values: dict[str, Any] = {
            "name": path.stem[len(prefix) :] if path.stem.startswith(prefix) else path.stem,
            "type": document_type,
            "status": "current" if document_type == "task" else "draft",
            "created": today,
            "updated": today,
            "tags": [],
        }
        marker_name = self._settings.governance.get("domain_marker", "_领域.md")
        current = path.parent
        while current == self._settings.vault_root or self._settings.vault_root in current.parents:
            marker = current / marker_name
            if marker.is_file():
                domain = parse_document(marker.read_text(encoding="utf-8")).frontmatter
                if domain.get("domain_id"):
                    values["domain"] = domain["domain_id"]
                project = domain.get("project_id") or domain.get("project")
                if project:
                    values["project"] = project
                return values
            if current == self._settings.vault_root:
                break
            current = current.parent
        raise ConfigurationError("正式文档必须位于已声明的 Domain 内")

    @staticmethod
    def _next_body(request: DocumentApplyRequest, current: str, exists: bool) -> str:
        if (
            exists
            and request.body is not None
            and not request.append_section
            and not request.replace_body
        ):
            raise ConfigurationError(
                "更新时 --body-file 必须与 --append-section 或 --replace-body 同时使用"
            )
        if request.append_section:
            if request.body is None:
                raise ConfigurationError("--append-section 必须与 --body-file 同时使用")
            heading = request.append_section.strip().lstrip("#").strip()
            return current.rstrip() + f"\n\n## {heading}\n\n{request.body.strip()}\n"
        if request.replace_body and request.body is not None:
            return request.body
        return current if exists else (request.body or "")

    def _result(
        self,
        request: DocumentApplyRequest,
        exists: bool,
        profile: str,
        expected_hash: str,
        status: str,
        issues: list[dict[str, Any]],
        missing_fields: list[str] | None = None,
    ) -> DocumentApplyResult:
        scope = Path(request.path).parent.as_posix()
        return DocumentApplyResult(
            status=status,
            workspace_id=self._settings.workspace_id,
            action="update" if exists else "create",
            path=request.path,
            profile=profile,
            expected_hash=expected_hash,
            issues=issues,
            missing_fields=missing_fields or [],
            follow_up=maintenance_follow_up(self._settings.workspace_id, [scope]),
        )
