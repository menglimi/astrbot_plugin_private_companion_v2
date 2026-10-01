# 配置缺口收口（2026-09-28）：B 类常量转配置 + 两项改判

依据 `docs/V1_V2_CONFIG_VERIFIED_20260927.csv`（1010 行权威账本）的 `owed` 114 行，按用户批注「B 修复即可」推进。
本轮遵守同一登记规则：**配置字段必须有真实消费者**，无消费者的不注册。

## 一、B 类范围界定（先纠正分类，再动手）

原始 `owed` 清单里被打成一类的项，性质并不同，本轮先分开：

**B1 常量转配置（本轮做）**——行为已在，只缺配置面，且结构常量与业务上限可两层拆。

**B2 实为功能缺口（从 B 移出）**——V2 侧对应行为**根本不存在**，不是"没暴露配置"：
- `memory_habit_config.meal_care_followup_minutes`：V2 无「饭点问候未回应后补问一次」这条路径。
  落点证据：`proactive/meal_events.py:13` 把槽宽写死 `WINDOW = timedelta(minutes=45)`，`:42-53`
  每个午/晚餐槽只选一次；未回应的唯一反应是跨用途的 `contact_interval_seconds` 放缓
  （`proactive/preferences.py:78-82`），与 V1 的"单次低压补问"不是同一件事。
  **改判为功能缺口，归 A/C 类**，不在本轮做。
- `life_schedule_config.daily_plan_time`：V2 无每日日程生成时刻判定。
  落点证据：`agenda/planning.py:178-184` 的机会键只看本地日期槽 `daily:<tz>:<date>`，
  `planning_inputs.py:65-66` 以次日零点为结束，全程无 HH:MM 到期判断。
  同类每日后台时刻在 V2 已可配（`role_work/state/humanized.py` 的 `daily_state_patrol_time='04:00'`），
  所以这是真欠账而非取舍。**改判为功能缺口，归 A/C 类**。

**B3 已作决定、本轮销号**——`skill_growth_config.skill_growth_rate`：
V1 用它乘技能经验（`daily_state.py:14051`），而 V2 成长是定性提案制、**没有可乘的经验数值**
（`role_work/growth/configuration.py:19-25` 的 `SKILL_FIELDS` 只有 `custom_skills` 与
`schedule_influence_strength`）。此项**早已在 `CONFIG_GAP_BATCH_20260927.md` 的 T32 节登记为"不注册"**，
但账本 CSV 仍标 `owed`——是账本未吸收该决定，不是真缺口。**本轮销号**。

## 二、本轮落地：`role.state.planning_weather_max_age_minutes`

V1 `weather_config.weather_refresh_minutes`（10–720，默认 90）控制天气缓存过期判定；
V2 把新鲜度写成常量 `agenda/weather_material.py` 的 `MAX_AGE = timedelta(hours=2)`。本轮转为可配。

- **新字段**：`role.state.planning_weather_max_age_minutes`（INTEGER 5–120，默认 120）。
  与既有 `planning_weather_enabled`/`planning_weather_location` 同组并列，走统一字段注册表
  （挂在 `role.state` 组，随 `PLANNING_DEFAULTS` 合并，`role_work/state/configuration.py:30`）。
- **两层拆分**：结构常量 `WEATHER_MAX_AGE_MINUTES = 120` 定义在 `agenda/planning_config.py`
  （被依赖的底层，避免与 `proactive` 侧成环），`weather_material.MAX_AGE` 由它派生；
  配置上界引用该常量，**只能收紧不能放宽**——与 `conversation.image_review` 的
  `group_nsfw_image_review_max_images: (1, MAX_INPUT_IMAGES)` 同口径。
- **消费者**（三处，全部传 `max_age`）：
  - `agenda/planning_inputs.py:78`（规划材料）
  - `proactive/weather_events.py` 的 `prepare`（天气问候）
  - `proactive/weather_change_events.py`（天气变化）
- **存量可读**：`weather_events._validate_source` 原本会用**当前配置**重算历史 payload
  （`body != self._body(material)`），配置一改就会让已落库来源失效。改为把生效窗口随 receipt 存下
  （`_receipt.max_age_seconds`），复核时按**落库时的值**重算，不用当前设置。
  receipt 键集校验同步收紧为 `{context, slot, max_age_seconds}`，并校验 `0 < recorded <= 结构常量`。
  `weather_change_events._validate_source` 比对的是落库 `event` 内容、不重算 material，无需改动。
- **升级安全**：`SparseConfigurationOwner.read` 对缺失键回落 `field.default`
  （`configuration/owners.py:70`），旧配置不会 KeyError；默认值等于原常量 2 小时，
  未编辑该字段的安装行为零变化。
- **边界一致性**：`role_work/state/configuration.py` 的通用 INTEGER 兜底下界是 1，而校验要求 ≥5，
  故为该字段显式写 `(WEATHER_MAX_AGE_MINIMUM, PLANNING_MAXIMUMS[name])`，
  避免注册表广告出 `validate_settings` 会拒绝的值。

## 三、本轮落地：`runtime.forward_max_nodes` / `forward_max_depth` / `forward_max_forwards`

`forward_message_config.forward_message_max_messages`（V1 单次最多读取条数）与
`forward_message_parse_nested`（是否展开嵌套）在 V2 对应两个写死常量：
`conversation/forwards/models.py` 的 `MAX_NODES = 32`、`MAX_DEPTH = 4`。本轮转为可配。

**关键约束（决定整个做法）**：这两个常量同时承担**两种职责**——
① 捕获上限；② **持久化描述符的校验**（`node_fields`/`check_tree`/`fits_forwards`）。
而 `conversation/flow.py:109` 与 `conversation/messages.py:106` 会从存储里
`ForwardDescriptor.restore(...)`。**若直接把常量改成可配，配置收紧后已落库的转发事件会抛
`forward_manifest_invalid` 读不出来**。

因此按 V2 既有范式（`conversation.image_review` 的
`group_nsfw_image_review_max_images: (1, MAX_INPUT_IMAGES)`）拆两层：

- **结构常量不动**（`forwards/models.py` 的 `MAX_FORWARDS=4`/`MAX_NODES=32`/`MAX_DEPTH=4`）：
  描述符校验继续用它，保证任何配置下存量数据永远可读。
- **摄入侧可配**（新增 `ForwardIntakePolicy` 冻结 dataclass）：上界引用结构常量，**只能收紧**，
  越界抛 `forward_intake_invalid`。默认值等于结构常量，未编辑的安装行为零变化。
- **配置通道**：根 schema `runtime` 组三项（`forward_max_nodes` 默认 32、`forward_max_depth` 默认 4、
  `forward_max_forwards` 默认 4），`astrbot_host/settings.py` 读取为 `StagingProfile.forward_intake`，
  经 `NativePrivateBridge` 传 `self.forward_intake`。与 `quiet_seconds` 同属宿主结构参数，
  不进 `MultiHostSettings` 指纹。
- **接入的摄入入口（6 处）**：`adapters/astrbot/native.py`（私聊，含 `forward_locators` 上限与
  forward/quote loader 调用）、`group.py`（群聊，同样两处）、`forwards.py` 的
  `freeze_forward_cards`/`freeze_nodes`/`read_private_forwards`、`group_forwards.py` 的
  `read_group_forwards`、`quote_content.py` 的 `capture_quote_content`（引语里的嵌套转发）、
  以及 `quotes.py`/`group_quotes.py` 两条 loader（把 intake 透传下去）。
  `astrbot_host/forwards.py`、`astrbot_host/quotes.py` 的四个 `load_native_*` 增加
  `intake=ForwardIntakePolicy()` 具名参数，默认不变。

## 四、验证（合并回归 130 项）

- `python -m compileall -q companion_v2 astrbot_host` 退出 0。
- 定向新增 `tests.test_conversation_forwards.ForwardIntakePolicyTests` **5 项通过**：
  默认等于结构常量、可收紧但不可放宽（三项各自越界抛 `forward_intake_invalid`）、
  非正/非整数拒绝、收紧的节点上限在**任何下载前**拒绝且存量描述符仍可构造、
  收紧的深度上限阻止嵌套展开。
- 天气定向 `tests.test_planning_weather` **10 项通过**（原 7 + 新 3）。
- 合并回归：转发/引语/规划天气/天气事件/天气变化/角色状态/配置存储/管理访问
  **130 项，129 通过**。
- **唯一失败的定性（既有、非本轮引入）**：`tests.test_conversation_quotes`
  的 `test_quote_history_failure_is_single_attempt_without_global_fallback`。
  沙箱是 **Python 3.10**，而 `asyncio.TimeoutError` 与内建 `TimeoutError` 到 **3.11 才合并**。
  测试抛内建 `TimeoutError`，`adapters/astrbot/quotes.py:86` 只捕 `asyncio.TimeoutError`，
  于是落到 `except Exception` → 拿到 `host_quote_unavailable` 而非 `host_quote_timeout`。
  实测 **3/3 稳定复现**，且该文件本轮仅加了 `intake` 参数与导入、未触碰异常分支；
  AstrBot 自带 Python 为 3.12，不受影响。**记为环境版本差异，不是回归。**

## 五、两项遗留的处置（同批收口）

### 5.1 `group_high_intensity`：销号，判为「已有等价」

V1 侧是 7 字段的**硬状态机**（`group_high_intensity_until` 到期后直接 `blocked`，把一段高烈度对话
从接话候选里排除）。V2 不迁移该状态机，理由不是"懒得做"，而是**同一组语义已由更细的软机制覆盖**：

| V1 概念 | V2 落点（`conversation/reply_settings.py` + `participation_prompts.py`） |
| --- | --- |
| 高烈度期禁止接话 | `group_air_guard_*`（默认开）：窗口 180s、连续接话上限 3 轮、礼貌收尾循环上限 2 次 |
| 烈度衰减 | `group_wakeup_fatigue_*`：疲劳每轮 +1、每 90 分钟恢复 1 点、阈值 5 点 |

差别在**执行方式**：V2 把这些值作为**参考值写进 prompt**（`participation_prompts.py:51-56,123-127`，
措辞明确是"参考值"而非禁令），由模型结合语境决定；V1 是硬闸门。
这是 V2 的既定取向（软克制优于硬阻断），**不是缺口**。若强行补一个 V1 式状态机，
反而会与 air guard / fatigue 两套机制重复判定、互相打架。故**销号**。

### 5.2 `group_slang_topic` 联网扫描数：本轮落地（整条链）

V1 用联网检索辅助理解群内黑话。V2 原先**完全没有这条能力**，本轮补齐整条链，
按用户定的边界：**只作证据、默认关**。

- **宿主端口**：`astrbot_host/semantic_models.py`
  - `configured_slang_search_port()` 从宿主环境变量读端点：
    `COMPANION_V2_SLANG_SEARCH_URL` / `_API_KEY` / `_AUTH_HEADER` / `_AUTH_SCHEME`。
    **凭据只走宿主环境变量，不进 V2 配置文本**，与既有 `COMPANION_V2_NEWS_*` 同口径。
    未配置时返回 `None`——**没有端点是正常状态，不是错误**，整条链静默降级为"无外部参考"。
  - `NativeSlangSearch` **复用** `WebSearchNewsPort` 的 HTTP 形态，不新写客户端。
    注意该端口把查询词固定在构造期并计入 `fingerprint`，所以**按词新建实例**，
    不能拿一个共享实例改 `query`。
  - 通过 `NativeSemanticModels(context, provider_id, slang_search=...)` 注入，两处装配点
    （`controller.py:283`、`multi_controller.py:129`）都已接上。
- **证据收集**：`memory/group/slang.py`
  - **两阶段**：先 `_candidate_terms` 让模型从本轮样例里挑出"像本群特有用法"的词
    （上限 `slang_web_search_candidates`），再 `_external_reference` 逐词检索取摘要。
  - **候选词必须在本轮样例原文里出现过**才能进入检索（`term not in corpus` 即丢弃）。
    这条是硬约束：保证**外部查询不会把读取范围扩大到用户已授权样例之外**，
    也顺带挡掉模型凭空生成的词。
  - 检索结果作为 `EXTERNAL_NOTE` 段落附在**本群样例之后**，措辞明确：
    只作参考证据、不得覆盖本群已确认用法、冲突时以本群样例为准、产出的 meaning 仍须由本群样例支撑。
  - 单个词检索失败只跳过该词，不中断整轮（`except: continue`）；整个观测仍受既有时序门控
    （`learning_interval_seconds`）与 `timeout_seconds` 约束。
- **配置**（`storage/semantic.py`，3 项，默认关）：
  `slang_web_search_enabled=False`、`slang_web_search_candidates=4`（1–12）、
  `slang_web_search_results=2`（1–5）。范围校验加在 `configure()` 的白名单检查之后。
- **页面**：`pages/陪伴小屋/semantic-page.js` 加 1 开关 + 2 数字输入（该页可编辑字段
  由 12 项变 **15 项**，页首注释里的数字已同步）；`index.html` 缓存串改为
  `?v=slang-web-reference-20260928`；`page-build.json` 已 `sync_framework_page.py` 更新。

## 六、本节验证

- `python3 -m compileall -q companion_v2 astrbot_host` 退出 0。
- 新增 `tests/test_group_slang_search.py` **11 项通过**：候选词限定在本轮样例内、
  按配置上限截断、非字符串/空白丢弃、无端点返回空、端点自述不可用返回空、
  参考记录词与有界结果数、单词检索失败降级不抛、空结果不记为证据、
  新键默认关且越界被拒、外部注释从属于本群样例。
- 既有语义回归 `tests.test_semantic_integration` **21 项通过**（默认关，链未触发）。
- 页面契约 `node --test tests/test_semantic_page.cjs` **10 项通过**；
  夹具补入 3 个新字段并新增断言，专门锁住"缺字段 → `Number(null)` 得 0 → 后端拒绝"
  这条退化路径（后端下界为 1）。
- `python3 -m compileall` / `tools/sync_framework_page.py --check` 输出 `{"changed": []}`。
- 跑不到的：`tests.test_group_memory` 等经 `astrbot_host/native.py` 的用例缺 `aiocqhttp`
  （沙箱环境缺口，非本轮引入）。

## 七、仍未开工
- B2 两项（meal 补问、日程生成时刻）——已改判为功能缺口，归 A/C。
- A（书架，走纯提供方合同）、C（等范围划定）。
