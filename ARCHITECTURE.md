# Campfire Architecture

本文固化 Campfire 的产品目标、业务模型、架构边界与长期不变量。实现细节可以演进，但不能在未记录决策的情况下偏离本文。

## 1. 产品定位

Campfire 是一个面向工作与学习场景的、本地优先的人机协作 CLI。它让人类和多个 Agent 围绕同一份可持续积累的上下文协作，并把口头要求、临时笔记、任务进度、项目资料和长期知识沉淀为可检索、可交接、可审计的工作空间。

Campfire 不把聊天记录当作长期事实来源，也不绑定 Obsidian、某一种 Agent 或某一个 Workspace。Obsidian Vault 是当前首个 Markdown 存储适配器，而不是产品边界。

Campfire 当前不负责 Agent 调度、实时消息推送或替代 Jira/Notion；它提供这些系统和不同 Agent 会话都可以共同读写的持久协作协议。

## 2. 核心业务对象

- **Workspace**：人和 Agent 共享的上下文边界；一个 Workspace 可对应一个 Markdown Vault。
- **Space**：Workspace 下的顶级内容容器，例如知识、工作；由 `_空间.md` 声明。
- **Domain**：Space 内可任意嵌套的内容边界；由 `_领域.md` 声明并拥有自动 MOC。
- **Project**：Workspace 连接的外部工作资源，关联代码仓库、本地路径和一个项目根 Domain。
- **Participant**：参与协作的人类或 Agent。
- **Document**：知识、项目、决策、计划、问题、记录等持久内容。
- **Task Channel**：围绕一项任务持续记录负责人、状态、进展、阻塞、交接、结果和验收的异步协作通道。
- **Inbox Item**：尚未完成归属、类型或意图判断的输入，以及需要人类确认的问题。
- **Decision**：人类或高级 Agent 必须回答的持久判断；以当前状态和追加事件跨会话传递。
- **Generated View**：由事实数据生成的 MOC、Base、报告和索引，不由人手重复维护。

## 3. 业务架构

```text
工作与学习场景
  收件箱 ──> Space ──> Domain 树 ──> 文档
     │                    │
     └──── 待人确认 <─────┘

人机协作协议
  提出意图 -> 分派 -> 认领 -> 执行 -> 阻塞/待确认 -> 提交结果 -> 验收 -> 完成
                         │                         │
                         └──────── 交接 ──────────┘

治理能力
  Schema + 命名 + 生命周期 + 计划/审批/执行 + 链接 + 归档 + 审计
```

Task Channel 借鉴 Go 的原则：**Do not communicate by sharing memory; instead, share memory by communicating.** 多个参与者不依赖各自会话中的隐式记忆，而是通过明确的任务状态与事件共享上下文。它是持久异步 Channel，不承诺实时唤醒；外部 Agent 运行时可在其上增加通知和调度。

## 4. 系统架构

```text
人类 / Codex / Claude Code / 其他 Agent
                  │
          全局 Skill + campfire CLI
                  │
        ┌─────────┴─────────┐
        │ Application Apps  │
        │ workspace         │
        │  space / domain   │
        │  restructure      │
        │ document          │
        │ maintenance       │
        │ skill / base      │
        └─────────┬─────────┘
                  │
        Common 治理与原子能力
      schema / documents / links /
      filesystem / database / reports
                  │
      ┌───────────┴───────────┐
Markdown Workspace Adapter   用户级状态
 文档事实、任务、知识、项目    ~/.campfire/
                              campfire.db + config.yml
                              batches/reports/locks
```

Decision 以 SQLite 当前快照和追加事件为 SSOT。全部状态在 `_协作/decisions/` 生成只读 Markdown 投影，并由统一的决策工作台按 pending、answered、closed、cancelled 展示。Notification 与未来 Task Channel 只通过稳定 Decision id 和事件联动，不反向拥有 Decision 状态。

`app/` 按可独立理解的业务能力组织，CLI 只做参数和输出适配，Service 承担业务流程，Repository 负责外部读写。跨 App 的用例编排由组合根 `AppContainer` 承担，`setup` 与 `upgrade` 是当前实例。`common/` 只放跨业务复用、无独立业务流程的原子能力；不能为了“复用”把业务编排下沉到 common。

配置采用两层模型：包内 `resources/defaults/config.yml` 保存完整默认契约，用户级 `~/.campfire/config.yml` 只保存覆盖项。Mapping 递归合并，scalar 和 list 整体替换；配置不按 Workspace 复制，运行状态不写回 YAML。

Document App 是所有面向用户和 Agent 的文档命令入口；Profile、类型命名、Frontmatter 和文档规则是其内部能力。Maintenance 只编排跨文档批量维护，Workspace 的 Restructure 用例只处理存量结构重构；两者调用 Document Service，不再从 `common/` 获取文档业务流程。

Document App 同时拥有设备本地的文档查询投影。Indexer 从 Markdown、Domain 声明、Project 文档根映射和显式链接生成文档记录与确定关系；Repository 只负责按 `workspace_id` 持久化完整快照。组合根从 Workspace Registry 提供当前 Project 映射，Document App 不直接读取 Workspace Repository，也不把每篇文档中可能漂移的重复字段当作物理归属。`document list` 和 `document inspect` 查询前自行轻量 reconcile，不要求 Agent 先运行 Maintenance。Maintenance 只在全量检查或可见生成物同步时触发索引校正，不拥有索引规则，也不是读取命令的前置步骤。

Frontmatter 规则采用声明式 Profile：`base` 是最小公共契约，`knowledge`、`project-doc`、`task` 只允许一层继承。Profile Loader 将配置编译为完整 EffectiveProfile，Resolver 根据文档类型和领域上下文选择 Profile，Validator 与 Formatter 共同消费该结果。字段规则不使用每种文档一个 Python 子类，也不在 Skill 中复制。

`template` 直接使用 base Profile，物理存放在 Domain 的 `_模板/`。模板作用域由 Domain 拓扑和路径确定；Skill 从目标 Domain 向祖先查找同名模板并使用最近的一份，系统不建立模板注册表或继承状态。

### CLI 设计理念：治理原语 + Skill SOP

Campfire 不是“Markdown 版 kubectl”，而是面向人机协作场景组合成熟 CLI 经验形成的独立设计。它在资源心智模型、`apply` 语义和机器可读接口上借鉴 kubectl，在“计划—审查—执行”上借鉴 Terraform，在稳定原语与上层工作流分离上借鉴 Git/Unix；Markdown SSOT、Agent 语义判断和显式 Maintenance 则是 Campfire 自身边界。

| 参考 | Campfire 采用的部分 | Campfire 不照搬的部分 |
| --- | --- | --- |
| [kubectl 命令与资源模型](https://kubernetes.io/docs/reference/kubectl/) | 按对象域组织命令、用 `apply` 统一创建与更新、显式选择作用域、提供稳定机器输出 | 不复制 `kubectl <verb> <type> <name>` 语法，不引入 API Server、Controller 或持续调谐 |
| [kubectl 声明式 apply](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/declarative-config/) | 目标不存在时创建、存在时更新；把“期望变更”交给工具校验和执行 | 不保存 `last-applied-configuration`，不实现三方合并或字段所有权；Campfire apply 是 Profile 约束下的显式补丁 |
| [Terraform plan/apply](https://developer.hashicorp.com/terraform/cli/commands/plan) | 写入前预览，可审查计划后再执行，执行前重新确认输入未漂移 | 不把所有日常写入都升级为持久计划；单文档原子修改保持轻量 |
| [Git plumbing/porcelain](https://git-scm.com/book/en/v2/Git-Internals-Plumbing-and-Porcelain) | CLI 提供可组合、可脚本化的稳定原语，Skill 组合成人类可理解的 SOP | 不暴露仅供内部实现使用的隐藏命令，不要求用户理解底层存储 |

本文中的“原子命令”特指**意图原子命令**，不是把实现拆成最小文件操作或最小函数。一个公共命令需同时满足三层原子性：

| 层次 | 规范 | 例子 |
| --- | --- | --- |
| 语义原子性 | 一条命令只表达一个可以用一句话说清的用户意图 | `document move` 表达“在已声明 Domain 之间正确移动一篇文档” |
| 一致性原子性 | 为保持该意图不变量而必须一起变更的事实，属于同一个变更集；整体成功或恢复到执行前 | 移动文档时同步修复可确定解析的引用 |
| 可组合原子性 | 不相关的派生治理不隐式执行；只有实际写入成功的结果用结构化 `follow_up` 声明必要步骤，由 Skill 决定组合顺序 | `document apply` 预览时 `follow_up` 为空，写入后只在必要时返回一个 scoped `maintenance sync` |

命令副作用按下列边界分类：

- **必须纳入当前事务**：不执行就会让当前意图产生破损状态的变更，例如结构迁移时的 Domain 声明、Project 归属和可移植 Manifest 对齐。
- **必须显式返回**：可从原始事实重建的派生结果，例如 MOC、关系页、索引和治理报告；这些作为 `follow_up` 由 Skill 显式执行。
- **禁止捎带**：与当前意图无关的全 Workspace 格式化、归档、结构重构或其他写操作。

“一次改多个文件”不等于不原子；“一次只改一个字段”也不自动等于边界正确。评审新命令时必须逐项回答：

1. 用户意图能否用一句话准确表达？
2. 对象和作用域是否显式？
3. 所有被修改的事实是否都是维持该意图不变量所必需？
4. 预览和 JSON 输出能否完整说明变更、阻断和后续操作？
5. 重复执行是否幂等，或至少以稳定结果明确拒绝？
6. 预览后的并发变更是否会被锁与快照复核阻断？
7. 可重建的派生工作是否作为可组合 `follow_up` 返回？

命令设计遵循以下约束：

1. **对象域优先**：公共入口采用 `campfire <object-domain> <verb>`，例如 `document apply`、`maintenance check`；动词在所属业务对象内保持单义，不为同一行为保留多个别名。
2. **意图原子、派生显式**：`document apply` 创建或更新文档，并在显式类型变化时将类型、文件名前缀和确定性引用作为同一变更提交；`document move` 原子完成单文档跨 Domain 移动、目标 Profile 对齐和确定性引用修复。命令只在 MOC、关系页或索引可能变化时返回零或一个可直接执行的最小 scope `maintenance sync`。
3. **契约声明式，变更显式**：Profile 是字段、类型、枚举、顺序和条件必填的 SSOT。Agent 提交业务值，CLI 解析有效 Profile 并拒绝猜测；已有文档只修改明确给出的字段或正文操作。
4. **写入先证明安全**：写命令默认预览，显式确认后才提交；提交时在锁内复核快照或期望哈希，多文件变更作为一个 ChangeSet 执行，失败回滚，避免静默覆盖和部分写入。
5. **人类与 Agent 共用一个契约**：命令和结果只有一套语义。JSON 状态、issues、missing fields 与 follow-up 供 Agent 稳定消费，`tree` 和分层 `-h` 供人类与 Agent 渐进发现，不维护第二套参数目录。
6. **语义与机制分层**：人类决定高风险取舍，Agent 理解正文和业务语义，Skill 规定加载时机、事实门禁与 SOP，CLI 只执行可确定验证的治理机制。歧义进入 Decision，不为“自动化成功”而猜测。
7. **聚合入口是少数例外**：`setup` 和 `upgrade` 可以编排多个服务，因为它们表达完整安装生命周期；日常内容治理保持原子能力，避免重新出现 `maintenance run` 一类不可审查的聚合入口。
8. **参数最小充分、黄金路径唯一**：调用方只提交 CLI 无法可靠推导的事实。已受管的 Workspace、Space、Domain 和 Project 优先使用稳定 id，路径只用于外部输入、未接管来源、显式物理位置或尚无稳定 id 的文档；同一事实不得同时要求 id、完整路径和父级关系。一个常规意图只保留一个公共入口，不用互斥模式参数、兼容别名或要求 Agent 手工拼装底层步骤来表达同一行为。

### Agent 可执行契约

Campfire 不把“调用方能够猜对未声明契约”作为可靠性前提。Agent 可能不会自行推断字段枚举、补丁值类型、Shell 引号、隐含前置步骤或上一次命令留下的状态；公共接口必须用已有入口提供足以完成当前意图的信息。

- 参数帮助说明参数语义和输入格式；列表、结构化补丁等不直观输入至少给出一个可直接使用的例子。
- 校验失败同时服务机器恢复和人工诊断：稳定错误码、字段与期望类型供程序判断，简短的实际值、示例或修复提示帮助调用方完成下一次正确调用。调用方不得被迫解析易变的自然语言 message。
- Profile 仍是字段类型、枚举和跨字段规则的唯一事实源。`tree` 只发现能力，Skill 只选择路径，帮助和错误只呈现当前调用所需信息；三者不得复制整套 Profile 或建立平行参数目录。
- 已知路径的正文小改直接使用文件工具；Frontmatter 契约已知时直接 `document apply`；现有文档的字段类型或合法值未知时使用一次 `document inspect` 后 apply。`tree` 只在不知道 Campfire 是否具有对应能力时使用，不是文档操作的固定前置步骤。
- CLI 不使用“最近一次 apply”之类的隐式可变状态补偿 Agent 能力。跨命令动作由当前结果中的结构化 `follow_up` 显式描述，输入、对象和作用域在每次调用中均可审查。

这里的“自解释”不是把所有教程塞进一个命令，也不是保证任何 Agent 零读取完成任意任务；它表示完成常规意图所需的契约有唯一来源、最短获取路径和可操作的失败反馈。只有出现新的独立用户意图时才增加命令，单纯的帮助或诊断不足不构成扩张命令面的理由。

横切关注点与业务 SOP 不使用同一种复用手段。哈希复核、写锁、原子替换和失败恢复由显式 ChangeSet Executor 复用；写命令返回的 `follow_up` 由 Skill 消费。不为了复用 Maintenance 而引入 AOP 切面、命令总线、全局钩子或隐式中间件。

因此，`document apply` 的准确含义是“对一个 Markdown 文档应用经 Profile 校验的显式意图”，不是“把完整声明持续调谐到某个服务端状态”。创建时文件名可省略类型前缀；显式变更类型时，CLI 负责同步类型、前缀和可确定引用。用户或 Agent 可以直接 edit 唯一路径下的已有正文；只有新建文档、修改 Frontmatter/类型/归属或需要派生治理时才进入 CLI 工作流。

## 5. SSOT 与派生数据

| 数据 | 唯一事实来源 | 派生或运行副本 |
| --- | --- | --- |
| 正文、知识、项目、任务 | Workspace 中的 Markdown | SQLite 索引、MOC、Base、报告 |
| Space、Domain 结构 | Workspace 中的 `_空间.md`、`_领域.md` | CLI 发现结果、MOC |
| 治理规则 | 包内 `config.yml` + `~/.campfire/config.yml` 覆盖 | 校验结果与执行计划 |
| Workspace、Project 可移植身份与 Project 根 Domain 绑定 | Vault 根 `.campfire.yaml` | Git 或文件同步 |
| Workspace、Project 本机路径绑定 | `~/.campfire/campfire.db` | 本机 CLI 命令 |
| Campfire Skills | Python 包内 `resources/skills/` | 全局 Agent Skill 目录 |
| 文档查询索引 | Workspace Markdown、结构声明与有效治理契约 | `~/.campfire/campfire.db` 中按 `workspace_id` 隔离的可重建投影 |
| Decision、结构重构批次和维护运行状态 | `~/.campfire/campfire.db` | Markdown 投影、报告与有限变更日志；当前不能仅从 Workspace 重建 |

SQLite 中的 Workspace 与 Project 注册数据是结构化事实，文档索引可以从 Markdown 重建；SQLite 不是知识内容的 SSOT。工具状态不写入 Workspace，因而一个 Campfire 安装可以管理多个 Workspace。

### 文档查询投影

文档索引保存列表查询需要的结构化字段、内容哈希、源文件 stat，以及显式 Frontmatter 关联、WikiLink、Markdown Link、Embed 形成的确定关系。它不复制正文，不保存相似度建议，也不把文件 mtime 解释为任务时间。

每次 `document list` 或 `document inspect` 先对账文件清单、size、mtime、有效配置哈希和 Space/Domain 拓扑哈希。stat 只用于筛选变化候选，内容哈希才表示内容版本；新增、修改和删除会在查询前自动 reconcile。候选快照在内存中完成后，通过单个 SQLite 事务替换文档、关系和 generation，中断不能暴露半套新索引。

`document list` 只做结构化精确枚举与 AND 筛选；未来正文关键词、模糊匹配、相关性排序或混合检索使用独立 `document search`。`document inspect.relations` 只返回可证明的 declared、outgoing、incoming 和 unresolved；相似文档属于未来独立 suggestions，不能混入确定关系。

索引新鲜度是 CLI 内部读取保障，不生成让 Agent 手工执行的 index follow-up。MOC、关系页等 Workspace 内可见生成物仍由成功写命令按需返回 scoped `maintenance sync`。

### 设备本地与跨设备边界

```text
随 Workspace 同步
  稳定 Workspace 身份
  Space / Domain 声明
  Project id / 名称 / 文档 Domain / Git remote
  治理契约版本
                │
                ▼ 新设备 attach
每台设备独立维护
  Project local_path
  SQLite 查询投影与运行记录
  Decision 与事件
  Skills 安装路径、锁、缓存和报告
```

Project 的逻辑身份可以跨设备保持一致，但 `local_path` 是机器绑定：同一个 Project 在不同电脑上可以位于不同目录，也可以在某台电脑上尚未克隆。新设备通过稳定 Project id 和 `git_remote_url` 识别代码仓库，自动探测失败时由用户或 Agent 在本机显式绑定路径。

可移植元数据由 Vault 根目录唯一的 `.campfire.yaml` 承载并随 Git 或文件同步；不得提交 `campfire.db` 来共享状态。Manifest 使用稳定的 `workspace.id`，保存 Workspace 名称、治理版本，以及 Project 的 id、名称、根 `document_domain_id`、Git remote、默认分支和状态，明确禁止 `local_path`。`projects[].document_domain_id` 是 Project–Domain 绑定的唯一事实；`_领域.md` 不保存 Project 字段。现有 `_空间.md` 与 `_领域.md` 分别承载 Space 和 Domain 自身事实。Decision 当前保持本地，不属于该 Manifest。

Space/Domain 声明采用区域所有权：Frontmatter 由 Workspace App 管理，成对 `AUTO-GENERATED` 标记内由生成器管理，标记外 Markdown 正文由人和 Agent 自由维护。声明 formatter 只能重排 Frontmatter，必须逐字节保留正文；生成器遇到重复、嵌套或未闭合标记时停止，不猜测覆盖范围。

新设备执行 `campfire setup --path <vault>`：读取 Manifest、注册本机路径、恢复 Project 逻辑元数据、同步类型/Profile/Skills/Bases 并执行健康检查。已注册 Workspace 只通过根级 `campfire --workspace <id> ...` 显式选择。无法自动确定的项目源码路径显示为 `unbound_projects`，再用 `campfire workspace project bind` 完成本机绑定。整个流程可重复执行。

### 领域结构重构

Domain 的机器身份、显示名称和物理位置是三个独立维度：

```text
domain_id  稳定身份，普通重命名和移动不改变
name       人类可读名称，通过 domain rename 修改
path       Workspace 内物理位置，通过 domain move 修改
```

`domain rename`、`domain move`、`domain merge`、`domain delete` 和高风险的 `domain rekey` 是领域级意图原子事务，不应拆成大量逐文件迁移。Project 通过 `.campfire.yaml` 中的稳定根 Domain id 单向绑定领域；普通路径变化不修改 Project 元数据，`merge` 或 `rekey` 改变稳定 id 时才在同一事务更新绑定。`rekey` 必须联动直接子领域的 `parent_domain`。`merge` 把源 Domain 的受管内容迁入目标 Domain，并在不变量满足时移除源 Domain；`delete` 只删除没有内容、附件、子 Domain 或 Project 绑定的逻辑空 Domain。它们不是跨业务聚合入口，内部必须复用同一 ChangeSet、快照复核和失败恢复边界。所有命令默认预览，显式 `--confirm` 后执行。

SQLite 中的 `spaces`、`domains` 与 `documents` 是本机查询投影，不是新的事实源。`setup`、`maintenance check` 和领域重构会自动从 `.campfire.yaml`、`_空间.md`、`_领域.md` 与内容文档刷新这些表；`workspace rebuild --confirm` 只提供低频的完整恢复入口。

### 存量文件夹接管

Adoption 是首次接管边界，不属于日常 Maintenance。`workspace domain adopt` 一次完成只读盘点、预览和确认后的原子接管，不持久化中间批次。外部目录通过临时隐藏目录复制并校验，原来源保持不变；Vault 内目录原地声明或移动到目标。CLI 负责哈希、软链接与冲突保护、声明、初始 MOC 和 Project/Manifest 联动；Agent 负责阅读正文、选择目标 Space/Domain，并执行返回的 `follow_up`。

## 6. 本地 Web 工作台

Campfire 可以提供由 CLI 启动的单进程本地 HTTP 服务和浏览器工作台。CLI 与 HTTP 是同级交付适配器，必须复用同一个 Application Service、Repository、事务和审计逻辑；前端不得直接访问 SQLite，也不得复制 Decision 状态机。

```text
Agent / Terminal ──> CLI Adapter  ──┐
                                    ├── Application Service ──> Repository
Human / Browser  ──> HTTP Adapter ──┘                           │
                                                                ├── SQLite
                                                                └── Vault
```

第一期 Web UI 只处理 Decision：查看 pending、answered、closed、cancelled，阅读问题、证据、建议、关联文档与来源 Session，并执行 answer 或 cancel。用户回答后仍由原 Agent 消费答案并调用 close。Obsidian Base 继续作为只读快速视图，不承担状态写入。

本地服务默认只监听 `127.0.0.1`，不内置账号、云同步、远程调度或多服务器部署。前端源码独立构建，静态产物随 Python wheel 发布；最终用户不需要 Node.js。

## 7. 稳定不变量

1. 人类和 Agent 使用同一套 CLI 契约，不维护两套规则。
2. 写操作默认先计划、再确认、再执行；执行前复核并发变更。
3. 规则集中在配置契约和规则引擎，Skill、模板、CLI 不复制枚举定义。
4. MOC、Base、关系和报告能生成就不手工维护。
5. 有歧义的分类和结构重构进入待确认，不由 Agent 擅自决定。
6. Markdown 内容可脱离 Campfire 阅读和迁移；文档查询投影在 SQLite 丢失后可以重建，Decision 与未完成批次等工作流状态不作此承诺。
7. 只有一个用户级 SQLite；所有 Workspace 业务表必须携带 `workspace_id`，Repository 查询不得越界。
8. 正式文档必须归入 Domain；Space 不直接替代 Domain，系统区域不伪装成 Space。

## 8. 演进方向

当前版本先稳定 Workspace 注册、存量结构重构、增量维护、归档、Skill 与治理视图。下一阶段围绕 Task Channel 补齐任务创建、进度事件、交接、待确认和验收协议，再连接工作日志、周报与绩效证据。只有出现真实用例时才新增模块，避免为未来能力预建空架构。
