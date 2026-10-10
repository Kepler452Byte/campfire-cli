import json
import subprocess

import pytest
from typer.testing import CliRunner

from campfire_cli.app.workspace.service.git_sync_service import GitSyncService
from campfire_cli.common.git import GitCommandError
from campfire_cli.main import app


def git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


@pytest.fixture
def repositories(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "--initial-branch=main", str(remote)],
        check=True,
        capture_output=True,
    )
    clones = []
    for name in ("first", "second"):
        path = tmp_path / name
        subprocess.run(["git", "clone", str(remote), str(path)], check=True, capture_output=True)
        git(path, "config", "user.name", "Sync Tester")
        git(path, "config", "user.email", "sync@example.test")
        clones.append(path)
        if name == "first":
            (path / "note.md").write_text("original\n", encoding="utf-8")
            (path / "delete.md").write_text("delete me\n", encoding="utf-8")
            git(path, "add", ".")
            git(path, "commit", "-m", "initial")
            git(path, "push", "-u", "origin", "main")
    return remote, *clones


def test_sync_full_vault_preview_commit_merge_push_and_idempotency(repositories, tmp_path):
    remote, first, second = repositories
    service = GitSyncService(first, tmp_path / "state")
    (first / "new 附件.txt").write_text("attachment", encoding="utf-8")
    (first / "note.md").write_text("edited", encoding="utf-8")
    (first / "delete.md").unlink()
    (first / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (first / "ignored.txt").write_text("private", encoding="utf-8")
    old_head = git(first, "rev-parse", "HEAD")
    preview = service.sync()
    assert preview["status"] == "ready"
    assert not preview["remote_checked"]
    assert not preview["write_performed"]
    assert "delete.md" in preview["changed_paths"]
    assert "ignored.txt" not in preview["changed_paths"]
    assert git(first, "rev-parse", "HEAD") == old_head
    done = service.sync(confirm=True, expected_plan=preview["expected_plan"])
    assert done["status"] == "synced", done
    assert done["remote_synced"] and done["local_commit"]
    git(second, "pull", "--ff-only")
    assert not (second / "delete.md").exists()
    assert (second / "new 附件.txt").read_text(encoding="utf-8") == "attachment"
    assert not (second / "ignored.txt").exists()
    assert service.sync(confirm=True)["local_commit"] is None
    assert git(first, "rev-parse", "HEAD") == done["head"]
    (second / "remote.md").write_text("remote", encoding="utf-8")
    git(second, "add", ".")
    git(second, "commit", "-m", "remote update")
    git(second, "push")
    fetched = service.sync(confirm=True)
    assert fetched["status"] == "synced"
    assert (first / "remote.md").read_text(encoding="utf-8") == "remote"


def test_sync_divergence_preserves_both_histories(repositories, tmp_path):
    _, first, second = repositories
    (second / "remote.md").write_text("remote")
    git(second, "add", ".")
    git(second, "commit", "-m", "remote")
    git(second, "push")
    (first / "local.md").write_text("local")
    done = GitSyncService(first, tmp_path / "state").sync(confirm=True)
    assert done["status"] == "synced", done
    assert len(git(first, "rev-list", "--parents", "-n", "1", "HEAD").split()) == 3
    git(second, "pull", "--ff-only")
    assert (second / "local.md").read_text() == "local"


def test_sync_conflict_aborts_only_merge_and_keeps_local_commit(repositories, tmp_path):
    _, first, second = repositories
    (second / "note.md").write_text("remote change\n")
    git(second, "add", ".")
    git(second, "commit", "-m", "remote")
    git(second, "push")
    (first / "note.md").write_text("local change\n")
    done = GitSyncService(first, tmp_path / "state").sync(confirm=True)
    assert done["status"] == "blocked"
    assert done["code"] == "merge-conflict"
    assert done["conflict_paths"] == ["note.md"]
    assert done["local_commit"] and not done["remote_synced"]
    assert (first / "note.md").read_text() == "local change\n"
    assert not (first / ".git/MERGE_HEAD").exists()
    assert not git(first, "status", "--porcelain")


def test_sync_rejects_staging_and_changed_plan(repositories, tmp_path):
    _, first, _ = repositories
    service = GitSyncService(first, tmp_path / "state")
    preview = service.sync()
    (first / "note.md").write_text("changed")
    assert (
        service.sync(confirm=True, expected_plan=preview["expected_plan"])["code"] == "plan-changed"
    )
    git(first, "add", ".")
    done = service.sync(confirm=True)
    assert done["status"] == "blocked"
    assert git(first, "diff", "--cached", "--name-only") == "note.md"


def test_sync_push_failure_keeps_local_commit(repositories, tmp_path, monkeypatch):
    _, first, _ = repositories
    import campfire_cli.app.workspace.service.git_sync_service as module

    original = module.run_git

    def fail_push(path, *args):
        if args[0] == "push":
            raise GitCommandError("credentials or concurrent push failure")
        return original(path, *args)

    monkeypatch.setattr(module, "run_git", fail_push)
    (first / "note.md").write_text("saved locally")
    done = GitSyncService(first, tmp_path / "state").sync(confirm=True)
    assert done["code"] == "git-push-failed"
    assert done["local_commit"] == git(first, "rev-parse", "HEAD")
    assert not done["remote_synced"]


def test_sync_detects_external_change_during_fetch(repositories, tmp_path, monkeypatch):
    _, first, _ = repositories
    import campfire_cli.app.workspace.service.git_sync_service as module

    original = module.run_git

    def change_file(path, *args):
        output = original(path, *args)
        if args[0] == "fetch":
            (path / "note.md").write_text("external writer")
        return output

    monkeypatch.setattr(module, "run_git", change_file)
    done = GitSyncService(first, tmp_path / "state").sync(confirm=True)
    assert done["code"] == "local-changed"
    assert done["local_commit"] is None
    assert (first / "note.md").read_text() == "external writer"


def test_sync_non_git_cli_reports_blocked_without_other_side_effects(workspace):
    result = CliRunner().invoke(app, ["workspace", "git", "sync"])
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert not payload["write_performed"]
    assert not (workspace / ".git").exists()


def test_fetch_failure_does_not_commit_or_stage(repositories, tmp_path, monkeypatch):
    _, first, _ = repositories
    import campfire_cli.app.workspace.service.git_sync_service as module

    original = module.run_git

    def fail_fetch(path, *args):
        if args[0] == "fetch":
            raise GitCommandError("offline")
        return original(path, *args)

    monkeypatch.setattr(module, "run_git", fail_fetch)
    (first / "note.md").write_text("offline change")
    head = git(first, "rev-parse", "HEAD")
    done = GitSyncService(first, tmp_path / "state").sync(confirm=True)
    assert done["code"] == "git-fetch-failed"
    assert not done["write_performed"]
    assert git(first, "rev-parse", "HEAD") == head
    assert not git(first, "diff", "--cached", "--name-only")


def test_commit_failure_clears_only_its_staging(repositories, tmp_path, monkeypatch):
    _, first, _ = repositories
    import campfire_cli.app.workspace.service.git_sync_service as module

    original = module.run_git

    def fail_commit(path, *args):
        if args[0] == "commit":
            raise GitCommandError("identity missing")
        return original(path, *args)

    monkeypatch.setattr(module, "run_git", fail_commit)
    (first / "note.md").write_text("preserved change")
    done = GitSyncService(first, tmp_path / "state").sync(confirm=True)
    assert done["code"] == "git-commit-failed"
    assert not git(first, "diff", "--cached", "--name-only")
    assert (first / "note.md").read_text() == "preserved change"


def test_sync_rejects_workspace_lock_and_unfinished_merge(repositories, tmp_path):
    _, first, _ = repositories
    from campfire_cli.common.filesystem.locking import workspace_write_lock

    state = tmp_path / "state"
    service = GitSyncService(first, state)
    with workspace_write_lock(state):
        assert service.sync(confirm=True)["code"] == "workspace-locked"
    (first / ".git/MERGE_HEAD").write_text(git(first, "rev-parse", "HEAD"))
    assert service.sync(confirm=True)["code"] == "unfinished-git-operation"
    assert (first / ".git/MERGE_HEAD").exists()


def test_sync_rejects_push_race_without_overwriting_remote(repositories, tmp_path, monkeypatch):
    _, first, second = repositories
    import campfire_cli.app.workspace.service.git_sync_service as module

    original = module.run_git

    def race(path, *args):
        if args[0] == "push":
            (second / "race.md").write_text("concurrent remote")
            git(second, "add", ".")
            git(second, "commit", "-m", "concurrent")
            git(second, "push")
        return original(path, *args)

    monkeypatch.setattr(module, "run_git", race)
    (first / "local.md").write_text("local")
    service = GitSyncService(first, tmp_path / "state")
    done = service.sync(confirm=True)
    assert done["code"] == "git-push-failed"
    assert done["local_commit"]
    monkeypatch.setattr(module, "run_git", original)
    assert service.sync(confirm=True)["status"] == "synced"
    assert (first / "race.md").read_text() == "concurrent remote"
