from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from campfire_cli.app.document.schema import DocumentApplyRequest
from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.common.filesystem.locking import workspace_write_lock
from campfire_cli.config.settings import AgentResourceSettings
from campfire_cli.container import AppContainer
from campfire_cli.main import app

runner = CliRunner()


@pytest.fixture
def domain(workspace: Path) -> Path:
    root = workspace / "mywork" / "自选目录"
    root.mkdir()
    (root / "_领域.md").write_text(
        "---\nname: 自选目录\ndomain_id: chosen\ndomain_type: general\n"
        "moc: MOC-自选目录\nstatus: active\n---\n",
        encoding="utf-8",
    )
    return root


def test_tags_are_exact_and_before_count_and_limit(workspace: Path, domain: Path) -> None:
    document = AppContainer.build("test").document
    for name, tags in [
        ("A", ["主线"]),
        ("B", ["主线", "公司任务"]),
        ("C", ["主线", "公司任务"]),
        ("D", ["主线-extra"]),
        ("E", ["Work"]),
        ("F", []),
    ]:
        document.apply(
            DocumentApplyRequest(
                path=f"mywork/自选目录/{name}",
                document_type="task",
                values={"description": name, "task_status": "todo", "tags": json.dumps(tags)},
                confirm=True,
            )
        )
    result = runner.invoke(
        app,
        [
            "document",
            "list",
            "--type",
            "task",
            "--tags",
            "主线",
            "--tags",
            "公司任务",
            "--tags",
            "主线",
            "--limit",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert (data["total"], data["returned"], data["truncated"]) == (2, 1, True)
    assert data["items"][0]["name"] == "B"
    assert data["items"][0]["tags"] == ["主线", "公司任务"]
    assert document.list(tags=["不存在"]).total == 0
    assert document.list(tags=["work"]).total == 0
    assert document.list(tags=["Work"]).total == 1
    assert document.list(tags=[]).model_dump() == document.list().model_dump()
    path = domain / "任务-A.md"
    path.write_text(path.read_text().replace("主线", "其他"), encoding="utf-8")
    assert document.list(tags=["主线"]).total == 2
    assert document.list(tags=["其他"]).items[0].name == "A"


def test_apply_repairs_collision_and_references(workspace: Path, domain: Path) -> None:
    source = domain / "wyx.md"
    source.write_text("# wyx\n\n原始正文\n", encoding="utf-8")
    existing = domain / "记录-wyx.md"
    existing.write_text("已有内容\n", encoding="utf-8")
    document = AppContainer.build("test").document
    refer = document.apply(
        DocumentApplyRequest(
            path="mywork/自选目录/引用",
            document_type="record",
            values={"description": "引用", "related_docs": '["[[mywork/自选目录/wyx.md]]"]'},
            confirm=True,
        )
    )
    args = [
        "document",
        "apply",
        "--path",
        "mywork/自选目录/wyx.md",
        "--type",
        "record",
        "--name",
        "补充",
        "--set",
        "description=补充说明",
    ]
    preview = runner.invoke(app, args)
    assert preview.exit_code == 0, preview.output
    data = json.loads(preview.stdout)
    assert data["target"] == "mywork/自选目录/记录-补充.md"
    assert data["updated_references"] == [refer.target]
    confirmation = [
        *args,
        "--expected-hash",
        data["expected_hash"],
        "--expected-plan",
        data["expected_plan"],
        "--confirm",
    ]
    done = runner.invoke(app, confirmation)
    assert done.exit_code == 0, done.output
    assert not source.exists()
    repaired = parse_document((workspace / data["target"]).read_text())
    assert repaired.frontmatter["name"] == "补充"
    assert repaired.body == "# wyx\n\n原始正文\n"
    assert existing.read_text() == "已有内容\n"
    assert "[[mywork/自选目录/记录-补充.md]]" in (workspace / refer.target).read_text()


@pytest.mark.parametrize("changed", ["source", "target", "reference"])
def test_apply_named_repair_rejects_stale_plan(workspace: Path, domain: Path, changed: str) -> None:
    source = domain / "wyx.md"
    source.write_text("正文\n", encoding="utf-8")
    document = AppContainer.build("test").document
    ref = document.apply(
        DocumentApplyRequest(
            path="mywork/自选目录/引用",
            document_type="record",
            values={"description": "引用", "related_docs": '["[[mywork/自选目录/wyx.md]]"]'},
            confirm=True,
        )
    )
    args = dict(
        path="mywork/自选目录/wyx.md",
        document_type="record",
        name="唯一名称",
        values={"description": "说明"},
    )
    preview = document.apply(DocumentApplyRequest(**args))
    target = workspace / preview.target
    path = {"source": source, "target": target, "reference": workspace / ref.target}[changed]
    path.write_text(
        path.read_text() + "外部变化\n" if path.exists() else "已有目标\n", encoding="utf-8"
    )
    before = {p: p.read_bytes() for p in domain.glob("*.md")}
    done = document.apply(
        DocumentApplyRequest(
            **args,
            expected_hash=preview.expected_hash,
            expected_plan=preview.expected_plan,
            confirm=True,
        )
    )
    assert done.status == "blocked"
    assert not done.write_performed
    assert {p: p.read_bytes() for p in domain.glob("*.md")} == before


def test_cli_result_streams_and_lock_diagnostics(workspace: Path, domain: Path) -> None:
    args = [
        "document",
        "apply",
        "--path",
        "mywork/自选目录/记录",
        "--type",
        "record",
        "--set",
        "description=记录",
    ]
    preview = runner.invoke(app, args)
    assert preview.exit_code == 0 and preview.stderr == ""
    assert json.loads(preview.stdout)["status"] == "planned"
    missing = runner.invoke(app, args[:-2])
    assert missing.exit_code == 0
    assert json.loads(missing.stdout)["status"] == "needs-input"
    blocked = runner.invoke(app, [*args, "--set", "tags=invalid"])
    assert blocked.exit_code == 3 and blocked.stdout == ""
    assert len(blocked.stderr.splitlines()) == 1
    assert json.loads(blocked.stderr)["status"] == "blocked"
    sync = runner.invoke(app, ["maintenance", "sync", "--scope", "absent"])
    assert sync.exit_code == 3 and sync.stdout == ""
    assert json.loads(sync.stderr)["issues"][0]["code"] == "scope-missing"
    root = AppContainer.build("test").settings.state_root
    with workspace_write_lock(root):
        locked = runner.invoke(app, [*args, "--confirm"])
    assert locked.exit_code == 3 and locked.stdout == ""
    details = json.loads(locked.stderr)
    assert details["code"] == "workspace-locked"
    assert details["pid"] == os.getpid()
    retry = runner.invoke(app, [*args, "--confirm"])
    assert retry.exit_code == 0, retry.output


def test_client_entrypoints_and_override_notice(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CAMPFIRE_AGENT_HINT_PATH", raising=False)
    monkeypatch.delenv("CAMPFIRE_SKILL_TARGETS", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    settings = AgentResourceSettings.load()
    assert settings.hints == [tmp_path / "claude/CLAUDE.md", tmp_path / "codex/AGENTS.md"]
    assert tmp_path / "claude/skills" in settings.targets
    target = tmp_path / "codex/AGENTS.override.md"
    target.parent.mkdir()
    target.write_text("existing override", encoding="utf-8")
    result = AppContainer.build_skill().align(dry_run=True)
    entry = next(h for h in result["agent_hints"] if h["client"] == "codex")
    assert entry["loading_verified"] is False
    assert "AGENTS.override.md" in entry["loading_hint"]
    assert target.read_text() == "existing override"


def test_partial_write_failure_retains_facts_in_error_stream(workspace, monkeypatch):
    from campfire_cli.app.maintenance.service.maintenance_service import MaintenanceService

    monkeypatch.setattr(
        MaintenanceService,
        "sync",
        lambda *args: {
            "status": "blocked",
            "write_performed": True,
            "issues": [{"code": "rollback-incomplete", "path": "mywork/note.md"}],
        },
    )
    result = runner.invoke(app, ["maintenance", "sync"])
    assert result.exit_code == 3 and result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["write_performed"]
    assert payload["issues"][0]["code"] == "rollback-incomplete"


@pytest.mark.parametrize(
    "arguments, expected_code",
    [
        (["invalid-command"], 2),
        (["document", "apply"], 2),
        (["maintenance", "sync", "--scope", "missing"], 3),
    ],
)
def test_executable_errors_emit_only_json(workspace, arguments, expected_code):
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", "from campfire_cli.main import app; app()", *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected_code
    assert result.stdout == ""
    assert len(result.stderr.splitlines()) == 1
    assert json.loads(result.stderr)["status"] == ("blocked" if expected_code == 3 else "error")
