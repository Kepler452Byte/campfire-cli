from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from campfire_cli.common.exceptions import GovernanceBlockedError


@contextmanager
def workspace_write_lock(scope_root: Path) -> Iterator[None]:
    """对 scope_root 范围内的治理写入互斥。

    锁的粒度由传入的根目录决定，锁文件位于 <scope_root>/locks/write.lock：

    - Workspace 的 state_root（~/.campfire/workspaces/<id>/）：
      互斥该 Workspace 的 Vault 写入与状态刷新；
    - campfire_home（~/.campfire/）：互斥跨 Workspace 的全局资源，
      包括注册库写入和全局 Skill 同步。
    """
    lock = scope_root / "locks" / "write.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    descriptor = _acquire(lock)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def _acquire(lock: Path) -> int:
    try:
        return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        try:
            pid = int(lock.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            raise GovernanceBlockedError(f"已有治理写操作且锁内容无法确认：{lock}") from exc
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            lock.unlink(missing_ok=True)
            try:
                return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as retry_exc:
                raise GovernanceBlockedError(f"已有治理写操作：{lock}") from retry_exc
        except PermissionError:
            pass
        raise GovernanceBlockedError(f"已有治理写操作（PID {pid}）：{lock}") from exc
