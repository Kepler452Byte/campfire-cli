"""Fingerprint a complete file change set without retaining session state."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from campfire_cli.common.filesystem.change_set import FileChangeSet


def plan_digest(root: Path, changes: FileChangeSet) -> str:
    payload = {
        "expected": sorted(
            (p.relative_to(root).as_posix(), h) for p, h in changes.expected.items()
        ),
        "writes": sorted(
            (w.path.relative_to(root).as_posix(), hashlib.sha256(w.content.encode()).hexdigest())
            for w in changes.writes
        ),
        "moves": sorted(
            (m.source.relative_to(root).as_posix(), m.target.relative_to(root).as_posix())
            for m in changes.moves
        ),
        "deletes": sorted(p.relative_to(root).as_posix() for p in changes.deletes),
        "directories": sorted(
            p.relative_to(root).as_posix() for p in changes.remove_empty_directories
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
