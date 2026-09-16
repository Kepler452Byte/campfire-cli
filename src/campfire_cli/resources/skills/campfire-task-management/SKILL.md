---
name: campfire-task-management
description: "查询、创建、更新和完成 Campfire 任务文档；适用于用户要求查看任务集合，或为某项目或个人维护任务时按结构化字段定位并依 Profile 写入，不负责执行任务、改代码或 Agent Session 调度。"
---

# Campfire 任务管理

统一任务文档（`任务-` 前缀）的创建与状态更新。基础 `document_status` 表示文档是否仍有效；task 专属 `task_status` 表示任务进度。`related_project` 是显式关联项目字段：Agent 根据已确认事实填写；不填表示个人或未关联项目。填写时 CLI 只接受 Manifest 中注册的 Project id，不按 Domain 自动写入或覆盖。

通用写入门禁遵循 `campfire-document-capture`；本 Skill 是任务类型的专项 SOP，不复制通用纪律。只查询任务集合时直接使用 `document list`，不加载完整 Project bootstrap。创建、修改 Frontmatter、文件名或归属时才加载 `campfire-context-bootstrap`。

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

### 0. 任务发现

- 查看当前 Workspace 全部任务时运行 `campfire document list --type task`，不隐式排除 completed、blocked 或其他 `task_status`。
- 用户明确了 Project、Domain 或 `task_status` 时追加对应筛选；多个筛选条件是 AND 关系。用户语义不明确时先澄清，不把 mtime、文件名或正文措辞解释成业务状态。
- CLI 会在查询前自动 reconcile 本地索引，不先跑 `maintenance check/sync`。需要阅读详情时只读取返回路径对应的正文；需要判断单篇任务的上下游时使用 `document inspect --path <path>`。
- `document list` 不做正文关键词或模糊检索。无法用结构化字段表达的内容检索暂时使用 Agent 自带文件搜索，并以 Markdown 正文为准。

### 1. 归属定位

1. 从用户表述提取项目关键词（项目名、简称、仓库名、路径片段）。
2. 运行 `campfire workspace project list`，在 id、name、git_remote_url、local_path、document_domain_id 中做子串匹配。
3. 唯一命中即定位该项目及其 `document_domain_id`；多候选或无候选时向用户列出候选并询问，不凭名称相似度猜测。
4. 用户明确表示任务不关联项目（个人待办、跨项目事务）时归入无项目任务。

### 2. 无项目任务归属

- 无项目任务统一落已声明的个人任务 Domain：`mylog/个人任务/`（`log-personal-tasks`）。不在该目录下再创建 `任务/` 子目录。
- 不虚构项目归属；任务确有明确关联但不属于项目任务时可填写 `related_project`，否则保持为空。

### 3. 契约获取与写入

1. 只提交任务标题和 `--type task`；CLI 从 type 推导最终文件名，Agent 不手写前缀映射。
2. 有项目任务落各自文档中心的任务子目录；已有 `任务/` 惯例的项目沿用，无先例时在文档中心根下创建并沿用同规则。
3. 准备任务正文骨架和可验证的业务字段，调用 `campfire document apply --type task`。CLI 根据有效 Profile 确定字段类型、枚举和顺序；项目关联明确时显式填写 `related_project`。列表使用严格 JSON 数组。Skill 不硬编码这些可演进契约。
4. CLI 返回 `needs-input` 时，根据其一次性列出的必填字段与允许值补齐事实，不猜测。

### 4. 状态流转

- 更新任务：Frontmatter 契约已知时直接使用 `document apply --set`；字段类型或合法值未知时先对该文档执行一次 `document inspect`，再 apply，不从 `tree` 或逐层 help 开始。进展记录使用 `document apply --append-section`；只修正文的小范围改动可使用 edit。
- 完成或取消任务时，只更新 `task_status`；结果、阻塞说明和进展记录写入正文，不固化为任务字段。字段类型或合法值以 CLI 当前 Profile 为准。
- 用户口头报进度时主动提议同步对应任务文档；一次汇报合并提议，不逐条打断。

### 5. 验证闭环

`document apply` 成功即表示目标文档已通过当前 Task Profile。写入后只执行结果实际返回的 follow-up，不固定追加 `document check` 或全 Workspace 扫描。向用户回报最终写入路径、动作、验证结果与未决字段。

## 边界

- 不负责执行任务本身、不修改代码、不分派或恢复 Agent Session。
- 任务的讨论与方案沉淀遵循 `campfire-document-capture`，结构治理遵循 `campfire-workspace-maintenance`。
- 看板类任务清单（`看板-` 前缀）的改造遵循 `campfire-kanban-board`，本 Skill 只处理单篇任务文档。
- 不确定归属、字段枚举与 Profile 冲突时询问用户或创建 `human-request`，不静默落盘。
