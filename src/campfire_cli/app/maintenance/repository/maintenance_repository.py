from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from campfire_cli.app.maintenance.schema.maintenance_schema import (
    DocumentState,
    Issue,
    MaintenancePlan,
    MaintenanceRunRecord,
)
from campfire_cli.common.database.models import Document, GovernanceIssue, MaintenanceRun
from campfire_cli.common.exceptions import GovernanceBlockedError
from campfire_cli.common.filesystem import atomic_write


class SqliteMaintenanceRepository:
    def __init__(self, session: Session, workspace_id: str, state_root: Path) -> None:
        self._session = session
        self._workspace_id = workspace_id
        self._state_root = state_root

    def replace_current_state(self, documents: list[DocumentState], issues: list[Issue]) -> None:
        self._session.execute(delete(Document).where(Document.workspace_id == self._workspace_id))
        self._session.execute(
            delete(GovernanceIssue).where(GovernanceIssue.workspace_id == self._workspace_id)
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

    def save_plan(self, plan: MaintenancePlan) -> None:
        atomic_write(self._plan_path(plan.plan_id), plan.model_dump_json(indent=2) + "\n")

    def load_plan(self, plan_id: str) -> MaintenancePlan:
        path = self._plan_path(plan_id)
        if not path.is_file():
            raise GovernanceBlockedError(f"Maintenance Plan 不存在：{plan_id}")
        return MaintenancePlan.model_validate_json(path.read_text(encoding="utf-8"))

    def _plan_path(self, plan_id: str) -> Path:
        if not plan_id or Path(plan_id).name != plan_id:
            raise GovernanceBlockedError(f"Maintenance Plan id 非法：{plan_id}")
        return self._state_root / "maintenance" / "plans" / plan_id / "plan.json"
