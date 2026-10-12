from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.config.defaults import effective_config


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
        try:
            config = effective_config(campfire_home() / "config.yml")
        except (OSError, ValueError) as exc:
            raise ConfigurationError(f"无法加载 Campfire config.yml：{exc}") from exc
        return cls(
            workspace_id=workspace_id,
            vault_root=root,
            state_root=state_root,
            governance=config["governance"],
            document_types=config["document_types"],
            frontmatter_schema=config["frontmatter_schema"],
            skills=config["skills"],
            bases=config["bases"],
        )


@dataclass(frozen=True)
class AgentResourceSettings:
    state_root: Path
    targets: list[Path]
    hints: list[Path]
    managed_skills: list[str]

    @classmethod
    def load(cls) -> AgentResourceSettings:
        home = campfire_home()
        try:
            skills = effective_config(home / "config.yml")["skills"]
        except (OSError, ValueError) as exc:
            raise ConfigurationError(f"无法加载 Campfire config.yml：{exc}") from exc
        override = os.environ.get("CAMPFIRE_SKILL_TARGETS")
        values = override.split(os.pathsep) if override else skills.get("targets", [])
        hint_override = os.environ.get("CAMPFIRE_AGENT_HINT_PATH")
        hints = (
            hint_override.split(os.pathsep)
            if hint_override
            else ["~/.claude/CLAUDE.md", "~/.agents/AGENTS.md"]
        )
        return cls(
            home,
            [Path(v).expanduser().absolute() for v in values if v],
            [Path(v).expanduser().absolute() for v in hints if v],
            list(skills.get("managed_skills", [])),
        )
