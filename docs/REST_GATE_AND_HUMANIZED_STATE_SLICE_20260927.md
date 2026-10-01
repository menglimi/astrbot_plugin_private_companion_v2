# T33 休息回复闸门 + T35 拟人状态强度与每日巡视（2026-09-27）

> 缺口清单：`V2_GAP_CLOSING_TASKS_20260927.md` 的 **T33「休息回复闸门+醒后补看」** 与 **T35「拟人状态强度注入+每日巡视时刻/保留天数」**。
> V1 参考：`../astrbot_plugin_private_companion/user_rest_gate.py`、`main.py`（`_rest_reply_boundary_score` /
> `_rest_reply_sleep_context` / `_should_reply_during_rest` / `_record_rest_reply_backlog` /
> `_take_rest_reply_backlog_prompt`，约 17955-18270 行）、`plugin_bootstrap.py:791-800`、
> `_conf_schema.json:3429-3488` 与 `:10180-10249`。
> 参考设计稿：`CORE_SHARED_ROLE_SLEEP_SCHEDULE_20260924.md`、`CORE_SHARED_ROLE_BODY_20260924.md`、
> `CORE_STATE_MAINTENANCE_EDITING_20260925.md`、`BUSY_REPLY_GATE_SLICE_20260927.md`（延迟口径）。

## 一、落点与口径

| 任务 | V2 落点 | 说明 |
| --- | --- | --- |
| T33 判定与留痕 | `companion_v2/role_work/life/rest_gate.py`（新） | 纯判定 + 一次有界睡眠回执读取 + 自己的持久文档；不 sleep、不排队、不封存、不发送 |
| T33 配置 | `companion_v2/role_work/life/configuration.py`（外科式） | 8 个字段并入既有 `role.life` 组与既有 owner `role.life.settings`，不新建组、不新建表 |
| T33 触发 | 宿主 accept 路径（**由主代理接线**，见第六节） | 延迟只进 `conversation_flows.due_at`，与 T52 同一口径 |
| T35 表达与巡视 | `companion_v2/role_work/state/humanized.py`（新） | 强度档位 → 有界表达块；每日巡视 + 保留天数清理 |
| T35 配置 | `companion_v2/role_work/state/configuration.py`（外科式） | 4 个字段并入既有 `role.state` 组与既有 owner `role.state.settings` |
| T35 注入 | `companion_v2/conversation/state_context.py`（外科式） | 强度随状态一起封存，`instruction()` 按档位追加一个有界块 |
| T35 巡视触发 | `companion_v2/role_work/state/maintenance.py`（外科式） | `StateMaintenance.advance()` 开头调用本地巡视，无模型调用、无发送 |

**睡眠信号**：角色**真实睡眠执行回执**——`role_activities` 中 `work.kind='sleep'` 且 `state='active'` 的行，由
`role_work/life/runtime.py` 建立、`life/body_clock.py` 结束，读取时复用 `role_work.codec.activity_from_json`。
计划唤醒时间取同一条回执的 `work.due_at`。`role_work/state` 的 `busy` 字段与任何 QQ 在线状态**不参与判定**
（`state/maintenance.py`、`conversation/life_context.py` 已明确禁止据此自动拒答）。

## 二、T33 配置字段（8 项，键名与 V1 一致）

配置组 `role.life`，owner `role.life.settings`，`layers=(WINDOW, ROLE)`，`apply_mode=IMMEDIATE`；
与既有睡眠/日记/梦境字段同组，因此**不改配置组契约、不改 `_conf_schema.json`**。实际作用域为窗口层
（`is_shared()` 仍只覆盖 4 个睡眠字段，role 层不读取这 8 项）。

| V2 字段（=V1 键） | 类型 | 范围 | 默认 | 真实消费者 |
| --- | --- | --- | --- | --- |
| `enable_rest_reply_simulation` | BOOLEAN | — | `False` | `judgement()` / `deferral()` 总闸 |
| `rest_reply_mode` | TEXT | `probability`/`llm` | `probability` | `judgement()` 分支；写入侧 `validate_changes` 拒绝非法值，读取侧按 V1 归一 |
| `rest_reply_probability` | INTEGER | 0–100（V1 的百分数） | `18` | `judgement()` 概率抽取（`random()*100 < p`） |
| `rest_reply_llm_threshold` | INTEGER | 0–100 | `65` | 边界分与模型分的放行阈值（`max(1, threshold)` 同 V1） |
| `rest_reply_active_windows` | TEXT | `HH:MM-HH:MM` 列表，可空 | `23:00-08:30,12:20-13:40` | `parse_windows`/`window_active`（含跨零点与「空=全天」） |
| `rest_reply_awake_grace_minutes` | INTEGER | 0–240 | `30` | `mark_awake`/`awake_grace` 免重判窗口 |
| `enable_rest_backlog_reply` | BOOLEAN | — | `True` | `append_backlog` 是否记录补看 |
| `rest_backlog_max_messages` | INTEGER | 1–32 | `4` | `Settings.max_backlog()` 决定补看上限（V1 只设下限，V2 加有界上限） |

`rest_reply_active_windows` 的解析**照抄 V1 `proactive_engine._parse_window_minutes`**：分隔符归一
（`：—–－~～至到`）、小时取模 24、`end <= start` 视为跨零点（`end += 1440`）。这正是 V1 默认时段能在
23:30 命中的原因；`window_active` 沿用 V1 的 `(now, now+1440)` 双候选比较。

### 判定顺序（V1 → V2 逐条对应）

1. 开关关闭 → `disabled`，不延迟。
2. 没有**真实睡眠回执**（或计时已到、或当前本地时间不在配置时段内）→ `not_sleeping` / `sleep_timer_due` /
   `outside_active_window`，不延迟。
3. 免重判：`awake_until` 未过期**且属于同一条睡眠回执** → 直接放行（`awake_grace`），不再看文本。
   V1 的 `_mark_sleep_woken_by_user` 用同一语义；V2 增加「同一回执」约束，新的睡眠会重新判定。
4. 边界分 `boundary_score(text)`（V1 `_rest_reply_boundary_score` 逐条移植）：
   `< 0` → 挂起（`user_asks_no_reply` / `user_asks_quiet`）；`>= max(1, threshold)` → 放行
   （`explicit_wakeup_request` / `user_corrects_not_resting` / `goodnight_ack` / `urgent_or_explicit_wakeup` /
   `soft_wakeup_request`）；其余落到概率或模型分支。
   > 注意：V1 把「睡了吗/在吗」一类软唤醒请求记为 72 分，默认阈值 65 时**直接放行**——这是 V1 既有语义，本片保留。
5. `probability`：命中即放行并记录免重判；未命中挂起。
6. `llm`：**默认关闭**（默认模式不是 `llm`）。判定由调用方注入
   `judge(text=…, sleep=…, settings=…) -> (score, reason)`；`judge` 缺失、抛错、返回类型不对或分数越界
   一律记为 `judge_unavailable` **挂起，绝不回复**。本模块自身不调用模型。

### 延迟写进 `due_at`（不在协程里 sleep）

`deferral()` 返回一个 `<= 900` 秒的延迟，宿主直接交给 `flow.accept(..., defer_seconds=…)`：

- 挂起时长 = `min(900, max(1, 距计划唤醒秒数))`，计划唤醒未知时为 900。闹钟到期即 `sleep_timer_due`，不再挂起。
- `flow.accept` 现有实现把延迟写进 `due_at` 并按 `deadline_for_deferral` 同步抬升 `deadline_at`
  （`due + quiet + 1s` 余量、上限 900），因此**不会出现 `deadline_elapsed` 丢消息**；`defer_seconds` 本身
  由 `validate_defer_seconds` 约束在 0–900，超出即拒绝。
- 本模块不新增计时字段、不在 intake 协程里等待，重启后等待时长由 `conversation_flows` 原样恢复。
- `conversation_flows.reason` 仍写 `busy_delay`（`flow.py` 本任务禁改，且该列复用同一「有延迟」语义）；
  休息闸门自己的原因记在它自己的文档 `last.reason` 与每条补看记录里，可查、可追溯。

### 免重判（同一批次不重复判定）

- **同一条入站**：以 `event_key`（宿主传 `event.scoped_key`）为键，重复调用返回**首次的延迟**，不再抽签、
  不再追加补看记录（`test_one_inbound_is_judged_once_and_never_redrawn` 连调 25 次证明）。
- **放行之后**：写 `awake_until = now + grace`，同一睡眠回执内的后续消息不再判定。
- **挂起期间**：不写免重判，后续消息各自判定（与 V1 一致）。

### 醒后补看

- 记录项：`{at, reason, source, capability, sleep}`——以入站 `SourceRef` 为**来源凭据**，按到达顺序追加，
  同一来源去重，最多 `rest_backlog_max_messages`（硬上限 32）。
- 只存引用**不存正文**；正文在消费时按原有授权重读（`backlog_prompt(entries, texts)`），撤权/过期/读不到
  一律显示「发来了一条消息」，不编造内容。
- `consume()` 只在角色**确实醒了**（无活动睡眠回执）时吐出并清空；仍睡时保留，绝不提前吐出。
- 文档存在 `runtime_metadata`（键前缀 `role.life.rest_gate.v1:`，**不新增表、不升 schema**），损坏内容按
  「从未挂起」读取，永不阻塞一轮回复。

## 三、T35 配置字段（4 项）

配置组 `role.state`，owner `role.state.settings`，`layers=(WINDOW,)`，`core_only=True`，`IMMEDIATE`。

| V2 字段 | V1 键 | 类型 | 范围 | 默认 | 真实消费者 |
| --- | --- | --- | --- | --- | --- |
| `humanized_state_intensity` | `humanized_state_intensity` | INTEGER | 0–100 | `50` | `state_context` 封存 + `humanized.instruction` 档位注入（0=不注入） |
| `daily_state_patrol_enabled` | `enable_daily_review` | BOOLEAN | — | `True` | `StateMaintenance.patrol()` 的开关（无模型调用、无发送） |
| `daily_state_patrol_time` | `daily_review_time` | TEXT | `HH:MM` 本地时间 | `04:00` | `patrol_due()` 的当日到点/补做判断（时区取既有 `planning_timezone`） |
| `daily_state_patrol_retention_days` | `daily_review_retention_days` | INTEGER | 3–180（V1 滑块范围） | `30` | `prune_reports()` 清理巡视自己的记录 |

改名说明：V2 已有 `role.self_review`（模型驱动的每日复盘）占用「每日复盘/巡视」语义，因此状态组这一组字段
用 `daily_state_patrol_*` 命名以免与那个子系统混淆；上表给出逐字段的 V1 键映射。

### 强度档位注入（0＝不注入）

- 档位：`0` = `off`（**完全不注入**，也不产生任何提示文本）；`1–33` 轻；`34–66` 标准；`67–100` 明显。
- 每档有硬上限（档位 → 面数, 字符数）：轻 (2, 220)、标准 (4, 420)、明显 (6, 700)；超出先裁面数，再截断，
  但**边界句永不裁剪**。
- 面数来源仅限本轮已授权 `simulation`：精力、**实际睡眠执行回执**（`sleep_execution`）、情绪、睡眠、健康、
  饥饿、周期、临时影响。**不含 location**（共享身体视图里它是窗口私有），不推断用户信息。
- 注入只影响表达：块内固定含「不改变身份、权限、记忆范围和安全规则」「忙碌或在线状态只是描述，不据此拒答」；
  代码层面也不触碰身份、权限、记忆范围与出站安全规则（只往 instruction 末尾追加文本）。
- 强度在 `capture()` 时**随状态一起封存**（快照新增可选键 `humanized_intensity`），重放与重启后逐字节一致；
  旧封存批次没有该键 → 不注入。快照里出现非法强度（`500`/`-1`/`"high"`/小数）直接 `state_snapshot_invalid`，
  不静默降级成默认档。

### 每日巡视与保留天数

- 触发：`StateMaintenance.advance()` 开头调用 `patrol()`（60 秒节流，避免唤醒循环反复读配置）。
- 到点口径：本地日（`planning_timezone`）当天 `daily_state_patrol_time` 过后、且当天尚未巡视过即执行；
  当天已巡视过不会重复，插件错过时刻后在下次唤醒补做（V1 的补巡视语义）。
- 巡视内容：一次 `role.state.read`（自己复核授权），记录 `{day, at, revision, state, live_conditions,
  expired_conditions, retention_days, role_timezone}`；**不写状态**（已过期条件在投影层隐藏，改写状态会让
  人工校准的版本作废），因此巡视不会让正在生成的一轮回复因 `state_changed` 被阻断。
- 保留天数：巡视记录存在 `runtime_metadata`（键前缀 `role.state.patrol.v1:`，每角色一条），每次巡视按
  `day >= today - retention_days` 清理过期记录，并保留硬上限 64 条；这与 V1「巡视报告只保留结构化结论、
  按保留天数清理」是同一意图。
- 授权失败/记录损坏只写进 `StateMaintenance.patrol_results`（`blocked`/`failed`），不影响维护队列。

## 四、V1 → V2 设计差异（未迁移项与理由）

1. **V1 的「不回复」在 V2 变成「有界延后」**：V1 直接 `stop_event()` 丢掉本轮；V2 的既有口径是
   「已接受的输入不丢」（`flow.py` 合并分支与整轮截止），因此休息中的消息改为写进 `due_at` 的**有界**等待
   （最长 900 秒，或到计划唤醒为止）。这是 T33 最重要的一条差异：**不会静默吞消息**，代价是极长睡眠里消息
   最晚 15 分钟后仍会被回复。
2. **`asyncio.sleep` 不迁移**（T52 同口径）；`_rest_reply_llm_score` 的模型调用不落在这里：宿主 accept 路径
   是同步的，无法 await 模型，因此 `llm` 模式只消费调用方注入的同步判定，缺判定即挂起（fail-closed）。
   `REST_WAKEUP_PROVIDER_ID` 因此不迁移（V2 用既有后台档案选模型，若日后要接，应作为后台任务在 accept 前
   预判，而不是在闸门里同步调模型）。
3. **V1 的 `user_rest_kind` / 用户休息静默（`user_rest_until`、`_classify_user_rest_signal`）不迁移**：
   那是「用户说自己要睡了」的**用户侧**静默，落在 V1 用户档案里；V2 的私聊没有等价的用户档案字段，
   且主动联系侧已有自己的偏好与暂停口径。本片只做**角色自己睡眠**的闸门。
4. **`rest_reply_active_windows` 的时区**取既有 `sleep_timezone`（同一角色共享睡眠字段），不新增时区字段。
5. **群聊不生效**：V1 的休息闸门本就只在私聊被动回复里用；V2 与 T52 一致，只对私聊生效（群聊入站时机由
   `group_timing` 治理）。
6. **`humanized_state_intensity` 不做「故意打错字」一类降级**：只按档位控制**状态表达**的面数与长度上限。
7. **巡视不做模型复盘**：模型驱动的每日复盘在 V2 已由 `role.self_review` 承担；本片只补 V1 的「时刻 + 保留
   天数」两项以及本地状态观察，不重复建设模型链。

## 五、测试

```powershell
cd C:\Users\99505\.astrbot\data\plugins\astrbot_plugin_private_companion_v2
$env:PYTHONPATH='C:/Users/99505/.astrbot/backend/app;C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/.p4-tmp'
$env:TEMP='…\.p4-tmp\temp'; $env:TMP=$env:TEMP
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -W ignore -m unittest tests.test_rest_reply_gate tests.test_humanized_state -q
```

**结果：28 项通过**（`Ran 28 tests … OK`）。覆盖：

| 目标 | 用例 |
| --- | --- |
| 配置登记与边界（8+4 项、owner/层/档位、默认值=V1、越界拒绝） | `RestGateJudgementTests.test_configuration_group_contract_and_defaults`、`HumanizedBandTests.test_configuration_registration_and_defaults` |
| 时段解析（跨零点、分隔符、空=全天、坏时区回落） | `test_windows_follow_the_v1_parser_including_midnight` |
| 睡眠窗口内概率判定与边界分 | `test_boundary_score_migrates_the_v1_intent`、`test_the_decision_needs_an_actual_sleep_receipt`、`test_probability_miss_and_boundaries_produce_a_bounded_hold` |
| 模型醒来判断默认关闭、失败/未知不得回复 | `test_model_judgement_is_off_by_default_and_unknown_never_replies` |
| 免重判（同批次、醒后 grace、跨睡眠回执） | `test_the_awake_grace_skips_a_second_judgement_for_the_same_sleep`、`test_one_inbound_is_judged_once_and_never_redrawn`、`test_a_waking_reply_is_not_judged_again_within_the_grace` |
| 醒后补看有界且可追溯（来源+顺序+能力），只在醒后释放一次 | `test_the_backlog_is_bounded_ordered_and_only_released_after_waking` |
| 延迟写进 `due_at`、`deadline_at` 安全、不得 `deadline_elapsed` | `test_a_sleep_window_moves_due_at_and_never_ends_in_deadline_elapsed`（真跑 `flow.accept(defer_seconds=…)` 到 `complete`） |
| 重启保持（判定与补看落库） | `test_an_unavailable_judgement_holds_the_reply_across_a_restart` |
| 睡眠回执读失败/已到点/不在时段 → 不延迟 | `test_a_sleep_receipt_that_stops_answering_keeps_the_ordinary_window`、`test_a_due_sleep_timer_or_a_foreign_window_is_not_sleeping`、`test_a_disabled_gate_or_an_awake_role_never_delays` |
| 强度 0＝不注入、封存与重放一致、非法强度拒绝 | `HumanizedStateHostTests.test_the_dial_is_sealed_with_the_state_and_zero_injects_nothing`、`test_an_unusable_dial_in_a_sealed_snapshot_is_refused_not_defaulted` |
| 真实回复链带上有界表达块、busy 不变成拒答、不含 location | `test_a_real_reply_carries_the_bounded_block_and_still_replies_while_busy` |
| 巡视时刻/一天一次/保留天数清理/不改状态/授权失败不阻塞 | `test_the_daily_patrol_records_once_per_local_day_and_prunes_by_retention`、`test_the_patrol_needs_its_own_grant_and_never_blocks_maintenance`、`test_a_disabled_patrol_leaves_no_records`、`HumanizedBandTests.test_patrol_time_contract_and_retention_pruning` |

## 六、宿主接线（主代理执行；本片未改宿主文件）

**A. `companion_v2/host/application.py`（必需）**

1) import（与既有 `from companion_v2.conversation import busy_gate` 并列）：
   `from companion_v2.role_work.life import rest_gate`
2) `accept()`（当前 421-424 行）把延迟改为两个闸门的上界：
   ```python
   defer_seconds=max(self.busy_deferral(context, event), self.rest_deferral(context, event))
   ```
3) 在 `busy_deferral` 之后新增同形方法：
   ```python
   def rest_deferral(self, context, event):
       if context.scope.kind is not ScopeKind.PRIVATE:
           return 0.0
       try:
           record = self.messages._read_source(event.source, context, event.capability, self.now())
           text = record.payload if record.content_hash == event.input_hash else ""
           return rest_gate.deferral(self.runtime, context, text=text, now=self.now(),
                                     event_key=event.scoped_key, source=event.source,
                                     capability=event.capability)
       except (TaskError, ValueError, KeyError, TypeError):
           return 0.0
   ```
   签名：`rest_gate.deferral(runtime, context, *, text="", now, event_key="", source=None, capability="",
   settings=None, judge=None) -> float`（0–900）。`judge` 有意不传：accept 路径同步，`llm` 模式因此挂起（fail-closed）。
4) 配置登记**无需改动**：8 个新字段已在 `life_configuration_fields()` 内，`extra` 与
   `LifeConfigurationOwner(owners=…)` 都已存在。

**B. `companion_v2/conversation/messages.py`（醒后补看注入，建议）** —— 该文件不在本片可改范围，故未实施：
在 role_state 指令块之后（现 514-516 行附近）对私聊追加
`rest_gate.consume(self.runtime, context, now=at)` → 用 `rest_gate.backlog_prompt(entries, texts,
timezone=settings.sleep_timezone, max_messages=settings.max_backlog())` 追加，`texts` 由原来源按
`entry["capability"]` 重读（读不到写 `None`）。API 与格式已测试，仅差这一处调用。

**C. 无需改动**：`delivery/**`、`adapters/**`、`conversation/flow.py`、`_conf_schema.json`、`main.py`。

## 七、遗留风险

1. **补看注入尚未接线**（第六节 B）：判定、记录、上限、顺序、释放时机与文案均已测试，但真实回复里还看不到
   那段文本，直到主代理补上 `messages.py` 的那一次调用。
2. **有界等待 ≠ 完全不回**：极长睡眠中被挂起的消息最晚 900 秒后仍会被回复（差异第 1 条）。要更保守就调小
   `rest_reply_active_windows` 或关闭总闸，无需改代码。
3. **`llm` 模式当前等价于「挂起」**：除非宿主注入同步 `judge`。若日后要真正用模型判断，应作为后台任务在
   accept 前预判并把结果作为 `judge` 注入，而不是在闸门里同步调用模型。
4. **V1 软唤醒词（「在吗」「睡了吗」）默认直接放行**：阈值 65 下这类文本得 72 分，属 V1 既有语义；若现场觉得
   太容易醒，应调 `rest_reply_llm_threshold`（例如 80）而不是改代码。
5. **巡视只观察不修正**：过期条件不写回状态记录，`daily_state_patrol_retention_days` 只清理巡视自己的记录；
   已过期条件仍留在状态正本里（投影层已隐藏），这是刻意的，避免巡视与人工校准争版本。
6. **`conversation_flows.reason` 仍显示 `busy_delay`**：`flow.py` 本任务禁改，休息闸门的原因只在它自己的
   文档里可查。若后续要给 `reason` 增加 `rest_delay`，需改 `flow.py` 的常量判断（该列无 CHECK 约束）。
7. **页面接入**：`_conf_schema.json` 与「陪伴小屋」控件未改（本任务禁改 / 属第②阶段），12 个字段目前只能经
   配置 API 或直接写入生效。
8. **真机时序未测**：全部结论来自确定性时钟夹具，没有真实睡眠窗口与平台延迟的现场数据。
9. **每轮多一次配置读**：强度在 `capture()` 时封存，因此每条入站封存会多读一次 `role.state` 组（与 T52 在 accept
   路径读 `conversation.busy_gate` 同量级）；这是「重放逐字节一致」的代价，读失败按「未知=不注入」处理。
10. **两处并行工作流造成的既有回归与本片无关**（已用因果探针确认）：`test_role_cycle_variation`
    的 `test_existing_clock_with_pending_plan_and_missing_variation_fields_stays_fixed`（去掉本片新增的 4 个
    `role.state` 默认键后仍失败）与 `test_astrbot_background_fairness` 的
    `test_queued_diary_and_state_run_before_next_reading_span_and_foreground_still_progresses`
    （临时停用巡视调用后仍失败）。两者都不在本片可改范围内，需由对应工作流处理。
