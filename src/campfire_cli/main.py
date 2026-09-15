from __future__ import annotations

import json
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

import typer

from campfire_cli import __version__
from campfire_cli.app.base.cli.base_cli import base_cli
from campfire_cli.app.decision.cli.decision_cli import decision_cli
from campfire_cli.app.document.cli.document_cli import document_cli
from campfire_cli.app.maintenance.cli.maintenance_cli import maintenance_cli
from campfire_cli.app.skill.cli.skill_cli import skill_cli
from campfire_cli.app.skill.service.skill_service import SkillService
from campfire_cli.app.workspace.cli.config_cli import config_cli
from campfire_cli.app.workspace.cli.domain_cli import domain_cli
from campfire_cli.app.workspace.cli.project_cli import project_cli
from campfire_cli.app.workspace.cli.restructure_cli import restructure_cli
from campfire_cli.app.workspace.cli.space_cli import space_cli
from campfire_cli.app.workspace.cli.workspace_cli import workspace_cli
from campfire_cli.common.exceptions import AppError, ConfigurationError
from campfire_cli.container import AppContainer

# Windows 控制台默认 GBK 代码页会把中文输出编码成 GBK 导致乱码；
# 统一以 UTF-8 输出（测试环境的替换流没有 reconfigure，直接跳过）。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        with suppress(OSError, ValueError):
            _stream.reconfigure(encoding="utf-8")

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


class LazyContainer:
    """Delay Workspace discovery until a command actually requests an application service."""

    def __init__(self, workspace: str | None) -> None:
        self._workspace = workspace
        self._container: AppContainer | None = None
        self._skill: SkillService | None = None

    def __getattr__(self, name: str) -> Any:
        # Skill 是全局资源（同步到 ~/.claude/skills 等），不依赖任何已注册
        # Workspace；单独构建，避免首次安装时尚未注册 Workspace 就无法使用。
        if name == "skill":
            if self._skill is None:
                self._skill = AppContainer.build_skill()
            return self._skill
        if self._container is None:
            try:
                self._container = AppContainer.build(self._workspace)
            except AppError as exc:
                typer.echo(
                    json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False),
                    err=True,
                )
                raise typer.Exit(exc.exit_code) from exc
        return getattr(self._container, name)


app = typer.Typer(
    help="人类与 Agent 共用的 Workspace 文档治理 CLI",
    no_args_is_help=True,
    context_settings=CONTEXT_SETTINGS,
)
workspace_cli.add_typer(project_cli, name="project")
workspace_cli.add_typer(space_cli, name="space")
workspace_cli.add_typer(domain_cli, name="domain")
workspace_cli.add_typer(config_cli, name="config")
workspace_cli.add_typer(restructure_cli, name="restructure")
app.add_typer(workspace_cli, name="workspace")
app.add_typer(document_cli, name="document")
app.add_typer(decision_cli, name="decision")
app.add_typer(maintenance_cli, name="maintenance")
app.add_typer(skill_cli, name="skill")
app.add_typer(base_cli, name="base")


@app.callback()
def main(
    ctx: typer.Context,
    workspace: str | None = typer.Option(None, "--workspace", help="已注册 Workspace 的稳定 id"),
) -> None:
    """初始化目标 Workspace 的应用依赖。"""
    if ctx.invoked_subcommand in {None, "version", "setup", "workspace", "document"}:
        return
    ctx.obj = LazyContainer(workspace)


@app.command("version")
def version() -> None:
    """显示 CLI 版本。"""
    typer.echo(__version__)


def render_command_tree(command: Any, name: str, prefix: str = "") -> list[str]:
    lines = [prefix + name]
    if not hasattr(command, "commands"):
        return lines
    children = [
        (child_name, child)
        for child_name, child in command.commands.items()
        if not getattr(child, "hidden", False)
    ]
    for index, (child_name, child) in enumerate(children):
        last = index == len(children) - 1
        connector = "└── " if last else "├── "
        child_prefix = prefix + ("    " if last else "│   ")
        child_lines = render_command_tree(child, child_name, child_prefix)
        child_lines[0] = prefix + connector + child_name
        lines.extend(child_lines)
    return lines


@app.command("tree")
def tree(ctx: typer.Context) -> None:
    """显示完整 CLI 命令树，便于人类和 Agent 渐进式发现能力。"""
    typer.echo("\n".join(render_command_tree(ctx.find_root().command, "campfire")))


@app.command("setup")
def setup(
    path: Path | None = typer.Option(
        None, "--path", help="要初始化的 Workspace 根目录；缺省时仅同步全局资源并输出接入引导"
    ),
    workspace_id: str | None = typer.Option(
        None, "--id", help="缺少 .campfire.yaml 时使用的稳定 Workspace id"
    ),
    make_default: bool = typer.Option(False, "--default", help="设为默认 Workspace"),
) -> None:
    """从 .campfire.yaml 配置本机，或为已注册 Workspace 创建首份 Manifest。"""
    try:
        if path is None and workspace_id is not None:
            raise ConfigurationError("--id 只能与 --path 一起使用")
        result = (
            AppContainer.setup_global_resources()
            if path is None
            else AppContainer.setup(path, make_default, workspace_id)
        )
    except AppError as exc:
        typer.echo(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        raise typer.Exit(exc.exit_code) from exc
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("upgrade")
def upgrade(
    skip_package: bool = typer.Option(
        False, "--skip-package", hidden=True, help="内部参数：跳过包自更新，仅对齐治理资源"
    ),
) -> None:
    """一条幂等命令升级 campfire：更新包并对齐治理资源（Skill、Base、提示词、Schema）。"""
    try:
        result = AppContainer.upgrade(skip_package=skip_package)
    except AppError as exc:
        typer.echo(
            json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False),
            err=True,
        )
        raise typer.Exit(exc.exit_code) from exc
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
