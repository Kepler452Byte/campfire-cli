# Maintenance App SPEC

本模块处理跨文档检查、MOC 等可见自动生成物和维护运行记录。Space/Domain 结构由 Workspace App 提供，文档查询索引由 Document App 提供；本模块不重复定义，也不承载文档语义修改计划。

文档扫描、类型、Profile、任务状态、模板枚举、Frontmatter 顺序、跨字段不变量与确定关系索引均委托 Document App；本模块只负责检查编排、过滤、可见派生内容和报告。全量 check 或 scoped sync 通过消费方维护端口触发 Document Index 校正，不依赖具体 Document Service，也不得实现第二套索引规则。写入通过共享 ChangeSet Executor 复核内容哈希并原子提交。

Domain MOC 只列出该 Domain `_模板/` 中实际存在的模板；Maintenance 不计算或持久化模板继承结果，Agent 按 Domain 祖先路径就近选择。

受管范围由当前 Workspace 中实际存在的 `_空间.md` 动态发现，不使用固定 Space 白名单；`scope_roots` 只补充 `_待用户确认/` 等非 Space 系统范围。声明文件由 Workspace App 校验，不计入普通文档问题。

`check --scope` 的 status 表示当前筛选结果，`workspace_status` 表示全 Workspace 状态。`sync --scope` 只发现并扫描 scope 内的 Domain 和文档，一次刷新 MOC、关系页并触发文档索引 reconcile；只受当前范围的结构问题阻塞。`document list/inspect` 不以 Maintenance 为前置步骤。单篇内容创建、补全和修改属于 Document App，批量迁移属于 Workspace Restructure。

```text
maintenance/
├── link_service.py
├── moc_service.py
└── maintenance_service.py
```

归档仅是 Document Profile 中的 `document_status` 值，通过 `document apply` 修改；Maintenance 不提供归档命令。

scoped sync 在全局拓扑中检查目标身份是否重复，再按稳定 Domain id 和当前 scope 更新结构投影；合法外部改名不依赖先 check。文档索引先独立提交完整 generation，再在文件变更事务内提交领域索引；领域索引提交失败回滚其事务并补偿生成文件，不在领域提交之后追加可能失败的文档索引提交。两个投影可分别重建，不宣称文件系统与 SQLite 共享事务。可捕获失败返回阶段与实际写入状态，补偿失败须停止并核对文件，不盲目重放。
关系页只消费 Document Index 的 `related_docs` 正向和反向投影；不另行解析正文链接、不计算标签或文本相似度。正文不再作为关系 SSOT，旧正文不自动迁移。
