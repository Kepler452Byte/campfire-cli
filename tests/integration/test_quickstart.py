from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from typer.testing import CliRunner

from campfire_cli.main import app


def test_documented_quickstart(tmp_path: Path) -> None:
    runner = CliRunner()
    root = tmp_path / "vault"
    created = runner.invoke(
        app, ["workspace", "create", "--id", "demo", "--path", str(root), "--default"]
    )
    assert created.exit_code == 0, created.output
    guide = (Path(__file__).parents[2] / "docs/quickstart.md").read_text(encoding="utf-8")
    inspections = []
    for block in re.findall(r"```text\n(.*?)```", guide, re.DOTALL):
        for line in block.strip().splitlines():
            args = shlex.split(line)
            assert args.pop(0) == "campfire"
            result = runner.invoke(app, args)
            assert result.exit_code == 0, result.output
            payload = json.loads(result.output)
            if "inspect" in args:
                inspections.append(payload)
    assert inspections[0]["relations"]["out_degree"] == 1
    assert inspections[1]["relations"]["in_degree"] == 1
    assert not list(root.rglob("_generated"))
    before = {p: p.read_bytes() for p in root.rglob("*.md")}
    result = runner.invoke(
        app, ["--workspace", "demo", "maintenance", "sync", "--scope", "mynote/Notes"]
    )
    assert result.exit_code == 0, result.output
    assert before == {p: p.read_bytes() for p in root.rglob("*.md")}
