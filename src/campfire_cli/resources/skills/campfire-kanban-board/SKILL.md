---
name: campfire-kanban-board
description: "把治理清单类文档改造为 Obsidian Kanban 插件可渲染的看板并用 CLI 验证；适用于用户要求把看板-或清单类文档变成可拖拽泳道视图时，不用于普通文档治理、MOC 与 Base 等生成视图的维护。"
---

# Kanban 看板改造

将 `看板-` 前缀或清单类内容文档改造为 Obsidian Kanban 插件（mgmeyers/obsidian-kanban）可直接渲染的看板。治理分类与渲染能力是正交的两件事：`type: board` 表达治理归属，`kanban-plugin` frontmatter 表达渲染形态。

## 渲染契约

```text
---
name: ...
type: board
kanban-plugin: basic
---

## 未排期

- [ ] 卡片内容

## 进行中

- 卡片内容
```

- frontmatter 必须含 `kanban-plugin: basic`，值非空。
- 正文由 `## 泳道名` 标题分区，至少一个泳道。
- 卡片是泳道内的列表项，支持 `- 文本`、`- [ ] 待办`、`- [x] 完成` 与嵌套缩进。
- 泳道之外只允许空行与 HTML 注释；正文文本、游离列表项都无法渲染。

campfire 治理字段照常保留：`kanban-plugin` 是插件键不是 Profile 字段，Profile 对未知字段的策略是保留，`document check` 不会因它报错。

## 改造流程

```text
读取原文档结构与分组
        │
        ▼
把章节重组为泳道：泳道名来自原文档自己的状态分组语义，
未排期 / 进行中 / 已完成 / 搁置只是常见示例，不是固定清单
        │
        ▼
frontmatter 增加 kanban-plugin: basic
        │
        ▼
campfire document kanban-check --path <文档路径>
        │
        ▼ renderable: true
campfire document check --path <文档路径>
        │
        ▼ 治理合规
campfire maintenance sync
```

```bash
campfire document kanban-check --path "mywork/【某项目】文档中心/看板-优化清单.md"
campfire document check --path "mywork/【某项目】文档中心/看板-优化清单.md"
campfire maintenance sync
```

`kanban-check` 返回 `renderable: false` 时按 issues 逐条修复：`kanban-plugin-missing` 补 frontmatter 键；`kanban-lane-missing` 补 `## 泳道` 标题；`kanban-card-outside-lane` 与 `kanban-content-outside-lane` 把内容移入泳道；`kanban-line-not-card` 把游离文本改为列表项。

## 边界

- 看板是人工交互视图：泳道与卡片由人拖拽维护，Agent 不批量再生成、不把泳道排列当作治理事实；插件拖拽写回的文件变更是正常人类编辑，不是并发冲突。
- 需要机器可读状态时仍以 frontmatter 字段为准，泳道位置不进入任何自动化判断。
- MOC、Base、相关文档页仍是唯一生成视图体系，看板不参与治理锁保护的重生成流程。
