from __future__ import annotations

from typing import Any


def render_maintenance_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Campfire 当前检查报告",
        "",
        f"- 状态：`{payload['status']}`",
        f"- 文档数：{payload['document_count']}",
        f"- 问题数：{payload['issue_count']}",
        f"- 生成时间：{payload['exported_at']}",
        "",
        "## 待处理问题",
        "",
    ]
    issues = payload.get("issues", [])
    if issues:
        for issue in issues:
            lines.append(
                f"- `{issue['severity']}` `{issue['code']}` `{issue['path']}`："
                f"{issue.get('message') or issue.get('detail', '')}"
            )
            if issue.get("suggestion"):
                lines.append(f"  - 建议：{issue['suggestion']}")
    else:
        lines.append("当前没有发现治理问题。")
    return "\n".join(lines) + "\n"
