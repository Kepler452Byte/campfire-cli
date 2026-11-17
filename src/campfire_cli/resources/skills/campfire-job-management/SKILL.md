---
name: campfire-job-management
description: 管理本机手动或定时命令、启动 Codex/Claude Code、查询运行日志，并按环境维护 Vault 的定时任务记录；不负责分派主线或管理远程设备。
---

# Campfire 本机 Job

通过 `campfire job` 管理当前设备的命令。Job 定义在本机，Vault 中的记录不部署任务；普通脚本、Campfire 和 Agent CLI 使用同一执行机制。

## 写入门禁

复用用户已明确的操作、执行范围与启用授权，只询问缺少的信息。创建配置、执行测试和启用周期任务是不同动作；已有持续执行授权不逐次重问。文档、发布、远端推送等权限按用户约定分别判断，不因查到主线标签扩大范围。运行中等待完成，不强杀来修改配置。

## 上下文与契约

- 已知命令契约直接使用，未知时读目标 `--help`。普通 Job 不要求 Workspace；Vault 工作显式填写稳定 workspace_id，查询时使用根级 `--workspace`，不从 cwd、任务名或默认 Workspace 猜绑定。
- 输入为 JSON 文件：id、绝对可执行程序的 argv 数组、绝对 cwd、schedule 和 timeout；可选 workspace_id，workspace_root 由 CLI 解析。无隐式 shell，需要时显式调用 shell。运行环境来自系统调度器，不依赖终端 PATH 或 shell 初始化；凭据使用客户端自己的登录或安全环境。
- manual 无原生条目；interval 为整分钟 60..86400 秒，daily/weekly 按设备本地时间。新定时 Job 暂停，更新保持启停；不补跑、不重试、不唤醒机器。平台会话或启动失败时按需读 [平台诊断](references/platform-notes.md)。
- Job 定义在 CAMPFIRE_HOME/jobs.yaml，环境 id 在 local.yaml，历史与日志在 jobs/runs.db。索引 campfire.db 可删除重建，不影响 Job。不要在有活动运行时删除日志库或锁。

## SOP

### 流程总览

```text
明确目标和已有授权 -> 已有 Job 先 list/show -> 新配置写 JSON
    |
    v
创建/更新/启停/删除：预览 -> 同一输入 + expected_plan + confirm
    |
    +-- 已获执行授权 -> run 预览 -> 当前摘要确认 -> result/logs + 实际产物
    +-- 已获启用授权 -> resume 预览与确认（测试不自动启用）
    |
    v
涉及 Vault 的配置变更成功 -> 查询本环境该 Workspace 的完整清单
    |
    +-- 成功 -> 更新 _定时任务/ 下自己的环境文档
    +-- 失败 -> 保留原记录，分别报告配置结果与清单待补写
```

### 执行步骤

1. 读取已有 Job 后最小修改；新 Job 明确命令、cwd、模式与超时。定时任务需要时用 job doctor 检查会话条件；manual 不先要求可用调度器。不修改未知或外来的系统条目。
2. 写操作默认预览。确认时带回本次 expected_plan 与 --confirm；过期则重新预览，不沿用旧摘要。run 同样预览并确认，检查实际 run.status、退出码和返回的 result/logs follow_up，失败运行也保留可查询入口。自定义 CAMPFIRE_HOME 在每次调用及后续动作中保持一致。
3. 同 Job 不重叠；同一 Workspace 的已绑定 Job 在执行层互斥，遇占用等待结束后核实，不无条件重试或删锁。运行锁与治理写锁不同，Agent 仍按文档 Skill 的普通写入规则操作。
4. 需要启动 Codex 或 Claude Code 时读取 [围绕 Vault 执行 Agent](references/agent-execution.md)。明确任务入口、允许动作、产物和停止条件，先在隔离或已授权范围测试。启动成功、模型自报和退出 0 都不等于业务验收。
5. 用户要求启用才执行 resume 的预览与确认；原已暂停的更新后保持暂停。移除旧 Tickwork 时先记录执行要求、暂停并等运行结束、删除旧条目，再用普通 Job 命令重建；不迁移历史、不保留双入口。
6. 成功创建、更新、暂停、恢复或删除 Workspace Job 后，按下节维护环境文档。Job 改绑 Workspace 时核验 before/after，分别刷新原、新 Workspace 中当前环境的记录。纯查询不写文档，每次定时触发不强制改记录。

## 环境任务文档

通过 `campfire --workspace <id> job list` 取得本机 environment、显式筛选后的 jobs 和 inventory_document；只使用成功、无未核实项的完整结果。不要从共享文档部署 Job，不把查询失败写成没有任务。

默认位置为 Vault 根 `_定时任务/记录-<主机名>.md`，以实际返回路径为准；一环境一篇 record，不维护额外总览。缺少 environment.id 时报告尚未建立本机 Job 身份，不临时生成标识、改名或写入其他环境文件。

不存在时，按授权使用 document apply 创建 record：--path 用返回路径、--type record、--set 填 description；确认携带预览哈希。随后在正文锚点后写易读的环境标题与内容，只执行实际 follow_up。name 随文件名使用可读主机名，环境 id 只在正文核对。已存在时读最新正文并直接编辑，保留 Frontmatter、生成区和人工备注。

正文包含环境名称和 id、平台/时区、最后完整核验时间；任务表只列 id、用途、频率、实际启停、最近运行结果。manual 如需展示则单列。无历史写“无可用运行记录”；完整成功查询为空写“当前无定时任务”，保留文档。用途从已知事实概括，未知保留说明，不复制完整命令、绝对路径、环境变量、凭据或日志。

目标不存在时，先检查该目录是否已有正文 environment id 相同的记录；唯一匹配时用 document apply --name 的预览、哈希和计划确认改名，保留备注和受管引用，不重复创建。多条匹配或同名文档属于其他环境时停止核实，不自动加随机后缀。主机名中的文件名非法字符由 CLI 替换为连字符。

文件中标识不符、外部变化或 Git 冲突时停止对应写入并核实；不覆盖其他环境，不自动归档离线环境或推送 Vault。Job 配置成功但文档失败时分别回报，重新查询后仅补文档，不重复创建任务。

## 命令示例

示例假设 /absolute/job.json 已由用户确认，创建一个 manual Job；具体路径和摘要使用实际值：

```bash
campfire job create --file /absolute/job.json
campfire job create --file /absolute/job.json --expected-plan <本次摘要> --confirm
campfire job run example
campfire job run example --expected-plan <本次运行摘要> --confirm
campfire --workspace demo job list
```

启停、更新、删除、cleanup 和 compact 也使用自己的新预览。清理历史不清理定义；compact 要求无运行。保留策略以配置和 cleanup 返回值为准，不复制另一套默认值。

## 完成条件与回报

区分配置是否写入、调度是否启用、本次执行结果、业务产物是否核验及环境记录是否更新。导航刷新和 Git 远端同步分别回报。认证失效、权限不足或环境不可用时记录阻塞，不更换账号或默认绕过权限。升级沿现有 campfire upgrade，不复制 Tickwork 升级流程；活动 Job 需先结束再替换环境。
