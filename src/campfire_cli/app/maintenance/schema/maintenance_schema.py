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


class SpaceState(BaseModel):
    space_id: str
    name: str
    path: str
    space_type: str
    status: str
    source_hash: str


class DomainState(BaseModel):
    domain_id: str
    space_id: str
    parent_domain_id: str | None = None
    project_id: str | None = None
    name: str
    path: str
    domain_type: str

    moc: str
    status: str
    source_hash: str


class MaintenanceResult(BaseModel):
    status: str
    document_count: int
    issue_count: int
    total_issue_count: int = 0
    issues: list[Issue] = Field(default_factory=list)
    changed_document_count: int = 0
    indexed_document_count: int = Field(
        default=0, description="Current Workspace index total, not this run's count"
    )
    index_available: bool | None = None
    index_generation: int | None = None
    index_processed_document_count: int = 0
    index_content_changed_document_count: int = 0
    index_full_rebuild: bool = False
    write_performed_scope: str = "markdown-files"
    checked_relations: str = "related_docs"
    body_links_checked: bool = False
    generated_file_count: int = 0
    write_performed: bool = False
    blocked_phase: str | None = None
    blocked_scope: str | None = None
    issue_counts: dict[str, int] = Field(default_factory=dict)
    operations: list[dict[str, Any]] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    scope: str | None = None
    workspace_status: str | None = None
    space_count: int = 0
    domain_count: int = 0


class MaintenanceRunRecord(BaseModel):
    run_id: str
    status: str
    scanned_count: int
    issue_count: int
    started_at: datetime
    finished_at: datetime
