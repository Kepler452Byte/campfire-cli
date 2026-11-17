"""Disposable execution history, independent of document projections."""

import hashlib
import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    delete,
    insert,
    select,
    update,
)

from campfire_cli.common.database import create_sqlite_engine, database_lease, initialize_database
from campfire_cli.common.exceptions import JobError

METADATA = MetaData()
RUNS = Table(
    "runs",
    METADATA,
    Column("id", String, primary_key=True),
    Column("job_id", String, nullable=False),
    Column("started", String, nullable=False),
    Column("finished", String),
    Column("status", String, nullable=False),
    Column("exit_code", Integer),
    Column("duration", Float),
    Column("truncated", Integer, nullable=False, default=0),
    Column("pid", Integer),
)
Index("runs_job", RUNS.c.job_id, RUNS.c.started)
LOGS = Table(
    "logs",
    METADATA,
    Column("seq", Integer, primary_key=True),
    Column("run_id", String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
    Column("stream", String, nullable=False),
    Column("content", Text, nullable=False),
)
Index("logs_run", LOGS.c.run_id, LOGS.c.seq)


class RunRepository:
    def __init__(self, path: Path):
        self.path = path
        self.engine = None
        self.history_rebuilt = False

    def initialize(self) -> None:
        if self.engine is None:
            existed = self.path.exists()
            engine = create_sqlite_engine(self.path)
            try:
                rebuilt = initialize_database(engine, METADATA)
                self.history_rebuilt = self.history_rebuilt or (existed and rebuilt)
            except BaseException:
                engine.dispose()
                raise
            self.engine = engine

    @contextmanager
    def connection(self):
        self.initialize()
        with self.engine.begin() as connection:
            yield connection

    @contextmanager
    def lease(self):
        self.initialize()
        with database_lease(self.path):
            yield

    def start(self, run_id: str, job_id: str, pid: int, started: str) -> None:
        with self.connection() as db:
            db.execute(
                update(RUNS)
                .where(RUNS.c.job_id == job_id, RUNS.c.status == "running")
                .values(status="interrupted", finished=started)
            )
            db.execute(
                insert(RUNS).values(
                    id=run_id,
                    job_id=job_id,
                    started=started,
                    status="running",
                    pid=pid,
                )
            )

    def append(self, run_id: str, stream: str, content: str) -> None:
        with self.connection() as db:
            db.execute(insert(LOGS).values(run_id=run_id, stream=stream, content=content))

    def finish(
        self,
        run_id: str,
        status: str,
        code: int | None,
        duration: float,
        truncated: bool,
        finished: str,
    ) -> None:
        with self.connection() as db:
            db.execute(
                update(RUNS)
                .where(RUNS.c.id == run_id)
                .values(
                    finished=finished,
                    status=status,
                    exit_code=code,
                    duration=duration,
                    truncated=int(truncated),
                )
            )

    def history(self, job_id: str | None, limit: int, offset: int) -> list[dict]:
        if not self.path.exists():
            return []
        query = select(RUNS).order_by(RUNS.c.started.desc(), RUNS.c.id.desc())
        if job_id is not None:
            query = query.where(RUNS.c.job_id == job_id)
        with self.connection() as db:
            return [dict(row) for row in db.execute(query.limit(limit).offset(offset)).mappings()]

    def result(self, run_id: str) -> dict:
        if self.path.exists():
            with self.connection() as db:
                row = db.execute(select(RUNS).where(RUNS.c.id == run_id)).mappings().first()
                if row is not None:
                    return dict(row)
        raise JobError("not-found", "Run does not exist")

    def logs(self, run_id: str, limit: int, after: int) -> list[dict]:
        self.result(run_id)
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    select(LOGS.c.seq, LOGS.c.stream, LOGS.c.content)
                    .where(LOGS.c.run_id == run_id, LOGS.c.seq > after)
                    .order_by(LOGS.c.seq)
                    .limit(limit)
                ).mappings()
            ]

    def completed(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    select(RUNS)
                    .where(RUNS.c.finished.is_not(None), RUNS.c.status != "running")
                    .order_by(RUNS.c.finished.desc(), RUNS.c.id.desc())
                ).mappings()
            ]

    def delete_completed(self, ids: list[str]) -> int:
        if not ids:
            return 0
        with self.connection() as db:
            return db.execute(
                delete(RUNS).where(
                    RUNS.c.id.in_(ids), RUNS.c.finished.is_not(None), RUNS.c.status != "running"
                )
            ).rowcount

    def running_jobs(self) -> list[str]:
        if not self.path.exists():
            return []
        with self.connection() as db:
            return list(
                db.execute(
                    select(RUNS.c.job_id).where(RUNS.c.status == "running").distinct()
                ).scalars()
            )

    def reconcile(self, job_id: str, finished: str) -> int:
        with self.connection() as db:
            return db.execute(
                update(RUNS)
                .where(RUNS.c.job_id == job_id, RUNS.c.status == "running")
                .values(status="interrupted", finished=finished)
            ).rowcount

    def compaction_state(self) -> str:
        if not self.path.exists():
            return "missing"
        signature = hashlib.sha256()
        with self.connection() as db:
            signature.update(
                json.dumps(
                    [
                        db.exec_driver_sql("PRAGMA page_count").scalar(),
                        db.exec_driver_sql("PRAGMA freelist_count").scalar(),
                    ]
                ).encode()
            )
            for table, key in ((RUNS, RUNS.c.id), (LOGS, LOGS.c.seq)):
                signature.update(table.name.encode())
                for row in db.execute(select(table).order_by(key)):
                    content = json.dumps(list(row), ensure_ascii=False).encode()
                    signature.update(str(len(content)).encode() + b":" + content)
        return signature.hexdigest()

    def compact(self) -> None:
        self.close()
        with database_lease(self.path, exclusive=True), closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.execute("VACUUM")
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def close(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None
