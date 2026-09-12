---
name: campfire-conversation-intake
description: "将用户在对话中表达的交办、个人任务、学习意图和沉淀请求转换为可确认的 Campfire 行动；普通问答不自动创建任务或文档。"
---

# Campfire 对话入口

让用户直接说出需求，不要求用户先创建收件箱文件或填写 Frontmatter。先解决当前对话需求，再判断是否需要跨 Session 跟踪或长期沉淀。

## 路由

1. 保留与意图有关的用户原话、来源和时间，不复制无关聊天内容。
2. 判断这是普通问答、明确任务、模糊交办、持续学习，还是明确的沉淀请求。
3. 普通问答直接回答；没有用户授权时，不自动创建任务或知识文档。
4. 用户说“记一下”“帮我跟进”“交给 Agent”“老板交代”等，视为允许提出任务建议，但不等于允许创建正式任务或实施。读取[模糊任务 SOP](references/task-intake.md)。
5. 用户表达“深入理解”“系统学习”“做实验并总结”等持续学习意图时，读取[学习与知识晋升 SOP](references/learning-intake.md)。
6. 无法判断对象、项目、行动或去向，或者用户暂时无法回答时，读取[收件箱衔接规则](references/inbox-handoff.md)。

只有进入具体操作时才加载对应 Skill：用户确认创建任务后读取 `mywork-task-governance`；确认沉淀长期知识后读取 `mynote-knowledge-governance`；处理收件箱文件时读取 `campfire-inbox-triage`；执行批量迁移、MOC、链接或 Schema 治理时读取 `campfire-workspace-governance`。软件开发进入实施阶段后读取目标项目自身的 `AGENTS.md` 和 `tasks/SPEC.md`。

## 交互原则

- 用户不需要理解 Campfire 目录、类型和字段；Agent 负责提出结构化草案。
- 能提供即时价值时先回答，不以“先建任务”为前置条件。
- 只询问会改变目标、范围、归属、验收或授权的关键问题，并给出推荐选项。
- 对话阶段只形成任务建议；正式任务的字段和生命周期完全由 `mywork-task-governance` 决定。
- Agent 执行中发现的内容先作为知识候选，不能直接晋升为正式知识。
- 当前 CLI 不支持的 Task Channel、Session 或通知命令不得伪造为已执行；使用现有任务文档表达草案，并明确报告能力缺口。

## 输出

对需要持续处理的意图，向用户返回一张简短确认卡：Agent 的理解、建议类型、目标项目或领域、关键问题和下一步。不要只在 Vault 中写文件而不在当前对话告知用户。
