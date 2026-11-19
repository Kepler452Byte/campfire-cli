"""Run the actual HTTP application against disposable local Job state."""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from campfire_cli.app.job.schema.job_schema import Job
from campfire_cli.container import AppContainer

with tempfile.TemporaryDirectory(prefix="campfire-web-e2e-") as raw:
    os.environ["CAMPFIRE_HOME"] = str(Path(raw) / "home")
    project = Path(raw) / "home/jobs/scripts/growth"
    (project / "helpers").mkdir(parents=True)
    (project / "daily.py").write_text(
        "from helpers.study import collect\n\ndef main():\n    return collect()\n", encoding="utf-8"
    )
    (project / "helpers/study.py").write_text(
        "def collect():\n    return '学习记录'\n", encoding="utf-8"
    )
    (project / "unknown.custom").write_text("plain text", encoding="utf-8")
    (project / "binary.bin").write_bytes(b"a\0b")
    (project / "node_modules").mkdir()
    extra = Path(raw) / "home/jobs/scripts/unbound-project"
    extra.mkdir()
    (extra / "daily.py").write_text("print('未关联任务的脚本')\n", encoding="utf-8")
    service = AppContainer.build_job()
    job = Job(
        "seed",
        [sys.executable, "-c", "print('隔离环境')"],
        raw,
        {"kind": "manual"},
        name="预置任务",
        script_project="growth",
    )
    plan = service.change("create", job.id, job, False, None)
    service.change("create", job.id, job, True, plan["expected_plan"])
    service.runs.close()
    metadata = Path(".e2e-home.json")
    metadata.write_text(json.dumps({"home": os.environ["CAMPFIRE_HOME"]}))
    metadata.chmod(0o600)
    ready = Path(".e2e-web.json")
    child = None
    try:
        while True:
            with ready.open("w") as output:
                ready.chmod(0o600)
                child = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "campfire_cli.main",
                        "web",
                        "--port",
                        "4173",
                        "--no-open",
                    ],
                    stdout=output,
                )
                child.wait()
            time.sleep(0.1)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        for file in [metadata, ready, Path(".e2e-session.json")]:
            file.unlink(missing_ok=True)
