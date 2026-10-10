from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from campfire_cli.common.exceptions import GovernanceBlockedError
from campfire_cli.common.filesystem.locking import workspace_write_lock
from campfire_cli.common.git import GitCommandError, run_git


class GitSyncService:
    """Synchronize an opted-in Vault using its existing Git upstream."""

    def __init__(self, root: Path, state_root: Path) -> None:
        self.root = root.resolve()
        self.state_root = state_root

    def sync(self, *, confirm: bool = False, expected_plan: str | None = None) -> dict:
        result = {
            "status": "ready",
            "write_performed": False,
            "local_commit": None,
            "remote_synced": False,
            "remote_checked": False,
            "conflict_paths": [],
        }
        phase = "inspect"
        try:
            if not confirm:
                return {**result, **self._inspect()}
            with workspace_write_lock(self.state_root):
                initial = self._inspect()
                result.update(initial)
                if expected_plan and expected_plan != initial["expected_plan"]:
                    return self._blocked(result, "plan-changed", phase)
                phase = "fetch"
                run_git(self.root, "fetch", "--", initial["remote"])
                result["remote_checked"] = True
                current = self._inspect()
                if current["expected_plan"] != initial["expected_plan"]:
                    return self._blocked(result, "local-changed", phase)
                result.update(current)
                if current["changed_paths"]:
                    phase = "stage"
                    try:
                        run_git(self.root, "add", "--all", "--", ".")
                        run_git(self.root, "diff", "--exit-code")
                        staged = self._snapshot()
                    except GitCommandError:
                        run_git(self.root, "reset", "--mixed", "HEAD")
                        raise
                    if staged != current["expected_plan"]:
                        # Reset only the index created by this invocation; retain file edits.
                        run_git(self.root, "reset", "--mixed", "HEAD")
                        return self._blocked(result, "local-changed", phase)
                    phase = "commit"
                    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
                    try:
                        run_git(self.root, "commit", "-m", f"docs: sync Vault {timestamp}")
                    except GitCommandError:
                        if run_git(self.root, "rev-parse", "HEAD").strip() == current["head"]:
                            run_git(self.root, "reset", "--mixed", "HEAD")
                        else:
                            result["local_commit"] = run_git(self.root, "rev-parse", "HEAD").strip()
                            result["write_performed"] = True
                        raise
                    result["local_commit"] = run_git(self.root, "rev-parse", "HEAD").strip()
                    result["write_performed"] = True
                phase = "merge"
                if run_git(self.root, "status", "--porcelain=v1", "-z"):
                    return self._blocked(result, "local-changed", phase)
                try:
                    run_git(
                        self.root,
                        "merge",
                        "--ff",
                        "--no-edit",
                        "-m",
                        "chore: merge upstream for Vault sync",
                        current["upstream"],
                    )
                except GitCommandError:
                    conflicts = self._paths("diff", "--name-only", "--diff-filter=U", "-z")
                    result["conflict_paths"] = conflicts
                    if self._git_path("MERGE_HEAD").exists():
                        try:
                            run_git(self.root, "merge", "--abort")
                        except GitCommandError:
                            return self._blocked(result, "merge-abort-failed", phase)
                    return self._blocked(
                        result, "merge-conflict" if conflicts else "merge-failed", phase
                    )
                result["write_performed"] |= (
                    run_git(self.root, "rev-parse", "HEAD").strip() != current["head"]
                )
                phase = "push"
                if run_git(self.root, "status", "--porcelain=v1", "-z"):
                    return self._blocked(result, "local-changed", phase)
                run_git(
                    self.root,
                    "push",
                    "--no-follow-tags",
                    "--",
                    current["remote"],
                    f"HEAD:{current['remote_ref']}",
                )
                result.update(status="synced", remote_synced=True, phase="complete")
                result["head"] = run_git(self.root, "rev-parse", "HEAD").strip()
                result["ahead"] = result["behind"] = 0
                return result
        except GitCommandError as exc:
            return {
                **self._blocked(result, exc.code or f"git-{phase}-failed", phase),
                "message": str(exc),
            }
        except GovernanceBlockedError:
            return self._blocked(result, "workspace-locked", phase)
        except OSError:
            return self._blocked(result, "local-read-failed", phase)

    def _inspect(self) -> dict:
        top = Path(run_git(self.root, "rev-parse", "--show-toplevel").strip()).resolve()
        if top != self.root:
            raise GitCommandError("Vault 必须是 Git 工作树根目录", "vault-not-git-root")
        for operation in (
            "MERGE_HEAD",
            "rebase-merge",
            "rebase-apply",
            "CHERRY_PICK_HEAD",
            "REVERT_HEAD",
        ):
            if self._git_path(operation).exists():
                raise GitCommandError("先完成或中止已有 Git 操作", "unfinished-git-operation")
        if self._paths("diff", "--name-only", "--diff-filter=U", "-z"):
            raise GitCommandError("先解决已有冲突", "unresolved-conflicts")
        if self._paths("diff", "--cached", "--name-only", "-z"):
            raise GitCommandError("先提交或取消人工暂存", "staged-changes")
        try:
            branch = run_git(self.root, "symbolic-ref", "--short", "HEAD").strip()
            remote = run_git(self.root, "config", "--get", f"branch.{branch}.remote").strip()
            remote_ref = run_git(self.root, "config", "--get", f"branch.{branch}.merge").strip()
        except GitCommandError as exc:
            raise GitCommandError("需要当前分支及其远端 upstream", "upstream-required") from exc
        if remote == "." or remote.startswith("-") or not remote_ref.startswith("refs/heads/"):
            raise GitCommandError("需要远端分支 upstream", "upstream-required")
        run_git(self.root, "check-ref-format", remote_ref)
        upstream = run_git(self.root, "rev-parse", "--symbolic-full-name", "@{upstream}").strip()
        behind, ahead = map(
            int,
            run_git(self.root, "rev-list", "--left-right", "--count", f"{upstream}...HEAD").split(),
        )
        return {
            "branch": branch,
            "remote": remote,
            "remote_ref": remote_ref,
            "upstream": upstream,
            "head": run_git(self.root, "rev-parse", "HEAD").strip(),
            "ahead": ahead,
            "behind": behind,
            "changed_paths": sorted(
                set(
                    self._paths("diff", "--name-only", "-z")
                    + self._paths("ls-files", "--others", "--exclude-standard", "-z")
                )
            ),
            "expected_plan": self._snapshot(),
        }

    def _snapshot(self) -> str:
        identity = run_git(self.root, "rev-parse", "HEAD") + run_git(
            self.root, "symbolic-ref", "HEAD"
        )
        identity += run_git(self.root, "config", "--get-regexp", r"^branch\.")
        identity += run_git(self.root, "remote", "-v")
        digest = hashlib.sha256(identity.encode())
        paths = sorted(
            set(
                self._paths("ls-files", "-z")
                + self._paths("diff", "HEAD", "--no-renames", "--name-only", "-z")
                + self._paths("ls-files", "--others", "--exclude-standard", "-z")
            )
        )
        for name in paths:
            path = self.root / name
            digest.update(name.encode())
            digest.update(b"\0")
            if path.is_symlink():
                digest.update(str(path.readlink()).encode())
            elif path.is_file():
                digest.update(str(path.stat().st_mode & 0o111).encode())
                digest.update(hashlib.sha256(path.read_bytes()).digest())
            elif path.exists():
                raise GitCommandError("Submodules and directory entries are unsupported")
            else:
                digest.update(b"deleted")
        return digest.hexdigest()

    def _paths(self, *arguments: str) -> list[str]:
        return [name for name in run_git(self.root, *arguments).split("\0") if name]

    def _git_path(self, name: str) -> Path:
        path = Path(run_git(self.root, "rev-parse", "--git-path", name).strip())
        return path if path.is_absolute() else self.root / path

    @staticmethod
    def _blocked(result: dict, code: str, phase: str) -> dict:
        return {
            **result,
            "status": "blocked",
            "code": code,
            "phase": phase,
            "hint": "检查 Git/upstream、凭据、暂存或未完成操作；保留本地内容，处理后重新预览同步。",
        }
