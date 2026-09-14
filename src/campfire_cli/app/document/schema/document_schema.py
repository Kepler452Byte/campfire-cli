from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DocumentApplyRequest(BaseModel):
    path: str
    document_type: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    body: str | None = None
    append_section: str | None = None
    replace_body: bool = False
    expected_hash: str | None = None
    confirm: bool = False


class DocumentFollowUp(BaseModel):
    command: Literal["maintenance sync", "maintenance check"]
    workspace: str
    scope: str


class DocumentApplyResult(BaseModel):
    status: Literal["planned", "needs-input", "blocked", "applied"]
    workspace_id: str
    action: Literal["create", "update"]
    path: str
    profile: str
    expected_hash: str
    write_performed: bool = False
    issues: list[dict[str, Any]] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    follow_up: list[DocumentFollowUp] = Field(default_factory=list)


class DocumentMoveResult(BaseModel):
    status: Literal["ready", "blocked", "moved"]
    workspace_id: str
    source: str
    target: str
    expected_hash: str
    write_performed: bool = False
    updated_references: list[str] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    follow_up: list[DocumentFollowUp] = Field(default_factory=list)
