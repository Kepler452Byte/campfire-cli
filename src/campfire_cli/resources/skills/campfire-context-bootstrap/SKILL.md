---
name: campfire-context-bootstrap
description: "补齐 Campfire 治理流程缺少的 Workspace、Domain 或 Project 上下文；仅涉及已知路径正文、或治理上下文已明确时不加载。"
---

# Campfire 上下文启动

只补齐当前任务缺少的治理上下文，不创建文档、不执行代码任务、不调度 Agent Session。已知信息直接复用；目标或相关结构变化时重新确认受影响部分，不维护隐式 Session 缓存。

## 上下文与契约

Workspace 使用根级 `campfire --workspace <id> ...` 选择。文档相对路径基于 Workspace 根，不是 cwd。Profile 拥有字段规则，CLI 解析 Domain 祖先与 Project 归属，不在 Skill 复制继承逻辑。

本流程以查询为主。发现漂移不等于获得修复授权；`.campfire.yaml`、声明 Frontmatter 和自动生成区只能通过 CLI 修改。

## SOP

### 流程总览

```text
当前任务缺什么？
|-- 本机定时任务 -> Tickwork 入口，见下文
|-- 不缺上下文 -> 直接返回原任务
|-- Workspace -> resolve
|-- 目标领域 -> domain list，已知项目则缩小范围
|-- 代码项目 -> project resolve / show，事实核验需要时才 check
`-- 类型或字段契约 -> 类型未知查 document type list；选定后查 profile / inspect
                  |
                  +-- 唯一明确 -> 返回所需上下文
                  `-- 缺失或冲突 -> 说明问题并询问，不猜测或顺手修复
```

### 执行步骤

1. Workspace 不明确才运行 `workspace resolve`；无法唯一确定时询问，首次接入交给 onboarding。
2. 目录未知才查 `workspace domain list`；项目已知使用 `--project <id>`。普通知识与个人任务不强制搜索代码项目。
3. 确实依赖当前代码项目时才运行 `workspace project resolve --path <cwd>`。命中结果同时包含仓库稳定 id；只有 `matched` 是唯一匹配，`remote_matches` 只是候选，不能替代本机路径绑定。
4. 写项目当前事实或诊断漂移时按需 `project show <id>` / `project check <id>`，读取相关证据。不因无关漂移阻断普通文档操作。
5. 类型未知时用 `document type list` 查询当前有效类型、名称和前缀，不猜 type；类型已明确则跳过。字段契约未知才查目标 Profile 或 inspect；list / inspect 自动对账索引，不先跑 Maintenance。

### 本机定时任务入口

用户要求注册、查询、调频、暂停、恢复、删除或排查本机定时任务时，加载 `tickwork-task-management`，通过 Tickwork CLI 管理；不额外查询无关的 Domain、Project 或 Profile。

本机缺少 Tickwork 时，按安装授权运行 `uv tool install tickwork-cli`，要求 Python 3.12+；安装工具或环境缺失时说明问题，不自动提升权限。缺少 Tickwork Skill 时，通过 `tickwork agent install --help` 获取接入契约，核实当前 Agent 的 Hint 和 Skill 目录，预览后按授权确认安装，再读取 Skill。安装资源不代表授权启用任务，已有暂停状态保持不变。

Vault Git 定时同步还需读取 `campfire-workspace-maintenance` 的 `references/git-sync-scheduling.md`，确认 Workspace、同步范围和 `remote_synced` 验收要求；其他定时命令直接进入 Tickwork Skill。具体任务管理流程只维护在 Tickwork Skill 中。

### 命令示例

已知注册 Workspace 为 demo，仅需查看任务契约：

```bash
campfire --workspace demo document profile resolve --type task
```

消费返回的有效字段与候选；不把示例中的 Workspace id 当作默认值。

## 异常与停止条件

- unmatched / ambiguous：澄清身份或归属，不因 remote 相同就选择某个 monorepo 项目。
- 发现未注册项目或漂移：先说明影响；经授权后才选择 create、adopt、bind 或 update，并按该命令真实契约操作，不统一假设都有预览参数。
- 关键事实无证据：标明限制或询问，不返回伪造的已核验状态。

## 完成条件与回报

只返回本次所需的 Workspace、Domain、必要的 Project、字段契约和未决项，不要求完整上下文卡。Project 物理归属不代表自动填写任务的 `related_project`。
