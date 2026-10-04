from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
import shutil
import tempfile
from pathlib import Path

from pydantic import ValidationError

from campfire_cli.app.video.schema.video_schema import Draft, Frame, Material
from campfire_cli.app.video.service.video_protocol import (
    MediaBackend,
    ModelDownloader,
    VideoRuntime,
)
from campfire_cli.common.exceptions import (
    AppError,
    ConfigurationError,
    GovernanceBlockedError,
    InputError,
)
from campfire_cli.common.filesystem.atomic import atomic_write
from campfire_cli.common.filesystem.change_set import FileChangeExecutor, FileChangeSet, FileWrite
from campfire_cli.common.filesystem.locking import workspace_write_lock


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked_path(path: Path) -> Path:
    path = path.expanduser().absolute()
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise InputError("不接受软链接或目录联接", field="path", expected_type="local path")
    return path.resolve()


def timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02}:{total // 60 % 60:02}:{total % 60:02}"


class VideoService:
    """Prepare local evidence and deliver reviewed content without acquiring online media."""

    def __init__(
        self,
        backend: MediaBackend,
        limits: dict,
        state_root: Path,
        downloader: ModelDownloader | None = None,
        runtime: VideoRuntime | None = None,
    ) -> None:
        self.model_config = limits.get("model", {})
        if not isinstance(self.model_config, dict):
            raise ConfigurationError("video.model 须为模型配置对象")
        limits = {key: value for key, value in limits.items() if key != "model"}
        if any(type(v) is not int or v <= 0 for v in limits.values()):
            raise ConfigurationError("video 配置限制须为正整数")
        repository = self.model_config.get("repository", "")
        revision = self.model_config.get("revision", "")
        size = self.model_config.get("approximate_bytes")
        if (
            not isinstance(repository, str)
            or not re.fullmatch(r"[\w-]+/[\w-]+", repository)
            or not isinstance(revision, str)
            or not re.fullmatch(r"[0-9a-f]{40}", revision)
            or type(size) is not int
            or size <= 0
        ):
            raise ConfigurationError("video.model 须指定模型仓库、完整提交哈希及正整数体积")
        self.backend = backend
        self.limits = limits
        self.state_root = state_root
        self.default_model = state_root / "models" / repository.split("/")[-1]
        self.downloader = downloader
        self.runtime = runtime

    def setup(self, *, confirm: bool = False, expected_plan: str | None = None) -> dict:
        if self.runtime is None:
            raise InputError("视频初始化不可用；请修复 Campfire 安装")
        model = checked_path(self.default_model)
        if model.exists() and not self.model_complete(model):
            raise InputError("已有模型目录不完整；请检查后重试，不自动覆盖", field="model")
        environment = self.runtime.plan()
        download = None if model.exists() else {**self.model_config, "path": str(model)}
        signature = {"environment": environment, "model": str(model), "download": download}
        plan = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
        if environment["missing"] and not environment["installer"]:
            return {
                "status": "needs-input",
                "write_performed": False,
                "skipped": ["dependency-install", "model-download", "model-validation"],
                "hint": "需在隔离环境安装 Campfire，并提供 uv 或该环境的 pip；不修改系统 Python",
            }
        if not confirm:
            return {
                "status": "planned",
                "expected_plan": plan,
                "python": environment["python"],
                "dependencies": environment["missing"],
                "installer": environment["installer"] if environment["missing"] else None,
                "model": str(model),
                "model_download": download,
                "write_performed": False,
            }
        if expected_plan != plan:
            raise GovernanceBlockedError("环境或模型计划已变化；重新预览 video setup")
        if environment["missing"]:
            self.runtime.install(environment, self.limits["timeout"])
        if download:
            self._download_model(model)
        self.backend.run(
            {"operation": "validate-model", "model": str(model)}, self.limits["timeout"]
        )
        return {
            "status": "ready",
            "model": str(model),
            "validation": "passed",
            "write_performed": bool(environment["missing"] or download),
        }

    @staticmethod
    def model_complete(model: Path) -> bool:
        paths = [
            checked_path(model / name) for name in ("model.bin", "config.json", "tokenizer.json")
        ]
        return all(path.is_file() and path.stat().st_size > 0 for path in paths)

    def _download_model(self, model: Path) -> None:
        if self.downloader is None:
            raise InputError("模型下载器不可用；使用 --model 指定已下载模型", field="model")
        checked_path(model)
        model.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".campfire-model-", dir=model.parent))
        try:
            self.downloader(self.model_config["repository"], self.model_config["revision"], staging)
            if not self.model_complete(staging):
                raise InputError("下载的模型不完整，未安装；请重新预览后重试", field="model")
            with workspace_write_lock(model.parent):
                checked_path(model)
                if model.exists():
                    raise GovernanceBlockedError("模型目录在下载期间出现；重新预览，不覆盖已有内容")
                staging.rename(model)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def prepare(
        self,
        source: Path,
        output: Path | None = None,
        *,
        model: Path | None = None,
        transcript: Path | None = None,
        confirm: bool = False,
        expected_plan: str | None = None,
    ) -> dict:
        source = checked_path(source)
        if not source.is_file() or not 0 < source.stat().st_size <= self.limits["max_bytes"]:
            raise InputError("输入须为大小限制内的本地视频文件", field="source")
        source_hash = digest(source)
        output = checked_path(
            output if output is not None else self.state_root / "materials" / source_hash
        )
        if output.exists():
            raise GovernanceBlockedError("素材目录已存在；复用其中材料或选择新的目录")
        if any((p / ".campfire.yaml").exists() for p in (output, *output.parents)):
            raise GovernanceBlockedError("临时素材目录不能位于 Workspace 内")
        if model is not None and transcript is not None:
            raise InputError("--model 与 --transcript 不能同时指定", field="model")
        if model is None and transcript is None:
            model = self.default_model
        if model is not None:
            model = checked_path(model)
            if not self.model_complete(model):
                raise InputError(
                    "本地模型缺失或不完整；先运行 campfire video setup，或指定有效 --model",
                    code="video-not-ready",
                    field="model",
                    path=str(model),
                )
        if transcript is not None:
            transcript = checked_path(transcript)
            if (
                not transcript.is_file()
                or transcript.stat().st_size > self.limits["max_text_bytes"]
            ):
                raise InputError("字幕 JSON 不存在或过大", field="transcript")
        request = {
            "source": str(source),
            "output": str(output),
            "limits": self.limits,
            "model": str(model) if model else None,
            "transcript": str(transcript) if transcript else None,
        }
        signature = {
            **request,
            "source_hash": source_hash,
            "transcript_hash": digest(transcript) if transcript else None,
        }
        plan = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
        if not confirm:
            return {
                "status": "planned",
                "expected_plan": plan,
                "output": str(output),
                "source_sha256": source_hash,
                "limits": self.limits,
                "model": str(model) if model else None,
                "write_performed": False,
            }
        if expected_plan != plan:
            raise GovernanceBlockedError("输入或计划已变化；重新预览并带回 expected_plan")
        required = ["av", "PIL"] + (["faster_whisper"] if model else [])
        missing = [name for name in required if importlib.util.find_spec(name) is None]
        if missing:
            raise InputError(
                "缺少视频依赖；先运行 campfire video setup",
                code="video-not-ready",
                missing=missing,
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".campfire-video-", dir=output.parent))
        try:
            data = self.backend.run({**request, "output": str(staging)}, self.limits["timeout"])
            material = Material(
                source_name=source.name,
                source_sha256=source_hash,
                **data,
                warnings=["自动转写和稀疏截图未经语义核验，须逐段阅读并检查关键画面。"],
            )
            if not material.segments:
                material.warnings.append("没有可用转写；须按画面整理，不能声称口播覆盖完整。")
            atomic_write(staging / "material.json", material.model_dump_json(indent=2))
            with workspace_write_lock(self.state_root):
                checked_path(output)
                if output.exists() or digest(source) != source_hash:
                    raise GovernanceBlockedError("来源或目标在处理期间变化，拒绝提交素材")
                if transcript and digest(transcript) != signature["transcript_hash"]:
                    raise GovernanceBlockedError("字幕在处理期间变化")
                staging.rename(output)
        except ValidationError as exc:
            raise InputError("媒体时间轴或转写格式无效", detail=str(exc)) from exc
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return {
            "status": "ready",
            "material": str(output / "material.json"),
            "segments": len(material.segments),
            "frames": len(material.frames),
            "duration": material.duration,
            "warnings": material.warnings,
            "write_performed": True,
        }

    def load(self, bundle: Path) -> tuple[Path, Material]:
        bundle = checked_path(bundle)
        path = checked_path(bundle / "material.json")
        if not path.is_file() or path.stat().st_size > self.limits["max_text_bytes"]:
            raise InputError("素材清单不存在或过大", field="bundle")
        try:
            material = Material.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise InputError("素材清单格式无效", field="bundle", detail=str(exc)) from exc
        if len(material.frames) > self.limits["max_frames"]:
            raise InputError("截图数量超过限制")
        for frame in material.frames:
            path = checked_path(bundle / frame.path)
            if path.parent != bundle or path.suffix != ".jpg":
                raise InputError("截图路径必须是素材目录内的 JPEG 文件名")
            if not path.is_file() or path.stat().st_size > self.limits["max_text_bytes"]:
                raise InputError("截图缺失或过大")
            if digest(path) != frame.sha256:
                raise GovernanceBlockedError("截图内容与清单哈希不符")
        return bundle, material

    def frames(
        self,
        source: Path,
        bundle: Path,
        times: list[float],
        *,
        confirm: bool = False,
        expected_plan: str | None = None,
    ) -> dict:
        bundle, material = self.load(bundle)
        source = checked_path(source)
        if not source.is_file() or digest(source) != material.source_sha256:
            raise GovernanceBlockedError("补帧源视频与素材哈希不一致")
        if not times or any(not math.isfinite(t) or not 0 <= t < material.duration for t in times):
            raise InputError("截图时间须为视频时长内的秒数", field="at")
        if len(times) + len(material.frames) > self.limits["max_frames"]:
            raise InputError("补帧后数量超过上限")
        original = (bundle / "material.json").read_bytes()
        if Material.model_validate_json(original) != material:
            raise GovernanceBlockedError("读取期间素材变化，请重试")
        plan = hashlib.sha256(original + json.dumps(times).encode()).hexdigest()
        if not confirm:
            return {"status": "planned", "expected_plan": plan, "write_performed": False}
        if expected_plan != plan:
            raise GovernanceBlockedError("素材或时间参数变化，重新预览")
        staging = Path(tempfile.mkdtemp(prefix=".campfire-frames-", dir=bundle.parent))
        try:
            data = self.backend.run(
                {
                    "source": str(source),
                    "output": str(staging),
                    "limits": self.limits,
                    "frames_only": True,
                    "times": times,
                },
                self.limits["timeout"],
            )
            existing = {frame.id: frame for frame in material.frames}
            writes = []
            expected = {bundle / "material.json": hashlib.sha256(original).hexdigest()}
            for value in data["frames"]:
                frame = Frame.model_validate(value)
                if frame.id in existing:
                    continue
                path = checked_path(bundle / frame.path)
                if path.parent != bundle or path.exists():
                    raise GovernanceBlockedError("补帧目标冲突")
                writes.append(FileWrite(path, (staging / frame.path).read_bytes()))
                expected[path] = None
                material.frames.append(frame)
                existing[frame.id] = frame
            if digest(source) != material.source_sha256:
                raise GovernanceBlockedError("补帧期间源视频变化")
            material.frames.sort(key=lambda f: f.seconds)
            writes.append(FileWrite(bundle / "material.json", material.model_dump_json(indent=2)))
            FileChangeExecutor(bundle, self.state_root).execute(
                FileChangeSet(writes=tuple(writes), expected=expected, label="video frames")
            )
        finally:
            shutil.rmtree(staging)
        return {"status": "applied", "frames": len(material.frames), "write_performed": True}

    def validate(self, bundle: Path, draft: Path) -> tuple[Material, Draft]:
        _, material = self.load(bundle)
        draft = checked_path(draft)
        if not draft.is_file() or draft.stat().st_size > self.limits["max_text_bytes"]:
            raise InputError("草稿不存在或过大", field="draft")
        try:
            content = Draft.model_validate_json(draft.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise InputError("草稿 JSON 无效", field="draft", detail=str(exc)) from exc
        if content.source_sha256 != material.source_sha256:
            raise GovernanceBlockedError("草稿与素材来源不同")
        used = {i for s in content.sections for i in s.segment_ids}
        if used != set(range(len(material.segments))):
            raise InputError("章节须覆盖所有转写 segment_ids，且不能引用不存在的片段")
        frame_ids = {f.id for f in material.frames}
        if any(f not in frame_ids for s in content.sections for f in s.frame_ids):
            raise InputError("章节引用了不存在的截图")
        if not content.visual_reviewed or not any(s.frame_ids for s in content.sections):
            raise InputError("图文交付须核验画面并选图；无视觉能力时报告降级，不进行完整交付")
        from markdown_it import MarkdownIt

        parser = MarkdownIt()
        for section in content.sections:
            for block in parser.parse(section.body):
                for token in (block, *(block.children or [])):
                    if token.type in {"image", "html_block", "html_inline"} or (
                        token.type == "text" and "![[" in token.content
                    ):
                        raise InputError(
                            "正文不能嵌入图片或 HTML，须通过 frame_ids 引用截图；代码示例不受限"
                        )
        return material, content

    def inspect(self, bundle: Path, draft: Path | None = None) -> dict:
        _, material = self.load(bundle)
        if draft:
            self.validate(bundle, draft)
        return {
            "status": "needs-review",
            "material": material.model_dump(),
            "structural_validation": "passed",
            "semantic_review_required": True,
        }

    def deliver(
        self,
        bundle: Path,
        draft: Path,
        target: Path,
        root: Path,
        state_root: Path,
        *,
        confirm: bool = False,
        expected_plan: str | None = None,
    ) -> dict:
        bundle = checked_path(bundle)
        target = checked_path(target)
        material, content = self.validate(bundle, draft)
        original_bytes = target.read_bytes()
        original = original_bytes.decode("utf-8")
        anchor = "<!-- CAMPFIRE:BODY -->"
        if original.count(anchor) != 1:
            raise GovernanceBlockedError("目标须为 document apply 创建、包含唯一正文锚点的文档")
        prefix, body = original.split(anchor, 1)
        if body.strip():
            raise GovernanceBlockedError("首期仅交付到空正文；已有内容请人工合并，不自动覆盖")
        assets = target.parent / "assets" / ("video-" + material.source_sha256[:16])

        def check_destinations():
            for candidate in expected:
                checked_path(candidate)
            marker = f"来源 SHA-256：`{material.source_sha256}`"
            for sibling in target.parent.glob("*.md"):
                if (
                    sibling != target
                    and not sibling.is_symlink()
                    and marker in sibling.read_text(encoding="utf-8")
                ):
                    raise GovernanceBlockedError(
                        "同目录已有此来源的文档；请先确认复用或合并", path=str(sibling)
                    )

        by_id = {f.id: f for f in material.frames}
        lines = [
            f"# {content.title}",
            "",
            f"来源文件：{material.source_name}",
            f"来源 SHA-256：`{material.source_sha256}`",
            f"时长：{timestamp(material.duration)}；转写：{material.transcript_source}",
            "",
        ]
        writes = []
        expected = {target: hashlib.sha256(original_bytes).hexdigest()}
        selected = {f for s in content.sections for f in s.frame_ids}
        for frame_id in sorted(selected):
            frame = by_id[frame_id]
            destination = checked_path(assets / f"{frame.sha256[:16]}.jpg")
            data = (bundle / frame.path).read_bytes()
            if hashlib.sha256(data).hexdigest() != frame.sha256:
                raise GovernanceBlockedError("截图在校验后变化")
            expected[destination] = digest(destination) if destination.exists() else None
            if expected[destination] not in (None, frame.sha256):
                raise GovernanceBlockedError("已有同名附件内容冲突")
            if not destination.exists():
                writes.append(FileWrite(destination, data))
        for section in content.sections:
            times = [material.segments[i].start for i in section.segment_ids]
            suffix = f"（{timestamp(min(times))}）" if times else ""
            lines.extend([f"## {section.title}{suffix}", "", section.body, ""])
            for frame_id in section.frame_ids:
                frame = by_id[frame_id]
                relative = (
                    (assets / f"{frame.sha256[:16]}.jpg").relative_to(target.parent).as_posix()
                )
                lines.extend([f"![视频画面 {timestamp(frame.seconds)}]({relative})", ""])
        lines.extend(
            [
                "## 核验与限制",
                "",
                *[f"- {s}" for s in content.limitations],
                "- 转写及文字整理可能存在误差；结构校验不等于事实或内容完整性证明。",
                "",
            ]
        )
        rendered = prefix + anchor + "\n\n" + "\n".join(lines)
        writes.append(FileWrite(target, rendered))
        payload = {
            "expected": {str(p): h for p, h in expected.items()},
            "content": hashlib.sha256(rendered.encode()).hexdigest(),
            "bundle": digest(bundle / "material.json"),
        }
        plan = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        result = {
            "status": "planned",
            "expected_plan": plan,
            "target": str(target),
            "images": len(selected),
            "write_performed": False,
            "follow_up": [],
        }
        check_destinations()
        if not confirm:
            return result
        if expected_plan != plan:
            raise GovernanceBlockedError("文档、草稿或附件已变化；重新预览")
        try:
            FileChangeExecutor(root, state_root).execute(
                FileChangeSet(writes=tuple(writes), expected=expected, label="video deliver"),
                before_write=check_destinations,
            )
        except OSError as exc:
            raise AppError("图文写入失败，已尝试回滚；原视频未修改") from exc
        return {**result, "status": "applied", "write_performed": True}
