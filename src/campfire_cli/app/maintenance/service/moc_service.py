"""
SPEC:
  name: moc_service
  purpose: 幂等生成领域 MOC 自动区域
  default_env_file: none
  env_override: none
  idempotent: true
  behavior:
    - 从领域声明和文档属性生成目录内容
    - 内容未变化时不重写文件
    - 支持 dry-run 和 JSON 输出
  safety:
    - 不移动、重命名、合并或删除原始笔记
    - 只覆盖成对标记之间的 MOC 自动区域
  idempotency_keys:
    domain: domain_id
"""

from __future__ import annotations

import os
from pathlib import Path

from campfire_cli.app.workspace.schema.workspace_schema import Domain

START_MARKER = "<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->"
END_MARKER = "<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->"


def direct_notes(domain: Domain, marker_name: str) -> list[Path]:
    excluded = {marker_name, f"{domain.moc}.md"}
    return sorted(
        [path for path in domain.path.glob("*.md") if path.name not in excluded],
        key=lambda path: path.name.casefold(),
    )


def direct_templates(domain: Domain) -> list[Path]:
    """Return templates physically owned by this Domain."""
    directory = domain.path / "_模板"
    if not directory.is_dir():
        return []
    return sorted(directory.glob("模板-*.md"), key=lambda path: path.name.casefold())


def moc_link(domain: Domain, target: Path) -> str:
    moc_directory = (domain.path / f"{domain.moc}.md").parent
    return Path(os.path.relpath(target.with_suffix(""), moc_directory)).as_posix()


def append_template_section(lines: list[str], domain: Domain, templates: list[Path]) -> None:
    if not templates:
        return
    lines.extend(["", "## 文档模板", ""])
    lines.extend(f"- [[{moc_link(domain, item)}|{item.stem}]]" for item in templates)


def replace_generated_region(original: str, generated: str) -> str:
    if original.count(START_MARKER) != 1 or original.count(END_MARKER) != 1:
        raise ValueError("MOC 自动生成标记必须且只能各出现一次")
    start = original.index(START_MARKER) + len(START_MARKER)
    end = original.index(END_MARKER)
    if end < start:
        raise ValueError("MOC 自动生成标记顺序无效")
    return original[:start] + "\n\n" + generated.rstrip() + "\n\n" + original[end:]


def generate_domain_content(
    domain: Domain,
    domains: list[Domain],
    notes: list[Path],
    templates: list[Path],
) -> str:
    children = sorted(
        [item for item in domains if item.parent_domain == domain.id],
        key=lambda item: item.name.casefold(),
    )
    parent = next((item for item in domains if item.id == domain.parent_domain), None)
    lines = ["## 领域位置", ""]
    lines.append(
        f"- 父领域：[[{moc_link(domain, parent.path / (parent.moc + '.md'))}|{parent.name}]]"
        if parent
        else "- 父领域：当前治理根"
    )
    lines.extend(["", "## 子领域", ""])
    lines.extend(
        [
            f"- [[{moc_link(domain, child.path / (child.moc + '.md'))}|{child.name}]]"
            for child in children
        ]
        or ["- 暂无"]
    )
    lines.extend(["", "## 本领域文档", ""])
    lines.extend([f"- [[{moc_link(domain, note)}|{note.stem}]]" for note in notes] or ["- 暂无"])
    append_template_section(lines, domain, templates)
    return "\n".join(lines)
