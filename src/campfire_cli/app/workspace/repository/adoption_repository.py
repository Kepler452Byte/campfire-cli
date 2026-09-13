from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from campfire_cli.app.workspace.schema.adoption_schema import AdoptionBatchState
from campfire_cli.common.database.models import AdoptionBatch
from campfire_cli.common.exceptions import ConfigurationError


class SqliteAdoptionRepository:
    def __init__(self, session: Session, workspace_id: str) -> None:
        self._session = session
        self._workspace_id = workspace_id

    def save(self, state: AdoptionBatchState) -> None:
        row = self._row(state.batch)
        if row is None:
            row = AdoptionBatch(workspace_id=self._workspace_id, batch_name=state.batch)
            self._session.add(row)
        row.source_path = state.source_path
        row.source_kind = state.source_kind
        row.staging_path = state.staging_path
        row.status = state.status
        row.inventory_json = json.dumps(
            [item.model_dump(mode="json") for item in state.inventory], ensure_ascii=False
        )
        row.plan_json = state.plan.model_dump_json() if state.plan else None
        self._session.commit()

    def load(self, batch: str) -> AdoptionBatchState:
        row = self._row(batch)
        if row is None:
            raise ConfigurationError(f"接管批次不存在：{batch}")
        return AdoptionBatchState(
            batch=row.batch_name,
            source_path=row.source_path,
            source_kind=row.source_kind,
            staging_path=row.staging_path,
            status=row.status,
            inventory=json.loads(row.inventory_json),
            plan=json.loads(row.plan_json) if row.plan_json else None,
        )

    def _row(self, batch: str) -> AdoptionBatch | None:
        if not batch or "/" in batch or "\\" in batch or batch in {".", ".."}:
            raise ConfigurationError("非法接管批次名称")
        return self._session.scalar(
            select(AdoptionBatch).where(
                AdoptionBatch.workspace_id == self._workspace_id,
                AdoptionBatch.batch_name == batch,
            )
        )
