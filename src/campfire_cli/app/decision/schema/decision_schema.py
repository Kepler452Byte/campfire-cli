from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DecisionStatus = Literal["pending", "answered", "closed", "cancelled"]


class DecisionEntry(BaseModel):
    id: str
    workspace_id: str
    dedupe_key: str
    question: str
    context: str = ""
    recommendation: str = ""
    options: list[str] = Field(default_factory=list)
    related_documents: list[str] = Field(default_factory=list)
    source_type: str
    source_id: str | None = None
    session_provider: str | None = None
    session_id: str | None = None
    status: DecisionStatus = "pending"
    answer: str | None = None
    answered_by: str | None = None
    cancellation_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    answered_at: datetime | None = None
    closed_at: datetime | None = None


class DecisionEventEntry(BaseModel):
    event_type: str
    actor: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class DecisionResult(BaseModel):
    status: str
    decision: DecisionEntry | None = None
    events: list[DecisionEventEntry] = Field(default_factory=list)
    projection_operations: list[dict[str, str]] = Field(default_factory=list)


class DecisionListResult(BaseModel):
    status: str = "ok"
    decisions: list[DecisionEntry] = Field(default_factory=list)


class DecisionSyncResult(BaseModel):
    status: str
    pending_count: int
    operations: list[dict[str, str]] = Field(default_factory=list)
