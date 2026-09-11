from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from campfire_cli.common.database.models import Base


def create_sqlite_engine(database_path: Path) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return engine


def initialize_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def open_session(engine: Engine) -> Session:
    return Session(engine)
