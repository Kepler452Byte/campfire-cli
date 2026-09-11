---
name: campfire-workspace-governance
description: "治理 Campfire Workspace 中的共享上下文；适用于收件箱分流、笔记分类、迁移、沉淀、MOC、领域声明和治理检查。"
---

# Campfire Workspace 治理

目标是允许人类低成本记录，同时让 Agent 以可审阅方式将笔记收敛到正式领域。

受管范围内任意 Markdown 都应可被纳管：脚本负责发现、校验、生成确定性计划和执行机械变更；Agent 负责理解正文并提出标题、摘要、类型和目标领域。语义不明确时必须进入待用户确认，而不是为追求检查通过而猜测。

先运行 `campfire workspace resolve` 获取目标 Workspace；需要指定其他 Workspace 时使用 `campfire --workspace <id>`。然后从返回的 Workspace 根目录读取 `AGENTS.md` 和治理 SPEC。用户直接在对话中表达交办、学习或沉淀意图时读取 `campfire-conversation-intake`；处理 `_收件箱/` 时读取 `campfire-inbox-triage`；处理 `mynote/`、`mywork/`、任务或周报时加载对应全局 Skill。

## 工作流

1. 确认已安装 `campfire-cli`，运行 `campfire workspace resolve` 和 `campfire maintenance check` 获取当前 Workspace 与状态；该命令不改原始笔记，但会刷新用户级治理状态，不得直接读写 `~/.campfire/`。
2. 阅读目标及相邻 `_领域.md`，依据收录范围和边界判断主归属。
3. 一次性存量治理使用 `campfire migration inventory --scope <path> --batch <id>` 与 `campfire migration plan --batch <id>`；工具无法推断的移动或元数据修改写入 YAML/JSON 意图规格，并使用 `campfire migration plan --batch <id> --spec <file>`。日常新增和变化使用 `campfire maintenance plan`。所有计划默认未审批，有关键歧义时不执行。
4. 只在用户授权范围内整理笔记。删除、合并、领域拆分、顶级领域创建和冲突权威判定必须由用户确认。
5. 写入前先运行不带 `--confirm` 的 `campfire migration apply` 或 `campfire maintenance apply`；只有计划已明确审批且预检通过时才追加 `--confirm`。
6. 使用 `campfire maintenance sync --dry-run` 预览生成物，再运行 `campfire maintenance sync`。批量治理最后运行 `campfire migration verify --batch <id>`；日常维护运行 `campfire maintenance run`。
7. 报告原始笔记变化、自动生成物以及仍需用户确认的事项。

## 不变量

- 整个 Workspace 只有根目录一个 `_收件箱/`；领域内部不创建收件箱。
- 正式领域以 `_领域.md` 为准；保留目录不是领域。
- 一篇笔记只有一个主物理位置，可以出现在多个自动索引中。
- MOC 自动区域、相关文档、反向链接、关系图和统计必须由 Python 工具生成，禁止手工维护。
- `campfire maintenance check` 必须只读原始笔记；`campfire maintenance sync` 不得移动、重命名、合并或删除原始笔记。
- 一次性治理与日常维护使用不同命令和状态；Agent 不得用 Migration 入口处理普通增量维护。
- 写入返回 `concurrent-change`、`source-hash-changed` 或 `migration-config-changed` 时，必须停止并重新审查，不得绕过快照保护。
- Schema 是字段与枚举规则的唯一来源；Skill 模板不得复制出与 Schema 冲突的取值。
- SQLite 只保存当前索引和工作流状态；Markdown 是内容事实来源，用户级配置是治理契约来源。
- 保留用户原文；内容沉淀和重写超出明确授权时先提出建议。
