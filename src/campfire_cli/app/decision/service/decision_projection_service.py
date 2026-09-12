from __future__ import annotations

import json
from pathlib import Path

from campfire_cli.app.decision.schema.decision_schema import DecisionEntry, DecisionSyncResult
from campfire_cli.common.filesystem import atomic_write, workspace_write_lock
from campfire_cli.config.settings import WorkspaceSettings

GENERATED_MARKER = "<!-- AUTO-GENERATED:CAMPFIRE-DECISION -->"
STATUS_DIRECTORIES = ("pending", "answered", "closed", "cancelled")


class DecisionProjectionService:
    """Project SQLite Decisions into disposable, human-readable Markdown."""

    def __init__(self, settings: WorkspaceSettings) -> None:
        self._settings = settings

    def sync(self, decisions: list[DecisionEntry]) -> DecisionSyncResult:
        root = self._projection_root()
        expected = {self._path(item): self._render(item) for item in decisions}
        directories = [root / status for status in STATUS_DIRECTORIES]
        managed = {
            path
            for path in root.rglob("Decision-*.md")
            if GENERATED_MARKER in path.read_text(encoding="utf-8")
        }
        operations: list[dict[str, str]] = []
        for path in directories:
            if not path.is_dir():
                operations.append(
                    {
                        "action": "create-directory",
                        "path": path.relative_to(self._settings.vault_root).as_posix(),
                    }
                )
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
                for path in directories:
                    path.mkdir(parents=True, exist_ok=True)
                for path, content in expected.items():
                    if not path.is_file() or path.read_text(encoding="utf-8") != content:
                        atomic_write(path, content)
                for path in managed - expected.keys():
                    path.unlink()
        return DecisionSyncResult(
            status="synced",
            pending_count=sum(item.status == "pending" for item in decisions),
            operations=operations,
        )

    def _projection_root(self) -> Path:
        return self._settings.vault_root / "_协作" / "decisions"

    def _path(self, decision: DecisionEntry) -> Path:
        return self._projection_root() / decision.status / f"Decision-{decision.id}.md"

    @staticmethod
    def _render(decision: DecisionEntry) -> str:
        title = DecisionProjectionService._title(decision.question)
        answered_at = decision.answered_at.isoformat() if decision.answered_at else None
        closed_at = decision.closed_at.isoformat() if decision.closed_at else None
        lines = [
            "---",
            f"name: {json.dumps(title, ensure_ascii=False)}",
            "object_type: decision",
            f"decision_id: {decision.id}",
            f"decision_status: {decision.status}",
            f"source_type: {json.dumps(decision.source_type, ensure_ascii=False)}",
            f"source_id: {json.dumps(decision.source_id, ensure_ascii=False)}",
            f"answered_by: {json.dumps(decision.answered_by, ensure_ascii=False)}",
            f"created_at: {decision.created_at.isoformat()}",
            f"updated_at: {decision.updated_at.isoformat()}",
            f"answered_at: {json.dumps(answered_at)}",
            f"closed_at: {json.dumps(closed_at)}",
            "---",
            "",
            GENERATED_MARKER,
            "",
            f"# {title}",
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
        if decision.answer:
            lines.extend(
                [
                    "",
                    "## 回答",
                    "",
                    decision.answer,
                    "",
                    f"回答者：`{decision.answered_by or '-'}`",
                ]
            )
        elif decision.status == "pending":
            lines.extend(
                [
                    "",
                    "## 回答方式",
                    "",
                    "```bash",
                    f"campfire decision answer {decision.id} "
                    '--answer "<回答>" --answered-by "<回答者>"',
                    "```",
                ]
            )
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _title(question: str) -> str:
        compact = " ".join(question.split())
        return compact if len(compact) <= 48 else compact[:47] + "…"
