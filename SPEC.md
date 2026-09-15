# Campfire SPEC

本项目是面向工作与学习场景的本地优先人机协作 CLI。产品目标与业务架构以 `ARCHITECTURE.md` 为准。

## 稳定边界

```text
CLI delivery adapter
        ↓
AppContainer 组合根，承担跨 App 编排
        ↓
Document / Workspace Restructure / Maintenance Service
        ↓
消费方 Protocol
        ↓
SQLite / Filesystem Implementation
```

- `app/` 放业务模块与 CLI 适配器。
- `common/` 放两个 App 共同使用的文档治理原子能力和技术机制。
- `config/` 放随 Workspace 或运行环境变化的配置。
- 跨 App 的用例编排放 `AppContainer` 组合根，`setup` 与 `upgrade` 是当前实例；CLI 不编排跨服务流程，单个 App Service 不直接调用其他 App 的 Service。
- 纯技术机制放 `common/`，例如网络查询、版本比较与进程编排；不得包含治理业务语义，也不得反向依赖 `app/`。
- `resources/defaults/config.yml` 是产品默认规则的唯一 SSOT；Service 不得重复声明可演进的目录、类型、状态、归档或 Issue 规则。
- CLI 通过用户级 registry 管理多个 Workspace，不依赖任何 Workspace 内的工具目录。
- Markdown 是内容事实来源；包内 `config.yml` 与可选的 `~/.campfire/config.yml` 覆盖共同形成有效治理契约；`~/.campfire/campfire.db` 是唯一数据库，保存 Workspace/Project 注册数据、按 Workspace 隔离的可重建索引和工作流状态。
- YAML 只承载人类可维护的配置和可移植 Manifest；JSON 只用于报告、计划交换和有限的最近变更。
- Workspace Restructure 与 Maintenance 不共享含义模糊的业务入口。
- CLI 不直接实现业务规则；Service 不依赖 Typer。
- 字段、枚举和跨字段不变量统一由 DocumentRuleService 解释；Maintenance 与 Workspace Restructure 不得复制规则值。
- Frontmatter Profile 只允许一层 `base` 配置继承；Profile Loader 编译完整规则，Validator 与 Formatter 共用同一个 EffectiveProfile。
- 公共接口不得依赖调用方猜测未声明契约。参数类型与复杂输入格式必须能从当前命令帮助获得；错误必须同时提供稳定机器字段和可操作的修复信息，但不得为此复制 Profile 枚举或新增平行命令。
- `tree` 只用于未知能力发现，不是 Agent 执行已知文档操作的固定前置步骤；Skill 必须把已知正文编辑、契约已知的 Frontmatter 写入和契约未知的 `inspect → apply` 分流清楚。
- 命令不得读取“最近一次操作”等隐式 Session 状态推导对象或作用域；跨命令后续动作只使用当前结果显式返回的结构化 `follow_up`。
- 所有写入默认预检，语义计划默认未审批。
- 写入用例必须在治理锁内复核生成计划时的内容哈希，发现外部变化时拒绝覆盖。

代码风格参考 `templates/fastapi-template`，但不引入 HTTP、WebSocket、认证和异步数据库等无关能力。

## CLI 输出契约

- 正常输出 indent JSON；错误输出单行 JSON 并写 stderr，退出码非 0。
- `status` 字段是 Agent 依赖的公共契约，只允许复用既有词汇，不得发明近义词。命令级词汇：ok、error、blocked、needs-input、needs-review、dry-run、synced、planned、ready、applied、issues-found、formatted、archived、up-to-date。文档、领域与 Decision 各有自己的字段词汇表。需要新状态先在本节登记。
- 可恢复的输入错误必须包含稳定 `code`、对应字段和机器可读的期望类型；当正确序列化方式不直观时，同时返回示例值或修复提示。自然语言 message 与示例可以演进，不作为调用方分支判断依据。
- 前置条件缺失时优先降级执行：能完成的部分照常完成，输出 `needs-input` 并以 `skipped` 字段显式列出被跳过的步骤，而非整体报错退出。

## 升级语义

- `campfire upgrade` 是唯一的幂等升级入口：先更新 Python 包本身，再对齐本机治理资源，覆盖 Schema 迁移、全局 Skill、Base 与提示词路标。
- 包自更新按检测到的安装方式在独立进程中执行，当前支持 uv tool 与 pipx。更新脚本必须等待当前进程退出后再运行，因为 Windows 会锁定运行中的解释器与可执行文件，包管理器无法原地替换；成功后由新版代码完成资源对齐。
- editable 源码安装、离线、无法识别安装方式时跳过包更新仅对齐资源，结果中以 `action` 与 `hint` 显式说明原因。
- 自更新链使用的内部参数必须 `hidden=True`，`--skip-package` 是当前实例，不进入公共 CLI 契约。
- 外部网络查询尽力而为，例如 PyPI 版本检测；失败或超时静默降级，不得让命令失败或明显变慢。

## 开发纪律

- 提交使用 conventional commits，类型限定为 feat、fix、perf、refactor、docs、chore，正文说明动机；纯重构独立成 commit，不与功能变更混排。
- 行为保持型重构的验收等于两条同时满足：既有测试不改断言仍通过，真实数据上新旧输出全等对比。只过测试不足以证明行为未变。
- Windows 不变量：进程探活用 `psutil.pid_exists`，不用 `os.kill(pid, 0)`，后者在 Windows 等价于发送 CTRL_C_EVENT；CLI 入口处对 stdout/stderr 执行 UTF-8 reconfigure。

## 注释与文档字符串

以 PEP 8 与 PEP 257 为基线，外加两条本项目的硬规则：

- 注释只写代码本身表达不了的约束：为什么这样做、什么条件下不能改。不写下一行做什么，不写给评审者看的改动说明，不重复代码；只对本次改动有意义的内容进提交说明，不进代码。
- Docstring 是 API 契约：摘要行一句话陈述行为，补充行写前置条件、返回语义与副作用，不描述实现步骤。
- 注释是完整句子，与代码同语言；行内注释只用于取值域等代码无法自明的信息。

## 版本规范

Campfire 使用语义化版本：

```text
主版本.次版本.补丁版本
0.17.0
│  │  └── patch：兼容的缺陷修复
│  └───── minor：兼容的新能力或治理契约变化
└──────── major：不兼容的公共接口或数据模型变化
```

- 已发布版本不可原地修改；同一版本号必须对应唯一、可重复构建的代码和资源。
- 只修复既有行为时增加补丁版本，例如 `0.17.0 -> 0.17.1`。
- 新增 CLI 能力、改变治理契约或增加可选公共字段时增加次版本，例如 `0.17.x -> 0.18.0`。
- 删除或重命名公共命令、改变不可兼容的数据格式时增加主版本；`0.x` 阶段仍应显式记录破坏性变化。
- 配置文件的 `version` 独立于 Python 包版本；只有配置结构或解释语义变化时递增。
- PyPI、源码标签、构建产物和 CLI 报告的版本必须一致。

## 设备边界

- 可跨设备共享的是 Workspace、Space、Domain 和 Project 的稳定身份与逻辑关联，不是本机文件路径。
- `git_remote_url`、Project id、文档 Domain 和治理契约版本属于可移植元数据。
- `local_path`、Skill 安装位置、锁、缓存、索引和运行报告属于设备本地状态，不得写入可移植元数据。
- Decision 及其事件当前属于创建它的本机工作流状态，不要求跨设备同步。
- 新设备接管已有 Workspace 时，从可移植元数据恢复逻辑关系，再在本机独立绑定项目路径并重建 SQLite 派生状态。
- Vault 根目录的 `.campfire.yaml` 是唯一可移植 Manifest；禁止在其他文件重复维护 Workspace/Project 便携元数据。
- `.campfire.yaml` 禁止保存 Vault 或代码仓库的本机绝对路径。
- `campfire setup` 必须幂等完成接入、契约/Skill/Base 同步和健康检查；未绑定项目必须显式报告，不得猜测路径。

## Domain 重构不变量

- `domain_id`、`name` 和 `path` 分别表示稳定身份、显示名称和物理位置，不得隐式绑定。
- 普通 rename 和 move 不得改变 `domain_id`；只有显式 `domain rekey` 可以修改稳定身份。
- 修改领域名称不得修改 Project 名称；Project 展示名称只能由 `workspace project update --name` 显式修改。
- 领域路径变化必须同步 Project `document_domain`、`.campfire.yaml` 和路径引用。
- `rekey` 必须同步直接子领域的 `parent_domain`。
- `move` 的目标必须使用 Space 或 Domain 稳定 id；`merge` 和 `delete` 不得退化为 Agent 手工移动、删除声明与清理索引。
- 已受管对象使用稳定 id，路径参数只用于新位置、具体文件、外部输入与扫描范围；不得同时要求可推导的 id、路径和父级关系。
- 领域级写入默认只预览，只有显式 `--confirm` 才执行。

## Workspace 索引

- SQLite `spaces`、`domains`、`documents` 只允许作为可重建本机投影，不得反向覆盖 Markdown SSOT。
- Document App 拥有文档记录、确定关系、集合查询和单篇关系查询；Repository 只持久化投影，不解释 Profile、Domain 或链接语义。
- 文档索引保存 schema version、parser version、有效配置 hash、拓扑 hash 和 generation；Domain 声明、Project 文档根映射等任一解释输入变化都必须自动完整重建。
- `document list` 与 `document inspect` 查询前必须轻量 reconcile。文件 stat 只筛选变化候选，content hash 表示内容版本；调用方不需要先运行 Maintenance。
- 候选文档与关系快照必须在一个 SQLite 事务中切换，失败继续保留上一完整 generation。
- `document list` 只做结构化精确筛选；`document inspect` 只返回显式关联和链接形成的确定关系。全文检索、模糊匹配、相关性排序和相似建议不得混入这两个契约。
- `setup` 与 `maintenance check` 必须自动刷新完整拓扑和文档索引。
- 索引 reconcile 是读取命令内部保障，不得作为 follow-up 暴露给 Agent。写命令只在实际写入成功且可见派生状态可能变化时返回零或一个可直接执行的 scoped `maintenance sync` follow-up；Domain 内部路径必须归一化为对应 Domain，预览和阻塞结果必须返回空列表；
  调用方只执行实际返回的 follow-up，不固定追加 check 或全量扫描。
- `workspace rebuild` 默认只预览；`--confirm` 后从 Manifest 和 Markdown 完整替换派生索引。

## Workspace 接管

- 外部来源必须只读，经临时隐藏目录复制和哈希校验后落到目标；不得删除或修改原目录。
- Vault 内来源原地盘点，不得重复复制。
- 软链接、目标冲突和源哈希变化必须 fail closed。
- 接管计划一次建立一个粗粒度 Domain；CLI 不得自行推断文档语义或子领域。
- `workspace domain adopt` 默认只预览，显式 `--confirm` 后在一个 ChangeSet 中移动或复制内容并创建领域声明。
- 提交成功前必须核对接管文件、哈希和领域声明；接管后的细分治理继续使用 Restructure。
