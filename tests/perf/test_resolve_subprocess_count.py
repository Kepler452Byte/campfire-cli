from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.mark.perf
def test_project_resolve_git_subprocesses_do_not_scale_with_registry(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """resolve 的 git 子进程数固定为至多 2 次，不随注册项目数增长。"""
    from typer.testing import CliRunner

    from campfire_cli.main import app

    domain = workspace / "mynote" / "perf-domain"
    domain.mkdir(parents=True)
    (domain / "_领域.md").write_text(
        "---\nname: perf-domain\ndomain_id: perf-domain\n"
        "domain_type: knowledge-domain\ngovernance: knowledge-docs\n"
        'moc: "[[MOC-perf-domain]]"\nstatus: active\n---\n',
        encoding="utf-8",
    )

    calls: list[list[str]] = []
    monkeypatch.setattr(
        "campfire_cli.app.workspace.service.project_service.subprocess.run",
        lambda command, **kwargs: calls.append(command)
        or subprocess.CompletedProcess(command, 1, stdout="", stderr=""),
    )
    runner = CliRunner()
    bootstrapped = runner.invoke(app, ["setup", "--workspace", str(workspace), "--default"])
    assert bootstrapped.exit_code == 0, bootstrapped.output
    for index in range(5):
        project_dir = tmp_path_factory.mktemp(f"project-{index}")
        registered = runner.invoke(
            app,
            [
                "workspace",
                "project",
                "add",
                "--id",
                f"perf-project-{index}",
                "--workspace",
                "test",
                "--name",
                f"perf-{index}",
                "--document-domain",
                "mynote/perf-domain",
                "--local-path",
                str(project_dir),
            ],
        )
        assert registered.exit_code == 0, registered.output

    calls.clear()
    matched = runner.invoke(
        app, ["workspace", "project", "resolve", "--path", str(project_dir)]
    )
    assert matched.exit_code == 0, matched.output
    bounded = len(calls)
    assert bounded <= 2, calls

    unregistered = tmp_path_factory.mktemp("unregistered")
    calls.clear()
    unmatched = runner.invoke(
        app, ["workspace", "project", "resolve", "--path", str(unregistered)]
    )
    assert unmatched.exit_code == 0, unmatched.output
    assert len(calls) == bounded, calls
