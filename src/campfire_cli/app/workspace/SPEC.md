# Workspace App SPEC

本模块管理 Workspace 注册表和初始化。Workspace id 是本机治理状态的稳定键；路径只是可变定位信息。注册表与每个 Workspace 的配置、数据库和运行状态全部位于用户级 `CAMPFIRE_HOME`，不得向目标 Workspace 创建工具状态目录。

解析优先级为显式 `--workspace`、当前目录所属的已注册 Workspace、默认 Workspace。写操作仍由具体业务模块执行。

`workspace add` 只接入已存在目录；`workspace create` 要求目标路径不存在，并创建全局收件箱、`mynote/`、`mywork/` 和治理视图基础目录。两者都初始化独立 SQLite Schema，不向 Workspace 写工具状态。
