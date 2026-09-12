# Document Profile App SPEC

本模块展示、解析并同步 Workspace 的文档 Profile 契约。包内默认配置是新 Workspace 和显式同步的来源，用户级 `frontmatter-schema.json` 是该 Workspace 当前治理契约。

Profile 只允许一层 `base` 继承。Service 将声明配置编译为完整 `EffectiveProfile`；Validator、Formatter 和 CLI 必须消费同一结果，不得复制字段与枚举。

标准字段用于格式化、补全和校验。默认 `unknown_fields: preserve`：已有业务扩展字段不参与标准排序但必须原样保留，不因尚未建立专属 Profile 而制造全库噪声；确需封闭字段集合的 Profile 可显式设为 `report`。

`profile sync` 默认只预览，必须使用 `--confirm` 才更新用户级契约。同步不修改任何 Workspace 文档。
