from __future__ import annotations

from pathlib import Path

import typer

from campfire_cli.app.document.repository.document_profile_repository import (
    DocumentProfileRepository,
)
from campfire_cli.app.document.service.rules.document_profile_service import (
    DocumentProfileService,
)
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.cli_output import emit, invoke
from campfire_cli.common.filesystem.cwd import safe_cwd
from campfire_cli.config.settings import WorkspaceSettings, campfire_home

profile_cli = typer.Typer(
    help="查看和解析文档 Profile 契约",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def service(ctx: typer.Context) -> DocumentProfileService:
    selector = ctx.find_root().params.get("workspace")
    root = campfire_home()
    resolution = WorkspaceService(root, SqliteWorkspaceRepository(root)).resolve(
        selector, safe_cwd()
    )
    settings = WorkspaceSettings.load(resolution.workspace_id, Path(resolution.workspace))
    return DocumentProfileService(
        settings.workspace_id,
        settings.vault_root,
        settings.document_types,
        DocumentProfileRepository(settings.state_root),
    )


@profile_cli.command("list")
def list_profiles(ctx: typer.Context) -> None:
    """列出所有有效 Profile。"""
    emit(invoke(lambda: service(ctx).list_profiles()))


@profile_cli.command("show")
def show_profile(ctx: typer.Context, name: str) -> None:
    """显示继承合并后的完整 Profile。"""
    emit(invoke(lambda: service(ctx).show_profile(name)))


@profile_cli.command("resolve")
def resolve(
    ctx: typer.Context,
    path: str | None = typer.Option(None, "--path", help="已有文档的 Workspace 相对或绝对路径"),
    document_type: str | None = typer.Option(None, "--type", help="新建文档类型，与 --path 二选一"),
) -> None:
    """按已有文档路径或新建文档类型解析有效 Profile。"""
    emit(invoke(lambda: service(ctx).resolve(path, document_type)))
