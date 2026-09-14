from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer

from campfire_cli.app.document.repository.document_profile_repository import (
    DocumentProfileRepository,
)
from campfire_cli.app.document.service.document_profile_service import (
    DocumentProfileService,
)
from campfire_cli.app.workspace.repository.workspace_repository import SqliteWorkspaceRepository
from campfire_cli.app.workspace.service.workspace_service import WorkspaceService
from campfire_cli.common.exceptions import AppError
from campfire_cli.config.settings import WorkspaceSettings, campfire_home
from campfire_cli.common.filesystem.cwd import safe_cwd

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


def invoke(operation: Callable[[], dict[str, Any]]) -> None:
    try:
        typer.echo(json.dumps(operation(), ensure_ascii=False, indent=2))
    except AppError as exc:
        typer.echo(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        raise typer.Exit(exc.exit_code) from exc


@profile_cli.command("list")
def list_profiles(ctx: typer.Context) -> None:
    """列出所有有效 Profile。"""
    invoke(lambda: service(ctx).list_profiles())


@profile_cli.command("show")
def show_profile(ctx: typer.Context, name: str) -> None:
    """显示继承合并后的完整 Profile。"""
    invoke(lambda: service(ctx).show_profile(name))


@profile_cli.command("resolve")
def resolve(ctx: typer.Context, path: str = typer.Option(..., "--path")) -> None:
    """解析一篇文档最终使用的 Profile。"""
    invoke(lambda: service(ctx).resolve(path))
