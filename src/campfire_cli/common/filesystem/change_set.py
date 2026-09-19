from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path

from campfire_cli.common.exceptions import AppError, GovernanceBlockedError
from campfire_cli.common.filesystem.atomic import atomic_write, atomic_write_bytes
from campfire_cli.common.governance import capture_snapshot, optimistic_write_lock


@dataclass(frozen=True)
class FileWrite:
    path: Path
    content: str


@dataclass(frozen=True)
class PathMove:
    source: Path
    target: Path


@dataclass(frozen=True)
class FileChangeSet:
    writes: tuple[FileWrite, ...] = ()
    deletes: tuple[Path, ...] = ()
    moves: tuple[PathMove, ...] = ()
    remove_empty_directories: tuple[Path, ...] = ()
    label: str = "write"
    expected: dict[Path, str | None] = field(default_factory=dict)

    @property
    def paths(self) -> tuple[Path, ...]:
        return tuple(
            dict.fromkeys(
                [
                    *(item.path for item in self.writes),
                    *self.deletes,
                    *(item.source for item in self.moves),
                    *(item.target for item in self.moves),
                    *self.remove_empty_directories,
                ]
            )
        )


class FileChangeExecutor:
    """Execute a precomputed change set under one optimistic lock with rollback."""

    def __init__(self, vault_root: Path, state_root: Path) -> None:
        self._vault_root = vault_root
        self._state_root = state_root

    def execute(
        self, changes: FileChangeSet, *, before_write: Callable[[], None] | None = None
    ) -> None:
        with self.transaction(changes, before_write=before_write):
            pass

    @contextmanager
    def transaction(
        self, changes: FileChangeSet, *, before_write: Callable[[], None] | None = None
    ) -> Iterator[None]:
        """Apply a change set and roll it back if a coordinated commit step fails."""

        self._validate_paths(changes)
        snapshot = capture_snapshot(self._vault_root, changes.paths)
        for path, digest in changes.expected.items():
            snapshot[path.resolve().relative_to(self._vault_root.resolve()).as_posix()] = digest
        with optimistic_write_lock(self._state_root, snapshot, self._vault_root) as concurrent:
            if concurrent:
                raise GovernanceBlockedError(
                    f"文件在 {changes.label} 期间发生变化：" + ", ".join(concurrent)
                )
            if before_write is not None:
                before_write()
            self._validate_moves(changes.moves)
            completed_moves: list[PathMove] = []
            created_directories: list[Path] = []
            removed_directories: list[Path] = []
            originals: dict[Path, bytes | None] = {}
            try:
                for move in changes.moves:
                    created_directories.extend(self._create_parents(move.target.parent))
                    move.source.rename(move.target)
                    completed_moves.append(move)
                content_paths = tuple(
                    dict.fromkeys([*(item.path for item in changes.writes), *changes.deletes])
                )
                originals = {
                    path: path.read_bytes() if path.is_file() else None for path in content_paths
                }
                for item in changes.writes:
                    atomic_write(item.path, item.content)
                for path in changes.deletes:
                    path.unlink(missing_ok=True)
                for path in changes.remove_empty_directories:
                    path.rmdir()
                    removed_directories.append(path)
                yield
            except Exception:
                try:
                    for directory in reversed(removed_directories):
                        directory.mkdir(parents=True, exist_ok=True)
                    self._restore(originals)
                    for move in reversed(completed_moves):
                        if move.target.exists() and not move.source.exists():
                            move.target.rename(move.source)
                    for directory in reversed(created_directories):
                        with suppress(OSError):
                            directory.rmdir()
                except OSError as exc:
                    raise AppError(
                        "文件操作失败且回滚未完成；停止重试并核对来源与目标",
                        code="file-rollback-failed",
                        write_performed=True,
                        paths=[str(path) for path in changes.paths],
                    ) from exc
                raise

    def _validate_paths(self, changes: FileChangeSet) -> None:
        root = self._vault_root.resolve()
        for path in [*changes.paths, *changes.expected]:
            resolved = path.resolve()
            if resolved != root and root not in resolved.parents:
                raise GovernanceBlockedError(f"文件变更路径超出 Vault：{path}")

    @staticmethod
    def _validate_moves(moves: tuple[PathMove, ...]) -> None:
        for move in moves:
            if not move.source.exists():
                raise GovernanceBlockedError(f"移动来源不存在：{move.source}")
            if move.target.exists():
                raise GovernanceBlockedError(f"移动目标已存在：{move.target}")
            if move.source == move.target or move.source in move.target.parents:
                raise GovernanceBlockedError("移动目标不能与来源相同或位于来源内部")

    @staticmethod
    def _create_parents(parent: Path) -> list[Path]:
        missing: list[Path] = []
        current = parent
        while not current.exists():
            missing.append(current)
            current = current.parent
        parent.mkdir(parents=True, exist_ok=True)
        return list(reversed(missing))

    @staticmethod
    def _restore(originals: dict[Path, bytes | None]) -> None:
        for path, content in originals.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write_bytes(path, content)
