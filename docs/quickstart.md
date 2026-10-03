# 独立环境快速上手

目标：用两篇文档体验字段治理和明确关联，无需 Obsidian、插件或 Agent。
要求：Python 3.12+、uv；Windows 示例使用 PowerShell 7.3+，POSIX 示例使用 bash。
先安装 `uv tool install campfire-cli`，检查 `campfire version`。源码用户先 `uv sync --frozen`，将下文 `campfire` 替换为 `uv run campfire`。

## 1. 隔离演示环境

在一个新终端中执行对应片段。所有治理状态、Skill 和提示词都放入新临时目录，不接入真实 Vault。路径输出后保留，后续查看文件使用它。

```powershell
$demo = Join-Path ([IO.Path]::GetTempPath()) ('campfire-demo-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $demo | Out-Null
$env:CAMPFIRE_HOME = Join-Path $demo 'state'
$env:CAMPFIRE_SKILL_TARGETS = Join-Path $demo 'skills'
$env:CAMPFIRE_AGENT_HINT_PATH = Join-Path $demo 'AGENTS.md'
campfire workspace create --id demo --path "$demo/vault" --default
Write-Output $demo
```

```bash
demo=$(mktemp -d)
export CAMPFIRE_HOME="$demo/state"
export CAMPFIRE_SKILL_TARGETS="$demo/skills"
export CAMPFIRE_AGENT_HINT_PATH="$demo/AGENTS.md"
campfire workspace create --id demo --path "$demo/vault" --default
printf '%s\n' "$demo"
```

`workspace create` 会直接初始化文件并同步资源，不需要 `--confirm`。独立环境应得到已注册的 demo Workspace；失败时先检查 JSON 的 status 和 issues，不继续执行写入。

## 2. 创建领域和文档

以下命令在上述两种 Shell 中相同。领域预览先检查路径和作用域，确认后创建。

```text
campfire --workspace demo workspace domain create --id notes --name Notes --path mynote/Notes --type knowledge-domain --governance knowledge-base
campfire --workspace demo workspace domain create --id notes --name Notes --path mynote/Notes --type knowledge-domain --governance knowledge-base --confirm
campfire --workspace demo document apply --path mynote/Notes/Target.md --type knowledge --set description=Target
campfire --workspace demo document apply --path mynote/Notes/Target.md --type knowledge --set description=Target --expected-hash missing --confirm
campfire --workspace demo document apply --path mynote/Notes/Source.md --type knowledge --set description=Source --set 'related_docs=["[[mynote/Notes/知识-Target.md]]"]'
campfire --workspace demo document apply --path mynote/Notes/Source.md --type knowledge --set description=Source --set 'related_docs=["[[mynote/Notes/知识-Target.md]]"]' --expected-hash missing --confirm
```

创建预览应为 `planned`，确认结果为 `applied`。`missing` 只适用于刚预览确认不存在的新文件；更新已有文件必须使用实际返回的哈希。返回的 target 会补齐 `知识-` 前缀。

使用文本编辑器打开返回的两个 target，在 `<!-- CAMPFIRE:BODY -->` 后写正文，例如 Source 写“这篇笔记参考 Target”。不要改 Frontmatter 或自动生成区域。正文不是 CLI 参数，也不强制使用模板。

## 3. 查询与导航

```text
campfire --workspace demo document list --domain notes
campfire --workspace demo document inspect --path mynote/Notes/知识-Source.md
campfire --workspace demo document inspect --path mynote/Notes/知识-Target.md
campfire --workspace demo maintenance sync --scope mynote/Notes --dry-run
campfire --workspace demo maintenance sync --scope mynote/Notes
```

Source 的 relations.out_degree 应为 1，Target 的 relations.in_degree 应为 1；只在 Source 声明关系，不需要反向重复填写。查询自行更新索引，不以 sync 为前提。
同步执行 apply 返回的同范围 follow_up，更新 MOC 导航，不生成 `_generated`。再次同步应无变更。

## 4. 退出与下一步

关闭此演示终端，环境变量不再影响其他终端。演示目录保留供阅读；确认不需要后，在文件管理器中只删除先前输出的临时目录。不要将真实 Vault 或默认 `~/.campfire` 当作演示目录清理。

查看 [数据安全与退出](safety.md) 了解恢复与卸载。Obsidian 是推荐阅读工具，不是 CLI 依赖；Kanban 和 Bases 只影响对应视图。插件配置教程待维护者提供博客链接，本指南不自动安装插件。
