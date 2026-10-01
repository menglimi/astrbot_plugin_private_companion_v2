# 实际生活回执进入经历记忆

本片补齐“实际活动／阅读／私人书写回执 → 经历记忆 → 相关聊天召回”，复用 V2 原有经历库、来源治理、增量索引和统一宿主生命周期。所有验收使用临时 V2 数据和合成模型／传输，没有读取 V1 用户数据、调用真实模型、发送 QQ 消息或在线重载。

## 已落地行为

- `memory/activity_receipts.py` 从 `role_life_operations` 读取已提交的原活动回执，并核对 `operations` 的完成状态、角色所有者、原会话及不可变活动历史版本。只有 `RoleActivityState.COMPLETED` 才形成完成经历；开始、暂停、取消、排队以及时间经过均不会被当作完成。
- 阅读经历保留实际 `[start_offset, end_offset)`、原文长度和完成时间。部分阅读明确标注未读完全文；阅读感想保留为角色主观回应，不归为用户事实。
- 日记／梦境只生成“保存过这个日期、第几版私人书写”的经历导航。日记正文、梦境情节及摘要继续由日记领域持有，不复制为独立事实来源。改写、删除后旧经历立即不可读，恢复需要新的真实保存回执。
- `memory/activity_ingestion.py` 将原回执摘要和逐句证据原子地保存到现有 `memory_views`，不依赖模型返回 JSON。格式不完整的进度文字仍是原始字符串，不会因解析失败丢失原执行记录。
- 每个经历保留当前私聊用户、角色、平台会话及原始来源依赖。生产者不把其他人、角色或窗口的回执挪作本窗口的新经历；同一人、同一角色的既有经历仍按原来源权限跨会话召回。
- 后续 `memory.query(kind=experiences/all)` 可检索经历、继续读取原证据。普通回复也会按话题自动选入至多一条相关经历，与已有 `context_items`／`context_chars` 共用预算；置顶事实保留独立预算。

## 生产入口与生命周期

```python
producer = memory.attach_life(life_context, require_running=app.require_running)

# 已认证窗口完成操作后可立即消费原回执。
producer.record(context, stream="activity", operation_id=original_operation_id)

# 统一宿主周期入口，不新开模型或发送循环。
producer.advance_bound(app.state_maintenance.bindings.values())

# 停机／故障时释放治理 owner。
producer.close()
```

`record()` 和 `advance()` 返回 `Outcome`。直接 `advance(context)` 每条原始回执流最多检查 16 行；读取原始 `rowid` 页后才过滤所有者，以保证数据库候选扫描也有界。仅包含整数游标的技术检查点保存在 `runtime_metadata`，与经历写入共用事务。重启沿检查点继续，不重新遍历已消费历史；同一原操作生成稳定的经历 ID。

`advance_bound()` 接收真实宿主的 `(TaskContext, instruction, guard)` 绑定集合，每次最多轮转 16 个窗口，每个窗口至少间隔 30 秒。它不派发模型或传输，因此不调用异步宿主派发 guard；本地任务 generation、当前身份／角色／来源权限在每次读取与写入前复核。关闭后清除节流状态并拒绝继续消费。

临时缺失的来源 owner 会将该回执流停在原位置，报告 `blocked` 及原因；恢复 owner 后继续本条。已撤回、过期、被替换或已遗忘的来源不被重新采用。结果中只含控制状态及原操作编号，没有日记正文。

正式装配由主任务完成：`CompanionApplication` 创建 `life_context` 后绑定生产者，driver 调用 `advance_bound()`，fault／close 关闭生产者。

## 召回和规划消费者合同

`memory.context.capture()` 新增可选字段：

```json
{"experience_references": [{"view_id": "原经历编号", "revision": 1}]}
```

原有 `references` 仍只放事实版本。读取一条经历使用：

```python
memory.experiences.read(context, ref["view_id"], expected_revision=ref["revision"])
```

结果包含 `source`、`statements`、`entities`、`links`、`occurred_at` 与 `perspective`。`statements` 每句包含原 `Evidence`；后台规划消费者应保留经历 `source` 的依赖并在使用时重验固定版本。聊天材料使用 `current_experience`，它是固定快照，不随同轮普通事实编辑悄悄更新。

## 撤回、遗忘与重启

每个回执来源登记 `memory.role_activity_receipt` 的运行时治理 owner，并持久化“需要 owner 在场”的标记。后续经历读取、来源 handle、模型材料和任务依赖都会重验原回执、原来源及当前授权。缺装配、停机或 owner 不在场时不释放旧来源内容。

原始阅读来源撤回会沿来源依赖阻止经历使用。记忆的 logical forget 不会替原领域全局撤回来源，因此该 owner 另外通过 `MemoryAccess` 复核原证据的遗忘标记；已遗忘原材料不能借回执摘要恢复。重建记忆检索缓存也会排除相应经历。这里沿用逻辑遗忘语义，不宣称擦除平台消息、备份或日记原库。

## 验收

新增 `tests/test_memory_activity_ingestion.py`，20 项通过，包含：

- 有完成回执／只有计划或暂停回执的区别，已读片段和主观感想，重复消费、事务回滚及暂缺 owner 后恢复。
- 跨人／角色拒绝、原来源撤回、逻辑遗忘、日记版本替换和删除、权限收回、缺 owner 重启与停机。
- 分页检查点、30 秒节流、有界绑定轮转、自动上下文开关与条数预算。
- 正式宿主 driver 自动生产经历，停机后新实例恢复治理 owner，不额外调用模型或发送消息。
- 后续真实对话编排自然召回经历，仅使用正常回复的一次合成模型调用；生成期间撤回原来源后阻止草稿进入交付。

受影响回归覆盖 `test_memory_experiences.py`、`test_memory_conversation.py`、`test_memory_polish.py`、`test_memory_mixed_incremental.py`。与新增文件一起运行得到 **83 passed、8 subtests passed，0 skipped，47.84 秒**。9 个本片文本文件的 UTF-8／LF／末尾换行与 Python AST 检查通过。

长正文夹具此前把全文作为平台消息编号；现在只将超过 512 字符的合成 `event_id` 改为稳定摘要编号，正文、Source 和内容 hash 保持不变。

本片不新增自动 embedding／rerank，不自动生成用户事实，不从未执行的计划生成经历。后续由规划与主动消费者沿这里的固定经历和真实来源接续，不绕过原 owner 的当前状态。
