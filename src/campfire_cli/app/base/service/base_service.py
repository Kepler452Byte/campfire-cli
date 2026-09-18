from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from campfire_cli.app.base.repository.base_repository import BaseRepository
from campfire_cli.app.base.schema.base_schema import BaseInfo, BaseResult
from campfire_cli.common.governance import enrich_issue, optimistic_write_lock
from campfire_cli.common.hashing import file_sha256, text_sha256
from campfire_cli.config.defaults import config_section
from campfire_cli.config.settings import WorkspaceSettings


class BaseService:
    _FIELD_REFERENCE = re.compile(
        r"(?<![.\w])([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*(?:==|!=|\.isEmpty\(|\.contains\()"
    )
    _ENUM_COMPARISON = re.compile(r"""\b([A-Za-z_]\w*)\s*(?:==|!=)\s*["']([^"']+)["']""")

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
            status="ok",
            bases=[self._info(path, root)],
            content=self._render(path) if source == "ssot" else self._repository.read(path),
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
                elif payload:
                    issues.extend(self._semantic_issues(payload, item.path))
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
            content = self._render(source)
            current = self._repository.read(target) if target.is_file() else None
            if current is not None and self._same_definition(current, content):
                continue
            operations.append(
                {
                    "action": "update" if target.exists() else "create",
                    "path": name,
                    "sha256": text_sha256(content),
                }
            )
            expected = file_sha256(target) if target.is_file() else None
            writes.append((target, content, expected))
        if not dry_run and writes:
            snapshot = {
                path.relative_to(self._settings.vault_root).as_posix(): expected
                for path, _content, expected in writes
            }
            with optimistic_write_lock(
                self._settings.state_root, snapshot, self._settings.vault_root
            ) as changed:
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
            self._repository.read(target), self._render(path)
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
        return list(config_section("bases").get("managed_bases", []))

    def _semantic_issues(self, payload: dict[str, Any], path: str) -> list[dict[str, str]]:
        known = self._known_fields()
        referenced = set(payload.get("properties", {}))
        for view in payload.get("views", []):
            if not isinstance(view, dict):
                continue
            referenced.update(view.get("order", []))
            group_by = view.get("groupBy", {})
            if isinstance(group_by, dict) and isinstance(group_by.get("property"), str):
                referenced.add(group_by["property"])
            for expression in self._expressions(view.get("filters")):
                referenced.update(self._FIELD_REFERENCE.findall(expression))
        for expression in self._expressions(payload.get("filters")):
            referenced.update(self._FIELD_REFERENCE.findall(expression))
        issues = [
            {"code": "base-unknown-field", "path": path, "detail": field}
            for field in sorted(field for field in referenced if field not in known)
        ]
        candidates = self._enum_candidates()
        for expression in self._expressions(payload.get("filters")) + [
            expression
            for view in payload.get("views", [])
            if isinstance(view, dict)
            for expression in self._expressions(view.get("filters"))
        ]:
            for field, value in self._ENUM_COMPARISON.findall(expression):
                if field in candidates and value not in candidates[field]:
                    issues.append(
                        {
                            "code": "base-enum-value-invalid",
                            "path": path,
                            "detail": f"{field}={value}",
                        }
                    )
        return issues

    def _known_fields(self) -> set[str]:
        profiles = self._settings.frontmatter_schema.get("profiles", {})
        fields = {
            field
            for profile in profiles.values()
            if isinstance(profile, dict)
            for field in profile.get("fields", {})
        }
        return fields | {"file.name", "file.path", "file.folder", "file.ext"}

    def _enum_candidates(self) -> dict[str, set[str]]:
        candidates = {"type": set(self._settings.document_types.get("types", {}))}
        for profile in self._settings.frontmatter_schema.get("profiles", {}).values():
            if not isinstance(profile, dict):
                continue
            for field, rule in profile.get("fields", {}).items():
                if isinstance(rule, dict) and rule.get("kind") == "enum" and rule.get("values"):
                    candidates.setdefault(field, set()).update(rule["values"])
        return candidates

    @staticmethod
    def _expressions(value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [
                item
                for values in value.values()
                if isinstance(values, list)
                for item in values
                if isinstance(item, str)
            ]
        return []

    def _render(self, source: Path) -> str:
        return self._repository.read(source)

    @staticmethod
    def _same_definition(left: str, right: str) -> bool:
        try:
            return yaml.safe_load(left) == yaml.safe_load(right)
        except yaml.YAMLError:
            return left == right
