# 定时启动 Codex 或 Claude Code

使用通用 Job 的 argv 启动已安装的 Agent CLI，不新增会话编排。先核对本机 `codex exec --help` 或 `claude --help`，使用绝对程序路径、明确工作目录和非交互模式；stdin 关闭。登录、工具权限与网络必须在实际调度环境中测试，不只在交互终端验证。

- Codex 使用 codex exec，按用户授权配置 sandbox 与工具权限；写任务需允许目标目录写入，跨 Vault/代码目录显式声明。不要默认使用绕过全部权限的选项。
- Claude Code 使用 claude -p，按本机契约配置 allowedTools 和无人应答时的处理；不默认 bypassPermissions。若依赖 Campfire Hint/Skill，不能使用会跳过它们的启动方式却声称已经加载。
- 普通定时任务每次启动新会话，读取最新任务与进展恢复上下文。用户显式要求恢复会话才配置准确的会话 id，不选“最近一次”。

启动任务至少说明：

```text
哪个 Workspace、哪些文档或 tags 范围
    -> 本次允许推进什么、如何验证结果
    -> 进展和阻塞写在哪里、何时停止
```

固定路径直接读；按 tags 查询仅发现候选，不授予执行权。新要求超出授权、多候选无法判定、事实不足或任务已完成时按约定回报后结束。已有主线可以长期或按阶段组织，不强制季度和目录。环境定时任务记录只是记录部署情况，不能当作业务主线或启动配置。

中断可能留下已完成的文件或外部动作。下一次先读取进展并核实，再继续，避免重复产出；不承诺整个 Agent 会话原子回滚。需要人决策时写入已授权的记录位置，仅在有相应授权时使用 human-request。运行记录验证进程，文档和实际产物验证业务结果。

首次上线前分别用真实 Codex、Claude Code 做隔离读取、授权写入和阻塞验收；检查实际加载的指令与 Skill。不能用假 CLI 或另一种客户端通过代替。参见 [Codex 非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)与 [Claude Code 非交互模式](https://code.claude.com/docs/en/headless)。
