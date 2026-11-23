from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

import yaml

from campfire_cli.app.workspace.schema.workspace_schema import WorkspaceManifest
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.common.filesystem import atomic_write

MANIFEST_FILENAME = ".campfire.yaml"


class WorkspaceManifestRepository:
    """Read and write the portable Workspace metadata stored with a Vault."""

    def path(self, workspace: Path) -> Path:
        return workspace / MANIFEST_FILENAME

    def load(self, workspace: Path) -> WorkspaceManifest | None:
        target = self.path(workspace)
        if not target.is_file():
            return None
        try:
            payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
            return WorkspaceManifest.model_validate(payload)
        except (yaml.YAMLError, ValueError) as exc:
            raise ConfigurationError(
                f"Manifest 无效：{target}：{exc}；请核对当前 Manifest 结构",
                code="manifest-invalid",
            ) from exc

    def save(self, workspace: Path, manifest: WorkspaceManifest) -> Path:
        target = self.path(workspace)
        atomic_write(target, self.render(manifest))
        return target

    def skill_roots(self, workspace: Path) -> tuple[tuple[Path, ...], list[dict[str, str]]]:
        manifest = self.load(workspace)
        roots: set[Path] = set()
        issues: list[dict[str, str]] = []
        if manifest is None or manifest.skills is None:
            return (), issues
        for value in manifest.skills.roots:
            try:
                if (
                    not value.strip()
                    or "\\" in value
                    or PureWindowsPath(value).anchor
                    or ".." in PurePosixPath(value).parts
                ):
                    raise ValueError("请使用 Vault 内的相对目录路径，以 / 分隔")
                path = (workspace / value).resolve()
                if not path.is_relative_to(workspace):
                    raise ValueError("解析后的目录必须位于 Vault 内")
                if not path.is_dir():
                    raise ValueError("目录不存在或路径不是目录")
            except (OSError, RuntimeError, ValueError) as exc:
                issues.append({"code": "skill-root-invalid", "path": value, "message": str(exc)})
                continue
            roots.add(path)
        return tuple(sorted(roots)), issues

    @staticmethod
    def render(manifest: WorkspaceManifest) -> str:
        return "".join(
            [
                "# Managed by Campfire CLI. Use `campfire workspace ...` for Workspace metadata.\n",
                yaml.safe_dump(
                    manifest.model_dump(mode="json", exclude_none=True),
                    allow_unicode=True,
                    sort_keys=False,
                ),
            ]
        )
