from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from campfire_cli.app.video.schema.video_schema import Material
from campfire_cli.app.video.service.video_service import VideoService, digest
from campfire_cli.common.exceptions import GovernanceBlockedError, InputError
from campfire_cli.config.defaults import builtin_section
from campfire_cli.main import app


class FakeMedia:
    def run(self, request, timeout):
        if request.get("operation") == "validate-model":
            return {"status": "ready"}
        return {
            "duration": 2,
            "width": 16,
            "height": 16,
            "transcript_source": "user-provided",
            "segments": [{"start": 0, "end": 1, "text": "example"}],
        }


@pytest.fixture
def media(tmp_path, monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", lambda name: object())
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    transcript = tmp_path / "transcript.json"
    transcript.write_text("[]")
    service = VideoService(FakeMedia(), builtin_section("video"), tmp_path / "state")
    output = tmp_path / "bundle"
    return service, source, transcript, output


def prepare(media):
    service, source, transcript, output = media
    plan = service.prepare(source, output, transcript=transcript)
    return service.prepare(
        source, output, transcript=transcript, confirm=True, expected_plan=plan["expected_plan"]
    )


def draft_file(tmp_path, source):
    path = tmp_path / "draft.json"
    path.write_text(
        json.dumps(
            {
                "title": "Sample",
                "source_sha256": digest(source),
                "schema_version": 2,
                "output_kind": "transcript",
                "purpose": "保留原话记录",
                "sections": [
                    {
                        "title": "Section",
                        "body": "Full explanation.",
                        "segment_ids": [0],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_prepare_preview_no_writes(media):
    service, source, transcript, output = media
    plan = service.prepare(source, output, transcript=transcript)
    assert plan["status"] == "planned"
    assert not output.exists()
    assert source.read_bytes() == b"source"


def test_prepare_requires_current_plan(media):
    service, source, transcript, output = media
    plan = service.prepare(source, output, transcript=transcript)
    transcript.write_text('[{"changed":true}]')
    with pytest.raises(GovernanceBlockedError):
        service.prepare(
            source, output, transcript=transcript, confirm=True, expected_plan=plan["expected_plan"]
        )
    assert not output.exists()


def test_default_material_directory(media):
    service, source, transcript, _ = media
    output = service.state_root / "materials" / digest(source)
    plan = service.prepare(source, transcript=transcript)
    assert Path(plan["output"]) == output
    assert not service.state_root.exists()
    assert service.prepare(source, transcript=transcript) == plan
    result = service.prepare(
        source, transcript=transcript, confirm=True, expected_plan=plan["expected_plan"]
    )
    assert Path(result["material"]) == output / "material.json"
    assert service.inspect(output)["material"]["source_sha256"] == digest(source)
    assert source.read_bytes() == b"source"
    assert not list(output.rglob("*.mp4"))
    with pytest.raises(GovernanceBlockedError):
        service.prepare(source, transcript=transcript)


def test_default_material_source_change_invalidates_plan(media):
    service, source, transcript, _ = media
    plan = service.prepare(source, transcript=transcript)
    source.write_bytes(b"changed")
    with pytest.raises(GovernanceBlockedError):
        service.prepare(
            source, transcript=transcript, confirm=True, expected_plan=plan["expected_plan"]
        )
    assert not service.state_root.exists()


def test_cli_default_material_home(media, monkeypatch, tmp_path):
    from campfire_cli.container import AppContainer

    service, source, transcript, _ = media
    home = tmp_path / "custom-home"
    monkeypatch.setenv("CAMPFIRE_HOME", str(home))
    container = AppContainer.build_video()
    container.backend = service.backend
    monkeypatch.setattr(AppContainer, "build_video", lambda: container)
    args = ["video", "prepare", "--source", str(source), "--transcript", str(transcript)]
    runner = CliRunner()
    preview = runner.invoke(app, args)
    assert preview.exit_code == 0, preview.output
    plan = json.loads(preview.stdout)
    assert Path(plan["output"]) == home / "materials" / digest(source)
    result = runner.invoke(app, [*args, "--expected-plan", plan["expected_plan"], "--confirm"])
    assert result.exit_code == 0, result.output
    assert Path(json.loads(result.stdout)["material"]).is_file()


def test_prepare_and_inspect(media):
    service, source, _, output = media
    assert prepare(media)["status"] == "ready"
    report = service.inspect(output)
    assert report["material"]["source_sha256"] == digest(source)
    assert report["semantic_review_required"]
    with pytest.raises(GovernanceBlockedError):
        prepare(media)


def test_input_and_workspace_boundary(media, tmp_path):
    service, source, transcript, output = media
    with pytest.raises(InputError):
        service.prepare(Path("https://example.com/video"), output, transcript=transcript)
    (tmp_path / ".campfire.yaml").write_text("workspace: test")
    with pytest.raises(GovernanceBlockedError):
        service.prepare(source, output, transcript=transcript)


def test_transcript_requires_full_coverage_and_order(media, tmp_path):
    service, source, _, output = media
    prepare(media)
    draft = draft_file(tmp_path, source)
    service.validate(output, draft)
    content = json.loads(draft.read_text())
    content["sections"][0]["segment_ids"] = []
    draft.write_text(json.dumps(content))
    with pytest.raises(InputError):
        service.validate(output, draft)
    content["sections"][0]["segment_ids"] = [0]
    content["sections"][0]["segment_ids"] = [0, 0]
    draft.write_text(json.dumps(content))
    with pytest.raises(InputError):
        service.validate(output, draft)


def test_delivery_text_and_preserved_frontmatter(media, tmp_path):
    service, source, _, output = media
    prepare(media)
    draft = draft_file(tmp_path, source)
    root = tmp_path / "vault"
    root.mkdir()
    target = root / "note.md"
    original = "---\nname: preserved\n---\n\n<!-- CAMPFIRE:BODY -->\n"
    target.write_text(original, encoding="utf-8")
    plan = service.deliver(output, draft, target, root, tmp_path / "state")
    assert target.read_text(encoding="utf-8") == original
    result = service.deliver(
        output,
        draft,
        target,
        root,
        tmp_path / "state",
        confirm=True,
        expected_plan=plan["expected_plan"],
    )
    assert result["status"] == "applied"
    assert target.read_text(encoding="utf-8").startswith(original)
    assert not list(root.rglob("*.jpg"))
    assert not list(root.rglob("*.mp4"))
    with pytest.raises(GovernanceBlockedError):
        service.deliver(output, draft, target, root, tmp_path / "state")
    delivered = target.read_text(encoding="utf-8")
    for material_file in output.iterdir():
        material_file.unlink()
    output.rmdir()
    assert target.read_text(encoding="utf-8") == delivered
    assert str(output) not in delivered


def test_deliver_rejects_changed_draft(media, tmp_path):
    service, source, _, output = media
    prepare(media)
    draft = draft_file(tmp_path, source)
    target = tmp_path / "note.md"
    target.write_text("<!-- CAMPFIRE:BODY -->\n")
    plan = service.deliver(output, draft, target, tmp_path, tmp_path / "state")
    draft.write_text(draft.read_text().replace("Full explanation.", "New content."))
    with pytest.raises(GovernanceBlockedError):
        service.deliver(
            output,
            draft,
            target,
            tmp_path,
            tmp_path / "state",
            confirm=True,
            expected_plan=plan["expected_plan"],
        )
    assert target.read_text() == "<!-- CAMPFIRE:BODY -->\n"


def test_prepare_failure_cleans_only_staging(media):
    service, source, transcript, output = media
    plan = service.prepare(source, output, transcript=transcript)

    def fail(request, timeout):
        raise InputError("bad media")

    service.backend.run = fail
    with pytest.raises(InputError):
        service.prepare(
            source, output, transcript=transcript, confirm=True, expected_plan=plan["expected_plan"]
        )
    assert not output.exists()
    assert source.read_bytes() == b"source"
    assert not list(output.parent.glob(".campfire-video-*"))


def test_timestamp_schema_rejects_invalid():
    with pytest.raises(ValueError):
        Material(
            source_name="x",
            source_sha256="a" * 64,
            duration=1,
            width=16,
            height=16,
            transcript_source="test",
            segments=[{"start": 0, "end": 10, "text": "bad"}],
        )


def test_video_help_without_workspace():
    result = CliRunner().invoke(app, ["video", "prepare", "--help"], terminal_width=120)
    assert result.exit_code == 0
    help_data = json.loads(result.stdout)
    assert any("--expected-plan" in p["options"] for p in help_data["parameters"])


def test_binary_changeset_rolls_back(tmp_path, monkeypatch):
    from campfire_cli.common.filesystem import change_set

    image = tmp_path / "image.jpg"
    text = tmp_path / "note.md"
    text.write_text("original")

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(change_set, "atomic_write", fail)
    changes = change_set.FileChangeSet(
        writes=(
            change_set.FileWrite(image, b"new-image"),
            change_set.FileWrite(text, "new-body"),
        )
    )
    with pytest.raises(OSError):
        change_set.FileChangeExecutor(tmp_path, tmp_path / "state").execute(changes)
    assert not image.exists()
    assert text.read_text() == "original"


def test_real_video_decode(tmp_path):
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    from campfire_cli.common.media.media_backend import ProcessMediaBackend

    source = tmp_path / "fixture.mp4"
    with av.open(str(source), "w") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width = stream.height = 32
        stream.pix_fmt = "yuv420p"
        for i in range(20):
            frame = av.VideoFrame.from_ndarray(
                np.full((32, 32, 3), i * 10, dtype=np.uint8), format="rgb24"
            )
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    transcript = tmp_path / "transcript.json"
    transcript.write_text('[{"start":0,"end":1,"text":"fixture"}]')
    service = VideoService(ProcessMediaBackend(), builtin_section("video"), tmp_path / "state")
    output = tmp_path / "bundle"
    plan = service.prepare(source, output, transcript=transcript)
    result = service.prepare(
        source, output, transcript=transcript, confirm=True, expected_plan=plan["expected_plan"]
    )
    assert result["segments"] == 1
    assert not list(output.glob("*.jpg"))
    assert service.load(output)[1].schema_version == 2


def test_deliver_cli_reuses_document_governance(media, tmp_path):
    _, source, _, output = media
    prepare(media)
    draft = draft_file(tmp_path, source)
    runner = CliRunner()
    root = tmp_path / "vault"

    def command(args):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        return json.loads(result.stdout)

    command(["workspace", "create", "--id", "video-test", "--path", str(root)])
    prefix = ["--workspace", "video-test"]
    command(
        prefix
        + [
            "workspace",
            "domain",
            "create",
            "--id",
            "learning",
            "--name",
            "Learning",
            "--path",
            "mynote/Learning",
            "--type",
            "knowledge-domain",
            "--confirm",
        ]
    )
    create = prefix + [
        "document",
        "apply",
        "--path",
        "mynote/Learning/Sample",
        "--type",
        "knowledge",
        "--set",
        "description=Video test",
    ]
    plan = command(create)
    created = command(create + ["--expected-hash", plan["expected_hash"], "--confirm"])
    deliver = prefix + [
        "video",
        "deliver",
        "--bundle",
        str(output),
        "--draft",
        str(draft),
        "--path",
        created["target"],
    ]
    plan = command(deliver)
    assert command(deliver + ["--expected-plan", plan["expected_plan"], "--confirm"])[
        "write_performed"
    ]
    inspection = command(prefix + ["document", "inspect", "--path", created["target"]])
    assert not inspection["issues"]
    assert not list(root.rglob("*.jpg"))


@pytest.mark.parametrize("cancel", [False, True])
def test_timeout_kills_and_reaps_worker(monkeypatch, cancel):
    import subprocess
    from unittest.mock import Mock

    from campfire_cli.common.exceptions import AppError
    from campfire_cli.common.media.media_backend import ProcessMediaBackend

    process = Mock(pid=1)
    interruption = KeyboardInterrupt() if cancel else subprocess.TimeoutExpired("worker", 1)
    process.communicate.side_effect = [interruption, ("", "")]
    parent = Mock()
    parent.children.return_value = []
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: process)
    monkeypatch.setattr("psutil.Process", lambda pid: parent)
    with pytest.raises(AppError) as error:
        ProcessMediaBackend().run({}, 1)
    assert error.value.code == ("cancelled" if cancel else "video-timeout")
    process.kill.assert_called_once()
    assert process.communicate.call_count == 2


def test_same_source_different_outputs_allowed(media, tmp_path):
    service, source, _, output = media
    prepare(media)
    draft = draft_file(tmp_path, source)
    for kind in ("transcript", "article"):
        data = json.loads(draft.read_text())
        data["output_kind"] = kind
        draft.write_text(json.dumps(data))
        target = tmp_path / f"{kind}.md"
        target.write_text("<!-- CAMPFIRE:BODY -->\n")
        plan = service.deliver(output, draft, target, tmp_path, tmp_path / "state")
        service.deliver(
            output,
            draft,
            target,
            tmp_path,
            tmp_path / "state",
            confirm=True,
            expected_plan=plan["expected_plan"],
        )
        assert kind in target.read_text(encoding="utf-8")
        with pytest.raises(GovernanceBlockedError):
            service.deliver(output, draft, target, tmp_path, tmp_path / "state")


def test_binary_plan_digest(tmp_path):
    from campfire_cli.common.filesystem.change_set import FileChangeSet, FileWrite
    from campfire_cli.common.filesystem.plan import plan_digest

    first = FileChangeSet(writes=(FileWrite(tmp_path / "a.jpg", b"one"),))
    second = FileChangeSet(writes=(FileWrite(tmp_path / "a.jpg", b"two"),))
    assert plan_digest(tmp_path, first) != plan_digest(tmp_path, second)


def test_whisper_audio_decoder_compatibility(tmp_path):
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    audio = pytest.importorskip("faster_whisper.audio")
    path = tmp_path / "tone.wav"
    with av.open(str(path), "w") as container:
        stream = container.add_stream("pcm_s16le", rate=16000)
        samples = (np.sin(np.arange(16000) * 2 * np.pi * 440 / 16000) * 1000).astype("int16")
        frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = 16000
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    decoded = audio.decode_audio(str(path))
    assert len(decoded) == 16000
    assert np.max(np.abs(decoded)) > 0


@pytest.mark.parametrize("body", ["![x](https://example.com/a.jpg)", "<img src='a'>", "![[a]]"])
def test_embedded_images_are_rejected(media, tmp_path, body):
    service, source, _, output = media
    prepare(media)
    draft = draft_file(tmp_path, source)
    data = json.loads(draft.read_text())
    data["sections"][0]["body"] = body
    draft.write_text(json.dumps(data))
    with pytest.raises(InputError):
        service.validate(output, draft)


def test_image_syntax_in_code_is_preserved(media, tmp_path):
    service, source, _, output = media
    prepare(media)
    draft = draft_file(tmp_path, source)
    data = json.loads(draft.read_text())
    data["sections"][0]["body"] = "Example: `![x](image.png)`\n\n```html\n<img src='x'>\n```"
    draft.write_text(json.dumps(data))
    service.validate(output, draft)


def test_io_error_has_json_contract(monkeypatch, tmp_path):
    from unittest.mock import Mock

    service = Mock()
    service.inspect.side_effect = PermissionError("denied")
    monkeypatch.setattr("campfire_cli.container.AppContainer.build_video", lambda: service)
    result = CliRunner().invoke(app, ["video", "inspect", "--bundle", str(tmp_path)])
    assert result.exit_code == 2
    assert json.loads(result.stderr)["code"] == "video-io-error"


def test_corrupt_media_worker_is_contained(tmp_path):
    pytest.importorskip("av")
    from campfire_cli.common.exceptions import AppError
    from campfire_cli.common.media.media_backend import ProcessMediaBackend

    source = tmp_path / "broken.mp4"
    source.write_bytes(b"not a video")
    with pytest.raises(AppError) as error:
        ProcessMediaBackend().run(
            {
                "source": str(source),
                "output": str(tmp_path),
                "limits": builtin_section("video"),
                "transcript": None,
            },
            15,
        )
    assert error.value.code == "video-processing-failed"
    assert source.read_bytes() == b"not a video"


def test_resource_limit_prevents_processing(media):
    service, source, transcript, output = media
    service.limits["max_bytes"] = 1
    with pytest.raises(InputError):
        service.prepare(source, output, transcript=transcript)
    assert not output.exists()


def test_changed_source_blocks_commit(media):
    service, source, transcript, output = media
    run = service.backend.run

    def change(request, timeout):
        result = run(request, timeout)
        source.write_bytes(b"external edit")
        return result

    service.backend.run = change
    plan = service.prepare(source, output, transcript=transcript)
    with pytest.raises(GovernanceBlockedError):
        service.prepare(
            source, output, transcript=transcript, confirm=True, expected_plan=plan["expected_plan"]
        )
    assert source.read_bytes() == b"external edit"
    assert not output.exists()


def test_incomplete_model_does_not_download(media, tmp_path):
    service, source, _, output = media
    model = tmp_path / "model"
    model.mkdir()
    (model / "model.bin").write_bytes(b"incomplete")
    with pytest.raises(InputError):
        service.prepare(source, output, model=model)
    assert list(model.iterdir()) == [model / "model.bin"]
    assert not output.exists()


def install_fake_model(path):
    path.mkdir(parents=True, exist_ok=True)
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (path / name).write_bytes(b"model-fixture")


class FakeRuntime:
    def __init__(self):
        self.missing = ["video-dependency"]
        self.calls = 0

    def plan(self):
        return {"python": "isolated-python", "missing": self.missing, "installer": ["installer"]}

    def install(self, plan, timeout):
        self.calls += 1
        self.missing = []


def test_default_model_preview_is_readonly_and_confirm_downloads_once(media):
    service, source, _, output = media
    calls = []

    def download(repository, revision, destination):
        calls.append((repository, revision))
        install_fake_model(destination)

    service.downloader = download
    service.runtime = FakeRuntime()
    plan = service.setup()
    model = service.state_root / "models" / "faster-whisper-small"
    assert plan["model"] == str(model)
    assert plan["model_download"]["repository"] == "Systran/faster-whisper-small"
    assert plan["model_download"]["approximate_bytes"] > 400_000_000
    assert not service.state_root.exists()
    assert not calls
    with pytest.raises(GovernanceBlockedError):
        service.setup(confirm=True, expected_plan="outdated")
    assert not calls
    result = service.setup(confirm=True, expected_plan=plan["expected_plan"])
    assert result["status"] == "ready"
    assert service.model_complete(model)
    assert len(calls) == 1
    second = service.setup()
    assert second["model_download"] is None
    assert (
        service.setup(confirm=True, expected_plan=second["expected_plan"])["write_performed"]
        is False
    )
    assert len(calls) == 1
    assert service.runtime.calls == 1
    assert not output.exists()


def test_explicit_model_and_transcript_skip_default_download(media, tmp_path):
    service, source, transcript, output = media
    model = tmp_path / "custom"
    install_fake_model(model)
    assert service.prepare(source, output, model=model)["model"] == str(model)
    assert "model_download" not in service.prepare(source, output, model=model)
    assert service.prepare(source, output, transcript=transcript)["model"] is None
    with pytest.raises(InputError):
        service.prepare(source, output, model=tmp_path / "missing")
    with pytest.raises(InputError):
        service.prepare(source, output, model=model, transcript=transcript)
    assert not service.state_root.exists()


@pytest.mark.parametrize("failure", ["network", "incomplete", "cancelled"])
def test_model_download_failure_leaves_no_installed_model(media, failure):
    service, source, _, output = media

    def download(repository, revision, destination):
        (destination / "model.bin").write_bytes(b"partial")
        if failure == "network":
            raise OSError("offline")
        if failure == "cancelled":
            raise KeyboardInterrupt

    service.downloader = download
    service.runtime = FakeRuntime()
    plan = service.setup()
    error = {"network": OSError, "incomplete": InputError, "cancelled": KeyboardInterrupt}[failure]
    with pytest.raises(error):
        service.setup(confirm=True, expected_plan=plan["expected_plan"])
    assert not service.default_model.exists()
    assert not output.exists()
    assert not list(service.default_model.parent.glob(".campfire-model-*"))
    assert service.runtime.missing == []
    service.downloader = lambda repository, revision, path: install_fake_model(path)
    retry = service.setup()
    service.setup(confirm=True, expected_plan=retry["expected_plan"])
    assert service.runtime.calls == 1


def test_incomplete_default_model_is_not_overwritten(media):
    service, source, _, output = media
    service.default_model.mkdir(parents=True)
    weight = service.default_model / "model.bin"
    weight.write_bytes(b"existing")
    with pytest.raises(InputError):
        service.prepare(source, output)
    assert weight.read_bytes() == b"existing"


def test_model_download_does_not_replace_concurrent_directory(media):
    service, source, _, output = media

    def download(repository, revision, destination):
        install_fake_model(destination)
        service.default_model.mkdir()
        (service.default_model / "human.txt").write_text("keep")

    service.downloader = download
    service.runtime = FakeRuntime()
    plan = service.setup()
    with pytest.raises(GovernanceBlockedError):
        service.setup(confirm=True, expected_plan=plan["expected_plan"])
    assert (service.default_model / "human.txt").read_text() == "keep"
    assert not list(service.default_model.parent.glob(".campfire-model-*"))


def test_model_revision_change_requires_new_confirmation(media):
    service, source, _, output = media
    service.runtime = FakeRuntime()
    plan = service.setup()
    service.model_config["revision"] = "a" * 40
    with pytest.raises(GovernanceBlockedError):
        service.setup(confirm=True, expected_plan=plan["expected_plan"])
    assert not service.state_root.exists()


def test_model_path_follows_campfire_home(tmp_path, monkeypatch):
    from campfire_cli.container import AppContainer

    home = tmp_path / "custom-home"
    monkeypatch.setenv("CAMPFIRE_HOME", str(home))
    assert AppContainer.build_video().default_model == home / "models" / "faster-whisper-small"
    monkeypatch.delenv("CAMPFIRE_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert (
        AppContainer.build_video().default_model
        == tmp_path / ".campfire" / "models" / "faster-whisper-small"
    )


def test_default_model_cli_preview_without_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("CAMPFIRE_HOME", str(tmp_path / "home"))
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"source")
    result = CliRunner().invoke(app, ["video", "setup"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["model_download"]["path"].endswith("faster-whisper-small")
    assert not (tmp_path / "home").exists()


def test_prepare_never_initializes_model_or_dependencies(media):
    service, source, _, output = media
    service.runtime = FakeRuntime()
    service.downloader = lambda *args: pytest.fail("prepare must not download")
    with pytest.raises(InputError) as error:
        service.prepare(source, output)
    assert error.value.code == "video-not-ready"
    assert service.runtime.calls == 0
    assert not service.state_root.exists()


def test_setup_install_failure_stops_before_model_download(media):
    service, _, _, _ = media
    service.runtime = FakeRuntime()
    service.downloader = lambda *args: pytest.fail("download must follow successful install")

    def fail(plan, timeout):
        raise InputError("install failed")

    service.runtime.install = fail
    plan = service.setup()
    with pytest.raises(InputError):
        service.setup(confirm=True, expected_plan=plan["expected_plan"])
    assert not service.default_model.exists()


def test_setup_validation_failure_preserves_installed_model(media):
    service, _, _, _ = media
    service.runtime = FakeRuntime()
    service.downloader = lambda repo, revision, path: install_fake_model(path)

    def fail(request, timeout):
        raise InputError("model failed to load")

    service.backend.run = fail
    plan = service.setup()
    with pytest.raises(InputError):
        service.setup(confirm=True, expected_plan=plan["expected_plan"])
    assert service.model_complete(service.default_model)


def test_setup_without_safe_installer_is_readonly(media):
    service, _, _, _ = media
    service.runtime = FakeRuntime()
    service.runtime.plan = lambda: {"missing": ["dependency"], "installer": None}
    assert service.setup()["status"] == "needs-input"
    assert service.setup(confirm=True)["write_performed"] is False
    assert not service.state_root.exists()


def test_download_adapter_pins_snapshot_and_wraps_network_failure(tmp_path, monkeypatch, capsys):
    hub = pytest.importorskip("huggingface_hub")
    from campfire_cli.common.exceptions import AppError
    from campfire_cli.common.media.model_download import download_model

    calls = []

    def snapshot(**kwargs):
        import sys

        calls.append(kwargs)
        print("download progress")
        print("download warning", file=sys.stderr)

    monkeypatch.setattr(hub, "snapshot_download", snapshot)
    download_model("owner/model", "a" * 40, tmp_path)
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert calls[0]["revision"] == "a" * 40
    assert calls[0]["local_dir"] == tmp_path
    assert calls[0]["token"] is False
    assert "model.bin" in calls[0]["allow_patterns"]

    def offline(**kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(hub, "snapshot_download", offline)
    with pytest.raises(AppError) as error:
        download_model("owner/model", "a" * 40, tmp_path)
    assert error.value.code == "video-model-download-failed"


def test_article_reorder_and_explained_omission(media, tmp_path):
    service, source, _, output = media
    prepare(media)
    manifest = output / "material.json"
    data = json.loads(manifest.read_text())
    data["segments"] += [{"start": 1, "end": 2, "text": "second"}]
    manifest.write_text(json.dumps(data))
    draft = draft_file(tmp_path, source)
    content = json.loads(draft.read_text())
    content["sections"][0]["segment_ids"] = [1, 0]
    draft.write_text(json.dumps(content))
    with pytest.raises(InputError):
        service.validate(output, draft)
    content["output_kind"] = "article"
    draft.write_text(json.dumps(content))
    service.validate(output, draft)
    content["sections"][0]["segment_ids"] = [1]
    draft.write_text(json.dumps(content))
    with pytest.raises(InputError):
        service.validate(output, draft)
    content["omissions"] = [{"segment_ids": [0], "reason": "Opening outside tutorial scope"}]
    draft.write_text(json.dumps(content))
    service.validate(output, draft)
    content["omissions"][0]["segment_ids"] = [1]
    draft.write_text(json.dumps(content))
    with pytest.raises(InputError):
        service.validate(output, draft)


def test_alpha_material_readonly_and_draft_rejected(media, tmp_path):
    service, source, _, output = media
    prepare(media)
    manifest = output / "material.json"
    data = json.loads(manifest.read_text())
    data["schema_version"] = 1
    data["frames"] = [{"path": "../missing.jpg"}]
    original = json.dumps(data).encode()
    manifest.write_bytes(original)
    assert "Alpha" in service.load(output)[1].warnings[-1]
    assert manifest.read_bytes() == original
    draft = draft_file(tmp_path, source)
    content = json.loads(draft.read_text())
    content.pop("schema_version")
    content["visual_reviewed"] = True
    draft.write_text(json.dumps(content))
    with pytest.raises(InputError, match="schema_version=2"):
        service.validate(output, draft)


@pytest.mark.parametrize("bad_id", [-1, True, "0", 0.5, 999])
def test_segment_ids_are_strict_and_bounded(media, tmp_path, bad_id):
    service, source, _, output = media
    prepare(media)
    draft = draft_file(tmp_path, source)
    content = json.loads(draft.read_text())
    content["sections"][0]["segment_ids"] = [bad_id]
    draft.write_text(json.dumps(content))
    with pytest.raises(InputError):
        service.validate(output, draft)


def test_delivery_rechecks_inputs_under_lock(media, tmp_path, monkeypatch):
    from campfire_cli.common.filesystem.change_set import FileChangeExecutor

    service, source, _, output = media
    prepare(media)
    draft = draft_file(tmp_path, source)
    target = tmp_path / "target.md"
    target.write_text("<!-- CAMPFIRE:BODY -->\n")
    plan = service.deliver(output, draft, target, tmp_path, tmp_path / "state")
    execute = FileChangeExecutor.execute

    def race(executor, changes, **kwargs):
        draft.write_text(draft.read_text().replace("Full explanation.", "Race changed content."))
        return execute(executor, changes, **kwargs)

    monkeypatch.setattr(FileChangeExecutor, "execute", race)
    with pytest.raises(GovernanceBlockedError):
        service.deliver(
            output,
            draft,
            target,
            tmp_path,
            tmp_path / "state",
            confirm=True,
            expected_plan=plan["expected_plan"],
        )
    assert target.read_text() == "<!-- CAMPFIRE:BODY -->\n"


def test_legacy_image_limits_reported_and_ignored(media):
    service, _, _, _ = media
    config = builtin_section("video")
    config["max_frames"] = "obsolete"
    updated = VideoService(service.backend, config, service.state_root)
    assert updated.ignored_config == ["max_frames"]
    assert "max_frames" not in updated.limits
