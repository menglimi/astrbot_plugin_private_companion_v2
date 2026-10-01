# V1 → V2 记忆功能对照检查（2026-09-23）

当前结论：V2 已落地私聊记忆核心闭环，尚未完整接替 V1 的记忆使用链。此前参考过 V1 总体功能盘点，但上一轮的 263 项定向测试主要证明 V2 记忆及宿主集成，不能作为 V1 功能全部迁移的证据。本次补做记忆专项源码对照，并据此更正实现记录和状态说明。

**2026-09-24 状态更新：** [私聊记忆完善切片](CORE_MEMORY_PRIVATE_POLISH_20260924.md)已补入置顶常驻、确认回复来源、凭据清洗、历史查询及事实批量治理；对应行已更新，最终主树受影响回归 115 项通过。其余缺口继续保留，不把这一批标为完整 V1 对等。

## 检查范围与判定

检查对象是当前本地源码，包含未提交改动，不代表对应仓库已发布版本：

- [V1 陪伴功能盘点](../../astrbot_plugin_private_companion/docs/evaluations/COMPANION_FEATURE_INVENTORY_20260917.md)中的 MEM01–MEM10，以及陪伴的本地画像、纠正和长期记忆桥接。
- 旧记忆插件目录 `astrbot_plugin_remember_you`；其 [metadata.yaml](../../astrbot_plugin_remember_you/metadata.yaml) 声明身份为 `astrbot_plugin_memory_companion`、版本为 2.1.4。对照实际 service、检索、来源捕获和管理代码，不仅依据 README。
- V2 的 [memory 领域](../companion_v2/memory/)、会话消费者、Dashboard API，以及已经由关系、角色生活和开放事项领域承接的部分。
- [记忆契约](../../astrbot_plugin_private_companion/docs/MEMORY_CONTRACT_V0.md)、[经历与追忆设计](../../astrbot_plugin_private_companion/docs/MEMORY_EXPERIENCE_AND_RECALL_V0.md)、[Content 记忆契约](../../astrbot_plugin_content_companion/docs/MEMORY_RECALL_FRAMEWORK_V1.md)。设计中的能力不直接计为已实现。

“已覆盖”指指定行为已有源码和对应合成测试证据；“部分”表示底座存在但完整入口、消费者或使用流程未接齐；“未接入”表示本次未找到 V2 对应实现；“由其他领域承接”不等于可省略跨领域验收。旧算法、旧指令名和旧存储布局无需原样复制，用户需要的能力必须有明确承接。

9 月 23 日原审查未重新运行功能测试；9 月 24 日增补执行了单独的定向回归。两批均没有读取 V1 用户数据、执行迁移、调用真实模型或操作在线插件；合成测试不能替代实际语义质量、平台适配或生产容量验收。

## 陪伴插件原清单逐项对照

| V1 项 | V2 分类 | 实际承接与剩余工作 |
| --- | --- | --- |
| MEM01 基础日记 | 由角色生活领域承接 | `role_work/journal/` 已有原稿、素材、修订及生成链；不在 Memory 再建日记正本。[生活使用链记录](CORE_ROLE_LIFE_END_TO_END_20260923.md)仍保留现场输出格式失败，不能写成全部线上验收完成。 |
| MEM02 梦境与碎片 | 由角色生活领域承接，记忆互通仍需补齐 | 梦境归档和普通对话材料已有；梦境进入 Memory 时仍须保留虚构归因和原来源，不能把通用提案接口视为该桥接已完成。 |
| MEM03 本地画像、偏好与习惯 | 部分，按新框架改造 | 通用事实、偏好、限定条件、有效期、反思和明确纠正已有；置顶称呼与边界已有独立每轮预算入口。习惯供主动使用的完整流程仍待接替；表达学习、关系印象由对应领域负责。 |
| MEM04 对话片段、共同经历、未完事项 | 部分，分领域承接 | Memory 已有经历摘要、来源续读和对象关联；开放事项已有独立对话消费者。旧片段的自动整理、所有查询/删除入口和两者之间的来源传播仍需逐场景验收。 |
| MEM05 Bot 自我时间线 | 由角色生活领域承接，跨域投影部分 | 活动、阅读回执、日记与梦境由各自 owner 持有。Memory 当前按人、Bot、角色的私聊关系归属，不等于已经具备独立 Bot Personal 档案及旧自我时间线的全部检索入口。 |
| MEM06 外部长期记忆与功能上下文 | 内部接入已替代一部分，领域适配未齐 | V2 统一宿主直接装配 Memory，减少主插件寻找外部实例的连接问题；旧桥接中的日程、照片、创作、穿搭、情绪、动态发布等数据流不能因存在通用 Writer 就标为已接通。可信进程内查询、提案提交与操作查账已经接入，见[提交与持久回执](CORE_MEMORY_PROPOSAL_WIRE_SLICE_20260924.md)；各实际领域消费者、跨进程 SDK 及订阅仍未接齐。 |
| MEM07 原文持久捕获、补交、脱敏与删除抑制 | 私聊文本链已补齐一批 | 入站来源、确认投递的 Bot 回复、版本/哈希复核、消息撤回、常见凭据清洗及记忆原文/反思选材已接入；完整媒体、历史补交和其他领域来源仍需继续验收。 |
| MEM08 明确纠正用户记忆 | 私聊核心已覆盖，跨域传播待验 | 已有查来源、原版本修订、冲突控制和操作回执，依赖原件的视图/回复会重新校验。仍需补照片、作品、主动候选、角色活动等实际消费者的纠正传播验收。 |
| MEM09 清空记忆、忘记我、用户删除 | 部分 | 单条遗忘、当前宿主私聊关系事实/修订的批量预览与执行、来源防再学习及所属索引清理已有；跨领域“忘记我”、群/群成员范围和各领域结果汇总仍未接齐。不承诺擦除宿主日志和已有备份。 |
| MEM10 每日终盘诊断与纠偏 | 归诊断/修改建议领域，不能由反思冒充 | V2 每日记忆反思负责整理有来源的认识，不等同于 V1 的运行巡视、异常诊断、次日建议、低风险修改及效果回看。按诊断与配置实施路线单独验收。 |

V1 关键依据：[本地画像](../../astrbot_plugin_private_companion/user_memory.py)的 `_maybe_refresh_companion_memory`、[私聊正本字段](../../astrbot_plugin_private_companion/authoritative_private_memory.py)的 `PRIVATE_MEMORY_FIELDS`、[多领域桥接](../../astrbot_plugin_private_companion/memory_companion_adapter.py)、[纠正传播](../../astrbot_plugin_private_companion/memory_revision_adapter.py)的 `run_memory_correction`、[双向来源交接](../../astrbot_plugin_private_companion/source_delivery_runtime.py)。

## 旧记忆插件能力专项对照

| 能力 | V2 分类 | 源码证据与边界 |
| --- | --- | --- |
| 每轮常驻核心记忆块 | 已覆盖私聊核心入口 | `context_mode=pinned` 与 retention 分离，按当前权限与证据读取；独立条数/字符预算、核心优先、去重、遗漏说明和本轮纠正续答已接入。`protected` 仍仅是保留/治理级别。 |
| 事实、偏好、归因、纠正与回执 | 已覆盖私聊核心 | V2 `models.py`、`writer.py` 有开放谓词、否定、限定条件、证据、原子提交、版本和操作记录。待处理提议不自动当成事实。语义抽取质量仍需真实模型评估。 |
| 同一人跨私聊会话记忆 | 已覆盖指定范围 | `owner_key` 包含安装、Bot、角色、可信用户，不包含 session。`durable` 可在同一归属的其他私聊会话召回；`session` 仍限制在原范围。来源须通过当前授权和原角色复核；这不是按昵称串号，也不能推导出所有平台和账号关联都已实测。 |
| 群聊普通发言、成员归属及可见性 | 未接入 | 旧 `handle_group_message` 具有独立捕获入口；V2 `Proposal.visibility` 和来源读取当前仅支持 private。不能将私聊画像直接投影到群里，也不能将群友转述自动记到被提及者名下。 |
| 入站及 Bot 已确认回复的双向原文 | 私聊普通回复已接入 | `ConfirmedReplySources` 复核 delivered 回执、原身份、入站/工具依赖，供原文查询和反思使用。Bot 归因保留，过期查询不复活；后台主动消息的 Memory 来源适配仍单列。 |
| 原文/媒体字段的敏感凭据清洗 | 文本新写入已接入，媒体/历史仍待补齐 | 共享来源层在入站持久化前清洗，HMAC 保留脱敏前冲突判断；记忆、经历和反思已解析输出同样清洗。未承诺历史数据、媒体字段或任意个人信息的全量处理。 |
| 中文全文、原文续读、时间和主体查询 | 已覆盖基础查询，历史检索部分 | 中文索引、原文续读、时间窗、主体过滤和共享预算已有；管理 API 可按 atom_id 分页审阅授权历史修订。`at_time` 仍只检查当前 active revision，尚无跨事实历史全文检索。 |
| Embedding、融合、重排和去重复召回 | 部分 | V2 有显式向量写入、模型标识校验与 RRF 融合底座；宿主未接自动 Embedding provider，角色工具也不接受向量参数。旧检索链的自动向量生产、Rerank 和 MMR 未接替，不能把“支持传向量”写成完整语义召回已上线。 |
| 经历与人物/物件导航 | 已有新框架替代底座 | V2 `MemoryExperiences` 保存证据、事实版本及经历关联；实体标签不绑定平台身份。它不是旧知识图谱的完整替代，自动建图、图检索和管理入口仍未接齐。 |
| 日常整理、会话总结及失败恢复 | 新方案已落地一部分 | 每日反思和待处理提议采用新设计，不复刻按条数晋升；有持久任务、预算及重复提交控制，默认未开启定时反思。但旧双向会话总结、坏批隔离、新批优先和修复流程仍需专项对照，不能仅凭“有每日任务”判为等价。 |
| 保留、到期、自然衰减与冷归档 | 部分 | V2 已支持 session/short/durable/protected 和读取时有效期检查；尚未看到完整的自动衰减、冷归档、容量治理与恢复流程。新实现应按设计处理来源和生命周期，不照搬旧固定分数。 |
| 管理页面与指令 | API 已补一批，完整页面仍待接入 | `memory_api.py` 支持列表、更正/撤回/遗忘、置顶、历史修订和事实清理预览/执行、统一配置。完整事实页面、旧指令迁移与候选采用管理入口仍未完成；现有“关系与记忆”页属于 relationships。 |
| 历史聊天导入、导出恢复、旧库迁移 | 未接入 | 旧插件有历史导入批次的暂停/恢复/回滚和 JSONL 导出导入。V2 `legacy/catalog.py` 仅登记旧来源及 handler 名；内部 v20→v21 建表不等于读取和迁移 V1 数据。 |
| 跨拓展查询、注入与变更传播 | 内部能力已有，稳定外部合同未启用 | 有内部 `memory.*` 工具、变更记录和来源依赖；仍不能据此宣布设计中的 `memory.*.v1` 封套、能力协商及全部领域消费者已接通。 |
| 大数据量检索 | 默认事实词法查询已增量化，其他路径及规模验收待补 | [增量召回](CORE_MEMORY_INCREMENTAL_RECALL_SLICE_20260924.md)已接分批建索引、按变更更新及命中后正本复核；原文、经历、all 和显式 vector/hybrid 仍沿原读取路径。有限候选数不构成 SQLite 总工作量或墙钟上限，自动语义检索、其余投影和规模验收仍待补。 |

旧插件依据：[service.py](../../astrbot_plugin_remember_you/core/service.py)、[retrieval.py](../../astrbot_plugin_remember_you/core/retrieval.py)、[source_capture.py](../../astrbot_plugin_remember_you/core/source_capture.py)、[commands.py](../../astrbot_plugin_remember_you/core/commands.py)。

V2 依据：[事实与归属](../companion_v2/memory/models.py)、[授权/来源](../companion_v2/memory/access.py)、[Writer](../companion_v2/memory/writer.py)、[自动上下文](../companion_v2/memory/context.py)、[查询](../companion_v2/memory/query.py)、[检索索引](../companion_v2/memory/search.py)、[原角色工具](../companion_v2/memory/tools.py)、[反思](../companion_v2/memory/reflection.py)、[管理 API](../astrbot_host/memory_api.py)、[入站来源](../companion_v2/adapters/astrbot/inbound.py)、[关系解释消费者](../companion_v2/conversation/relationship_context.py)、[旧来源目录](../companion_v2/legacy/catalog.py)。

## 已有测试证明什么

- [记忆对话测试](../tests/test_memory_conversation.py)：原角色通过工具保存、查询、纠正与续答，以及后来私聊会话的召回。证明合成工具链可接续，不证明模型会在所有表达下正确选择工具。
- [记忆边界测试](../tests/test_memory_boundaries.py)：同一 owner 跨私聊 session、session 记忆隔离、人格切换不继承、并发纠正、当前授权不能被历史时间绕过、索引重建。
- [记忆查询测试](../tests/test_memory_query.py)：中文召回、原文分页预算、游标失效及显式向量排名；手工向量测试不证明自动 Embedding provider 已接好。
- [写入](../tests/test_memory_writer.py)、[经历](../tests/test_memory_experiences.py)、[管理](../tests/test_memory_management.py)、[反思](../tests/test_memory_reflection.py)及[宿主 API](../tests/test_memory_host_api.py)覆盖对应内部切片；它们没有把上述全部 V1 缺项补成可用功能。

263 是上一轮特定快照的记忆及关联宿主定向测试结果，包含其他领域的回归；9 月 23 日对照只审阅源码和已有测试，9 月 24 日私聊完善切片另执行 115 项。数字不累加为 V1 对等覆盖率，其他窗口的新增用例不算作此批已执行。

## 后续补齐顺序与验收出口

1. **私聊基础使用缺口本轮已补一批。** 共享来源凭据清洗、可信 Bot 普通回复原文和核心常驻记忆的独立预算入口已落地，合成测试覆盖索引失败降级、归因、撤回、纠正和工具续答。媒体/后台来源和实际语义质量继续单独验收。
2. **补完整召回与治理流程。** 接统一模型服务的自动向量生产、重排/去重复、增量索引与有界取数；授权历史修订和私聊事实批量预览已有，后续补全主体/跨领域治理及完整事实页面。继续验收同义改写、服务降级、重启后不复活和操作者/主体分离。
3. **补群聊与领域消费者。** 先通过可信身份和群受众授权，再接群消息；逐个接照片、作品、活动、日记与主动候选的来源/纠正链。使用转述、同名成员、切换角色、来源撤回等反例，不用关键词表决定记忆归属。
4. **最后进行迁移与替换验收。** 先用合成 V1 非空档案验证映射、冲突、预览、回滚、导出恢复和禁复活；稳定跨拓展合同、配置生命周期及线上语义验收分别记账。真实 V1 数据迁移是独立切换工作。

后续实施按上表闭合用户流程。已确认由新方案替代的旧算法无需照搬；尚未接入的用户能力也不能直接标记为“已移除”。
