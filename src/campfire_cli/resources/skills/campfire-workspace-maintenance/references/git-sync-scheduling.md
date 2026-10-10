# Vault Git 系统定时同步 SOP

只在管理定时同步时读取通用步骤和当前平台章节。示例 Workspace 是 `personal`，间隔是五分钟，必须替换为用户选择。使用本机系统调度器，不新增 Campfire 守护进程。

## 通用步骤与完成条件

1. 复用已确认的 Workspace、频率和授权。开启定时同步代表允许提交并推送整个 Vault 的可提交改动；仅要求写文档、升级或查看任务不构成开启授权。暂停、删除和调整按用户指定范围执行，不先运行同步。
2. 查当前用户的已有任务及 Obsidian Git、cron 等其他自动同步。按实际执行参数识别目标，不能只看名称；同一工作树只保留一个自动同步入口。旧示例的 `campfire-vault-sync.timer` 也可能存在，不另建一份重复运行。只修改已核实归属的任务。
3. 新建或恢复前，确认 `campfire` 和 `git` 可执行路径、Vault 注册、Git identity/upstream 与非交互凭据。先预览 `campfire --workspace personal workspace git sync`，范围符合授权后确认同步并核对 `remote_synced: true`。定时动作使用 `--confirm`，不携带以前的 `--expected-plan`。
4. 以 Workspace id 区分任务；下面名称适用于默认 Campfire 用户目录。如果使用自定义 `CAMPFIRE_HOME`，在任务环境中明确传入，并用不同任务名称区分，不能在不同设备复制绝对路径或凭据。系统配置和日志放本机，不能放入 Vault 根 `.campfire.yaml` 或 `~/.campfire/local.yaml`。
5. 新建后查看调度器实际配置并手动触发一次，等待结束，核对退出码及远端结果。注册成功、任务等待中和 `local_commit` 都不是推送成功的证据。暂停需停止后续触发；正在同步时优先等待完成，避免强杀 Git。删除仅移除本任务配置，保留 Vault 和诊断日志。

报告任务名称、平台、Workspace、频率、启用状态、最近执行结果和日志入口。调频不能顺便恢复已暂停任务；升级不能启用旧任务。桌面示例依赖用户会话，关机期间不会同步；需要退出登录后运行时，另行配置对应系统账户与凭据，不默认扩展到管理员或服务账户。

## Linux：systemd 用户任务

用 `command -v campfire` 核实下面 `ExecStart` 的绝对路径；包含空格的路径使用双引号。先检查已存在的目标：

```bash
systemctl --user list-timers --all
systemctl --user cat campfire-vault-sync-personal.service campfire-vault-sync-personal.timer
```

缺少任务时，创建 `~/.config/systemd/user/campfire-vault-sync-personal.service`：

```ini
[Unit]
Description=Campfire Vault Git sync (personal)

[Service]
Type=oneshot
ExecStart=%h/.local/bin/campfire --workspace personal workspace git sync --confirm
TimeoutStartSec=5min
```

创建同目录 `campfire-vault-sync-personal.timer`：

```ini
[Unit]
Description=Campfire Vault Git sync timer (personal)

[Timer]
OnStartupSec=2min
OnUnitInactiveSec=5min
Unit=campfire-vault-sync-personal.service

[Install]
WantedBy=timers.target
```

五分钟从上一次运行结束计算，允许 systemd 的定时精度误差。先用 `systemd-analyze --user verify <service绝对路径> <timer绝对路径>` 检查配置，再按开启授权执行：

```bash
systemctl --user daemon-reload
systemctl --user enable --now campfire-vault-sync-personal.timer
systemctl --user start campfire-vault-sync-personal.service
systemctl --user show campfire-vault-sync-personal.service -p Result -p ExecMainStatus
journalctl --user -u campfire-vault-sync-personal.service -n 50 --no-pager
```

查看状态使用 `list-timers --all`、`is-enabled`、`is-active` 和日志。调频修改 timer 的 `OnUnitInactiveSec`，`daemon-reload` 后仅在原任务 active 时 restart timer；暂停中的任务保持暂停。

```bash
# 暂停；已运行的 service 可以自然完成。
systemctl --user disable --now campfire-vault-sync-personal.timer
# 恢复。
systemctl --user enable --now campfire-vault-sync-personal.timer
```

删除时先暂停并等待 service 结束，再删除已核实的上述两个文件，执行 `daemon-reload` 和 `reset-failed`（只指定本任务）。用户 manager 必须运行；服务器退出登录后运行可由管理员启用 lingering，不由 Campfire 自动设置。SSH agent 环境需要在用户 service 中可用，不能假定终端里的环境已被继承。

## macOS：当前用户 LaunchAgent

任务标识为 `local.campfire.vault-sync.personal`，文件为 `~/Library/LaunchAgents/local.campfire.vault-sync.personal.plist`。用 `command -v campfire` 核实绝对路径。先查看已有 plist、`launchctl print gui/$(id -u)/local.campfire.vault-sync.personal` 和 `launchctl print-disabled gui/$(id -u)`。

缺少任务时创建上述 plist，替换示例中的 `/Users/YOU` 与实际可执行路径；用 XML 转义路径中的 `&` 等字符：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.campfire.vault-sync.personal</string>
  <key>ProgramArguments</key><array>
    <string>/Users/YOU/.local/bin/campfire</string>
    <string>--workspace</string><string>personal</string>
    <string>workspace</string><string>git</string><string>sync</string><string>--confirm</string>
  </array>
  <key>StartInterval</key><integer>300</integer>
  <key>StandardOutPath</key><string>/Users/YOU/Library/Logs/Campfire/personal-sync.out.log</string>
  <key>StandardErrorPath</key><string>/Users/YOU/Library/Logs/Campfire/personal-sync.err.log</string>
</dict></plist>
```

先创建日志目录并 `plutil -lint` 检查 plist。仅按启用授权执行，已加载时不重复 bootstrap：

```bash
mkdir -p "$HOME/Library/Logs/Campfire"
plutil -lint "$HOME/Library/LaunchAgents/local.campfire.vault-sync.personal.plist"
launchctl enable "gui/$(id -u)/local.campfire.vault-sync.personal"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.campfire.vault-sync.personal.plist"
launchctl kickstart "gui/$(id -u)/local.campfire.vault-sync.personal"
launchctl print "gui/$(id -u)/local.campfire.vault-sync.personal"
tail -n 50 "$HOME/Library/Logs/Campfire/personal-sync.out.log" "$HOME/Library/Logs/Campfire/personal-sync.err.log"
```

等待进程结束，再看 `last exit code` 与本次日志 JSON，不要把历史成功当成本次成功。LaunchAgent 在登录会话运行，休眠会影响触发；没有 GUI 会话的服务器不能直接照搬 `gui/` 示例。凭据和 Git 的 PATH 必须在该会话可用，必要时通过 plist 的 `EnvironmentVariables` 设置本机 PATH 或 `CAMPFIRE_HOME`，不存令牌。

暂停先 `launchctl disable gui/<uid>/<label>`，待当前同步结束，再 `launchctl bootout gui/<uid>/<label>` 卸载已加载任务。恢复执行 enable，未加载时 bootstrap。调频修改 `StartInterval` 秒数，已加载任务等结束后 bootout/bootstrap；原先 disabled 的保持 disabled。删除先暂停、卸载，再删除已核实 plist，保留日志。不使用 `kickstart -k` 强杀正在运行的同步。

## Windows：Task Scheduler

使用 PowerShell ScheduledTasks 模块。任务放 `\`，名称 `Campfire-VaultSync-personal`。先查看当前任务的 Actions、Triggers、Principal 和 State；不存在时才注册，不用 `-Force` 覆盖未知任务：

```powershell
$taskName = 'Campfire-VaultSync-personal'
Get-ScheduledTask -TaskPath '\' -TaskName $taskName -ErrorAction SilentlyContinue |
    Format-List TaskName, State, Actions, Triggers, Principal
```

以下使用当前已登录账户和实际 CLI 绝对路径，不保存密码、不要求最高权限。任务只在该账户登录时运行；权限或组织策略阻止注册时报告原因，不自动换 SYSTEM 账户。

```powershell
$campfirePath = (Get-Command campfire -CommandType Application -ErrorAction Stop).Source
$action = New-ScheduledTaskAction -Execute $campfirePath -Argument '--workspace personal workspace git sync --confirm'
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -StartWhenAvailable
Register-ScheduledTask -TaskPath '\' -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings
Start-ScheduledTask -TaskPath '\' -TaskName $taskName
Get-ScheduledTask -TaskPath '\' -TaskName $taskName
Get-ScheduledTaskInfo -TaskPath '\' -TaskName $taskName
```

等待运行结束，用 `LastRunTime` 区分是否实际执行，`LastTaskResult` 为 0 才是进程成功；非零查看任务计划程序的 History（可能需启用历史记录）。直接可执行动作不会保留 CLI stdout/stderr：排障时在同一账户及环境中手动运行 CLI，捕获 JSON 和 `$LASTEXITCODE`，核对 `remote_synced`。若需每次保存 JSON，可按用户日志需求使用本机 PowerShell 包装脚本重定向日志，并显式 `exit $LASTEXITCODE`；不把它写进 Vault，不把包装脚本成功误当成 CLI 成功。

调频创建新 `$trigger`，用 `Set-ScheduledTask -TaskPath '\' -TaskName $taskName -Trigger $trigger` 更新，核对原 Disabled 状态仍保留。暂停与恢复：

```powershell
Disable-ScheduledTask -TaskPath '\' -TaskName $taskName
Enable-ScheduledTask -TaskPath '\' -TaskName $taskName
```

删除先 Disable，等正在执行的动作结束，核对目标后 `Unregister-ScheduledTask -TaskPath '\' -TaskName $taskName -Confirm:$false`。不默认 Stop 强杀 Git。自定义环境和 SSH agent 需要在任务实际账户可用；不要假定其他终端中临时设置的环境能被任务继承。

## 失败排查与参考

先区分未触发、找不到可执行文件、凭据不可用和 CLI 返回的同步失败。按 JSON 的 `phase`、`code`、提示与冲突路径处理：只有本地提交成功时仍未同步；不要强推或自动选冲突一方。修复后重新预览和确认，再恢复用户要求的调度；未解决时报告失败，不无条件循环重试或自动追加新任务。日志增长按本机日志策略处理，不记录凭据。

平台参数以本机 `man systemd.timer`、`man launchctl` 或 PowerShell `Get-Help` 为准：

- [systemd timer](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)
- [Apple LaunchAgent 配置](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
- [Windows 定时触发](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasktrigger)
- [Windows 任务设置](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset)
