from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path


def frames(container, stream, times: list[float], output: Path, dimension: int) -> list[dict]:
    from PIL import Image

    result = []
    seen = set()
    origin = stream.start_time or 0
    for seconds in times:
        container.seek(int(seconds / stream.time_base) + origin, stream=stream)
        for frame in container.decode(stream):
            if frame.pts is None:
                continue
            actual = float((frame.pts - origin) * stream.time_base)
            if actual + 0.001 < seconds:
                continue
            picture = frame.to_image()
            picture.thumbnail((dimension, dimension), Image.Resampling.LANCZOS)
            digest = hashlib.sha256(picture.tobytes()).hexdigest()
            if digest not in seen:
                seen.add(digest)
                name = f"frame-{round(actual * 1000):010d}"
                path = output / f"{name}.jpg"
                picture.save(path, quality=90)
                result.append(
                    {
                        "id": name,
                        "path": path.name,
                        "seconds": actual,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
            break
    return result


def run(request: dict) -> dict:
    import av

    if request.get("operation") == "validate-model":
        import huggingface_hub  # noqa: F401
        from faster_whisper import WhisperModel
        from faster_whisper.vad import get_vad_model
        from markdown_it import MarkdownIt
        from PIL import Image

        WhisperModel(request["model"], device="cpu", compute_type="int8", local_files_only=True)
        get_vad_model()
        MarkdownIt().parse("validation")
        Image.new("RGB", (1, 1))
        return {"status": "ready"}

    source = request["source"]
    limits = request["limits"]
    output = Path(request["output"])
    with av.open(
        source,
        options={
            "protocol_whitelist": "file",
            "format_whitelist": "mov,matroska,webm,avi,mpegts",
        },
    ) as container:
        if not container.streams.video:
            raise ValueError("输入没有视频流")
        stream = container.streams.video[0]
        duration = (
            float(stream.duration * stream.time_base)
            if stream.duration is not None
            else (container.duration or 0) / av.time_base
        )
        if not math.isfinite(duration) or not 0 < duration <= limits["max_duration"]:
            raise ValueError("媒体时长未知或超出限制")
        if stream.width * stream.height > limits["max_pixels"]:
            raise ValueError("视频分辨率超过 8K 处理上限")
        times = request.get("times")
        if times is None:
            interval = max(limits["frame_interval"], duration / limits["max_frames"])
            times = [i * interval for i in range(math.ceil(duration / interval))]
        if len(times) > limits["max_frames"] or any(not 0 <= t < duration for t in times):
            raise ValueError("截图时间或数量超出限制")
        result = {
            "duration": duration,
            "width": stream.width,
            "height": stream.height,
            "frames": frames(container, stream, times, output, limits["max_dimension"]),
        }
        audio = bool(container.streams.audio)
    if request.get("frames_only"):
        return result
    if request.get("transcript"):
        result["segments"] = json.loads(Path(request["transcript"]).read_text(encoding="utf-8"))
        result["transcript_source"] = "user-provided"
    elif audio:
        from faster_whisper import WhisperModel

        model = WhisperModel(
            request["model"],
            device="cpu",
            compute_type="int8",
            local_files_only=True,
            cpu_threads=4,
        )
        segments, _ = model.transcribe(source, beam_size=5, vad_filter=True)
        result["segments"] = [
            {"start": s.start, "end": s.end, "text": s.text.strip()}
            for s in segments
            if s.text.strip()
        ]
        result["transcript_source"] = "local-faster-whisper"
    else:
        result["segments"] = []
        result["transcript_source"] = "no-audio"
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.loads(sys.stdin.read())), ensure_ascii=True))
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
