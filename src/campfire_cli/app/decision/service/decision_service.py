from __future__ import annotations

import re
from uuid import uuid4

from campfire_cli.app.decision.repository.decision_repository import SqliteDecisionRepository
from campfire_cli.app.decision.schema.decision_schema import (
    DecisionListResult,
    DecisionResult,
    DecisionSyncResult,
)
from campfire_cli.app.decision.service.decision_projection_service import (
    DecisionProjectionService,
)
from campfire_cli.common.exceptions import ConfigurationError

KEY_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,159}")
STATUSES = {"pending", "answered", "closed", "cancelled"}


class DecisionService:
    def __init__(
        self,
        repository: SqliteDecisionRepository,
        projection: DecisionProjectionService,
    ) -> None:
        self._repository = repository
        self._projection = projection

    def create(
        self,
        *,
        key: str,
        question: str,
        context: str = "",
        recommendation: str = "",
        options: list[str] | None = None,
        related_documents: list[str] | None = None,
        source_type: str,
        source_id: str | None = None,
        session_provider: str | None = None,
        session_id: str | None = None,
        actor: str | None = None,
    ) -> DecisionResult:
        if not KEY_RE.fullmatch(key):
            raise ConfigurationError("Decision key 只能使用小写字母、数字和连字符")
        if not question.strip() or not source_type.strip():
            raise ConfigurationError("Decision question 和 source-type 不能为空")
        decision = self._repository.create_or_refresh(
            str(uuid4()),
            {
                "dedupe_key": key,
                "question": question.strip(),
                "context": context.strip(),
                "recommendation": recommendation.strip(),
                "options": [item.strip() for item in options or [] if item.strip()],
                "related_documents": list(dict.fromkeys(related_documents or [])),
                "source_type": source_type.strip(),
                "source_id": source_id,
                "session_provider": session_provider,
                "session_id": session_id,
            },
            actor,
        )
        projection = self._sync_projection()
        events = self._repository.events(decision.id)
        return DecisionResult(
            status="created" if len(events) == 1 else "refreshed",
            decision=decision,
            events=events,
            projection_operations=projection.operations,
        )

    def list(self, status: str | None = None) -> DecisionListResult:
        if status is not None and status not in STATUSES:
            raise ConfigurationError(f"未知 Decision 状态：{status}")
        return DecisionListResult(decisions=self._repository.list(status))

    def show(self, decision_id: str) -> DecisionResult:
        return DecisionResult(
            status="ok",
            decision=self._repository.get(decision_id),
            events=self._repository.events(decision_id),
        )

    def answer(self, decision_id: str, answer: str, answered_by: str) -> DecisionResult:
        if not answer.strip() or not answered_by.strip():
            raise ConfigurationError("Decision answer 和 answered-by 不能为空")
        decision = self._repository.answer(decision_id, answer.strip(), answered_by.strip())
        projection = self._sync_projection()
        return DecisionResult(
            status="answered",
            decision=decision,
            events=self._repository.events(decision_id),
            projection_operations=projection.operations,
        )

    def close(self, decision_id: str, actor: str | None = None) -> DecisionResult:
        decision = self._repository.close(decision_id, actor)
        projection = self._sync_projection()
        return DecisionResult(
            status="closed",
            decision=decision,
            events=self._repository.events(decision_id),
            projection_operations=projection.operations,
        )

    def cancel(self, decision_id: str, reason: str, actor: str | None = None) -> DecisionResult:
        if not reason.strip():
            raise ConfigurationError("Decision cancellation reason 不能为空")
        decision = self._repository.cancel(decision_id, reason.strip(), actor)
        projection = self._sync_projection()
        return DecisionResult(
            status="cancelled",
            decision=decision,
            events=self._repository.events(decision_id),
            projection_operations=projection.operations,
        )

    def sync(self) -> DecisionSyncResult:
        return self._sync_projection()

    def _sync_projection(self) -> DecisionSyncResult:
        return self._projection.sync(self._repository.list("pending"))
