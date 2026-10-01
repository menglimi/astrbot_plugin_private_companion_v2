# V1 本体功能对照与 V2 前置补齐

日期：2026-09-21，实施状态更新至 2026-09-24。范围：V1 主陪伴已经提供的功能，不是 Reality、Together、Screen、Content、Image、Live、Game 的拓展内部实现。本文修正当前推进重点：先查清并补齐核心功能的依赖，再继续 G6 安装管理。

依据为 [V1 逐项功能清单](../../astrbot_plugin_private_companion/docs/evaluations/COMPANION_FEATURE_INVENTORY_20260917.md)、[功能对等要求](../../astrbot_plugin_private_companion/docs/FUNCTIONAL_COVERAGE_AND_PARITY.md)和当前工作区源码。清单中的“现役”“本地新增”“联动”“实验”继续分别标识；存在代码不证明当前实例已开启或已通过 V2 验收。没有读取生产聊天、用户数据或实际配置。

## 1. 对当前进度的修正

G4 的本地回复链、G5 的活动/分享核，只完成了最小领域切片。V1 已有的多人格设置、完整关系/情绪、便签日历、群聊、模型分流、学习管理及用量功能尚不能由这些切片代证。

当前应补的是这些功能需要的稳定数据、公共服务和可验证闭环。复杂页面、具体天气/平台客户端及完整旧数据迁移可在各自接入时完成；不是要求先把 V1 全部算法原样搬来，也不是重新开展一轮总体设计。现有设计继续有效，本文把它们落到 V2 实施依赖。

上轮 [跨能力前置审查](G6_CROSS_CAPABILITY_PREREQUISITES.md)保留为 G6/G7 的配套资料，不再作为本轮用户问题的主线。现有 G6 持久记录和 Screen 切片保留，下一实现切片优先补本体。

实施更新：已完成 [CORE-01 持久身份与配置首批切片](CORE_CONFIGURATION_SLICE.md)、[CORE-04 个人便签/提醒首批本地切片](CORE_AGENDA_SLICE.md)及 [公共对象权限与原角色工具续答本地切片](CORE_OBJECT_ACCESS_AND_ROLE_TOOLS_SLICE.md)。后者已接身份等级、精确共享与原角色结果续答，仍缺管理入口认证、删除意图、正式宿主/后台/投递；以下保留各组完整责任，局部切片不等于整项或迁移全部完成。

随后 [设计符合性检查](DESIGN_CONFORMANCE_AUDIT_20260921.md)补充了不能后置的横向前提：完整 Bot/账号/会话/角色作用域及稳定 owner、公共权限在配置/能力服务的一致采用、最小诊断证据与答疑材料。当前已修复普通对话的同号事件冲突、角色切换和资料受众/时钟检查；CORE-01 与 UI07 仍不能标为完成。以下总体路线保留，第 3 步前先按 ALIGN-01/02/03 补齐上述前置。

最新 [ALIGN-01 人格解析/旧范围映射](ALIGN_PERSONA_RESOLUTION_AND_LEGACY_MAPPING_SLICE.md)已将多 Bot 路由、运行快照、角色优先级及有证据的旧范围映射接入现有消费者；[ALIGN-02 公共管理权限](ALIGN_COMMON_MANAGEMENT_ACCESS_SLICE.md)已统一配置、能力和对象的安装身份语义；[ALIGN-03 诊断与修改建议](ALIGN_DIAGNOSTICS_AND_REPAIR_SLICE.md)已接入实际本地证据、原角色续答和持久建议确认/取消。第 3 步的任务、模型、消息及内外部工具链已接入[统一宿主](CORE_HOST_LIFECYCLE_AND_BATCHING_SLICE.md)，[AstrBot 试运行](CORE_ASTRBOT_STAGING_HOST_SLICE.md)已有一次单目标真实发送 ACK。当前进入第 4 步，[活动切片](CORE_ROLE_LIFE_PERSISTENCE_SLICE.md)已完成活动/产物持久化和暂停/恢复，[日记/梦境切片](CORE_ROLE_JOURNAL_SLICE.md)已完成日期归档、修订/删除、来源与衍生依赖读取，并在[历史审查后接入原角色写作 worker](CORE_JOURNAL_WRITING_REVIEW_20260923.md)及角色活动台账素材适配器；消息/作品/阅读素材分类、每日/睡眠调度和关系记忆仍待补，局部证据不构成多 Bot 全功能或替换发行验收。

## 2. 必须提前接好的八组本体功能

下表的“先补”表示现在实现公共记录和最小闭环；真实平台及全部效果仍按 G8-G10 取证。编号引用旧清单，功能是否保留与 V2 实现程度分开记录。

| 编号 / V1 功能 | 当前 V2 差距 | 现在先补什么 | 旧实现依据 |
| --- | --- | --- | --- |
| CORE-01 多人格、用户/群绑定和配置继承。ID01-ID10、UI06、OPS02-OPS04 | 已有持久账号/授权/窗口角色绑定、三级配置继承、差异提交及采用回执；完整 Actor、个人/关系层级、宿主入口、全量字段和定义升级仍缺。 | 先用已完成的 [首批切片](CORE_CONFIGURATION_SLICE.md)支撑便签/提醒，其余类型、字段和真实消费者随接入补齐；持续按 [配置专项](CONFIGURATION_CONSISTENCY_AND_PANEL_PERFORMANCE.md)保存来源、显式值和旧映射。权限与关系分别迁移；旧资料不由当前人格认领。 | [persona_config.py](../../astrbot_plugin_private_companion/persona_config.py)：`resolve_persona_setting`；[persona_sqlite_store.py](../../astrbot_plugin_private_companion/persona_sqlite_store.py)；[unified_person_registry.py](../../astrbot_plugin_private_companion/unified_person_registry.py)。 |
| CORE-02 日常对话、媒体理解、撤回和真实历史。CHAT01-CHAT10、OUTPUT01/05、OPS05/07 | [消息切片](CORE_CONVERSATION_MESSAGES_SLICE.md)、[工具续答](CORE_ROLE_TOOL_LOOP_SLICE.md)和[统一宿主](CORE_HOST_LIFECYCLE_AND_BATCHING_SLICE.md)已接自动合并/撤回、异步生成、工具循环、逐段回执与确认发送历史；已有单目标纯文本 ACK。[静态图片](CORE_PRIVATE_IMAGES_SLICE_20260924.md)已接原图、来源、工具续答及记忆引用的本地完整链；GIF/多帧、合并转发、群路由及图片真实视觉/平台验收仍缺。 | 继续接动态媒体覆盖、转发原消息/原作者引用与更多投递场景；静态图片不把发送者推定为拍摄者、作者或画中人。只把已确认送出的正文/附件记作已说。当前按整批依赖停用未发内容，语义片段修订、撤回回看及跨领域遗忘/删除仍分别治理。 | [event_dispatch.py](../../astrbot_plugin_private_companion/event_dispatch.py)、[conversation_injection_plan.py](../../astrbot_plugin_private_companion/conversation_injection_plan.py)、[private_image.py](../../astrbot_plugin_private_companion/private_image.py)、[forward_message.py](../../astrbot_plugin_private_companion/forward_message.py)、[final_response_persistence.py](../../astrbot_plugin_private_companion/final_response_persistence.py)。 |
| CORE-03 关系、情绪、画像、记忆修订与表达学习。REL01-REL10、MEM03/04/06/08/09 | 关系背景/情绪事件的版本正本、审阅采用、修订撤回及私聊消费已接通；内置 Memory 已接事实/经历、反思、默认事实增量检索、角色工具和公共查询/提交/查账。完整关系配置、表达学习、跨领域遗忘及群记忆仍缺。 | 按角色和真实对象保存关系背景、情绪事件及主观解释；事实/偏好、情绪、表达规则分开。保留查看、修订、审核、采用、撤回及作用域；纠正传播到后续召回、摘要和提示。Memory 已作为内置领域服务落地；跨拓展消费者沿标准读取、提议和查账入口接入。 | [relationship_account_store.py](../../astrbot_plugin_private_companion/relationship_account_store.py)、[user_memory.py](../../astrbot_plugin_private_companion/user_memory.py)、[expression_scope_ownership.py](../../astrbot_plugin_private_companion/expression_scope_ownership.py)、[memory_revision_adapter.py](../../astrbot_plugin_private_companion/memory_revision_adapter.py)。 |
| CORE-04 日程、统一日历、约定、便签、重复待办与提醒。TIME01-TIME07 | 已有持久便签、固定重复期次、本地提醒准备、身份等级/对象共享及原角色工具适配，见 [后续切片](CORE_OBJECT_ACCESS_AND_ROLE_TOOLS_SLICE.md)；后台扫描和公共投递已接统一宿主；[日历与状态切片](CORE_STATE_CALENDAR_AND_QQ_PRESENCE_20260924.md)已接版本化事件、明确约定、期次例外、角色工具与管理 API，完整页面和提醒现场验收仍待补。 | 在日历事件、明确约定、期次例外和原提醒链基础上接管理页面与现场验收；分清 Bot 计划、用户自述候选、已接受约定和实际经历，保存/宿主排程/提醒到达分别出结果。 | [unified_agenda.py](../../astrbot_plugin_private_companion/unified_agenda.py)、[agenda_runtime.py](../../astrbot_plugin_private_companion/agenda_runtime.py)、[memo_notes.py](../../astrbot_plugin_private_companion/memo_notes.py)、[planning.py](../../astrbot_plugin_private_companion/planning.py)。 |
| CORE-05 连续生活、睡眠/忙碌、身体状态、日记、梦境、技能和目标。STATE04-STATE08、TIME08/09、MEM01/02/05/10、LIFE01-03/10 | [活动、日记/梦境、阅读素材及每日/睡眠触发](CORE_ROLE_LIFE_END_TO_END_20260923.md)已接入统一宿主；角色成长另有[v22 技能/长期目标正本](CORE_ROLE_GROWTH_SLICE_20260923.md)，保存私聊来源引用、显式确认、修订历史和幂等回执。后续[成长授权读取与管理 API](CORE_ROLE_GROWTH_CONTEXT_SLICE_20260924.md)已接普通私聊原版本消费、当前来源受众复核及独立管理操作者；后续[角色工具与授权设置](CORE_ROLE_GROWTH_TOOLS_AND_ACCESS_20260924.md)已接查询、待确认提案和 STANDARD 精确授权；[活动历史与自我时间线](CORE_ROLE_TIMELINE_SLICE_20260924.md)已完成版本存储和受授权查询；[角色状态维护与 QQ 展示](CORE_STATE_CALENDAR_AND_QQ_PRESENCE_20260924.md)已接饥饿、健康、睡眠、忙碌等模拟状态、周期维护、普通回复、日程短状态与整轮输入提示；[生理期连续周期](CORE_ROLE_CYCLE_20260924.md)随后补齐三阶段/六阶段、持久锚点、显式定位与原人格拟人表达。管理 UI、跨窗口统一状态及完整 V1 对等仍待补。 | 管理页面与来源选择器由另一窗口接续；读取/提案权限设置和角色提案工具已落地。非页面主线已补齐活动版本轨迹及自我时间线；日历/约定及身体状态领域已完成本地切片；后续进行页面、真实客户端与跨窗口验收。成长不能按时间、日记措辞或计划自动增加；技能保持描述性进展，长期目标须由显式确认和修订推进。跨窗口 owner 不构成读取许可。 | [daily_state.py](../../astrbot_plugin_private_companion/daily_state.py)、[chronotype.py](../../astrbot_plugin_private_companion/chronotype.py)、[busy_reply_gate.py](../../astrbot_plugin_private_companion/busy_reply_gate.py)、[dreaming.py](../../astrbot_plugin_private_companion/dreaming.py)、[self_timeline.py](../../astrbot_plugin_private_companion/self_timeline.py)、[daily_review.py](../../astrbot_plugin_private_companion/daily_review.py)。 |
| CORE-06 主动的个人偏好、暂停、额度、未回应和接续。ACTIVE01-ACTIVE10、LIFE07-LIFE09 | [主动联系切片](CORE_PROACTIVE_CONTACT_SLICE.md)已接四层偏好、13 类目的、临时暂停/免打扰、独立后台生成和共用投递；[后续切片](CORE_AUTOMATIC_CONTACT_AND_HISTORY_SLICE.md)已接私聊空闲机会、窗口额度、关系级跨窗口额度、未回应背景和联系/提醒的已发历史投影。更多领域机会及线上验收仍缺。 | 安装/角色/关系/窗口的逐项偏好、13 类目的、临时暂停到期恢复、明确免打扰、已接受事项和历史联系结果；持续工作与是否联系分开。权重只用于多个可行念头竞争；未回应是背景/可诊断状态，不直接编成用户行为。 | [companion/proactive_preferences.py](../../astrbot_plugin_private_companion/proactive_preferences.py)、[life_control_api.py](../../astrbot_plugin_private_companion/life_control_api.py)、[proactive.py](../../astrbot_plugin_private_companion/proactive.py)、[proactive_engine.py](../../astrbot_plugin_private_companion/proactive_engine.py)。 |
| CORE-07 群聊观察、参与、黑话/名场面和跨窗口转述。GROUP01-GROUP14、RELAY01-RELAY05 | 有 GROUP scope 和通用受众检查，不等于已经具备群观察、唤醒接续、群材料学习及转述业务。 | 群观察和回复独立开关；原发言者、群材料、话题范围及撤回关联；同角色的公共生活与各群/个人资料裁剪；明确委托、各目标回执和等待某人出现的未决转述。先用私聊/两个群/多个 Bot 的隔离样例定范围，再接真实群路由。 | [group_observation.py](../../astrbot_plugin_private_companion/group_observation.py)、[group_wakeup.py](../../astrbot_plugin_private_companion/group_wakeup.py)、[worldbook.py](../../astrbot_plugin_private_companion/worldbook.py)、[atrelay.py](../../astrbot_plugin_private_companion/atrelay.py)。 |
| CORE-08 任务模型、提示词、用量、超时与后台维护。MODEL01-MODEL07、UI05、OPS07-OPS10 | [任务切片](CORE_TASK_SUPERVISOR_SLICE.md)和[模型切片](CORE_MODEL_GATEWAY_SLICE.md)已接持久任务/attempt、前后台名额、取消/超时/恢复、任务路由/提示词采用和分层预算；内外部工具多轮链、统一宿主及受控真实模型已有证据。软预算/额度页面、选模兼容、完整领域后台调度、正式生产宿主及归档仍缺。 | 继续接领域后台任务，落实关系/用户规则选模、拒答后换模及余额关注；保留配置来源和真实用量依据。前台回复与后台状态/学习/复盘分开调度；补提供方速率治理与真实消费者，逐阶段诊断，不固定串行所有维护模型或重算全量配置。 | [model_routing.py](../../astrbot_plugin_private_companion/model_routing.py)、[task_prompt_registry.py](../../astrbot_plugin_private_companion/task_prompt_registry.py)、[token_budget.py](../../astrbot_plugin_private_companion/token_budget.py)、[reply_performance.py](../../astrbot_plugin_private_companion/reply_performance.py)、[plugin_bootstrap.py](../../astrbot_plugin_private_companion/plugin_bootstrap.py)。 |

### 2.1 会直接导致返工的具体例子

- V1 的 `resolve_persona_setting()` 已按“字段是否存在”继承。若 V2 只保存最终值，用户清空提示词、关闭功能以及恢复继承将无法区分；以后配置迁移和页面都会重做。
- V1 的 `memo_notes.py` 已有日、周、月、年重复、月日锚点、提醒开关、完成次数和上次提醒记录。V2 不能只做一个“到时间发消息”的定时器；同一次完成操作重试只能推进一次，闰日/月末沿明确规则处理。
- V1 的 `ProactivePreferences` 已有逐字段继承、来源、临时覆盖和到期恢复。不能把它们折叠成每个拓展一个开关和权重；用户暂停主动也不等于停止角色自己的生活。
- V1 已把实际发出内容与模型草稿分开记录。V2 接真实模型和分段前就要确定历史归档责任，否则“只发了一半却记成整段已说”的问题会再次出现。
- V1 存在整数百分比与小数概率并用、按数值猜单位的代码路径；保存回显与运行采用也不是同一事实。V2 的字段/单位、提交/应用状态和大型配置页加载协议须在 CORE-01 确定，详见 [配置一致性与管理页性能](CONFIGURATION_CONSISTENCY_AND_PANEL_PERFORMANCE.md)。

这些都是现有用户能力的兼容要求，不是为了 V2 新增的流程。语义选择优先交给原模型与材料/提示词；旧关系分数、忙碌阈值、周期档位和词表不自动成为新权威，用户明确偏好、历史依据和技术限制则继续保留。

## 3. 可以稍后适配，但不能漏掉

这些功能不要求抢在上述基础前实现完整客户端或页面。先登记归属和旧数据映射，接入时仍需对等验收；“稍后”不等于可从直接替换发行中静默删掉。

| V1 本体功能 | 可后置的工作 | 现在保留的前提 |
| --- | --- | --- |
| 日期、农历、节气、天气、城市绑定和预警，STATE01-03 | 历法算法与天气客户端适配、展示。 | 时间/时区、城市归属、样本新鲜度、预警取消/过期及原联系记录；角色地点与用户真实地点分开。 |
| 菜谱、饮食偏好、技能和长期目标细节，STATE09、TIME08/09 | 菜单页、技能/目标编辑和建议体验。 | 偏好来源归记忆，角色成长按实际活动依据推进；已有进度和明确选择保留。 |
| 衣柜、穿搭、参考图库、图片额度与审核，IMAGE03-09 | V1 主插件承担的管理、素材选择与参数适配；不重做外部生图后端。 | 角色物品/当前穿搭、原图版本和用途、人工换装优先关系、资源保留、审核/额度设置有明确 owner。 |
| 表情素材管理与检索，IMAGE10/11 | 导入、标签、检索、重扫及自动选用体验。 | 素材及描述的来源、范围、版本与删除；未实际发送的表情不能进入已发表达。 |
| TTS、多语种、分段、戳一戳和在线状态，OUTPUT01-08 | 宿主/平台执行和 UI，逐步接入 G8 输出。 | 原语义与语音文本映射、分段结构、文字/语音/附件顺序、逐目标回执、明确取消及参数继承。分段体验保留，不把所有等待都归咎于分段。 |
| 新闻、AI 日报、主动搜索与外界见闻，SOURCE01-05 | 已有主插件客户端和来源适配；外部视频联动只保留交接责任。 | 发布/获取时间、已读范围和可追问原文；获取和联系分开，不因权重改变刷新速度。 |
| 综合管理、独立 WebUI、资料柜、聊天答疑/调参、备份导入，UI01/03-08、OPS02-04/07 | 完整页面、登录适配、领域编辑器及导入导出体验；小屋外观另沿 G6。 | 页面、命令、工具共用业务服务；配置字段注册、来源/生效状态、按组读取和差异保存先确定。首个设置页验证 700/1500 字段规模、草稿及角色切换，不等全量表单完成再优化；批注/标签及治理保留真实记录。 |
| QQ 空间读写/评论/排程，QZONE01-05 | 沿原路线暂缓平台适配，当前不抢占核心工作。 | 这是 V1 已有本体功能，不因涉及外部平台就从本次盘点排除。既有“暂缓”不证明替换兼容；声明直接替换前必须提供适用兼容路径或有明确产品范围处理，不能仅记 held 就算功能通过。 |

MODEL02 的按关系选模型、MODEL03/04 的用户规则换模/拒答后换模、MODEL07 的余额关注，以及 OUTPUT08 的平台状态同步，旧清单已有产品/迁移细节缺口。现在登记其显式配置与历史来源，在对应服务接入前确定可兼容行为、预算及外部动作边界；不擅自删除用户规则，也不照搬默认串行复核来增加回复延迟。本轮模型网关仅在明确未处理请求且有零用量回执时启用技术备用，该规则不替代这些产品能力。

UI07 的完整页面/命令适配可以随宿主接入，最小诊断服务已按 [ALIGN-03](ALIGN_DIAGNOSTICS_AND_REPAIR_SLICE.md)完成本地切片：explain/self_check/incident/repair_proposal、实际检查证据、unknown、范围/时效/脱敏，以及确认/取消建议对接公共配置服务。“查看主动判定”只是其中一个检查；任务排队/执行、本地模型配置/用量和消息分段回执已接，真实 provider/sender、外部检查注册与 L3 执行随后续服务补齐。

HDSI、旧驱力实验、人格问卷/自动校准和 P4/P5/P6 继续按实验/迁移工具处理，不与稳定本体功能混报。已有退役项保持原退役依据，不因“兼容”重新开放。

## 4. 存储和迁移需要现在展开

[V2 旧数据目录](../companion_v2/legacy/catalog.py)中的 `private.core_profiles`、`private.host_configuration` 是来源概述，不是逐功能转换器；[surface 台账](../companion_v2/legacy/surface_ledger.py)也未覆盖完整本体操作。现有 [目录测试](../tests/test_legacy_catalog.py)检查结构、条目数量下限和分类合法性，不能据此声称全部功能对等。

当前 [V1 core_store.py](../../astrbot_plugin_private_companion/core_store.py) 已显式登记 `users/groups`、日程/日历、便签、日记及删除日期、梦境、穿搭、技能、用量、主动、表达学习、关系资料和转述记录等持久区。V2 新增各领域时应逐项记录旧源字段、真实 owner、目标记录、版本/删除含义、配置来源、未知/缺失的保留办法及对应入口；不能把整份 JSON 塞进一个 V2 字段就称为完成迁移。

先使用合成非空夹具验证：多角色/多用户、多群、显式关闭和继承、循环待办、取消事项、已删日记、被纠正记忆、未决转述及已发送部分。生产自动探测、最终快照、旧 writer/sender 停止和实际切换仍在 G9/G10；本轮不读取或迁移真实数据。

## 5. 下一实现顺序

1. **本体配置与可信角色范围。** 先做 CORE-01，建立持久身份/角色绑定、字段注册与单位、配置 owner/继承解析、差异提交和实际采用回执；同步展开核心资料和旧入口/旧单位映射。按 [CFG-01/02/03](CONFIGURATION_CONSISTENCY_AND_PANEL_PERFORMANCE.md)先验证本体及 G6 样例，这是关系、日程、偏好、模型及页面共同依赖。
2. **便签与提醒的完整本地闭环。** 在第 1 步基础上实现 CORE-04 的便签和提醒子集，贯通操作权限、保存、版本、重复期次、改期/取消、后台恢复及本地回执；暂不发真实消息。该场景已有 [便签与提醒操作目录](../../astrbot_plugin_private_companion/docs/OPERATION_ACCESS_CATALOG_V0.md)，不需要重定产品方向。
3. **模型与消息公共链。** 接 CORE-08 和 CORE-02 的任务路由、提示词/预算、输入/取消与已发历史接口，先隔离验证，再接受控模型；前台不等待无关状态刷新、表达学习或日终复盘。
4. **关系记忆与连续生活。** 接 CORE-03/05 及 Calendar 其余内容，把事实、主观关系、角色活动、日记/梦境、成长和开放事项存实，并验证修订、删除与重启。
5. **主动偏好与群聊。** 接 CORE-06/07，共用前述记录完成有据主动、免打扰、临时暂停、群参与及转述；完善核心管理投影。已承诺提醒沿原预约办理，普通主动权重不吞掉提醒职责。
6. **继续 G6 及后续路线。** 核心服务具备上述最小证据后继续拓展管理和 Screen；领域接入仍按 G7，真实输出按 G8，自动迁移与替换发行按 G9/G10。外围本体功能在其依赖就绪后逐项适配，不用等待全部拓展先完成。

本次调整是补足 G1/G2/G4/G5 的实施深度。第 1 步的持久身份/三级配置、第 2 步的便签/提醒本地子集及公共对象权限/原角色工具适配已落代码，范围分别见 [配置记录](CORE_CONFIGURATION_SLICE.md)、[便签/提醒记录](CORE_AGENDA_SLICE.md)和 [后续权限与工具记录](CORE_OBJECT_ACCESS_AND_ROLE_TOOLS_SLICE.md)。ALIGN-01/02/03 已完成对应前置的首批本地闭环；第 3 步的任务、模型、消息、内外部工具及统一宿主已贯通，另有单目标真实 ACK。当前第 4 步已完成[活动持久化](CORE_ROLE_LIFE_PERSISTENCE_SLICE.md)、[日记/梦境日期、版本与删除记录](CORE_ROLE_JOURNAL_SLICE.md)、原角色写作及角色活动台账素材适配。消息/作品/阅读素材、每日/睡眠触发、关系与记忆、成长工具及自我时间线已由后续切片接入。下一段优先完整 Calendar/约定和身体状态；跨域受众投影、表达学习、全量字段、完整 UI 和正式入口仍按相应关卡补齐。当前证据与缺口见[进度核对](FRAMEWORK_PROGRESS_AUDIT_20260924.md)，不随局部完成提升验收等级。

配置服务就绪后先做 CFG-04 的小型管理页纵向样例，验证按需加载、草稿及 700/1500 字段预算，再逐领域铺开。本体设置和拓展设置共用这一基础；概率的显示/存储单位与旧数据转换不能交给每个页面自行猜测。

## 6. 对应验收场景

下列保留完整验收目标；局部证据见 [CORE-01 切片](CORE_CONFIGURATION_SLICE.md)、[CORE-04 首批切片](CORE_AGENDA_SLICE.md)和 [对象权限与工具切片](CORE_OBJECT_ACCESS_AND_ROLE_TOOLS_SLICE.md)，不代表包含完整管理入口、宿主或平台的整项已通过。其余测试随相关切片执行，不要求每次改动重跑全框架。

CORE-C07 的活动暂停、宿主重开和显式恢复已有[活动证据](CORE_ROLE_LIFE_PERSISTENCE_SLICE.md)；日记日期/版本、删除防补写、梦境主观类型及旧材料失效已有[日记/梦境证据](CORE_ROLE_JOURNAL_SLICE.md)。[技能/目标正本](CORE_ROLE_GROWTH_SLICE_20260923.md)及[授权读取与管理 API](CORE_ROLE_GROWTH_CONTEXT_SLICE_20260924.md)已支持显式提案、确认、修订、当前来源复核和重启后的原版本消费；角色提案工具、独立授权设置、活动历史与自我时间线已经补齐，见[成长工具](CORE_ROLE_GROWTH_TOOLS_AND_ACCESS_20260924.md)及[时间线切片](CORE_ROLE_TIMELINE_SLICE_20260924.md)；成长管理 UI 和来源选择器由另一窗口推进，局部证据不代表整体替换验收完成。

| 编号 | 最小应证明的行为 |
| --- | --- |
| CORE-C01 | 两角色分别设置昵称、模型和主动偏好；私聊/群聊换绑后不串资料，显式关闭/空值与继承在重启后仍不同。 |
| CORE-C02 | 创建便签不设置提醒；另建独立提醒不强制造便签；保存、宿主排程、本地或实际投递的结果分别解释。 |
| CORE-C03 | 月末/闰年重复事项，完成重试只推进一次；改期/取消与旧期次并发、重启后旧触发不重复办理；不把计划记成经历。 |
| CORE-C04 | 连续消息合并后撤回其中一条，只修订受影响上下文/待发部分；图片与转发保留原作者，实际只发两段时不归档未发第三段。 |
| CORE-C05 | 用户纠正、撤回或忘记请求使相关画像、学习规则、日记引用和待发材料失效；不借旧缓存、旧日记或迟到后台结果复活。 |
| CORE-C06 | 情绪事件保留实际对象；某群争执不被写成另一用户冒犯；管理身份不自动变亲密，用户偏好不被角色台词自证。 |
| CORE-C07 | 活动暂停后重启接续，日记按实际日期和版本归档；已删日期不自动补写，梦境明确属于角色主观材料，技能/目标不凭未来日程增长。 |
| CORE-C08 | 13 类联系偏好逐项继承、个人覆盖与临时暂停可恢复；暂停联系仍可保留角色活动；调整权重不改变准入、预算、抓取或真实回执。 |
| CORE-C09 | 群观察开、回复关仍可按授权观察；群 A 材料不进入群 B；转述到两个目标部分成功时只记各自结果，等待某人出现的任务不因同名用户触发。 |
| CORE-C10 | 日记/学习后台任务不堵住普通被动首句；任务提示词覆盖有来源；预算软硬限额、超时/备用模型和未知用量沿原任务记账，阶段延迟可定位。 |
| CORE-C11 | 页面/工具对同一便签、记忆或配置的操作有一致权限和版本；删除、重置、导入的范围可核对；诊断清楚区分未执行、失败与未知。 |
| CORE-C12 | 合成旧资料逐功能映射可查，旧显式值/墓碑/未决动作不被默认值覆盖；天气、表情、语音、平台状态及 QQ 空间有具体后续去向。 |

配置专项另列 CFG-C01 至 CFG-C14，覆盖保存/采用、单位、旧数据、并发、范围及页面规模。已有本地子场景证据见首批切片记录，完整条目仍待逐项验收；不与已有测试数量混算。

CORE-C04 已有合并、撤回墓碑、取消未发部分、保留分段间隔及仅归档确认发送的本地证据，另有单目标真实发送 ACK；静态图片已保留原消息、发送者、组件位置和原件，未知作者/拍摄时间不推定，并验证工具续答、撤权及记忆引用。当前依赖粒度是整批，动态媒体、转发原作者、语义片段修订和完整平台场景仍缺。CORE-C05 的跨领域纠正/遗忘不能由此代证，CORE-C10 的真实首句延迟也未测量。

本文初次交付为本体源码/设计对照和推进顺序修订，后续实现与测试另记对应切片。真实宿主、模型及平台的有限试运行证据见 [AstrBot 宿主记录](CORE_ASTRBOT_STAGING_HOST_SLICE.md)；仍无生产迁移或完整替换发行证据。
