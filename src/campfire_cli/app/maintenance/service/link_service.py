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

import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

WIKILINK_RE = re.compile(r"!?\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
FENCED_CODE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def vault_markdown_files(vault_root: Path) -> list[Path]:
    excluded = {".git", ".obsidian", ".campfire"}
    return sorted(
        path
        for path in vault_root.rglob("*.md")
        if not any(part in excluded for part in path.relative_to(vault_root).parts)
    )


def check_links(vault_root: Path, sources: list[Path]) -> list[dict[str, str]]:
    by_stem: dict[str, list[Path]] = defaultdict(list)
    for candidate in vault_root.rglob("*"):
        if candidate.is_file() and ".git" not in candidate.relative_to(vault_root).parts:
            by_stem[candidate.stem].append(candidate)
    issues: list[dict[str, str]] = []
    for source in sources:
        text = INLINE_CODE_RE.sub("", FENCED_CODE_RE.sub("", source.read_text(encoding="utf-8")))
        for raw in WIKILINK_RE.findall(text):
            target = unquote(raw.strip()).replace("\\", "/")
            if "/" in target:
                candidates = [
                    vault_root / target,
                    vault_root / f"{target}.md",
                    source.parent / target,
                    source.parent / f"{target}.md",
                ]
                matches = {item.resolve() for item in candidates if item.is_file()}
            else:
                stem = target[:-3] if target.lower().endswith(".md") else target
                matches = set(by_stem.get(stem, []))
            if not matches:
                issues.append(
                    {
                        "code": "wikilink-missing",
                        "path": source.relative_to(vault_root).as_posix(),
                        "detail": raw,
                    }
                )
            elif len(matches) > 1:
                issues.append(
                    {
                        "code": "wikilink-ambiguous",
                        "path": source.relative_to(vault_root).as_posix(),
                        "detail": raw,
                    }
                )
        for raw in MARKDOWN_LINK_RE.findall(text):
            target = unquote(raw.strip().strip("<>").split("#", 1)[0])
            if not target or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
                continue
            candidate = (
                vault_root / target.lstrip("/")
                if target.startswith("/")
                else source.parent / target
            )
            if not candidate.exists():
                issues.append(
                    {
                        "code": "markdown-link-missing",
                        "path": source.relative_to(vault_root).as_posix(),
                        "detail": raw,
                    }
                )
    return issues
