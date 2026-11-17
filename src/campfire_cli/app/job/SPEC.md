# Job SPEC

Job 是设备本地的命令执行与原生调度能力，独立于 Workspace 装配。CLI 只适配参数与 JSON；JobService 负责用例、身份与时间；Repository 只持久化调用者提供的数据；消费方 Scheduler Protocol 由三平台 adapter 实现。

```text
job CLI -> JobService -> JobRepository -> jobs.yaml
                     -> Scheduler -> systemd / launchd / Task Scheduler
                     -> Runner -> RunRepository -> jobs/runs.db
```

- jobs.yaml 是唯一执行定义，local.yaml 保存稳定环境 id；runs.db 是可清理且丢失后不可恢复的历史，和可删除重建的 campfire.db 分离。无旧格式兼容或迁移链，替换日志库拒绝活动 Run 和连接。
- manual 不部署、不要求调度器；interval/daily/weekly 使用本地时区与原生会话规则。新建暂停，更新保留状态；无常驻服务、补跑、自动重试或唤醒。
- 写入默认 planned，确认带本次 expected_plan；锁内复核定义和实际原生状态。手动 run 也复核执行摘要。scheduled 入口读取当前定义和启用状态，不复用旧计划；内部标记不构成权限边界。
- 同 Job 和显式绑定同 Workspace 的 Run 使用独立 OS 锁，不覆盖治理写锁；父进程不持有整轮治理写锁或 SQLite 写事务。运行中拒绝修改、删除、compact 和安装环境替换，不强杀来维护。
- workspace_id 显式选择稳定注册，workspace_root 由 CLI 用例解析并保存本机绑定快照；运行前绑定不符则停止，更新重新预览。普通 Job 不猜默认 Workspace。
- 部署只管理带产品/home/id 所有权的条目，runner 携带准确 home 和安装环境；Windows 使用 pythonw 及无控制台子进程。不得提升权限或保存系统密码。
- 子进程 stdin 关闭、输出单独流式记录，上限来自默认配置并明确 truncated。超时终止进程树，进程退出与业务产物分开验收。
- 升级由 System 在 Job 空闲门禁内启动，已有异步升级状态阻止新 Run，避免检查与启动之间竞争；不会开启或恢复 Job。
- Job 变更后的文档维护由可选 Skill 承担：查询成功后更新 Vault `_定时任务/` 下当前环境的一篇 record。文件名使用可读主机名，正文环境 id 核对身份；主机改名由 Skill 定位同 id 原文档后走受管 apply --name，同名异环境停止核实。只记录显式绑定该 Workspace 的任务，不写完整命令、路径、凭据或原始日志；文档不反向部署。
- 环境目录属于系统受管 scope，不声明 Domain；首次写入才创建，无额外总览、MOC 或新文档类型。查询、Runner 和升级不自动写此文档，失败分别报告。
