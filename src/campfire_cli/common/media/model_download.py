from pathlib import Path

from campfire_cli.common.exceptions import AppError, InputError


def download_model(repository: str, revision: str, output: Path) -> None:
    """Download a pinned model snapshot into the caller's staging directory."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise InputError("缺少模型下载依赖；安装 campfire-cli[video]") from exc
    try:
        snapshot_download(
            repo_id=repository,
            revision=revision,
            local_dir=output,
            allow_patterns=["model.bin", "config.json", "tokenizer.json", "vocabulary.*"],
            token=False,
        )
    except Exception as exc:
        raise AppError(
            "模型下载失败；检查网络或代理后重新预览，也可用 --model 指定本地模型",
            code="video-model-download-failed",
            detail=str(exc),
        ) from exc
