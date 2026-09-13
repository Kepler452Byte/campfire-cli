from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from campfire_cli.common.hashing import file_sha256


def capture_snapshot(root: Path, paths: Iterable[Path]) -> dict[str, str | None]:
    root = root.resolve()
    result: dict[str, str | None] = {}
    for path in sorted({item.resolve() for item in paths}):
        relative = path.relative_to(root).as_posix()
        result[relative] = file_sha256(path) if path.is_file() else None
    return result


def snapshot_changes(root: Path, snapshot: dict[str, str | None]) -> list[str]:
    changes: list[str] = []
    for relative, expected in snapshot.items():
        key = Path(relative)
        path = key if key.is_absolute() else root / key
        actual = file_sha256(path) if path.is_file() else None
        if actual != expected:
            changes.append(relative)
    return changes
