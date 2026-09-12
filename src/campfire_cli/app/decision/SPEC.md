# Decision App SPEC

本模块维护人类或高级 Agent 必须作出的显式判断。调用方不判断交互模式：不能唯一决定时创建 Decision，得到答案后写入并关闭；尚未回答的 Decision 自然跨会话保留。

SQLite 的 `decisions` 保存当前状态，`decision_events` 追加保存审计历史，两者是 Decision 的 SSOT。Vault 中 `_收件箱/待用户确认/待确认-Decision-*.md` 是只读投影，可由 `decision sync` 重建，不接受反向写入。

状态机保持最小：

```text
pending ──answer──> answered ──close──> closed
   └──────────────cancel─────────────> cancelled
```

`dedupe_key` 在一个 Workspace 内唯一。重复创建仍处于 `pending` 的同一事项时刷新内容而不产生重复 Decision；已经回答、关闭或取消的 key 不得静默复用。

Decision 不发送通知、不调度 Agent，也不直接修改关联文档。未来 Notification 消费 Decision Event，Task Channel 通过稳定 `decision_id` 关联阻塞和恢复事件。
