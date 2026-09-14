---
name: campfire-workspace-adoption
description: "把 Vault 内外已有文档文件夹首次接管为 Campfire Domain；适用于安全暂存、结构判断、接管计划和验收，不用于已受管领域的日常维护或再次重构。"
---

# Campfire Workspace Adoption

本 Skill 只负责把一个尚未受管的已有文件夹接入 Campfire。接管完成后，格式治理交给 `campfire-workspace-maintenance`，后续移动、改名、拆分或合并交给 `campfire-workspace-restructure`。

## 路由

```text
来源文件夹
├── Vault 外 → inventory --confirm 安全复制到 _收件箱/待接管/<batch>
└── Vault 内 → inventory 原地冻结事实，不复制
                 │
                 ▼
       Agent 阅读内容并设计粗粒度 Domain
                 │
                 ▼
       plan → apply 预检 → apply --confirm → verify
                 │
                 ▼
       Maintenance 格式治理 / Restructure 子领域拆分
```

## SOP

1. 运行 `campfire workspace resolve`，确认唯一 Workspace。
2. `campfire workspace adopt inventory --source <folder> --batch <id>` 只读盘点。外部目录审查复制清单后追加 `--confirm`；不得手工移动或删除外部原目录。
3. 阅读真实文档，确认 Space、目标路径、稳定 `domain_id`、领域名称、治理类型及可选 Project。无法确定唯一归属时先询问用户或创建 Decision。
4. 使用 `campfire workspace adopt plan` 建立粗粒度目标 Domain。不要在接管阶段假装自动完成语义分类；需要多个子领域时，接管根领域后再使用 Restructure。
5. 运行不带 `--confirm` 的 `apply` 审查最终计划；用户已经明确授权且没有冲突时追加 `--confirm`。
6. 运行 `verify`，再按 apply 返回的 `follow_up` 加载 Maintenance Skill，显式刷新派生视图和索引，并处理标题、摘要、类型、Frontmatter 和归档问题；需要拆分子领域时加载 Restructure Skill。

## 安全边界

- 外部来源只复制到暂存区，绝不修改或删除原目录。
- 软链接、目标冲突、暂存内容冲突或源哈希变化必须阻塞。
- 接管计划一次建立一个粗粒度 Domain；语义拆分由 Agent 提案并走独立重构计划。
- CLI 原子管理复制、哈希、声明、初始 MOC 与 Project/Manifest 联动；派生视图和索引由 `follow_up` 显式刷新，Agent 负责理解正文。
- 验收前不得宣称接管完成；报告复制数量、目标 Domain、剩余治理问题和原始来源是否保留。
