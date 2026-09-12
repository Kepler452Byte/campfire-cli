from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli.app.workspace.cli.workspace_cli import emit, invoke
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.service.structure_service import DomainService
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.config.settings import campfire_home

domain_cli = typer.Typer(
    help="管理 Space 内可嵌套的内容领域", context_settings={"help_option_names": ["-h", "--help"]}
)


def service(workspace: str | None) -> DomainService:
    home = campfire_home()
    resolved = WorkspaceService(home, SqliteWorkspaceRepository(home)).resolve(
        workspace, Path.cwd()
    )
    return DomainService(Path(resolved.workspace), home)


@domain_cli.command("list")
def list_domains(
    space: str | None = typer.Option(None, "--space"),
    workspace: str | None = typer.Option(None, "--workspace"),
) -> None:
    emit(invoke(lambda: service(workspace).list(space)))


@domain_cli.command("show")
def show(domain_id: str, workspace: str | None = typer.Option(None, "--workspace")) -> None:
    emit(invoke(lambda: service(workspace).show(domain_id)))


@domain_cli.command("check")
def check(workspace: str | None = typer.Option(None, "--workspace")) -> None:
    emit(invoke(lambda: service(workspace).check()))


@domain_cli.command("create")
def create(
    domain_id: str = typer.Option(..., "--id"),
    name: str = typer.Option(..., "--name"),
    path: str = typer.Option(..., "--path"),
    space: str = typer.Option(..., "--space"),
    domain_type: str = typer.Option(..., "--type"),
    governance: str = typer.Option(..., "--governance"),
    parent: str | None = typer.Option(None, "--parent"),
    project: str | None = typer.Option(None, "--project"),
    workspace: str | None = typer.Option(None, "--workspace"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    emit(
        invoke(
            lambda: service(workspace).create(
                domain_id=domain_id,
                name=name,
                path=path,
                space_id=space,
                domain_type=domain_type,
                governance=governance,
                parent_domain=parent,
                project_id=project,
                confirm=confirm,
            )
        )
    )
