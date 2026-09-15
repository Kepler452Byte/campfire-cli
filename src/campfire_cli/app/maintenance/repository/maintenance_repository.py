from __future__ import annotations

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from campfire_cli.app.maintenance.schema.maintenance_schema import (
    DocumentState,
    DomainState,
    Issue,
    MaintenanceRunRecord,
    SpaceState,
)
from campfire_cli.common.database.models import (
    Document,
    GovernanceIssue,
    MaintenanceRun,
    WorkspaceDomain,
    WorkspaceSpace,
)


class SqliteMaintenanceRepository:
    def __init__(self, session: Session, workspace_id: str) -> None:
        self._session = session
        self._workspace_id = workspace_id

    def replace_current_state(
        self,
        documents: list[DocumentState],
        issues: list[Issue],
        spaces: list[SpaceState],
        domains: list[DomainState],
    ) -> None:
        self._session.execute(delete(Document).where(Document.workspace_id == self._workspace_id))
        self._session.execute(
            delete(GovernanceIssue).where(GovernanceIssue.workspace_id == self._workspace_id)
        )
        self._session.execute(
            delete(WorkspaceDomain).where(WorkspaceDomain.workspace_id == self._workspace_id)
        )
        self._session.execute(
            delete(WorkspaceSpace).where(WorkspaceSpace.workspace_id == self._workspace_id)
        )
        self._session.add_all(
            [
                WorkspaceSpace(workspace_id=self._workspace_id, **item.model_dump())
                for item in spaces
            ]
        )
        self._session.add_all(
            [
                WorkspaceDomain(workspace_id=self._workspace_id, **item.model_dump())
                for item in domains
            ]
        )
        self._session.add_all(
            [
                Document(
                    workspace_id=self._workspace_id,
                    path=item.path,
                    content_hash=item.content_hash,
                    document_type=item.document_type,
                    domain_id=item.domain_id,
                    status=item.status,
                )
                for item in documents
            ]
        )
        self._session.add_all(
            [
                GovernanceIssue(
                    workspace_id=self._workspace_id,
                    path=item.path,
                    code=item.code,
                    detail=item.detail,
                    severity=item.severity,
                )
                for item in issues
            ]
        )
        self._session.commit()

    def save_run(self, run: MaintenanceRunRecord) -> None:
        self._session.add(
            MaintenanceRun(
                workspace_id=self._workspace_id,
                run_id=run.run_id,
                status=run.status,
                scanned_count=run.scanned_count,
                issue_count=run.issue_count,
                started_at=run.started_at,
                finished_at=run.finished_at,
            )
        )
        self._session.commit()

    def replace_scope_index(
        self,
        scope: str,
        documents: list[DocumentState],
        domains: list[DomainState],
    ) -> None:
        normalized = scope.strip("/")
        for model in (Document, WorkspaceDomain):
            selection = model.workspace_id == self._workspace_id
            if normalized not in {"", "."}:
                selection = selection & or_(
                    model.path == normalized,
                    model.path.startswith(f"{normalized}/", autoescape=True),
                )
            self._session.execute(delete(model).where(selection))
        self._session.add_all(
            [
                WorkspaceDomain(workspace_id=self._workspace_id, **item.model_dump())
                for item in domains
            ]
        )
        self._session.add_all(
            [
                Document(
                    workspace_id=self._workspace_id,
                    path=item.path,
                    content_hash=item.content_hash,
                    document_type=item.document_type,
                    domain_id=item.domain_id,
                    status=item.status,
                )
                for item in documents
            ]
        )
        try:
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
