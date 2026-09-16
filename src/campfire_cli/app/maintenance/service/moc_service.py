"""
SPEC:
  name: moc_service
  purpose: 幂等生成领域 MOC 自动区域、相关文档页面、索引缓存和治理报告
  default_env_file: none
  env_override: none
  idempotent: true
  behavior:
    - 从领域声明和 Markdown 正文生成派生内容
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
import re
from collections import Counter
from pathlib import Path
from typing import Any

from campfire_cli.app.workspace.schema.workspace_schema import Domain
from campfire_cli.app.workspace.service.structure_service import parse_marker as parse_frontmatter
from campfire_cli.config.defaults import config_section

START_MARKER = "<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->"
END_MARKER = "<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->"

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9.+#_-]{1,}")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]{2,}")


IGNORED_TERMS = frozenset(
    {
        "text",
        "true",
        "false",
        "none",
        "一个",
        "可以",
        "使用",
        "通过",
        "这个",
        "如果",
        "需要",
        "进行",
        "我们",
        "什么",
        "如何",
        "例如",
        "文件",
        "目录",
        "实现",
        "这里",
        "下面",
        "对于",
        "就是",
        "因为",
        "所以",
    }
)

IGNORED_TITLE_KEYWORDS = frozenset(
    {"go", "agent", "development", "document", "guide", "note", "over", "and", "with"}
)


def note_title(path: Path) -> str:
    return title_from_text(path.read_text(encoding="utf-8"), path.stem)


def title_from_text(text: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def note_terms(path: Path) -> Counter[str]:
    return terms_from_text(path.read_text(encoding="utf-8"))


def terms_from_text(text: str) -> Counter[str]:
    terms: list[str] = [token.lower() for token in LATIN_RE.findall(text)]
    for block in CHINESE_RE.findall(text):
        terms.extend(block[index : index + 2] for index in range(len(block) - 1))
    return Counter(term for term in terms if term not in IGNORED_TERMS)


def similarity(left: Counter[str], right: Counter[str]) -> tuple[float, list[str]]:
    left_terms = set(left)
    right_terms = set(right)
    union = left_terms | right_terms
    if not union:
        return 0.0, []
    common = left_terms & right_terms
    return len(common) / len(union), top_reasons(left, right, common)


def top_reasons(left: Counter[str], right: Counter[str], common: set[str]) -> list[str]:
    return [
        term
        for term, _ in sorted(
            ((term, left[term] + right[term]) for term in common),
            key=lambda item: (-item[1], item[0]),
        )[:5]
    ]


def title_keywords(path: Path) -> set[str]:
    return keywords_from_title(f"{path.stem} {note_title(path)}")


def keywords_from_title(title: str) -> set[str]:
    return {token.lower() for token in LATIN_RE.findall(title)} - IGNORED_TITLE_KEYWORDS


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


def generate_relations(
    notes: list[Path],
    domain_by_note: dict[Path, str],
    vault_root: Path,
    limit: int,
    minimum: float,
    cross_limit: int,
    cross_minimum: float,
) -> dict[Path, list[dict[str, Any]]]:
    # reasons 与标题关键词在候选保留后才计算，保证 O(n^2) 内层循环只做集合运算。
    texts = {note: note.read_text(encoding="utf-8") for note in notes}
    vectors = {note: terms_from_text(texts[note]) for note in notes}
    term_sets = {note: frozenset(vector) for note, vector in vectors.items()}
    term_sizes = {note: len(terms) for note, terms in term_sets.items()}
    title_keywords_by_note = {
        note: keywords_from_title(f"{note.stem} {title_from_text(texts[note], note.stem)}")
        for note in notes
    }
    explicit_links = {
        note: {Path(value).stem for value in WIKILINK_RE.findall(texts[note])} for note in notes
    }
    relations: dict[Path, list[dict[str, Any]]] = {}
    for source in notes:
        strong: list[dict[str, Any]] = []
        same_domain_semantic: list[dict[str, Any]] = []
        cross_domain_semantic: list[dict[str, Any]] = []
        source_terms = term_sets[source]
        source_links = explicit_links[source]
        source_domain = domain_by_note[source]
        for target in notes:
            if source == target:
                continue
            reasons: list[str] = []
            if target.stem in source_links:
                relation_type = "direct-link"
                score = 1.0
                reasons = ["正文直接链接"]
            elif source.stem in explicit_links[target]:
                relation_type = "backlink"
                score = 1.0
                reasons = ["目标文档引用本文"]
            else:
                if source_domain == domain_by_note[target]:
                    relation_type = "same-domain-similarity"
                else:
                    common_title_keywords = sorted(
                        title_keywords_by_note[source] & title_keywords_by_note[target]
                    )
                    if not common_title_keywords:
                        continue
                    relation_type = "cross-domain-similarity"
                    reasons = [f"标题共同关键词:{value}" for value in common_title_keywords]
                target_terms = term_sets[target]
                common = source_terms & target_terms
                union_size = term_sizes[source] + term_sizes[target] - len(common)
                score = len(common) / union_size if union_size else 0.0
            threshold = cross_minimum if relation_type == "cross-domain-similarity" else minimum
            if relation_type in {"direct-link", "backlink"} or score >= threshold:
                if relation_type not in {"direct-link", "backlink"}:
                    reasons = reasons + top_reasons(vectors[source], vectors[target], common)
                item = {
                    "target": str(target.relative_to(vault_root).with_suffix("")),
                    "target_name": target.stem,
                    "target_domain": domain_by_note[target],
                    "type": relation_type,
                    "score": round(score, 4),
                    "reasons": reasons,
                }
                if relation_type in {"direct-link", "backlink"}:
                    strong.append(item)
                elif relation_type == "same-domain-similarity":
                    same_domain_semantic.append(item)
                else:
                    cross_domain_semantic.append(item)
        strong.sort(key=lambda item: (item["type"], item["target"].casefold()))
        same_domain_semantic.sort(key=lambda item: (-item["score"], item["target"].casefold()))
        cross_domain_semantic.sort(key=lambda item: (-item["score"], item["target"].casefold()))
        relations[source] = (
            strong + same_domain_semantic[:limit] + cross_domain_semantic[:cross_limit]
        )
    return relations


def replace_generated_region(original: str, generated: str) -> str:
    if original.count(START_MARKER) != 1 or original.count(END_MARKER) != 1:
        raise ValueError("MOC 自动生成标记必须且只能各出现一次")
    start = original.index(START_MARKER) + len(START_MARKER)
    end = original.index(END_MARKER)
    if end < start:
        raise ValueError("MOC 自动生成标记顺序无效")
    return original[:start] + "\n\n" + generated.rstrip() + "\n\n" + original[end:]


def write_if_changed(
    path: Path, content: str, dry_run: bool, changes: list[str], vault_root: Path
) -> None:
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    if previous == content:
        return
    changes.append(str(path.relative_to(vault_root)))
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def generate_domain_content(
    domain: Domain,
    domains: list[Domain],
    notes: list[Path],
    templates: list[Path],
    relation_page: Path | None,
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
    lines.extend(["", "## 自动关系", ""])
    lines.append(f"- [[{relation_page.stem}|相关文档计算结果]]" if relation_page else "- 暂无")
    return "\n".join(lines)


def generate_project_domain_content(
    domain: Domain,
    domains: list[Domain],
    notes: list[Path],
    templates: list[Path],
    marker_name: str,
    project_doc_types: dict[str, dict[str, str]] | None = None,
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
    if project_doc_types is None:
        config = config_section("document_types")
        project_doc_types = {
            name: config["types"][name] for name in config["profiles"]["project-docs"]
        }
    by_type: dict[str, list[tuple[Path, str]]] = {}
    for note in notes:
        if note.name in {"README.md", "CLAUDE.md"}:
            continue
        meta = parse_frontmatter(note)
        doc_type = meta.get("type", "") if meta else ""
        status = meta.get("status", "") if meta else ""
        if not meta:
            status = "缺 frontmatter"
        if doc_type not in project_doc_types:
            doc_type = "未分类"
        by_type.setdefault(doc_type, []).append((note, status))
    for doc_type in [*project_doc_types, "未分类"]:
        entries = sorted(by_type.get(doc_type, []), key=lambda item: item[0].name.casefold())
        if not entries:
            continue
        heading = "未分类" if doc_type == "未分类" else project_doc_types[doc_type]["label"]
        lines.extend([f"### {heading}", ""])
        for note, status in entries:
            suffix = f" `{status}`" if status else ""
            lines.append(f"- [[{note.stem}]]{suffix}")
        lines.append("")
    record_dirs = [d for d in ["记录", "_总览"] if (domain.path / d).is_dir()]
    for d in record_dirs:
        count = len(list((domain.path / d).rglob("*.md")))
        if count:
            lines.extend([f"### {d}/", "", f"- {count} 篇，见目录", ""])
    archive_dir = domain.path / "archive"
    if archive_dir.is_dir():
        archived_notes = sorted(
            archive_dir.rglob("*.md"),
            key=lambda path: str(path.relative_to(archive_dir)).casefold(),
        )
        if archived_notes:
            lines.extend(["### 已归档", ""])
            for archived_note in archived_notes:
                meta = parse_frontmatter(archived_note)
                reason = meta.get("archive_reason", "待补原因") if meta else "待补元数据"
                successor = meta.get("superseded_by", "") if meta else ""
                suffix = f"；替代：{successor}" if successor and successor != "[]" else ""
                rel = archived_note.relative_to(domain.path).with_suffix("")
                lines.append(f"- [[{rel}|{archived_note.stem}]]：`{reason}`{suffix}")
            lines.append("")
    append_template_section(lines, domain, templates)
    lines.append("")
    return "\n".join(lines).rstrip()


def relation_markdown(
    domain: Domain, notes: list[Path], relations: dict[Path, list[dict[str, Any]]]
) -> str:
    lines = [
        f"# {domain.name}相关文档",
        "",
        "> 本页由 `governance_sync.py` 自动生成，请勿手工编辑。",
        "",
    ]
    for note in notes:
        lines.extend([f"## [[{note.stem}]]", ""])
        items = relations.get(note, [])
        if not items:
            lines.extend(["- 暂无达到阈值的相关文档", ""])
            continue
        for item in items:
            reason = "、".join(item["reasons"]) or "同领域内容相似"
            lines.append(
                f"- [[{item['target']}|{item['target_name']}]]："
                f"`{item['type']}`，得分 `{item['score']:.4f}`；依据：{reason}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
