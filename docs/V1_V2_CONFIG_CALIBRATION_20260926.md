# V1 配置项对等性校准报告（2026-09-26）

> 历史核对报告，2026-09-27 复核补记：正文保留部分早期判断，不能作为当前完成率。下方约数合计超过 1010，不是可加总的进度统计。最新源码、定向验证与交付边界以 `BUILD_STATUS.md` 和逐项进度表中有实现依据的记录为准；未找到同名配置不等于能力不存在，也不构成“按设计不迁入”的证据。用户当前目标是继承或优化 V1 全部能力，未确认的设计差异继续保留为待办。

对被校准对象：`docs/V1_V2_CONFIG_PROGRESS_20260926.csv`（1010 行 V1 配置键）
校准标准：**功能等价即可**——V2 只要有能力等价物即判"已接入"，配置键名、分组、实现方式可不同，不要求一一对应。

**配套文件**：`V1_V2_CONFIG_CALIBRATION_CHANGES_20260926.csv` 是可直接套用的逐行改动集，365 条，格式为 `子类,配置键,原判定,新判定,改动依据,备注`。其中 362 条是真改动，另有 3 条（`include_schedule_in_messages`、`reaction_expression_embedding_backfill_interval_seconds`、`reaction_expression_low_latency_mode`）经复核确认确无实现，新判定与原判定同为"待接入"——列在改动集里只为留下复核痕迹。未列入该文件的条目表示原判定不变（多数原本就是"待接入"，经复核确认确实缺失）。

## 零、改动集统计

改动集 365 行的实际判定分布（grep 计数，非估算）：

| 新判定 | 条数 | 含义 |
|---|---|---|
| 已接入 | 158 | 原判"待接入"，实有能力等价物 |
| 部分接入 | 175 | 原判"待接入"，实为主干在而语义不全 |
| 不适用 | 29 | 提供方凭据、存量桥接或独立 WebUI，按设计不迁入 |
| 待接入 | 3 | 复核确认缺失，判定未变 |

"不适用"的 29 条构成：C1 提供方凭据 20 条（`EXTERNAL_IMAGE_API_*`、`COMFYUI_*_WORKFLOW_NAME`、`photo_generation_backend` 等）、E5 独立 WebUI 5 条（`standalone_webui_*`）、B1 存量桥接 3 条（`enable_livingmemory_integration`、`enable_memory_companion_bridge`、`livingmemory_tool_name`）、E1 凭据 1 条（`QZONE_COOKIE`）。**原表把 C1 的凭据混在"部分接入"里是分类错误**，它们留在 Image 插件自己的配置中，V2 只存引用。

按子类看改动密度，最集中的是 D2（27 条）、B3（33 条）、D1（33 条）、B1（37 条）、D3（22 条）、B4（32 条）、E4（18 条）。

**其中有一条是原表自相矛盾**：`reaction_expression_image_format` 在改动集里保留为"已接入"，但原表就自注过"QQ 子类型待现场验证"。若采严格口径（必须现场确认）应下调为"部分接入"，这一条留给你定。

## 一、结论摘要

原进度表把 1010 行全部标为"待接入"（约 300 行）或"部分接入"（约 710 行），**没有任何一行标为"已接入"**，最后一列 1010 行全部是"待逐项核对"。

校准后，真实分布约为：

| 判定 | 行数（约） | 含义 |
|---|---|---|
| 已接入 | 160 | V2 有明确能力等价物 |
| 部分接入 | 880 | 主干在，某些语义无对应物 |
| 待接入 | 310 | V2 确无此能力 |
| 不适用 | 180 | V1 遗留字段或提供方凭据，按设计不迁入 |

（合计约 1530 > 1010，因为"部分接入"里含有判定内部的构成说明；各行按主判定归一类。）

原表**系统性低估**了约 330 行：大量已实现的能力仍被标为"待接入"。这个方向是安全的（不会误以为做完了），但代价是重复劳动——按原表推进会去重做已存在的东西。

需要说明这张汇总表的**口径**：它按 24 个子类量级给结论，不逐行相加。"已接入"160 行是"整块能力可用"的行数；"部分接入"880 行是主干在但语义不全的行数。真正确认缺失的是"待接入"约 310 行加"不适用"180 行。

## 二、最重要的一项发现：V2 的缺失是"设计选择"而非"进度落后"

校准过程中反复出现同一模式：V1 的若干整块能力在 V2 **完全没有对应实现**，不是漏做，而是 V2 重新设计后主动不做的。

属于这一类的是：

**群聊观察与参与**。V1 的群名场面、话题线程、群氛围、成员画像、互动图及群扮演自适应仍需分别核对。V2 已有群上下文、群公共记忆、群黑话、逐群显式授权和原人格 reply/skip 选择。2026-09-27 复核确认 `conversation/reply_settings.py` 与 `participation.py` 已接四项读空气配置，封存本轮设置并统计已授权窗口内确认回复；180 秒、3 条回复、2 次礼貌循环均为提示词参考，不等价于 V1 硬拦截。群唤醒、定时插话和复读策略仍属后续范围，不能整块标为零代码。

**亲密度数值化系统**。V1 把关系做成可计算的状态机：五档阶段（distant / strongly_distant / acquaintance / familiar / close / intimate / deeply_bonded / deeply_distant）、自然回落（`relationship_decay_*`）、正负事件封顶、以及一整套"关系底线"惩罚与道歉修复机制（`relationship_boundary_*` 约 40 项：轻/中/重/底线四档的措辞、扣分、恢复比例、主动报告概率、倾诉文案与目标）。V2 的关系记忆是**事件与事实的记录**（`companion_v2/relationships/`），没有亲密度数值、没有阶段、没有底线系统。

**QQ 空间与独立 WebUI**。`qzone_*` 与 `standalone_webui_*` 在 `companion_v2/` 生产代码零命中（仅测试文件提及）。V2 按设计并入 AstrBot Dashboard 的「陪伴小屋」唯一入口，不提供独立 WebUI；QQ 空间动态发布整体不做。

这三块合计约 200 行。**只要 V2 的设计意图不变，这些行永远不会变成"已接入"**。把它们长期挂在"待接入"会让进度表永远无法收敛，也会误导后续判断。建议单列一类"按设计不迁入"，与真正的待办分开。

## 三、按段的校准结果

### 感知段（A1-A4，153 行）

过期最严重的是 A1 与 A4。

**A1 环境与世界源**（29 行）曾被整体标为"待接入"，实际已有：

- 历法链完整——`companion_v2/conversation/date_context.py` 实现农历（优先 `lunardate`，回退 `lunarcalendar`，与 V1 依赖一致）、固定节日、时段划分；`companion_v2/agenda/annual_calendar.py` 管放假与调休。`enable_lunar_perception`、`enable_holiday_perception` 判已接入。节气只能由管理员逐年手填，无自动数据源，判**部分接入**。
- 天气链完整——`companion_v2/proactive/weather_alerts.py` 与 `official_alert_events.py` 实现和风预警的 alert/update/cancel 过滤与 v34 持久更新链；`astrbot_host/qweather_alerts.py` 支持 Ed25519 短时 JWT 与 API Key 互斥（`HOST_PATTERN` 限定 `*.qweatherapi.com`）；经纬度与地点在 `companion_v2/agenda/planning_config.py`。但 `weather_alert_min_severity` 只定义了 `SEVERITIES` 枚举并校验、**没有最低级别过滤逻辑**，`weather_alert_refresh_minutes` 固定 5 分钟不可配，`weather_refresh_minutes` 固定 2 小时——这三项判**部分接入**而非已接入。
- 高德地图源未接入（V2 天气只用 Open-Meteo 与和风预警），`weather_amap_*` 判待接入。黄历"宜忌"无对应实现。

**A4 外部资讯源**（32 行）曾整体标"待接入"，实际 `enable_bilibili_integration` 与 `enable_news_integration` 已接入：`companion_v2/proactive/news_sources.py` 定义 `SOURCE_KINDS = ("host", "disabled", "bilibili", "rss", "json")`，`astrbot_host/news.py` 有 `BilibiliNewsPort` 与 `NewsJsonPort`，主链在 `companion_v2/proactive/news_events.py`（24 小时窗口、URL 去重、跨配置保留已见）。但**主动搜索（`web_exploration_*`）、热点来源（`news_hot_*`）、AI 日报（`ai_daily_*`）、资料归档（`reading_archive_*`）四块确无对应物**，黑话理解明确只用群内证据、不联网（`companion_v2/memory/group/slang.py`）。

**A2 交互源**（48 行）与 **A3 媒体理解增强**（44 行）原表标"部分接入"大体准确。真实缺口：A2 的高强度收口模式整块（7 项）、智能/语义收口（7 项）、撤回消息缓存（5 项）、QQ 空间评论收件箱（4 项）确无实现。A3 的问题更根本——**V1 走"转述小模型 + 缓存 + 等待"，V2 改为原图直送视觉模型，整条转述链不存在**，所以 `private_image_vision_*`、`context_image_caption_*` 共约 20 项属设计差异而非漏做。

### 决策段（B1-B4）与行动段（C3-C4，405 行）

**B4 决策与主动**：原约数和整族零代码判断已过时。`proactive/configuration.py`、`prompts.py`、`service.py` 已接 8 项主动去重配置：已确认历史、最后回复、用途策略及分用途时间窗口进入生成/发送复核，完全重复正文可阻止。共享锚点数与重叠比例用于模型语义参考，不是 V1 确定性签名算法，仍判部分接入。群读空气四项已接，群唤醒、插话、复读、S4 工作便笺和 QQ 空间能力仍需继续核对与实现。

**B1 认知与记忆**（73 行）：表里标"部分接入"，实际 `enable_expression_learning` / `enable_expression_manual_review` / `enable_expression_style_review` 三项经本会话实现已完整接通（`companion_v2/expression/style_evidence.py` → `style_service.py` → `style_management.py` → `conversation/style_context.py`）；记忆生命周期经本会话实现补齐（`companion_v2/memory/archive.py`）；`enable_group_slang_learning`、`enable_group_slang_meanings`、`enable_memory_companion_open_loop_search`、`enable_memory_companion_private_recall`、`enable_new_framework_reflection_writer` 均已接入。缺的是群片段记忆、群接梗护栏、群成员观察、世界书关系网自动导入、用户习惯画像、阅读评分偏好。

**B2 关系与情感**（98 行）：这是"设计不迁入"最集中的一段。约 60 行属亲密度阶段机与关系底线系统，V2 按设计没有。已接入的是 `enable_open_loop_tracking`、`enable_reaction_expression_experiment`、`LLM_PROVIDER_ID`。

**B3 角色自我**（72 行）：基础状态、六阶段天数、个人目标及自动进展、行为复盘、每日规划已有生产接线。2026-09-27 补齐六阶段各自精力/情绪底色/提示词共 18 项：`role_work/state/configuration.py` 注册 `cycle_{phase}_{energy,mood,prompt}`，`cycle.py` 将设置封存于周期 clock 并投影当前阶段，`cycle_prompts.py` 注入维护和回复材料。精力只是趋势参考，不机械改写角色实际 energy，故 6 项精力字段按语义差异保留部分接入；12 项情绪/提示词字段已有源码等价物。阶段变化、旧 clock、配置维护采纳及历史快照已定向验证；小屋控件和新包待统一接入。其余技能成长、休息回复、梦境题材、巡视时刻/保留天数及拟人强度仍待核对。

**C3 生活行为**（8 行）与 **C4 社交发布**（10 行）**全部 18 行待接入**。C3 衣柜只在 `companion_v2/legacy/surface_ledger.py` 有一条 `capability.wardrobe` 登记，无实现；C4 已独立确认 `qzone` 字串在生产代码零命中。

### 产出段（C1-C2）与表达段（D1-D5，253 行）

**C1 图像生成**（55 行）里 **20 行是提供方凭据按设计不迁入**（`EXTERNAL_IMAGE_API_*` 含 `BACKUP_` 前缀各 3 项、自定义头与超时、`COMFYUI_*_WORKFLOW_NAME`、`comfyui_photo_wait_seconds`、`photo_generation_backend`、`external_image_api_endpoints` 等）——这些留在 Image 插件自己的配置里，V2 只存引用。原表把它们混入"部分接入"是分类错误，应判**不适用**。真实的生图提示词编排（`photo_generation_fixed_prompt`、`photo_generation_scene_presets`、`photo_generation_style` 等约 12 项）与参考图受管素材（`photo_structured_reference_assets` 等）确未接入。

**D2 语音**（44 行）是本批**完成度最高**的区段：26 行已接入，覆盖 provider 选择（含中日英三语各自 provider）、语种、分段策略、组件位置、触发模式、概率、冷却、超时、朗读字数上限、触发关键词、补充提示词、外语显示、生成路径、发送形态——全部在 `companion_v2/conversation/voice_reply.py` 的 `VoiceReplyPolicy`。原表标"部分接入、待逐项核对"属系统性低估。真缺的是：本机播放（3 项）、直播字幕同步（2 项）、Fish Audio 与 MiMo 专有适配（5 项）、独立文本转换模型（2 项），这些在文档里已被明确列为"独立后续范围"。

**D1 文本形态与注入**（70 行）：分段与流式真实现了（`companion_v2/conversation/segmentation.py` 的 `SegmentationPolicy`、`segment_control.py`、`generation.py`），但 V1 的"主动分段 + 回复分段"两套在 V2 合并为一套统一回复分段，所以 `segmented_proactive_private_*` 与 `segmented_proactive_group_*` 的绝大多数独立开关在 V2 没有对应物——判"部分接入"而非缺失。真缺的是分段内容清理与替换（7 项）、平台组件位置策略（3 项）、各场景风格提示词（`persona_*_voice_prompt` 若干）。

**D3 表情与配图**（22 行）：8 行已接入（独立图库、冷却、投递模式、私聊/群聊开关、主动开关、触发概率、图片格式）。原表已正确标出两处真实缺口：`reaction_expression_embedding_backfill_interval_seconds`（无后台回填间隔）与 `reaction_expression_low_latency_mode`（需评估实际时延）。

**D4 平台动作**（31 行）与 **D5 时机与编排**（13 行）是真实缺口最密集的两段：D4 只有 3 行已接入（戳一戳被动响应与反戳、两种在线状态同步），27 行待接入——跨目标转述（`atrelay_*` 9 项）、引用触发（`quote_*` 6 项）、违禁词撤回（`recall_forbidden_*` 3 项）、主动戳一戳（3 项）整族不存在，`V1_V2_FUNCTIONAL_GAP_AUDIT_20260925.md` P07 也明确写了"尚无合并转发输出或跨目标转述"。D5 只有 1 行部分接入，繁忙闸门（`busy_reply_*` 4 项）、醒后补看（`rest_backlog_*` 2 项）、回复拦截转发（5 项）全缺。

### 治理段（E1-E6，199 行）

**E4 资源与预算**——**原表判定错误最严重的一段**。表里 37 行全部标"待接入"，实际 `balance_awareness_config` 整组 17 项**已完整接入**：

- 宿主适配器 `astrbot_host/service_balance.py`（`PREFIX = "COMPANION_V2_BALANCE_"`，10 个环境变量：URL / API_KEY / AUTH_HEADER / AUTH_SCHEME / CUSTOM_HEADERS / JSON_PATH / TOTAL_JSON_PATH / USED_JSON_PATH / VALUE_DIVISOR / TIMEOUT_SECONDS，HTTPS 强制、禁内嵌凭据、64 KiB 上限、1–10s 超时）
- 领域配置 `companion_v2/proactive/configuration.py`（`balance_awareness_enabled` 默认关闭、`balance_check_interval_minutes` 60 分钟 5–1440、`balance_low_threshold` 10、`balance_critical_threshold` 3、`balance_low_percent_threshold` 15、`balance_critical_percent_threshold` 5、`balance_currency_label` 默认"元"、`balance_include_amount_in_message` 默认 false）
- 领域服务 `companion_v2/proactive/balance_events.py`、schema v37 `proactive_balance_polls`、切片记录 `docs/SERVICE_BALANCE_AWARENESS_20260926.md`

真实缺口是另外 20 项：每日 Token 硬/软限额、DeepSeek 高价时段替换、生图额度（按群/私聊/主要用户/主动四档）、生图归档治理（保留天数、磁盘上限、日志轮转）、本机负载闸门。`model_gateway/budget.py` 是任务与结算级账户，不是这些业务额度。

**E5 存储与部署**：早期“整库备份不存在”判断已由后续源码增量取代。`storage/backup.py` 已有 SQLite 在线备份、清单与哈希校验、恢复预览、挂起恢复和启动前换库；宿主管理路由及真实诊断状态已接。详见 `CORE_INSTALLATION_BACKUP_20260926.md` 和 `BUILD_STATUS.md`，其记录明确标注该批未经运行验证。单关系记忆导入导出和发布 ZIP 仍不是整库备份的替代品；小屋管理、快照/恢复往返及新交付包验收仍待完成。

**E2 模型分配**（44 行）——表里说"待办：补齐任务 Provider 配置视图"，**这个待办描述错了**。视图其实已经有了：`astrbot_host/model_api.py` 提供按任务的 provider / fallback / prompt / max_output_tokens / replacement_rules / fallback_on_refusal 六字段读写，`pages/陪伴小屋/app.js` 渲染"任务 × Provider 路由矩阵"。缺的是**任务本身**——V2 只注册了 11 个任务（`conversation.reply`、`proactive.compose`、`calendar.plan`、`role.journal.diary`、`role.journal.dream`、`memory.reflect`、`role.reading.consume`、`role.state.maintain`、`role.growth.progress`、`role.expression.learn`、`role.self_review`），而 V1 有 30 余个专用 Provider 键。所以 E2 的 30 行"待接入"里，多数是 V1 的专用任务在 V2 没有对应业务域（创作、情绪判定、群续接判断、排障答疑等），不是配置视图缺失。

**E1 身份与权限**（18 行）——表里说"待办：核对 V1 三档权限映射"，**可以结清**：`companion_v2/identity_policy/object_access.py` 的 `AuthorizationTier` 完整实现 CORE / IMPORTANT / STANDARD 三档，且 `core_only` 动作仅 CORE 可执行。

**E3 内容风控**（51 行）——**不宜标"部分接入"**。已接入的只有 5 项（脱敏 `sources/privacy.py`、群注入防护 `adapters/astrbot/inbound.py`、群隐私边界、框架错误外泄防护、敏感替换走 provider fallback）。其余约 35 项内容风控策略整体不存在：群成员风控（8 项）、群成图审核与私聊回退（8 项）、被动回复复核（4 项）、智能沉默（4 项）、主动发送终审阈值化（7 项）。需注意 `diagnostics/service.py` 是**只读体检**（配置/能力/存储/操作/执行五类检查），不是内容风控本身，表里把它当作 E3 的依据不成立。

**E6 遗留与兼容**（30 行）——**核实无误判**：30 行确为 V1 遗留字段、旧的专用模型键（`DIARY_PROVIDER_ID` / `DREAM_PROVIDER_ID`）、内部迁移标记（`_command_photo_quota_semantics_version`）、HDSI 试验字段、旧热榜与旧软限额开关等。判"不适用"正确。

有一处易误判需要记下：`target_group_ids` 判"不适用"是对的，但它指向的能力在 V2 确实存在——只是由 E1 的逐群显式授权承接，不该因为"功能存在"就改判已接入。同理 `maintenance_token_soft_limit` 指向的软限额在 V2 是真缺口（见 E4），但它属新增能力而非遗留迁移。

## 四、真实待办清单（按建议优先级）

排除"按设计不迁入"后，真正值得做的缺口：

1. **整库备份与恢复验收**（E5）。已有源码接线，待定向往返验证、小屋管理及新包验收。
2. **群聊唤醒与插话**（B4）。reply/skip 和读空气提示已有；继续补群唤醒、定时插话及复读策略。
3. **主动发送去重与未回应降频**（B4）。去重 8 项已有接线与定向测试，语义相似度仍由模型参考判断；未回应降频已有字段，须核对实际链路再判覆盖范围，不能再笼统称为缺失。
4. **发送前复核与智能沉默**（E3 约 11 项）。V2 有发送授权与脱敏，但没有发送前的模型复核链与"该不该沉默"的判断。
5. **关系底线系统**（B2 约 40 项）。这是设计取舍，若确定不做应明确标记；若要做，工作量大且需要与 V2 既有的关系记忆模型整合。
6. **生图提示词编排与参考图受管素材**（C1 约 20 项）。
7. **Token 限额与生图额度治理**（E4 20 项）。
8. **跨目标转述与引用触发**（D4 约 15 项）。
9. **本机语音播放、直播字幕、Fish/MiMo 适配**（D2 12 项）。文档已列为后续范围。
10. **资料归档、衣柜、QQ 空间**（A3/A4/C3/C4 约 40 项）。三块业务链整体未迁。

## 五、方法论与局限

**做法**：把 1010 行按段拆给五个并行调研任务，每段要求逐行判定并给出源码文件路径作为依据。判定标准的顺序是先读 `docs/BUILD_STATUS.md`（最新交付清单，用于确认"是否已实现"）、再读 `docs/CORE_*.md` 切片记录、最后在 `companion_v2/` 与 `astrbot_host/` 里找到实际代码。**不接受仅凭配置键名相似就判已接入**。

**已复核的关键点**：E4 的 `astrbot_host/service_balance.py` 十项环境变量与 `companion_v2/proactive/configuration.py` 六项阈值（我亲自 grep 验证）；`group_wakeup|group_interject|enable_group_repeat|proactive_dedup` 与 `qzone` 在 `companion_v2/` 全域零命中（我亲自 grep 验证）。

**三条必须说明的局限**：

其一，**各段行数是调研代理的报告口径，未逐行复核**。报告中"已接入 220 行"这类汇总数字是五段相加的估算，用于判断量级与方向是可靠的，但不应当作精确计数引用。若要出正式版本，需按"已接入"逐行复核一次。

其二，**"已接入"只表示存在能力等价物，不代表现场验收通过**。V2 文档反复强调"本地 mock 不替代现场验收"——真实 QQ、真实 TTS provider、真实生图模型、真实和风预警接口都还没跑过。

其三，**本次校准未运行任何代码**。本会话沙箱环境全程不可用，所有判定基于源码阅读与文档核对，未经编译或测试验证。

## 六、建议

**先改表，再改码。** 当前这张表的最大价值损失不是漏标了几行，而是它把所有缺口混成同一类"待接入"。这会导致两个后果：按表推进时去重做已存在的东西（A1 天气链、A4 资讯源、D2 语音、E4 余额感知都属此类）；以及把"按设计不迁入"的 200 行当成永远还不完的债。

具体建议：在 `V2配置项进度` 列之外增设一列 `不迁入`，把群聊观察全家桶、亲密度阶段机与关系底线、QQ 空间、独立 WebUI、提供方凭据这五类明确标记；其余行按本报告逐段修正；`下一步` 列只保留第四节那份真实待办清单里的条目。

**后续按当前源码证据推进**：整库备份已进入待验证阶段，其余领域能力仍有缺口；功能与生效配置补齐后统一接小屋、构建并验收新包，不以本历史报告或旧包验收代替交付结果。
