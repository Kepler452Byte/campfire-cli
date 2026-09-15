---
name: campfire-workspace-restructure
description: "用领域原子命令或审批批次重构 Campfire Workspace；适用于 Domain 移动、合并、空删除、rekey，以及批量文档迁移、领域拆分和引用更新，不用于单篇文档移动或日常维护。"
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
    ├── 移入目标领域/空间 → domain move
    ├── 并入另一领域     → domain merge
    ├── 删除逻辑空领域   → domain delete
    └── 修改稳定机器身份 → domain rekey（高风险）
```

领域级命令默认只输出影响计划，用户明确要求执行且计划无歧义时才追加 `--confirm`：

```bash
campfire workspace domain rename --domain <id> --name <name>
campfire workspace domain move --domain <id> --target <space-or-domain-id>
campfire workspace domain merge --source <id> --target <id>
campfire workspace domain delete --domain <id>
campfire workspace domain rekey --domain <id> --new-id <id> --confirm
```

先运行不带 `--confirm` 的同一命令审查计划；用户已授权且没有 issues 时原样追加 `--confirm`。预览或阻塞结果的 `follow_up` 必须为空；只在确认命令实际写入成功后执行其返回的一个后续。`rename` 只修改领域显示名称，不隐式修改目录或 Project；`move` 只接收目标 Space/Domain 的稳定 ID，由 CLI 推导路径与父子关系。`merge` 一次完成内容迁移、直接子领域改挂和源领域移除；`delete` 只接受没有内容、附件、子领域、Project 绑定或人工声明正文的逻辑空领域。普通操作保持 `domain_id`；只有用户明确要求改变稳定身份时使用 `rekey`。

1. 使用 `campfire workspace restructure inventory --scope <path> --batch <id>` 冻结明确范围。
2. 使用 `workspace restructure plan --batch <id>` 生成推断计划。无 spec 时只推断类型和文件名前缀规范化；返回 `up-to-date` 就结束。只有 Domain 原子命令无法表达的批量文档映射、领域拆分或 Frontmatter Patch 才写 YAML/JSON 意图规格；使用规格前读取[批量重构规格](references/restructure-spec.md)。
3. 逐项审查 source、target、Frontmatter Patch、理由和审批状态。删除、合并、根领域拆分、冲突权威判定和无法逆推的语义必须由用户确认。
4. 先运行不带 `--confirm` 的 `workspace restructure apply --batch <id>` 做执行前预检；计划已经明确审批且没有阻塞问题时才追加 `--confirm`。
5. 执行 `workspace restructure verify --batch <id>`，再只执行命令实际返回的 `follow_up`，不自行追加重复预览或检查。

## 安全边界

- 纯移动必须保持文档内容不变；只有 Spec 明确提供 Frontmatter Patch 时才改写内容。
- `restructure verify` 只验证 source/target 迁移事实；文档 Profile 与 Formatter 合规交给 Maintenance。
- 不用 Restructure 处理普通增量维护，也不绕过批次计划直接移动受管文档。
- 写入返回 `concurrent-change`、`source-hash-changed` 或 `restructure-config-changed` 时停止，重新 inventory 和 plan。
- 一篇文档只有一个主目标位置；跨领域关系使用链接和自动索引表达。
- 领域路径变化必须联动 Project `document_domain`、`.campfire.yaml`、路径引用和子领域解析；不得手工分别维护。
- 不手工删除 `_领域.md`、MOC 或领域目录；合并使用 `domain merge`，删除使用 `domain delete`。
- `domain_id` 是稳定身份；`rekey` 必须更新直接子领域的 `parent_domain`，且必须显式确认。
- 目标冲突、来源缺失、链接歧义或语义不明确时保持未执行并请求确认。
- 报告移动、改名、Frontmatter 变化、引用更新、验证结果和剩余问题。
