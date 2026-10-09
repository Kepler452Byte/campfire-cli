---
name: campfire-workspace-maintenance
description: "持续维护 Campfire Workspace 的结构与文档合规；适用于 Space/Domain 声明、文档检查与格式化、MOC 同步、归档和日常维护，不用于跨领域批量重构。"
---

# Campfire Workspace 日常维护

诊断结构和文档问题，修复明确范围并更新派生物；不做跨领域批量重构，不把每次文档操作变成全库治理。

## 执行门禁

操作范围已获授权、目标明确、业务修正有依据。检查不等于授权修复全部问题；归档和删除需要用户对具体对象明确同意。待确认文档也需记录授权，不能因歧义自动落盘。

## 上下文与契约

- 已知 Workspace、目标和契约直接复用，缺失才 bootstrap。根级 `--workspace` 选择环境，路径以 Workspace 根为基准。
- Vault 根目录 `.campfire.yaml` 管便携项目事实，`~/.campfire/local.yaml` 管本机接入与路径绑定，Markdown 管内容与声明，SQLite 和生成视图是派生状态；不直接编辑数据库、Base 或自动生成区域。
- 普通文档归属 Domain，系统受管区按配置处理；Project 由 Manifest 的稳定 Domain 绑定推导，不向 Domain 声明重复写入项目字段。
- list / inspect 自行对账索引；check 用于诊断，不是每次查询或写入的前置步骤。

## SOP

### 流程总览

```text
维护目标
|-- 查集合 / 单篇关系 -> list / inspect，不先 sync
|-- 诊断问题 -> 选择 config / space / domain / maintenance check
|-- 只改人工正文 -> Read -> Edit -> 核对
|-- 字段或类型 -> apply；仅字段顺序 -> format
|-- 单篇改名 / 跨领域移动 -> rename / move
|-- 接管目录 -> workspace-adoption
|-- 领域或批量重构 -> workspace-restructure
`-- 刷新派生物 -> 明确 scope 后 maintenance sync

写入需预览的命令 -> 计划符合授权且无阻塞 -> 确认
                 `-- 有歧义 / 冲突 -> 暂停，不猜测
实际写入成功 -> 仅执行实际 follow_up -> 回报
```

### 执行步骤

1. 选择最窄的操作范围。诊断用对应 check；新建 Space/Domain 用 create，已有目录接管用 adopt；不要手写声明。
2. 修改文档结构时只查询尚未知的 Profile；apply 负责结构，正文由 Edit 维护。新建后用返回的 target 在 `<!-- CAMPFIRE:BODY -->` 后补正文，不手工同步类型前缀。
3. `_xxx/` 统一表示系统治理目录，不能声明为 Domain；其他目录名没有隐藏保留语义。新 Domain 使用 create，已有内容目录使用 adopt，文档类型不强制决定目录；归档只更新 `document_status`，不创建或移动到 `archive/`。
4. 只改标题用 rename，跨 Domain 用 move；确认带上预览返回的 `--expected-hash` 和 `--expected-plan`。批量语义迁移使用重构流程，不逐文件绕过计划。
5. 声明顺序异常时使用诊断返回的 format 修复入口，不把 formatter 列为日常必经步骤。声明标记外的人工正文可直接编辑。
6. sync 刷新 MOC，不再生成关系页；历史关系页不自动删除，清理需先盘点并确认范围，保留人工内容和疑点文件。关联查询使用 document inspect，无需预先 sync。sync 自身直接写入派生物；用户要求预览时才使用 --dry-run，不传不存在的 --confirm。使用实际 follow_up 的 scope 或用户明确的治理范围，不无条件扩大全库。
7. 只有索引损坏或明确恢复需求才使用 workspace rebuild 预览和确认；不把 rebuild 放入普通维护链。
8. 通用模板集中在 Workspace 根目录 `_模板/`，使用 template 类型；局部模板明确指定才使用，不逐层查找。共享模板只留必要结构，顶部写适用类型与特殊说明；完整原则可放目录 README，不逐份复制或强制每次加载。正文可直接编辑但模板变更须获授权，扩展单篇文档不等于授权修改模板，不校验使用者是否套用。

### 命令示例

已知 demo 中需要诊断 Hello World 领域：

```bash
campfire --workspace demo maintenance check --scope "mywork/【Hello World】文档中心"
```

用户已授权刷新同一领域的派生物，或写命令实际返回该 scope：

```bash
campfire --workspace demo maintenance sync --scope "mywork/【Hello World】文档中心"
```

两条不是固定串行步骤。读取 status、issues 和实际写入结果；失败时不宣称维护完成。

## 异常与停止条件

自动生成标记异常、结构断链或并发变化时停止对应写入，按 issue 处理，不手改生成区。业务语义无法唯一确定时询问；缺 CLI 能力则报告，不直接改 Manifest 或数据库。只在核实状态并消除原因后重试。

用户明确要求删除具体文档时，用 rm 或等价文件工具直接删除；CLI 不提供 document delete。索引查询会自动对账，MOC 按需 scoped sync。删除不自动授权改写引用方正文或清理 related_docs；遗留引用另行核实和处理。

## 完成条件与回报

报告已修正内容、生成物变化和剩余问题。Maintenance 不改变主物理归属，不自动合并领域；只验证了局部就不宣称全 Workspace 合规。关系唯一事实源是 `related_docs`，纯正文编辑不改变受管关系，无需同步。
