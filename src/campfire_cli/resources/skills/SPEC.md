# Skill Resources SPEC

本目录是 Campfire 托管 Skill 的唯一事实来源。全局 Agent Skill 目录是由 `campfire skill sync` 生成的运行副本，不在副本中直接维护托管 Skill。

## 职责链

```text
conversation-router → 已知路径的正文小改 → edit
                    → 治理流程 → context-bootstrap
                    → document-capture / task-management
                    → document apply → workspace-maintenance
                    → workspace-restructure / kanban-board 等专项流程
```

- Skill 负责加载时机、事实门禁、业务语义和工作流程。
- CLI Profile 负责字段、枚举、类型、顺序和条件必填；Skill 不复制这些契约。
- 已知唯一存在路径的正文读取和小改直接使用文件工具，不启动 bootstrap。
- 创建正式文档、修改 Frontmatter 或显式变更类型使用 `document apply`。
- 发现结构化文档集合使用 `document list`，理解单篇文档的确定关系使用 `document inspect`；两者自行 reconcile，不先运行 Maintenance。
- `document list` 不承担正文关键词、模糊匹配或相关性排序；需要正文内容时由 Agent 按返回路径读取或使用文件搜索。
- 写入命令保持原子性；Skill 只执行命令实际返回的 scoped `maintenance sync`，诊断或发布验收时再显式 `check`。
- 已存在的 Workspace、Space、Domain 和 Project 使用稳定 ID 选择；路径只用于新位置、具体文件、外部输入和显式扫描范围。

## 新增或修改 Skill checklist

1. description 说清加载时机、适用边界和不负责的事。
2. 一个 Skill 只覆盖一个可辨识的工作阶段，新故事先尝试放入现有 Skill。
3. 不复制 Profile、Manifest 或其他 Skill 的唯一事实来源。
4. 不叫 Agent 手写 Frontmatter，不硬编码可演进枚举。
5. 命令示例使用稳定公共入口，并写清 dry-run、确认和失败语义。
6. 资源修改后运行 `campfire skill check` 与 `campfire skill sync`，验证全局副本。
