from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from typer.testing import CliRunner

from campfire_cli.common.documents.markdown import parse_document
from campfire_cli.main import app


def test_published_creation_examples_and_follow_up(tmp_path: Path) -> None:
    runner = CliRunner()

    def invoke(arguments: list[str]) -> dict:
        result = runner.invoke(app, arguments)
        assert result.exit_code == 0, result.output
        return json.loads(result.output)

    vault = tmp_path / "demo"
    invoke(
        [
            "workspace",
            "create",
            "--id",
            "demo",
            "--path",
            str(vault),
            "--demo",
            "hello-world",
        ]
    )
    domain = invoke(
        [
            "--workspace",
            "demo",
            "workspace",
            "domain",
            "create",
            "--id",
            "practice",
            "--name",
            "开发实践",
            "--path",
            "mynote/开发实践",
            "--type",
            "knowledge-domain",
            "--governance",
            "knowledge-base",
            "--confirm",
        ]
    )
    assert domain["status"] == "created"
    resources = Path(__file__).resolve().parents[2] / "src/campfire_cli/resources/skills"
    for name in ("campfire-task-management", "campfire-document-capture"):
        text = (resources / name / "SKILL.md").read_text(encoding="utf-8")
        example = re.search(
            r"`(campfire --workspace (?:demo|<id>) document profile resolve --type \w+)`", text
        )
        assert example is not None
        contract = invoke(shlex.split(example[1].replace("<id>", "demo"))[1:])
        commands = [line for line in text.splitlines() if line.startswith("campfire ")]
        assert len(commands) == 2
        planned = invoke(shlex.split(commands[0])[1:])
        assert planned["status"] == "planned"
        assert planned["profile"] == contract["profile"]["name"]
        assert planned["expected_hash"] == "missing"
        assert planned["follow_up"] == []
        applied = invoke(shlex.split(commands[1])[1:])
        assert applied["status"] == "applied"
        assert applied["write_performed"]
        assert applied["target"] == planned["target"]
        path = vault / applied["target"]
        original = path.read_text(encoding="utf-8")
        path.write_text(original + "\n## 验证\n运行版本命令确认安装可用。\n", encoding="utf-8")
        assert parse_document(path.read_text(encoding="utf-8")).frontmatter == (
            parse_document(original).frontmatter
        )
        for follow_up in applied["follow_up"]:
            synced = invoke(
                [
                    "--workspace",
                    follow_up["workspace"],
                    *follow_up["command"].split(),
                    "--scope",
                    follow_up["scope"],
                ]
            )
            assert synced["status"] == "synced"
        checked = invoke(
            [
                "--workspace",
                "demo",
                "document",
                "check",
                "--path",
                applied["target"],
            ]
        )
        assert checked["status"] == "ok"
    assert invoke(["--workspace", "demo", "skill", "check"])["status"] == "ok"
