# Maintenance App SPEC

本模块处理后续增量维护、链接检查、MOC 等自动生成物、两阶段归档和状态索引。Space/Domain 结构由 Workspace App 提供，本模块不重复定义，也不承载文档语义修改计划。

文档扫描、类型、Profile、任务状态、模板枚举、Frontmatter 顺序和跨字段不变量均委托 Document App；本模块只负责检查编排、过滤、派生内容、索引和报告。写入通过共享 ChangeSet Executor 复核内容哈希并原子提交。

受管范围由当前 Workspace 中实际存在的 `_空间.md` 动态发现，不使用固定 Space 白名单；`scope_roots` 只补充收件箱等非 Space 系统范围。声明文件由 Workspace App 校验，不计入普通文档问题。

`check --scope` 的 status 表示当前筛选结果，`workspace_status` 表示全 Workspace 状态。`sync --scope` 只发现并扫描 scope 内的 Domain 和文档，一次刷新 MOC、关系页与该范围的 SQLite 索引；只受当前范围的结构问题阻塞。单篇内容创建、补全和修改属于 Document App，批量迁移属于 Workspace Restructure。

```text
maintenance/
├── link_service.py
├── moc_service.py
├── archive_service.py
└── maintenance_service.py
```

归档是 Maintenance 子用例，对外使用 `campfire maintenance archive check/apply`，不建立独立 Archive App。
