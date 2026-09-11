from __future__ import annotations

import re
from pathlib import Path

from campfire_cli.app.workspace.schema.workspace_schema import (
    WorkspaceCreateRequest,
    WorkspaceDefaultResult,
    WorkspaceEntry,
    WorkspaceListResult,
    WorkspaceResolution,
    WorkspaceResult,
)
from campfire_cli.app.workspace.service.workspace_protocol import WorkspaceRepositoryProtocol
from campfire_cli.common.database import upgrade_database
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem import vault_write_lock
from campfire_cli.config.defaults import default_configs

SCAFFOLD_DIRECTORIES = (
    "_收件箱/用户输入",
    "_收件箱/待用户确认",
    "mynote",
    "mywork",
    "治理视图",
)


class WorkspaceService:
    def __init__(self, governance_root: Path, repository: WorkspaceRepositoryProtocol) -> None:
        self._root = governance_root
        self._repository = repository

    def add(self, request: WorkspaceCreateRequest) -> WorkspaceResult:
        root = request.path.expanduser().resolve()
        if not root.is_dir():
            raise ConfigurationError(f"Workspace 不存在：{root}")
        return self._initialize(request.workspace_id, root, request.make_default)

    def create(self, request: WorkspaceCreateRequest) -> WorkspaceResult:
        root = request.path.expanduser().resolve()
        self._validate_id(request.workspace_id)
        if root.exists():
            raise ConfigurationError(f"目标路径已存在；接入现有 Workspace 请使用 workspace add：{root}")
        directories = self._repository.create_scaffold(root, SCAFFOLD_DIRECTORIES)
        result = self._initialize(request.workspace_id, root, request.make_default)
        result.created_directories = directories
        return result

    def list(self) -> WorkspaceListResult:
        registry = self._repository.load_registry()
        return WorkspaceListResult(**registry.model_dump())

    def show(self, selector: str) -> WorkspaceResolution:
        workspace_id, path = self._resolve(selector)
        return WorkspaceResolution(
            workspace_id=workspace_id,
            workspace=str(path),
            state_root=str(self._root / "workspaces" / workspace_id),
        )

    def resolve(self, selector: str | None, cwd: Path) -> WorkspaceResolution:
        workspace_id, path = self._resolve(selector, cwd)
        return WorkspaceResolution(
            workspace_id=workspace_id,
            workspace=str(path),
            state_root=str(self._root / "workspaces" / workspace_id),
        )

    def set_default(self, workspace_id: str) -> WorkspaceDefaultResult:
        with vault_write_lock(self._root):
            registry = self._repository.load_registry()
            if workspace_id not in registry.workspaces:
                raise ConfigurationError(f"Workspace 未注册：{workspace_id}")
            registry.default_workspace = workspace_id
            self._repository.save_registry(registry)
        return WorkspaceDefaultResult(default_workspace=workspace_id)

    def _initialize(self, workspace_id: str, root: Path, make_default: bool) -> WorkspaceResult:
        self._validate_id(workspace_id)
        with vault_write_lock(self._root):
            registry = self._repository.load_registry()
            existing = registry.workspaces.get(workspace_id)
            if existing and Path(existing.path).expanduser().resolve() != root:
                raise ConfigurationError(f"Workspace id 已指向其他路径：{workspace_id}")
            registry.workspaces[workspace_id] = WorkspaceEntry(path=str(root))
            if make_default or not registry.default_workspace:
                registry.default_workspace = workspace_id
            created, preserved = self._repository.initialize_configs(workspace_id, default_configs())
            self._repository.save_registry(registry)
            upgrade_database(self._root / "workspaces" / workspace_id / "db" / "campfire.db")
        return WorkspaceResult(
            status="initialized",
            workspace_id=workspace_id,
            workspace=str(root),
            state_root=str(self._root / "workspaces" / workspace_id),
            default=registry.default_workspace == workspace_id,
            created=created,
            preserved=preserved,
        )

    def _resolve(self, selector: str | None, cwd: Path | None = None) -> tuple[str, Path]:
        registry = self._repository.load_registry()
        if selector is not None:
            if selector in registry.workspaces:
                return selector, Path(registry.workspaces[selector].path).expanduser().resolve()
            candidate = Path(selector).expanduser().resolve()
            for workspace_id, entry in registry.workspaces.items():
                if Path(entry.path).expanduser().resolve() == candidate:
                    return workspace_id, candidate
            raise ConfigurationError(f"Workspace 未注册：{selector}；请先运行 campfire workspace add")
        current = (cwd or Path.cwd()).resolve()
        matches = [
            (workspace_id, Path(entry.path).expanduser().resolve())
            for workspace_id, entry in registry.workspaces.items()
            if current == Path(entry.path).expanduser().resolve()
            or Path(entry.path).expanduser().resolve() in current.parents
        ]
        if matches:
            return max(matches, key=lambda item: len(item[1].parts))
        if registry.default_workspace in registry.workspaces:
            entry = registry.workspaces[registry.default_workspace]
            return registry.default_workspace, Path(entry.path).expanduser().resolve()
        raise ConfigurationError(
            "没有可用 Workspace；请运行 campfire workspace add --id <id> --path <path> --default"
        )

    @staticmethod
    def _validate_id(workspace_id: str) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", workspace_id):
            raise ConfigurationError("id 只能使用小写字母、数字和连字符")
