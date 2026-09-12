from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from campfire_cli.app.document.service import frontmatter_plan, type_apply, type_plan
from campfire_cli.app.document.service.document_rule_service import DocumentRuleService
from campfire_cli.app.document.service.document_scanner import iter_documents
from campfire_cli.app.document.service.frontmatter_formatter import format_text
from campfire_cli.app.document.service.profile_registry import ProfileRegistry
from campfire_cli.app.maintenance.schema.maintenance_schema import (
    Issue,
    MaintenanceIntentSpec,
    MaintenancePlan,
    MaintenancePlanItem,
    MaintenanceResult,
)
from campfire_cli.app.maintenance.service.maintenance_protocol import (
    MaintenanceRepositoryProtocol,
)
from campfire_cli.common.documents.document_types import prefixed_name, set_frontmatter_scalar
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.exceptions import GovernanceBlockedError
from campfire_cli.common.filesystem import atomic_write, safe_path
from campfire_cli.common.filesystem.locking import workspace_write_lock
from campfire_cli.common.governance import enrich_issue
from campfire_cli.common.hashing import file_sha256, text_sha256
from campfire_cli.config.settings import WorkspaceSettings


class MaintenancePlanService:
    """Create and execute one auditable, scope-bound document maintenance plan."""

    def __init__(
        self, settings: WorkspaceSettings, repository: MaintenanceRepositoryProtocol
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._rules = DocumentRuleService(settings.document_types, settings.frontmatter_schema)
        self._profiles = ProfileRegistry(settings.document_types, settings.frontmatter_schema)

    def plan(
        self,
        plan_id: str,
        *,
        scope: str | None = None,
        spec_path: Path | None = None,
    ) -> MaintenanceResult:
        paths = self._scoped_documents(scope)
        if spec_path is not None:
            return self._plan_from_spec(plan_id, scope, spec_path, paths)
        type_items = {
            item["source"]: item
            for item in type_plan.build_plan(
                self._settings.vault_root, self._settings.document_types
            )["items"]
        }
        metadata_items = {
            item["path"]: item
            for item in frontmatter_plan.build_plan(
                self._settings.vault_root,
                self._settings.document_types,
                self._settings.frontmatter_schema,
            )["items"]
        }
        items: list[MaintenancePlanItem] = []
        for path in paths:
            relative = path.relative_to(self._settings.vault_root).as_posix()
            type_item = type_items.get(relative)
            metadata_item = metadata_items.get(relative)
            patch = {
                field: proposal["value"]
                for field, proposal in (metadata_item or {}).get("fields", {}).items()
                if proposal.get("value") is not None
            }
            if type_item and type_item.get("proposed_type"):
                patch["type"] = type_item["proposed_type"]
            text = path.read_text(encoding="utf-8")
            parsed = parse_document(text)
            profile = self._profiles.resolve(
                parsed.frontmatter.get("type"), parsed.frontmatter, path
            )
            formatted, format_errors = format_text(text, list(profile.field_order))
            needs_format = not format_errors and formatted != text
            if not type_item and not metadata_item and not needs_format:
                continue
            reasons = [
                value
                for value in (
                    type_item.get("reason") if type_item else None,
                    "missing-frontmatter-fields" if metadata_item else None,
                    "frontmatter-field-order" if needs_format else None,
                )
                if value
            ]
            items.append(
                MaintenancePlanItem(
                    source=relative,
                    target=type_item["target"] if type_item else relative,
                    source_sha256=file_sha256(path),
                    frontmatter=patch,
                    format_frontmatter=needs_format or bool(patch),
                    reason=", ".join(reasons),
                )
            )
        plan = MaintenancePlan(
            plan_id=plan_id,
            scope=scope,
            config_hash=self._config_hash(),
            items=items,
        )
        self._repository.save_plan(plan)
        return self._plan_result(plan)

    def show(self, plan_id: str) -> MaintenanceResult:
        return self._plan_result(self._repository.load_plan(plan_id))

    def apply(self, plan_id: str, confirm: bool) -> MaintenanceResult:
        plan = self._repository.load_plan(plan_id)
        approved = [item for item in plan.items if item.approved]
        unapproved = [item for item in plan.items if not item.approved]
        if unapproved:
            issues = [
                Issue.model_validate(
                    enrich_issue(
                        {
                            "code": "maintenance-item-unapproved",
                            "path": item.source,
                            "detail": item.reason,
                        }
                    )
                )
                for item in unapproved
            ]
            return MaintenanceResult(
                status="blocked",
                document_count=len(plan.items),
                issue_count=len(issues),
                issues=issues,
                operations=[item.model_dump(mode="json") for item in plan.items],
            )
        issues = self._preflight(plan, approved)
        if issues or not confirm:
            return MaintenanceResult(
                status="blocked" if issues else "ready",
                document_count=len(approved),
                issue_count=len(issues),
                issues=[Issue.model_validate(enrich_issue(item)) for item in issues],
                operations=[item.model_dump(mode="json") for item in approved],
            )
        with workspace_write_lock(self._settings.state_root):
            locked_issues = self._preflight(plan, approved)
            if locked_issues:
                return MaintenanceResult(
                    status="blocked",
                    document_count=len(approved),
                    issue_count=len(locked_issues),
                    issues=[Issue.model_validate(enrich_issue(item)) for item in locked_issues],
                )
            self._apply_items(approved)
        return MaintenanceResult(
            status="applied",
            document_count=len(approved),
            issue_count=0,
            changed_document_count=len(approved),
            write_performed=bool(approved),
            operations=[item.model_dump(mode="json") for item in approved],
        )

    def verify(self, plan_id: str) -> MaintenanceResult:
        plan = self._repository.load_plan(plan_id)
        raw_issues: list[dict[str, Any]] = []
        approved = [item for item in plan.items if item.approved]
        for item in approved:
            source = safe_path(self._settings.vault_root, item.source)
            target = safe_path(self._settings.vault_root, item.target)
            if not target.is_file():
                raw_issues.append({"code": "maintenance-target-missing", "path": item.target})
                continue
            if source != target and source.exists():
                raw_issues.append({"code": "maintenance-source-still-exists", "path": item.source})
            raw_issues.extend(self._rules.check_document(self._settings.vault_root, target))
        issues = [Issue.model_validate(enrich_issue(item)) for item in raw_issues]
        return MaintenanceResult(
            status="ok" if not issues else "needs-review",
            document_count=len(approved),
            issue_count=len(issues),
            issues=issues,
            issue_counts=self._issue_counts(issues),
            operations=[item.model_dump(mode="json") for item in approved],
        )

    def _plan_from_spec(
        self,
        plan_id: str,
        scope: str | None,
        spec_path: Path,
        paths: list[Path],
    ) -> MaintenanceResult:
        if not spec_path.is_file():
            return self._blocked_issue("maintenance-spec-missing", str(spec_path))
        try:
            spec = MaintenanceIntentSpec.model_validate(
                yaml.safe_load(spec_path.read_text(encoding="utf-8"))
            )
        except Exception as exc:
            return self._blocked_issue("maintenance-spec-invalid", str(spec_path), str(exc))
        allowed = {path.relative_to(self._settings.vault_root).as_posix() for path in paths}
        items: list[MaintenancePlanItem] = []
        raw_issues: list[dict[str, Any]] = []
        targets: set[str] = set()
        for intent in spec.operations:
            if intent.path not in allowed:
                raw_issues.append({"code": "maintenance-path-outside-scope", "path": intent.path})
                continue
            source = safe_path(self._settings.vault_root, intent.path)
            parsed = parse_document(source.read_text(encoding="utf-8"))
            raw_issues.extend(
                self._rules.validate_patch(
                    self._settings.vault_root,
                    source,
                    parsed.frontmatter,
                    intent.frontmatter,
                )
            )
            document_type = intent.frontmatter.get("type", parsed.frontmatter.get("type"))
            target_name = intent.filename
            if target_name is not None and Path(target_name).name != target_name:
                raw_issues.append({"code": "maintenance-filename-invalid", "path": intent.path})
                continue
            if target_name is None and isinstance(document_type, str):
                target_name = prefixed_name(
                    source.name, document_type, self._settings.document_types
                )
            target = source.with_name(target_name or source.name)
            target_relative = target.relative_to(self._settings.vault_root).as_posix()
            if target_relative in targets:
                raw_issues.append({"code": "maintenance-target-duplicate", "path": target_relative})
            targets.add(target_relative)
            items.append(
                MaintenancePlanItem(
                    source=intent.path,
                    target=target_relative,
                    source_sha256=file_sha256(source),
                    frontmatter=intent.frontmatter,
                    format_frontmatter=intent.format_frontmatter,
                    reason=intent.reason,
                    approved=intent.approved,
                )
            )
        if raw_issues:
            issues = [Issue.model_validate(enrich_issue(item)) for item in raw_issues]
            return MaintenanceResult(
                status="blocked",
                document_count=len(items),
                issue_count=len(issues),
                issues=issues,
                issue_counts=self._issue_counts(issues),
                scope=scope,
            )
        plan = MaintenancePlan(
            plan_id=plan_id,
            scope=scope,
            config_hash=self._config_hash(),
            items=items,
        )
        self._repository.save_plan(plan)
        return self._plan_result(plan)

    def _preflight(
        self, plan: MaintenancePlan, items: list[MaintenancePlanItem]
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        if plan.config_hash != self._config_hash():
            issues.append({"code": "maintenance-config-changed", "path": plan.plan_id})
        targets: set[Path] = set()
        for item in items:
            source = safe_path(self._settings.vault_root, item.source)
            target = safe_path(self._settings.vault_root, item.target)
            if not source.is_file():
                issues.append({"code": "maintenance-source-missing", "path": item.source})
                continue
            if file_sha256(source) != item.source_sha256:
                issues.append({"code": "concurrent-change", "path": item.source})
            if source.parent != target.parent:
                issues.append(
                    {
                        "code": "maintenance-cross-domain-move",
                        "path": item.source,
                        "detail": item.target,
                    }
                )
            if target in targets:
                issues.append({"code": "maintenance-target-duplicate", "path": item.target})
            if target != source and target.exists():
                issues.append({"code": "maintenance-target-exists", "path": item.target})
            targets.add(target)
            parsed = parse_document(source.read_text(encoding="utf-8"))
            issues.extend(
                self._rules.validate_patch(
                    self._settings.vault_root,
                    source,
                    parsed.frontmatter,
                    item.frontmatter,
                )
            )
            document_type = item.frontmatter.get("type", parsed.frontmatter.get("type"))
            if target != source:
                if document_type not in self._settings.document_types.get("types", {}):
                    issues.append({"code": "maintenance-type-required", "path": item.source})
                elif target.name != prefixed_name(
                    source.name, document_type, self._settings.document_types
                ):
                    issues.append(
                        {
                            "code": "maintenance-target-invalid",
                            "path": item.source,
                            "detail": target.name,
                        }
                    )
        return issues

    def _apply_items(self, items: list[MaintenancePlanItem]) -> None:
        type_operations: list[dict[str, Any]] = []
        for item in items:
            source = safe_path(self._settings.vault_root, item.source)
            current = parse_document(source.read_text(encoding="utf-8")).frontmatter
            document_type = item.frontmatter.get("type", current.get("type"))
            if item.target != item.source or "type" in item.frontmatter:
                type_operations.append(
                    {
                        "source": source,
                        "target": safe_path(self._settings.vault_root, item.target),
                        "type": document_type,
                    }
                )
        if type_operations:
            type_apply.apply_plan(self._settings.vault_root, type_operations)
        for item in items:
            target = safe_path(self._settings.vault_root, item.target)
            original = target.read_text(encoding="utf-8")
            updated = original
            for field, value in item.frontmatter.items():
                updated = set_frontmatter_scalar(updated, field, self._render_value(value))
            if item.format_frontmatter:
                parsed = parse_document(updated)
                profile = self._profiles.resolve(
                    parsed.frontmatter.get("type"), parsed.frontmatter, target
                )
                updated, errors = format_text(updated, list(profile.field_order))
                if errors:
                    raise GovernanceBlockedError(
                        f"Frontmatter 无法格式化：{item.target}: {', '.join(errors)}"
                    )
            if updated != original:
                atomic_write(target, updated)

    def _scoped_documents(self, scope: str | None) -> list[Path]:
        paths = iter_documents(self._settings.vault_root, self._settings.document_types)
        if scope is None:
            return paths
        scope_path = safe_path(self._settings.vault_root, scope)
        if not scope_path.exists():
            raise GovernanceBlockedError(f"Maintenance Scope 不存在：{scope}")
        return [path for path in paths if path == scope_path or scope_path in path.parents]

    def _config_hash(self) -> str:
        payload = {
            "document_types": self._settings.document_types,
            "frontmatter_schema": self._settings.frontmatter_schema,
        }
        return text_sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    @staticmethod
    def _render_value(value: object) -> str:
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, list):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @staticmethod
    def _plan_result(plan: MaintenancePlan) -> MaintenanceResult:
        return MaintenanceResult(
            status="planned",
            document_count=len(plan.items),
            issue_count=0,
            scope=plan.scope,
            operations=[item.model_dump(mode="json") for item in plan.items],
        )

    @staticmethod
    def _blocked_issue(code: str, path: str, detail: str = "") -> MaintenanceResult:
        issue = Issue.model_validate(enrich_issue({"code": code, "path": path, "detail": detail}))
        return MaintenanceResult(
            status="blocked",
            document_count=0,
            issue_count=1,
            issues=[issue],
            issue_counts={code: 1},
        )

    @staticmethod
    def _issue_counts(issues: list[Issue]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for issue in issues:
            counts[issue.code] = counts.get(issue.code, 0) + 1
        return dict(sorted(counts.items()))
