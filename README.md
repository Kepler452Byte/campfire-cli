# Campfire

`campfire` 是面向工作与学习场景的本地优先人机协作 CLI。它让人类和多个 Agent 围绕同一份持久共享上下文协作：把口头要求、临时笔记、任务进度、项目资料和长期知识沉淀进可检索、可交接、可审计的 Workspace。

- **人类和 Agent 同一条链路**：同一套 CLI 契约 + 全局 Agent Skill，没有两套规则。
- **Markdown 是事实源**：正文永远可脱离 campfire 阅读和迁移；SQLite 只是可重建的本机索引与运行状态。
- **写操作默认预览**：先计划、再确认、执行前在治理锁内复核内容哈希，多会话并发不会互相覆盖。
- **本地优先**：不绑定云服务、不内置账号；Obsidian Vault 是当前首个存储适配器，Workspace 才是顶层概念。

产品目标、业务对象、SSOT 与模块边界见 [ARCHITECTURE.md](ARCHITECTURE.md)。不知道 Campfire 是否具有某项能力时用 `campfire tree` 发现命令；已知文档操作不把 tree 作为固定前置步骤。

## 安装

标准安装（已发布至 PyPI，无需源码仓库）：

```bash
uv tool install campfire-cli
campfire version
```

升级：`campfire upgrade` 是一条幂等命令——检测 PyPI 新版本并按安装方式（uv tool / pipx）更新包本身（更新器在独立进程中等待当前进程退出后执行，完成后自动用新版代码对齐治理资源），随后对齐 SQLite Schema、全局 Skill、Base 与提示词路标。离线、已是最新、editable 源码安装或无法识别安装方式时跳过包更新仅对齐资源。

开发机安装（跟随本地源码）：

```bash
git clone https://github.com/Kepler452Byte/campfire-cli
uv tool install --editable /path/to/campfire-cli
```

源码开发使用 `uv sync` 后直接 `uv run campfire --help`。

## 快速上手

```bash
# 1. 接入已有 Vault（目录已存在，含或不含 .campfire.yaml）
campfire setup --path /path/to/vault --default

# 2. 或者从零创建新 Workspace（初始化目录结构并注册）
campfire workspace create --id personal --path /path/to/vault --default

# 3. 日常：检查治理状态、刷新生成视图
campfire maintenance check --summary
campfire maintenance sync --dry-run
```

不指定 `--path` 运行 `campfire setup` 是降级执行而不是报错：仍会同步全局 Skill 与提示词路标，输出接入引导，并显式列出被跳过的 Manifest 相关步骤。

`setup` 与 `skill sync` 会向 `~/.claude/CLAUDE.md`、`~/.agents/AGENTS.md` 注入幂等的 campfire 路标块（带注释标记、不触碰块外内容；`CAMPFIRE_AGENT_HINT_PATH` 可覆盖目标），并把托管 Skill 同步到 `~/.claude/skills`、`~/.agents/skills`（`CAMPFIRE_SKILL_TARGETS` 可覆盖）。Agent 冷启动时由此知道本机装有 campfire。

## 核心概念

```text
Workspace ── Space ── Domain 树 ── 文档
     │        （_空间.md）（_领域.md + 自动 MOC）
     └── Project（关联代码仓库与项目根 Domain）
```

| 对象 | 说明 | 事实源 |
|------|------|--------|
| Workspace | 人与 Agent 共享的上下文边界，可对应一个 Vault | `~/.campfire/campfire.db`（注册）+ `.campfire.yaml`（便携 Manifest） |
| Space / Domain | 顶级容器 / 可嵌套内容边界，声明式 + 自动 MOC | Vault 内 `_空间.md`、`_领域.md` |
| Document | 知识、计划、问题、决策、记录等持久内容 | Markdown 正文 + Frontmatter |
| Human request | Agent 需要人类回答的待确认事项 | `_收件箱/待用户确认/` 中的 `human-request` 文档 |
| Generated View | MOC、相关文档页、Base、报告 | 派生数据，能生成就不手工维护 |

设备边界：`.campfire.yaml` 只保存可跨设备同步的稳定身份与逻辑关联（Project id、Git remote、文档 Domain 等），禁止本机绝对路径；新设备执行 `campfire setup --path <vault>` 即可恢复。本机路径绑定、索引、锁与报告都在 `~/.campfire/`（可用 `CAMPFIRE_HOME` 覆盖），按 Workspace 隔离。

## 常用命令

```bash
campfire tree                                    # 完整命令树
campfire workspace resolve                       # Agent 冷启动第一步：解析当前 Workspace
campfire workspace list / show / export / import # 注册库管理与备份
campfire workspace project resolve               # 当前目录属于哪个已注册项目

campfire maintenance check [--summary] [--scope] # Schema/枚举校验 + 刷新索引
campfire maintenance sync [--dry-run] [--scope]  # 刷新 MOC 与相关文档页

campfire document inspect / check / format       # 单篇文档查看、校验、格式化
campfire document list                           # 精确枚举和筛选受管文档
campfire document apply / move                   # 创建更新、类型转换、跨 Domain 移动
campfire document profile list / show / resolve  # Frontmatter Profile 规则
campfire document type list                      # 文档类型与前缀
campfire base list / show / check / sync          # Obsidian Base 治理视图
```

Domain 可在 `_模板/` 中维护基础属性的 `template` 文档。Agent 创建结构化文档时按当前 Domain 到祖先 Domain 的顺序使用最近同名模板；模板只提供正文骨架，不替代目标文档 Profile。

结构治理命令默认只输出计划，追加 `--confirm` 才执行：

```bash
campfire workspace space create --id research --name "研究" --path myresearch --type research
campfire workspace domain create --id wiki --name "Wiki" --path "mywork/项目/wiki" \
  --type knowledge-domain --confirm
campfire --workspace personal workspace project adopt --id example \
  --name "Example" --domain project-example --local-path /path/to/repo
campfire workspace rebuild --confirm             # 索引损坏时从 SSOT 完整恢复
```

## 存量接管与结构重构

`workspace domain adopt` 用一条命令接管一个已有文件夹。Vault 外来源经临时暂存和哈希校验复制到目标 Domain，原目录始终保留；Vault 内来源原地声明或移动到明确目标。命令一次建立一个粗粒度 Domain，语义细分交给后续 Restructure。

```bash
campfire workspace domain adopt --source /path/to/folder --target-path "mynote/新领域" \
  --id knowledge-new --name "新领域" \
  --type knowledge-domain --governance knowledge-docs
# 审查同一份结构化计划后，对相同命令追加 --confirm
```

单篇文档在已声明 Domain 之间移动使用 `document move --path <source> --domain <target-domain-id> [--name <filename>]`。常见 Domain 调整直接使用 `domain move/merge/delete`；只有批量文档映射、领域拆分或 Frontmatter Patch 才进入持久批次：

```bash
campfire workspace restructure inventory --scope work --batch move-001
campfire workspace restructure plan --batch move-001 --spec restructure.yaml
campfire workspace restructure apply --batch move-001 --confirm
campfire workspace restructure verify --batch move-001
```

领域三个维度独立演进：`domain rename`（显示名）、`domain move --target <space-or-domain-id>`（物理位置）、`domain rekey`（稳定身份，高风险）。领域合并和逻辑空领域删除分别使用 `domain merge`、`domain delete`；领域级命令联动 `_领域.md`、子领域、Project、`.campfire.yaml` 与路径引用。

## 治理模型

- **本地查询投影**：`document list` 按 Project、Domain、类型、`document_status` 和 `task_status` 精确筛选；`document inspect` 返回显式关联、出链、反向链接和失效/歧义引用。两者在查询前自动 reconcile，Agent 无需先运行 Maintenance。SQLite 不复制正文，正文仍由 Agent 按返回路径读取。
- **校验分工**：`maintenance check` 汇总 Space/Domain 结构与正式文档问题，并刷新可重建索引；`workspace space/domain check` 提供结构声明的专项诊断。`maintenance sync` 只因结构、MOC、路径或并发安全问题阻塞，单篇文档问题不阻止其他领域刷新。
- **Frontmatter Profile**：声明式一层继承（`base` 或 `base → task/human-request/board`），`document profile show` 展示编译后的完整规则；Formatter 只按有效 Profile 排序并保留值，不允许字段由 Validator 报告、不自动删除。
- **并发与提交安全**：写入前在治理锁内复核内容哈希，外部变化返回 `concurrent-change` / `source-hash-changed`，拒绝覆盖；多文件写入和路径移动经同一 ChangeSet 提交，失败恢复到执行前。
- **按需后续治理**：写入命令只在实际写入成功且派生内容可能变化时返回零或一个、且可直接执行的最小 scope `maintenance sync`；预览和阻塞结果的 `follow_up` 为空。位于 Domain 内部的 scope 由 CLI 归一化为有效 Domain。Skill 消费该结果，没有 follow-up 就结束，不固定追加 dry-run 或全量 check。
- **配置两层模型**：产品默认契约在包内 `resources/defaults/config.yml`（SSOT），用户只在 `~/.campfire/config.yml` 写覆盖项；Mapping 递归合并，`campfire workspace config check` 验证有效配置。

## Agent 协作

全局 Skill（`campfire skill list` 查看托管清单，`campfire skill sync` 手动同步）定义了 Agent 的标准工作流：已给出唯一文件路径的正文读取或小改直接使用文件工具；新建文档、修改 Frontmatter/类型/归属或执行结构治理时才加载 bootstrap，并使用 `document apply/move` 等原子命令。`document apply --path` 创建或唯一更新时可省略 `.md`，创建时也可省略类型前缀。Frontmatter 契约已知时直接 apply；现有文档的字段类型或合法值未知时只执行一次 `document inspect` 后 apply。批量结构调整用 `workspace restructure`；归档在用户明确同意后通过 `document apply --set document_status=archived` 执行。关键歧义进入 `human-request`，不由 Agent 擅自决定。

## 许可

MIT。
