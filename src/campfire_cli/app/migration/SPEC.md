# Migration App SPEC

本模块处理一次性、批次化的存量治理。CLI 只收集参数；Service 负责 inventory、plan、apply、verify 流程；Repository 保存批次证据；Schema 定义稳定边界。

自动计划只处理可确定推导的规范化；跨目录移动和 Frontmatter 修改通过显式 YAML/JSON Plan Spec 输入。所有计划项保存 inventory 源哈希、配置哈希、理由和审批状态，执行时在治理锁内复核。
