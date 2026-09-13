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
                              campfire.db + config/
                              batches/reports/locks
```

Decision 以 SQLite 当前快照和追加事件为 SSOT。全部状态在 `_协作/decisions/` 生成只读 Markdown 投影，并由统一的决策工作台按 pending、answered、closed、cancelled 展示。Notification 与未来 Task Channel 只通过稳定 Decision id 和事件联动，不反向拥有 Decision 状态。

`app/` 按可独立理解的业务能力组织，CLI 只做参数和输出适配，Service 承担业务流程，Repository 负责外部读写。`common/` 只放跨业务复用、无独立业务流程的原子能力；不能为了“复用”把业务编排下沉到 common。

Document App 是所有面向用户和 Agent 的文档命令入口；Profile、类型命名、Frontmatter 和文档规则是其内部能力。Maintenance 只编排跨文档批量维护，Workspace 的 Restructure 用例只处理存量结构重构；两者调用 Document Service，不再从 `common/` 获取文档业务流程。

Frontmatter 规则采用声明式 Profile：`base` 是最小公共契约，`knowledge`、`project-doc`、`task` 只允许一层继承。Profile Loader 将配置编译为完整 EffectiveProfile，Resolver 根据文档类型和领域上下文选择 Profile，Validator 与 Formatter 共同消费该结果。字段规则不使用每种文档一个 Python 子类，也不在 Skill 中复制。

## 5. SSOT 与派生数据

| 数据 | 唯一事实来源 | 派生或运行副本 |
| --- | --- | --- |
| 正文、知识、项目、任务 | Workspace 中的 Markdown | SQLite 索引、MOC、Base、报告 |
| Space、Domain 结构 | Workspace 中的 `_空间.md`、`_领域.md` | CLI 发现结果、MOC |
| 治理规则 | `~/.campfire/workspaces/<id>/config/` | 校验结果与执行计划 |
| Workspace、Project 注册关系 | `~/.campfire/campfire.db` | JSON 导入导出备份 |
| Campfire Skills | Python 包内 `resources/skills/` | 全局 Agent Skill 目录 |
| 文档索引、结构重构和维护状态 | `~/.campfire/campfire.db`，按 `workspace_id` 隔离 | JSON 当前快照、有限变更日志 |

SQLite 中的 Workspace 与 Project 注册数据是结构化事实，文档索引可以从 Markdown 重建；SQLite 不是知识内容的 SSOT。工具状态不写入 Workspace，因而一个 Campfire 安装可以管理多个 Workspace。

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
  SQLite 索引与运行记录
  Decision 与事件
  Skills 安装路径、锁、缓存和报告
```

Project 的逻辑身份可以跨设备保持一致，但 `local_path` 是机器绑定：同一个 Project 在不同电脑上可以位于不同目录，也可以在某台电脑上尚未克隆。新设备通过稳定 Project id 和 `git_remote_url` 识别代码仓库，自动探测失败时由用户或 Agent 在本机显式绑定路径。

可移植元数据由 Vault 根目录唯一的 `.campfire.yaml` 承载并随 Git 或文件同步；不得提交 `campfire.db` 来共享状态。Manifest 使用稳定的 `workspace.id`，保存 Workspace 名称、治理版本，以及 Project 的 id、名称、文档领域、Git remote、默认分支和状态，明确禁止 `local_path`。现有 `_空间.md` 与 `_领域.md` 继续分别承载 Space 和 Domain 事实，避免在 Manifest 重复维护。Decision 当前保持本地，不属于该 Manifest。

新设备执行 `campfire setup --workspace <vault>`：读取 Manifest、注册本机路径、恢复 Project 逻辑元数据、同步类型/Profile/Skills/Bases 并执行健康检查。无法自动确定的项目源码路径显示为 `unbound_projects`，再用 `campfire workspace project bind` 完成本机绑定。整个流程可重复执行。

### 领域结构重构

Domain 的机器身份、显示名称和物理位置是三个独立维度：

```text
domain_id  稳定身份，普通重命名和移动不改变
name       人类可读名称，通过 domain rename 修改
path       Workspace 内物理位置，通过 domain move 或显式目录重命名修改
```

`domain rename`、`domain move` 和高风险的 `domain rekey` 是领域级事务，不应拆成大量逐文件迁移。路径变化必须联动 `_领域.md`、Project `document_domain`、`.campfire.yaml` 和路径引用；`rekey` 必须联动直接子领域的 `parent_domain`。所有命令默认预览，显式 `--confirm` 后执行。

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
6. Markdown 内容可脱离 Campfire 阅读和迁移；SQLite 丢失后可以重建。
7. 只有一个用户级 SQLite；所有 Workspace 业务表必须携带 `workspace_id`，Repository 查询不得越界。
8. 正式文档必须归入 Domain；Space 不直接替代 Domain，系统区域不伪装成 Space。

## 8. 演进方向

当前版本先稳定 Workspace 注册、存量结构重构、增量维护、归档、Skill 与治理视图。下一阶段围绕 Task Channel 补齐任务创建、进度事件、交接、待确认和验收协议，再连接工作日志、周报与绩效证据。只有出现真实用例时才新增模块，避免为未来能力预建空架构。
