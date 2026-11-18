# Campfire Web

从自有 v3-admin-template 派生。工程与文件边界见 SPEC.md。

开发使用 Node 24、pnpm 10.12.1。执行 `pnpm install --frozen-lockfile`，通过 `pnpm lint`、`pnpm typecheck`、`pnpm exec vitest run` 后运行 `pnpm build`，生成随 Python 包分发的网页。

`pnpm test:e2e` 启动隔离的真实 Campfire 后端并验证界面，不访问本机生产任务或 Vault。

源码预览在仓库根目录执行 `uv sync --frozen`、`uv run campfire web --no-open`，使用输出的连接链接打开。修改界面后重新 `pnpm build` 并刷新。

使用 Vite 热更新时，先以固定端口启动后端 `uv run campfire web --no-open --port 5287`，再在本目录运行 `CAMPFIRE_WEB_URL=http://127.0.0.1:5287 pnpm dev`。将连接链接中的地址替换为 Vite 地址，保留一次性的 `#connect=...`。会话与写请求仍经过后端验证，不能把开发服务暴露到公网。

构建生成到 `src/campfire_cli/resources/web/`，由 Python 打包钩子纳入 wheel 与 sdist；使用者无需 Node。发布记录统一见仓库 CHANGELOG，模板来源的 MIT 许可保留在本目录 LICENSE。
