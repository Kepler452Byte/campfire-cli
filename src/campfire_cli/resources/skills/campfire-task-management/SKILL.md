---
name: campfire-task-management
description: "创建、更新和完成 Campfire 任务文档；适用于用户要求为某项目或个人新建/更新/完成任务时定位归属、按 Profile 契约写入并验证，不负责执行任务、改代码或 Agent Session 调度。"
---

# Campfire 任务管理

统一任务文档（`任务-` 前缀）的创建、状态更新与完成闭环。任务分两类：有项目任务（关联已注册 Project）与无项目任务（个人待办、跨项目事务）。两类任务都不得虚构归属：`project` 字段只在能唯一解析到已注册 Project 时填写。

通用写入门禁（授权、对象唯一、事实核验）遵循 `campfire-document-capture`；本 Skill 是任务类型的专项 SOP，不复制通用纪律。首次读写 Campfire 文档的 Session 先运行 `campfire-context-bootstrap` 解析 Workspace 与 Project。

## 状态机

```text
用户表达任务意图
        │
        ▼
project list 关键词匹配
        │
   ┌────┴────┐
唯一命中   多候选/无候选
   │           │
   ▼           ▼
有项目任务   能澄清则问用户，
   │         不凭相似度猜测
   │           │
   │      用户明确无项目？
   │        │        │
   │       是        否（取消或继续澄清）
   │        │
   ▼        ▼
项目文档中心  全局任务领域
   └────┬────┘
        ▼
document inspect 取契约 → 写入 → check → sync → 回报路径
```

## 工作流

### 1. 归属定位

1. 从用户表述提取项目关键词（项目名、简称、仓库名、路径片段）。
2. 运行 `campfire workspace project list`，在 id、name、git_remote_url、local_path、document_domain 中做子串匹配。
3. 唯一命中即定位该项目及其 `document_domain`；多候选或无候选时向用户列出候选并询问，不凭名称相似度猜测。
4. 用户明确表示任务不关联项目（个人待办、跨项目事务）时归入无项目任务。

### 2. 无项目任务归属

- 无项目任务统一落 `mywork/【工作日志】文档中心/任务/`（个人事务域；该子目录不存在时随首次任务创建，并遵循 `campfire-workspace-maintenance` 的领域检查）。
- frontmatter 的 `project` 字段留空，`domain` 填实际所在领域；不虚构项目归属，不把跨项目事务挂到某一个项目下。

### 3. 契约获取与写入

1. 文件名使用 `任务-<一句话标题>.md` 前缀，类型契约以 `campfire document type list` 为准。
2. 运行 `campfire document inspect --path <同领域最近一篇任务文档>` 获取该领域 task 类型的 Profile 字段与顺序；同领域无先例时在目标路径上以 inspect 反查领域默认 Profile。不硬编码字段清单。
3. 按 field_order 拼 frontmatter 并写入正文骨架。字段规则：

| 字段 | 规则 |
|------|------|
| task_id | 同领域既有任务递增编号；无先例时从 1 起 |
| status | 新建 `todo`，进行中 `doing`，完成 `done`，取消 `cancelled`；以 Profile 实际枚举为准 |
| lifecycle | 新建 `proposed`，进行中 `current`，完成/取消后 `completed` |
| priority | 默认 `medium`；用户明示紧急/低优时用 `high`/`low` |
| requires_human | 任务含部署、发布、对外沟通等 Agent 不可独立完成的关键步骤时为 `true` |
| project | 仅在唯一解析到已注册 Project 时填写；无项目任务留空 |

4. 有项目任务落各自文档中心的任务子目录（已有 `任务/` 惯例的项目沿用；无先例时在文档中心根下创建并沿用同规则）。

### 4. 状态流转

- 更新任务：只改 status、lifecycle、completed、result_summary 等状态字段与正文进展记录，不重写既有事实。
- 完成任务：status → `done`、lifecycle → `completed`、补 result_summary 与 completed 日期；正文追加结论与证据来源。
- 取消任务：status → `cancelled`，正文注明取消原因；不删除文档。
- 用户口头报进度时主动提议同步对应任务文档；一次汇报合并提议，不逐条打断。

### 5. 验证闭环

```bash
campfire --workspace personal document check --path "mywork/【某项目】文档中心/任务/任务-....md"
campfire --workspace personal maintenance sync --scope "mywork/【某项目】文档中心"
```

写入或更新后必须执行 check 与 sync，向用户回报写入路径、创建或更新结果与未决字段；check 不通过不得声称完成。

## 边界

- 不负责执行任务本身、不修改代码、不分派或恢复 Agent Session。
- 任务的讨论与方案沉淀遵循 `campfire-document-capture`，结构治理遵循 `campfire-workspace-maintenance`。
- 看板类任务清单（`看板-` 前缀）的改造遵循 `campfire-kanban-board`，本 Skill 只处理单篇任务文档。
- 不确定归属、字段枚举与 Profile 冲突时询问用户或走 Decision，不静默落盘。
