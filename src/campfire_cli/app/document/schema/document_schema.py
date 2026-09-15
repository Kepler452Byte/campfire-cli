from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from campfire_cli.app.base.schema.operation_schema import CommandFollowUp


class DocumentApplyRequest(BaseModel):
    path: str
    document_type: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)
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
    target: str
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
