from __future__ import annotations

from pathlib import Path
from typing import Protocol

from campfire_cli.app.workspace.schema.workspace_schema import ProjectEntry, WorkspaceRegistry


class WorkspaceRepositoryProtocol(Protocol):
    def load_registry(self) -> WorkspaceRegistry: ...

    def save_registry(self, registry: WorkspaceRegistry) -> None: ...

    def list_projects(self, workspace_id: str | None = None) -> list[ProjectEntry]: ...

    def get_project(self, project_id: str) -> ProjectEntry | None: ...

    def save_project(self, project: ProjectEntry) -> str: ...

    def replace_registry(
        self, registry: WorkspaceRegistry, projects: list[ProjectEntry]
    ) -> None: ...

    def initialize_configs(
        self, workspace_id: str, configs: dict[str, dict]
    ) -> tuple[list[str], list[str]]: ...

    def create_scaffold(self, root: Path, directories: tuple[str, ...]) -> list[str]: ...
