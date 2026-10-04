from types import SimpleNamespace

import pytest

from campfire_cli.common.exceptions import AppError, GovernanceBlockedError
from campfire_cli.common.media import video_runtime


def test_plan_reads_extra_and_transitive_requirements_without_writes(monkeypatch):
    requirements = {
        "campfire-cli": ["core>=1", 'video-lib>=2; extra == "video"'],
        "video-lib": ["child>=1"],
    }
    monkeypatch.setattr(video_runtime.metadata, "requires", lambda name: requirements.get(name, []))
    monkeypatch.setattr(
        video_runtime.metadata,
        "distributions",
        lambda: [SimpleNamespace(metadata={"Name": "video-lib"}, version="2.0")],
    )
    monkeypatch.setattr(video_runtime.sys, "prefix", "isolated")
    monkeypatch.setattr(video_runtime.sys, "base_prefix", "system")
    monkeypatch.setattr(video_runtime.shutil, "which", lambda name: "uv")
    plan = video_runtime.LocalVideoRuntime().plan()
    assert plan["requirements"] == ["video-lib>=2"]
    assert plan["missing"] == ["child>=1"]
    assert plan["installer"][-2:] == ["--python", video_runtime.sys.executable]
    assert plan["constraints"] == ["video-lib==2.0"]


def test_system_python_never_gets_an_installer(monkeypatch):
    monkeypatch.setattr(video_runtime.sys, "prefix", video_runtime.sys.base_prefix)
    assert video_runtime.LocalVideoRuntime().plan()["installer"] is None


def test_install_uses_constraints_without_reinstalling_campfire(monkeypatch):
    runtime = video_runtime.LocalVideoRuntime()
    plan = {
        "requirements": ["example>=1"],
        "missing": ["example>=1"],
        "installer": ["uv", "pip", "install", "--python", "isolated-python"],
        "constraints": ["campfire-cli==0.2.0", "core==1"],
    }
    current = dict(plan)
    monkeypatch.setattr(runtime, "plan", lambda: current)

    def install(command, **kwargs):
        constraints = video_runtime.Path(command[command.index("--constraint") + 1])
        assert constraints.read_text() == "campfire-cli==0.2.0\ncore==1"
        assert command[-1] == "example>=1"
        assert not any("campfire-cli[" in item for item in command)
        assert kwargs["timeout"] == 10
        current["missing"] = []
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(video_runtime.subprocess, "run", install)
    runtime.install(plan, 10)


def test_install_rejects_changed_environment(monkeypatch):
    runtime = video_runtime.LocalVideoRuntime()
    monkeypatch.setattr(runtime, "plan", lambda: {"changed": True})
    with pytest.raises(GovernanceBlockedError):
        runtime.install({}, 10)


@pytest.mark.parametrize("timeout", [False, True])
def test_installer_errors_are_structured(monkeypatch, timeout):
    runtime = video_runtime.LocalVideoRuntime()
    plan = {
        "missing": ["example"],
        "requirements": ["example"],
        "installer": ["installer"],
        "constraints": [],
    }
    monkeypatch.setattr(runtime, "plan", lambda: plan)

    def fail(command, **kwargs):
        if timeout:
            raise video_runtime.subprocess.TimeoutExpired(command, 1)
        return SimpleNamespace(returncode=1, stderr="offline")

    monkeypatch.setattr(video_runtime.subprocess, "run", fail)
    with pytest.raises(AppError) as error:
        runtime.install(plan, 1)
    assert error.value.code == ("video-install-timeout" if timeout else "video-install-failed")
