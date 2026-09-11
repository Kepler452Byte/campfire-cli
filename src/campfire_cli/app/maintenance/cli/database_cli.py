from __future__ import annotations

import json

import typer

database_cli = typer.Typer(
    help="SQLite 初始化、升级、备份和恢复",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def emit(result: dict[str, object]) -> None:
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@database_cli.command("initialize")
def initialize(ctx: typer.Context) -> None:
    """初始化或升级当前 Vault 状态库。"""
    emit(ctx.obj.database.upgrade())


@database_cli.command("upgrade")
def upgrade(ctx: typer.Context) -> None:
    """升级当前 Vault 状态库 Schema。"""
    emit(ctx.obj.database.upgrade())


@database_cli.command("backup")
def backup(ctx: typer.Context) -> None:
    """覆盖当前关键状态快照并保留有限变更。"""
    emit(ctx.obj.database.backup())


@database_cli.command("restore")
def restore(ctx: typer.Context, confirm: bool = typer.Option(False, "--confirm")) -> None:
    """预检或恢复当前关键状态快照。"""
    emit(ctx.obj.database.restore(confirm))
