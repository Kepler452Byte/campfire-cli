from datetime import UTC, datetime, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from campfire_cli.common.exceptions import JobError


def display_run(run: dict[str, Any], timezone: str) -> dict[str, Any]:
    zone: tzinfo | None
    if timezone not in {"UTC", "local"}:
        try:
            zone = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise JobError("invalid-timezone", f"Unknown IANA timezone: {timezone}") from exc
    else:
        zone = UTC if timezone == "UTC" else None
    converted: dict[str, str | None] = {}
    for field in ("started", "finished"):
        value = run.get(field)
        converted[field] = (
            datetime.fromisoformat(value).astimezone(zone).isoformat() if value else None
        )
    return {**run, "display_time": {"timezone": timezone, **converted}}
