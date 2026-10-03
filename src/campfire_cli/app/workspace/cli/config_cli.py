from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli.app.workspace.cli.workspace_cli import resolution
from campfire_cli.app.workspace.service.config_service import WorkspaceConfigService
from campfire_cli.common.cli_output import emit, invoke
from campfire_cli.config.settings import WorkspaceSettings

config_cli = typer.Typer(
    help="检查 Workspace 治理配置契约",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def service(ctx: typer.Context) -> WorkspaceConfigService:
    resolved = resolution(ctx)
    settings = WorkspaceSettings.load(resolved.workspace_id, Path(resolved.workspace))
    return WorkspaceConfigService(settings)


@config_cli.command("check")
def check(ctx: typer.Context) -> None:
    emit(invoke(lambda: service(ctx).check()))
