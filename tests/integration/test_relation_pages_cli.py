from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_relation_queries_and_sync_across_cli_processes(workspace: Path) -> None:
    def cli(*args: str) -> dict:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from campfire_cli.main import app; app()",
                "--workspace",
                "test",
                *args,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    cli(
        "workspace",
        "domain",
        "create",
        "--id",
        "example",
        "--name",
        "Example",
        "--path",
        "mynote/Example",
        "--type",
        "knowledge-domain",
        "--governance",
        "knowledge-base",
        "--confirm",
    )
    target = "mynote/Example/知识-Target.md"
    source = "mynote/Example/知识-Source.md"
    for path in (target, source):
        args = [
            "document",
            "apply",
            "--path",
            path,
            "--type",
            "knowledge",
            "--set",
            "description=CLI end-to-end test",
        ]
        if path == source:
            args += ["--set", "related_docs=" + json.dumps([f"[[{target}]]"])]
        preview = cli(*args)
        assert preview["status"] == "planned"
        assert (
            cli(*args, "--expected-hash", preview["expected_hash"], "--confirm")["status"]
            == "applied"
        )
    assert cli("document", "inspect", "--path", source)["relations"]["out_degree"] == 1
    assert cli("document", "inspect", "--path", target)["relations"]["in_degree"] == 1

    root = workspace / "mynote/Example"
    moc = root / "_总览/MOC-Example总览.md"
    legacy = root / "_generated/相关文档-Example.md"
    legacy.parent.mkdir()
    legacy.write_text("Legacy page with user notes\n", encoding="utf-8")
    content = (
        moc.read_text(encoding="utf-8").replace(
            "<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->",
            "## 自动关系\n- [[相关文档-Example]]\n<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->",
        )
        + "\nAuthored text\n"
    )
    moc.write_text(content, encoding="utf-8")
    args = ("maintenance", "sync", "--scope", "mynote/Example")
    assert cli(*args, "--dry-run")["status"] == "dry-run"
    assert moc.read_text(encoding="utf-8") == content
    assert cli(*args)["status"] == "synced"
    assert "## 自动关系" not in moc.read_text(encoding="utf-8")
    assert moc.read_text(encoding="utf-8").endswith("Authored text\n")
    assert legacy.read_text(encoding="utf-8") == "Legacy page with user notes\n"
    legacy.unlink()
    legacy.parent.rmdir()
    assert cli(*args)["generated_file_count"] == 0
    assert not legacy.parent.exists()

    (workspace / target).unlink()
    result = cli("document", "inspect", "--path", source)
    assert result["relations"]["out_degree"] == 0
    assert result["relations"]["unresolved"][0]["resolution"] == "missing"
    assert not legacy.parent.exists()
