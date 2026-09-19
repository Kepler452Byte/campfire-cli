---
name: campfire-workspace-restructure
description: "用领域原子命令或审批批次重构 Campfire Workspace；适用于 Domain 移动、合并、空删除、rekey，以及批量文档迁移、领域拆分和引用更新，不用于单篇文档移动或日常维护。"
---

# Campfire Workspace Restructure

本 Skill 只处理会改变文档主物理位置或领域结构的一次性重构。日常新增、格式修正、声明补全、MOC、归档和持续检查使用 `campfire-workspace-maintenance`。

## 执行门禁

范围、目标和稳定身份已明确，操作已有授权；合并、删除、根领域拆分与 rekey 不得猜测。已有授权不重复询问，计划新增的影响超出授权时才补充确认。

## 上下文与契约

Workspace 未知才 resolve；读取尚未知的局部规则和相关文档，不重复查询已明确的上下文。路径以 Workspace 根为基准，领域以稳定 id 选择。Agent 解释业务语义，CLI 负责冻结事实、哈希复核、原子写入和确定引用更新。

## SOP

### 流程总览

先识别被重构的对象，不要把领域目录改名拆成大量逐文件移动：

```text
重构意图
├── 单篇仅改标题     → document rename，保留目录
├── 单篇跨 Domain  → document move
├── 一批内容文档   → inventory / plan / apply / verify
└── 已声明 Domain
    ├── 修改显示名称     → domain rename --name
    ├── 原地修改目录名   → domain rename --folder-name
    ├── 移入目标领域/空间 → domain move
    ├── 并入另一领域     → domain merge
    ├── 删除逻辑空领域   → domain delete
    └── 修改稳定机器身份 → domain rekey（高风险）
```

### 执行步骤

先选择上图对应入口。领域原子命令可表达的操作不进入批次；领域级命令默认预览，计划符合已有授权且无歧义才追加 `--confirm`。

以下是参数形式，尖括号替换为已确认的值，不是要依次执行的命令清单：

```bash
campfire workspace domain rename --domain <id> --name <name>
campfire workspace domain rename --domain <id> --folder-name <folder-name>
campfire workspace domain move --domain <id> --target <space-or-domain-id>
campfire workspace domain merge --source <id> --target <id>
campfire workspace domain delete --domain <id>
campfire workspace domain rekey --domain <id> --new-id <id>
```

先运行不带 `--confirm` 的同一命令审查计划；用户已授权且没有 issues 时追加 `--confirm`。包含 `--folder-name` 的 rename 还必须带回预览的 `--expected-plan <摘要>`；检查 old_path、path、path_changed 和 operations，摘要不一致就重新预览。预览或阻塞结果的 follow_up 为空，只在实际写入成功后执行返回的后续。

`rename --name` 只改显示名称，`--folder-name` 只改原父级内的目录名；用户明确要求两者一起改时同时传入，不推断命名前缀。两者均不改 Domain id 或 Project 绑定。当前文件系统不支持直接大小写改名时，CLI 明确阻止；需要两次使用未占用中间名称时，先确认这个额外操作，不手工移动。可捕获写入失败会尝试回滚，回滚失败先核对实际文件，不盲目重试；不承诺断电原子性。

`move` 只接收目标 Space/Domain 稳定 ID，由 CLI 推导路径与父子关系。`merge` 一次完成内容迁移、直接子领域改挂和源领域移除；`delete` 只接受没有内容、附件、子领域、Project 绑定或人工声明正文的逻辑空领域。普通操作保持 domain_id；只有用户明确要求改变稳定身份时使用 rekey。

单篇 document rename / move 的确认需要预览返回的 `--expected-hash` 和 `--expected-plan`；领域目录 rename 只需计划摘要，不传文档级 expected-hash。其余领域命令沿用各自参数，不套用单篇文档示例。

以下仅用于需要持久批次的重构；原子命令已经覆盖的操作不进入此链路。

```text
inventory → plan
              ├── up-to-date → 结束
              └── 有变更 → 审查操作与审批状态 → apply 预检
                          ├── 未审批 / 有阻塞 → 补充审批或修正计划，暂不执行
                          └── 已审批且无阻塞 → apply --confirm → verify
                                              ├── 失败 → 报告问题，不宣称完成
                                              └── 通过 → 仅执行实际 follow_up → 回报
```

1. 使用 `campfire workspace restructure inventory --scope <path> --batch <id>` 冻结明确范围。
2. 使用 `workspace restructure plan --batch <id>` 生成推断计划。无 spec 时只推断类型和文件名前缀规范化；返回 `up-to-date` 就结束。只有 Domain 原子命令无法表达的批量文档映射、领域拆分或 Frontmatter Patch 才写 YAML/JSON 意图规格；使用规格前读取[批量重构规格](references/restructure-spec.md)。
3. 逐项审查 source、target、Frontmatter Patch、理由和审批状态。删除、合并、根领域拆分、冲突权威判定和无法逆推的语义必须由用户确认。
4. 先运行不带 `--confirm` 的 `workspace restructure apply --batch <id>` 做执行前预检；计划已经明确审批且没有阻塞问题时才追加 `--confirm`。
5. 执行 `workspace restructure verify --batch <id>`，再只执行命令实际返回的 `follow_up`，不自行追加重复预览或检查。

## 异常与停止条件

- 纯移动保持正文不变，`related_docs` 中受影响的路径由 CLI 同步；其他字段只有 Spec 明确提供 Frontmatter Patch 时才改写。
- `restructure verify` 只验证 source/target 迁移事实；文档 Profile 与 Formatter 合规交给 Maintenance。
- 不用 Restructure 处理普通增量维护，也不绕过批次计划直接移动受管文档。
- 写入返回 `concurrent-change`、`source-hash-changed` 或 `restructure-config-changed` 时停止，重新 inventory 和 plan。
- 一篇文档只有一个主目标位置；跨领域关系只通过 `related_docs` 表达，自动索引从该字段派生；不解析或改写正文链接，不自动改写 Canvas。
- Project 只通过 `.campfire.yaml` 的稳定根 Domain id 建立绑定。领域改名和移动不修改 Project 元数据；merge 或 rekey 改变稳定 id 时由同一事务更新绑定、路径引用和子领域解析，不得手工分别维护。
- 不手工删除 `_领域.md`、MOC 或领域目录；合并使用 `domain merge`，删除使用 `domain delete`。
- `domain_id` 是稳定身份；`rekey` 必须更新直接子领域的 `parent_domain`，且必须显式确认。
- 目标冲突、来源缺失、链接歧义或语义不明确时保持未执行并请求确认。
## 完成条件与回报

原子命令实际写入成功，或批次 verify 通过，实际 follow_up 已处理；报告移动、改名、字段变化、引用更新和剩余问题。verify 只证明迁移事实，不把它说成全库字段合规。

## 按需参考

只有需要批量映射或字段补丁时，读取[批量重构规格](references/restructure-spec.md)，不为单篇操作创建 spec。
