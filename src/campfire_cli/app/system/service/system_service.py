from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from campfire_cli.app.agent_resources.service.agent_resource_service import AgentResourceService
from campfire_cli.app.workspace.repository.workspace_repository import FilesystemWorkspaceRepository
from campfire_cli.app.workspace.service.config_service import WorkspaceConfigService
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.database import create_sqlite_engine, initialize_database
from campfire_cli.common.exceptions import AppError
from campfire_cli.config.settings import campfire_home

if TYPE_CHECKING:
    from campfire_cli.container import AppContainer


class SystemService:
    def __init__(
        self,
        workspace_builder: Callable[[str | Path | None], AppContainer],
        skill: AgentResourceService,
    ):
        self.workspace_builder = workspace_builder
        self.skill = skill
        self.workspace_repository = FilesystemWorkspaceRepository(campfire_home())

    def setup(
        self,
        workspace: Path,
        make_default: bool = False,
        workspace_id: str | None = None,
        verbose: bool = True,
    ) -> dict:
        preflight = self.align_resources(dry_run=True)
        if preflight["skills"]["status"] == "blocked":
            return self._summarize(
                {
                    "status": "blocked",
                    "resources": preflight,
                    "skipped": ["workspace-registration", "config-check", "bases", "health-check"],
                },
                verbose,
            )
        setup = WorkspaceService(campfire_home(), self.workspace_repository).setup(
            workspace, make_default, workspace_id
        )
        container = self.workspace_builder(setup.workspace_id)
        aligned = self.align_resources()
        health = container.maintenance.check().model_dump(mode="json")
        resources = {
            "config": WorkspaceConfigService(container.settings).check().model_dump(mode="json"),
            **aligned,
            "bases": container.base.sync(dry_run=False).model_dump(mode="json"),
        }
        status = (
            "blocked"
            if any(
                item.get("status") not in {"ok", "synced", "up-to-date"}
                for item in resources.values()
                if isinstance(item, dict)
            )
            else health["status"]
            if health["status"] != "ok"
            else "needs-review"
            if setup.binding_issues
            else "needs-input"
            if setup.unbound_repositories
            else "ok"
        )
        return self._summarize(
            {
                **setup.model_dump(mode="json"),
                "resources": resources,
                "health": health,
                "status": status,
            },
            verbose,
        )

    def setup_global_resources(self, verbose: bool = True) -> dict:
        aligned = self.align_resources()
        return self._summarize(
            {
                "status": "blocked" if aligned["skills"]["status"] == "blocked" else "needs-input",
                "message": "未指定 Workspace：已对齐可完成的全局资源；接入后执行完整 setup。",
                "paths": [
                    {
                        "scenario": "接入已有 Vault",
                        "command": "campfire setup --path <vault路径> [--id <id>] --default",
                    },
                    {
                        "scenario": "创建 Workspace",
                        "command": "campfire workspace create --id <id> --path <路径> --default",
                    },
                    {
                        "scenario": "已注册 Workspace 资源对齐",
                        "command": "campfire upgrade --skip-package",
                    },
                ],
                "resources": aligned,
                "skipped": [
                    "workspace-registration",
                    "manifest",
                    "config-check",
                    "bases",
                    "document-index",
                    "health-check",
                ],
            },
            verbose,
        )

    @staticmethod
    def _summarize(result: dict, verbose: bool) -> dict:
        if verbose:
            return result
        result["resources"] = {
            key: {
                **{k: v for k, v in value.items() if k != "operations"},
                "operation_count": len(value.get("operations", [])),
            }
            if isinstance(value, dict)
            else value
            for key, value in result["resources"].items()
        }
        result["details_hint"] = (
            "Repeat setup with --verbose to obtain resource operations and hashes."
        )
        return result

    def align(self) -> dict:
        resources = self.align_resources()
        try:
            engine = create_sqlite_engine(campfire_home() / "campfire.db")
            try:
                initialize_database(engine)
            finally:
                engine.dispose()
            database = {"status": "up-to-date"}
        except (OSError, ValueError, SQLAlchemyError) as exc:
            database = {"status": "blocked", "message": str(exc)}
        workspaces = []
        for workspace_id in self.workspace_repository.load_registry().workspaces:
            item = {"workspace_id": workspace_id}
            try:
                container = self.workspace_builder(workspace_id)
                item["projects"] = {
                    "status": "ok",
                    "project_count": len(self.workspace_repository.list_projects(workspace_id)),
                }
                item["config"] = (
                    WorkspaceConfigService(container.settings).check().model_dump(mode="json")
                )
                item["bases"] = container.base.sync(dry_run=False).model_dump(mode="json")
                item["status"] = (
                    "blocked"
                    if any(
                        value.get("status") not in {"ok", "synced", "up-to-date"}
                        for value in (item["config"], item["bases"])
                    )
                    else "ok"
                )
            except (AppError, OSError, ValueError, SQLAlchemyError) as exc:
                item.update(
                    {
                        "status": "blocked",
                        "message": str(exc),
                        "code": (exc.code or exc.error_code)
                        if isinstance(exc, AppError)
                        else "workspace-alignment-failed",
                        "skipped": [stage for stage in ("config", "bases") if stage not in item],
                    }
                )
            workspaces.append(item)
        return {
            "status": "blocked"
            if resources["skills"]["status"] == "blocked"
            or database["status"] == "blocked"
            or any(item["status"] != "ok" for item in workspaces)
            else "ok",
            "database": database,
            **resources,
            "workspaces": workspaces,
        }

    def align_resources(self, dry_run: bool = False) -> dict:
        """Align global resources and report preflight or write failures."""
        try:
            return self.skill.align(dry_run=dry_run)
        except (AppError, OSError, ValueError, SQLAlchemyError) as exc:
            return {
                "skills": {
                    "status": "blocked",
                    "operations": [],
                    "completed_operations": [],
                    "issues": [
                        {
                            "code": (exc.code or exc.error_code)
                            if isinstance(exc, AppError)
                            else "resource-preflight-failed",
                            "message": str(exc),
                        }
                    ],
                },
                "agent_hints": [],
            }
