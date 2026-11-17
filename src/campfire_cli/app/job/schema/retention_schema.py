from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from campfire_cli.common.exceptions import JobError

FAILURE_STATUSES = {"failed", "timeout", "interrupted"}


@dataclass(frozen=True)
class RetentionPolicy:
    success_days: int
    failure_days: int
    success_limit: int
    failure_limit: int
    failure_keep: int

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 0 for value in asdict(self).values()):
            raise JobError("invalid-retention", "Retention values must be nonnegative integers")
        if (
            self.success_limit < 1
            or self.failure_limit < 1
            or self.failure_keep > self.failure_limit
        ):
            raise JobError(
                "invalid-retention",
                "Limits must be positive; failure_keep cannot exceed failure_limit",
            )

    def select(
        self,
        rows: list[dict[str, Any]],
        now: datetime,
        *,
        job_id: str | None = None,
        statuses: set[str] | None = None,
        older_than: int | None = None,
        keep_failures: bool = False,
    ) -> list[str]:
        selected: list[str] = []
        counts: dict[tuple[str, bool], int] = {}
        for row in rows:
            if row["finished"] is None or row["status"] == "running":
                continue
            failure = row["status"] in FAILURE_STATUSES
            key = row["job_id"], failure
            rank = counts.get(key, 0)
            counts[key] = rank + 1
            if job_id is not None and row["job_id"] != job_id:
                continue
            if statuses is not None and row["status"] not in statuses:
                continue
            if keep_failures and failure:
                continue
            finished = datetime.fromisoformat(row["finished"]).astimezone(UTC)
            age = now - finished
            if older_than is not None:
                expired = age >= timedelta(days=older_than)
            else:
                limit = self.failure_limit if failure else self.success_limit
                days = self.failure_days if failure else self.success_days
                expired = rank >= limit or (
                    age >= timedelta(days=days) and (not failure or rank >= self.failure_keep)
                )
            if expired:
                selected.append(row["id"])
        return selected
