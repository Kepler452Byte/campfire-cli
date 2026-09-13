# Tests SPEC

- Service 单元测试使用内存 Fake Protocol，不访问真实 Vault。
- Repository 与 CLI 集成测试使用临时 Vault 和临时 SQLite。
- 性能回归测试放 `tests/perf`，标记 `@pytest.mark.perf`；只断言确定性计数，如文件读取次数、子进程派生次数、`sys.modules` 成员，不断言墙钟时间。
- 所有写入路径必须覆盖预检失败、幂等、哈希变化和中途异常场景。
