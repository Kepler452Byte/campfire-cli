from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from campfire_cli.common.exceptions import GovernanceBlockedError
from campfire_cli.common.filesystem.atomic import atomic_write
from campfire_cli.common.governance import capture_snapshot, optimistic_write_lock


@dataclass(frozen=True)
class FileWrite:
    path: Path
    content: str


@dataclass(frozen=True)
class FileChangeSet:
    writes: tuple[FileWrite, ...]
    deletes: tuple[Path, ...] = ()
    label: str = "write"
    expected: dict[Path, str | None] = field(default_factory=dict)

    @property
    def paths(self) -> tuple[Path, ...]:
        return tuple(dict.fromkeys([*(item.path for item in self.writes), *self.deletes]))


class FileChangeExecutor:
    """Execute a precomputed change set under one optimistic lock with rollback."""

    def __init__(self, vault_root: Path, state_root: Path) -> None:
        self._vault_root = vault_root
        self._state_root = state_root

    def execute(self, changes: FileChangeSet) -> None:
        snapshot = capture_snapshot(self._vault_root, changes.paths)
        for path, digest in changes.expected.items():
            snapshot[path.resolve().relative_to(self._vault_root.resolve()).as_posix()] = digest
        with optimistic_write_lock(self._state_root, snapshot, self._vault_root) as concurrent:
            if concurrent:
                raise GovernanceBlockedError(
                    f"文件在 {changes.label} 期间发生变化：" + ", ".join(concurrent)
                )
            originals = {
                path: path.read_text(encoding="utf-8") if path.is_file() else None
                for path in changes.paths
            }
            try:
                for item in changes.writes:
                    atomic_write(item.path, item.content)
                for path in changes.deletes:
                    path.unlink(missing_ok=True)
            except Exception:
                self._restore(originals)
                raise

    @staticmethod
    def _restore(originals: dict[Path, str | None]) -> None:
        for path, content in originals.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, content)
