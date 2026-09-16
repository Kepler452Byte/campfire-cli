---
name: campfire-conversation-router
description: "路由用户在对话中表达的问答、任务、学习和文档沉淀意图；只决定是否进入 Campfire 文档协作流程，不负责写作、治理或 Agent Session 调度。"
---

# Campfire 对话路由

让用户直接说出需求，不要求用户先创建文件、选择类型或填写 Frontmatter。只判断当前表达是否需要形成或更新 Vault 文档，然后交给垂直 Skill；不负责 Agent Session 的分派、认领、恢复或通信。

## 路由

```text
用户在对话中表达意图
          │
          ▼
是否只需要当前回答？ ──是──> 直接回答，不创建文档
          │否
          ▼
是否要形成或更新文档？ ──是──> campfire-document-capture
          │                          │
          │                          ├── 知识文档
          │                          ├── 项目文档
          │                          ├── 任务计划文档
          │                          └── human-request
          │
          └── 无法判断 ──> 先问一个关键问题
                                │
                          无法及时确认
                                │
                                ▼
                         decision create
```

1. 普通问答直接回答；用户没有要求跨对话保留时，不自动创建文档。
2. 用户说“沉淀一下”“记到项目里”“整理成文档”或要求创建、更新、总结文档时，加载 `campfire-document-capture`。
3. 领导交办、个人待办、实施计划或“帮我跟进”需要形成任务计划文档时，读取[任务文档接入](references/task-intake.md)，再加载 `campfire-document-capture`。
4. “深入理解”“系统学习”“做实验并总结”等表达先读取[学习与知识文档接入](references/learning-intake.md)；只有用户要持续保留成果时才加载 `campfire-document-capture`。
5. 已有文件位于 `_收件箱/` 时加载 `campfire-inbox-triage`；对话中无法及时解决的关键歧义读取[收件箱衔接规则](references/inbox-handoff.md)，并创建 `human-request`。

本 Skill 到路由完成即结束。授权、资源、源码现状和目标文档由 `campfire-document-capture` 检查；成品内容由知识、项目文档或任务 Skill 负责；格式、链接、MOC 和持续检查由 `campfire-workspace-maintenance` 负责。

## 交互原则

- 用户不需要理解 Campfire 目录、类型和字段；Agent 负责提出结构化草案。
- 能提供即时价值时先回答，不以“先建任务”为前置条件。
- 只询问会改变目标、范围、归属、验收或授权的关键问题，并给出推荐选项。
- 任务计划本身就是一种正式文档；确认创建后由 `campfire-workspace-maintenance` 处理，字段和生命周期读取 Document Profile。
- 沉淀的授权、资源与事实门禁完全由 `campfire-document-capture` 决定，本 Skill 不复制其规则。
- 不在本 Skill 中设计或执行 Agent Session 交接；创建任务文档不等于已把任务交给某个 Agent。

## 输出

对需要持续处理的意图，向用户返回一张简短确认卡：Agent 的理解、建议类型、目标项目或领域、关键问题和下一步。不要只在 Vault 中写文件而不在当前对话告知用户。
