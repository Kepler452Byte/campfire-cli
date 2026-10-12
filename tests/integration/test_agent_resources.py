import json
from contextlib import contextmanager

import pytest

from campfire_cli.common.exceptions import GovernanceBlockedError
from campfire_cli.container import AppContainer


def test_legacy_adoption_preserves_bytes_and_unmanaged_files(tmp_path):
    service = AppContainer.build_skill()
    target = tmp_path / "agent-skills" / "campfire-context-bootstrap"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_bytes(b"---\nname: campfire-context-bootstrap\n---\nold\n")
    user = target / "user.bin"
    user.write_bytes(b"\x00user\xff")
    hint = tmp_path / "agent-hints"
    prefix = b"user\r\n<!-- other:start -->other<!-- other:end -->\r\n"
    suffix = b"\r\nuser suffix\r\n"
    hint.write_bytes(
        prefix + b"<!-- campfire:agent-hints:start -->old<!-- campfire:agent-hints:end -->" + suffix
    )
    result = service.align()
    assert result["skills"]["status"] == "synced"
    assert len(result["skills"]["adopted"]) >= 2
    assert hint.read_bytes().startswith(prefix)
    assert hint.read_bytes().endswith(suffix)
    assert user.read_bytes() == b"\x00user\xff"
    assert service.align()["skills"]["operations"] == []
    registry = json.loads(service.registry_path.read_bytes())
    assert all(set(item) == {"path", "kind"} for item in registry["files"])


@pytest.mark.parametrize(
    "markers",
    [
        b"<!-- campfire:agent-hints:start -->",
        b"<!-- campfire:agent-hints:end -->",
        b"<!-- campfire:agent-hints:end --><!-- campfire:agent-hints:start -->",
        b"<!-- campfire:agent-hints:start --><!-- campfire:agent-hints:start -->"
        b"<!-- campfire:agent-hints:end -->",
    ],
)
def test_invalid_markers_write_nothing(tmp_path, markers):
    hint = tmp_path / "agent-hints"
    hint.write_bytes(markers)
    with pytest.raises(GovernanceBlockedError, match="markers"):
        AppContainer.build_skill().align()
    assert hint.read_bytes() == markers
    assert not (tmp_path / "agent-skills").exists()


def test_foreign_skill_is_not_overwritten(tmp_path):
    target = tmp_path / "agent-skills" / "campfire-context-bootstrap" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"---\nname: other-product\n---\n")
    result = AppContainer.build_skill().align()
    assert result["skills"]["status"] == "blocked"
    assert result["skills"]["completed_operations"] == []
    assert target.read_bytes() == b"---\nname: other-product\n---\n"


def test_registered_removed_assets_and_target_changes(tmp_path, monkeypatch):
    service = AppContainer.build_skill()
    assert service.align()["skills"]["status"] == "synced"
    original_assets = service.repository.assets
    removed = "campfire-context-bootstrap/SKILL.md"
    monkeypatch.setattr(
        service.repository,
        "assets",
        lambda names: {
            path: content for path, content in original_assets(names).items() if path != removed
        },
    )
    user = tmp_path / "agent-skills" / "campfire-context-bootstrap" / "custom.txt"
    user.write_bytes(b"user")
    assert service.align()["skills"]["status"] == "synced"
    assert not (tmp_path / "agent-skills" / removed).exists()
    assert user.read_bytes() == b"user"
    monkeypatch.setenv("CAMPFIRE_SKILL_TARGETS", str(tmp_path / "new skills"))
    service = AppContainer.build_skill()
    assert service.align()["skills"]["status"] == "synced"
    assert (tmp_path / "new skills" / removed).is_file()
    assert service.align()["skills"]["operations"] == []


def test_concurrent_change_is_rejected(tmp_path, monkeypatch):
    service = AppContainer.build_skill()
    hint = tmp_path / "agent-hints"

    @contextmanager
    def change_before_lock(targets):
        hint.write_bytes(b"external edit")
        yield

    monkeypatch.setattr(service.repository, "lock", change_before_lock)
    result = service.align()["skills"]
    assert result["status"] == "blocked"
    assert result["issues"][0]["code"] == "concurrent-change"
    assert result["completed_operations"] == []
    assert hint.read_bytes() == b"external edit"


def test_partial_io_failure_is_reported(tmp_path, monkeypatch):
    service = AppContainer.build_skill()
    write = service.repository.write
    count = 0

    def fail_after_one(path, content):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("disk failure")
        write(path, content)

    monkeypatch.setattr(service.repository, "write", fail_after_one)
    result = service.align()["skills"]
    assert result["status"] == "blocked"
    assert len(result["completed_operations"]) == 1
    assert result["issues"][0]["code"] == "resource-write-failed"


def test_symlink_target_is_rejected(tmp_path, monkeypatch):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation is unavailable")
    monkeypatch.setenv("CAMPFIRE_SKILL_TARGETS", str(link))
    with pytest.raises(GovernanceBlockedError):
        AppContainer.build_skill().align()
    assert list(actual.iterdir()) == []


def test_internal_state_target_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("CAMPFIRE_SKILL_TARGETS", str(tmp_path / "campfire-home" / "skills"))
    with pytest.raises(GovernanceBlockedError) as error:
        AppContainer.build_skill().align()
    assert error.value.code == "unsafe-path"
    assert not (tmp_path / "campfire-home").exists()
