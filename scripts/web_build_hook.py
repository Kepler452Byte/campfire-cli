"""
SPEC:
  name: web_build_hook
  purpose: 阻止发布缺少网页资源的发行物，并将同一构建产物放入 wheel 与 sdist
  idempotent: true
  side_effects: []
"""

import re
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class WebBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:
        if version == "editable":
            return
        assets = Path(self.root) / "src/campfire_cli/resources/web"
        index = assets / "index.html"
        if not index.is_file():
            raise RuntimeError("Build frontend first: cd frontend && pnpm install && pnpm build")
        for name in re.findall(r'(?:src|href)="(/assets/[^"?]+)', index.read_text()):
            if not (assets / name.lstrip("/")).is_file():
                raise RuntimeError(f"Missing compiled web asset: {name}")
        destination = (
            "campfire_cli/resources/web"
            if self.target_name == "wheel"
            else "src/campfire_cli/resources/web"
        )
        build_data["force_include"][str(assets)] = destination
