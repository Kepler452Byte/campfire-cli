from __future__ import annotations

from sqlalchemy import delete, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from campfire_cli.app.maintenance.schema.maintenance_schema import (
    DomainState,
    Issue,
    MaintenanceRunRecord,
    SpaceState,
)
from campfire_cli.common.database.models import (
    GovernanceIssue,
    MaintenanceRun,
    WorkspaceDomain,
    WorkspaceSpace,
)
from campfire_cli.common.exceptions import AppError


class SqliteMaintenanceRepository:
    def __init__(self, session: Session, workspace_id: str) -> None:
        self._session = session
        self._workspace_id = workspace_id

    def replace_current_state(
        self,
        issues: list[Issue],
        spaces: list[SpaceState],
        domains: list[DomainState],
    ) -> None:
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
        domains: list[DomainState],
    ) -> None:
        normalized = scope.strip("/")
        selection = WorkspaceDomain.workspace_id == self._workspace_id
        if normalized not in {"", "."}:
            selection &= or_(
                WorkspaceDomain.path == normalized,
                WorkspaceDomain.path.startswith(f"{normalized}/", autoescape=True),
                WorkspaceDomain.domain_id.in_([item.domain_id for item in domains]),
            )
        try:
            self._session.execute(delete(WorkspaceDomain).where(selection))
            self._session.add_all(
                WorkspaceDomain(workspace_id=self._workspace_id, **item.model_dump())
                for item in domains
            )
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise AppError(
                "领域索引提交失败，已回滚本次索引更新",
                code="domain-index-write-failed",
            ) from exc
