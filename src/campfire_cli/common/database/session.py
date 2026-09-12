from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from campfire_cli.common.database.models import Base


def create_sqlite_engine(database_path: Path) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{database_path}")

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    return engine


def initialize_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def open_session(engine: Engine) -> Session:
    return Session(engine)
