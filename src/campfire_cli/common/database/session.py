from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from sqlalchemy import UniqueConstraint, create_engine, inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from campfire_cli.common.database.models import Base
from campfire_cli.common.exceptions import GovernanceBlockedError


@contextmanager
def _lease(path: Path, *, exclusive: bool = False) -> Iterator[None]:
    handle = path.with_suffix(path.suffix + ".lock").open("a+b")
    try:
        if os.name == "nt":
            import ctypes
            import msvcrt
            from ctypes import wintypes

            class Overlapped(ctypes.Structure):
                _fields_ = [
                    ("Internal", ctypes.c_size_t),
                    ("InternalHigh", ctypes.c_size_t),
                    ("Offset", wintypes.DWORD),
                    ("OffsetHigh", wintypes.DWORD),
                    ("hEvent", wintypes.HANDLE),
                ]

            # CRT read-lock modes are exclusive; LockFileEx supports shared leases.
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            lock = kernel.LockFileEx
            lock.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(Overlapped),
            ]
            lock.restype = wintypes.BOOL
            if not lock(
                msvcrt.get_osfhandle(handle.fileno()),
                3 if exclusive else 1,
                0,
                1,
                0,
                ctypes.byref(Overlapped()),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
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
    try:
        yield
    finally:
        try:
            if os.name == "nt":
                unlock = kernel.UnlockFileEx
                unlock.argtypes = [
                    wintypes.HANDLE,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    ctypes.POINTER(Overlapped),
                ]
                unlock.restype = wintypes.BOOL
                unlock(msvcrt.get_osfhandle(handle.fileno()), 0, 1, 0, ctypes.byref(Overlapped()))
        finally:
            handle.close()


class _CacheConnection(sqlite3.Connection):
    lease: ExitStack

    def close(self) -> None:
        try:
            super().close()
        finally:
            self.lease.close()


def create_sqlite_engine(database_path: Path) -> Engine:
    """Create an engine whose live connections prevent cache replacement."""
    database_path.parent.mkdir(parents=True, exist_ok=True)

    def connect() -> _CacheConnection:
        lease = ExitStack()
        lease.enter_context(_lease(database_path))
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
