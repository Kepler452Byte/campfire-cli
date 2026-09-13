from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
    source: str
    target: str | None = None
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    reason: str
    approved: bool = False


class RestructureIntentSpec(BaseModel):
    schema_version: int = 1
    operations: list[RestructureIntentItem]


class RestructureResult(BaseModel):
    status: str
    batch: str
    item_count: int
    applied_count: int = 0
    issues: list[dict[str, Any]] = Field(default_factory=list)


class DomainRestructureResult(BaseModel):
    status: str
    domain_id: str
    name: str
    path: str
    operations: list[dict[str, str]] = Field(default_factory=list)
    affected_projects: list[str] = Field(default_factory=list)
    write_performed: bool = False
    issues: list[dict[str, Any]] = Field(default_factory=list)
