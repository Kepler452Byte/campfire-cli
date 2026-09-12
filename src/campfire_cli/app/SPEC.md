# App SPEC

业务模块采用 `CLI → Service → Protocol ← Implementation` 单向依赖。CLI 只解析参数、选择输出格式并翻译异常；Service 实现用例；Protocol 由消费方定义；Repository 负责 SQLite 或文件持久化，不作语义判断。

当前模块：

- `document/`：文档自身、文档规则以及面向用户和 Agent 的文档命令。
- `migration/`：一次性、大规模、批次化治理。
- `maintenance/`：新增与变更文档的持续维护，归档属于其用例。
- `workspace/`：注册、初始化、解析和选择多个 Workspace。
- `skill/`：Campfire SOP Skill 的发现、加载、校验和同步。
- `base/`：Obsidian Base 标准治理视图。
