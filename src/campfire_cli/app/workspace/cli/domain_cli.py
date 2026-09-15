from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli.app.workspace.cli.workspace_cli import emit, invoke
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.service.structure_service import DomainService
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.filesystem.cwd import safe_cwd
from campfire_cli.config.settings import campfire_home
from campfire_cli.container import AppContainer

domain_cli = typer.Typer(
    help="管理 Space 内可嵌套的内容领域", context_settings={"help_option_names": ["-h", "--help"]}
)


def service(workspace: str | None) -> DomainService:
    home = campfire_home()
    resolved = WorkspaceService(home, SqliteWorkspaceRepository(home)).resolve(
        workspace, safe_cwd()
    )
    return DomainService(Path(resolved.workspace), home)


def applications(ctx: typer.Context, workspace: str | None) -> AppContainer:
    selector = workspace or ctx.find_root().params.get("workspace")
    return AppContainer.build(selector)


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


@domain_cli.command("adopt")
def adopt(
    ctx: typer.Context,
    source: Path = typer.Option(..., "--source"),
    domain_id: str = typer.Option(..., "--id"),
    name: str = typer.Option(..., "--name"),
    target_path: str = typer.Option(..., "--target-path"),
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
            lambda: applications(ctx, workspace).adoption.adopt(
                source,
                domain_id=domain_id,
                name=name,
                target_path=target_path,
                space_id=space,
                domain_type=domain_type,
                governance=governance,
                parent_domain=parent,
                project_id=project,
                confirm=confirm,
            )
        )
    )


@domain_cli.command("rename")
def rename(
    ctx: typer.Context,
    domain_id: str = typer.Option(..., "--domain"),
    name: str = typer.Option(..., "--name"),
    rename_directory: bool = typer.Option(False, "--rename-directory"),
    target_path: str | None = typer.Option(None, "--target-path"),
    project_name: str | None = typer.Option(None, "--project-name"),
    confirm: bool = typer.Option(False, "--confirm"),
    workspace: str | None = typer.Option(None, "--workspace"),
) -> None:
    """修改领域显示名称；可显式联动目录和 Project 展示名称。"""
    emit(
        invoke(
            lambda: applications(ctx, workspace).domain_restructure.rename(
                domain_id,
                name,
                rename_directory=rename_directory,
                target_path=target_path,
                project_name=project_name,
                confirm=confirm,
            )
        )
    )


@domain_cli.command("move")
def move(
    ctx: typer.Context,
    domain_id: str = typer.Option(..., "--domain"),
    target_path: str = typer.Option(..., "--target-path"),
    parent_domain: str | None = typer.Option(None, "--parent-domain"),
    confirm: bool = typer.Option(False, "--confirm"),
    workspace: str | None = typer.Option(None, "--workspace"),
) -> None:
    """移动完整领域目录，并更新父领域、Project、Manifest 和路径引用。"""
    emit(
        invoke(
            lambda: applications(ctx, workspace).domain_restructure.move(
                domain_id,
                target_path,
                parent_domain=parent_domain,
                confirm=confirm,
            )
        )
    )


@domain_cli.command("rekey")
def rekey(
    ctx: typer.Context,
    domain_id: str = typer.Option(..., "--domain"),
    new_id: str = typer.Option(..., "--new-id"),
    confirm: bool = typer.Option(False, "--confirm"),
    workspace: str | None = typer.Option(None, "--workspace"),
) -> None:
    """高风险修改稳定 domain_id，并更新直接子领域引用。"""
    emit(
        invoke(
            lambda: applications(ctx, workspace).domain_restructure.rekey(
                domain_id, new_id, confirm=confirm
            )
        )
    )
