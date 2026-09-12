"""
SPEC:
  name: link_service
  purpose: 只读检查 Vault 或已治理范围的 wikilink、Markdown 链接、嵌入和附件引用
  default_env_file: none
  env_override: none
  idempotent: true
  behavior:
    - 支持 managed 和 vault 两种扫描范围
    - 报告失效、歧义 wikilink 和失效相对链接
  safety:
    - 不修改任何文件
"""

from __future__ import annotations

from pathlib import Path


def vault_markdown_files(vault_root: Path) -> list[Path]:
    excluded = {".git", ".obsidian", ".campfire"}
    return sorted(
        path
        for path in vault_root.rglob("*.md")
        if not any(part in excluded for part in path.relative_to(vault_root).parts)
    )
