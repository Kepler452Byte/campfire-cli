from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from campfire_cli.common.exceptions import ConfigurationError


def campfire_home() -> Path:
    return Path(os.environ.get("CAMPFIRE_HOME", "~/.campfire")).expanduser().resolve()


@dataclass(frozen=True)
class WorkspaceSettings:
    workspace_id: str
    vault_root: Path
    state_root: Path
    governance: dict[str, Any]
    document_types: dict[str, Any]
    frontmatter_schema: dict[str, Any]
    skills: dict[str, Any]
    bases: dict[str, Any]

    def skill_targets(self) -> list[Path]:
        override = os.environ.get("CAMPFIRE_SKILL_TARGETS")
        values = override.split(os.pathsep) if override else self.skills.get("targets", [])
        return [Path(value).expanduser().resolve() for value in values]

    @classmethod
    def load(cls, workspace_id: str, root: Path) -> WorkspaceSettings:
        if not root.is_dir():
            raise ConfigurationError(f"已注册 Workspace 不存在：{root}")
        state_root = campfire_home() / "workspaces" / workspace_id
        config_root = state_root / "config"
        required = {
            "governance": config_root / "governance.json",
            "document_types": config_root / "document-types.json",
            "frontmatter_schema": config_root / "frontmatter-schema.json",
            "skills": config_root / "skills.json",
            "bases": config_root / "bases.json",
        }
        missing = [str(path) for path in required.values() if not path.is_file()]
        if missing:
            raise ConfigurationError("缺少 Campfire 配置：" + ", ".join(missing))
        return cls(
            workspace_id=workspace_id,
            vault_root=root,
            state_root=state_root,
            **{
                name: json.loads(path.read_text(encoding="utf-8"))
                for name, path in required.items()
            },
        )
