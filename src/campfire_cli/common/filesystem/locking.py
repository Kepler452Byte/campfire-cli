from __future__ import annotations

import ctypes
import os
import sys
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
        if _process_alive(pid):
            raise GovernanceBlockedError(f"已有治理写操作（PID {pid}）：{lock}") from exc
        lock.unlink(missing_ok=True)
        try:
            return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as retry_exc:
            raise GovernanceBlockedError(f"已有治理写操作：{lock}") from retry_exc


def _process_alive(pid: int) -> bool:
    """探测进程是否存活。

    Windows 上不能用 os.kill(pid, 0)：signal 0 等于 CTRL_C_EVENT，
    GenerateConsoleCtrlEvent 会向同控制台进程广播 Ctrl+C，干扰自身进程；
    改用 OpenProcess + GetExitCodeProcess 只读探测。
    """
    if sys.platform == "win32":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
