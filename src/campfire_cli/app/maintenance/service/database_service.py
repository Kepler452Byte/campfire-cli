from __future__ import annotations

import json
from datetime import UTC, datetime

from alembic.migration import MigrationContext
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from campfire_cli.common.database.migrations import upgrade_database
from campfire_cli.common.database.models import MigrationBatch
from campfire_cli.common.filesystem import atomic_write
from campfire_cli.common.hashing import text_sha256
from campfire_cli.config.settings import WorkspaceSettings, campfire_home


class DatabaseService:
    def __init__(self, settings: WorkspaceSettings, engine: Engine, session: Session) -> None:
        self._settings = settings
        self._engine = engine
        self._session = session

    def upgrade(self) -> dict[str, object]:
        upgrade_database(campfire_home() / "campfire.db")
        return {"status": "ok", "revision": self._revision()}

    def backup(self) -> dict[str, object]:
        changes_path = self._settings.state_root / "backup" / "changes.jsonl"
        existing = (
            changes_path.read_text(encoding="utf-8").splitlines() if changes_path.is_file() else []
        )
        sequence = 1
        if existing:
            sequence = int(json.loads(existing[-1])["sequence"]) + 1
        batches = [
            {
                "batch_uuid": row.batch_uuid,
                "batch_name": row.batch_name,
                "scope": row.scope,
                "status": row.status,
                "config_hash": row.config_hash,
            }
            for row in self._session.scalars(
                select(MigrationBatch).where(
                    MigrationBatch.workspace_id == self._settings.workspace_id
                )
            ).all()
        ]
        payload = {
            "schema_version": 1,
            "database_revision": self._revision(),
            "sequence": sequence,
            "exported_at": datetime.now(UTC).isoformat(),
            "config_hash": self._config_hash(),
            "data": {"migration_batches": batches},
        }
        atomic_write(
            self._settings.state_root / "backup" / "current.json",
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )
        event = json.dumps(
            {
                "sequence": sequence,
                "operation": "database_backup",
                "created_at": payload["exported_at"],
            },
            ensure_ascii=False,
        )
        retained = [*existing, event][-50:]
        atomic_write(changes_path, "\n".join(retained) + "\n")
        return {"status": "ok", "sequence": sequence, "batch_count": len(batches)}

    def restore(self, confirm: bool) -> dict[str, object]:
        source = self._settings.state_root / "backup" / "current.json"
        if not source.is_file():
            return {
                "status": "blocked",
                "issues": [{"code": "backup-missing", "path": str(source)}],
            }
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("database_revision") != self._revision():
            return {
                "status": "blocked",
                "issues": [{"code": "database-revision-mismatch", "path": str(source)}],
            }
        if not confirm:
            return {"status": "ready", "batch_count": len(payload["data"]["migration_batches"])}
        existing_names = set(
            self._session.scalars(
                select(MigrationBatch.batch_name).where(
                    MigrationBatch.workspace_id == self._settings.workspace_id
                )
            ).all()
        )
        restored = 0
        for item in payload["data"]["migration_batches"]:
            if item["batch_name"] in existing_names:
                continue
            self._session.add(
                MigrationBatch(workspace_id=self._settings.workspace_id, **item)
            )
            restored += 1
        self._session.commit()
        return {"status": "restored", "restored_batch_count": restored}

    def _revision(self) -> str | None:
        with self._engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()

    def _config_hash(self) -> str:
        data = {
            "governance": self._settings.governance,
            "document_types": self._settings.document_types,
            "frontmatter_schema": self._settings.frontmatter_schema,
        }
        return text_sha256(json.dumps(data, ensure_ascii=False, sort_keys=True))
