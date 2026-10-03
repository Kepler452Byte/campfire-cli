"""cwd 探测的统一出口。

进程工作目录可能已被删除（目录改名/移走后残留的 shell），os.getcwd() 此时抛
OSError。所有以 cwd 作为解析起点的入口统一走 safe_cwd：探测失败回落 HOME，
调用方拿到的语义是"尽力而为的上下文锚点"而非进程崩溃。
"""

import sys
from pathlib import Path


def safe_cwd() -> Path:
    """返回当前工作目录；目录已不存在时回落用户 HOME 并告警。"""
    try:
        return Path.cwd()
    except OSError:
        print(
            '{"warning": "当前工作目录已不存在，已回落 HOME 解析"}',
            file=sys.stderr,
        )
        return Path.home()
