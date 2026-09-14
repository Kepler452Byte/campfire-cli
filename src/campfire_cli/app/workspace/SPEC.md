# Workspace App SPEC

本模块管理 Workspace、Space、Domain、Project 注册表和 Workspace 初始化。Workspace id 与 Project id 是本机治理状态的稳定键；路径只是可变定位信息。用户级 `CAMPFIRE_HOME/campfire.db` 是唯一数据库，保存注册数据、文档索引和工作流状态；每个 Workspace 只保留配置与人类可审阅的运行产物，不再拥有独立数据库。所有工具状态均位于 `CAMPFIRE_HOME`，不得向目标 Workspace 创建工具状态目录。

解析优先级为显式 `--workspace`、当前目录所属的已注册 Workspace、默认 Workspace。写操作仍由具体业务模块执行。

`campfire setup --workspace <path>` 根据 Manifest 接入已有 Workspace；缺少 Manifest 时必须提供 `--id` 以创建首份 Manifest。`workspace create` 要求目标路径不存在，并创建全局收件箱、带 `_空间.md` 的知识/工作 Space 和治理视图基础目录。两者写入全局 SQLite 注册表，不向 Workspace 写工具状态。

`workspace space/domain create` 只创建不存在的新目录；对应的 `adopt` 原地纳管已有目录，只新增 `_空间.md`，或 `_领域.md` 和声明的 MOC，不移动、改名或删除已有内容。两者默认只输出计划，追加 `--confirm` 才写入。

`workspace config check` 统一校验包内产品默认值和当前 Workspace 的有效治理契约，包括目录与 Space 冲突、文档类型前缀、Profile 引用和继承、归档策略以及托管资源列表。

`workspace restructure` 负责一次性改变已有 Workspace 的批量文档或 Domain 物理结构：冻结范围、生成带内容哈希的审批计划、执行批量跨领域移动或改名、更新引用并验证迁移事实。单篇文档移动属于 `document move`。纯移动不得重写文档内容；`verify` 只验证本批次 source/target 结果，文档格式合规由 Maintenance 独立检查。该能力属于 Workspace Service，不设独立 App，也不用于日常增量维护。

Adoption、文档批量 Restructure 与 Domain Restructure 均使用共享 ChangeSet Executor 提交文件写入和路径移动，并在协调的 Repository 写入失败时补偿恢复。Workspace Service 不调用 Maintenance Service；成功结果以轻量 `follow_up` 返回 scoped `maintenance sync/check`。

Space 是 Workspace 根下以 `_空间.md` 声明的顶级内容容器；Domain 位于 Space 内，以 `_领域.md` 声明并可任意嵌套。子 Domain 必须处于父 Domain 路径下、属于同一 Space 并继承 governance。`_收件箱` 与 `治理视图` 是系统区域，不是 Space。Maintenance 只消费本模块发现的结构，不维护第二套领域规则。

Space 与 Domain 声明文件只由本模块解释和校验；Document App 对其返回 `not-applicable`。`workspace space check --space <id>` 支持对单个 Space 做局部复检。

Project 是 Workspace 连接的外部工作资源，记录稳定 id、显示名称、文档领域、本地代码路径、Git remote、默认分支和生命周期状态。Project 业务代码归属本模块，对外使用 `campfire workspace project` 子命令。提供本地 Git 路径时可自动发现 remote 和分支；动态 Git 状态不写入注册表。

`project resolve` 只按规范化后的本地 Git 根目录和 remote 识别已注册 Project，不凭目录名称猜测；零匹配和多匹配都返回可判断状态。`project check` 只报告源码路径、remote、默认分支和文档领域的漂移，不自动更新稳定身份或归属。

`project create` 用于新 Project onboarding，默认只返回计划，追加 `--confirm` 后通过 Domain Service 创建工作 Space 内的项目根 Domain 并注册 Project。初始化不虚构业务子领域；已存在文档中心使用 `project adopt` 接入。

注册数据只通过 CLI 和 SQLite 维护。JSON 仅用于显式 export/import；import 默认只预检，必须使用 `--confirm` 才替换当前注册数据。不读取旧 JSON 注册表，不维护双事实源。
