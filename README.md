# Campfire

`campfire` 是面向工作与学习场景的本地优先人机协作 CLI。它让人类和多个 Agent 围绕持久共享上下文协作，并把一次性 Workspace 结构重构与后续增量维护分开。

产品目标、业务对象、SSOT 与模块边界见 [ARCHITECTURE.md](ARCHITECTURE.md)。Markdown/Obsidian Vault 是当前首个存储适配器，Workspace 才是面向用户的顶层概念。

```bash
uv sync
uv run campfire --help
uv run campfire setup --workspace /path/to/vault --default
uv run campfire workspace list
uv run campfire --workspace personal maintenance check
```

Vault 根目录的 `.campfire.yaml` 是可跨设备同步的 Workspace/Project 元数据事实源；它不保存任何设备绝对路径。CLI 通过本机唯一的 `~/.campfire/campfire.db` 管理路径绑定、Decision、文档索引和运行状态。各 Workspace 的配置、批次和报告保存在 `~/.campfire/workspaces/<id>/`，不会向 Workspace 写入工具状态目录。可用 `CAMPFIRE_HOME` 覆盖用户级根目录。

## 安装与调用

标准安装（已发布至 PyPI，无需源码仓库）：

```bash
uv tool install campfire-cli
campfire version
```

升级使用 `uv tool upgrade campfire-cli`（或 `pipx upgrade campfire-cli`）。

开发机安装（跟随本地源码）：

```bash
uv tool install --editable /path/to/campfire-cli
campfire version
```

安装全局 Agent Skill（同步到 `~/.claude/skills` 与 `~/.agents/skills`）：

```bash
campfire skill list   # 查看包内 SSOT Skill 与全局同步状态
campfire skill sync   # 确定性同步托管 Skill 到全局目录
```

`skill` 命令不依赖已注册 Workspace，可在 `setup` 之前使用；`campfire setup` 初始化
Workspace 时也会自动执行一次同步。可用 `CAMPFIRE_SKILL_TARGETS`（路径分隔符分隔的
列表）覆盖同步目标。

人类和 Agent 使用同一条链路：全局 Skill 先调用 `campfire workspace resolve`，再读取目标 Workspace 的 `AGENTS.md`，并使用 Workspace id 调用 `campfire`。不修改原始笔记的检查可以直接执行（会刷新 SQLite 当前状态和 current 报告）；`campfire workspace restructure apply`、
`maintenance apply` 和 `maintenance archive apply` 必须先审查计划，并使用命令要求的显式确认参数。

```bash
campfire workspace add --id personal --path /path/to/vault --default
campfire workspace create --id new-vault --path /new/path --default
campfire setup --workspace /path/to/existing-vault --default
campfire workspace attach --path /path/to/existing-vault --default
campfire workspace project bind --id example --local-path /path/to/repository
campfire workspace space list --workspace personal
campfire workspace domain list --workspace personal
campfire workspace domain check --workspace personal
campfire workspace space create --id research --name "研究" --path myresearch --type research
campfire workspace space create --id research --name "研究" --path myresearch --type research --confirm
campfire workspace space adopt --id research --name "研究" --path myresearch --type research
campfire workspace config check --workspace personal
campfire workspace domain create --id distributed-systems --name "分布式系统" --path "knowledge/分布式系统" --space knowledge --type knowledge-domain --governance knowledge-docs
campfire workspace domain create --id distributed-systems --name "分布式系统" --path "knowledge/分布式系统" --space knowledge --type knowledge-domain --governance knowledge-docs --confirm
campfire workspace domain adopt --id meetings --name "会议记录" --path "mywork/会议记录" --space work --type work-domain --governance work-docs
campfire workspace domain adopt --id meetings --name "会议记录" --path "mywork/会议记录" --space work --type work-domain --governance work-docs --confirm
campfire workspace project add --id example --workspace personal --name "Example" --document-domain "work/example" --local-path /path/to/repository
campfire workspace project list --workspace personal
campfire --workspace personal document profile list
campfire --workspace personal document profile show task
campfire --workspace personal document profile resolve --path "work/example/任务-示例.md"
campfire --workspace personal document type list
campfire --workspace personal document check --path "knowledge/example/知识-示例.md"
campfire --workspace personal document format --path "knowledge/example/知识-示例.md"
campfire --workspace personal document format --path "knowledge/example/知识-示例.md" --confirm
campfire --workspace personal decision create --key example-decision --question "需要确认什么？" --source-type agent
campfire --workspace personal decision list --status pending
campfire --workspace personal decision show <decision-id>
campfire --workspace personal decision answer <decision-id> --answer "确认内容" --answered-by user
campfire --workspace personal decision close <decision-id>
campfire workspace export --output campfire-registry-backup.json
campfire workspace import --input campfire-registry-backup.json
campfire workspace import --input campfire-registry-backup.json --confirm
campfire workspace resolve
campfire workspace rebuild --confirm
campfire workspace adopt inventory --source /path/to/folder --batch notes-001
campfire workspace adopt inventory --source /path/to/folder --batch notes-001 --confirm
campfire workspace adopt plan --batch notes-001 --target-path "mynote/新领域" --domain-id knowledge-new --name "新领域" --space knowledge --type knowledge-domain --governance knowledge-docs
campfire workspace adopt apply --batch notes-001 --confirm
campfire workspace adopt verify --batch notes-001
campfire tree
campfire --workspace personal maintenance check
campfire --workspace personal maintenance check --summary
campfire --workspace personal maintenance plan --id <plan-id>
campfire --workspace personal maintenance apply --plan <plan-id> --confirm
campfire --workspace personal maintenance sync --dry-run
campfire --workspace personal maintenance sync --scope "work/example"
```

`maintenance check` 统一负责正式文档 Schema 与枚举校验，并从当前 `_空间.md`、`_领域.md` 刷新 SQLite 中可重建的 Space、Domain 和 Document 索引；结构声明本身由 `workspace space/domain check` 校验。`maintenance sync` 只因领域结构、MOC、路径或并发安全问题阻塞。单篇文档的元数据问题会继续出现在检查报告中，但不会阻止其他领域刷新生成视图。`sync` 和 `run` 可用 `--scope` 限定同步领域。索引损坏或被删除时使用 `workspace rebuild --confirm` 从 Manifest 和 Markdown SSOT 完整恢复。

`workspace adopt` 负责首次接管已有文件夹。Vault 外来源先按哈希复制到 `_收件箱/待接管/<batch>`，原目录始终保留；Vault 内来源原地盘点。计划一次建立一个粗粒度 Domain，应用后自动生成声明与 MOC 并刷新索引。文档语义和子领域拆分仍由 Agent 通过 Maintenance/Restructure 的审批计划完成。

所有受管内容文档都使用 `base` 或 `base → knowledge/project-doc/task` 的一层配置继承；`human-request` 等没有专属字段的类型直接使用 `base`。`_空间.md`、`_领域.md` 是 Workspace 声明，不是内容文档。`document profile show` 展示编译后的完整规则，`document profile resolve` 展示指定文档最终使用的 Profile。Formatter 只按有效 Profile 排序并保留值；不允许字段由 Validator 报告，不会被自动删除。

Decision 的当前状态和追加事件位于全局 SQLite。全部状态自动投影到 `_协作/decisions/`，并统一显示在 `治理视图/决策工作台.base` 的不同状态视图中。投影不是事实源，不接受手工更新。

跨目录重构或显式修改 Frontmatter 时，先冻结范围，再传入 YAML/JSON 意图规格：

```yaml
operations:
  - source: work/old-project/技术-架构.md
    target: work/new-project/platform/技术-架构.md
    frontmatter:
      project: new-project
      domain: platform
    reason: 文档实际描述新项目的平台实现
    approved: false
```

```bash
campfire --workspace /path/to/vault workspace restructure inventory --scope work --batch move-001
campfire --workspace /path/to/vault workspace restructure plan --batch move-001 --spec restructure.yaml
# 审查批次 plan.json，将确定项目 approved 改为 true
campfire --workspace /path/to/vault workspace restructure apply --batch move-001
campfire --workspace /path/to/vault workspace restructure apply --batch move-001 --confirm
campfire --workspace /path/to/vault workspace restructure verify --batch move-001
```

领域名称、路径和稳定身份分别使用 `domain rename`、`domain move` 和高风险的 `domain rekey`。领域级命令会联动领域声明、子领域关系、Project、`.campfire.yaml` 和路径引用，默认只预览，追加 `--confirm` 才执行。

Workspace Restructure、Maintenance、Archive 写入前会在治理锁内复核内容哈希；检测到其他会话修改时返回
`concurrent-change` 或 `source-hash-changed`，不会覆盖新内容。文档、任务状态和 Skill 模板枚举由
同一个治理规则引擎按照有效 `config.yml` 中的 `frontmatter_schema` 校验。

产品默认契约位于包内 `resources/defaults/config.yml`，用户只在 `~/.campfire/config.yml` 写需要覆盖的配置。首次初始化会创建最小用户配置；修改后运行 `campfire workspace config check` 验证完整有效配置。`.campfire.yaml` 是便携元数据 SSOT；本机 SQLite 是设备路径、Decision、索引和运行状态的 SSOT。`workspace export/import` 只用于本机注册库备份，不承担跨设备同步。
