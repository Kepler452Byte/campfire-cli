from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(63), primary_key=True)
    path: Mapped[str] = mapped_column(Text, unique=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(63), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    document_domain: Mapped[str] = mapped_column(Text)
    git_remote_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("workspace_id", "path"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(Text, index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    document_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    domain_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exists: Mapped[bool] = mapped_column(Boolean, default=True)
    indexed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class GovernanceIssue(Base):
    __tablename__ = "governance_issues"
    __table_args__ = (UniqueConstraint("workspace_id", "path", "code", "detail"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(Text)
    code: Mapped[str] = mapped_column(String(96), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), default="error")
    status: Mapped[str] = mapped_column(String(16), default="open")


class MaintenanceRun(Base):
    __tablename__ = "maintenance_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str] = mapped_column(String(36), unique=True)
    status: Mapped[str] = mapped_column(String(24))
    scanned_count: Mapped[int] = mapped_column(Integer, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (UniqueConstraint("workspace_id", "dedupe_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(160))
    question: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    options_json: Mapped[str] = mapped_column(Text, default="[]")
    related_documents_json: Mapped[str] = mapped_column(Text, default="[]")
    source_type: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    session_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DecisionEvent(Base):
    __tablename__ = "decision_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str | None] = mapped_column(String(160), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class RestructureBatch(Base):
    __tablename__ = "restructure_batches"
    __table_args__ = (UniqueConstraint("workspace_id", "batch_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    batch_uuid: Mapped[str] = mapped_column(String(36), unique=True)
    batch_name: Mapped[str] = mapped_column(String(128))
    scope: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="inventoried")
    config_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class RestructureItem(Base):
    __tablename__ = "restructure_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    batch_id: Mapped[int] = mapped_column(ForeignKey("restructure_batches.id"), index=True)
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
