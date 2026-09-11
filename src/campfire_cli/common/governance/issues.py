from __future__ import annotations

from collections.abc import Iterable
from typing import Any

ISSUE_CATALOG: dict[str, tuple[str, str]] = {
    "untitled-note": (
        "文档仍使用临时名称。",
        "理解正文后按文档类型改为有意义的名称；无法判断时保留并请求用户确认。",
    ),
    "project-doc-frontmatter-missing": (
        "项目文档缺少 Frontmatter。",
        "根据正文确定类型和领域，再使用对应项目文档模板补齐元数据。",
    ),
    "frontmatter-missing": (
        "受管文档缺少 Frontmatter。",
        "运行 campfire maintenance plan 生成可审阅的补全计划。",
    ),
    "frontmatter-field-missing": (
        "Frontmatter 缺少必填字段。",
        "根据 detail 指定的字段补充真实值，不要编造业务信息。",
    ),
    "frontmatter-enum-invalid": (
        "Frontmatter 使用了契约之外的枚举值。",
        "使用 issue 的 allowed 值；任务完成语义应写入 lifecycle: completed。",
    ),
    "task-requested-by-missing": (
        "上级交办任务缺少交办人。",
        "填写 requested_by；无法确认时设置 requires_human: true。",
    ),
    "task-blocked-reason-missing": (
        "阻塞任务缺少阻塞原因。",
        "填写 blocked_reason，或将 lifecycle 修正为实际状态。",
    ),
    "task-completion-evidence-missing": (
        "完成任务缺少结果或验证证据。",
        "补齐 completed、result_summary 和 verification 后再标记完成。",
    ),
    "document-archive-state-mismatch": (
        "文档状态、生命周期和 archive 路径不一致。",
        "使用两阶段归档流程统一修复，不要只修改其中一个字段。",
    ),
    "template-enum-invalid": (
        "Skill 模板中的枚举值与当前 Schema 不一致。",
        "修改项目内 Skill SSOT 后运行 campfire skill sync。",
    ),
    "concurrent-change": (
        "计划生成后有文件被其他会话修改。",
        "重新检查并生成计划；不要覆盖外部会话的最新内容。",
    ),
    "migration-source-not-in-inventory": (
        "迁移来源不在冻结的批次清单中。",
        "重新 inventory 正确范围，或修正计划规格中的 source。",
    ),
    "migration-config-changed": (
        "生成计划后治理配置发生变化。",
        "重新 inventory 和 plan，避免用旧规则执行迁移。",
    ),
    "source-hash-changed": (
        "生成迁移计划后源文档已被修改。",
        "审查其他会话的变更后重新生成迁移计划。",
    ),
    "moc-missing": (
        "领域声明引用的 MOC 文件不存在。",
        "创建声明的 MOC 文件后重新运行 sync；不要让 sync 猜测文件名。",
    ),
}

ISSUE_CATEGORIES: dict[str, tuple[str, str]] = {
    "migration-": ("迁移计划不满足执行条件。", "修正规格或重新生成迁移批次后再执行。"),
    "source-": ("迁移源文件状态不符合计划。", "重新 inventory 和 plan，避免覆盖新变化。"),
    "target-": ("迁移目标路径存在问题。", "检查目标路径、重复项和已有文件。"),
    "frontmatter-": ("Frontmatter 不符合当前契约。", "根据字段规则修正后重新检查。"),
    "document-": ("文档类型、命名或状态不符合规则。", "按文档类型契约修正并重新检查。"),
    "task-": ("任务文档缺少必要状态或证据。", "补充真实任务信息后重新检查。"),
    "domain-": ("领域声明不完整或不一致。", "检查 _领域.md 与目录结构。"),
    "archive-": ("文档暂不满足归档条件。", "补齐归档原因或后继关系后重试。"),
    "inbox-": ("全局收件箱配置异常。", "检查治理配置与 _收件箱 目录。"),
}

WARNING_CODES = {"untitled-note", "undeclared-directory"}


def enrich_issue(issue: dict[str, Any]) -> dict[str, Any]:
    result = dict(issue)
    code = str(result.get("code"))
    fallback = next(
        (content for prefix, content in ISSUE_CATEGORIES.items() if code.startswith(prefix)),
        ("发现治理规则问题。", "根据 code、path 和 detail 审查后处理。"),
    )
    message, suggestion = ISSUE_CATALOG.get(code, fallback)
    result.setdefault("message", message)
    result.setdefault("suggestion", suggestion)
    result.setdefault("severity", "warning" if code in WARNING_CODES else "error")
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
