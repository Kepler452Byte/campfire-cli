---
name: campfire-skill-maintenance
description: 创建、修改和审查随 Campfire CLI 分发的内置 Skill，核对命令契约、受管清单、Agent Hint 与安装副本。适用于维护 Campfire 源码中的 Skill。
---

# 维护 Campfire 内置 Skill

内置 Skill 的维护入口是 Campfire 源码仓库的 `src/campfire_cli/resources/skills/`。Vault 自定义技能在各 Workspace 的技能库中维护。

## 执行门禁

改动前确认目标 Skill、预期行为和写入范围。用当前命令帮助、实现或测试核对涉及的契约。发布、升级和同步真实客户端资源按各自的授权执行。

## SOP

### 流程总览

```text
定位包内 Skill -> 核对契约和触发条件 -> 修改源码 -> 隔离验证
                                      |
                                      `-- 新增或更名 -> 核对受管清单和引用
```

### 执行步骤

1. 在源码仓库读取 Skill 目录下的 `SPEC.md`。新建或重写时参考同目录的 `TEMPLATE.md`。优先检查现有 Skill 能否承接该场景，再决定是否新增。
2. 修改目标 `SKILL.md` 及实际受影响的资源。保留与目录名一致的 `name`，让 `description` 说明触发场景。字段和命令契约以 CLI 为准，正文只记录工作流需要的选择与边界。
3. 新增或更名时核对 `src/campfire_cli/resources/defaults/config.yml` 的 `skills.managed_skills`，搜索旧名称的调用方。确需让 Agent 从全局提示找到新入口时，同步编辑 `src/campfire_cli/resources/agent_hint.md`。运行副本由资源对齐生成。
4. 在隔离环境使用当前 checkout 运行 `skill list`、`skill sync` 和 `skill check`。将 `CAMPFIRE_HOME`、`CAMPFIRE_SKILL_TARGETS` 和需要验证的 `CAMPFIRE_AGENT_HINT_PATH` 指向临时位置。验证涉及的命令示例和实际使用场景。同步返回冲突时先核对目标文件的归属。

## 完成条件与回报

回报源码改动、受管清单和验证结果。涉及 Hint 时，分别说明受管区块写入和客户端新会话实际加载的验证结果。
