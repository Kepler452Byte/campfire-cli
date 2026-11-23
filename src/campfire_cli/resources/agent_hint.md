## Campfire 文档协作

本机提供 campfire CLI（`campfire --help`）。仅在用户的文档、任务或 Workspace 工作适用时使用，按意图加载对应 Skill，不把 Skill 清单当作固定流水线。

- 首次接入或修复 Workspace 用 campfire-workspace-onboarding；上下文缺失才用 campfire-context-bootstrap。
- 文档记录或更新用 campfire-document-capture，普通任务用 campfire-task-management；周清单分流和持续主线维护可选 campfire-task-mainline。其他文档意图由 campfire-conversation-router 路由。
- 当前任务可能适用 Workspace 的业务 Skill 且 Workspace 已明确时，运行 `campfire --workspace <id> skill list --source workspace`。按名称和描述选择一项，用文件工具读取返回路径的 `SKILL.md`，再按正文引用读取必要资源。已知入口时直接读取；目录为空或无合适 Skill 时继续原任务。
- 已知唯一路径的正文读取与小改直接用文件工具，保留 Frontmatter、声明及生成区；创建和结构变化走 CLI。字段契约未知时按 Skill 获取，不从 tree 固定开始探索。
- 治理检查、导航刷新及 Vault Git 同步用 campfire-workspace-maintenance；同一 Workspace 的治理写操作串行执行，只消费实际返回的 follow_up。
- 文档或任务维护不等于授权实施任务、归档或推送。导航刷新与 Git 远端同步分别回报，失败检查 status、issues 和实际写入结果。
- 本机命令或定时执行用 campfire-job-management；按环境维护 Vault 的 `_定时任务/` 记录，普通 Job 不要求 Workspace。
- 维护 Campfire 随包内置 Skill 用 campfire-skill-maintenance。

具体参数、写入门禁、模板、关系与同步规则在对应 Skill 中按需读取。升级使用 campfire upgrade；离线对齐资源使用 campfire upgrade --skip-package。安装了资源不代表当前客户端已加载，新会话入口与核验见产品说明。
