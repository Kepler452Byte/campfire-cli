from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from campfire_cli.config.defaults import config_section


def enrich_issue(issue: dict[str, Any]) -> dict[str, Any]:
    result = dict(issue)
    code = str(result.get("code"))
    policy = config_section("issues")
    fallback = next(
        (content for prefix, content in policy["categories"].items() if code.startswith(prefix)),
        (policy["default"]["message"], policy["default"]["suggestion"]),
    )
    message, suggestion = policy["catalog"].get(code, fallback)
    result.setdefault("message", message)
    result.setdefault("suggestion", suggestion)
    result.setdefault("severity", "warning" if code in policy["warning_codes"] else "error")
    return result


def filter_issues(
    issues: Iterable[dict[str, Any]],
    *,
    scope: str | None = None,
    code: str | None = None,
    severity: str | None = None,
) -> list[dict[str, Any]]:
    prefix = scope.strip("/") if scope else None
    return [
        issue
        for issue in issues
        if (prefix is None or str(issue.get("path", "")).strip("/").startswith(prefix))
        and (code is None or issue.get("code") == code)
        and (severity is None or issue.get("severity", "error") == severity)
    ]
