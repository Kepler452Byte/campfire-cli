from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from campfire_cli.app.base.schema.operation_schema import maintenance_follow_up
from campfire_cli.app.workspace.repository.manifest_repository import (
    WorkspaceManifestRepository,
)
from campfire_cli.app.workspace.schema.restructure_schema import DomainRestructureResult
from campfire_cli.app.workspace.schema.workspace_schema import (
    Domain,
    ManifestProject,
    ProjectEntry,
)
from campfire_cli.app.workspace.service.structure_service import (
    DOMAIN_MARKER,
    ID_RE,
    DomainService,
    parse_marker,
    reserved_directories,
)
from campfire_cli.app.workspace.service.workspace_protocol import WorkspaceRepositoryProtocol
from campfire_cli.common.documents.markdown import parse_document, render_document
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


class DomainRestructureService:
    """Plan and execute structural changes to one declared Domain."""

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

    def rename(
        self,
        domain_id: str,
        name: str,
        *,
        rename_directory: bool = False,
        target_path: str | None = None,
        project_name: str | None = None,
        confirm: bool = False,
    ) -> DomainRestructureResult:
        domain = self._domain(domain_id)
        new_name = name.strip()
        if not new_name:
            raise ConfigurationError("Domain name 不能为空")
        if target_path and rename_directory:
            raise ConfigurationError("--target-path 与 --rename-directory 只能使用一个")
        target = domain.path
        if target_path:
            target = self._validate_target(target_path, domain)
        elif rename_directory:
            target = domain.path.with_name(self._directory_name(domain.path.name, new_name))
        return self._change(
            domain,
            target=target,
            name=new_name,
            new_id=domain.id,
            parent_domain=domain.parent_domain,
            project_name=project_name,
            confirm=confirm,
        )

    def move(
        self,
        domain_id: str,
        target_path: str,
        *,
        parent_domain: str | None = None,
        confirm: bool = False,
    ) -> DomainRestructureResult:
        domain = self._domain(domain_id)
        target = self._validate_target(target_path, domain)
        if parent_domain:
            parent = self._domain(parent_domain)
            if parent.path not in target.parents:
                raise ConfigurationError("目标路径必须位于指定父 Domain 下")
            if parent.governance != domain.governance:
                raise ConfigurationError("移动后的子 Domain 必须继承父 Domain governance")
        return self._change(
            domain,
            target=target,
            name=domain.name,
            new_id=domain.id,
            parent_domain=parent_domain,
            project_name=None,
            confirm=confirm,
        )

    def rekey(
        self, domain_id: str, new_id: str, *, confirm: bool = False
    ) -> DomainRestructureResult:
        if not ID_RE.fullmatch(new_id):
            raise ConfigurationError("Domain id 只能使用小写字母、数字和连字符")
        domain = self._domain(domain_id)
        if any(item.id == new_id for item in self._domains.discover()[0]):
            raise ConfigurationError(f"Domain id 已存在：{new_id}")
        return self._change(
            domain,
            target=domain.path,
            name=domain.name,
            new_id=new_id,
            parent_domain=domain.parent_domain,
            project_name=None,
            confirm=confirm,
        )

    def _change(
        self,
        domain: Domain,
        *,
        target: Path,
        name: str,
        new_id: str,
        parent_domain: str | None,
        project_name: str | None,
        confirm: bool,
    ) -> DomainRestructureResult:
        old_relative = domain.path.relative_to(self._settings.vault_root).as_posix()
        new_relative = target.relative_to(self._settings.vault_root).as_posix()
        projects = [
            project
            for project in self._workspaces.list_projects(self._settings.workspace_id)
            if project.document_domain == old_relative
        ]
        operations: list[dict[str, str]] = []
        if target != domain.path:
            operations.append(
                {"action": "move-domain", "source": old_relative, "path": new_relative}
            )
        if name != domain.name:
            operations.append({"action": "rename-domain", "source": domain.name, "path": name})
        if new_id != domain.id:
            operations.append({"action": "rekey-domain", "source": domain.id, "path": new_id})
        if parent_domain != domain.parent_domain:
            operations.append(
                {
                    "action": "update-parent-domain",
                    "source": domain.parent_domain or "none",
                    "path": parent_domain or "none",
                }
            )
        for project in projects:
            operations.append({"action": "update-project", "path": project.id})
        if not confirm:
            return self._result(domain, new_id, name, new_relative, operations, projects, False)
        if target != domain.path and target.exists():
            raise ConfigurationError(f"目标路径已存在：{new_relative}")
        current = self._domain(domain.id)
        if current.path != domain.path or current.name != domain.name:
            raise ConfigurationError("Domain 在预览后发生变化，请重新执行")
        updated_projects = [
            project.model_copy(
                update={
                    "document_domain": new_relative,
                    "name": project_name.strip() if project_name else project.name,
                }
            )
            for project in projects
        ]
        change_set = self._plan_changes(
            domain,
            target=target,
            name=name,
            new_id=new_id,
            parent_domain=parent_domain,
            updated_projects=updated_projects,
        )
        try:
            with self._executor.transaction(change_set):
                if updated_projects:
                    self._workspaces.save_projects(updated_projects)
        except Exception:
            if projects:
                self._workspaces.save_projects(projects)
            raise
        domain_check = self._domains.check()
        affected_prefix = f"{new_relative}/"
        issues = [
            issue
            for issue in domain_check.issues
            if str(issue.get("path", "")).startswith(affected_prefix)
            or issue.get("path") == new_relative
        ]
        result = self._result(domain, new_id, name, new_relative, operations, projects, True)
        if issues:
            result.status = "needs-review"
            result.issues = issues
        return result

    def _domain(self, domain_id: str) -> Domain:
        matches = [item for item in self._domains.discover()[0] if item.id == domain_id]
        if len(matches) != 1:
            raise ConfigurationError(f"Domain 不存在或不唯一：{domain_id}")
        return matches[0]

    def _validate_target(self, value: str, domain: Domain) -> Path:
        target = safe_path(self._settings.vault_root, value)
        spaces = self._domains.spaces.discover()[0]
        owners = [
            space for space in spaces if (self._settings.vault_root / space.path) in target.parents
        ]
        if len(owners) != 1:
            raise ConfigurationError("Domain 目标路径必须位于唯一一个已声明 Space 下")
        relative_to_space = target.relative_to(self._settings.vault_root / owners[0].path)
        if any(
            part in reserved_directories() or part.startswith(".")
            for part in relative_to_space.parts
        ):
            raise ConfigurationError("Domain 目标路径不能使用保留目录")
        if target != domain.path and target.exists():
            raise ConfigurationError(f"目标路径已存在：{value}")
        return target

    @staticmethod
    def _directory_name(current: str, name: str) -> str:
        if re.fullmatch(r"【[^】]+】文档中心", current):
            return f"【{name}】文档中心"
        return name

    def _plan_changes(
        self,
        domain: Domain,
        *,
        target: Path,
        name: str,
        new_id: str,
        parent_domain: str | None,
        updated_projects: list[ProjectEntry],
    ) -> FileChangeSet:
        references = self._reference_files()
        originals = {path: path.read_text(encoding="utf-8") for path in references}
        contents = dict(originals)
        marker = domain.path / DOMAIN_MARKER
        parsed = parse_document(contents[marker])
        frontmatter = dict(parsed.frontmatter)
        frontmatter["name"] = name
        frontmatter["domain_id"] = new_id
        if parent_domain:
            frontmatter["parent_domain"] = parent_domain
        else:
            frontmatter.pop("parent_domain", None)
        body = re.sub(r"^# .+$", f"# {name}", parsed.body, count=1, flags=re.MULTILINE)
        contents[marker] = render_document(frontmatter, body, list(frontmatter))

        if new_id != domain.id:
            for child in domain.path.rglob(DOMAIN_MARKER):
                if child == marker or parse_marker(child).get("parent_domain") != domain.id:
                    continue
                child_parsed = parse_document(contents[child])
                child_frontmatter = dict(child_parsed.frontmatter)
                child_frontmatter["parent_domain"] = new_id
                contents[child] = render_document(
                    child_frontmatter, child_parsed.body, list(child_frontmatter)
                )
            pattern = re.compile(
                rf"(?m)^(\s*(?:domain|domain_id|parent_domain):\s*)(['\"]?)"
                rf"{re.escape(domain.id)}\2\s*$"
            )
            for path, content in contents.items():
                if path.suffix.lower() == ".md":
                    contents[path] = pattern.sub(rf"\g<1>\g<2>{new_id}\g<2>", content)

        old_relative = domain.path.relative_to(self._settings.vault_root).as_posix()
        new_relative = target.relative_to(self._settings.vault_root).as_posix()
        if old_relative != new_relative:
            for path, content in contents.items():
                contents[path] = content.replace(old_relative, new_relative).replace(
                    quote(old_relative), quote(new_relative)
                )

        def final_path(path: Path) -> Path:
            if path == domain.path or domain.path in path.parents:
                return target / path.relative_to(domain.path)
            return path

        writes = [
            FileWrite(final_path(path), content)
            for path, content in contents.items()
            if content != originals[path]
        ]
        expected = {path: file_sha256(path) for path in references}
        if updated_projects:
            manifest_path, manifest_content = self._manifest_update(updated_projects)
            writes.append(FileWrite(manifest_path, manifest_content))
            expected[manifest_path] = file_sha256(manifest_path)
        return FileChangeSet(
            writes=tuple(writes),
            moves=(PathMove(domain.path, target),) if target != domain.path else (),
            label="domain restructure",
            expected=expected,
        )

    def _manifest_update(self, updated_projects: list[ProjectEntry]) -> tuple[Path, str]:
        manifest = self._manifests.load(self._settings.vault_root)
        if manifest is None:
            raise ConfigurationError("Workspace 缺少 .campfire.yaml")
        replacements = {project.id: project for project in updated_projects}
        projects = [
            replacements.get(project.id, project)
            for project in self._workspaces.list_projects(self._settings.workspace_id)
        ]
        manifest.projects = [
            ManifestProject.model_validate(
                project.model_dump(exclude={"workspace_id", "local_path"})
            )
            for project in projects
        ]
        return self._manifests.path(self._settings.vault_root), self._manifests.render(manifest)

    def _reference_files(self) -> list[Path]:
        ignored = {".git", ".obsidian"}
        return sorted(
            path
            for path in self._settings.vault_root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".md", ".canvas", ".base"}
            and not any(
                part in ignored for part in path.relative_to(self._settings.vault_root).parts
            )
        )

    def _result(
        self,
        domain: Domain,
        domain_id: str,
        name: str,
        path: str,
        operations: list[dict[str, str]],
        projects: list,
        written: bool,
    ) -> DomainRestructureResult:
        return DomainRestructureResult(
            status="applied" if written else "planned",
            domain_id=domain_id,
            name=name,
            path=path,
            operations=operations,
            affected_projects=[project.id for project in projects],
            write_performed=written,
            follow_up=maintenance_follow_up(self._settings.workspace_id, [path]),
        )
