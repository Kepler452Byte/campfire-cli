import json
import os
import sys
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from campfire_cli.app.job.schema.job_schema import Job
from campfire_cli.app.script.service.script_service import ScriptService
from campfire_cli.common.exceptions import InputError, JobError
from campfire_cli.config.defaults import builtin_section
from campfire_cli.container import AppContainer
from campfire_cli.main import app
from campfire_cli.web.server import create_app


@pytest.fixture
def scripts(tmp_path, monkeypatch):
    home = tmp_path / "state"
    monkeypatch.setenv("CAMPFIRE_HOME", str(home))
    project = home / "scripts" / "growth"
    (project / "helpers").mkdir(parents=True)
    (project / "daily.py").write_bytes(b"print('hello')\r\n")
    (project / "helpers" / "study.py").write_text("# 学习\n", encoding="utf-8", newline="\n")
    (project / "node_modules").mkdir()
    (project / "node_modules" / "ignored.js").write_text("ignored")
    return ScriptService(home, builtin_section("scripts"))


def test_read_only_listing_nested_content_and_missing_root(tmp_path, scripts):
    missing = ScriptService(tmp_path / "missing", builtin_section("scripts"))
    assert missing.projects()["projects"] == []
    assert not missing.root.parent.exists()
    (scripts.root / ".hidden").mkdir()
    (scripts.root / "node_modules").mkdir()
    before = (scripts.root / "growth/daily.py").read_bytes()
    assert scripts.projects()["projects"] == ["growth"]
    with pytest.raises(InputError):
        scripts.directory("node_modules")
    assert [entry["name"] for entry in scripts.directory("growth")["entries"]] == [
        "helpers",
        "daily.py",
    ]
    assert scripts.file("growth", "helpers/study.py")["content"] == "# 学习\n"
    assert scripts.file("growth", "daily.py")["content"] == "print('hello')\r\n"
    assert (scripts.root / "growth/daily.py").read_bytes() == before
    (scripts.root / "growth/helpers/study.py").write_text("new")
    assert scripts.file("growth", "helpers/study.py")["content"] == "new"


@pytest.mark.parametrize(
    "path",
    [
        "../daily.py",
        "/etc/passwd",
        "helpers/../../x",
        "C:/x",
        "helpers\\study.py",
        "helpers//study.py",
        "node_modules/ignored.js",
    ],
)
def test_reject_paths_outside_project_or_filtered_directory(scripts, path):
    with pytest.raises(InputError) as exc:
        scripts.file("growth", path)
    assert exc.value.code == "invalid-script-path"


@pytest.mark.parametrize(
    "project", ["..", ".", "../growth", "a/b", "a\\b", "C:", " growth", "growth."]
)
def test_invalid_project_names(scripts, project):
    with pytest.raises(InputError) as exc:
        scripts.directory(project)
    assert exc.value.code == "invalid-script-project"


def test_large_binary_missing_and_special_files(scripts):
    project = scripts.root / "growth"
    for name, content in [
        ("large.txt", b"x" * (scripts.max_file_bytes + 1)),
        ("binary", b"a\0b"),
        ("invalid.txt", b"\xff"),
    ]:
        (project / name).write_bytes(content)
        with pytest.raises(InputError) as exc:
            scripts.file("growth", name)
        assert exc.value.code == "invalid-script-file"
    with pytest.raises(InputError) as exc:
        scripts.file("growth", "missing.py")
    assert exc.value.code == "not-found"
    if hasattr(os, "mkfifo"):
        os.mkfifo(project / "pipe")
        assert "pipe" not in [entry["name"] for entry in scripts.directory("growth")["entries"]]
        with pytest.raises(InputError):
            scripts.file("growth", "pipe")
    scripts.max_entries = 1
    with pytest.raises(InputError) as exc:
        scripts.directory("growth")
    assert exc.value.code == "invalid-script-directory"


def test_symlinks_do_not_expose_external_files(scripts, tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    (external / "secret.txt").write_text("outside")
    project = scripts.root / "growth"
    try:
        (project / "linked").symlink_to(external, target_is_directory=True)
        (scripts.root / "linked-project").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symbolic links requires OS permission")
    assert "linked" not in [entry["name"] for entry in scripts.directory("growth")["entries"]]
    assert "linked-project" not in scripts.projects()["projects"]
    with pytest.raises(InputError):
        scripts.file("growth", "linked/secret.txt")
    with pytest.raises(InputError):
        scripts.directory("linked-project")
    dangling = ScriptService(tmp_path / "dangling", builtin_section("scripts"))
    dangling.root.parent.mkdir()
    dangling.root.symlink_to(tmp_path / "absent", target_is_directory=True)
    with pytest.raises(InputError):
        dangling.projects()


def test_cli_http_read_same_files_and_require_session(scripts):
    result = CliRunner().invoke(app, ["script", "read", "growth", "--path", "helpers/study.py"])
    assert result.exit_code == 0, result.output
    cli = json.loads(result.stdout)
    application = create_app()
    with TestClient(application, base_url="http://127.0.0.1") as client:
        assert client.get("/api/v1/scripts").status_code == 401
        headers = {"Origin": "http://127.0.0.1", "X-Campfire-Request": "1"}
        client.post(
            "/api/session", json={"ticket": application.state.access.ticket}, headers=headers
        )
        assert client.get("/api/v1/scripts").json()["data"]["projects"] == ["growth"]
        assert (
            client.get("/api/v1/scripts/growth/file", params={"path": "helpers/study.py"}).json()[
                "data"
            ]
            == cli
        )
        assert client.get("/api/v1/scripts/growth/file", params={"path": "../x"}).status_code == 422
        assert (
            client.get("/api/v1/scripts/growth/file", params={"path": "missing.py"}).status_code
            == 404
        )
        assert client.post("/api/v1/scripts/growth/file", json={}).status_code == 403


def test_job_association_roundtrip_stale_plan_and_existing_jobs(scripts):
    service = AppContainer.build_job()
    try:
        job = Job(
            "growth-task",
            [sys.executable, "-c", "print('hello')"],
            str(scripts.root),
            {"kind": "manual"},
        )
        assert "script_project" not in job.data()
        invalid = replace(job, script_project="missing")
        with pytest.raises(InputError):
            service.change("create", job.id, invalid, False, None)
        linked = replace(job, script_project="growth")
        plan = service.change("create", job.id, linked, False, None)
        with pytest.raises(JobError) as exc:
            service.change("create", job.id, job, True, plan["expected_plan"])
        assert exc.value.code == "stale-plan"
        service.change("create", job.id, linked, True, plan["expected_plan"])
        assert service.show(job.id)["job"]["script_project"] == "growth"
        assert Job.parse(service.repository.read()[job.id].data()) == linked
        plan = service.change("update", job.id, job, False, None)
        service.change("update", job.id, job, True, plan["expected_plan"])
        assert "script_project" not in service.get(job.id).data()
        assert (scripts.root / "growth/daily.py").is_file()
    finally:
        service.runs.close()
