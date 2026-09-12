from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath

from campfire_cli.app.workspace.schema.workspace_schema import (
    ProjectEntry,
    ProjectListResult,
    ProjectResult,
    ProjectUpsertRequest,
)
from campfire_cli.app.workspace.service.workspace_protocol import WorkspaceRepositoryProtocol
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem import workspace_write_lock

PROJECT_STATUSES = {"active", "paused", "archived"}


class ProjectService:
    def __init__(self, governance_root: Path, repository: WorkspaceRepositoryProtocol) -> None:
        self._root = governance_root
        self._repository = repository

    def add(self, request: ProjectUpsertRequest) -> ProjectResult:
        if self._repository.get_project(request.project_id):
            raise ConfigurationError(
                f"Project 已存在：{request.project_id}；请使用 campfire project update"
            )
        return self._save(request)

    def update(self, request: ProjectUpsertRequest) -> ProjectResult:
        if not self._repository.get_project(request.project_id):
            raise ConfigurationError(
                f"Project 未注册：{request.project_id}；请使用 campfire project add"
            )
        return self._save(request)

    def list(self, workspace_id: str | None = None) -> ProjectListResult:
        if workspace_id and workspace_id not in self._repository.load_registry().workspaces:
            raise ConfigurationError(f"Workspace 未注册：{workspace_id}")
        return ProjectListResult(projects=self._repository.list_projects(workspace_id))

    def show(self, project_id: str) -> ProjectResult:
        project = self._repository.get_project(project_id)
        if not project:
            raise ConfigurationError(f"Project 未注册：{project_id}")
        return ProjectResult(**project.model_dump(), operation="none")

    def _save(self, request: ProjectUpsertRequest) -> ProjectResult:
        self._validate_id(request.project_id)
        registry = self._repository.load_registry()
        workspace = registry.workspaces.get(request.workspace_id)
        if not workspace:
            raise ConfigurationError(f"Workspace 未注册：{request.workspace_id}")
        domain = self._validate_domain(request.document_domain)
        domain_path = Path(workspace.path) / domain
        if not domain_path.is_dir():
            raise ConfigurationError(f"项目文档领域不存在：{domain_path}")
        local_path = request.local_path.expanduser().resolve() if request.local_path else None
        if local_path and not local_path.is_dir():
            raise ConfigurationError(f"项目本地路径不存在：{local_path}")
        remote = request.git_remote_url or self._git_value(
            local_path, "remote", "get-url", "origin"
        )
        branch = request.default_branch or self._detect_default_branch(local_path)
        if request.status not in PROJECT_STATUSES:
            raise ConfigurationError(
                f"Project status 必须是：{', '.join(sorted(PROJECT_STATUSES))}"
            )
        project = ProjectEntry(
            id=request.project_id,
            workspace_id=request.workspace_id,
            name=request.name.strip(),
            document_domain=domain,
            git_remote_url=remote,
            local_path=str(local_path) if local_path else None,
            default_branch=branch,
            status=request.status,
        )
        if not project.name:
            raise ConfigurationError("Project name 不能为空")
        with workspace_write_lock(self._root):
            operation = self._repository.save_project(project)
        return ProjectResult(**project.model_dump(), operation=operation)

    @staticmethod
    def _validate_id(project_id: str) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", project_id):
            raise ConfigurationError("Project id 只能使用小写字母、数字和连字符")

    @staticmethod
    def _validate_domain(value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or not value.strip():
            raise ConfigurationError("document-domain 必须是 Workspace 内的相对路径")
        return path.as_posix()

    @staticmethod
    def _git_value(local_path: Path | None, *arguments: str) -> str | None:
        if not local_path or not (local_path / ".git").exists():
            return None
        result = subprocess.run(
            ["git", "-C", str(local_path), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None if result.returncode == 0 else None

    @classmethod
    def _detect_default_branch(cls, local_path: Path | None) -> str | None:
        reference = cls._git_value(local_path, "symbolic-ref", "refs/remotes/origin/HEAD")
        if reference:
            return reference.rsplit("/", 1)[-1]
        return cls._git_value(local_path, "branch", "--show-current")
