from __future__ import annotations

import json

import typer

HELP_SETTINGS = {"help_option_names": ["-h", "--help"]}

maintenance_cli = typer.Typer(help="后续增量文档维护", context_settings=HELP_SETTINGS)
archive_cli = typer.Typer(help="项目文档两阶段归档", context_settings=HELP_SETTINGS)
maintenance_cli.add_typer(archive_cli, name="archive")


def emit(result: object) -> None:
    typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


@maintenance_cli.command("check")
def check(
    ctx: typer.Context,
    scope: str | None = typer.Option(None, "--scope", help="只显示指定 Vault 相对路径下的问题"),
    code: str | None = typer.Option(None, "--code", help="只显示指定错误代码"),
    severity: str | None = typer.Option(None, "--severity", help="只显示指定严重级别"),
    summary: bool = typer.Option(False, "--summary", help="只输出统计，不展开问题列表"),
) -> None:
    """检查当前受管文档并刷新 SQLite 当前状态。"""
    emit(ctx.obj.maintenance.check(scope=scope, code=code, severity=severity, summary=summary))


@maintenance_cli.command("sync")
def sync(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run"),
    scope: str | None = typer.Option(None, "--scope", help="只同步指定领域或治理根目录"),
) -> None:
    """同步 MOC 等确定性派生内容。"""
    emit(ctx.obj.maintenance.sync(dry_run, scope))


@archive_cli.command("check")
def archive_check(
    ctx: typer.Context,
    scope: str | None = typer.Option(None, "--scope", help="只检查指定 Vault 相对路径"),
) -> None:
    """只读检查归档候选。"""
    emit(ctx.obj.maintenance.archive(False, scope))


@archive_cli.command("apply")
def archive_apply(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--confirm"),
    scope: str | None = typer.Option(None, "--scope", help="只归档指定 Vault 相对路径"),
) -> None:
    """执行已经标记并通过检查的归档请求。"""
    emit(ctx.obj.maintenance.archive(confirm, scope))
