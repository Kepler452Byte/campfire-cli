from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class WorkspaceEntry(BaseModel):
    path: str
    status: str = "active"
    default: bool = False


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


class ManifestWorkspace(BaseModel):
    id: str
    name: str
    governance_version: int = 1


class ManifestProject(BaseModel):
    id: str
    name: str
    document_domain: str
    git_remote_url: str | None = None
    default_branch: str | None = None
    status: str = "active"


class WorkspaceManifest(BaseModel):
    schema_version: int = 1
    workspace: ManifestWorkspace
    projects: list[ManifestProject] = Field(default_factory=list)


class WorkspaceSetupResult(WorkspaceResult):
    manifest: str
    manifest_operation: str
    imported_projects: list[str] = Field(default_factory=list)
    unbound_projects: list[str] = Field(default_factory=list)


class Space(BaseModel):
    id: str
    name: str
    path: str
    type: str
    status: str = "active"


class SpaceListResult(BaseModel):
    status: str = "ok"
    spaces: list[Space] = Field(default_factory=list)


class SpaceCheckResult(BaseModel):
    status: str
    spaces: list[Space] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)


class SpaceCreateResult(BaseModel):
    status: str
    space: Space
    operations: list[dict[str, str]] = Field(default_factory=list)
    write_performed: bool = False


class Domain(BaseModel):
    id: str
    name: str
    path: Path
    space_id: str
    type: str
    governance: str
    moc: str
    parent_domain: str | None = None
    project_id: str | None = None
    status: str = "active"


class DomainListResult(BaseModel):
    status: str = "ok"
    domains: list[Domain] = Field(default_factory=list)


class DomainCheckResult(BaseModel):
    status: str
    domains: list[Domain] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)


class DomainCreateResult(BaseModel):
    status: str
    domain: Domain
    operations: list[dict[str, str]] = Field(default_factory=list)
    write_performed: bool = False


class WorkspaceConfigCheckResult(BaseModel):
    status: str
    checked: list[str] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    id: str
    workspace_id: str
    name: str
    document_domain: str
    git_remote_url: str | None = None
    local_path: str | None = None
    default_branch: str | None = None
    status: str = "active"


class ProjectUpsertRequest(BaseModel):
    project_id: str
    workspace_id: str
    name: str
    document_domain: str
    git_remote_url: str | None = None
    local_path: Path | None = None
    default_branch: str | None = None
    status: str = "active"


class ProjectResult(ProjectEntry):
    operation: str = "saved"


class ProjectBindResult(BaseModel):
    status: str = "bound"
    project: ProjectEntry


class ProjectListResult(BaseModel):
    status: str = "ok"
    projects: list[ProjectEntry] = Field(default_factory=list)


class ProjectMatch(BaseModel):
    project: ProjectEntry
    match_basis: list[str] = Field(default_factory=list)


class ProjectResolutionResult(BaseModel):
    status: str
    query_path: str
    git_root: str | None = None
    git_remote_url: str | None = None
    matches: list[ProjectMatch] = Field(default_factory=list)


class ProjectCheckResult(BaseModel):
    status: str
    project: ProjectEntry
    observed: dict[str, Any] = Field(default_factory=dict)
    issues: list[dict[str, Any]] = Field(default_factory=list)


class ProjectCreateResult(BaseModel):
    status: str
    project: ProjectEntry
    document_domain_path: str
    operations: list[dict[str, str]] = Field(default_factory=list)
    write_performed: bool = False


class RegistryExport(BaseModel):
    schema_version: int = 1
    default_workspace: str | None = None
    workspaces: dict[str, WorkspaceEntry] = Field(default_factory=dict)
    projects: list[ProjectEntry] = Field(default_factory=list)


class RegistryTransferResult(BaseModel):
    status: str
    path: str
    workspace_count: int
    project_count: int
