---
name: campfire-workspace-maintenance
description: "持续维护 Campfire Workspace 的结构与文档合规；适用于 Space/Domain 声明、文档检查与格式化、MOC 同步、归档和日常维护，不用于跨领域批量重构。"
---

# Campfire Workspace Maintenance

`.campfire.yaml` 是 Workspace 与 Project 注册事实源，其中 `projects[].document_domain_id` 是 Project 到根 Domain 绑定的唯一事实。`_空间.md`、`_领域.md` 和内容文档是结构与内容事实源；SQLite 中的 Workspace 拓扑与文档数据只是本机可重建索引。首次接入使用 `campfire setup --path <vault>`，它会自动扫描并建立索引，不要求用户单独初始化数据库。Workspace 已注册后，显式选择只使用根级 `campfire --workspace <id> ...`；在该 Workspace 内运行时可省略。

日常运行 `campfire maintenance check` 时会同步刷新 Space、Domain 和 Document 索引。仅在 SQLite 被删除、怀疑索引漂移或 CLI 升级修复时使用低频恢复入口：

```bash
campfire workspace rebuild
campfire workspace rebuild --confirm
```

`rebuild` 不修改 Vault 文档；它从 Manifest 和 Markdown SSOT 完整替换本机派生索引。不要直接修改 SQLite，也不要把数据库提交到 Git 或跨设备同步。

发现受管文档集合使用 `document list`，理解单篇文档的显式关联、出链、反向链接和失效引用使用 `document inspect`。两者查询前自动 reconcile，不要求 Agent 先执行 Maintenance；正文仍由 Agent 按返回路径读取。

目标是允许人类低成本记录，同时让 Agent 以可审阅、可重复执行的方式保持 Workspace 合规。

进入需要 Workspace、Domain、Project 或 Profile 上下文的治理流程时，先加载 `campfire-context-bootstrap`。用户已给出唯一存在路径，且只读取或小范围修改人工正文时，直接使用文件工具，不启动 bootstrap。诊断配置、结构或文档问题时分别使用 `workspace config check`、`workspace space/domain check` 或 `maintenance check`；不要把全量检查当作每次写文档的固定步骤。

## 工作流

1. 通过 `workspace space/domain list` 和声明文件理解现有结构。正式文档必须归入 Domain，Space 不直接承载正式文档。
2. 新目录使用 `space/domain create`；已有目录使用 `space/domain adopt`。CLI 根据目标路径推导所属 Space 和最近父 Domain。Project 从 Manifest 绑定的稳定根 Domain id 与祖先拓扑推导，Domain 声明不保存 Project 字段。默认先预览，用户确认后追加 `--confirm`。
3. 创建正式文档、接管无 Frontmatter 的既有正文、修改 Frontmatter 或显式变更类型，使用一次 `campfire document apply`。CLI 根据目标 Domain 解析有效 Profile，根据 type 推导文件名，并一次返回所有缺失字段。契约已知时直接 apply；现有文档的字段类型或合法值未知时只执行一次 `document inspect` 后 apply，不从 `tree` 开始逐层探索。Agent 不手工同步 type 和文件名前缀。格式顺序单独使用 `document format`。
4. 单篇文档改名或跨 Domain 移动使用 `document move --path <source> --domain <target-domain-id> [--name <filename>]`；批量文档迁移使用 `workspace restructure`。不要让 Agent 拼目标目录，不要为单篇修改创建批次计划。
5. 只在结果明确表示已实际写入后读取结构化 `follow_up`：有 `maintenance sync` 就直接执行一次；没有就结束。预览、阻塞或缺输入结果的 `follow_up` 必须为空。只有用户要求预览派生变化时才加 `--dry-run`，只有诊断合规问题或发布验收时才运行 scoped `maintenance check`。
6. `maintenance sync --scope <path>` 只扫描 scope 内的 Domain 和文档，一次刷新 MOC、关系页并校正本机索引；不要随后无条件重复 sync 或扩大到整个 Workspace。
7. 报告原始笔记变化、自动生成物和仍需用户确认的事项。无法从正文、领域上下文或项目事实唯一决定时，调用 `campfire decision create`；获得回答后调用 `decision answer`，答案被原任务消费后调用 `decision close`。

## 路由

```text
发现对象
   |
   +-- 新建、补 Frontmatter 或修改字段
   |      -> document apply 预览 -> 补齐 missing_fields
   |      -> document apply --confirm -> 仅执行返回的 follow_up
   |
   +-- 只改正文
   |      -> 已知唯一路径时直接 edit
   |      -> 显式链接、生成视图或用户要求即时刷新时才 sync 一次
   |
   +-- 单篇文档改名或跨 Domain 移动
   |      -> document move 预览 -> 必要时 --set/--unset 补齐
   |      -> document move --confirm -> 仅执行返回的 follow_up
   |
   +-- 已有目录但没有声明
   |      -> space/domain adopt
   |
   +-- 需要新 Space 或 Domain
   |      -> space/domain create
   |
   +-- 已声明 Domain 合并或删除逻辑空领域
   |      -> campfire-workspace-restructure
   |      -> domain merge/delete 预览 -> 同命令 --confirm
   |
   +-- 需要批量迁移文档或拆分领域
   |      -> campfire-workspace-restructure
   |
   `-- 归属或语义不能唯一确定
          -> decision create
          -> pending Decision 自动投影到 _协作/decisions/pending
```

Agent 负责理解正文、项目事实和业务语义；CLI 负责 Profile 校验、预览、哈希保护、原子执行、引用更新和索引刷新；用户负责确认歧义与高风险归属。批量内容迁移必须进入 Workspace Restructure 计划。

## 不变量

- 整个 Workspace 只有一个根 `_收件箱/`；语义无法唯一判断时进入待用户确认，不为追求检查通过而猜测。
- `_空间.md` 声明 Space，`_领域.md` 声明可多级嵌套的 Domain；保留目录不是 Space 或 Domain。
- `.campfire.yaml`、声明文件、MOC 自动区域、Base、关系页和 SQLite 可读但不可由 Agent 直接写入；必须使用对应 Campfire 语义命令，命令缺失时报告能力缺口。
- Project 单向绑定稳定根 Domain id；Domain 移动不改变绑定，子 Domain 通过祖先拓扑继承 Project。
- 一篇文档只有一个主物理 Domain，可以出现在多个自动索引中。
- MOC 自动区域、相关文档、反向链接、关系和统计由 CLI 生成，不手工维护。
- Maintenance 只检查文档、刷新派生内容和执行显式归档，不改变文档主物理归属，不进行跨领域移动、领域合并或拆分。
- 写入返回 `concurrent-change` 时停止并重新检查，不覆盖其他会话的新内容。
- Markdown 是内容事实来源，用户级配置是治理契约；SQLite 只保存索引与工作流状态。
- Decision 是工作流对象：SQLite 当前状态与追加事件是 SSOT，`_协作/decisions/` 只读投影不得手工维护。

## 内容与任务

- 跨项目可复用的长期认知归入 knowledge 类型 Space；项目当前实现、方案、决策、问题或记录归入 Project 绑定的 Domain。项目事实必须检查已注册源码、配置和测试。
- `status`、`lifecycle` 和其他字段只从 Document Profile 获取。任务正文需要创建或更新时参考[任务正文结构](references/任务正文结构.md)。
- 归档必须由显式 `archive_requested` 触发；先运行 `maintenance archive check`，审查后执行 `archive apply --confirm`。不得仅因长期未更新而归档。
