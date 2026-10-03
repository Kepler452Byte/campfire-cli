# Common SPEC

本目录放 Workspace 与 Maintenance 等业务模块共同使用的原子能力。

- `documents/`：Markdown、Frontmatter、文档类型、链接、领域、关系和 MOC。
- `database/`：SQLite、模型和数据库迁移机制。
- `filesystem/`：安全路径、原子写入和锁。
- `reports/`：稳定 JSON 与 Markdown 报告渲染。
- `governance/`：跨用例共享的规则引擎、Issue 目录和乐观并发快照；治理规则不得散落在 Service。

`common/` 不承载完整用例流程；检查、计划、执行与验收的编排仍由 `app/` Service 负责。
