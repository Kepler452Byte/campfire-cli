from __future__ import annotations

import errno
import json
from pathlib import Path

import pytest

from campfire_cli.common import package_update_worker as worker


@pytest.mark.parametrize("failures", [1, 5, 6])
def test_windows_status_snapshot_retries_are_bounded(tmp_path: Path, monkeypatch, failures):
    path = tmp_path / "result.json"
    path.write_text('{"state":"pending"}', encoding="utf-8")
    replace = worker.os.replace
    attempts = []
    waits = []

    def locked_then_replace(source, target):
        attempts.append(target)
        if len(attempts) <= failures:
            error = PermissionError(errno.EACCES, "reader holds status file")
            error.winerror = 32
            raise error
        replace(source, target)

    monkeypatch.setattr(worker.sys, "platform", "win32")
    monkeypatch.setattr(worker.os, "replace", locked_then_replace)
    monkeypatch.setattr(worker.time, "sleep", waits.append)
    if failures < 6:
        worker.save(path, {"state": "completed"})
        assert json.loads(path.read_text())["state"] == "completed"
        assert len(attempts) == failures + 1
    else:
        with pytest.raises(PermissionError):
            worker.save(path, {"state": "completed"})
        assert json.loads(path.read_text())["state"] == "pending"
        assert len(attempts) == 6
    assert len(waits) == min(failures, 5)
    assert list(tmp_path.iterdir()) == [path]


def test_non_windows_permission_failure_does_not_retry(tmp_path: Path, monkeypatch):
    def denied(*args):
        raise PermissionError(errno.EACCES, "denied")

    def unexpected_wait(*args):
        pytest.fail("Non-Windows errors must fail immediately")

    monkeypatch.setattr(worker.sys, "platform", "linux")
    monkeypatch.setattr(worker.os, "replace", denied)
    monkeypatch.setattr(worker.time, "sleep", unexpected_wait)
    with pytest.raises(PermissionError):
        worker.save(tmp_path / "result.json", {"state": "completed"})
    assert not list(tmp_path.iterdir())
