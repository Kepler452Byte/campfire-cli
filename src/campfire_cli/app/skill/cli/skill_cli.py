from __future__ import annotations

import typer

from campfire_cli.common.cli_output import emit

skill_cli = typer.Typer(
    help="发现、加载、校验和同步 Agent SOP Skill",
    context_settings={"help_option_names": ["-h", "--help"]},
)


@skill_cli.command("list")
def list_skills(ctx: typer.Context) -> None:
    """列出包内 SSOT Skill 及全局同步状态。"""
    emit(ctx.obj.skill.list())


@skill_cli.command("show")
def show(ctx: typer.Context, name: str, source: str = typer.Option("ssot", "--source")) -> None:
    """读取一个 Skill；source 可选 ssot 或 global。"""
    emit(ctx.obj.skill.show(name, source))


@skill_cli.command("resolve")
def resolve(ctx: typer.Context, path: str = typer.Option(..., "--path")) -> None:
    """根据目标文档路径解析 Agent 应加载的 Skill。"""
    emit(ctx.obj.skill.resolve(path))


@skill_cli.command("check")
def check(ctx: typer.Context) -> None:
    """只读校验 SSOT、配置和同步状态。"""
    emit(ctx.obj.skill.check())


@skill_cli.command("sync")
def sync(ctx: typer.Context, dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    """将托管 Skill 从包内 SSOT 确定性同步到全局 Agent 目录。"""
    emit(ctx.obj.skill.sync(dry_run))
