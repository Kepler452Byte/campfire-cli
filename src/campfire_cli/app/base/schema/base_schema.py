from __future__ import annotations

from pydantic import BaseModel, Field


class BaseInfo(BaseModel):
    name: str
    path: str
    status: str
    views: list[str] = Field(default_factory=list)


class BaseResult(BaseModel):
    status: str
    bases: list[BaseInfo] = Field(default_factory=list)
    operations: list[dict[str, str]] = Field(default_factory=list)
    issues: list[dict[str, str]] = Field(default_factory=list)
    content: str | None = None
