# Decisions

- 2026-09-11 — Decision: 项目名和包名使用 Campfire / `campfire_cli`，主命令使用 `campfire`，并发布 `campfire-cli` 别名。Why: 项目语义完整且日常调用简短。Impact: 文档使用 `campfire`，自动化可使用任一入口。
- 2026-09-11 — Decision: CLI 源码独立维护在 `dev-lab/apps/campfire-cli`，运行数据保存在目标 Vault 的 `.campfire/`。Why: 解耦工具发布周期与笔记内容。Impact: Agent 通过安装后的 CLI 操作任意 Vault。
- 2026-09-11 — Decision: SQLite 保存当前状态，Markdown 保持内容事实来源，JSON 只保存配置、当前关键快照和有限变更。Why: 同时获得查询能力、可移植性和 Git 可审查性。Impact: 活动数据库不提交 Git。
