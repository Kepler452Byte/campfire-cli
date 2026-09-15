# Campfire 稳定命令

人类与 Agent 先用 `campfire tree` 发现命令，再用任意层级的 `-h` 渐进加载参数。

```bash
campfire setup --path <vault-path> [--id <workspace-id>] --default
campfire upgrade
campfire skill sync
campfire base sync
campfire workspace resolve
campfire workspace rebuild
campfire workspace rebuild --confirm
campfire workspace project bind --id <project-id> --local-path <repository-path>
campfire workspace space list
campfire workspace space check
campfire workspace space check --space <space-id>
campfire workspace config check
campfire workspace domain list
campfire workspace domain check
campfire workspace domain create --id <id> --name <name> --path <workspace-relative-path> --type <type> [--governance <policy>] [--project <id>] [--confirm]
campfire workspace domain adopt --source <folder> --id <id> --name <name> --type <type> [--target-path <path>] [--governance <policy>] [--project <id>] [--confirm]
campfire workspace domain rename --domain <id> --name <name> [--confirm]
campfire workspace domain move --domain <id> --target <space-or-domain-id> [--confirm]
campfire workspace domain merge --source <id> --target <id> [--confirm]
campfire workspace domain delete --domain <id> [--confirm]
campfire workspace domain rekey --domain <id> --new-id <id> [--confirm]
campfire workspace restructure inventory --scope <path> --batch <id>
campfire workspace restructure plan --batch <id>
campfire workspace project resolve --path "$PWD"
campfire document apply --path <workspace-relative-markdown> --type <type> --set <field=value> [--body-file <path>] [--confirm]
campfire document move --path <source> --domain <target-domain-id> [--name <filename>] [--set <field=value>] [--unset <field>] [--expected-hash <sha256>] [--confirm]
campfire document inspect --path <file>
campfire document type list
campfire document profile list
campfire decision create --key <key> --question <question> --source-type <source>
campfire decision list --status pending
campfire decision show <decision-id>
campfire decision answer <decision-id> --answer <answer> --answered-by <actor>
campfire decision close <decision-id>
campfire decision sync
campfire maintenance check --summary
campfire maintenance sync --scope <path> [--dry-run]
campfire maintenance archive check [--scope <path>]
campfire maintenance archive apply [--scope <path>] --confirm
```

Space、Domain、Project 的 `create`/`adopt`，以及文档移动、重构、归档写操作默认先预览；审查通过后才追加 `--confirm`。已注册 Workspace 只通过根级 `campfire --workspace <id> ...` 选择；已声明 Space、Domain 和 Project 使用稳定 ID，CLI 自行推导路径和父子关系。路径参数只用于新位置、具体文件、外部输入和显式扫描范围。

`document apply` 可新建、更新或为已有正文补齐 Frontmatter；`document move` 可在任意已声明 Domain 之间移动单篇文档并对齐可确定的 `domain`/`project`。目标 Profile 缺少语义字段时返回 `missing_fields`，调用方用 `--set`/`--unset` 补齐。只有实际写入成功的结果才可返回一个实际需要的 scoped `maintenance sync` follow-up；预览、阻塞或无派生影响时返回空列表。具体参数以对应命令的 `-h` 为准。
