# 数据安全、误操作恢复与退出

Campfire 不提供独立备份系统。先明确写入边界，再使用已有 Git 历史或文件备份恢复。Git 只能恢复已经提交的内容，远端推送不是对未提交内容的保障。

## 哪些内容会改变

| 操作 | 可能写入的位置 |
| --- | --- |
| workspace create / setup | Workspace 声明、Manifest、默认资源、本机注册、索引、Skill 和 Agent 提示词 |
| document apply / rename / move | 目标文档受管字段、名称、路径及确定的 related_docs 引用 |
| maintenance check / list / inspect | 本机索引和检查状态；不是完全无副作用的文件读取 |
| maintenance sync | MOC 自动区域和本机投影，不写人工正文或历史关系页 |
| base sync | `_治理视图` 中的内置 Base 定义，可能补回已删除的内置视图 |
| upgrade | Python 包、当前派生数据库初始化、已注册 Workspace 的 Base、全局 Skill 和提示词 |

默认本机状态在 `~/.campfire`；`CAMPFIRE_HOME` 可覆盖。提示词默认位于 `~/.claude/CLAUDE.md`、`~/.agents/AGENTS.md`，Skill 默认位于两者的 skills 目录。`CAMPFIRE_AGENT_HINT_PATH` 和 `CAMPFIRE_SKILL_TARGETS` 可覆盖，多个目标按操作系统路径分隔符分开。

结构变更通常先预览再确认；setup、workspace create、sync、资源升级存在直接写入路径，先看具体帮助。生成同步支持 dry-run，但 dry-run 仍可能对账本机索引，不应理解为整台机器零写入。
锁、哈希复核和变更集降低并发覆盖风险，不保证所有外部编辑器遵守锁，也不保证断电时文件系统与数据库跨介质原子恢复。报告补偿失败时先停下核对，不反复重放命令。

## 误改文档如何恢复

1. 停止当前写入和自动同步，确认受影响文件及用户自己的未提交修改。
2. 用 Git diff/history 或文件备份核对旧内容；只恢复明确的文件，不用全库 hard reset 覆盖其他工作。
3. 恢复正文或字段后，用 document inspect 查询，CLI 自动对账；需要刷新导航时预览并运行受影响领域的 maintenance sync。
4. 结构移动、合并或 rekey 影响多个文件时，声明、Manifest 和引用必须恢复到一致状态，不只恢复单个文件夹。

没有旧副本就不能承诺恢复。Obsidian Git 是可选的历史管理工具，Git 提交、远端同步和可靠备份不是同一概念。

## 内容与本机状态分开恢复

Markdown、`_空间.md`、`_领域.md` 和 `.campfire.yaml` 是可移植事实。新设备通过 setup 接入已有目录，再显式绑定无法恢复的源码本机路径。
`~/.campfire/local.yaml` 保存 Vault 注册、默认选择和仓库本机绑定；remote 和项目元数据只保存在 Vault 根目录 `.campfire.yaml`。停止所有 Campfire 操作后可删除 `campfire.db`、`campfire.db-wal` 与 `campfire.db-shm`，通过查询或 setup 重建；未执行计划重新生成并重新审批。文件操作失败恢复未完成时先核对与恢复文件，不清理证据。`workspace rebuild` 不是“恢复删除笔记”。

需要备份本机状态时，先退出所有 Campfire 进程并暂停写入，再复制整个实际 CAMPFIRE_HOME 目录；不要在写入中只复制 SQLite 主文件而漏掉 WAL。恢复前保留当前状态，停止进程，使用一致快照恢复，并核对 CLI 和当前配置结构；产品不读取旧格式或运行历史迁移。

## 卸载与停止治理

停止自动调用后，使用原安装工具卸载：uv 安装用 `uv tool uninstall campfire-cli`，pipx 安装用 `pipx uninstall campfire-cli`。不要执行与实际安装方式无关的删除命令。

卸载不会自动删除 Vault，也不会自动撤销所有全局资源：

- Markdown、Manifest、MOC、Base 可以保留；普通内容仍能阅读，某些视图需要 Obsidian。
- 检查实际 Skill 安装位置，只移除确认属于 Campfire 的托管目录，保留其他 Skill。
- 提示词仅移除 `<!-- campfire:agent-hints:start -->` 到对应 end 的完整块，不删除整个 AGENTS.md 或 CLAUDE.md。
- 本机状态是否保留由用户决定；先理解并备份需要保留的注册和运行记录，不把卸载等同于清空它们。

诊断日志、绝对路径、仓库地址和文档内容可能含隐私；提交 Issue 前使用虚构示例并脱敏。没有必要时不要上传真实 Vault、数据库、访问令牌或企业资料。
