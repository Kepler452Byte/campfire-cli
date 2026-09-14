from __future__ import annotations

import shutil
from pathlib import Path

from campfire_cli.app.base.schema.operation_schema import maintenance_follow_up
from campfire_cli.app.workspace.repository.manifest_repository import (
    WorkspaceManifestRepository,
)
from campfire_cli.app.workspace.schema.adoption_schema import (
    AdoptionBatchState,
    AdoptionInventoryItem,
    AdoptionPlan,
    AdoptionResult,
)
from campfire_cli.app.workspace.schema.workspace_schema import Domain, ManifestProject
from campfire_cli.app.workspace.service.adoption_protocol import AdoptionRepositoryProtocol
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
    """Safely stage and adopt one existing folder as a managed Domain."""

    def __init__(
        self,
        settings: WorkspaceSettings,
        repository: AdoptionRepositoryProtocol,
        workspace_repository: WorkspaceRepositoryProtocol,
        manifest_repository: WorkspaceManifestRepository | None = None,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._workspaces = workspace_repository
        self._manifests = manifest_repository or WorkspaceManifestRepository()
        self._domains = DomainService(settings.vault_root, settings.state_root)
        self._executor = FileChangeExecutor(settings.vault_root, settings.state_root)

    def inventory(self, batch: str, source: Path, confirm: bool = False) -> AdoptionResult:
        root = source.expanduser().resolve()
        if not root.is_dir():
            raise ConfigurationError(f"待接管目录不存在：{root}")
        if root == self._settings.vault_root:
            raise ConfigurationError("不能把整个 Workspace 作为一个接管批次")
        source_kind = "internal" if self._settings.vault_root in root.parents else "external"
        inventory, issues = self._scan(root)
        staging = (
            self._settings.vault_root / "_收件箱" / "待接管" / batch
            if source_kind == "external"
            else None
        )
        state = AdoptionBatchState(
            batch=batch,
            source_path=str(root),
            source_kind=source_kind,
            staging_path=(
                staging.relative_to(self._settings.vault_root).as_posix() if staging else None
            ),
            status="blocked" if issues else "inventoried",
            inventory=inventory,
        )
        operations = []
        copied = 0
        if source_kind == "external":
            operations = [
                {
                    "action": "copy",
                    "source": str(root / item.path),
                    "path": f"{state.staging_path}/{item.path}",
                }
                for item in inventory
            ]
            if not issues and confirm:
                copy_issues = self._copy_to_staging(root, staging, inventory)
                issues.extend(copy_issues)
                if not issues:
                    copied = len(inventory)
                    state.status = "staged"
        self._repository.save(state)
        return AdoptionResult(
            status=(
                "blocked"
                if issues
                else "staged"
                if source_kind == "external" and confirm
                else "inventoried"
            ),
            batch=batch,
            source=str(root),
            source_kind=source_kind,
            staging_path=state.staging_path,
            item_count=len(inventory),
            copied_count=copied,
            operations=operations,
            issues=issues,
            write_performed=bool(copied),
        )

    def plan(
        self,
        batch: str,
        *,
        target_path: str,
        domain_id: str,
        name: str,
        space_id: str,
        domain_type: str,
        governance: str,
        parent_domain: str | None = None,
        project_id: str | None = None,
    ) -> AdoptionResult:
        state = self._repository.load(batch)
        if state.source_kind == "external" and state.status != "staged":
            return self._blocked(state, "adoption-source-not-staged", state.source_path)
        if not ID_RE.fullmatch(domain_id):
            raise ConfigurationError("Domain id 只能使用小写字母、数字和连字符")
        if any(item.id == domain_id for item in self._domains.discover()[0]):
            raise ConfigurationError(f"Domain id 已存在：{domain_id}")
        target = self._validate_target(target_path, space_id)
        source = self._active_source(state)
        if target != source and target.exists():
            raise ConfigurationError(f"目标路径已存在：{target_path}")
        if (source / DOMAIN_MARKER).exists():
            raise ConfigurationError("来源目录已经是受管 Domain")
        if governance == "project-docs" and not project_id:
            raise ConfigurationError("project-docs Domain 必须绑定 Project id")
        if project_id and self._workspaces.get_project(project_id) is None:
            raise ConfigurationError(f"Project 未注册：{project_id}")
        if parent_domain:
            parent = self._domains.show(parent_domain)
            parent_path = self._settings.vault_root / parent.path
            if parent_path not in target.parents:
                raise ConfigurationError("目标路径必须位于指定父 Domain 下")
            if parent.governance != governance:
                raise ConfigurationError("子 Domain 必须继承父 Domain governance")
        plan = AdoptionPlan(
            batch=batch,
            target_path=target.relative_to(self._settings.vault_root).as_posix(),
            domain_id=domain_id,
            name=name.strip(),
            space_id=space_id,
            domain_type=domain_type,
            governance=governance,
            parent_domain=parent_domain,
            project_id=project_id,
        )
        if not plan.name:
            raise ConfigurationError("Domain name 不能为空")
        state.plan = plan
        state.status = "planned"
        self._repository.save(state)
        operations = []
        if target != source:
            operations.append(
                {
                    "action": "move-directory",
                    "source": self._display_path(source),
                    "path": plan.target_path,
                }
            )
        operations.extend(
            [
                {"action": "create-domain-marker", "path": f"{plan.target_path}/_领域.md"},
                {
                    "action": "create-moc",
                    "path": f"{plan.target_path}/_总览/MOC-{plan.name}总览.md",
                },
            ]
        )
        return self._result(state, "planned", operations=operations)

    def apply(self, batch: str, confirm: bool = False) -> AdoptionResult:
        state = self._repository.load(batch)
        if state.plan is None:
            return self._blocked(state, "adoption-plan-missing", batch)
        source = self._active_source(state)
        target = safe_path(self._settings.vault_root, state.plan.target_path)
        issues = self._verify_files(source, state.inventory)
        if target != source and target.exists():
            issues.append({"code": "target-exists", "path": state.plan.target_path})
        moc = target / "_总览" / f"MOC-{state.plan.name}总览.md"
        if target == source and ((target / DOMAIN_MARKER).exists() or moc.exists()):
            issues.append({"code": "adoption-declaration-exists", "path": state.plan.target_path})
        if issues or not confirm:
            result = self._result(state, "blocked" if issues else "ready")
            result.issues = issues
            return result
        domain = Domain(
            id=state.plan.domain_id,
            name=state.plan.name,
            path=target,
            space_id=state.plan.space_id,
            type=state.plan.domain_type,
            governance=state.plan.governance,
            moc=f"_总览/MOC-{state.plan.name}总览",
            parent_domain=state.plan.parent_domain,
            project_id=state.plan.project_id,
        )
        writes = [
            FileWrite(target / DOMAIN_MARKER, DomainService.render_marker(domain)),
            FileWrite(target / f"{domain.moc}.md", DomainService.render_moc(domain)),
        ]
        expected = {source / item.path: item.sha256 for item in state.inventory}
        expected[target / DOMAIN_MARKER] = None
        expected[target / f"{domain.moc}.md"] = None
        moves = (PathMove(source, target),) if target != source else ()
        original_project = None
        updated_project = None
        if state.plan.project_id:
            original_project = self._workspaces.get_project(state.plan.project_id)
            if original_project:
                updated_project = original_project.model_copy(
                    update={"document_domain": state.plan.target_path}
                )
                manifest_path, manifest_content = self._manifest_update(updated_project)
                writes.append(FileWrite(manifest_path, manifest_content))
                expected[manifest_path] = file_sha256(manifest_path)
        original_state = state.model_copy(deep=True)
        state.status = "applied"
        try:
            with self._executor.transaction(
                FileChangeSet(
                    writes=tuple(writes),
                    moves=moves,
                    label="workspace adoption",
                    expected=expected,
                )
            ):
                if updated_project:
                    self._workspaces.save_project(updated_project)
                self._repository.save(state)
        except Exception:
            if original_project:
                self._workspaces.save_project(original_project)
            self._repository.save(original_state)
            raise
        result = self._result(state, "applied")
        result.write_performed = True
        return result

    def verify(self, batch: str) -> AdoptionResult:
        state = self._repository.load(batch)
        if state.plan is None:
            return self._blocked(state, "adoption-plan-missing", batch)
        target = safe_path(self._settings.vault_root, state.plan.target_path)
        issues = self._verify_files(target, state.inventory)
        if not (target / DOMAIN_MARKER).is_file():
            issues.append({"code": "domain-marker-missing", "path": state.plan.target_path})
        status = "ok" if not issues else "needs-review"
        result = self._result(state, status)
        result.issues = issues
        return result

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

    def _copy_to_staging(
        self, source: Path, staging: Path, items: list[AdoptionInventoryItem]
    ) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        for item in items:
            target = staging / item.path
            if target.exists() and (not target.is_file() or file_sha256(target) != item.sha256):
                issues.append({"code": "adoption-staging-conflict", "path": item.path})
        if issues:
            return issues
        for item in items:
            target = staging / item.path
            if target.is_file():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / item.path, target)
        return []

    def _validate_target(self, value: str, space_id: str) -> Path:
        target = safe_path(self._settings.vault_root, value)
        space = self._domains.spaces.show(space_id)
        space_root = self._settings.vault_root / space.path
        if space_root not in target.parents:
            raise ConfigurationError("目标路径必须位于指定 Space 下")
        if any(
            part in reserved_directories() or part.startswith(".")
            for part in target.relative_to(space_root).parts
        ):
            raise ConfigurationError("目标路径不能使用保留目录")
        return target

    def _active_source(self, state: AdoptionBatchState) -> Path:
        if state.source_kind == "external":
            if not state.staging_path:
                raise ConfigurationError("外部接管批次缺少暂存路径")
            return safe_path(self._settings.vault_root, state.staging_path)
        return Path(state.source_path).resolve()

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
        projects = self._workspaces.list_projects(self._settings.workspace_id)
        projects = [
            updated_project if project.id == updated_project.id else project for project in projects
        ]
        manifest.projects = [
            ManifestProject.model_validate(
                project.model_dump(exclude={"workspace_id", "local_path"})
            )
            for project in projects
        ]
        return self._manifests.path(self._settings.vault_root), self._manifests.render(manifest)

    def _result(
        self,
        state: AdoptionBatchState,
        status: str,
        *,
        operations: list[dict[str, str]] | None = None,
    ) -> AdoptionResult:
        return AdoptionResult(
            status=status,
            batch=state.batch,
            source=state.source_path,
            source_kind=state.source_kind,
            staging_path=state.staging_path,
            target_path=state.plan.target_path if state.plan else None,
            item_count=len(state.inventory),
            operations=operations or [],
            follow_up=(
                maintenance_follow_up(self._settings.workspace_id, [state.plan.target_path])
                if state.plan
                else []
            ),
        )

    def _blocked(self, state: AdoptionBatchState, code: str, path: str) -> AdoptionResult:
        result = self._result(state, "blocked")
        result.issues = [{"code": code, "path": path}]
        return result

    def _display_path(self, path: Path) -> str:
        if self._settings.vault_root in path.parents:
            return path.relative_to(self._settings.vault_root).as_posix()
        return str(path)
