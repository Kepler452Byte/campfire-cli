import re
from pathlib import Path

import yaml

from campfire_cli.app.job.schema.job_schema import Job
from campfire_cli.common.exceptions import JobError
from campfire_cli.common.filesystem import atomic_write
from campfire_cli.common.filesystem.locking import workspace_write_lock


class JobRepository:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.path = home / "jobs.yaml"

    def read(self) -> dict[str, Job]:
        if not self.path.exists():
            return {}
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise JobError("invalid-config", str(exc)) from exc
        if (
            not isinstance(data, dict)
            or set(data) != {"jobs"}
            or not isinstance(data["jobs"], list)
        ):
            raise JobError("invalid-config", "jobs.yaml requires one jobs array")
        tasks = [Job.parse(item) for item in data["jobs"]]
        if len({task.id for task in tasks}) != len(tasks):
            raise JobError("invalid-config", "Duplicate job ids")
        return {task.id: task for task in tasks}

    def write(self, jobs: dict[str, Job]) -> None:
        atomic_write(
            self.path,
            yaml.safe_dump(
                {"jobs": [job.data() for job in jobs.values()]},
                allow_unicode=True,
                sort_keys=False,
            ),
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
