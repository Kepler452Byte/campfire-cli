from pathlib import Path

import pytest

from campfire_cli.common.filesystem import (
    FileChangeExecutor,
    FileChangeSet,
    FileWrite,
    PathMove,
)
from campfire_cli.common.filesystem.atomic import atomic_write as real_atomic_write
from campfire_cli.common.hashing import file_sha256


def test_change_set_restores_all_files_when_commit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    vault.mkdir()
    first = vault / "first.md"
    second = vault / "second.md"
    first.write_bytes(b"first-before\r\n")
    second.write_text("second-before\n", encoding="utf-8")
    calls = 0

    def fail_second_write(path: Path, content: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected commit failure")
        real_atomic_write(path, content)

    monkeypatch.setattr("campfire_cli.common.filesystem.change_set.atomic_write", fail_second_write)

    with pytest.raises(OSError, match="injected commit failure"):
        FileChangeExecutor(vault, state).execute(
            FileChangeSet(
                writes=(
                    FileWrite(first, "first-after\n"),
                    FileWrite(second, "second-after\n"),
                )
            )
        )

    assert first.read_bytes() == b"first-before\r\n"
    assert second.read_text(encoding="utf-8") == "second-before\n"


def test_change_set_moves_directory_and_writes_inside_target(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    source = vault / "old"
    source.mkdir(parents=True)
    original = source / "note.md"
    original.write_text("before\n", encoding="utf-8")
    target = vault / "nested/new"

    FileChangeExecutor(vault, state).execute(
        FileChangeSet(
            writes=(FileWrite(target / "note.md", "after\n"),),
            moves=(PathMove(source, target),),
            expected={original: file_sha256(original), target: None},
        )
    )

    assert not source.exists()
    assert (target / "note.md").read_text(encoding="utf-8") == "after\n"


def test_change_set_transaction_restores_move_when_coordinated_step_fails(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    source = vault / "old"
    source.mkdir(parents=True)
    original = source / "note.md"
    original.write_text("before\n", encoding="utf-8")
    target = vault / "nested/new"
    executor = FileChangeExecutor(vault, state)

    with (
        pytest.raises(RuntimeError, match="database failed"),
        executor.transaction(
            FileChangeSet(
                writes=(FileWrite(target / "note.md", "after\n"),),
                moves=(PathMove(source, target),),
                expected={original: file_sha256(original), target: None},
            )
        ),
    ):
        raise RuntimeError("database failed")

    assert original.read_text(encoding="utf-8") == "before\n"
    assert not target.exists()
    assert not (vault / "nested").exists()
