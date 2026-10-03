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
from typing import Any

from campfire_cli.app.workspace.schema.workspace_schema import Domain
from campfire_cli.app.workspace.service.structure_service import parse_marker as parse_frontmatter
from campfire_cli.config.defaults import config_section

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


def template_link(domain: Domain, template: Path) -> str:
    moc_directory = (domain.path / f"{domain.moc}.md").parent
    return Path(os.path.relpath(template.with_suffix(""), moc_directory)).as_posix()


def append_template_section(lines: list[str], domain: Domain, templates: list[Path]) -> None:
    if not templates:
        return
    lines.extend(["", "## 文档模板", ""])
    lines.extend(f"- [[{template_link(domain, item)}|{item.stem}]]" for item in templates)


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
    lines.append(f"- 父领域：[[{parent.moc}|{parent.name}]]" if parent else "- 父领域：当前治理根")
    lines.extend(["", "## 子领域", ""])
    lines.extend([f"- [[{child.moc}|{child.name}]]" for child in children] or ["- 暂无"])
    lines.extend(["", "## 本领域文档", ""])
    lines.extend([f"- [[{note.stem}]]" for note in notes] or ["- 暂无"])
    append_template_section(lines, domain, templates)
    return "\n".join(lines)


def generate_project_domain_content(
    domain: Domain,
    domains: list[Domain],
    notes: list[Path],
    templates: list[Path],
    marker_name: str,
    project_groups: list[dict[str, Any]] | None = None,
) -> str:
    """project-docs 领域的 MOC 自动区域：按文档类型分组并列出状态，不计算相似度关系。"""
    children = sorted(
        [item for item in domains if item.parent_domain == domain.id],
        key=lambda item: item.name.casefold(),
    )
    parent = next((item for item in domains if item.id == domain.parent_domain), None)
    lines = ["## 领域位置", ""]
    lines.append(f"- 父领域：[[{parent.moc}|{parent.name}]]" if parent else "- 父领域：当前治理根")
    lines.extend(["", "## 子领域", ""])
    lines.extend([f"- [[{child.moc}|{child.name}]]" for child in children] or ["- 暂无"])
    lines.extend(["", "## 文档索引", ""])
    if project_groups is None:
        project_groups = config_section("moc").get("project_groups", [])
    group_by_type = {
        document_type: group["label"]
        for group in project_groups
        for document_type in group.get("types", [])
    }
    by_group: dict[str, list[tuple[Path, str]]] = {}
    for note in notes:
        if note.name in {"README.md", "CLAUDE.md"}:
            continue
        meta = parse_frontmatter(note)
        doc_type = meta.get("type", "") if meta else ""
        status = meta.get("document_status", "") if meta else ""
        if not meta:
            status = "缺 frontmatter"
        group = group_by_type.get(doc_type, "未分类")
        by_group.setdefault(group, []).append((note, status))
    for group in [*(item["label"] for item in project_groups), "未分类"]:
        entries = sorted(by_group.get(group, []), key=lambda item: item[0].name.casefold())
        if not entries:
            continue
        lines.extend([f"### {group}", ""])
        for note, status in entries:
            suffix = f" `{status}`" if status else ""
            lines.append(f"- [[{note.stem}]]{suffix}")
        lines.append("")
    record_dirs = [d for d in ["记录", "_总览"] if (domain.path / d).is_dir()]
    for d in record_dirs:
        count = len(list((domain.path / d).rglob("*.md")))
        if count:
            lines.extend([f"### {d}/", "", f"- {count} 篇，见目录", ""])
    append_template_section(lines, domain, templates)
    lines.append("")
    return "\n".join(lines).rstrip()
