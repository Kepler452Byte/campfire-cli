import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from campfire_cli.app.script.schema.project_schema import validate_project_name
from campfire_cli.common.exceptions import JobError

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class Job:
    id: str
    argv: list[str] | None
    cwd: str
    schedule: dict[str, Any]
    timeout: int = 3600
    workspace_id: str | None = None
    workspace_root: str | None = None
    name: str | None = None
    agent: dict[str, Any] | None = None
    script_project: str | None = None

    def __post_init__(self) -> None:
        if self.script_project is not None:
            validate_project_name(self.script_project)
        if self.name is not None and (not isinstance(self.name, str) or not self.name.strip()):
            raise JobError("invalid-job", "name must be a nonempty string")
        if self.workspace_id is not None and (
            not isinstance(self.workspace_id, str) or not self.workspace_id.strip()
        ):
            raise JobError("invalid-job", "workspace_id must be a nonempty stable id")
        if self.workspace_root is not None and (
            self.workspace_id is None
            or not isinstance(self.workspace_root, str)
            or not Path(self.workspace_root).is_absolute()
        ):
            raise JobError("invalid-job", "workspace_root must be an absolute resolved binding")
        if not isinstance(self.id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", self.id):
            raise JobError("invalid-job", "id must match [a-z][a-z0-9-]{0,47}")
        if (self.argv is None) == (self.agent is None):
            raise JobError("invalid-job", "Supply exactly one of agent or argv")
        command = self.command
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(arg, str) or "\0" in arg for arg in command)
        ):
            raise JobError("invalid-job", "argv must be a nonempty string array without NUL")
        if any(character in command[0] for character in "\r\n"):
            raise JobError("invalid-job", "Executable paths cannot contain newlines")
        if not Path(command[0]).is_absolute():
            raise JobError("invalid-job", "Executable must be an absolute path")
        if (
            not isinstance(self.cwd, str)
            or any(char in self.cwd for char in "\0\r\n")
            or not Path(self.cwd).is_absolute()
        ):
            raise JobError("invalid-job", "cwd must be an absolute directory")
        if type(self.timeout) is not int or not 1 <= self.timeout <= 86400:
            raise JobError("invalid-job", "timeout must be 1..86400 seconds")
        schedule = self.schedule
        if not isinstance(schedule, dict):
            raise JobError("invalid-job", "schedule must be an object")
        kind = schedule.get("kind")
        if kind == "manual":
            valid = set(schedule) == {"kind"}
        elif kind == "interval":
            seconds = schedule.get("seconds")
            valid = (
                set(schedule) == {"kind", "seconds"}
                and type(seconds) is int
                and 60 <= seconds <= 86400
                and seconds % 60 == 0
            )
        elif kind in {"daily", "weekly"}:
            time = schedule.get("time")
            valid = (
                isinstance(time, str)
                and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time) is not None
            )
            keys = {"kind", "time"}
            if kind == "weekly":
                keys.add("day")
                valid = valid and schedule.get("day") in DAYS
            valid = valid and set(schedule) == keys
        else:
            valid = False
        if not valid:
            raise JobError(
                "invalid-job",
                "schedule: manual, interval seconds (whole minutes 60..86400), "
                "daily HH:MM, or weekly day mon..sun HH:MM",
            )

    @property
    def command(self) -> list[str]:
        if self.agent is not None:
            from campfire_cli.app.job.schema.agent_command import compile_agent

            return compile_agent(self.agent)
        return self.argv

    def data(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("argv" if self.agent is not None else "agent")
        if self.script_project is None:
            data.pop("script_project")
        return data

    @classmethod
    def parse(cls, data: object) -> "Job":
        if not isinstance(data, dict) or set(data) - {
            "id",
            "argv",
            "cwd",
            "schedule",
            "timeout",
            "workspace_id",
            "workspace_root",
            "name",
            "agent",
            "script_project",
        }:
            raise JobError(
                "invalid-job",
                "Use id, cwd, schedule, timeout and exactly one of argv/agent; "
                "optional name, workspace_id, workspace_root, script_project",
            )
        try:
            return cls(**({"argv": None, **data} if "agent" in data else data))
        except TypeError as exc:
            raise JobError("invalid-job", str(exc)) from exc
