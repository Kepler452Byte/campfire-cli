---
name: campfire-kanban-board
description: "把治理清单类文档改造为 Obsidian Kanban 插件可渲染的看板并用 CLI 验证；适用于用户要求把看板-或清单类文档变成可拖拽泳道视图时，不用于普通文档治理、MOC 与 Base 等生成视图的维护。"
---

# Kanban 看板维护

将已明确的清单内容整理为 Obsidian Kanban 泳道，并用 CLI 检查正文可渲染性与文档合规。不是 MOC、Base 或关系页生成器。

## 执行门禁

用户授权维护目标看板，泳道语义与卡片事实明确；不把整理看板当作批量改任务状态的授权。保留既有卡片和人工修改，关键分类不明时询问。

## 上下文与契约

- Campfire 类型与基础字段由有效 board Profile 管理，结构变更使用 apply；字段未知才 inspect 或 profile show。
- 插件标记 `kanban-plugin` 与 Campfire 基础字段不同。当前 board Profile 保留已有扩展字段，但 apply 不接受未声明字段的赋值；不得据此虚构可用的 --set。
- 已有插件标记保留。缺标记且 Profile 无写入入口时，请用户通过 Obsidian Kanban 插件初始化，不直接改受管 Frontmatter 或假称 CLI 已完成。
- 正文使用二级标题作为泳道、列表项作为卡片；渲染诊断以当前 kanban-check 返回为准，不复制完整解析规则。

## SOP

### 流程总览

```text
读取目标看板与原有分组
|-- 标记或结构前提缺失 -> 使用合法入口；无入口则报告并暂停
`-- 前提满足 -> 按已确认语义 Edit 正文泳道与卡片
                -> kanban-check + document check
                   |-- 有问题 -> 修正有依据的问题；语义不明则询问
                   `-- 通过 -> 必要时局部同步 -> 回报
```

### 执行步骤

1. 读取当前内容，保留卡片事实、链接和进展；泳道名来自用户或原文档语义，不强制套用固定状态表。
2. 类型或基础字段需要变更时 apply 预览，获授权且无问题后以返回哈希确认。插件标记缺失按上文能力边界处理。
3. 用 Edit 最小调整人工正文，不重建 Frontmatter，不修改自动生成区。卡片可以是普通列表或复选框，不把泳道顺序当作机器状态。
4. 执行 kanban-check 与 document check，分别确认渲染与治理结果。
5. 结构写入有 follow_up 时执行实际返回值；仅正文变化时，只有显式关系变化或用户要求刷新派生物才局部 sync，不固定全库维护。

### 命令示例

假设 demo 中目标看板已存在：

```bash
campfire --workspace demo document kanban-check --path "mywork/【Hello World】文档中心/看板-进展.md"
campfire --workspace demo document check --path "mywork/【Hello World】文档中心/看板-进展.md"
```

前者需返回 renderable 为 true，后者需无治理问题；CLI 检查通过不代表已经在人类 Obsidian 客户端实际渲染。

## 异常与停止条件

缺插件标记、缺泳道或卡片位置错误时依据 issues 处理；没有合法字段写入入口时停止该部分。并发编辑后重新读取，不覆盖人类拖拽的新内容；插件正常写回不是文档违规。

## 完成条件与回报

说明正文调整、两项检查结果及是否需要用户在 Obsidian 初始化或查看。MOC、Base 和相关文档仍由 CLI 维护，看板不参与自动重生成；任务状态仍以字段为准。
