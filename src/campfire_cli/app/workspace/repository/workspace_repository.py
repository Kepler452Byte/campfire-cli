from __future__ import annotations

from pathlib import Path

import yaml

from campfire_cli.app.workspace.repository.manifest_repository import WorkspaceManifestRepository
from campfire_cli.app.workspace.schema.workspace_schema import (
    ProjectEntry,
    WorkspaceRegistry,
    portable_project,
    restore_project,
)
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem import atomic_write


class FilesystemWorkspaceRepository:
    """Read portable projects from their Vaults and device bindings from local.yaml."""

    def __init__(self, governance_root: Path) -> None:
        self._path = governance_root / "local.yaml"
        self._manifests = WorkspaceManifestRepository()

    def load_registry(self) -> WorkspaceRegistry:
        if not self._path.exists():
            return WorkspaceRegistry()
        try:
            return WorkspaceRegistry.model_validate(
                yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
            )
        except (ValueError, yaml.YAMLError) as exc:
            raise ConfigurationError(
                f"Invalid local configuration: {self._path}: {exc}", code="local-config-invalid"
            ) from exc

    def save_registry(self, registry: WorkspaceRegistry) -> None:
        atomic_write(
            self._path,
            yaml.safe_dump(registry.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
        )

    def list_projects(self, workspace_id: str | None = None) -> list[ProjectEntry]:
        registry = self.load_registry()
        result = []
        for identity, entry in sorted(registry.workspaces.items()):
            if workspace_id is not None and identity != workspace_id:
                continue
            manifest = self._manifests.load(Path(entry.path))
            if manifest is None:
                raise ConfigurationError(
                    f"Workspace Manifest missing: {entry.path}", code="manifest-missing"
                )
            if manifest.workspace.id != identity:
                raise ConfigurationError(
                    f"Workspace identity mismatch: {entry.path}", code="manifest-workspace-mismatch"
                )
            for portable in sorted(manifest.projects, key=lambda item: item.id):
                project = restore_project(portable, identity, None)
                bindings = entry.repository_bindings.get(project.id, {})
                for repository in project.repositories:
                    repository.local_path = bindings.get(repository.id)
                result.append(project)
        return result

    def get_project(self, project_id: str) -> ProjectEntry | None:
        matches = [item for item in self.list_projects() if item.id == project_id]
        if len(matches) > 1:
            raise ConfigurationError(
                f"Project id occurs in multiple Workspaces: {project_id}", code="project-ambiguous"
            )
        return matches[0] if matches else None

    def save_project(self, project: ProjectEntry) -> str:
        existing = self.list_projects(project.workspace_id)
        found = any(item.id == project.id for item in existing)
        projects = [project if item.id == project.id else item for item in existing]
        if not found:
            projects.append(project)
        self.replace_projects(project.workspace_id, projects)
        return "updated" if found else "created"

    def replace_projects(self, workspace_id: str, projects: list[ProjectEntry]) -> None:
        registry = self.load_registry()
        previous_registry = registry.model_copy(deep=True)
        entry = registry.workspaces[workspace_id]
        root = Path(entry.path)
        manifest = self._manifests.load(root)
        if manifest is None:
            raise ConfigurationError(f"Workspace Manifest missing: {root}", code="manifest-missing")
        portable = [portable_project(item) for item in projects]
        metadata_changed = manifest.projects != portable
        manifest.projects = portable
        for project in projects:
            bindings = {
                item.id: item.local_path for item in project.repositories if item.local_path
            }
            if bindings:
                entry.repository_bindings[project.id] = bindings
            else:
                entry.repository_bindings.pop(project.id, None)
        target = self._manifests.path(root)
        original = target.read_text(encoding="utf-8")
        try:
            if metadata_changed:
                self._manifests.save(root, manifest)
            if registry != previous_registry:
                self.save_registry(registry)
        except Exception:
            if metadata_changed:
                atomic_write(target, original)
            raise

    def replace_registry(self, registry: WorkspaceRegistry, projects: list[ProjectEntry]) -> None:
        originals = {
            self._manifests.path(Path(entry.path)): self._manifests.path(
                Path(entry.path)
            ).read_text(encoding="utf-8")
            for entry in registry.workspaces.values()
        }
        local = self._path.read_text(encoding="utf-8") if self._path.exists() else None
        try:
            self.save_registry(registry)
            for workspace_id in registry.workspaces:
                self.replace_projects(
                    workspace_id, [item for item in projects if item.workspace_id == workspace_id]
                )
        except Exception:
            for path, content in originals.items():
                atomic_write(path, content)
            if local is None:
                self._path.unlink(missing_ok=True)
            else:
                atomic_write(self._path, local)
            raise

    @staticmethod
    def create_scaffold(root: Path, directories: tuple[str, ...]) -> list[str]:
        for relative in directories:
            (root / relative).mkdir(parents=True, exist_ok=True)
        return list(directories)
