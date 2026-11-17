from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import UniqueConstraint, create_engine, inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from campfire_cli.common.database.models import Base
from campfire_cli.common.exceptions import GovernanceBlockedError


def _lease(path: Path, *, exclusive: bool = False) -> BinaryIO:
    handle = path.with_suffix(path.suffix + ".lock").open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK if exclusive else msvcrt.LK_NBRLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise GovernanceBlockedError(
            "缓存正在使用，等待其他 Campfire 操作结束后重试",
            code="database-busy",
            path=str(path),
        ) from exc
    return handle


class _CacheConnection(sqlite3.Connection):
    lease: BinaryIO

    def close(self) -> None:
        try:
            super().close()
        finally:
            self.lease.close()


def create_sqlite_engine(database_path: Path) -> Engine:
    """Create an engine whose live connections prevent cache replacement."""
    database_path.parent.mkdir(parents=True, exist_ok=True)

    def connect() -> _CacheConnection:
        lease = _lease(database_path)
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


def _current(connection: Connection) -> bool:
    inspector = inspect(connection)
    actual = set(inspector.get_table_names())
    if actual != set(Base.metadata.tables):
        return False
    for name, table in Base.metadata.tables.items():
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
    return True


def _compatible(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            return _current(connection)
    except DatabaseError as exc:
        if getattr(exc.orig, "sqlite_errorname", "") in {"SQLITE_CORRUPT", "SQLITE_NOTADB"}:
            return False
        raise


def initialize_database(engine: Engine) -> None:
    """Replace incompatible disposable caches without migrations or backups."""
    if _compatible(engine):
        return
    path = Path(engine.url.database)
    engine.dispose()
    # The exclusive lease also excludes other Workspaces sharing this database.
    with _lease(path, exclusive=True):
        bootstrap = create_engine(engine.url, poolclass=NullPool)
        try:
            if _compatible(bootstrap):
                return
            bootstrap.dispose()
            for suffix in ("", "-wal", "-shm"):
                Path(str(path) + suffix).unlink(missing_ok=True)
            Base.metadata.create_all(bootstrap)
            with bootstrap.connect() as connection:
                connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        finally:
            bootstrap.dispose()


def open_session(engine: Engine) -> Session:
    return Session(engine)
