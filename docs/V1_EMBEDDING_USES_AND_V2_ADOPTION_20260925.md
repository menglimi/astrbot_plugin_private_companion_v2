# V1 嵌入模型用法与 V2 承接建议

记录日期：2026-09-25。状态：V1 用法研究与 V2 接入核对；本文新增的接入链路已经落到当前源码，真实 provider 相关性和现场投递效果仍待验收。

本轮检查了 V1 本体、Remember You 记忆扩展及 V2 当前源码和配置 schema。没有读取 V1 用户数据、数据库、真实配置或日志，没有调用线上模型、发送消息或重载插件。下文“已实现”指找到生产调用链，不代表当前安装已启用或真实模型效果已经验证。

V1 的嵌入模型覆盖三个直接用途：按回应意图选表情、为陌生群内表达寻找相近释义、从不同措辞中召回相关记忆。值得承接的是各自完整的输入、学习、检索与采用过程。V2 当前已接入共享嵌入网关、记忆自动向量化、表情素材检索与视觉复核、群词义学习和语境召回；页面也已提供真实配置、素材管理和索引状态。是否启用、模型是否可用及真实相关性仍由当前配置和现场 provider 决定。

## 1. 已核实的 V1 用法

| 用途 | 实际进入向量模型的内容 | 结果如何被使用 |
| --- | --- | --- |
| 表情包检索 | 名称、画面描述、可见文字、标签、情绪、沟通用途；查询包含需求及回应语境 | 与词法匹配、使用记录、偏好共同选图，满足条件时做视觉复核，再进入图片投递链 |
| 群内黑话联想 | 已有“群内表达＋含义＋用法”；查询是本轮提取到的陌生短表达 | 最多两条相近释义作为本群回复提示材料，不直接写成新词义 |
| 长期记忆召回 | 记忆类型、范围、标签、正文、摘要、关键事实及证据等；查询是检索意图 | 与关键词、当前窗口和时间候选合并，可选重排，再交给后续回复使用 |

### 表情包：检索的是“我想怎样回应”

1. 素材导入后，视觉模型建立画面、文字、情绪和沟通用途元数据。提示词要求看不清就不要猜，避免只给“图片”“表情包”等无区分度标签。[视觉分析提示词][v1-reaction-analysis]
2. 嵌入模型处理的是这些文本元数据，当前实现没有把图像直接编码为多模态向量。[索引文档][v1-reaction-document]
3. 检索上下文包括用途、情绪、强度、当前语境、候选检索表达及用户偏好。查询向量在工具执行链实际生成，并传入素材检索器。[回应意图][v1-reaction-intent]、[查询接线][v1-reaction-call]
4. 素材相似度容易集中在较窄区间。V1 在至少八个有效向量、最佳相似度达到阈值时，按本轮最高分和中位数计算相对加分，并降低偶然标签命中的影响；否则保留混合加分。近期使用惩罚与偏好影响最终选择。[混合排序][v1-reaction-ranking]
5. 向量主导且满足复核配置时，视觉模型再次判断实际图片是否贴合。明确不贴合则不发；无视觉模型、复核失败会返回空复核并继续依赖元数据，低延迟路径跳过复核。因此不能把 V1 描述成“每张图片都已确认”。[视觉复核][v1-reaction-review]、[投递前采用][v1-reaction-send]
6. 新素材和元数据变更触发后台补向量；模型不可用或查询失败时回退本地检索。索引记录 provider 和元数据哈希。[后台补齐][v1-reaction-backfill]

示意：用户说“气死了”，角色先结合语境决定是安慰、陪着吐槽还是轻轻缓和，再检索适合这种回应的图片。仅把“气死了”向量化并挑最像“愤怒”的图片，可能把嘲讽、挑衅图选进来。这里描述的是承接时应保留的意图建模，不是一次真实选图结果。

### 黑话：先积累本群释义，再做近义联想

V1 先从群聊中积累短表达和出现次数；独立的低频语言模型任务根据群聊样例整理含义、用法、类型、证据与置信度。外部搜索是可选辅助，本群用法优先。自动结果不会覆盖标为人工校正或显式纠正的已有词义。[候选学习][v1-slang-learn]、[释义任务][v1-slang-explain]、[校正优先][v1-slang-correction]

当出现陌生短表达时，V1 再检索已有释义：检查前四十个词条中的合格项，只为其中前十二项计算匹配，达到 0.68 后取最多两条；缓存命中可避免重复调用，另有按群冷却。实际提示明确写着“只有结合当前原句确实说得通时才采用；不要把向量近似当成确定词义或用户纠正”。结果已接入群回复上下文。[近义召回][v1-slang-recall]、[回复接线][v1-slang-prompt]

这能辅助理解已有梗的近义说法。陌生暗号如果没有相关证据，嵌入模型不能凭相似分数推导出本群约定。

### 记忆：把不同说法连接到已有经历

Remember You 为新增或缺失索引的记忆后台生成向量，写入前检查正文哈希是否仍匹配。查询时调用嵌入模型，复核所属范围、可见性、生命周期和时间条件，再进行向量检索。[记忆索引文档][v1-memory-document]、[记忆补齐][v1-memory-backfill]、[查询向量][v1-memory-query]

关键词与向量候选并行召回，之后可选调用独立 rerank 模型。去重和 MMR 多样化也在后续链路中，但 V1 此处的 MMR 使用文本片段、标签等本地特征，不能把这些步骤统称为“嵌入模型实现”。[候选合并][v1-memory-merge]、[后处理][v1-memory-postprocess]、[MMR 特征][v1-memory-mmr]

## 2. V1 的真实配置关系

以下是 V1 schema 和调用代码中的名字，不是已经新增到 V2 的配置。

| 能力 | 开关与模型选择 | 实际行为 |
| --- | --- | --- |
| 通用语义嵌入 | `EMBEDDING_PROVIDER_ID` | 本体的表情和黑话可以共用；不会调用普通聊天模型冒充嵌入模型 |
| 表情检索 | `reaction_expression_embedding_enabled`、`REACTION_EXPRESSION_EMBEDDING_PROVIDER_ID` | 专用模型优先，其次通用模型；均未指定时可自动寻找可用嵌入 provider；schema 中嵌入开关默认关闭 |
| 黑话理解 | `enable_group_slang_learning`、`enable_group_slang_meanings`、`GROUP_SLANG_PROVIDER_ID` | 前两项管理学习/释义，`GROUP_SLANG_PROVIDER_ID` 用于语言模型释义；近义召回继承通用嵌入模型，兼容表情专用模型；两者都为空时跳过该向量层 |
| 记忆检索 | `retrieval.embedding_enabled`、`retrieval.embedding_provider_id` | 位于记忆扩展的独立配置；嵌入开关默认关闭，provider 留空时扫描可用嵌入模型，并非自动继承本体通用设置 |
| 记忆重排 | `retrieval.mode`、`retrieval.rerank_provider_id` | 独立于嵌入模型，失败可退回本地排序 |

来源：[本体通用模型说明][v1-shared-schema]、[表情模型解析][v1-embedding-resolution]、[共用模型继承][v1-embedding-inheritance]、[表情开关][v1-reaction-schema]、[记忆 schema][v1-memory-schema]。

## 3. V2 当前接入状态与剩余验收

| 项目 | 源码现状 | 完整承接还需要什么 |
| --- | --- | --- |
| 记忆向量底座 | `MemorySemanticRecall` 在可信服务内生成查询和资料向量；按 owner、模型、正文哈希隔离，支持后台补齐、混合排名和可选当前页重排 | 真实 provider 的维度、限流、相关性和长时间回填仍需按部署验收；模型切换后的旧向量需要观察覆盖恢复 |
| 普通记忆工具 | `memory.query` 只接收查询意图等文本参数，服务自动生成向量并交给已有查询器复核；模型不能编造向量 | 需要用真实记忆规模验证回填耗时、失败恢复和跨措辞召回；无 provider 时明确回退关键词检索 |
| 表情表达 | 已有 V2-only 素材库、原图/GIF 导入、视觉标注、语义与关键词混合检索、近期重复惩罚、视觉复核、来源发布和现有图片投递接线；同步发送、迟到回执及显式对账均按已送达清单幂等记录使用 | 真实视觉/嵌入 provider、QQ 客户端显示与低延迟路径仍需现场验收；模型失败时保留关键词结果，复核不通过时不采用 |
| 群内语言 | 已有群词条证据、自动学习、人工/显式纠正、按群 owner 隔离、语境召回、回复提示接入和来源失效校验 | 真实群消息样本、纠正流程和学习周期需现场验收；没有证据的陌生暗号仍不会凭相似分数生成词义 |
| 模型设置 | `SemanticWebAPI` 提供嵌入、重排、视觉/词义分析 provider 选择、开关、超时、批次和索引状态；宿主适配位于 `astrbot_host/` | 当前已通过合成 provider 和 Dashboard API 测试；实际安装要确认 provider 能力清单与授权对象选择 |

证据：[V2 查询接口][v2-query]、[向量写入][v2-vector-write]、[混合排名][v2-vector-rank]、[记忆工具][v2-tools]、[群公共记忆查询][v2-group-query]。页面内保留的 V1 功能清单不作为 V2 已实现证据。

## 4. 建议的承接方式

共用嵌入模型接入、缓存、批量任务和统计；各领域保存自己的资料及采用逻辑。宿主 provider 适配放在 `astrbot_host/`；嵌入请求/结果合同与调度放在 `companion_v2/model_gateway/` 的独立子模块；记忆继续归 `memory/`，群词义可以沿 `memory/group/` 扩展；表情素材与选图按明确业务建立领域模块，接入现有媒体投递服务。核心领域不反向导入宿主。

承接顺序已经完成：共享模型网关、记忆自动索引、表情完整链路、群词义完整链路和管理页真实状态均已接入。后续验收应按“素材或证据进入 → 召回 → 角色采用”逐条使用真实 provider 验证，而不是只看页面显示为已配置。

需要在承接时调整的 V1 细节：

- 黑话查询目前主要编码候选词串，缺少原句中的语气、否定和对象。V2 应带必要的原句上下文，并提示模型判断是否为反话、旧梗或普通用语。
- 黑话先截取四十项、再取十二项计算，后面的相关词可能一直进不了候选。V2 应使用按群索引和可续扫检索，输出当前覆盖情况。
- 黑话结果缓存键含群标识和候选词串，缺少词库修订和模型版本。V2 应把 owner、资料修订和 provider/model 指纹纳入缓存；人工纠正后及时失效。
- V1 黑话向量调用复用了表情函数和超时设置。V2 应拆成共同嵌入服务，分别保留任务超时、优先级及失败诊断。
- 保留元数据变更后重建向量、后台补齐、关键词回退、可不发图、人工纠正优先等行为。内容是否合适主要交给有语境的提示词和模型判断；身份、资料归属和真实投递仍走现有程序校验。
- 表情高分只表示候选相关，不能等同于视觉复核通过；群词义高分也不能当作事实置信度。管理页应呈现实际检索方式、索引覆盖及复核状态。

小屋管理入口复用已有导航：语义与表情页集中配置语义嵌入，显示模型状态、索引覆盖、关键词回退，并管理表情与群词义；普通私聊自动召回相关事实和共同经历，记忆页仍以来源和修订校验为准。能力未接好时不显示“已启用”。后续仍可在关系、兴趣和世界书工作台补充更细的命中来源展示。

## 5. 可继续扩展的用途

| 建议 | 具体价值 | 与本次源码结论的关系 |
| --- | --- | --- |
| 表达偏好检索 | 用户说“不用一直给我打气”时，召回已有的安慰方式偏好，让角色调整语气 | V1 已有偏好参与表情选择；“通用偏好语义检索”仍需独立设计 |
| 共同经历与事件梗 | 用“上回那个乌龙”寻找相关经历，再读取原证据确认是哪件事 | 可沿用已有记忆召回；是否同一事件由来源和语境核对 |
| 角色知识、世界书 | 当前问题只召回相关设定，减少整本设定塞进提示词 | 本轮未找到 V1 本体 `worldbook.py` 直接调用嵌入模型的证据，属于扩展建议 |
| 内容兴趣匹配 | 阅读/分享候选按兴趣语义找到相关项，同时参考近期是否分享过 | 属于后续设计，不能由本轮研究宣称 V2 已实现 |

## 6. 定向验证与后续扩展

已用合成素材和 provider 定向验证：表情的意图召回、视觉复核、近期重复使用、无 provider 时关键词回退、GIF 原图保留与投递；黑话的同词异群、人工纠正后的结果失效、来源撤回和后部词条召回；记忆的措辞变化、资料自动向量化、模型切换隔离、重排失败回退；管理 API 的登录身份、配置 CAS、对象/群会话隔离和停机注销。下一步只需用实际配置的 provider 验证相关性、延迟、额度和 QQ 展示效果，并记录真实结果与合成结果的差异。

本轮 AstrBot 自带 Python 定向运行 `tests/test_semantic_integration.py` 与 `tests/test_semantic_host_api.py`，共 17 项通过，覆盖普通事实、共同经历的自动语义召回及嵌入失败后的关键词回退，也验证了表情真实送达记账、近期降重、重启后迟到回执幂等记账、黑话来源撤回和同轮人工纠正。测试使用本地替身 provider 和临时数据根，不代表真实模型或真实 QQ 投递已经验收。

[v1-reaction-analysis]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/page_api.py:2975
[v1-reaction-document]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/reaction_asset_library.py:460
[v1-reaction-intent]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/llm_tool_actions.py:5997
[v1-reaction-call]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/llm_tool_actions.py:7199
[v1-reaction-ranking]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/reaction_asset_library.py:1234
[v1-reaction-review]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/llm_tool_actions.py:6952
[v1-reaction-send]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/llm_tool_actions.py:7380
[v1-reaction-backfill]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/llm_tool_actions.py:5789
[v1-slang-learn]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/group_observation.py:2165
[v1-slang-explain]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/group_observation.py:5033
[v1-slang-correction]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/group_observation.py:5195
[v1-slang-recall]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/group_observation.py:3048
[v1-slang-prompt]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/passive_state_pipeline.py:589
[v1-memory-document]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_remember_you/core/models.py:428
[v1-memory-backfill]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_remember_you/core/service.py:4179
[v1-memory-query]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_remember_you/core/retrieval.py:1623
[v1-memory-merge]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_remember_you/core/retrieval.py:1353
[v1-memory-postprocess]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_remember_you/core/retrieval.py:262
[v1-memory-mmr]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_remember_you/core/retrieval.py:661
[v1-shared-schema]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/_conf_schema.json:5087
[v1-embedding-resolution]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/llm_tool_actions.py:5585
[v1-embedding-inheritance]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/llm_tool_actions.py:5637
[v1-reaction-schema]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/_conf_schema.json:13164
[v1-memory-schema]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_remember_you/_conf_schema.json:458
[v2-query]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/memory/query.py:179
[v2-vector-write]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/memory/search.py:179
[v2-vector-rank]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/memory/recall_vectors.py:30
[v2-tools]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/memory/tools.py:15
[v2-group-query]: C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/memory/group/service.py:73
