from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import yaml

from campfire_cli.app.document.service.document_rule_service import DocumentRuleService
from campfire_cli.app.document.service.type_apply import (
    rewrite_markdown_links,
    rewrite_wikilinks,
)
from campfire_cli.app.workspace.schema.restructure_schema import (
    InventoryItem,
    RestructureIntentSpec,
    RestructurePlan,
    RestructurePlanItem,
    RestructureResult,
)
from campfire_cli.app.workspace.service.restructure_protocol import RestructureRepositoryProtocol
from campfire_cli.common.documents.markdown import parse_document, render_document
from campfire_cli.common.exceptions import GovernanceBlockedError
from campfire_cli.common.filesystem import FileChangeExecutor, FileChangeSet, FileWrite, safe_path
from campfire_cli.common.hashing import file_sha256, text_sha256
from campfire_cli.config.settings import WorkspaceSettings

LEADING_CATEGORY_RE = re.compile(r"^((?:【[^】]+】)+)(.*)$")
CATEGORY_RE = re.compile(r"【([^】]+)】")


class RestructureService:
    def __init__(
        self,
        settings: WorkspaceSettings,
        repository: RestructureRepositoryProtocol,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._rules = DocumentRuleService(settings.document_types, settings.frontmatter_schema)
        self._executor = FileChangeExecutor(settings.vault_root, settings.state_root)

    def inventory(self, batch: str, scope: str) -> RestructureResult:
        root = safe_path(self._settings.vault_root, scope)
        if not root.is_dir():
            return RestructureResult(
                status="blocked",
                batch=batch,
                item_count=0,
                issues=[{"code": "scope-missing", "path": scope}],
            )
        items = [
            InventoryItem(
                path=path.relative_to(self._settings.vault_root).as_posix(),
                sha256=file_sha256(path),
                size=path.stat().st_size,
            )
            for path in self._inventory_documents(root)
        ]
        config_hash = self._config_hash()
        self._repository.save_batch(str(uuid4()), batch, scope, config_hash)
        self._repository.save_inventory(batch, items)
        return RestructureResult(status="inventoried", batch=batch, item_count=len(items))

    def plan(self, batch: str, spec_path: Path | None = None) -> RestructureResult:
        scope, config_hash, inventory = self._repository.load_inventory(batch)
        if spec_path is not None:
            return self._plan_from_spec(batch, scope, config_hash, inventory, spec_path)
        types = self._settings.document_types["types"]
        items: list[RestructurePlanItem] = []
        issues: list[dict[str, object]] = []
        for record in inventory:
            path = safe_path(self._settings.vault_root, record.path)
            if not path.is_file():
                issues.append({"code": "source-missing", "path": record.path})
                continue
            if file_sha256(path) != record.sha256:
                issues.append({"code": "source-hash-changed", "path": record.path})
                continue
            parsed = parse_document(path.read_text(encoding="utf-8"))
            current_type = parsed.frontmatter.get("type")
            proposed_type = current_type if current_type in types else None
            if proposed_type is None:
                for name, rule in types.items():
                    if path.name.startswith(rule["prefix"]):
                        proposed_type = name
                        break
            target_name = self._normalized_name(path.name, proposed_type)
            target = path.with_name(target_name)
            changes_type = proposed_type is not None and current_type != proposed_type
            changes_name = target != path
            if not changes_type and not changes_name:
                continue
            reason = ", ".join(
                part
                for part, enabled in (("补齐文档类型", changes_type), ("规范文件名", changes_name))
                if enabled
            )
            items.append(
                RestructurePlanItem(
                    item_id=str(uuid4()),
                    source=record.path,
                    target=target.relative_to(self._settings.vault_root).as_posix(),
                    source_sha256=record.sha256,
                    action="rename" if changes_name else "update-metadata",
                    proposed_type=proposed_type,
                    frontmatter={"type": proposed_type} if changes_type else {},
                    reason=reason,
                    confidence="high" if proposed_type else "low",
                )
            )
        if issues:
            return RestructureResult(
                status="blocked", batch=batch, item_count=len(items), issues=issues
            )
        plan = RestructurePlan(batch=batch, scope=scope, config_hash=config_hash, items=items)
        self._repository.save_plan(plan)
        return RestructureResult(status="planned", batch=batch, item_count=len(items))

    def _plan_from_spec(
        self,
        batch: str,
        scope: str,
        config_hash: str,
        inventory: list[InventoryItem],
        spec_path: Path,
    ) -> RestructureResult:
        payload = yaml.safe_load(spec_path.expanduser().read_text(encoding="utf-8"))
        spec = RestructureIntentSpec.model_validate(payload)
        known = {item.path: item for item in inventory}
        allowed_fields = self._rules.known_fields()
        items: list[RestructurePlanItem] = []
        issues: list[dict[str, object]] = []
        for intent in spec.operations:
            record = known.get(intent.source)
            if record is None:
                issues.append(
                    {"code": "restructure-source-not-in-inventory", "path": intent.source}
                )
                continue
            target_name = intent.target or intent.source
            try:
                source = safe_path(self._settings.vault_root, intent.source)
                target = safe_path(self._settings.vault_root, target_name)
            except GovernanceBlockedError:
                issues.append({"code": "restructure-path-outside-vault", "path": target_name})
                continue
            unknown = sorted(set(intent.frontmatter) - allowed_fields)
            if unknown:
                issues.append(
                    {
                        "code": "restructure-frontmatter-field-unknown",
                        "path": intent.source,
                        "detail": ",".join(unknown),
                    }
                )
                continue
            proposed_type = intent.frontmatter.get("type")
            if (
                proposed_type is not None
                and proposed_type not in self._settings.document_types["types"]
            ):
                issues.append(
                    {
                        "code": "restructure-document-type-invalid",
                        "path": intent.source,
                        "detail": str(proposed_type),
                    }
                )
                continue
            if not source.is_file() or file_sha256(source) != record.sha256:
                issues.append({"code": "source-hash-changed", "path": intent.source})
                continue
            current = parse_document(source.read_text(encoding="utf-8")).frontmatter
            patch_issues = self._rules.validate_patch(
                self._settings.vault_root, target, current, intent.frontmatter
            )
            if patch_issues:
                issues.extend(patch_issues)
                continue
            action = "move" if source != target else "update-metadata"
            items.append(
                RestructurePlanItem(
                    item_id=str(uuid4()),
                    source=intent.source,
                    target=target_name,
                    source_sha256=record.sha256,
                    action=action,
                    proposed_type=proposed_type,
                    frontmatter=intent.frontmatter,
                    reason=intent.reason,
                    confidence="explicit",
                    approved=intent.approved,
                )
            )
        if issues:
            return RestructureResult(
                status="blocked", batch=batch, item_count=len(items), issues=issues
            )
        plan = RestructurePlan(batch=batch, scope=scope, config_hash=config_hash, items=items)
        self._repository.save_plan(plan)
        return RestructureResult(status="planned", batch=batch, item_count=len(items))

    def apply(self, batch: str, confirm: bool) -> RestructureResult:
        plan = self._repository.load_plan(batch)
        approved = [item for item in plan.items if item.approved]
        issues = self._preflight(plan, approved)
        if issues or not confirm:
            return RestructureResult(
                status="blocked" if issues else "ready",
                batch=batch,
                item_count=len(approved),
                issues=issues,
            )
        result = RestructureResult(
            status="applied", batch=batch, item_count=len(approved), applied_count=len(approved)
        )
        with self._executor.transaction(self._build_change_set(approved)):
            self._repository.save_execution(result)
        return result

    def verify(self, batch: str) -> RestructureResult:
        plan = self._repository.load_plan(batch)
        issues: list[dict[str, object]] = []
        for item in [entry for entry in plan.items if entry.approved]:
            target = safe_path(self._settings.vault_root, item.target)
            source = safe_path(self._settings.vault_root, item.source)
            if not target.is_file():
                issues.append({"code": "target-missing", "path": item.target})
            if source != target and source.exists():
                issues.append({"code": "source-still-exists", "path": item.source})
        result = RestructureResult(
            status="ok" if not issues else "needs-review",
            batch=batch,
            item_count=len(plan.items),
            issues=issues,
        )
        self._repository.save_verification(result)
        return result

    def _normalized_name(self, name: str, proposed_type: str | None) -> str:
        if not proposed_type:
            return name
        prefix = self._settings.document_types["types"][proposed_type]["prefix"]
        stem = name[:-3]
        if stem.startswith(prefix):
            stem = stem[len(prefix) :]
        match = LEADING_CATEGORY_RE.match(stem)
        if match:
            categories = "-".join(CATEGORY_RE.findall(match.group(1)))
            stem = f"{categories}-{match.group(2)}"
        return f"{prefix}{stem}.md"

    def _preflight(
        self, plan: RestructurePlan, items: list[RestructurePlanItem]
    ) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        if plan.config_hash != self._config_hash():
            issues.append({"code": "restructure-config-changed", "path": plan.batch})
        targets: set[Path] = set()
        sources: set[Path] = set()
        for item in items:
            source = safe_path(self._settings.vault_root, item.source)
            target = safe_path(self._settings.vault_root, item.target)
            if not source.is_file():
                issues.append({"code": "source-missing", "path": item.source})
            elif file_sha256(source) != item.source_sha256:
                issues.append({"code": "source-hash-changed", "path": item.source})
            if source.suffix.lower() != ".md" or target.suffix.lower() != ".md":
                issues.append({"code": "restructure-not-markdown", "path": item.source})
            if target in targets:
                issues.append({"code": "target-duplicate", "path": item.target})
            if source in sources:
                issues.append({"code": "source-duplicate", "path": item.source})
            if target != source and target.exists():
                issues.append({"code": "target-exists", "path": item.target})
            targets.add(target)
            sources.add(source)
        return issues

    def _build_change_set(self, items: list[RestructurePlanItem]) -> FileChangeSet:
        references = self._reference_files()
        original_contents = {path: path.read_text(encoding="utf-8") for path in references}
        contents = dict(original_contents)
        stem_counts: dict[str, int] = {}
        for path in references:
            if path.suffix.lower() == ".md":
                stem_counts[path.stem] = stem_counts.get(path.stem, 0) + 1

        for item in items:
            source = safe_path(self._settings.vault_root, item.source)
            target = safe_path(self._settings.vault_root, item.target)
            updated = contents.pop(source)
            if item.frontmatter or item.proposed_type:
                parsed = parse_document(updated)
                frontmatter = dict(parsed.frontmatter)
                frontmatter.update(item.frontmatter)
                if item.proposed_type:
                    frontmatter["type"] = item.proposed_type
                updated = render_document(
                    frontmatter,
                    parsed.body,
                    self._rules.field_order_for(frontmatter, target),
                )
            contents[target] = updated

            old_path = Path(item.source)
            new_path = Path(item.target)
            for reference, text in list(contents.items()):
                rewritten = text.replace(item.source, item.target).replace(
                    quote(item.source), quote(item.target)
                )
                if stem_counts.get(source.stem) == 1 and old_path.stem != new_path.stem:
                    rewritten = rewrite_wikilinks(rewritten, old_path.stem, new_path.stem)
                if reference.suffix.lower() == ".md":
                    rewritten = rewrite_markdown_links(
                        rewritten,
                        reference,
                        self._settings.vault_root / old_path,
                        self._settings.vault_root / new_path,
                    )
                contents[reference] = rewritten

        sources = {safe_path(self._settings.vault_root, item.source) for item in items}
        writes = tuple(
            FileWrite(path, content)
            for path, content in contents.items()
            if path not in original_contents or content != original_contents[path]
        )
        deletes = tuple(source for source in sources if source not in contents)
        expected = {path: file_sha256(path) for path in references}
        for item in items:
            target = safe_path(self._settings.vault_root, item.target)
            if target not in original_contents:
                expected[target] = None
        return FileChangeSet(
            writes=writes,
            deletes=deletes,
            label="workspace restructure",
            expected=expected,
        )

    def _reference_files(self) -> list[Path]:
        ignored = {".git", ".campfire"}
        return sorted(
            path
            for path in self._settings.vault_root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".md", ".canvas"}
            and not any(
                part in ignored for part in path.relative_to(self._settings.vault_root).parts
            )
        )

    def _inventory_documents(self, root: Path) -> list[Path]:
        ignored = set(self._settings.document_types.get("ignored_directories", []))
        ignored.update({".git", ".obsidian", ".campfire"})
        exempt = set(self._settings.document_types.get("exempt_basenames", []))
        return sorted(
            path
            for path in root.rglob("*.md")
            if path.name not in exempt
            and not any(
                part in ignored for part in path.relative_to(self._settings.vault_root).parts[:-1]
            )
        )

    def _config_hash(self) -> str:
        return text_sha256(
            json.dumps(
                {
                    "governance": self._settings.governance,
                    "types": self._settings.document_types,
                    "frontmatter": self._settings.frontmatter_schema,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
