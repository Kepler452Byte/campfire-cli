"""Kernel-held locks for local operations and database leases."""

import ctypes
import os
from contextlib import contextmanager
from pathlib import Path

from campfire_cli.common.exceptions import JobError


@contextmanager
def os_lock(path: Path, *, shared: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            from ctypes import wintypes

            class Overlapped(ctypes.Structure):
                _fields_ = [
                    ("Internal", ctypes.c_size_t),
                    ("InternalHigh", ctypes.c_size_t),
                    ("Offset", wintypes.DWORD),
                    ("OffsetHigh", wintypes.DWORD),
                    ("hEvent", wintypes.HANDLE),
                ]

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            lock = kernel.LockFileEx
            lock.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(Overlapped),
            ]
            lock.restype = wintypes.BOOL
            if not lock(
                msvcrt.get_osfhandle(handle.fileno()),
                1 if shared else 3,
                0,
                1,
                0,
                ctypes.byref(Overlapped()),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            import fcntl

            fcntl.flock(handle, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                unlock = kernel.UnlockFileEx
                unlock.argtypes = [
                    wintypes.HANDLE,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    ctypes.POINTER(Overlapped),
                ]
                unlock.restype = wintypes.BOOL
                unlock(msvcrt.get_osfhandle(handle.fileno()), 0, 1, 0, ctypes.byref(Overlapped()))
    finally:
        handle.close()


@contextmanager
def process_lock(path: Path, *, shared: bool = False):
    """Reject conflicting operations; allow explicitly shared readers."""
    try:
        with os_lock(path, shared=shared):
            yield
    except OSError as exc:
        if not isinstance(exc, BlockingIOError) and getattr(exc, "winerror", None) not in {32, 33}:
            raise
        raise JobError(
            "busy",
            "Another operation holds this lock; retry after it finishes",
            lock_path=str(path),
        ) from exc
