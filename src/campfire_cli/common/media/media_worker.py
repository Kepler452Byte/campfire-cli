from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def run(request: dict) -> dict:
    import av

    if request.get("operation") == "validate-model":
        import huggingface_hub  # noqa: F401
        from faster_whisper import WhisperModel
        from faster_whisper.vad import get_vad_model
        from markdown_it import MarkdownIt

        WhisperModel(request["model"], device="cpu", compute_type="int8", local_files_only=True)
        get_vad_model()
        MarkdownIt().parse("validation")
        return {"status": "ready"}

    source = request["source"]
    limits = request["limits"]
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
        result = {
            "duration": duration,
            "width": stream.width,
            "height": stream.height,
        }
        audio = bool(container.streams.audio)
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
