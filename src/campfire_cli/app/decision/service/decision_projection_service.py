from __future__ import annotations

import json
from pathlib import Path

from campfire_cli.app.decision.schema.decision_schema import DecisionEntry, DecisionSyncResult
from campfire_cli.common.filesystem import atomic_write, workspace_write_lock
from campfire_cli.config.settings import WorkspaceSettings

GENERATED_MARKER = "<!-- AUTO-GENERATED:CAMPFIRE-DECISION -->"


class DecisionProjectionService:
    """Project pending SQLite Decisions into disposable, human-readable Markdown."""

    def __init__(self, settings: WorkspaceSettings) -> None:
        self._settings = settings

    def sync(self, pending: list[DecisionEntry]) -> DecisionSyncResult:
        root = self._projection_root()
        expected = {self._path(item): self._render(item) for item in pending}
        managed = {
            path
            for path in root.glob("待确认-Decision-*.md")
            if GENERATED_MARKER in path.read_text(encoding="utf-8")
        }
        operations: list[dict[str, str]] = []
        for path, content in expected.items():
            current = path.read_text(encoding="utf-8") if path.is_file() else None
            if current != content:
                operations.append(
                    {
                        "action": "update" if current is not None else "create",
                        "path": path.relative_to(self._settings.vault_root).as_posix(),
                    }
                )
        for path in sorted(managed - expected.keys()):
            operations.append(
                {
                    "action": "delete-projection",
                    "path": path.relative_to(self._settings.vault_root).as_posix(),
                }
            )
        if operations:
            with workspace_write_lock(self._settings.state_root):
                root.mkdir(parents=True, exist_ok=True)
                for path, content in expected.items():
                    if not path.is_file() or path.read_text(encoding="utf-8") != content:
                        atomic_write(path, content)
                for path in managed - expected.keys():
                    path.unlink()
        return DecisionSyncResult(
            status="synced",
            pending_count=len(pending),
            operations=operations,
        )

    def _projection_root(self) -> Path:
        inbox = self._settings.governance.get("inbox", "_收件箱")
        return self._settings.vault_root / inbox / "待用户确认"

    def _path(self, decision: DecisionEntry) -> Path:
        return self._projection_root() / f"待确认-Decision-{decision.id}.md"

    @staticmethod
    def _render(decision: DecisionEntry) -> str:
        created = decision.created_at.date().isoformat()
        updated = decision.updated_at.date().isoformat()
        lines = [
            "---",
            f"name: {json.dumps(decision.question, ensure_ascii=False)}",
            'description: "等待人类或高级 Agent 回答的 Campfire Decision 投影"',
            "type: human-request",
            "status: draft",
            f"created: {created}",
            f"updated: {updated}",
            "tags: [campfire, decision]",
            "---",
            "",
            GENERATED_MARKER,
            "",
            "# 待确认事项",
            "",
            "> 此文档由 Campfire 根据 SQLite Decision 自动生成。"
            "请通过 `campfire decision answer` 回答，不要手工修改。",
            "",
            f"- Decision ID：`{decision.id}`",
            f"- 来源：`{decision.source_type}`",
            f"- 来源对象：`{decision.source_id or '-'}`",
            f"- 来源 Session：`{decision.session_provider or '-'} / {decision.session_id or '-'}`",
            "",
            "## 问题",
            "",
            decision.question,
        ]
        if decision.context:
            lines.extend(["", "## 背景与已确认事实", "", decision.context])
        if decision.options:
            lines.extend(["", "## 可选方案", ""])
            lines.extend(f"- {option}" for option in decision.options)
        if decision.recommendation:
            lines.extend(["", "## Agent 建议", "", decision.recommendation])
        if decision.related_documents:
            lines.extend(["", "## 关联文档", ""])
            lines.extend(f"- `{path}`" for path in decision.related_documents)
        lines.extend(
            [
                "",
                "## 回答方式",
                "",
                "```bash",
                f"campfire decision answer {decision.id} "
                '--answer "<回答>" --answered-by "<回答者>"',
                "```",
                "",
            ]
        )
        return "\n".join(lines)
