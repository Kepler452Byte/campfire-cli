# Config SPEC

配置和状态统一保存在用户级 `CAMPFIRE_HOME`，默认是 `~/.campfire/`。唯一的 `campfire.db` 注册多个 Workspace 和 Project，并按 `workspace_id` 隔离索引与工作流状态；每个 Workspace 的治理契约位于 `workspaces/<id>/config/`。CLI 不读取或创建 Workspace 内 `.campfire/`。

包内 `resources/defaults/` 是产品默认值的唯一来源：Workspace 模板、文档类型、Profile、项目状态、归档原因和 Issue 展示规则均使用按领域拆分的 JSON。Python 只负责加载、校验和执行；正则表达式、文件协议标记等实现细节保留在代码中。初始化时将可定制的 Workspace 治理契约复制到用户级配置，运行状态不得写回包内默认值。
