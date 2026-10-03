# 参与贡献

先阅读 [SPEC](SPEC.md) 的边界，再讨论问题和范围。小修复直接提交 PR；新增命令、领域模型或兼容性变化先开 Issue。不要将内部公司代码、数据或无权分发的资料提交到项目。

## 开发与验证

Python 3.12+ 和 uv 是开发前提，安装后运行：

```text
uv sync --frozen
uv run python scripts/quality_check.py
uv run python scripts/quality_check.py --release
```

最后一项额外构建并在临时环境安装 wheel，不发布。测试必须隔离 CAMPFIRE_HOME、Skill 与提示词目录，不修改开发者真实 Workspace。公开上手案例见 [quickstart](docs/quickstart.md)。

提交使用 conventional commits，说明动机、改动范围和验证结果。只暂存相关文件；不提交 .venv、状态数据库、真实 Vault 或凭据。行为保持型重构与功能变更分开提交。不要自行重写公开历史或重建已发布标签。

## 报告问题

通过 [Issues](https://github.com/Kepler452Byte/campfire-cli/issues) 提供 CLI/Python/系统版本、最小命令、预期和实际 JSON 结果。使用脱敏的最小文件，不附原始企业资料。安全问题先读 [SECURITY](SECURITY.md)。

## 发布职责

维护者核对 CHANGELOG、版本和标签，运行 release_check 与本地门禁；只有明确发布授权后才推送标签。三平台 release 工作流通过后发布验证过的包，随后从公共 PyPI 安装验证。GitHub Release Notes 摘录 CHANGELOG 对应版本；不修改已有版本的包和标签。

当前 v0.1.25 聚焦开源文档、隔离示例与使用安全；领域模式重构、搜索和插件自动管理不在本轮范围。
