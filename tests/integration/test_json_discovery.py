import json

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from campfire_cli import __version__
from campfire_cli.main import app


def public_commands(command, path=()):
    yield path, command
    for name, child in getattr(command, "commands", {}).items():
        if not child.hidden:
            yield from public_commands(child, (*path, name))


@pytest.mark.parametrize("path,command", list(public_commands(get_command(app))))
def test_every_public_help_is_structured_json(path, command, tmp_path):
    result = CliRunner().invoke(app, [*path, "--help"], terminal_width=40)
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["command"] == ["campfire", *path]
    assert isinstance(payload["parameters"], list)
    for parameter in payload["parameters"]:
        assert {"name", "kind", "options", "type", "required", "default"} <= parameter.keys()
    assert "\x1b" not in result.stdout
    assert not (tmp_path / "campfire-home").exists()


@pytest.mark.parametrize("args", [[], ["video"], ["document"], ["--help"]])
def test_implicit_and_explicit_help_share_json_contract(args):
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "ok"
    assert result.stderr == ""


def test_version_and_tree_are_json():
    runner = CliRunner()
    assert json.loads(runner.invoke(app, ["version"]).stdout) == {
        "status": "ok",
        "version": __version__,
    }
    result = json.loads(runner.invoke(app, ["tree"]).stdout)
    assert result["tree"]["name"] == "campfire"
    video = next(c for c in result["tree"]["commands"] if c["name"] == "video")
    assert {c["name"] for c in video["commands"]} == {
        "setup",
        "prepare",
        "inspect",
        "deliver",
    }


def test_help_hides_internal_options_and_exposes_types():
    runner = CliRunner()
    upgrade = json.loads(runner.invoke(app, ["upgrade", "--help"]).stdout)
    assert "skip_package" not in {p["name"] for p in upgrade["parameters"]}
    removed = runner.invoke(app, ["video", "frames", "--help"])
    assert removed.exit_code != 0
    assert json.loads(removed.stderr)["status"] == "error"


@pytest.mark.parametrize("args", [["missing-command"], ["video", "prepare"], ["--bad-option"]])
def test_errors_are_single_json_on_stderr(args):
    result = CliRunner().invoke(app, args)
    assert result.exit_code != 0
    assert result.stdout == ""
    assert json.loads(result.stderr)["status"] == "error"
    assert len(result.stderr.splitlines()) == 1


def test_unexpected_failure_is_json(monkeypatch):
    def fail():
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr("campfire_cli.container.AppContainer.build_video", fail)
    result = CliRunner().invoke(app, ["video", "setup"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert json.loads(result.stderr)["code"] == "internal-error"
