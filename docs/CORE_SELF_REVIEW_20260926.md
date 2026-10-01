# C09 行为自我复盘生产链

日期：2026-09-26。状态：源码已接线，尚未接入小屋页面、未纳入交付包、未做真实模型与 QQ 现场验收。

本片补齐 [V1/V2 功能差距核对](V1_V2_FUNCTIONAL_GAP_AUDIT_20260925.md) 中 C09 的缺口。此前
`companion_v2/role_work/journal/self_review.py` 只有"候选合同"：它能校验模型输出，但没有复盘任务、
没有指导正本、没有审阅流程，也没有向后续请求注入。V1 的对应行为是[每日自我巡视][v1-review]生成临时
指导并[注入后续请求][v1-review-guidance]。

## 范围

| 层 | 实现 | 职责 |
| --- | --- | --- |
| 证据 | `companion_v2/role_work/journal/self_review_evidence.py` | 按当前角色与精确私聊 scope 收集有回执的行为证据，发布不含内部标识的句柄 |
| 生产 | `companion_v2/role_work/journal/self_review_service.py` | 后台任务、模型调用、候选落库、游标推进与生命周期 |
| 审阅 | `companion_v2/role_work/journal/self_review_management.py` | 已认证操作者的分页读取与接受/拒绝 |
| 消费 | `companion_v2/conversation/self_review_context.py` | 只注入已接受且未过期、原证据仍可复核的指导 |

存储为 `companion_v2/storage/self_review_schema.py`，内部 schema **v38 → v39**，新增
`role_self_review_runs` 与 `role_self_review_items` 两张表及两个索引。

## 关键语义

**证据只来自角色自己的可观察行为。** 两类来源都已由各自的 owner 证明发生过：一是**已确认送达的回复**
（`conversation_sent_history` 中同时存在 delivery receipt 的 part，说明角色确实在这段私聊里说过），
二是**已完成的活动/日记回执**。写入、计划和单纯的时间经过都不构成证据，因此不会出现"把提议记成已完成"
的复盘结论。

**句柄不泄露内部标识。** 模型只看到 `reply:<digest>` / `receipt:<digest>` 形式的句柄和去标识文本，
可以引用但不能反推会话、消息号或操作 ID。句柄在同一 scope 内稳定，便于重放核对。

**只有被引用的证据需要仍然有效。** 接受单条指导时调用 `resolve_handles`，只复核该条实际引用的句柄。
同一窗口里另一条证据被撤回，不会连带让这条变成不可决定——这与"整批依赖停用"的媒体撤回语义不同，
因为复盘针对的是每一条独立的观察。

**未通过复核一律拒绝，不降级。** 证据缺失、窗口未闭合、来源撤权或授权变化都会抛错，而不是静默换用
新材料。操作者看到的内容与实际生效的指导必须是同一份。

**no_change 不能作为指导生效。** 它是"本轮无需调整"的信息性条目，可以拒绝但不能接受，避免空指导
被注入提示词。

**指导只短期生效且不压过用户。** `expires_at` 由模型给出并在审阅时确认为未来时间；注入文本明确写着
这是角色自己的短期自我指导，不是用户要求，也不是关于任何人的结论，与本轮对方表达冲突时以对方为准。

**指导失效时不阻断回复。** 注入阶段逐条复核，某条已过期或证据失效就跳过该条；其余仍可用。全部失效
则本次不注入任何内容，回复照常进行。

## 边界

本片不读取或迁移 V1 用户数据，不调用真实模型、QQ 或任何平台，未重载在线插件，未重建交付包。
候选与正本均为 V2 独立存储。

未完成的部分：小屋的复盘审阅页面、V1 的定时巡视排程节拍、真实模型的指导质量评估，以及真实 QQ
环境下的注入效果验收。这些仍需后续切片与现场取证。

## 验证

新增 `tests/test_self_review.py`，覆盖候选解析（未知/重复/缺失证据句柄、非法 kind、越界 confidence、
已过期与无时区 expiry、额外字段、非 JSON 输入、无时区 now）、证据窗口（文档顺序、材料指纹稳定性与
顺序敏感性、窗口上限、条目预算）、上下文快照（外部 context 拒绝、ready/unavailable 状态约束、
重复引用、超预算、时间戳不一致、注入措辞约束）与 v38→v39 存储迁移（升级保留既有数据、迁移记录写入、
半迁移回滚拒绝）。

既有测试同步修正：`remove_v38` 现在先回退 v39（`tests/execution_support.py`），
`test_proactive_balance_events.py` 与 `test_proactive_news_events.py` 的版本断言改用当前
`SCHEMA_VERSION`，不再硬编码 v38。

运行方式（与其他定向测试一致）：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_self_review -q
```

[v1-review]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/daily_review.py:1522
[v1-review-guidance]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/daily_review.py:1795
