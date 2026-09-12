from __future__ import annotations

import json
import re
from pathlib import Path

from campfire_cli.app.workspace.schema.workspace_schema import (
    RegistryExport,
    RegistryTransferResult,
    WorkspaceCreateRequest,
    WorkspaceDefaultResult,
    WorkspaceEntry,
    WorkspaceListResult,
    WorkspaceRegistry,
    WorkspaceResolution,
    WorkspaceResult,
)
from campfire_cli.app.workspace.service.workspace_protocol import WorkspaceRepositoryProtocol
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem import atomic_write, workspace_write_lock
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
            raise ConfigurationError(
                f"目标路径已存在；接入现有 Workspace 请使用 workspace add：{root}"
            )
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
        with workspace_write_lock(self._root):
            registry = self._repository.load_registry()
            if workspace_id not in registry.workspaces:
                raise ConfigurationError(f"Workspace 未注册：{workspace_id}")
            registry.default_workspace = workspace_id
            self._repository.save_registry(registry)
        return WorkspaceDefaultResult(default_workspace=workspace_id)

    def export_registry(self, target: Path) -> RegistryTransferResult:
        registry = self._repository.load_registry()
        projects = self._repository.list_projects()
        payload = RegistryExport(
            default_workspace=registry.default_workspace,
            workspaces=registry.workspaces,
            projects=projects,
        )
        destination = target.expanduser().resolve()
        atomic_write(
            destination,
            json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        )
        return RegistryTransferResult(
            status="exported",
            path=str(destination),
            workspace_count=len(registry.workspaces),
            project_count=len(projects),
        )

    def import_registry(self, source: Path, confirm: bool = False) -> RegistryTransferResult:
        source = source.expanduser().resolve()
        if not source.is_file():
            raise ConfigurationError(f"导入文件不存在：{source}")
        payload = RegistryExport.model_validate_json(source.read_text(encoding="utf-8"))
        self._validate_import(payload)
        if confirm:
            with workspace_write_lock(self._root):
                self._repository.replace_registry(
                    WorkspaceRegistry(
                        schema_version=payload.schema_version,
                        default_workspace=payload.default_workspace,
                        workspaces=payload.workspaces,
                    ),
                    payload.projects,
                )
        return RegistryTransferResult(
            status="imported" if confirm else "planned",
            path=str(source),
            workspace_count=len(payload.workspaces),
            project_count=len(payload.projects),
        )

    def _initialize(self, workspace_id: str, root: Path, make_default: bool) -> WorkspaceResult:
        self._validate_id(workspace_id)
        with workspace_write_lock(self._root):
            registry = self._repository.load_registry()
            existing = registry.workspaces.get(workspace_id)
            if existing and Path(existing.path).expanduser().resolve() != root:
                raise ConfigurationError(f"Workspace id 已指向其他路径：{workspace_id}")
            duplicate = next(
                (
                    other_id
                    for other_id, entry in registry.workspaces.items()
                    if other_id != workspace_id and Path(entry.path).expanduser().resolve() == root
                ),
                None,
            )
            if duplicate:
                raise ConfigurationError(f"Workspace 路径已由其他 id 注册：{duplicate}")
            registry.workspaces[workspace_id] = WorkspaceEntry(path=str(root))
            if make_default or not registry.default_workspace:
                registry.default_workspace = workspace_id
            created, preserved = self._repository.initialize_configs(
                workspace_id, default_configs()
            )
            self._repository.save_registry(registry)
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
            raise ConfigurationError(
                f"Workspace 未注册：{selector}；请先运行 campfire workspace add"
            )
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

    @classmethod
    def _validate_import(cls, payload: RegistryExport) -> None:
        if payload.default_workspace and payload.default_workspace not in payload.workspaces:
            raise ConfigurationError("default_workspace 未出现在 workspaces 中")
        for workspace_id, entry in payload.workspaces.items():
            cls._validate_id(workspace_id)
            if not Path(entry.path).expanduser().is_absolute():
                raise ConfigurationError(f"Workspace path 必须是绝对路径：{workspace_id}")
        project_ids: set[str] = set()
        for project in payload.projects:
            if project.id in project_ids:
                raise ConfigurationError(f"Project id 重复：{project.id}")
            project_ids.add(project.id)
            if project.workspace_id not in payload.workspaces:
                raise ConfigurationError(
                    f"Project 引用了未注册 Workspace：{project.id}/{project.workspace_id}"
                )

    @staticmethod
    def _validate_id(workspace_id: str) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", workspace_id):
            raise ConfigurationError("id 只能使用小写字母、数字和连字符")
