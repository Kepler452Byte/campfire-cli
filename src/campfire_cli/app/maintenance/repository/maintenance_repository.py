from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from campfire_cli.app.maintenance.schema.maintenance_schema import (
    DocumentState,
    Issue,
    MaintenanceRunRecord,
)
from campfire_cli.common.database.models import Document, GovernanceIssue, MaintenanceRun


class SqliteMaintenanceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_current_state(self, documents: list[DocumentState], issues: list[Issue]) -> None:
        self._session.execute(delete(Document))
        self._session.execute(delete(GovernanceIssue))
        self._session.add_all(
            [
                Document(
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
                run_id=run.run_id,
                status=run.status,
                scanned_count=run.scanned_count,
                issue_count=run.issue_count,
                started_at=run.started_at,
                finished_at=run.finished_at,
            )
        )
        self._session.commit()
