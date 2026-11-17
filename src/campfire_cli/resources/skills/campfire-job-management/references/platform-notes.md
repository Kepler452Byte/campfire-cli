# 原生调度诊断

时间使用设备本地时区及原生 DST 规则。Job 不唤醒关机或休眠设备、不补跑、不重试。

- Linux 使用 systemd 用户 service/timer，要求用户 manager 可用；不自行开启 lingering。检查 job doctor、journalctl --user 和对应 timer/service。
- macOS 使用 launchd GUI agent，要求已登录 GUI 会话；无 GUI 的 SSH 会话不保证可用。StartCalendarInterval 在唤醒后可能合并触发，属于系统行为。
- Windows 使用当前用户 Task Scheduler，InteractiveToken/LeastPrivilege，要求用户登录；不保存密码、不提高权限。原生入口使用同安装环境 pythonw，控制台子命令不显示窗口；检查 LastTaskResult 与 Operational 日志。

命令以 argv 运行，无隐式 shell；运行环境不同于终端。可执行文件、cwd 与 CAMPFIRE_HOME 必须正确。安装环境移除可能在记录 Run 前就启动失败，缺历史不等于没有触发；需要检查系统原生诊断。重新安装到其他位置后显式 update Job，核验新的入口，保留原启停状态。

同 Job 和同 Workspace 的自动执行互斥，忙时报告阻塞而非排队。超时终止子进程树。日志达到上限仍排空输出并报告 truncated；历史已清理无法重建，任务定义仍保留。日志清理与 compact 使用预览和实际摘要，不删除活动锁或在运行中删库。
