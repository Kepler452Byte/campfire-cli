"""
SPEC:
  name: migration_check
  purpose: 使用迁移映射校验文档迁移前后的内容哈希和路径状态
  default_env_file: none
  env_override: none
  idempotent: true
  behavior:
    - before 阶段输出源文件 SHA-256 基线
    - after 阶段校验目标文件与基线内容一致
  safety:
    - 不修改、移动或删除任何文件
    - 所有映射路径必须位于 Vault 根目录内
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_path(vault_root: Path, relative: str) -> Path:
    resolved_root = vault_root.resolve()
    candidate = (resolved_root / relative).resolve()
    candidate.relative_to(resolved_root)
    return candidate


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def before(
    vault_root: Path, mapping: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    records: list[dict[str, str]] = []
    issues: list[dict[str, str]] = []
    seen_targets: set[str] = set()
    for item in mapping.get("items", []):
        source_name = item["source"]
        target_name = item["target"]
        source = safe_path(vault_root, source_name)
        target = safe_path(vault_root, target_name)
        if target_name in seen_targets:
            issues.append({"code": "duplicate-target", "path": target_name})
        seen_targets.add(target_name)
        if not source.is_file():
            issues.append({"code": "source-missing", "path": source_name})
            continue
        if target.exists() and target != source:
            issues.append({"code": "target-exists", "path": target_name})
        records.append(
            {
                "source": source_name,
                "target": target_name,
                "sha256": sha256(source),
                "size": str(source.stat().st_size),
            }
        )
    return {"version": 1, "items": records}, issues


def after(vault_root: Path, baseline: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for item in baseline.get("items", []):
        source = safe_path(vault_root, item["source"])
        target = safe_path(vault_root, item["target"])
        if source.exists() and source != target:
            issues.append({"code": "source-still-exists", "path": item["source"]})
        if not target.is_file():
            issues.append({"code": "target-missing", "path": item["target"]})
            continue
        if sha256(target) != item["sha256"]:
            issues.append({"code": "content-hash-mismatch", "path": item["target"]})
        if str(target.stat().st_size) != str(item["size"]):
            issues.append({"code": "content-size-mismatch", "path": item["target"]})
    return issues
