from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from campfire_cli.app.base.schema.operation_schema import (
    CommandFollowUp,
    maintenance_sync_follow_up,
)
from campfire_cli.app.document.schema import (
    DocumentApplyRequest,
    DocumentApplyResult,
)
from campfire_cli.app.document.service.document_patch_values import (
    decode_patch_values,
    enrich_profile_issues,
)
from campfire_cli.app.document.service.document_relocation import prepare_document_relocation
from campfire_cli.app.document.service.document_rule_service import DocumentRuleService
from campfire_cli.app.document.service.profile_candidates import workspace_candidate_sets
from campfire_cli.app.document.service.profile_registry import ProfileRegistry
from campfire_cli.common.documents.document_types import prefixed_name
from campfire_cli.common.documents.domain_context import (
    DomainContext,
    DomainContextError,
    resolve_domain_context,
)
from campfire_cli.common.documents.frontmatter_format import render_patch
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
        project_roots: dict[str, str] | None = None,
    ) -> None:
        self._settings = settings
        self._rules = rules
        self._profiles = profiles
        self._project_roots = project_roots or {}
        self._executor = FileChangeExecutor(settings.vault_root, settings.state_root)

    def apply(self, request: DocumentApplyRequest) -> DocumentApplyResult:
        source = safe_path(self._settings.vault_root, request.path)
        if source.is_dir():
            raise ConfigurationError(
                "document apply 目标不能是目录",
                code="document-path-is-directory",
                path=request.path,
                hint="请提供目标文档名称；创建时可以省略 .md 和类型前缀",
            )
        if not source.suffix:
            source = source.with_name(source.name + ".md")
        elif source.suffix.lower() != ".md":
            raise ConfigurationError(
                "document apply 目标必须是 Markdown 文件",
                code="document-extension-invalid",
                path=request.path,
                expected_suffix=".md",
                hint="请删除其他扩展名；无扩展名时 CLI 会自动补充 .md",
            )
        exists = source.is_file()
        original = source.read_text(encoding="utf-8") if exists else ""
        parsed = parse_document(original)

        current_type = parsed.frontmatter.get("type")
        if "type" in request.values:
            raise GovernanceBlockedError("文档类型只能通过 --type 表达")
        document_type = request.document_type or (
            current_type if isinstance(current_type, str) else None
        )
        if not document_type:
            raise ConfigurationError("创建文档时必须提供 --type")
        if document_type not in self._settings.document_types.get("types", {}):
            raise ConfigurationError(f"未知文档类型：{document_type}")

        changes_type = (
            exists and request.document_type is not None and current_type != document_type
        )
        action = "create" if not exists else "retype" if changes_type else "update"
        target = (
            source.with_name(
                prefixed_name(source.name, document_type, self._settings.document_types)
            )
            if not exists or changes_type
            else source
        )
        target_name = target.relative_to(self._settings.vault_root).as_posix()
        context = self._domain_context(target) if document_type != "human-request" else None
        relative_target = target.relative_to(self._settings.vault_root).as_posix()
        if document_type == "human-request" and not relative_target.startswith(
            "_收件箱/待用户确认/"
        ):
            raise GovernanceBlockedError("human-request 只能创建在 _收件箱/待用户确认/")

        today = date.today().isoformat()
        frontmatter = dict(parsed.frontmatter)
        profile = None
        if not exists or not parsed.has_frontmatter:
            defaults = self._creation_defaults(target, document_type, today)
            profile = self._profiles.resolve(document_type, defaults, target)
            for field in profile.fields:
                if field.default is not None:
                    defaults.setdefault(field.name, field.default)
            frontmatter.update(defaults)
        profile = profile or self._profiles.resolve(document_type, frontmatter, target)
        removed_fields: tuple[str, ...] = ()
        if changes_type and isinstance(current_type, str):
            previous_profile = self._profiles.resolve(current_type, parsed.frontmatter, source)
            removed_fields = tuple(
                field
                for field in previous_profile.allowed
                if field not in profile.allowed and field in frontmatter
            )
            for field in removed_fields:
                frontmatter.pop(field, None)
        actual_hash = file_sha256(source) if exists else "missing"
        unknown = sorted(set(request.values) - set(profile.allowed))
        if unknown:
            return self._result(
                request,
                target_name,
                action,
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

        values, input_issues = decode_patch_values(
            profile,
            request.values,
            request.path,
            workspace_candidate_sets(self._settings.vault_root),
        )
        if input_issues:
            return self._result(
                request,
                target_name,
                action,
                profile.name,
                actual_hash,
                "blocked",
                input_issues,
            )
        # Field semantics are fully declared by the selected Profile; no type-specific injection.
        frontmatter.update(values)
        frontmatter["type"] = document_type
        frontmatter["updated"] = today

        next_body = parsed.body if exists else ""
        if exists and parsed.has_frontmatter:
            patch = {**values, "updated": today}
            if changes_type:
                patch["type"] = document_type
            rendered, render_errors = render_patch(
                original,
                patch,
                next_body,
                list(profile.field_order),
                removed_fields,
            )
            if render_errors:
                return self._result(
                    request,
                    target_name,
                    action,
                    profile.name,
                    actual_hash,
                    "blocked",
                    [{"code": code, "path": request.path} for code in render_errors],
                )
        else:
            rendered = render_document(frontmatter, next_body, list(profile.field_order))
        issues = self._rules.check_content(self._settings.vault_root, target, rendered, profile)
        if target != source and target.exists():
            issues.insert(0, {"code": "target-exists", "path": target_name})
        enrich_profile_issues(issues, profile, workspace_candidate_sets(self._settings.vault_root))
        missing_codes = {"frontmatter-field-missing", "frontmatter-field-empty"}
        missing = [item for item in issues if item["code"] in missing_codes]
        status = "needs-input" if missing else "blocked" if issues else "planned"
        result = self._result(
            request,
            target_name,
            action,
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

        updated_references: list[str] = []
        if exists and target != source:
            writes, updated_references, expected = prepare_document_relocation(
                self._settings.vault_root, source, target, rendered
            )
            expected[source] = actual_hash
            expected[target] = None
            change_set = FileChangeSet(
                writes=tuple(writes),
                deletes=(source,),
                label="document apply",
                expected=expected,
            )
        else:
            change_set = FileChangeSet(
                writes=(FileWrite(target, rendered),),
                label="document apply",
                expected={target: None if not exists else actual_hash},
            )
        self._executor.execute(change_set)
        return result.model_copy(
            update={
                "status": "applied",
                "write_performed": True,
                "updated_references": updated_references,
                "follow_up": self._follow_up(
                    request,
                    exists,
                    parsed.has_frontmatter,
                    context,
                    changes_type,
                ),
            }
        )

    def _creation_defaults(
        self,
        path: Path,
        document_type: str,
        today: str,
    ) -> dict[str, Any]:
        prefix = self._settings.document_types["types"][document_type]["prefix"]
        values: dict[str, Any] = {
            "name": path.stem[len(prefix) :] if path.stem.startswith(prefix) else path.stem,
            "type": document_type,
            "document_status": "current" if document_type == "task" else "draft",
            "created": today,
            "updated": today,
            "tags": [],
        }
        return values

    def _result(
        self,
        request: DocumentApplyRequest,
        target: str,
        action: str,
        profile: str,
        expected_hash: str,
        status: str,
        issues: list[dict[str, Any]],
        missing_fields: list[str] | None = None,
    ) -> DocumentApplyResult:
        return DocumentApplyResult(
            status=status,
            workspace_id=self._settings.workspace_id,
            action=action,
            path=request.path,
            requested_path=request.path,
            target=target,
            normalization=self._normalization(request, target),
            profile=profile,
            expected_hash=expected_hash,
            issues=issues,
            missing_fields=missing_fields or [],
        )

    def _normalization(self, request: DocumentApplyRequest, target: str) -> list[dict[str, str]]:
        actions: list[dict[str, str]] = []
        requested = Path(request.path)
        normalized_request = requested
        if not requested.suffix:
            normalized_request = requested.with_name(requested.name + ".md")
            actions.append({"reason": "markdown-extension", "required_suffix": ".md"})
        if request.document_type is not None and Path(target).name != normalized_request.name:
            actions.append(
                {
                    "reason": "document-type-prefix",
                    "document_type": request.document_type,
                    "required_prefix": self._settings.document_types["types"][
                        request.document_type
                    ]["prefix"],
                }
            )
        return actions

    def _follow_up(
        self,
        request: DocumentApplyRequest,
        exists: bool,
        had_frontmatter: bool,
        context: DomainContext | None,
        changes_type: bool,
    ) -> list[CommandFollowUp]:
        derived_fields = {
            "name",
            "type",
            "document_status",
            "task_status",
            "related_project",
        }
        needs_sync = not exists or not had_frontmatter
        needs_sync = needs_sync or bool(set(request.values) & derived_fields)
        needs_sync = needs_sync or changes_type
        if context is None:
            return []
        return (
            maintenance_sync_follow_up(
                self._settings.workspace_id,
                [context.root.relative_to(self._settings.vault_root).as_posix()],
            )
            if needs_sync
            else []
        )

    def _domain_context(self, path: Path) -> DomainContext:
        try:
            return resolve_domain_context(
                self._settings.vault_root,
                path,
                self._project_roots,
                self._settings.governance.get("domain_marker", "_领域.md"),
            )
        except DomainContextError as exc:
            raise exc
