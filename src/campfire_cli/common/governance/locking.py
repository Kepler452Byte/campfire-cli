from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from campfire_cli.common.filesystem.locking import workspace_write_lock
from campfire_cli.common.governance.snapshots import snapshot_changes


@contextmanager
def optimistic_write_lock(
    state_root: Path,
    snapshot: dict[str, str | None],
    root: Path | None = None,
) -> Iterator[list[str]]:
    """乐观并发控制的治理写锁：取治理写锁，并复核快照哈希后放行写入。

    与悲观互斥的 workspace_write_lock（只防提交瞬间的并发）不同，本锁用于
    覆盖"计划到执行"的长窗口：yield 变化路径清单，非空表示计划生成后内容
    被其他会话修改，调用方必须放弃写入（返回 blocked 结果或抛出
    GovernanceBlockedError）；空清单表示可安全写入，写入动作在 with 块内
    完成，退出时释放锁。

    快照的期望哈希必须由 file_sha256 产出，与 snapshot_changes 的复核口径
    一致；不允许各服务手工拼装其他口径的期望哈希。snapshot 的键通常是相对
    root 的 POSIX 路径，也允许绝对路径键（Vault 之外的同步目标，如全局
    Skill 目录），此时 root 不参与该键的解析。
    """
    with workspace_write_lock(state_root):
        yield snapshot_changes(root or Path(), snapshot)
