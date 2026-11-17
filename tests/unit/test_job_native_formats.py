import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from campfire_cli.app.job.adapter.systemd_scheduler import quote
from campfire_cli.app.job.adapter.windows_scheduler import NS, WindowsScheduler
from campfire_cli.app.job.interface.scheduler import namespace, runner_argv
from campfire_cli.app.job.schema.job_schema import Job
from campfire_cli.common.exceptions import JobError


def test_windows_xml_preserves_paths_schedule_and_security(
    task: Job, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python = tmp_path / "Python 中文 space" / "python.exe"
    python.parent.mkdir()
    pythonw = python.with_name("pythonw.exe")
    pythonw.touch()
    monkeypatch.setattr(
        "campfire_cli.app.job.adapter.windows_scheduler.sys.executable", str(python)
    )
    home = tmp_path / "spaces & unicode中文"
    scheduler = WindowsScheduler(home)
    for schedule in (
        {"kind": "interval", "seconds": 300},
        {"kind": "daily", "time": "09:00"},
        {"kind": "weekly", "day": "sun", "time": "12:00"},
    ):
        definition = Job(task.id, task.argv, task.cwd, schedule)
        root = ET.fromstring(scheduler.xml(definition, False, "S-1-5-21-test"))
        assert (
            root.findtext(f"{{{NS}}}Principals/{{{NS}}}Principal/{{{NS}}}LogonType")
            == "InteractiveToken"
        )
        assert root.findtext(f"{{{NS}}}Settings/{{{NS}}}Enabled") == "false"
        assert root.findtext(f"{{{NS}}}Actions/{{{NS}}}Exec/{{{NS}}}Command") == str(pythonw)
        assert root.findtext(
            f"{{{NS}}}Actions/{{{NS}}}Exec/{{{NS}}}Arguments"
        ) == subprocess.list2cmdline(runner_argv(home, task.id)[1:])


def test_systemd_escaping_and_namespace(tmp_path: Path) -> None:
    assert quote('a%$"\\b') == '"a%%$$\\"\\\\b"'
    assert namespace(tmp_path) != namespace(tmp_path / "other")


def test_windows_deployment_requires_same_environment_pythonw(
    task: Job, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "campfire_cli.app.job.adapter.windows_scheduler.sys.executable",
        str(tmp_path / "missing" / "python.exe"),
    )
    with pytest.raises(JobError) as error:
        WindowsScheduler(tmp_path).xml(task, False, "S-1-test")
    assert error.value.code == "windowless-python-unavailable"


@pytest.fixture
def task(tmp_path):
    import sys

    return Job(
        "example",
        [sys.executable, "-c", "print('hi')"],
        str(tmp_path),
        {"kind": "interval", "seconds": 60},
        5,
    )
