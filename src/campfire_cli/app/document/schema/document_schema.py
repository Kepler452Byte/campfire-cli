from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from campfire_cli.app.base.schema.operation_schema import CommandFollowUp


class DocumentApplyRequest(BaseModel):
    path: str
    document_type: str | None = None
    values: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    append_section: str | None = None
    replace_body: bool = False
    expected_hash: str | None = None
    confirm: bool = False


class DocumentApplyResult(BaseModel):
    status: Literal["planned", "needs-input", "blocked", "applied"]
    workspace_id: str
    action: Literal["create", "update", "retype"]
    path: str
    requested_path: str
    target: str
    normalization: list[dict[str, Any]] = Field(default_factory=list)
    profile: str
    expected_hash: str
    write_performed: bool = False
    updated_references: list[str] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    follow_up: list[CommandFollowUp] = Field(default_factory=list)


class DocumentMoveResult(BaseModel):
    status: Literal["ready", "needs-input", "blocked", "moved"]
    workspace_id: str
    source: str
    target: str
    expected_hash: str
    source_domain: str | None = None
    target_domain: str | None = None
    profile: str | None = None
    write_performed: bool = False
    updated_references: list[str] = Field(default_factory=list)
    frontmatter_changes: dict[str, Any] = Field(default_factory=dict)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    follow_up: list[CommandFollowUp] = Field(default_factory=list)


class DocumentIndexRecord(BaseModel):
    path: str
    content_hash: str
    name: str | None = None
    document_type: str | None = None
    domain_id: str | None = None
    project_id: str | None = None
    status: str | None = None
    lifecycle: str | None = None
    priority: str | None = None
    assignee: list[str] = Field(default_factory=list)
    due: str | None = None
    source_updated: str | None = None
    source_size: int
    source_mtime_ns: int
    queryable: bool = True
    indexed_at: datetime | None = None


class DocumentEdgeRecord(BaseModel):
    source_path: str
    target_path: str | None = None
    raw_target: str
    relation_type: Literal[
        "declared-related",
        "declared-superseded-by",
        "wikilink",
        "markdown-link",
        "embed",
    ]
    resolution: Literal["resolved", "missing", "ambiguous"]
    candidates: list[str] = Field(default_factory=list)
    line: int | None = None


class DocumentIndexMetadata(BaseModel):
    schema_version: int
    parser_version: str
    config_hash: str
    topology_hash: str
    generation: int
    status: Literal["ready", "dirty"] = "ready"
    rebuilt_at: datetime | None = None
    indexed_at: datetime | None = None


class DocumentIndexResult(BaseModel):
    status: Literal["ok"] = "ok"
    workspace_id: str
    generation: int
    document_count: int
    edge_count: int
    changed_document_count: int
    full_rebuild: bool


class DocumentListItem(BaseModel):
    path: str
    name: str | None = None
    type: str | None = None
    project: str | None = None
    domain: str | None = None
    status: str | None = None
    lifecycle: str | None = None
    priority: str | None = None
    assignee: list[str] = Field(default_factory=list)
    due: str | None = None
    updated: str | None = None


class DocumentListResult(BaseModel):
    status: Literal["ok"] = "ok"
    workspace_id: str
    index_generation: int
    filters: dict[str, str] = Field(default_factory=dict)
    count: int
    total: int
    returned: int
    truncated: bool
    items: list[DocumentListItem] = Field(default_factory=list)
