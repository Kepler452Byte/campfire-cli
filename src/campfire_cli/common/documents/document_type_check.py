"""
SPEC:
  name: document_type_check
  purpose: 只读检查 Vault 文档的单选 type 与文件名前缀是否一致
  default_env_file: none
  env_override: none
  idempotent: true
  behavior:
    - 按全局类型契约扫描配置范围
    - 报告缺失、多选、非法 type 和文件名前缀不一致
  safety:
    - 不修改、移动、删除或重命名任何文件
    - 不扫描配置范围外的文档
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from campfire_cli.common.documents.document_types import (
    frontmatter_value,
    iter_documents,
    prefix_type,
    prefixed_name,
)


def check_document(root: Path, path: Path, config: dict[str, Any]) -> list[dict[str, str]]:
    rel = str(path.relative_to(root))
    text = path.read_text(encoding="utf-8")
    doc_type, multiple = frontmatter_value(text, "type")
    filename_type = prefix_type(path.name, config)
    issues: list[dict[str, str]] = []
    if multiple:
        issues.append({"code": "document-type-multiple", "path": rel})
        return issues
    if not doc_type:
        issues.append({"code": "document-type-missing", "path": rel})
        if not filename_type:
            issues.append({"code": "document-prefix-missing", "path": rel})
        return issues
    if doc_type not in config["types"]:
        issues.append({"code": "document-type-invalid", "path": rel, "detail": doc_type})
        return issues
    if not filename_type:
        issues.append(
            {
                "code": "document-prefix-missing",
                "path": rel,
                "detail": config["types"][doc_type]["prefix"],
            }
        )
    elif filename_type != doc_type:
        issues.append(
            {
                "code": "document-prefix-mismatch",
                "path": rel,
                "detail": f"type={doc_type}, prefix={filename_type}",
            }
        )
    elif prefixed_name(path.name, doc_type, config) != path.name:
        issues.append(
            {
                "code": "document-name-bracket-category",
                "path": rel,
                "detail": prefixed_name(path.name, doc_type, config),
            }
        )
    return issues


def build_result(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve()
    documents = iter_documents(root, config)
    issues = [issue for path in documents for issue in check_document(root, path, config)]
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue["code"]] = counts.get(issue["code"], 0) + 1
    return {
        "status": "ok" if not issues else "issues-found",
        "document_count": len(documents),
        "issue_count": len(issues),
        "issue_counts": dict(sorted(counts.items())),
        "issues": issues,
    }
