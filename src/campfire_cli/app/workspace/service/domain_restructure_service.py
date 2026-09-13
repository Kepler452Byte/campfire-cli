from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from campfire_cli.app.maintenance.service.maintenance_service import MaintenanceService
from campfire_cli.app.workspace.repository.manifest_repository import (
    WorkspaceManifestRepository,
)
from campfire_cli.app.workspace.schema.restructure_schema import DomainRestructureResult
from campfire_cli.app.workspace.schema.workspace_schema import Domain, ManifestProject
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
from campfire_cli.common.filesystem import atomic_write, safe_path, workspace_write_lock
from campfire_cli.config.settings import WorkspaceSettings


class DomainRestructureService:
    """Plan and execute structural changes to one declared Domain."""

    def __init__(
        self,
        settings: WorkspaceSettings,
        workspace_repository: WorkspaceRepositoryProtocol,
        maintenance: MaintenanceService,
        manifest_repository: WorkspaceManifestRepository | None = None,
    ) -> None:
        self._settings = settings
        self._workspaces = workspace_repository
        self._maintenance = maintenance
        self._manifests = manifest_repository or WorkspaceManifestRepository()
        self._domains = DomainService(settings.vault_root, settings.state_root)

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
        with workspace_write_lock(self._settings.state_root):
            current = self._domain(domain.id)
            if current.path != domain.path or current.name != domain.name:
                raise ConfigurationError("Domain 在预览后发生变化，请重新执行")
            if target != domain.path:
                target.parent.mkdir(parents=True, exist_ok=True)
                domain.path.rename(target)
            marker = target / DOMAIN_MARKER
            self._update_marker(marker, name=name, domain_id=new_id, parent_domain=parent_domain)
            if new_id != domain.id:
                self._rewrite_child_parent_ids(target, domain.id, new_id)
                self._rewrite_domain_id_references(domain.id, new_id)
            self._rewrite_path_references(old_relative, new_relative)
            for project in projects:
                updated = project.model_copy(
                    update={
                        "document_domain": new_relative,
                        "name": project_name.strip() if project_name else project.name,
                    }
                )
                self._workspaces.save_project(updated)
            self._sync_manifest()
        sync = self._maintenance.sync(scope=new_relative)
        index = self._maintenance.check(summary=True)
        operations.extend(
            {str(key): str(value) for key, value in operation.items()}
            for operation in sync.operations
        )
        domain_check = self._domains.check()
        affected_prefix = f"{new_relative}/"
        issues = [
            issue
            for issue in domain_check.issues
            if str(issue.get("path", "")).startswith(affected_prefix)
            or issue.get("path") == new_relative
        ]
        issues.extend(issue.model_dump(mode="json") for issue in sync.issues)
        issues.extend(issue.model_dump(mode="json") for issue in index.issues)
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

    @staticmethod
    def _update_marker(
        marker: Path, *, name: str, domain_id: str, parent_domain: str | None
    ) -> None:
        parsed = parse_document(marker.read_text(encoding="utf-8"))
        frontmatter = dict(parsed.frontmatter)
        frontmatter["name"] = name
        frontmatter["domain_id"] = domain_id
        if parent_domain:
            frontmatter["parent_domain"] = parent_domain
        else:
            frontmatter.pop("parent_domain", None)
        body = re.sub(r"^# .+$", f"# {name}", parsed.body, count=1, flags=re.MULTILINE)
        atomic_write(marker, render_document(frontmatter, body, list(frontmatter)))

    def _rewrite_child_parent_ids(self, root: Path, old_id: str, new_id: str) -> None:
        for marker in root.rglob(DOMAIN_MARKER):
            if (
                marker == root / DOMAIN_MARKER
                or parse_marker(marker).get("parent_domain") != old_id
            ):
                continue
            parsed = parse_document(marker.read_text(encoding="utf-8"))
            frontmatter = dict(parsed.frontmatter)
            frontmatter["parent_domain"] = new_id
            atomic_write(marker, render_document(frontmatter, parsed.body, list(frontmatter)))

    def _rewrite_domain_id_references(self, old_id: str, new_id: str) -> None:
        pattern = re.compile(
            rf"(?m)^(\s*(?:domain|domain_id|parent_domain):\s*)(['\"]?){re.escape(old_id)}\2\s*$"
        )
        for path in self._settings.vault_root.rglob("*.md"):
            if ".git" in path.relative_to(self._settings.vault_root).parts:
                continue
            text = path.read_text(encoding="utf-8")
            updated = pattern.sub(rf"\g<1>\g<2>{new_id}\g<2>", text)
            if updated != text:
                atomic_write(path, updated)

    def _rewrite_path_references(self, old: str, new: str) -> None:
        if old == new:
            return
        ignored = {".git", ".obsidian"}
        for path in self._settings.vault_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".canvas", ".base"}:
                continue
            if any(part in ignored for part in path.relative_to(self._settings.vault_root).parts):
                continue
            text = path.read_text(encoding="utf-8")
            updated = text.replace(old, new).replace(quote(old), quote(new))
            if updated != text:
                atomic_write(path, updated)

    def _sync_manifest(self) -> None:
        manifest = self._manifests.load(self._settings.vault_root)
        if manifest is None:
            raise ConfigurationError("Workspace 缺少 .campfire.yaml")
        manifest.projects = [
            ManifestProject.model_validate(
                project.model_dump(exclude={"workspace_id", "local_path"})
            )
            for project in self._workspaces.list_projects(self._settings.workspace_id)
        ]
        self._manifests.save(self._settings.vault_root, manifest)

    @staticmethod
    def _result(
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
        )
