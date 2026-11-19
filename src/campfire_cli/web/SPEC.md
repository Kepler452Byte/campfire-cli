# Web SPEC

- HTTP 路由集中在 `api/`，只解析请求、调用业务 Service、翻译响应；不直接修改仓储或执行 CLI。
- 每个请求释放业务资源，不跨请求共享可变 Session。执行交给独立 Runner，网页退出不终止任务。
- 仅监听回环地址，校验本机会话、Host 与同源写请求。访问凭据不进入 Job、Vault 或访问日志。
- 业务结果放响应 `data`，保留稳定错误码与实际写入事实；API 错误不能回退成 HTML。

- `server.py` 只装配服务，`api/session.py` 管理浏览器会话接口，`runtime.py` 持有进程与升级租约，`connection.py` 负责同用户 CLI 重连。运行登记 `CAMPFIRE_HOME/web.json` 是私有临时状态，正常退出删除，不写入任务库或 Vault。
- 一次性票据只用于建立 Cookie；会话不按时间过期，重启后失效。CLI 凭私有控制凭据续发票据，浏览器不能续发；续发不撤销已有会话。
- HTML 200 只表示页面外壳可访问；连接验收必须验证认证后 API 与实际页面。
