# Tests SPEC

- Service 单元测试使用内存 Fake Protocol，不访问真实 Vault。
- Repository 与 CLI 集成测试使用临时 Vault 和临时 SQLite。
- 性能回归测试放 `tests/perf`，标记 `@pytest.mark.perf`；只断言确定性计数，如文件读取次数、子进程派生次数、`sys.modules` 成员，不断言墙钟时间。
- 所有测试默认隔离 Campfire 用户状态，不读取真实 `~/.campfire`、Workspace 注册、Skill 或 Agent Hint。
- CLI 测试验证参数和结构化契约；不把 ANSI、Rich 边框、终端换行或完整中文句子当作稳定 API。
- 所有写入路径必须覆盖预检失败、幂等、哈希变化和中途异常场景。
