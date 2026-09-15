from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from campfire_cli.app.document.service.document_rule_service import DocumentRuleService
from campfire_cli.app.document.service.document_scanner import iter_documents
from campfire_cli.app.maintenance.schema.maintenance_schema import (
    DocumentState,
    DomainState,
    Issue,
    MaintenanceResult,
    MaintenanceRunRecord,
    SpaceState,
)
from campfire_cli.app.maintenance.service import archive_service as project_archive
from campfire_cli.app.maintenance.service import moc_service as governance_sync
from campfire_cli.app.maintenance.service.maintenance_protocol import (
    MaintenanceRepositoryProtocol,
)
from campfire_cli.app.workspace.service.structure_service import DomainService
from campfire_cli.common.documents.domain_context import (
    DomainContextError,
    resolve_domain_context,
)
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.exceptions import GovernanceBlockedError
from campfire_cli.common.filesystem import (
    FileChangeExecutor,
    FileChangeSet,
    FileWrite,
    atomic_write,
    safe_path,
)
from campfire_cli.common.governance import (
    capture_snapshot,
    enrich_issue,
    filter_issues,
    optimistic_write_lock,
)
from campfire_cli.common.hashing import file_sha256
from campfire_cli.common.reports.json_report import render_json_report
from campfire_cli.common.reports.markdown_report import render_maintenance_report
from campfire_cli.config.settings import WorkspaceSettings


class MaintenanceService:
    def __init__(
        self, settings: WorkspaceSettings, repository: MaintenanceRepositoryProtocol
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._rules = DocumentRuleService(settings.document_types, settings.frontmatter_schema)
        self._executor = FileChangeExecutor(settings.vault_root, settings.state_root)

    def check(
        self,
        *,
        scope: str | None = None,
        code: str | None = None,
        severity: str | None = None,
        summary: bool = False,
    ) -> MaintenanceResult:
        structure = DomainService(self._settings.vault_root, self._settings.state_root)
        discovered_domains, _domain_issues = structure.discover()
        discovered_spaces, _space_issues = structure.spaces.discover()
        spaces, domains = self._topology_states(discovered_spaces, discovered_domains)
        documents: list[DocumentState] = []
        issues: list[Issue] = []
        paths = self._iter_documents()
        for path in paths:
            documents.append(self._document_state(path))
            issues.extend(
                Issue.model_validate(enrich_issue(item))
                for item in self._rules.check_document(self._settings.vault_root, path)
            )
        issues.extend(
            Issue.model_validate(enrich_issue(item))
            for item in self._rules.check_collection(self._settings.vault_root, paths)
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
            space_count=len(spaces),
            domain_count=len(domains),
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
        observed.update({f"{item.path}/_空间.md": item.source_hash for item in spaces})
        observed.update({f"{item.path}/_领域.md": item.source_hash for item in domains})
        with optimistic_write_lock(
            self._settings.state_root, observed, self._settings.vault_root
        ) as changed:
            if changed:
                return self._concurrent_result(changed)
            self._repository.replace_current_state(documents, issues, spaces, domains)
            self._repository.save_run(run)
            self._export_current_report(result, completed_at)
        selected = filter_issues(
            (item.model_dump() for item in issues), scope=scope, code=code, severity=severity
        )
        selected_issues = [Issue.model_validate(item) for item in selected]
        scoped_documents = [
            item
            for item in documents
            if scope is None or self._path_matches_scope(item.path, scope)
        ]
        return MaintenanceResult(
            status="ok" if not selected_issues else "needs-review",
            document_count=len(scoped_documents),
            issue_count=len(selected_issues),
            total_issue_count=len(issues),
            issues=[] if summary else selected_issues,
            issue_counts=self._issue_counts(selected_issues),
            scope=scope,
            workspace_status=result.status,
            space_count=len(spaces),
            domain_count=len(domains),
        )

    def _export_current_report(self, result: MaintenanceResult, exported_at: datetime) -> None:
        payload = result.model_dump(mode="json")
        payload["exported_at"] = exported_at.isoformat()
        report_root = self._settings.state_root / "reports"
        atomic_write(report_root / "current.json", render_json_report(payload))
        atomic_write(report_root / "current.md", render_maintenance_report(payload))

    def sync(self, dry_run: bool = False, scope: str | None = None) -> MaintenanceResult:
        domains, issues = DomainService(
            self._settings.vault_root, self._settings.state_root
        ).discover()
        if scope:
            scope_path = (self._settings.vault_root / scope).resolve()
            if not self._is_within_workspace(scope_path):
                return self._sync_blocked("scope-outside-workspace", scope, scope)
            domains = [
                domain
                for domain in domains
                if domain.path == scope_path or scope_path in domain.path.parents
            ]
            issues = [issue for issue in issues if self._path_matches_scope(issue["path"], scope)]
            if not domains and not scope_path.exists():
                return self._sync_blocked("scope-missing", scope, scope)
        if issues:
            return MaintenanceResult(
                status="blocked",
                document_count=0,
                issue_count=len(issues),
                issues=[Issue.model_validate(enrich_issue(item)) for item in issues],
                blocked_phase="preflight",
                blocked_scope=scope or "workspace",
            )
        scoped_documents = iter_documents(
            self._settings.vault_root,
            self._settings.document_types,
            (domain.path for domain in domains),
        )
        snapshot = capture_snapshot(self._settings.vault_root, scoped_documents)
        marker_name = self._settings.governance.get("domain_marker", "_领域.md")
        profile = self._settings.document_types.get("profiles", {}).get("project-docs", [])
        type_mapping = {
            name: self._settings.document_types["types"][name]
            for name in profile
            if name in self._settings.document_types["types"]
        }
        changes: list[tuple[Path, str]] = []
        generated_snapshot: dict[str, str | None] = {}
        note_count = 0
        notes_by_domain = {
            domain.id: governance_sync.direct_notes(domain, marker_name) for domain in domains
        }
        project_domain_ids = {
            domain.id for domain in domains if domain.governance == "project-docs"
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
            int(self._settings.governance["related_limit"]),
            float(self._settings.governance["related_min_score"]),
            int(self._settings.governance["cross_domain_related_limit"]),
            float(self._settings.governance["cross_domain_min_score"]),
        )
        for domain in sorted(domains, key=lambda item: item.id):
            notes = notes_by_domain[domain.id]
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
                    ] = file_sha256(relation_page) if relation_page.is_file() else None
                    if existing != relation_content:
                        changes.append((relation_page, relation_content))
                generated = governance_sync.generate_domain_content(
                    domain, domains, notes, relation_page
                )
            moc = domain.path / f"{domain.moc}.md"
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
                    blocked_phase="preflight",
                    blocked_scope=scope or "workspace",
                )
            current_moc = moc.read_text(encoding="utf-8")
            generated_snapshot[moc.relative_to(self._settings.vault_root).as_posix()] = file_sha256(
                moc
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
        indexed_document_count = 0
        if not dry_run:
            expected = {
                self._settings.vault_root / path: digest for path, digest in snapshot.items()
            }
            change_set = FileChangeSet(
                writes=tuple(FileWrite(path, content) for path, content in changes),
                label="maintenance sync",
                expected=expected,
            )
            try:
                with self._executor.transaction(change_set):
                    indexed_documents = [
                        self._document_state(path)
                        for path in iter_documents(
                            self._settings.vault_root,
                            self._settings.document_types,
                            (domain.path for domain in domains),
                        )
                    ]
                    domain_states = self._topology_states([], domains)[1]
                    self._repository.replace_scope_index(
                        scope or ".", indexed_documents, domain_states
                    )
                    indexed_document_count = len(indexed_documents)
            except GovernanceBlockedError as exc:
                return self._sync_blocked("concurrent-change", str(exc), scope)
        return MaintenanceResult(
            status="dry-run" if dry_run else "synced",
            document_count=note_count,
            issue_count=0,
            indexed_document_count=indexed_document_count,
            generated_file_count=len(changes),
            write_performed=bool(changes and not dry_run),
            operations=operations,
            scope=scope,
            domain_count=len(domains),
        )

    def _sync_blocked(self, code: str, path: str, scope: str | None) -> MaintenanceResult:
        return MaintenanceResult(
            status="blocked",
            document_count=0,
            issue_count=1,
            issues=[Issue.model_validate(enrich_issue({"code": code, "path": path}))],
            blocked_phase="preflight",
            blocked_scope=scope or "workspace",
        )

    def _is_within_workspace(self, path: Path) -> bool:
        return path == self._settings.vault_root or self._settings.vault_root in path.parents

    @staticmethod
    def _path_matches_scope(path: str, scope: str) -> bool:
        normalized_path = path.strip("/")
        normalized_scope = scope.strip("/")
        return normalized_path == normalized_scope or normalized_path.startswith(
            normalized_scope + "/"
        )

    def archive(self, confirm: bool = False, scope: str | None = None) -> MaintenanceResult:
        items, raw_issues = project_archive.collect_items(
            self._settings.vault_root, self._settings.governance
        )
        if scope is not None:
            scope_path = safe_path(self._settings.vault_root, scope)
            items = [
                item
                for item in items
                if item.source == scope_path or scope_path in item.source.parents
            ]
            paths = {
                item.source.relative_to(self._settings.vault_root).as_posix() for item in items
            }
            raw_issues = [issue for issue in raw_issues if issue.get("path") in paths]
        applied: list[dict[str, str]] = []
        if confirm and items:
            snapshot = capture_snapshot(
                self._settings.vault_root,
                [path for item in items for path in (item.source, item.target)],
            )
            with optimistic_write_lock(
                self._settings.state_root, snapshot, self._settings.vault_root
            ) as changed:
                if changed:
                    return self._concurrent_result(changed)
                applied = project_archive.apply_items(
                    self._settings.vault_root,
                    items,
                    raw_issues,
                    __import__("datetime").date.today().isoformat(),
                    self._rules.field_order_for,
                )
        issues = [Issue.model_validate(enrich_issue(item)) for item in raw_issues]
        return MaintenanceResult(
            status="issues-found" if issues else ("applied" if confirm else "ok"),
            document_count=len(items),
            issue_count=len(issues),
            issues=issues,
            issue_counts=self._issue_counts(issues),
            changed_document_count=len(applied),
            write_performed=bool(applied),
            operations=applied,
            candidates=project_archive.candidate_entries(self._settings.vault_root, items),
        )

    def _iter_documents(self) -> list[Path]:
        return iter_documents(self._settings.vault_root, self._settings.document_types)

    def _nearest_domain(self, path: Path) -> str | None:
        try:
            return resolve_domain_context(self._settings.vault_root, path).domain_id
        except DomainContextError:
            return None

    def _document_state(self, path: Path) -> DocumentState:
        parsed = parse_document(path.read_text(encoding="utf-8"))
        document_type = parsed.frontmatter.get("type")
        return DocumentState(
            path=path.relative_to(self._settings.vault_root).as_posix(),
            content_hash=file_sha256(path),
            document_type=document_type if isinstance(document_type, str) else None,
            domain_id=self._nearest_domain(path),
            status=parsed.frontmatter.get("status"),
        )

    def _topology_states(self, spaces, domains) -> tuple[list[SpaceState], list[DomainState]]:
        space_states: list[SpaceState] = []
        seen_spaces: set[str] = set()
        for space in spaces:
            marker = self._settings.vault_root / space.path / "_空间.md"
            if not space.id or space.id in seen_spaces or not marker.is_file():
                continue
            seen_spaces.add(space.id)
            space_states.append(
                SpaceState(
                    space_id=space.id,
                    name=space.name,
                    path=space.path,
                    space_type=space.type,
                    status=space.status,
                    source_hash=file_sha256(marker),
                )
            )
        domain_states: list[DomainState] = []
        seen_domains: set[str] = set()
        for domain in domains:
            marker = domain.path / "_领域.md"
            if not domain.id or domain.id in seen_domains or not marker.is_file():
                continue
            seen_domains.add(domain.id)
            domain_states.append(
                DomainState(
                    domain_id=domain.id,
                    space_id=domain.space_id,
                    parent_domain_id=domain.parent_domain,
                    project_id=domain.project_id,
                    name=domain.name,
                    path=domain.path.relative_to(self._settings.vault_root).as_posix(),
                    domain_type=domain.type,
                    governance=domain.governance,
                    moc=domain.moc,
                    status=domain.status,
                    source_hash=file_sha256(marker),
                )
            )
        return space_states, domain_states

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
