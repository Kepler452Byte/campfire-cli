from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from campfire_cli import __version__
from campfire_cli.app.agent_resources.service.agent_hints import (
    default_hint_paths,
    inject_agent_hint,
)
from campfire_cli.app.agent_resources.service.agent_resource_service import AgentResourceService
from campfire_cli.app.workspace.repository.workspace_repository import FilesystemWorkspaceRepository
from campfire_cli.app.workspace.service.config_service import WorkspaceConfigService
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.package_version import (
    default_align_command,
    detect_install_method,
    fetch_latest_version,
    is_newer_version,
    spawn_detached_updater,
)
from campfire_cli.config.settings import campfire_home

if TYPE_CHECKING:
    from campfire_cli.container import AppContainer

PACKAGE_NAME = "campfire-cli"


class SystemService:
    def __init__(
        self,
        workspace_builder: Callable[[str | Path | None], AppContainer],
        skill: AgentResourceService,
    ):
        self.workspace_builder = workspace_builder
        self.skill = skill

    def setup(
        self, workspace: Path, make_default: bool = False, workspace_id: str | None = None
    ) -> dict:
        """Bootstrap one device from the portable Workspace Manifest."""
        governance_root = campfire_home()
        setup_result = WorkspaceService(
            governance_root, FilesystemWorkspaceRepository(governance_root)
        ).setup(workspace, make_default, workspace_id)
        container = self.workspace_builder(setup_result.workspace_id)
        settings = container.settings
        health = container.maintenance.check().model_dump(mode="json")
        return {
            **setup_result.model_dump(mode="json"),
            "resources": {
                "config": WorkspaceConfigService(settings).check().model_dump(mode="json"),
                "skills": container.skill.sync(dry_run=False).model_dump(mode="json"),
                "bases": container.base.sync(dry_run=False).model_dump(mode="json"),
                "agent_hints": self._inject_hints(),
            },
            "health": health,
            "status": (
                health["status"]
                if health["status"] != "ok"
                else "needs-review"
                if setup_result.binding_issues
                else "needs-input"
                if setup_result.unbound_repositories
                else "ok"
            ),
        }

    def setup_global_resources(self) -> dict:
        """无 Workspace 时的降级 setup：同步不依赖 Manifest 的全局资源，跳过其余步骤。"""
        return {
            "status": "needs-input",
            "message": (
                "未指定 Workspace：已同步全局治理资源；接入 Workspace 后可执行完整 setup。"
                "按场景选择以下入口之一"
            ),
            "paths": [
                {
                    "scenario": "接入已有 Vault（目录已存在，含或不含 .campfire.yaml）",
                    "command": "campfire setup --path <vault路径> [--id <id>] --default",
                },
                {
                    "scenario": "从零创建新 Workspace（初始化目录结构并注册）",
                    "command": "campfire workspace create --id <id> --path <路径> --default",
                },
                {
                    "scenario": "已注册 Workspace 的本机资源全量对齐",
                    "command": "campfire upgrade",
                },
            ],
            "resources": {
                "skills": self.skill.sync(dry_run=False).model_dump(mode="json"),
                "agent_hints": self._inject_hints(),
            },
            "skipped": [
                "workspace-registration",
                "manifest",
                "config-check",
                "bases",
                "document-index",
                "health-check",
            ],
        }

    def upgrade(self, skip_package: bool = False) -> dict:
        """一条幂等命令完成 campfire 升级：更新 Python 包本身，再对齐治理资源。

        包更新按检测到的安装方式在独立进程中执行，完成后由新版 CLI 自动执行
        资源对齐。离线、已是最新、editable 或无法识别安装方式时跳过包更新，
        仅对齐本机资源。
        """
        home = campfire_home()
        package = self._plan_package_update(skip_package)
        if package["action"] == "updater-spawned":
            return {
                "status": "ok",
                "database": {"status": "up-to-date"},
                "package": package,
                "resources": "deferred",
                "note": (
                    "更新器已启动：等待本进程退出后更新 Python 包，"
                    "并自动执行 campfire upgrade --skip-package 对齐治理资源"
                ),
            }
        workspaces = []
        workspace_repository = FilesystemWorkspaceRepository(home)
        for workspace_id in workspace_repository.load_registry().workspaces:
            project_sync = {
                "status": "ok",
                "project_count": len(workspace_repository.list_projects(workspace_id)),
            }
            container = self.workspace_builder(workspace_id)
            workspaces.append(
                {
                    "workspace_id": workspace_id,
                    "projects": project_sync,
                    "bases": container.base.sync(dry_run=False).model_dump(mode="json"),
                }
            )
        return {
            "status": "ok",
            "database": {"status": "up-to-date"},
            "package": package,
            "skills": self.skill.sync(dry_run=False).model_dump(mode="json"),
            "agent_hints": self._inject_hints(),
            "workspaces": workspaces,
        }

    @staticmethod
    def _plan_package_update(skip_package: bool) -> dict[str, object]:
        installed = __version__
        latest = fetch_latest_version(PACKAGE_NAME)
        package: dict[str, object] = {
            "installed": installed,
            "latest": latest,
            "update_available": latest is not None and is_newer_version(latest, installed),
        }
        if skip_package:
            package["action"] = "skipped-by-flag"
        elif latest is None:
            package["action"] = "skipped-offline"
        elif not package["update_available"]:
            package["action"] = "up-to-date"
        else:
            install = detect_install_method(PACKAGE_NAME)
            align = default_align_command()
            if install.update_command is not None and align is not None:
                spawn_detached_updater(install.update_command, align)
                package["action"] = "updater-spawned"
                package["update_command"] = install.update_command
            else:
                package["action"] = f"skipped-{install.manager}"
                if install.hint:
                    package["hint"] = install.hint
        return package

    @staticmethod
    def _inject_hints() -> list[dict[str, str]]:
        return [
            {"path": str(path), "action": inject_agent_hint(path)} for path in default_hint_paths()
        ]
