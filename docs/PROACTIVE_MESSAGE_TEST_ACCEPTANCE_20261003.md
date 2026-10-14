# 主动消息目的覆盖验收

本记录按 `PROACTIVE_MESSAGE_TEST_INSTRUCTIONS_20261002.md` 的两层边界登记源码现状。领域事件测试使用临时 V2 数据根、模型替身与平台投递替身；真实用户发送不在自动化范围内。

| 目的 | 生产器现状 | 触发器/链路证据 | 验收层级 |
|---|---|---|---|
| `affection` | 常规联系节律中的自发亲近表达候选；不依赖用户近期说过固定词 | `test_proactive_relationship_events.RelationshipContactEventTests.test_relationship_contact_uses_a_later_slot_without_a_new_user_message`；`test_explicit_affection_reaches_the_contact_model_and_delivery` | 默认来源有效期之后仍能进入关系表达链；对话历史仅提供连续性 |
| `care` | 常规联系节律中的低压力近况问候；旧情绪不能当作当前状态 | `test_explicit_feeling_creates_care_contact_from_original_private_turn`；`test_neutral_private_text_can_reach_enabled_relationship_prompt`；`test_proactive_rhythm_and_greetings` | 不要求近期出现情绪词；由模型决定是否自然联系 |
| `play` | 常规联系节律中的轻松互动候选 | `test_explicit_play_reaches_the_contact_model_and_delivery` | 不要求用户先提出玩法；不虚构共同梗或共同经历 |
| `repair` | 常规联系节律可进入模型判断，但只有对话能核验具体分歧时才可修复 | `test_explicit_repair_reaches_the_contact_model_and_delivery` | 没有具体分歧来源时不道歉、不推测矛盾 |
| `chat` | 自动会话调度器 | `test_proactive_contacts`、`test_proactive_activity_events` | 触发器与主动联系链路 |
| `greeting` | 日常窗口与日期事件生产器 | `test_proactive_rhythm_and_greetings`、`test_proactive_date_events` | 触发器与主动联系链路 |
| `life` | 角色活动与日记事件生产器 | `test_proactive_activity_events`、`test_proactive_journal_events` | 触发器与主动联系链路 |
| `creation` | 完成阅读活动生产器 | `test_proactive_activity_events` | 触发器与主动联系链路 |
| `news` | 外部资讯生产器；环境诊断支持 `external_news` 变体复用该来源 | `test_proactive_news_events`、`test_proactive_diagnostic_routes` | 触发器与主动联系链路；诊断路由与来源归因 |
| `followup` | 基于已确认投递历史的接话候选器 | `test_proactive_relationship_events.FollowupContactEventTests.test_followup_waits_then_composes_and_delivers_and_respects_cooldown`、`test_recent_followup_receipt_blocks_a_second_followup_during_cooldown`、`test_a_new_user_input_supersedes_an_unanswered_followup` | 等待前不触发；等待后完成 compose/投递；冷却与新输入取消均通过 |
| `invitation` | 常规联系节律中的自主活动邀请候选 | `test_explicit_invitation_reaches_the_contact_model_and_delivery`、`test_common_interest_is_not_forced_into_an_invitation`、`test_explicitly_rejected_invitation_can_be_skipped_without_a_delivery` | 不要求用户先提活动；共同兴趣不被当成已约事实；拒绝后不投递 |
| `reminder` | 已接受日历约定生产器 | `test_proactive_calendar_events` | 触发器与主动联系链路 |
| `environment` | 天气观测、天气变化、官方预警、服务余额四个来源生产器 | `test_proactive_weather_events`、`test_proactive_weather_change_events`、`test_proactive_official_alert_events`、`test_proactive_balance_events` | 四个来源分支各自有触发器与主动联系链路 |
| `meal` | 本地饭点生产器 | `test_proactive_meal_events` | 触发器与主动联系链路 |
| `screen` | 已授权屏幕观察生产器，生成屏幕专属 `ContactIntent` 并由 `ContactSchedule` 传给通用联系服务 | `test_screen_interpretation.ScreenInterpretationTests.test_authorized_screen_producer_validates_and_rejects_revocation`；`test_screen_observation_reaches_contact_composition_and_confirmed_delivery` | 生产器候选、来源有效性、撤权，以及屏幕专属 compose/确认投递均通过 |

## 通用链路与失败语义

- `test_proactive_contacts.ProactiveContactTests.test_contact_uses_persona_evidence_shared_model_delivery_and_independent_receipts` 检查可信来源进入模型材料、投递回执与 `observe` 返回同一任务的回执引用。
- `test_proactive_appointments_and_judge.PersonaJudgeTests.test_allowed_judgement_delivers_the_sealed_body` 检查开启人格复核时先复核密封正文，再投递并由同一任务 `observe` 到 `resolved`。
- `test_proactive_contacts.ProactiveContactTests.test_skip_is_successful_model_decision_without_draft_or_delivery` 覆盖模型明确 `skip`；`test_accepted_receipt_is_not_reported_as_delivered` 覆盖平台已接受但未确认；`test_unknown_is_not_replayed_after_restart_and_late_receipt_still_counts` 覆盖未知结果不重放及迟到回执。
- 撤权、候选过期、配置关闭/变更、静默、冷却和去重分别由上述生产器套件与 `test_proactive_contacts` 的来源撤权、暂停、静默和去重用例覆盖。各事件套件的断言主要以是否调用模型、是否产生 contact 记录、是否触发替身发送表达结果；无需把所有场景重复复制到每个目的。

关系用途不再要求用户先说出固定词。常规联系时机将已启用的关系用途和日常话题放入同一个 `Opportunity`，由现有 Planner 按配置权重选一个方向，再由统一主动联系模型根据真实来源判断发送或跳过；这不会增加模型分类调用。最近私聊原文仍经过当前授权读取与哈希复核，候选分类不是情绪、承诺或意图事实；关系候选也继续服从常规空闲、冷却、未回应和活动曲线门槛。固定词正则只保留给显式诊断兼容，不决定自动主动消息是否进入候选。亲近、玩笑、修复和邀请各有完整 compose/投递用例；邀请另覆盖只有共同兴趣时模型可跳过，以及明确拒绝时不投递。`followup` 只读取同一关系内已确认送达的主动消息历史，等待期未到不建立候选，且新输入会使其失效。

屏幕生产器会返回带 `proactive.screen` 来源的专属 `ContactIntent`，调度器将该专属来源送入统一 compose、确认投递和 `observe` 回执；撤销屏幕读取授权会令来源校验失败。定向链路还发现并修复 `screen` 未登记目的去重路线导致 compose 抛出 `KeyError` 的问题。

## 统一提示合同

`companion_v2.proactive.prompts.PURPOSE_INSTRUCTIONS` 对 15 个已登记目的逐一提供表达边界，并在 `request_for` 中附加到通用 JSON/角色/授权指令之后。`tests.test_style_prompts.ProactiveStyleTests.test_each_registered_purpose_has_its_own_evidence_guidance` 检查目的集合与逐类装配；这些断言证明提示合同，不证明没有生产器的目的已接通。

`affection`、`care`、`play`、`repair`、`invitation` 使用同一个来源驱动候选器和统一发送链路，各目的均有独立线索与发送/跳过验收。`followup` 覆盖等待、冷却、无新输入时接话、收到新输入后取消；屏幕来源也已走过 compose、确认投递和 `observe` 回执。

定向验收发现普通聊天的基础间隔门原先位于事件候选器之前，会连带挡住各自等待和冷却已满足的跟进、屏幕与关系事件；现已把该门移到事件候选器之后，继续只限制普通聊天。去重合同也增加目的全集覆盖，防止新登记目的进入 compose 后才遇到缺失映射。
