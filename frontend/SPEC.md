# Frontend SPEC

从 `v3-admin-template` 派生，保留工程规范和文件职责；本目录只负责本机 Web 界面。

## 工程与代码

- Vue 3、TypeScript 严格模式、Vite、Element Plus、pnpm；使用 Composition API 与 `<script setup lang="ts">`。
- 使用 ESLint 校验与格式化，不增加 Prettier。组件用 PascalCase，页面和 TS 文件用 kebab-case。
- `@` 指向 src，`@@` 指向 src/common。公共类型靠近使用方，未知值使用 unknown，避免 any 与不必要的类型断言。
- 简单状态放组件或 composable；只有实际跨页面需要才用 Pinia。页面不直接操作 DOM，样式使用 scoped SCSS 和主题变量。

## 文件职责

- `pages/app/jobs/` 收拢任务页面，`pages/app/scripts/` 收拢只读脚本项目页；接口、类型和专用组件靠近业务。CodeViewer 放公共组件，语言扩展按需加载。
- `common/` 放共用组件、样式和 composable，`layouts/` 放外壳，`http/` 放请求与错误适配，`router/` 组合模块路由。
- 公共层不导入业务页面，App 不导入 Admin 业务；可复用列表能力已在公共层，不复制页面 loading、分页和竞态状态机。

## 交互与接口

- 沿用模板外壳，采用 Admin 式筛选卡片、表格卡片、右下分页；正文不重复导航标题。
- 页面使用模板标签栏切换；每次运行的日志使用独立路由，重复打开复用标签，不放返回列表按钮。表格后台刷新不显示 loading 遮罩，不打断操作菜单。
- 操作按钮使用明确文字，表格操作固定右侧；弹窗居中、窄屏留白、正文滚动，提交期间禁止关闭或重复提交。
- 筛选和分页交给后端，清空、重置与条件变化回到第一页；旧请求不覆盖新结果，失败不能显示成空数据或最新数据。
- HTTP 成功信封 code=0，data 是业务结果；错误由统一请求层提示。预览确认使用后端计划，不在前端重复业务规则。
- 本机 Cookie 会话由启动连接建立，写请求携带同源保护头；不引入账户登录、生产域名或密钥。
- 执行时区使用设备返回值。日志按文本显示、按游标读取；进程成功不表示业务完成。

## 验证与分发

- 执行 `pnpm lint`、`pnpm typecheck`、`pnpm exec vitest run`、`pnpm build` 与相关 Playwright 测试。
- 浏览器测试连接隔离的真实后端，不在生产代码中放模拟接口；覆盖桌面、390px、弹窗、失败与运行日志。
- 构建输出到 Python 包的 resources/web，由现有发布流水线打包；用户不需要 Node、Nginx 或单独前端部署。
