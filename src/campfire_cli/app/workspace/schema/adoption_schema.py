from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from campfire_cli.app.base.schema.operation_schema import CommandFollowUp


class AdoptionInventoryItem(BaseModel):
    path: str
    sha256: str
    size: int


class AdoptionResult(BaseModel):
    status: str
    source: str
    source_kind: str
    target_path: str
    item_count: int = 0
    operations: list[dict[str, str]] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    follow_up: list[CommandFollowUp] = Field(default_factory=list)
    write_performed: bool = False
