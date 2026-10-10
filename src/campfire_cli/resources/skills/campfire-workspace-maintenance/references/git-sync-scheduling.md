# Vault Git 的 Tickwork 定时同步 SOP

Campfire 负责提交并推送 Vault；Tickwork 负责本机任务注册、三平台调度与执行记录。管理 Vault 定时同步时读取本页，再加载 `tickwork-task-management`。其他本机定时命令直接进入 Tickwork Skill，不需要 Campfire bootstrap。

## 流程总览

```text
定时同步需求 -> 核实 Workspace、范围、频率与已有入口
             -> Tickwork Skill：查询任务和调度能力
             -> 按授权预览并管理任务
             -> 核对调度状态、执行记录和 remote_synced
```

## 执行步骤

1. 复用已确认的 Workspace、频率和授权。启用定时同步代表允许提交并推送整个 Vault 的可提交改动；仅写文档、升级或查询不构成启用授权。暂停、删除或调频不先运行同步，不顺便恢复已暂停任务。
2. 按 Tickwork Skill 查询已有任务和原生调度状态，并核对 Obsidian Git、cron 等其他同步入口。按实际执行参数识别目标，不只看名称。同一工作树只保留一个自动同步入口；旧入口的交接按 Tickwork Skill 处理，不自动改动未知系统任务。
3. 新建或恢复前，核实本机 Campfire 绝对路径、Vault 注册与根目录、Git identity/upstream 和非交互凭据。按已有同步授权预览、确认一次手动同步，核对 `remote_synced: true`。Tickwork 不可用时报告缺少工具；安装按用户授权执行，不另写平台定时脚本。
4. 任务 argv 使用 Campfire 绝对路径及 `--workspace <id> workspace git sync --confirm`，cwd 使用本机 Vault 根目录。定时执行不携带固定的旧 `--expected-plan`。频率和 timeout 按用户需求及 Tickwork 当前契约选择；五分钟只是示例，不是自动启用的默认值。不同设备分别解析路径，不复制其他设备的路径或凭据。使用自定义 `CAMPFIRE_HOME` 时，先确认任务实际运行环境指向正确配置。
5. 通过 Tickwork CLI 预览并确认创建或修改，使用本次返回的计划摘要。新任务默认暂停，获得启用授权后才恢复；已暂停任务调整后保持暂停。参数、文件格式和平台限制以 CLI 帮助及 Tickwork Skill 为准，不手写原生调度配置。
6. 用 Tickwork 查询部署与启用状态；获执行授权后手动运行并检查 history、result 和 logs。退出码为零只代表命令执行成功，仍需从本次 Campfire JSON 核对 `remote_synced: true`。报告任务 id、Workspace、间隔、启用状态和最近运行结果，不用历史成功替代本次结果。

## 失败与完成边界

先区分未触发、可执行文件或凭据不可用、Tickwork 执行失败与 Campfire 同步失败。调度及日志问题交给 Tickwork Skill；同步问题按 Campfire JSON 的阶段、提示与冲突路径处理，不强推或自动选一方。正在同步时优先等待结束，不为修改任务强杀 Git。

任务定义保存在本机 Tickwork 配置，不写入 Vault `.campfire.yaml` 或 Campfire `~/.campfire/local.yaml`；运行记录和日志由 Tickwork 管理。用户会话、休眠与关机的触发限制见 Tickwork 平台说明，不承诺设备离线时同步，也不默认扩大权限。Campfire setup/upgrade 只更新资源，不创建或启用任务。
