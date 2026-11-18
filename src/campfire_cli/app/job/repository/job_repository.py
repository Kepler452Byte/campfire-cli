import re
from pathlib import Path

import yaml
from sqlalchemy import delete, insert, select

from campfire_cli.app.job.repository.database import JobDatabase
from campfire_cli.app.job.repository.schema import JOBS
from campfire_cli.app.job.schema.job_schema import Job
from campfire_cli.common.exceptions import JobError
from campfire_cli.common.filesystem import atomic_write
from campfire_cli.common.filesystem.locking import workspace_write_lock


class JobRepository:
    def __init__(self, home: Path, database: JobDatabase) -> None:
        self.home = home
        self.database = database
        self.path = database.path

    def read(self) -> dict[str, Job]:
        if not self.database.exists():
            return {}
        with self.database.connection() as db:
            return {
                row["id"]: Job.parse(dict(row))
                for row in db.execute(select(JOBS).order_by(JOBS.c.id)).mappings()
            }

    def write(self, jobs: dict[str, Job]) -> None:
        with self.database.connection() as db:
            db.execute(delete(JOBS))
            if jobs:
                db.execute(
                    insert(JOBS),
                    [dict(job.data(), script_project=job.script_project) for job in jobs.values()],
                )

    def environment_id(self) -> str | None:
        path = self.home / "local.yaml"

        def read():
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
            except (OSError, yaml.YAMLError) as exc:
                raise JobError("invalid-config", "Cannot read local.yaml") from exc
            if not isinstance(data, dict):
                raise JobError("invalid-config", "local.yaml must be a mapping")
            identity = data.get("environment_id")
            if identity is not None and (
                not isinstance(identity, str) or re.fullmatch(r"[a-f0-9]{32}", identity) is None
            ):
                raise JobError("invalid-config", "Invalid local environment_id")
            return data, identity

        return read()[1]

    def ensure_environment(self, identity: str) -> str:
        with workspace_write_lock(self.home):
            current = self.environment_id()
            if current is not None:
                return current
            path = self.home / "local.yaml"
            data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
            data["environment_id"] = identity
            atomic_write(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
            return identity
