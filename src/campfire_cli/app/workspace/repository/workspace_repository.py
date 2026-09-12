from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete, select

from campfire_cli.app.workspace.schema.workspace_schema import (
    ProjectEntry,
    WorkspaceEntry,
    WorkspaceRegistry,
)
from campfire_cli.common.database import create_sqlite_engine, open_session, upgrade_database
from campfire_cli.common.database.models import Project, Workspace
from campfire_cli.common.filesystem import atomic_write


class SqliteWorkspaceRepository:
    """Persist the user-level Workspace and Project registry in SQLite."""

    def __init__(self, governance_root: Path) -> None:
        self._root = governance_root
        database_path = governance_root / "campfire.db"
        upgrade_database(database_path)
        self._engine = create_sqlite_engine(database_path)

    def load_registry(self) -> WorkspaceRegistry:
        with open_session(self._engine) as session:
            rows = session.scalars(select(Workspace).order_by(Workspace.id)).all()
        default = next((row.id for row in rows if row.is_default), None)
        return WorkspaceRegistry(
            default_workspace=default,
            workspaces={
                row.id: WorkspaceEntry(path=row.path, status=row.status, default=row.is_default)
                for row in rows
            },
        )

    def save_registry(self, registry: WorkspaceRegistry) -> None:
        with open_session(self._engine) as session, session.begin():
            existing = {row.id: row for row in session.scalars(select(Workspace)).all()}
            for workspace_id, entry in registry.workspaces.items():
                row = existing.pop(workspace_id, None)
                if row is None:
                    row = Workspace(id=workspace_id, path=entry.path)
                    session.add(row)
                row.path = entry.path
                row.status = entry.status
                row.is_default = workspace_id == registry.default_workspace
            for row in existing.values():
                session.delete(row)

    def list_projects(self, workspace_id: str | None = None) -> list[ProjectEntry]:
        statement = select(Project).order_by(Project.workspace_id, Project.id)
        if workspace_id is not None:
            statement = statement.where(Project.workspace_id == workspace_id)
        with open_session(self._engine) as session:
            rows = session.scalars(statement).all()
            return [self._project_entry(row) for row in rows]

    def get_project(self, project_id: str) -> ProjectEntry | None:
        with open_session(self._engine) as session:
            row = session.get(Project, project_id)
            return self._project_entry(row) if row else None

    def save_project(self, project: ProjectEntry) -> str:
        with open_session(self._engine) as session, session.begin():
            row = session.get(Project, project.id)
            operation = "updated" if row else "created"
            if row is None:
                row = Project(id=project.id, workspace_id=project.workspace_id)
                session.add(row)
            row.workspace_id = project.workspace_id
            row.name = project.name
            row.document_domain = project.document_domain
            row.git_remote_url = project.git_remote_url
            row.local_path = project.local_path
            row.default_branch = project.default_branch
            row.status = project.status
        return operation

    def replace_registry(self, registry: WorkspaceRegistry, projects: list[ProjectEntry]) -> None:
        with open_session(self._engine) as session, session.begin():
            session.execute(delete(Project))
            session.execute(delete(Workspace))
            for workspace_id, entry in registry.workspaces.items():
                session.add(
                    Workspace(
                        id=workspace_id,
                        path=entry.path,
                        status=entry.status,
                        is_default=workspace_id == registry.default_workspace,
                    )
                )
            session.flush()
            for project in projects:
                session.add(
                    Project(
                        id=project.id,
                        workspace_id=project.workspace_id,
                        name=project.name,
                        document_domain=project.document_domain,
                        git_remote_url=project.git_remote_url,
                        local_path=project.local_path,
                        default_branch=project.default_branch,
                        status=project.status,
                    )
                )

    def initialize_configs(
        self, workspace_id: str, configs: dict[str, dict]
    ) -> tuple[list[str], list[str]]:
        config_root = self._root / "workspaces" / workspace_id / "config"
        created: list[str] = []
        preserved: list[str] = []
        for name, payload in configs.items():
            target = config_root / name
            if target.exists():
                preserved.append(str(target))
                continue
            atomic_write(target, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            created.append(str(target))
        return created, preserved

    @staticmethod
    def create_scaffold(root: Path, directories: tuple[str, ...]) -> list[str]:
        for relative in directories:
            (root / relative).mkdir(parents=True, exist_ok=True)
        return list(directories)

    @staticmethod
    def _project_entry(row: Project) -> ProjectEntry:
        return ProjectEntry(
            id=row.id,
            workspace_id=row.workspace_id,
            name=row.name,
            document_domain=row.document_domain,
            git_remote_url=row.git_remote_url,
            local_path=row.local_path,
            default_branch=row.default_branch,
            status=row.status,
        )
