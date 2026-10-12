# System SPEC

System 编排 setup、升级与结果核验，消费 Workspace、Agent Resources 和 Base 的公开能力。Container 只装配依赖，CLI 只解析参数与输出 JSON。

- version、--version/-V 共用安装版本，不创建用户状态或连接数据库；tree 从真实命令生成。
- setup、upgrade 保留默认执行，先内部预检，不新增审批参数。
- upgrade --skip-package 完全离线；包和资源阶段分别报告并持久化。
- 包更新启动返回 planned 与 operation_id；agent upgrade-status 查询实际结果。后台进程启动不代表完成。
- 新版核验产品身份与安装版本后才对齐资源，包失败不执行资源写入；逐 Workspace 报告配置与 Base 完成、失败和跳过项。
- blocked 输出 stderr 单行 JSON 并退出 3；资源阶段失败不得汇总为 ok。
