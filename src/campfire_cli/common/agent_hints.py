from __future__ import annotations

import os
from pathlib import Path

from campfire_cli.common.filesystem import atomic_write

HINT_START = "<!-- campfire:agent-hints:start -->"
HINT_END = "<!-- campfire:agent-hints:end -->"

HINT_BODY = """## Campfire 文档治理

本机装有 campfire CLI（`campfire --help`），Obsidian Vault 已注册为文档工作区。
当用户要求"沉淀/记录/写文档/归档/跟踪问题"到知识库或项目文档时，先运行
`campfire workspace resolve` 解析工作区，再按 campfire skill 流程处理；
不要直接在代码仓库里创建笔记文件。"""


def default_hint_paths() -> list[Path]:
    override = os.environ.get("CAMPFIRE_AGENT_HINT_PATH")
    if override:
        return [Path(item).expanduser().resolve() for item in override.split(os.pathsep) if item]
    home = Path.home()
    return [home / ".claude" / "CLAUDE.md", home / ".agents" / "AGENTS.md"]


def render_hint_block() -> str:
    return f"{HINT_START}\n{HINT_BODY}\n{HINT_END}"


def inject_agent_hint(path: Path) -> str:
    """幂等地向 path 写入 campfire 路标块，返回 created/appended/updated/kept。

    块由 HTML 注释标记包围；已存在时整体替换以升级内容，块外用户内容不动。
    """
    block = render_hint_block()
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    if HINT_START in current and HINT_END in current:
        start = current.index(HINT_START)
        end = current.index(HINT_END) + len(HINT_END)
        updated = current[:start] + block + current[end:]
        action = "updated" if updated != current else "kept"
    elif current:
        separator = "" if current.endswith("\n\n") else ("\n" if current.endswith("\n") else "\n\n")
        updated = current + separator + block + "\n"
        action = "appended"
    else:
        updated = block + "\n"
        action = "created"
    if action != "kept":
        atomic_write(path, updated)
    return action
