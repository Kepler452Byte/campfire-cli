from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(Text, unique=True, index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    document_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    domain_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exists: Mapped[bool] = mapped_column(Boolean, default=True)
    indexed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class GovernanceIssue(Base):
    __tablename__ = "governance_issues"
    __table_args__ = (UniqueConstraint("path", "code", "detail"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(Text)
    code: Mapped[str] = mapped_column(String(96), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), default="error")
    status: Mapped[str] = mapped_column(String(16), default="open")


class MaintenanceRun(Base):
    __tablename__ = "maintenance_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), unique=True)
    status: Mapped[str] = mapped_column(String(24))
    scanned_count: Mapped[int] = mapped_column(Integer, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MigrationBatch(Base):
    __tablename__ = "migration_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_uuid: Mapped[str] = mapped_column(String(36), unique=True)
    batch_name: Mapped[str] = mapped_column(String(128), unique=True)
    scope: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="inventoried")
    config_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class MigrationItem(Base):
    __tablename__ = "migration_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("migration_batches.id"), index=True)
    item_uuid: Mapped[str] = mapped_column(String(36), unique=True)
    source_path: Mapped[str] = mapped_column(Text)
    target_path: Mapped[str] = mapped_column(Text)
    source_hash: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    proposed_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(16), default="low")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_status: Mapped[str] = mapped_column(String(24), default="pending")
