# Document App SPEC

本模块承载面向用户和 Agent 的文档业务能力。当前首个子能力是展示、解析并同步 Workspace 的文档 Profile 契约；后续文档创建、命名、格式化与单篇校验也应由本 App 对外提供。

Document App 负责文档自身及其规则；Maintenance App 负责跨文档批量扫描、计划和派生内容同步；Migration App 负责存量结构迁移。纯解析、序列化和路径安全等无业务状态的原子能力保留在 `common/documents/`。

包内默认 Profile 配置是新 Workspace 和显式同步的来源，用户级 `frontmatter-schema.json` 是该 Workspace 当前治理契约。

Profile 只允许一层 `base` 继承。Service 将声明配置编译为完整 `EffectiveProfile`；Validator、Formatter 和 CLI 必须消费同一结果，不得复制字段与枚举。

标准字段用于格式化、补全和校验。默认 `unknown_fields: preserve`：已有业务扩展字段不参与标准排序但必须原样保留，不因尚未建立专属 Profile 而制造全库噪声；确需封闭字段集合的 Profile 可显式设为 `report`。

`document profile sync` 默认只预览，必须使用 `--confirm` 才更新用户级契约。同步不修改任何 Workspace 文档。
