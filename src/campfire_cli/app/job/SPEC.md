# Job SPEC

Job 是设备本地的命令执行与原生调度能力，独立于 Workspace 装配。CLI 只适配参数与 JSON；JobService 负责用例、身份与时间；Repository 只持久化调用者提供的数据；消费方 Scheduler Protocol 由三平台 adapter 实现。

```text
CLI / web/api -> JobService -> JobRepository -> jobs/jobs.db (jobs)
                     -> Scheduler -> systemd / launchd / Task Scheduler
                     -> Runner -> RunRepository -> jobs/jobs.db (runs, logs)
```

- jobs/jobs.db 是任务事实来源，jobs、runs、logs 共用一个 JobDatabase；local.yaml 保存稳定环境 id。只初始化缺失的新库，现有库必须符合当前表契约，不兼容或损坏时明确阻塞，不删库、不转换。旧存储未切换时给出诊断，不把它显示为空任务；不解析旧定义或自动导入。历史清理只删除已完成 runs 及关联 logs；删除任务保留其历史。
- name 是可选显示名称，id 保持稳定；argv 是程序与参数的唯一执行契约。Agent 调用和提示词由用户脚本维护，不保留 Agent 专用字段、命令编译层或历史格式转换。
- Web 及 CLI --detach 通过独立 Runner 执行；取得锁并创建 Run 后握手，调用方确认启动才执行用户命令。Web 关闭不终止任务，活动 Web 阻止替换安装环境。
- manual 不部署、不要求调度器；interval/daily/weekly 使用本地时区与原生会话规则。新建暂停，更新保留状态；无常驻服务、补跑、自动重试或唤醒。
- 写入默认 planned，确认带本次 expected_plan；锁内复核定义和实际原生状态。手动 run 也复核执行摘要。scheduled 入口读取当前定义和启用状态，不复用旧计划；内部标记不构成权限边界。
- 同 Job 和显式绑定同 Workspace 的 Run 使用独立 OS 锁，不覆盖治理写锁；父进程不持有整轮治理写锁或 SQLite 写事务。运行中拒绝修改、删除、compact 和安装环境替换，不强杀来维护。
- workspace_id 显式选择稳定注册，workspace_root 由 CLI 用例解析并保存本机绑定快照；运行前绑定不符则停止，更新重新预览。普通 Job 不猜默认 Workspace。
- 部署只管理带产品/home/id 所有权的条目，runner 携带准确 home 和安装环境；Windows 使用 pythonw 及无控制台子进程。不得提升权限或保存系统密码。
- 子进程 stdin 关闭、输出单独流式记录，上限来自默认配置并明确 truncated。超时终止进程树，进程退出与业务产物分开验收。
- 升级由 System 在 Job 空闲门禁内启动，已有异步升级状态阻止新 Run，避免检查与启动之间竞争；不会开启或恢复 Job。
- 用户需要 Vault 快照时由可选 Skill 查询后维护 `_定时任务/` 下当前环境的一篇 record，不要求每次变更都刷新。文件名使用可读主机名，正文环境 id 核对身份；主机改名由 Skill 定位同 id 原文档后走受管 apply --name，同名异环境停止核实。只记录显式绑定该 Workspace 的任务，不写完整命令、路径、凭据或原始日志；文档不反向部署。
- 环境目录属于系统受管 scope，不声明 Domain；首次写入才创建，无额外总览、MOC 或新文档类型。查询、Runner 和升级不自动写此文档，失败分别报告。

- script_project 是可选的本机脚本项目关联，参与任务计划复核；不改变 argv 的执行含义，不从复杂命令推断关联，也不把脚本内容复制进任务定义。创建或更新关联时核实项目存在，清除关联不删除文件。
