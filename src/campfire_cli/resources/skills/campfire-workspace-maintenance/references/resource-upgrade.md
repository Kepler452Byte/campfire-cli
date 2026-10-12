# Campfire 升级结果核验

仅在用户已授权升级 CLI 或对齐本机资源时执行。升级不启用定时任务，不覆盖 Workspace 根 `_模板/` 或用户文档。

1. 更新包与资源使用 `campfire upgrade`；明确要求离线、只对齐资源时使用 `campfire upgrade --skip-package`，不查询 PyPI。
2. 返回 `planned` 时，保存 `operation_id` 并执行 `campfire agent upgrade-status <operation_id>` 查询。只有 `state=completed` 且包与资源阶段符合实际目标时才报告完成，启动成功不等于升级完成。
3. editable、未知渠道或离线可能仅完成资源对齐；按 `package.action` 与 `hint` 报告，不能称包已更新。资源阶段逐 Workspace 返回配置与 Base 结果。
4. `blocked` 或非零退出时，查看具体 issue、已完成操作、跳过项与日志路径；修复明确问题后重试，不手写资源登记或清空状态绕过所有权检查。

托管 Skill 与 Hint 块按包恢复，首次升级可接管旧受管资源。Hint 块外正文、其他产品块和用户新增文件保留；异常标记、未知同名资源或并发变化会阻止写入。受管内容需要定制时维护包内来源，不直接修改安装副本。
