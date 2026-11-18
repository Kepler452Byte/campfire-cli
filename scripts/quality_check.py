"""
SPEC:
  name: quality_check
  purpose: 运行本地与 CI 共用的快速或发布质量门禁
  idempotent: true
  side_effects:
    - 发布门禁在临时目录构建并安装包
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import tomllib
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*command: str) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def check_tag(version: str) -> None:
    tag = os.environ.get("GITHUB_REF_NAME")
    if tag and tag.startswith("v") and tag != f"v{version}":
        raise SystemExit(f"tag {tag} does not match project version {version}")


def smoke_web(campfire: Path, environment: dict, version: str) -> None:
    process = subprocess.Popen(
        [str(campfire), "web", "--no-open"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    ready: queue.Queue = queue.Queue(maxsize=1)

    def read():
        raw = ""
        for line in process.stdout:
            raw += line
            try:
                ready.put(json.loads(raw))
                return
            except ValueError:
                continue
        ready.put({"status": "error"})

    threading.Thread(target=read, daemon=True).start()
    run_directory = tempfile.TemporaryDirectory(prefix="campfire-web-run-")
    marker = Path(run_directory.name) / "completed"
    started_run = None
    try:
        started = ready.get(timeout=30)
        if started.get("status") != "ok":
            raise RuntimeError("Installed Web failed to start")
        address = started["address"]
        ticket = urllib.parse.parse_qs(urllib.parse.urlsplit(started["url"]).fragment)["connect"][0]
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        request = urllib.request.Request(
            address + "/api/session",
            data=json.dumps({"ticket": ticket}).encode(),
            headers={
                "Content-Type": "application/json",
                "Origin": address,
                "X-Campfire-Request": "1",
            },
        )
        with client.open(request, timeout=10) as response:
            assert response.status == 200
        with client.open(address + "/api/v1/environment", timeout=10) as response:
            assert json.load(response)["data"]["version"] == version
        with client.open(address + "/app/jobs", timeout=10) as response:
            html = response.read().decode()
            assert "Campfire" in html
        for asset in re.findall(r'(?:src|href)="(/assets/[^"?]+)', html):
            with client.open(address + asset, timeout=10) as response:
                assert response.status == 200 and response.read()

        def post(path: str, data: dict) -> dict:
            request = urllib.request.Request(
                address + "/api/v1" + path,
                data=json.dumps(data).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Origin": address,
                    "X-Campfire-Request": "1",
                },
            )
            with client.open(request, timeout=30) as response:
                return json.load(response)["data"]

        python = campfire.parent / ("python.exe" if os.name == "nt" else "python")
        definition = {
            "id": "web-smoke",
            "argv": [
                str(python),
                "-c",
                "import time,pathlib;time.sleep(2);"
                f"pathlib.Path({str(marker)!r}).write_text('done')",
            ],
            "cwd": run_directory.name,
            "schedule": {"kind": "manual"},
            "timeout": 30,
        }
        preview = post("/jobs", {"job": definition})
        post(
            "/jobs", {"job": definition, "confirm": True, "expected_plan": preview["expected_plan"]}
        )
        preview = post("/jobs/web-smoke/run", {})
        started_run = post(
            "/jobs/web-smoke/run",
            {
                "confirm": True,
                "expected_plan": preview["expected_plan"],
            },
        )["run"]["id"]
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()
        try:
            if started_run is not None:
                deadline = time.monotonic() + 15
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                if not marker.exists() or marker.read_text() != "done":
                    raise RuntimeError("Detached task did not survive Web shutdown")
                result = subprocess.run(
                    [str(campfire), "job", "result", started_run],
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=True,
                    timeout=30,
                )
                if json.loads(result.stdout)["run"]["status"] != "succeeded":
                    raise RuntimeError("Detached task did not finish successfully")
        finally:
            run_directory.cleanup()


def smoke_test_wheel(version: str, artifact_dir: Path | None = None) -> None:
    with tempfile.TemporaryDirectory(prefix="campfire-quality-") as raw_directory:
        directory = Path(raw_directory).resolve()
        dist = artifact_dir or directory / "dist"
        if artifact_dir is not None and dist.exists() and any(dist.iterdir()):
            raise SystemExit(f"artifact directory must be empty: {dist}")
        dist.mkdir(parents=True, exist_ok=True)
        environment = directory / "venv"
        workspace = directory / "workspace"
        run("uv", "build", "--out-dir", str(dist))
        wheels = list(dist.glob("*.whl"))
        source_distributions = list(dist.glob("*.tar.gz"))
        if len(wheels) != 1 or len(source_distributions) != 1:
            raise SystemExit("build must produce exactly one wheel and one source distribution")
        wheel = wheels[0]
        run("uv", "venv", str(environment))
        executable_dir = "Scripts" if os.name == "nt" else "bin"
        python = environment / executable_dir / ("python.exe" if os.name == "nt" else "python")
        campfire = (
            environment / executable_dir / ("campfire.exe" if os.name == "nt" else "campfire")
        )
        run("uv", "pip", "install", "--python", str(python), str(wheel))
        smoke_environment = os.environ.copy()
        smoke_environment.update(
            {
                "CAMPFIRE_HOME": str(directory / "campfire-home"),
                "CAMPFIRE_AGENT_HINT_PATH": str(directory / "agent-hints"),
                "CAMPFIRE_SKILL_TARGETS": str(directory / "agent-skills"),
            }
        )
        installed = subprocess.run(
            [str(campfire), "version"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env=smoke_environment,
        ).stdout
        installed = json.loads(installed)["version"]
        if installed != version:
            raise SystemExit(f"installed version {installed} does not match {version}")
        smoke_web(campfire, smoke_environment, version)
        subprocess.run(
            [str(campfire), "workspace", "create", "--path", str(workspace), "--id", "smoke"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env=smoke_environment,
        )
        for name in ("README.md", "模板-任务.md", "模板-版本发布清单.md"):
            if not (workspace / "_模板" / name).is_file():
                raise SystemExit(f"installed wheel did not initialize template: {name}")
        output = subprocess.run(
            [str(campfire), "--workspace", "smoke", "document", "type", "list"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env=smoke_environment,
        ).stdout
        json.loads(output)
        # Every CLI process has exited before taking the offline state snapshot.
        state = directory / "campfire-home"
        backup = directory / "backup"
        shutil.copytree(workspace, backup / "workspace")
        shutil.copytree(state, backup / "state")
        document = workspace / "_模板" / "README.md"
        original = document.read_bytes()
        document.write_bytes(original + b"\nRecovery drill\n")
        shutil.copy2(backup / "workspace" / "_模板" / "README.md", document)
        shutil.copytree(backup / "state", state, dirs_exist_ok=True)
        subprocess.run(
            [str(campfire), "--workspace", "smoke", "document", "type", "list"],
            cwd=directory,
            check=True,
            capture_output=True,
            env=smoke_environment,
        )
        if document.read_bytes() != original:
            raise SystemExit("offline document restore changed content")
        run("uv", "pip", "uninstall", "--python", str(python), "campfire-cli")
        if campfire.exists() or document.read_bytes() != original or not state.is_dir():
            raise SystemExit("uninstall must remove the CLI and preserve user content and state")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--artifact-dir", type=Path)
    arguments = parser.parse_args()
    if arguments.artifact_dir is not None and not arguments.release:
        parser.error("--artifact-dir 只能与 --release 一起使用")
    run("uv", "run", "ruff", "check", "src", "tests", "scripts", "frontend/tests/e2e")
    run("uv", "run", "python", "-m", "pytest", "-q", "--durations=10")
    if arguments.release:
        version = project_version()
        check_tag(version)
        smoke_test_wheel(
            version,
            arguments.artifact_dir.resolve() if arguments.artifact_dir is not None else None,
        )


if __name__ == "__main__":
    main()
