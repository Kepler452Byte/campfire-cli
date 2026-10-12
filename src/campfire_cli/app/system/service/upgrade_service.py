from __future__ import annotations

import json
import uuid

from campfire_cli.app.system.service.system_service import SystemService
from campfire_cli.common.filesystem.resource_files import atomic_write, write_lock
from campfire_cli.common.package_updater import PackageUpdater, plan_digest
from campfire_cli.common.package_version import (
    fetch_latest_version,
    installed_version,
    is_newer_version,
)


class UpgradeService:
    def __init__(self, system: SystemService, updater: PackageUpdater):
        self.system = system
        self.updater = updater

    def upgrade(self, skip_package: bool = False) -> dict:
        installed = installed_version()
        # Explicit offline alignment never opens a network connection.
        latest = None if skip_package else fetch_latest_version("campfire-cli")
        package = {
            "installed": installed,
            "latest": latest,
            "update_available": latest is not None and is_newer_version(latest, installed),
        }
        plan = self.updater.plan()
        package["manager"] = plan["manager"]
        if skip_package:
            package["action"] = "skipped-by-flag"
        elif not plan["supported"]:
            package.update(action="skipped-" + str(plan["manager"]), hint=plan["hint"])
        elif latest is None:
            package["action"] = "skipped-offline"
        elif not package["update_available"]:
            package["action"] = "up-to-date"
        else:
            preflight = self.system.align_resources(dry_run=True)
            if preflight["skills"]["status"] == "blocked":
                package["action"] = "blocked"
                return self._record(
                    {
                        "status": "blocked",
                        "version": installed,
                        "package": package,
                        **preflight,
                        "skipped": ["package-update", "workspace-alignment"],
                    },
                    "skipped",
                )
            plan["target_version"] = latest
            operation = self.updater.start(plan, plan_digest(plan))
            package.update(action="updater-spawned", update_command=plan["update_command"])
            return {
                "status": "planned",
                "version": installed,
                "package": package,
                "resources": "deferred",
                **operation,
                "follow_up": [
                    {
                        "argv": ["campfire", "agent", "upgrade-status", operation["operation_id"]],
                        "reason": "Verify package and resource completion",
                    }
                ],
            }
        aligned = self.system.align()
        result = {**aligned, "version": installed, "package": package}
        return self._record(result, "completed" if package["action"] == "up-to-date" else "skipped")

    def _record(self, result: dict, package_stage: str) -> dict:
        """Persist a synchronous attempt for the public operation query."""
        operation_id = uuid.uuid4().hex
        job = {
            "operation_id": operation_id,
            "package": "campfire-cli",
            "state": "completed" if result["status"] == "ok" else "failed",
            "package_stage": package_stage,
            "resource_stage": "completed" if result["status"] == "ok" else "failed",
            "installed_version": result["version"],
            "resources": result,
        }
        with write_lock(self.updater.state_root):
            atomic_write(
                self.updater.state_root / "upgrades" / operation_id / "result.json",
                json.dumps(job, ensure_ascii=False).encode(),
            )
        result["operation_id"] = operation_id
        return result

    def status(self, operation_id: str) -> dict:
        result = self.updater.status(operation_id)
        return {"status": "blocked" if result["state"] == "failed" else "ok", **result}
