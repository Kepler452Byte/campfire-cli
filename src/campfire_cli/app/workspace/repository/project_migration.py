"""Translate version-one registry data at explicit upgrade and import boundaries."""

from __future__ import annotations

from typing import Any


def migrate_project_records(payload: dict[str, Any], *, portable: bool) -> dict[str, Any]:
    """Return version-two data without retaining legacy Project fields."""
    if payload.get("schema_version", 1) != 1:
        return payload
    migrated = dict(payload)
    projects = []
    for original in payload.get("projects", []):
        project = dict(original)
        if portable and "local_path" in project:
            raise ValueError("Portable Project metadata cannot contain local_path")
        fields = {
            key: project.pop(key)
            for key in ("git_remote_url", "default_branch", "local_path")
            if key in project
        }
        if "repositories" not in project:
            project["repositories"] = [{"id": "default", **fields}]
        projects.append(project)
    migrated.update(schema_version=2, projects=projects)
    return migrated
