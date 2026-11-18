"""Own the persistent task database without cache replacement or migrations."""

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from campfire_cli.app.job.repository.schema import METADATA
from campfire_cli.common.database import create_sqlite_engine, database_lease, schema_matches
from campfire_cli.common.exceptions import JobError


class JobDatabase:
    def __init__(self, path: Path):
        self.path = path
        self.engine = None

    def exists(self) -> bool:
        """Refuse to present unconverted task storage as an empty task list."""
        if self.path.exists():
            return True
        previous = [self.path.parent.parent / "jobs.yaml", self.path.parent / "runs.db"]
        if any(path.exists() for path in previous):
            raise JobError(
                "job-storage-required",
                "Existing task data requires a one-time agent-assisted move to jobs/jobs.db",
                path=str(self.path),
                hint="Stop Web and active runs; preserve definitions, history and scheduler state",
            )
        return False

    def initialize(self) -> None:
        """Create a missing database; reject incompatible or damaged existing data."""
        if self.engine is not None:
            return
        engine = create_sqlite_engine(self.path)
        try:
            if not self.exists():
                with database_lease(self.path, exclusive=True):
                    if not self.exists():
                        bootstrap = create_engine(engine.url, poolclass=NullPool)
                        try:
                            METADATA.create_all(bootstrap)
                            with bootstrap.connect() as connection:
                                connection.exec_driver_sql("PRAGMA journal_mode=WAL")
                        finally:
                            bootstrap.dispose()
            with engine.connect() as connection:
                if not schema_matches(connection, METADATA):
                    raise JobError(
                        "job-database-incompatible",
                        "Task database structure is incompatible; data was not rebuilt",
                        path=str(self.path),
                        hint="Stop task operations and inspect the database; do not delete it",
                    )
        except BaseException as exc:
            engine.dispose()
            if isinstance(exc, DBAPIError):
                raise self.error(exc) from exc
            raise
        self.engine = engine

    def error(self, exc: DBAPIError) -> JobError:
        code = getattr(exc.orig, "sqlite_errorcode", 0) & 255
        kind = "busy" if code in {5, 6} else "corrupt" if code in {11, 26} else "error"
        return JobError(
            f"job-database-{kind}",
            "Cannot access the task database; data was not rebuilt",
            path=str(self.path),
            hint="Wait if busy; otherwise inspect the task database without deleting it",
        )

    @contextmanager
    def connection(self):
        self.initialize()
        try:
            with self.engine.begin() as connection:
                yield connection
        except DBAPIError as exc:
            raise self.error(exc) from exc

    def close(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None
