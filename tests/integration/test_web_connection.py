import http.cookiejar
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import suppress

import psutil
import pytest
from fastapi.testclient import TestClient

from campfire_cli.common.exceptions import JobError
from campfire_cli.web.connection import WebConnection
from campfire_cli.web.server import create_app


def test_reissue_requires_private_control_and_preserves_existing_cookie():
    app = create_app()
    origin = "http://127.0.0.1"
    headers = {"Origin": origin, "X-Campfire-Request": "1"}
    with TestClient(app, base_url=origin) as client:
        first = app.state.access.ticket
        assert (
            client.post("/api/session", headers=headers, json={"ticket": first}).status_code == 200
        )
        assert client.post("/api/session/link").status_code == 403
        assert client.post("/api/session/link", headers=headers).status_code == 403
        control = {"X-Campfire-Control": app.state.access.control}
        assert (
            client.post("/api/session/link", headers={**control, "Origin": origin}).status_code
            == 403
        )
        result = client.post("/api/session/link", headers=control)
        assert result.status_code == 200
        ticket = result.json()["data"]["ticket"]
        assert ticket != first
        assert client.get("/api/v1/environment").status_code == 200
        assert (
            client.post("/api/session", headers=headers, json={"ticket": ticket}).status_code == 200
        )
        assert (
            client.post("/api/session", headers=headers, json={"ticket": ticket}).status_code == 401
        )
        client.cookies.clear()
        assert client.get("/api/v1/environment", headers=control).status_code == 401
        assert client.get("/api/v1/environment").headers["cache-control"] == "no-store"


def test_restart_rejects_old_cookie_but_html_remains_available():
    origin = "http://127.0.0.1"
    first = create_app()
    with TestClient(first, base_url=origin) as old:
        old.post(
            "/api/session",
            headers={"Origin": origin, "X-Campfire-Request": "1"},
            json={"ticket": first.state.access.ticket},
        )
        cookie = old.cookies.get("campfire_session")
    with TestClient(create_app(), base_url=origin) as new:
        new.cookies.set("campfire_session", cookie)
        assert new.get("/app/scripts?project=example").status_code == 200
        denied = new.get("/api/v1/environment")
        assert denied.status_code == 401 and denied.json()["data"]["code"] == "session-required"


@pytest.mark.parametrize(
    "content", ["{}", "[]", "null", "{", '{"port":true,"pid":1,"control":"bad"}']
)
def test_invalid_runtime_registration_is_blocked(tmp_path, content):
    path = tmp_path / "web.json"
    path.write_text(content)
    path.chmod(0o600)
    with pytest.raises(JobError):
        WebConnection.read(path)


@pytest.mark.skipif(os.name == "nt", reason="POSIX file ownership and mode")
def test_runtime_registration_must_be_private(tmp_path):
    path = tmp_path / "web.json"
    connection = WebConnection(1234, os.getpid(), "a" * 43)
    connection.write(path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert WebConnection.read(path) == connection
    path.chmod(0o644)
    with pytest.raises(JobError):
        WebConnection.read(path)


def test_cli_reopens_live_web_and_replaces_stale_registration(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("CAMPFIRE_HOME", str(home))
    home.mkdir()
    registration = home / "web.json"
    registration.write_text("stale registration")
    output = tmp_path / "ready.json"
    with output.open("w") as stream:
        process = subprocess.Popen(
            [sys.executable, "-m", "campfire_cli.main", "web", "--no-open"],
            stdout=stream,
        )
        try:
            deadline = time.monotonic() + 15
            ready = None
            while time.monotonic() < deadline:
                try:
                    ready = json.loads(output.read_text())
                    break
                except (ValueError, OSError):
                    assert process.poll() is None
                    time.sleep(0.05)
            assert ready and ready["action"] == "started"
            info = WebConnection.read(registration)
            # Windows virtualenv launchers run the interpreter in a child process.
            assert info.pid in {
                process.pid,
                *(child.pid for child in psutil.Process(process.pid).children(recursive=True)),
            }
            before = registration.read_bytes()
            renewed = subprocess.run(
                [sys.executable, "-m", "campfire_cli.main", "web", "--no-open"],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            result = json.loads(renewed.stdout)
            assert result["action"] == "reconnected" and result["address"] == ready["address"]
            assert registration.read_bytes() == before and process.poll() is None
            with pytest.raises(JobError):
                info.link(1 if info.port != 1 else 2)
            jar = http.cookiejar.CookieJar()
            browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            ticket = result["url"].split("#connect=")[1]
            request = urllib.request.Request(
                f"{result['address']}/api/session",
                data=json.dumps({"ticket": ticket}).encode(),
                headers={
                    "Origin": result["address"],
                    "X-Campfire-Request": "1",
                    "Content-Type": "application/json",
                },
            )
            with browser.open(request, timeout=5) as response:
                assert response.status == 200
            info.link(0)
            with browser.open(f"{result['address']}/api/v1/environment", timeout=5) as response:
                assert response.status == 200
        finally:
            children = []
            with suppress(psutil.NoSuchProcess):
                children = psutil.Process(process.pid).children(recursive=True)
            for child in reversed(children):
                with suppress(psutil.NoSuchProcess):
                    child.terminate()
            process.terminate()
            process.wait(timeout=10)
            _, alive = psutil.wait_procs(children, timeout=5)
            for child in alive:
                with suppress(psutil.NoSuchProcess):
                    child.kill()
    if os.name != "nt":
        assert not registration.exists()
