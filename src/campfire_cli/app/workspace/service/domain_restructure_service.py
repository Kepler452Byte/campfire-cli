from __future__ import annotations

import re
from pathlib import Path

from campfire_cli.app.base.schema.operation_schema import maintenance_sync_follow_up
from campfire_cli.app.document.service.document_scanner import iter_documents
from campfire_cli.app.workspace.repository.manifest_repository import (
    WorkspaceManifestRepository,
)
from campfire_cli.app.workspace.schema.restructure_schema import (
    DomainDeleteResult,
    DomainMergeResult,
    DomainRestructureResult,
)
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
from campfire_cli.common.documents.frontmatter_format import render_patch
from campfire_cli.common.documents.markdown import parse_document, render_document
from campfire_cli.common.documents.related_docs import rewrite_related_docs
from campfire_cli.common.exceptions import AppError, ConfigurationError, GovernanceBlockedError
from campfire_cli.common.filesystem import (
    FileChangeExecutor,
    FileChangeSet,
    FileWrite,
    PathMove,
    safe_path,
)
from campfire_cli.common.filesystem.plan import plan_digest
from campfire_cli.common.hashing import file_sha256, text_sha256
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
        name: str | None = None,
        *,
        folder_name: str | None = None,
        expected_plan: str | None = None,
        confirm: bool = False,
    ) -> DomainRestructureResult:
        domain = self._domain(domain_id)
        if name is None and folder_name is None:
            raise ConfigurationError("请提供 --name 或 --folder-name", code="rename-input-missing")
        new_name = domain.name if name is None else name.strip()
        if not new_name:
            raise ConfigurationError("Domain name 不能为空")
        target = domain.path
        if folder_name is not None:
            if (
                not folder_name.strip()
                or folder_name in {".", ".."}
                or any(char in folder_name for char in '/\\<>:"|?*')
                or folder_name.endswith((" ", "."))
                or any(ord(char) < 32 for char in folder_name)
                or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?", folder_name)
            ):
                raise ConfigurationError(
                    "--folder-name 必须是单个合法目录名", code="folder-name-invalid"
                )
            target = domain.path.with_name(folder_name)
            if folder_name != domain.path.name and target.exists() and target.samefile(domain.path):
                raise ConfigurationError(
                    "当前文件系统不支持直接进行仅大小写不同的目录改名",
                    code="case-only-rename-unsupported",
                    hint="先用 domain rename 改为未占用的临时目录名，再改为目标名；每步先预览。",
                )
            target = self._validate_target(
                target.relative_to(self._settings.vault_root).as_posix(), domain
            )
        return self._change(
            domain,
            target=target,
            name=new_name,
            new_id=domain.id,
            parent_domain=domain.parent_domain,
            confirm=confirm,
            expected_plan=expected_plan,
            protect_plan=folder_name is not None,
        )

    def move(
        self,
        domain_id: str,
        target_id: str,
        *,
        confirm: bool = False,
    ) -> DomainRestructureResult:
        domain = self._domain(domain_id)
        domains = [item for item in self._domains.discover()[0] if item.id == target_id]
        spaces = [item for item in self._domains.spaces.discover()[0] if item.id == target_id]
        if len(domains) + len(spaces) != 1:
            raise ConfigurationError(f"目标 Space 或 Domain 不存在或不唯一：{target_id}")
        if domains:
            parent = domains[0]
            if parent.id == domain.id or domain.path in parent.path.parents:
                raise ConfigurationError("Domain 不能移动到自身或自己的子 Domain")
            if parent.governance != domain.governance:
                raise ConfigurationError("移动后的子 Domain 必须继承父 Domain governance")
            is_project_root = any(
                project.document_domain_id == domain.id
                for project in self._workspaces.list_projects(self._settings.workspace_id)
            )
            if parent.project_id != domain.project_id and not (
                is_project_root and parent.project_id is None
            ):
                raise ConfigurationError("移动后的 Domain 与目标父 Domain Project 不一致")
            target = parent.path / domain.path.name
            parent_domain = parent.id
        else:
            target = self._settings.vault_root / spaces[0].path / domain.path.name
            parent_domain = None
        target = self._validate_target(
            target.relative_to(self._settings.vault_root).as_posix(), domain
        )
        return self._change(
            domain,
            target=target,
            name=domain.name,
            new_id=domain.id,
            parent_domain=parent_domain,
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
            confirm=confirm,
        )

    def merge(
        self, source_domain: str, target_domain: str, *, confirm: bool = False
    ) -> DomainMergeResult:
        source = self._domain(source_domain)
        target = self._domain(target_domain)
        issues = self._merge_issues(source, target)
        projects = [
            project
            for project in self._workspaces.list_projects(self._settings.workspace_id)
            if project.document_domain_id == source.id
        ]
        updated_projects = [
            project.model_copy(update={"document_domain_id": target.id}) for project in projects
        ]
        files = sorted(path for path in source.path.rglob("*") if path.is_file())
        source_moc = source.path / f"{source.moc}.md"
        retained = [path for path in files if path not in {source.path / DOMAIN_MARKER, source_moc}]
        targets = {path: target.path / path.relative_to(source.path) for path in retained}
        for source_path, target_path in targets.items():
            if target_path.exists():
                issues.append(
                    {
                        "code": "domain-merge-target-exists",
                        "path": target_path.relative_to(self._settings.vault_root).as_posix(),
                        "source": source_path.relative_to(self._settings.vault_root).as_posix(),
                    }
                )
        child_domains = [
            item
            for item in self._domains.discover()[0]
            if item.id != source.id and source.path in item.path.parents
        ]
        documents = [path for path in retained if path.suffix.lower() == ".md"]
        assets = [path for path in retained if path.suffix.lower() != ".md"]
        operations = [
            {
                "action": "move-file",
                "source": path.relative_to(self._settings.vault_root).as_posix(),
                "path": targets[path].relative_to(self._settings.vault_root).as_posix(),
            }
            for path in retained
        ]
        operations.extend(
            {
                "action": "reparent-domain",
                "source": child.id,
                "path": target.id,
            }
            for child in child_domains
            if child.parent_domain == source.id
        )
        operations.extend({"action": "update-project", "path": item.id} for item in projects)
        change_set = self._merge_change_set(
            source,
            target,
            retained,
            targets,
            updated_projects,
        )
        moved_targets = set(targets.values())
        manifest_path = self._manifests.path(self._settings.vault_root)
        reference_updates = sorted(
            write.path
            for write in change_set.writes
            if write.path not in moved_targets and write.path != manifest_path
        )
        operations.extend(
            {
                "action": "update-reference",
                "path": path.relative_to(self._settings.vault_root).as_posix(),
            }
            for path in reference_updates
        )
        operations.append(
            {
                "action": "delete-domain",
                "path": source.path.relative_to(self._settings.vault_root).as_posix(),
            }
        )
        follow_up = maintenance_sync_follow_up(
            self._settings.workspace_id,
            [
                source.path.parent.relative_to(self._settings.vault_root).as_posix(),
                target.path.relative_to(self._settings.vault_root).as_posix(),
            ],
        )
        if issues or not confirm:
            return DomainMergeResult(
                status="blocked" if issues else "planned",
                source_domain=source.id,
                target_domain=target.id,
                document_count=len(documents),
                asset_count=len(assets),
                child_domain_count=len(child_domains),
                reference_count=len(reference_updates),
                operations=operations,
                affected_projects=[item.id for item in projects],
                issues=issues,
            )
        current_source = self._domain(source.id)
        current_target = self._domain(target.id)
        if current_source.path != source.path or current_target.path != target.path:
            raise ConfigurationError("Domain 在预览后发生变化，请重新执行")
        try:
            with self._executor.transaction(change_set):
                if updated_projects:
                    self._workspaces.save_projects(updated_projects)
                if source.path.exists():
                    raise ConfigurationError("Domain 合并后源目录仍然存在")
        except Exception:
            if projects:
                self._workspaces.save_projects(projects)
            raise
        return DomainMergeResult(
            status="applied",
            source_domain=source.id,
            target_domain=target.id,
            document_count=len(documents),
            asset_count=len(assets),
            child_domain_count=len(child_domains),
            reference_count=len(reference_updates),
            operations=operations,
            affected_projects=[item.id for item in projects],
            write_performed=True,
            follow_up=follow_up,
        )

    def delete(self, domain_id: str, *, confirm: bool = False) -> DomainDeleteResult:
        domain = self._domain(domain_id)
        relative = domain.path.relative_to(self._settings.vault_root).as_posix()
        marker = domain.path / DOMAIN_MARKER
        moc = domain.path / f"{domain.moc}.md"
        files = sorted(path for path in domain.path.rglob("*") if path.is_file())
        child_domains = [
            item
            for item in self._domains.discover()[0]
            if item.id != domain.id and domain.path in item.path.parents
        ]
        projects = [
            project
            for project in self._workspaces.list_projects(self._settings.workspace_id)
            if project.document_domain_id == domain.id
        ]
        content = [path for path in files if path not in {marker, moc}]
        issues: list[dict[str, object]] = []
        if child_domains:
            issues.append(
                {
                    "code": "domain-delete-child-domains",
                    "path": relative,
                    "detail": ",".join(sorted(item.id for item in child_domains)),
                    "hint": "先使用 domain merge 或 workspace restructure 迁移子领域",
                }
            )
        if content:
            issues.append(
                {
                    "code": "domain-delete-not-empty",
                    "path": relative,
                    "detail": ",".join(
                        path.relative_to(domain.path).as_posix() for path in content
                    ),
                    "hint": "先使用 domain merge 或 workspace restructure 迁移内容",
                }
            )
        if projects:
            issues.append(
                {
                    "code": "domain-delete-project-bound",
                    "path": relative,
                    "detail": ",".join(sorted(project.id for project in projects)),
                    "hint": "先把 Project 文档中心迁移或合并到另一个 Domain",
                }
            )
        issues.extend(self._authored_declaration_issues(domain, marker, moc, "delete"))
        delete_files = [path for path in (marker, moc) if path.is_file()]
        directories = sorted(
            [domain.path, *(path for path in domain.path.rglob("*") if path.is_dir())],
            key=lambda path: len(path.parts),
            reverse=True,
        )
        operations = [
            {
                "action": "delete-file",
                "path": path.relative_to(self._settings.vault_root).as_posix(),
            }
            for path in delete_files
        ]
        operations.extend(
            {
                "action": "delete-directory",
                "path": path.relative_to(self._settings.vault_root).as_posix(),
            }
            for path in directories
        )
        follow_up = maintenance_sync_follow_up(
            self._settings.workspace_id,
            [domain.path.parent.relative_to(self._settings.vault_root).as_posix()],
        )
        if issues or not confirm:
            return DomainDeleteResult(
                status="blocked" if issues else "planned",
                domain_id=domain.id,
                path=relative,
                operations=operations,
                issues=issues,
            )
        change_set = FileChangeSet(
            deletes=tuple(delete_files),
            remove_empty_directories=tuple(directories),
            label="workspace domain delete",
            expected={path: file_sha256(path) for path in delete_files},
        )
        self._executor.execute(change_set)
        return DomainDeleteResult(
            status="applied",
            domain_id=domain.id,
            path=relative,
            operations=operations,
            write_performed=True,
            follow_up=follow_up,
        )

    def _change(
        self,
        domain: Domain,
        *,
        target: Path,
        name: str,
        new_id: str,
        parent_domain: str | None,
        confirm: bool,
        expected_plan: str | None = None,
        protect_plan: bool = False,
    ) -> DomainRestructureResult:
        old_relative = domain.path.relative_to(self._settings.vault_root).as_posix()
        new_relative = target.relative_to(self._settings.vault_root).as_posix()
        projects = [
            project
            for project in self._workspaces.list_projects(self._settings.workspace_id)
            if project.document_domain_id == domain.id and new_id != domain.id
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
        if target != domain.path and target.exists():
            raise ConfigurationError(f"目标路径已存在：{new_relative}")
        current = self._domain(domain.id)
        if current.path != domain.path or current.name != domain.name:
            raise ConfigurationError("Domain 在预览后发生变化，请重新执行")
        updated_projects = [
            project.model_copy(
                update={
                    "document_domain_id": new_id,
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
        for write in change_set.writes:
            relative = write.path.relative_to(self._settings.vault_root).as_posix()
            operations.append({"action": "update-file", "path": relative})
        digest = plan_digest(self._settings.vault_root, change_set)
        result = self._result(domain, new_id, name, new_relative, operations, projects, False)
        result.expected_plan = digest
        if not change_set.writes and not change_set.moves:
            result.status = "up-to-date"
            return result
        if not confirm:
            return result
        if protect_plan and expected_plan != digest:
            result.status = "blocked"
            result.issues = [
                {
                    "code": "plan-changed" if expected_plan else "expected-plan-required",
                    "hint": "重新预览并在确认时带回 --expected-plan。",
                }
            ]
            return result

        def verify_plan() -> None:
            current_changes = self._plan_changes(
                domain,
                target=target,
                name=name,
                new_id=new_id,
                parent_domain=parent_domain,
                updated_projects=updated_projects,
            )
            if plan_digest(self._settings.vault_root, current_changes) != digest:
                raise GovernanceBlockedError("领域内容或引用在提交前发生变化", code="plan-changed")

        try:
            with self._executor.transaction(change_set, before_write=verify_plan):
                if updated_projects:
                    self._workspaces.save_projects(updated_projects)
        except Exception as exc:
            if projects:
                self._workspaces.save_projects(projects)
            if isinstance(exc, OSError):
                raise AppError(
                    "领域写入失败，文件变更已回滚",
                    code="domain-write-failed",
                    write_performed=False,
                    hint="排除占用或权限问题后重新预览。",
                ) from exc
            raise
        result = self._result(domain, new_id, name, new_relative, operations, projects, True)
        result.expected_plan = digest
        try:
            domain_check = self._domains.check()
        except (AppError, OSError) as exc:
            result.status = "needs-review"
            result.issues = [
                {
                    "code": "domain-postcheck-failed",
                    "detail": str(exc),
                    "hint": "文件已写入，不要重复改名；排除问题后执行返回的同步与领域检查。",
                }
            ]
            return result
        affected_prefix = f"{new_relative}/"
        issues = [
            issue
            for issue in domain_check.issues
            if str(issue.get("path", "")).startswith(affected_prefix)
            or issue.get("path") == new_relative
        ]
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

    def _merge_issues(self, source: Domain, target: Domain) -> list[dict[str, object]]:
        source_relative = source.path.relative_to(self._settings.vault_root).as_posix()
        issues: list[dict[str, object]] = []
        if source.id == target.id:
            issues.append({"code": "domain-merge-same-domain", "path": source_relative})
        if source.path in target.path.parents:
            issues.append({"code": "domain-merge-target-inside-source", "path": source_relative})
        if source.governance != target.governance:
            issues.append(
                {
                    "code": "domain-merge-governance-conflict",
                    "path": source_relative,
                    "source": source.governance,
                    "target": target.governance,
                }
            )
        source_is_project_root = any(
            project.document_domain_id == source.id
            for project in self._workspaces.list_projects(self._settings.workspace_id)
        )
        if source.project_id != target.project_id and not (
            source_is_project_root and target.project_id is None
        ):
            issues.append(
                {
                    "code": "domain-merge-project-conflict",
                    "path": source_relative,
                    "source": source.project_id or "none",
                    "target": target.project_id or "none",
                }
            )
        for path in source.path.rglob("*"):
            if path.is_symlink():
                issues.append(
                    {
                        "code": "domain-merge-symlink",
                        "path": path.relative_to(self._settings.vault_root).as_posix(),
                    }
                )
        issues.extend(
            self._authored_declaration_issues(
                source,
                source.path / DOMAIN_MARKER,
                source.path / f"{source.moc}.md",
                "merge",
            )
        )
        return issues

    @staticmethod
    def _rewrite_domain_id(text: str, old: str, new: str) -> str:
        parsed = parse_document(text)
        patch = {
            key: new
            for key in ("domain", "domain_id", "parent_domain")
            if parsed.frontmatter.get(key) == old
        }
        if not patch:
            return text
        rendered, issues = render_patch(text, patch, parsed.body, list(parsed.frontmatter))
        if issues:
            raise GovernanceBlockedError("领域属性无法安全修改：" + ", ".join(issues))
        return rendered

    def _merge_change_set(
        self,
        source: Domain,
        target: Domain,
        retained: list[Path],
        targets: dict[Path, Path],
        updated_projects: list[ProjectEntry],
    ) -> FileChangeSet:
        marker = source.path / DOMAIN_MARKER
        moc = source.path / f"{source.moc}.md"
        reference_files = self._reference_files()
        originals = {path: path.read_text(encoding="utf-8") for path in reference_files}
        writes: list[FileWrite] = []
        direct_children = {
            item.path / DOMAIN_MARKER
            for item in self._domains.discover()[0]
            if item.parent_domain == source.id and source.path in item.path.parents
        }
        nested_domains = sorted(
            [
                item
                for item in self._domains.discover()[0]
                if item.id != source.id and source.path in item.path.parents
            ],
            key=lambda item: len(item.path.parts),
            reverse=True,
        )
        for path, original in originals.items():
            if path in {marker, moc}:
                continue
            mapping = {
                p.relative_to(self._settings.vault_root).as_posix(): targets.get(
                    p, target.path / p.relative_to(source.path)
                )
                .relative_to(self._settings.vault_root)
                .as_posix()
                for p in reference_files
                if source.path in p.parents
            }
            content = rewrite_related_docs(original, mapping)
            content = self._rewrite_domain_id(content, source.id, target.id)
            if path in direct_children:
                parsed = parse_document(content)
                frontmatter = dict(parsed.frontmatter)
                frontmatter["parent_domain"] = target.id
                content = render_document(frontmatter, parsed.body, list(frontmatter))
            elif path.suffix.lower() == ".md" and source.path in path.parents:
                owner = next((item for item in nested_domains if item.path in path.parents), source)
                if owner.id == source.id:
                    parsed = parse_document(content)
                    if parsed.frontmatter:
                        frontmatter = dict(parsed.frontmatter)
                        if "domain" in frontmatter:
                            frontmatter["domain"] = target.id
                            content = render_document(frontmatter, parsed.body, list(frontmatter))
            final_path = targets.get(path, path)
            if content != original or final_path != path:
                writes.append(FileWrite(final_path, content))
        moves = tuple(PathMove(path, targets[path]) for path in retained)
        directories = sorted(
            [source.path, *(path for path in source.path.rglob("*") if path.is_dir())],
            key=lambda path: len(path.parts),
            reverse=True,
        )
        expected = {path: file_sha256(path) for path in source.path.rglob("*") if path.is_file()}
        expected[marker] = file_sha256(marker)
        if moc.is_file():
            expected[moc] = file_sha256(moc)
        for final_path in targets.values():
            expected[final_path] = None
        for path in reference_files:
            if source.path not in path.parents:
                expected[path] = file_sha256(path)
        if updated_projects:
            manifest_path, manifest_content = self._manifest_update(updated_projects)
            writes.append(FileWrite(manifest_path, manifest_content))
            expected[manifest_path] = file_sha256(manifest_path)
        return FileChangeSet(
            writes=tuple(writes),
            deletes=tuple(path for path in (marker, moc) if path.is_file()),
            moves=moves,
            remove_empty_directories=tuple(directories),
            label="workspace domain merge",
            expected=expected,
        )

    def _authored_declaration_issues(
        self,
        domain: Domain,
        marker: Path,
        moc: Path,
        operation: str,
    ) -> list[dict[str, object]]:
        issues: list[dict[str, object]] = []
        relative = domain.path.relative_to(self._settings.vault_root).as_posix()
        if marker.is_file() and self._has_authored_text(marker, generated_moc=False):
            issues.append(
                {
                    "code": f"domain-{operation}-authored-marker",
                    "path": relative,
                }
            )
        if moc.is_file() and self._has_authored_text(moc, generated_moc=True):
            issues.append(
                {
                    "code": f"domain-{operation}-authored-moc",
                    "path": moc.relative_to(self._settings.vault_root).as_posix(),
                }
            )
        return issues

    @staticmethod
    def _has_authored_text(path: Path, *, generated_moc: bool) -> bool:
        body = parse_document(path.read_text(encoding="utf-8")).body
        if generated_moc:
            body = re.sub(
                r"<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->.*?"
                r"<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->",
                "",
                body,
                flags=re.DOTALL,
            )
        remaining = [
            line.strip()
            for line in body.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        return bool(remaining)

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
        originals = {path: path.read_bytes().decode("utf-8") for path in references}
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
        body = (
            re.sub(r"^# .+$", lambda _: f"# {name}", parsed.body, count=1, flags=re.MULTILINE)
            if name != domain.name
            else parsed.body
        )
        if frontmatter != parsed.frontmatter or body != parsed.body:
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
            for path, content in contents.items():
                contents[path] = self._rewrite_domain_id(content, domain.id, new_id)

        old_relative = domain.path.relative_to(self._settings.vault_root).as_posix()
        new_relative = target.relative_to(self._settings.vault_root).as_posix()
        if old_relative != new_relative:
            mapping = {
                p.relative_to(self._settings.vault_root).as_posix(): (
                    target / p.relative_to(domain.path)
                )
                .relative_to(self._settings.vault_root)
                .as_posix()
                for p in references
                if domain.path in p.parents
            }
            for path, content in contents.items():
                contents[path] = rewrite_related_docs(content, mapping)

        def final_path(path: Path) -> Path:
            if path == domain.path or domain.path in path.parents:
                return target / path.relative_to(domain.path)
            return path

        writes = [
            FileWrite(final_path(path), content)
            for path, content in contents.items()
            if content != originals[path]
        ]
        expected = {path: text_sha256(text) for path, text in originals.items()}
        manifest = self._manifests.path(self._settings.vault_root)
        expected[manifest] = file_sha256(manifest) if manifest.is_file() else None
        if target != domain.path:
            for path in domain.path.rglob("*"):
                if path.is_symlink():
                    raise GovernanceBlockedError(
                        "领域迁移不接受符号链接", code="domain-move-symlink"
                    )
                if path not in expected:
                    expected[path] = file_sha256(path) if path.is_file() else None
            expected[target] = None
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
        documents = iter_documents(self._settings.vault_root, self._settings.document_types)
        declarations = [domain.path / DOMAIN_MARKER for domain in self._domains.discover()[0]]
        return sorted(set(documents) | set(declarations))

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
            old_path=domain.path.relative_to(self._settings.vault_root).as_posix(),
            path_changed=path != domain.path.relative_to(self._settings.vault_root).as_posix(),
            operations=operations,
            affected_projects=[project.id for project in projects],
            write_performed=written,
            follow_up=(
                maintenance_sync_follow_up(
                    self._settings.workspace_id,
                    [
                        domain.path.relative_to(self._settings.vault_root).as_posix(),
                        path,
                        *(
                            Path(item["path"]).parent.as_posix()
                            for item in operations
                            if item["action"] == "update-file"
                        ),
                    ],
                )
                if written
                else []
            ),
        )
