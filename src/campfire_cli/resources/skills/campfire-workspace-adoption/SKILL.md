---
name: campfire-workspace-adoption
description: "把 Vault 内外已有文档文件夹首次接管为 Campfire Domain；适用于安全盘点、结构判断、一次性接管和验收，不用于已受管领域的日常维护或再次重构。"
---

# Campfire Workspace Adoption

本 Skill 只负责把一个尚未受管的已有文件夹接入 Campfire。接管完成后，日常格式、单篇改名或移动交给 `campfire-workspace-maintenance`；领域拆分或合并交给 `campfire-workspace-restructure`。

## 路由

```text
来源文件夹 → Agent 阅读内容并设计一个粗粒度 Domain
          → domain adopt 预览 → 同命令追加 --confirm
          → 按 follow_up 同步 / 必要时再拆分
```

## SOP

1. 运行 `campfire workspace resolve`，确认唯一 Workspace。
2. 阅读真实文档，确认目标位置、稳定 `domain_id`、领域名称和领域类型。CLI 从目标路径推导 Space 与最近父 Domain；Project 通过 Manifest 根 Domain 绑定和祖先拓扑解析，不写入 Domain 声明。无法确定唯一归属时先询问用户或创建 `human-request`。
3. Vault 内原地接管运行一次 `campfire workspace domain adopt --source <folder> --id <id> --name <name> --type <type> [--governance <policy>]`；外部来源额外提供 `--target-path <workspace-relative-path>`。审查文件清单、推导出的目标和 issues。
4. 用户已授权且没有冲突时，对完全相同的命令追加 `--confirm`。不要拆成 inventory/plan/apply/verify，也不要创建持久化接管批次。
5. 成功后只执行结果返回的 `follow_up`；需要多个子领域时，再加载 Restructure Skill。

## 安全边界

- 外部来源经临时隐藏目录完成复制与哈希校验，成功后直接落到目标 Domain；绝不修改或删除原目录，也不保留接管批次状态。
- 软链接、目标冲突、暂存内容冲突或源哈希变化必须阻塞。
- 接管计划一次建立一个粗粒度 Domain；语义拆分由 Agent 提案并走独立重构计划。
- CLI 原子管理复制、哈希、声明、初始 MOC 与 Project/Manifest 联动；派生视图和索引由 `follow_up` 显式刷新，Agent 负责理解正文。
- 命令成功返回 `adopted` 且目标声明、MOC 与清单文件均通过校验后才宣称完成；报告文件数量、目标 Domain、剩余治理问题和原始来源是否保留。
