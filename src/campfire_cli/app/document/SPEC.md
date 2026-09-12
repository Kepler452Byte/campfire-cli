# Document App SPEC

本模块承载面向用户和 Agent 的文档业务能力，包括单篇检查与格式化、类型契约、Profile 契约、命名和 Frontmatter 治理。

Document App 负责文档自身及其规则；Maintenance App 负责跨文档批量扫描、计划和派生内容同步；Migration App 负责存量结构迁移。纯解析、序列化和路径安全等无业务状态的原子能力保留在 `common/documents/`。

## 当前能力

```text
document/
├── cli/
│   ├── document_cli.py
│   ├── profile_cli.py
│   └── type_cli.py
├── service/
│   ├── document_profile_service.py
│   ├── document_type_service.py
│   ├── document_service.py
│   ├── document_rule_service.py
│   ├── document_scanner.py
│   ├── profile_registry.py
│   ├── type_plan.py
│   ├── type_apply.py
│   ├── frontmatter_plan.py
│   ├── frontmatter_apply.py
│   └── frontmatter_formatter.py
└── repository/
    ├── document_profile_repository.py
    └── document_type_repository.py
```

- `profile`：定义并解析不同文档的属性契约。
- `type`：检查、规划和执行单选类型与文件命名治理。
- `frontmatter`：检查、规划、执行和格式化文档属性。
- `rule`：统一解释类型、Profile、枚举与跨字段不变量。
- `scanner`：统一解释受管根、忽略目录和豁免文件；Document 与 Maintenance 共用。

Document Service 可以被 Maintenance 和 Migration 编排，但不得反向依赖它们。批量计划文件、运行记录、MOC、Base、归档和迁移批次不属于 Document App。

包内默认 Profile 配置是新 Workspace 和显式同步的来源，用户级 `frontmatter-schema.json` 是该 Workspace 当前治理契约。

Profile 只允许一层 `base` 继承。Service 将声明配置编译为完整 `EffectiveProfile`；Validator、Formatter 和 CLI 必须消费同一结果，不得复制字段与枚举。

标准字段用于格式化、补全和校验。默认 `unknown_fields: preserve`：已有业务扩展字段不参与标准排序但必须原样保留，不因尚未建立专属 Profile 而制造全库噪声；确需封闭字段集合的 Profile 可显式设为 `report`。

`document profile sync` 与 `document type sync` 默认只预览，必须使用 `--confirm` 才更新用户级契约。标准契约升级时保留 Workspace 自定义类型和自定义 Profile，同步不修改任何 Workspace 文档。

`document format --path <文档>` 默认只预览字段顺序变化，追加 `--confirm` 后才写入；它不新增、删除或修改属性值。
