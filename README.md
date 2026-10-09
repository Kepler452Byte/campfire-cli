# Campfire

`campfire` 是面向工作与学习场景的本地优先人机协作 CLI。它让人类和多个 Agent 围绕同一份持久共享上下文协作：把口头要求、临时笔记、任务进度、项目资料和长期知识沉淀进可检索、可交接、可审计的 Workspace。

- **人类和 Agent 同一条链路**：同一套 CLI 契约 + 全局 Agent Skill，没有两套规则。
- **Markdown 是事实源**：正文永远可脱离 campfire 阅读和迁移；SQLite 保存可重建索引，也保存本机注册与运行状态，不能整体当作缓存删除。
- **写操作默认预览**：先计划、再确认、执行前在治理锁内复核内容哈希，检测到输入变化时拒绝覆盖；不承诺外部编辑器遵守锁或跨介质崩溃原子性。
- **本地优先**：不绑定云服务、不内置账号；Obsidian 是推荐阅读工具而非强依赖；CLI 可独立治理 Markdown Workspace。

产品目标、业务对象、SSOT 与模块边界见 [ARCHITECTURE.md](ARCHITECTURE.md)。不知道 Campfire 是否具有某项能力时用 `campfire tree` 发现命令；已知文档操作不把 tree 作为固定前置步骤。

## 使用入口

首次使用先看 [独立环境快速上手](docs/quickstart.md)，完整走通文档创建与关联查询，不接入真实 Vault。需要 Python 3.12+；发布流程验证 Linux、macOS 和 Windows，具体 Shell 要求见示例。

- [数据安全、误操作恢复与退出](docs/safety.md)
- [版本变化](CHANGELOG.md) · [贡献指南](CONTRIBUTING.md) · [安全反馈](SECURITY.md)

推荐搭配 Obsidian：内置 Bases 展示表格，大纲提供章节导航；Kanban 用于看板，Obsidian Git 用于版本历史。它们不是普通文档查询和治理的前提。Templater、TOC 不作为依赖。插件配置教程等待维护者提供博客链接，不在 CLI 输出或仓库重复编写，也不自动修改插件设置。

## 本地视频文字整理（v0.2.0）

本版统一公共 CLI 输出：成功在 stdout 返回一个 JSON 对象，错误在 stderr 返回一个 JSON 对象并以非零状态退出。`--help` 返回结构化参数，`tree` 返回层级命令树，`version` 返回 `{"status":"ok","version":"0.2.0"}`。旧脚本若将版本输出当纯字符串读取，须改读 `version` 字段；不再提供文本帮助或 shell 补全脚本输出。

安装正式版：`uv tool install "campfire-cli==0.2.0"`；已有安装使用 `campfire upgrade`。生成内容仍须实际核对，CLI 结构检查不能证明语义保真。

本轮只接受本地单视频，不解析抖音、B站或其他 URL。核心 CLI 不依赖视频运行库；首次使用执行 `campfire video setup`，统一预览缺失依赖与默认模型下载，带回 `--expected-plan <摘要> --confirm` 后一次完成安装和模型加载验证。无需 Workspace 或输入视频。视频由 PyAV 解码，无需额外安装 FFmpeg 命令；语音由 faster-whisper 在 CPU 本地转写。PyAV 暂限 `<19`，避免其删除的 `metadata_errors` 参数与当前转写库冲突。

初始化后运行 `campfire video prepare --source <本地视频> --output <Workspace外新目录>` 预览，带回 `--expected-plan` 和 `--confirm` 处理。`prepare` 不再安装依赖或下载模型，缺失时提示 `video setup`。默认模型位于 `<CAMPFIRE_HOME>/models/faster-whisper-small`，主目录默认 `~/.campfire`，Windows、macOS、Linux 沿用同一相对布局。初始化预览列出 Python 环境、缺失依赖、Hugging Face 固定版本、约 486 MB 模型体积及目标目录；确认后先安装再下载，最后在离线子进程中验证加载。已有依赖和模型复用，不静默更新模型，不上传媒体。

依赖安装只支持当前 uv tool、pipx 或 venv 隔离环境，通过可用的 uv 或环境内 pip 安装二进制包；不修改系统 Python，不重装运行中的 Campfire，不替换已有包。无可用安装器时返回 `needs-input`；版本冲突或缺少兼容 wheel 时停止，由用户按原安装方式修复后重试。安装中断时保留已完成部分，不回滚卸载；正常下载失败清理本次模型临时目录，下载成功但验证失败则保留模型并报告错误。包管理器升级或同步后若移除了可选依赖，重新执行 `video setup` 补齐。源码开发者仍可用 `uv sync --extra video` 管理锁定依赖，再用 `video setup` 验证模型。

可用 `--model <本地模型目录>` 覆盖默认位置；显式路径缺失或不完整时只报错，不下载或覆盖。已有默认目录不完整时也拒绝覆盖。也可用 `--transcript` 提供时间戳 JSON 数组，格式见命令帮助，此时不需要模型。模型权重目录须含非空的 `model.bin`、`config.json`、`tokenizer.json`；配置与权重能否实际加载仍由转写引擎校验。

内置 `campfire-video-capture` Skill 引导 Agent 阅读全部转写，再按意图生成校订转写稿或用途文章。校订稿保持顺序和有意义细节；文章可重组内容，保留来源映射并说明取舍。术语、数字和画面依赖内容明确标记待核实或回看。无需截图或视觉能力；可选截图建议仅说明用途及参考时段。

`video inspect` 校验素材与草稿，不证明内容质量；`video deliver` 向受管空正文交付文字，沿用 `document apply` 创建结构，不覆盖已有人工正文。同源不同目标可分别交付，Agent 仅在用户明确要求时创建第二份。草稿 schema_version=2，包含 output_kind（transcript/article）、title、source_sha256、purpose、sections（title/body/segment_ids）、可选 omissions（segment_ids/reason）与 limitations。ID 为 segments 的零基下标。校订稿须顺序覆盖一次全部片段；文章允许重排，未采用片段需说明取舍。格式与示例见内置 Skill 和 deliver 命令帮助。

默认限制为 4 GiB、2 小时、单次处理 3 小时，配置在内置 config.yml 的 video 分区。支持本地 MP4/MOV、Matroska/WebM、AVI、MPEG-TS，具体解码依赖 PyAV。素材默认保存到 `<CAMPFIRE_HOME>/materials/<视频SHA-256>/`，`--output` 可指定 Workspace 外新目录；已有目录不覆盖。素材保留用于核验，不自动过期。原视频只读且不复制，Vault 仅接收正文，交付后可独立阅读。

### 从 Alpha 升级

0.2.0 移除 `video frames`、自动抽帧和截图附件交付；移除 Pillow 直接依赖。旧 max_frames/frame_interval/max_dimension/max_pixels 配置忽略并在视频结果中报告。旧素材仅只读读取文字部分，不校验或复制旧截图；新转写用 `--output <新目录>`，不覆盖旧目录。旧图文草稿拒绝并提示重写为版本 2，删除 frame_ids/visual_reviewed 字段并选择产物用途。旧文档、附件、模型和素材保留。显式 transcript 输入与模型复用继续支持。

模型权重与媒体许可由使用者核对，PyAV/FFmpeg 许可随安装构建而异，本项目不捆绑模型或独立 FFmpeg 可执行文件。

## 安装

### 升级注意事项

`maintenance sync` 不再生成 `_generated/相关文档-*.md`，并移除 MOC 自动区域中的关系页入口；MOC 的文档导航、分组和模板入口保持不变。`related_docs` 仍为可选字段，Agent 通过 `document list` 定位文档、通过 `document inspect` 查询出向、入向及失效关联，查询不要求先同步 MOC。

同步不会删除或改写历史关系页，也不会修改人工正文链接。历史清理须先核实来源和人工内容，再确认具体范围；不能按 `_generated` 或 `generated` 目录名递归删除。Base 同步策略和领域模型不在本次变更范围内。

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

`setup` 会向 `~/.claude/CLAUDE.md`、`~/.agents/AGENTS.md` 注入幂等的 campfire 路标块，保留标记外内容；`CAMPFIRE_AGENT_HINT_PATH` 可覆盖目标。`setup` 与 `skill sync` 会把托管 Skill 同步到 `~/.claude/skills`、`~/.agents/skills`，可通过 `CAMPFIRE_SKILL_TARGETS` 覆盖。单独执行 `skill sync` 不更新提示词路标。

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
| Human request | Agent 需要人类回答的待确认事项 | `_待用户确认/` 中的 `human-request` 文档 |
| Generated View | MOC、Base、报告 | 派生数据，能生成就不手工维护 |

`任务/`、`记录/` 可按实际组织需要成为 Domain，但文档类型不强制对应同名目录，也不要求每个 Project 预建。新建受管文档在 Frontmatter 后提供 `<!-- CAMPFIRE:BODY -->`，Agent 以该锚点定位人工正文；旧文档无需迁移。

设备边界：`.campfire.yaml` 只保存可跨设备同步的稳定身份与逻辑关联（Project id、Git remote、文档 Domain 等），禁止本机绝对路径；新设备执行 `campfire setup --path <vault>` 即可恢复。本机路径绑定、索引、锁与报告都在 `~/.campfire/`（可用 `CAMPFIRE_HOME` 覆盖），按 Workspace 隔离。

## 常用命令

```bash
campfire tree                                    # 完整命令树
campfire workspace resolve                       # Workspace 不明确时解析
campfire workspace list / show / export / import # 注册库管理与备份
campfire workspace project resolve               # 当前目录属于哪个已注册项目

campfire maintenance check [--summary] [--scope] # Schema/枚举校验 + 刷新索引
campfire maintenance sync [--dry-run] [--scope]  # 刷新 MOC 导航

campfire document inspect / check / format       # 单篇文档查看、校验、格式化
campfire document list                           # 精确枚举和筛选受管文档
campfire document apply / move / rename          # 结构写入、跨 Domain 移动、原地改名
campfire document profile list / show / resolve  # Frontmatter Profile 规则
campfire document type list                      # 文档类型与前缀
campfire base list / show / check / sync          # Obsidian Base `_治理视图/`
```

通用模板集中在 Workspace 根目录 `_模板/`，方便人类查看维护；模板使用 `template` 类型和基础属性。正文顶部说明适用类型和裁剪规则，Agent 按需参考，不强制套用；更新已有文档优先保留合理结构。局部模板只在用户或领域规则明确指定时使用，不逐层查找或自动覆盖。模板不替代 Profile，也不校验正文。

新建 Workspace 默认附带模板原则 README、任务模板和版本发布清单模板，无需额外参数。模板仅初始化一次，之后由用户维护；setup、upgrade 不覆盖修改，也不补回被删除的模板。实际使用时保留格式规范卡片、替换示例正文，不把模板当成真实任务。

结构治理命令默认只输出计划，追加 `--confirm` 才执行：

```bash
campfire workspace space create --id research --name "研究" --path myresearch --type research
campfire workspace domain create --id wiki --name "Wiki" --path "mywork/项目/wiki" \
  --type knowledge-domain --governance knowledge-base --confirm
campfire --workspace personal workspace project adopt --id example \
  --name "Example" --domain project-example --local-path /path/to/repo
campfire workspace rebuild --confirm             # 索引损坏时从 SSOT 完整恢复
```

## Project 多仓库与新设备接入

一个业务 Project 绑定一个文档根 Domain，可登记零个或多个仓库。仓库由 Project 内唯一的稳定 `id` 标识，`role` 只是描述；角色修改或列表重排不改变本机路径绑定。

```bash
campfire workspace project create --id product --name "Product" --path mywork/Product \
  --repositories '[{"id":"web","role":"frontend","git_remote_url":"https://example.org/web.git"},{"id":"api","role":"backend","git_remote_url":"https://example.org/api.git"}]'
# 审查后对同一条 create 命令追加 --confirm
campfire workspace project bind --id product --repository web --local-path /path/to/web
campfire workspace project bind --id product --repository api --local-path /path/to/api
campfire workspace project update --id product --repository api --role server
# 审查后，对相同 update 命令追加 --expected-hash <预览哈希> --confirm
```

`create/adopt --repositories` 接受 JSON 数组，条目包含必填 `id` 以及可选 `git_remote_url`、`default_branch`、`role`、`local_path`，不能与旧单仓库参数混用。`update --repository` 新增或修改一个仓库，默认只预览；`--unbind` 清除本机路径，`--remove-repository` 移除注册项，两者均须预览哈希和确认，均不删除代码文件。角色可传空字符串清空。Project 名称、Domain 和状态仍单独使用旧 update 入口。

旧单仓库参数继续支持；旧数据自动映射为 `default` 仓库，单仓库 JSON 的顶层 remote、路径和分支仍是该仓库的兼容字段，多仓库时为 null，不默认指向第一项。已有单仓库具有其他 id 时，旧参数保留其 id 与角色。零仓库允许只管理文档；旧 bind 不指定仓库时可为零仓库 Project 创建 `default`，其余显式仓库注册使用 update。

本地 resolve 按最深绑定路径匹配并返回仓库 id，不执行 Git 子进程；相同深度多个绑定返回 ambiguous，包括同一 Project 内的多个仓库。共享 remote 允许登记，但远程匹配只返回候选，不自动认定归属。绑定路径可重叠，调用方需根据结果明确选择。check 逐仓库报告未绑定、路径缺失及 Git 信息漂移。

setup 默认输出资源操作摘要；逐文件路径与哈希使用 `setup --verbose`。健康问题返回 needs-review，健康检查通过但仓库未绑定时返回 needs-input；unbound_repositories 提供仓库身份和绑定参数，实际本机目录须用户提供。重复 setup 按仓库 id 保留已有绑定，不扫描或自动绑定猜测路径。

升级至 0.2.1 自动执行数据库迁移 013，保留原单仓库值；旧 Manifest v1 和注册备份 v1 可读取，新写入使用 v2。Manifest 仅保存便携仓库元数据，本机路径仍在 SQLite；setup 读取旧 Manifest 时不强制改写，后续 Project 或 Domain 元数据写入才采用 v2。含多仓库的 v2 数据不承诺供旧版 CLI 使用，降级前应恢复升级前完整备份，不手工删除数据库或仓库列表。本轮版本号 0.2.1 按用户明确决定采用。

## 索引统计与检查范围

`maintenance check` 和 `workspace rebuild --confirm` 完整重建索引；治理问题不等于索引不可用。`indexed_document_count` 是当前整个 Workspace 的索引总量；`index_processed_document_count` 是本次索引处理的文档数量，完整重建时包括内容未改变的文档；`index_content_changed_document_count` 是内容哈希发生变化或新增、删除的文档数量。`index_generation` 标识快照，`index_available` 为 true 表示本次确认可用，null 表示当前步骤未评估。`document_count` 仍表示本次治理扫描范围的数量。

`write_performed` 只表示 Markdown 文件变更，不包含 SQLite 或运行报告写入，范围由 write_performed_scope 明示。无文件变化与索引可用可以同时成立。scoped sync 的索引总量仍按 Workspace 统计，其文件维护范围由 scope 限定。

关系检查仅覆盖 Frontmatter 的 `related_docs`，正文链接不参与索引、治理检查或自动改写。零治理问题不代表正文全部链接有效。用户要求删除具体文档时直接使用 rm 或文件工具；Campfire 不提供 document delete。查询会自动对账索引，MOC 按需 scoped sync，遗留引用另行核实和处理。

类型未知时使用 `campfire --workspace <id> document type list` 查询当前有效类型、名称与前缀，再对选定类型查询 Profile；已知类型不重复列举，不猜测 type 或按目录名推断。

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
- **并发与提交安全**：写入前在治理锁内复核内容哈希，外部变化返回 `concurrent-change` / `source-hash-changed`，拒绝覆盖；多文件写入和路径移动经同一 ChangeSet 提交，可捕获失败尝试补偿；若报告恢复失败，停止重试并核对实际文件。
- **按需后续治理**：写入命令只在实际写入成功且派生内容可能变化时返回零或一个、且可直接执行的最小 scope `maintenance sync`；预览和阻塞结果的 `follow_up` 为空。位于 Domain 内部的 scope 由 CLI 归一化为有效 Domain。Skill 消费该结果，没有 follow-up 就结束，不固定追加 dry-run 或全量 check。
- **配置两层模型**：产品默认契约在包内 `resources/defaults/config.yml`（SSOT），用户只在 `~/.campfire/config.yml` 写覆盖项；Mapping 递归合并，`campfire workspace config check` 验证有效配置。

## Agent 协作

全局 Skill 定义 Agent 的文档工作流：已知路径的人工正文直接 Edit；新建文档先 apply 创建结构，再按返回的 `target` 补正文。只在治理上下文缺失时加载 bootstrap；字段契约未知时，新建查一次目标 Profile，更新查一次 inspect。已明确的信息不重复查询，用户已有授权不重复询问。文档相对路径以 Workspace 根目录为基准，不随 cwd 改变；创建时可省略类型前缀与 `.md`。改标题用 rename，跨 Domain 移动用 move，完成后仅执行实际 follow_up。归档仍需用户对具体文档明确同意，关键歧义不得自行猜测。

仓库 Skill 编写规范见 `src/campfire_cli/resources/skills/SPEC.md`。本地与 CI 共用 `uv run python scripts/quality_check.py`；发布前使用 `--release` 增加构建、wheel 隔离安装与冒烟验证。测试日志包含最慢 10 项耗时。Release 的公共 PyPI 安装验证最多等待 3 分钟、间隔 15 秒重试，不重试上传；安装后版本不符直接失败。

发布准备先执行 `uv run python scripts/release_check.py --tag <目标标签>`（默认检查 HEAD，可用 `--target <提交>` 指定）。这是只读检查，不创建或推送标签。远端标签不存在时按正常流程创建；已有标签一致时复用；对象不同或提交不同时停止核对，不强推、不重建。远端已有而本地缺失时先获取原标签再检查。IDE 拉取时的标签冲突不等于源码合并冲突，也不代表分支拉取已完成；不要全局开启“始终替换本地标记”。检查通过不替代质量门禁或用户发布授权。

## 许可

MIT。
