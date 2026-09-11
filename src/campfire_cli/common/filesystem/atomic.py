from __future__ import annotations

import os
import tempfile
from pathlib import Path

from campfire_cli.common.exceptions import GovernanceBlockedError


def safe_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise GovernanceBlockedError(f"路径超出 Vault：{relative}")
    return candidate


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
