import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any

from campfire_cli.app.job.interface.scheduler import marker, namespace, runner_argv
from campfire_cli.app.job.schema.job_schema import DAYS, Job
from campfire_cli.common.exceptions import JobError
from campfire_cli.common.process import command


class LaunchdScheduler:
    domain: str

    def __init__(self, home: Path) -> None:
        self.home = home
        self.prefix = namespace(home)
        self.directory = Path.home() / "Library/LaunchAgents"
        if sys.platform == "win32":
            raise JobError("unsupported-platform", "launchd requires macOS")
        self.domain = f"gui/{os.getuid()}"

    def label(self, job_id: str) -> str:
        return f"io.campfire.{self.prefix}.{job_id}"

    def path(self, job_id: str) -> Path:
        return self.directory / (self.label(job_id) + ".plist")

    def owned(self, job_id: str) -> dict[str, Any] | None:
        path = self.path(job_id)
        if not path.exists():
            return None
        with path.open("rb") as handle:
            data: dict[str, Any] = plistlib.load(handle)
        if data.get("CampfireOwner") != marker(self.home, job_id):
            raise JobError("foreign-job", f"Refusing to modify unowned plist {path}")
        return data

    def loaded(self, job_id: str) -> bool:
        result = subprocess.run(
            ["launchctl", "print", f"{self.domain}/{self.label(job_id)}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return True
        if result.returncode == 113:
            return False
        raise JobError("scheduler-failed", result.stderr.strip())

    def state(self, job_id: str) -> dict[str, Any]:
        owned = self.owned(job_id)
        loaded = self.loaded(job_id)
        if loaded and owned is None:
            raise JobError("foreign-job", "Loaded launchd job has no owned plist")
        # Bootstrapped jobs in the GUI domain are authoritative, not a YAML enabled flag.
        return {
            "deployed": self.path(job_id).exists() or loaded,
            "enabled": loaded,
            "active": loaded,
            "runner_current": owned.get("ProgramArguments") == runner_argv(self.home, job_id)
            if owned
            else None,
        }

    def deploy(self, task: Job, enabled: bool) -> None:
        self.state(task.id)
        if self.loaded(task.id):
            command(["launchctl", "bootout", f"{self.domain}/{self.label(task.id)}"])
        data: dict[str, Any] = {
            "Label": self.label(task.id),
            "CampfireOwner": marker(self.home, task.id),
            "ProgramArguments": runner_argv(self.home, task.id),
            "ProcessType": "Background",
            "RunAtLoad": False,
            "Disabled": not enabled,
        }
        schedule = task.schedule
        if schedule["kind"] == "interval":
            data["StartInterval"] = schedule["seconds"]
        else:
            hour, minute = map(int, schedule["time"].split(":"))
            calendar = {"Hour": hour, "Minute": minute}
            if schedule["kind"] == "weekly":
                calendar["Weekday"] = (DAYS.index(schedule["day"]) + 1) % 7
            data["StartCalendarInterval"] = calendar
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.path(task.id).open("wb") as handle:
            plistlib.dump(data, handle)
        target = f"{self.domain}/{self.label(task.id)}"
        command(["launchctl", "enable" if enabled else "disable", target])
        if enabled:
            command(["launchctl", "bootstrap", self.domain, str(self.path(task.id))])

    def remove(self, job_id: str) -> None:
        self.state(job_id)
        if self.loaded(job_id):
            command(["launchctl", "bootout", f"{self.domain}/{self.label(job_id)}"])
        command(["launchctl", "enable", f"{self.domain}/{self.label(job_id)}"])
        self.path(job_id).unlink(missing_ok=True)

    def doctor(self) -> dict[str, Any]:
        command(["launchctl", "print", self.domain])
        return {
            "platform": "macos",
            "scheduler": "launchd-user",
            "available": True,
            "session_requirement": "Logged-in GUI user session required.",
            "native_logs": "launchctl print gui/<uid>/<label>; inspect launchd logs",
            "sleep_behavior": "launchd may coalesce missed events on wake; no catch-up.",
        }
