# CORE-03 私聊事实增量索引与分批召回

2026-09-24。默认 `kind=facts` 的词法召回已接入增量投影和有界候选读取，普通对话、记忆工具和只读 provider 共用此路径。此前每次查询都会读取 owner 下全部 active facts、逐条验证来源，再同步整个分区；现在首次分批建立投影，后续按 `memory_changes` 更新，命中后才读取事实正本及来源。此批属于插件本体的记忆运行链。

## 运行行为

- `memory/fact_index.py` 按稳定的 installation/Bot/persona/human owner 与 namespace 维护独立投影。首次使用主键续扫 active facts，每次最多处理 256 条；建立期间的新变更再沿 owner 的变更序列补齐。已就绪后，每次最多处理 256 条变更，合并同一事实的重复更新。SQL 额外读取一条用于判断续页。
- `memory/fact_query.py` 在完整匹配集合上执行词法排序，再取候选页，每次最多复核 128 条事实。主体、时间、retention、confidence 和 session scope 筛选先在投影上执行，事实返回前再次由正本复核筛选条件、当前来源、角色与授权。没有先截取最近一批事实再搜索。
- `memory.query.v1` 的 `budget.max_candidates` 可进一步缩小候选复核上限；`usage.candidates` 记录本次实际尝试读取的候选数，包含因来源失效而跳过的候选。此计数不代表 FTS 内部扫描量或索引维护量。
- 索引未就绪时返回空 `items`、有效 `next_cursor` 和 `complete=false`；wire 返回 `partial / memory_index_catching_up`。候选读取达到本页上限而后面仍有结果时，可返回 `partial / memory_candidates_pending`。空页不表示没有记忆，继续查询需要保持原有条件。
- 续页使用原会话的调用、字符和期限预算。索引进度持久保存在可重建缓存中，下一会话或重启可以接续；没有在内部循环读取到完成。超大初始数据集可能跨多个查询会话建立，尚无后台预热任务。
- 普通对话遇到未完成召回时保留已授权的置顶记忆、原文句柄及“不完整”提示。提示词说明何时按游标继续查证、何时保留不确定性。

## 一致性与数据归属

新增的 `fact_documents`、`fact_lexical`、`fact_sync`、`fact_epoch` 仅位于原 `memory-search.sqlite3` 派生数据库；统一 V2 正本仍为 schema v22。投影保存检索词、引用和筛选元数据，不作为事实或来源授权依据。遗忘/当前关系批量清理同时清除这些新投影及进度。

投影词项与检查点在同一个缓存事务提交。每次读取先用正本中的变更及对应修订检查上一批的快照依据。新增、纠正和撤回在内部记录中携带随机 `change_token`；遗忘后的当前墓碑仅保留遗忘标记与该不含正文的随机值，历史墓碑仍彻底清除原内容。即使外层事务回滚后复用了相同 change sequence、atom id、revision 和语义正文，也不会把回滚事务的投影视为新事务的有效缓存。旧 V2 记录缺少该字段仍可读取，无需正本 schema 迁移。

结果游标固定查询条件、owner 修订依据、投影 generation 和词法索引 epoch。FTS 的 bm25 使用整个词法表统计，其他分区的词项变化也可能调整排序，因此会保守地使旧结果游标失效。当前页的候选时间筛选沿用首个结果页的时点，防止过期记录让 OFFSET 前移；每条实际返回的事实仍按当前时间和当前授权重新读取。显式 `at_time` 只回看事实有效期，不能恢复今天已撤回的来源或权限。

已处理缓存建立中途失败、事务回滚、重启接续、修订/撤回、来源撤销、到期、跨私聊 session 和游标失效。损坏/缺失缓存沿原入口在重新装配时重建；运行中数据库错误明确返回 `memory_index_unavailable`，不会回退到无来源正文。

## 验证

新增专项测试位于 `tests/test_memory_incremental.py`，另补 wire 的空页续建/候选预算回归，以及对话置顶块与不完整召回共存回归。原检索失败测试改为在新候选入口注入故障，继续验证已授权核心记忆不被清空。

本批新增 18 项回归，其中增量索引 15 项、wire 2 项、普通对话上下文 1 项。定向结果：

- 核心相关 **109 项通过**：`test_memory_incremental`、`test_memory_query`、`test_memory_boundaries`、`test_memory_writer`、`test_memory_wire`、`test_memory_polish`、`test_memory_conversation`、`test_memory_provider_host`、`test_provider_registry`、`test_memory_management`、`test_memory_experiences`、`test_memory_reflection`。
- SDK 宿主 **50 项通过**：`test_astrbot_staging_host`、`test_astrbot_staging_bootstrap`、`test_astrbot_native`、`test_isolation`，包含加载、停止及原路由注销。
- 新的索引续建、候选预算续页及成功结果共 **7 份回执**通过 review 合同的 Draft 2020-12 JSON Schema 校验。未增加运行时依赖。

上述模块均位于 `tests/`。测试数字仅说明这批受影响链路的验证范围，不表示全插件已完成生产验收。

测试使用 AstrBot 自带 Python、临时 V2 数据根及合成模型/发送器；SDK 导入前设置临时 `ASTRBOT_ROOT`，`PYTHONPATH` 指向 `backend/app`。没有读取 V1 用户数据、重载在线插件、调用真实模型或发送消息。

## 剩余范围

本批优化默认私聊事实词法查询。`sources`、`experiences`、`all` 和显式 vector/hybrid 路径仍沿原检索实现，置顶选择也保留自己的扫描逻辑；自动 Embedding、重排、去重和更多领域增量投影仍待补。FTS 排序、OFFSET 及来源依赖图验证仍有随数据量增长的成本，有限行数不等于 SQLite 指令数、总扫描量或墙钟时间有硬上限，也尚无抢占式 SQL deadline 取消。

写入 wire、operation lookup、订阅/resync 和稳定跨进程 SDK 继续沿公共能力路线推进。本批没有增加拓展页或管理页面。
