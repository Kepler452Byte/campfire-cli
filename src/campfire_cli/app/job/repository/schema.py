"""Current persistent task definitions and execution history tables."""

from sqlalchemy import (
    JSON,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

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

JOBS = Table(
    "jobs",
    METADATA,
    Column("id", String, primary_key=True),
    Column("argv", JSON, nullable=False),
    Column("cwd", String, nullable=False),
    Column("schedule", JSON, nullable=False),
    Column("timeout", Integer, nullable=False),
    Column("workspace_id", String),
    Column("workspace_root", String),
    Column("name", String),
    Column("script_project", String),
)
