# 记忆能力补全路线稿

日期：2026-09-29。这份稿子的每一项都按 `文件:行号` 实查过，不沿用文档自评。
凡与原始判断不一致处，在「实查修正」里标出。

## 零、实查结论（先看这段）

四项确认，一项推翻，两项重定级。

**A1 属实。** `companion_v2/memory/configuration.py:52` 的 `reflection_enabled` 默认 `False`，
唯一消费点是 `companion_v2/memory/scheduling.py:50`（`values["memory.enabled"] and values["memory.reflection_enabled"]`）。
打开它就会按 `reflection_time`（默认 23:50）走定时整理。

**A3 属实，但描述要改。** 不是"零件已建好、没接消费者"，而是**消费者也建好了、没人驱动它**：

- 服务端 `MemorySubscriptions` 在 `companion_v2/memory/provider.py:92` 由 `make_memory_subscriptions` 造出。
- 消费端 `MemoryReferenceConsumer` 在 `companion_v2/host/application.py:287` 造出，挂在 `self.memory_reference_views`。
- 但它的十个方法（`bind`/`stage_page`/`apply_batch`/`activate`/`read`/`close`/`recovery_checkpoint` …，
  `stream_consumer.py:11-190`）**全仓只有 `tests/test_memory_stream_host.py` 调用**，
  生产路径零调用点。`grep -rn "memory_reference_views"` 只有 `application.py:269`（初始化为 `None`）、
  `:287`（赋值）与两个测试。

所以这两条的分工比原描述更清楚：**A1 差一个默认值，A3 差一个驱动循环**——
后者不是"接上消费者"一行，是要决定谁按什么节奏推进 `read()`。

**A2 属实，且比原描述更贴近现实。** 主动侧的提示词组装在
`companion_v2/proactive/prompts.py:74` 的 `request_for(job, records, preferences, history, last_reply, ...)`，
参数里**没有任何记忆入口**。被动侧是 `conversation/messages.py:123,414` 通过 `memory.context` 注入的。
所以不是"记忆不能影响主动消息"，而是主动侧压根没接那条通道。

**E 部分属实，但成因不是冷归档。** 查证如下：

- `companion_v2/memory/archive.py` 全程只 `UPDATE memory_atoms`（`:169`、`:218`），
  **不删 `sources`、不删 `evidence`**。全仓 `DELETE FROM sources` 只出现在 5 个测试文件里。
- 但原文**确实会失效**，机制在别处：`sources/repositories.py:55` 的 `is_expired_at` 与
  `:256` 的同一判断，`sources/dependencies.py:77-78` 的 `source_dependency_expired`。
  即 **`SourceRecord` 自带 `expires_at`**（`repositories.py:42,146`），到期后证据读不出来。

所以结论要改写：**不是"归档把原文移走"，而是"来源自带有效期，到期后证据链自然断"**。
这条比原来那条更值得记——因为它是设计出来的，不是副作用，抄不了近路：
「可核验」依赖被核验对象的存活期，而存活期由来源方决定。

## 一、A 类：建议做（小、且明确改善）

成本已经付了，只是没通电的两项加上一条通道。

| # | 改动 | 位置 | 代价 | 依据 |
| --- | --- | --- | --- | --- |
| A1 | `reflection_enabled=True` | `memory/configuration.py:52` | 一个默认值；成本是一天一次模型调用 | 补"自动积累"，最接近旧插件的记性 |
| A2 | 主动消息接入记忆 | `proactive/prompts.py:74` 的 `request_for` | 照抄被动路径 `messages.py:414` 的注入形状 | 现在只有单向连通：主动消息能变记忆，记忆不能影响主动消息 |
| A3 | 驱动订阅消费循环 | `host/application.py:287` 造的对象 + 一个定时驱动 | 零件与消费者都在，缺驱动者 | 十个方法零生产调用点，见第零节 |

A1 与 A3 的共同点：**成本已经付了，只是没通电。**

A3 有一个必须先定的问题：**谁驱动、多久一次、推进到哪一页算完。**
`MemoryReferenceConsumer` 是分页的（`stage_page` → `apply_batch` → `activate`），
不是一次拉完。建议照 `memory/scheduling.py` 的定时器范式做，而不是新建一套调度。

## 二、B 类：建议做但要先定方案

| # | 改动 | 待定问题 |
| --- | --- | --- |
| B1 | 召回排序加时间因子 | 不必照搬半衰期，只要同等相关度下旧的排后面。**先定**：衰减函数要不要暴露成配置 |
| B2 | 媒体作为记忆来源 | 现在 `source_kind` 仅四类文本（`models.py` 的 `Evidence.__post_init__` 校验 `human_message`/`bot_message`/`source`/`observation`），图片/语音只在当轮，真会丢。要动 `sources` 枚举 + 本机适配层 |
| B3 | 旧记忆迁移适配器 | 缺 `v2.memory-snapshot-adapter`（`legacy/catalog.py:137` 只有声明、无实现体）。架子已备：`legacy_api.py` 的发现→试算→写库 + `plan_token`；`ConfigIntent` 换 `MemoryIntent` 是同构的。**难点是旧记忆的原文能否对回 `conversation_inputs`** |
| B4 | 归因标记 | 若要 B3，需给 `attribution` 加 `"imported"`。实查：封闭枚举在 `memory/models.py:105`，取值 `user`/`third_party`/`bot`/`unknown`/`observed`，加值是一行 |

B3 的难点值得展开。`legacy/catalog.py:136` 把 `memory_companion.db` 标成 `COMPAT_READABLE`，
而 `legacy/migration.py:14` 对该处置的定义是**"保持原位可读，V2 不复制它"**——
这是**设计成不迁**，不是没写完。要改的是这个决定本身，不只是补个适配器。

## 三、C 类：记录在案，暂不做

| # | 项 | 为什么暂缓 |
| --- | --- | --- |
| C1 | 历史对话导入 | 真缺，但设计稿排在第 4 步"最后" |
| C2 | 知识图谱（建图/图检索/图入口） | 换了表示法，不是丧失。`memory_atoms` 是主语-谓词-宾语三元组（`storage/memory_schema.py:18-23`），`evidence` 表连回原文。安全取舍 + 欠账 |
| C3 | 用量/成本聚合读出口 | 后端底座有，页面无 |
| C4 | 旧聊天指令迁移 | V2 无命令注册，与"只一个小屋页面"的设计相关 |
| C5 | 成批读原文 + 真实"未读位置" | 设计稿要，未做 |
| C6 | 计数统计（多少次、最早最近） | 设计稿要，未做 |
| C7 | 查询便笺 | 设计稿要，未做 |
| C8 | "现实/模拟"归属标记 | 设计稿要，未做。检索侧无法区分世界内与现实 |

## 四、D 类：操作/收尾

| # | 项 | 状态 |
| --- | --- | --- |
| D1 | 全量回归 | **未跑。** V45 迁移改了所有库的公共路径，这是唯一未覆盖的风险面 |
| D2 | 交付包构建 | 从未跑过，无 zip / release-manifest |
| D3 | 真机验收 | 86 行全是"待测"，只有你能做 |
| D4 | 文案统一 | 已改（宿主管理页 + `_conf_schema`），未经验收 |

## 五、E 类：新观察（已按实查改写）

**证据链依赖原文的存活期，而存活期由来源方决定。**

不是冷归档移走原文——归档只 `UPDATE memory_atoms`，不碰 `sources`。
真正的机制是 `SourceRecord.expires_at`：`sources/repositories.py:54-55` 与
`sources/dependencies.py:77-78` 会在读取时判过期并报 `source_expired` / `source_dependency_expired`。

**这意味着什么：** 「可核验」是这一版记忆的核心卖点（每条事实都能点回原文），
但它建立在一个不由我们控制的前提上。一旦来源过期，事实还在、证据没了，
页面上就会出现「来源已不可读取」——这正好是 `memory-page.js` 里已经处理的那条分支
（`mem-source-unavailable` 与 `sourceButtons()` 的空态）。

**建议记一条设计约束：** 证据过期不该让事实本身降级为不可信，
但页面必须把「有证据」和「证据已过期」分得清楚，不能让两者看起来一样。
当前页面文案已经分开了，但**没有实测过原文过期后的真实表现**——列入 D1。

## 六、建议的动手顺序

1. **A1**（一行，当晚就能看到效果，且风险最低——不满意改回去即可）
2. **A2**（通道，改被动侧与主动侧的提示词组装对齐；能立刻让主动消息「记得事」）
3. **A3**（先定驱动方案再动手，别先写代码）
4. **B1**（在 A1 跑出真实召回数据之后再做排序，否则没有语料判断"旧的该排多后"）
5. **B3 + B4**（迁移器；要先对你拍板"改不改 COMPAT_READABLE 这个决定"）
6. **D1/D2/D3**（收尾三件，越早越好——D1 是唯一未覆盖的风险面）

**B2 建议排最后**，因为它要动 `Evidence` 的枚举校验，属于会牵连存量数据的改动，
而前五项都不动存量。

## 七、待你拍板

1. **A1 现在开吗？** 开了就是每天一次模型调用，且会真的写入记忆。
2. **B3 要不要改 `COMPAT_READABLE` 这个设计决定？** 不改的话，旧记忆永远进不来——
   这是你的选择，不是技术限制。
3. **A3 的驱动节奏**由谁定：新增调度器，还是复用 `memory/scheduling.py` 的定时器？

## 八、执行进度（2026-09-30 追加）

### A1 已完成 —— `reflection_enabled` 默认 `True`

`companion_v2/memory/configuration.py:52` 已改，并加注释说明为什么它不该是 `false`
（关掉不等于"更省"，等于"原文存着但没人整理"）。核实生效：注册表默认值读出 `True`。

**实查补充：这台机器的 profile 里 13 张记忆表全是空的。**
`memory_atoms` / `memory_revisions` / `memory_reflections` / `memory_reflection_jobs` /
`memory_schedules` 全 0 行，只有 `memory_recall_changes` 5 行。这是"反思默认关闭"最硬的
证据：不是理论上不记，是**实际一条事实都没有**。所以 A1 不是"体感好一点"，而是
**让记忆功能真正开始工作**。

**A1 顺带暴露了一处测试脆弱点**（不是产品缺陷）：`test_memory_reflection` 的调度用例
依赖该默认值，改默认值后它失败，而失败信息看起来像"调度坏了"。已让它显式声明前提
（新增 `enable_reflection` / `disable_reflection` 助手）。

**一处更正**：执行中一度把 `memory_schedules` 里同时出现 `daily` 与
`memory-daily-<owner_key>` 报成"既有双日程缺陷"。**这是错的**——`schedule_id='daily'`
只在 `tests/test_memory_reflection.py` 里出现，是测试用内部 API 自己造的；产品只有
`sync_configuration` 一条路径（`scheduling.py:48`），且没有路由暴露 `configure`。
产品里不存在双日程。

**A1 的生效路径**：`sync_configuration` 在每条私聊消息被接受时触发
（`application.py:509`），异常被吞（设计如此：无效的可选记忆设置不该拒绝一条已接受的消息）。
所以用户下次发一条私聊，`memory-daily-<owner_key>` 日程就会自动建好。

**不需要额外操作**：该 profile 无 `reflection_enabled` 存档值，走注册表默认值，A1 立即生效。

### A2 已完成 —— 主动消息接入记忆

改 6 个文件：`memory/context.py`（新增 `contact_capture` / `contact_contributions`）、
`proactive/prompts.py`（`request_for(..., memory=())` + `MEMORY_INSTRUCTION`）、
`proactive/service.py`（`attach_memory` + fail-open 的 `_memory_materials`）、
`proactive/contact_models.py`（可选 `deadline_at`）、`host/application.py:365`
（`self.proactive.attach_memory(self.memory)`）、`tests/test_proactive_memory.py`（新 7 项）。

**无批次问题的解法**：`capture` 的 `batch_id` 只用来构造 `memory_sessions.session_id`
（授权键），从不写入 `conversation_batches`，所以用一个 contact 作用域的合成键
（`"memory-contact-" + digest(job.request_hash)`）即可，**没有伪造 batch 行**——伪造行会是
一个"可被寻址的谎言"，因为 `enrich_semantic` 与工具链刷新都按 batch id 寻址。
过期时间取 `job.deadline_at`（= `opportunity.expires_at` = 任务截止），所以会话不会比消息活得久。

**可选性与失败兜底**：未接线时提示词与今天逐字节相同；任何异常被捕获并记 warning，
**主动消息绝不因记忆失败而不发**。

**验证**：新 7 项全过；含 A2 的 70 项全过；变异验证（删掉材料投影 → 3 项失败；
去掉 try/except → 失败兜底用例失败；两次还原后 SHA-256 与基线一致）。

### 顺带修掉一条过期断言

`tests/test_proactive_management.py:45` 写死 `len(purposes) == 13`，而
`proactive.configuration.PURPOSES` 实际 15 项（含 `environment`、`screen`）。
已改为与注册表比较（`len(PURPOSES)`），不再写死数字——写死会让"加了一类契机"
看起来像"状态接口坏了"。

### A3 重新定级 —— 建议**不做**（理由与本文第七节不同）

实查 `MemoryReferenceConsumer` 后发现，它的性质与"缺一个驱动循环"不同：

- 十个方法没有生产调用点，**且 `astrbot_host/*_api.py` 没有暴露订阅的任何路由**；
- `read()` 不是"排空队列"，而是**返回订阅的当前投影**（`stream_consumer.py:177`），
  并且要先通过 `state["fresh"]`、`server["state"] == "live"`、`checkpoint` 一致、
  `sequence == store.revision()` 四道校验，`activate()` 才提交。

也就是说：**这套订阅是给外部消费者用的前向接口**，而 V2 里那个消费者还不存在
（本工作区唯一的 `memory.query.v1` 客户端是 V1 自己，且仍指向旧桥）。
**给它写一个驱动循环，等于让一个没人读的投影周期性刷新。** 那不是补缺口，是往空处填。

建议 A3 改为：**等真的有外部消费者时再做**，届时由消费者自己决定节奏。
如果只是想验证这条链路端到端可用，那应该先定"谁消费"，而不是先写驱动。

### B1 的前提已就绪

A1 打开后，B1 需要的"真实召回语料"才会开始产生。**建议先用一段时间再动排序**，
否则没有语料判断"旧的该排多后"。

