from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts/release_check.py"
spec = importlib.util.spec_from_file_location("release_check", SCRIPT)
assert spec and spec.loader
release_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_check)


def test_real_git_tag_objects_are_never_replaced(tmp_path: Path) -> None:
    git = release_check.git
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    repo.mkdir()
    git(tmp_path, "init", "--bare", str(remote))
    git(repo, "init")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "initial")
    assert release_check.check_release(repo, "v1")["action"] == "create"
    git(repo, "-c", "tag.gpgsign=false", "tag", "-a", "v1", "-m", "first")
    assert release_check.check_release(repo, "v1")["action"] == "push-existing"
    git(repo, "push", "origin", "refs/tags/v1")
    original = git(repo, "ls-remote", "origin", "refs/tags/v1")
    for _ in range(2):
        assert release_check.check_release(repo, "v1")["action"] == "reuse"
    git(repo, "tag", "-d", "v1")
    assert release_check.check_release(repo, "v1")["code"] == "tag-local-missing"
    git(repo, "-c", "tag.gpgsign=false", "tag", "-a", "v1", "-m", "different object")
    assert release_check.check_release(repo, "v1")["code"] == "tag-object-conflict"
    git(repo, "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "next")
    assert release_check.check_release(repo, "v1")["code"] == "tag-commit-conflict"
    assert git(repo, "ls-remote", "origin", "refs/tags/v1") == original
