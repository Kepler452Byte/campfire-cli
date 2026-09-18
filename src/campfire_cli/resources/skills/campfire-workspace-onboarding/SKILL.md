---
name: campfire-workspace-onboarding
description: "首次创建或接入 Campfire Workspace；适用于用户给出新目录、已有未接管目录或初始配置异常时，不用于已注册 Workspace 的日常文档治理。"
---

# Campfire Workspace 首次接入

将用户指定的新目录或已有目录接入为 Workspace，不自动接管存量业务文件，也不猜测项目归属。

## 执行门禁

路径、稳定 Workspace id 和接入意图明确；已有授权不重复询问。create / setup 会直接写入，不虚构预览或 confirm 参数。只有用户要求切换默认工作区时才加 --default；演示项目也需用户要求。

## 上下文与契约

先读取目标目录是否存在及 Manifest 状态，不手写或覆盖 `.campfire.yaml`。新建目录用 create，接入已有目录用 setup。显式 Workspace 选择是根参数 `--workspace <id>`。

## SOP

### 流程总览

```text
目标路径与意图
|-- 不明确 -> 询问，暂不写入
|-- 路径不存在 -> 已授权新建 -> workspace create
|-- 已有合法 Manifest -> 已授权接入 -> setup
|-- 已有目录无 Manifest -> 确认身份与接入 -> setup --id
`-- Manifest 损坏或身份冲突 -> 报告错误，停止，不覆盖
                                     |
入口成功 -> 查看返回的资源与健康结果 -> 回报
             `-- 存量内容未受管 -> 明确剩余范围，按授权转 Adoption
```

### 执行步骤

1. 复用已知路径与身份，缺稳定 id 才提出候选并询问；不把默认 Workspace 当成用户选择。
2. 新目录通过 create 生成基础布局、Manifest 和本机资源；不要先手工复制受管文件。
3. 已有目录通过 setup 接入，保留已有内容；无 Manifest 时提供已确认的 id。接入不代表全部内容已成为受管 Domain。
4. 消费命令返回的 config、resources、health 等结果，已返回的检查不重复跑；某项缺失或发现问题时才执行对应检查。
5. 用户要求标准布局或公开 demo 时按需读取蓝图。新增业务 Domain、模板和文档需要明确组织意图，不自动填充虚构内容。

### 命令示例

以下为互斥入口；将绝对路径和 id 替换成已确认的值：

```bash
# 全新目录
campfire workspace create --id notes --path "/absolute/path/to/new-vault"
# 已有合法 Manifest 的目录
campfire setup --path "/absolute/path/to/existing-vault"
# 已有目录且没有 Manifest
campfire setup --path "/absolute/path/to/existing-folder" --id notes
```

不要依次执行三条。检查返回的 Workspace id、实际路径、资源与健康结果；需要 demo 时只在 create 追加 `--demo hello-world`。

## 异常与停止条件

Manifest 解析失败、身份或目录冲突时原样报告，停止；不删除配置或手动改成“合法”。缺专用修复入口时说明能力边界，不能以新建覆盖旧目录。

## 完成条件与回报

注册目标身份和路径符合预期，初始化资源与健康结果已核对。报告仍未受管的目录，不宣称已完成 Adoption；说明是否改变默认 Workspace 以及下一步。

## 按需参考

用户要求标准布局或公开项目演示时，读取[标准 Workspace 蓝图](references/标准工作区结构.md)。
