---
name: campfire-workspace-adoption
description: "把 Vault 内外已有文档文件夹首次接管为 Campfire Domain；适用于安全盘点、结构判断、一次性接管和验收，不用于已受管领域的日常维护或再次重构。"
---

# Campfire Workspace 接管

把尚未受管的已有文件夹接入一个粗粒度 Domain，不在同一次接管中做语义拆分。已受管领域的迁移与合并使用 workspace-restructure。

## 执行门禁

来源、目标和接管授权明确，领域身份与归属有依据。存在关键歧义先询问；待确认文档也需记录授权。外部来源必须保持不变，不因接管授权删除原文件。

## 上下文与契约

Workspace 已知直接复用，未知才 resolve。Vault 内来源可原地接管，外部来源需目标 Workspace 相对路径。CLI 推导 Space 与最近父 Domain；Project 由 Manifest 绑定和祖先拓扑解析，不写入 Domain 声明。

## SOP

### 流程总览

```text
阅读来源，明确一个目标 Domain
|-- 归属或授权不明 -> 询问，暂不写入
`-- 已明确 -> domain adopt 预览
               |-- issues / 冲突 -> 停止并处理，不手工绕过
               `-- 计划一致且已授权 -> 原命令追加 --confirm
                                      |-- 失败或结果不明 -> 核查实际状态
                                      `-- adopted -> 实际 follow_up -> 回报
```

### 执行步骤

1. 阅读授权范围内真实文档，确定稳定 id、名称、类型与目标位置，不凭目录名推断项目。
2. Vault 内使用 `domain adopt --source`；外部来源额外提供 `--target-path`。根 Domain 提供治理策略；未知参数查当前命令帮助。
3. 审查预览清单、目标和 issues。用户已授权且无问题时，对同一输入追加 `--confirm`，不另建接管批次。
4. 成功后只执行实际 follow_up；需要子领域拆分时另走重构流程，不能把进一步治理算作已完成。

### 命令示例

假设 Workspace demo 已存在，`mynote/待接管示例` 是用户授权原地接管、尚无领域声明的文件夹：

```bash
campfire --workspace demo workspace domain adopt --source "mynote/待接管示例" --id knowledge-example --name "接管示例" --type knowledge-domain --governance knowledge-base
campfire --workspace demo workspace domain adopt --source "mynote/待接管示例" --id knowledge-example --name "接管示例" --type knowledge-domain --governance knowledge-base --confirm
```

仅在预览无阻塞且符合授权时执行第二条。确认返回 adopted 后才按返回的 scope 维护派生物。

## 异常与停止条件

- 软链接、目标冲突、暂存冲突和源哈希变化必须阻塞，不绕过检查。
- 外部内容由 CLI 暂存、复制和核验，Agent 不手工移动或删除来源。
- 执行结果不确定时核查声明和文件状态，不盲目重复接管。
- 纯接管不授权语义拆分、内容改写或来源清理。

## 完成条件与回报

以 adopted 和实际清单校验为依据，报告目标 Domain、文件数量、原始来源保留情况、follow_up 结果和剩余治理问题。日常文档问题不伪装成已全部修复。
