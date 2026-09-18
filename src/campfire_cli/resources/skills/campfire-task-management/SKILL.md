---
name: campfire-task-management
description: "查询、创建、更新和完成 Campfire 任务文档；按结构化字段定位项目或个人任务，不负责执行任务、改代码或 Agent Session 调度。"
---

# Campfire 任务管理

用户明确要求记录任务即为创建授权，不再重复询问是否建文档；创建任务不等于授权实施任务。只查询缺失的上下文：已知 Workspace、目标目录和字段契约时直接写入，不固定加载 bootstrap 或转交 capture、maintenance。

## 写入门禁

创建和更新都须满足：操作在授权范围内、目标唯一、任务内容和状态有依据。缺授权先提议，目标或关键事实不明先澄清；不得把用户计划写成已完成工作。条件已满足直接执行，不重复审批，不为普通待办检查无关代码项目。

## 上下文与契约

- 全部任务使用 `campfire document list --type task`；用户指定项目、领域或状态时增加对应筛选，不隐式排除已完成任务。无需先执行 Maintenance。
- 用户指定文档时直接使用该路径。项目尚未定位才查询 `workspace project list`；多个候选时询问，不凭相似名称猜测。已知项目但目录未知时使用 `workspace domain list --project <id>`。
- 个人任务使用当前 Workspace 人工规则约定的任务 Domain；没有约定或目标不唯一时询问，不硬编码个人 Vault 路径，也不为个人任务搜索代码项目。
- `document_status` 表示文档有效性，`task_status` 表示任务进度。`related_project` 必须显式填写有效 Project id；CLI 不自动注入，未填写表示未关联项目。合法字段和候选以当前 Profile 为准。

## SOP

### 流程总览

```text
用户任务意图
├── 只查看 → document list 按明确条件筛选 → 按需读正文
├── 查看关联上下文 → inspect → 同时看 outgoing / incoming → 按需读关联文档
├── 只补进展正文 → Read → Edit → 核对
└── 创建任务 / 修改任务字段
    ├── 目标明确 → 复用目标，不重复查项目或领域
    └── 目标缺失 → 按需定位；多个候选则询问，暂不写入
        ↓ 目标与授权明确
    契约已知则跳过查询；未知才查 Profile / inspect
        ↓
    有明确关联则一并填写 related_docs；无关联则省略
        ↓
    apply 预览 → 无问题则以返回哈希确认 → 新建时补正文
        ↓
    仅执行实际 follow_up → 回报路径和结果
```

预览缺字段时补充已知信息，缺业务事实时询问；出现阻塞或并发冲突时停止写入，不沿图继续确认。


### 执行步骤

1. 目标和授权明确后，优先使用最近 Domain 的任务模板；没有模板时正文只写任务目标、已知约束和完成条件，不补造事实。
2. task 契约未知时运行 `campfire --workspace <id> document profile show task`；已知时跳过。`--path` 必填，接受 Workspace 根相对路径或内部绝对路径，不相对于 cwd。创建可省略类型前缀与 `.md`；标题由路径推导，不传 `title` 字段。
3. apply 默认预览。确认计划与授权一致且没有 issues 后，保持原输入并追加返回的 `expected_hash` 与 `--confirm`。失败时按全部 issues / missing_fields 一次修正；缺业务事实才问用户，不猜枚举。
4. 成功后按 `target` 找到文件，用 Edit 补正文，保留 CLI 生成的 Frontmatter 和自动生成区。没有 `--body` 参数。完成正文后执行结果实际返回的 follow_up，不固定追加 check 或全库扫描。

### 命令示例

以下示例假设 Workspace `demo` 中已存在 Hello World 项目目录，用户要求创建“验证安装”任务。示例值不是字段规则的副本；有效 Profile 不同时按当前契约调整。

```bash
campfire --workspace demo document apply --path "mywork/【Hello World】文档中心/验证安装" --type task --set 'description=验证安装后可以运行版本命令' --set 'task_status=todo' --set 'related_project=hello-world'
campfire --workspace demo document apply --path "mywork/【Hello World】文档中心/验证安装" --type task --set 'description=验证安装后可以运行版本命令' --set 'task_status=todo' --set 'related_project=hello-world' --expected-hash missing --confirm
```

新建预览应返回 `status: planned`、`expected_hash: missing` 和规范化 `target`；确认应返回 `status: applied`、`write_performed: true`。`missing` 仅用于该新建预览，不用于已有文档。以上目录必须以当前 Workspace 实际目录为准。

### 更新已有任务

- 只修改进展正文：读取目标段落，最小 Edit，再核对修改区域，不调用 apply。
- 修改任务状态：契约已知时直接 `document apply --path <path> --set 'task_status=<值>'`；未知时先 `document inspect --path <path>`。预览后按原输入加返回哈希与 `--confirm`。
- 完成任务只更新 `task_status`，结果和阻塞原因写正文；不把完成任务等同于归档。设置 `document_status=archived` 必须先取得用户对该文档的明确同意。
- 只改标题用 `document rename`，跨 Domain 移动用 `document move`；确认带回预览的 `--expected-hash` 与 `--expected-plan`。不手改文件名与受管字段，遇到并发冲突先重新读取。

### 创建与更新任务关联

- 创建任务时，已明确且已存在的需求、技术方案、问题记录等文档可一并写入 `related_docs`；没有关联就省略，不为填字段全库探索或猜测。路径格式为 `[[Workspace根相对路径.md]]`，不写别名或锚点。
- 更新关联前读取来源任务的当前 `related_docs`。`--set 'related_docs=["[[路径/文档.md]]"]'` 替换整个列表，不是追加；添加时保留原有项并去重，解除时只移除指定项。`related_docs=[]` 仅用于明确清空全部出向关联。
- 为任务产出新文档时，先创建成功，再用返回的 `target` 更新任务关联；两次写入分别确认结果，后一步失败不得重建已存在的文档。修改任务须在授权范围内。
- 任务既能关联其他文档，也能被其他文档关联。需要上下文时 `document inspect --path <任务路径>`，同时看 `outgoing`、`incoming` 和 `unresolved`；不把反向结果复制进任务的字段，不要求双方对称填写。
- 从其他文档发起的关联只在其来源文档维护；要解除一条入向关联，应在获授权后修改对应来源的 `related_docs`，不能通过清空任务自己的列表解除。
- 完成任务保留关联用于追溯；关联不代表依赖、阻塞或完成状态，不自动改对方状态。正文仍由 Edit 维护，不参与关系计算。

## 异常与停止条件

预览有字段错误时按实际契约修正，缺业务事实或归属不明确时询问；并发冲突先重新读取，不无条件重试。无法确认完成事实时不标记完成。

## 完成条件与回报

新建任务有可理解的正文，字段更新符合当前 Profile，必要 follow_up 已执行。回报最终路径、实际动作和未解决事项；不宣称尚未执行的任务已经完成。
