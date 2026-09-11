from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from campfire_cli.app.maintenance.schema.maintenance_schema import (
    DocumentState,
    Issue,
    MaintenanceResult,
    MaintenanceRunRecord,
)
from campfire_cli.app.maintenance.service.maintenance_protocol import (
    MaintenanceRepositoryProtocol,
)
from campfire_cli.common.archive import planner as project_archive
from campfire_cli.common.documents import (
    document_type_apply,
    document_type_plan,
    frontmatter_apply,
    frontmatter_plan,
)
from campfire_cli.common.documents import (
    domains as governance_check,
)
from campfire_cli.common.documents import (
    moc as governance_sync,
)
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.filesystem import atomic_write
from campfire_cli.common.filesystem.locking import workspace_write_lock
from campfire_cli.common.governance import (
    GovernanceRuleEngine,
    capture_snapshot,
    enrich_issue,
    filter_issues,
    snapshot_changes,
)
from campfire_cli.common.hashing import file_sha256, text_sha256
from campfire_cli.common.reports.json_report import render_json_report
from campfire_cli.common.reports.markdown_report import render_maintenance_report
from campfire_cli.config.settings import WorkspaceSettings


class MaintenanceService:
    def __init__(
        self, settings: WorkspaceSettings, repository: MaintenanceRepositoryProtocol
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._rules = GovernanceRuleEngine(settings.document_types, settings.frontmatter_schema)

    def check(
        self,
        *,
        scope: str | None = None,
        code: str | None = None,
        severity: str | None = None,
        summary: bool = False,
    ) -> MaintenanceResult:
        documents: list[DocumentState] = []
        issues: list[Issue] = []
        paths = self._iter_documents()
        for path in paths:
            relative = path.relative_to(self._settings.vault_root).as_posix()
            text = path.read_text(encoding="utf-8")
            parsed = parse_document(text)
            document_type = parsed.frontmatter.get("type")
            documents.append(
                DocumentState(
                    path=relative,
                    content_hash=file_sha256(path),
                    document_type=document_type if isinstance(document_type, str) else None,
                    domain_id=self._nearest_domain(path),
                    status=parsed.frontmatter.get("status"),
                )
            )
            issues.extend(
                Issue.model_validate(enrich_issue(item))
                for item in self._rules.check_document(self._settings.vault_root, path)
            )
        issues.extend(Issue.model_validate(enrich_issue(item)) for item in self._check_inbox())
        for skills_root in self._settings.skill_targets():
            issues.extend(
                Issue.model_validate(enrich_issue(item))
                for item in self._rules.check_templates(skills_root.parent, skills_root)
            )
        issues = list({(item.path, item.code, item.detail): item for item in issues}.values())
        result = MaintenanceResult(
            status="ok" if not issues else "needs-review",
            document_count=len(documents),
            issue_count=len(issues),
            total_issue_count=len(issues),
            issues=issues,
            issue_counts=self._issue_counts(issues),
        )
        completed_at = datetime.now(UTC)
        run = MaintenanceRunRecord(
            run_id=str(uuid4()),
            status=result.status,
            scanned_count=result.document_count,
            issue_count=result.issue_count,
            started_at=completed_at,
            finished_at=completed_at,
        )
        observed = {document.path: document.content_hash for document in documents}
        with workspace_write_lock(self._settings.state_root):
            changed = snapshot_changes(self._settings.vault_root, observed)
            if changed:
                return self._concurrent_result(changed)
            self._repository.replace_current_state(documents, issues)
            self._repository.save_run(run)
            self._export_current_report(result, completed_at)
        selected = filter_issues(
            (item.model_dump() for item in issues), scope=scope, code=code, severity=severity
        )
        selected_issues = [Issue.model_validate(item) for item in selected]
        return MaintenanceResult(
            status=result.status,
            document_count=len(documents),
            issue_count=len(selected_issues),
            total_issue_count=len(issues),
            issues=[] if summary else selected_issues,
            issue_counts=self._issue_counts(selected_issues),
        )

    def _export_current_report(self, result: MaintenanceResult, exported_at: datetime) -> None:
        payload = result.model_dump(mode="json")
        payload["exported_at"] = exported_at.isoformat()
        report_root = self._settings.state_root / "reports"
        atomic_write(report_root / "current.json", render_json_report(payload))
        atomic_write(report_root / "current.md", render_maintenance_report(payload))

    def plan(self) -> MaintenanceResult:
        paths = self._iter_documents()
        snapshot = capture_snapshot(self._settings.vault_root, paths)
        type_plan = document_type_plan.build_plan(
            self._settings.vault_root, self._settings.document_types
        )
        metadata_plan = frontmatter_plan.build_plan(
            self._settings.vault_root,
            self._settings.document_types,
            self._settings.frontmatter_schema,
        )
        changed = snapshot_changes(self._settings.vault_root, snapshot)
        if changed:
            return self._concurrent_result(changed)
        payload = {
            "schema_version": 1,
            "document_types": type_plan,
            "frontmatter": metadata_plan,
            "snapshot": snapshot,
        }
        target = self._settings.state_root / "maintenance" / "current-plan.json"
        atomic_write(target, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        count = len(type_plan["items"]) + len(metadata_plan["items"])
        return MaintenanceResult(status="planned", document_count=count, issue_count=0)

    def apply(self, confirm: bool) -> MaintenanceResult:
        plan_path = self._settings.state_root / "maintenance" / "current-plan.json"
        if not plan_path.is_file():
            return MaintenanceResult(
                status="blocked",
                document_count=0,
                issue_count=1,
                issues=[
                    Issue.model_validate(
                        enrich_issue({"code": "maintenance-plan-missing", "path": str(plan_path)})
                    )
                ],
            )
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
        type_ops, type_issues = document_type_apply.preflight(
            self._settings.vault_root,
            payload["document_types"],
            self._settings.document_types,
        )
        metadata_ops, metadata_issues = frontmatter_apply.preflight(
            self._settings.vault_root,
            payload["frontmatter"],
            self._settings.frontmatter_schema,
        )
        issues = [*type_issues, *metadata_issues]
        if issues or not confirm:
            return MaintenanceResult(
                status="blocked" if issues else "ready",
                document_count=len(type_ops) + len(metadata_ops),
                issue_count=len(issues),
                issues=[Issue.model_validate(enrich_issue(item)) for item in issues],
            )
        with workspace_write_lock(self._settings.state_root):
            changed = snapshot_changes(self._settings.vault_root, payload.get("snapshot", {}))
            if changed:
                return self._concurrent_result(changed)
            type_result = document_type_apply.apply_plan(self._settings.vault_root, type_ops)
            changed_metadata = frontmatter_apply.apply(metadata_ops)
        return MaintenanceResult(
            status="applied",
            document_count=len(type_ops) + len(metadata_ops),
            issue_count=0,
            changed_document_count=type_result["applied_count"] + changed_metadata,
        )

    def sync(self, dry_run: bool = False) -> MaintenanceResult:
        snapshot = capture_snapshot(self._settings.vault_root, self._iter_documents())
        domains, issues = governance_check.discover_domains(
            self._settings.vault_root,
            self._settings.governance,
            self._settings.document_types,
            self._settings.frontmatter_schema,
        )
        if issues:
            return MaintenanceResult(
                status="blocked",
                document_count=0,
                issue_count=len(issues),
                issues=[Issue.model_validate(enrich_issue(item)) for item in issues],
            )
        marker_name = self._settings.governance.get("domain_marker", "_领域.md")
        profile = self._settings.document_types.get("profiles", {}).get("project-docs", [])
        type_mapping = {
            name: self._settings.document_types["types"][name]["prefix"]
            for name in profile
            if name in self._settings.document_types["types"]
        }
        changes: list[tuple[Path, str]] = []
        generated_snapshot: dict[str, str | None] = {}
        note_count = 0
        notes_by_domain = {
            domain.domain_id: governance_sync.direct_notes(domain, marker_name)
            for domain in domains
        }
        project_domain_ids = {
            domain.domain_id for domain in domains if domain.governance == "project-docs"
        }
        domain_by_note = {
            note: domain_id
            for domain_id, notes in notes_by_domain.items()
            for note in notes
            if domain_id not in project_domain_ids
        }
        all_notes = sorted(
            domain_by_note,
            key=lambda path: str(path.relative_to(self._settings.vault_root)).casefold(),
        )
        all_relations = governance_sync.generate_relations(
            all_notes,
            domain_by_note,
            self._settings.vault_root,
            int(self._settings.governance.get("related_limit", 3)),
            float(self._settings.governance.get("related_min_score", 0.08)),
            int(self._settings.governance.get("cross_domain_related_limit", 2)),
            float(self._settings.governance.get("cross_domain_min_score", 0.06)),
        )
        for domain in sorted(domains, key=lambda item: item.domain_id):
            notes = notes_by_domain[domain.domain_id]
            note_count += len(notes)
            if domain.governance == "project-docs":
                generated = governance_sync.generate_project_domain_content(
                    domain, domains, notes, marker_name, type_mapping
                )
            else:
                relation_page = None
                if notes:
                    relations = {note: all_relations[note] for note in notes}
                    relation_page = domain.path / "generated" / f"相关文档-{domain.name}.md"
                    relation_content = governance_sync.relation_markdown(domain, notes, relations)
                    existing = (
                        relation_page.read_text(encoding="utf-8") if relation_page.is_file() else ""
                    )
                    generated_snapshot[
                        relation_page.relative_to(self._settings.vault_root).as_posix()
                    ] = text_sha256(existing) if relation_page.is_file() else None
                    if existing != relation_content:
                        changes.append((relation_page, relation_content))
                generated = governance_sync.generate_domain_content(
                    domain, domains, notes, relation_page
                )
            moc = domain.path / f"{domain.moc_name}.md"
            if not moc.is_file():
                return MaintenanceResult(
                    status="blocked",
                    document_count=note_count,
                    issue_count=1,
                    issues=[
                        Issue.model_validate(
                            enrich_issue(
                                {
                                    "code": "moc-missing",
                                    "path": moc.relative_to(self._settings.vault_root).as_posix(),
                                }
                            )
                        )
                    ],
                )
            current_moc = moc.read_text(encoding="utf-8")
            generated_snapshot[moc.relative_to(self._settings.vault_root).as_posix()] = text_sha256(
                current_moc
            )
            updated = governance_sync.replace_generated_region(current_moc, generated)
            if updated != current_moc:
                changes.append((moc, updated))
        operations = [
            {
                "action": "update" if path.is_file() else "create",
                "path": path.relative_to(self._settings.vault_root).as_posix(),
                "reason": "refresh-generated-content",
            }
            for path, _content in changes
        ]
        for path, expected in generated_snapshot.items():
            snapshot.setdefault(path, expected)
        if not dry_run and changes:
            with workspace_write_lock(self._settings.state_root):
                changed = snapshot_changes(self._settings.vault_root, snapshot)
                if changed:
                    return self._concurrent_result(changed)
                for path, content in changes:
                    atomic_write(path, content)
        return MaintenanceResult(
            status="dry-run" if dry_run else "synced",
            document_count=note_count,
            issue_count=0,
            generated_file_count=len(changes),
            operations=operations,
        )

    def archive(self, confirm: bool = False) -> MaintenanceResult:
        items, raw_issues = project_archive.collect_items(
            self._settings.vault_root, self._settings.governance
        )
        applied: list[dict[str, str]] = []
        if confirm and items:
            snapshot = capture_snapshot(
                self._settings.vault_root,
                [path for item in items for path in (item.source, item.target)],
            )
            with workspace_write_lock(self._settings.state_root):
                changed = snapshot_changes(self._settings.vault_root, snapshot)
                if changed:
                    return self._concurrent_result(changed)
                applied = project_archive.apply_items(
                    self._settings.vault_root,
                    items,
                    raw_issues,
                    __import__("datetime").date.today().isoformat(),
                )
        issues = [Issue.model_validate(enrich_issue(item)) for item in raw_issues]
        return MaintenanceResult(
            status="issues-found" if issues else ("applied" if confirm else "ok"),
            document_count=len(items),
            issue_count=len(issues),
            issues=issues,
            issue_counts=self._issue_counts(issues),
            changed_document_count=len(applied),
            operations=applied,
        )

    def _iter_documents(self) -> list[Path]:
        config = self._settings.document_types
        ignored = set(config.get("ignored_directories", []))
        exempt = set(config.get("exempt_basenames", []))
        result: list[Path] = []
        for raw_root in config.get("scope_roots", []):
            root = self._settings.vault_root / raw_root
            if not root.is_dir():
                continue
            result.extend(
                path
                for path in root.rglob("*.md")
                if path.name not in exempt
                and not any(part in ignored for part in path.relative_to(root).parts[:-1])
            )
        return sorted(set(result), key=lambda item: item.as_posix().casefold())

    def _nearest_domain(self, path: Path) -> str | None:
        current = path.parent
        while current == self._settings.vault_root or self._settings.vault_root in current.parents:
            marker = current / "_领域.md"
            if marker.is_file():
                parsed = parse_document(marker.read_text(encoding="utf-8"))
                value = parsed.frontmatter.get("domain_id")
                return value if isinstance(value, str) else None
            if current == self._settings.vault_root:
                break
            current = current.parent
        return None

    def _check_inbox(self) -> list[Issue]:
        inbox = self._settings.vault_root / self._settings.governance.get("inbox", "_收件箱")
        if not inbox.is_dir():
            return [Issue(code="inbox-missing", path=inbox.name)]
        return []

    @staticmethod
    def _issue_counts(issues: list[Issue]) -> dict[str, int]:
        result: dict[str, int] = {}
        for issue in issues:
            result[issue.code] = result.get(issue.code, 0) + 1
        return dict(sorted(result.items()))

    @staticmethod
    def _concurrent_result(paths: list[str]) -> MaintenanceResult:
        issues = [
            Issue.model_validate(enrich_issue({"code": "concurrent-change", "path": path}))
            for path in paths
        ]
        return MaintenanceResult(
            status="blocked",
            document_count=0,
            issue_count=len(issues),
            issues=issues,
            issue_counts=MaintenanceService._issue_counts(issues),
        )
