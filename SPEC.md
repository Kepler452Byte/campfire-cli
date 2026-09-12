# Campfire SPEC

本项目是面向工作与学习场景的本地优先人机协作 CLI。产品目标与业务架构以 `ARCHITECTURE.md` 为准。

## 稳定边界

```text
CLI delivery adapter
        ↓
Migration / Maintenance Service
        ↓
消费方 Protocol
        ↓
SQLite / Filesystem Implementation
```

- `app/` 放业务模块与 CLI 适配器。
- `common/` 放两个 App 共同使用的文档治理原子能力和技术机制。
- `config/` 放随 Workspace 或运行环境变化的配置。
- CLI 通过用户级 registry 管理多个 Workspace，不依赖任何 Workspace 内的工具目录。
- Markdown 是内容事实来源；`~/.campfire/workspaces/<id>/config/` 是治理契约来源；`~/.campfire/campfire.db` 是唯一数据库，保存 Workspace/Project 注册数据、按 Workspace 隔离的可重建索引和工作流状态。
- JSON 仅承载配置、关键状态备份和有限的最近变更。
- Migration 与 Maintenance 不共享含义模糊的业务入口。
- CLI 不直接实现业务规则；Service 不依赖 Typer。
- 字段、枚举和跨字段不变量统一由 `common/governance/` 解释；Service 与具体检查器不得复制规则值。
- Frontmatter Profile 只允许一层 `base` 配置继承；Profile Loader 编译完整规则，Validator 与 Formatter 共用同一个 EffectiveProfile。
- 所有写入默认预检，语义计划默认未审批。
- 写入用例必须在治理锁内复核生成计划时的内容哈希，发现外部变化时拒绝覆盖。

代码风格参考 `templates/fastapi-template`，但不引入 HTTP、WebSocket、认证和异步数据库等无关能力。
