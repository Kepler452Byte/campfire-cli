"""Shared helpers for the Vault-wide single-select document type contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

FRONTMATTER_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$")


def safe_path(root: Path, relative: str) -> Path:
    root = root.resolve()
    path = (root / relative).resolve()
    path.relative_to(root)
    return path


def frontmatter_bounds(text: str) -> tuple[int, int] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    return (4, end) if end >= 0 else None


def frontmatter_value(text: str, key: str) -> tuple[str | None, bool]:
    """Return scalar value and whether the key is represented as a YAML sequence."""
    bounds = frontmatter_bounds(text)
    if not bounds:
        return None, False
    lines = text[bounds[0] : bounds[1]].splitlines()
    for index, line in enumerate(lines):
        match = FRONTMATTER_KEY_RE.match(line)
        if not match or match.group(1) != key:
            continue
        value = (match.group(2) or "").strip().strip('"').strip("'")
        sequence = value.startswith("[")
        if not value:
            for following in lines[index + 1 :]:
                if FRONTMATTER_KEY_RE.match(following):
                    break
                if re.match(r"^\s+-\s+", following):
                    sequence = True
                    break
        return value or None, sequence
    return None, False


def set_frontmatter_scalar(text: str, key: str, value: str) -> str:
    bounds = frontmatter_bounds(text)
    if not bounds:
        return f"---\n{key}: {value}\n---\n\n{text}"
    lines = text[bounds[0] : bounds[1]].splitlines()
    output: list[str] = []
    replaced = False
    skipping_sequence = False
    for line in lines:
        match = FRONTMATTER_KEY_RE.match(line)
        if match:
            skipping_sequence = False
            if match.group(1) == key:
                if not replaced:
                    output.append(f"{key}: {value}")
                    replaced = True
                skipping_sequence = not (match.group(2) or "").strip()
                continue
        if skipping_sequence and re.match(r"^\s+-\s+", line):
            continue
        output.append(line)
    if not replaced:
        output.append(f"{key}: {value}")
    return "---\n" + "\n".join(output) + text[bounds[1] :]


def prefix_type(filename: str, config: dict[str, Any]) -> str | None:
    matches = [
        name for name, item in config["types"].items() if filename.startswith(item["prefix"])
    ]
    return matches[0] if len(matches) == 1 else None


def prefixed_name(filename: str, doc_type: str, config: dict[str, Any]) -> str:
    prefix = config["types"][doc_type]["prefix"]
    known = sorted((item["prefix"] for item in config["types"].values()), key=len, reverse=True)
    stem = filename
    for existing in known:
        if stem.startswith(existing):
            stem = stem[len(existing) :]
            break
    result = prefix + stem
    if config.get("filename_rules", {}).get("flatten_leading_bracket_categories", False):
        result = flatten_leading_bracket_categories(result, prefix)
    return result


def flatten_leading_bracket_categories(filename: str, prefix: str) -> str:
    """Convert PREFIX-【A】【B】Title.md to PREFIX-A-B-Title.md."""
    if not filename.startswith(prefix):
        return filename
    remainder = filename[len(prefix) :]
    categories: list[str] = []
    while True:
        match = re.match(r"^【([^】]+)】\s*", remainder)
        if not match:
            break
        category = match.group(1).strip().strip("-_")
        if category:
            categories.append(category)
        remainder = remainder[match.end() :]
    if not categories:
        return filename
    remainder = remainder.lstrip(" -_")
    parts = [*categories, remainder] if remainder else categories
    return prefix + "-".join(parts)


def profile_mapping(config: dict[str, Any], profile: str) -> dict[str, str]:
    names = config.get("profiles", {}).get(profile, [])
    return {name: config["types"][name]["prefix"] for name in names if name in config["types"]}
