---
name: campfire-workspace-restructure
description: "按审批计划重构 Campfire Workspace 的已有物理结构；适用于批量跨领域迁移、批量改名、领域拆分或合并和引用更新，不用于单篇文档移动、日常检查、格式化或 MOC 同步。"
---

# Campfire Workspace Restructure

本 Skill 只处理会改变文档主物理位置或领域结构的一次性重构。日常新增、格式修正、声明补全、MOC、归档和持续检查使用 `campfire-workspace-maintenance`。

先运行 `campfire workspace resolve`，读取目标 Workspace 的 `AGENTS.md`、相关 `_空间.md`、`_领域.md` 和已有 MOC。Agent 负责理解内容并提出目标结构；CLI 负责冻结事实、哈希保护、计划执行、引用更新和验收。

## 工作流

先识别被重构的对象，不要把领域目录改名拆成大量逐文件移动：

```text
重构意图
├── 单篇内容文档     → document move（交回 Maintenance Skill）
├── 一批内容文档   → inventory / plan / apply / verify
└── 已声明 Domain
    ├── 修改人类名称     → domain rename
    ├── 修改物理位置     → domain move
    └── 修改稳定机器身份 → domain rekey（高风险）
```

领域级命令默认只输出影响计划，用户明确要求执行且计划无歧义时才追加 `--confirm`：

```bash
campfire workspace restructure domain rename --domain <id> --name <name>
campfire workspace restructure domain rename --domain <id> --name <name> --rename-directory --project-name <name> --confirm
campfire workspace restructure domain move --domain <id> --target-path <path> --parent-domain <id> --confirm
campfire workspace restructure domain rekey --domain <id> --new-id <id> --confirm
```

`rename` 默认只修改领域显示名称；`--rename-directory` 或 `--target-path` 才修改目录，`--project-name` 才修改关联 Project 展示名称。普通 rename/move 必须保持 `domain_id`；只有用户明确要求改变稳定身份时使用 `rekey`。

1. 使用 `campfire workspace restructure inventory --scope <path> --batch <id>` 冻结明确范围。
2. 使用 `workspace restructure plan --batch <id>` 生成推断计划。工具不能表达的移动或 Frontmatter 修改写入 YAML/JSON 意图规格，再运行 `plan --spec <file>`。
3. 逐项审查 source、target、Frontmatter Patch、理由和审批状态。删除、合并、根领域拆分、冲突权威判定和无法逆推的语义必须由用户确认。
4. 先运行不带 `--confirm` 的 `workspace restructure apply --batch <id>` 做执行前预检；计划已经明确审批且没有阻塞问题时才追加 `--confirm`。
5. 执行 `workspace restructure verify --batch <id>`，再按命令返回的 `follow_up` 加载 `campfire-workspace-maintenance`，预览并刷新派生内容。

## 安全边界

- 纯移动必须保持文档内容不变；只有 Spec 明确提供 Frontmatter Patch 时才改写内容。
- `restructure verify` 只验证 source/target 迁移事实；文档 Profile 与 Formatter 合规交给 Maintenance。
- 不用 Restructure 处理普通增量维护，也不绕过批次计划直接移动受管文档。
- 写入返回 `concurrent-change`、`source-hash-changed` 或 `restructure-config-changed` 时停止，重新 inventory 和 plan。
- 一篇文档只有一个主目标位置；跨领域关系使用链接和自动索引表达。
- 领域路径变化必须联动 Project `document_domain`、`.campfire.yaml`、路径引用和子领域解析；不得手工分别维护。
- `domain_id` 是稳定身份；`rekey` 必须更新直接子领域的 `parent_domain`，且必须显式确认。
- 目标冲突、来源缺失、链接歧义或语义不明确时保持未执行并请求确认。
- 报告移动、改名、Frontmatter 变化、引用更新、验证结果和剩余问题。
