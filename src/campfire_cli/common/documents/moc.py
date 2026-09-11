"""
SPEC:
  name: governance_sync
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

import re
from collections import Counter
from pathlib import Path
from typing import Any

from campfire_cli.common.documents.domains import (
    END_MARKER,
    PROJECT_DOC_TYPES,
    START_MARKER,
    Domain,
    parse_frontmatter,
)

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9.+#_-]{1,}")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]{2,}")


def note_title(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else path.stem


def note_terms(path: Path) -> Counter[str]:
    text = path.read_text(encoding="utf-8")
    terms: list[str] = [token.lower() for token in LATIN_RE.findall(text)]
    for block in CHINESE_RE.findall(text):
        terms.extend(block[index : index + 2] for index in range(len(block) - 1))
    ignored = {
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
    return Counter(term for term in terms if term not in ignored)


def similarity(left: Counter[str], right: Counter[str]) -> tuple[float, list[str]]:
    left_terms = set(left)
    right_terms = set(right)
    union = left_terms | right_terms
    if not union:
        return 0.0, []
    common = left_terms & right_terms
    score = len(common) / len(union)
    reasons = [
        term
        for term, _ in sorted(
            ((term, left[term] + right[term]) for term in common),
            key=lambda item: (-item[1], item[0]),
        )[:5]
    ]
    return score, reasons


def title_keywords(path: Path) -> set[str]:
    title = f"{path.stem} {note_title(path)}"
    keywords = {token.lower() for token in LATIN_RE.findall(title)}
    ignored = {"go", "agent", "development", "document", "guide", "note", "over", "and", "with"}
    return keywords - ignored


def direct_notes(domain: Domain, marker_name: str) -> list[Path]:
    excluded = {marker_name, f"{domain.moc_name}.md"}
    return sorted(
        [path for path in domain.path.glob("*.md") if path.name not in excluded],
        key=lambda path: path.name.casefold(),
    )


def generate_relations(
    notes: list[Path],
    domain_by_note: dict[Path, str],
    vault_root: Path,
    limit: int,
    minimum: float,
    cross_limit: int,
    cross_minimum: float,
) -> dict[Path, list[dict[str, Any]]]:
    vectors = {note: note_terms(note) for note in notes}
    texts = {note: note.read_text(encoding="utf-8") for note in notes}
    explicit_links = {
        note: {Path(value).stem for value in WIKILINK_RE.findall(texts[note])} for note in notes
    }
    relations: dict[Path, list[dict[str, Any]]] = {}
    for source in notes:
        strong: list[dict[str, Any]] = []
        same_domain_semantic: list[dict[str, Any]] = []
        cross_domain_semantic: list[dict[str, Any]] = []
        for target in notes:
            if source == target:
                continue
            score, reasons = similarity(vectors[source], vectors[target])
            if target.stem in explicit_links[source]:
                relation_type = "direct-link"
                score = 1.0
                reasons = ["正文直接链接"]
            elif source.stem in explicit_links[target]:
                relation_type = "backlink"
                score = 1.0
                reasons = ["目标文档引用本文"]
            else:
                same_domain = domain_by_note[source] == domain_by_note[target]
                relation_type = (
                    "same-domain-similarity" if same_domain else "cross-domain-similarity"
                )
                if not same_domain:
                    common_title_keywords = sorted(title_keywords(source) & title_keywords(target))
                    if not common_title_keywords:
                        continue
                    reasons = [
                        f"标题共同关键词:{value}" for value in common_title_keywords
                    ] + reasons
            threshold = cross_minimum if relation_type == "cross-domain-similarity" else minimum
            if relation_type in {"direct-link", "backlink"} or score >= threshold:
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
    domain: Domain, domains: list[Domain], notes: list[Path], relation_page: Path | None
) -> str:
    children = sorted(
        [item for item in domains if item.parent_domain == domain.domain_id],
        key=lambda item: item.name.casefold(),
    )
    parent = next((item for item in domains if item.domain_id == domain.parent_domain), None)
    lines = ["## 领域位置", ""]
    lines.append(
        f"- 父领域：[[{parent.moc_name}|{parent.name}]]" if parent else "- 父领域：当前治理根"
    )
    lines.extend(["", "## 子领域", ""])
    lines.extend([f"- [[{child.moc_name}|{child.name}]]" for child in children] or ["- 暂无"])
    lines.extend(["", "## 本领域文档", ""])
    lines.extend([f"- [[{note.stem}]]" for note in notes] or ["- 暂无"])
    lines.extend(["", "## 自动关系", ""])
    lines.append(f"- [[{relation_page.stem}|相关文档计算结果]]" if relation_page else "- 暂无")
    return "\n".join(lines)


def generate_project_domain_content(
    domain: Domain,
    domains: list[Domain],
    notes: list[Path],
    marker_name: str,
    project_doc_types: dict[str, str] | None = None,
) -> str:
    """project-docs 领域的 MOC 自动区域：按文档类型分组并列出状态，不计算相似度关系。"""
    children = sorted(
        [item for item in domains if item.parent_domain == domain.domain_id],
        key=lambda item: item.name.casefold(),
    )
    parent = next((item for item in domains if item.domain_id == domain.parent_domain), None)
    lines = ["## 领域位置", ""]
    lines.append(
        f"- 父领域：[[{parent.moc_name}|{parent.name}]]" if parent else "- 父领域：当前治理根"
    )
    lines.extend(["", "## 子领域", ""])
    lines.extend([f"- [[{child.moc_name}|{child.name}]]" for child in children] or ["- 暂无"])
    lines.extend(["", "## 文档索引", ""])
    project_doc_types = project_doc_types or PROJECT_DOC_TYPES
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
    label = {
        "product-spec": "产品",
        "tech-spec": "技术",
        "decision": "决策",
        "plan": "计划",
        "issue": "问题",
        "record": "记录",
        "moc": "导航",
        "未分类": "未分类",
    }
    for doc_type in [
        "product-spec",
        "tech-spec",
        "decision",
        "plan",
        "issue",
        "record",
        "moc",
        "未分类",
    ]:
        entries = sorted(by_type.get(doc_type, []), key=lambda item: item[0].name.casefold())
        if not entries:
            continue
        lines.extend([f"### {label[doc_type]}", ""])
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
                f"- [[{item['target']}|{item['target_name']}]]：`{item['type']}`，得分 `{item['score']:.4f}`；依据：{reason}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
