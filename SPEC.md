# Campfire SPEC

本项目是面向工作与学习场景的本地优先人机协作 CLI。产品目标与业务架构以 `ARCHITECTURE.md` 为准。

## 稳定边界

```text
CLI delivery adapter
        ↓
Workspace Restructure / Maintenance Service
        ↓
消费方 Protocol
        ↓
SQLite / Filesystem Implementation
```

- `app/` 放业务模块与 CLI 适配器。
- `common/` 放两个 App 共同使用的文档治理原子能力和技术机制。
- `config/` 放随 Workspace 或运行环境变化的配置。
- `resources/defaults/` 是产品默认规则的 JSON SSOT；Service 不得重复声明可演进的目录、类型、状态、归档或 Issue 规则。
- CLI 通过用户级 registry 管理多个 Workspace，不依赖任何 Workspace 内的工具目录。
- Markdown 是内容事实来源；`~/.campfire/workspaces/<id>/config/` 是治理契约来源；`~/.campfire/campfire.db` 是唯一数据库，保存 Workspace/Project 注册数据、按 Workspace 隔离的可重建索引和工作流状态。
- JSON 仅承载配置、关键状态备份和有限的最近变更。
- Workspace Restructure 与 Maintenance 不共享含义模糊的业务入口。
- CLI 不直接实现业务规则；Service 不依赖 Typer。
- 字段、枚举和跨字段不变量统一由 DocumentRuleService 解释；Maintenance 与 Workspace Restructure 不得复制规则值。
- Frontmatter Profile 只允许一层 `base` 配置继承；Profile Loader 编译完整规则，Validator 与 Formatter 共用同一个 EffectiveProfile。
- 所有写入默认预检，语义计划默认未审批。
- 写入用例必须在治理锁内复核生成计划时的内容哈希，发现外部变化时拒绝覆盖。

代码风格参考 `templates/fastapi-template`，但不引入 HTTP、WebSocket、认证和异步数据库等无关能力。

## 版本规范

Campfire 使用语义化版本：

```text
主版本.次版本.补丁版本
0.17.0
│  │  └── patch：兼容的缺陷修复
│  └───── minor：兼容的新能力或治理契约变化
└──────── major：不兼容的公共接口或数据模型变化
```

- 已发布版本不可原地修改；同一版本号必须对应唯一、可重复构建的代码和资源。
- 只修复既有行为时增加补丁版本，例如 `0.17.0 -> 0.17.1`。
- 新增 CLI 能力、改变治理契约或增加可选公共字段时增加次版本，例如 `0.17.x -> 0.18.0`。
- 删除或重命名公共命令、改变不可兼容的数据格式时增加主版本；`0.x` 阶段仍应显式记录破坏性变化。
- 配置文件的 `version` 独立于 Python 包版本；只有配置结构或解释语义变化时递增。
- PyPI、源码标签、构建产物和 CLI 报告的版本必须一致。

## 设备边界

- 可跨设备共享的是 Workspace、Space、Domain 和 Project 的稳定身份与逻辑关联，不是本机文件路径。
- `git_remote_url`、Project id、文档 Domain 和治理契约版本属于可移植元数据。
- `local_path`、Skill 安装位置、锁、缓存、索引和运行报告属于设备本地状态，不得写入可移植元数据。
- Decision 及其事件当前属于创建它的本机工作流状态，不要求跨设备同步。
- 新设备接管已有 Workspace 时，从可移植元数据恢复逻辑关系，再在本机独立绑定项目路径并重建 SQLite 派生状态。
- Vault 根目录的 `.campfire.yaml` 是唯一可移植 Manifest；禁止在其他文件重复维护 Workspace/Project 便携元数据。
- `.campfire.yaml` 禁止保存 Vault 或代码仓库的本机绝对路径。
- `campfire setup` 必须幂等完成接入、契约/Skill/Base 同步和健康检查；未绑定项目必须显式报告，不得猜测路径。

## Domain 重构不变量

- `domain_id`、`name` 和 `path` 分别表示稳定身份、显示名称和物理位置，不得隐式绑定。
- 普通 rename 和 move 不得改变 `domain_id`；只有显式 `domain rekey` 可以修改稳定身份。
- 修改领域名称不得默认修改 Project 名称；必须由 `--project-name` 明确表达。
- 领域路径变化必须同步 Project `document_domain`、`.campfire.yaml` 和路径引用。
- `rekey` 必须同步直接子领域的 `parent_domain`。
- 领域级写入默认只预览，只有显式 `--confirm` 才执行。
