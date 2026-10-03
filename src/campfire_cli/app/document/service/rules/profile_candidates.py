"""Workspace facts exposed to Profiles as generic candidate sets."""

from __future__ import annotations

from pathlib import Path

import yaml


def workspace_candidate_sets(vault_root: Path) -> dict[str, list[str]]:
    """Read manifest identifiers once; Profile rules never inspect domain topology."""
    manifest = vault_root / ".campfire.yaml"
    if not manifest.is_file():
        return {"workspace.project_ids": []}
    payload = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    projects = payload.get("projects", []) if isinstance(payload, dict) else []
    ids = sorted(
        item["id"]
        for item in projects
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
    )
    return {"workspace.project_ids": ids}
