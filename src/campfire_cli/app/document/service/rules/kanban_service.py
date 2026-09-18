"""
SPEC:
  name: kanban_service
  purpose: 校验 Markdown 文档是否满足 Obsidian Kanban 插件的渲染契约
  default_env_file: none
  env_override: none
  idempotent: true
  behavior:
    - 只读检查 frontmatter 与正文结构，输出确定性 issue 列表
    - 不修改文档；改造由 Agent 按 skill 流程完成
  safety:
    - 不把渲染契约混入 Frontmatter Profile 契约，两者正交
"""

from __future__ import annotations

import re
from typing import Any

from campfire_cli.common.documents.markdown import parse_document

LANE_RE = re.compile(r"^##\s+\S")
COMMENT_START_RE = re.compile(r"^(<!--|%%)")
INDENTED_RE = re.compile(r"^\s+\S")


def check_kanban_renderability(text: str) -> list[dict[str, str]]:
    """返回文档渲染为 Obsidian Kanban 看板的阻碍项；空列表即可渲染。

    契约按真实看板校准：frontmatter 含 kanban-plugin 键；正文由 `## 泳道`
    标题分区，卡片为列表项；泳道前的 H1 标题与引用块导言、`%%` 设置块、
    卡片的缩进续行都被插件容忍，不视为阻碍。
    """
    parsed = parse_document(text)
    issues: list[dict[str, str]] = []
    plugin = parsed.frontmatter.get("kanban-plugin") if parsed.has_frontmatter else None
    if not isinstance(plugin, str) or not plugin.strip():
        issues.append({"code": "kanban-plugin-missing"})
    lane_seen = False
    comment_block = False
    for number, raw in enumerate(parsed.body.splitlines(), start=1):
        stripped = raw.strip()
        if comment_block:
            if stripped == "%%" or stripped.endswith("%%"):
                comment_block = False
            continue
        if not stripped:
            continue
        if stripped.startswith("%%") and not stripped.endswith("%%"):
            comment_block = True
            continue
        if LANE_RE.match(raw):
            lane_seen = True
            continue
        if COMMENT_START_RE.match(stripped) or raw.startswith("#") or stripped.startswith(">"):
            continue
        if INDENTED_RE.match(raw) or stripped.startswith("-"):
            if not lane_seen:
                issues.append({"code": "kanban-card-outside-lane", "detail": f"line {number}"})
            continue
        issues.append({"code": "kanban-line-not-card", "detail": f"line {number}"})
    if not lane_seen:
        issues.append({"code": "kanban-lane-missing"})
    return issues


def renderability_result(relative_path: str, issues: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "status": "ok" if not issues else "needs-review",
        "path": relative_path,
        "renderable": not issues,
        "issue_count": len(issues),
        "issues": issues,
    }
