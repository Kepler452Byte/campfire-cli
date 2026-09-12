from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path, PurePosixPath

from campfire_cli.app.workspace.schema.workspace_schema import (
    Domain,
    DomainCheckResult,
    DomainCreateResult,
    DomainListResult,
    Space,
    SpaceCheckResult,
    SpaceCreateResult,
    SpaceListResult,
)
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem import atomic_write, workspace_write_lock
from campfire_cli.config.defaults import builtin_config

SPACE_MARKER = "_空间.md"
DOMAIN_MARKER = "_领域.md"
ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")


def reserved_directories() -> set[str]:
    return set(builtin_config("workspace-template.json")["reserved_directories"])


def parse_marker(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2).strip().strip('"').strip("'")
    return values


class SpaceService:
    def __init__(self, workspace_root: Path, lock_root: Path) -> None:
        self.root = workspace_root.resolve()
        self.lock_root = lock_root

    def discover(self) -> tuple[list[Space], list[dict[str, str]]]:
        spaces: list[Space] = []
        issues: list[dict[str, str]] = []
        seen: set[str] = set()
        for marker in sorted(self.root.glob(f"*/{SPACE_MARKER}")):
            meta = parse_marker(marker)
            relative = marker.relative_to(self.root).as_posix()
            missing = [
                key for key in ("name", "space_id", "space_type", "status") if not meta.get(key)
            ]
            for field in missing:
                issues.append({"code": "space-field-missing", "path": relative, "detail": field})
            space_id = meta.get("space_id", "")
            if space_id in seen:
                issues.append({"code": "duplicate-space-id", "path": relative, "detail": space_id})
            seen.add(space_id)
            spaces.append(
                Space(
                    id=space_id,
                    name=meta.get("name", marker.parent.name),
                    path=marker.parent.relative_to(self.root).as_posix(),
                    type=meta.get("space_type", ""),
                    status=meta.get("status", "active"),
                )
            )
        return spaces, issues

    def list(self) -> SpaceListResult:
        spaces, _ = self.discover()
        return SpaceListResult(spaces=spaces)

    def show(self, space_id: str) -> Space:
        matches = [item for item in self.discover()[0] if item.id == space_id]
        if len(matches) != 1:
            raise ConfigurationError(f"Space 不存在或不唯一：{space_id}")
        return matches[0]

    def check(self) -> SpaceCheckResult:
        spaces, issues = self.discover()
        return SpaceCheckResult(
            status="ok" if not issues else "issues-found", spaces=spaces, issues=issues
        )

    def create(
        self, space_id: str, name: str, path: str, space_type: str, confirm: bool = False
    ) -> SpaceCreateResult:
        return self._define(space_id, name, path, space_type, confirm, adopt=False)

    def adopt(
        self, space_id: str, name: str, path: str, space_type: str, confirm: bool = False
    ) -> SpaceCreateResult:
        """Add a Space declaration to an existing root directory without moving content."""
        return self._define(space_id, name, path, space_type, confirm, adopt=True)

    def _define(
        self,
        space_id: str,
        name: str,
        path: str,
        space_type: str,
        confirm: bool,
        *,
        adopt: bool,
    ) -> SpaceCreateResult:
        if not ID_RE.fullmatch(space_id):
            raise ConfigurationError("Space id 只能使用小写字母、数字和连字符")
        relative = PurePosixPath(path)
        if (
            relative.is_absolute()
            or len(relative.parts) != 1
            or relative.name in reserved_directories()
        ):
            raise ConfigurationError("Space path 必须是 Workspace 根下的单层非保留目录")
        target = self.root / relative
        space = Space(
            id=space_id,
            name=name.strip(),
            path=relative.as_posix(),
            type=space_type,
            status="active",
        )
        if not space.name or not space.type:
            raise ConfigurationError("Space name 和 type 不能为空")
        existing = self.discover()[0]
        if any(item.id == space_id or item.path == relative.as_posix() for item in existing):
            raise ConfigurationError("Space id 或已声明路径存在")
        if adopt:
            if not target.is_dir():
                raise ConfigurationError("adopt 只接入已存在的目录")
            if (target / SPACE_MARKER).exists():
                raise ConfigurationError("目录已经包含 Space 声明")
        elif target.exists():
            raise ConfigurationError("Space 目标路径已存在；请使用 space adopt 接入")
        operations = [] if adopt else [{"action": "create-directory", "path": space.path}]
        operations.append({"action": "create", "path": f"{space.path}/{SPACE_MARKER}"})
        if confirm:
            with workspace_write_lock(self.lock_root):
                marker = target / SPACE_MARKER
                if adopt and (not target.is_dir() or marker.exists()):
                    raise ConfigurationError("接入目录在确认后发生变化，请重新预览")
                if not adopt and target.exists():
                    raise ConfigurationError("Space 路径在确认后发生变化，请重新预览")
                target.mkdir(parents=True, exist_ok=adopt)
                atomic_write(marker, self.render_marker(space))
        return SpaceCreateResult(
            status=("adopted" if adopt else "created") if confirm else "planned",
            space=space,
            operations=operations,
            write_performed=confirm,
        )

    @staticmethod
    def render_marker(space: Space) -> str:
        return "".join(
            [
                "---\n",
                f"name: {json.dumps(space.name, ensure_ascii=False)}\n",
                f"space_id: {space.id}\nspace_type: {space.type}\n",
                f"status: {space.status}\n---\n\n",
                f"# {space.name}空间\n\n",
                "用于组织同类领域；具体内容归属由下级 `_领域.md` 声明。\n",
            ]
        )


class DomainService:
    def __init__(self, workspace_root: Path, lock_root: Path) -> None:
        self.root = workspace_root.resolve()
        self.lock_root = lock_root
        self.spaces = SpaceService(workspace_root, lock_root)

    def discover(self) -> tuple[list[Domain], list[dict[str, str]]]:
        spaces, issues = self.spaces.discover()
        domains: list[Domain] = []
        seen: set[str] = set()
        for space in spaces:
            space_root = self.root / space.path
            for directory in sorted([space_root, *space_root.rglob("*")]):
                if not directory.is_dir() or directory == space_root:
                    continue
                parts = directory.relative_to(space_root).parts
                if any(part in reserved_directories() or part.startswith(".") for part in parts):
                    continue
                direct_notes = [
                    item for item in directory.glob("*.md") if item.name != DOMAIN_MARKER
                ]
                child_domain = any(
                    (child / DOMAIN_MARKER).is_file()
                    for child in directory.iterdir()
                    if child.is_dir()
                )
                if not (directory / DOMAIN_MARKER).is_file() and (direct_notes or child_domain):
                    issues.append(
                        {
                            "code": "undeclared-domain-directory",
                            "path": directory.relative_to(self.root).as_posix(),
                        }
                    )
            for marker in sorted(space_root.rglob(DOMAIN_MARKER)):
                if any(
                    part in reserved_directories()
                    for part in marker.relative_to(space_root).parts[:-1]
                ):
                    continue
                meta = parse_marker(marker)
                relative = marker.relative_to(self.root).as_posix()
                required = ("name", "domain_id", "domain_type", "governance", "moc", "status")
                for field in required:
                    if not meta.get(field):
                        issues.append(
                            {"code": "domain-field-missing", "path": relative, "detail": field}
                        )
                domain_id = meta.get("domain_id", "")
                if domain_id in seen:
                    issues.append(
                        {"code": "duplicate-domain-id", "path": relative, "detail": domain_id}
                    )
                seen.add(domain_id)
                domains.append(
                    Domain(
                        id=domain_id,
                        name=meta.get("name", marker.parent.name),
                        path=marker.parent,
                        space_id=space.id,
                        type=meta.get("domain_type", ""),
                        governance=meta.get("governance", ""),
                        moc=meta.get("moc", "").replace("[[", "").replace("]]", ""),
                        parent_domain=meta.get("parent_domain") or None,
                        project_id=meta.get("project_id") or None,
                        status=meta.get("status", "active"),
                    )
                )
        by_id = {item.id: item for item in domains if item.id}
        for item in domains:
            if item.parent_domain:
                parent = by_id.get(item.parent_domain)
                if not parent:
                    issues.append(
                        {
                            "code": "parent-domain-missing",
                            "path": item.path,
                            "detail": item.parent_domain,
                        }
                    )
                elif parent.space_id != item.space_id or parent.path not in item.path.parents:
                    issues.append(
                        {
                            "code": "domain-parent-path-mismatch",
                            "path": item.path.relative_to(self.root).as_posix(),
                            "detail": item.parent_domain,
                        }
                    )
                elif item.governance != parent.governance:
                    issues.append(
                        {
                            "code": "domain-governance-mismatch",
                            "path": item.path.relative_to(self.root).as_posix(),
                            "detail": parent.governance,
                        }
                    )
            moc = item.path / f"{item.moc}.md"
            if item.moc and not moc.is_file():
                issues.append(
                    {"code": "moc-missing", "path": moc.relative_to(self.root).as_posix()}
                )
        return domains, issues

    def list(self, space_id: str | None = None) -> DomainListResult:
        domains = self.discover()[0]
        return DomainListResult(
            domains=[
                self._external(item)
                for item in domains
                if not space_id or item.space_id == space_id
            ]
        )

    def show(self, domain_id: str) -> Domain:
        matches = [item for item in self.discover()[0] if item.id == domain_id]
        if len(matches) != 1:
            raise ConfigurationError(f"Domain 不存在或不唯一：{domain_id}")
        return self._external(matches[0])

    def check(self) -> DomainCheckResult:
        domains, issues = self.discover()
        return DomainCheckResult(
            status="ok" if not issues else "issues-found",
            domains=[self._external(item) for item in domains],
            issues=issues,
        )

    def create(
        self,
        *,
        domain_id: str,
        name: str,
        path: str,
        space_id: str,
        domain_type: str,
        governance: str,
        parent_domain: str | None = None,
        project_id: str | None = None,
        confirm: bool = False,
    ) -> DomainCreateResult:
        return self._define(
            domain_id=domain_id,
            name=name,
            path=path,
            space_id=space_id,
            domain_type=domain_type,
            governance=governance,
            parent_domain=parent_domain,
            project_id=project_id,
            confirm=confirm,
            adopt=False,
        )

    def adopt(
        self,
        *,
        domain_id: str,
        name: str,
        path: str,
        space_id: str,
        domain_type: str,
        governance: str,
        parent_domain: str | None = None,
        project_id: str | None = None,
        confirm: bool = False,
    ) -> DomainCreateResult:
        """Add a Domain declaration to an existing directory without moving its content."""
        return self._define(
            domain_id=domain_id,
            name=name,
            path=path,
            space_id=space_id,
            domain_type=domain_type,
            governance=governance,
            parent_domain=parent_domain,
            project_id=project_id,
            confirm=confirm,
            adopt=True,
        )

    def _define(
        self,
        *,
        domain_id: str,
        name: str,
        path: str,
        space_id: str,
        domain_type: str,
        governance: str,
        parent_domain: str | None,
        project_id: str | None,
        confirm: bool,
        adopt: bool,
    ) -> DomainCreateResult:
        if not ID_RE.fullmatch(domain_id):
            raise ConfigurationError("Domain id 只能使用小写字母、数字和连字符")
        space = self.spaces.show(space_id)
        target = (self.root / PurePosixPath(path)).resolve()
        space_root = (self.root / space.path).resolve()
        if (
            target == space_root
            or space_root not in target.parents
            or any(part in reserved_directories() for part in target.relative_to(space_root).parts)
        ):
            raise ConfigurationError("Domain path 必须位于指定 Space 下且不能使用保留目录")
        existing = self.discover()[0]
        if any(item.id == domain_id or item.path == target for item in existing):
            raise ConfigurationError("Domain id 或已声明路径存在")
        if adopt:
            if not target.is_dir():
                raise ConfigurationError("adopt 只接入已存在的目录")
            if (target / DOMAIN_MARKER).exists():
                raise ConfigurationError("目录已经包含领域声明")
        elif target.exists():
            raise ConfigurationError("Domain 目标路径已存在；请使用 domain adopt 接入")
        if parent_domain:
            parent = next((item for item in existing if item.id == parent_domain), None)
            if (
                not parent
                or parent.space_id != space_id
                or (self.root / parent.path) not in target.parents
            ):
                raise ConfigurationError("父 Domain 不存在、跨 Space 或与目标路径不匹配")
            if governance != parent.governance:
                raise ConfigurationError("子 Domain 必须继承父 Domain 的 governance")
            project_id = parent.project_id or project_id
        if governance == "project-docs" and not project_id:
            raise ConfigurationError("project-docs Domain 必须绑定 Project id")
        moc = f"_总览/MOC-{name}总览"
        domain = Domain(
            id=domain_id,
            name=name.strip(),
            path=target,
            space_id=space_id,
            type=domain_type,
            governance=governance,
            moc=moc,
            parent_domain=parent_domain,
            project_id=project_id,
        )
        relative_path = target.relative_to(self.root).as_posix()
        operations = [] if adopt else [{"action": "create-directory", "path": relative_path}]
        operations.extend(
            [
                {"action": "create", "path": f"{relative_path}/{DOMAIN_MARKER}"},
                {"action": "create", "path": f"{relative_path}/{moc}.md"},
            ]
        )
        if confirm:
            with workspace_write_lock(self.lock_root):
                marker = target / DOMAIN_MARKER
                moc_path = target / f"{moc}.md"
                if adopt and (not target.is_dir() or marker.exists() or moc_path.exists()):
                    raise ConfigurationError("接入目录在确认后发生变化，请重新预览")
                if not adopt and target.exists():
                    raise ConfigurationError("Domain 路径在确认后发生变化，请重新预览")
                (target / "_总览").mkdir(parents=True, exist_ok=adopt)
                atomic_write(target / DOMAIN_MARKER, self.render_marker(domain))
                atomic_write(moc_path, self.render_moc(domain))
        return DomainCreateResult(
            status=("adopted" if adopt else "created") if confirm else "planned",
            domain=self._external(domain),
            operations=operations,
            write_performed=confirm,
        )

    def _external(self, domain: Domain) -> Domain:
        return domain.model_copy(update={"path": domain.path.relative_to(self.root)})

    @staticmethod
    def render_marker(domain: Domain) -> str:
        optional = f"parent_domain: {domain.parent_domain}\n" if domain.parent_domain else ""
        optional += f"project_id: {domain.project_id}\n" if domain.project_id else ""
        return "".join(
            [
                "---\n",
                f"name: {json.dumps(domain.name, ensure_ascii=False)}\n",
                f"domain_id: {domain.id}\ndomain_type: {domain.type}\n",
                f"governance: {domain.governance}\n",
                f'moc: "[[{domain.moc}]]"\n',
                optional,
                "status: active\n---\n\n",
                f"# {domain.name}\n\n",
                "## 领域定位\n\n## 收录范围\n\n## 不收录\n\n",
                "## 与相邻领域的边界\n",
            ]
        )

    @staticmethod
    def render_moc(domain: Domain) -> str:
        today = date.today().isoformat()
        project_fields = ""
        if domain.governance == "project-docs":
            project_fields = (
                f"project: {domain.project_id}\ndomain: {domain.id}\nlifecycle: maintained\n"
            )
        return "".join(
            [
                "---\n",
                f"name: {json.dumps(domain.name + '总览', ensure_ascii=False)}\n",
                f"description: {json.dumps(domain.name + '领域导航入口。', ensure_ascii=False)}\n",
                "type: moc\n",
                project_fields,
                "status: current\n",
                f"created: {today}\nupdated: {today}\n",
                "tags: []\n---\n\n",
                f"# {domain.name}总览\n\n",
                "<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->\n\n",
                "<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->\n",
            ]
        )
