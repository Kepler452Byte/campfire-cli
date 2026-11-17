from datetime import UTC, datetime, timedelta

from campfire_cli.app.job.schema.retention_schema import RetentionPolicy
from campfire_cli.common.time_display import display_run


def test_per_job_success_failure_caps_and_explicit_age():
    now = datetime.now(UTC)
    rows = [
        {
            "id": f"{job}-{status}-{i}",
            "job_id": job,
            "status": status,
            "finished": (now - timedelta(days=i + 1)).isoformat(),
        }
        for job in ("fast", "slow")
        for status in ("succeeded", "failed", "timeout", "interrupted")
        for i in range(5)
    ]
    rows.append({"id": "active", "job_id": "fast", "status": "running", "finished": None})
    rows.sort(key=lambda row: row["finished"] or "", reverse=True)
    policy = RetentionPolicy(2, 2, 3, 4, 3)
    expired = set(policy.select(rows, now))
    for job in ("fast", "slow"):
        remaining = [
            row
            for row in rows
            if row["job_id"] == job and row["finished"] is not None and row["id"] not in expired
        ]
        assert sum(row["status"] == "succeeded" for row in remaining) == 1
        assert sum(row["status"] != "succeeded" for row in remaining) == 3
    assert "active" not in expired
    assert all("succeeded" in identity for identity in policy.select(rows, now, keep_failures=True))
    assert policy.select(rows, now, job_id="slow", statuses={"failed"}, older_than=4) == [
        "slow-failed-3",
        "slow-failed-4",
    ]


def test_timezone_display_preserves_utc_originals():
    row = {"started": "2026-11-17T00:00:00+00:00", "finished": None}
    result = display_run(row, "Asia/Shanghai")
    assert result["started"] == row["started"]
    assert result["display_time"]["started"] == "2026-11-17T08:00:00+08:00"
