---
name: campfire-workspace-onboarding
description: "首次创建或接入 Campfire Workspace；适用于用户给出新目录、已有未接管目录或初始配置异常时，不用于已注册 Workspace 的日常文档治理。"
---

# Campfire Workspace 首次接入

只把用户给出的路径安全地变成可用 Workspace，随后交给已有专项 Skill。不要接管 Domain、创建业务文档、猜测项目归属，或直接编辑 `.campfire.yaml`。

## 路由

```text
目标路径
├── 不存在
│   └── 用户明确要新建 → workspace create
├── 存在且 Manifest 合法
│   └── setup
├── 存在但没有 Manifest
│   └── 用户确认作为 Workspace → setup --id
│       └── 存量目录需要纳管 → workspace-adoption
└── Manifest 无法解析或结构冲突
    └── 报告 CLI 错误并停止，不手改或覆盖 Manifest
```

## SOP

1. 确认目标路径与用户意图：是新建空 Workspace，还是接入已有目录。稳定 Workspace id 不明确时，基于目录名提出一个候选并请求确认。
2. 路径不存在时，只有用户明确要求创建后才运行：

   ```bash
   campfire workspace create --id <workspace-id> --path <path> --default
   ```

   该命令会创建基础目录、首份 Manifest 和本机注册；不要先手工创建目录或声明文件。
   用户明确要求采用标准初始布局时，再读取[标准 Workspace 蓝图](references/标准工作区结构.md)，按其中命令补充可选 Space 并验收 Base。不要据此猜测或创建 Project、Domain、业务文档或正文模板。
3. 路径已存在且 Manifest 合法时运行：

   ```bash
   campfire setup --path <path> --default
   ```

   它恢复本机注册、索引、Skill、Base 和提示词路标。完成后运行一次 `maintenance check --summary`，再交给后续文档流程。
4. 路径已存在但没有 Manifest 时，先得到用户对 Workspace id 和接入意图的确认，再运行：

   ```bash
   campfire setup --path <path> --id <workspace-id> --default
   ```

   `setup` 只创建 Manifest 和本机治理资源，不猜测 Space 或 Domain。已有文档目录需要成为正式内容区时，加载 `campfire-workspace-adoption` 逐个接管；空目录按需要使用 `workspace space/domain create`。
5. `setup` 返回 Manifest 解析、身份冲突或结构错误时，原样报告错误与文件路径，停止。不得删除、覆盖或直接修改 `.campfire.yaml`；只有未来存在专门的 CLI 修复入口时才使用它。

## 完成条件

- `campfire workspace resolve` 能返回目标 Workspace；
- `workspace config check` 与 `maintenance check --summary` 的结果已报告；
- 已有未受管内容明确交给 Adoption，而不是假称已完成接管；
- 报告 Workspace id、根路径、Manifest 状态和下一步。
