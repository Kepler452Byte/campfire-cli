# Vault Git 的 Job 定时同步

Campfire 的 workspace git sync 负责提交和远端同步，job 负责本机调度与日志。管理定时同步时读取本页和 campfire-job-management，不安装 Tickwork，也不手写平台调度脚本。

## 流程

```text
已有同步授权与目标 -> 核对 Workspace、频率及其他同步入口
    -> 预览实际 Git 状态 -> 按授权测试并核验 remote_synced
    -> Job 创建/更新预览 -> 确认 -> 按授权启用
    -> 查询本机实际状态与运行结果 -> 更新当前环境记录
```

1. 启用定时同步代表允许提交并推送整个 Vault 的可提交新增、修改与删除。仅文档编辑、升级或查询不构成授权；已有持续同步授权直接复用。暂停、调频或删除不先执行 Git 同步，不顺便恢复暂停状态。
2. 查询已有 Job，并核对插件、cron 等其他同步入口；同一工作树只保留一个自动同步入口。旧 Tickwork 按用户已确认范围由 Agent 记录要求、暂停等待、移除，再普通新建；不双启动、不迁移历史。
3. 核实 Campfire 绝对路径、Workspace 注册、Git identity/upstream 和实际调度环境的非交互凭据。按授权测试本次 git sync，核对 remote_synced=true；缺 upstream、冲突或认证失败时按真实阶段处理，不强推、不自动解决冲突。
4. Job JSON 的 argv 为绝对 Campfire 程序路径及 --workspace <id> workspace git sync --confirm，cwd 为本机 Vault 根目录，同时填写 workspace_id。频率与 timeout 来自用户需求；定时执行不携带陈旧 Git expected_plan。自定义 CAMPFIRE_HOME 在原生运行环境中保持正确，必要时显式 wrapper，不复制其他设备路径或凭据。
5. Job 配置沿当前预览和摘要确认；新建默认暂停，获执行及启用授权后测试并 resume。更新保持启停状态；按实际 Job 结果与本次 Git JSON 验收，进程退出 0 不代替 remote_synced。
6. 配置变更后按 Job Skill 更新 Vault `_定时任务/` 中当前环境的文档。区分调度已启用、本次执行结果、远端已同步和环境记录是否更新；失败只补失败步骤。文档记录不反向部署任务，setup/upgrade 不启用任务。
