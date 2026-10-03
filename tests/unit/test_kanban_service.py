from __future__ import annotations

import unittest

from campfire_cli.app.document.service.rules.kanban_service import check_kanban_renderability


def board(plugin: str = "basic", body: str = "## 未排期\n\n- [ ] 卡片\n") -> str:
    return f"---\nname: 看板\ntype: board\nkanban-plugin: {plugin}\n---\n{body}"


class KanbanRenderabilityTests(unittest.TestCase):
    def test_valid_board_passes(self) -> None:
        self.assertEqual([], check_kanban_renderability(board()))

    def test_missing_plugin_key_reports(self) -> None:
        text = "---\nname: 看板\ntype: board\n---\n## 未排期\n\n- 卡片\n"
        codes = {item["code"] for item in check_kanban_renderability(text)}
        self.assertEqual({"kanban-plugin-missing"}, codes)

    def test_preamble_and_settings_block_are_tolerated(self) -> None:
        text = board(
            body=(
                "# 看板标题\n\n"
                "> 人类和 Agent 共用的队列。\n\n"
                "## 未排期\n\n"
                "- [ ] 多行卡片\n"
                "\t缩进续行属于卡片内容\n"
                "### 嵌套小节\n\n"
                "- 卡片\n\n"
                "%% kanban:settings\n"
                '{"kanban-plugin":"basic"}\n'
                "%%\n"
            )
        )
        self.assertEqual([], check_kanban_renderability(text))

    def test_checkbox_doc_without_lanes_reports(self) -> None:
        text = "---\nkanban-plugin: basic\n---\n# 标题\n\n### 未排期\n\n- [ ] 卡片\n"
        codes = {item["code"] for item in check_kanban_renderability(text)}
        self.assertEqual({"kanban-lane-missing", "kanban-card-outside-lane"}, codes)

    def test_stray_text_and_cards_outside_lane_report(self) -> None:
        text = board(body="游离文本\n\n- 泳道外卡片\n\n## 进行中\n\n- 卡片\n更多游离文本\n")
        details = {(item["code"], item["detail"]) for item in check_kanban_renderability(text)}
        self.assertEqual(
            {
                ("kanban-line-not-card", "line 1"),
                ("kanban-card-outside-lane", "line 3"),
                ("kanban-line-not-card", "line 8"),
            },
            details,
        )


if __name__ == "__main__":
    unittest.main()
