# Campfire

`campfire` 是面向工作与学习场景的本地优先人机协作 CLI。它让人类和多个 Agent 围绕同一份持久共享上下文协作：把口头要求、临时笔记、任务进度、项目资料和长期知识沉淀进可检索、可交接、可审计的 Workspace。

- **人类和 Agent 同一条链路**：同一套 CLI 契约 + 全局 Agent Skill，没有两套规则。
- **Markdown 是事实源**：正文永远可脱离 campfire 阅读和迁移；SQLite 只是可重建的本机索引与运行状态。
- **写操作默认预览**：先计划、再确认、执行前在治理锁内复核内容哈希，多会话并发不会互相覆盖。
- **本地优先**：不绑定云服务、不内置账号；Obsidian Vault 是当前首个存储适配器，Workspace 才是顶层概念。

产品目标、业务对象、SSOT 与模块边界见 [ARCHITECTURE.md](ARCHITECTURE.md)，命令全景用 `campfire tree` 渐进发现。

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
campfire setup --workspace /path/to/vault --default

# 2. 或者从零创建新 Workspace（初始化目录结构并注册）
campfire workspace create --id personal --path /path/to/vault --default

# 3. 日常：检查治理状态、刷新生成视图
campfire maintenance check --summary
campfire maintenance sync --dry-run
```

不指定 `--workspace` 运行 `campfire setup` 是降级执行而不是报错：仍会同步全局 Skill 与提示词路标，输出接入引导，并显式列出被跳过的 Manifest 相关步骤。

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
| Decision | 需要人类或高级 Agent 回答的持久判断 | 全局 SQLite，投影到 `_协作/decisions/` |
| Generated View | MOC、相关文档页、Base、报告 | 派生数据，能生成就不手工维护 |

设备边界：`.campfire.yaml` 只保存可跨设备同步的稳定身份与逻辑关联（Project id、Git remote、文档 Domain 等），禁止本机绝对路径；新设备执行 `campfire setup --workspace <vault>` 即可恢复。本机路径绑定、索引、Decision、锁与报告都在 `~/.campfire/`（可用 `CAMPFIRE_HOME` 覆盖），按 Workspace 隔离。

## 常用命令

```bash
campfire tree                                    # 完整命令树
campfire workspace resolve                       # Agent 冷启动第一步：解析当前 Workspace
campfire workspace list / show / export / import # 注册库管理与备份
campfire workspace project resolve               # 当前目录属于哪个已注册项目

campfire maintenance check [--summary] [--scope] # Schema/枚举校验 + 刷新索引
campfire maintenance sync [--dry-run] [--scope]  # 刷新 MOC 与相关文档页
campfire maintenance archive check / apply       # 归档候选检查与执行

campfire document inspect / check / format       # 单篇文档查看、校验、格式化
campfire document apply / move                   # 单篇文档创建更新、跨 Domain 移动
campfire document profile list / show / resolve  # Frontmatter Profile 规则
campfire document type list                      # 文档类型与前缀

campfire decision create / list / answer / close # 持久决策通道
```

结构治理命令默认只输出计划，追加 `--confirm` 才执行：

```bash
campfire workspace space create --id research --name "研究" --path myresearch --type research
campfire workspace domain create --id wiki --name "Wiki" --path "mywork/项目/wiki" \
  --space work --type knowledge-domain --governance project-docs --confirm
campfire workspace project adopt --id example --workspace personal \
  --name "Example" --document-domain "work/example" --local-path /path/to/repo
campfire workspace rebuild --confirm             # 索引损坏时从 SSOT 完整恢复
```

## 存量接管与结构重构

`workspace domain adopt` 用一条命令接管一个已有文件夹。Vault 外来源经临时暂存和哈希校验复制到目标 Domain，原目录始终保留；Vault 内来源原地声明或移动到明确目标。命令一次建立一个粗粒度 Domain，语义细分交给后续 Restructure。

```bash
campfire workspace domain adopt --source /path/to/folder --target-path "mynote/新领域" \
  --id knowledge-new --name "新领域" --space knowledge \
  --type knowledge-domain --governance knowledge-docs
# 审查同一份结构化计划后，对相同命令追加 --confirm
```

单篇文档在已声明 Domain 之间移动使用 `document move`。批量文档或 Domain 结构重构先冻结范围，再传入 YAML/JSON 意图规格（含 Frontmatter 修改），逐项审查 `approved` 后执行：

```bash
campfire workspace restructure inventory --scope work --batch move-001
campfire workspace restructure plan --batch move-001 --spec restructure.yaml
campfire workspace restructure apply --batch move-001 --confirm
campfire workspace restructure verify --batch move-001
```

领域三个维度独立演进：`domain rename`（显示名）、`domain move`（物理路径）、`domain rekey`（稳定身份，高风险）。领域级命令联动 `_领域.md`、子领域、Project、`.campfire.yaml` 与路径引用。

## 治理模型

- **校验分工**：`maintenance check` 统一负责正式文档的 Schema 与枚举校验，并刷新可重建索引；结构声明由 `workspace space/domain check` 校验；`maintenance sync` 只因结构、MOC、路径或并发安全问题阻塞，单篇文档问题不阻止其他领域刷新。
- **Frontmatter Profile**：声明式一层继承（`base` 或 `base → knowledge/project-doc/task`），`document profile show` 展示编译后的完整规则；Formatter 只按有效 Profile 排序并保留值，不允许字段由 Validator 报告、不自动删除。
- **并发与提交安全**：写入前在治理锁内复核内容哈希，外部变化返回 `concurrent-change` / `source-hash-changed`，拒绝覆盖；多文件写入和路径移动经同一 ChangeSet 提交，失败恢复到执行前。
- **按需后续治理**：写入命令只在派生内容可能变化时返回一个最小 scope 的 `maintenance sync`；Skill 消费该结果，没有 follow-up 就结束，不固定追加 dry-run 或全量 check。
- **配置两层模型**：产品默认契约在包内 `resources/defaults/config.yml`（SSOT），用户只在 `~/.campfire/config.yml` 写覆盖项；Mapping 递归合并，`campfire workspace config check` 验证有效配置。

## Agent 协作

全局 Skill（`campfire skill list` 查看托管清单，`campfire skill sync` 手动同步）定义了 Agent 的标准工作流：首次读写先 `workspace resolve` 并读取 Workspace 的 `AGENTS.md`；单文档用 `document apply/move`，批量结构调整用 `workspace restructure`，归档用 `maintenance archive`。有歧义的分类和重构进入 Decision，不由 Agent 擅自决定。

## 许可

MIT。
