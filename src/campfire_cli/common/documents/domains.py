"""
SPEC:
  name: governance_check
  purpose: 只读检查知识库领域声明、MOC、内部链接和候选目录
  default_env_file: none
  env_override: none
  idempotent: true
  behavior:
    - 扫描配置中的治理根目录
    - 校验领域标识、父领域和 MOC
    - 报告未声明目录、未命名文档和失效内部链接
  safety:
    - 不修改任何文件
    - 不扫描配置范围外的目录
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from campfire_cli.common.documents.document_types import profile_mapping

START_MARKER = "<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->"
END_MARKER = "<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->"
WIKILINK_RE = re.compile(r"!?\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
FENCED_CODE_RE = re.compile(r"\x60\x60\x60.*?\x60\x60\x60|~~~.*?~~~", re.DOTALL)
INLINE_CODE_RE = re.compile(r"\x60[^\x60\n]*\x60")

PROJECT_DOC_TYPES = {
    "moc": "MOC-",
    "product-spec": "产品-",
    "tech-spec": "技术-",
    "decision": "决策-",
    "plan": "计划-",
    "issue": "问题-",
    "record": "记录-",
}
PROJECT_CURRENT_UNIQUE_TYPES = {"moc", "product-spec"}


@dataclass(frozen=True)
class Domain:
    path: Path
    name: str
    domain_id: str
    parent_domain: str
    moc_name: str
    governance: str = "knowledge-docs"


def load_config(vault_root: Path, config_arg: str) -> dict[str, Any]:
    config_path = Path(config_arg)
    if not config_path.is_absolute():
        config_path = vault_root / config_path
    return json.loads(config_path.read_text(encoding="utf-8"))


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*)$", line)
        if not match:
            continue
        value = match.group(2).strip().strip('"').strip("'")
        values[match.group(1)] = value
    return values


def discover_domains(
    vault_root: Path,
    config: dict[str, Any],
    type_config: dict[str, Any] | None = None,
    schema: dict[str, Any] | None = None,
) -> tuple[list[Domain], list[dict[str, str]]]:
    marker_name = config.get("domain_marker", "_领域.md")
    ignored = set(config.get("ignored_directories", []))
    domains: list[Domain] = []
    issues: list[dict[str, str]] = []

    for relative_root in config.get("managed_roots", []):
        managed_root = (vault_root / relative_root).resolve()
        if not managed_root.exists():
            issues.append({"code": "managed-root-missing", "path": relative_root})
            continue
        all_dirs = sorted([managed_root, *[p for p in managed_root.rglob("*") if p.is_dir()]])
        project_reserved_paths: set[Path] = set()
        reserved_names = project_reserved_directories(config)
        for directory in all_dirs:
            marker = directory / marker_name
            if marker.exists() and parse_frontmatter(marker).get("governance") == "project-docs":
                for child in directory.rglob("*"):
                    if child.is_dir() and (
                        child.name in reserved_names
                        or any(
                            part in reserved_names for part in child.relative_to(directory).parts
                        )
                    ):
                        project_reserved_paths.add(child)
        for directory in all_dirs:
            relative_parts = directory.relative_to(vault_root).parts
            if any(part in ignored for part in relative_parts):
                continue
            marker = directory / marker_name
            markdown_files = [p for p in directory.glob("*.md") if p.name != marker_name]
            child_directories = [
                p for p in directory.iterdir() if p.is_dir() and p.name not in ignored
            ]
            if not marker.exists():
                if directory in project_reserved_paths:
                    continue
                if markdown_files or child_directories:
                    issues.append(
                        {
                            "code": "undeclared-directory",
                            "path": str(directory.relative_to(vault_root)),
                        }
                    )
                continue
            meta = parse_frontmatter(marker)
            required = ("name", "domain_id", "domain_type", "governance", "moc")
            for field in required:
                if not meta.get(field):
                    issues.append(
                        {
                            "code": "domain-field-missing",
                            "path": str(marker.relative_to(vault_root)),
                            "detail": field,
                        }
                    )
            moc_name = meta.get("moc", "").replace("[[", "").replace("]]", "")
            domain = Domain(
                path=directory,
                name=meta.get("name", directory.name),
                domain_id=meta.get("domain_id", ""),
                parent_domain=meta.get("parent_domain", ""),
                moc_name=moc_name,
                governance=meta.get("governance", "knowledge-docs"),
            )
            domains.append(domain)
            if moc_name:
                moc_path = directory / f"{moc_name}.md"
                if not moc_path.exists():
                    issues.append(
                        {"code": "moc-missing", "path": str(moc_path.relative_to(vault_root))}
                    )
                else:
                    text = moc_path.read_text(encoding="utf-8")
                    if text.count(START_MARKER) != 1 or text.count(END_MARKER) != 1:
                        issues.append(
                            {
                                "code": "moc-markers-invalid",
                                "path": str(moc_path.relative_to(vault_root)),
                            }
                        )
            for note in markdown_files:
                if note.stem.lower() in {"未命名", "untitled", "new note"}:
                    issues.append(
                        {"code": "untitled-note", "path": str(note.relative_to(vault_root))}
                    )

    ids = {domain.domain_id for domain in domains if domain.domain_id}
    seen: set[str] = set()
    for domain in domains:
        if domain.domain_id in seen:
            issues.append(
                {
                    "code": "duplicate-domain-id",
                    "path": str(domain.path.relative_to(vault_root)),
                    "detail": domain.domain_id,
                }
            )
        seen.add(domain.domain_id)
        if domain.parent_domain and domain.parent_domain not in ids:
            issues.append(
                {
                    "code": "parent-domain-missing",
                    "path": str(domain.path.relative_to(vault_root)),
                    "detail": domain.parent_domain,
                }
            )
        if domain.governance == "project-docs":
            issues.extend(check_project_docs(domain, config, vault_root, type_config, schema))
    return domains, issues


def managed_markdown_files(vault_root: Path, config: dict[str, Any]) -> list[Path]:
    ignored = set(config.get("ignored_directories", []))
    files: set[Path] = set()
    for relative_root in config.get("managed_roots", []):
        managed_root = (vault_root / relative_root).resolve()
        if not managed_root.exists():
            continue
        for path in managed_root.rglob("*.md"):
            relative_parts = path.relative_to(vault_root).parts
            if any(part in ignored for part in relative_parts):
                continue
            files.add(path)
    return sorted(files)


def build_vault_file_index(vault_root: Path) -> tuple[dict[str, list[Path]], dict[str, Path]]:
    by_stem: dict[str, list[Path]] = defaultdict(list)
    by_relative: dict[str, Path] = {}
    for path in vault_root.rglob("*"):
        if not path.is_file() or ".git" in path.relative_to(vault_root).parts:
            continue
        relative = path.relative_to(vault_root)
        by_stem[path.stem].append(path)
        by_relative[str(relative)] = path
        by_relative[str(relative.with_suffix(""))] = path
    return by_stem, by_relative


def resolve_wikilink(
    target: str,
    source: Path,
    vault_root: Path,
    by_stem: dict[str, list[Path]],
    by_relative: dict[str, Path],
) -> tuple[str, list[Path]]:
    cleaned = unquote(target.strip()).replace("\\", "/")
    if not cleaned:
        return "valid", []
    if "/" in cleaned:
        candidates = []
        source_relative = source.parent.relative_to(vault_root)
        for value in (
            cleaned,
            f"{cleaned}.md",
            str(source_relative / cleaned),
            str(source_relative / f"{cleaned}.md"),
        ):
            normalized = os.path.normpath(value)
            if normalized in by_relative:
                candidates.append(by_relative[normalized])
        unique = sorted(set(candidates))
    else:
        stem = cleaned[:-3] if cleaned.lower().endswith(".md") else cleaned
        unique = sorted(set(by_stem.get(stem, [])))
    if not unique:
        return "missing", []
    if len(unique) > 1:
        return "ambiguous", unique
    return "valid", unique


def resolve_markdown_link(target: str, source: Path, vault_root: Path) -> bool:
    cleaned = unquote(target.strip().strip("<>").split("#", 1)[0])
    if not cleaned or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", cleaned) or cleaned.startswith("//"):
        return True
    candidate = (
        (vault_root / cleaned.lstrip("/")) if cleaned.startswith("/") else (source.parent / cleaned)
    )
    return candidate.exists()


def check_links(vault_root: Path, sources: list[Path]) -> list[dict[str, str]]:
    by_stem, by_relative = build_vault_file_index(vault_root)
    issues: list[dict[str, str]] = []
    for source in sources:
        text = source.read_text(encoding="utf-8")
        text = INLINE_CODE_RE.sub("", FENCED_CODE_RE.sub("", text))
        for target in WIKILINK_RE.findall(text):
            status, candidates = resolve_wikilink(target, source, vault_root, by_stem, by_relative)
            if status == "missing":
                issues.append(
                    {
                        "code": "wikilink-missing",
                        "path": str(source.relative_to(vault_root)),
                        "detail": target,
                    }
                )
            elif status == "ambiguous":
                detail = f"{target} -> " + ", ".join(
                    str(path.relative_to(vault_root)) for path in candidates[:5]
                )
                issues.append(
                    {
                        "code": "wikilink-ambiguous",
                        "path": str(source.relative_to(vault_root)),
                        "detail": detail,
                    }
                )
        for target in MARKDOWN_LINK_RE.findall(text):
            if not resolve_markdown_link(target, source, vault_root):
                issues.append(
                    {
                        "code": "markdown-link-missing",
                        "path": str(source.relative_to(vault_root)),
                        "detail": target,
                    }
                )
    return issues


def project_reserved_directories(config: dict[str, Any]) -> set[str]:
    return set(config.get("project_reserved_directories", ["记录", "archive", "_总览", "a_skill"]))


def check_project_docs(
    domain: Domain,
    config: dict[str, Any],
    vault_root: Path | None = None,
    type_config: dict[str, Any] | None = None,
    schema: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """校验 project-docs 领域内文档的 frontmatter 契约与命名前缀。"""
    issues: list[dict[str, str]] = []
    project_doc_types = PROJECT_DOC_TYPES
    required_fields: set[str] = set()
    enum_rules: dict[str, list[str]] = {}
    if type_config is not None:
        configured = profile_mapping(type_config, "project-docs")
        if configured:
            project_doc_types = configured
    if schema is not None:
        for rules in (
            schema.get("base", {}),
            schema.get("profiles", {}).get("project-docs", {}),
        ):
            required_fields.update(rules.get("required", []))
            enum_rules.update(rules.get("enums", {}))
    reserved = project_reserved_directories(config) | set(config.get("ignored_directories", []))
    exempt = set()
    if vault_root is not None:
        for raw in config.get("project_doc_exempt_files", []):
            exempt.add(str((vault_root / raw).resolve()))
    docs = [
        p
        for p in domain.path.glob("*.md")
        if p.name
        not in {
            config.get("domain_marker", "_领域.md"),
            f"{domain.moc_name}.md",
            "README.md",
            "CLAUDE.md",
        }
    ]
    current_keys: dict[tuple[str, str, str], list[str]] = {}
    for doc in docs:
        rel = str(doc.relative_to(domain.path))
        if vault_root is not None and str(doc.resolve()) in exempt:
            continue
        meta = parse_frontmatter(doc)
        if not meta:
            issues.append({"code": "project-doc-frontmatter-missing", "path": rel})
            continue
        for field in required_fields:
            if field not in meta:
                issues.append({"code": "project-doc-field-missing", "path": rel, "detail": field})
        doc_type = meta.get("type", "")
        if doc_type and doc_type not in project_doc_types:
            issues.append({"code": "project-doc-type-invalid", "path": rel, "detail": doc_type})
        elif doc_type in project_doc_types and not doc.name.startswith(project_doc_types[doc_type]):
            issues.append({"code": "project-doc-prefix-mismatch", "path": rel, "detail": doc_type})
        status = meta.get("status", "")
        if status and enum_rules.get("status") and status not in enum_rules["status"]:
            issues.append({"code": "project-doc-status-invalid", "path": rel, "detail": status})
        lifecycle = meta.get("lifecycle", "")
        if lifecycle and enum_rules.get("lifecycle") and lifecycle not in enum_rules["lifecycle"]:
            issues.append(
                {"code": "project-doc-lifecycle-invalid", "path": rel, "detail": lifecycle}
            )
        if status == "archived" and lifecycle != "archived":
            issues.append({"code": "project-doc-archived-lifecycle-invalid", "path": rel})
        if (
            doc_type in PROJECT_CURRENT_UNIQUE_TYPES
            and status == "current"
            and meta.get("project")
            and meta.get("domain")
        ):
            key = (meta["project"], meta["domain"], doc_type)
            current_keys.setdefault(key, []).append(rel)
    for (project, doc_domain, doc_type), paths in sorted(current_keys.items()):
        if len(paths) > 1:
            issues.append(
                {
                    "code": "project-doc-current-conflict",
                    "path": domain.path.name,
                    "detail": f"{project}/{doc_domain}/{doc_type}: " + ", ".join(sorted(paths)),
                }
            )
    for child in sorted(p for p in domain.path.iterdir() if p.is_dir()):
        if child.name in reserved:
            continue
        if not (child / config.get("domain_marker", "_领域.md")).exists() and any(
            child.glob("*.md")
        ):
            issues.append(
                {
                    "code": "undeclared-directory",
                    "path": str(child.relative_to(domain.path.parent.parent)),
                }
            )
    return issues


def build_result(vault_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    domains, issues = discover_domains(vault_root, config)
    link_issues = check_links(vault_root, managed_markdown_files(vault_root, config))
    issues.extend(link_issues)
    inbox = vault_root / config.get("inbox", "_收件箱")
    inbox_files = (
        sorted(
            str(p.relative_to(vault_root))
            for p in inbox.rglob("*")
            if p.is_file() and p.name != ".gitkeep"
        )
        if inbox.exists()
        else []
    )
    if not inbox.exists():
        issues.append({"code": "inbox-missing", "path": str(inbox.relative_to(vault_root))})
    return {
        "status": "ok" if not issues else "issues-found",
        "domain_count": len(domains),
        "inbox_count": len(inbox_files),
        "inbox_files": inbox_files,
        "link_issue_count": len(link_issues),
        "domains": [
            {
                "domain_id": d.domain_id,
                "name": d.name,
                "path": str(d.path.relative_to(vault_root)),
                "parent_domain": d.parent_domain,
                "moc": d.moc_name,
            }
            for d in sorted(domains, key=lambda item: item.domain_id)
        ],
        "issues": issues,
    }


def print_result(result: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"治理状态：{result['status']}")
    print(f"正式领域：{result['domain_count']}")
    print(f"收件箱文件：{result['inbox_count']}")
    print(f"链接问题：{result['link_issue_count']}")
    print(f"治理问题：{len(result['issues'])}")
    for issue in result["issues"]:
        detail = f" ({issue['detail']})" if issue.get("detail") else ""
        print(f"- {issue['code']}: {issue['path']}{detail}")
