# Script SPEC

- CAMPFIRE_HOME/jobs/scripts 下的一个顶级目录表示一个脚本项目，内部允许多级目录；文件是脚本事实来源，不写入 SQLite、任务定义或 Vault。
- CLI 与集中 HTTP 路由共用 ScriptService；服务只列目录、读取文本，不创建、修改、执行或迁移脚本，不依赖 Job、Web 或 Workspace。
- 读取不跟随符号链接和 Windows 目录联接，不允许越界路径或特殊文件。目录单层懒加载，忽略依赖与缓存，大小和条目限制来自 defaults/config.yml。
- Web 在现有页面标签栏复用项目页；内部文件标签保存选择与滚动。CodeMirror 只读，未知语言显示纯文本，文件树顶部统一刷新。失败显示明确状态，不把旧内容表示为最新。
- Agent 维护实际文件；文件变化不自动执行任务，当前预览不代表某次历史运行的源码快照。升级、日志清理和文档索引重建保留 scripts。
