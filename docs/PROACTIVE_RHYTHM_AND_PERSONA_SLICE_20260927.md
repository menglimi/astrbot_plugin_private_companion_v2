# 主动节奏、预约执行、日锚点与主动人格判定（T38 / T39 / T40 / T41）

日期：2026-09-27。范围：V2 缺口清单 P2 的四个主动缺口任务。全部实现落在 `companion_v2/proactive/`（外科式修改 + 新文件）与 `companion_v2/agenda/appointments.py`，配置进既有 `proactive.contact` 组，**不新增数据表、不升级 schema、不新增发送路径**。

> **历史设计，已于 2026-10-16 调整。** 本文记录的主动尝试次数与人格复核每日上限已退役。当前唯一主动次数上限是每个私聊窗口每日实际联系数；决策和复核调用只统计，不再设置次数硬上限。当前合同见 [自动联系与历史](CORE_AUTOMATIC_CONTACT_AND_HISTORY_SLICE.md)。

参考的 V1 实现（只读）：`proactive.py`（爆发式发送、小时活跃曲线、强度预设、收束留白、人格判定阈值/缓存/日限）、`proactive_engine.py`（`_pick_daily_greeting_event`、`_pick_insomnia_night_event`、`_can_send_insomnia_night_message`、`_review_planned_proactive_with_model`、`_in_llm_timer_pre_silence_window`）、`proactive_message.py`（`proactive_share_probability`）、`daily_state_tick.py`（锚点触发）、`plugin_bootstrap.py` + `_conf_schema.json`（逐键核对键名、默认值与取值范围）。

## 1. T38 主动节奏增强

落点：新文件 [`proactive/rhythm.py`](../companion_v2/proactive/rhythm.py)（节奏判定）+ [`proactive/scheduling.py`](../companion_v2/proactive/scheduling.py) 的机会权重与既有投递链；正文长度指引进 [`proactive/prompts.py`](../companion_v2/proactive/prompts.py)。

| V1 键 | V2 字段 | 默认 | 语义与消费者 |
| --- | --- | --- | --- |
| `enable_proactive_burst` | `proactive_burst_*` 总开关 | `false` | 一轮内追加短消息；关闭时槽位网格与改造前完全一致。 |
| `proactive_burst_max_messages` | `proactive_burst_max_messages` | `2`（2–3） | 单轮上限；与强度档位取较小值。 |
| `proactive_burst_gap_min_seconds` / `_max_seconds` | 同名字段 | `45` / `180` | 段间隔；由 `(context.key, 上一条 contact_id)` 定种，重启不重掷。 |
| `proactive_hour_activity_curve` | `proactive_hour_activity_curve` | V1 原曲线 | 24 个小时权重（钳制 0.05–2.0；长度不对回退默认，单项不可用回退 1.0）。 |
| （V1 无开关，恒生效） | `proactive_hour_activity_enabled` | `false` | 曲线是否参与机会准入；V2 采用显式开关，避免改动存量部署的节奏网格。 |
| `proactive_intensity_preset` | `proactive_intensity_preset` | `off` | 五档 `off/balanced/high_private/high_group/live`（沿用 V1 别名，含「直播/高频」），只缩放已登记值：间隔×档位系数、空闲门槛×档位系数、爆发条数上限、正文长度指引。 |
| `proactive_closing_grace_minutes` | `proactive_closing_grace_minutes` | `45` | 收束留白时长。 |
| （V2 新增阈值） | `proactive_closing_contacts_threshold` | `3` | 连续已确认主动达到该条数后进入留白；新输入或留白结束即释放。 |
| （长度指引） | `proactive_intensity_body_chars` | `0` | 0=沿用档位；>0 时作为提示词长度上限（不截断已封存正文）。 |

实现要点：

- **爆发一轮**=最后一条已接受输入之后的连续已确认主动。只有上一条已封存主动的目的为 `chat` 时才续发；提醒、天气、官方预警、问候、分享都不会拖着爆发尾巴。存在未确认投递（`pending/dispatched/accepted/unknown`）时不再叠加下一条。
- 爆发槽位自成时间轴：`opened = 上一条 created_at + gap`，`expires = opened + min(gap, 5min)`；错过不补发，任务 ID 由 `(context.key, opened, index)` 派生，唯一且可复算。
- 爆发校验（`validate_burst`）按 **marker 里的来源 contact_id** 重新推导，而不是"最新一条"，因此提交事务里刚写入的草稿不会把自己的校验推翻。
- 额度不变：爆发仍受 `max_contacts_24h`、关系额度、尝试额度与免打扰约束；档位只能收紧，不能放宽任何额度。
- 曲线准入用 `(context.key, "hour-activity", opened)` 定种，同一槽位永不抖动，也不因重启重掷。

## 2. T39 预约主动执行

落点：新文件 [`agenda/appointments.py`](../companion_v2/agenda/appointments.py)（`upcoming_occurrences` / `occurrence_at` / `AppointmentSilence`）+ 外科式改造 [`proactive/calendar_events.py`](../companion_v2/proactive/calendar_events.py) 与 `scheduling.py`。

| V1 键 | V2 字段 | 默认 | 语义 |
| --- | --- | --- | --- |
| （原 30 分钟常量） | `appointment_lead_minutes` | `30`（0–240） | 预约前多久可开口；`0` 表示**到点开口**（机会在预约时刻开、至少保持 1 分钟）。 |
| `max_proactive_plan_lag_minutes` | `appointment_lag_minutes` | `0`（0–180） | 预约时刻之后仍可开口的时长；超时即丢弃，不补发、不重放。 |
| `timer_pre_silence_minutes` | `appointment_pre_silence_minutes` | `20`（0–240） | 预约前静默窗口：该窗口内不产生"没有由头"的主动（普通日常机会与问候），预约提醒本身与其它事件型机会保持各自既有授权。 |

- 预约仍复用既有 `agenda` 记录（`kind=commitment`、`state=accepted`、人类明确接受、无独立提醒）、原 revision、`accepted_by` 与来源复核；来源发布、`record_hash`、撤回传播链路未改，默认值下行为与改造前一致（`lead=30, lag=0`）。
- 静默窗口用 `CalendarService.occurrences` 读取，按窗口 + 配置解析令牌做 30 秒节流缓存（与预约扫描同一节奏），不新增调度器；日历不可读时视为"没有已知预约"（静默是礼貌边界，不是授权闸门）。
- 未知不重放：机会窗口由 `due ± 配置` 推导，任务 ID 只由 `(context.key, record_id, sequence, due)` 派生；停机错过的预约只会在 `lag` 内仍可开口，否则永久丢弃。

## 3. T40 早午晚锚点问候 + 失眠深夜消息

落点：新文件 [`proactive/greetings.py`](../companion_v2/proactive/greetings.py)（`GreetingContactEvents`），由 `scheduling.py` 在预约机会之后、事件型机会之前选择。

| V1 键 | V2 字段 | 默认 | 语义 |
| --- | --- | --- | --- |
| `enable_daily_greetings` | `enable_daily_greetings` | `false` | 早/午/晚各一个本地窗口，每个本地日每个锚点最多一次（机会 ID 含本地日期）。 |
| `greeting_idle_minutes` | `greeting_idle_minutes` | `30`（0–240） | 问候前的空闲门槛；刚说过话就顺延到窗口内下一次调度。 |
| （V1 窗口为硬编码/wake 推导） | `greeting_morning_window` / `_noon_window` / `_evening_window` | `07:45-10:20` / `12:05-13:35` / `20:10-21:20` | 本地锚点窗口（`HH:MM-HH:MM`，同日、起点早于终点）。 |
| `allow_insomnia_night_message` | `allow_insomnia_night_message` | `false` | 深夜消息总开关。 |
| （V1 硬编码 23:00–06:00） | `insomnia_night_start` / `_end` | `23:00` / `06:00` | 明确时间窗，支持跨午夜。 |
| `insomnia_night_daily_limit` | `insomnia_night_daily_limit` | `1`（0–3） | 每夜上限：夜窗按时长等分为 N 个槽位，每槽最多一条；`0` 停用。 |
| （V1 要求失眠状态） | `insomnia_require_sleep_state` | `false` | 置真时要求角色状态里存在存活的 `kind=sleep` 临时状况；状态不可读按不满足处理。 |
| `proactive_share_probability` | `proactive_share_probability` | `100`（0–100） | 角色近况分享（`life`/`creation`）机会的准入概率；默认 100＝保持既有确定性行为（V1 默认 45 会随机丢掉过半分享机会，记为默认值差异）。 |

- **本地时间**全部按 `quiet_timezone` 计算；锚点与夜窗都用 `zoneinfo` 组合本地日期，不做系统本地时区猜测。
- **免打扰互斥**：两条路径都先过 `preferences.reason(问候目的)`。深夜消息并不豁免免打扰——默认免打扰为 23:00–07:00，正好覆盖默认夜窗，因此默认配置下深夜消息不会发出；这是相对 V1（失眠豁免免打扰）的**有意差异**，也是本任务"不得在免打扰时段发出"的要求。
- 深夜消息的睡眠状况只作为提示词里的"角色状态提示"，不是事实来源；未回应、未读、对方在睡等推断仍被禁止。

## 4. T41 主动人格判定

落点：新文件 [`proactive/persona_judge.py`](../companion_v2/proactive/persona_judge.py) + [`proactive/service.py`](../companion_v2/proactive/service.py) 两阶段提交 + `scheduling.py` 的判定领取。

| V1 键 | V2 字段 | 默认 | 语义 |
| --- | --- | --- | --- |
| `enable_llm_proactive_persona_judge` | `enable_llm_proactive_persona_judge` | `false` | 默认关闭（V1 默认 true，V2 按"涉及模型调用默认关闭"）。 |
| `proactive_persona_judge_send_threshold` | `proactive_persona_judge_threshold` | `62`（0–100） | 放行阈值：`decision=send` 且 `score ≥ 阈值` 才放行。 |
| `proactive_persona_judge_cache_minutes` | `proactive_persona_judge_cache_minutes` | `180`（0–720） | 相同 (目的, 正文) 判定缓存窗口，落在既有 `proactive_contacts` 记录里。 |
| `proactive_persona_judge_max_daily` | `proactive_persona_judge_daily_limit` | `12`（0–100） | 每个本地日最多消耗的判定模型调用次数；用尽后不再放行未判定正文。 |
| `PROACTIVE_PERSONA_JUDGE_PROVIDER_ID`（供应商 ID） | `proactive_persona_judge_exempt_purposes` | `""` | 供应商 ID 在 V2 不是字段（模型按已注册任务档路由，见"设计差异"）；本字段替代 V1 的"特权计划跳过判定"：列出的联系目的豁免判定。 |

实现要点（两阶段）：

1. **封存草稿**：成稿通过框架异常防护、替换与违禁词闸门、去重后，若判定适用则写入 `proactive_contacts`，`decision="judge_pending"`，并在同一事务内提交 `proactive.judge` 后台任务（`idempotency_key=contact_id`）。此时**不排队投递**。
2. **判定**：`ContactSchedule.advance()` 用空闲后台槽位领取判定任务；判定从草稿所属的原始已接受批次重新取人格（`validate_origin` + `_origin` 复核批次、角色哈希），按封存正文提问。
3. **收口**：一个事务里二选一——放行则把 `decision` 改为 `send` 并用既有 `delivery.queue` 排队（语音/戳一戳计划仍按原样保留），否则改为 `skip`。语义、来源、受众、授权、身份都不被判定修改；判定只回答"能不能发"。
4. **失败/未知一律不发**：模型档未注册、当日额度用尽、机会无判定时间、模型报错、输出不合契约、判定任务在重启后无法续做（原输入随进程消失）——全部落到"扣下草稿"，并在记录里留下 `judge.failure`；`observe()` 暴露 `judge/judge_allowed/judge_reason`。
5. **不占额外并发**：判定是独立后台任务（不与成稿任务嵌套），因此 `background_slots=1` 的默认部署也能工作：成稿 -> 判定 -> 投递依次使用同一个槽位。
6. **判定中的正文不带表情原图**：表情选择会发布原图，不能先于判定发生；`judge_pending` 的载荷只有正文（语音/戳一戳是记录里的计划，仍保留）。这是相对"未开启判定"路径的一处有意收紧。

### 设计差异（未迁移项）

- `PROACTIVE_PERSONA_JUDGE_PROVIDER_ID`：V2 由已注册的 `ModelTaskProfile` 决定供应商（`model.proactive.judge.*` 组），不再按字段指定供应商 ID。
- V1 的 `rewrite/defer` 判定结果不迁移：V2 判定只影响是否发送（改写会牵动已封存正文、来源与操作回执）。
- V1 `timer_config` 其余 7 项（引用相关 7 项）由 T51 完成；`enable_proactive_decorating_hooks`、`enable_precise_platform_send` 是 AstrBot 宿主发送路径细节，V2 只有一条投递链且未知不重放，不迁移；`check_interval_seconds` 由 V2 宿主唤醒循环与 `interval_seconds/idle_seconds` 承担。
- `timer_pre_silence_minutes` 的"模型预约"语义（V1 由模型安排临时预约）在 V2 落在既有 `agenda` 已接受约定上；V2 没有"模型自行创建预约"的通道，也就不需要额外的预约来源校验。

## 5. 配置

29 个新字段全部进**既有 `proactive.contact` 组**（`configuration_fields()`），由 `with_contact_fields` + `ContactConfigurationOwner` 汇总进公共注册表，因此：

- **不需要**给宿主配置汇总行追加 `extra` 或 `owners` 项，也不需要改 `_conf_schema.json`（与 T46/T49 同口径）。
- 新增的取值校验：`proactive_intensity_preset`（档位名，含 V1 别名）、`proactive_hour_activity_curve`（24 项归一化）、`greeting_*_window`（`HH:MM-HH:MM`）、`insomnia_night_start/end`（`HH:MM`）、`proactive_persona_judge_exempt_purposes`（已登记目的子集），均返回规范化值并在非法时抛 `ConfigurationError`。

### 需要主代理的接线（唯一一处）

主动人格判定需要一个**已注册的模型任务档**；档位由宿主装配时传入，请在 `astrbot_host/multi_session.py`（与 `companion_v2/adapters/astrbot/staging.py`）的 profiles 里加一行：

```python
from companion_v2.proactive.service import contact_profile, persona_judge_profile
# 与 contact_profile(...) 并列：
persona_judge_profile(common.provider_id, max_output_tokens=common.max_output_tokens),
```

未接线时的行为是"扣下未判定正文"（fail-closed，`judge.failure=judge_profile_unavailable`），不会发出未判定消息，也不会静默改走其它路径。

## 6. 验证

新增 2 个测试文件，共 31 项：

```powershell
$env:PYTHONPATH='C:/Users/99505/.astrbot/backend/app;C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2;C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/.p4-tmp'
$env:TEMP='<工作区>\.p4-tmp\temp'; $env:TMP=$env:TEMP
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -W ignore -m unittest `
  tests.test_proactive_rhythm_and_greetings tests.test_proactive_appointments_and_judge -q
```

覆盖：字段登记与边界（含非法值拒绝、曲线钳制与回退）、强度档位只缩放不改写、爆发一轮有界（条数/间隔/来源/停轮）、收束留白先扣后放、正文长度提示进请求、锚点本地时间与跨日不重放、问候空闲门槛、免打扰与锚点/深夜互斥、深夜窗口与每夜上限、分享概率只作用于角色分享、预约 lead（含"到点开口"）、预约 lag（错过即丢弃、调大后仍可开口）、预约前静默只约束无由头主动、重复预约逐期有界、判定默认关闭不改行为、放行才投递、低于阈值/不合格输出/档位未注册/日限为 0 一律不发且留下失败原因、相同正文复用缓存、豁免目的不调模型。

回归批次（既有模块 + 本批 2 个新模块）命令与结果见交付回执；本批未新增表、未改 schema 版本，因此没有迁移夹具改动。

## 7. 遗留风险

- 判定中的草稿不占"联系额度"（额度只统计已入队/已投递记录），同一关系在判定进行中理论上多出一份草稿；后台槽位与 `interval_seconds` 把它限制在极短窗口内。
- 判定会消耗一份后台槽位额度；槽位全被其它后台任务占用时判定顺延到下一次调度，期间草稿保持未发送。
- 问候/爆发机会仍受 T52 忙碌闸门约束（`conversation/busy_gate.py` 的事件豁免集合不在本批可改范围），忙碌窗口内会被顺延或错过。
- 免打扰与深夜窗口的默认组合使深夜消息默认不可达（需要运营显式调整免打扰），这是刻意的安全默认。
- 真实现场验收（真实模型供应商、QQ 投递、长期日常运行）仍待现场阶段；本批测试全部使用合成模型与本地发送器。
