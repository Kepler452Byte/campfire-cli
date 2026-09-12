from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from campfire_cli import __version__
from campfire_cli.app.base.cli.base_cli import base_cli
from campfire_cli.app.document.cli.document_cli import document_cli
from campfire_cli.app.maintenance.cli.maintenance_cli import maintenance_cli
from campfire_cli.app.migration.cli.migration_cli import migration_cli
from campfire_cli.app.skill.cli.skill_cli import skill_cli
from campfire_cli.app.workspace.cli.project_cli import project_cli
from campfire_cli.app.workspace.cli.workspace_cli import initialize, workspace_cli
from campfire_cli.common.exceptions import AppError
from campfire_cli.container import AppContainer

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


class LazyContainer:
    """Delay Workspace discovery until a command actually requests an application service."""

    def __init__(self, workspace: str | None) -> None:
        self._workspace = workspace
        self._container: AppContainer | None = None

    def __getattr__(self, name: str) -> Any:
        if self._container is None:
            try:
                self._container = AppContainer.build(self._workspace)
            except AppError as exc:
                typer.echo(
                    json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False),
                    err=True,
                )
                raise typer.Exit(exc.exit_code) from exc
        return getattr(self._container, name)


app = typer.Typer(
    help="人类与 Agent 共用的 Workspace 文档治理 CLI",
    no_args_is_help=True,
    context_settings=CONTEXT_SETTINGS,
)
app.add_typer(migration_cli, name="migration")
app.add_typer(maintenance_cli, name="maintenance")
app.add_typer(skill_cli, name="skill")
app.add_typer(base_cli, name="base")
app.add_typer(workspace_cli, name="workspace")
app.add_typer(project_cli, name="project")
app.add_typer(document_cli, name="document")


@app.callback()
def main(
    ctx: typer.Context,
    workspace: str | None = typer.Option(None, "--workspace", help="已注册 Workspace 的 id 或路径"),
) -> None:
    """初始化目标 Workspace 的应用依赖。"""
    if ctx.invoked_subcommand in {None, "version", "init", "workspace", "project", "document"}:
        return
    ctx.obj = LazyContainer(workspace)


@app.command("version")
def version() -> None:
    """显示 CLI 版本。"""
    typer.echo(__version__)


@app.command("init")
def initialize_workspace(
    workspace: Path = typer.Option(..., "--workspace", help="要初始化的 Workspace 根目录"),
    workspace_id: str = typer.Option(..., "--id", help="稳定的 Workspace id"),
    make_default: bool = typer.Option(False, "--default", help="设为默认 Workspace"),
) -> None:
    """注册新 Workspace，并在用户级 CAMPFIRE_HOME 初始化配置和状态目录。"""
    result = initialize(workspace_id, workspace, make_default)
    typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
