from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Issue(BaseModel):
    code: str
    path: str
    detail: str = ""
    severity: str = "error"
    message: str = ""
    suggestion: str = ""
    field: str | None = None
    actual: Any = None
    allowed: list[Any] = Field(default_factory=list)


class DocumentState(BaseModel):
    path: str
    content_hash: str
    document_type: str | None = None
    domain_id: str | None = None
    status: str | None = None


class MaintenanceResult(BaseModel):
    status: str
    document_count: int
    issue_count: int
    total_issue_count: int = 0
    issues: list[Issue] = Field(default_factory=list)
    changed_document_count: int = 0
    generated_file_count: int = 0
    write_performed: bool = False
    blocked_phase: str | None = None
    blocked_scope: str | None = None
    issue_counts: dict[str, int] = Field(default_factory=dict)
    operations: list[dict[str, Any]] = Field(default_factory=list)


class MaintenanceRunRecord(BaseModel):
    run_id: str
    status: str
    scanned_count: int
    issue_count: int
    started_at: datetime
    finished_at: datetime
