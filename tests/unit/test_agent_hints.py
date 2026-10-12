from __future__ import annotations

import os
from pathlib import Path

from campfire_cli.container import AppContainer

HINT_START = "<!-- campfire:agent-hints:start -->"
HINT_END = "<!-- campfire:agent-hints:end -->"


def inject_agent_hint(path: Path) -> str:
    os.environ["CAMPFIRE_AGENT_HINT_PATH"] = str(path)
    result = AppContainer.build_skill().align()
    assert result["skills"]["status"] == "synced", result
    return next(item["action"] for item in result["agent_hints"] if item["path"] == str(path))


def test_inject_creates_then_keeps(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    assert inject_agent_hint(target) == "created"
    content = target.read_text(encoding="utf-8")
    assert content.startswith(HINT_START)
    assert content.endswith(HINT_END + "\n")
    assert inject_agent_hint(target) == "kept"


def test_inject_appends_without_touching_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    original = "# 我的规范\n\n- 保持原样\n"
    target.write_text(original, encoding="utf-8")
    assert inject_agent_hint(target) == "appended"
    content = target.read_text(encoding="utf-8")
    assert content.startswith(original)
    assert HINT_END in content


def test_inject_replaces_stale_block_only(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    stale = f"# 头部\n\n{HINT_START}\n旧内容\n{HINT_END}\n# 尾部\n"
    target.write_text(stale, encoding="utf-8")
    assert inject_agent_hint(target) == "updated"
    content = target.read_text(encoding="utf-8")
    assert "旧内容" not in content
    assert content.startswith("# 头部")
    assert content.endswith("# 尾部\n")
