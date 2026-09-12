# Maintenance App SPEC

本模块处理后续增量维护、链接检查、MOC 等自动生成物、两阶段归档和状态索引。Space/Domain 结构由 Workspace App 提供，本模块不重复定义。语义计划默认未审批，写操作必须显式确认。

文档扫描、类型、Profile、任务状态、模板枚举和跨字段不变量均委托 Document App；本模块只负责 Workspace 范围的扫描编排、过滤、计划、执行、派生内容和报告。写入在治理锁内复核内容快照。

```text
maintenance/
├── link_service.py
├── moc_service.py
├── archive_service.py
└── maintenance_service.py
```

归档是 Maintenance 子用例，对外使用 `campfire maintenance archive check/apply`，不建立独立 Archive App。
