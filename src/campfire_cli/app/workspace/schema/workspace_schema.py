from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError


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


class WorkspaceCreateResult(WorkspaceResult):
    manifest: str
    resources: dict[str, Any] = Field(default_factory=dict)
    health: dict[str, Any] = Field(default_factory=dict)
    demo: dict[str, Any] | None = None


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


class ManifestRepository(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")
    git_remote_url: str | None = None
    default_branch: str | None = None
    role: str | None = None


class RepositoryEntry(ManifestRepository):
    local_path: str | None = None


class ManifestProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    document_domain_id: str
    repositories: list[ManifestRepository] = Field(default_factory=list)
    status: str = "active"

    @model_validator(mode="after")
    def unique_repository_ids(self):
        ids = [item.id for item in self.repositories]
        if len(ids) != len(set(ids)):
            raise PydanticCustomError("repository-id-duplicate", "Repository ids must be unique")
        return self


class WorkspaceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    workspace: ManifestWorkspace
    projects: list[ManifestProject] = Field(default_factory=list)


class WorkspaceSetupResult(WorkspaceResult):
    manifest: str
    manifest_operation: str
    imported_projects: list[str] = Field(default_factory=list)
    unbound_projects: list[str] = Field(default_factory=list)
    unbound_repositories: list[dict[str, Any]] = Field(default_factory=list)


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


class DeclarationFormatResult(BaseModel):
    status: str
    path: str
    reordered: list[str] = Field(default_factory=list)
    issues: list[dict[str, str]] = Field(default_factory=list)
    write_performed: bool = False


class WorkspaceConfigCheckResult(BaseModel):
    status: str
    checked: list[str] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)


class ProjectEntry(ManifestProject):
    workspace_id: str
    repositories: list[RepositoryEntry] = Field(default_factory=list)


class ProjectRegistrationRequest(BaseModel):
    repositories: list[RepositoryEntry] = Field(default_factory=list)
    project_id: str
    workspace_id: str
    name: str
    document_domain_id: str
    document_domain_path: str | None = None
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
    repository_id: str | None = None
    repository: RepositoryEntry | None = None
    project: ProjectEntry
    match_basis: list[str] = Field(default_factory=list)


class ProjectResolutionResult(BaseModel):
    status: str
    query_path: str
    git_root: str | None = None
    git_remote_url: str | None = None
    matches: list[ProjectMatch] = Field(default_factory=list)
    remote_matches: list[ProjectMatch] = Field(default_factory=list)
    hint: str | None = None


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
    schema_version: Literal[2] = 2
    default_workspace: str | None = None
    workspaces: dict[str, WorkspaceEntry] = Field(default_factory=dict)
    projects: list[ProjectEntry] = Field(default_factory=list)


class RegistryTransferResult(BaseModel):
    status: str
    path: str
    workspace_count: int
    project_count: int


def portable_project(project: ProjectEntry) -> ManifestProject:
    """Return portable metadata without device-local repository paths."""
    payload = project.model_dump(exclude={"workspace_id"})
    payload["repositories"] = [
        item.model_dump(exclude={"local_path"}) for item in project.repositories
    ]
    return ManifestProject.model_validate(payload)


def restore_project(
    portable: ManifestProject, workspace_id: str, existing: ProjectEntry | None
) -> ProjectEntry:
    """Restore portable identity while retaining local bindings by repository id."""
    bindings = {item.id: item.local_path for item in existing.repositories} if existing else {}
    payload = portable.model_dump()
    payload["repositories"] = [
        {**item.model_dump(), "local_path": bindings.get(item.id)} for item in portable.repositories
    ]
    return ProjectEntry(**payload, workspace_id=workspace_id)
