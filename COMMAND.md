# Campfire 稳定命令

人类与 Agent 先用 `campfire tree` 发现命令，再用任意层级的 `-h` 渐进加载参数。

```bash
campfire workspace resolve
campfire workspace space list
campfire workspace space check
campfire workspace space check --space <space-id>
campfire workspace config check
campfire workspace domain list
campfire workspace domain check
campfire workspace restructure inventory --scope <path> --batch <id>
campfire workspace restructure plan --batch <id>
campfire workspace project resolve --path "$PWD"
campfire document inspect --path <file>
campfire document type sync --confirm
campfire document type list
campfire document profile list
campfire decision create --key <key> --question <question> --source-type <source>
campfire decision list --status pending
campfire decision show <decision-id>
campfire decision answer <decision-id> --answer <answer> --answered-by <actor>
campfire decision close <decision-id>
campfire decision sync
campfire maintenance check --summary
campfire maintenance plan --id <plan-id> --scope <path> [--spec <yaml-or-json>]
campfire maintenance show --plan <plan-id>
campfire maintenance apply --plan <plan-id>
campfire maintenance apply --plan <plan-id> --confirm
campfire maintenance verify --plan <plan-id>
campfire maintenance sync --scope <path> --dry-run
```

Space、Domain、Project 的 `create`、存量目录的 `space/domain adopt`，以及文档重构、归档写操作默认先预览；审查通过后才追加 `--confirm`。`adopt` 只新增声明文件和必要 MOC，不移动已有内容。具体参数以对应命令的 `-h` 为准，避免在文档中维护第二份参数目录。
