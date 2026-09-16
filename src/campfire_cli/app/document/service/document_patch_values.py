"""Decode explicit Frontmatter assignments against one effective Profile."""

from __future__ import annotations

import json
from typing import Any

from campfire_cli.app.document.service.profile_registry import EffectiveProfile


def decode_patch_values(
    profile: EffectiveProfile,
    raw_values: dict[str, str],
    path: str,
    candidate_sets: dict[str, list[str]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Decode raw assignment values without relying on implicit YAML coercion."""
    values: dict[str, Any] = {}
    issues: list[dict[str, Any]] = []
    for field, raw in raw_values.items():
        expected = _expected_type(profile, field)
        if expected == "boolean":
            if raw not in {"true", "false"}:
                issues.append(_invalid_issue(path, field, raw, expected))
                continue
            values[field] = raw == "true"
            continue
        if expected == "list":
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                value = None
            if not isinstance(value, list):
                issues.append(_invalid_issue(path, field, raw, expected))
                continue
            values[field] = value
            continue
        allowed = _allowed_values(profile, field, expected, candidate_sets)
        if profile.field(field) and profile.field(field).kind == "enum" and raw not in allowed:
            issues.append(
                {
                    **_invalid_issue(path, field, raw, expected),
                    "code": "frontmatter-enum-invalid",
                    "allowed": allowed,
                }
            )
            continue
        values[field] = raw
    return values, issues


def enrich_profile_issues(
    issues: list[dict[str, Any]],
    profile: EffectiveProfile,
    candidate_sets: dict[str, list[str]] | None = None,
) -> None:
    """Attach machine-readable constraints without inventing missing business values."""
    for issue in issues:
        field = issue.get("field")
        if not isinstance(field, str) or field not in profile.allowed:
            continue
        expected = _expected_type(profile, field)
        issue.setdefault("expected_type", expected)
        issue.setdefault("allowed", _allowed_values(profile, field, expected, candidate_sets))
        if issue.get("code") in {
            "frontmatter-date-invalid",
            "frontmatter-list-invalid",
            "frontmatter-type-invalid",
        }:
            issue.setdefault("argument_example", {"--set": _example(field, expected)})


def _expected_type(profile: EffectiveProfile, field: str) -> str:
    if field in profile.lists:
        return "list"
    if field in profile.dates:
        return "date"
    return profile.value_types.get(field, "string")


def _allowed_values(
    profile: EffectiveProfile,
    field: str,
    expected: str,
    candidate_sets: dict[str, list[str]] | None = None,
) -> list[str]:
    rule = profile.field(field)
    if rule and rule.kind == "enum":
        return list(rule.allowed_values(candidate_sets))
    if expected == "date":
        return ["YYYY-MM-DD"]
    return [expected]


def _example(field: str, expected: str) -> str:
    if expected == "boolean":
        return f"{field}=true"
    if expected == "list":
        return f'{field}=["item1","item2"]'
    if expected == "date":
        return f"{field}=YYYY-MM-DD"
    return f"{field}=<value>"


def _invalid_issue(path: str, field: str, actual: str, expected: str) -> dict[str, Any]:
    return {
        "code": ("frontmatter-list-invalid" if expected == "list" else "frontmatter-type-invalid"),
        "path": path,
        "detail": field,
        "field": field,
        "actual": actual,
        "expected_type": expected,
        "allowed": [expected],
        "argument_example": {"--set": _example(field, expected)},
    }
