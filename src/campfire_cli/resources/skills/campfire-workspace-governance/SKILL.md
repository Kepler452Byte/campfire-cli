---
name: campfire-workspace-governance
description: "治理 Campfire Workspace 中的共享上下文；适用于收件箱分流、笔记分类、迁移、沉淀、MOC、领域声明和治理检查。"
---

# Campfire Workspace 治理

目标是允许人类低成本记录，同时让 Agent 以可审阅方式将笔记收敛到正式领域。

受管范围内任意 Markdown 都应可被纳管：脚本负责发现、校验、生成确定性计划和执行机械变更；Agent 负责理解正文并提出标题、摘要、类型和目标领域。语义不明确时必须进入待用户确认，而不是为追求检查通过而猜测。

先运行 `campfire workspace resolve` 获取目标 Workspace；需要指定其他 Workspace 时使用 `campfire --workspace <id>`。然后从返回的 Workspace 根目录读取 `AGENTS.md` 和治理 SPEC。本 Skill 只处理分类、迁移、MOC、链接、Frontmatter、领域声明和治理检查；对话意图、具体任务、知识写作和周报分别由对应的垂直 Skill 处理。

## 工作流

1. 确认已安装 `campfire-cli`，运行 `campfire workspace resolve` 和 `campfire maintenance check` 获取当前 Workspace 与状态；该命令不改原始笔记，但会刷新用户级治理状态，不得直接读写 `~/.campfire/`。
2. 运行 `campfire workspace space list` 与 `campfire workspace domain list` 获取候选结构；阅读目标及相邻 `_领域.md`，依据收录范围和边界判断主归属。
3. 一次性存量治理使用 `campfire migration inventory --scope <path> --batch <id>` 与 `campfire migration plan --batch <id>`；工具无法推断的移动或元数据修改写入 YAML/JSON 意图规格，并使用 `campfire migration plan --batch <id> --spec <file>`。日常新增和变化使用 `campfire maintenance plan`。所有计划默认未审批，有关键歧义时不执行。
4. 只在用户授权范围内整理笔记。删除、合并、领域拆分、顶级领域创建和冲突权威判定必须由用户确认。
5. 写入前先运行不带 `--confirm` 的 `campfire migration apply` 或 `campfire maintenance apply`；只有计划已明确审批且预检通过时才追加 `--confirm`。
6. 使用 `campfire maintenance sync --dry-run` 预览生成物，再运行 `campfire maintenance sync`。批量治理最后运行 `campfire migration verify --batch <id>`；日常维护运行 `campfire maintenance run`。
7. 报告原始笔记变化、自动生成物以及仍需用户确认的事项。

## 不变量

- 整个 Workspace 只有根目录一个 `_收件箱/`；领域内部不创建收件箱。
- 顶级内容空间以 `_空间.md` 为准，正式领域以 `_领域.md` 为准；保留目录不是空间或领域。
- Space 只组织领域树，不直接承载正式文档；Domain 可多级嵌套，子领域继承父领域 governance。
- 新增顶级 Space 或根 Domain 必须获得用户确认；明确授权后使用 `workspace space/domain create`，不手写标记和 MOC。
- 一篇笔记只有一个主物理位置，可以出现在多个自动索引中。
- MOC 自动区域、相关文档、反向链接、关系图和统计必须由 Python 工具生成，禁止手工维护。
- `campfire maintenance check` 必须只读原始笔记；`campfire maintenance sync` 不得移动、重命名、合并或删除原始笔记。
- 一次性治理与日常维护使用不同命令和状态；Agent 不得用 Migration 入口处理普通增量维护。
- 写入返回 `concurrent-change`、`source-hash-changed` 或 `migration-config-changed` 时，必须停止并重新审查，不得绕过快照保护。
- Schema 是字段与枚举规则的唯一来源；Skill 模板不得复制出与 Schema 冲突的取值。
- 文档 Profile 由 `base` 一层继承编译得到；使用 `campfire document profile show` 或 `document profile resolve` 查看有效规则，不从多个 Skill 拼接字段定义。
- SQLite 只保存当前索引和工作流状态；Markdown 是内容事实来源，用户级配置是治理契约来源。
- 保留用户原文；内容沉淀和重写超出明确授权时先提出建议。

## 内容归属

- 跨项目可复用、可独立理解的长期认知归入 knowledge Space；仅描述某个项目当前实现、方案、决策、问题或记录的内容归入该 Project 绑定的根 Domain 或子 Domain。
- 一篇文档只有一个主物理 Domain；跨领域关系用链接和自动索引表达。不能唯一判断 Project、Space 或 Domain 时进入待用户确认。
- 项目当前事实不能从计划、问题或历史记录推断；写当前实现前检查已注册源码路径及相关源码、配置和测试。
- `status` 表示文档有效性，`lifecycle` 表示项目文档工作阶段；合法字段与枚举只从 Document Profile 读取。

## 项目文档归档

不得仅因长时间未更新而归档。先设置 `archive_requested: true` 和明确原因；被替代或合并时补充 `superseded_by`。运行 `campfire maintenance archive check` 审查，再用 `archive apply --confirm` 移入同一 Domain 的扁平 `archive/`。归档前将仍然有效的结论回写当前产品、技术或决策文档；`archive/` 内容不能作为当前事实的唯一依据。

## 任务文档

任务跟踪承诺与执行，正式产品、技术和决策文档沉淀最终事实。任务必须使用 `type: task`，字段、条件必填项和合法生命周期只通过 `campfire document profile show task` 读取。创建任务正文时参考[任务正文结构](references/任务正文结构.md)。

- 明确属于 Project 的任务归入其根 Domain 或约定的任务区域；Project 不明确时进入收件箱，不为了收纳任务猜测归属。
- 保留原始要求，区分原话、当前理解、待确认、验收标准、执行计划、关键进展和结果证据。
- `task_source: personal` 与 `assigned` 表示责任来源；Agent 不得自行把个人任务改为上级交办，也不根据来源推断优先级。
- Agent 可以根据证据更新执行中、阻塞、待验收状态及相应说明；完成、取消和归档默认需要人类确认，除非已有范围明确且验收可自动验证的授权。
- 完成前填写结果摘要和验证证据，并检查是否需要回写正式文档。工作日志可以引用任务过程，周报和绩效只能使用有证据的结果。
- 小型确认保留在任务本身；影响任务是否成立、Project/Domain 归属、合并或权威结论的问题才生成收件箱待确认文档。
