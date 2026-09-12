from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from campfire_cli.app.decision.schema.decision_schema import DecisionEntry, DecisionEventEntry
from campfire_cli.common.database.models import Decision, DecisionEvent, utc_now
from campfire_cli.common.exceptions import GovernanceBlockedError


class SqliteDecisionRepository:
    """Persist Decision snapshots and their append-only audit events atomically."""

    def __init__(self, session: Session, workspace_id: str) -> None:
        self._session = session
        self._workspace_id = workspace_id

    def create_or_refresh(
        self,
        decision_id: str,
        values: dict[str, Any],
        actor: str | None,
    ) -> DecisionEntry:
        try:
            row = self._session.scalar(
                select(Decision).where(
                    Decision.workspace_id == self._workspace_id,
                    Decision.dedupe_key == values["dedupe_key"],
                )
            )
            event_type = "decision.created"
            if row is None:
                row = Decision(id=decision_id, workspace_id=self._workspace_id)
                self._session.add(row)
            elif row.status != "pending":
                raise GovernanceBlockedError(
                    f"Decision key 已经结束，不能静默复用：{values['dedupe_key']}"
                )
            else:
                event_type = "decision.refreshed"
            self._assign_content(row, values)
            row.updated_at = utc_now()
            self._append_event(row, event_type, actor, {"dedupe_key": row.dedupe_key})
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._entry(row)

    def list(self, status: str | None = None) -> list[DecisionEntry]:
        statement = select(Decision).where(Decision.workspace_id == self._workspace_id)
        if status is not None:
            statement = statement.where(Decision.status == status)
        statement = statement.order_by(Decision.created_at.desc(), Decision.id)
        rows = self._session.scalars(statement).all()
        return [self._entry(row) for row in rows]

    def get(self, decision_id: str) -> DecisionEntry:
        row = self._row(decision_id)
        return self._entry(row)

    def events(self, decision_id: str) -> list[DecisionEventEntry]:
        self._row(decision_id)
        rows = self._session.scalars(
            select(DecisionEvent)
            .where(
                DecisionEvent.workspace_id == self._workspace_id,
                DecisionEvent.decision_id == decision_id,
            )
            .order_by(DecisionEvent.id)
        ).all()
        return [
            DecisionEventEntry(
                event_type=row.event_type,
                actor=row.actor,
                payload=json.loads(row.payload_json),
                created_at=row.created_at,
            )
            for row in rows
        ]

    def answer(self, decision_id: str, answer: str, actor: str) -> DecisionEntry:
        try:
            row = self._row(decision_id)
            self._require_status(row, "pending")
            now = utc_now()
            row.status = "answered"
            row.answer = answer
            row.answered_by = actor
            row.answered_at = now
            row.updated_at = now
            self._append_event(row, "decision.answered", actor, {"answer": answer})
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._entry(row)

    def close(self, decision_id: str, actor: str | None) -> DecisionEntry:
        try:
            row = self._row(decision_id)
            self._require_status(row, "answered")
            now = utc_now()
            row.status = "closed"
            row.closed_at = now
            row.updated_at = now
            self._append_event(row, "decision.closed", actor, {})
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._entry(row)

    def cancel(self, decision_id: str, reason: str, actor: str | None) -> DecisionEntry:
        try:
            row = self._row(decision_id)
            self._require_status(row, "pending")
            now = utc_now()
            row.status = "cancelled"
            row.cancellation_reason = reason
            row.closed_at = now
            row.updated_at = now
            self._append_event(row, "decision.cancelled", actor, {"reason": reason})
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._entry(row)

    def _row(self, decision_id: str) -> Decision:
        row = self._session.get(Decision, decision_id)
        if row is None or row.workspace_id != self._workspace_id:
            raise GovernanceBlockedError(f"Decision 不存在：{decision_id}")
        return row

    @staticmethod
    def _require_status(row: Decision, expected: str) -> None:
        if row.status != expected:
            raise GovernanceBlockedError(
                f"Decision 状态不允许当前操作：expected={expected}, actual={row.status}"
            )

    def _append_event(
        self,
        row: Decision,
        event_type: str,
        actor: str | None,
        payload: dict[str, Any],
    ) -> None:
        self._session.add(
            DecisionEvent(
                workspace_id=self._workspace_id,
                decision_id=row.id,
                event_type=event_type,
                actor=actor,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
        )

    @staticmethod
    def _assign_content(row: Decision, values: dict[str, Any]) -> None:
        row.dedupe_key = values["dedupe_key"]
        row.question = values["question"]
        row.context = values["context"]
        row.recommendation = values["recommendation"]
        row.options_json = json.dumps(values["options"], ensure_ascii=False)
        row.related_documents_json = json.dumps(values["related_documents"], ensure_ascii=False)
        row.source_type = values["source_type"]
        row.source_id = values["source_id"]
        row.session_provider = values["session_provider"]
        row.session_id = values["session_id"]

    @staticmethod
    def _entry(row: Decision) -> DecisionEntry:
        return DecisionEntry(
            id=row.id,
            workspace_id=row.workspace_id,
            dedupe_key=row.dedupe_key,
            question=row.question,
            context=row.context,
            recommendation=row.recommendation,
            options=json.loads(row.options_json),
            related_documents=json.loads(row.related_documents_json),
            source_type=row.source_type,
            source_id=row.source_id,
            session_provider=row.session_provider,
            session_id=row.session_id,
            status=row.status,
            answer=row.answer,
            answered_by=row.answered_by,
            cancellation_reason=row.cancellation_reason,
            created_at=row.created_at,
            updated_at=row.updated_at,
            answered_at=row.answered_at,
            closed_at=row.closed_at,
        )
