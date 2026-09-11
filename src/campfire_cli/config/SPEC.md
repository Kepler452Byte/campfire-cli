# Config SPEC

配置和状态统一保存在用户级 `CAMPFIRE_HOME`，默认是 `~/.campfire/`。`registry.json` 注册多个 Workspace；每个 Workspace 的治理契约位于 `workspaces/<id>/config/`。CLI 不读取或创建 Workspace 内 `.campfire/`。
