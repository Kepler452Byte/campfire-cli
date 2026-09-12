# Workspace App SPEC

本模块管理 Workspace、Project 注册表和 Workspace 初始化。Workspace id 与 Project id 是本机治理状态的稳定键；路径只是可变定位信息。用户级 `CAMPFIRE_HOME/campfire.db` 是唯一数据库，保存注册数据、文档索引和工作流状态；每个 Workspace 只保留配置与人类可审阅的运行产物，不再拥有独立数据库。所有工具状态均位于 `CAMPFIRE_HOME`，不得向目标 Workspace 创建工具状态目录。

解析优先级为显式 `--workspace`、当前目录所属的已注册 Workspace、默认 Workspace。写操作仍由具体业务模块执行。

`workspace add` 只接入已存在目录；`workspace create` 要求目标路径不存在，并创建全局收件箱、`mynote/`、`mywork/` 和治理视图基础目录。两者写入全局 SQLite 注册表，不向 Workspace 写工具状态。

Project 是 Workspace 连接的外部工作资源，记录稳定 id、显示名称、文档领域、本地代码路径、Git remote、默认分支和生命周期状态。Project 业务代码归属本模块，对外使用 `campfire workspace project` 子命令。提供本地 Git 路径时可自动发现 remote 和分支；动态 Git 状态不写入注册表。

`project resolve` 只按规范化后的本地 Git 根目录和 remote 识别已注册 Project，不凭目录名称猜测；零匹配和多匹配都返回可判断状态。`project check` 只报告源码路径、remote、默认分支和文档领域的漂移，不自动更新稳定身份或归属。

`project create` 用于新 Project onboarding，默认只返回计划，追加 `--confirm` 后才在同一治理锁内创建项目根 `_领域.md`、`_总览/MOC-<项目>总览.md` 并注册 Project。初始化不虚构业务子领域；已存在文档中心必须使用 `project add` 接入。

注册数据只通过 CLI 和 SQLite 维护。JSON 仅用于显式 export/import；import 默认只预检，必须使用 `--confirm` 才替换当前注册数据。不读取旧 JSON 注册表，不维护双事实源。
