from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from campfire_cli.app.migration.schema.migration_schema import (
    InventoryItem,
    MigrationPlan,
    MigrationResult,
)
from campfire_cli.common.database.models import MigrationBatch
from campfire_cli.common.filesystem import atomic_write


class SqliteMigrationRepository:
    def __init__(self, session: Session, state_root: Path) -> None:
        self._session = session
        self._state_root = state_root

    def save_batch(self, batch_uuid: str, batch: str, scope: str, config_hash: str) -> None:
        existing = self._session.scalar(
            select(MigrationBatch).where(MigrationBatch.batch_name == batch)
        )
        if existing is None:
            self._session.add(
                MigrationBatch(
                    batch_uuid=batch_uuid,
                    batch_name=batch,
                    scope=scope,
                    config_hash=config_hash,
                )
            )
        else:
            existing.scope = scope
            existing.config_hash = config_hash
        self._session.commit()

    def save_inventory(self, batch: str, items: list[InventoryItem]) -> None:
        payload = {
            "schema_version": 1,
            "batch": batch,
            "items": [item.model_dump() for item in items],
        }
        self._write(batch, "inventory.json", payload)

    def load_inventory(self, batch: str) -> tuple[str, str, list[InventoryItem]]:
        row = self._session.scalar(select(MigrationBatch).where(MigrationBatch.batch_name == batch))
        if row is None:
            raise ValueError(f"批次不存在：{batch}")
        payload = self._read(batch, "inventory.json")
        return (
            row.scope,
            row.config_hash,
            [InventoryItem.model_validate(item) for item in payload["items"]],
        )

    def save_plan(self, plan: MigrationPlan) -> None:
        self._write(plan.batch, "plan.json", plan.model_dump(mode="json"))

    def load_plan(self, batch: str) -> MigrationPlan:
        return MigrationPlan.model_validate(self._read(batch, "plan.json"))

    def save_execution(self, result: MigrationResult) -> None:
        self._write(result.batch, "execution.json", result.model_dump(mode="json"))

    def save_verification(self, result: MigrationResult) -> None:
        self._write(result.batch, "verification.json", result.model_dump(mode="json"))

    def _path(self, batch: str, name: str) -> Path:
        if not batch or "/" in batch or "\\" in batch or batch in {".", ".."}:
            raise ValueError("非法批次名称")
        return self._state_root / "batches" / batch / name

    def _write(self, batch: str, name: str, payload: dict[str, object]) -> None:
        atomic_write(
            self._path(batch, name), json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        )

    def _read(self, batch: str, name: str) -> dict[str, object]:
        return json.loads(self._path(batch, name).read_text(encoding="utf-8"))
