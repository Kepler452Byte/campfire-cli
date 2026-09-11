from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path

from alembic.config import Config

from alembic import command


def upgrade_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    resource = files("campfire_cli").joinpath("alembic")
    with as_file(resource) as script_location:
        config = Config()
        config.set_main_option("script_location", str(script_location))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
        command.upgrade(config, "head")
