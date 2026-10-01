# V2 整合前的实施记录

以下保留各批次原始状态；当前发行范围以 RELEASE_V2_0.md 为准。历史中的“下一步”可能已由后续批次完成。

# Companion V2

已接入 [QQ 展示设置与日程公开文案编辑](CORE_QQ_PRESENTATION_EDITING_20260925.md)：角色状态页支持输入提示开关、刷新间隔、自定义短状态开关及已有角色计划的公开文案。并发修改保留草稿，丢回执沿原请求显式核对，角色切换固定原保存目标；修改文案保留原来源、例外和提醒。36 项定向测试均有通过记录，桌面及 390px/320px 浏览器验收通过。下一步接入饥饿、健康、生理期等状态维护参数与人工校准；真实 QQ 连续提示效果仍待现场验证。

已接入[群 Reply 音视频与合并转发原件](CORE_GROUP_QUOTE_MEDIA_20260925.md)：原群定向读取、原成员来源关联、三层归因、工具续答、撤回/撤权和重启复核共用已有领域服务；后续历史只保留附件元数据。群聊与私聊复用内容冻结器，目录和旧引用格式保持兼容。168 项定向测试及 120 个子用例按 ID 去重后均有通过记录，真实 SDK / 本地 ACK 入口通过，测试等待调整经过详见落地记录。下一步推进群聊图片出站的原群受众与逐段回执合同。

已完成[核心 Demo 的真实 SDK 宿主验收](CORE_DEMO_HOST_ACCEPTANCE_20260925.md)：实际插件入口、宿主管理页、HTTP 路由和 SQLite 贯通，单目标/多目标在独立进程中验证初始化、启动、预览、停止与恢复。修复真实查询参数对象兼容及重启预览权限问题，保留 Bot/角色/来源隔离和旧实例失效。85 项定向测试、30 项浏览器与宿主检查通过；无需用户控制台，模型与平台均使用本地替身。下一步整理可安装 Demo 包并验证全新安装流程。

已接入[群合并转发节点的语音、视频和采样帧](CORE_GROUP_FORWARD_MEDIA_20260925.md)：原群、当前转发者、节点显示身份和媒体来源分别保留；当前回合提供语音及最多四张视频帧，后续群历史只呈现元数据。共享预算、工具续答、撤回/撤权和跨重启复核已覆盖，157 项定向测试与 52 个 subtest 最终均有通过记录，独立真实 SDK / 本地 ACK 入口通过。无数据库迁移、真实模型/QQ 调用或 V1 数据访问。该原消息合同已由[群 Reply 扩展](CORE_GROUP_QUOTE_MEDIA_20260925.md)接通。

已接入[宿主管理页](CORE_HOST_MANAGEMENT_PAGE_20260924.md)：从普通 AstrBot Dashboard Page 读取单/多目标状态，显式执行只读探测，并确认初始化、启动与停止；默认预览、OneBot 授权和错误状态均有清晰提示。7 个无头浏览器场景、宿主及页面目录回归通过，当前仍需已登录 Dashboard 的真实账号完成现场探测。

已完成[同一角色共享自动睡眠排程](CORE_SHARED_ROLE_SLEEP_SCHEDULE_20260924.md)：自动睡眠开关、时间、时区和时长由同一 installation / Bot / role 共享；首次写入一次性接管窗口旧值，唯一有效窗口按稳定 context key 执行，管理页展示实际执行窗口和下一次入睡/计划唤醒。旧 configuration owner 回执可兼容重放；生活页桌面、390px/320px、幂等、撤权和焦点场景通过，生活排程定向 5 项通过。无 schema 迁移、在线重载、真实模型/QQ 调用或 V1 数据访问。下一步把共享作息接入角色状态维护页，统一展示饥饿、健康、睡眠和生理期阶段，并继续做真实 QQ 状态现场验收。

已完成[角色状态总览与共享作息展示](CORE_ROLE_STATE_PAGE_20260925.md)，并补齐 [QQ 展示诊断与原请求追踪](CORE_QQ_PRESENTATION_DIAGNOSTICS_20260925.md)：同页显示开关、授权、刷新间隔、原会话回复状态、公开文案、日程/账号争用原因及带原时间和标识的回执。重启读取短状态记录不重发、不刷新原时间；输入提示按原会话续持，避免其他窗口忙碌时误续。该诊断批次 35 项定向测试及 V2 页面桌面、390px/320px 浏览器验收通过；后续编辑能力见本文件最新记录。4 秒默认间隔只降低请求频率，真实 QQ 闪烁效果仍待实测。


已接入[体素小屋拓展页的记忆工作区](CORE_VOXEL_HOME_MEMORY_PAGE_20260924.md)：沿用现有小屋首页、导航和记忆入口，按授权目标/角色读取事实、整理进度并显式继续或修复；丢回执使用原操作核对。页面源码共用 Content 的整合预览，通过 `tools/sync_framework_page.py` 发布至本插件 `pages/陪伴小屋/`。41 项定向测试与 17 个无头浏览器场景通过；新增路由随 V2 下次正常加载生效，其他页面区域仍为预览。下一步接事实更正、置顶、修订历史与遗忘确认。

已完成[后台生活任务排队与排程公平性](CORE_BACKGROUND_FAIRNESS_20260924.md)：阅读、日记/梦境和角色状态维护共享等待队列，暂时满额时保留原输入、回执和截止时间；符合条件的较早任务先执行，持续阅读不再抢在已等待的日记/状态维护之前。状态排程分批续扫，旧人格记录不再挡住后续目标。新增 15 项；199 项定向回归首轮 198 项通过，修正测试夹具后队列专项 9/9 项通过，范围内每项均有通过记录；真实 SDK 入口启停通过。下一步统一同一角色跨窗口的身体状态与作息时钟。

多目标宿主已接入[阅读、睡眠、日记与梦境管理](CORE_MULTI_TARGET_LIFE_20260924.md)：每个私人 target/role 提供固定 `life_api`，当前原生人格独立绑定生活执行器和日记排程；切换后旧任务退出，重启保留记录与回执，未知模型结果不重放。新增 9 项，最终 156 项定向回归及真实 SDK 入口启停通过。页面可从 `/host/status` 取得入口，实施边界与验证命令见记录。

多目标宿主已补齐[角色状态、日历与周期管理](CORE_MULTI_TARGET_STATE_20260924.md)：每个私人 target/role 提供固定 `state_api`，复用既有配置、周期定位、日历和维护命令；QQ 展示回执按原上下文隔离，启动恢复绑定并读取持久回执，避免重复发送。新增 11 项，最终 103 项定向测试通过；页面可从 `/host/status` 取得入口。

多目标宿主已接通[群聊可信入站](CORE_GROUP_PREVIEW_20260924.md)、[独立授权投递](CORE_GROUP_DELIVERY_20260924.md)、[多成员共享上下文](CORE_GROUP_CONTEXT_20260924.md)及[群公共记忆](CORE_GROUP_MEMORY_20260924.md)：成员陈述可保存、查询、由本人修订或撤回，跨成员召回保留原发言者与证据；群、Bot、账号、角色和原生 session 分别隔离。[群图片与引用消息](CORE_GROUP_MEDIA_20260924.md)已接入原件、动态图帧、群定向读取、模型证据、工具续答和撤回依赖，随后接入[群转发及节点音视频](CORE_GROUP_FORWARD_MEDIA_20260925.md)。历史附件只展示元数据，引用保留原发送者与当前引用者。群聊默认预览，发送独立配置并逐群授权 15 分钟；旧稿和未知回执不补发，私聊授权不适用于群聊。群消息不读取私聊记忆和私人角色资料；[群 Reply 内音视频及转发原件](CORE_GROUP_QUOTE_MEDIA_20260925.md)也已接入，群图片出站仍待后续。

生理期已补齐[连续周期与拟人表达](CORE_ROLE_CYCLE_20260924.md)、[连续性优化](ROLE_CYCLE_OPTIMIZATION_20260924.md)和[可选的每轮阶段差异](ROLE_CYCLE_VARIATION_20260924.md)：跨午夜回复保持观测时的材料，长度及差异设置从下一周期生效，周期依据独立保存，人工适用性保持优先，支持自然初始化与同次不适延续。最新 119 项定向测试通过。周期及阶段差异默认关闭，管理 API 已接入，页面与真实模型语义效果仍待验收。

本轮已接入[日历、角色状态与 QQ 展示](CORE_STATE_CALENDAR_AND_QQ_PRESENCE_20260924.md)：版本化计划/约定、日程例外、饥饿/健康/睡眠/忙碌状态、后台维护、QQ 短状态跟随日程和整轮输入提示。领域、宿主和管理 API 已贯通，开关默认关闭；新增 35 项定向测试通过。页面接线和 QQ 客户端现场效果仍待验收。

此前已完成[角色活动历史与自我时间线](CORE_ROLE_TIMELINE_SLICE_20260924.md)：普通私聊可按时间查询活动、阅读、日记/梦境操作轨迹和成长历史，保留原权限、版本与来源治理；该批将 V2 内部存储升至 v23。新增 25 项用例通过，相关回归与最终复验见实施记录。

新框架记忆拓展现已接入私聊事实/经历记忆、来源复核、召回、反思、角色工具及管理 API；成长正本沿用 v22 的角色技能/长期目标修订记录与操作回执，v23 进一步保存活动历史。普通对话已接入当前角色成长读取，只固定 ID/revision，并在提示重建时重验身份、私聊 scope、记录版本和来源受众；已认证 Dashboard API 已接通提案、确认、修订、暂停/恢复、目标完成及退出，角色查询、待确认提案工具及独立读取/提案权限设置已接通，管理页面由另一窗口推进。实现范围见[记忆实施记录](CORE_MEMORY_IMPLEMENTATION_20260923.md)、[角色成长正本](CORE_ROLE_GROWTH_SLICE_20260923.md)、[成长授权读取与管理](CORE_ROLE_GROWTH_CONTEXT_SLICE_20260924.md)、[成长工具与授权设置](CORE_ROLE_GROWTH_TOOLS_AND_ACCESS_20260924.md)及[V1 专项对照](CORE_MEMORY_V1_PARITY_AUDIT_20260923.md)。

本轮已完成[日记、梦境、阅读与睡眠的完整使用链](CORE_ROLE_LIFE_END_TO_END_20260923.md)：持久日程、真实阅读执行、睡眠唤醒、原文书架和归档管理页面均已接通。累计 202 项定向测试通过，真实 Dashboard 页面及阅读执行已验收；现场日记/梦境输出未通过格式合同，原 unknown 回执保留。详见该记录中的使用说明与现场结果。

随后完成[连续生活进入普通私聊](CORE_ROLE_LIFE_CONTEXT_SLICE_20260923.md)：活动状态、实际阅读范围、日记和梦境可在独立授权下作为当前角色提示材料，按原版本与来源引用复核；最近一批相关对话、宿主和隔离测试 123 项通过。

这是陪伴插件 V2 的独立源码根。当前主线为[本体实施路线](V1_CORE_FEATURE_PREREQUISITES.md)第 4 步：关系记忆与连续生活。[日记/梦境归档](CORE_ROLE_JOURNAL_SLICE.md)及[原角色写作流程](CORE_JOURNAL_WRITING_REVIEW_20260923.md)已完成一批本地切片；可信角色活动、已完成文本产物和已授权对话输入可按日期转为带来源/活动引用的日记素材；文本产物原文继续受来源治理，对话标明为对方表达并保留原引用。[阅读完成和当天汇集](CORE_ROLE_READING_AND_COLLECTION_SLICE.md)、[明确每日/睡眠触发](CORE_JOURNAL_TRIGGER_AND_SELECTION_SLICE.md)已接入共享宿主。新完成的[关系记忆基础切片](CORE_RELATIONSHIP_MEMORY_SLICE.md)为角色与已识别用户保存有来源的关系背景/情绪事件，支持审阅、采用、修订、撤回和历史版本；已通过[普通对话消费者](CORE_RELATIONSHIP_CONTEXT_SLICE.md)将当前私聊已采用记录接入提示材料，固定原版本并在生成和逐段发送前重验；可信审阅、采用、更正与撤回管理服务及 Dashboard 身份入口已接入。日记与生活的管理页面已随本线落地。[公共后台协调与提醒投递](CORE_BACKGROUND_AND_AGENDA_DELIVERY_SLICE.md)已贯通扫描、共享任务、发送回执和停机恢复。[主动联系偏好与执行链](CORE_PROACTIVE_CONTACT_SLICE.md)已接入四层继承、临时暂停、免打扰、原角色生成和公共投递，内部 schema 已升至 v20。完整进度见[构建状态](BUILD_STATUS.md)，目录归属见[文件组织](REPOSITORY_LAYOUT.md)和[工程约定](../AGENTS.md)。

[设计符合性检查](DESIGN_CONFORMANCE_AUDIT_20260921.md)列出的前置项已完成首批本地补齐。[ALIGN-01](ALIGN_PERSONA_RESOLUTION_AND_LEGACY_MAPPING_SLICE.md)已接多 Bot/人格路由，[ALIGN-02](ALIGN_COMMON_MANAGEMENT_ACCESS_SLICE.md)统一公共管理权限，[ALIGN-03](ALIGN_DIAGNOSTICS_AND_REPAIR_SLICE.md)提供本地诊断与修改建议。在持久任务、模型网关、消息链、原角色工具和[外部工具监督](CORE_EXTERNAL_TOOL_SUPERVISION_SLICE.md)之后，[统一宿主](CORE_HOST_LIFECYCLE_AND_BATCHING_SLICE.md)已能自动走完入站、合并、生成/工具、分段回执与历史。AstrBot 4.27.2 的[受控试运行宿主](CORE_ASTRBOT_STAGING_HOST_SLICE.md)已有单目标纯文本 ACK；现场后已撤权、停机并恢复关闭。此前框架批次未重载在线插件；本轮已完成日记与生活现场验收。其他连续生活领域、生产宿主、跨域受众投影和替换发行仍待后续。

根目录的 Python 文件仅保留 AstrBot 入口 `main.py`，宿主配置、原生对象探测、控制器和管理路由放入 `astrbot_host/`，领域实现放入 `companion_v2/`；测试、工具和记录各有所属目录。当前有测试专用的 `metadata.yaml`，没有根级 `__init__.py`。AstrBot 可加载默认关闭、支持单目标 staging 或多 Bot／多人格共享宿主的 `_v2` 测试插件；正式发布时仍计划使用 V1 的插件身份 `astrbot_plugin_private_companion`，开发目录的 `_v2` 后缀不会进入替换发行身份。

[试运行宿主入口](CORE_ASTRBOT_STAGING_HOST_SLICE.md)从 Dashboard 鉴权管理 API 显式执行 probe、initialize、authorize-delivery、start、stop、inspect、preview 和 revoke-delivery。每个 profile 使用独立新库，重启保留当前配置及原回执，不补回撤权，也不能把 preview 库改成发送库；delivery grant 具有固定 ID、精确 scope 和有限有效期。受影响范围和 AstrBot 原生契约通过，原生契约网络尝试为 0；运行中的 AstrBot 已加载入口并验证未认证请求返回 401。后续现场测试仍需新的有限期授权，历史 unknown 批次不会自动重放，也不会读取现役 V1 数据。

多 Bot／多人格共享宿主已接入一个共享 V2 installation/runtime 的多目标运行链：每个目标显式绑定平台账号、逻辑 Bot、私聊参与者和原生 persona→V2 `role_id`，并按 target 提供记忆管理路由与投递授权。记忆 owner 仍由 installation + bot + role + human subject 构成；相同 `role_id` 共享记忆，不同 `role_id` 隔离。实现和本地宿主验证见[多目标宿主落地记录](CORE_MULTI_TARGET_HOST_20260924.md)。真实多账号在线验收仍待进行。

只校验[合成示例配置](fixtures/astrbot_staging.example.json)（不初始化、不连接宿主）：

```powershell
& 'C:\Users\99505\.astrbot\backend\python\python.exe' -X utf8 tools/validate_staging_config.py fixtures/astrbot_staging.example.json
```

当前基线提供：

- 确定性时钟和只位于系统临时目录的 SQLite 测试辅助器；
- 静态隔离扫描，拒绝 V1 运行时导入、AstrBot/网络/平台调用和未批准的数据访问；
- 不执行读取的 `LegacyCompatibilityCatalog`，列出已知 V1 来源、版本、归属和目标处理方式；
- `LegacySurfaceLedger`，列出 V1 的用户可达表面及其 V2 分类。
- `ScopeRef`、主体/受众、来源、资源、操作、任务、尝试、分段和版本引用；
- 仅接受经宿主认证的账号主体，按当前绑定、精确 scope、撤权和过期复核授权的身份策略核。
- V2 自己的数据根、SQLite 正本、CAS、操作回执、inbox/outbox、来源/证据/资源治理读取，以及无副作用的合成对话回放。
- V2 内部数据库版本升级、持久能力选择与家具投影，以及同源追问、处理中撤权和未知结果恢复的 Screen 本地链。范围和测试见 [G6 切片记录](G6_CAPABILITIES_AND_SCREEN_SLICE.md)。
- 持久账号/授权与窗口角色绑定、统一配置注册/三级继承、同事务差异提交、概率单位、采用回执和有限分页变更读取；G6 设置通过 owner 共用入口，独立进程恢复和规模测试见 [CORE-01 切片记录](CORE_CONFIGURATION_SLICE.md)。
- 持久个人便签、独立/关联提醒、固定重复期次、改期/取消、原操作恢复和到期准备；[后台扫描与公共投递](CORE_BACKGROUND_AND_AGENDA_DELIVERY_SLICE.md)已接共享任务及 sender，过期记录有界跳过、未知发送不重放。已完成替身验证，提醒平台现场验收仍待进行。
- [主动联系偏好与执行链](CORE_PROACTIVE_CONTACT_SLICE.md)：安装/角色/关系/窗口逐字段继承、13 类目的、暂停到期恢复和免打扰；[自动机会与历史接续](CORE_AUTOMATIC_CONTACT_AND_HISTORY_SLICE.md)已接私聊空闲调度、窗口及关系级滚动额度和未回应背景，确认投递的联系/提醒进入后续主动和普通回复。新输入、撤回或换绑使旧稿失效；自动联系默认关闭，更多领域机会及线上验收仍待补齐。
- 持久角色活动/产物目录、进度更新、暂停/恢复、原操作幂等及跨窗口 owner；统一宿主共用数据库与时钟，关闭重开后保留原进度。目录只供可信内部使用，对外内容仍需原 Source/Asset 授权，范围见 [活动切片](CORE_ROLE_LIFE_PERSISTENCE_SLICE.md)。
- 日记/梦境日期归档、时区、来源/活动快照和修订版本；正文修改、删除或原来源撤回后，旧依赖不能继续读取。已接素材语义、原角色后台写作及独立衍生提取，允许片段或仅余韵，失败不写兜底，原任务不自动重放。自动日程和公开入口仍待接入，范围见[归档切片](CORE_ROLE_JOURNAL_SLICE.md)和[写作审查与实现](CORE_JOURNAL_WRITING_REVIEW_20260923.md)。
- 安装级身份等级、精确对象共享/撤回/过期，以及原角色便签工具结果续答的本地适配；非空 V2 内部 v4→v5 升级和受影响链路共 140 项定向测试通过，范围见 [对象权限与原角色工具记录](CORE_OBJECT_ACCESS_AND_ROLE_TOOLS_SLICE.md)。
- 有范围的配置采用、能力、数据库与原操作诊断；持久修改建议的预览/确认/取消与原角色答疑本地适配；过期、撤权或资料变更需重新检查，未观测的外部效果保持 unknown。范围见 [诊断切片](ALIGN_DIAGNOSTICS_AND_REPAIR_SLICE.md)。
- 持久任务/attempt、前后台独立名额、原角色与权限复核、取消/超时/重启恢复及原任务诊断；未知动作不自动重做，旧 worker 确认停止后才释放名额。当前只执行可信本地异步处理器，范围见 [任务切片](CORE_TASK_SUPERVISOR_SLICE.md)。
- 本地异步模型网关、任务路由/提示词配置采用、分层 token/费用原子预留和按回执结算；取消/超时保留未知用量，迟到草稿失效不抹除实际消耗。原角色与资料保持、多 Bot 隔离和模型诊断已有本地证据，真实模型已接 staging 宿主，额度管理页仍待补，范围见 [模型切片](CORE_MODEL_GATEWAY_SLICE.md)。
- 持久输入合并与撤回墓碑、异步原角色生成、逐段本地发送回执及只归档确认送出的历史；部分发送、重启、迟到回执和资料失效已验证，诊断不展示正文。原角色工具多轮续答、便签/提醒 owner、精确来源句柄和诊断结果复核已接入，范围见 [消息切片](CORE_CONVERSATION_MESSAGES_SLICE.md) 和 [工具续答切片](CORE_ROLE_TOOL_LOOP_SLICE.md)。真实平台已有单目标发送 ACK，阅读证据仍待补。
- 外部工具使用独立前台子任务、精确领取、固定能力包与 provider、原会话授权及受治理原件；超时/取消保持 unknown，实际回执可单独核对，竞争权重不影响用户请求工具。AstrBot 可信目录端口已有映射及替身验证，范围见 [外部工具切片](CORE_EXTERNAL_TOOL_SUPERVISION_SLICE.md)；真实宿主端口和不可信代码的进程隔离仍待接。
- 统一宿主装配、原子启动、空闲事件等待、自动合并/分段调度、有界停机及安全恢复；多 Bot/人格、父子工具名额、旧计时、未知发送与迟到回执已有完整模拟宿主测试，范围见 [宿主切片](CORE_HOST_LIFECYCLE_AND_BATCHING_SLICE.md)。AstrBot 4.27.2 的私聊字段、原生模型 provider 和 OneBot reverse WebSocket sender 已通过原生契约；preview 和独立授权的 sender 均已接到[试运行宿主](CORE_ASTRBOT_STAGING_HOST_SLICE.md)。

按改动范围运行测试。只检查核心隔离可使用本地 Python：

```powershell
python -X utf8 -m unittest tests.test_isolation -q
```

宿主测试需要 AstrBot 自带 Python 和 SDK 源码路径；下面的 `PYTHONPATH` 仅作用于当前 PowerShell 进程，测试会在导入 SDK 前使用临时数据根：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_staging_host tests.test_isolation -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 tools/run_native_contracts.py --host-source 'C:/Users/99505/.astrbot/backend/app'
```

核心测试使用本地 Python、时区数据库和临时文件；宿主及原生契约测试另需 AstrBot SDK，但自动测试不调用真实模型、不连接平台，也不读取现役用户数据。Windows 的 IANA 时区数据依赖已在 `pyproject.toml` 登记为 `tzdata`。本批日记/梦境与 v17 的验证命令见 [CORE-05 切片记录](CORE_ROLE_JOURNAL_SLICE.md)。既有[失败分类](CORE_MODEL_FAILURE_DIAGNOSTICS_SLICE.md)和[现场复验](CORE_ASTRBOT_DIAGNOSTICS_LIVE_20260923.md)保留为历史证据，具体模型故障不阻挡当前框架实施；既有单次 ACK 不代表 G4/G8 或替换发行已完成。
