# Campfire

`campfire` 是面向工作与学习场景的本地优先人机协作 CLI。它让人类和多个 Agent 围绕持久共享上下文协作，并把一次性存量迁移与后续增量维护分开。

产品目标、业务对象、SSOT 与模块边界见 [ARCHITECTURE.md](ARCHITECTURE.md)。Markdown/Obsidian Vault 是当前首个存储适配器，Workspace 才是面向用户的顶层概念。

```bash
uv sync
uv run campfire --help
uv run campfire init --id personal --workspace /path/to/vault --default
uv run campfire workspace list
uv run campfire --workspace personal maintenance check
```

CLI 通过唯一的用户级 `~/.campfire/campfire.db` 管理多个 Workspace、Project、文档索引和工作流状态。各 Workspace 的配置、批次和报告保存在 `~/.campfire/workspaces/<id>/`，不会向 Workspace 写入工具状态目录。可用 `CAMPFIRE_HOME` 覆盖用户级根目录。

## 安装与调用

开发机安装：

```bash
uv tool install --editable /path/to/campfire-cli
campfire version
```

人类和 Agent 使用同一条链路：全局 Skill 先调用 `campfire workspace resolve`，再读取目标 Workspace 的 `AGENTS.md`，并使用 Workspace id 调用 `campfire`。不修改原始笔记的检查可以直接执行（会刷新 SQLite 当前状态和 current 报告）；`migration apply`、
`maintenance apply` 和 `maintenance archive apply` 必须先审查计划，并使用命令要求的显式确认参数。

```bash
campfire workspace add --id personal --path /path/to/vault --default
campfire workspace create --id new-vault --path /new/path --default
campfire workspace space list --workspace personal
campfire workspace domain list --workspace personal
campfire workspace domain check --workspace personal
campfire workspace space create --id research --name "研究" --path myresearch --type research
campfire workspace space create --id research --name "研究" --path myresearch --type research --confirm
campfire workspace domain create --id distributed-systems --name "分布式系统" --path "knowledge/分布式系统" --space knowledge --type knowledge-domain --governance knowledge-docs
campfire workspace domain create --id distributed-systems --name "分布式系统" --path "knowledge/分布式系统" --space knowledge --type knowledge-domain --governance knowledge-docs --confirm
campfire workspace project add --id example --workspace personal --name "Example" --document-domain "work/example" --local-path /path/to/repository
campfire workspace project list --workspace personal
campfire --workspace personal document profile list
campfire --workspace personal document profile show task
campfire --workspace personal document profile resolve --path "work/example/任务-示例.md"
campfire --workspace personal document profile sync
campfire --workspace personal document profile sync --confirm
campfire --workspace personal document type list
campfire --workspace personal document type sync
campfire --workspace personal document type sync --confirm
campfire --workspace personal document check --path "knowledge/example/知识-示例.md"
campfire --workspace personal document format --path "knowledge/example/知识-示例.md"
campfire --workspace personal document format --path "knowledge/example/知识-示例.md" --confirm
campfire workspace export --output campfire-registry-backup.json
campfire workspace import --input campfire-registry-backup.json
campfire workspace import --input campfire-registry-backup.json --confirm
campfire workspace resolve
campfire tree
campfire --workspace personal maintenance check
campfire --workspace personal maintenance check --summary
campfire --workspace personal maintenance plan
campfire --workspace personal maintenance apply --confirm
campfire --workspace personal maintenance sync --dry-run
campfire --workspace personal maintenance sync --scope "work/example"
```

`maintenance check` 统一负责文档 Schema 与枚举校验；`maintenance sync` 只因领域结构、MOC、路径或并发安全问题阻塞。单篇文档的元数据问题会继续出现在检查报告中，但不会阻止其他领域刷新生成视图。`sync` 和 `run` 可用 `--scope` 限定同步领域。

Frontmatter 使用 `base → knowledge/project-doc/task` 一层配置继承。`document profile show` 展示编译后的完整规则，`document profile resolve` 展示指定文档最终使用的 Profile。Formatter 只按有效 Profile 排序并保留值；不允许字段由 Validator 报告，不会被自动删除。

跨目录迁移或显式修改 Frontmatter 时，先冻结范围，再传入 YAML/JSON 意图规格：

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
campfire --workspace /path/to/vault migration inventory --scope work --batch move-001
campfire --workspace /path/to/vault migration plan --batch move-001 --spec migration.yaml
# 审查批次 plan.json，将确定项目 approved 改为 true
campfire --workspace /path/to/vault migration apply --batch move-001
campfire --workspace /path/to/vault migration apply --batch move-001 --confirm
campfire --workspace /path/to/vault migration verify --batch move-001
```

Migration、Maintenance、Archive 写入前会在治理锁内复核内容哈希；检测到其他会话修改时返回
`concurrent-change` 或 `source-hash-changed`，不会覆盖新内容。文档、任务状态和 Skill 模板枚举由
同一个治理规则引擎按照 `frontmatter-schema.json` 校验。

配置契约位于 `~/.campfire/workspaces/<id>/config/`；全局唯一 SQLite 是注册数据的事实源和当前运行状态的主索引，
`backup/current.json` 是可移植快照，`backup/changes.jsonl` 只保留最近的有限变更记录。
