from __future__ import annotations

import json
from pathlib import Path

import typer

from campfire_cli.common.exceptions import AppError
from campfire_cli.container import AppContainer

adoption_cli = typer.Typer(
    help="把已有文档文件夹安全接管为受管 Domain",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def service(ctx: typer.Context):
    return AppContainer.build(ctx.find_root().params.get("workspace")).adoption


def invoke(operation) -> None:
    try:
        result = operation()
        typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    except AppError as exc:
        typer.echo(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        raise typer.Exit(exc.exit_code) from exc


@adoption_cli.command("inventory")
def inventory(
    ctx: typer.Context,
    source: Path = typer.Option(..., "--source"),
    batch: str = typer.Option(..., "--batch"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """盘点目录；外部来源追加 --confirm 后复制到待接管暂存区。"""
    invoke(lambda: service(ctx).inventory(batch, source, confirm))


@adoption_cli.command("plan")
def plan(
    ctx: typer.Context,
    batch: str = typer.Option(..., "--batch"),
    target_path: str = typer.Option(..., "--target-path"),
    domain_id: str = typer.Option(..., "--domain-id"),
    name: str = typer.Option(..., "--name"),
    space_id: str = typer.Option(..., "--space"),
    domain_type: str = typer.Option(..., "--type"),
    governance: str = typer.Option(..., "--governance"),
    parent_domain: str | None = typer.Option(None, "--parent-domain"),
    project_id: str | None = typer.Option(None, "--project"),
) -> None:
    """声明整个来源文件夹的目标 Domain，并生成接管计划。"""
    invoke(
        lambda: service(ctx).plan(
            batch,
            target_path=target_path,
            domain_id=domain_id,
            name=name,
            space_id=space_id,
            domain_type=domain_type,
            governance=governance,
            parent_domain=parent_domain,
            project_id=project_id,
        )
    )


@adoption_cli.command("apply")
def apply(
    ctx: typer.Context,
    batch: str = typer.Option(..., "--batch"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """预检接管计划；追加 --confirm 后移动到正式领域并建立声明。"""
    invoke(lambda: service(ctx).apply(batch, confirm))


@adoption_cli.command("verify")
def verify(ctx: typer.Context, batch: str = typer.Option(..., "--batch")) -> None:
    """验证文件哈希、领域声明与最终位置。"""
    invoke(lambda: service(ctx).verify(batch))
