from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InventoryItem(BaseModel):
    path: str
    sha256: str
    size: int


class MigrationPlanItem(BaseModel):
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


class MigrationPlan(BaseModel):
    schema_version: int = 1
    batch: str
    scope: str
    config_hash: str
    items: list[MigrationPlanItem] = Field(default_factory=list)


class MigrationIntentItem(BaseModel):
    source: str
    target: str | None = None
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    reason: str
    approved: bool = False


class MigrationIntentSpec(BaseModel):
    schema_version: int = 1
    operations: list[MigrationIntentItem]


class MigrationResult(BaseModel):
    status: str
    batch: str
    item_count: int
    applied_count: int = 0
    issues: list[dict[str, Any]] = Field(default_factory=list)
