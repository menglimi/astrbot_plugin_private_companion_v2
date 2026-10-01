# V2 缺口补全任务清单（2026-09-27）

> 依据 2026-09-27 逐段代码审计（非文档自评）编列。范围：把 V1 配置页功能在 V2 框架约定下迁移/改造/补全。
> 优先处理非插件拓展（七个可选伴侣提供方）的部分；每个任务动工前先读其"参考设计稿"列所列文档。
> 全部任务属工程顺序第①阶段（领域功能+实际生效配置）；陪伴小屋页面接入（第②阶段）在功能完成后统一做，不逐任务立页。
> 批注方式：直接在任务行后加「批注：」，或在文末决策点处给结论。编号（T/DC）固定，后续以编号引用。

## V2 框架硬约束清单（v1→V2 改造基线，2026-09-27 总结）

> 下列 13 条为 V2 相对 V1 的强制架构约束，所有 T 任务（含迁移 / 改造 / 补全）动工前必须逐条对齐；任一条不满足即视为"未完成"，即使代码能跑也不算达标。每条附"反面教材 / 易踩坑"。

1. **代码组织 · 禁止散落根目录**：根目录只保留 `main.py` 与包声明；所有业务进 `companion_v2/<领域>/`（conversation / memory / role_work / proactive / expression / delivery / model_gateway / knowledge 等）。核心模块禁止反向导入宿主（astrbot 框架层）；宿主能力只经注入端口（host port）调用。
2. **存储迁移 · schema 版本化**：每新增 / 变更一张表 = 一个新 schema 版本（当前 v41），必须配套"回滚到上一版本再重开"的迁移测试（夹具缺漏会报 `incomplete vXX-to-vYY migration`）；逐项字段映射写入迁移注释。T09 因审核 / 回退字段可挂 `runtime_metadata` 故不新增表、不升 schema。
3. **配置强注册 · 禁止硬编码**（本次补强要点）：所有可调阈值、窗口、上下限、概率、强度、间隔、档位 **必须** 经 `FieldDefinition` 注册，且每条必须有真实消费者（无消费者不登记，宁可记为设计差异）。严禁业务代码散落硬编码常量——如 `MAX_SAMPLE_CHARS=800` / `MIN_SAMPLES=4` / `MAX_WINDOW_HOURS=720` / `MAX_RULES` 这类正是 T28 被判定"原报完成不成立"的根因。
4. **身份归属 · owner 铁律**：记忆与状态必须带 owner 归属（群 + 成员 / 用户 / Bot 角色），复用既有 owner 体系，不新建成员画像；只有真实回执（授权 / 投递成功 / 操作者回执）才可信，未知状态不重放、不谎报成功。
5. **能力默认关闭**：涉及模型调用的能力默认 `enable_*=False`，由配置显式开启；涉及发送的能力沿用授权 / 回执 / 未知不重放铁律。
6. **页面性能预算**：首屏资源 ≤300KiB；单页 API ≤3 次、单次载荷 ≤100KiB；暖态堆 ≤10MiB；后台无轮询、无 3D / 重动画（V1 管理页常一次性拉全量配置，V2 须分页 / 懒加载）。
7. **回复速度与原生流式**：前台回复不串行等后台任务（智能沉默 / 主动判定等异步，不阻塞出站）；长文分段或 SSE 原生流式，避免整段生成后一次性吐出（V1 常等整段生成才回复）。
8. **未知 / 取消诚实处理**：能力未配置 / 未授权 / 被取消 / 超时等"未知 / 失败"必须诚实告知，不得谎称"已停止 / 已完成"或静默吞掉；用户取消后不重放。
9. **跨能力协作边界**：多能力协作走明确事务 / 事件边界；事务不包裹 I/O（网络 / 文件 / 模型调用不进 DB 事务）。
10. **诊断可观测**：关键路径（审核 / 回退 / 迁移 / 主动判定）留结构化诊断日志与可查询状态，便于排障与复核。
11. **核对口径**：完成判定只认工作区实际代码 + `docs/` 切片文档 + 可复跑定向测试，不采信自评 / 交接结论；声称"已完成"须能指到落点文件 + 测试模块。
12. **迁移 / 替换发行铁律**：凡标记"从 V1 迁移 / 替换"的任务，需提供真实证据（v1 源码对照 + V2 落点 + 测试），禁止"名义迁移"（只登记 FieldDefinition 不接消费逻辑，或只写常量不接行为）。
13. **v1 资产优先复用**：V2 是 V1 的架构重置而非空白重写；每个迁移 / 改造任务动工前先查本页「v1 既有资产索引」读对应 v1 模块，以"读现有实现 → 适配 V2 架构"为优先路径。

## 批注记录

- 2026-09-27 用户批注：DC-1 定案（四档默认全 -1 不限；只做张数限制，费用限制不做→T02 销账）；亲密度相关搁置标注（T30 搁置）；群成员风控改为「规则命中 + 每日反思阶段统一判断处理」（T08 重新立项）；复读跟读/打断复读保留（T37 保留）；DC-5/6/7/8 对应任务搁置标注（T23、T43、T47、T11、T07）；被动回复复核/主动消息终审搁置、倾向删除/重做（T04、T05 搁置）；智能沉默保留但需优化（T06 保留，先优化设计再动工）；识屏日记与日记功能重复，融合进日记链（T17 改造为融合方案）。
- 2026-09-27 第二轮核对：新增文末「进度快照」区，逐项以代码与测试实证复核任务状态；T10 由「正常排期」改为已完成并补台账；T28 原报完成经复核不成立，退回待办；T09/T25/T31/T35 实测未开工。
- 2026-09-27 第三轮（用户批注）：T09 私聊回退口径定为「本批一起做」（选项 B）。V2 投递信封按原始受众密封，框架内没有「群任务改发私聊」的通道，因此改造为：群侧只发文字、图片走独立私聊投递（不同受众/授权/回执）；私聊通道只在「该成员本身是已配置私聊 target 且有当前投递授权」时成立，否则保持阻止而不广播。已按此完成 T09 首版并补切片记录与台账。
- 2026-09-27 第四轮（用户批注）：①拟人回复 Prompt 定为「可选开关 + 可自定义文本」，承载在**各渠道既有的风格组**（`conversation.presentation` / `proactive.contact` / `role.life`），不新建独立配置组；②表达学习的分布问题按用户原话定为**「用后降权」**（不是只修窗口/批次）；③决策页 B4 定为**挂真实控件 + 补两个沉默字段控件**；④流程上明确「以 v1 现有实现为参考改造、减少逐项测试改为攒批统一测试」。四条均已落地，见 [切片记录](HUMANIZED_AND_EXPRESSION_LEARNING_SLICE_20260927.md)：拟人开关与自定义文本（含 v1/v2 差异说明：不采纳"故意打错字"一类会损伤已送达文本的做法）、T28 首版含群聊学习与用后降权轮换、决策页 B4 与 `silence_min_confidence`/`silence_feedback_penalty` 控件、表情系统 v1↔v2 迁移审计、反思与梦境融合设计稿。

## 进度快照（2026-09-27 第三轮核对）

> 口径：只看工作区实际代码、切片文档与可复跑的定向测试，不采信自评结论。本轮核实的完整证据见[已完成项核实记录](COMPLETED_TASKS_VERIFICATION_20260927.md)。

### 已完成（代码 + 切片 + 定向测试齐备）

| 编号 | 实证落点 | 验证 |
| --- | --- | --- |
| T01 | `conversation/media/quota.py` | `tests.test_image_quota` 通过 |
| T03 | `conversation/text_processing.py` framework_guard | `tests.test_framework_guard` 通过 |
| T06 | `proactive/configuration.py` 的 `silence_min_confidence`/`silence_feedback_penalty` | `tests.test_proactive_contacts` 沉默用例通过 |
| T08 | `memory/group/hits.py` + 存储 v41 `group_member_safety_hits` | `tests.test_group_member_safety` 通过 |
| T09 | `conversation/media/review.py` + `review_service.py` + `fallback.py` | `tests.test_group_image_review` 18 项通过 |
| T10 | `conversation/reply_settings.py` 三开关进封存快照 | `test_group_safety_guards`/`test_addressing_prompts`/`test_reply_text_processing` 通过 |
| T14 | `ReplyTextPolicy.forbidden_word_guard` 作用域+Bot 身份语义 | `tests.test_reply_text_processing` 11 项通过 |
| T15 | `conversation/date_context.py` + 宿主节气表 `astrbot_host/solar_terms.py`（★ 2026-09-28 才补上宿主生产者，此前 `solar_term_port` 全程无生产者、恒 `unavailable`） | `tests.test_host_solar_terms` 10 项通过 |
| T16/T32/T34/T42/T44/T54 | 各自配置字段已登记且有真实消费者 | 4 个新增模块 + 受影响回归通过 |
| T25 | `memory/episode_settings.py` + 既有 `memory` 组四项字段 + `memory/reflection.py` 群分支材料（**整合口径，不建第二套记忆**） | `tests.test_group_episode_material` 8 项通过 |
| T26 | `memory/habits.py`（`KIND="user.habit.v1"`）+ `memory/context.py` 真实消费 | `tests.test_user_habit_profile` 通过 |
| T27 | `knowledge/` 七文件（导入/解析/检索/成员线索）+ `astrbot_host/knowledge_sources.py` 装配；14 项 `knowledge` 组 | `tests.test_knowledge_import` 通过 |
| T28 | `expression/style_rotation.py` + `expression.learning` 组；衰减照抄 V1 `dreaming.py:330` 的 `pow(0.72, age_hours/24)` | 见 [切片记录](HUMANIZED_AND_EXPRESSION_LEARNING_SLICE_20260927.md) |
| T29 | `conversation/group_observation.py` + `participation.py` 折入 `runtime_metadata`；7 项沿用 V1 键名 | `tests.test_group_observation_family` 通过 |
| T31 | `memory/episodes.py`（`CURSOR_PREFIX="memory.episode.v1:"`、`episode_due()` 三态阈值）+ `memory/reflection.py` 消费 | `tests.test_private_dialogue_episode` 通过 |
| T33 | `role_work/life/rest_gate.py` + `conversation/flow.py` 写 `due_at`；8 项并入 `role.life` | `tests.test_rest_reply_gate` 通过 |
| T35 | `role_work/state/humanized.py` + `conversation/state_context.py`；`state/maintenance.py` 调 `patrol_due/patrol`（含保留天数裁剪）；4 字段并入 `role.state` | `tests.test_humanized_state` 通过 |
| T45/T46/T48/T49/T51/T52/T53 | 各自切片记录；T53 的 V1 依据已核（安装级无窗口、默认 1000000/True/800000、`limit<=0` 为不限） | 各自定向测试 + 受控回归通过 |

### 未完成

| 编号 | 实测结论 | 证据 |
| --- | --- | --- |
| T50 | 排后（依赖 T27） | 跨群转述与 @ 群友尚未开工 |

> **2026-09-28 复核更正**：本节此前把 T31、T35 记为「未开工」，**判定有误**。逐文件核验后两项均已落地（见上表）。同时 P2 表内 T29/T31 各有重复一行（一行「已完成首版」、一行「待批注/未开工」），重复行已删除。另有 T21/T18/T22/T24 的落点与字段计数不实，已在下表更正。
>
> 该节口径要求「不采信自评结论」，但当时对 T31/T35 的否定结论同样未做文件级核验即写下，属同类错误。

### 本轮统一验证与工作区

- **已完成项核实**：53 处声明文件引用全部成立（标"缺失"的均为"来源（V1）"列）；切片引用的 40 个测试模块全部存在；32 模块定向实跑 350 项中 341 通过，9 项未通过经逐项定性为 **1 项真实失败 + 12 项批次污染**，详见[核实记录](COMPLETED_TASKS_VERIFICATION_20260927.md)。
- **真实失败已修**：`conversation/segment_control.py` 的分段标记判据按 V1 `segmented_message.py:236-251` 对齐（只排除代码围栏与引用行，缩进不豁免；切分两侧 `rstrip`/`lstrip`），并修掉保护区间两处既有缺陷（删标记未收缩区间导致偏移错位、`_word_boundaries` 右端开区间）。`tests.test_reply_segmentation` 10 项全通过，新增 `test_a_marker_line_is_a_boundary_unless_fenced_or_quoted` 钉住 V1 规则；原"列表内标记应保持原子"的期望与 V1 不符，已收窄。
- **批次污染的定性已修正**：后续独立复跑同一 31 模块命令两次，**`busy_reply_gate`/`daily_token_soft_limit` 零失败**，且唯一失败项单独跑同样失败（并发编辑滞后），故原 9 项**不是隔离缺陷**，而是（a）墙钟轮询超时 +（b）并行编辑中间态。真实存在但**不充分**的隔离问题另记：`tests/test_astrbot_staging_host.py:12-19` 在模块体写 `ASTRBOT_ROOT` 且恢复只写在永不执行的 `tearDownModule`，同链让 SDK 把 root logger 永久设 DEBUG 并起 2 个后台线程（定向实验证明不足以打挂测试，留作独立小任务）。
- **超时治理已落地**：`tests/test_host_application.py` 的 `until()`（`wait_seconds=20`）与 `tests/staging_bootstrap_support.py` 的 `wait_for_batch()`（20s）改为"预算用于兜住挂死、不用于量被测行为快慢"；改动后同一条 31 模块批次 **343 项只剩 1 项失败**，超时类失败清零（`test_busy_reply_gate`/`test_host_application`/`test_group_participation`/`test_agenda_background` 78 项全绿）。
- **剩余 1 项非本批**：`tests.test_style_prompts.test_style_prompt_enters_proactive_instruction` 报 `KeyError: 'proactive_intensity_preset'`，单独跑同样失败——`companion_v2/proactive/rhythm.py:66` 已读该键而 `tests/test_style_prompts.py:19-24` 的 `PREF_VALUES` 未补，属主动强度预设在建功能的滞后夹具。
- 工作区：`git status --short` 显示插件目录整体为未跟踪状态（无提交基线），未执行任何破坏性 Git 操作，未回滚、未清理。

### 下一步建议顺序

1. **T31**：私聊片段按 T25 的整合口径落地（并入既有 `memory` 组、走既有反思链），并同时补 V1 的"刷新到期判断"（**落在既有反思/记忆调度游标，不新增状态列**）；届时须把片段任务的 kind 登进 `DEFAULT_SOFT_DEFER_KINDS`——V1 的低优先清单本就含 `group_episode`/`dialogue_episode`（`token_budget.py:875,877`），V2 目前缺这两项。
2. **T28 群作用域入口**：JSON 路径已修（`$.audience.scope.*`），但 `style_service.advance()` 仍只遍历 `state_maintenance.bindings` 并跳过非私聊作用域；放开前需先定 V1 `expression_group_application_mode`（默认 `all`）的等价闸，否则群内学到的形式规则会直接流入私聊回复。
3. **T35**：拟人状态强度注入 + 每日巡视时刻/保留天数，落在 `role_work/state/` 与 `conversation/state_context.py`。
4. **T50（依赖 T27）** 与 **T13/T17/T18/T19/T20/T21/T22/T24/T26/T27/T29/T33/T36/T37/T38/T39/T40/T41** 仍按原排期。
5. 上述任一批次完成后统一跑定向测试 + `compileall` + UTF-8/LF 检查，再进入第②阶段页面接入。

## 决策点速览

| 编号 | 决策点 | 影响任务 | 结论 |
| --- | --- | --- | --- |
| DC-1 | 生图张数额度：默认值/scope 口径/配置位置/是否传 scope 给提供方 | T01 | **已定**：四档默认全 -1（不限，0–100 语义同 V1）；scope 由安装/Bot/角色+权限层推导；配置进统一配置注册表（FieldDefinition）；本批只做 V2 端闸门，不传 scope 给提供方 |
| DC-2 | 生图费用限制路径 | T02 | **已定：不做**（费用检测不好做），只按张数限制；T02 销账 |
| DC-3 | 亲密度数值系统/情绪事件复核 | T30 | **搁置标注**（亲密度相关内容先搁置） |
| DC-4 | 群成员风控与复读跟读 | T08、T37 | **已定**：群成员风控改为规则命中，每日反思阶段统一判断处理（T08 重新立项）；复读跟读/打断复读保留（T37 保留） |
| DC-5 | 资料归档整体/简版/移交 | T23 | **搁置标注** |
| DC-6 | 驱力-马斯洛-校准实验 | T43 | **搁置标注** |
| DC-7 | 本机播放/直播字幕 | T47 | **搁置标注** |
| DC-8 | 智能收口/话题抑制 | T11、T07 | **搁置标注** |
| DC-9 | 模型复核类强度/模式 | T04、T05、T06 | **已定**：T04 被动复核、T05 主动终审搁置，倾向删除/重做（不按 V1 设计迁）；T06 智能沉默保留，需先优化设计 |
| DC-10 | 昨日屏幕日记数据来源 | T17 | **已定**：识屏日记与日记功能重复，融合进日记功能即可（识屏材料进入既有日记链，不另建上下文注入） |

## P0 —— 用户已点名 / 程序级，先做

| 编号 | 任务 | 来源（V1） | 方式 | 目标位置 | 参考设计稿 | 验收 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T01 | 生图张数额度四档：private_owner/private_friend/group/proactive 每日张数上限（-1 不限，0=禁止，1–100 上限），本地日重置，持久账本，原生 image 动作派发前准入闸 | `photo_generation_scope.py`、`photo_action_config` | 迁移+改造（scope 由 V2 安装/Bot/角色+权限层推导） | `companion_v2/conversation/media/quota.py` + 配置注册 + 派发链准入 | `V1_V2_NATIVE_CONFIGURATION_MAP_20260925.md`、`CORE_NATIVE_IMAGE_DELIVERY_20260925.md`、V1 `photo_generation_scope.py` | 定向测试：四档边界/跨日重置/重启保持/scope 归类/未授权跳过 | **已完成**（[切片记录](IMAGE_QUOTA_SLICE_20260927.md)，8 项定向测试通过；页面接入待第②阶段） |
| T03 | 框架异常文本外泄拦截：内部身份锚点剥离 + traceback/栈帧转储整体替换为安全文案，被动/群回复与主动成稿两条出站链生效 | `enable_framework_error_leak_guard` | 迁移+改造 | `conversation/text_processing.py`（framework_guard）+ `reply_preparation.py` + `proactive/service.py` | `CORE_REPLY_SEGMENTATION_STREAMING_20260925.md`、V1 `helpers.py`/`event_dispatch.py` | 定向测试：命中/不命中/分段场景 | **已完成**（[切片记录](FRAMEWORK_GUARD_SLICE_20260927.md)，7 项定向测试通过） |

## P1 —— E3 内容风控

| 编号 | 任务 | 来源（V1） | 方式 | 目标位置 | 参考设计稿 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| T06 | 智能沉默（保留，需优化）：主动机会生成后判定"此刻是否开口"；优化方向：置信度门槛+结果影响后续机会权重，避免每机会必调模型 | `enable_smart_silence`、`smart_silence_*` 4 项 | 迁移+优化（先出优化设计再动工） | `proactive/silence.py` | `CORE_AUTOMATIC_CONTACT_AND_HISTORY_SLICE.md` | **已完成首版**（[设计与实施记录](SMART_SILENCE_OPTIMIZATION_20260927.md)；统一配置、单次生成置信度闸门及后续同目的权重反馈；页面接入待第②阶段） |
| T08 | 群成员风控（重新立项）：①规则命中——确定性规则（称呼仿冒、验证码/收款类特征词、高频重复发言、@轰炸）在群入站与 Bot 出站两侧评估，命中写入按群+成员归因的 hit 记录（复用群记忆 owner 归属，不建新成员画像）；②每日反思阶段——每日群记忆反思任务在现有材料外附加当日 hit 记录，由模型输出待审处置建议（标记风险/建议管理者关注/无事项），并复核称呼是否合适；③处置——管理者在既有群记忆管理入口审阅建议并留操作回执 | `group_member_safety_*` 8 项 | 改造（V2 化：规则命中+反思批处理） | `companion_v2/memory/group/hits.py`（规则+记录）+ `memory/group/reflection` 挂钩 + 既有管理入口 | `CORE_MEMORY_REFLECTION_SELECTION_20260924.md`、`CORE_GROUP_MEMORY_20260924.md`、V1 `group_member_safety.py` | **已完成首版**（[切片记录](GROUP_MEMBER_SAFETY_SLICE_20260927.md)；页面与真实现场验收待第②阶段/现场） |
| T09 | 群成图安全审核与私聊回退：provider 产物入 V2 后按配置做模型/规则审核，失败按配置丢弃或降级私聊 | `enable_group_nsfw_private_fallback`、`group_nsfw_image_review_*` 8 项 | 迁移+改造（审核在 V2 端，产物链已有） | `conversation/media/generated.py` 群受众分支 | `CORE_NATIVE_IMAGE_DELIVERY_20260925.md`、`CORE_GROUP_IMAGE_DELIVERY_20260925.md` | **已完成首版**（[切片记录](GROUP_IMAGE_REVIEW_SLICE_20260927.md)；用户批注：私聊回退本批一起做＝选项 B。审核落在 `conversation/media/review.py` + `review_service.py`，私聊回退落在 `conversation/media/fallback.py`；判定/替换/回退写进既有 `runtime_metadata`，不新增表不升 schema；8 项配置 + 2 个视觉档位字段共 11 项 FieldDefinition。新增 18 项定向测试通过。页面与真实现场验收待第②阶段/现场） |
| T10 | 群聊防注入+隐私边界+现实承诺：提示词边界补充 + 出站文本特征拦截 | `enable_group_injection_guard`、`enable_group_privacy_guard`、`enable_group_reality_promise_guard` | 改造 | `conversation/participation_prompts.py` + `text_processing.py` | `CORE_GROUP_CONTEXT_20260924.md`、`CORE_GROUP_PARTICIPATION_20260925.md` | **已完成**（[切片记录](GROUP_SAFETY_GUARDS_SLICE_20260927.md)；三开关进封存快照 + 每日反思称呼复核；页面接入待第②阶段） |

## P2 —— B 段记忆/关系/角色/主动缺口

| 编号 | 任务 | 来源（V1） | 方式 | 目标位置 | 参考设计稿 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| T25 | 群聊片段记忆：按群周期整理"本群最近发生"摘要，进群上下文 | `enable_group_episode_memory` 等 4 项 | 迁移+改造 | `memory/group/episodes.py` | `CORE_GROUP_MEMORY_20260924.md` | **已完成首版**（[切片记录](GROUP_EPISODE_MEMORY_SLICE_20260927.md)：按「整合进既有记忆链」口径并入既有 `memory` 组（`group_episode_memory_enabled`/`group_episode_refresh_minutes`/`group_episode_min_messages`/`max_group_episodes`），群片段作为既有反思群分支的有界材料（`group.episode`），只取已确认送达的回复，免迁移；片段刷新到期判断与 T31 私聊片段另批） |
| T26 | 用户习惯画像+吃什么推荐 | `enable_user_habit_learning` 等 5 项 | 迁移 | `memory/habits.py` + conversation 上下文 | `CORE_MEMORY_IMPLEMENTATION_20260923.md` | **已完成首版**（[切片记录](USER_HABIT_AND_DIALOGUE_EPISODE_SLICE_20260927.md)：一条 `memory_views`（`user.habit.v1`）按安装/Bot/角色/人类主体归属，经既有私聊材料通道进提示词，证据不足不产出；V1 菜名库/打分改为提示词材料；9 字段并入既有 `memory` 组，免迁移） |
| T27 | 世界书/知识库自动导入+群成员识别 | `worldbook_auto_import` 等 12 项 | 补全 | `knowledge/` + `astrbot_host` 装配 | `CORE_NATIVE_GAP_CLOSURE_20260925.md` | **已完成首版**（[切片记录](KNOWLEDGE_IMPORT_SLICE_20260927.md)：版本化目录/导入/失效 + 按安装/Bot/群作用域命中注入（每条带来源）；成员条目只作显示归因线索，不写画像不改权限；14 字段 `knowledge` 组，复用 `memory_views` 免迁移；写入型自登记与跨用户记忆桥未迁移） |
| T29 | 群观察画像族：接梗护栏、名场面、氛围、人格降噪 | `group_observation_config` 7 项 | 改造（轻量：提示参考+记录） | `conversation/group_*` | `CORE_GROUP_PARTICIPATION_20260925.md` | **已完成首版**（[切片记录](GROUP_OBSERVATION_AND_RHYTHM_SLICE_20260927.md)：四类观察按群 owner 归属记入 `runtime_metadata`，仅作有界提示参考；7 项沿用 V1 键名与默认；按成员玩笑画像/名场面引用信号不迁移） |
| T31 | 对话片段记忆（私聊）：按消息数/分钟阈值周期整理片段 | `enable_dialogue_episode_memory` 等 4 项 | 迁移 | `memory/episodes.py` | `CORE_MEMORY_MIXED_RECALL_20260924.md` | **已完成首版**（[切片记录](USER_HABIT_AND_DIALOGUE_EPISODE_SLICE_20260927.md)：与 T25 群片段同构的 `dialogue.episode` 有界材料 + `runtime_metadata` 游标，阈值三态（分钟/消息数/都不满足）与重启不重复整理均有测试；免迁移） |
| T28 | 表达学习配置化：窗口/批次/条目上限/来源范围/应用范围 8 项 FieldDefinition 化 + 群聊作用域 | `expression_*` 14 项 | 补全 | `expression/style_service.py` 等 | `CORE_EXPRESSION_MEMORY_ARCHIVE_20260926.md` | **已完成首版**（[切片记录](HUMANIZED_AND_EXPRESSION_LEARNING_SLICE_20260927.md)：新增 `expression.learning` 组 10 项 FieldDefinition 与跨字段校验；窗口/批次/样本下限/字符上限/每轮条数/字符预算/扫描间隔全部配置化；群聊学习从"完全不运行"改为显式开关 + 按群取样（不再按触发者过滤）；分布问题按用户口径用"用后降权"修复——照抄 v1 `dreaming.py:325/442` 的 `pow(0.72, 天)` 衰减 + 加权无重复抽样，未用过的规则优先，使用次数只降概率不淘汰；抽样在 capture 时定种并写进封存快照保证同轮可复现；审阅视图返回每条规则的注入次数与最近注入时间。真实现场验收与审阅控件上页待后续） |
| T32 | 技能成长配置：自定义技能域接入进展提案提示词；日程约束强度 0–3 档接入规划材料；倍率不注册（V2 无数值经验可乘，见批注） | `skill_growth_*` | 补全 | `role_work/growth/configuration.py` + `growth/progress.py` + `agenda/planning_inputs.py` | `CORE_ROLE_GROWTH_SLICE_20260923.md` | **已完成**（[CONFIG_GAP_BATCH_20260927](CONFIG_GAP_BATCH_20260927.md)），倍率留待批注 |
| T33 | 休息回复闸门+醒后补看：睡眠窗口内概率回复/模型醒来判断/免重判/醒后补看 N 条 | `enable_rest_reply_simulation` 等 8 项 | 迁移（挂共享睡眠执行窗口） | `role_work/life/` + `conversation/` | `CORE_SHARED_ROLE_SLEEP_SCHEDULE_20260924.md`、V1 `user_rest_gate.py` | **已完成首版**（[切片记录](REST_GATE_AND_HUMANIZED_STATE_SLICE_20260927.md)：睡眠窗口内概率判定与免重判、醒后补看有界可追溯；延迟走 `due_at` 持久计时正本（不 sleep）并与繁忙闸门取上界；8 字段并入 `role.life`；V1「不回复」改为有界延后，`llm` 模式暂等价挂起） |
| T34 | 梦境题材候选/混搭/暧昧开关+余韵强度档（auto/轻/标准/明显同 V1），仅对梦境写作生效；暧昧表述保持非露骨边界 | `enable_enhanced_dreams` 等 4 项 | 补全 | `role_work/life/configuration.py` + `journal/prompts.py` + `journal/writing.py` | `CORE_ROLE_JOURNAL_SLICE.md` | **已完成**（[CONFIG_GAP_BATCH_20260927](CONFIG_GAP_BATCH_20260927.md)） |
| T35 | 拟人状态强度注入+每日巡视时刻/保留天数 | `humanized_state_intensity` 等 4 项 | 补全 | `role_work/state/` + `conversation/state_context.py` | `CORE_STATE_MAINTENANCE_EDITING_20260925.md` | **已完成首版**（[切片记录](REST_GATE_AND_HUMANIZED_STATE_SLICE_20260927.md)：强度档位有界注入（0＝不注入，只影响表达不改身份/权限/记忆范围）、每日巡视时刻 + 保留天数清理；4 字段并入既有 `role.state` 组，复用既有状态维护机制，无新表） |
| T36 | 群聊主动插话：间隔/每日上限/反馈学习 | `enable_group_interjection` 等 5 项 | 迁移 | `proactive/` + `conversation/participation` | `CORE_GROUP_PARTICIPATION_20260925.md` | **已完成首版**（[切片记录](GROUP_OBSERVATION_AND_RHYTHM_SLICE_20260927.md)：间隔/日上限/反馈学习账本只认已送达回执，走既有群参与与投递授权链；间隔与上限是提示参考而非硬配额；3 项 V1 字段未迁移并说明理由） |
| T37 | 群复读跟读/打断复读（用户确认保留） | `enable_group_repeat_follow` 等 7 项 | 迁移 | `conversation/group_timing.py`/participation | `CORE_GROUP_PARTICIPATION_20260925.md` | **已完成首版**（[切片记录](GROUP_OBSERVATION_AND_RHYTHM_SLICE_20260927.md)：确定性规则——达阈值跟读、同一波已跟读则按打断概率递增停止；冷却/窗口/文案可配，不绕过群授权与防注入/隐私边界） |
| T38 | 主动节奏增强：爆发式发送、小时活跃曲线、强度预设、收束留白 | `enable_proactive_burst` 等 8 项 | 迁移 | `proactive/scheduling.py` | `CORE_PROACTIVE_CONTACT_SLICE.md` | **已完成首版**（[切片记录](PROACTIVE_RHYTHM_AND_PERSONA_SLICE_20260927.md)：爆发只续 chat 目的且未确认即停轮、槽位错过后不补发；曲线默认关以保持存量节奏；强度档位只能收紧不能放宽额度；10 字段进 `proactive.contact`） |
| T39 | 预约主动执行：到点触发主动消息，预约前静默窗口 | `timer_config` 10 项 | 改造（基于 agenda 提醒扩展） | `agenda/` + `proactive/` | `CORE_AGENDA_SLICE.md` | **已完成首版**（[切片记录](PROACTIVE_RHYTHM_AND_PERSONA_SLICE_20260927.md)：预约=既有 agenda 已接受约定，机会窗口 (due−lead, due+lag]，预约前静默只约束无由头的日常主动；来源/授权/撤回链路未改，超窗即弃不重放） |
| T40 | 早午晚锚点问候+失眠深夜消息 | `enable_daily_greetings` 等 4 项 | 改造 | `proactive/` | `CORE_PLANNING_ACTIVITY_INTEGRATION_20260925.md` | **已完成首版**（[切片记录](PROACTIVE_RHYTHM_AND_PERSONA_SLICE_20260927.md)：锚点按 `quiet_timezone` 本地窗口每日每锚点一次；深夜窗按槽位限额且**不豁免免打扰**（故默认不可达，属有意差异）；11 字段进 `proactive.contact`） |
| T41 | 主动人格判定：生成后模型按人格/世界观判定放行 | `enable_llm_proactive_persona_judge` 等 5 项 | 迁移 | `proactive/` | `CORE_PROACTIVE_CONTACT_SLICE.md` | **已完成首版**（[切片记录](PROACTIVE_RHYTHM_AND_PERSONA_SLICE_20260927.md)：成稿写 `judge_pending` 后由独立后台任务判定，一个事务内二选一（放行排队/改判 skip）；模型档未注册、日限用尽、超时、契约不符、重启无法续做一律不发且记录 `judge.failure`；判定只决定是否发送） |
| T42 | 主动生成上下文：召回条数（0–8）与字符上限（0–8192）接入 compose 快照；模板由既有按对象 note 等价承担；整理模式/原文条数为 V2 设计差异 | `proactive_generation_*` 5 项 | 补全+改造 | `proactive/configuration.py` + `delivery/history.py` + `proactive/service.py` | `CORE_AUTOMATIC_CONTACT_AND_HISTORY_SLICE.md` | **已完成**（[CONFIG_GAP_BATCH_20260927](CONFIG_GAP_BATCH_20260927.md)） |

## P3 —— A 段感知缺口

| 编号 | 任务 | 来源（V1） | 方式 | 目标位置 | 参考设计稿 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| T13 | 撤回消息缓存+转述命令 | `enable_recall_message_cache` 等 6 项 | 迁移 | `conversation/recalls.py` + 管理命令 | `CORE_PLATFORM_RECALL_20260925.md` | **已完成**（撤回事实见 [P3 收口记录](P3_DOMAIN_CLOSEOUT_20260927.md)；转述见[识屏生产链与撤回转述](SCREEN_PERCEPTION_AND_RECALL_PRODUCTION_20260927.md)：`conversation.recall` 组 4 项 + `ConversationRecalls.transcribe` + `RecallManagement` + `GET /reply/recalls`；不另建短期缓存、不复制撤回原图、不做聊天命令，记为设计差异） |
| T14 | 违禁词自动撤回：出站前违禁词命中→撤回/拦截 | `enable_forbidden_word_recall` 等 4 项 | 迁移 | `text_processing.py` 出站闸 | `CORE_REPLY_SEGMENTATION_STREAMING_20260925.md` | **已完成首版**（[切片记录](FORBIDDEN_WORD_OUTBOUND_GUARD_SLICE_20260927.md)；已补显式 Bot 出站身份语义，普通/主动出站复核，未接真实平台撤回） |
| T15 | 自动节气数据源+轻量黄历 | `enable_solar_term_perception` 等 3 项 | 补全 | `conversation/date_context.py` + `agenda/annual_calendar.py` | `PLANNING_WEATHER_SOURCE_20260926.md` | **已完成首版**（[切片记录](SOLAR_TERM_ALMANAC_SLICE_20260927.md)；自动 provider 默认关闭并由宿主端口注入，管理员年度日历优先；页面接入待第②阶段） |
| T16 | 官方预警轮询间隔/天气采样间隔/预警最低级别过滤三项可配（unknown 级别保留不静默丢弃）；高德源仍不接 | `weather_refresh_minutes` 等 4 项 | 补全 | `proactive/configuration.py` + `official_alert_events.py` + `weather_change_events.py` | `OFFICIAL_WEATHER_ALERT_SOURCE_20260926.md` | **已完成**（[CONFIG_GAP_BATCH_20260927](CONFIG_GAP_BATCH_20260927.md)） |
| T17 | 识屏材料融合日记：Screen 捕获/解读作为日记素材进入既有日记链，不另建"昨日屏幕日记"上下文 | `enable_yesterday_screen_diary_context` 2 项 | 改造（用户定：与日记融合） | `role_work/journal/` + `screen/` | `SCREEN_NATIVE_HOST_INTEGRATION_20260926.md`、`CORE_ROLE_JOURNAL_SLICE.md` | **已完成**（生产入口见[识屏生产链与撤回转述](SCREEN_PERCEPTION_AND_RECALL_PRODUCTION_20260927.md)：`screen.interpretation` 任务 + 解读落库 + `screen` 组 3 项；消费端来源连接列名错误已修） |
| T18 | 群图唤醒：群图片命中唤醒权重 | `enable_group_image_wakeup` 等 3 项 | 迁移 | **`conversation/reply_settings.py` + `participation_prompts.py`**（★ 原记 `group_timing.py`，该文件内 `group_wakeup_image` 零命中）；仅作提示词文案，**未做数值加权** | `CORE_GROUP_MEDIA_20260924.md` | **部分落地**（见 [P3 收口记录](P3_DOMAIN_CLOSEOUT_20260927.md)；「唤醒权重」名不副实，实为提示参考） |
| T19 | 上下文图片摘要补全：本轮未见图的旧图摘要补全（有界） | `enable_context_image_captioning` 等 3 项 | 迁移 | `conversation/media/` + `model_gateway/perception.py` | `CORE_NATIVE_IMAGE_DELIVERY_20260925.md` | **已完成首版**（见 [P3 收口记录](P3_DOMAIN_CLOSEOUT_20260927.md)） |
| T20 | 主动识屏调度：晚安识屏/沉默窥屏/每日上限/冷却（能力已建，缺调度） | `enable_screen_glance_action` 等 8 项 | 补全 | `proactive/` + `screen/` | `SCREEN_NATIVE_HOST_INTEGRATION_20260926.md` | **已完成**（[识屏生产链与撤回转述](SCREEN_PERCEPTION_AND_RECALL_PRODUCTION_20260927.md)：8 项 V1 键全部有等价物——既有 3 项 + 晚安/沉默窥屏 5 项；`ScreenPeekService` 经原生日志扩展发起设备采集并交解读链，默认关闭、按授权/日上限/冷却，未知不重放；`CapabilityConfigurationOwner` 接入统一配置面以允许主动锚点） |
| T21 | 主动搜索 web_exploration：兴趣倾向/间隔/结果数 | `enable_web_exploration` 等 **4 项已接入**（原记 13 项，未接入部分见备注） | 迁移 | **`proactive/news_events.py` 的 `kind=="search"` 分支** + `astrbot_host/news.py:102 WebSearchNewsPort`（★ 原记 `proactive/search_events.py`，**该文件全仓不存在**） | `OFFICIAL_WEATHER_ALERT_SOURCE_20260926.md`、`news_sources.py` 模式 | **部分落地**（见 [P3 收口记录](P3_DOMAIN_CLOSEOUT_20260927.md)；自定义搜索接口/空档自主搜索未迁移） |
| T22 | 热点来源+AI 日报 | `enable_news_daily_hot_read` 等 **3 项已接入**（原记 6 项） | 迁移 | `proactive/news_events.py` 的 `kind=="hot"` 分支 + `astrbot_host/news.py:123 HotTrendNewsPort` | 同上 | **部分落地**（见 [P3 收口记录](P3_DOMAIN_CLOSEOUT_20260927.md)） |
| T24 | 外界信息自我关联：资讯事件触发分享欲加权 | `enable_external_event_self_link` 等 **3 项已接入**（原记 4 项） | 迁移 | `proactive/news_events.py` 机会权重（`min(weight, 1.0 + 0.25 * matches)`） | `PROACTIVE_ACTIVITY_EVENTS_20260925.md` | **部分落地**（见 [P3 收口记录](P3_DOMAIN_CLOSEOUT_20260927.md)）；`external_event_self_link_override_*` 三项放宽阈值依赖 V1 分享欲评分，V2 未引入该数值体系，记为设计差异（见[识屏生产链与撤回转述](SCREEN_PERCEPTION_AND_RECALL_PRODUCTION_20260927.md)第五节） |

## P4 —— D 段表达与时机缺口

| 编号 | 任务 | 来源（V1） | 方式 | 目标位置 | 参考设计稿 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| T44 | 场景风格提示词：对话（presentation.style_prompt）/主动（contact.style_prompt）/创作与日记（role.life.diary_style_prompt）三渠道接入；计划由既有 planning_prompt 等价承担；内心无 V2 载体（设计差异） | `persona_*_voice_prompt` 5 项 | 补全+改造 | `text_processing.py` + `proactive/prompts.py` + `journal/writing.py` | `AGENTS.md`（表达优先调提示词） | **已完成**（[CONFIG_GAP_BATCH_20260927](CONFIG_GAP_BATCH_20260927.md)） |
| T45 | 组件顺序策略：@/表情等组件位置补齐 | `segmented_proactive_component_order` 等 3 项 | 补全 | `conversation/reply_settings.py` + onebot 编码 | `CORE_REPLY_SEGMENTATION_STREAMING_20260925.md` | **已完成**（[P4 批次切片](P4_EXPRESSION_AND_TIMING_20260927.md)：`component_order` 空值保持现有行为，新增 `at`/`face` 组件与排序；平台原生 `face` 无生产者、V1 四值位置不迁移，均记为设计差异） |
| T46 | 主动语音行为：主动消息可带语音 | `enable_voice_action` 等 3 项 | 迁移 | `proactive/` + `conversation/voice_reply.py` | `CORE_VOICE_REPLY_ENHANCEMENT_20260925.md` | **已完成**（[主动语音与戳一戳](PROACTIVE_VOICE_AND_POKE_SLICE_20260927.md)：计划封存进 `proactive_contacts`，冷却/额度读既有表，语音不进指纹；V1 本机播放与 pokepro 依赖不迁移） |
| T48 | 表情低延迟模式/向量回填间隔/候选上限 | `reaction_expression_low_latency_mode` 等 4 项 | 补全 | `expression/` | `CORE_EXPRESSION_MEMORY_ARCHIVE_20260926.md` | **已完成**（[表情检索性能与配置](REACTION_PERFORMANCE_AND_CONFIG_20260927.md)：审计 B1+B2+B4；新增 `expression.reaction` 组 9 字段；G3/G6/G14/G15/G16 与 B5 管理面明确不迁移） |
| T49 | 主动戳一戳：主动消息以戳一戳开场（每日上限/冷却） | `enable_poke_action` 等 3 项 | 迁移 | `proactive/` + onebot 编码 | `CORE_GROUP_DELIVERY_20260924.md` | **已完成**（[主动语音与戳一戳](PROACTIVE_VOICE_AND_POKE_SLICE_20260927.md)：日额度与冷却分离、按本地日归零、戳为独立 OneBot 动作且失败不阻塞正文） |
| T50 | 跨群转述与 @ 群友（atrelay）：依赖 T27 | `enable_atrelay_tools` 等 9 项 | 迁移 | `conversation/` + `group_authority` | `CORE_GROUP_FORWARDS_SLICE_20260925.md` | 排后（依赖 T27；跨群目标解析、受众切换与跨群授权均建立在其上） |
| T51 | 引用触发策略：群回复/插话/私聊主动的引用行为 | `enable_quote_group_reply` 等 6 项 | 迁移 | `delivery/` + onebot 编码 | `CORE_GROUP_QUOTE_MEDIA_20260925.md` | **已完成**（[P4 批次切片](P4_EXPRESSION_AND_TIMING_20260927.md)：总开关默认关、按轮次只首条、短回复阈值、可选 @ 触发者；`quoted/auto` 与私聊主动引用因 V2 无可追溯原生消息号不迁移） |
| T52 | 繁忙回复闸门：忙碌时段回复延迟 | `enable_busy_reply_gate` 等 4 项 | 迁移 | `conversation/` 或 `delivery/` | `CORE_HOST_LIFECYCLE_AND_BATCHING_SLICE.md` | **已完成**（[繁忙回复闸门](BUSY_REPLY_GATE_SLICE_20260927.md)：忙碌取 `agenda` 已接受 `role_plan` 窗口，延迟写进 `due_at` 并同步抬升 `deadline_at`；V1 群聊 12 秒硬顶与 superseded 取消不迁移） |

## P5 —— E 段治理缺口

| 编号 | 任务 | 来源（V1） | 方式 | 目标位置 | 参考设计稿 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| T53 | 每日 Token 硬/软限额：安装/角色级每日额度 | `daily_token_limit` 等 3 项 | 迁移 | `model_gateway/budget.py` 日期窗口 | `CORE_MODEL_GATEWAY_SLICE.md` | **已完成**（[切片记录](DAILY_TOKEN_SOFT_LIMIT_SLICE_20260927.md)：硬额度沿用既有按日账户与宿主档位；软额度为 `model.budget` 安装/角色两字段、预留时实时读取，只延后可选后台任务且不产生预留。页面接入待第②阶段） |
| T54 | DeepSeek 高价时段替换：`replacement_rules` 的 time_window（timezone/start/end/weekdays）已完整覆盖该场景，按现有 `model.replacement_rules` 配置即可 | `model_fallback_overrides` | 核实销账 | `model_gateway/replacement_rules.py` | `V1_V2_CONFIG_CALIBRATION_20260926.md` | **已完成**（[CONFIG_GAP_BATCH_20260927](CONFIG_GAP_BATCH_20260927.md)） |

**P5 已收口**：T53、T54 均完成，本段无待办项。

## 可选伴侣对照表

七家能力提供方的状态、设计稿、V1 实现与进度单独成表：[七个可选伴侣：状态 / 设计稿 / V1 实现 / 要求 / 进度](COMPANION_PROVIDER_STATUS_20260927.md)。本页只登记 v1 键级迁移任务，不重复该表内容。

## 搁置区（批注要求暂不处理，保留编号）

| 编号 | 任务 | 搁置原因 |
| --- | --- | --- |
| T04 | 被动回复复核 | 用户批注：搁置，倾向删除/重做（不按 V1 设计迁） |
| T05 | 主动消息终审 | 用户批注：搁置，倾向删除/重做 |
| T07 | 普通回复重复话题抑制 | DC-8 搁置标注 |
| T11 | 智能收口小模型 | DC-8 搁置标注 |
| T17 所属 DC-10 原方案 | 独立"昨日屏幕日记上下文"注入 | 已并入 T17 融合方案，原独立方案废弃 |
| T23 | 资料归档 | DC-5 搁置标注 |
| T30 | 情绪事件复核（亲密度相关） | DC-3 搁置标注 |
| T43 | 驱力-马斯洛-校准实验 | DC-6 搁置标注 |
| T47 | 本机播放+直播字幕 | DC-7 搁置标注 |

## 已销账项（审计确认按设计不迁入/移交/不做，无需任务）

- **T02 生图费用限制**（2026-09-27 用户批注：不做，只按张数限制）。
- 亲密度数值机约 71 项（B2，DC-3 搁置范围内）；`E6 遗留 30 项`；`standalone_webui 5 项`；生图提供方凭据 18 项（image_companion 在位）；创作域 7 项（content_companion 在位）；livingmemory/外部记忆桥 12 项（V2 自有记忆替代）。

## v1 既有资产索引（迁移优先复用）

进度核对曾把"V2 侧未落地"误等同"从零开发"，导致 T25/T28/T31/T35 等标注偏保守。实际 v1 是一个**完整成熟的项目库**（仅 `_worktree_pr215_20260909` 快照就有 200+ 个 py 文件）——情绪、梦境、群观察、议程日历、主动消息引擎、表情资产、关系账本、世界书、习惯画像、Token 预算、跨群 relay、迁移工具链等**全部已有实现**。下面把每个「迁移/改造/补全」类任务对应的 v1 源码列出——**这些任务应以"读 v1 现有实现 → 适配 V2 架构"为优先路径，而非空白重写**：

| V2 任务 | v1 已有等价源码（备份 `_worktree_pr215_20260909/`，亦可看 `../astrbot_plugin_private_companion/`） | 迁移提示 |
| --- | --- | --- |
| T09 群成图安全审核+私聊回退 | `private_image.py`、`private_reading.py`、`group_member_safety.py`、`image_companion_bridge.py` | 私聊回退/群图审核 v1 已有基础，迁移而非从零 |
| T13 撤回消息缓存+转述命令 | `forward_message.py`（转述/relay）、`tool_history_sanitizer.py` | 转述命令 v1 已有；撤回缓存需核对 |
| T18 群图唤醒 | `group_wakeup.py`、`image_companion_bridge.py` | 群图唤醒权重 v1 已有 |
| T19 上下文图片摘要补全 | `private_image.py`、`image_companion_bridge.py` | 图理解/摘要 v1 已有基础 |
| T20 主动识屏调度 | （v1 无对应；属 V2 宿主 `screen/` 能力新建） | V2 宿主原生能力，v1 无等价 |
| T21 主动搜索 web_exploration | `news_exploration.py` | 搜索/探索 v1 已有 |
| T22 热点来源+AI 日报 | `news_exploration.py` | 同上 |
| T24 外界信息自我关联 | `news_exploration.py` | 资讯机会权重 v1 已有 |
| T25 群聊片段记忆 | `daily_review.py`、`memory_companion_adapter.py` | 群周期整理 v1 已有积累 |
| T26 用户习惯画像+吃什么 | `user_memory.py`（含习惯/吃喝，测试 `test_user_habit_quality`） | 用户画像 v1 已有 |
| T27 世界书/知识库+群成员识别 | `worldbook.py`、`astrbot_knowledge.py` | 世界书/知识库 v1 已有 |
| T28 表达学习配置化 | `companion_interaction_expression.py`、`expression_scope_ownership.py`、`domains/affect/`、`reaction_expression.py` | 表达/风格抽取 v1 已有，先读再补 FieldDefinition |
| T29 群观察画像族 | `group_observation.py`、`domains/social/group_mood.py`、`group_moments.py`、`joke_boundary.py`、`roleplay_strength.py`、`group_context_interception.py`、`group_cycle_boundary.py`、`group_prompt_context.py` | 群观察/氛围/名场面 v1 已是子系统 |
| T31 对话片段记忆 | `daily_review.py`、`memory_companion_adapter.py` | 与 T25 同抽象，建议同批 |
| T33 休息回复闸门+醒后补看 | `user_rest_gate.py`、`busy_reply_gate.py`、`passive_state_pipeline.py` | 休息闸门/醒后补看 v1 已有 |
| T35 拟人状态强度+每日巡视 | `domains/affect/`（emotion_event_contract/ledger/targeting、`affect_modulation`、`reply_temperature`、`interaction_dynamics`）、`daily_state.py`、`daily_state_tick.py`、`emotion_diagnostics.py`、`state_views.py` | 情绪/状态/每日状态 v1 已是子系统 |
| T36 群聊主动插话 | `proactive.py`、`proactive_engine.py`、`proactive_message.py`、`proactive_routes.py`、`proactive_chat_runtime_bridge.py` | 主动插话 v1 主动引擎已有 |
| T37 群复读跟读/打断复读 | 群 timing 相关（`forward_message.py`/V2 拟 `conversation/group_timing.py`）；v1 需核对 | 用户确认保留，先读 v1 群 timing |
| T38 主动节奏增强 | `proactive.py`、`proactive_engine.py` | 爆发/活跃曲线 v1 已有 |
| T39 预约主动执行 | `agenda_contracts.py`、`agenda_disclosure.py`、`agenda_runtime.py`、`schedule_authority.py`、`schedule_reconciler.py`、`unified_agenda.py`、`calendar_contracts.py`、`calendar_observer.py` | 议程/日程/预约 v1 已有完整子系统 |
| T40 早午晚锚点问候 | `proactive.py`、`proactive_engine.py`、`daily_state_tick.py` | 锚点问候 v1 已有 |
| T41 主动人格判定 | `proactive.py`（人格/世界观判定） | 主动人格判定 v1 已有 |
| T45 组件顺序策略 | `segmented_message.py`、`conversation_injection_plan.py`、`conversation_prompt_section.py`、`prompt_surface.py` | 组件顺序/分段 v1 已有 |
| T46 主动语音行为 | `tts_enhancement.py`、`tts_tool_sanitizer.py` | 语音增强 v1 已有 |
| T48 表情低延迟模式 | `reaction_expression.py`、`reaction_asset_library.py`、`owned_reaction_asset_catalog.py`、`reference_asset_gate.py`、`reference_assets.py` | 表情资产/低延迟 v1 已有 |
| T49 主动戳一戳 | `proactive.py`（poke 动作） | 戳一戳 v1 已有 |
| T50 跨群转述与@群友 | `atrelay.py` | 跨群 relay v1 已有独立模块（任务名即取自该模块） |
| T51 引用触发策略 | `forward_message.py`、`segmented_message.py` | 引用/转发策略 v1 已有 |
| T52 繁忙回复闸门 | `busy_reply_gate.py` | 繁忙闸门 v1 已有独立模块 |
| T53 每日 Token 限额 | `token_budget.py` | Token 预算 v1 已有 |
| T34 梦境（已完成） | `dreaming.py` | 已作为参考完成迁移 |

**v1 自带迁移工具链**（V2 的 schema 版本化 v40/v41 是等效新实现，迁移思路可参考）：`config_migration.py`、`migration_coordinator.py`、`migration_dual_write.py`、`migration_backfill.py`、`migration_replay.py`、`migration_read_router.py`、`migration_scoped_projection.py`、`migration_source_inspector.py`、`migration_stability.py`、`migration_outbox.py`。

**v1 专有 / 范围待定**（v1 有但 V2 可能不接或需重做，先标注避免误迁移）：`qzone_*`（QQ空间社交馈送）、`desktop_pet_bridge.py`（桌面宠物）、`nai_image_bridge.py`（NovelAI）、`photo_reference_*`（图参考记忆）、`p4_*/p5_*/p6_*`（安全 attestation，V2 自有体系）。

> 迁移口径：V2 为 V1 的**架构重置**（见 v1 `docs/ARCHITECTURE_RESET.md`、`V2_REPLACEMENT_RELEASE_GATE_V0.md`），v1 代码不能直接原样运行，须按 V2 存储（schema 版本化）、归属（domains/role_work）、契约约定重写/适配。但"读 v1 现有实现再适配"明显优于"从空白设计"。上表仅按文件名/子系统语义建立**索引级映射**，动工前务必执行流程约定第 1 条：读参考设计稿 + 对应 V1 模块（逐文件确认函数级可复用点）。

## 流程约定

1. 每个任务动工前：读"参考设计稿"列 + 对应 V1 模块（优先查本页「v1 既有资产索引」）；实现遵守 `REPOSITORY_LAYOUT.md` 归属与依赖方向。
2. 每个任务交付：领域代码 + 实际生效配置（FieldDefinition 或宿主表单）+ `tests/` 定向测试 + `docs/` 切片记录；`BUILD_STATUS.md` 追加条目。
3. 页面接入（第②阶段）不逐任务做；攒批统一接「陪伴小屋」。
4. 涉及模型调用的任务全部默认关闭；涉及发送的任务沿用授权/回执/未知不重放铁律。
5. 所有任务另须对齐上文「V2 框架硬约束清单」13 条，任一条不满足即视为未完成（核对口径见第 11 条）。
