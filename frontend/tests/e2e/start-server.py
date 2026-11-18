"""Run the actual HTTP application against disposable local Job state."""

import json
import os
import sys
import tempfile
from pathlib import Path

import uvicorn

from campfire_cli.app.job.schema.job_schema import Job
from campfire_cli.container import AppContainer
from campfire_cli.web.server import create_app

with tempfile.TemporaryDirectory(prefix="campfire-web-e2e-") as raw:
    os.environ["CAMPFIRE_HOME"] = str(Path(raw) / "home")
    project = Path(raw) / "home/scripts/growth"
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
    app = create_app()
    state = {
        "cookies": [
            {
                "name": "campfire_session",
                "value": app.state.access.session,
                "domain": "127.0.0.1",
                "path": "/",
                "expires": -1,
                "httpOnly": True,
                "secure": False,
                "sameSite": "Strict",
            }
        ],
        "origins": [],
    }
    file = Path(".e2e-session.json")
    file.write_text(json.dumps(state))
    file.chmod(0o600)
    try:
        uvicorn.run(app, host="127.0.0.1", port=4173, access_log=False, log_level="warning")
    finally:
        file.unlink(missing_ok=True)
