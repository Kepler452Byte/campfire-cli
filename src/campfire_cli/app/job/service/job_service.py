import hashlib
import json
import platform
import re
import socket
import uuid
from collections.abc import Callable
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from campfire_cli.app.job.interface.scheduler import Scheduler
from campfire_cli.app.job.repository.job_repository import JobRepository
from campfire_cli.app.job.repository.run_repository import RunRepository
from campfire_cli.app.job.schema.job_schema import Job
from campfire_cli.app.job.schema.retention_schema import RetentionPolicy
from campfire_cli.app.job.service.runner import run_job
from campfire_cli.app.script.service.script_service import ScriptService
from campfire_cli.common.exceptions import AppError, JobError
from campfire_cli.common.filesystem.process_lock import process_lock
from campfire_cli.common.time_display import display_run
from campfire_cli.config.defaults import config_section


class JobService:
    def __init__(
        self,
        home: Path,
        scheduler: Scheduler,
        repository: JobRepository,
        runs: RunRepository,
        policy: RetentionPolicy,
        resolve_workspace,
        config: dict,
        scripts: ScriptService,
    ) -> None:
        self.home = home
        self.repository = repository
        self.runs = runs
        self.scheduler = scheduler
        self.policy = policy
        self.resolve_workspace = resolve_workspace
        self.config = config
        self.scripts = scripts

    def lock(self):
        return process_lock(self.home / "jobs/locks/config.lock")

    def run_lock(self, job_id: str):
        return process_lock(self.home / f"jobs/locks/run-{job_id}.lock")

    def get(self, job_id: str) -> Job:
        jobs = self.repository.read()
        if job_id not in jobs:
            raise JobError("not-found", f"Job {job_id} does not exist")
        return jobs[job_id]

    def state(self, job: Job) -> dict[str, Any]:
        if job.schedule["kind"] == "manual":
            return {"deployed": False, "enabled": False, "active": False, "details": {}}
        return self.scheduler.state(job.id)

    def follow_up(self, job_id: str) -> list[dict[str, Any]]:
        return [
            {
                "argv": ["campfire", "job", "run", job_id],
                "environment": {"CAMPFIRE_HOME": str(self.home)},
                "reason": "Preview and test this Job within its execution authorization",
                "requires_execution_authorization": True,
            }
        ]

    def environment(self) -> dict:
        identity = self.repository.environment_id()
        return {
            "id": identity,
            "name": socket.gethostname(),
            "platform": platform.system(),
            "timezone": str(datetime.now().astimezone().tzinfo),
            "observed_at": datetime.now().astimezone().isoformat(),
        }

    def inventory_path(self) -> str | None:
        identity = self.repository.environment_id()
        if identity is None:
            return None
        prefix = config_section("document_types")["types"]["record"]["prefix"]
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", socket.gethostname()).strip(" .")
        return str(Path(self.config["inventory_root"]) / f"{prefix}{name or '本机'}.md").replace(
            "\\", "/"
        )

    def list_jobs(self, workspace_id: str | None = None) -> dict:
        if workspace_id is not None:
            self.resolve_workspace(workspace_id)
        with self.lock():
            jobs = []
            for job in self.repository.read().values():
                if workspace_id is not None and job.workspace_id != workspace_id:
                    continue
                rows = self.runs.history(job.id, 1, 0)
                jobs.append(
                    {
                        **job.data(),
                        "scheduler": self.state(job),
                        "latest_run": rows[0] if rows else None,
                    }
                )
            return {
                "status": "ok",
                "environment": self.environment(),
                "workspace_id": workspace_id,
                "inventory_document": self.inventory_path(),
                "jobs": jobs,
                "issues": [],
            }

    def query_jobs(
        self,
        *,
        name: str = "",
        workspace_id: str | None = None,
        state: str | None = None,
        unbound: bool = False,
        page: int = 1,
        page_size: int = 10,
    ) -> dict:
        """Filter and paginate one observed snapshot of local task state."""
        if type(page) is not int or page < 1:
            raise JobError("invalid-page", "page must be a positive integer")
        self.validate_page(page_size, 0)
        if state not in {None, "enabled", "paused", "manual"}:
            raise JobError("invalid-state", "Use enabled, paused or manual")
        if unbound and workspace_id is not None:
            raise JobError("invalid-filter", "unbound and workspace_id are mutually exclusive")
        result = self.list_jobs(workspace_id)
        rows = result.pop("jobs")
        rows = [row for row in rows if name.casefold() in (row.get("name") or row["id"]).casefold()]
        if unbound:
            rows = [row for row in rows if row["workspace_id"] is None]
        if state:
            rows = [row for row in rows if self.job_state(row) == state]
        rows.sort(key=lambda row: ((row.get("name") or row["id"]).casefold(), row["id"]))
        total = len(rows)
        return {
            **result,
            "list": rows[(page - 1) * page_size : page * page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }

    @staticmethod
    def job_state(row: dict) -> str:
        if row["schedule"]["kind"] == "manual":
            return "manual"
        return "enabled" if row["scheduler"]["enabled"] else "paused"

    def start_run(self, job_id: str, expected: str) -> dict:
        """Start an independent runner after it acquires locks and records its Run."""
        from campfire_cli.app.job.service.detached_runner import start_detached

        result = start_detached(self.home, job_id, expected)
        return {**result, "follow_up": self.run_follow_up(result["run"]["id"])}

    def show(self, job_id: str) -> dict[str, Any]:
        with self.lock():
            job = self.get(job_id)
            return {
                "status": "ok",
                "environment": self.environment(),
                "job": {**job.data(), "scheduler": self.state(job)},
            }

    def check_upgrade(self) -> None:
        active = self.home / "active-upgrade.json"
        if active.exists():
            try:
                identity = json.loads(active.read_text())["operation_id"]
                state = json.loads((self.home / "upgrades" / identity / "result.json").read_text())
            except (OSError, KeyError, ValueError) as exc:
                raise JobError(
                    "upgrade-active", "Cannot verify active upgrade; inspect its result"
                ) from exc
            if state.get("state") not in {"completed", "failed"}:
                raise JobError(
                    "upgrade-active", "Package upgrade is active; inspect its result first"
                )

    @contextmanager
    def idle(self):
        """Prevent new starts while the caller schedules an environment replacement."""
        with self.lock(), process_lock(self.home / "jobs/locks/web.lock"), ExitStack() as stack:
            for identity in sorted(set(self.repository.read()) | set(self.runs.running_jobs())):
                stack.enter_context(self.run_lock(identity))
            yield

    def verify_binding(self, job: Job) -> None:
        if job.workspace_id is not None:
            current = self.resolve_workspace(job.workspace_id)
            if str(current) != job.workspace_root:
                raise JobError(
                    "workspace-binding-changed",
                    "Workspace binding changed; preview and update this Job before execution",
                )

    def change(
        self, action: str, job_id: str, job: Job | None, confirm: bool, expected: str | None
    ) -> dict[str, Any]:
        if job is not None and (not Path(job.command[0]).is_file() or not Path(job.cwd).is_dir()):
            raise JobError(
                "invalid-job",
                "Executable and working directory must exist when creating or updating",
            )
        if job is not None and job.script_project is not None:
            self.scripts.require_project(job.script_project)
        if job is not None and job.workspace_id is not None:
            job = replace(job, workspace_root=str(self.resolve_workspace(job.workspace_id)))
        with self.lock():
            self.check_upgrade()
            jobs = self.repository.read()
            old = jobs.get(job_id)
            if action == "create" and old:
                raise JobError("already-exists", f"Job {job_id} exists")
            if action != "create" and old is None:
                raise JobError("not-found", f"Job {job_id} does not exist")
            replacement = job or old
            assert replacement is not None
            if action == "resume":
                self.verify_binding(replacement)
            manual = replacement.schedule["kind"] == "manual"
            if action in {"pause", "resume"} and manual:
                raise JobError(
                    "schedule-not-applicable", "Manual jobs have no schedule to pause or resume"
                )
            native_change = not manual or (old is not None and old.schedule["kind"] != "manual")
            state = self.scheduler.state(job_id) if native_change else self.state(replacement)
            if action == "create" and state["deployed"]:
                raise JobError(
                    "already-deployed", "A native job already exists; reconcile it before creating"
                )
            enabled = not manual and (
                action == "resume"
                or (
                    action == "update"
                    and old is not None
                    and old.schedule["kind"] != "manual"
                    and bool(state["enabled"])
                )
            )
            payload = {
                "action": action,
                "job_id": job_id,
                "before": old.data() if old else None,
                "after": replacement.data() if action != "delete" and replacement else None,
                "scheduler_before": state,
                "enabled_after": enabled,
                "config": hashlib.sha256(self.repository.path.read_bytes()).hexdigest()
                if self.repository.path.exists()
                else "missing",
            }
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            plan: dict[str, Any] = {
                "status": "planned",
                "write_performed": False,
                "follow_up": [],
                "expected_plan": digest,
                **{key: value for key, value in payload.items() if key != "config"},
            }
            if not confirm:
                return plan
            if expected != digest:
                raise JobError(
                    "stale-plan",
                    "Use --expected-plan from a fresh preview; definition or native state changed",
                )
            with self.run_lock(job_id):
                self.repository.ensure_environment(uuid.uuid4().hex)
                try:
                    if action == "delete":
                        if native_change:
                            self.scheduler.remove(job_id)
                        del jobs[job_id]
                    else:
                        assert replacement is not None
                        if manual:
                            if native_change:
                                self.scheduler.remove(job_id)
                        else:
                            self.scheduler.deploy(replacement, enabled)
                        jobs[job_id] = replacement
                    self.repository.write(jobs)
                except Exception as exc:
                    try:
                        if old and state["deployed"]:
                            self.scheduler.deploy(old, bool(state["enabled"]))
                        elif native_change:
                            self.scheduler.remove(job_id)
                    except Exception as rollback:
                        raise JobError(
                            "recovery-required",
                            f"Operation failed: {exc}; compensation failed: {rollback}. "
                            "Inspect native scheduler and jobs.yaml.",
                        ) from exc
                    raise JobError(
                        "change-failed",
                        f"Operation failed and native configuration was restored: {exc}",
                    ) from exc
            changed_execution = old is None or (
                replacement.command,
                replacement.cwd,
                replacement.timeout,
            ) != (old.command, old.cwd, old.timeout)
            try:
                after = self.state(replacement)
            except AppError as exc:
                return {
                    **plan,
                    "status": "blocked",
                    "write_performed": True,
                    "code": "state-verification-failed",
                    "issues": [exc.payload()],
                    "follow_up": [],
                }
            return {
                **plan,
                "status": "ok",
                "write_performed": True,
                "environment": self.environment(),
                "inventory_document": self.inventory_path() if replacement.workspace_id else None,
                "scheduler": after,
                "follow_up": self.follow_up(job_id)
                if action in {"create", "update"} and changed_execution
                else [],
            }

    def run(
        self,
        job_id: str,
        confirm: bool,
        expected: str | None = None,
        scheduled: bool = False,
        *,
        on_started: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        with self.lock(), ExitStack() as stack:
            self.check_upgrade()
            job = self.get(job_id)
            self.verify_binding(job)
            digest = hashlib.sha256(json.dumps(job.data(), sort_keys=True).encode()).hexdigest()
            if not confirm:
                return {
                    "status": "planned",
                    "action": "run",
                    "job": job.data(),
                    "expected_plan": digest,
                    "follow_up": [],
                    "write_performed": False,
                }
            if not scheduled and expected != digest:
                raise JobError("stale-plan", "Use --expected-plan from this run preview")
            if scheduled and not self.state(job)["enabled"]:
                raise JobError("busy", "Scheduled trigger ignored: Job is paused")
            stack.enter_context(self.run_lock(job_id))
            if job.workspace_id is not None:
                key = hashlib.sha256(job.workspace_id.encode()).hexdigest()
                stack.enter_context(process_lock(self.home / f"jobs/locks/workspace-{key}.lock"))
            stack.enter_context(self.runs.lease())
            execution = stack.pop_all()
        try:
            self.runs.delete_completed(self.policy.select(self.runs.completed(), datetime.now(UTC)))
            result = run_job(job, self.runs, self.config["log_limit_bytes"], on_started=on_started)
            expired = self.policy.select(self.runs.completed(), datetime.now(UTC))
            self.runs.delete_completed([run for run in expired if run != result["id"]])
            payload = {
                "status": "ok" if result["status"] == "succeeded" else "error",
                "run": result,
                "follow_up": self.run_follow_up(result["id"]),
            }
            if result["status"] != "succeeded":
                payload.update(
                    code="run-failed", message="Process did not succeed; inspect this Run"
                )
            return payload
        finally:
            execution.close()

    def history(
        self, job_id: str | None, limit: int, offset: int, timezone: str = "UTC"
    ) -> list[dict[str, Any]]:
        self.validate_page(limit, offset)
        display_run({}, timezone)
        return [display_run(run, timezone) for run in self.runs.history(job_id, limit, offset)]

    def history_page(self, job_id: str, page: int, page_size: int) -> dict:
        if page < 1:
            raise JobError("invalid-page", "page must be positive")
        rows = self.history(job_id, page_size, (page - 1) * page_size, "local")
        total = self.runs.count(job_id)
        return {
            "status": "ok",
            "list": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }

    def result(self, run_id: str, timezone: str = "UTC") -> dict[str, Any]:
        display_run({}, timezone)
        return display_run(self.runs.result(run_id), timezone)

    def logs(self, run_id: str, limit: int, after: int) -> dict[str, Any]:
        self.validate_page(limit, after)
        chunks = self.runs.logs(run_id, limit, after)
        return {
            "chunks": chunks,
            "next_cursor": chunks[-1]["seq"] if chunks else after,
            "truncated": self.runs.result(run_id)["truncated"] == 1,
        }

    @staticmethod
    def validate_page(limit: int, cursor: int) -> None:
        if not 1 <= limit <= 100 or cursor < 0:
            raise JobError("invalid-page", "limit must be 1..100 and offset/cursor nonnegative")

    def run_follow_up(self, run_id: str) -> list[dict[str, Any]]:
        return [
            {
                "argv": ["campfire", "job", action, run_id],
                "environment": {"CAMPFIRE_HOME": str(self.home)},
                "reason": "Inspect this run and verify expected artifacts",
                "requires_execution_authorization": False,
            }
            for action in ("result", "logs")
        ]

    def cleanup(
        self,
        job_id: str | None,
        older_than: int | None,
        statuses: list[str] | None,
        keep_failures: bool,
        confirm: bool,
        expected: str | None,
    ) -> dict[str, Any]:
        if statuses is not None and not set(statuses) <= {
            "succeeded",
            "failed",
            "timeout",
            "interrupted",
        }:
            raise JobError("invalid-status", "Use succeeded, failed, timeout or interrupted")
        if older_than is not None and older_than < 0:
            raise JobError(
                "invalid-retention", "older-than must be nonnegative rolling 24-hour days"
            )
        with self.lock():
            self.check_upgrade()
            rows = self.runs.completed()
            filters = {
                "job": job_id,
                "older_than": older_than,
                "statuses": statuses,
                "keep_failures": keep_failures,
            }
            ids = self.policy.select(
                rows,
                datetime.now(UTC),
                job_id=job_id,
                statuses=set(statuses) if statuses else None,
                older_than=older_than,
                keep_failures=keep_failures,
            )
            plan = hashlib.sha256(
                json.dumps(
                    {"rows": rows, "ids": ids, "filters": filters, "policy": asdict(self.policy)},
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            result = {
                "status": "planned",
                "expected_plan": plan,
                "filters": filters,
                "policy": asdict(self.policy),
                "delete_count": len(ids),
                "running_excluded": True,
                "reconciled_count": 0,
                "write_performed": False,
            }
            if confirm:
                if expected != plan:
                    raise JobError("stale-plan", "History or cleanup policy changed; preview again")
                # Reconcile only after plan approval and under the execution lock.
                reconciled = 0
                for job in self.runs.running_jobs():
                    if job_id is not None and job != job_id:
                        continue
                    if statuses is not None and "interrupted" not in statuses:
                        continue
                    try:
                        with self.run_lock(job):
                            reconciled += self.runs.reconcile(job, datetime.now(UTC).isoformat())
                    except JobError as exc:
                        if exc.code != "busy":
                            raise
                deleted = self.runs.delete_completed(ids)
                result.update(
                    status="ok",
                    delete_count=deleted,
                    reconciled_count=reconciled,
                    write_performed=bool(deleted or reconciled),
                )
            return result

    def compact(self, confirm: bool, expected: str | None) -> dict[str, Any]:
        with self.lock(), ExitStack() as stack:
            self.check_upgrade()
            jobs = sorted(set(self.repository.read()) | set(self.runs.running_jobs()))
            for job in jobs:
                stack.enter_context(self.run_lock(job))
            path = self.runs.path
            stats = {
                str(file): {"size": file.stat().st_size, "modified": file.stat().st_mtime_ns}
                for file in path.parent.glob("runs.db*")
            }
            plan = self.runs.compaction_state()
            result = {
                "status": "planned",
                "expected_plan": plan,
                "bytes_before": sum(item["size"] for item in stats.values()),
                "write_performed": False,
            }
            if confirm:
                if expected != plan:
                    raise JobError("stale-plan", "Database changed; preview compaction again")
                if path.exists():
                    self.runs.compact()
                result.update(
                    status="ok",
                    write_performed=path.exists(),
                    bytes_after=path.stat().st_size if path.exists() else 0,
                )
            return result
