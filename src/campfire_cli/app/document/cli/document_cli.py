from __future__ import annotations

import typer

from campfire_cli.app.document.cli.profile_cli import profile_cli

document_cli = typer.Typer(
    help="创建、检查和维护文档及其规则",
    context_settings={"help_option_names": ["-h", "--help"]},
)
document_cli.add_typer(profile_cli, name="profile")
