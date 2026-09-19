from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from campfire_cli.app.base.schema.operation_schema import CommandFollowUp


class InventoryItem(BaseModel):
    path: str
    sha256: str
    size: int


class RestructurePlanItem(BaseModel):
    item_id: str
    source: str
    target: str
    source_sha256: str
    action: str
    proposed_type: str | None = None
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    reason: str
    confidence: str
    approved: bool = False


class RestructurePlan(BaseModel):
    schema_version: int = 1
    batch: str
    scope: str
    config_hash: str
    items: list[RestructurePlanItem] = Field(default_factory=list)


class RestructureIntentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str | None = None
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    approved: bool = False


class RestructureIntentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    operations: list[RestructureIntentItem]


class RestructureResult(BaseModel):
    status: str
    batch: str
    item_count: int
    inventory_count: int = 0
    planned_count: int = 0
    approved_count: int = 0
    unapproved_count: int = 0
    blocked_count: int = 0
    applied_count: int = 0
    issues: list[dict[str, Any]] = Field(default_factory=list)
    follow_up: list[CommandFollowUp] = Field(default_factory=list)


class DomainRestructureResult(BaseModel):
    status: str
    domain_id: str
    name: str
    path: str
    old_path: str = ""
    path_changed: bool = False
    expected_plan: str | None = None
    operations: list[dict[str, str]] = Field(default_factory=list)
    affected_projects: list[str] = Field(default_factory=list)
    write_performed: bool = False
    issues: list[dict[str, Any]] = Field(default_factory=list)
    follow_up: list[CommandFollowUp] = Field(default_factory=list)


class DomainMergeResult(BaseModel):
    status: str
    source_domain: str
    target_domain: str
    document_count: int = 0
    asset_count: int = 0
    child_domain_count: int = 0
    reference_count: int = 0
    operations: list[dict[str, str]] = Field(default_factory=list)
    affected_projects: list[str] = Field(default_factory=list)
    write_performed: bool = False
    issues: list[dict[str, Any]] = Field(default_factory=list)
    follow_up: list[CommandFollowUp] = Field(default_factory=list)


class DomainDeleteResult(BaseModel):
    status: str
    domain_id: str
    path: str
    operations: list[dict[str, str]] = Field(default_factory=list)
    write_performed: bool = False
    issues: list[dict[str, Any]] = Field(default_factory=list)
    follow_up: list[CommandFollowUp] = Field(default_factory=list)
