from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from campfire_cli.app.workspace.repository.manifest_repository import WorkspaceManifestRepository
from campfire_cli.app.workspace.schema.workspace_schema import (
    ProjectBindResult,
    ProjectCheckResult,
    ProjectCreateResult,
    ProjectEntry,
    ProjectListResult,
    ProjectMatch,
    ProjectRegistrationRequest,
    ProjectResolutionResult,
    ProjectResult,
    RepositoryEntry,
    portable_project,
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

    def adopt(self, request: ProjectRegistrationRequest) -> ProjectResult:
        if self._repository.get_project(request.project_id):
            raise ConfigurationError(
                f"Project 已存在：{request.project_id}；请使用 campfire workspace project update"
            )
        return self._save(request)

    def update(self, request: ProjectRegistrationRequest) -> ProjectResult:
        existing = self._repository.get_project(request.project_id)
        if not existing:
            raise ConfigurationError(
                f"Project 未注册：{request.project_id}；请使用 campfire workspace project adopt"
            )
        request.repositories = existing.repositories
        return self._save(request)

    def create(
        self, request: ProjectRegistrationRequest, confirm: bool = False
    ) -> ProjectCreateResult:
        if self._repository.get_project(request.project_id):
            raise ConfigurationError(f"Project 已存在：{request.project_id}")
        project, domain_path = self._prepare(request, require_domain=False)
        if domain_path.exists():
            raise ConfigurationError(
                f"项目文档领域已存在；接入现有领域请使用 project adopt：{domain_path}"
            )
        structure = DomainService(
            Path(self._repository.load_registry().workspaces[project.workspace_id].path), self._root
        )
        if request.document_domain_path is None:
            raise ConfigurationError("创建 Project 必须提供项目根 Domain 路径")
        self._owning_space_id(structure.spaces, request.document_domain_path)
        domain_plan = structure.create(
            domain_id=project.document_domain_id,
            name=project.name,
            path=request.document_domain_path,
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
            domain_id=project.document_domain_id,
            name=project.name,
            path=request.document_domain_path,
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

    def show(self, project_id: str) -> ProjectEntry:
        project = self._repository.get_project(project_id)
        if not project:
            raise ConfigurationError(f"Project 未注册：{project_id}")
        return project

    def resolve(self, path: Path) -> ProjectResolutionResult:
        query = path.expanduser().resolve()
        projects = self._repository.list_projects()
        candidates = []
        for project in projects:
            for repository in project.repositories:
                if not repository.local_path:
                    continue
                registered = Path(repository.local_path).expanduser().resolve()
                if query == registered or registered in query.parents:
                    candidates.append(
                        (
                            len(registered.parts),
                            ProjectMatch(
                                project=project,
                                repository_id=repository.id,
                                repository=repository,
                                match_basis=["local-path"],
                            ),
                        )
                    )
        if candidates:
            depth = max(item[0] for item in candidates)
            matches = [item[1] for item in candidates if item[0] == depth]
            return ProjectResolutionResult(
                status="matched" if len(matches) == 1 else "ambiguous",
                query_path=str(query),
                matches=matches,
                git_remote_url=matches[0].repository.git_remote_url if len(matches) == 1 else None,
            )
        git_root_value = self._git_command(query, "rev-parse", "--show-toplevel")
        git_root = Path(git_root_value).resolve() if git_root_value else None
        remote = self._git_command(git_root or query, "remote", "get-url", "origin")
        normalized = self._normalize_remote(remote)
        matches = [
            ProjectMatch(
                project=project, repository_id=item.id, repository=item, match_basis=["git-remote"]
            )
            for project in projects
            for item in project.repositories
            if normalized and normalized == self._normalize_remote(item.git_remote_url)
        ]
        return ProjectResolutionResult(
            status="unmatched",
            query_path=str(query),
            git_root=str(git_root) if git_root else None,
            git_remote_url=remote,
            remote_matches=matches,
            hint=(
                "Remote matches are candidates only. Use workspace project bind "
                "--id <project-id> --repository <repository-id> --local-path <path>."
                if matches
                else None
            ),
        )

    def check(self, project_id: str) -> ProjectCheckResult:
        project = self._repository.get_project(project_id)
        if not project:
            raise ConfigurationError(f"Project 未注册：{project_id}")
        registry = self._repository.load_registry()
        workspace = registry.workspaces.get(project.workspace_id)
        issues: list[dict[str, str | None]] = []
        observations = []
        for repository in project.repositories:
            path = (
                Path(repository.local_path).expanduser().resolve()
                if repository.local_path
                else None
            )
            exists = bool(path and path.is_dir())
            if not repository.local_path:
                issues.append(
                    {"code": "project-repository-unbound", "repository_id": repository.id}
                )
            elif not exists:
                issues.append(
                    {
                        "code": "project-local-path-missing",
                        "path": repository.local_path,
                        "repository_id": repository.id,
                    }
                )
            remote = self._git_command(path, "remote", "get-url", "origin") if exists else None
            branch = self._detect_default_branch(path) if exists else None
            if (
                remote
                and repository.git_remote_url
                and self._normalize_remote(remote)
                != self._normalize_remote(repository.git_remote_url)
            ):
                issues.append(
                    {
                        "code": "project-git-remote-changed",
                        "repository_id": repository.id,
                        "expected": repository.git_remote_url,
                        "actual": remote,
                    }
                )
            if branch and repository.default_branch and branch != repository.default_branch:
                issues.append(
                    {
                        "code": "project-default-branch-changed",
                        "repository_id": repository.id,
                        "expected": repository.default_branch,
                        "actual": branch,
                    }
                )
            observations.append(
                {
                    "repository_id": repository.id,
                    "local_path_exists": exists,
                    "git_remote_url": remote,
                    "default_branch": branch,
                }
            )
        domain_path = None
        if workspace is not None:
            try:
                domain = DomainService(Path(workspace.path), self._root).show(
                    project.document_domain_id
                )
                domain_path = Path(workspace.path) / domain.path
            except ConfigurationError:
                issues.append(
                    {
                        "code": "project-document-domain-missing",
                        "domain_id": project.document_domain_id,
                    }
                )
        if workspace is None:
            issues.append({"code": "project-workspace-missing", "path": project.workspace_id})
        return ProjectCheckResult(
            status="ok" if not issues else "needs-review",
            project=project,
            observed={
                "repositories": observations,
                "document_domain_path": str(domain_path) if domain_path else None,
                "document_domain_exists": bool(domain_path and domain_path.is_dir()),
            },
            issues=issues,
        )

    def _repository_project(
        self, project: ProjectEntry, repositories: list[RepositoryEntry]
    ) -> ProjectEntry:
        payload = project.model_dump()
        payload["repositories"] = [item.model_dump() for item in repositories]
        return ProjectEntry.model_validate(payload)

    def _validated_repository(self, repository: RepositoryEntry) -> RepositoryEntry:
        payload = repository.model_dump()
        path = Path(repository.local_path).expanduser().resolve() if repository.local_path else None
        if path and not path.is_dir():
            raise ConfigurationError(
                f"Repository directory does not exist: {path}",
                code="repository-local-path-missing",
                field="local_path",
            )
        if path:
            remote = self._git_value(path, "remote", "get-url", "origin")
            if (
                remote
                and repository.git_remote_url
                and self._normalize_remote(remote)
                != self._normalize_remote(repository.git_remote_url)
            ):
                raise ConfigurationError(
                    "Local remote differs from portable repository metadata",
                    code="repository-remote-mismatch",
                    repository_id=repository.id,
                )
            payload.update(
                local_path=str(path),
                git_remote_url=repository.git_remote_url or remote,
                default_branch=repository.default_branch or self._detect_default_branch(path),
            )
        return RepositoryEntry.model_validate(payload)

    def _snapshot_hash(self, project: ProjectEntry) -> str:
        workspace = self._repository.load_registry().workspaces[project.workspace_id]
        manifest = self._manifests.path(Path(workspace.path)).read_bytes()
        return hashlib.sha256(project.model_dump_json().encode() + manifest).hexdigest()

    def update_repository(
        self,
        project_id: str,
        repository_id: str,
        *,
        changes: dict,
        remove: bool = False,
        unbind: bool = False,
        confirm: bool = False,
        expected_hash: str | None = None,
    ) -> dict:
        self._validate_id(repository_id, field="repository")
        project = self.show(project_id)
        existing = next((item for item in project.repositories if item.id == repository_id), None)
        if remove and (changes or unbind):
            raise ConfigurationError(
                "Removal cannot be combined with repository changes",
                code="repository-options-conflict",
            )
        if (remove or unbind) and existing is None:
            raise ConfigurationError("Repository is not registered", code="repository-not-found")
        if unbind and "local_path" in changes:
            raise ConfigurationError(
                "Unbind cannot be combined with local-path", code="repository-options-conflict"
            )
        repositories = list(project.repositories)
        if remove:
            repositories = [item for item in repositories if item.id != repository_id]
        else:
            payload = existing.model_dump() if existing else {"id": repository_id}
            payload.update(changes)
            if unbind:
                payload["local_path"] = None
            repository = self._validated_repository(RepositoryEntry.model_validate(payload))
            if existing:
                repositories = [
                    repository if item.id == repository_id else item for item in repositories
                ]
            else:
                repositories.append(repository)
        updated = self._repository_project(project, repositories)
        snapshot = self._snapshot_hash(project)
        if not confirm:
            return {
                "status": "planned",
                "project": updated.model_dump(mode="json"),
                "expected_hash": snapshot,
                "write_performed": False,
                "follow_up": [],
            }
        with workspace_write_lock(self._root):
            current = self.show(project_id)
            if not expected_hash or expected_hash != self._snapshot_hash(current):
                raise ConfigurationError(
                    "Project or Manifest changed; preview again", code="project-concurrent-change"
                )
            self._persist(updated)
        return {
            "status": "applied",
            "project": updated.model_dump(mode="json"),
            "write_performed": True,
            "follow_up": [],
        }

    def _persist(self, project: ProjectEntry) -> None:
        previous = self._repository.list_projects(project.workspace_id)
        self._repository.save_project(project)
        try:
            self._sync_manifest(project.workspace_id)
        except Exception:
            self._repository.replace_projects(project.workspace_id, previous)
            raise

    def bind(self, project_id: str, local_path: Path, repository_id: str) -> ProjectBindResult:
        project = self.show(project_id)
        repository = next((item for item in project.repositories if item.id == repository_id), None)
        if repository is None:
            raise ConfigurationError(
                "Repository is not registered",
                code="repository-not-found",
                field="repository",
                repository_id=repository_id,
            )
        snapshot = self._snapshot_hash(project)
        updated = self._validated_repository(
            RepositoryEntry(**{**repository.model_dump(), "local_path": str(local_path)})
        )
        repositories = [
            updated if item.id == repository.id else item for item in project.repositories
        ]
        project = self._repository_project(project, repositories)
        with workspace_write_lock(self._root):
            if self._snapshot_hash(self.show(project_id)) != snapshot:
                raise ConfigurationError(
                    "Project or Manifest changed; retry bind", code="project-concurrent-change"
                )
            self._persist(project)
        return ProjectBindResult(project=project)

    def _save(self, request: ProjectRegistrationRequest) -> ProjectResult:
        before = self._repository.get_project(request.project_id)
        manifest_path = self._manifests.path(
            Path(self._repository.load_registry().workspaces[request.workspace_id].path)
        )
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        project, _domain_path = self._prepare(request, require_domain=True)
        with workspace_write_lock(self._root):
            if (
                self._repository.get_project(request.project_id) != before
                or hashlib.sha256(manifest_path.read_bytes()).hexdigest() != manifest_hash
            ):
                raise ConfigurationError(
                    "Project or Manifest changed; retry update", code="project-concurrent-change"
                )
            self._persist(project)
        return ProjectResult(**project.model_dump(), operation="updated" if before else "created")

    def _sync_manifest(self, workspace_id: str) -> None:
        registry = self._repository.load_registry()
        workspace = registry.workspaces.get(workspace_id)
        if not workspace:
            raise ConfigurationError(f"Workspace 未注册：{workspace_id}")
        root = Path(workspace.path).expanduser().resolve()
        manifest = self._manifests.load(root)
        if manifest is None:
            raise ConfigurationError(
                f"Workspace 缺少 .campfire.yaml；请先运行 campfire setup --path {root}"
            )
        manifest.projects = [
            portable_project(project) for project in self._repository.list_projects(workspace_id)
        ]
        self._manifests.save(root, manifest)

    def _prepare(
        self, request: ProjectRegistrationRequest, *, require_domain: bool
    ) -> tuple[ProjectEntry, Path]:
        self._validate_id(request.project_id)
        registry = self._repository.load_registry()
        workspace = registry.workspaces.get(request.workspace_id)
        if not workspace:
            raise ConfigurationError(f"Workspace 未注册：{request.workspace_id}")
        self._validate_id(request.document_domain_id)
        duplicate = next(
            (
                project
                for project in self._repository.list_projects(request.workspace_id)
                if project.id != request.project_id
                and project.status == "active"
                and project.document_domain_id == request.document_domain_id
            ),
            None,
        )
        if duplicate:
            raise ConfigurationError(f"Domain 已被 active Project 绑定：{duplicate.id}")
        domains = DomainService(Path(workspace.path), self._root)
        if require_domain:
            domain_path = Path(workspace.path) / domains.show(request.document_domain_id).path
        elif request.document_domain_path is not None:
            relative = self._validate_domain(request.document_domain_path)
            domain_path = Path(workspace.path) / relative
        else:
            raise ConfigurationError("创建 Project 必须提供项目根 Domain 路径")
        statuses = set(config_section("project")["statuses"])
        if request.status not in statuses:
            raise ConfigurationError(f"Project status 必须是：{', '.join(sorted(statuses))}")
        try:
            project = ProjectEntry(
                id=request.project_id,
                workspace_id=request.workspace_id,
                name=request.name.strip(),
                document_domain_id=request.document_domain_id,
                status=request.status,
                repositories=[self._validated_repository(item) for item in request.repositories],
            )
        except ValidationError as exc:
            duplicate = any(item["type"] == "repository-id-duplicate" for item in exc.errors())
            raise ConfigurationError(
                "Invalid repository configuration",
                code="repository-id-duplicate" if duplicate else "invalid-repositories",
                field="repositories",
                expected_type="array[repository]",
                hint="Use unique stable repository ids and declared repository fields",
                detail=str(exc),
            ) from exc
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
    def _validate_id(project_id: str, *, field: str = "id") -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", project_id):
            raise ConfigurationError(
                "id 只能使用小写字母、数字和连字符，最多 63 字符",
                code="invalid-id",
                field=field,
                expected_type="string",
                example="backend",
            )

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
