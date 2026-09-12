---
name: campfire-workspace-maintenance
description: "持续维护 Campfire Workspace 的结构与文档合规；适用于 Space/Domain 声明、文档检查与格式化、MOC 同步、归档和日常维护，不用于跨领域批量重构。"
---

# Campfire Workspace Maintenance

目标是允许人类低成本记录，同时让 Agent 以可审阅、可重复执行的方式保持 Workspace 合规。

先运行 `campfire workspace resolve` 获取目标 Workspace，再读取其 `AGENTS.md`。运行 `campfire workspace config check`、`workspace space/domain check` 和 `campfire maintenance check` 获取当前状态；检查不修改原始笔记，但可能刷新用户级索引和报告，不得直接编辑 `~/.campfire/`。

## 工作流

1. 通过 `workspace space/domain list` 和声明文件理解现有结构。正式文档必须归入 Domain，Space 不直接承载正式文档。
2. 新目录使用 `space/domain create`；已有目录使用 `space/domain adopt`。默认先预览，用户确认后追加 `--confirm`。顶级 Space、根 Domain 和有歧义的父子关系必须由用户确认。
3. 单篇文档使用 `campfire document profile resolve/check/format`；字段、顺序与枚举以 CLI 解析的有效 Profile 为准，不在 Skill 中复制。
4. 日常批量维护使用 `campfire maintenance plan`，审查后使用 `maintenance apply --confirm`。
5. 使用 `maintenance sync --dry-run` 预览 MOC、关系页与治理视图变更，再执行 `maintenance sync`；日常完整流程使用 `maintenance run`。
6. 报告原始笔记变化、自动生成物和仍需用户确认的事项。涉及跨领域移动、批量改名、领域拆分或合并时停止，改用 `campfire-workspace-restructure`。

## 不变量

- 整个 Workspace 只有一个根 `_收件箱/`；语义无法唯一判断时进入待用户确认，不为追求检查通过而猜测。
- `_空间.md` 声明 Space，`_领域.md` 声明可多级嵌套的 Domain；保留目录不是 Space 或 Domain。
- 一篇文档只有一个主物理 Domain，可以出现在多个自动索引中。
- MOC 自动区域、相关文档、反向链接、关系和统计由 CLI 生成，不手工维护。
- Maintenance 不改变文档主物理归属，不进行跨领域移动、批量改名、领域合并或拆分。
- 写入返回 `concurrent-change` 时停止并重新检查，不覆盖其他会话的新内容。
- Markdown 是内容事实来源，用户级配置是治理契约；SQLite 只保存索引与工作流状态。

## 内容与任务

- 跨项目可复用的长期认知归入 knowledge 类型 Space；项目当前实现、方案、决策、问题或记录归入 Project 绑定的 Domain。项目事实必须检查已注册源码、配置和测试。
- `status`、`lifecycle` 和其他字段只从 Document Profile 获取。任务正文需要创建或更新时参考[任务正文结构](references/任务正文结构.md)。
- 归档必须由显式 `archive_requested` 触发；先运行 `maintenance archive check`，审查后执行 `archive apply --confirm`。不得仅因长期未更新而归档。
