"""JSON delivery for read-only script project browsing."""

import typer

from campfire_cli.common.cli_output import emit, invoke
from campfire_cli.container import AppContainer

script_cli = typer.Typer(help="只读浏览本机 scripts 顶级脚本项目；文件由用户或 Agent 维护")


@script_cli.command("list")
def projects():
    """列出本机脚本项目及脚本根目录，不创建目录。"""
    emit(invoke(lambda: AppContainer.build_script().projects()))


@script_cli.command("tree")
def directory(
    project: str, path: str = typer.Option("", "--path", help="项目内相对目录，返回当前层条目")
):
    """查询脚本项目的一层目录；不跟随符号链接。"""
    emit(invoke(lambda: AppContainer.build_script().directory(project, path)))


@script_cli.command("read")
def read(project: str, path: str = typer.Option(..., "--path", help="项目内相对 UTF-8 文件路径")):
    """读取当前文件正文，不读取历史版本或执行文件。"""
    emit(invoke(lambda: AppContainer.build_script().file(project, path)))
