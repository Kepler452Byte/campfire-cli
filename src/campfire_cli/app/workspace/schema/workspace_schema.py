from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class WorkspaceEntry(BaseModel):
    path: str


class WorkspaceRegistry(BaseModel):
    schema_version: int = 1
    default_workspace: str | None = None
    workspaces: dict[str, WorkspaceEntry] = Field(default_factory=dict)


class WorkspaceResult(BaseModel):
    status: str
    workspace_id: str
    workspace: str
    state_root: str
    default: bool = False
    created: list[str] = Field(default_factory=list)
    preserved: list[str] = Field(default_factory=list)
    created_directories: list[str] = Field(default_factory=list)


class WorkspaceResolution(BaseModel):
    status: str = "ok"
    workspace_id: str
    workspace: str
    state_root: str | None = None


class WorkspaceListResult(BaseModel):
    status: str = "ok"
    schema_version: int = 1
    default_workspace: str | None = None
    workspaces: dict[str, WorkspaceEntry] = Field(default_factory=dict)


class WorkspaceDefaultResult(BaseModel):
    status: str = "updated"
    default_workspace: str


class WorkspaceCreateRequest(BaseModel):
    workspace_id: str
    path: Path
    make_default: bool = False
