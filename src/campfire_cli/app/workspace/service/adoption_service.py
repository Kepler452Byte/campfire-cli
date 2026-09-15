from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from campfire_cli.app.base.schema.operation_schema import maintenance_sync_follow_up
from campfire_cli.app.workspace.repository.manifest_repository import (
    WorkspaceManifestRepository,
)
from campfire_cli.app.workspace.schema.adoption_schema import (
    AdoptionInventoryItem,
    AdoptionResult,
)
from campfire_cli.app.workspace.schema.workspace_schema import Domain, ManifestProject
from campfire_cli.app.workspace.service.structure_service import (
    DOMAIN_MARKER,
    ID_RE,
    DomainService,
    reserved_directories,
)
from campfire_cli.app.workspace.service.workspace_protocol import WorkspaceRepositoryProtocol
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem import (
    FileChangeExecutor,
    FileChangeSet,
    FileWrite,
    PathMove,
    safe_path,
)
from campfire_cli.common.hashing import file_sha256
from campfire_cli.config.settings import WorkspaceSettings

IGNORED_NAMES = {".git", ".obsidian", ".DS_Store", "__pycache__"}


class AdoptionService:
    """Preview or atomically adopt one existing folder as a Domain."""

    def __init__(
        self,
        settings: WorkspaceSettings,
        workspace_repository: WorkspaceRepositoryProtocol,
        manifest_repository: WorkspaceManifestRepository | None = None,
    ) -> None:
        self._settings = settings
        self._workspaces = workspace_repository
        self._manifests = manifest_repository or WorkspaceManifestRepository()
        self._domains = DomainService(settings.vault_root, settings.state_root)
        self._executor = FileChangeExecutor(settings.vault_root, settings.state_root)

    def adopt(
        self,
        source: Path,
        *,
        target_path: str | None,
        domain_id: str,
        name: str,
        domain_type: str,
        governance: str | None = None,
        project_id: str | None = None,
        confirm: bool = False,
    ) -> AdoptionResult:
        source = source.expanduser().resolve()
        if not source.is_dir():
            raise ConfigurationError(f"待接管目录不存在：{source}")
        if source == self._settings.vault_root:
            raise ConfigurationError("不能把整个 Workspace 接管为一个 Domain")
        source_kind = "internal" if self._settings.vault_root in source.parents else "external"
        if target_path is None:
            if source_kind != "internal":
                raise ConfigurationError("外部来源必须提供 --target-path")
            target_path = source.relative_to(self._settings.vault_root).as_posix()
        inventory, issues = self._scan(source)
        target, space_id = self._validate_target(target_path)
        domain = self._domain(
            target,
            domain_id=domain_id,
            name=name,
            space_id=space_id,
            domain_type=domain_type,
            governance=governance,
            project_id=project_id,
        )
        follow_up_scopes = [target_path]
        if domain.parent_domain:
            follow_up_scopes.append(self._domains.show(domain.parent_domain).path)
        if target != source and target.exists():
            issues.append({"code": "target-exists", "path": target_path})
        if (source / DOMAIN_MARKER).exists():
            issues.append({"code": "adoption-declaration-exists", "path": str(source)})
        moc = target / f"{domain.moc}.md"
        if target == source and moc.exists():
            issues.append({"code": "adoption-declaration-exists", "path": target_path})
        operations = self._operations(source, source_kind, target, target_path, domain, inventory)
        if issues or not confirm:
            return self._result(
                source,
                source_kind,
                target_path,
                inventory,
                operations,
                "blocked" if issues else "planned",
                issues,
                follow_up_scopes=follow_up_scopes,
            )

        staging: Path | None = None
        active_source = source
        if source_kind == "external":
            staging = self._stage_external(source, inventory)
            active_source = staging
            issues = self._verify_files(source, inventory)
            issues.extend(self._verify_files(staging, inventory))
            if issues:
                shutil.rmtree(staging, ignore_errors=True)
                return self._result(
                    source,
                    source_kind,
                    target_path,
                    inventory,
                    operations,
                    "blocked",
                    issues,
                    follow_up_scopes=follow_up_scopes,
                )

        original_project = None
        updated_project = None
        writes = [
            FileWrite(target / DOMAIN_MARKER, DomainService.render_marker(domain)),
            FileWrite(target / f"{domain.moc}.md", DomainService.render_moc(domain)),
        ]
        expected = {active_source / item.path: item.sha256 for item in inventory}
        expected[target / DOMAIN_MARKER] = None
        expected[target / f"{domain.moc}.md"] = None
        if project_id:
            original_project = self._workspaces.get_project(project_id)
            if original_project:
                updated_project = original_project.model_copy(
                    update={"document_domain": target_path}
                )
                manifest_path, manifest_content = self._manifest_update(updated_project)
                writes.append(FileWrite(manifest_path, manifest_content))
                expected[manifest_path] = file_sha256(manifest_path)
        moves = (PathMove(active_source, target),) if active_source != target else ()
        try:
            with self._executor.transaction(
                FileChangeSet(
                    writes=tuple(writes),
                    moves=moves,
                    label="workspace domain adopt",
                    expected=expected,
                )
            ):
                if updated_project:
                    self._workspaces.save_project(updated_project)
                if self._verify_files(target, inventory):
                    raise ConfigurationError("接管后文件验证失败")
        except Exception:
            if original_project:
                self._workspaces.save_project(original_project)
            raise
        finally:
            if staging and staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
        return self._result(
            source,
            source_kind,
            target_path,
            inventory,
            operations,
            "adopted",
            [],
            write_performed=True,
            follow_up_scopes=follow_up_scopes,
        )

    def _domain(
        self,
        target: Path,
        *,
        domain_id: str,
        name: str,
        space_id: str,
        domain_type: str,
        governance: str | None,
        project_id: str | None,
    ) -> Domain:
        if not ID_RE.fullmatch(domain_id):
            raise ConfigurationError("Domain id 只能使用小写字母、数字和连字符")
        if any(item.id == domain_id or item.path == target for item in self._domains.discover()[0]):
            raise ConfigurationError("Domain id 或已声明路径存在")
        existing = self._domains.discover()[0]
        parents = [item for item in existing if item.path in target.parents]
        parent = max(parents, key=lambda item: len(item.path.parts)) if parents else None
        if parent:
            if governance and parent.governance != governance:
                raise ConfigurationError("子 Domain 必须继承父 Domain governance")
            if project_id and parent.project_id and project_id != parent.project_id:
                raise ConfigurationError("显式 Project 与父 Domain 继承的 Project 冲突")
            governance = parent.governance
            project_id = project_id or parent.project_id
        elif not governance:
            raise ConfigurationError("根 Domain 必须提供 governance")
        if governance == "project-docs" and not project_id:
            raise ConfigurationError("project-docs Domain 必须绑定或继承 Project id")
        if project_id and self._workspaces.get_project(project_id) is None:
            raise ConfigurationError(f"Project 未注册：{project_id}")
        if not name.strip():
            raise ConfigurationError("Domain name 不能为空")
        return Domain(
            id=domain_id,
            name=name.strip(),
            path=target,
            space_id=space_id,
            type=domain_type,
            governance=governance,
            moc=f"_总览/MOC-{name.strip()}总览",
            parent_domain=parent.id if parent else None,
            project_id=project_id,
        )

    def _scan(self, root: Path) -> tuple[list[AdoptionInventoryItem], list[dict[str, str]]]:
        items: list[AdoptionInventoryItem] = []
        issues: list[dict[str, str]] = []
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if any(part in IGNORED_NAMES or part.startswith(".") for part in relative.parts):
                continue
            if path.is_symlink():
                issues.append({"code": "adoption-symlink", "path": relative.as_posix()})
            elif path.is_file():
                items.append(
                    AdoptionInventoryItem(
                        path=relative.as_posix(),
                        sha256=file_sha256(path),
                        size=path.stat().st_size,
                    )
                )
        return items, issues

    def _stage_external(self, source: Path, inventory: list[AdoptionInventoryItem]) -> Path:
        staging_root = self._settings.vault_root / "_收件箱" / "待接管"
        staging_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".adopt-", dir=staging_root))
        try:
            for item in inventory:
                target = staging / item.path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / item.path, target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return staging

    def _validate_target(self, value: str) -> tuple[Path, str]:
        target = safe_path(self._settings.vault_root, value)
        spaces = self._domains.spaces.discover()[0]
        owners = [
            space for space in spaces if (self._settings.vault_root / space.path) in target.parents
        ]
        if len(owners) != 1:
            raise ConfigurationError("目标路径必须唯一位于一个已声明 Space 下")
        space = owners[0]
        space_root = self._settings.vault_root / space.path
        if target == space_root or space_root not in target.parents:
            raise ConfigurationError("目标路径必须位于指定 Space 下")
        if any(
            part in reserved_directories() or part.startswith(".")
            for part in target.relative_to(space_root).parts
        ):
            raise ConfigurationError("目标路径不能使用保留目录")
        return target, space.id

    @staticmethod
    def _verify_files(root: Path, inventory: list[AdoptionInventoryItem]) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        for item in inventory:
            path = root / item.path
            if not path.is_file():
                issues.append({"code": "adoption-file-missing", "path": item.path})
            elif file_sha256(path) != item.sha256:
                issues.append({"code": "source-hash-changed", "path": item.path})
        return issues

    def _manifest_update(self, updated_project) -> tuple[Path, str]:
        manifest = self._manifests.load(self._settings.vault_root)
        if manifest is None:
            raise ConfigurationError("Workspace 缺少 .campfire.yaml")
        projects = [
            updated_project if project.id == updated_project.id else project
            for project in self._workspaces.list_projects(self._settings.workspace_id)
        ]
        manifest.projects = [
            ManifestProject.model_validate(
                project.model_dump(exclude={"workspace_id", "local_path"})
            )
            for project in projects
        ]
        return self._manifests.path(self._settings.vault_root), self._manifests.render(manifest)

    @staticmethod
    def _operations(
        source: Path,
        source_kind: str,
        target: Path,
        target_path: str,
        domain: Domain,
        inventory: list[AdoptionInventoryItem],
    ) -> list[dict[str, str]]:
        if source_kind == "external":
            action = "copy-file"
        elif source == target:
            action = "preserve-file"
        else:
            action = "move-file"
        operations = [
            {
                "action": action,
                "source": str(source / item.path),
                "path": f"{target_path}/{item.path}",
            }
            for item in inventory
        ]
        operations.extend(
            [
                {"action": "create-domain-marker", "path": f"{target_path}/{DOMAIN_MARKER}"},
                {"action": "create-moc", "path": f"{target_path}/{domain.moc}.md"},
            ]
        )
        return operations

    def _result(
        self,
        source: Path,
        source_kind: str,
        target_path: str,
        inventory: list[AdoptionInventoryItem],
        operations: list[dict[str, str]],
        status: str,
        issues: list[dict[str, str]],
        *,
        write_performed: bool = False,
        follow_up_scopes: list[str] | None = None,
    ) -> AdoptionResult:
        return AdoptionResult(
            status=status,
            source=str(source),
            source_kind=source_kind,
            target_path=target_path,
            item_count=len(inventory),
            operations=operations,
            issues=issues,
            follow_up=(
                maintenance_sync_follow_up(
                    self._settings.workspace_id, follow_up_scopes or [target_path]
                )
                if write_performed and not issues
                else []
            ),
            write_performed=write_performed,
        )
