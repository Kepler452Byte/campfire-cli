import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from campfire_cli.container import AppContainer

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_NATIVE_TEST") != "1", reason="requires real user scheduler"
)


def invoke(home: Path, *arguments: str) -> dict[str, Any]:
    if arguments[:2] == ("job", "run") and "--confirm" in arguments:
        preview = invoke(home, *(x for x in arguments if x != "--confirm"))
        arguments = (*arguments, "--expected-plan", preview["expected_plan"])
    result = subprocess.run(
        [sys.executable, "-m", "campfire_cli.main", *arguments],
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=30,
        env={**os.environ, "CAMPFIRE_HOME": str(home)},
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    return json.loads(result.stdout)  # type: ignore[no-any-return]


def mutate(home: Path, *arguments: str) -> dict[str, Any]:
    preview = invoke(home, *arguments)
    assert preview["status"] == "planned"
    return invoke(home, *arguments, "--confirm", "--expected-plan", preview["expected_plan"])


def test_native_lifecycle_and_real_interval_trigger(tmp_path: Path) -> None:
    home = tmp_path / "home space 中文 & percent% dollar$"
    home.mkdir()
    os.environ["CAMPFIRE_HOME"] = str(home)
    artifact = tmp_path / "evidence.json"
    expected = 'arg with spaces 中文 & % $ " \\ end'
    spec = tmp_path / "task.json"
    spec.write_text(
        json.dumps(
            {
                "id": "native-probe",
                "argv": [
                    sys.executable,
                    "-c",
                    "import json,sys; from pathlib import Path; "
                    "Path(sys.argv[1]).write_text(json.dumps(sys.argv[2]),encoding='utf-8'); "
                    "print('native-success'); "
                    + (
                        "import ctypes; assert ctypes.windll.kernel32.GetConsoleWindow() == 0; "
                        "print('console-window=0')"
                        if sys.platform == "win32"
                        else ""
                    ),
                    str(artifact),
                    expected,
                ],
                "cwd": str(tmp_path),
                "schedule": {"kind": "interval", "seconds": 60},
                "timeout": 10,
            }
        ),
        encoding="utf-8",
    )
    evidence: dict[str, Any] = {"platform": sys.platform, "doctor": invoke(home, "job", "doctor")}
    try:
        created = mutate(home, "job", "create", "--file", str(spec))
        assert not created["scheduler"]["enabled"]
        run = invoke(home, "job", "run", "native-probe", "--confirm")
        assert run["run"]["status"] == "succeeded"
        assert json.loads(artifact.read_text(encoding="utf-8")) == expected
        artifact.unlink()
        resumed = mutate(home, "job", "resume", "native-probe")
        assert resumed["scheduler"]["enabled"]
        # Re-registering the same definition must preserve enabled state too.
        assert mutate(home, "job", "update", "--file", str(spec))["scheduler"]["enabled"]
        deadline = time.monotonic() + 150
        while not artifact.exists() and time.monotonic() < deadline:
            time.sleep(1)
        assert artifact.exists(), json.dumps(invoke(home, "job", "show", "native-probe"))
        assert json.loads(artifact.read_text(encoding="utf-8")) == expected
        # Wait for final DB commit after the artifact appears.
        time.sleep(1)
        history = invoke(home, "job", "history", "--job", "native-probe")
        assert len(history["runs"]) >= 2 and history["runs"][0]["status"] == "succeeded"
        evidence["runs"] = history["runs"]
        logs = invoke(home, "job", "logs", history["runs"][0]["id"])
        assert any("native-success" in chunk["content"] for chunk in logs["chunks"])
        evidence["logs"] = logs
        assert mutate(home, "job", "pause", "native-probe")["scheduler"]["enabled"] is False
        assert mutate(home, "job", "update", "--file", str(spec))["scheduler"]["enabled"] is False
        # Exercise native calendar formats without waiting for their future trigger.
        data = json.loads(spec.read_text(encoding="utf-8"))
        for schedule in (
            {"kind": "daily", "time": "23:59"},
            {"kind": "weekly", "day": "sun", "time": "23:58"},
        ):
            data["schedule"] = schedule
            spec.write_text(json.dumps(data), encoding="utf-8")
            mutate(home, "job", "update", "--file", str(spec))
            mutate(home, "job", "resume", "native-probe")
            mutate(home, "job", "pause", "native-probe")
        for path in (home / "jobs").glob("runs.db*"):
            path.unlink()
        assert len(invoke(home, "job", "list")["jobs"]) == 1
        assert invoke(home, "job", "history")["runs"] == []
        mutate(home, "job", "delete", "native-probe")
        assert invoke(home, "job", "list")["jobs"] == []
        assert not AppContainer.build_job().scheduler.state("native-probe")["deployed"]
        evidence["result"] = "passed"
    finally:
        container = AppContainer.build_job()

        service = container
        service.scheduler.remove("native-probe")
        container.runs.close()
        output = Path(os.getenv("NATIVE_EVIDENCE_DIR", str(tmp_path)))
        output.mkdir(parents=True, exist_ok=True)
        (output / f"native-{sys.platform}.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def test_native_manual_mode_handoff(tmp_path: Path) -> None:
    home = tmp_path / "mode-home"
    os.environ["CAMPFIRE_HOME"] = str(home)
    spec = tmp_path / "mode.json"
    task_id = "manual-handoff"
    data = {
        "id": task_id,
        "argv": [sys.executable, "-c", "print('manual-evidence')"],
        "cwd": str(tmp_path),
        "schedule": {"kind": "manual"},
        "timeout": 5,
    }
    spec.write_text(json.dumps(data), encoding="utf-8")
    container = AppContainer.build_job()
    evidence: dict[str, Any] = {"platform": sys.platform}
    try:
        created = mutate(home, "job", "create", "--file", str(spec))
        assert not created["scheduler"]["deployed"]
        assert not container.scheduler.state(task_id)["deployed"]
        assert invoke(home, "job", "run", task_id, "--confirm")["run"]["status"] == "succeeded"
        data["schedule"] = {"kind": "interval", "seconds": 60}
        spec.write_text(json.dumps(data), encoding="utf-8")
        converted = mutate(home, "job", "update", "--file", str(spec))
        assert converted["scheduler"]["deployed"] and not converted["scheduler"]["enabled"]
        mutate(home, "job", "resume", task_id)
        data["schedule"] = {"kind": "manual"}
        spec.write_text(json.dumps(data), encoding="utf-8")
        converted = mutate(home, "job", "update", "--file", str(spec))
        assert not converted["scheduler"]["deployed"]
        assert not container.scheduler.state(task_id)["deployed"]
        assert invoke(home, "job", "run", task_id, "--confirm")["run"]["status"] == "succeeded"
        mutate(home, "job", "delete", task_id)
        assert invoke(home, "job", "list")["jobs"] == []
        evidence["result"] = "passed"
    finally:
        container.scheduler.remove(task_id)
        container.runs.close()
        output = Path(os.getenv("NATIVE_EVIDENCE_DIR", str(tmp_path)))
        output.mkdir(parents=True, exist_ok=True)
        (output / f"manual-{sys.platform}.json").write_text(json.dumps(evidence), encoding="utf-8")
