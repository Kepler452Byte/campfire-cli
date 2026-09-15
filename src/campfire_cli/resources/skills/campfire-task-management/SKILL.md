---
name: campfire-task-management
description: "创建、更新和完成 Campfire 任务文档；适用于用户要求为某项目或个人新建/更新/完成任务时定位归属、按 Profile 契约写入并验证，不负责执行任务、改代码或 Agent Session 调度。"
---

# Campfire 任务管理

统一任务文档（`任务-` 前缀）的创建、状态更新与完成闭环。任务分两类：有项目任务（关联已注册 Project）与无项目任务（个人待办、跨项目事务）。两类任务都不得虚构归属：`project` 字段只在能唯一解析到已注册 Project 时填写。

通用写入门禁遵循 `campfire-document-capture`；本 Skill 是任务类型的专项 SOP，不复制通用纪律。任务归属和 Task Profile 需要治理上下文，进入本 Skill 前加载 `campfire-context-bootstrap`。

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
document apply 取契约并写入 → 只执行返回的 follow_up → 回报路径
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

1. 只提交任务标题和 `--type task`；CLI 从 type 推导最终文件名，Agent 不手写前缀映射。
2. 有项目任务落各自文档中心的任务子目录；已有 `任务/` 惯例的项目沿用，无先例时在文档中心根下创建并沿用同规则。
3. 准备任务正文骨架和可验证的业务字段，调用 `campfire document apply --type task`。CLI 负责 Profile、枚举、字段顺序和 YAML 类型；Skill 不硬编码这些可演进契约。
4. CLI 返回 `needs-input` 时，根据其一次性列出的必填字段与允许值补齐事实，不猜测。

### 4. 状态流转

- 更新任务：Frontmatter 补丁使用 `document apply --set`，进展记录使用 `document apply --append-section`；只修正文的小范围改动可使用 edit。
- 完成或取消任务时，以 CLI 返回的当前 Task Profile 为准补齐状态、结果与验证信息，不在 Skill 中复制枚举。
- 用户口头报进度时主动提议同步对应任务文档；一次汇报合并提议，不逐条打断。

### 5. 验证闭环

`document apply` 成功即表示目标文档已通过当前 Task Profile。写入后只执行结果实际返回的 follow-up，不固定追加 `document check` 或全 Workspace 扫描。向用户回报最终写入路径、动作、验证结果与未决字段。

## 边界

- 不负责执行任务本身、不修改代码、不分派或恢复 Agent Session。
- 任务的讨论与方案沉淀遵循 `campfire-document-capture`，结构治理遵循 `campfire-workspace-maintenance`。
- 看板类任务清单（`看板-` 前缀）的改造遵循 `campfire-kanban-board`，本 Skill 只处理单篇任务文档。
- 不确定归属、字段枚举与 Profile 冲突时询问用户或走 Decision，不静默落盘。
