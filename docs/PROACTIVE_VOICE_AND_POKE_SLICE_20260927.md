# 主动语音与主动戳一戳切片

日期：2026-09-27。补齐缺口 T46「主动语音行为」与 T49「主动戳一戳」：主动联系可以在正文之外留一小段语音，也可以先用戳一戳开场，两者都受独立开关、冷却和每日额度约束。

本批只做代码、封存文档与替身测试，没有在线重载、真实 TTS 合成或向 QQ 发送。宿主 TTS 渲染与 OneBot `friend_poke`/`group_poke` 的投递合同由[出站语音强化](CORE_VOICE_REPLY_ENHANCEMENT_20260925.md)、[群聊独立授权与 OneBot 投递闭环](CORE_GROUP_DELIVERY_20260924.md)与本批共同说明。

## V1 参考位置

| 能力 | V1 位置 | 说明 |
| --- | --- | --- |
| 主动戳一戳执行 | `proactive_message.py` `_run_poke_action`（L9769）、`_send_single_poke`（L9756） | 私人 `friend_poke`、群聊 `group_poke`，缺动作时回退 `astrbot_plugin_pokepro` |
| 戳一戳冷却与在途占位 | `proactive_message.py` `_poke_action_cooldown_remaining`（L9737） | `poke_action_cooldown_minutes` 默认 30，另有 `poke_action_inflight_until` 在途占位 |
| 戳一戳次数选择 | `proactive_message.py` `_choose_poke_repeat_count`（L9831）、`_choose_pre_message_poke_count`（L9862）、`_maybe_run_pre_message_poke`（L9896） | 按人格与原因加权抽 1～3 次；发送前概率决定是否先戳 |
| 主动语音执行 | `proactive_message.py` `_run_voice_action`（L9918）、`_create_voice_record_component`（L10568） | 走 TTS 生成 `record` 组件，可延迟本机播放 |
| 主动语音文本截断 | `proactive_message.py` L10472/L10523/L10539/L10559 调 `helpers.py` `_single_line`（L177） | `re.sub(r"\s+", " ", text).strip()[:limit]` |
| 配置解析 | `plugin_bootstrap.py` L1578～L1588 | `enable_poke_action`/`enable_voice_action` 默认 false；`poke_action_max_times` 1（1～3）、`poke_action_cooldown_minutes` 30（0～1440）、`voice_action_max_chars` 30（6～80） |
| 每日额度 | `proactive.py` `_effective_user_poke_daily_limit`（L1873） | 直接读 `poke_action_max_times`，用户档案可覆盖 |

## V2 落点与理由

| 文件 | 落点 | 理由 |
| --- | --- | --- |
| `companion_v2/proactive/configuration.py` | `proactive.contact` 组新增 6 个字段 | 语音与戳都是「这个联系人可以怎样被联系」的关系偏好，和既有免打扰、额度、去重同层继承 |
| `companion_v2/proactive/prompts.py` | `VOICE_INSTRUCTION`、`POKE_INSTRUCTION`、`request_for(..., voice_available, poke_available)`、`contact_output` 白名单 | 表达方式交给提示词；可用性由程序在调用前算好，不在提示词里承诺效果 |
| `companion_v2/proactive/service.py` | `single_line`、`local_day_start`、`_last_plan_at`、`_planned_pokes`、`_voice_available`、`_poke_available`、`_expression_plans`；`_generate` 封存 `document["voice"]`/`document["poke"]`；`delivery_text`/`_draft` 只读重放 | 生成期决策、投递期重放与既有 `document["reaction"]` 同形；额度与冷却全部落回 `proactive_contacts` |
| `companion_v2/delivery/service.py` | `OutboundDelivery._content` 接受 `DeliveryContent` 并把 `voice`/`poke` 传给 `DeliveryEnvelope` 与 `ImageDeliveryEnvelope` | 公共后台投递只认「正文 + 图片指纹」；呈现层副作用按原样透传 |
| `companion_v2/adapters/astrbot/onebot.py`（主代理已实现） | 封套带 `voice` 用宿主 TTS 组段（L83～L133），带 `poke` 在正文前调用戳一戳（L156、L182） | 平台动作留在适配器；核心包不导入宿主 |

模型只表达意向：`voice_intent`/`poke_intent` 是布尔开关，朗读内容由程序从正文截取，程序不因为模型说「已发送」就相信效果。`decision=skip` 的输出不允许携带这两个键，避免把「不发送」写成「换个方式发送」。

## 配置字段

| 字段 | 类型 | 默认 | 范围 | 消费者 |
| --- | --- | --- | --- | --- |
| `proactive.contact.voice_action_enabled` | BOOLEAN | `False` | — | `_voice_available`；为假时不追加语音提示段、不封存语音 |
| `proactive.contact.voice_action_max_chars` | INTEGER | `30` | 6～80 | `_expression_plans` 截取 `speech` |
| `proactive.contact.voice_action_cooldown_minutes` | INTEGER | `60` | 0～1440 | `_voice_available` 的最小间隔 |
| `proactive.contact.poke_action_enabled` | BOOLEAN | `False` | — | `_poke_available`；为假时不追加戳提示段、不封存戳 |
| `proactive.contact.poke_action_daily_limit` | INTEGER | `1` | 0～20 | `_poke_available` 的当日次数上限（按本地日） |
| `proactive.contact.poke_action_cooldown_minutes` | INTEGER | `30` | 0～1440 | `_poke_available` 的最小间隔 |

六个字段都按该文件既有写法注册：布尔进 `defaults` 字典、整数进 `(name, default, min, max)` 元组，取值范围由 `FieldDefinition.validate` 统一拒绝，不需要额外的 `ContactField.validate` 专用分支。`capability_configuration`（`_conf_schema.json`）本批不改：字段由 `with_contact_fields` 汇总进公共注册表，属于 V2 配置正本。

## 额度与冷却记账口径

全部基于既有 `proactive_contacts` 表，不新增表、不新增列、不升级 schema：

- 归属：`origin_key = context.key`，即一个完整私聊窗口；同联系人同窗口共用一份冷却与额度。
- 语音冷却：取 `json_extract(record_json, '$.voice') IS NOT NULL` 的最近一条 `created_at`，加 `voice_action_cooldown_minutes`；`0` 表示不设冷却。窗口内已有语音封存时不产生第二条。
- 戳一戳当日额度：`COUNT(*) WHERE origin_key = ? AND created_at >= 本地日起点 AND json_extract(record_json, '$.poke') IS NOT NULL`。本地时区取该关系自己的 `quiet_timezone`（默认 `Asia/Shanghai`），起点即该时区的当日 00:00 换算成 UTC；跨本地日自动归零，无需定时任务或计数器。
- 戳一戳冷却：同法取最近一条含 `$.poke` 的 `created_at` 加 `poke_action_cooldown_minutes`。
- 封存即占用：额度与冷却按「已封存计划」记账，而不是按平台回执。语音合成失败、戳一戳超时或结果未知都不会把额度退回——戳可能已经到达对方，退回会突破管理员配置的上限；文本已封存也说明这次表达的额度已经用掉。
- 被守卫清空的正文（`skip`）不写 `voice`/`poke`，因此不占用额度也不进入冷却。
- 可用性在生成前算一次用于提示词，封存前在同一事务里用新的当前时间重算一次；模型即使凭空给出意向，也必须再过一次程序门控。
- 投递期不重新决策这两个开关：`delivery_text` 只读封存行，重启、冷却或额度变化都不会改写已封存计划。授权、暂停、免打扰、来源与去重仍在投递前照旧复核；只有「这次要不要用语音/戳」这一表达选择按原计划执行。

## 为什么语音与戳不进指纹

`payload_hash` 仍是 `manifest_hash(正文, 图片清单)`，封套授权、回执核对与「未知不重放」都只看它：

- 语音和戳是尽力而为的呈现层。TTS 失败、Provider 不可用、戳一戳超时都是常见结果，把它们计入指纹会让一次已经授权、已经封存的正文因为播放层失败而变成「载荷不一致」，从而停止发送或误报冲突。这与会话语音「合成失败保留图文」的既有决定一致。
- 计划的真实性由封存记录自证：`VoicePlan`/`PokePlan` 存在 `proactive_contacts.record_json` 里，投递前由 owner 重新解析并校验；篡改或缺字段会得到 `contact_draft_unavailable`，不会静默降级成纯文本。
- 因此 `delivery_text` 只读封存行、不重新决策：重启后按原计划投递，冷却或额度在重启后变化也不会改变已经封存的那一条。

## 未迁移项

| V1 能力 | 现状 | 原因 |
| --- | --- | --- |
| TTS 本机播放（`enable_tts_local_playback`、音量、最小间隔、直播专用限制） | 未迁移 | V2 主动语音只把音频交给平台会话；在本机出声属于独立设备输出与账号绑定，需要自己的授权与回执链 |
| `pokepro` 回退 | 未迁移 | V1 在客户端没有 `friend_poke`/`group_poke` 时导入第三方 `PokeSender`；V2 只用原生 OneBot 反向上行动作，动作失败只记日志，不伪造成功 |
| V1 字符串回执 | 未迁移 | V1 把「poke：已轻轻戳了 X 一下」这类文本回灌模型上下文；V2 不把呈现结果写成事实，也不在提示词里声称已经发送，正文投递仍以平台回执为准 |
| V1 单次多次数的双重语义 | 未迁移 | V1 `poke_action_max_times`（1～3）既是单次重复次数又是每日上限；V2 拆成 `poke_action_daily_limit`（0～20，按本地日）与固定 `PokePlan(count=1)`，连戳与按用户覆盖不在本批范围内 |
| V1 语音 Provider 选择、`<pc_tts>` 标签、`voice_only` | 未迁移 | 主动语音固定 `provider_id=""`（由宿主按原会话取当前 TTS Provider）、`position="after_text"`、`delivery_mode="voice_and_text"`，正文永远保留；外语译文与隐藏正文属于被动回复强化链 |

## 验证

```powershell
cd C:\Users\99505\.astrbot\data\plugins\astrbot_plugin_private_companion_v2
$env:PYTHONPATH='C:/Users/99505/.astrbot/backend/app;C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/.p4-tmp'
$env:TEMP='C:\Users\99505\.astrbot\data\plugins\astrbot_plugin_private_companion_v2\.p4-tmp\temp'; $env:TMP=$env:TEMP
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_proactive_voice_poke -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_proactive_contacts tests.test_proactive_reactions tests.test_delivery_components tests.test_astrbot_onebot -q
```

本批新增 `tests/test_proactive_voice_poke.py` **14 项通过**，覆盖默认值与越界拒绝、开关关闭不封存不投递、开关打开按意向封存、语音冷却、戳一戳每日额度与跨本地日重置、事务内守卫清空正文时两者都放弃、低置信度跳过、封存计划被篡改时报 `contact_draft_unavailable`、重启后按原计划投递，以及 OneBot 侧「先戳后发」、戳失败不影响正文、无计划时仍是单次调用。

回归 `tests.test_proactive_contacts`、`tests.test_proactive_reactions`、`tests.test_delivery_components`、`tests.test_astrbot_onebot` **47 项通过**。另按投递链相邻范围跑了 `tests.test_proactive_dedup`、`tests.test_proactive_text_presentation`、`tests.test_background_history`、`tests.test_contact_scheduling`、`tests.test_conversation_messages`、`tests.test_astrbot_group_delivery`：**85 项中 84 项通过**，唯一失败是 `tests.test_astrbot_group_delivery.test_mode_defaults_and_existing_fingerprints_remain_compatible`，与本批无关——该断言用未经归档裁剪的 `asdict` 复算 `MultiHostSettings.fingerprint`，而指纹会主动剔除 `common` 里后加的 `voice_reply_enabled`/`voice_reply_policy`、`streaming`、`segmentation` 和路由字段；本批只读地验证过指纹公式本身自洽，未改 `astrbot_host/`。

全部使用替身模型、替身 TTS 段与本地 socket 形状，没有调用真实 TTS Provider、没有向 QQ 发送；真实客户端的语音与戳显示仍需现场验收。
