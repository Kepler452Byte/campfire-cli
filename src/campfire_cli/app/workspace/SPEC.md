# Workspace App SPEC

本模块管理 Workspace、Space、Domain、Project 注册表和 Workspace 初始化。`.campfire.yaml` 保存可移植的 Workspace、Project 身份和 Project 到根 Domain 的稳定绑定；`CAMPFIRE_HOME/campfire.db` 保存本机路径及其查询投影，不得反向覆盖 Manifest。路径只是可变定位信息。每个 Workspace 只保留配置与人类可审阅的运行产物，不拥有独立数据库。所有工具状态均位于 `CAMPFIRE_HOME`，不得向目标 Workspace 创建工具状态目录。

解析优先级为根级显式 `--workspace <id>`、当前目录所属的已注册 Workspace、默认 Workspace。显式值只接受稳定 Workspace id，不接受路径；叶命令不得重复暴露 Workspace 选择器。写操作仍由具体业务模块执行。

`campfire setup --path <path>` 根据 Manifest 接入已有 Workspace；缺少 Manifest 时必须提供 `--id` 以创建首份 Manifest。`workspace create` 要求目标路径不存在，并创建全局收件箱、带 `_空间.md` 的知识/工作 Space 和治理视图基础目录。两者写入全局 SQLite 注册表，不向 Workspace 写工具状态。

`workspace space/domain create` 只创建不存在的新目录；`space adopt` 原地纳管已有 Space，`domain adopt` 可原地声明或把一个 Vault 内外已有目录接管到明确目标。Domain 所属 Space 和最近父 Domain 从目标路径唯一推导；Project 从 Manifest 绑定的根 Domain id 与祖先拓扑推导，Domain 声明不保存 Project。外部来源始终保留。命令默认只输出计划，追加 `--confirm` 才写入。

`workspace config check` 统一校验包内产品默认值和当前 Workspace 的有效治理契约，包括目录与 Space 冲突、文档类型前缀、Profile 引用和继承、归档策略以及托管资源列表。

`workspace restructure` 负责原子命令无法表达的批量文档映射、领域拆分和 Frontmatter Patch：冻结范围、生成带内容哈希的审批计划、更新引用并验证迁移事实。Domain 的 rename/move/merge/delete/rekey 直接位于 `workspace domain`；move 使用目标 Space/Domain id 推导路径，merge 一次完成内容迁移和源领域移除，delete 只删除逻辑空领域。单篇文档移动属于 `document move`，以目标 Domain id 代替目标路径。无 `--spec` 时只推断可确定的文档类型与文件名前缀规范化；没有变化返回 `up-to-date`，任意路径映射或 Frontmatter Patch 必须使用已文档化的 spec。纯移动不得重写文档内容；`verify` 只验证本批次 source/target 结果。该能力属于 Workspace Service，不设独立 App，也不用于日常增量维护。

Adoption、文档批量 Restructure 与 Domain Restructure 均使用共享 ChangeSet Executor 提交文件写入和路径移动，并在协调的 Repository 写入失败时补偿恢复。Workspace Service 不调用 Maintenance Service；实际写入成功的结果只在必要时以轻量 `follow_up` 返回零或一个可直接执行的 scoped `maintenance sync`，预览和阻塞结果不返回可执行后续。

Space 是 Workspace 根下以 `_空间.md` 声明的顶级内容容器；Domain 位于 Space 内，以 `_领域.md` 声明并可任意嵌套。子 Domain 必须处于父 Domain 路径下、属于同一 Space 并继承 governance。`_收件箱` 与 `治理视图` 是系统区域，不是 Space。Maintenance 只消费本模块发现的结构，不维护第二套领域规则。

Space 与 Domain 声明 Frontmatter 只由本模块解释、格式化和修改；Document App 对其返回 `not-applicable`。`workspace space/domain format` 只规范化 Frontmatter 并逐字节保留 Markdown 正文。声明文件中 `AUTO-GENERATED` 标记区域由 CLI 独占，标记外正文允许人和 Agent 编辑。`workspace space check --space <id>` 支持对单个 Space 做局部复检。

Project 是 Workspace 连接的外部工作资源，记录稳定 id、显示名称、文档领域、本地代码路径、Git remote、默认分支和生命周期状态。Project 业务代码归属本模块，对外使用 `campfire workspace project` 子命令。提供本地 Git 路径时可自动发现 remote 和分支；动态 Git 状态不写入注册表。

`project resolve` 只按规范化后的本地 Git 根目录和 remote 识别已注册 Project，不凭目录名称猜测；零匹配和多匹配都返回可判断状态。`project check` 只报告源码路径、remote、默认分支和文档领域的漂移，不自动更新稳定身份或归属。

`project create --path` 用于新 Project onboarding，默认只返回计划，追加 `--confirm` 后通过 Domain Service 创建工作 Space 内的项目根 Domain 并注册 Project。初始化不虚构业务子领域；已存在文档中心使用 `project adopt --domain <id>` 接入，更新只提交显式给出的字段。

注册数据只通过 CLI 和 SQLite 维护。JSON 仅用于显式 export/import；import 默认只预检，必须使用 `--confirm` 才替换当前注册数据。不读取旧 JSON 注册表，不维护双事实源。
