from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AdoptionInventoryItem(BaseModel):
    path: str
    sha256: str
    size: int


class AdoptionPlan(BaseModel):
    batch: str
    target_path: str
    domain_id: str
    name: str
    space_id: str
    domain_type: str
    governance: str
    parent_domain: str | None = None
    project_id: str | None = None


class AdoptionBatchState(BaseModel):
    batch: str
    source_path: str
    source_kind: str
    staging_path: str | None = None
    status: str
    inventory: list[AdoptionInventoryItem]
    plan: AdoptionPlan | None = None


class AdoptionResult(BaseModel):
    status: str
    batch: str
    source: str
    source_kind: str
    staging_path: str | None = None
    target_path: str | None = None
    item_count: int = 0
    copied_count: int = 0
    operations: list[dict[str, str]] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    write_performed: bool = False
