# Document App SPEC

本模块承载面向用户和 Agent 的文档业务能力，包括单篇检查与格式化、类型契约、Profile 契约、命名和 Frontmatter 治理。

Document App 负责文档自身及其规则；Maintenance App 负责跨文档统一计划、执行、验收和派生内容同步；Workspace Restructure 用例负责存量结构重构。纯解析、序列化和路径安全等无业务状态的原子能力保留在 `common/documents/`。

## 当前能力

```text
document/
├── cli/
│   ├── document_cli.py
│   ├── profile_cli.py
│   └── type_cli.py
├── schema/
│   └── document_schema.py
├── service/
│   ├── document_apply_service.py
│   ├── document_move_service.py
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
- `inspect`：向 Agent 返回单篇文档的 Domain、类型、有效 Profile 和具体问题。
- `apply`：根据目标路径和类型解析 Profile，不存在时生成文档，已存在时仅应用显式补丁；先完整渲染并校验，追加 `--confirm` 后原子写入。
- `move`：在任意已声明 Domain 之间移动或改名一篇文档，按目标 Profile 对齐可确定的 `domain`/`project` 归属，并更新可确定解析的 Wiki、Markdown 和路径引用。目标 Profile 缺少业务字段时返回 `needs-input`，不猜测。
- `scanner`：统一解释受管根、忽略目录和豁免文件；Document 与 Maintenance 共用。

Document Service 可以被 Maintenance 和 Workspace Restructure 编排，但不得反向依赖它们。批量计划文件、运行记录、MOC、Base、归档和重构批次不属于 Document App。

`apply` 与 `move` 只保证目标文档操作自身有效，不触发 Maintenance。Skill SOP 在写入后显式编排 scoped `maintenance sync` 和 `maintenance check`。所有写入先生成完整 ChangeSet，再经共享 Executor 在乐观锁内提交；多文件操作失败时恢复提交前内容。

包内 `config.yml` 的默认 Profile 与用户级 `~/.campfire/config.yml` 覆盖共同构成当前治理契约。

Profile 只允许一层 `base` 继承。Service 将声明配置编译为完整 `EffectiveProfile`；Validator、Formatter 和 CLI 必须消费同一结果，不得复制字段、枚举与值类型。`value_types` 声明不能由 YAML 形状可靠推断的标量类型，当前支持 `string` 和 `boolean`。

标准字段用于格式化、补全和校验。默认 `unknown_fields: preserve`：已有业务扩展字段不参与标准排序但必须原样保留，不因尚未建立专属 Profile 而制造全库噪声；确需封闭字段集合的 Profile 可显式设为 `report`。

Document 不维护配置副本，也不提供契约同步命令。升级 Python 包会更新默认契约；用户自定义类型和 Profile 只写入 `~/.campfire/config.yml`，并通过 `workspace config check` 验证。

`_空间.md`、`_领域.md` 等声明文件由 Workspace App 按结构契约校验，不是普通 Document，不得套用 base Profile。Document 的单篇命令遇到豁免文件时返回 `not-applicable` 和对应的 Workspace 检查入口。

Document Rule 必须把属性顺序错误作为正式 Issue 暴露；顺序取自同一个 Effective Profile。`document format --path <文档>` 默认只预览字段顺序变化，追加 `--confirm` 后才写入；它不新增、删除或修改属性值。
