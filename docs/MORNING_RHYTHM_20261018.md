# 早安连续链与作息学习设计

日期：2026-10-18。范围：`astrbot_plugin_private_companion_v2` 私聊主动联系。目标是把 V1 那种「早安 + 催起床 + 后续跟进」的连续感找回来，同时让它由**学到的用户作息**和**类型化醒来证据**驱动，而不是固定时间群发。

## 一、缺口

| 现有能力 | 问题 |
| --- | --- |
| `proactive/greetings.py` 每日早晨锚点 | 只按配置的时间窗发一次，和用户实际作息无关；「窗口不代表对方刚醒」 |
| `proactive/rhythm.py` 24 小时曲线 | 是运营者手填的固定曲线，不随用户作息变化 |
| `reality/wakeup_alarm.py` | 只负责叫醒播放，不知道叫醒后用户是否真的起来，也没有「没接话就轻轻再确认一次」的连续动作 |
| `wake_detection.py`（本轮 P0） | 已能判断「用户可能刚醒」，但还没有连续链、没有作息学习、没有动态节奏 |
| `role_work/life/body_clock.py` | 有角色自己的醒来回执，但没有接进早晨主动链 |

V1 的连续机制在新仓库里没有对应实现；这里按同样的产品意图重建：**角色醒来先说早安 → 用户醒来窗口附近轻轻确认 → 用户接话就转正常聊天，不接就不再追**。

## 二、三层机制

```
第 1 层：角色醒来（role body_clock）
    role_wake_at(body_sleep) → role_morning 机会

第 2 层：用户醒来预测（routine learning + wake evidence）
    RoutineSample[] → estimate() → RoutineProfile
    → predict_wake_window() → WakeWindow

第 3 层：起床确认（会话感知）
    morning_plan(contact, user_last_input_at, negative_evidence_at)
    → role_morning / wake_nudge / hold / skip
```

三层共用同一个 `proactive_contacts` 机会账本与人格判定；`morning_rhythm.py` 只做计划，不发送、不写库。

## 三、作息学习

### 3.1 样本

`RoutineSample` 每个本地日一条，字段全部是类型化数据：

| 字段 | 来源 | 说明 |
| --- | --- | --- |
| `local_date` | 本地日期 | 分桶键 |
| `wake_minutes` | `wake_detection.observe()` 的 `woke_at` | 当天估计醒来时刻；没有就是 `None` |
| `sleep_minutes` | 最近 `sleep_reported` 证据 | 当天估计入睡时刻；没有就是 `None` |
| `morning_contact` | 早晨机会账本 | 当天是否已开过早安机会 |
| `replied_after_contact` | 私聊输入时间戳 | 早安后用户是否接过话 |
| `response_delay_minutes` | 两个时间戳之差 | 用于估计回应速度 |

不记录消息内容、不记录应用名、不记录位置、不建立画像；样本只保留本地分钟与布尔值。

当前 P1 落地的样本来源：

- `wake_minutes`：当天第一条私聊输入的本地分钟（结构化时间戳，不读正文），作为「开始活动」的保守代理；
- `sleep_minutes`：暂不推断，保留 `None`，入睡估计使用默认 23:00；后续接入持久化的 `sleep_reported` 证据后再填；
- `morning_contact / replied_after_contact / response_delay_minutes`：来自既有 `proactive_contacts` 中 `morning_event` 记录与之后第一条私聊输入的时间差；
- 核心 `astrbot_core` 私聊路径若没有 `conversation_inputs` 行，作息样本为空，自动回退默认窗口；设备证据与早安链仍可工作。

### 3.2 估计

- 工作日与周末分开：各自至少 2 条才独立估计，否则回退到总体估计。
- 醒来时间用**中位数 + MAD**（中位数绝对偏差），对偶尔熬夜/赖床不敏感。
- 入睡时间按「跨午夜环形」处理：先把 `(minute - 12:00) % 24h` 映射到同一夜，再取中位数，避免 23:30 与 00:30 被算成相差 23 小时。
- 置信度 = 样本量因子 × 稳定性因子，范围 0–1；少于 2 条或置信度 < 0.2 时使用默认 `07:00` 窗口并标记 `source=default`。
- 响应率与中位回应时延来自「有早安机会」的样本，只用于决定催促延迟，不用于评价用户。

### 3.3 预测窗口

`predict_wake_window(profile, at)`：

- 按 `at` 的本地星期选择工作日/周末估计；
- 半宽 `pad = clamp(2 × MAD, 20, 60)` 分钟；
- 起点不早于 04:00，终点不晚于 14:00，至少 30 分钟宽；
- 返回 `WakeWindow(start_at, end_at, center_at, confidence, source)`，并带 `contains()`；跨重启可重算。

## 四、连续早晨链

状态与动作：

| 动作 | 触发 | 说明 |
| --- | --- | --- |
| `role_morning` | 角色醒来回执存在、当前在预测窗口前 30 分钟到窗口结束后 60 分钟内、本 episode 尚未开过口 | 角色自己先说早安，不要求用户已醒 |
| `wake_nudge` | 早安已发、用户未接话、超过 `nudge_delay_minutes`、仍在窗口内、未超过次数上限 | 轻轻确认一次是否起来 |
| `hold` | 还没到窗口、角色还没醒、催促延迟未到、催促冷却中、最近有睡眠证据 | 等待，不产生机会 |
| `skip` | 用户已接话、窗口已关闭、催促次数用完、角色醒来太久 | 关闭本 episode，不再追 |

决策顺序与 reason code：

| 顺序 | reason | 含义 |
| --- | --- | --- |
| 1 | `recent_sleep_evidence` | 45 分钟内有睡眠/静止证据，先不打扰 |
| 2 | `user_engaged` | 用户已在早安后发言，转正常聊天 |
| 3 | `before_wake_window` | 还没到预测窗口 |
| 4 | `wake_window_closed` | 预测窗口已过 |
| 5 | `role_not_awake` | 角色还没有醒来回执 |
| 6 | `role_wake_window_elapsed` | 角色醒来太久，早安时机已过 |
| 7 | `nudge_delay_not_elapsed` | 早安后还没到确认延迟 |
| 8 | `nudge_cooldown` | 距上次确认太近 |
| 9 | `nudge_budget_exhausted` | 本次 episode 的确认次数已用完 |
| 10 | `role_woke_in_wake_window` | 可以发角色早安 |
| 11 | `no_user_reply_yet` | 可以发一次起床确认 |

关键约束：

- **用户接话就停**：`contact.user_replied_at` 或 `user_last_input_at >= contact.sent_at` 都算接过话。
- **不接话最多再确认一次**：`max_nudges` 默认 1；发完即记账，不重复。
- **睡眠证据优先**：最近 45 分钟有 `sleep_reported / resting_reported` 就 `hold`，宁可错过也不吵醒。
- **不追加第三次**：窗口关闭或次数用完就 `skip`，等下一个自然机会。
- 所有动作仍要过 `ContactSchedule` 的空闲门槛、预算、未回应暂停、静默时段和人格判定。
## 五、动态主动节奏

`rhythm_adjustment(profile)` 把学到的作息变成对既有 24 小时曲线的**有界缩放**：

| 区域 | 因子 |
| --- | --- |
| 学到的清醒窗口内 | `1.15` |
| 窗口边缘 60 分钟 | `0.80` |
| 其余（睡眠/休息区） | `0.45` |

- 结果仍夹在既有 `RHYTHM_FLOOR=0.05` 与 `RHYTHM_CEILING=2.0` 之间，不会突破 `rhythm.py` 的边界。
- `rhythm_adjustment.apply(curve)` 返回新的 24 项曲线，交给既有 `hour_allows` 使用；不新增第二条曲线读取路径。
- 清醒窗口起点 = 醒来中位数 - 30 分钟；终点 = 入睡中位数 - 60 分钟；无法估计时回退默认。
- `morning_anchor_recommendation(profile)` 给出 `HH:MM-HH:MM`，建议把现有 `greeting_morning_window` 对齐到「醒来中位数 - 45 分钟 ～ + 75 分钟」，但最终仍由运营者配置决定。

这样早安锚点、主动间隔、小时权重会随用户作息慢慢移动，而不是永久固定在出厂值。

## 六、提示词口径

`MORNING_INSTRUCTION`：

> 这是角色自己醒来后的可选早安机会。先用角色自己的状态、当天语境或一个自然的话头开口，不要求对方已经醒着，也不索取回应。不要从时间推断对方睡眠、不要报时、不要把它写成打卡，不要提设备、观察、叫醒记录或任何内部判断。

`NUDGE_INSTRUCTION`：

> 这是一次轻量的起床确认机会，不是催促打卡。只在对方还没有接过话时轻轻问一句是否已经起来，不重复叫醒、不施压、不制造内疚、不连续追问；对方没回就不再发；对方回了就自然转入聊天。不要提设备、观察、叫醒记录或任何内部判断，也不要说自己一直在看着对方。

`wake_detection.intent_summary()` 仍负责给出证据抽象与置信度，并禁止「我看到你醒了」「我一直在看着你」这类表达。

## 七、实现落点与顺序

| 阶段 | 文件 | 内容 | 状态 |
| --- | --- | --- | --- |
| P0 | `companion_v2/proactive/wake_detection.py` | 证据融合与 wake episode | 已完成 |
| P0 | `companion_v2/proactive/morning_rhythm.py` | 作息样本、估计、预测窗口、早晨计划、节奏缩放、提示口径 | 已完成 |
| P0 | `tests/test_proactive_wake_detection.py` | 14 个测试 | 已完成 |
| P0 | `tests/test_proactive_morning_rhythm.py` | 20 个测试 | 已完成 |
| P0 | `tests/test_proactive_morning_chain.py` | 7 个 producer 单元测试 | 已完成 |
| P1 | `tests/test_proactive_morning_chain_host.py` | 2 个真实调度/账本集成测试 | 已完成 |
| P1 | `companion_v2/proactive/wake_events.py` | `WakeContactEvents`：产出 `role_morning / wake_nudge` 两类 `ContactIntent`；读作息、设备/叫醒证据与既有早安账本 | 已完成 |
| P2 | `companion_v2/proactive/scheduling.py` | `ContactSchedule` 注入 `wake_port`；`_plan` 在问候锚点前尝试早晨链；`validate_origin` 重读证据与窗口 | 已完成 |
| P3 | `companion_v2/host/application.py`、`astrbot_host/multi_session.py`、`astrbot_host/native_extensions/reality/common.py` | 组装 port：Reality `mobile_context`、`wakeup_snapshot`、角色 body_clock | 已完成 |
| P4 | `companion_v2/proactive/configuration.py` | 注册早晨链配置字段（默认全关） | 已完成 |
| P5 | `companion_v2/proactive/rhythm.py` | `hour_allows` 接受 `rhythm_adjustment.apply()` 后的曲线；保持原有边界 | 已完成 |
| P6 | `companion_v2/proactive/scheduling.py` | 复用 `proactive_schedule_diagnostics` 记录早晨链拒绝原因、状态/置信度摘要与 `next_at` | 已完成 |

建议配置（默认全关，加在 `proactive.contact`）：

| 字段 | 默认 | 范围 | 说明 |
| --- | --- | --- | --- |
| `morning_chain_enabled` | `false` | bool | 早晨连续链总开关 |
| `morning_role_greeting_enabled` | `true` | bool | 角色醒来是否可以先说早安 |
| `morning_nudge_enabled` | `true` | bool | 用户未接话时是否允许一次起床确认 |
| `morning_nudge_delay_minutes` | 25 | 10–90 | 早安后多久还没接话才确认 |
| `morning_nudge_max_attempts` | 1 | 0–2 | 每次 episode 的确认次数上限 |
| `routine_learning_enabled` | `true` | bool | 是否用历史样本调整窗口与曲线 |
| `routine_window_days` | 60 | 14–180 | 学习窗口 |
| `morning_wake_confidence_floor` | 0.25 | 0–1 | 低于此值不预测，改用默认窗口 |

## 七点五、实际接线

- `MultiHostSession` 新增 `_wake_snapshot(context)`：从 `NativeExtensionRegistry.api("reality")` 读取 `mobile_context(user_id)` 与 `wakeup_snapshot(user_id)`，只返回类型化字段。
- `CompanionApplication` 接受 `wake_port` 并传给 `ContactSchedule`；`ContactSchedule` 构造 `WakeContactEvents`。
- `ContactSchedule._plan` 在日历、约定静默之后、普通问候锚点之前调用 `wake_events.select`；返回的 marker 写入 `automatic_origin.morning_event`，继续走既有 `proactive_contacts` 与人格判定。
- `ContactSchedule.validate_origin` 识别 `morning_event`，重算作息窗口、设备证据与已接话状态；过期、用户已接话、次数用完都会拒绝。
- 角色 body_clock 不可用时（默认 `role.state.enabled=false`），`_role_woke_at` 回退到「学到的醒来窗口开始前 15 分钟」，保留旧版每日早安节奏，但仍不使用用户沉默作为证据。
- `rhythm.hour_allows(curve=...)` 接受缩放后的 24 项曲线；曲线仍夹在 `0.05–2.0`。
- 早晨链拒绝原因写入既有 `proactive_schedule_diagnostics`（stage=`morning`），reason_code 带 wake 状态与置信度摘要，不新增表。

## 八、测试

已完成（P0）：

- 工作日/周末分别估计，样本不足回退总体；
- 无样本回退默认 `07:00` 且置信度 0；
- MAD 越大置信度越低；
- 入睡中位数跨午夜正确；
- 预测窗口有界且包含中心；
- 周末窗口使用周末中心；
- 角色未到窗口 `hold`、角色醒来在窗口内 `role_morning`；
- 无角色醒来回执 `hold`、角色醒太久 `skip`；
- 催促延迟、冷却、次数上限；
- 用户接话取消催促（显式回执与最近输入两条路径）；
- 最近睡眠证据 `hold`、窗口关闭 `skip`；
- 节奏缩放有界、锚点建议正确；
- `role_wake_at` 只读角色自己的回执；
- 两段提示词包含证据边界。

待补（P1–P6）：

- 同一 morning episode 只开一次早安、最多一次催促；
- 重启后仍能通过 `proactive_contacts` 去重；
- 人格判定 `drop` 后不补发；
- 用户接话后立即转入普通对话链，不被早晨链重复拦截；
- 作息学习随新样本缓慢移动，不因单日异常跳变；
- 静默时段、未回应暂停、每日预算优先级高于早晨链。

## 九、风险与默认值

| 风险 | 处理 |
| --- | --- |
| 误以为用户已醒 | 最近睡眠证据优先 `hold`；预测窗口只是时机，不是事实 |
| 催促变成骚扰 | 默认最多 1 次；用户接话立即停；窗口关闭即停；可整体关闭 |
| 作息学习被异常日带偏 | 中位数 + MAD；工作日/周末分离；样本不足回退默认 |
| 熬夜/夜班用户 | 学习窗口会随实际作息移动；仍受静默时段与预算约束 |
| 暴露隐私 | 只存本地分钟、布尔、时间戳；提示词禁止提设备/观察；不存原始数据 |
| 与普通问候重复 | 同一 episode 账本去重；`greeting` 目的与既有去重策略继续生效 |
| 曲线被放大过度 | `apply()` 夹在 0.05–2.0；只缩放既有曲线，不新增额度 |

验收判据：打开开关后，角色在预测窗口附近醒来会先说一句早安；用户接话则当天不再催促；用户没接话且没有近期睡眠证据时，最多再轻轻确认一次；窗口关闭或次数用完立即停止；作息变化在若干天后体现在窗口与小时权重上。