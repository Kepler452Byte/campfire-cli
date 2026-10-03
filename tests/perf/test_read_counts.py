from __future__ import annotations

from pathlib import Path

import pytest


class ReadTextCounter:
    """统计 Path.read_text 调用次数；性能回归用确定性计数代替墙钟时间。"""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.count = 0
        self._original = Path.read_text
        counter = self

        def counting_read_text(path, *args, **kwargs):
            counter.count += 1
            return counter._original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", counting_read_text)

    def reset(self) -> None:
        self.count = 0


def write_notes(directory: Path, start: int, count: int) -> list[Path]:
    notes = []
    for index in range(start, start + count):
        note = directory / f"知识-笔记{index}.md"
        note.write_text(
            f"# 笔记{index}\nalpha beta gamma delta {index}\n中文内容编号{index}\n",
            encoding="utf-8",
        )
        notes.append(note)
    return notes


def make_domain(vault: Path, domain_id: str, doc_count: int) -> None:
    domain = vault / "mynote" / domain_id
    domain.mkdir(parents=True, exist_ok=True)
    (domain / "_领域.md").write_text(
        "---\n"
        f"name: {domain_id}\n"
        f"domain_id: {domain_id}\n"
        "domain_type: knowledge-domain\n"
        "governance: knowledge-docs\n"
        f'moc: "[[MOC-{domain_id}]]"\n'
        "status: active\n"
        "---\n",
        encoding="utf-8",
    )
    moc_markers = (
        "<!-- AUTO-GENERATED:DOMAIN-INDEX:START -->\n"
        "占位\n"
        "<!-- AUTO-GENERATED:DOMAIN-INDEX:END -->\n"
    )
    (domain / f"MOC-{domain_id}.md").write_text(
        "---\n"
        f"name: {domain_id}总览\n"
        "description: 测试领域导航入口。\n"
        "type: moc\n"
        "document_status: current\n"
        "lifecycle: maintained\n"
        "created: 2026-09-14\n"
        "updated: 2026-09-14\n"
        "tags: []\n"
        "---\n"
        f"# {domain_id}总览\n"
        f"{moc_markers}",
        encoding="utf-8",
    )
    write_notes(domain, 0, doc_count)


@pytest.mark.perf
def test_maintenance_check_reads_scale_linearly(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from campfire_cli.container import AppContainer

    counter = ReadTextCounter(monkeypatch)
    make_domain(workspace, "perf-domain", 15)
    maintenance = AppContainer.build("test").maintenance

    counter.reset()
    maintenance.check()
    reads_small = counter.count

    make_domain(workspace, "perf-domain", 20)
    counter.reset()
    maintenance.check()
    reads_large = counter.count

    assert reads_large < 3 * reads_small, (reads_small, reads_large)
    assert reads_large <= 25 * 35


@pytest.mark.perf
def test_maintenance_sync_reads_scale_linearly(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from campfire_cli.container import AppContainer

    counter = ReadTextCounter(monkeypatch)
    make_domain(workspace, "perf-domain", 15)
    maintenance = AppContainer.build("test").maintenance

    counter.reset()
    maintenance.sync(dry_run=True)
    reads_small = counter.count

    make_domain(workspace, "perf-domain", 20)
    counter.reset()
    maintenance.sync(dry_run=True)
    reads_large = counter.count

    assert reads_large < 3 * reads_small, (reads_small, reads_large)
    assert reads_large <= 25 * 35
