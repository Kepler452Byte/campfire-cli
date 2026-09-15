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

from campfire_cli.common.documents.links import (
    extract_link_references,
    resolve_link_reference,
    stem_index,
)


def vault_markdown_files(vault_root: Path) -> list[Path]:
    excluded = {".git", ".obsidian", ".campfire"}
    return sorted(
        path
        for path in vault_root.rglob("*.md")
        if not any(part in excluded for part in path.relative_to(vault_root).parts)
    )


def check_links(vault_root: Path, sources: list[Path]) -> list[dict[str, str]]:
    candidates = {
        candidate.resolve()
        for candidate in vault_root.rglob("*")
        if candidate.is_file() and ".git" not in candidate.relative_to(vault_root).parts
    }
    by_stem = stem_index(candidates)
    issues: list[dict[str, str]] = []
    for source in sources:
        for reference in extract_link_references(source.read_text(encoding="utf-8")):
            resolution = resolve_link_reference(vault_root, source, reference, candidates, by_stem)
            if resolution.external:
                continue
            if reference.syntax == "wiki" and resolution.status == "missing":
                issues.append(
                    {
                        "code": "wikilink-missing",
                        "path": source.relative_to(vault_root).as_posix(),
                        "detail": reference.raw_target,
                    }
                )
            elif reference.syntax == "wiki" and resolution.status == "ambiguous":
                issues.append(
                    {
                        "code": "wikilink-ambiguous",
                        "path": source.relative_to(vault_root).as_posix(),
                        "detail": reference.raw_target,
                    }
                )
            elif reference.syntax == "markdown" and resolution.status == "missing":
                issues.append(
                    {
                        "code": "markdown-link-missing",
                        "path": source.relative_to(vault_root).as_posix(),
                        "detail": reference.raw_target,
                    }
                )
    return issues
