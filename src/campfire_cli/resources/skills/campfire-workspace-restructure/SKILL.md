---
name: campfire-workspace-restructure
description: "按审批计划重构 Campfire Workspace 的已有物理结构；适用于跨领域移动、批量改名、领域拆分或合并和引用更新，不用于日常检查、格式化或 MOC 同步。"
---

# Campfire Workspace Restructure

本 Skill 只处理会改变文档主物理位置或领域结构的一次性重构。日常新增、格式修正、声明补全、MOC、归档和持续检查使用 `campfire-workspace-maintenance`。

先运行 `campfire workspace resolve`，读取目标 Workspace 的 `AGENTS.md`、相关 `_空间.md`、`_领域.md` 和已有 MOC。Agent 负责理解内容并提出目标结构；CLI 负责冻结事实、哈希保护、计划执行、引用更新和验收。

## 工作流

1. 使用 `campfire workspace restructure inventory --scope <path> --batch <id>` 冻结明确范围。
2. 使用 `workspace restructure plan --batch <id>` 生成推断计划。工具不能表达的移动或 Frontmatter 修改写入 YAML/JSON 意图规格，再运行 `plan --spec <file>`。
3. 逐项审查 source、target、Frontmatter Patch、理由和审批状态。删除、合并、根领域拆分、冲突权威判定和无法逆推的语义必须由用户确认。
4. 先运行不带 `--confirm` 的 `workspace restructure apply --batch <id>` 做执行前预检；计划已经明确审批且没有阻塞问题时才追加 `--confirm`。
5. 执行 `workspace restructure verify --batch <id>`，随后加载 `campfire-workspace-maintenance` 运行 `maintenance check` 与 `maintenance sync --dry-run`，审查后刷新派生内容。

## 安全边界

- 不用 Restructure 处理普通增量维护，也不绕过批次计划直接移动受管文档。
- 写入返回 `concurrent-change`、`source-hash-changed` 或 `restructure-config-changed` 时停止，重新 inventory 和 plan。
- 一篇文档只有一个主目标位置；跨领域关系使用链接和自动索引表达。
- 目标冲突、来源缺失、链接歧义或语义不明确时保持未执行并请求确认。
- 报告移动、改名、Frontmatter 变化、引用更新、验证结果和剩余问题。
