from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from campfire_cli.app.migration.service.migration_verifier import after, before  # noqa: E402
from campfire_cli.common.archive.planner import (
    build_result as build_archive_result,  # noqa: E402
)
from campfire_cli.common.documents.document_type_apply import (
    apply_plan as apply_type_plan,
)  # noqa: E402
from campfire_cli.common.documents.document_type_apply import (
    preflight as preflight_type_plan,
)
from campfire_cli.common.documents.document_type_check import (
    build_result as build_type_check_result,  # noqa: E402
)
from campfire_cli.common.documents.document_type_plan import (  # noqa: E402
    build_plan as build_type_plan,
)
from campfire_cli.common.documents.domains import check_links
from campfire_cli.common.documents.frontmatter_apply import (
    apply as apply_frontmatter,
)  # noqa: E402
from campfire_cli.common.documents.frontmatter_apply import (
    preflight as preflight_frontmatter,
)
from campfire_cli.common.documents.frontmatter_check import (
    build_result as build_frontmatter_check,  # noqa: E402
)
from campfire_cli.common.documents.frontmatter_format import format_text  # noqa: E402
from campfire_cli.common.documents.frontmatter_plan import (
    build_plan as build_frontmatter_plan,  # noqa: E402
)
from campfire_cli.common.documents.frontmatter_profile import ProfileRegistry
from campfire_cli.common.documents.moc import generate_relations  # noqa: E402
from campfire_cli.common.exceptions import ConfigurationError, GovernanceBlockedError
from campfire_cli.common.filesystem.locking import workspace_write_lock
from campfire_cli.common.governance.rules import GovernanceRuleEngine
from campfire_cli.config.defaults import default_configs


class WriteLockTests(unittest.TestCase):
    def test_recovers_lock_owned_by_dead_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            lock = state / "locks/write.lock"
            lock.parent.mkdir()
            lock.write_text("99999999", encoding="utf-8")
            with workspace_write_lock(state):
                self.assertTrue(lock.is_file())
            self.assertFalse(lock.exists())

    def test_does_not_steal_live_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            lock = state / "locks/write.lock"
            lock.parent.mkdir()
            lock.write_text(str(os.getpid()), encoding="utf-8")
            with self.assertRaises(GovernanceBlockedError), workspace_write_lock(state):
                pass


class LinkCheckTests(unittest.TestCase):
    def test_ignores_links_inside_code_and_resolves_real_wikilink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            target = root / "target.md"
            target.write_text("# Target\n", encoding="utf-8")
            source.write_text(
                "[[target]]\n```text\n[[missing-example]]\n```\n`[[inline-example]]`\n",
                encoding="utf-8",
            )
            self.assertEqual([], check_links(root, [source]))

    def test_reports_missing_wikilink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            source.write_text("[[missing]]\n", encoding="utf-8")
            issues = check_links(root, [source])
            self.assertEqual("wikilink-missing", issues[0]["code"])

    def test_resolves_wikilink_to_stem_containing_dot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            target = root / "【LangChain】 1.0 知识梳理.md"
            target.write_text("# Target\n", encoding="utf-8")
            source.write_text("[[【LangChain】 1.0 知识梳理]]\n", encoding="utf-8")
            self.assertEqual([], check_links(root, [source]))


class RelationTests(unittest.TestCase):
    def test_generates_cross_domain_relation_for_shared_title_keyword(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "AGUI Over MCP.md"
            right = root / "Go MCP Server.md"
            left.write_text(
                "# AGUI Over MCP\nMCP agent server client protocol transport\n", encoding="utf-8"
            )
            right.write_text(
                "# Go MCP Server\nMCP agent server client protocol transport\n", encoding="utf-8"
            )
            domains = {left: "ag-ui", right: "go"}
            relations = generate_relations([left, right], domains, root, 3, 0.08, 2, 0.06)
            self.assertEqual("cross-domain-similarity", relations[left][0]["type"])
            self.assertEqual("Go MCP Server", relations[left][0]["target_name"])


class MigrationCheckTests(unittest.TestCase):
    def test_before_and_after_accept_unchanged_move(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source" / "note.md"
            target = root / "target" / "note.md"
            source.parent.mkdir()
            target.parent.mkdir()
            source.write_text("unchanged\n", encoding="utf-8")
            manifest, issues = before(
                root, {"items": [{"source": "source/note.md", "target": "target/note.md"}]}
            )
            self.assertEqual([], issues)
            source.rename(target)
            self.assertEqual([], after(root, manifest))

    def test_after_rejects_changed_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            target = root / "target.md"
            source.write_text("before\n", encoding="utf-8")
            manifest, issues = before(
                root, {"items": [{"source": "source.md", "target": "target.md"}]}
            )
            self.assertEqual([], issues)
            source.rename(target)
            target.write_text("after\n", encoding="utf-8")
            codes = {issue["code"] for issue in after(root, manifest)}
            self.assertIn("content-hash-mismatch", codes)


class ProjectArchiveTests(unittest.TestCase):
    def make_vault(self, root: Path) -> Path:
        domain = root / "mywork" / "【测试】文档中心"
        domain.mkdir(parents=True)
        (domain / "_领域.md").write_text(
            '---\nname: 测试项目\ndomain_id: test-project\ndomain_type: project-domain\ngovernance: project-docs\nmoc: "[[MOC-测试项目]]"\nstatus: active\n---\n',
            encoding="utf-8",
        )
        return domain

    @staticmethod
    def config() -> dict:
        return {
            "managed_roots": ["mywork/【测试】文档中心"],
            "domain_marker": "_领域.md",
            "ignored_directories": ["assets"],
        }

    @staticmethod
    def document(reason: str = "completed", successor: str = "[]") -> str:
        return (
            "---\nname: 旧计划\ndescription: 测试\nproject: test-project\ndomain: core\n"
            "type: plan\nstatus: current\nlifecycle: proposed\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
            f"related: []\nsuperseded_by: {successor}\narchive_requested: true\narchive_reason: {reason}\n---\n# 旧计划\n"
        )

    def test_check_is_read_only_and_apply_moves_to_flat_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            domain = self.make_vault(root)
            source = domain / "计划-旧计划.md"
            source.write_text(self.document(), encoding="utf-8")
            checked = build_archive_result(root, self.config(), False, "2026-09-07")
            self.assertEqual("ok", checked["status"])
            self.assertTrue(source.exists())
            applied = build_archive_result(root, self.config(), True, "2026-09-07")
            target = domain / "archive" / source.name
            self.assertEqual(1, applied["applied_count"])
            self.assertFalse(source.exists())
            self.assertTrue(target.exists())
            text = target.read_text(encoding="utf-8")
            self.assertIn("status: archived", text)
            self.assertIn("archive_requested: false", text)
            self.assertIn("archived_at: 2026-09-07", text)
            repeated = build_archive_result(root, self.config(), True, "2026-09-08")
            self.assertEqual(0, repeated["applied_count"])
            self.assertIn("archived_at: 2026-09-07", target.read_text(encoding="utf-8"))

    def test_missing_successor_blocks_superseded_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            domain = self.make_vault(root)
            source = domain / "计划-旧计划.md"
            source.write_text(self.document(reason="superseded"), encoding="utf-8")
            result = build_archive_result(root, self.config(), True, "2026-09-07")
            self.assertEqual(0, result["applied_count"])
            self.assertTrue(source.exists())
            self.assertIn(
                "archive-successor-missing", {issue["code"] for issue in result["issues"]}
            )

    def test_multiline_successor_allows_superseded_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            domain = self.make_vault(root)
            source = domain / "计划-旧计划.md"
            source.write_text(
                self.document(reason="superseded", successor='\n  - "[[计划-新计划]]"'),
                encoding="utf-8",
            )
            result = build_archive_result(root, self.config(), False, "2026-09-07")
            self.assertNotIn(
                "archive-successor-missing", {issue["code"] for issue in result["issues"]}
            )

    def test_manual_archive_is_normalized_but_not_moved_again(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            domain = self.make_vault(root)
            target = domain / "archive" / "计划-旧计划.md"
            target.parent.mkdir()
            target.write_text(self.document(), encoding="utf-8")
            result = build_archive_result(root, self.config(), True, "2026-09-07")
            self.assertEqual(1, result["applied_count"])
            self.assertEqual("normalized", result["applied"][0]["action"])
            self.assertTrue(target.exists())


class DocumentTypeTests(unittest.TestCase):
    @staticmethod
    def config() -> dict:
        return {
            "version": 1,
            "scope_roots": ["notes"],
            "ignored_directories": ["assets"],
            "exempt_basenames": ["README.md", "_领域.md"],
            "filename_rules": {"flatten_leading_bracket_categories": True},
            "types": {
                "knowledge": {"prefix": "知识-", "label": "知识"},
                "tech-spec": {"prefix": "技术-", "label": "技术"},
            },
        }

    def test_check_requires_single_type_and_matching_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            notes = root / "notes"
            notes.mkdir()
            (notes / "知识-正确.md").write_text(
                "---\ntype: knowledge\ntags:\n  - test\n---\n", encoding="utf-8"
            )
            (notes / "错误.md").write_text(
                "---\ntype:\n  - knowledge\n  - tech-spec\n---\n", encoding="utf-8"
            )
            result = build_type_check_result(root, self.config())
            codes = {item["code"] for item in result["issues"]}
            self.assertIn("document-type-multiple", codes)
            self.assertEqual(1, result["issue_count"])

    def test_plan_defaults_to_unapproved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            notes = root / "notes"
            notes.mkdir()
            (notes / "架构.md").write_text("---\ntype: tech-spec\n---\n", encoding="utf-8")
            plan = build_type_plan(root, self.config())
            self.assertEqual("notes/技术-架构.md", plan["items"][0]["target"])
            self.assertFalse(plan["items"][0]["approved"])

    def test_plan_flattens_leading_bracket_category(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            notes = root / "notes"
            notes.mkdir()
            source = notes / "知识-【Algorithm】cuDNN与CUDA深度学习加速原理.md"
            source.write_text("---\ntype: knowledge\n---\n", encoding="utf-8")
            plan = build_type_plan(root, self.config())
            self.assertEqual(
                "notes/知识-Algorithm-cuDNN与CUDA深度学习加速原理.md", plan["items"][0]["target"]
            )
            checked = build_type_check_result(root, self.config())
            self.assertEqual("document-name-bracket-category", checked["issues"][0]["code"])

    def test_plan_keeps_unknown_document_for_semantic_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            notes = root / "notes"
            notes.mkdir()
            (notes / "无法判断.md").write_text("# 混合内容\n", encoding="utf-8")
            plan = build_type_plan(root, self.config())
            self.assertEqual(1, len(plan["items"]))
            self.assertIsNone(plan["items"][0]["proposed_type"])
            self.assertEqual("low", plan["items"][0]["confidence"])
            self.assertFalse(plan["items"][0]["approved"])

    def test_apply_updates_type_filename_wikilink_and_canvas_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            notes = root / "notes"
            notes.mkdir()
            source = notes / "架构.md"
            source.write_text("# 架构\n", encoding="utf-8")
            (notes / "索引.md").write_text(
                "[[架构]]\n[同目录](./架构.md)\n[带锚点](./架构.md#范围)\n", encoding="utf-8"
            )
            (root / "map.canvas").write_text(
                '{"nodes":[{"type":"file","file":"notes/架构.md"}],"edges":[]}', encoding="utf-8"
            )
            raw_plan = {
                "items": [
                    {
                        "source": "notes/架构.md",
                        "target": "notes/技术-架构.md",
                        "proposed_type": "tech-spec",
                        "approved": True,
                    }
                ]
            }
            operations, issues = preflight_type_plan(root, raw_plan, self.config())
            self.assertEqual([], issues)
            result = apply_type_plan(root, operations)
            target = notes / "技术-架构.md"
            self.assertEqual(1, result["renamed_count"])
            self.assertFalse(source.exists())
            self.assertIn("type: tech-spec", target.read_text(encoding="utf-8"))
            self.assertIn("[[技术-架构]]", (notes / "索引.md").read_text(encoding="utf-8"))
            self.assertIn(
                "[同目录](./技术-架构.md)", (notes / "索引.md").read_text(encoding="utf-8")
            )
            self.assertIn(
                "[带锚点](./技术-架构.md#范围)", (notes / "索引.md").read_text(encoding="utf-8")
            )
            self.assertIn("notes/技术-架构.md", (root / "map.canvas").read_text(encoding="utf-8"))

    def test_apply_rejects_cross_directory_and_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            notes = root / "notes"
            other = root / "other"
            notes.mkdir()
            other.mkdir()
            (notes / "架构.md").write_text("# 架构\n", encoding="utf-8")
            (other / "技术-架构.md").write_text("# 已存在\n", encoding="utf-8")
            plan = {
                "items": [
                    {
                        "source": "notes/架构.md",
                        "target": "other/技术-架构.md",
                        "proposed_type": "tech-spec",
                        "approved": True,
                    }
                ]
            }
            _, issues = preflight_type_plan(root, plan, self.config())
            codes = {item["code"] for item in issues}
            self.assertIn("type-plan-cross-directory", codes)
            self.assertIn("type-target-exists", codes)


class FrontmatterGovernanceTests(unittest.TestCase):
    @staticmethod
    def type_config() -> dict:
        return {
            "scope_roots": ["notes"],
            "ignored_directories": [],
            "exempt_basenames": [],
            "types": {"knowledge": {"prefix": "知识-", "label": "知识"}},
        }

    @staticmethod
    def schema() -> dict:
        schema = default_configs()["frontmatter-schema.json"]
        schema["profiles"]["knowledge"]["required"] = ["domain"]
        schema["profiles"]["knowledge"]["field_order"].insert(3, "domain")
        return schema

    def test_check_merges_base_and_type_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            notes = root / "notes"
            notes.mkdir()
            (notes / "知识-测试.md").write_text(
                "---\ntype: knowledge\nstatus: 当前\ntags: text\n---\n# 测试\n", encoding="utf-8"
            )
            result = build_frontmatter_check(root, self.type_config(), self.schema())
            codes = {issue["code"] for issue in result["issues"]}
            self.assertIn("frontmatter-field-missing", codes)
            self.assertIn("frontmatter-list-invalid", codes)
            self.assertIn("frontmatter-enum-invalid", codes)

    def test_profile_inheritance_compiles_one_effective_contract(self) -> None:
        registry = ProfileRegistry(self.type_config(), self.schema())
        knowledge = registry.get("knowledge")
        self.assertEqual("base", registry.get("base").name)
        self.assertIn("name", knowledge.required)
        self.assertIn("domain", knowledge.required)
        self.assertEqual(len(knowledge.allowed), len(knowledge.field_order))
        self.assertEqual("preserve", knowledge.unknown_fields)

    def test_profile_inheritance_rejects_deep_chain(self) -> None:
        schema = self.schema()
        schema["profiles"]["deep"] = {
            "extends": "knowledge",
            "field_order": [],
            "required": [],
            "optional": [],
        }
        with self.assertRaises(ConfigurationError):
            ProfileRegistry(self.type_config(), schema)

    def test_rule_engine_reports_actionable_fields_and_collection_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            first = root / "产品-a.md"
            second = root / "产品-b.md"
            content = (
                "---\nname: 产品\ntype: product-spec\nstatus: current\n"
                "project: p\ndomain: core\ncreated: invalid\ntags: text\n---\n"
            )
            first.write_text(content, encoding="utf-8")
            second.write_text(content, encoding="utf-8")
            defaults = default_configs()
            types = defaults["document-types.json"]
            schema = defaults["frontmatter-schema.json"]
            engine = GovernanceRuleEngine(types, schema)

            document_issues = engine.check_document(root, first)
            by_code = {item["code"]: item for item in document_issues}
            self.assertIn(
                "description",
                {
                    item["field"]
                    for item in document_issues
                    if item["code"] == "frontmatter-field-missing"
                },
            )
            self.assertEqual("text", by_code["frontmatter-list-invalid"]["actual"])
            self.assertEqual(["YYYY-MM-DD"], by_code["frontmatter-date-invalid"]["allowed"])
            collection_issues = engine.check_collection(root, [first, second])
            self.assertEqual("project-doc-current-conflict", collection_issues[0]["code"])

    def test_plan_only_suggests_deterministic_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            notes = root / "notes"
            notes.mkdir()
            (notes / "知识-测试.md").write_text(
                "---\ntype: knowledge\n---\n# 正文标题\n", encoding="utf-8"
            )
            plan = build_frontmatter_plan(root, self.type_config(), self.schema())
            fields = plan["items"][0]["fields"]
            self.assertEqual("正文标题", fields["name"]["value"])
            self.assertEqual([], fields["tags"]["value"])
            self.assertIsNone(fields["description"]["value"])
            self.assertTrue(all(not value["approved"] for value in fields.values()))

    def test_apply_writes_only_approved_fields_and_preserves_body(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            note = root / "note.md"
            note.write_text("# 正文\n内容\n", encoding="utf-8")
            plan = {
                "items": [
                    {
                        "path": "note.md",
                        "fields": {
                            "name": {"value": "正文", "approved": True},
                            "description": {"value": "不得写入", "approved": False},
                        },
                    }
                ]
            }
            ops, issues = preflight_frontmatter(
                root, plan, self.type_config(), self.schema()
            )
            self.assertEqual([], issues)
            self.assertEqual(1, apply_frontmatter(ops))
            text = note.read_text(encoding="utf-8")
            self.assertIn("name: 正文", text)
            self.assertNotIn("不得写入", text)
            self.assertTrue(text.endswith("# 正文\n内容\n"))

    def test_formatter_reorders_blocks_without_changing_values_or_body(self) -> None:
        text = "---\ntype: prompt\ncreated: 2026-03-26\ndescription: 描述\nname: 提示词\npurpose: 用途\nstatus: current\nupdated: 2026-09-10\ntags:\n  - DB\ncustom: keep\n---\n# 正文\n"
        order = ["name", "description", "type", "status", "created", "updated", "purpose", "tags"]
        formatted, errors = format_text(text, order)
        self.assertEqual([], errors)
        self.assertTrue(
            formatted.startswith(
                "---\nname: 提示词\ndescription: 描述\ntype: prompt\nstatus: current\ncreated: 2026-03-26\nupdated: 2026-09-10\npurpose: 用途\ntags:\n  - DB\ncustom: keep\n---\n"
            )
        )
        self.assertTrue(formatted.endswith("# 正文\n"))
        self.assertEqual((formatted, []), format_text(formatted, order))

    def test_formatter_refuses_duplicate_keys(self) -> None:
        text = "---\nname: one\ntype: knowledge\nname: two\n---\n# Body\n"
        formatted, errors = format_text(text, ["name", "type"])
        self.assertEqual(text, formatted)
        self.assertEqual(["frontmatter-duplicate-key"], errors)


if __name__ == "__main__":
    unittest.main()
