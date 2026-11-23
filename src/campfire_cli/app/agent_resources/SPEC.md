# Agent Resources SPEC

本模块提供 Vault 技能发现，并管理包内 SSOT Skill 与 Hint。Service 决定托管范围、旧资源接管与同步动作；Repository 提供包资源、登记和目标文件的字节读写与锁，不解释所有权规则。

- 全局资源使用 AgentResourceSettings，不依赖 Workspace 或数据库。
- `skill list --source workspace` 按需从 Workspace Manifest 的 `skills.roots` 读取 Vault 技能目录。目录条目只含名称、描述与本机绝对入口路径，异常根目录或入口附诊断并保留有效条目。
- Vault 技能包独立于普通文档治理，Agent 按需直接读取入口与资源。目录实时扫描，不创建索引，不参与全局资源同步。
- 托管内容按包恢复，登记只保存产品身份、目标和文件类型，不保存历史内容哈希。
- 首次接管仅限配置受管名单与带本产品标记的 Hint；未知文件保留，登记过且从包删除的文件可清理。
- Hint 标记重复、残缺或倒序时拒绝写入；块外原始字节不变。所有附属文件按字节分发。
- 同步内部先预检，在锁内复核整个计划与逐文件快照；部分失败返回已完成操作，不报告成功。
