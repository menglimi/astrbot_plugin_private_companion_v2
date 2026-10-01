# P4 批次切片（2026-09-27）：D 段表达与时机缺口

依据 [V2 缺口补全任务清单](V2_GAP_CLOSING_TASKS_20260927.md) 的 **P4（D 段表达与时机）** 推进。本批按用户要求「充分参考 V1 实现 → 在 V2 框架约束下改造」，并把逐项测试合并为**一次统一回归**，不再一项一跑。

## 范围与结论

| 编号 | 任务 | 状态 | 切片记录 |
| --- | --- | --- | --- |
| T44 | 场景风格提示词 | 本批之前已完成 | [配置缺口小批](CONFIG_GAP_BATCH_20260927.md) |
| T45 | 组件顺序策略（@/表情等组件位置补齐） | **已完成** | 本页 |
| T46 | 主动语音行为 | **已完成** | [主动语音与戳一戳](PROACTIVE_VOICE_AND_POKE_SLICE_20260927.md) |
| T48 | 表情低延迟模式/向量回填/候选上限 + 检索排序改造 | **已完成** | 见该切片文档 |
| T49 | 主动戳一戳 | **已完成** | [主动语音与戳一戳](PROACTIVE_VOICE_AND_POKE_SLICE_20260927.md) |
| T50 | 跨群转述与 @ 群友（atrelay） | **排后**（依赖未开工的 T27 世界书/知识库与群成员识别；`atrelay` 的目标解析、受众切换与跨群授权都建立在 T27 之上） | — |
| T51 | 引用触发策略 | **已完成** | 本页 |
| T52 | 繁忙回复闸门 | **已完成** | [繁忙回复闸门](BUSY_REPLY_GATE_SLICE_20260927.md) |

## 共享合同：一次出站计划（T45/T46/T49/T51 的共同底座）

V1 在这四项里各有一套「在事件上打 memo、投递前再决定」的做法（`event_dispatch.py` 的引用 memo、`segmented_message.py` 的链式组件、`proactive_message.py` 的戳/语音计划）。V2 的投递契约是「封存即不可变、回执即事实」，因此在 `companion_v2/delivery/plan.py` 引入一个**出站计划**，把两类事实严格分开：

- `OutboundPlan`（**内容**：引用目标、@ 成员、平台表情、组件顺序）——由**已封存批次**的不可变输入重新推导（`companion_v2/conversation/outbound_plan.py`）：设置来自批次封存时的回复快照，引用目标与 @ 成员来自封存的入站事件，段序来自已封存分段。生成与投递用同一纯函数，因此投递出去的就是被复核过的那一条，**不需要新增计划列、也不改动绑定正文与原图的 payload 指纹**。
- `VoicePlan` / `PokePlan`（**尽力而为的呈现层副作用**）——与会话语音同一口径：由 owner 在投递前从自己的封存行重读并校验（`proactive/service.py` 的 `_draft`），失败只降低体验，不改变已授权正文；因此**不进 payload_hash**。
- `DeliveryContent`——后台投递 owner 的返回类型（正文 + 有序原图 + 可选计划/副作用）。

编码侧统一在 `companion_v2/adapters/astrbot/onebot.py`：`reply` 段固定在消息最前，`at`/`face` 段按组件顺序进入同一条 `message` 数组；带 `voice` 计划的封套用宿主 TTS 渲染（`provider_id=""` 时取当前 TTS Provider）；带 `poke` 计划的封套在正文之前单独调用 `friend_poke`/`group_poke`。

## T45 组件顺序策略

**V1 参考**：`segmented_proactive_component_order`（有序 7 元列表，默认 `voice,at,text,face,image,other,reaction`）、`segmented_proactive_at_strategy`、`segmented_proactive_face_strategy`（`segmented_message.py:511-626` 的 `plan_component_chunks`：引用摘出不参与排序，其余组件按 rank 稳定排序；`inline/separate/previous/next` 决定与相邻正文的关系）。

**V2 落点与改造**：

- `conversation.presentation.component_order`（TEXT，JSON 列表，默认 `"[]"`）。**空值＝保持现有行为**（`image_position` + 语音 `position`），只有显式声明时才改序——V1 的四值位置语义在 V2 已被压缩为 before/after（一段＝一个信封，不是 V1 的「一链多 chunk」），因此不做机械平移。
- 组件种类扩为 `text/image/voice/at/face`（`delivery/components.py`）：`at` 只接受十进制账号、`face` 只接受小整数；不可用标识符被**丢弃而不是拒绝整条回复**。
- 未显式声明顺序时：@ 紧贴正文之前，平台表情收尾（可预测的默认）。
- 消费者：`build_component_plan`（编码）、`reply_management.preview`（离线预览返回 `component_order`）。

**设计差异（明确不迁）**：V2 出站没有平台原生 `face` 生产者——表情由 `expression.reactions` 素材库承担（QQ 表情格式即 `sub_image_type=1` 的图片段），因此只保留编码与排序能力，不登记「表情位置」配置；`other/reaction` 两类在 V2 无独立载体（`reaction` 即图片段）。`separate/previous/next` 三值不迁移（见上）。

## T51 引用触发策略

**V1 参考**：三层决策——场景开关 `enable_proactive_quote_trigger_message`（总开关，默认关）+ `enable_quote_group_reply`/`enable_quote_group_interjection`/`enable_quote_private_proactive`，目标策略 `quote_target_strategy`（`current/quoted/auto`），短回复阈值 `quote_skip_short_reply_chars`，同对象只首条 `quote_group_reply_once_per_target`；构造组件时按平台能力试错并在进程内 dict 里记账。

**V2 落点与改造**（`conversation.presentation` 组，随回复批次封存）：

| 字段 | 类型/范围 | 默认 | 语义 |
| --- | --- | --- | --- |
| `reply_quote_enabled` | BOOLEAN | `False` | V1 总开关的等价物：默认不引用（与 V1「总开关关 + 子开关开＝净效果不引用」一致） |
| `reply_quote_group_enabled` | BOOLEAN | `True` | 群回复是否引用触发消息 |
| `reply_quote_first_part_only` | BOOLEAN | `True` | 只在本轮第一条正文段引用（V1 `quote_group_reply_once_per_target` 的 V2 等价：按**轮次**而不是进程内 memo，重启后语义不变） |
| `reply_quote_skip_chars` | INTEGER 0–120 | `0` | 去空白字符数 ≤ 阈值不引用 |
| `reply_mention_speaker_enabled` | BOOLEAN | `False` | 群回复是否 @ 触发者（为 V2 出站 `at` 组件提供真实生产者，默认关闭以免改变现有 QQ 行为） |

**只引用本轮触发消息**：引用目标与 @ 成员取批次**第一个未撤回入站事件**的原生消息号与账号，且必须是十进制平台标识（测试夹具里的合成 id 会被跳过而不是伪造引用）。

**设计差异（明确不迁）**：① `quote_target_strategy` 的 `quoted/auto` 依赖「本轮是被引用消息触发」的原生原消息号，V2 私聊主动链没有可追溯的原生消息号（`delivery/history.py` 只保存 event_key/hash 与已确认投递的 `platform_ref`），本轮只实现 `current`；② `enable_quote_private_proactive`（私聊主动引用）同上理由不迁；③ `enable_quote_group_interjection` 在 V2 群插话与群回复共用同一条封存批次，因此由 `reply_quote_group_enabled` 一并覆盖，不另设开关；④ V1 的「平台能力试错 + 进程内 dict」不迁——V2 直连 reverse-WS，只发 `{"type":"reply","data":{"id":…}}`，群引用目标就是同一 scope 的原始消息号。

## T46 / T49 主动语音与戳一戳

见[主动语音与戳一戳切片](PROACTIVE_VOICE_AND_POKE_SLICE_20260927.md)：`proactive.contact` 新增 6 字段（`voice_action_enabled`/`voice_action_max_chars`/`voice_action_cooldown_minutes`/`poke_action_enabled`/`poke_action_daily_limit`/`poke_action_cooldown_minutes`），计划由模型意向 + 程序门控生成并封存进 `proactive_contacts.record_json`，额度与冷却全部读既有表（**无新表、无 schema 变更**），投递期只读封存计划，戳在正文之前单独调用 OneBot 动作且失败不阻塞正文。

## T48 表情检索与配置

见该任务切片文档（低延迟缓存、候选上限、向量权重/阈值/扫描上限、后台补向量开关与间隔、复核三态，以及向量主导排序、语义簇与用后降权；未迁移项为每意图偏好（需 schema 升级）、语义触发表情（依赖未开工的入站意图分析）、表达式专用 embedding provider）。

## T52 繁忙回复闸门

见[繁忙回复闸门切片](BUSY_REPLY_GATE_SLICE_20260927.md)：`conversation.busy_gate` 组（开关、延迟区间、忙后主动缓冲、关键词表），忙碌判据取 `agenda` 的已接受 `role_plan` 事件窗口（V2 没有 V1 式自由文本日程），延迟写进 `conversation_flows.due_at` 这一持久计时正本（**不 sleep、不占协程**），并同步抬升 `deadline_at` 以免被 `deadline_elapsed` 丢弃；主动链在 `proactive/scheduling.py` 顺延到忙碌结束 + 缓冲。

## 未迁移项汇总（本批）

| 项 | 理由 |
| --- | --- |
| T50 跨群转述与 @ 群友 | 依赖 T27（世界书/知识库 + 群成员识别）未开工；跨群目标解析、受众切换与跨群授权都建立在其上 |
| V1 组件位置四值（separate/previous/next） | V2 一段＝一个信封，无「一链多 chunk」结构 |
| 平台原生 `face` 生产者 | V2 表情由素材库承担；仅保留编码与排序 |
| 私聊主动引用（`enable_quote_private_proactive`）与 `quoted/auto` 策略 | V2 私聊主动无可追溯原生消息号 |
| V1 进程内「同对象只首条」memo | 重启即丢；改为按轮次封存口径 |
| V1 主动语音失败即放弃整次动作 | 与 V2 既有契约相反（非法语音被忽略、保留文字与图片） |
| V1 `poke_action_max_times` 双重语义、pokepro 依赖、字符串回执、本机播放 | 分别拆成日额度 + 冷却、改用自有 reverse-WS、改用 `DeliveryReceipt`、V2 无本机音频能力 |
| V1 繁忙闸门的群聊 12 秒硬顶与「新消息取消陈旧回复」 | V2 群聊已有 `short_input_wait`/插话窗口；V2 语义是延迟期内合并而非取消 |

## 验证

统一回归（AstrBot 自带 Python + `backend/app` 入 `PYTHONPATH`；全部使用合成事件、模型替身与本地 reverse WebSocket ACK）。按用户「减少一项项测试、统一测试」的要求，本批**只在收口时跑一次**覆盖全部 P4 改动面的大批：

```powershell
cd C:\Users\99505\.astrbot\data\plugins\astrbot_plugin_private_companion_v2
$env:PYTHONPATH='<AstrBot>/backend/app;<plugin>/.p4-tmp'     # .p4-tmp 仅提供沙箱临时根垫片
$env:TEMP='<plugin>\.p4-tmp\temp'; $env:TMP=$env:TEMP
& '<AstrBot>/backend/python/python.exe' -X utf8 -W ignore -m unittest `
  tests.test_reply_outbound_plan tests.test_proactive_voice_poke tests.test_reaction_retrieval_settings `
  tests.test_busy_reply_gate tests.test_delivery_components tests.test_astrbot_onebot `
  tests.test_astrbot_voice_reply tests.test_voice_reply tests.test_segmented_stream_delivery `
  tests.test_reply_management tests.test_group_safety_guards tests.test_reply_text_processing `
  tests.test_group_image_review tests.test_group_image_delivery tests.test_group_participation `
  tests.test_proactive_contacts tests.test_proactive_reactions tests.test_background_history `
  tests.test_conversation_messages tests.test_semantic_integration tests.test_semantic_host_api `
  tests.test_expression_style tests.test_host_application tests.test_host_recovery `
  tests.test_contact_scheduling tests.test_isolation
```

**结果：Ran 381 tests / OK（465.9 秒）**，无失败、无跳过。其中新增定向测试：`test_reply_outbound_plan` 16、`test_proactive_voice_poke` 14、`test_reaction_retrieval_settings` 25、`test_busy_reply_gate` 21（矩阵内的 host 端到端用例均真断言 `reason == "busy_delay"`，无跳过守卫）。

`compileall companion_v2 astrbot_host main.py` 退出 0；本批新增/修改文件的 UTF-8 无 BOM、LF、末尾换行校验通过。

**已知与本批无关的既有失败**：`tests.test_astrbot_group_delivery.test_mode_defaults_and_existing_fingerprints_remain_compatible`。该用例用「只剔除 `group_delivery_mode` 的 `asdict`」复算 `MultiHostSettings.fingerprint`，而指纹实现会无条件剔除 `common.voice_reply_enabled`/`common.voice_reply_policy`（并在默认时剔除 `segmentation`/`streaming`）与 4 个路由字段（`multi_settings.py:62-77`），因此在语音回复切片引入这些字段后该断言已不可能成立；已用脚本复核确认与 P4 改动无关。修复属于 `astrbot_host/` 身份指纹口径的维护范围，本批未改动该测试。

## 边界

未接「陪伴小屋」页面（第②阶段统一接入，新字段已在统一配置注册表内）；未重载在线插件、未调用真实模型/TTS/QQ、未构建交付包；未读取或修改 V1 用户数据；未新增数据库表或 schema 迁移。真实平台上的引用显示、@ 呈现、语音与戳的手感、表情排序手感仍需现场验收。

> 测试环境备注：本机 DSH 文件沙箱会把 `tempfile.mkdtemp` 的 `0o700` 目录映射成创建进程也无法写入的目录，导致测试临时根创建失败。上面的 `.p4-tmp` 只提供一个 `sitecustomize.py`（把 `os.mkdir` 的 mode 归一为 `0o777`）与一个可写的 `TEMP` 根；它是本地脚手架、不属于交付内容，且沙箱 ACL 使其中部分临时目录无法删除（删除动作本身被沙箱拒绝），需要时可在沙箱外直接删除整个 `.p4-tmp/` 目录。常规环境无需该垫片。
