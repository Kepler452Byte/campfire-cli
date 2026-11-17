import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Protocol

from campfire_cli.app.job.schema.job_schema import Job


class Scheduler(Protocol):
    def state(self, job_id: str) -> dict[str, Any]: ...
    def deploy(self, task: Job, enabled: bool) -> None: ...
    def remove(self, job_id: str) -> None: ...
    def doctor(self) -> dict[str, Any]: ...


def namespace(home: Path) -> str:
    return "campfire-" + hashlib.sha256(str(home).encode()).hexdigest()[:12]


def runner_argv(home: Path, job_id: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "campfire_cli.main",
        "job",
        "run",
        job_id,
        "--confirm",
        "--scheduled",
        "--home",
        str(home),
    ]


def marker(home: Path, job_id: str) -> str:
    return json.dumps({"owner": "campfire", "home": str(home), "id": job_id}, sort_keys=True)
