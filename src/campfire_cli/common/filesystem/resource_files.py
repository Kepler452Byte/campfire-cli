"""Safe file operations with per-file atomic replacement and cooperative locking."""

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from campfire_cli.common.exceptions import GovernanceBlockedError
from campfire_cli.common.filesystem.locking import workspace_write_lock


def safe_path(path: Path) -> Path:
    """Reject symlink ancestors before resolving explicit installation targets."""
    path = path.expanduser().absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise GovernanceBlockedError(
            "Symbolic links are not valid managed targets", code="unsafe-path"
        )
    return path.resolve()


def read_bytes(path: Path) -> bytes | None:
    safe_path(path)
    if path.exists() and not path.is_file():
        raise GovernanceBlockedError("Managed target is not a regular file", code="unsafe-path")
    return path.read_bytes() if path.is_file() else None


def atomic_write(path: Path, content: bytes) -> None:
    safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".agent-")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            os.chmod(name, path.stat().st_mode)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def target_write_lock(root: Path, targets: list[Path] | None = None) -> Iterator[None]:
    """Serialize cooperating writers, including products sharing one Hint file."""
    safe_path(root)
    root.mkdir(parents=True, exist_ok=True)
    locks: list[Path] = []
    locks.extend(
        sorted(
            {
                safe_path(path).with_name("." + path.name + ".agent-write.lock")
                for path in targets or []
            }
        )
    )
    acquired: list[Path] = []
    try:
        for lock in locks:
            safe_path(lock)
            lock.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as exc:
                raise GovernanceBlockedError(
                    "Another resource update holds the lock; retry after it finishes", code="locked"
                ) from exc
            os.close(descriptor)
            acquired.append(lock)
        yield
    finally:
        for lock in reversed(acquired):
            lock.unlink(missing_ok=True)


@contextmanager
def write_lock(root: Path, targets: list[Path] | None = None) -> Iterator[None]:
    with workspace_write_lock(root), target_write_lock(root, targets):
        yield
