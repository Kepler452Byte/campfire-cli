---
name: mywork-task-governance
description: "创建和维护 mywork 通用任务文档；适用于个人任务、上级交办、Agent执行任务、状态流转、阻塞、验收以及日志周报绩效证据联动。"
---

# mywork 通用任务治理

任务文档跟踪承诺和执行，正式产品、技术和决策文档沉淀最终事实。新建任务使用[任务模板](references/任务模板.md)。只有需要在项目文档中心定位、迁移或归档任务时才读取 `mywork-project-docs-governance`；只有执行批量治理、MOC、链接或 Schema 检查时才读取 `campfire-workspace-governance`。

## 归属

- 明确属于项目的任务放在该项目文档中心的 `任务/`；项目仍是主归属。
- 归属不明确时留在 `_收件箱/用户输入/`，不得为了收纳任务创建新领域。
- 所有任务统一使用 `type: task` 和 `任务-` 前缀。
- `task_source: personal` 表示个人主动任务；`assigned` 表示上级明确交办。沟通渠道另用 `source_channel`。

## 生命周期

本 Skill 是任务生命周期语义的唯一 Skill 来源。合法值以 Campfire Schema 为机器权威：`todo → in-progress → blocked/review → completed → archived`；取消使用 `cancelled`。尚未确认的内容是对话中的任务建议或收件箱确认事项，不创建 `lifecycle: draft` 的正式任务。`status` 表示文档是否有效，不能代替任务生命周期。

Agent可以在有证据时更新 `in-progress`、`blocked`、`review`、阻塞原因、结果摘要和验收证据。`review → completed`、取消和归档默认需要人确认；低风险且验收完全自动化时可按明确授权完成。

## 工作流

1. 保留原始要求和来源，区分原话与当前理解。
2. 定义可验证的验收标准；无法确定范围时设置 `requires_human: true`。
3. 执行过程中只记录关键状态、阻塞和证据，不把任务文档写成流水账。
4. 完成后填写结果、交付物和验证证据，并检查是否需要回写产品、技术或决策文档。
5. 工作日志引用任务记录当日过程；周报按周期汇总已验证变化；绩效只生成有证据的成果候选。
6. 完成且结论已沉淀后，沿用项目文档两阶段归档。

## 边界

- 不按任务数量推断绩效价值，不编造影响、负责人、截止日期或完成状态。
- 不把 `assigned` 自动等同高优先级。
- Agent不能自行将 `personal` 改成 `assigned`。
- 小型确认保留在任务的 `requires_human` 和 `blocked_reason`；影响归属、合并或任务是否成立的问题才生成收件箱确认单。
