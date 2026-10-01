# 识屏生产链与撤回转述：P3 剩余建设收口

日期：2026-09-27。范围：P3（A 段感知缺口）中在代码层面仍未闭环的部分——识屏解读的**生产入口**、两条主动识屏触发链、以及撤回原文的管理视图；不含页面接入（第②阶段）与交付包构建（第③阶段）。

## 一、为什么还要做这一批（实证）

| 现状（本批之前） | 证据 |
| --- | --- |
| 识屏链断在半路：解释与锚点只有测试调用 | `ScreenProcessingPipeline`/`ScreenCaptureService` 无生产调用点（审计 B9/B10） |
| 主动识屏与日记素材两条消费链永远取不到数据 | `proactive/screen_events.py`（`feedback_kind='proactive'`）、`screen/journal_materials.py`（`feedback_kind='journal'`）都依赖 `screen_analyses` + `screen_feedback_anchors`，而两者只能由 pipeline 写入 |
| 两条消费链的 SQL 引用了不存在的列 | `JOIN sources s ON s.source_lineage_id = c.source_lineage_id`；`sources` 的真实列是 `lineage_id`（`companion_v2/sources/repositories.py` 的 INSERT），因此即使有数据，查询也会抛 `no such column` |
| 主动识屏没有任何触发者 | 配置只有「看一眼屏幕/日上限/冷却」三项；V1 的晚安识屏与沉默窥屏 5 项没有等价物，也没有设备调用入口 |
| 撤回只有「撤回事实」，没有转述 | `conversation/recalls.py` 只做标记、撤销与失效；V1 的 `enable_recall_message_cache` 等键零命中 |

## 二、本批落地

### 1. 识屏解读的生产入口（T17/T19/T20 的共同缺口）

- `companion_v2/screen/interpretation.py`（新）：`ScreenInterpretationService`
  - 任务种类 `screen.interpretation`（后台车道、`SideEffect.LOCAL`、单次尝试、并发 1、超时 60s）；模型档位 `screen.interpretation`（`capabilities=("text","image")`）。
  - `submit(context, capture, purpose, ...)`：只在窗口开启解读、能力同意仍在、原始件可读时排队；同一 capture+purpose 只排一次（`execution_tasks` 唯一）。
  - `generate(run)`：用既有 `ScreenProcessingPipeline` 完成「准备—解读—落库—回执」；端口实现 `interpret()` 通过模型网关取回 `{"interpretation": "…"}`，解析失败按未知处理，不补写、不重放。
  - 反馈锚点：`reply` → REPLY；`glance` → PROACTIVE（需扩展能力设置允许主动）；`journal` → JOURNAL；窗口开启日记融合时**同一次解读**再记一个 JOURNAL 锚点（同分析，两个锚点各自唯一）。
- `ScreenProcessingPipeline.process` 改为异步：端口允许返回 awaitable（既有同步夹具端口继续可用），并新增 `extra_feedback`（一次解读可带多个明确意图）。`tests/test_screen_pipeline.py`、`tests/test_capability_configuration.py` 的调用点同步改为 `asyncio.run(...)`；重入用例改用独立线程复现原语义。
- `astrbot_host/native_extensions/screens.py`：采纳成功后在同一事务内排队解读（`purpose="reply"`），**不阻塞**工具结果与回复；事务回滚时排队一起回滚。
- 模型档位在**单目标 staging** 与**多目标共享宿主**两处都登记（`companion_v2/adapters/astrbot/staging.py`、`astrbot_host/multi_session.py`），因此私聊识屏在两种装配下都可用。

### 2. 日记融合开关（T17）

- 新增配置组 `screen`（owner `screen`，窗口层、稀疏继承）：
  - `screen.interpretation_enabled`（默认关）：是否对已采纳原件做有界模型解读。
  - `screen.journal_material_enabled`（默认关）：解读是否作为当日日记素材。
  - `screen.journal_material_max_chars`（默认 700，200–1600）：单条素材上限。
- `ScreenJournalMaterialProducer` 增加 settings 门控：开关关闭或设置不可读时返回空页，仍沿用既有日记授权与来源校验；素材文本按上限截断。
- 与 V1 的差异（有意）：不建「昨日屏幕日记」独立上下文（用户决定：与日记融合），因此 `enable_yesterday_screen_diary_context`/`screen_diary_context_max_chars` 映射为上述两字段，不再读外部 Screen 插件的日记文件。

### 3. 主动识屏两条链（T20）

- `companion_v2/screen/peek.py`（新）：`ScreenPeekService`，任务种类 `screen.peek`（后台、`SideEffect.EXTERNAL_DEVICE`、单次尝试、并发 1、超时 120s）。
  - 通过**已注册的原生 `screen.capture` 扩展**发起一次设备采集：合成一次性 invocation，`before_dispatch` 复核任务与能力准入，复用既有 `ExternalToolExecutor.admit`（本批新增的公开准入方法）；采纳结果仍由既有 `ScreenAdopter` 发布为受治理原件。
  - 采集成功后把原件交给解读链（`purpose="glance"`）；采集失败/未知只记一次尝试，**不重放**。
  - 记录口径：日上限按「本窗口本地日的 `screen.peek` 任务数」计（尝试即计数，与 V1「开始识屏即 +1」一致）；冷却按最近一次主动识屏联系（既有 `screen_glance_cooldown_minutes`）。
- 触发判定（`proactive/screen_events.py` 的 `peek_due`；`ContactSchedule.advance()` 在计划前先问一次）：
  - **晚安识屏**：本窗口最近一条**已确认送达**的 Bot 文本命中 `晚安|好梦|早点睡|睡吧|休息吧|明天见`，等待 `screen_glance_goodnight_delay_minutes` 后触发；期间用户再次发言即取消该 episode；同一 episode 只触发一次；计入日上限。
  - **沉默窥屏**：最近一条**已送达**的主动联系（非 screen 目的）之后经过 `screen_glance_followup_after_minutes` 且用户始终沉默；受 `screen_glance_followup_cooldown_minutes` 约束；与 V1 一致**不占**日上限，但仍受普通冷却。
- 新增配置（沿用 `proactive.contact` 组，与既有 `screen_glance_*` 同处）：`screen_glance_goodnight_enabled`（默认关）、`screen_glance_goodnight_delay_minutes`（45，1–180）、`screen_glance_followup_enabled`（默认关）、`screen_glance_followup_after_minutes`（45，10–240）、`screen_glance_followup_cooldown_minutes`（180，30–1440）。
- V1↔V2 键映射：`enable_screen_glance_action`→`screen_glance_enabled`；`screen_peek_max_daily`→`screen_glance_daily_limit`；`screen_peek_cooldown_minutes`→`screen_glance_cooldown_minutes`；`enable_goodnight_screen_check`/`goodnight_screen_check_delay_minutes`/`enable_unanswered_screen_peek_followup`/`unanswered_screen_peek_after_minutes`/`unanswered_screen_peek_cooldown_minutes`→上列 5 项（语义按 V2 调度器改写，见下）。
- 有意的差异：V1 在「刚发出晚安回复」时排期，并限 30 分钟内可排；V2 的调度器自行轮询，因此把「可排期时效」放宽为 6 小时（保证 180 分钟的最大延迟仍能生效），其余判据（已送达、用户期间发言即取消、单次 episode、冷却与配额口径）保持。
- 必要前置：`PROACTIVE` 锚点要求 `capability_settings.proactive_enabled`，而此前**没有任何生产写入路径**。本批把 `CapabilityConfigurationOwner`（每个已声明扩展一个）接入统一配置注册表与 owners（`companion_v2/adapters/astrbot/application.py` 由声明派生，`CompanionApplication(capability_owners=...)` 注册），使「主动分享/念头权重」可在统一配置面按 scope 设置。

### 4. 撤回原文的管理视图（T13 收尾）

- 新增配置组 `conversation.recall`（窗口层、稀疏继承）：`transcribe_enabled`（默认关）、`transcribe_max_items`（5，1–20）、`transcribe_text_chars`（500，80–2000）、`transcribe_window_minutes`（10，1–1440）。
- `ConversationRecalls.transcribe(context, operator, settings, at)`：只读本窗口**已撤回**的入站行，回读其**原始来源载荷**（载荷与自身哈希不一致则跳过），按本地时间倒序、条数与字符双上限；时区取 `conversation.perception.calendar_timezone`（与日期语境同源）。
  - 授权：`memory.manage`（core-only）→ 等价 V1「Bot 管理员」；普通窗口参与者没有该权限。
  - 边界：不复活已撤销来源、不发布新来源、不进入生成上下文；未知/过期一律返回空列表而不是猜测。
- `companion_v2/conversation/recall_management.py` + Dashboard 路由 `GET /astrbot_plugin_private_companion_v2/reply/recalls`（限 1–20，Dashboard 身份校验，未初始化/停机有明确错误码）。
- 有意的差异（V1 键映射）：不另建短期消息缓存（V2 本来就保留入站行并在原处标记撤回）；不复制/补发撤回原图（V1 会把图片落盘并在转述时补发，V2 不复制受治理字节）；不做聊天命令（V2 的管理入口是已认证 Dashboard 视图），自然语言提问链路随之取消。

## 三、验证

新增/更新的定向测试：

| 测试 | 覆盖 |
| --- | --- |
| `tests/test_screen_interpretation.py`（新，4 项） | 解读链端到端：窗口开关、锚点（reply+journal）、日记素材可读、模型确实收到屏幕图片、同 capture 不重复解读、窗口关闭不触模型；晚安识屏等待与「用户回来即取消」；沉默窥屏的沉默前置与自身冷却 |
| `tests/test_recall_transcribe.py`（新，2 项） | 撤回原文仅在开关开启且 operator 为 CORE 时可读；读回内容与作者正确；撤回来源保持撤销 |
| `tests/test_screen_pipeline.py`（更新） | 异步管线 + 多意图锚点不改变既有语义（重入用例改用独立线程） |
| `tests/test_capability_configuration.py`（更新） | 异步调用点 |

统一回归（AstrBot 自带 Python，`PYTHONPATH` 含 `backend/app`）：见 `BUILD_STATUS.md` 最新条目；`python -m compileall -q companion_v2 astrbot_host` 通过。

## 四、顺带修复的缺陷

1. `screen/journal_materials.py` 与 `proactive/screen_events.py` 的来源连接列名错误（`s.source_lineage_id` → `s.lineage_id`）；修正前两条消费链在有数据时也会抛 `no such column`。
2. 同一批新增服务在 `CompanionApplication` 的装配点（注册、attach、planner、句柄、故障清理、close）全部接线，避免「服务存在但无人驱动」。
3. 新增功能暴露了一处同类隐患（**未在本批修改**，已登记为审计 B17）：`conversation/media/review_service.py` 的模型档键名 `image_review` 与任务种类 `conversation.image_review` 不一致，`ModelRouter.resolve` 按任务种类取档，生产调用会以 `model_task_unregistered` 失败；该模块的测试只覆盖配置字段，因此此前未被发现。识屏解读的新档位按同一约定写作「档名 = 任务种类」并在两种宿主装配中登记，不存在该问题。

## 五、未纳入本批（保留为待办，不当作已完成）

- **页面控件**：`screen` 组与 `conversation.recall` 组、主动识屏 5 项字段，以及「撤回原文」视图都还没有挂到唯一公开页「陪伴小屋」；按项目顺序留到第②阶段统一接入。
- **A4 外部资讯源**：
  - `WEB_EXPLORATION_API_BASE_URL/API_KEY/API_MODEL`（V1 的自定义搜索接口）在 V2 由宿主搜索端口负责（`astrbot_host/news.py` 的 `WebSearchNewsPort` + `COMPANION_V2_NEWS_*`/宿主配置），插件侧只保留兴趣倾向与结果数；「接口模型名」无对应消费者，记为设计差异。
  - `enable_web_exploration_boredom_search`（空档自主搜索）依赖 V1 的「无聊判定」子系统；V2 的主动机会由既有节奏/空闲/配额门控决定，未另建无聊模型，记为设计差异。
  - `external_event_self_link_override_*`（意愿放宽阈值）依赖 V1 的分享欲评分（relevance/desire/probability 三元）；V2 的资讯机会权重是另一套有界评分，未引入 V1 数值体系，记为设计差异。
- **真实设备/现场**：本批没有触发真实截图、真实模型或 QQ 发送；主动识屏的现场效果（含 Screen 扩展未安装、设备拒绝、能力未授予三种失败面）仍需在受控账号上验收。
- **图片转述**：V1 会补发撤回原图，本批只做文本；如需迁移需先定义受治理字节的读取与受众口径。
