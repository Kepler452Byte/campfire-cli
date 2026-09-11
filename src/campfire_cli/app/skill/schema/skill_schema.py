from __future__ import annotations

from pydantic import BaseModel, Field


class SkillInfo(BaseModel):
    name: str
    description: str = ""
    path: str
    status: str = "unknown"


class SkillResult(BaseModel):
    status: str
    skills: list[SkillInfo] = Field(default_factory=list)
    operations: list[dict[str, str]] = Field(default_factory=list)
    issues: list[dict[str, str]] = Field(default_factory=list)
    content: str | None = None
