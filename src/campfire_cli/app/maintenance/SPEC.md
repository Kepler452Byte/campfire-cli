# Maintenance App SPEC

本模块处理后续增量维护、链接检查、MOC 等自动生成物、两阶段归档和状态索引。Space/Domain 结构由 Workspace App 提供，本模块不重复定义。语义计划使用稳定 ID，默认未审批，写操作必须显式确认；不维护含义不明的 `current-plan`。

文档扫描、类型、Profile、任务状态、模板枚举、Frontmatter 顺序和跨字段不变量均委托 Document App；本模块只负责 Workspace 范围的扫描编排、过滤、统一计划、执行、局部验收、派生内容和报告。写入在治理锁内复核内容哈希和治理配置哈希。

受管范围由当前 Workspace 中实际存在的 `_空间.md` 动态发现，不使用固定 Space 白名单；`scope_roots` 只补充收件箱等非 Space 系统范围。声明文件由 Workspace App 校验，不计入普通文档问题。

`maintenance plan --spec` 是 Agent 语义判断进入确定性执行链路的唯一批量入口。Plan 可以修改 Frontmatter、按有效 type 在同一 Domain 内修正文件名并格式化字段顺序；不得跨目录移动。跨 Domain 迁移属于 Workspace Restructure。

`maintenance verify` 只检查指定 Plan 涉及的文档，不被其他范围的历史问题影响。`check --scope` 的 status 表示当前筛选结果，`workspace_status` 表示全 Workspace 状态。`sync --scope` 只受当前范围的结构问题阻塞。

```text
maintenance/
├── link_service.py
├── moc_service.py
├── archive_service.py
├── plan_service.py
└── maintenance_service.py
```

归档是 Maintenance 子用例，对外使用 `campfire maintenance archive check/apply`，不建立独立 Archive App。
