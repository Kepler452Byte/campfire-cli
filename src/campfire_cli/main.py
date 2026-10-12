from __future__ import annotations

import sys
from contextlib import suppress
from typing import Any

import typer

from campfire_cli.app.agent_resources.cli.skill_cli import skill_cli
from campfire_cli.app.agent_resources.service.agent_resource_service import AgentResourceService
from campfire_cli.app.base.cli.base_cli import base_cli
from campfire_cli.app.document.cli.document_cli import document_cli
from campfire_cli.app.maintenance.cli.maintenance_cli import maintenance_cli
from campfire_cli.app.system.cli.system_cli import register_system_commands, version_option
from campfire_cli.app.video.cli.video_cli import video_cli
from campfire_cli.app.workspace.cli.config_cli import config_cli
from campfire_cli.app.workspace.cli.domain_cli import domain_cli
from campfire_cli.app.workspace.cli.git_cli import git_cli
from campfire_cli.app.workspace.cli.project_cli import project_cli
from campfire_cli.app.workspace.cli.restructure_cli import restructure_cli
from campfire_cli.app.workspace.cli.space_cli import space_cli
from campfire_cli.app.workspace.cli.workspace_cli import workspace_cli
from campfire_cli.common.cli_output import JsonTyperGroup, emit
from campfire_cli.common.exceptions import AppError
from campfire_cli.container import AppContainer

# Windows 控制台默认 GBK 代码页会把中文输出编码成 GBK 导致乱码；
# 统一以 UTF-8 输出（测试环境的替换流没有 reconfigure，直接跳过）。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        with suppress(OSError, ValueError):
            _stream.reconfigure(encoding="utf-8")

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


class LazyContainer:
    """Delay Workspace discovery until a command actually requests an application service."""

    def __init__(self, workspace: str | None) -> None:
        self._workspace = workspace
        self._container: AppContainer | None = None
        self._skill: AgentResourceService | None = None

    def __getattr__(self, name: str) -> Any:
        # Skill 是全局资源（同步到 ~/.claude/skills 等），不依赖任何已注册
        # Workspace；单独构建，避免首次安装时尚未注册 Workspace 就无法使用。
        if name == "skill":
            if self._skill is None:
                self._skill = AppContainer.build_skill()
            return self._skill
        if self._container is None:
            try:
                self._container = AppContainer.build(self._workspace)
            except AppError as exc:
                emit(exc.payload(), err=True)
                raise typer.Exit(exc.exit_code) from exc
        return getattr(self._container, name)


app = typer.Typer(
    add_completion=False,
    help="人类与 Agent 共用的 Workspace 文档治理 CLI",
    no_args_is_help=True,
    context_settings=CONTEXT_SETTINGS,
    cls=JsonTyperGroup,
)
workspace_cli.add_typer(git_cli, name="git")
workspace_cli.add_typer(project_cli, name="project")
workspace_cli.add_typer(space_cli, name="space")
workspace_cli.add_typer(domain_cli, name="domain")
workspace_cli.add_typer(config_cli, name="config")
workspace_cli.add_typer(restructure_cli, name="restructure")
app.add_typer(workspace_cli, name="workspace")
app.add_typer(document_cli, name="document")
app.add_typer(maintenance_cli, name="maintenance")
app.add_typer(skill_cli, name="skill")
app.add_typer(base_cli, name="base")
app.add_typer(video_cli, name="video")


@app.callback()
def main(
    ctx: typer.Context,
    workspace: str | None = typer.Option(None, "--workspace", help="已注册 Workspace 的稳定 id"),
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=version_option,
        is_eager=True,
        help="显示安装包版本并退出",
    ),
) -> None:
    """初始化目标 Workspace 的应用依赖。"""
    if ctx.invoked_subcommand in {None, "version", "setup", "workspace", "document"}:
        return
    ctx.obj = LazyContainer(workspace)


register_system_commands(app)
