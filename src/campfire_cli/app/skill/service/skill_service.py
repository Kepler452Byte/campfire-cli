from __future__ import annotations

import hashlib
import re
from pathlib import Path

from campfire_cli.app.skill.repository.skill_repository import SkillRepository
from campfire_cli.app.skill.schema.skill_schema import SkillInfo, SkillResult
from campfire_cli.common.filesystem import vault_write_lock
from campfire_cli.common.governance import enrich_issue
from campfire_cli.config.settings import WorkspaceSettings

NAME_RE = re.compile(r"^name:\s*[\"']?([^\n\"']+)", re.MULTILINE)
DESCRIPTION_RE = re.compile(r"^description:\s*[\"']?([^\n\"']+)", re.MULTILINE)


class SkillService:
    def __init__(self, settings: WorkspaceSettings, repository: SkillRepository) -> None:
        self._settings = settings
        self._repository = repository

    def list(self) -> SkillResult:
        return SkillResult(status="ok", skills=self._skills())

    def show(self, name: str, source: str = "ssot") -> SkillResult:
        root = self._source_root() if source == "ssot" else self._target_roots()[0]
        path = root / name / "SKILL.md"
        if not path.is_file():
            return SkillResult(
                status="not-found", issues=[{"code": "skill-missing", "path": str(path)}]
            )
        info = self._parse_skill(path, root)
        return SkillResult(status="ok", skills=[info], content=self._repository.read(path))

    def resolve(self, path: str) -> SkillResult:
        names = ["campfire-workspace-governance"]
        normalized = path.replace("\\", "/")
        if normalized.startswith("_收件箱/"):
            names.append("campfire-inbox-triage")
        elif normalized.startswith("mynote/"):
            names.append("mynote-knowledge-governance")
        elif normalized.startswith("mywork/"):
            if "【" in normalized:
                names.append("mywork-project-docs-governance")
            if "/任务/" in normalized or Path(normalized).name.startswith("任务-"):
                names.append("mywork-task-governance")
            if "工作周报/" in normalized:
                names.append("mywork-weekly-report-writing")
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

    def sync(self, dry_run: bool = False) -> SkillResult:
        operations: list[dict[str, str]] = []
        writes: list[tuple[Path, str, str | None]] = []
        source_root = self._source_root()
        for target_root in self._target_roots():
            for name in self._managed_names():
                source_dir = source_root / name
                if not (source_dir / "SKILL.md").is_file():
                    continue
                for source in sorted(path for path in source_dir.rglob("*") if path.is_file()):
                    relative = source.relative_to(source_root)
                    target = target_root / relative
                    content = self._repository.read(source)
                    current = self._repository.read(target) if target.is_file() else None
                    if current == content:
                        continue
                    operations.append(
                        {
                            "action": "update" if target.exists() else "create",
                            "path": str(target),
                            "sha256": hashlib.sha256(content.encode()).hexdigest(),
                        }
                    )
                    expected = (
                        hashlib.sha256(current.encode()).hexdigest()
                        if current is not None
                        else None
                    )
                    writes.append((target, content, expected))
        if not dry_run and writes:
            with vault_write_lock(self._settings.state_root):
                changed = [
                    str(path)
                    for path, _content, expected in writes
                    if self._current_hash(path) != expected
                ]
                if changed:
                    return SkillResult(
                        status="blocked",
                        issues=[
                            enrich_issue({"code": "concurrent-change", "path": path})
                            for path in changed
                        ],
                    )
                for target, content, _expected in writes:
                    self._repository.write(target, content)
        return SkillResult(status="dry-run" if dry_run else "synced", operations=operations)

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
        return self._settings.skill_targets()

    @staticmethod
    def _current_hash(path: Path) -> str | None:
        if not path.is_file():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _managed_names(self) -> list[str]:
        return list(self._settings.skills.get("managed_skills", []))
