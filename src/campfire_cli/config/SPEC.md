# Config SPEC

配置和状态统一保存在用户级 `CAMPFIRE_HOME`，默认是 `~/.campfire/`。`local.yaml` 保存多个 Workspace 的本机路径、默认选择和仓库目录绑定；Vault 根目录 `.campfire.yaml` 保存便携项目元数据。`campfire.db` 只按 `workspace_id` 隔离可重建索引与工作流状态。CLI 不读取或创建 Workspace 内 `.campfire/`。

包内 `resources/defaults/config.yml` 是产品默认值的唯一来源：Workspace 模板、文档类型、Profile、项目状态、归档原因和 Issue 展示规则按顶级分区集中维护。`~/.campfire/config.yml` 只保存用户覆盖项，使用 mapping 深度合并、列表整体替换；运行状态不得写入配置。

Job 的默认日志上限、保留策略和环境记录目录在 jobs 分区。jobs.yaml 保存本机执行定义，local.yaml 另保存稳定 environment_id；jobs/runs.db 保存可清理运行历史，独立于文档缓存。`_定时任务/` 纳入系统文档 scope，首次记录时创建，不预建空环境文件。
