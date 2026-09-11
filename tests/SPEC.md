# Tests SPEC

- Service 单元测试使用内存 Fake Protocol，不访问真实 Vault。
- Repository 与 CLI 集成测试使用临时 Vault 和临时 SQLite。
- 所有写入路径必须覆盖预检失败、幂等、哈希变化和中途异常场景。
