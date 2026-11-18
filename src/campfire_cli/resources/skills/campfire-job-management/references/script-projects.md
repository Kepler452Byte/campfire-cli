# 创建和维护脚本项目

用户要求为 Campfire Job 创建或维护多文件脚本时使用。复用已明确的目标、位置和执行授权；缺少会改变脚本行为的关键输入时询问，不从任务名猜业务规则。

```text
script list 取得实际根目录
    -> 文件工具创建 / 维护一个顶级项目目录
    -> 按授权验证入口和依赖
    -> Job 预览并确认 script_project 与执行命令
    -> Web 查看源码；执行 / 启用分别核验授权和结果
```

1. **确定位置**：执行 `campfire script list`，使用返回的 `root`，不硬编码其他设备的路径。默认位置为 `CAMPFIRE_HOME/scripts`。一个顶级目录代表一个项目，名称使用可读的业务名称；项目内可以有任意层级的源码、模板和依赖声明。已有项目先查询和读取，避免同名覆盖；仓库中已有的脚本继续由所属仓库维护，不自动搬迁。
2. **创建文件**：用文件工具在明确的项目目录下创建入口及必要文件。只读 CLI 不负责创建目录，没有 `campfire script create` 或登记步骤。代码、提示词文件和模板各保留一份事实来源；不把文件正文复制到任务定义、SQLite 或 Vault。解释器和依赖由当前设备准备，不把 `.venv`、缓存或凭据当作脚本源码。项目属于本机，不能假设 Vault Git 会同步它。
3. **验证脚本**：按实际语言检查语法、导入和用户授权的行为。优先使用临时输入或无写入模式；运行会修改 Vault、调用 Agent 或访问外部服务时，核对是否已有对应授权。没有执行授权时完成可做的静态检查，并如实报告尚未执行。活动任务结束后再修改它使用的代码。
4. **关联任务**：在 Job JSON 中填写 `script_project`，同时填写真实的 `argv`。关联只决定 Web 打开哪个项目，不会自动选择入口、安装依赖或改变工作目录。需要调用 Codex/Claude Code 时，按 [Agent 执行指引](agent-execution.md) 把调用和提示词放在项目文件中，不填写专用 Agent 字段。更新已有 Job 时保留其他字段、原生启停与 Workspace 绑定；通过 `job create/update --file` 的预览和本次 `expected_plan` 确认。关联变化也要重新预览；解除关联或删除任务不删除脚本。
5. **核验结果**：用 `job show` 核对关联与实际命令，Web「查看脚本」可打开项目页面。`script tree` 返回一层目录，需要时查询下一层；`script read` 返回当前 UTF-8 文本。脚本超大、二进制、链接或不可读取时按实际错误处理。测试成功不自动启用定时任务，执行退出码也不代替产物核验。

下面假设 `script list` 返回 `/absolute/campfire/scripts`，用户已确认创建 growth 项目：

```text
/absolute/campfire/scripts/growth/
├── daily.py
├── helpers/
│   └── study.py
└── requirements.txt
```

维护文件后，可通过只读命令核对：

```bash
campfire script tree growth --path helpers
campfire script read growth --path daily.py
```

任务 JSON 示例；替换当前设备的真实解释器、入口和工作目录，不把这些示例路径直接提交：

```json
{
  "id": "growth-daily",
  "name": "每日成长整理",
  "script_project": "growth",
  "argv": ["/absolute/python", "/absolute/campfire/scripts/growth/daily.py"],
  "cwd": "/absolute/working-directory",
  "schedule": {"kind": "manual"},
  "timeout": 360
}
```

```bash
campfire job create --file /absolute/job.json
campfire job create --file /absolute/job.json --expected-plan <本次预览摘要> --confirm
campfire job show growth-daily
```

工作目录与脚本位置独立，普通 Job 不要求 Workspace；处理 Vault 时显式填写已确认的 `workspace_id`。按用户要求选择手动或定时计划，不把示例的 manual 当作所有任务的固定配置。后续运行与启用沿 Job Skill 的现有门禁执行。
