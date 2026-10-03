# Config SPEC

配置和状态统一保存在用户级 `CAMPFIRE_HOME`，默认是 `~/.campfire/`。唯一的 `campfire.db` 注册多个 Workspace 和 Project，并按 `workspace_id` 隔离索引与工作流状态。CLI 不读取或创建 Workspace 内 `.campfire/`。

包内 `resources/defaults/config.yml` 是产品默认值的唯一来源：Workspace 模板、文档类型、Profile、项目状态、归档原因和 Issue 展示规则按顶级分区集中维护。`~/.campfire/config.yml` 只保存用户覆盖项，使用 mapping 深度合并、列表整体替换；运行状态不得写入配置。
