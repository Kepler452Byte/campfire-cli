from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from campfire_cli.app.video.schema.video_schema import Draft, Material
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
        self.ignored_config = sorted(
            set(limits) & {"max_frames", "frame_interval", "max_dimension", "max_pixels"}
        )
        limits = {
            key: value
            for key, value in limits.items()
            if key != "model" and key not in self.ignored_config
        }
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
                "ignored_legacy_config": self.ignored_config,
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
                "ignored_legacy_config": self.ignored_config,
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
            "ignored_legacy_config": self.ignored_config,
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
        required = ["av"] + (["faster_whisper"] if model else [])
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
                warnings=["自动转写未经语义核验，须阅读全部转写；画面依赖内容须标明回看。"],
            )
            if not material.segments:
                material.warnings.append(
                    "没有可用转写；请提供显式转写或检查音轨，不能交付声称完整的文字稿。"
                )
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
            "duration": material.duration,
            "warnings": material.warnings,
            "ignored_legacy_config": self.ignored_config,
            "write_performed": True,
        }

    def load(self, bundle: Path) -> tuple[Path, Material]:
        bundle = checked_path(bundle)
        path = checked_path(bundle / "material.json")
        if not path.is_file() or path.stat().st_size > self.limits["max_text_bytes"]:
            raise InputError("素材清单不存在或过大", field="bundle")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("素材清单须为 JSON 对象")
            legacy = data.get("schema_version", 1) == 1
            if legacy:
                data.pop("frames", None)
                data["schema_version"] = 2
            material = Material.model_validate(data)
            if legacy:
                material.warnings.append(
                    "Alpha 素材仅只读使用文字部分；截图及旧目录保留；新转写用 --output 指定新目录。"
                )
        except (ValueError, OSError) as exc:
            raise InputError(
                "素材清单格式无效；重新 prepare --output <新目录>，不覆盖原素材",
                field="bundle",
                detail=str(exc),
            ) from exc
        return bundle, material

    def validate(self, bundle: Path, draft: Path) -> tuple[Material, Draft]:
        _, material = self.load(bundle)
        draft = checked_path(draft)
        if not draft.is_file() or draft.stat().st_size > self.limits["max_text_bytes"]:
            raise InputError("草稿不存在或过大", field="draft")
        try:
            content = Draft.model_validate_json(draft.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise InputError(
                "草稿 JSON 无效；Alpha 草稿需重写为 schema_version=2，"
                "output_kind=transcript/article，移除 frame_ids/visual_reviewed",
                expected_type="draft schema v2",
                field="draft",
                detail=str(exc),
            ) from exc
        if content.source_sha256 != material.source_sha256:
            raise GovernanceBlockedError("草稿与素材来源不同")
        ids = [i for section in content.sections for i in section.segment_ids]
        omitted = [i for omission in content.omissions for i in omission.segment_ids]
        all_ids = set(range(len(material.segments)))
        if not all_ids or not set(ids + omitted) <= all_ids:
            raise InputError(
                "草稿须引用有效转写；segment_ids 为 segments 的零基整数下标",
                field="segment_ids",
                expected_type="list[int]",
            )
        if content.output_kind == "transcript":
            if ids != list(range(len(material.segments))) or omitted:
                raise InputError(
                    "校订稿须按原顺序逐段覆盖一次，不允许遗漏或重排", field="segment_ids"
                )
        elif set(ids) & set(omitted) or set(ids + omitted) != all_ids:
            raise InputError(
                "成文稿须映射全部来源；未采用的片段在 omissions 中说明取舍", field="omissions"
            )
        from markdown_it import MarkdownIt

        parser = MarkdownIt()
        for section in content.sections:
            for block in parser.parse(section.body):
                for token in (block, *(block.children or [])):
                    if token.type in {"image", "html_block", "html_inline"} or (
                        token.type == "text" and "![[" in token.content
                    ):
                        raise InputError(
                            "文字交付不能嵌入图片或 HTML；截图建议写用途和参考时段；代码示例不受限"
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
            "ignored_legacy_config": self.ignored_config,
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
        input_hashes = {
            "bundle": digest(bundle / "material.json"),
            "draft": digest(checked_path(draft)),
        }
        material, content = self.validate(bundle, draft)
        if input_hashes != {
            "bundle": digest(bundle / "material.json"),
            "draft": digest(checked_path(draft)),
        }:
            raise GovernanceBlockedError("素材或草稿在读取期间变化；重新预览")
        original_bytes = target.read_bytes()
        original = original_bytes.decode("utf-8")
        anchor = "<!-- CAMPFIRE:BODY -->"
        if original.count(anchor) != 1:
            raise GovernanceBlockedError("目标须为 document apply 创建、包含唯一正文锚点的文档")
        prefix, body = original.split(anchor, 1)
        if body.strip():
            raise GovernanceBlockedError("首期仅交付到空正文；已有内容请人工合并，不自动覆盖")

        def check_destinations():
            for candidate in expected:
                checked_path(candidate)
            if (
                digest(bundle / "material.json") != payload["bundle"]
                or digest(checked_path(draft)) != payload["draft"]
            ):
                raise GovernanceBlockedError("素材或草稿在交付期间变化；重新预览")

        lines = [
            f"# {content.title}",
            "",
            f"来源文件：{material.source_name}",
            f"来源 SHA-256：`{material.source_sha256}`",
            f"时长：{timestamp(material.duration)}；转写：{material.transcript_source}",
            f"处理日期：{datetime.now(UTC).date().isoformat()}（UTC）；产物：{content.output_kind}",
            f"用途与读者：{content.purpose}",
            "",
        ]
        writes = []
        expected = {target: hashlib.sha256(original_bytes).hexdigest()}
        for section in content.sections:
            times = [material.segments[i].start for i in section.segment_ids]
            suffix = f"（{timestamp(min(times))}）" if times else ""
            references = ", ".join(
                f"{i}: {timestamp(material.segments[i].start)}"
                f"–{timestamp(material.segments[i].end)}"
                for i in section.segment_ids
            )
            lines.extend(
                [
                    f"## {section.title}{suffix}",
                    "",
                    section.body,
                    "",
                    f"来源片段（ID: 原媒体起止时间）：{references}",
                    "",
                ]
            )
        if content.omissions:
            lines.extend(["## 内容取舍", ""])
            for omission in content.omissions:
                times = ", ".join(
                    timestamp(material.segments[i].start) for i in omission.segment_ids
                )
                lines.extend([f"- {times}：{omission.reason}", ""])
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
            **input_hashes,
        }
        plan = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        result = {
            "status": "planned",
            "expected_plan": plan,
            "target": str(target),
            "output_kind": content.output_kind,
            "write_performed": False,
            "follow_up": [],
        }
        check_destinations()
        if not confirm:
            return result
        if expected_plan != plan:
            raise GovernanceBlockedError("文档、素材或草稿已变化；重新预览")
        try:
            FileChangeExecutor(root, state_root).execute(
                FileChangeSet(writes=tuple(writes), expected=expected, label="video deliver"),
                before_write=check_destinations,
            )
        except OSError as exc:
            raise AppError("正文写入失败，已尝试回滚；原视频未修改") from exc
        return {**result, "status": "applied", "write_performed": True}
