from pathlib import Path
from typing import Protocol


class MediaBackend(Protocol):
    def run(self, request: dict, timeout: int) -> dict: ...


class ModelDownloader(Protocol):
    def __call__(self, repository: str, revision: str, output: Path) -> None: ...


class VideoRuntime(Protocol):
    def plan(self) -> dict: ...

    def install(self, plan: dict, timeout: int) -> None: ...
