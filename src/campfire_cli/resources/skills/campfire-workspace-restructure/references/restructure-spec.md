# 批量重构规格

仅当 Domain 原子命令不能表达用户意图时使用 `workspace restructure` 规格。规格文件为 YAML 或 JSON，根对象只有 `operations`；每项以 inventory 中的 Workspace 相对路径标识源文档。

```yaml
operations:
  - source: mynote/旧领域/知识-并发.md
    target: mywork/目标领域/知识-并发.md
    frontmatter:
      status: current
    reason: 并入项目文档中心
    approved: true
```

- `source` 必填，且必须存在于当前 batch 的 inventory。
- `target` 可选；省略时保持路径不变。
- `frontmatter` 可选；只写用户已确认且 Profile 允许的 Patch。
- `reason` 可选，用于审阅计划。
- `approved` 默认 `false`；未审批项会在 apply 预检中计入 `unapproved_count` 并阻止执行。

先执行 `plan --spec <file>`，再执行不带 `--confirm` 的 `apply`。预检中的 `planned_count`、`approved_count`、`unapproved_count` 和 `blocked_count` 必须与审阅结论一致；只有全部获批且无阻塞问题时才追加 `--confirm`。
