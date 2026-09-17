from __future__ import annotations

import typer

from campfire_cli.common.cli_output import emit

base_cli = typer.Typer(
    help="管理 Obsidian Base 标准治理视图", context_settings={"help_option_names": ["-h", "--help"]}
)


@base_cli.command("list")
def list_bases(ctx: typer.Context) -> None:
    """列出包内 SSOT Base 及 Vault 同步状态。"""
    emit(ctx.obj.base.list())


@base_cli.command("show")
def show(ctx: typer.Context, name: str, source: str = typer.Option("ssot", "--source")) -> None:
    """读取一个 Base；source 可选 ssot 或 vault。"""
    emit(ctx.obj.base.show(name, source))


@base_cli.command("check")
def check(ctx: typer.Context) -> None:
    """只读检查 Base 配置、YAML 和同步状态。"""
    emit(ctx.obj.base.check())


@base_cli.command("sync")
def sync(ctx: typer.Context, dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    """将托管 Base 从包内 SSOT 确定性同步到 Vault。"""
    emit(ctx.obj.base.sync(dry_run))
