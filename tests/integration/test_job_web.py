import json
import sys
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from campfire_cli.common.exceptions import JobError
from campfire_cli.common.filesystem.process_lock import process_lock
from campfire_cli.container import AppContainer
from campfire_cli.main import app
from campfire_cli.web.server import create_app


@pytest.fixture
def service():
    service = AppContainer.build_job()
    yield service
    service.runs.close()


@pytest.fixture
def client(service):
    application = create_app(build_job=lambda: service)
    with TestClient(application, base_url="http://127.0.0.1") as client:
        client.headers.update({"Origin": "http://127.0.0.1", "X-Campfire-Request": "1"})
        response = client.post("/api/session", json={"ticket": application.state.access.ticket})
        assert response.status_code == 200
        yield client


def definition(tmp_path, identity="example", code="print('hello')"):
    return {
        "id": identity,
        "name": "测试任务",
        "argv": [sys.executable, "-c", code],
        "cwd": str(tmp_path),
        "schedule": {"kind": "manual"},
        "timeout": 30,
    }


def create(client, data):
    preview = client.post("/api/v1/jobs", json={"job": data}).json()["data"]
    response = client.post(
        "/api/v1/jobs",
        json={"job": data, "confirm": True, "expected_plan": preview["expected_plan"]},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_local_session_origin_host_and_single_use_ticket():
    application = create_app()
    with TestClient(application, base_url="http://127.0.0.1") as client:
        assert client.get("/api/v1/environment").status_code == 401
        ticket = application.state.access.ticket
        assert client.post("/api/session", json={"ticket": ticket}).status_code == 403
        headers = {"Origin": "http://127.0.0.1", "X-Campfire-Request": "1"}
        assert (
            client.post("/api/session", json={"ticket": ticket}, headers=headers).status_code == 200
        )
        assert (
            client.post("/api/session", json={"ticket": ticket}, headers=headers).status_code == 401
        )
        assert client.get("/api/v1/environment").status_code == 200
        assert (
            client.get(
                "/api/v1/environment", headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert (
            client.get("/api/v1/environment", headers={"Host": "evil.example"}).status_code == 403
        )
        assert client.post("/api/v1/jobs", json={}).status_code == 403
        assert client.get("/api/v1/missing").status_code == 404
        assert client.get("/api/v1/missing").headers["content-type"].startswith("application/json")


def test_cli_and_http_share_definition_and_reject_stale_preview(client, service, tmp_path):
    data = definition(tmp_path)
    preview = client.post("/api/v1/jobs", json={"job": data}).json()["data"]
    assert not preview["write_performed"] and not service.repository.path.exists()
    create(client, data)
    result = CliRunner().invoke(app, ["job", "show", data["id"]])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["job"]["name"] == data["name"]
    data["name"] = "网页待保存名称"
    preview = client.put("/api/v1/jobs/example", json={"job": data}).json()["data"]
    other = replace(service.get("example"), name="Agent 已修改")
    fresh = service.change("update", other.id, other, False, None)
    service.change("update", other.id, other, True, fresh["expected_plan"])
    before = service.repository.path.read_bytes()
    response = client.put(
        "/api/v1/jobs/example",
        json={"job": data, "confirm": True, "expected_plan": preview["expected_plan"]},
    )
    assert response.status_code == 409
    assert response.json()["data"]["code"] == "stale-plan"
    assert response.json()["data"]["status"] == "blocked"
    assert service.repository.path.read_bytes() == before


def test_script_argv_round_trips_and_rejects_agent_configuration(client, service, tmp_path):
    data = definition(tmp_path)
    script = tmp_path / "entry.py"
    script.write_text("import json,sys\nprint(json.dumps(sys.argv[1],ensure_ascii=False))\n")
    argument = "整理文档\n保留今天的中文进展"
    data["argv"] = [sys.executable, str(script), argument]
    create(client, data)
    stored = service.repository.read()["example"]
    assert stored.argv == data["argv"]
    plan = service.run("example", False)
    result = service.run("example", True, plan["expected_plan"])
    assert result["run"]["status"] == "succeeded"
    output = "".join(
        chunk["content"] for chunk in service.logs(result["run"]["id"], 100, 0)["chunks"]
    )
    assert json.loads(output) == argument
    before = service.repository.path.read_bytes()
    data["agent"] = {"kind": "codex", "prompt": argument, "executable": sys.executable}
    assert client.put("/api/v1/jobs/example", json={"job": data}).status_code == 422
    assert service.repository.path.read_bytes() == before


def test_query_pagination_unknown_filters_and_input_errors(client, tmp_path):
    for identity in ["first", "second", "third"]:
        create(client, definition(tmp_path, identity))
    result = client.get("/api/v1/jobs?page=2&page_size=2&state=manual").json()["data"]
    assert result["total"] == 3 and len(result["list"]) == 1 and result["pages"] == 2
    assert client.get("/api/v1/jobs?name=missing").json()["data"]["total"] == 0
    assert client.get("/api/v1/jobs?page=0").status_code == 422
    assert client.get("/api/v1/jobs?state=missing").status_code == 422
    assert client.get("/api/v1/jobs/missing").status_code == 404
    assert client.post("/api/v1/jobs/first/delete", json={"confirm": "false"}).status_code == 422


def test_detached_run_readiness_busy_and_result(client, service, tmp_path):
    marker = tmp_path / "completed.txt"
    create(
        client,
        definition(
            tmp_path,
            code=(
                "import time,pathlib;time.sleep(1);"
                f"pathlib.Path({str(marker)!r}).write_text('done')"
            ),
        ),
    )
    preview = client.post("/api/v1/jobs/example/run", json={}).json()["data"]
    with service.run_lock("example"):
        blocked = client.post(
            "/api/v1/jobs/example/run",
            json={"confirm": True, "expected_plan": preview["expected_plan"]},
        )
        assert blocked.status_code == 409 and blocked.json()["data"]["code"] == "busy"
    started = client.post(
        "/api/v1/jobs/example/run",
        json={"confirm": True, "expected_plan": preview["expected_plan"]},
    )
    assert started.status_code == 202, started.text
    identity = started.json()["data"]["run"]["id"]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = client.get(f"/api/v1/runs/{identity}").json()["data"]["run"]
        if result["status"] != "running":
            break
        time.sleep(0.05)
    assert result["status"] == "succeeded" and marker.read_text() == "done"
    assert client.get("/api/v1/jobs/example/runs").json()["data"]["total"] == 1
    assert client.get(f"/api/v1/runs/{identity}/logs").status_code == 200


def test_api_uses_packaged_assets_without_api_fallback(tmp_path):
    (tmp_path / "index.html").write_text("<html>Campfire</html>")
    application = create_app(assets=tmp_path)
    with TestClient(application, base_url="http://127.0.0.1") as client:
        assert client.get("/app/jobs").text == "<html>Campfire</html>"
        assert client.get("/assets/missing.js").status_code == 404
        assert client.get("/api/v1/missing").status_code == 401


def test_partial_write_blocked_keeps_http_failure_and_written_fact(
    client, service, tmp_path, monkeypatch
):
    data = definition(tmp_path)
    preview = client.post("/api/v1/jobs", json={"job": data}).json()["data"]
    original = service.state
    calls = 0

    def state(job):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise JobError("scheduler-unavailable", "Cannot observe native state")
        return original(job)

    monkeypatch.setattr(service, "state", state)
    response = client.post(
        "/api/v1/jobs",
        json={
            "job": data,
            "confirm": True,
            "expected_plan": preview["expected_plan"],
        },
    )
    assert response.status_code == 409
    payload = response.json()["data"]
    assert payload["status"] == "blocked" and payload["write_performed"]
    assert service.get("example").name == data["name"]


def test_web_runtime_prevents_installation_replacement(service):
    with process_lock(service.home / "jobs/locks/web.lock"):
        with pytest.raises(JobError) as error, service.idle():
            pytest.fail("Active Web must prevent environment replacement")
        assert error.value.code == "busy"


def test_concurrent_readers_share_config_lock_but_writes_remain_exclusive(
    client, service, tmp_path
):
    from campfire_cli.common.filesystem.process_lock import os_lock

    data = definition(tmp_path)
    create(client, data)
    with os_lock(service.home / "jobs/locks/config.lock", shared=True):
        response = client.get("/api/v1/jobs/example")
        assert response.status_code == 200, response.text
        assert client.get("/api/v1/jobs").status_code == 200
        shown = CliRunner().invoke(app, ["job", "show", data["id"]])
        assert shown.exit_code == 0, shown.output
        blocked = client.put("/api/v1/jobs/example", json={"job": data})
        assert blocked.status_code == 409
        assert blocked.json()["data"]["code"] == "busy"
