# Campfire 稳定命令

人类与 Agent 先用 `campfire tree` 发现命令，再用任意层级的 `-h` 渐进加载参数。

```bash
campfire workspace resolve
campfire workspace space list
campfire workspace space check
campfire workspace domain list
campfire workspace domain check
campfire workspace project resolve --path "$PWD"
campfire document type list
campfire document profile list
campfire maintenance check --summary
```

Space、Domain、Project 的 `create`、存量目录的 `domain adopt`，以及文档、迁移、归档写操作默认先预览；审查通过后才追加 `--confirm`。`domain adopt` 只新增领域声明和 MOC，不移动已有内容。具体参数以对应命令的 `-h` 为准，避免在文档中维护第二份参数目录。
