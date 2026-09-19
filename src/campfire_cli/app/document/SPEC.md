# Document App SPEC

本模块承载面向用户和 Agent 的文档业务能力，包括单篇检查与格式化、类型契约、Profile 契约、命名与 Frontmatter 治理，以及设备本地可重建的文档查询投影。

Document App 负责单篇文档及其规则；Maintenance App 负责检查、派生内容同步和归档；Workspace Restructure 负责存量批量结构重构。纯解析、序列化和路径安全等无业务状态的原子能力保留在 `common/documents/`。

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
│   ├── document_service.py       # 公开应用入口
│   ├── document_scanner.py       # 统一受管范围
│   ├── rules/                    # Profile、字段校验与格式
│   ├── index/                    # 新鲜度、投影构建与查询
│   └── mutation/                 # 写入、移动与关系改写
└── repository/
    ├── document_index_repository.py
    ├── document_profile_repository.py
    └── document_type_repository.py
```

- `profile`：定义并解析不同文档的属性契约。
- `profile resolve --type` 用于新建前查询，`--path` 用于已有文档，两者互斥；和 apply 共用 ProfileRegistry。`show` 只按 Profile 名查询，不把 type 当作同义参数，不新增领域覆盖机制。
- `type`：检查、规划和执行单选类型与文件命名治理。
- `frontmatter`：检查、规划、执行和格式化文档属性。
- `rule`：统一解释类型、Profile、枚举与跨字段不变量。
- `index`：Service 只编排新鲜度、generation 和查询，Builder 只把 Markdown 属性、Domain/Project 上下文与 `related_docs`转换为确定性投影；配置、拓扑或解析器变化时完整重建，普通文件变化时调用时 reconcile。
- `list`：按 Project、Domain、类型和生命周期对索引做精确 AND 筛选；返回全部生命周期，不读取或复制正文。
- `inspect`：向 Agent 返回单篇文档的 Domain、类型、有效 Profile、具体问题，以及 outgoing、incoming、unresolved 及入度、出度。
- `apply`：根据目标路径和类型解析 Profile，不存在时生成文档，已有 Frontmatter 时只应用显式补丁，无 Frontmatter 时保留正文并补齐完整契约；先完整渲染并校验，追加 `--confirm` 后原子写入。
- `template`：只继承 base Profile，必须位于所属 Domain 的 `_模板/`；Domain 归属由物理路径解析，不在 Frontmatter 复制模板作用域或继承关系。
- `move`：在任意已声明 Domain 之间移动一篇文档，按目标 Profile 对齐可确定的 `domain`/`project` 归属，并只更新 `related_docs` 的精确路径引用。目标 Profile 缺少业务字段时返回 `needs-input`，不猜测。
- `rename`：保持一篇文档的物理目录与 Domain 归属不变，根据逻辑标题重算类型前缀文件名，并在同一变更集中更新 `name` 与可确定引用。目标存在时阻止，不覆盖或自动编号。
- `scanner`：统一解释受管根、忽略目录和豁免文件；Document 与 Maintenance 共用。

Document Service 可以被 Workspace Restructure 编排，但不得反向依赖 Maintenance。批量计划文件、运行记录、MOC、Base、归档和重构批次不属于 Document App。

Markdown 是内容事实源，Frontmatter `related_docs` 是文档关系唯一 SSOT，SQLite 是按 Workspace 隔离的查询投影。Document Index Repository 不解析 Markdown、Profile 或 Domain，只原子持久化文档、关系和 generation 快照。索引不得复制正文；相似度、全文关键词和相关性排序不属于当前契约，未来只能以独立 suggestions/search 契约扩展。

`list` 与 `inspect` 自行保障查询新鲜度，不返回索引维护 follow-up。文件 size/mtime 只用于发现变化候选，content hash 表示内容版本；Space/Domain 声明、Project 根 Domain 映射或有效治理配置变化必须触发完整重建。Project 归属只从 Manifest 的稳定根 Domain id 与 Domain 祖先拓扑解析，不读取 Domain 声明或文档 Frontmatter 中的重复值。MOC 与其他生成文档不作为普通内容节点。

`related_docs` 可选，省略或空数组均表示无出向关联。每项为完整 Workspace 相对 POSIX Wiki 路径并保留 `.md`；拒绝别名、锚点、越界、无效目标、自引用和重复项。目标删除保留 unresolved 路径，恢复后重新解析；来源删除移除出向边。正文链接、Canvas 和相似度不参与此协议。

索引增量提交只更新变化文档与对应来源边；目标可用性变化只更新受影响目标边。查询在 SQL 层筛选，反向查询按 target 索引，索引 generation 通过事务复核，避免旧快照覆盖新投影。

改路径的确认必须带预览返回的 `expected_plan`，摘要覆盖来源、目标和全部引用方的预期哈希与写入内容。可捕获文件异常回滚；文件成功但索引失败返回 write_performed 与修复提示，dirty 索引在后续读取重建。不承诺跨文件写入具备断电原子性。

`apply` 与 `move` 保证目标及受影响的字段引用在同一文件变更集提交，不触发 Maintenance。结果只在派生状态可能变化时返回一个最小 scope 的 `maintenance sync`；调用方不得固定追加 check。所有写入先生成完整 ChangeSet，再经共享 Executor 在乐观锁内提交；多文件操作失败时恢复提交前内容。

包内 `config.yml` 的默认 Profile 与用户级 `~/.campfire/config.yml` 覆盖共同构成当前治理契约。

Profile 只允许一层 `base` 继承。Service 将声明配置编译为完整 `EffectiveProfile`；Validator、Formatter 和 CLI 必须消费同一结果，不得复制字段、枚举与值类型。`value_types` 声明不能由 YAML 形状可靠推断的标量类型，当前支持 `string` 和 `boolean`。

Document 写入接口不得要求 Agent 猜测 Frontmatter 输入契约：

- `--set` 是统一的显式字段补丁入口。CLI Adapter 只拆分首个 `=`、拒绝空字段名和重复字段，并保留原始 value；它不解释 Profile，也不使用 YAML 隐式类型推断。
- Document App 解析一次目标 EffectiveProfile，并由 apply 与 move 共用的值解码器转换补丁：enum、string 和 date 保留原始字符串，boolean 只接受明确的 `true` 或 `false`，list 只接受严格 JSON 数组。
- Profile 与 Rule Service 继续拥有字段类型、合法值和业务校验，不保存命令行字符串。命令帮助负责 Shell 展示方式，并为列表值给出 `--set 'tags=["tag1","tag2"]'` 形式的最小例子。
- 输入错误统一返回稳定错误码、字段、实际值、期望类型和可直接照抄的参数示例；apply 与 move 不得分别构造两套解码或诊断。
- apply 在 Profile 已明确时并列收集可确定的禁用字段、缺失字段与类型错误；无效赋值不再重复报同字段缺失。有错误不写入且 follow-up 为空；只有缺失输入时返回 needs-input，含其他问题时返回 blocked 并保留 missing_fields。
- 文档相对路径始终以 Workspace 根解析，不受 cwd 影响；apply 的 domain-missing 返回实际解析路径和带 Workspace 的领域发现入口，不默认枚举全量候选。
- 不因输入格式不直观而增加 `--tags`、`--sources` 等字段专用参数，也不把逗号字符串静默猜成列表。
- 现有文档的有效 Profile 已由 `document inspect` 返回。Skill 只在字段契约未知时安排一次 `inspect → apply`；契约已知的补丁直接 apply，正文小改不进入本接口。

标准字段用于格式化、补全和校验。默认 `unknown_fields: preserve`：已有业务扩展字段不参与标准排序但必须原样保留，不因尚未建立专属 Profile 而制造全库噪声；确需封闭字段集合的 Profile 可显式设为 `report`。

Document 不维护配置副本，也不提供契约同步命令。升级 Python 包会更新默认契约；用户自定义类型和 Profile 只写入 `~/.campfire/config.yml`，并通过 `workspace config check` 验证。

`_空间.md`、`_领域.md` 等声明文件由 Workspace App 按结构契约校验，不是普通 Document，不得套用 base Profile。Document 的单篇命令遇到豁免文件时返回 `not-applicable` 和对应的 Workspace 检查入口。

Document Rule 必须把属性顺序错误作为正式 Issue 暴露；顺序取自同一个 Effective Profile。`document format --path <文档>` 默认只预览字段顺序变化，追加 `--confirm` 后才写入；它不新增、删除或修改属性值。
