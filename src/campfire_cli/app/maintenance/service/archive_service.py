"""
SPEC:
  name: project_archive
  purpose: 检查并执行项目文档的显式两阶段归档请求
  default_env_file: none
  env_override: none
  idempotent: true
  behavior:
    - check 模式只读列出归档请求、路径状态和阻塞问题
    - apply 模式只移动校验通过的请求到同领域扁平 archive 目录
    - 完成归档时统一 status、lifecycle、archive_requested 和 archived_at
  safety:
    - 不依据更新时间自动归档
    - 不覆盖同名目标，不删除文档，不处理治理范围外文件
    - 缺少归档原因或必要替代文档时拒绝执行该文档
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from campfire_cli.app.workspace.service.structure_service import (
    DomainService,
)
from campfire_cli.app.workspace.service.structure_service import (
    parse_marker as parse_frontmatter,
)
from campfire_cli.config.defaults import builtin_config


@dataclass(frozen=True)
class ArchiveItem:
    source: Path
    target: Path
    domain: Path
    in_archive: bool


def is_true(value: str) -> bool:
    return value.strip().lower() == "true"


def list_has_values(value: str) -> bool:
    compact = value.strip()
    return bool(compact and compact not in {"[]", "null", "~"})


def frontmatter_list_has_values(text: str, key: str, parsed_value: str) -> bool:
    if list_has_values(parsed_value):
        return True
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---\n", 4)
    if end < 0:
        return False
    lines = text[4:end].splitlines()
    for index, line in enumerate(lines):
        if not re.match(rf"^{re.escape(key)}:\s*$", line):
            continue
        for following in lines[index + 1 :]:
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_-]*:", following):
                break
            if re.match(r"^\s+-\s+\S", following):
                return True
    return False


def is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def project_domains(vault_root: Path, config: dict[str, Any]) -> list[Path]:
    domains, _ = DomainService(vault_root, vault_root).discover()
    return sorted(
        (item.path for item in domains if item.governance == "project-docs"),
        key=lambda path: (len(path.parts), str(path)),
    )


def owning_domain(path: Path, domains: list[Path]) -> Path | None:
    matches = [domain for domain in domains if is_under(path, domain)]
    return max(matches, key=lambda item: len(item.parts)) if matches else None


def collect_items(
    vault_root: Path, config: dict[str, Any]
) -> tuple[list[ArchiveItem], list[dict[str, str]]]:
    domains = project_domains(vault_root, config)
    policy = builtin_config("archive-policy.json")
    archive_reasons = set(policy["reasons"])
    reasons_requiring_successor = set(policy["reasons_requiring_successor"])
    marker_name = config.get("domain_marker", "_领域.md")
    ignored = set(config.get("ignored_directories", [])) - {"archive", "记录"}
    items: list[ArchiveItem] = []
    issues: list[dict[str, str]] = []

    for domain in domains:
        for doc in domain.rglob("*.md"):
            if (
                owning_domain(doc, domains) != domain
                or doc.name == marker_name
                or doc.name.startswith("MOC-")
            ):
                continue
            relative_to_domain = doc.relative_to(domain)
            if any(part in ignored for part in relative_to_domain.parts):
                continue
            in_archive = "archive" in relative_to_domain.parts[:-1]
            meta = parse_frontmatter(doc)
            requested = is_true(meta.get("archive_requested", "false")) if meta else False
            if not requested and not in_archive:
                continue
            target = doc if in_archive else domain / "archive" / doc.name
            item = ArchiveItem(doc, target, domain, in_archive)
            items.append(item)
            rel = str(doc.relative_to(vault_root))

            if not meta:
                issues.append({"code": "archive-frontmatter-missing", "path": rel})
                continue
            raw_text = doc.read_text(encoding="utf-8")
            reason = meta.get("archive_reason", "")
            if not reason:
                issues.append({"code": "archive-reason-missing", "path": rel})
            elif reason not in archive_reasons:
                issues.append({"code": "archive-reason-invalid", "path": rel, "detail": reason})
            if reason in reasons_requiring_successor and not frontmatter_list_has_values(
                raw_text, "superseded_by", meta.get("superseded_by", "")
            ):
                issues.append({"code": "archive-successor-missing", "path": rel})
            if not in_archive and target.exists():
                issues.append(
                    {
                        "code": "archive-target-exists",
                        "path": rel,
                        "detail": str(target.relative_to(vault_root)),
                    }
                )
            if in_archive:
                if meta.get("status") != "archived" or meta.get("lifecycle") != "archived":
                    issues.append({"code": "archive-path-state-mismatch", "path": rel})
            elif meta.get("status") == "archived" or meta.get("lifecycle") == "archived":
                issues.append({"code": "archive-request-state-premature", "path": rel})
    return sorted(items, key=lambda item: str(item.source)), issues


def issue_paths(issues: list[dict[str, str]]) -> set[str]:
    return {item["path"] for item in issues}


def replace_frontmatter_fields(text: str, values: dict[str, str]) -> str:
    if not text.startswith("---\n"):
        raise ValueError("frontmatter missing")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("frontmatter closing marker missing")
    body = text[4:end]
    lines = body.splitlines()
    positions: dict[str, int] = {}
    for index, line in enumerate(lines):
        match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*):", line)
        if match:
            positions[match.group(1)] = index
    for key, value in values.items():
        rendered = f"{key}: {value}"
        if key in positions:
            lines[positions[key]] = rendered
        else:
            lines.append(rendered)
    return "---\n" + "\n".join(lines) + text[end:]


def apply_items(
    vault_root: Path, items: list[ArchiveItem], issues: list[dict[str, str]], archived_at: str
) -> list[dict[str, str]]:
    applied: list[dict[str, str]] = []
    for item in items:
        rel = str(item.source.relative_to(vault_root))
        # A path/state mismatch is repairable after an explicit manual move.
        # Other issues block the document.
        item_issues = [issue for issue in issues if issue["path"] == rel]
        if any(issue["code"] != "archive-path-state-mismatch" for issue in item_issues):
            continue
        current_meta = parse_frontmatter(item.source)
        if (
            item.in_archive
            and current_meta.get("status") == "archived"
            and current_meta.get("lifecycle") == "archived"
            and not is_true(current_meta.get("archive_requested", "false"))
            and current_meta.get("archived_at")
        ):
            continue
        effective_archived_at = current_meta.get("archived_at") or archived_at
        updated = replace_frontmatter_fields(
            item.source.read_text(encoding="utf-8"),
            {
                "status": "archived",
                "lifecycle": "archived",
                "archive_requested": "false",
                "archived_at": effective_archived_at,
            },
        )
        if item.in_archive:
            item.source.write_text(updated, encoding="utf-8")
            action = "normalized"
        else:
            item.target.parent.mkdir(parents=True, exist_ok=True)
            item.target.write_text(updated, encoding="utf-8")
            item.source.unlink()
            action = "archived"
        applied.append(
            {
                "action": action,
                "source": rel,
                "target": str(item.target.relative_to(vault_root)),
            }
        )
    return applied


def build_result(
    vault_root: Path, config: dict[str, Any], apply: bool, archived_at: str
) -> dict[str, Any]:
    vault_root = vault_root.resolve()
    items, issues = collect_items(vault_root, config)
    applied = apply_items(vault_root, items, issues, archived_at) if apply else []
    return {
        "status": "issues-found" if issues else ("applied" if apply else "ok"),
        "mode": "apply" if apply else "check",
        "candidate_count": len(items),
        "applied_count": len(applied),
        "candidates": [
            {
                "source": str(item.source.relative_to(vault_root)),
                "target": str(item.target.relative_to(vault_root)),
                "already_in_archive": item.in_archive,
            }
            for item in items
        ],
        "applied": applied,
        "issues": issues,
    }
