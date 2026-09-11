from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from campfire_cli.common.exceptions import GovernanceBlockedError


@contextmanager
def vault_write_lock(state_root: Path) -> Iterator[None]:
    lock = state_root / "locks" / "write.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    descriptor = _acquire(lock)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
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
