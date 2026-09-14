from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath

from campfire_cli.app.workspace.repository.manifest_repository import WorkspaceManifestRepository
from campfire_cli.app.workspace.schema.workspace_schema import (
    ManifestProject,
    ProjectBindResult,
    ProjectCheckResult,
    ProjectCreateResult,
    ProjectEntry,
    ProjectListResult,
    ProjectMatch,
    ProjectResolutionResult,
    ProjectResult,
    ProjectUpsertRequest,
)
from campfire_cli.app.workspace.service.structure_service import DomainService, SpaceService
from campfire_cli.app.workspace.service.workspace_protocol import WorkspaceRepositoryProtocol
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem import workspace_write_lock
from campfire_cli.config.defaults import config_section


class ProjectService:
    def __init__(
        self,
        governance_root: Path,
        repository: WorkspaceRepositoryProtocol,
        manifest_repository: WorkspaceManifestRepository | None = None,
    ) -> None:
        self._root = governance_root
        self._repository = repository
        self._manifests = manifest_repository or WorkspaceManifestRepository()

    def add(self, request: ProjectUpsertRequest) -> ProjectResult:
        if self._repository.get_project(request.project_id):
            raise ConfigurationError(
                f"Project 已存在：{request.project_id}；请使用 campfire workspace project update"
            )
        return self._save(request)

    def update(self, request: ProjectUpsertRequest) -> ProjectResult:
        if not self._repository.get_project(request.project_id):
            raise ConfigurationError(
                f"Project 未注册：{request.project_id}；请使用 campfire workspace project add"
            )
        return self._save(request)

    def create(self, request: ProjectUpsertRequest, confirm: bool = False) -> ProjectCreateResult:
        if self._repository.get_project(request.project_id):
            raise ConfigurationError(f"Project 已存在：{request.project_id}")
        project, domain_path = self._prepare(request, require_domain=False)
        if domain_path.exists():
            raise ConfigurationError(
                f"项目文档领域已存在；接入现有领域请使用 project add：{domain_path}"
            )
        structure = DomainService(
            Path(self._repository.load_registry().workspaces[project.workspace_id].path), self._root
        )
        space_id = self._owning_space_id(structure.spaces, project.document_domain)
        domain_plan = structure.create(
            domain_id=f"project-{project.id}",
            name=project.name,
            path=project.document_domain,
            space_id=space_id,
            domain_type="project-domain",
            governance="project-docs",
            project_id=project.id,
            confirm=False,
        )
        operations = [*domain_plan.operations, {"action": "register-project", "path": project.id}]
        if not confirm:
            return ProjectCreateResult(
                status="planned",
                project=project,
                document_domain_path=str(domain_path),
                operations=operations,
            )
        structure.create(
            domain_id=f"project-{project.id}",
            name=project.name,
            path=project.document_domain,
            space_id=space_id,
            domain_type="project-domain",
            governance="project-docs",
            project_id=project.id,
            confirm=True,
        )
        with workspace_write_lock(self._root):
            if self._repository.get_project(request.project_id):
                raise ConfigurationError("Project 在确认后已被注册")
            self._repository.save_project(project)
            self._sync_manifest(project.workspace_id)
        return ProjectCreateResult(
            status="created",
            project=project,
            document_domain_path=str(domain_path),
            operations=operations,
            write_performed=True,
        )

    def list(self, workspace_id: str | None = None) -> ProjectListResult:
        if workspace_id and workspace_id not in self._repository.load_registry().workspaces:
            raise ConfigurationError(f"Workspace 未注册：{workspace_id}")
        return ProjectListResult(projects=self._repository.list_projects(workspace_id))

    def show(self, project_id: str) -> ProjectResult:
        project = self._repository.get_project(project_id)
        if not project:
            raise ConfigurationError(f"Project 未注册：{project_id}")
        return ProjectResult(**project.model_dump(), operation="none")

    def resolve(self, path: Path) -> ProjectResolutionResult:
        query = path.expanduser().resolve()
        # 先做零成本的 local_path 匹配；有命中时注册信息足以应答，跳过 git 子进程
        # （每次会话冷启动必经路径，两个 git 探测只为富化字段，属纯延迟开销）。
        # 无 local_path 命中才跑 git 探测走 remote 兜底；此时 git_root/git_remote_url
        # 输出实测值，local 命中路径输出 None 与注册 remote。
        local_matches: list[ProjectMatch] = []
        for project in self._repository.list_projects():
            if not project.local_path:
                continue
            registered = Path(project.local_path).expanduser().resolve()
            if query == registered or registered in query.parents:
                local_matches.append(ProjectMatch(project=project, match_basis=["local-path"]))
        if local_matches:
            deepest = max(len(Path(item.project.local_path or "/").parts) for item in local_matches)
            local_matches = [
                item
                for item in local_matches
                if len(Path(item.project.local_path or "/").parts) == deepest
            ]
            return ProjectResolutionResult(
                status="matched" if len(local_matches) == 1 else "ambiguous",
                query_path=str(query),
                git_root=None,
                git_remote_url=local_matches[0].project.git_remote_url,
                matches=local_matches,
            )
        git_root_value = self._git_command(query, "rev-parse", "--show-toplevel")
        git_root = Path(git_root_value).resolve() if git_root_value else None
        remote = self._git_command(git_root or query, "remote", "get-url", "origin")
        normalized_remote = self._normalize_remote(remote)
        matches: list[ProjectMatch] = []
        for project in self._repository.list_projects():
            basis: list[str] = []
            if (
                normalized_remote
                and project.git_remote_url
                and normalized_remote == self._normalize_remote(project.git_remote_url)
            ):
                basis.append("git-remote")
            if basis:
                matches.append(ProjectMatch(project=project, match_basis=basis))
        remote_only = matches
        if local_matches:
            deepest = max(len(Path(item.project.local_path or "/").parts) for item in local_matches)
            local_matches = [
                item
                for item in local_matches
                if len(Path(item.project.local_path or "/").parts) == deepest
            ]
            status = "matched" if len(local_matches) == 1 else "ambiguous"
            return ProjectResolutionResult(
                status=status,
                query_path=str(query),
                git_root=str(git_root) if git_root else None,
                git_remote_url=remote,
                matches=local_matches,
            )
        if remote_only:
            # 查询目录本身未注册（常见于 monorepo 子目录或未绑定 local_path 的新机器），
            # 仅共享 Git remote 不足以断言"当前目录属于该项目"，不返回 matched 终态。
            candidates = "、".join(item.project.id for item in remote_only)
            return ProjectResolutionResult(
                status="unmatched",
                query_path=str(query),
                git_root=str(git_root) if git_root else None,
                git_remote_url=remote,
                remote_matches=remote_only,
                hint=(
                    f"查询目录未注册为任何项目的 local_path，仅与 {candidates} 共享 Git remote；"
                    "若确属其中之一请运行 campfire workspace project bind "
                    "--id <id> --local-path <path>，若是新项目（如 monorepo 子目录）请走注册流程"
                ),
            )
        return ProjectResolutionResult(
            status="unmatched",
            query_path=str(query),
            git_root=str(git_root) if git_root else None,
            git_remote_url=remote,
        )

    def check(self, project_id: str) -> ProjectCheckResult:
        project = self._repository.get_project(project_id)
        if not project:
            raise ConfigurationError(f"Project 未注册：{project_id}")
        registry = self._repository.load_registry()
        workspace = registry.workspaces.get(project.workspace_id)
        issues: list[dict[str, str | None]] = []
        local_path = Path(project.local_path).expanduser().resolve() if project.local_path else None
        local_exists = bool(local_path and local_path.is_dir())
        if project.local_path and not local_exists:
            issues.append({"code": "project-local-path-missing", "path": project.local_path})
        observed_remote = (
            self._git_command(local_path, "remote", "get-url", "origin") if local_exists else None
        )

        if (
            observed_remote
            and project.git_remote_url
            and self._normalize_remote(observed_remote)
            != self._normalize_remote(project.git_remote_url)
        ):
            issues.append(
                {
                    "code": "project-git-remote-changed",
                    "expected": project.git_remote_url,
                    "actual": observed_remote,
                }
            )
        observed_branch = self._detect_default_branch(local_path) if local_exists else None
        if observed_branch and project.default_branch and observed_branch != project.default_branch:
            issues.append(
                {
                    "code": "project-default-branch-changed",
                    "expected": project.default_branch,
                    "actual": observed_branch,
                }
            )
        domain_path = (
            Path(workspace.path) / project.document_domain if workspace is not None else None
        )
        if workspace is None:
            issues.append({"code": "project-workspace-missing", "path": project.workspace_id})
        elif not domain_path.is_dir():
            issues.append({"code": "project-document-domain-missing", "path": str(domain_path)})
        return ProjectCheckResult(
            status="ok" if not issues else "needs-review",
            project=project,
            observed={
                "local_path_exists": local_exists,
                "git_remote_url": observed_remote,
                "default_branch": observed_branch,
                "document_domain_path": str(domain_path) if domain_path else None,
                "document_domain_exists": bool(domain_path and domain_path.is_dir()),
            },
            issues=issues,
        )

    def bind(self, project_id: str, local_path: Path) -> ProjectBindResult:
        project = self._repository.get_project(project_id)
        if not project:
            raise ConfigurationError(f"Project 未注册：{project_id}")
        path = local_path.expanduser().resolve()
        if not path.is_dir():
            raise ConfigurationError(f"项目本地路径不存在：{path}")
        observed_remote = self._git_value(path, "remote", "get-url", "origin")
        if (
            project.git_remote_url
            and observed_remote
            and self._normalize_remote(project.git_remote_url)
            != self._normalize_remote(observed_remote)
        ):
            raise ConfigurationError("本地项目的 Git remote 与 Manifest 元数据不一致")
        updated = project.model_copy(
            update={
                "local_path": str(path),
                "git_remote_url": project.git_remote_url or observed_remote,
                "default_branch": project.default_branch or self._detect_default_branch(path),
            }
        )
        with workspace_write_lock(self._root):
            self._repository.save_project(updated)
            self._sync_manifest(updated.workspace_id)
        return ProjectBindResult(project=updated)

    def _save(self, request: ProjectUpsertRequest) -> ProjectResult:
        project, _domain_path = self._prepare(request, require_domain=True)
        with workspace_write_lock(self._root):
            operation = self._repository.save_project(project)
            self._sync_manifest(project.workspace_id)
        return ProjectResult(**project.model_dump(), operation=operation)

    def _sync_manifest(self, workspace_id: str) -> None:
        registry = self._repository.load_registry()
        workspace = registry.workspaces.get(workspace_id)
        if not workspace:
            raise ConfigurationError(f"Workspace 未注册：{workspace_id}")
        root = Path(workspace.path).expanduser().resolve()
        manifest = self._manifests.load(root)
        if manifest is None:
            raise ConfigurationError(
                f"Workspace 缺少 .campfire.yaml；请先运行 campfire setup --workspace {root}"
            )
        manifest.projects = [
            ManifestProject.model_validate(
                project.model_dump(exclude={"workspace_id", "local_path"})
            )
            for project in self._repository.list_projects(workspace_id)
        ]
        self._manifests.save(root, manifest)

    def _prepare(
        self, request: ProjectUpsertRequest, *, require_domain: bool
    ) -> tuple[ProjectEntry, Path]:
        self._validate_id(request.project_id)
        registry = self._repository.load_registry()
        workspace = registry.workspaces.get(request.workspace_id)
        if not workspace:
            raise ConfigurationError(f"Workspace 未注册：{request.workspace_id}")
        domain = self._validate_domain(request.document_domain)
        domain_path = Path(workspace.path) / domain
        if require_domain and not domain_path.is_dir():
            raise ConfigurationError(f"项目文档领域不存在：{domain_path}")
        local_path = request.local_path.expanduser().resolve() if request.local_path else None
        if local_path and not local_path.is_dir():
            raise ConfigurationError(f"项目本地路径不存在：{local_path}")
        remote = request.git_remote_url or self._git_value(
            local_path, "remote", "get-url", "origin"
        )
        branch = request.default_branch or self._detect_default_branch(local_path)
        statuses = set(config_section("project")["statuses"])
        if request.status not in statuses:
            raise ConfigurationError(f"Project status 必须是：{', '.join(sorted(statuses))}")
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
        return project, domain_path

    @staticmethod
    def _owning_space_id(spaces: SpaceService, document_domain: str) -> str:
        path = PurePosixPath(document_domain)
        matches = [
            space
            for space in spaces.discover()[0]
            if path == PurePosixPath(space.path) or PurePosixPath(space.path) in path.parents
        ]
        if len(matches) != 1:
            raise ConfigurationError("项目文档领域必须唯一位于一个已声明 Space 下")
        expected = config_section("project")["default_space_type"]
        if matches[0].type != expected:
            raise ConfigurationError(f"项目文档领域必须位于 {expected} 类型 Space")
        return matches[0].id

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
        if not local_path or not local_path.is_dir():
            return None
        result = subprocess.run(
            ["git", "-C", str(local_path), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None if result.returncode == 0 else None

    @staticmethod
    def _git_command(path: Path, *arguments: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(path), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None if result.returncode == 0 else None

    @staticmethod
    def _normalize_remote(value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip().removesuffix(".git").rstrip("/")
        ssh = re.fullmatch(r"git@([^:]+):(.+)", normalized)
        if ssh:
            return f"{ssh.group(1).lower()}/{ssh.group(2).lower()}"
        normalized = re.sub(r"^[a-z][a-z0-9+.-]*://", "", normalized, flags=re.I)
        normalized = normalized.removeprefix("git@").replace(":", "/", 1)
        return normalized.lower()

    @classmethod
    def _detect_default_branch(cls, local_path: Path | None) -> str | None:
        reference = cls._git_value(local_path, "symbolic-ref", "refs/remotes/origin/HEAD")
        if reference:
            return reference.rsplit("/", 1)[-1]
        return cls._git_value(local_path, "branch", "--show-current")
