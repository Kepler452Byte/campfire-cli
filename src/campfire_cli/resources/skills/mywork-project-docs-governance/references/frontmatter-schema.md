# 项目文档 frontmatter 字段契约

`mywork/【项目】文档中心/` 下新建的项目 Markdown 文档，以及被 MOC 标记为当前有效的存量项目文档，必须使用以下基础字段。`assets/`、`a_skill/`、代码、生成物等非项目文档不适用。

```yaml
---
name: 文档名称
description: 一到两句话概述本文的目标、范围或当前结论
project: 项目标识
domain: 领域标识
type: tech-spec
status: draft
lifecycle: proposed
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: []
related: []
superseded_by: []
archive_requested: false
---
```

## 字段规则

| 字段 | 必填 | 规则 |
|---|---|---|
| `name` | 是 | 面向阅读者的中文名称，应与正文一级标题一致。 |
| `description` | 是 | 一到两句话概述本文解决的问题、适用范围或当前结论；用于人和 Agent 的快速筛选，不复制正文目录。 |
| `project` | 是 | 项目稳定标识，使用小写英文和连字符，例如 `joyit-ai-gateway`。 |
| `domain` | 是 | 项目内领域的稳定标识，使用小写英文和连字符，例如 `mcp-gateway`；总览统一为 `overview`。 |
| `type` | 是 | 只能使用下表中的类型枚举。 |
| `status` | 是 | 只能使用 `draft`、`current`、`archived`。 |
| `lifecycle` | 是 | 只能使用 `maintained`、`proposed`、`completed`、`archived`。 |
| `created` | 是 | 文档首次创建日期，格式为 `YYYY-MM-DD`，创建后不修改。 |
| `updated` | 是 | 最后一次实质内容更新日期，格式为 `YYYY-MM-DD`。 |
| `tags` | 是 | 标签列表；没有标签时写 `[]`。 |
| `related` | 是 | 相关文档的 wikilink 列表；没有时写 `[]`。 |
| `superseded_by` | 是 | 替代当前文档的 wikilink 列表；无替代时写 `[]`。 |
| `archive_requested` | 否 | `true` 表示请求归档；缺省等同 `false`。标记时不提前修改 `status`。 |

## 归档扩展字段

待归档或已归档文档使用以下字段：

```yaml
archive_requested: true
archive_reason: superseded
archive_requested_by: human
archive_requested_at: 2026-09-07
archived_at:
```

- `archive_reason` 枚举：`superseded`、`completed`、`cancelled`、`obsolete`、`merged`、`project-closed`。
- `archive_requested_by` 可选值为 `human` 或 `agent`，用于审计标记来源。
- `archive_requested_at` 是提出归档请求的日期。
- `archived_at` 由执行脚本在归档完成时写入。
- `superseded` 或 `merged` 必须提供非空 `superseded_by`。
- 已归档文档保留 `archive_reason`，并将 `archive_requested` 重置为 `false`。

## 文档类型

| `type` | 文件名前缀 | 用途 |
|---|---|---|
| `moc` | `MOC-` | 项目或领域导航索引。 |
| `product-spec` | `产品-` | 当前产品定位、范围、用户与需求。 |
| `tech-spec` | `技术-` | 当前技术架构、接口、机制与约束。 |
| `decision` | `决策-` | 已作出的取舍、边界和结论。 |
| `plan` | `计划-` | 尚待实施或持续推进的工作安排。 |
| `issue` | `问题-` | 缺陷、风险、故障或待解决问题。 |
| `record` | `记录-` | 会议纪要、测试结果、调研、复盘和踩坑记录。 |

## 状态与生命周期组合

- 当前产品、技术、决策和 MOC：`status: current`，通常配 `lifecycle: maintained`。
- 当前实施计划或待解决问题：`status: current`，配 `lifecycle: proposed`。它们是当前的计划或问题，但不是当前已实现行为。
- 已完成且仍值得保留的记录：`status: current`，配 `lifecycle: completed`。
- 已被替代或仅作历史参考的文档：`status: archived`，配 `lifecycle: archived`，并填写 `superseded_by` 或在正文开头说明归档原因。

路径与状态的约束：当前目录中的 `status: archived` 是待修复异常；`archive/` 中的文档一律按历史资料检索，即使其元数据尚未补齐。正常归档必须通过 `archive_requested: true` → 检查 → 执行完成，不使用日期自动决定失效。

类型专属字段可以追加在基础字段之后，例如会议记录的 `attendees`。不得使用中文值替代基础枚举，如 `status: 草稿`、`status: 已完成`。
