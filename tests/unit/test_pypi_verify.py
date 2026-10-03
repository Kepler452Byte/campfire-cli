from __future__ import annotations

import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    ("failures", "installed", "expected_installs", "fails"),
    [
        (0, "0.1.17", 1, False),
        (2, "0.1.17", 3, False),
        (100, "0.1.17", 12, True),
        (0, "wrong", 1, True),
    ],
)
def test_pypi_install_retry_boundary(
    tmp_path: Path,
    failures: int,
    installed: str,
    expected_installs: int,
    fails: bool,
) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "pypi_verify.py"
    verify = runpy.run_path(str(script))["verify"]
    calls: list[list[str]] = []
    sleeps: list[int] = []
    attempts = 0

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        calls.append(command)
        if command[:3] == ["uv", "pip", "install"]:
            attempts += 1
            assert 0 < kwargs["timeout"] <= 180
            assert "--refresh" in command
            if attempts <= failures:
                raise subprocess.CalledProcessError(1, command, stderr="version unavailable")
        return subprocess.CompletedProcess(command, 0, stdout=installed)

    verify.__globals__["subprocess"] = SimpleNamespace(
        run=run,
        CalledProcessError=subprocess.CalledProcessError,
        TimeoutExpired=subprocess.TimeoutExpired,
    )
    verify.__globals__["time"] = SimpleNamespace(
        monotonic=lambda: sum(sleeps),
        sleep=sleeps.append,
    )
    if fails:
        with pytest.raises((subprocess.CalledProcessError, SystemExit)) as exc:
            verify("0.1.17", tmp_path / "venv")
        if failures:
            assert exc.value.stderr == "version unavailable"
        else:
            assert "wrong" in str(exc.value)
    else:
        verify("0.1.17", tmp_path / "venv")
    assert attempts == expected_installs
    assert all(delay == 15 for delay in sleeps)
    assert sum(sleeps) <= 180
    assert sum(command[:2] == ["uv", "venv"] for command in calls) == 1
    assert not any("publish" in command or "build" in command for command in calls)


def test_pypi_stalled_install_stops_at_deadline(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "pypi_verify.py"
    verify = runpy.run_path(str(script))["verify"]
    elapsed = 0.0
    sleeps: list[int] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal elapsed
        if command[:3] == ["uv", "pip", "install"]:
            elapsed += kwargs["timeout"]
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return subprocess.CompletedProcess(command, 0)

    verify.__globals__["subprocess"] = SimpleNamespace(
        run=run,
        CalledProcessError=subprocess.CalledProcessError,
        TimeoutExpired=subprocess.TimeoutExpired,
    )
    verify.__globals__["time"] = SimpleNamespace(
        monotonic=lambda: elapsed,
        sleep=sleeps.append,
    )
    with pytest.raises(subprocess.TimeoutExpired):
        verify("0.1.17", tmp_path / "venv")
    assert elapsed == 180
    assert sleeps == []
