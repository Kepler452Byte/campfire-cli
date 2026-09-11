# Decisions

- 2026-09-11 — Decision: 产品名使用 Campfire，Python 分发包和源码包分别使用 `campfire-cli` 与 `campfire_cli`，唯一命令入口使用 `campfire`。Why: 项目语义完整且日常调用简短。Impact: 人类和自动化统一调用 `campfire`。
- 2026-09-11 — Decision: CLI 源码独立维护在 `dev-lab/apps/campfire-cli`。Why: 解耦工具发布周期与 Workspace 内容。Impact: Agent 通过安装后的 CLI 操作任意 Workspace。
- 2026-09-12 — Decision: 产品命名为 Campfire，顶层对象从 Vault 提升为 Workspace，CLI 为 `campfire`。Why: 产品服务于人和多个 Agent 围绕共享上下文协作，而非只做 Obsidian 文档治理。Impact: 不保留 `vg`、`vault-governance` 或 Vault 内状态目录的兼容入口。
- 2026-09-12 — Decision: 运行状态统一位于用户级 `~/.campfire/workspaces/<id>/`。Why: 支持多个 Workspace 并使 CLI 与内容存储解耦。Impact: Markdown 是内容 SSOT，SQLite 是可重建索引。
- 2026-09-11 — Decision: SQLite 保存当前状态，Markdown 保持内容事实来源，JSON 只保存配置、当前关键快照和有限变更。Why: 同时获得查询能力、可移植性和 Git 可审查性。Impact: 活动数据库不提交 Git。
