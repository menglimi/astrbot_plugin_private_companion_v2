# V1 与 V2 当前源码功能差距核对

核对日期：2026-09-26。结论：**V2 已有可独立运行的主框架和多条完整业务链，但尚未达到 V1 及其伴侣的功能对等。当前主要欠缺业务生产者、宿主接线和部分外部执行器。**

本记录比较 V1 本体及七个伴侣的实际业务入口，与当前 V2 工作树的实现、装配和消费者。当前源码包含 Image 原生执行、群媒体、角色状态和计划管理等后续增量；同日已续接原生撤回、关系提案、群选择性参与、Content 原生消费、[原生规划与真实活动联动](CORE_PLANNING_ACTIVITY_INTEGRATION_20260925.md)以及待审成长进展闭环，以下按实现更新。已发布 ZIP 的范围仍以发行说明为准。旧进度表、静态迁移映射、页面陈设、状态发现和合成测试夹具均不单独视为功能完成。

状态含义：**已接通**指已有生产入口、领域实现和消费者；**部分完成**指其中仍缺环节；**未接入**指未找到 V2 生产业务链；**交付待验**指已有实现，还缺真实平台或新安装包验收。不用测试数量或目录数量计算功能完成百分比。

**已经落地的基础**

| 范围 | 当前 V2 已有能力 | 不能据此推定已完成的部分 |
| --- | --- | --- |
| 本体与运行框架 | 唯一本体、唯一公开小屋；独立数据根；任务、模型网关、预算、授权、来源、操作回执、恢复及启停。见[实际组装][v2-app]、[无 V1 隔离验收](NATIVE_INDEPENDENCE_ACCEPTANCE_20260925.md)。 | 所有外部伴侣业务均已原生化；所有 AstrBot 版本和模型提供商均可用。 |
| 对话与媒体 | 私聊、群聊、多 Bot/多角色；原图、动画、语音及视频采样画面；引用与合并转发输入；私群图文及默认关闭的 TTS 回复、确认历史及重启恢复；QQ 撤回 notice 与群旁听/回复选择。 | 无消息主动群插话；V1 TTS 策略、合并转发输出和任意目标转述。视频画面采样不代表完整音轨理解。 |
| 记忆 | 私聊事实/经历、核心记忆、原文和确认送达的 Bot 内容；实际活动/阅读回执及私人书写导航进入经历并可在普通对话召回；增量召回与续读；自动向量化、混合检索和可选当前页重排；群公共记忆、跨成员归因、作者更正/撤回和管理 API。 | 真实嵌入/重排模型及规模效果待验；完整图遍历、冷归档/导入导出、V1 世界书和角色知识检索仍缺。 |
| 关系与状态 | 私聊角色依据真实来源提交关系/情绪提案，经审阅采用后在同原生私聊路线跨会话重置延续；修订、撤回和原授权复核；共享能量、饥饿、健康、睡眠、心情、周期等维护。状态维护已读取最近真实对话。见[状态维护][v2-state]、[关系提案链](CORE_RELATIONSHIP_PRODUCER_20260925.md)。 | 后台情绪抽取与完整长期余韵链；真实模型的提案质量。不能描述为“对话完全不影响心情”。 |
| 生活、日记与梦境 | 阅读原文和范围、实际阅读进度、睡眠执行、定时日记、睡眠完成触发梦、正文与衍生分离、来源复核、修订和归档。见[生活主链](CORE_ROLE_LIFE_END_TO_END_20260923.md)。 | 所有日常活动的实际执行与完成回执、新闻/屏幕/设备素材入口。 |
| 日历与成长 | 计划创建、重复与例外、改期/取消、提醒；默认关闭的每日/跨周规划和临近细化；成长/目标提案、审阅、状态管理与角色读取。活动完成或日记保存回执可生成待审进展，接受后后续规划读取新 revision。规划可读取管理员明确配置的逐年放假、调休及节气日期，也可选择读取角色所在地的 Open-Meteo 当前天气。见[规划联动](CORE_PLANNING_ACTIVITY_INTEGRATION_20260925.md)、[天气来源](PLANNING_WEATHER_SOURCE_20260926.md)、[进展服务](../companion_v2/role_work/growth/progress.py)及[成长工具][v2-growth]。 | 不自动接受进展或改写已有日程；没有自动年度数据源、天气预报或完整全天活动执行，真实模型和 QQ 回执仍待现场验收。 |
| 主动联系与 QQ 展示 | 空闲私聊、真实阅读/睡眠完成、日记/梦境保存、已接受私人约定、饭点、固定公历节日/显式公历及农历纪念日期、角色所在地当前天气及显著天气变化、官方预警候选；发送/跳过、免打扰、联系额度、历史接续；输入提示、自定义短状态、默认关闭的被动戳一戳和普通在线模式切换。 | 资讯/作品等其他外部事件的主动分享；主动语音、模型即兴戳回复与连续反戳；真实天气服务、模型及 QQ 展示仍待现场验收。 |
| Image | 原生 SD/ComfyUI 生成、同 owner 单产物编辑、独立保存、模型采用、私群图文发送和回执。见[原生 Image 主链](CORE_NATIVE_IMAGE_DELIVERY_20260925.md)。 | 入站/跨来源编辑、多参考、相册衣柜、蒙版局部编辑及真实后端现场效果。 |

**生活、见闻、关系与记忆的差距**

| 编号 / 功能 | V1 已有的实际行为 | V2 状态及具体剩余工作 |
| --- | --- | --- |
| C01 自动生活计划与临近细化 | [每日计划][v1-plan]结合天气、记忆和素材生成整天安排；[临近细化][v1-detail]补活动、地点和生活片段。 | **规划生产与指定期次细化已接通，执行仍部分完成**。[原生规划](CORE_PLANNING_ACTIVITY_INTEGRATION_20260925.md)以日历、目标、记忆、会话及管理员配置的逐年日期生成每日小步、跨周长期节点，并细化临近已接受期次；可另行启用[角色所在地当前天气观测](PLANNING_WEATHER_SOURCE_20260926.md)。均默认关闭。尚缺天气预报等外部材料及完整全天活动执行，不把时间经过当作完成。 |
| C02 成长与长期目标的自动推进 | [日常循环][v1-tick]含技能/目标进展结算。 | **审阅式进展闭环已接通，现场待验**。已提交的实际活动完成或日记保存回执进入有界模型提案；[管理操作](../companion_v2/role_work/growth/progress_management.py)接受或拒绝，接受后更新成长正本，后续规划读取新 revision。日记正文不证明其中事件发生，旧日程不会自动重写。真实模型提案质量与 QQ 回执仍未现场验证；是否使用数值经验值是产品选择。 |
| C03 天气、预警与节日语境 | [天气抓取][v1-weather]、[预警刷新][v1-alert]、农历/节日语境参与生活和主动联系。 | **受控来源已接通，现场待验**。`conversation/date_context.py` 按显式时区投影日期、星期、时段、固定公历节日及可用年份内的农历日期。管理员可通过 `planning_annual_calendars` 提供版本化年度 JSON；`agenda/planning_inputs.py` 只投影规划窗口内明确列出的放假、调休和节气。显式配置角色地点后，[Open-Meteo 当前天气](PLANNING_WEATHER_SOURCE_20260926.md)可用于规划及默认关闭的主动联系；同地点两次新鲜观测可产生[显著天气变化候选](PROACTIVE_WEATHER_CHANGE_EVENTS_20260926.md)。独立的[和风天气官方预警链](OFFICIAL_WEATHER_ALERT_SOURCE_20260926.md)已接入默认关闭的私聊候选，需部署凭据。均不代表用户所在地；当前天气码不等于官方预警。自动年度数据源、真实天气服务和 QQ 投递尚未验收；固定节日不代表放假，小屋[天气与时段示例][v2-environment-ui]仍是本地显示偏好。 |
| C04 新闻阅读、网页搜索与自主探索 | [新闻抓取/阅读][v1-news]、每日新闻、[搜索][v1-search]、[自主探索][v1-explore]及 B 站相关来源。 | **资讯主动分享源码已接线，探索链仍部分缺失**。管理员提供 HTTPS JSON 资讯源后，V2 可按默认关闭的私聊偏好轮询、筛选 24 小时内条目、持久去重并经原主动联系模型和投递链分享；来源可在发送前复核。正文抓取、搜索、B 站、自主选题和小屋见闻管理仍缺；真实资讯源/模型/QQ 与新交付包未验。 |
| C05 多来源主动行为 | 生活事件、醒来/饭点、重要日期、天气、新闻、日记/梦境、创作及外部活动可提供主动候选。 | **部分完成**。[空闲私聊][v2-contact-schedule]、真实阅读/睡眠完成、私人日记/梦境保存、已接受私人约定、饭点、显式日期、当前天气、显著天气变化、官方预警、服务余额及默认关闭的[外部 JSON 资讯主动分享](../companion_v2/proactive/news_events.py)已有候选；接入原对话、来源复核、去重、免打扰及额度链，[执行输出][v2-contact-send]仍以文字决定为主。作品和其他外部事件尚未生产，真实服务、模型和 QQ 投递待现场验收。 |
| C06 关系/情绪事件与连续余韵 | V1 从对话[结算情绪事件][v1-affect]、维护关系印象并提供[情绪诊断][v1-affect-diagnostics]。 | **提案与跨重置消费已接通，长期余韵仍缺**。[关系工具](../companion_v2/relationships/tools.py)调用[关系服务][v2-rel-propose]，经[管理 API][v2-rel-api]审阅采用后进入私聊。来源保留原 scope，按同人物/角色/原生私聊路线和原授权复核，conversation/session 重置后可延续。65 项定向测试通过，含原生 MultiSession 工具续答与管理采用；显式授予 read/propose，不自动扩权。见[交付记录](CORE_RELATIONSHIP_PRODUCER_20260925.md)。 |
| C07 自动语义召回与图导航 | V1 记忆扩展有[embedding 回填][v1-embedding]、[重排序][v1-rerank]及[图导航][v1-graph]。 | **语义召回与当前批次 MMR 已接、图导航部分完成**。V2 在记忆工具链自动生成查询向量、增量补齐资料向量并混合检索；`memory/recall_query.py` 现在只对向量召回页中已通过 `RecallObjects.read` 正本授权复核的候选做稳定 MMR，并把有限候选页的剩余顺序写入游标，缺失向量退化为相关度顺序。原文、经历和 all 均有[增量召回][v2-memory-query]。这不是完整语义重排模型、全局图导航或大库效果保证；完整图遍历及真实 provider/大库效果仍待补验，详见[嵌入专项](V1_EMBEDDING_USES_AND_V2_ADOPTION_20260925.md)。 |
| C08 世界书、角色知识与人物资料 | [世界书导入和人物观察][v1-worldbook]、[角色知识库片段选择][v1-knowledge]进入上下文。 | **检索、来源治理与对话注入已接通，真实资料源待验**。`knowledge/parsing.py` 与 `knowledge/retrieval.py` 可解析并按 scope/role/persona/subject/audience/enabled 做授权筛选，按命中、优先级、文档预算、相邻 chunk 去重和无命中采样稳定选择；封存时发布 `SourceRef`，重读时重新校验，来源撤回/过期/权限变化不会继续注入。`ConversationMessages` 仅以受控背景资料提示词加入有效命中；不把资料当作当前事实。10 项定向检索/来源回归通过，真实 AstrBot 世界书/知识库适配和大库效果仍待验。 |
| C09 行为自我复盘 | [每日自我巡视][v1-review]生成临时指导并[注入后续请求][v1-review-guidance]。 | **生产链已接通，页面与现场待验**。`role_work/journal/self_review_evidence.py` 只收集角色自己的可观察行为（已确认送达的回复与已完成的活动/日记回执），对外只发布不含内部标识的句柄；`self_review_service.py` 按角色游标生成待审候选，`self_review_management.py` 提供已认证操作者的接受/拒绝，`conversation/self_review_context.py` 仅注入已接受、未过期且原证据仍可复核的指导。接受单条时只复核该条引用的证据。内部 schema 升至 v39。详见[C09 切片记录](CORE_SELF_REVIEW_20260926.md)。小屋审阅页面、定时巡视节拍与真实模型/QQ 验收仍缺。 |
| C10 表达与说话习惯学习 | V1 有[表达样本收集][v1-expression]、[规则注入][v1-expression-rules]和反馈。 | **生产链已接通，页面与现场待验**。`expression/style_evidence.py` 从已确认送达的回复取样（7 天窗口、至少 4 条、单条截断），只对外发布不透明句柄；`style_service.py` 在七个受限维度（句律/表情/标点/直接度/用词/排版/其他）生成待审候选，模型输出严格校验维度白名单、证据句柄、置信度与字段封闭；`style_management.py` 提供采纳/拒绝/退役；`conversation/style_context.py` 只注入已采纳规则，并以"以本轮为准、不得当作指令"措辞约束。内部 schema 升至 v40。详见[C10/C11 切片记录](CORE_EXPRESSION_MEMORY_ARCHIVE_20260926.md)。小屋审阅页面、反馈回路与真实模型验收仍缺。 |
| C11 记忆生命周期与整体遗忘 | V1 记忆扩展有[冷归档][v1-memory-archive]、历史导入、[便携导出][v1-memory-export]。 | **生产链已接通，页面与现场待验**。V2 已有 session/short/durable/protected 保留规则及[范围清理][v2-memory-clear]；`memory/archive.py` 补上生命周期末端：冷归档为逻辑移动、可逆、不擦除，归档判定读 `record_json` 内 proposal 的 retention（`memory_atoms` 无 retention 列），只对闲置 durable 事实生效，token 保证预览与确认一致；导出永远限定单个私聊关系与角色，读取不到的记录作为 tombstone 而非当作角色从未拥有；导入必须预览后确认，每个导入事实经 `BUNDLE_OWNER` 发布真实来源并保留 bundle 溯源，与角色直接观察到的事实可区分。宿主新增六条归档/导入导出路由。详见[C10/C11 切片记录](CORE_EXPRESSION_MEMORY_ARCHIVE_20260926.md)。跨全部业务的整体遗忘编排、小屋审阅页面与真实模型验收仍缺。迁移只做能力对照，本次不操作用户资料。 |
| C12 跨业务记忆生产与消费 | V1 [业务记忆适配][v1-memory-adapters]连接多种共同活动与外部能力。 | **部分完成**。V2 查询、提议/操作、订阅与引用消费者已有[宿主装配][v2-memory-ports]；[真实活动/阅读及私人书写回执](MEMORY_ACTIVITY_PRODUCTION_20260925.md)已生产经历并供普通对话使用。创作、游戏、直播等其他外部领域仍需逐个接入。 |
| C13 身份绑定、解绑与合并管理 | V1 有[绑定/解绑/合并预览][v1-identity-manage]及身份恢复流程。 | **部分完成**。V2 原生人格、多 Bot/多目标与[身份 bind/revoke][v2-identity]已存在；多账号关联、解绑确认、合并预览、待确认身份审阅和恢复管理流程尚未找到。 |

日记和梦境的保存回执已能提供经历导航与有时效的主动联系候选，但不会把私人正文复制成独立事实。当前主要欠缺完整生活、新闻、屏幕、共同活动及设备观察等上游材料入口，以及真实模型和 QQ 对日记/梦境分享的现场验收。正文生成、归档和修订已经落地，不宜再从头实现。具体模型写作品质和长期连续性还需要独立现场验收。

**群聊行为的差距**

| 编号 / 功能 | V1 已有的实际行为 | V2 状态及具体剩余工作 |
| --- | --- | --- |
| G01 旁听、选择性唤醒与主动插话 | [旁听入口][v1-group-listen]、[唤醒决策][v1-group-wake]、[主动插话][v1-group-interject]。 | **新消息触发的选择性参与已接通**。[参与 owner](../companion_v2/conversation/participation.py)按原角色提示提供 reply/skip，直接回复无需额外模型决策轮次；旁听保留授权原话但不生成或发送占位回复，选择回执与重启恢复已接。123 项定向测试通过。无新消息时的定时插话和群社会画像仍缺。见[交付记录](CORE_GROUP_PARTICIPATION_20260925.md)。 |
| G02 群长期社会理解 | V1 有[黑话学习][v1-group-language]、昵称校正、[气氛维护][v1-group-atmosphere]和[群事件整理][v1-group-events]。 | **部分完成**。V2 已有[群公共记忆][v2-group-memory]和[有原话证据的词义学习、纠正及语义召回](../companion_v2/memory/group/slang.py)；成员画像、别名、关系边、气氛、群事件整理及其参与行为尚未完整承接。 |
| G03 群公共记忆管理页面 | 群观察和记忆管理入口。 | **后台已接、页面未接**。V2 [管理员 API][v2-group-memory-api]已有列表、详情、撤回和操作回执，并已[注册][v2-group-memory-register]；当前[小屋记忆页][v2-group-memory-ui]仍引导选择私聊。页面沿原有分工对接，无需重建后台 API。 |

**平台交互与图像能力的差距**

| 编号 / 功能 | V1 证据 | V2 状态及具体剩余工作 |
| --- | --- | --- |
| P01 QQ 撤回通知 | [V1 notice 入口][v1-recall]；另有平台删除消息。 | **原生通知链已接通、现场待验**。[插件入口](../main.py)通过[可信 notice 桥](../astrbot_host/recalls.py)接收 friend_recall/group_recall，按原路由和 raw 消息号持久撤回；引用、派生材料、待发内容和可定位的 Bot 历史复核生效，实际 ACK 保留。22 项撤回专项通过，含真实 SDK convert_message 到插件入口。尚未新增 delete_msg 主动撤回或旧撤回正文查询。见[交付记录](CORE_PLATFORM_RECALL_20260925.md)。 |
| P02 TTS 与语音回复 | [V1 发送增强][v1-tts-hook]和[语音组件生成][v1-tts]。 | **被动回复强化链已接通，V1 专用后端及主动语音仍未完成**。V2 默认关闭；支持按请求/模型标签/概率选句、私群冷却、语种 Provider、外语可见文字、语音独占、分段范围和语音组件位置。原会话图文与语音共用 OneBot ACK，合成失败保留图文，未知 ACK 不重发。见[强化记录](CORE_VOICE_REPLY_ENHANCEMENT_20260925.md)。V1 的独立文本转换模型、MiMo、Fish Audio 专用控制、主动消息语音与本机播放仍需单独接入；真实 Provider 与 QQ 待现场验收。 |
| P03 入站图片编辑、多参考和人物一致性 | [参考用途选择][v1-image-reference]、[聊天图片任务装配][v1-image-chat]支持受管图库及身份/服装/姿态/风格引用。 | **部分完成**。V2 [公开 Image 参数][v2-image-api]和[编辑合同][v2-image-types]只接受本 owner 的单张 artifact；缺入站和跨来源资源采用、多参考用途及旧提示词编排。 |
| P04 相册与衣柜 | [相册工具][v1-album]有拍照留念、读取、检视、评价、选择和删除；[衣柜][v1-wardrobe]含维护及看图入柜，[每日穿搭][v1-outfit]随日程生成。 | **未接入业务链**。生成图存储不是完整相册。V2 尚无对应管理/角色操作及穿搭连续性；小屋衣柜陈设不代表衣物正本。 |
| P05 蒙版、区域编辑与更多图片后端 | 旧 Image 的[区域裁剪/贴回][v1-image-region]；V1 [NAI 桥][v1-nai]。 | **部分完成**。原生 Image [后端][v2-image-backends]当前为 SD/ComfyUI，Comfy 路线明确拒绝 mask；区域合同、局部编辑和 NAI provider 尚未原生接入。`integration/nai_image.py` 已提供不访问凭据/网络的参数映射合同。 |
| P06 戳一戳与普通 QQ 状态 | [V1 戳一戳入口][v1-poke]、回戳及[普通在线状态][v1-online]。 | **被动戳一戳与普通在线模式基础链接通，V1 即兴行为仍部分完成**。默认关闭的[通知入口](../astrbot_host/pokes.py)只接已配置用户戳当前 Bot 的可信 OneBot notice；按当前私聊/群聊投递授权发送预设短句，可选单次反戳，持久去重，未知发送结果不重放。同一账号/群/发送者在同一秒的多次通知会合并。输入提示、自定义短状态及默认关闭的普通在线/离开/忙碌/隐身模式由 [V2 presence][v2-presence]接入；模式需角色状态明确给出，当前日程公开短状态优先，两个状态开关共用账号授权，OneBot 请求与未知回执按账号持久去重，不凭空重置手工状态。单目标/多目标戳一戳及普通模式有合成宿主测试；真实 QQ 待验。V1 的模型即兴戳回复和连续反戳仍未接入。 |
| P07 合并转发输出、跨会话转述 | [V1 合并转发发送][v1-forward-out]及[指定群/私聊转述工具][v1-relay]。 | **未接入**。V2 已接转发输入；出站固定原私聊/原群受众，可带文字、图片和默认关闭的语音，尚无合并转发输出或跨目标转述。跨目标发送需重新明确目标授权，不能直接复用原窗口权限。 |
| P08 表情素材与语义选图 | V1 按回应意图结合素材标签、嵌入检索和视觉复核，选择可发送的表情原图；另有自动概率、冷却、发送位置及 QQ 表情格式策略。 | **被动回复和主动联系的图库选图已接通**。V2 的[表情素材 owner](../companion_v2/expression/reactions.py)已接管理员导入与编辑、视觉标注、混合检索、复核、原图/GIF 投递及确认送达后记账；[会话偏好](../companion_v2/expression/reaction_preferences.py)支持当前发言者暂停/恢复、单轮明确请求、自动触发概率、确认送达后的冷却及反馈排序。私聊默认开启、群聊默认关闭；[回复发送链](../companion_v2/conversation/generation.py)支持正文前、同条及正文后发送，明确索图同条发送；OneBot 可只对图库表情应用 QQ 表情格式。[主动联系](../companion_v2/proactive/service.py)默认不附图，启用后模型可给出可选检索意图，按原语义库选择素材；图文清单绑定原图，投递前重读素材并校验，素材失效时整条取消，确认送达或迟到回执后幂等记账。V1 的低延迟缓存及部分细粒度嵌入参数仍未等价接入；真实视觉/嵌入 provider、QQ 显示和低延迟表现仍需现场验证。 |

**七个可选伴侣的原生化差距**

| 提供方 | 当前 V2 状态 | 尚缺的 V1 业务 |
| --- | --- | --- |
| Image | **基础链已接通**。独立 owner、存储、执行、采用和私群投递。 | 入站/跨来源编辑、多参考、相册衣柜编排、蒙版/区域编辑和额外后端，详见 P03–P05。真实 SD/ComfyUI 效果和 QQ 投递仍需现场验收。 |
| Content | **作品基础链已接通**。[main][content-main]装配原生 provider，[七个作品操作][v2-content]通过可信 owner/source/contributor、AccessPort 和宿主角色工具进入 V2；固定版本读取、模型续答、撤回事件与派生材料/待发内容失效已接。见[消费者交付](CONTENT_NATIVE_CONSUMER_20260925.md)。 | V1 [创作/续写/审核][v1-creative]的专用任务编排、封面与主动分享仍缺；`conversation/content/authoring.py` 新增合成草稿的提示词/输出合同，不自动保存或采用。[QQ 空间动作][v1-qzone]、自动生活发布和评论收件箱也尚未迁入。 |
| Screen | **单次本机截图已接 V2 原生执行链**。[V2 流水线][v2-screen]含原件、授权、解释和反馈回执，宿主已把实际截图交给模型图片上下文。 | 定时观察、自定义任务、窗口/输入轨迹、远端采集和真实视觉模型/QQ 验收仍缺；旧自动观察不由此自动迁入。 |
| Together | **V2 原生房间 create/snapshot/close 已接通**，票据固定角色、模型和语音执行绑定，小说书库按 V2 scope 隔离；见[原生记录](REALITY_TOGETHER_NATIVE_20260926.md)。 | [观影/通话/共读/工作房间][v1-together]的真实服务器、视频帧/字幕、实时语音与打断、活动通知和共同经历需现场核对及继续接线，不能以建房工具代表完整活动。 |
| Reality | **V2 原生快照、设备目录/状态与受限控制已接通**，设备别名、白名单和确认回执由提供方核验；见[原生记录](REALITY_TOGETHER_NATIVE_20260926.md)。 | [移动位置/活动/遥测][v1-mobile]、[米家场景][v1-mihome]、摄像、本地音频、提醒/唤醒与后台设备快照仍缺；真实米家设备控制未验。 |
| Game | **四种 V2 聊天内游戏已接通**：井字棋、五子棋、掷骰竞分、单人二十一点，分别默认关闭，拥有独立操作账本和私聊终局经历来源；见[原生记录](GAME_LIVE_NATIVE_20260926.md)。 | [七种游戏][v1-game]的其余三种、浏览器房间身份/席位、活动占用、共同对话、余韵和主动邀请仍缺；真实 QQ 与最终包未验。 |
| Live | **B 站/Twitch 当前场次状态与近期事件只读端口已接通**，短期游标、停播与平台开关隔离；见[原生记录](GAME_LIVE_NATIVE_20260926.md)。 | [B 站/Twitch 主动回复][v1-live]、VTS 表情/热键/参数、字幕/TTS/嘴型、OBS、观众观察/话题/高光/小结仍缺 V2 执行与回执；只读端口不启动直播或发送。 |

因此，七个提供方都已有至少一条 V2 原生或宿主执行链，但覆盖深度不同：Live 仅只读，Game 仅聊天内四种玩法，Screen 仅单次本机截图，其他领域也仍缺上表所列流程。“已被小屋发现”“源码可执行”和“最终包实机通过”继续分开统计；不能把作品基础操作计作完整创作、封面或分享流程。

**模型、管理和替换交付的差距**

| 编号 / 范围 | 当前覆盖 | 剩余工作 |
| --- | --- | --- |
| D01 模型路由与成本 | [V2 任务模型配置][v2-routing]已有 provider/fallback/提示词/输出限制；关键词、正则和时区时段规则已接入任务选模，支持规则指定模型名、备用 Provider、显式拒绝时可选回退及工具续答期间封存路由。[预算账本][v2-budget]按实际 Provider 费率预留与结算，拒绝用量保留。离线 SDK 流式与分段组合、配置重载和 v36 失败记录迁移已定向验证。[服务余额感知](SERVICE_BALANCE_AWARENESS_20260926.md)已从宿主 HTTPS JSON 接口接入默认关闭的私聊主动联系、来源复核和 v37 持久冷却。 | 当前[宿主模型适配][v2-native-model]要求确切的 ProviderOpenAIOfficial 类型，不能宣称支持所有 AstrBot 模型提供商。余额接口、真实 Provider 的选模、费率/用量、拒绝及 QQ 投递仍待实机验收，当前源码也尚未纳入最终交付包。 |
| D02 管理小屋 | 生活、记忆、关系、状态、日历、成长和宿主已接真实 API。 | 群公共记忆管理 UI、完整能力安装/升级/启用/授权流程、模型/提示词/主动策略编辑及用量成本管理仍未齐全。[联系安排][v2-contact-ui]和[模型页面][v2-model-ui]主要引导 AstrBot 配置；[能力详情][v2-provider-ui]主要展示公开状态。页面继续沿已有任务分工推进。 |
| D03 平台与宿主范围 | V2 [元数据][v2-metadata]固定 AstrBot 4.27.2 与 aiocqhttp，原生桥为 OneBot 反向 WebSocket。 | V1 有[更广的平台能力分档][v1-platform]；V2 尚未扩展到 QQ 官方及其他适配器/版本。V1 源码声明也不等于这些平台都已现场验证。 |
| D04 数据与旧入口 | V2 独立存储；[legacy 映射][v2-legacy]记录旧表面的归属。 | 尚未交付 V1 用户资料迁移、对账和回滚；旧命令需逐项决定替代入口或兼容别名。内部 V2 schema 升级不是 V1 数据迁移，本次没有读取或迁移 V1 用户数据。 |
| D05 安装包与现场运行 | 已有 V2.0 安装快照、真实 SDK 临时进程和无 V1 隔离验收。 | 后续 Image、Content、状态/计划及本批撤回/关系/群参与增量尚未进入原 ZIP；新包需定向安装验收。真实 QQ、真实模型/图片后端、长期日常运行仍需分项验证，不能用合成通过记录代替。 |

**不机械照搬的旧行为**

- V1 数值经验值、根据忙碌状态延迟回复等行为应按 V2 产品语义重新决定。V2 已有定性成长和 busy 状态；[V1 繁忙延迟][v1-busy]本身默认关闭，缺少同名开关不等于整个忙碌能力缺失。
- 数值好感、固定关系阶段和情绪档位不直接记为遗漏；V2 使用有来源、经审阅的关系理解，一次情绪变化不自动升级关系。记忆内置于 V2 核心，也不需要重新依赖旧记忆插件。
- 旧命令改由页面或角色工具承担，不必把每个别名记为独立功能；独立 WebUI 是否保留也属于入口选择。
- 不能把 V1 自身没有完成的“游戏房间跨重启恢复”“直接发送到 Twitch 聊天室”列为 V2 回归缺口。
- 本次未找到 V1 实际修改 QQ 头像或个性签名的执行入口，不将它们记为确定缺口。
- 未知发送不重放、来源撤回后不继续使用、提案与事实分开，是当前 V2 的运行语义，不属于待恢复的旧功能。

**待迁功能的迁移方式**

“可直接迁移”仅指业务计算或只读材料可薄适配，并不等于复制 V1 文件、全局配置或用户数据。V2 已有上下文贡献、任务、来源、授权和回执接口；当前没有阻止低冲突功能接入的框架级缺口。

| 判定 | V1 功能 | V2 所需工作 |
| --- | --- | --- |
| 可先薄适配 | C03 的当前本地时间、星期/时段、受支持年份内的农历日期及固定公历节日名 | 在 V2 对话领域按受控时区投影为本轮材料，明确日历数据依赖和可用年份；不读 V1 数据。年度放假/调休与 V1 固定日期节气表不在这一类。 |
| 已接通、现场待验 | C03 的天气变化与官方预警、C05 的显式农历纪念日 | 天气变化比较同一角色地点的新鲜观测；官方预警使用独立凭据和来源。农历纪念日须显式配置且历法可用。三者均已接入主动联系生产链，真实天气服务、模型和 QQ 投递尚未现场验收。 |
| 需要修正后迁入 | C03 的自动年度日历数据源，C04 网页/B 站探索、C05 其余主动事件 | 年度日历可由管理员显式配置并进入规划；当前天气、变化、官方预警、余额及单条 JSON 资讯主动分享已有受控链。自动年度数据、全文/搜索/自主探索、作品和其余外部事件仍缺运行链接线。 |
| 需要修正后迁入 | C06 关系长期余韵、C07 图导航及 MMR 生产接线、C09 复盘注入、C10 表达学习流程、C11 记忆归档/导入导出、C12 外部领域记忆、C13 身份合并管理 | MMR 排序、知识格式解析/检索注入、复盘/表达候选合同已补；其余生产流程仍需各自正本/生产者、授权范围、版本及原来源复核；旧库不可直接接入。 |
| 需要修正后迁入 | G01 定时群插话、G02 除词义外的社会画像/气氛/事件、G03 群记忆页面 | 群来源和参与决策已存在，后台生产及各群独立受众仍需落地；G03 页面由并行页面任务负责。 |
| 需要修正后迁入 | P01 主动删除/撤回回看、P02 选择性 TTS、P03–P05 进阶图片/相册/衣柜、P06 戳一戳/普通在线状态、P07 出站转发/跨目标转述 | 平台副作用、资源所有权、目标授权和不确定回执需通过 V2 宿主端口；不能从原会话权限推导跨目标发送权。 |
| 需要修正后迁入 | Content 专用创作工作流/封面/分享/Qzone，Screen 真实采集，Together/Reality/Game 房间/Live 原生链；D02 剩余管理、D03 其他平台、D04 旧数据/命令、D05 更新安装包 | Content 草稿合同、NAI 参数映射、关键词/时段生产选模及四种游戏纯规则已具备；各领域仍需独立执行、来源和回执，旧数据迁移应另有对账与回滚。D01 服务余额感知已有源码链路，交付包与实机另行验收。 |
| 已特殊处理 | V1 数值经验/好感/固定阶段、忙碌强制延迟、旧命令与独立 WebUI、旧记忆插件依赖、强制输出密码 | V2 分别采用可审阅定性成长/关系、角色状态、角色工具与单一小屋、内置记忆和不暴露密钥的诊断，不按旧行为逐项复刻。 |

**下一步建议与验收终点**

| 优先级 | 工作线 | 完成时必须能证明 |
| --- | --- | --- |
| 已补：替换基础 | 原生 QQ 撤回 notice、关系/情绪提案与跨会话重置、群旁听与选择性参与已接通。 | 生产链与真实 SDK 合成用例已验证。下一步在真实账号上验证平台通知、提案质量和角色参与方式；源码增量待纳入新安装包。 |
| 已补：Content 原生消费 | main、可信访问、宿主工具、固定版本读取与撤回传播已接通。 | V2 原角色可创建、保存/采用候选并读取指定版本；撤回后的旧模型材料和待发稿不可继续使用。下一段是专用创作流程、封面与分享。 |
| 已补：规划与活动回执联动 | 每日/跨周规划及临近细化 → 原活动回执 → 经历记忆和阅读/睡眠主动候选已接通。 | 规划、完成与发送分别留据，旧来源在读取时复核；[交付记录](CORE_PLANNING_ACTIVITY_INTEGRATION_20260925.md)的 67 项定向/宿主用例通过。 |
| 已补：成长与后续安排 | 已提交活动/日记回执 → 待审成长进展 → 管理接受/拒绝 → 正本新 revision → 后续规划读取。 | 34 项成长/规划/SDK 定向测试通过；真实模型、QQ 和安装包现场验收未做。既有日程不会自动修改；资讯、其他生活事件及 TTS 继续分片补齐。 |
| 已补：低成本领域合同 | 日期/农历投影、MMR 纯排序、四种游戏规则、知识格式、复盘/表达候选、Content 草稿、逐年日历、天气/新闻归一化、NAI 参数映射及关键词/时段匹配已有独立模块和定向测试；四种游戏规则已进入 V2 聊天内原生端口，资讯 JSON 源已进入默认关闭的主动联系。 | 验收命令和各模块边界见[低成本迁移合同切片](LOW_COST_MIGRATION_CONTRACTS_20260926.md)。自动年度数据、新闻全文/搜索/自主探索、知识检索注入、候选持久化/采用及 NAI/provider 仍未完成；原生源码不等于最终包或真实 QQ 验收。 |
| 再后：扩展与交付 | 入站/跨来源编辑、图库/衣柜/局部编辑；其余伴侣逐个完成业务切片；更新安装包与现场验收。 | 每个提供方至少有一条脱离 V1 的实际业务链，并明确未覆盖的高级能力；源码与交付包范围一致。 |

当前仍处固定流程第 1 阶段：继续补齐缺失领域能力和生效配置，尤其 Game 浏览器房间/其余玩法、Live 主动接话和外部呈现、Content 专用创作/分享及其他主动来源；随后统一接小屋、构最终包，并按真实验收表在受控账号上逐项测试。资讯、天气、活动和四种聊天游戏的源码接线不代表现场已通过。

本清单持续区分纯合同、生产接线和现场验证。低成本合同切片的实现及验收证据见对应交付文档；不能据合成通过记录推断真实外部来源或平台执行已可用。以下链接指向核对时的本机源码，行号可能随后续开发移动。

**源码索引**

[v2-app]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/host/application.py:118
[v2-state]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/role_work/state/maintenance.py:18
[v2-growth]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/role_work/growth/tools.py:16
[v1-plan]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/planning.py:755
[v1-detail]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/planning.py:89
[v1-tick]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/daily_state.py:18811
[v1-weather]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/daily_state.py:7350
[v1-alert]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/daily_state.py:7124
[v2-environment-ui]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/pages/陪伴小屋/app.js:201
[v1-news]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/news_exploration.py:3248
[v1-search]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/news_exploration.py:4261
[v1-explore]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/news_exploration.py:4755
[v2-share]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/sharing/planner.py:36
[v2-discoveries-ui]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/pages/陪伴小屋/app.js:326
[v2-contact-schedule]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/proactive/scheduling.py:59
[v2-contact-send]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/proactive/service.py:235
[v2-rel-propose]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/relationships/service.py:157
[v2-rel-api]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/astrbot_host/relationships_api.py:68
[v1-worldbook]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/worldbook.py:316
[v1-knowledge]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/astrbot_knowledge.py:314
[v2-persona]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/adapters/astrbot/native.py:47
[v1-review]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/daily_review.py:1522
[v1-review-guidance]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/daily_review.py:1795
[v1-recall]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/main.py:9327
[v2-withdraw]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/host/application.py:323
[v2-tombstone]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/conversation/messages.py:494
[v2-main]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/main.py:85
[v1-tts-hook]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/main.py:11194
[v1-tts]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/tts_enhancement.py:6229
[v2-sender]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/adapters/astrbot/onebot.py:70
[v1-image-reference]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/companion/integrations/image_reference_catalog.py:62
[v1-image-chat]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/companion/integrations/image_chat_tasks.py:148
[v2-image-api]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_companion/native_v2/adapter.py:55
[v2-image-types]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_companion/native_v2/types.py:109
[v1-album]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/photo_album_runtime.py:204
[v1-wardrobe]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/wardrobe_runtime.py:433
[v1-outfit]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/daily_state.py:662
[v1-image-region]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_edit_region.py:32
[v1-nai]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/nai_image_bridge.py:132
[v2-image-backends]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_companion/native_v2/backends.py:48
[v1-poke]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/main.py:9176
[v1-online]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/proactive_message.py:10284
[v2-presence]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/adapters/astrbot/presence.py:46
[v1-forward-out]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/proactive_message.py:17252
[v1-relay]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/main.py:13727
[v2-content]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/companion/content_v2/provider.py:37
[content-main]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/main.py:492
[v1-creative]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/creative.py:617
[v1-qzone]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/main.py:715
[v2-screen]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/screen/pipeline.py:35
[v1-screen]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_screen_companion/core/media.py:3435
[together-main]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/main.py:64
[v1-together]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/main.py:856
[reality-main]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/main.py:186
[v1-reality-owner]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/mobile_snapshot_owner.py:88
[v1-mobile]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/mobile_gateway.py:526
[v1-mihome]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/mihome_client.py:1736
[game-main]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_game_companion/main.py:269
[v1-game]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_game_companion/room_manager.py:43
[live-main]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_live_stream_companion/main.py:117
[v1-live]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_live_stream_companion/main.py:1373
[v2-routing]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/model_gateway/routing.py:21
[v2-budget]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/model_gateway/budget.py:23
[v1-routing]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/model_routing.py:36
[v1-balance]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/balance_awareness.py:475
[v2-native-model]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/astrbot_host/native.py:193
[v2-contact-ui]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/pages/陪伴小屋/app.js:309
[v2-model-ui]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/pages/陪伴小屋/app.js:312
[v2-provider-ui]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/pages/陪伴小屋/product-page.js:189
[v2-metadata]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/metadata.yaml:15
[v1-platform]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/platform_compat.py:20
[v2-legacy]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/legacy/surface_ledger.py:1
[v1-busy]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/busy_reply_gate.py:270
[v1-affect]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/domains/affect/interaction_dynamics.py:64
[v1-affect-diagnostics]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/emotion_diagnostics.py:248
[v2-rel-context]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/conversation/relationship_context.py:45
[v1-embedding]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_remember_you/core/service.py:4179
[v1-rerank]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_remember_you/core/retrieval.py:415
[v1-graph]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_remember_you/core/service.py:6585
[v2-memory-query]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/memory/query.py:179
[v2-memory-vectors]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/memory/search.py:179
[v1-expression]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/user_memory.py:3109
[v1-expression-rules]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/user_memory.py:3657
[v1-memory-archive]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_remember_you/core/service.py:7594
[v1-memory-export]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_remember_you/core/service.py:7086
[v2-memory-clear]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/memory/management.py:85
[v1-memory-adapters]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/memory_companion_adapter.py:2793
[v2-memory-ports]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/host/application.py:156
[v1-identity-manage]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/page_api_users_groups.py:512
[v2-identity]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/identity_policy/repository.py:129
[v1-group-listen]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/message_pipeline.py:1327
[v1-group-wake]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/group_wakeup.py:1121
[v1-group-interject]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/group_observation.py:4656
[v2-group-claims]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/astrbot_host/multi_controller.py:219
[v2-group-intake]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/astrbot_host/multi_session.py:187
[v1-group-language]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/group_observation.py:2165
[v1-group-atmosphere]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/group_observation.py:2475
[v1-group-events]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/group_observation.py:4882
[v2-group-memory]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/memory/group/service.py:73
[v2-group-memory-api]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/astrbot_host/group_memory_api.py:19
[v2-group-memory-register]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/astrbot_host/multi_api.py:140
[v2-group-memory-ui]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/pages/陪伴小屋/memory-page.js:227
