---
name: campfire-context-bootstrap
description: "在 Agent 首次读写 Campfire 文档时解析 Workspace 和当前 Project，检查项目注册元信息及漂移；不负责写文档、执行任务或调度 Agent Session。"
---

# Campfire 上下文启动

仅在当前 Session 首次需要读取或沉淀 Campfire 文档时运行一次。目标是向后续文档 Skill 提供可靠的 Workspace、Project、源码路径和文档中心，不把运行态 Session 信息写进 Project 元数据。

## 状态机

```text
首次需要 Campfire 文档能力
            │
            ▼
  campfire workspace resolve
            │
            ▼
当前目录是否属于已注册 Project？
            │
  campfire workspace project resolve --path <cwd>
        │                    │
      matched          unmatched / ambiguous
        │                    │
        ▼                    ▼
 project check       自动读取 Git 与候选项目
        │                    │
    ┌───┴───┐          能唯一确定？
    │       │            │       │
   ok   needs-review     是       否
    │       │            │       │
    ▼       ▼            ▼       ▼
完成上下文  提议修复   提议注册  询问用户
                \        /          │
                 用户确认           │
                     │               │
                     ▼               ▼
             project add/update   停止猜测
                     │
                     ▼
                  重新 check
```

## 工作流

1. 运行 `campfire workspace resolve`。无法唯一解析 Workspace 时询问用户，不擅自使用无关默认值。
2. 在当前工作目录运行 `campfire workspace project resolve --path <cwd>`。`matched` 才表示唯一项目；`unmatched` 和 `ambiguous` 都不能猜测。
3. 唯一匹配后运行 `campfire workspace project check <id>`，把 Project 元信息和实际源码、Git、文档中心进行比较。
4. CLI 能读取的信息先自行读取：Git 根目录、origin remote、默认分支、注册项目列表和现有文档中心。只询问用户无法可靠推断的稳定身份与归属。
5. Project 未注册且文档中心不存在时，向用户展示建议的 `id`、`name`、Workspace、`document_domain`、`local_path`、remote、默认分支和依据。先运行不带 `--confirm` 的 `campfire workspace project create` 展示计划，用户确认后追加 `--confirm`；命令只初始化项目根领域和项目总览，不虚构业务子领域。已有文档中心使用 `project add` 接入。
6. Project 已注册但发生漂移时，区分定位信息与稳定身份。local path、同仓库 remote 或默认分支变化可以建议 `project update`；Project id、Workspace、文档中心、合并关系或归档状态必须明确确认。
7. 写入后重新运行 `project check`。只有结果为 `ok`，或已向用户明确说明不影响当前文档工作的剩余问题，才把上下文交给后续 Skill。

## 当前 Project 元信息

CLI 维护：稳定 `id`、`workspace_id`、显示 `name`、Vault 内 `document_domain`、`git_remote_url`、本机 `local_path`、`default_branch` 和 `status`。合法状态以 CLI 为准；本 Skill 不复制枚举。

## 输出

向后续流程提供一张紧凑上下文卡：Workspace id 与路径、Project id 与名称、源码路径、文档中心、匹配依据、检查状态和待用户确认项。未匹配到代码项目不阻止处理纯知识文档，但必须明确 Project 为空。

本 Skill 不创建知识、项目或任务文档，不执行代码任务，也不分派、恢复或跟踪 Agent Session。
