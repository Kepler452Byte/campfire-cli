---
name: campfire-inbox-triage
description: "分流 Campfire Workspace 全局收件箱中的输入；适用于判断目标 Space、Domain 和文档类型，以及生成需要用户确认的归属问题。"
---

# Campfire 收件箱分流

只处理已经进入 `_收件箱/` 的原始材料和待确认文档，不负责从对话提炼新文档。先读取 `campfire-workspace-maintenance`，再读取候选领域的 `_领域.md`；涉及沉淀内容是否足以晋升时加载 `campfire-document-capture`，涉及跨领域批量移动时加载 `campfire-workspace-restructure`。

## 工作流

1. `_收件箱/` 只保存用户原始输入；Decision 位于 `_协作/decisions/`，不作为收件箱材料分流。处理关联 Decision 时通过 `campfire decision show` 读取事实。
2. 只在已有正式领域中选择目标；创建顶级领域、合并内容或删除原文必须由用户确认。
3. 给出目标空间、领域、类型、文件名、摘要、理由和置信度。
4. 归属和事实明确时形成默认未审批的维护建议，不直接移动或晋升。
5. 空间、领域、权威性或合并关系存在歧义时调用 `campfire decision create`，由 CLI 生成可读投影，并保持原文不动。
6. 用户通过 `decision answer` 给出决定并转为已审批计划后才执行；完成后同步 MOC，再调用 `decision close`。

## 边界

- `high` 只表示可以生成待审批计划，不表示可以跳过审批。
- `medium` 或 `low` 必须请求确认。
- Decision 必须关联原文、列出候选及一个明确问题，不能代替正式知识文档；`_协作/decisions/Decision-*.md` 不允许手工维护。
