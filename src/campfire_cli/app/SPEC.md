# App SPEC

业务模块采用 `CLI → Service → Protocol ← Implementation` 单向依赖。CLI 只解析参数、选择输出格式并翻译异常；Service 实现用例；Protocol 由消费方定义；Repository 负责 SQLite 或文件持久化，不作语义判断。

当前模块：

- `migration/`：一次性、大规模、批次化治理。
- `maintenance/`：新增与变更文档的持续维护，归档属于其用例。
- `vault/`：注册、初始化、解析和选择多个 Vault。
