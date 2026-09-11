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

CLI 通过用户级 `~/.campfire/registry.json` 管理多个 Workspace。配置、SQLite、批次、报告和锁全部保存在 `~/.campfire/workspaces/<id>/`，不会向 Workspace 写入工具状态目录。可用 `CAMPFIRE_HOME` 覆盖用户级根目录。

## 安装与调用

开发机安装：

```bash
uv tool install --editable /path/to/campfire-cli
campfire version
```

人类和 Agent 使用同一条链路：全局 Skill 先调用 `campfire workspace resolve`，再读取目标 Workspace 的 `AGENTS.md`，并使用 Workspace id 调用 `campfire`。不修改原始笔记的检查可以直接执行（会刷新 SQLite 当前状态和 current 报告）；`migration apply`、
`maintenance apply` 和 `archive apply` 必须先审查计划，并使用命令要求的显式确认参数。

```bash
campfire workspace add --id personal --path /path/to/vault --default
campfire workspace create --id new-vault --path /new/path --default
campfire workspace resolve
campfire --workspace personal maintenance check
campfire --workspace personal maintenance check --summary
campfire --workspace personal maintenance plan
campfire --workspace personal maintenance apply --confirm
campfire --workspace personal maintenance sync --dry-run
```

跨目录迁移或显式修改 Frontmatter 时，先冻结范围，再传入 YAML/JSON 意图规格：

```yaml
operations:
  - source: mywork/旧项目/技术-架构.md
    target: mywork/新项目/平台/技术-架构.md
    frontmatter:
      project: new-project
      domain: platform
    reason: 文档实际描述新项目的平台实现
    approved: false
```

```bash
campfire --workspace /path/to/vault migration inventory --scope mywork --batch move-001
campfire --workspace /path/to/vault migration plan --batch move-001 --spec migration.yaml
# 审查批次 plan.json，将确定项目 approved 改为 true
campfire --workspace /path/to/vault migration apply --batch move-001
campfire --workspace /path/to/vault migration apply --batch move-001 --confirm
campfire --workspace /path/to/vault migration verify --batch move-001
```

Migration、Maintenance、Archive 写入前会在治理锁内复核内容哈希；检测到其他会话修改时返回
`concurrent-change` 或 `source-hash-changed`，不会覆盖新内容。文档、任务状态和 Skill 模板枚举由
同一个治理规则引擎按照 `frontmatter-schema.json` 校验。

配置契约位于 `~/.campfire/workspaces/<id>/config/`；SQLite 是当前运行状态的主索引，
`backup/current.json` 是可移植快照，`backup/changes.jsonl` 只保留最近的有限变更记录。
