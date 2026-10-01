# T52 繁忙回复闸门切片（2026-09-27）

> 缺口清单：`V2_GAP_CLOSING_TASKS_20260927.md` 的 **T52「繁忙回复闸门：忙碌时段回复延迟」**（V1 来源 `enable_busy_reply_gate`、`busy_reply_min_delay_seconds`、`busy_reply_max_delay_seconds`、`busy_reply_proactive_resume_buffer_minutes`）。
> V1 参考：`../astrbot_plugin_private_companion/busy_reply_gate.py`（460 行，`BusyReplyGateMixin`）。参考设计稿：`CORE_HOST_LIFECYCLE_AND_BATCHING_SLICE.md`。

## 一、V1 参考位置与 V2 落点

| V1 落点 | 行为 | V2 落点 |
| --- | --- | --- |
| `_BUSY_ACTIVITY_PATTERN` / `_BUSY_ACTIVITY_EXCLUSION_PATTERN`（20-28 行） | 日程活动/Mood 文本关键词命中即「忙」，排除项优先 | `conversation/busy_gate.py` 的 `busy_activity_keywords` / `busy_exclude_keywords`（可配置，默认等价中文关键词）+ `is_busy_text` |
| `_busy_reply_item_is_busy`（138-170 行） | 只认当天计划当前条目；排除睡觉/休息；`presence` 为忙碌也算 | `busy_context`：只认 `agenda` 中**已接受**的 `role_plan` 且当前时刻落在 `[start, start+duration)`；排除关键词优先；`presence` 参与判定 |
| `_busy_reply_item_end_at`（172-223 行） | 算出忙碌结束时刻 | `busy_context()["until"]`（同一 occurrence 的 `start + duration_minutes`） |
| `_apply_busy_reply_gate_delay`（270-325 行） | `await asyncio.sleep(delay)` 把回复压在事件协程里 | **不迁移 sleep**：`deferral()` 返回秒数 → 宿主写进 `conversation_flows.due_at`，由 `next_wake` 唤醒（口径 1） |
| `_busy_reply_bypass_reason`（258-268 行） | 紧急/安全、`!` `/` 命令前缀、`陪伴…设置/配置/状态…` 管理命令放行 | `bypass_reason`：同一意图，关键词集合可配置，映射为 `urgent_or_safety` / `command` / `management_command` |
| `_busy_reply_proactive_block_context`（343-385 行） | 忙碌期顺延主动消息，忙完加 `busy_reply_proactive_resume_buffer_minutes` | `proactive_defer_until` + `proactive_hold`；调度落点见第四节 |
| `_defer_proactive_for_busy`（415-460 行） | 改 `user["next_proactive_at"]` 等一串时间戳 | **不迁移**：V2 不在候选上挪时间，改为「忙碌期不产出机会」（第四节理由） |
| `_BUSY_PROACTIVE_EXEMPT_SOURCES`（33-44 行） | timer/排障/模拟/便签/环境变化豁免 | `busy_exempt_source`：`calendar/journal/activity/date/meal/weather/weather_change/official_alert/balance/news` 事件候选豁免（与 `ContactSchedule.validate_origin` 的 `event_markers` 同一集合） |

**V2 落点与理由**

- 判定与配置放 `companion_v2/conversation/busy_gate.py`：T52 目标位置即 `conversation/`，且「是否延迟」是对话时机的一部分；主动侧的顺延只是消费同一个判定。
- 唯一的 I/O 是 `calendar_items()`：一次有界只读查询（`LIMIT 64`），按 `versioned_records.owner_key(context)` 读本窗口自己的 `calendar_records`，与 `agenda/calendar.py:230-232` 已采用的直接读取范式一致。它**不授予任何权限**，读失败一律视为「不忙」（`readable_items`）。
- 不使用 `role_work/state/` 的 `busy` 字段，也不使用任何 QQ 在线状态：`state/maintenance.py`、`conversation/life_context.py` 已明确禁止据此自动拒答或改变回复（口径 6）。日程忙碌只影响**何时**回复，不影响是否回复。

## 二、配置字段表

配置组 `conversation.busy_gate`，自有 owner `conversation.busy_gate`，`layers=(ConfigLayer.WINDOW,)`，`apply_mode=IMMEDIATE`（范式同 `expression/configuration.py`）。`Group=GROUP`、`OWNER`、`LAYERS`、`configuration_fields()`、`SettingsReader`/`read_settings`、`Settings`、`BusyGateConfigurationOwner` 均已提供。

| 字段 | 类型 | 范围 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `busy_reply_gate_enabled` | BOOLEAN | — | `False` | 总开关，默认关闭（涉及延迟发送，默认不改变现网行为） |
| `busy_reply_min_delay_seconds` | INTEGER | 0–900 | `60` | 延迟区间下限；与 V1 同 |
| `busy_reply_max_delay_seconds` | INTEGER | 0–900 | `300` | 延迟区间上限；`min>max` 时按 V1 语义互换而非报错 |
| `busy_reply_proactive_resume_buffer_minutes` | INTEGER | 0–120 | `10` | 忙完后主动消息的额外缓冲 |
| `busy_activity_keywords` | TEXT | JSON 列表或分隔串（≤64 项、每项 ≤24 字） | V1 活动关键词等价集合 | 命中即「忙」 |
| `busy_exclude_keywords` | TEXT | 同上 | V1 排除关键词等价集合 | 命中即「不忙」，优先于活动关键词 |
| `busy_urgent_keywords` | TEXT | 同上 | V1 紧急/安全关键词等价集合 | 命中即放行；V1 该集合是硬编码常量，此处**额外**配置化以满足「关键词集合必须可配置」 |

校验：范围由 `FieldDefinition` 保证；`BusyGateConfigurationOwner` 在 `preview_set`/`write` 内用 `Settings.from_values` 复核整组（含关键词解析），非法写入返回 `busy_gate_settings_invalid` 且不落库。读侧 `SettingsReader.read` 遇到任何 `ConfigurationError` 回落到全默认值，坏配置不会卡住一轮回复。

## 三、与整轮截止（`deadline_at`）的关系

`flow._advance_one` 一旦 `now >= deadline_at` 就 `cancel + halt("deadline_elapsed")` 丢消息，所以延迟绝不能让 `due_at` 越过 `deadline_at`。

1. `ConversationFlow.accept(..., defer_seconds=0.0)`：先 `validate_defer_seconds`（有限、`0 <= v <= 900`，否则 `busy_gate_defer_invalid`，且在任何事务之前拒绝，不留下半份状态）。
2. `due_at = now + initial_wait + defer`（`initial_wait` 仍为 `quiet_seconds`，群聊仍取 `short_input_wait`，本任务不改群聊窗口）。
3. `deadline_at = deadline_for_deferral(now, due_at, deadline_at=now+turn_timeout, quiet_seconds, max_delay_seconds=defer)`，即 `deadline_at + min(900, max(defer, due_at + quiet + 1s - deadline_at))`。
   - **量化上限**：单批 `deadline_at` 最多比原 `turn_timeout_seconds`（默认 180s）晚 **900 秒**（`MAX_TURN_DEADLINE_EXTENSION_SECONDS`，与配置的延迟上限同值，`busy_reply_max_delay_seconds ≤ 900` 保证实际不会更远）。
   - `defer_seconds == 0` 时函数原样返回传入的 `deadline_at`，因此**开关关闭或未命中时原有计时逐字节不变**（`test_host_application`/`test_host_recovery` 的固定时间断言全部保持通过）。
   - 抬升幅度同时覆盖「本次延迟」与「延迟后再留一个静默窗口 + 1 秒余量」，所以 `due_at + quiet_seconds < deadline_at` 恒成立，不会出现 `deadline_elapsed`。
4. `reason` 记 `'busy_delay'`（`conversation_flows.reason` 无 CHECK 约束，无需 schema 升级）；`defer == 0` 时仍是 `'debounce'`。
5. **合并分支（`busy_delay` 的批次再收到新输入）**：`defer > 0` 时把窗口取为 `min(now + quiet + defer, deadline)` 并把 `deadline_at` 抬到 `max(现值, deadline_for_deferral(...))`、`reason` 置为 `busy_delay`；随后统一做 `due = max(previous_due, min(due, deadline))`（32 条满载时改为立即封存）。语义一句话：**同一批次已经许下的等待只会保持不变或被更晚的窗口延长，任何后续输入都不能把它拉早，也不能把 `due_at` 推过自己的 `deadline_at`**；`merge_until` 语义未改（合并窗口仍由首条输入决定，`max` 只防止已承诺的延迟被合并窗口截短）。
6. `ConversationPolicy` 只在**末尾**新增 `defer_seconds: float = 0.0`（默认 0，约 40 处测试的位置参数构造不受影响），并在 `__post_init__` 内加 0–900 的有限性校验。
7. 已派发信封（`operation_id` 非空）路径完全未改动：延迟只作用于 `state='collecting'` 且尚未 seal 的批次。

## 四、主动链顺延口径

落点在 `proactive/scheduling.py`：`ContactSchedule._busy_hold(context, origin, now)`，在 `advance()` 内 `_plan(...)` 成功之后、**创建 worker 之前**调用；返回非 None 即 `continue`（本次不产出机会）。此时 `OutboundDelivery.queue` 还没被触碰，`not_before` 尚未冻结，因此 `_run` 事后比对报错的结构性问题不存在。

- 忙碌期间：不产出机会（`return None`），既不重排也不补发。原来的机会窗口 `[opened, expires)` 过期即自然消失，重启后不会产生补发积压——这正是 V1「忙完再顺延」意图在 V2「机会即槽位」语义下的等价物；若改成在既有 `next_proactive_at` 上前后挪时间戳，就等于重排一个已经决定过的机会，与「未知不重放」原则冲突。
- 忙碌结束后：`now` 已越过 `until`，`_busy_hold` 返回 None，下一轮 `advance()` 按正常规则产出新机会；`busy_reply_proactive_resume_buffer_minutes` 决定的是「忙完多久之内仍算忙」，即 `proactive_defer_until = until + buffer`。
- 豁免：`_plan` 现有的 calendar/events/journal/date/meal/official_alert/balance/news/weather 候选先返回的结构**一字未改**，`busy_exempt_source(origin)` 对这些事件候选返回 True，忙碌期也照常产出（事件驱动的时机由事件本体决定）。
- `proactive_hold(runtime, context, *, now, settings=None, items=None)` 也对外提供，供未来需要在别处读取「何时可恢复」的调用方使用。

## 五、未迁移项（设计差异，理由）

1. **群聊 12 秒硬顶不迁移**：V1 对群聊把 min/max 都压到 `min(…, 12)`。V2 群聊的入站时机由 `conversation/group_timing.short_input_wait` 与插话窗口统一治理（`flow.accept` 的群聊分支、`reply_settings` 的 `group_wakeup_short_text_wait_ms` 等已有配置），再叠一层 900 秒上限的随机静默会与那套窗口互相打架，而且群聊被动回复叠加「角色在忙」的私人化延迟在语义上不成立（同一群里其他人并不共享该角色的日程）。因此 T52 只对**私聊被动回复**生效；群聊窗口保持现状，本条差异在此记录。
2. **`superseded`（新消息取消陈旧回复）不迁移**：V1 在 sleep 结束后重新检查「本轮是否已被更新私聊取代」，是则丢弃。V2 语义是延迟期内新消息**合并进同一批次**（`flow.py` 的合并分支），并由整轮截止保证有界；沿用 V1 的取消语义会与「已接受的输入不丢」冲突。`_busy_reply_note_inbound_event` / `_busy_reply_event_is_superseded` / `_busy_reply_latest_inbound_tokens` 等 token 机制因此整体不迁移。
3. **`_busy_reply_proactive_block_context` 的「外部实时活动」（`_external_realtime_activity_block_until`）不迁移**：V2 没有该注册表（无实时通话/共同观看面），属 V1 专有。
4. **V1 的 `_defer_proactive_for_busy` 时间戳串改不迁移**（见第四节理由）。
5. **不迁移 V1 的「概率回复/醒后补看」**：那是 T33 的范围，本次不涉及。

## 六、宿主侧接线（已由主代理完成并生效）

**A. `companion_v2/host/application.py`（主代理实现，本切片只做说明）**

1) import：`from companion_v2.conversation import busy_gate` 以及 `BusyGateConfigurationOwner`、`configuration_fields as busy_gate_configuration_fields`。
2) 配置组登记：`busy_gate_configuration_fields()` 已加入 `extra` 元组，`BusyGateConfigurationOwner(runtime)` 已加入 `ConfigurationService(..., owners=(...))`。
3) accept 路径：`self.flow.accept(..., defer_seconds=self.busy_deferral(context, event))`；`busy_deferral` 仅私聊生效，先 `messages._read_source` 取本轮正文（用于紧急/命令旁路），再调用 `busy_gate.deferral(self.runtime, context, text=text, now=self.now())`，任何异常返回 `0.0`。此路径**不 sleep**：延迟只进入 `due_at`。

**B. `companion_v2/adapters/**`、`delivery/**`、`proactive/service.py`**：无需改动。
**C. `proactive/scheduling.py`**：已由本切片自行完成（`_busy_hold`），不需要宿主接线。

## 七、测试

```
cd C:\Users\99505\.astrbot\data\plugins\astrbot_plugin_private_companion_v2
$env:PYTHONPATH='C:/Users/99505/.astrbot/backend/app;C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/.p4-tmp'
$env:TEMP='…\.p4-tmp\temp'; $env:TMP=$env:TEMP
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_busy_reply_gate -q
```

**最终结果：`tests.test_busy_reply_gate` 21 项全部通过（无 skip）。** 5 个 `BusyGateHostTests` 端到端用例已真正断言 `reason == "busy_delay"`（原先的 `wired()` skip 守卫已随宿主接线落地而删除）。覆盖：

| 目标 | 用例 |
| --- | --- |
| 开关关闭 → 无延迟 | `test_gate_disabled_busy_window_or_urgent_text_never_delays` |
| 忙碌命中 → `due_at ∈ [now+min, now+max]` 且 `deadline_at` 同步安全 | `test_busy_window_defers_the_batch_and_keeps_the_deadline_safe`、`test_flow_level_deferral_moves_due_at_and_extends_the_deadline_in_bounds`（后者直接驱动 `accept(defer_seconds=…)`，不依赖宿主接线） |
| 紧急/命令旁路 | `test_bypass_reason_migrates_the_v1_intent`、`test_defer_seconds_stays_inside_the_configured_interval`（旁路先于区间抽取）、`test_urgent_and_management_text_bypass_the_busy_delay` |
| 非忙碌日程 → 无延迟 | `test_busy_context_honours_the_switch_window_and_exclusions`、`test_leisure_sleep_and_unaccepted_calendar_never_delay` |
| 延迟期内第二条消息合并进同一批次、且不截短已承诺的等待 | `test_new_input_arms_and_then_never_shortens_the_deferred_window` |
| 重启保持：`due_at` 不变、不重开计时 | `test_deferred_batch_keeps_its_timer_across_a_restart`（重启前删掉日历记录，证明只有持久计时能解释延迟） |
| 配置边界与默认值、owner 校验 | `test_configuration_group_contract_and_defaults`、`test_keyword_text_accepts_json_and_separated_forms`、`test_owner_registers_the_group_without_a_grant_and_rejects_a_malformed_keyword_write` |
| 主动链忙碌不顺延、忙后恢复、豁免来源不受影响 | `test_a_busy_calendar_holds_automatic_contact_and_resumes_after_the_window`、`test_an_event_opportunity_is_not_held_by_the_busy_window`、`test_event_opportunities_are_exempt_from_the_gate`、`test_proactive_resume_uses_the_busy_end_plus_the_configured_buffer` |
| 未知不重放回归：延迟期间撤权 → 封存前被 `messages.authorize` 拒绝 | `test_a_revoked_grant_is_refused_before_the_deferred_batch_seals` |
| 拒绝越界 `defer_seconds` 且不留半份状态 | `test_flow_level_deferral_is_rejected_outside_its_range`、`test_defer_seconds_is_rejected_outside_its_registered_range` |
| 日历读失败不拖住回复 | `test_a_busy_calendar_read_failure_keeps_the_ordinary_window` |

受影响回归（同一命令追加模块名）：

| 命令 | 结果 |
| --- | --- |
| `tests.test_busy_reply_gate` | **21 项通过**（34.3s） |
| `tests.test_busy_reply_gate tests.test_host_application tests.test_host_recovery tests.test_contact_scheduling` | **70 项通过**（155.7s）：其中 `test_host_application`+`test_host_recovery`+`test_contact_scheduling` 合计 49 项 |

`compileall` 通过；`busy_gate.py`/`flow.py`/`scheduling.py`/`test_busy_reply_gate.py`/本文档均为 UTF-8 无 BOM、LF、末尾换行；无调试输出、无临时探针脚本残留。

## 八、遗留风险

1. **延迟抬升了整轮截止**：单批 `deadline_at` 最坏比原 180 秒晚 `defer`（≤900，即 `busy_reply_max_delay_seconds` 的值），所以一条在忙碌期来的消息最坏可占住整轮名额约 18 分钟。默认关闭时无影响；期间该窗口的后续输入仍合并进同一批次（32 条上限与自身截止兜底）。要更保守就把 `busy_reply_max_delay_seconds` 调小，无需改代码。
2. **忙碌判定依赖角色日历质量**：`role_plan` 的 `title/detail/presence` 文本决定命中；日历为空或全部被排除关键词覆盖时闸门不生效（安全默认）。关键词集合已配置化，管理页编辑属第②阶段。
3. **随机性**：区间抽取沿用 V1 的 `random.uniform`，同一窗口内两次接受可能得到不同延迟；这是 V1 既有行为，测试只断言落在区间内。
4. **群聊无延迟**是刻意的设计差异（第五节第 1 条）；若后续确需群聊「角色在忙」的轻延迟，应作为独立任务在 `group_timing` 内实现，而不是复用本闸门的 900 秒区间。
5. **AstrBot 管理页字段**：`_conf_schema.json` 未改（本任务禁止修改）；`conversation.busy_gate` 组的可视编辑依赖第②阶段「陪伴小屋」统一接入。
6. **真机时序未测**：全部结论来自确定性时钟夹具，没有真实手机/平台延迟的 p95 数据，不能把这里的秒级参数当成现场表现。
