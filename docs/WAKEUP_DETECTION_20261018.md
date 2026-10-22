# 用户起床观测与主动问候链设计

日期：2026-10-18。范围：`astrbot_plugin_private_companion_v2` 私聊主动联系。目标是把「用户是否起床」变成一条**有证据、可拒绝、可审计**的主动链条，而不是靠猜语气或猜时间。

## 一、现状：有叫醒，没有起床判定

| 层 | 现有能力 | 缺口 |
| --- | --- | --- |
| `astrbot_host/native_extensions/reality/wakeup_alarm.py` | 定时 TTS 叫醒、重复触达、`acknowledged / snoozed / cancelled` 反馈分类、`last_private_activity_at` 跳过 | 只有「用户回了叫醒」才算已知结果；不回就是 `exhausted / delivery_unknown`，没有把设备活动、屏幕使用、步数当作证据 |
| `astrbot_host/native_extensions/reality/mobile_gateway.py` | 手机设备状态、前台应用摘要、遥测（步数/心率/睡眠时长/活动状态）、位置，均带 `available / age_seconds / stale` | 只作为感知材料注入 prompt，没有进入主动决策 |
| `companion_v2/proactive/greetings.py` | 早晨/午间/晚间锚点 + 夜间窗口，生成一次可选的问候机会 | 提示词明确写「窗口不代表对方刚醒」；是否真的醒来完全不参与判定 |
| `companion_v2/proactive/scheduling.py` | 机会账本、预算、静默时段、空闲门槛、人格判定、去重、送达 | 没有「醒来」这个契机生产者，也没有 wake episode 去重 |
| `companion_v2/role_work/life/body_clock.py` | **角色自己**的睡眠回执 | 不能拿来推断用户；角色刚醒不等于用户刚醒 |

结论：系统知道「现在几点、该不该发」，但不知道「对方是不是刚醒」。所以早安只能按时间窗发，既可能发给熬夜的人，也可能错过真正刚起床的人。

## 二、目标与非目标

目标：

1. 用**多源类型化证据**判断用户当前是否可能已醒，并给出可解释的置信度与醒来时刻。
2. 只有满足条件时，才在当前 wake episode 内开**一次**主动问候机会；其余全部走既有 `proactive_contacts` 机会账本与拒绝原因。
3. 文案只把证据用于「什么时候开口、用什么语气」，不允许声称看见/听见/确认对方起床。
4. 默认关闭；打开后也遵守静默时段、每日预算、未回应暂停、人格判定。

非目标：

- 不做健康诊断、睡眠评分、作息评价。
- 不建立用户画像，不把一次证据写成长期习惯。
- 不新增调度器、不新增发送路径、不新增第二套机会账本。
- 不读取任何自然语言文本做「起床关键词」判断。

## 三、设计原则

1. **无证据不等于睡着，沉默不等于没醒。** 只有设备明确报告睡眠/静止才产生负证据；没有证据就是 `unknown`。
2. **不猜。** 不用消息语气、标点、表情、时间段单独推断起床；这些最多是上下文，不是证据。
3. **类型化，不做关键词。** 只读移动端 API 的封闭枚举（`walking/running/cycling/sleeping/resting`）、时间戳、`available/stale`、步数数值；应用名、标题、正文一律忽略。
4. **证据有寿命。** 每个信号有自己的最大时效；过期即丢弃，不做旧证据累加。
5. **最近负证据优先。** 最近一次「睡眠/静止」之后的正面信号才属于当前 episode；之前的属于上一段。
6. **一次 wake episode 只开一次机会。** episode key 由「醒来时刻 + 本地日期 + 90 分钟桶」决定，跨重启仍可去重。
7. **只做时机，不做事实。** 证据不进入「用户说了什么/做了什么」的事实层，只影响主动开口的时机与温度。
## 四、证据表（`companion_v2/proactive/wake_detection.py`）

| kind | 极性 | 默认时效 | 默认置信 | 来源 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `alarm_acknowledged` | 正 | 12h | 100 | 叫醒会话 `acknowledged` | 用户本人明确回应已醒，最强证据 |
| `explicit_input` | 正 | 3h | 92 | 私聊输入 | 用户正在发消息，证明此刻清醒；仅在安静间隔后算「醒来转变」 |
| `motion_activity` | 正 | 20m | 70 | 手机遥测 `activity.state` | `walking / running / cycling` 等封闭枚举 |
| `screen_resumed` | 正 | 20m | 58 | 前台应用摘要 | 设备重新出现新的前台使用摘要，且未 stale |
| `device_reconnected` | 正 | 20m | 40 | 设备状态 | 设备重新在线并上报，弱信号 |
| `steps_increased` | 正 | 30m | 52 | 步数测量 | 步数高于上一观测，说明身体活动 |
| `sleep_reported` | 负 | 14h | 88 | 遥测 `sleeping` / 叫醒 `snoozed` | 最近状态是睡眠，或用户要求再睡一会 |
| `resting_reported` | 负 | 45m | 45 | 遥测 `resting` | 静止休息，弱负证据；不做强否定 |

融合规则：

1. 先按每个 kind 的 `max_age_seconds` 过滤；未来时间戳（超过 5 秒容差）也丢弃。
2. 取最近负证据 `negative_at`；正面信号必须严格晚于它才属于当前 episode。
3. 当前 episode 置信度 = `max(衰减后单条置信) + min(20, 6 × (独立 source 数 - 1))`。
4. 30 分钟内出现显式证据（私聊输入 / 叫醒确认）→ `confirmed`，置信度 100。
5. 否则 `≥65 → awake_likely`，`≥40 → stirring`，其余 `unknown`。
6. `woke_at` 取当前 episode 最早的显式证据；没有显式证据则取最早正面信号。
7. `episode_key = wake:{本地日期}:{90 分钟桶}:{时区}`。

状态机：

```
unknown ──正面弱信号──> stirring ──多源/更强──> awake_likely ──显式证据──> confirmed
   ▲                        │                         │
   └──── 证据过期 ──────────┴──── 新负证据 ───────────┘  asleep_likely
```

`asleep_likely` 不是「正在睡」的断言，只表示「最近一条可信状态是睡眠/静止」；没有证据时回到 `unknown`。

## 五、主动链条

```
手机网关 / 叫醒会话 / 私聊输入
        │  （已有数据，不新增采集）
        ▼
evidence_from_mobile_snapshot()
evidence_from_wakeup_session()
evidence_from_private_input()
        │  WakeEvidence[]
        ▼
observe() ──> WakeObservation(state, confidence, woke_at, episode_key)
        │
        ▼
contact_decision()  ── 目的开关 / 置信度 / 窗口 / 静默 / 时段 / episode 去重
        │  allowed
        ▼
WakeContactEvents.select()  ── 生成 ContactIntent("greeting", thought)
        │
        ▼
ContactSchedule._plan()  ── 既有空闲门槛、预算、未回应暂停、人格判定、去重
        │
        ▼
既有主动发送与送达回执 ──> proactive_contacts 记录 episode_key
        │
        ▼
用户回复 / 叫醒确认 / 新负证据 ──> 关闭本 episode，不再追发
```

关键边界：

- `WakeContactEvents` 只产出 `ContactIntent`，不直接发送。
- 机会仍然走 `ContactSchedule` + `proactive_contacts` 的既有幂等账本；不新建表。
- 人格判定（`persona_judge`）保留最终否决权；证据不足时模型可以 `skip`。
- 叫醒会话的 `snoozed` 立即写入负证据；`acknowledged` 写入正证据；`exhausted` 本身不产生证据。

## 六、主动决策规则

`contact_decision()` 按顺序返回稳定 reason code：

| 顺序 | reason | 含义 |
| --- | --- | --- |
| 1 | `purpose_disabled` | 问候目的被关闭 |
| 2 | `not_awake_likely` | 状态不是 `awake_likely / confirmed` |
| 3 | `confidence_below_threshold` | 低于配置的最低置信度 |
| 4 | `no_wake_time` | 没有可用的醒来时刻 |
| 5 | `woke_in_future` | 时间戳异常 |
| 6 | `wake_window_elapsed` | 超过醒来后的问候窗口（默认 90 分钟） |
| 7 | `wake_contact_already_sent` | 本 episode 已开过口 |
| 8 | `quiet_hours` | 命中静默时段 |
| 9 | `outside_wake_window` | 不在早晨时段（默认 05:00–12:00） |
| 10 | `wake_contact_candidate` | 允许开一次机会 |

建议配置（全部默认关闭，新增在 `proactive.contact`）：

| 字段 | 默认 | 范围 | 说明 |
| --- | --- | --- | --- |
| `wake_detection_enabled` | `false` | bool | 总开关 |
| `wake_contact_window_minutes` | 90 | 15–240 | 醒来后多久内仍算「刚醒」 |
| `wake_contact_min_confidence` | 65 | 40–100 | 最低置信度 |
| `wake_morning_start` | `05:00` | 本地时间 | 允许问候的起点 |
| `wake_morning_end` | `11:30` | 本地时间 | 允许问候的终点 |
| `wake_contact_max_daily` | 1 | 0–3 | 每日 wake 问候上限 |
| `wake_require_device_evidence` | `false` | bool | 是否必须有多源设备证据（关闭时允许显式私聊单独触发） |
## 七、提示词口径

`intent_summary()` 生成 `Thought.summary`，只包含：

1. 这是一次「用户醒来线索触发的可选问候机会」，并给出状态与参考置信度。
2. 证据的**抽象描述**（例如「用户侧设备从休息状态转为步行、跑步或骑行等活动」），不出现设备名、传感器名、数值、字段名、应用名。
3. 明确边界：不证明亲眼看见/听见/确认；不说「我看到你醒了」「我一直在看着你」；不复述观察过程。
4. 只用于时机与语气：像自然碰上这个早晨，先带来自己的话、轻话题或真实近况；不追问睡了多久、不评价作息、不要求报平安、不把起床变成打卡。
5. 允许 `skip`：没有自然的话、线索不够确定、对方可能不想被打扰时就不发。

不新增「起床关键词」提示，也不要求模型从文本判断对方是否起床；判定已经由证据层完成。

## 八、实现落点与顺序

| 阶段 | 文件 | 内容 | 状态 |
| --- | --- | --- | --- |
| P0 | `companion_v2/proactive/wake_detection.py` | 证据类型、状态机、episode key、决策、提示摘要、三个适配器 | 已完成 |
| P0 | `tests/test_proactive_wake_detection.py` | 14 个纯单元测试 | 已完成 |
| P1 | `companion_v2/proactive/wake_events.py` | `WakeContactEvents.select/validate`：调用 port 取证据，产出 `ContactIntent("greeting", thought)`，marker 带 episode_key | 已完成 |
| P2 | `companion_v2/proactive/scheduling.py` | `ContactSchedule` 新增 `wake_port`；`_plan()` 在问候锚点前尝试 wake 机会；`validate_origin` 重读证据并拒绝过期 episode | 已完成 |
| P3 | `companion_v2/host/application.py`、`astrbot_host/multi_session.py`、`astrbot_host/native_extensions/reality/common.py` | 注入 `wake_port`：从 Reality 扩展读 `mobile_context(user_id)` 与叫醒会话，读最近私聊输入时间；不新增采集 | 已完成 |
| P4 | `companion_v2/proactive/configuration.py` | 注册第六节配置字段与默认值 | 已完成 |
| P5 | `companion_v2/proactive/prompts.py` | 问候目的继续使用现有 `GREETING_INSTRUCTION`；醒来线索的时机边界由 `morning_rhythm` 的 `MORNING_INSTRUCTION / NUDGE_INSTRUCTION` 注入 | 已完成 |
| P6 | 诊断页 | 在既有 `proactive_schedule_diagnostics` 记录拒绝原因与 wake 状态/置信度摘要（reason_code），不新增表 | 已完成 |

## 九、测试计划

已完成（P0）：

- 无证据 → `unknown`，拒绝。
- 负证据更新 → `asleep_likely`，拒绝。
- 两个独立设备信号 → `awake_likely`，允许一次。
- 单个弱信号 → `unknown`，拒绝。
- 显式私聊 → `confirmed`，允许。
- 静默时段 / 非早晨时段 → 拒绝。
- 窗口过期 / 本 episode 已发 → 拒绝。
- 证据过期 → `unknown`。
- episode key 90 分钟分桶稳定。
- 移动端枚举映射；文本标签不参与判定。
- 叫醒 `acknowledged / snoozed` 映射。
- 私聊间隔不足不产生「醒来转变」。
- 提示摘要包含边界句，且不泄露文本标签。

待补（P1–P6）：

- `WakeContactEvents` 只产出 intent、不直接发送。
- `ContactSchedule._plan` 在同一 episode 内最多一次；新负证据后重新评估。
- 重启后 episode 去重仍生效（依赖 `proactive_contacts` 账本）。
- 人格判定 `drop` 时不留下第二次机会。
- 叫醒 `snoozed` 后 90 分钟内不再因同一批旧信号触发问候。
- 静默时段、未回应暂停、每日预算仍然优先。

## 十、风险与默认值

| 风险 | 处理 |
| --- | --- |
| 误判用户已醒 | 默认关闭；`awake_likely` 需要多源或强信号；`unknown` 不触发 |
| 把设备在线当成在用手机 | `device_reconnected` 只有 40 分，单独不够阈值 |
| 叫醒后用户其实没醒 | `snoozed` 是负证据；`exhausted` 不产生正证据 |
| 泄露隐私或显得监视 | 只用类型化状态与时间；提示词禁止声称看见；不保存原始设备数据 |
| 与普通问候重复 | 同一 `episode_key` 去重；仍受 `greeting` 目的与去重策略约束 |
| 熬夜/夜班用户被早晨打扰 | 早晨时段、静默时段、每日上限均可配置；默认关闭 |
| 证据来源不可用 | 返回 `unknown`，退回既有时间窗问候，不报错、不阻塞 |

验收判据：打开开关后，只有「有新鲜证据 + 在醒来窗口内 + 未发过 + 非静默 + 人格放行」才产生一条主动问候；任何一项不满足都记录明确 reason，且不会补发第二条。
## 十一、与早安连续链的关系

`wake_detection.py` 只回答「用户现在可能是什么状态」。真正的连续早晨动作在 `morning_rhythm.py`：

- 角色自己的醒来回执（`role_wake_at`）决定能不能先说早安；
- 学到的作息（`estimate` / `predict_wake_window`）决定用户大概什么时候醒；
- `morning_plan` 决定是等、说早安、轻轻确认一次，还是用户已接话就停；
- `rhythm_adjustment` 把作息变成对既有 24 小时曲线的有界缩放。

完整设计见 `docs/MORNING_RHYTHM_20261018.md`。