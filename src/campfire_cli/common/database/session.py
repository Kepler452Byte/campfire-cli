from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from sqlalchemy import MetaData, UniqueConstraint, create_engine, inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from campfire_cli.common.database.models import Base
from campfire_cli.common.exceptions import GovernanceBlockedError


@contextmanager
def database_lease(path: Path, *, exclusive: bool = False) -> Iterator[None]:
    from campfire_cli.common.filesystem.process_lock import os_lock

    try:
        with os_lock(path.with_suffix(path.suffix + ".lock"), shared=not exclusive):
            yield
    except OSError as exc:
        if not isinstance(exc, BlockingIOError) and getattr(exc, "winerror", None) not in {32, 33}:
            raise
        raise GovernanceBlockedError(
            "数据库正在使用，等待其他 Campfire 操作结束后重试",
            code="database-busy",
            path=str(path),
        ) from exc


class _CacheConnection(sqlite3.Connection):
    lease: ExitStack

    def close(self) -> None:
        try:
            super().close()
        finally:
            self.lease.close()


def create_sqlite_engine(database_path: Path) -> Engine:
    """Create an engine whose live connections hold database maintenance leases."""
    database_path.parent.mkdir(parents=True, exist_ok=True)

    def connect() -> _CacheConnection:
        lease = ExitStack()
        lease.enter_context(database_lease(database_path))
        try:
            connection = sqlite3.connect(
                database_path, factory=_CacheConnection, check_same_thread=False
            )
            connection.lease = lease
            connection.execute("PRAGMA foreign_keys=ON")
            return connection
        except Exception:
            lease.close()
            raise

    return create_engine(f"sqlite:///{database_path}", creator=connect, poolclass=NullPool)


def schema_matches(connection: Connection, metadata: MetaData) -> bool:
    """Check the current table contract without changing persistent data."""
    inspector = inspect(connection)
    actual = set(inspector.get_table_names())
    if actual != set(metadata.tables):
        return False
    for name, table in metadata.tables.items():
        columns = {column["name"]: column for column in inspector.get_columns(name)}
        if set(columns) != set(table.columns.keys()):
            return False
        for column in table.columns:
            found = columns[column.name]
            if (
                found["nullable"] != column.nullable
                or bool(found["primary_key"]) != column.primary_key
                or str(found["type"]) != str(column.type)
            ):
                return False
        expected_unique = {
            tuple(c.name for c in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        if expected_unique != {
            tuple(c["column_names"]) for c in inspector.get_unique_constraints(name)
        }:
            return False
        expected_indexes = {(tuple(c.name for c in i.columns), i.unique) for i in table.indexes}
        if expected_indexes != {
            (tuple(i["column_names"]), i["unique"]) for i in inspector.get_indexes(name)
        }:
            return False
        expected_foreign_keys = {
            (
                tuple(element.parent.name for element in constraint.elements),
                constraint.referred_table.name,
                tuple(element.column.name for element in constraint.elements),
                constraint.ondelete,
            )
            for constraint in table.foreign_key_constraints
        }
        if expected_foreign_keys != {
            (
                tuple(key["constrained_columns"]),
                key["referred_table"],
                tuple(key["referred_columns"]),
                key.get("options", {}).get("ondelete"),
            )
            for key in inspector.get_foreign_keys(name)
        }:
            return False
    return True


def _compatible(engine: Engine, metadata: MetaData) -> bool:
    try:
        with engine.connect() as connection:
            return schema_matches(connection, metadata)
    except DatabaseError as exc:
        if getattr(exc.orig, "sqlite_errorname", "") in {"SQLITE_CORRUPT", "SQLITE_NOTADB"}:
            return False
        raise


def initialize_database(engine: Engine, metadata: MetaData = Base.metadata) -> bool:
    """Replace incompatible disposable caches without migrations or backups."""
    if _compatible(engine, metadata):
        return False
    path = Path(engine.url.database)
    engine.dispose()
    # The exclusive lease also excludes other Workspaces sharing this database.
    with database_lease(path, exclusive=True):
        bootstrap = create_engine(engine.url, poolclass=NullPool)
        try:
            if _compatible(bootstrap, metadata):
                return False
            bootstrap.dispose()
            for suffix in ("", "-wal", "-shm"):
                Path(str(path) + suffix).unlink(missing_ok=True)
            metadata.create_all(bootstrap)
            with bootstrap.connect() as connection:
                connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        finally:
            bootstrap.dispose()
    return True


def open_session(engine: Engine) -> Session:
    return Session(engine)
