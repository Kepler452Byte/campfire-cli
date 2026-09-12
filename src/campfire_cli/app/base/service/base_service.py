from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from campfire_cli.app.base.repository.base_repository import BaseRepository
from campfire_cli.app.base.schema.base_schema import BaseInfo, BaseResult
from campfire_cli.common.filesystem import workspace_write_lock
from campfire_cli.common.governance import enrich_issue, snapshot_changes
from campfire_cli.config.defaults import builtin_config
from campfire_cli.config.settings import WorkspaceSettings


class BaseService:
    def __init__(self, settings: WorkspaceSettings, repository: BaseRepository) -> None:
        self._settings = settings
        self._repository = repository

    def list(self) -> BaseResult:
        return BaseResult(status="ok", bases=self._bases())

    def show(self, name: str, source: str = "ssot") -> BaseResult:
        filename = name if name.endswith(".base") else f"{name}.base"
        root = self._source_root() if source == "ssot" else self._target_root()
        path = root / filename
        if not path.is_file():
            return BaseResult(
                status="not-found", issues=[{"code": "base-missing", "path": str(path)}]
            )
        return BaseResult(
            status="ok", bases=[self._info(path, root)], content=self._repository.read(path)
        )

    def check(self) -> BaseResult:
        bases = self._bases()
        configured = set(self._managed_names())
        available = {item.name for item in bases}
        issues: list[dict[str, str]] = []
        for name in sorted(configured - available):
            issues.append({"code": "ssot-base-missing", "path": name})
        for item in bases:
            if item.name in configured and item.status != "current":
                issues.append({"code": "managed-base-not-current", "path": item.path})
            try:
                payload = yaml.safe_load(self._repository.read(self._source_root() / item.path))
                if not isinstance(payload, dict) or not isinstance(payload.get("views"), list):
                    issues.append({"code": "base-views-missing", "path": item.path})
            except yaml.YAMLError as exc:
                issues.append({"code": "base-yaml-invalid", "path": item.path, "detail": str(exc)})
        return BaseResult(status="ok" if not issues else "needs-review", bases=bases, issues=issues)

    def sync(self, dry_run: bool = False) -> BaseResult:
        operations: list[dict[str, str]] = []
        writes: list[tuple[Path, str, str | None]] = []
        for name in self._managed_names():
            source = self._source_root() / name
            if not source.is_file():
                continue
            target = self._target_root() / name
            content = self._repository.read(source)
            current = self._repository.read(target) if target.is_file() else None
            if current is not None and self._same_definition(current, content):
                continue
            operations.append(
                {
                    "action": "update" if target.exists() else "create",
                    "path": name,
                    "sha256": hashlib.sha256(content.encode()).hexdigest(),
                }
            )
            expected = hashlib.sha256(current.encode()).hexdigest() if current is not None else None
            writes.append((target, content, expected))
        if not dry_run and writes:
            snapshot = {
                path.relative_to(self._settings.vault_root).as_posix(): expected
                for path, _content, expected in writes
            }
            with workspace_write_lock(self._settings.state_root):
                changed = snapshot_changes(self._settings.vault_root, snapshot)
                if changed:
                    return BaseResult(
                        status="blocked",
                        issues=[
                            enrich_issue({"code": "concurrent-change", "path": path})
                            for path in changed
                        ],
                    )
                for target, content, _expected in writes:
                    self._repository.write(target, content)
        return BaseResult(status="dry-run" if dry_run else "synced", operations=operations)

    def _bases(self) -> list[BaseInfo]:
        return [
            self._info(path, self._source_root())
            for path in sorted(self._source_root().glob("*.base"))
        ]

    def _info(self, path: Path, root: Path) -> BaseInfo:
        payload = yaml.safe_load(self._repository.read(path)) or {}
        views = [
            str(view.get("name", "")) for view in payload.get("views", []) if isinstance(view, dict)
        ]
        target = self._target_root() / path.name
        status = "missing-or-stale"
        if target.is_file() and self._same_definition(
            self._repository.read(target), self._repository.read(path)
        ):
            status = "current"
        return BaseInfo(
            name=path.name, path=path.relative_to(root).as_posix(), status=status, views=views
        )

    def _source_root(self) -> Path:
        return self._repository.source_root()

    def _target_root(self) -> Path:
        return self._settings.vault_root / self._settings.bases.get("target", "治理视图")

    def _managed_names(self) -> list[str]:
        return list(builtin_config("bases.json").get("managed_bases", []))

    @staticmethod
    def _same_definition(left: str, right: str) -> bool:
        try:
            return yaml.safe_load(left) == yaml.safe_load(right)
        except yaml.YAMLError:
            return left == right
