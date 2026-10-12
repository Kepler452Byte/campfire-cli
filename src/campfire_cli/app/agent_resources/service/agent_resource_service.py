from __future__ import annotations

import json
import re
from pathlib import Path

from campfire_cli.app.agent_resources.repository.agent_resource_repository import (
    AgentResourceRepository,
)
from campfire_cli.app.agent_resources.schema.agent_resource_schema import (
    Change,
    OwnedFile,
    Registry,
    SkillInfo,
    SkillResult,
    resource_digest,
)
from campfire_cli.common.exceptions import GovernanceBlockedError
from campfire_cli.common.package_version import installed_version
from campfire_cli.config.defaults import config_section
from campfire_cli.config.settings import AgentResourceSettings

NAME_RE = re.compile(r"^name:\s*[\"']?([^\n\"']+)", re.MULTILINE)
DESCRIPTION_RE = re.compile(r"^description:\s*[\"']?([^\n\"']+)", re.MULTILINE)


class AgentResourceService:
    def __init__(
        self, settings: AgentResourceSettings, repository: AgentResourceRepository
    ) -> None:
        self._settings = settings
        self._repository = repository
        self.repository = repository
        self.state_root = settings.state_root
        self.registry_path = repository.registry_path
        self.distribution = "campfire-cli"

    def list(self) -> SkillResult:
        return SkillResult(status="ok", skills=self._skills())

    def show(self, name: str, source: str = "ssot") -> SkillResult:
        root = self._source_root() if source == "ssot" else self._target_roots()[0]
        path = root / name / "SKILL.md"
        if not path.is_file():
            return SkillResult(
                status="not-found", issues=[{"code": "skill-missing", "path": str(path)}]
            )
        info = (
            next(item for item in self._skills() if item.name == name)
            if source == "ssot"
            else self._parse_skill(path, root)
        )
        return SkillResult(status="ok", skills=[info], content=self._repository.read(path))

    def resolve(self, path: str) -> SkillResult:
        names = ["campfire-workspace-maintenance"]
        normalized = path.replace("\\", "/")
        if normalized.startswith("_收件箱/"):
            names.append("campfire-inbox-triage")
        elif "工作周报/" in normalized or Path(normalized).name.startswith("周报-"):
            names.append("campfire-weekly-report-writing")
        available = {item.name: item for item in self._skills()}
        return SkillResult(
            status="ok", skills=[available[name] for name in names if name in available]
        )

    def check(self) -> SkillResult:
        issues: list[dict[str, str]] = []
        configured = set(self._managed_names())
        source = {item.name: item for item in self._skills()}
        for name in sorted(configured - source.keys()):
            issues.append({"code": "ssot-skill-missing", "path": name})
        for name, info in source.items():
            if name != Path(info.path).parent.name:
                issues.append({"code": "skill-name-mismatch", "path": info.path})
            if not info.description:
                issues.append({"code": "skill-description-missing", "path": info.path})
            if name in configured and info.status != "current":
                issues.append({"code": "managed-skill-not-current", "path": info.path})
        return SkillResult(
            status="ok" if not issues else "needs-review",
            skills=list(source.values()),
            issues=issues,
        )

    def _skills(self) -> list[SkillInfo]:
        root = self._source_root()
        targets = self._target_roots()
        result: list[SkillInfo] = []
        for path in sorted(root.glob("*/SKILL.md")):
            info = self._parse_skill(path, root)
            installed = [target / info.name / "SKILL.md" for target in targets]
            info.status = (
                "current"
                if all(
                    item.is_file() and self._repository.read(item) == self._repository.read(path)
                    for item in installed
                )
                else "missing-or-stale"
            )
            result.append(info)
        return result

    def _parse_skill(self, path: Path, root: Path) -> SkillInfo:
        content = self._repository.read(path)
        name = NAME_RE.search(content)
        description = DESCRIPTION_RE.search(content)
        return SkillInfo(
            name=name.group(1).strip() if name else path.parent.name,
            description=description.group(1).strip() if description else "",
            path=path.relative_to(root).as_posix(),
        )

    def _source_root(self) -> Path:
        return self._repository.source_root()

    def _target_roots(self) -> list[Path]:
        return self._settings.targets

    def _managed_names(self) -> list[str]:
        configured = list(self._settings.managed_skills)
        packaged = config_section("skills").get("managed_skills", [])
        names = list(dict.fromkeys([*packaged, *configured]))
        if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name) for name in names):
            raise GovernanceBlockedError("Invalid managed Skill name", code="unsafe-path")
        return names

    def _markers(self) -> tuple[bytes, bytes]:
        return (
            b"<!-- campfire:agent-hints:start -->",
            b"<!-- campfire:agent-hints:end -->",
        )

    def _block(self, current: bytes) -> tuple[int, int] | None:
        start, end = self._markers()
        counts = current.count(start), current.count(end)
        if counts == (0, 0):
            return None
        if counts != (1, 1) or current.index(start) >= current.index(end):
            raise GovernanceBlockedError(
                "Hint markers are duplicate, incomplete or out of order", code="invalid-markers"
            )
        return current.index(start), current.index(end) + len(end)

    def plan(
        self, include_hints: bool = True
    ) -> tuple[list[Change], Registry, list[dict[str, str]], str, list[dict[str, str]]]:
        raw = self.repository.read_bytes(self.registry_path)
        registry = (
            Registry.load(raw, self.distribution)
            if raw is not None
            else Registry(self.distribution, [], [], [])
        )
        # Ownership may only refer to registered, absolute targets.
        for registered_file in registry.files:
            registered_target = self.repository.resolve(Path(registered_file.path))
            valid = (
                str(registered_target) in registry.hints
                if registered_file.kind == "hint"
                else any(
                    registered_target.is_relative_to(self.repository.resolve(Path(root)))
                    for root in registry.skills
                )
            )
            if not valid or str(registered_target) != registered_file.path:
                raise GovernanceBlockedError(
                    "Registry contains a registered_target outside registered locations",
                    code="invalid-registry",
                )
        skills = list(registry.skills)
        hints = list(registry.hints)
        for supplied, targets in [(path, skills) for path in self._target_roots()] + (
            [(path, hints) for path in self._settings.hints] if include_hints else []
        ):
            location = str(self.repository.resolve(supplied))
            if location not in targets:
                targets.append(location)
        for location in [*skills, *hints]:
            if self.repository.resolve(Path(location)).is_relative_to(self.state_root):
                raise GovernanceBlockedError(
                    "Agent targets must be outside internal CLI state", code="unsafe-path"
                )
        old = {item.path: item for item in registry.files if include_hints or item.kind != "hint"}
        desired: dict[str, tuple[bytes, str]] = {}
        for root in skills:
            for relative, asset_content in self.repository.assets(self._managed_names()).items():
                desired[str(self.repository.resolve(Path(root) / relative))] = (
                    asset_content,
                    "skill",
                )
        start, end = self._markers()
        hint = self.repository.hint()
        if hint and include_hints:
            for path in hints:
                if path in desired:
                    raise GovernanceBlockedError(
                        "Skill and hint destinations overlap", code="unsafe-path"
                    )
                desired[path] = (start + b"\n" + hint.rstrip(b"\r\n") + b"\n" + end, "hint")
        changes: list[Change] = []
        owned: list[OwnedFile] = [
            item for item in registry.files if not include_hints and item.kind == "hint"
        ]
        adopted: list[dict[str, str]] = []
        conflicts: list[dict[str, str]] = []
        observed: dict[str, str] = {}
        for path in sorted(set(desired) | set(old)):
            target = self.repository.resolve(Path(path))
            current = self.repository.read_bytes(target)
            observed[path] = resource_digest(current)
            previous = old.get(path)
            item = desired.get(path)
            kind = item[1] if item else old[path].kind
            block = self._block(current or b"") if kind == "hint" else None
            managed = (
                (current[block[0] : block[1]] if current is not None and block else None)
                if kind == "hint"
                else current
            )
            content = item[0] if item else None
            # Registered resources follow the package; only foreign targets conflict.
            legacy = (
                previous is None
                and managed is not None
                and (
                    (kind == "hint" and block is not None)
                    or (kind == "skill" and self._legacy_skill(target, skills))
                )
            )
            if legacy:
                adopted.append({"path": path, "kind": kind})
            if previous is None and not legacy and managed is not None and managed != content:
                conflicts.append({"path": path, "code": "unmanaged-target"})
                continue
            if item:
                owned.append(OwnedFile(path, kind))
            updated = content
            if kind == "hint":
                if block:
                    updated = (
                        (current or b"")[: block[0]]
                        + (content or b"")
                        + (current or b"")[block[1] :]
                    )
                elif content:
                    separator = (
                        b""
                        if not current or current.endswith(b"\n\n")
                        else (b"\n" if current.endswith(b"\n") else b"\n\n")
                    )
                    updated = (current or b"") + separator + content + b"\n"
                else:
                    updated = current
            if updated != current:
                changes.append(
                    Change(
                        target,
                        resource_digest(current),
                        updated,
                        "delete"
                        if updated is None
                        else ("update" if current is not None else "create"),
                    )
                )
        new = Registry(
            self.distribution,
            sorted(skills),
            sorted(hints),
            sorted(owned, key=lambda item: item.path),
        )
        encoded = new.encode()
        if raw != encoded and (skills or hints or raw is not None):
            changes.append(Change(self.registry_path, resource_digest(raw), encoded, "register"))
        plan_data = {
            "package": self.distribution,
            "version": installed_version(),
            "registry_hash": resource_digest(raw),
            "observed": observed,
            "operations": [item.describe() for item in changes],
            "conflicts": conflicts,
        }
        plan_hash = resource_digest(json.dumps(plan_data, sort_keys=True).encode())
        return changes, new, conflicts, plan_hash, adopted

    def _legacy_skill(self, target: Path, roots: list[str]) -> bool:
        for root in roots:
            relative = target.relative_to(root) if target.is_relative_to(root) else None
            if (
                relative is None
                or len(relative.parts) < 2
                or relative.parts[0] not in self._managed_names()
            ):
                continue
            anchor = self.repository.resolve(Path(root) / relative.parts[0] / "SKILL.md")
            content = self.repository.read_bytes(anchor)
            if content is not None:
                match = NAME_RE.search(content.decode("utf-8", errors="replace"))
                if match and match.group(1).strip() == relative.parts[0]:
                    return True
        return False

    def sync(self, dry_run: bool = False) -> SkillResult:
        return SkillResult(**self.align(dry_run, include_hints=False)["skills"])

    def align(self, dry_run: bool = False, *, include_hints: bool = True) -> dict:
        changes, _registry, conflicts, signature, adopted = self.plan(include_hints)
        operations = [change.describe() for change in changes]
        result = {
            "status": "dry-run" if dry_run else "synced",
            "operations": operations,
            "issues": conflicts,
            "adopted": adopted,
            "completed_operations": [],
            "preserved_files": [
                str(path)
                for root in _registry.skills
                for name in self._managed_names()
                for path in sorted((Path(root) / name).rglob("*"))
                if path.is_file()
                and str(path) not in {item.path for item in _registry.files}
                and str(path) not in {str(change.path) for change in changes}
            ],
        }
        changed = {str(change.path): change for change in changes}
        hints = []
        if include_hints:
            for path in _registry.hints:
                current = self.repository.read_bytes(Path(path))
                action = "kept"
                if path in changed:
                    action = (
                        "created"
                        if current is None
                        else "updated"
                        if self._block(current)
                        else "appended"
                    )
                hints.append({"path": path, "action": action})
        if conflicts:
            result["status"] = "blocked"
            return {"skills": result, "agent_hints": hints}
        if not dry_run and changes:
            try:
                with self.repository.lock([change.path for change in changes]):
                    fresh = self.plan(include_hints)
                    if fresh[3] != signature:
                        raise GovernanceBlockedError(
                            "Resources changed during synchronization", code="concurrent-change"
                        )
                    for change in changes:
                        if (
                            resource_digest(self.repository.read_bytes(change.path))
                            != change.before
                        ):
                            raise GovernanceBlockedError(
                                "Target changed during synchronization",
                                code="concurrent-change",
                                path=str(change.path),
                            )
                        if change.content is None:
                            self.repository.remove(change.path)
                        else:
                            self.repository.write(change.path, change.content)
                        result["completed_operations"].append(change.describe())
            except (OSError, GovernanceBlockedError) as exc:
                result["status"] = "blocked"
                result["issues"].append(
                    {
                        "code": exc.code or "resource-write-failed",
                        "path": str(getattr(exc, "filename", "") or self.registry_path),
                        "message": str(exc),
                    }
                    if isinstance(exc, GovernanceBlockedError)
                    else {
                        "code": "resource-write-failed",
                        "path": str(exc.filename or self.registry_path),
                        "message": str(exc),
                    }
                )
        return {"skills": result, "agent_hints": hints}
