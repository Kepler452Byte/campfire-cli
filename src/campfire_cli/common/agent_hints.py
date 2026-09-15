from __future__ import annotations

import os
from pathlib import Path

from campfire_cli.common.filesystem import atomic_write

HINT_START = "<!-- campfire:agent-hints:start -->"
HINT_END = "<!-- campfire:agent-hints:end -->"

HINT_BODY = """## Campfire 文档治理

本机装有 campfire CLI（`campfire --help`），Obsidian Vault 已注册为文档工作区。
当用户要求"沉淀/记录/写文档/归档/跟踪问题"到知识库或项目文档时：

1. 用户已给出唯一存在路径，且只读取或小范围修改人工正文时，
   直接使用文件工具；不加载 bootstrap，不调用 Campfire CLI。
2. 新建、Frontmatter、文件名、归属、移动、归档、派生维护或结构治理
   需要 Workspace、Project、Domain 或 Profile 上下文；当前 Session
   首次进入这类治理流程时加载 `campfire-context-bootstrap`。
3. 发现文档集合使用 `campfire document list`，理解单篇文档的确定关系使用
   `campfire document inspect`；两者不要求预先运行 Maintenance。
4. 治理流程按用户意图加载对应的 Campfire 垂直 Skill。
5. 创建正式文档或修改 Frontmatter 时，优先使用
   `campfire document apply`；不手写或猜测 Profile 字段和枚举。
6. 文件工具不得编辑自动生成区域。CLI 写命令完成后只执行结果实际返回的
   `follow_up`；正文编辑会影响关系计算时执行一次局部 `maintenance sync`。
   没有 follow-up 就结束，不固定追加 dry-run、check 或全 Workspace 扫描。
7. CLI 返回 `needs-input` 时补齐事实后重试，不为通过检查而猜测。

不要直接在代码仓库里创建笔记文件。Agent Hint 只规定入口纪律；
字段、枚举和顺序以 Campfire Profile 为唯一事实来源。

## 写作风格

以下风格适用于所有文档、提交说明、注释与回复，违反即返工：

- 禁止括号补充说明。补充内容改用从句、冒号或"例如"引导的句子展开；
  函数调用等代码必要括号不受影响。
- 简洁直接，不啰嗦：一句话能说清的不拆成三句，同一信息不重复出现。
- 代码注释只写代码本身表达不了的约束；不写下一行做什么，不写给评审者
  看的改动说明。"""


def default_hint_paths() -> list[Path]:
    override = os.environ.get("CAMPFIRE_AGENT_HINT_PATH")
    if override:
        return [Path(item).expanduser().resolve() for item in override.split(os.pathsep) if item]
    home = Path.home()
    return [home / ".claude" / "CLAUDE.md", home / ".agents" / "AGENTS.md"]


def render_hint_block() -> str:
    return f"{HINT_START}\n{HINT_BODY}\n{HINT_END}"


def inject_agent_hint(path: Path) -> str:
    """幂等地向 path 写入 campfire 路标块，返回 created/appended/updated/kept。

    块由 HTML 注释标记包围；已存在时整体替换以升级内容，块外用户内容不动。
    """
    block = render_hint_block()
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    if HINT_START in current and HINT_END in current:
        start = current.index(HINT_START)
        end = current.index(HINT_END) + len(HINT_END)
        updated = current[:start] + block + current[end:]
        action = "updated" if updated != current else "kept"
    elif current:
        separator = "" if current.endswith("\n\n") else ("\n" if current.endswith("\n") else "\n\n")
        updated = current + separator + block + "\n"
        action = "appended"
    else:
        updated = block + "\n"
        action = "created"
    if action != "kept":
        atomic_write(path, updated)
    return action
