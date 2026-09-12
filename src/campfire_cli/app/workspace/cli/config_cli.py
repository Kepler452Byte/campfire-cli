from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli.app.workspace.cli.workspace_cli import emit, invoke
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.service.config_service import WorkspaceConfigService
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.config.settings import WorkspaceSettings, campfire_home

config_cli = typer.Typer(
    help="检查 Workspace 治理配置契约",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def service(workspace: str | None) -> WorkspaceConfigService:
    home = campfire_home()
    resolved = WorkspaceService(home, SqliteWorkspaceRepository(home)).resolve(
        workspace, Path.cwd()
    )
    settings = WorkspaceSettings.load(resolved.workspace_id, Path(resolved.workspace))
    return WorkspaceConfigService(settings)


@config_cli.command("check")
def check(workspace: str | None = typer.Option(None, "--workspace")) -> None:
    emit(invoke(lambda: service(workspace).check()))
