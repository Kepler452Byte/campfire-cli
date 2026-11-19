"""Launch the optional local browser entry without loading it for other commands."""

import typer

from campfire_cli.common.cli_output import invoke


def web(
    port: int = typer.Option(0, "--port", min=0, max=65535, help="本机端口，0 为自动选择"),
    no_open: bool = typer.Option(False, "--no-open", help="不自动打开浏览器，可通过 SSH 转发访问"),
) -> None:
    """启动本机 Web 管理页；CLI 与定时任务不依赖此服务。"""
    from campfire_cli.web.runtime import serve

    invoke(lambda: serve(port, no_open))
