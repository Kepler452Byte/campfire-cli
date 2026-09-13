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
    governance: str
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


class MaintenanceIntentItem(BaseModel):
    path: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    filename: str | None = None
    format_frontmatter: bool = True
    reason: str
    approved: bool = False


class MaintenanceIntentSpec(BaseModel):
    schema_version: int = 1
    operations: list[MaintenanceIntentItem]


class MaintenancePlanItem(BaseModel):
    source: str
    target: str
    source_sha256: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    format_frontmatter: bool = False
    reason: str
    approved: bool = False


class MaintenancePlan(BaseModel):
    schema_version: int = 1
    plan_id: str
    scope: str | None = None
    config_hash: str
    items: list[MaintenancePlanItem] = Field(default_factory=list)


class MaintenanceRunRecord(BaseModel):
    run_id: str
    status: str
    scanned_count: int
    issue_count: int
    started_at: datetime
    finished_at: datetime
