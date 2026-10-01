# V1 → V2「表情包 / 反应图片（reaction）」系统迁移差距审计

日期：2026-09-27
审计范围：V1 `astrbot_plugin_private_companion` 的反应图（表情包）检索、排序、复核、投递与配置；V2 `astrbot_plugin_private_companion_v2` 的对应现状。
取证口径：**只采信代码实证**，每条结论后方括号内给出 `文件:行号`。V2 文档自评（如 `docs/V2_GAP_CLOSING_TASKS_20260927.md`）仅用于对照批次编号，不作为能力证据。
约束遵守说明：未改动任何 V1 文件；未读取 V1 的 `data/` 目录（用户数据/数据库/日志/配置实例）；未运行完整测试套件；未改动 V2 业务代码。

## 〇、一句话结论与最重要的三个差距

**一句话结论**：V2 的 reaction 系统已经具备「素材库 + 混合检索 + 视觉复核 + 使用记录 + 偏好边界」的完整骨架，但在三个最影响选图质量的地方比 V1 明显退化——**亲和度模型只有全局标量而没有「按回应意图」的维度、向量在排序中只与词法等权相加（没有 V1 的分布相对排序与主导权切换）、以及完全没有低延迟缓存与容量/淘汰机制**；此外 V1 的 37 个 `reaction_*` 配置键里只有 10 个在 V2 有对应物。

最重要的三个差距：

1. **「按本轮回应意图」的偏好维度在 V2 完全缺失。** V1 为每个素材维护 `intent_scores`（按意图签名分桶的分数），并在排序里以 `intent_score * 0.16` 参与，同名素材在「安慰」与「吐槽」两个意图下会被拉开 [V1 `reaction_expression.py:154-204`][V1 `reaction_asset_library.py:1200-1204`]；V2 的 `reaction_affinity` 只有 `(owner, actor, id, score)`，`scores()` 返回的字典与意图无关 [V2 `companion_v2/storage/semantic.py:48-51`][V2 `companion_v2/expression/reaction_preferences.py:162-166`]，排序里只乘一个常数 0.08 [V2 `companion_v2/expression/reactions.py:115-118`]。用户对某张图在「安慰」场景下的好评，会同时抬高它在「吐槽」场景下的排序。

2. **向量只做「加分项」，没有 V1 的向量主导模式。** V1 在本轮向量候选数 ≥ 8 且最高相似度 ≥ 阈值时进入 `embedding_led` 分支：按本轮相似度分布相对排序给分（最佳=满分、中位=0），并把词法分封顶到 0.5，让词法只做同簇内的破平 [V1 `reaction_asset_library.py:1240-1251`][V1 `reaction_asset_library.py:1306-1327`]；V2 的公式是 `score = lexical * 0.25 + max(0, cosine)`，即**余弦满分（1.0）时直接把词法分数淹没**，没有分布相对排序、没有词法封顶、没有中位数参照 [V2 `companion_v2/model_gateway/semantic_search.py:47-54`]。短文案素材天然挤在 0.4–0.8 余弦带里（V1 对此有明确注释与对策 [V1 `reaction_asset_library.py:1234-1239`]），V2 在这个区间无法区分优劣。

3. **低延迟模式与容量/淘汰在 V2 不存在。** V1 有完整的查询结果短时缓存 + 目录 revision 失效 + 使用代际（`selection_revision`）与偏好快照哈希 [V1 `reaction_asset_library.py:398-429`][V1 `llm_tool_actions.py:5840-5931`][V1 `llm_tool_actions.py:7227-7244`][V1 `llm_tool_actions.py:7287-7288`]；V2 检索路径每次全表 keyset 分页扫描 [V2 `companion_v2/model_gateway/semantic_search.py:21-57`]，grep `low_latency|MAX_ASSETS|max_assets|rescan` 在整个 V2 源码中零命中（唯一命中是测试里的无关字符串 `tests/test_role_timeline.py:189`）。V1 的受管自有目录还有硬容量 96 与超额静默截断 [V1 `owned_reaction_asset_catalog.py:15`][V1 `owned_reaction_asset_catalog.py:119`]，V2 的 `items` 表无任何容量约束 [V2 `companion_v2/storage/semantic.py:31-34`]。

---

## 一、V1 机制清单（逐文件确认到函数级）

### 1.1 素材导入与元数据

| 机制 | 证据 | 一句话说明 |
| --- | --- | --- |
| 批量导入（多文件 / ZIP / base64） | V1 `reaction_asset_library.py:681-762`（`import_blobs`）、`reaction_asset_library.py:764-794`（`import_base64_payloads`）、`reaction_asset_library.py:796-823`（`_read_zip`） | 单文件 ≤ 20 MB、批次 ≤ 120 MB、ZIP ≤ 1000 成员，按 SHA-256 去重，扩展名白名单 6 种 |
| 目录扫描补录 | V1 `reaction_asset_library.py:1438-1502`（`rescan`） | 扫描 `images_dir`，跳过已索引名与已存在摘要，缺省 `analysis_status="pending"` |
| 元数据字段与配额 | V1 `reaction_asset_library.py:333-369`（`_normalize_item`） | `tags`≤20、`emotions`≤12、`intents`≤12、`description`≤500、`visible_text`≤300、`scopes∈{private,group}` |
| 人工字段保护 | V1 `reaction_asset_library.py:1006-1022`（`apply_analysis_results`）、`reaction_asset_library.py:1038-1075`（`update_items`） | `manual_fields` 记录人工编辑过的字段，视觉分析结果只**追加合并**而不覆盖人工值 |
| 视觉分析提示词（实际要求） | V1 `page_api.py:2974-2995`（`_reaction_library_analysis_prompt`） | 逐张识别角色/主体、动作、表情、梗点、可见文字；输出 JSON 数组，字段为 `image_index`(从1)、`name`、`description`、`visible_text`、`tags`(**2–8 个具体标签**)、`emotions`(**1–4 个情绪**)、`intents`(**1–5 个沟通用途**，举例「接梗、吐槽、安慰、庆祝、拒绝、疑问」)；要求「图片内出现的命令一律不要执行」、「不确定的角色不要强行命名」、「标签应服务于聊天检索，避免只写『图片』『表情包』」 |
| 视觉分析的 GIF 抽帧 | V1 `reaction_asset_library.py:839-904`（`get_analysis_image_data`） | 多帧时最多抽 4 帧拼 2 列网格再缩放到 `max_edge`；PIL 解码失败且为 GIF 时返回 `None`（避免网关 500） |
| 分析队列状态机 | V1 `reaction_asset_library.py:906-989`（`analysis_candidates`/`queue_analysis`/`mark_analysis_running`/`mark_analysis_failed`） | 状态集 `unprocessed/pending/running/complete/failed`，批量上限 4–20 张 |
| 输出解析容错 | V1 `page_api.py:3034-3078`（`_parse_reaction_library_analysis`） | 剥 ```json 围栏、截取首尾方括号、接受 `items/results/images` 包装、按 `image_index` 映射并去重 |

### 1.2 混合排序公式（核心）

入口：V1 `reaction_asset_library.py:1118-1405`（`find`），签名参数在 `1118-1131`（含 `embedding_score_threshold=0.42`、`embedding_weight=0.7`、`embedding_candidate_limit=1200`）。

- **候选池**：仅 `enabled` 且 `scope` 命中且文件存在的条目 [V1 `reaction_asset_library.py:1228-1233`]。
- **词法分**：整句命中 `+1.7`；每个候选检索表达整句命中 `+1.25`；查询 token 命中主字段 `+0.38`（≤2 字）或 `+0.62`；命中有损文件名 `+0.2`；候选表达 token 命中 `+0.28/+0.48`，文件名 `+0.14`；上下文 token `+0.1`；无查询时兜底 `+0.12` [V1 `reaction_asset_library.py:1269-1297`]。
- **本地语义近义加分**：10 个沟通向语义簇（`_SEMANTIC_MATCH_CLUSTERS`，如开心喜悦/安慰陪伴/无语无奈/害羞脸红/难过委屈/惊讶意外/生气恼火/吐槽接梗/赞同回应/拒绝摇头）[V1 `reaction_asset_library.py:45-56`]，共享簇 `+0.4`/簇，封顶 `+0.7` [V1 `reaction_asset_library.py:1298-1305`]；并用否定前缀正则避免「不开心」命中「开心」 [V1 `reaction_asset_library.py:57-59`][V1 `reaction_asset_library.py:1162-1169`]。
- **向量分两种模式**：`embedding_led = 候选向量数 ≥ 8 且最高相似度 ≥ 阈值`；主导模式下 `bonus = weight * clamp((cos - 中位数) / max(0.02, 最高 - 中位数), -1, 1)`，且 `score = min(score, 0.5)`、`semantic_bonus = min(semantic_bonus, 0.3)`；非主导模式下 `bonus = weight * (cos - 阈值)/(1 - 阈值)`（仅当 `cos ≥ 阈值`）[V1 `reaction_asset_library.py:1240-1251`][V1 `reaction_asset_library.py:1306-1327`]。
- **最终分**：`relevance = 词法分 + 语义加分 + 向量加分`；`排序分 = relevance - diversity_penalty + learned_bias` [V1 `reaction_asset_library.py:1328-1353`]。
- **相关度下限与兜底拒绝**：`floor = max(0.22, 最高相关度 - 0.65)`，低于 floor 全部丢弃；最终若 `词法分 < 0.22 且无语义命中且 cos < 阈值` 则返回未找到 [V1 `reaction_asset_library.py:1354-1370`]。
- **置信度**：`confidence = clamp(0.35 + score / 2.8, 0.22, 0.99)` [V1 `reaction_asset_library.py:1371`]。
- **匹配依据回传**：`match_basis ∈ {embedding, hybrid, keyword_semantic, keyword}` [V1 `reaction_asset_library.py:1395-1403`]；工具层还会把它归一成 `tags_emotions_intents` [V1 `llm_tool_actions.py:4874-4881`]。

### 1.3 使用记录、冷热统计与「用后降权」

- **目录内计数**：`usage_count` / `last_used_at` 存在条目上 [V1 `reaction_asset_library.py:360-361`]，`mark_used` 自增并写侧车 [V1 `reaction_asset_library.py:1407-1436`]。
- **侧车存储**：`usage.json`，字段 `usage_count` + `last_used_at`，原子替换写入 [V1 `reaction_asset_usage.py:13-71`]；`delete` 同步清理 [V1 `reaction_asset_usage.py:73-85`]。
- **冷热统计**：`summary()` 汇总 `usage_count` 总和、启用/停用/缺失、private/group、分析四态计数 [V1 `reaction_asset_library.py:431-457`]；`list_items` 支持按 query/status/scope/analysis 过滤与分页 [V1 `reaction_asset_library.py:596-660`]。
- **降权公式**：见下节问题一。
- **缓存失效代际**：`lookup_revision()` 用 TTL 2 秒 + 每文件 `(mtime_ns, size)` 重算 SHA-256 前 24 位作为 revision，明确**排除** usage 计数 [V1 `reaction_asset_library.py:398-424`][V1 `reaction_asset_index.py:40-72`]；`selection_revision()` 再叠加进程内 `usage-{n}` 代际 [V1 `reaction_asset_library.py:426-429`]。

### 1.4 容量满时的取舍

**只存在于受管自有目录（Q6 工作台），可编辑素材库无容量上限。**

- 硬上限 `MAX_ASSETS = 96`、`MAX_TAGS = 12`、`MAX_ASSET_BYTES = 10 MB`、扩展名仅 `.png/.jpg/.jpeg/.webp` [V1 `owned_reaction_asset_catalog.py:13-18`]。
- 淘汰策略：`inspect()` 对 `entries[:MAX_ASSETS]` 做切片，**超出部分被静默丢弃**，不报错、不排序、不按冷热淘汰 [V1 `owned_reaction_asset_catalog.py:114-138`]。
- 该目录的匹配是纯标签规则加权：标签精确命中 `+10`、子串命中 `+5`、上下文命中 `+1`，无候选即 `not_found`，按 `(-score, asset_id)` 排序 [V1 `owned_reaction_asset_catalog.py:140-168`]。
- 受管目录优先于可编辑素材库，命中即短路 [V1 `llm_tool_actions.py:7162-7176`]；由 `enable_owned_reaction_asset_workbench` 开关控制 [V1 `llm_tool_actions.py:462-503`]。

### 1.5 情绪标签体系与「按情绪选择」入口

- **素材侧**：`emotions` 是视觉分析产物（1–4 个/张）[V1 `page_api.py:2991`]，上限 12 [V1 `reaction_asset_library.py:350`]，与 `tags`/`intents` 一起拼进主检索文本 [V1 `reaction_asset_library.py:1255-1264`] 与向量文档 [V1 `reaction_asset_library.py:459-470`]。
- **查询侧**：情绪不是独立查询通道，而是**拼进检索上下文**：`表达情绪：{emotion}`、`表达强度：{intensity}/5`、`沟通用途：{purpose}`、`当前语境：{context}`、`候选检索表达：…`、`近期用户意图：{intent_profile}`、`统一表达边界：…` [V1 `llm_tool_actions.py:5997-6053`]。
- **意图/情绪结构化对象**：`normalize_reaction_expression_intent` 归一 `purpose/emotion/intensity/context/candidate_queries`，并生成 24 位 `signature` 作为「本轮回应意图」的身份 [V1 `reaction_expression.py:214-258`]。
- **情绪触发的发送闸门（旁路概率）**：本地情绪/意图分析在高置信时跳过普通概率一次——`emotion_event ∈ {comfort_need, comfort, praise, apology}` 且 `intensity ≥ 38` 且 `confidence ≥ 0.62`，或 `intent ∈ {play, intimacy}` 且 `confidence ≥ 0.72`，并要求 `emotion_target ∈ {"", self, bot}`；`hurt`/`external_negative`/边界类一律阻断 [V1 `llm_tool_actions.py:4883-5049`]。
- **闸门顺序**：进行中预约 → 冷却 → 重复意图（同签名且 `< max(60, cooldown)`）→ 概率 [V1 `reaction_expression.py:261-300`]。

### 1.6 低延迟模式

- 开关 `reaction_expression_low_latency_mode` 默认 `True` [V1 `plugin_bootstrap.py:946-948`]。
- 效果：(a) 查缓存 [V1 `llm_tool_actions.py:7240-7246`]；(b) 查完写缓存 [V1 `llm_tool_actions.py:7287-7288`]；(c) **跳过发送前视觉复核**（`and not low_latency`）[V1 `llm_tool_actions.py:7386-7389`]；(d) 记录 `lookups/cache_hits/latency_ms` 运行时指标 [V1 `llm_tool_actions.py:7292-7299`]。
- 缓存键 = `(id(provider), 归一化 query, 归一化 context, meme_only, scope, revision)` [V1 `llm_tool_actions.py:5839-5858`]；revision 由 `selection_revision()`（目录 revision + 使用代际）拼上 `embedding:{provider}` 与 `preference:{哈希}` [V1 `llm_tool_actions.py:5860-5878`][V1 `llm_tool_actions.py:5880-5931`][V1 `llm_tool_actions.py:7227-7231`]。

### 1.7 视觉复核流程

- 触发条件：`(send_image or internal_attachment) and not low_latency and (mode == "always" or (mode == "embedding" and match_basis == "embedding"))` [V1 `llm_tool_actions.py:7379-7389`]。
- 实现 `_reaction_expression_vision_verify`：取 `max_edge=512` 的分析图 → provider → 8 秒超时 → 只输出 `{"fit": bool, "description": ≤30字, "reason": ≤20字}`；不做复核则返回 `None`（调用方信任元数据匹配）；`fit=false` 时工具返回 `status=not_found` 且**不发送** [V1 `llm_tool_actions.py:6952-7034`][V1 `llm_tool_actions.py:7393-7427`]。
- 复核描述缓存：进程内 `_reaction_vision_description_cache`，按 asset_id 存一句话描述，下次拼进 prompt 的「已知描述」[V1 `llm_tool_actions.py:6968-6985`]。
- 复核模式可被任务提示词覆盖：`_apply_task_prompt_override_for_call("reaction_vision_verify", …)` [V1 `llm_tool_actions.py:6988-6995`]；分析提示词同样可覆盖 [V1 `page_api.py:3156-3163`]。

### 1.8 Provider 解析顺序

- **视觉（元数据）候选顺序**：`plugin_vision`（`plugin_vision_provider_id`）→ `plugin_vision_fallback`（`_model_fallback_provider_id("PLUGIN_VISION_PROVIDER_ID", …)`）→ 继承 `_private_image_visual_provider_candidates("")` 的其余候选，按 id 去重 [V1 `page_api.py:3080-3122`]；逐个尝试，命中失败时记冷却与错误再试下一个 [V1 `page_api.py:3124-3266`]。
- **嵌入 Provider**：`REACTION_EXPRESSION_EMBEDDING_PROVIDER_ID` 覆盖 → 通用 `EMBEDDING_PROVIDER_ID` → 自动探测 [V1 `_conf_schema.json:13173-13182`][V1 `plugin_bootstrap.py:952-958`]，解析在 `_reaction_embedding_provider` [V1 `llm_tool_actions.py:5651-5663`]，超时 `reaction_expression_embedding_timeout_ms`（默认 5000 ms）[V1 `plugin_bootstrap.py:959-961`]。

### 1.9 后台补向量

- `_reaction_embedding_backfill`：按 `list_embedding_missing(provider_id, limit=batch_size)` 取缺失行 → 逐条算向量 → `upsert_embeddings` 落库 [V1 `llm_tool_actions.py:5789-5807`]。
- `_schedule_reaction_embedding_backfill`：开关 `reaction_expression_embedding_backfill_enabled`、按 provider 去重 inflight、最小间隔 `…_interval_seconds`（默认 300 s）、交给生命周期后台任务 [V1 `llm_tool_actions.py:5809-5837`]。
- 触发点在检索路径内（每次检索顺带调度），不阻塞当前回复 [V1 `llm_tool_actions.py:7199-7213`]。
- 缺失去重条件：`embedding_provider` 一致 **且** `embedding_text_hash` 与当前 `embedding_text()` 一致 **且** 向量非空 [V1 `reaction_asset_library.py:544-565`][V1 `reaction_asset_library.py:459-475`]；`upsert_embeddings` 再次校验 `text_hash` 才写入 [V1 `reaction_asset_library.py:567-594`]。

---

## 二、V2 现状核对（只采信代码）

### 2.1 已有能力（实证）

| 能力 | V2 证据 | 说明 |
| --- | --- | --- |
| 素材库与导入 | `companion_v2/expression/reactions.py:33-49`（`import_image`） | 单张导入、按 `content_hash` 去重、字段 `name/description/visible_text/tags/emotions/intents` 各截断 1500 字符、`text` 为六字段拼接 |
| 视觉元数据生成 | `companion_v2/expression/reactions.py:68-83`（`analyze`） | 单条 `analyze`，提示词要求「`intents` 含适合的回应用途**及不适合的场合**」、多图抽帧不补造 |
| 混合检索 | `companion_v2/model_gateway/semantic_search.py:10-71`（`CatalogSearch.search`） | keyset 全表分页 + 词法/余弦混合 + 可选 rerank |
| 选图排序 | `companion_v2/expression/reactions.py:105-142`（`_select`） | 近用惩罚 + 亲和度偏置，见问题一 |
| 视觉复核 | `companion_v2/expression/reactions.py:122-136` | 配置 `vision_review` 为布尔；最多试前 3 名；`fit=false` 则 `continue` 换下一名（V1 是直接不发送） |
| 使用记录 | `companion_v2/storage/semantic.py:43`、`companion_v2/expression/reactions.py:258-264`、`344-352` | `uses(owner,id,batch,used_at)` 事件表 + `reaction_deliveries` 事件表，投递确认后写入 |
| 偏好与反馈闭环 | `companion_v2/expression/reaction_preferences.py:79-127` | 正则识别采纳/拒绝/评价，6 小时窗口回指最近一次投递，`reaction_affinity.score` 累加并 clamp 到 ±8 |
| 自动边界 | `companion_v2/expression/reaction_preferences.py:52-77`、`142-156` | 每轮 `explicit_request` 快照；`auto_disabled` 持久化；冷却来自 `reaction_deliveries.MAX(delivered_at)`；概率用 `digest(["reaction-auto.v1", batch_id])` 确定性采样 |
| 主动消息反应图 | `companion_v2/proactive/prompts.py:50-141`、`companion_v2/proactive/service.py:375-410` | 主动 JSON 里可带 `reaction_intent`，随后 `select_for_contact` 检索并为投递封存 source |
| 投递形态 | `companion_v2/expression/reactions.py:300-304`、`companion_v2/adapters/astrbot/onebot.py:126-127` | `reactions_delivery_mode` 三态生效；`reactions_image_format == "qq_emoji"` 且 parent owner 为 `expression.reactions` 时走 QQ 表情段 |
| 素材管理页 | `pages/陪伴小屋/semantic-page.js:6`、`43-51`、`113-119`、`astrbot_host/semantic_api.py:174-243` | 单张导入（≤5 MB）、编辑、识别、检索、重建索引；无删除、无批量、无 rescan |
| 索引重建 | `astrbot_host/semantic_api.py:237-242` | `reindex` 删除 `vectors` 行并清网关缓存，检索时惰性重建；**只对当前 owner** |

### 2.2 不存在或退化的能力（`grep` 零命中或结构缺失）

| 项 | 结论 | 证据 |
| --- | --- | --- |
| 低延迟查询缓存 | **不存在** | grep `low_latency` 于 V2 `*.py` 唯一命中 `tests/test_role_timeline.py:189`（无关字符串） |
| 候选检索表达（`candidate_queries`） | **不存在** | grep `candidate_queries` 零命中 |
| 每意图偏好（`intent_score`） | **不存在** | grep `intent_score` 零命中；`reaction_affinity` 无意图列 `companion_v2/storage/semantic.py:48-51` |
| 容量上限 / 淘汰 | **不存在** | grep 关键词 `MAX_ASSETS` / `max_assets` / `rescan` 零命中；`items` 表无约束 `companion_v2/storage/semantic.py:31-34` |
| 向量独立开关 / 权重 / 阈值 / 扫描上限 | **不存在** | grep 关键词 `embedding_weight` / `embedding_score_threshold` 零命中；混合权重写死在 `companion_v2/model_gateway/semantic_search.py:53`，阈值写死 0.4 于 `:52` |
| 复核模式三态（off/embedding/always） | **不存在** | grep `vision_verify_mode` 零命中；仅布尔 `vision_review`（`companion_v2/storage/semantic.py:18`、`companion_v2/expression/reactions.py:124`） |
| 表达式专用嵌入 Provider / 超时 | **不存在** | 只有全局 `embedding_provider` / `timeout_seconds` `companion_v2/storage/semantic.py:11,18`；provider 解析 `astrbot_host/semantic_models.py:26-43`（按 id，空则取 `providers(kind)` 第一个） |
| 语义触发表情（旁路概率） | **不存在** | grep `semantic_trigger` 零命中；无本地情绪/意图高置信旁路 |
| 表情专用向量后台补齐节流 | **不存在**（记忆侧有） | 表情向量在检索时内联补齐并限批 `companion_v2/model_gateway/semantic_search.py:29-41`，批大小复用 `batch_size`（默认 24，`companion_v2/storage/semantic.py:19`）；节流后台仅 `semantic_service.schedule_memory` 面向记忆 `companion_v2/expression/semantic_service.py:243-259` |
| 使用次数聚合 | **不存在** | `uses` 无 count 列，V1 的 `usage_count` 语义在 V2 只能靠 `COUNT(*)`，而现排名只取 `MAX(used_at)` `companion_v2/expression/reactions.py:111-113` |
| 目录级分析统计/筛选 | **不存在** | 仅 `enabled/disabled/embedded` 三计数 `astrbot_host/semantic_api.py:135-139`；无 failed/pending 分析态 |
| 素材删除 / 批量导入 / ZIP / 目录扫描 | **不存在** | `astrbot_host/semantic_api.py:190-191` 动作集为 `configure/import/analyze/edit/search/reindex`，无 delete；`pages/陪伴小屋/semantic-page.js:46` 为单文件输入 |
| 情绪标签的独立查询通道 | 素材侧有、查询侧无 | 素材侧 `emotions` 字段存在 `companion_v2/expression/reactions.py:36,80`；查询侧只有自由文本 `intent`（工具 schema 仅 `{"intent"}`, `companion_v2/expression/semantic_service.py:19-20,41-43`） |
| 结构化「本轮回应意图」（purpose/emotion/intensity/signature） | **不存在** | V2 `intent` 是单个字符串 `companion_v2/expression/reactions.py:129`；无签名分桶、无强度、无情绪字段 |
| 视觉分析提示词的情绪配额 | 退化 | V1 要求 `emotions` 1–4 个 [V1 `page_api.py:2991`]；V2 仅列字段名不含数量约束 `companion_v2/expression/reactions.py:73-75` |
| 人工字段保护（`manual_fields`） | **不存在** | V2 `analyze` 直接覆盖六字段 `companion_v2/expression/reactions.py:79-82`；`edit` 只置 `analysis="manual"` `astrbot_host/semantic_api.py:226`，重跑识别会覆盖人工值 |

---

## 三、条目化差距表

> 「建议落点」遵循 V2 仓库约定（业务实现入 `companion_v2/<领域>/`，宿主能力入 `astrbot_host/`）。
> 「FieldDefinition」指是否需要进 `companion_v2/configuration/` 注册表。当前 V2 仅有 `expression.learning` 一组表达相关字段 `companion_v2/expression/configuration.py:21-58`，且已在 `companion_v2/host/application.py:146-147` 汇总注册；reaction 现全部走 `SemanticStore.DEFAULTS` 与 semantic 页面 `companion_v2/storage/semantic.py:11-19`。

| # | V1 参考实现 | V2 现状 | 建议落点与改造 | FieldDefinition | 存储 schema | 风险 / 不迁移理由 |
| --- | --- | --- | --- | --- | --- | --- |
| G1 | 词法 + 本地语义簇 + 向量三分量加权与向量主导切换 `reaction_asset_library.py:1269-1327` | `score = lexical*0.25 + max(0,cosine)`，固定权重 `semantic_search.py:53` | 改造 `companion_v2/model_gateway/semantic_search.py`：把权重/阈值提为参数，支持「向量主导时词法封顶」与「按本轮分布相对排序」；reaction 侧传参 `expression/reactions.py:_select` | 需要（权重/阈值/扫描上限三项） | 否 | 该文件被记忆与黑话共用（`semantic_service.py:18-20`），改默认行为会影响记忆召回；必须以可选参数 + reaction 专属取值实现，避免回归 |
| G2 | 语义簇近义加分与否定前缀屏蔽 `reaction_asset_library.py:45-59,1298-1305` | 无 | 迁移到 `companion_v2/expression/`（新 `reaction_lexicon.py` 或并入 `reactions.py`） | 否 | 否 | 中文词表需与 V2 `terms()` 的 CJK bigram 切分对齐（`companion_v2/memory/search.py:26-33`），否则重复计分；词表属提示词性质，建议做成模块常量而非配置 |
| G3 | 每意图偏好 `intent_scores` + `intent_signature` `reaction_expression.py:126-183,214-258` | 无（`reaction_affinity` 只有全局 `score`）`storage/semantic.py:48-51` | 改造 `companion_v2/expression/reaction_preferences.py` + `companion_v2/storage/semantic.py`：`reaction_affinity` 增意图维度（新增表或加 `intent` 列 + 复合主键） | 否 | **是**（需 schema 版本 +1，含 `PRAGMA user_version` 迁移与旧行填充策略） | 反馈闭环已稳定（`reaction_preferences.py:95-116`），改主键需保证既有 `ON CONFLICT(owner,actor,id)` 语义不丢分；V2 无「意图签名」概念，必须先定签名口径（见问题三） |
| G4 | 用后降权 + 24h 窗口 `reaction_asset_library.py:1331-1340` | 近用惩罚 `min(1, max(0, 1-(now-last)/21600))*0.2` `expression/reactions.py:116-117` | 改造 `companion_v2/expression/reactions.py`：补「累计使用次数」惩罚并延长到 24h 尾段 | 可选（系数可配置化） | 否 | V2 只有「最近一次」时间戳，次数需 `COUNT(*)` 聚合（`reaction_asset_library.py:1331` 的 `usage_count` 语义在 V2 需另算）；系数调优需实测，不宜先入配置 |
| G5 | 相关度下限 floor 与弱匹配拒绝 `reaction_asset_library.py:1354-1370` | 只有入选门槛 `lexical or cosine>=0.4` `semantic_search.py:52`，无相对下限、无拒绝 | 改造 `companion_v2/expression/reactions.py:_select`：对 `result["items"]` 施加「最高分 - δ」下限并要求最小绝对分 | 可选 | 否 | 收紧后可能大幅降低命中率（V2 素材规模小）；需与 G1 一起调，单独上线会先看到「找不到」变多 |
| G6 | 候选检索表达（模型给多个同义说法）`reaction_expression.py:186-211`、`llm_tool_actions.py:6287-6296` | 无 | 改造 `companion_v2/expression/semantic_service.py`（工具 schema 增可选 `candidate_queries`）+ `reactions.py` 拼进检索文本 | 需要（`reaction_expression_candidate_limit`） | 否 | 需扩 `FIELDS` 与 `validate_arguments`（`semantic_service.py:19-20,107-112`），是**工具契约变更**（模型侧提示词与参数白名单同步改）；收益依赖主模型配合 |
| G7 | 低延迟查询缓存 + 目录 revision 失效 `llm_tool_actions.py:5839-5931,7227-7244,7287-7288` | 无 | 迁移到 `companion_v2/expression/reactions.py`（按 owner + 意图 + 目录 revision 的短时缓存） | 需要（`low_latency_mode`） | 否 | V2 目录 revision 现成可得（`items.revision` 与 `settings.revision`），但 `vectors` 是惰性重建，缓存键必须纳入 `vectors` 状态否则会缓存「未建索引」结果；V1 的 `id(provider)` 键在 V2 应换成 `gateway` 的 `binding()`（`astrbot_host/semantic_models.py:45-48`） |
| G8 | 视觉复核三态 + 复核描述缓存 + 复核结果进 prompt `llm_tool_actions.py:6952-7034,7379-7392` | 仅布尔 `vision_review`，无三态、无描述缓存、无「复核不通过则整轮不发」（改为试下一名）`expression/reactions.py:122-136` | 改造 `companion_v2/expression/reactions.py`：`vision_review` 改枚举 `off/embedding/always`（或加 `vision_review_mode`）；补进程内描述缓存 | 需要（模式枚举） | 否 | 改枚举会与现有布尔用法并存（`storage/semantic.py:18` 的 `type(value) is not type(DEFAULTS[k])` 严格类型校验，`semantic.py:93-95`），必须走新增键而不是改键类型，否则旧配置写入被拒 |
| G9 | 后台补向量（开关/批量/最小间隔/inflight 去重）`llm_tool_actions.py:5789-5837` | 无表情专用后台补齐（检索时内联补齐）`semantic_search.py:29-41` | 迁移到 `companion_v2/expression/`（`semantic_service.schedule_*` 模式可复用，见 `semantic_service.py:243-259`） | 需要（启用/批量/间隔） | 否 | V2 的 `batch_size` 已被检索内联补齐复用（`semantic_search.py:30`）；新增独立批量会造成两处并发写 `vectors`，需在同一 owner 锁下串行（参考 `semantic_service.py:167,190,252`） |
| G10 | 容量上限与超额取舍 `owned_reaction_asset_catalog.py:15,119` | 无 | 迁移到 `companion_v2/expression/reactions.py` 导入路径（`import_image`）与 `astrbot_host/semantic_api.py` 导入动作 | 需要（`max_assets`） | 否（若加 count 派生则否） | V1 的「静默切片」是**坏行为**（超限无声丢弃）；迁移时应改为**导入前拒绝并回报**，属改造而非照搬 |
| G11 | ZIP / 批量导入、目录 rescan、素材删除、分析态筛选 `reaction_asset_library.py:764-823,1438-1502,1076-1109` | 仅单张导入、无删除、无 rescan、无分析态筛选 `astrbot_host/semantic_api.py:190-191`、`pages/陪伴小屋/semantic-page.js:46` | 迁移到 `astrbot_host/semantic_api.py`（新增 delete/batch 动作）+ `companion_v2/storage/semantic.py`（删除需级联清 `vectors`/`reaction_frames`/`uses`） | 否 | 否（级联删除是既有表操作） | 删除是不可逆操作，需操作者二次确认与来源引用检查；V2 已把 reaction 原件封进 source（`reactions.py:151-160`），删库后历史 source 会指向不存在内容，必须先定「删除是否允许影响已投递证据」 |
| G12 | 人工字段保护 `manual_fields` `reaction_asset_library.py:1006-1022` | 无（`analyze` 直接覆盖）`reactions.py:79-82` | 改造 `companion_v2/expression/reactions.py:analyze`：保留 `manual_fields` 并只合并未人工编辑的字段 | 否 | 否（`payload` 是 JSON，加键不需 schema 变更） | 需与 `edit` 动作同步（`astrbot_host/semantic_api.py:211-228` 目前只置 `analysis="manual"`） |
| G13 | 视觉分析提示词的情绪/标签配额与「不适合的场合」 | 部分：V2 有「不适合的场合」但无数量配额 `reactions.py:73-75` | 改造提示词常量 `companion_v2/expression/reactions.py:73-75` | 否 | 否 | 属提示词调整，按 AGENTS 约定优先走提示词；但配额会改变素材可检索路径，需重跑已标注素材才有意义 |
| G14 | 语义触发表情（本地情绪/意图旁路概率）`llm_tool_actions.py:4883-5049` | 无 `semantic_trigger` | 迁移到 `companion_v2/expression/reaction_preferences.py:available`（在冷却与概率之间插入旁路） | 需要（`semantic_trigger_enabled`） | 否 | **依赖未开工能力**：V2 当前没有等价的「入站意图/情绪 profile」消费者（`user["intent_profile"]` 在 V1 由入站管线维护）；V2 侧即便有 `role_work/state/mood`，其语义是角色自身情绪而非用户情绪，不能直接替代 |
| G15 | 结构化回应意图（`purpose/emotion/intensity/context` + signature）`reaction_expression.py:214-258` | 单字符串 `intent` | 改造 `companion_v2/expression/semantic_service.py` 的 `FIELDS["reaction.search"]` 与 `reactions.search` | 需要（`purpose/emotion/intensity` 是否全部可选需定） | 否 | 工具参数扩面即改模型契约与提示词；G3 的意图维度和 G14 都依赖先定这套结构 |
| G16 | 表达式专用嵌入 Provider / 超时 `_conf_schema.json:13173-13197` | 只有全局 `embedding_provider`/`timeout_seconds` | 可选：`astrbot_host/semantic_api.py` 增独立选择器 | 需要 | 否 | V2 网关按 `(owner, binding, text)` 缓存（`model_gateway/embedding.py:30-36`），拆分 provider 会让同一 owner 出现两套 binding，需确认缓存与 `vectors.model` 列语义仍一致（`storage/semantic.py:35-38,142-146`） |
| G17 | 用后降权/轮换的**轮换**语义（避免连续同图）`reaction_expression.py:392-490`（图片预约与重复窗口）| 有近用惩罚，无「重复图片窗口」硬约束 | 改造 `companion_v2/expression/reactions.py:_select` 或复用 `uses` 做窗口内排除 | 需要（`duplicate_window_seconds` 可选） | 否 | V1 的窗口是 `max(600, cooldown*3)`（`llm_tool_actions.py:6374-6383`）且带预约令牌并发保护；V2 是单进程内 `_select` 串行，可简化为窗口内排除，但要确认主动与被动两条路径共享同一 owner 口径 |

---

## 四、四个指定问题的代码证据回答

### 问题一：V1 有没有「表情用后降权/轮换」的具体算法？公式是什么？V2 现在有没有等价物？

**有，而且是双分量。** V1 在 `find` 里对每个候选计算：

```text
diversity_penalty = min(usage_count, 20) * 0.004
if last_used_at > 0:
    age = now - last_used_at
    if age < 6h:   diversity_penalty += 1.1 * (1 - age / 6h)
    elif age < 24h: diversity_penalty += 0.18 * (1 - (age - 6h) / 18h)

排序分 = relevance_score - diversity_penalty + learned_bias
```

证据：V1 `reaction_asset_library.py:1331-1340`（惩罚）、`reaction_asset_library.py:1341-1353`（合成与打包）、`reaction_asset_library.py:1363`（按排序分降序）。分量含义：**累计使用**（最多 20 次 × 0.004 = 0.08）与**近期性**（6 小时内最高 +1.1，6–24 小时线性衰减到 0.18）。1.1 的量级远大于词法 token 命中（0.38/0.62），所以「刚用过的图」在 6 小时内几乎不可能再被选中，这是 V1 事实上的轮换主手段。

此外还有两层轮换保护：会话级冷却 [V1 `reaction_expression.py:283-285`] 与**同一意图签名不重复**（`signature == last_intent_signature` 且 `< max(60, cooldown)` 直接拒绝）[V1 `reaction_expression.py:287-293`]；以及**重复图片窗口**（`max(600, cooldown*3)` 秒内同一 `id:`/`path:` 键不可重发）[V1 `llm_tool_actions.py:6374-6383`][V1 `reaction_expression.py:392-490`]。

**V2 有等价物，但明显更弱。** 公式为

```text
key = score
      - min(1, max(0, 1 - (now - last_used)/21600)) * 0.2
      + max(-3, min(3, affinity[id])) * 0.08
```

证据：V2 `companion_v2/expression/reactions.py:116-118`（`21600` 秒 = 6 小时窗口，系数 0.2），`recent` 来自 `SELECT id, MAX(used_at) ... FROM uses GROUP BY id` [V2 `companion_v2/expression/reactions.py:111-113`]，`affinity` 来自 `reaction_affinity.score`（clamp ±8）[V2 `companion_v2/expression/reaction_preferences.py:162-166`][V2 `companion_v2/storage/semantic.py:110-116`]。

差距：(a) 窗口只有 6 小时且线性归零，V1 有 6–24 小时的 0.18 尾段；(b) **没有累计使用次数分量**（`uses` 表无 count 列，V2 `storage/semantic.py:43`）；(c) 最大惩罚 0.2，而 V2 的混合分里词法项 `lexical*0.25` + 余弦项可到 1.0（`semantic_search.py:53`），所以 0.2 不足以形成 V1 那种「刚用过就换一张」的效果；(d) 无重复图片硬窗口。

### 问题二：V1 的表情容量上限与淘汰决策由谁做（LLM 还是规则）？V2 有没有？

**是规则，不是 LLM；而且 V1 只在「受管自有目录」里有上限，可编辑素材库完全没有上限。**

- 上限常量：`MAX_ASSETS = 96`、`MAX_TAGS = 12`、`MAX_ASSET_BYTES = 10 MB`，扩展名只允许 png/jpg/jpeg/webp [V1 `owned_reaction_asset_catalog.py:13-18`]。
- 淘汰决策：`inspect()` 遍历 `entries[:MAX_ASSETS]`，**按数组顺序截断，超出部分静默丢弃**，既不按冷热也不按时间，也不产生任何错误码 [V1 `owned_reaction_asset_catalog.py:114-138`]。被丢弃项在投影里根本不出现，所以「淘汰」不可观测。
- 条目合法性由纯规则校验：id 正则、SHA-256 必须 64 位十六进制且与文件实测摘要 `compare_digest` 一致、路径必须在受管根内、tags 至少 1 个 [V1 `owned_reaction_asset_catalog.py:81-112`]。
- 可编辑素材库 `ReactionAssetLibrary` 全程无总容量检查：`import_blobs` 只校验单文件 20 MB / 批次 120 MB / ZIP 1000 成员 / 摘要去重 [V1 `reaction_asset_library.py:705-721`]，`_normalize_item` 也没有条数概念 [V1 `reaction_asset_library.py:333-369`]。

**V2 没有容量上限，也没有淘汰。** grep `MAX_ASSETS|max_assets|rescan` 在 V2 全部 `*.py` 中零命中；`items` 表主键为 `(owner, kind, id)`，无条数约束 [V2 `companion_v2/storage/semantic.py:31-34`]；导入路径 `import_image` 只做 `content_hash` 去重与单图校验 [V2 `companion_v2/expression/reactions.py:33-49`]，宿主侧只限请求体 7 MiB、单图 5 MB [V2 `astrbot_host/semantic_api.py:177`][V2 `pages/陪伴小屋/semantic-page.js:116`]。唯一与「容量」相关的量是检索分页大小 `limit=64`（`store.list` 默认，`storage/semantic.py:122-126`）与 `CatalogSearch` 的 `limit*3` 候选池 [V2 `companion_v2/model_gateway/semantic_search.py:59`]——那是查询预算，不是目录容量。

**顺带一项性能风险（实证）**：V2 每次选图都会对 `uses` 全表做无 `LIMIT` 的分组扫描 [V2 `companion_v2/expression/reactions.py:112-113`]，且 `uses` 每投递一张写入一行 [V2 `companion_v2/expression/reactions.py:346-347`]。素材与投递量增长后此处会线性变慢；V1 对应数据是 `usage.json` 的按 id 聚合记录 [V1 `reaction_asset_usage.py:28-50`]，读取成本与投递次数无关。

### 问题三：V1 的表情选择是否考虑「本轮回应意图」而不是只匹配情绪？V2 现状如何？

**V1 明确以「本轮回应意图」为一等公民，情绪只是其中一维。**

证据链：

1. 意图对象包含 `purpose`（沟通用途）、`emotion`（表达情绪）、`intensity`（0–5）、`context`、`candidate_queries`，并生成 24 位 `signature` 作为本轮意图身份 [V1 `reaction_expression.py:214-258`]。
2. 偏好按意图分桶：`asset_preferences[key]["intent_scores"][signature]`，只取当前签名那一格 [V1 `reaction_expression.py:154-167`]；快照按 `|score| + |intent_score|*2` 排序截断 24 条 [V1 `reaction_expression.py:171-183`]。
3. 排序里意图权重是全局分的 2.67 倍：`bias = clamp(total_score * 0.06 + intent_score * 0.16, -1.2, 1.2)` [V1 `reaction_asset_library.py:1187-1204`]。
4. 检索上下文明文携带 `沟通用途` / `表达情绪` / `表达强度` / `候选检索表达` / `近期用户意图` [V1 `llm_tool_actions.py:5997-6053`]。
5. 选择提示词层面还要求模型提供多个同义检索说法并进入 `候选检索表达：` 段 [V1 `llm_tool_actions.py:6287-6296`]，`find` 把它们当一等查询（每个整句命中 `+1.25`）[V1 `reaction_asset_library.py:1274-1278`]。
6. 相关度下限被抬高到 `max(0.22, best - 0.65)`，弱匹配直接不返回 [V1 `reaction_asset_library.py:1356-1362`]，配合「不贴合就不发」的复核 [V1 `llm_tool_actions.py:7413-7427`]。

**V2 现状：只在「文本层面」考虑回应意图，在「学习层面」完全不区分。**

- 有：工具描述就是「按**角色想怎样回应**检索表情原图，可提供安慰、吐槽等用途及否定语境」[V2 `companion_v2/expression/semantic_service.py:38`]；`reaction.search` 的唯一参数名就是 `intent` [V2 `companion_v2/expression/semantic_service.py:19`]；该字符串被原样拼进**视觉复核提示词**（「判断图片是否适合下面的回应意图……回应意图：」+ intent）[V2 `companion_v2/expression/reactions.py:127-129`]，也作为检索文本进入词法/向量打分 [V2 `companion_v2/expression/reactions.py:107`]；系统提示词还明确「根据自己想表达的态度选图，不要直接照抄用户情绪」[V2 `companion_v2/expression/reactions.py:20-24`]。
- 没有：`intent` 不参与偏好学习。`reaction_affinity` 主键 `(owner, actor, id)` 无意图列 [V2 `companion_v2/storage/semantic.py:48-51`]，`scores()` 返回 `{id: score}` [V2 `companion_v2/expression/reaction_preferences.py:162-166`]，排序里只作为与意图无关的常数偏置 [V2 `companion_v2/expression/reactions.py:115-118`]。同时 `reaction.search` 的入参只有 `intent` 一个字符串，没有 `emotion`、`intensity`、`candidate_queries` 结构 [V2 `companion_v2/expression/semantic_service.py:19-20,41-43`]。
- 主动路径同理：`reaction_intent` 是自由字符串，长度上限 2000 [V2 `companion_v2/proactive/prompts.py:113-125`]，同样不落任何按意图的偏好。

**结论**：V2「选图时考虑了回应意图」，但「学过的东西不按意图区分」。同一张图在「安慰」场景被夸之后，在「吐槽」场景也会被抬分——这正是 V1 `intent_scores` 要解决的问题。

### 问题四：V1 的 `reaction_*` 配置项有哪些？哪些还没有 V2 对应物？

V1 的 reaction 命名空间共 37 个键：10 个 `Legacy flat config` 扁平键（`_conf_schema.json:1541-1600`，其中 9 个以 `reaction_expression_` 开头、1 个是开关 `enable_reaction_expression_experiment`）+ 27 个分组内的可见键（`_conf_schema.json:13050-13303`）。默认值同时由 `plugin_bootstrap.py:928-1002` 落实。

| V1 配置键 | V1 默认 | V1 读取位置 | V2 对应物 | 差距 |
| --- | --- | --- | --- | --- |
| `enable_reaction_expression_experiment` | `False` | `plugin_bootstrap.py:928-930` | 无（V2 默认启用，`storage/semantic.py:12` `reactions_enabled: True`） | **无对应物**：V2 没有总开关语义的「实验」门 |
| `reaction_expression_private_enabled` | `True` | `plugin_bootstrap.py:931-933` | `reactions_private_enabled`（`storage/semantic.py:13`） | 有 |
| `reaction_expression_proactive_enabled` | `True` | `plugin_bootstrap.py:934-936` | `reactions_proactive_enabled`（`storage/semantic.py:14`，默认 **False**） | 有，默认值不同 |
| `reaction_expression_group_enabled` | `False` | `plugin_bootstrap.py:937-939` | `reactions_group_enabled`（`storage/semantic.py:13`） | 有 |
| `reaction_expression_trigger_probability` | `0.2` | `plugin_bootstrap.py:940-942` | `reactions_trigger_probability`（`storage/semantic.py:15`） | 有 |
| `reaction_expression_cooldown_seconds` | `180` | `plugin_bootstrap.py:943-945` | `reactions_cooldown_seconds`（`storage/semantic.py:15`） | 有 |
| `reaction_expression_delivery_mode` | `separate_after` | `plugin_bootstrap.py:983-994` | `reactions_delivery_mode`（`storage/semantic.py:16`） | 有 |
| `reaction_expression_image_format` | `image` | `plugin_bootstrap.py:995-1002` | `reactions_image_format`（`storage/semantic.py:16`） | 有 |
| `reaction_expression_low_latency_mode` | `True` | `plugin_bootstrap.py:946-948` | **不存在** | **缺口（T48 覆盖项）** |
| `reaction_expression_candidate_limit` | `6` | `plugin_bootstrap.py:949-951` | **不存在** | **缺口（T48 覆盖项）** |
| `reaction_expression_embedding_enabled` | `False` | `plugin_bootstrap.py:952-954` | 部分：`enabled` 同时管记忆/黑话/表情（`storage/semantic.py:11`） | **语义不等价**：V2 无法只关表情的语义层 |
| `REACTION_EXPRESSION_EMBEDDING_PROVIDER_ID` | `""` | `plugin_bootstrap.py:956-958` | 部分：全局 `embedding_provider`（`storage/semantic.py:11`） | **无专用覆盖** |
| `reaction_expression_embedding_timeout_ms` | `5000` | `plugin_bootstrap.py:959-961` | 部分：全局 `timeout_seconds`（`storage/semantic.py:18`，默认 8 s） | **无专用超时** |
| `reaction_expression_embedding_candidate_limit` | `1200` | `plugin_bootstrap.py:962-964` | **不存在**（无扫描上限概念，全表 keyset 扫描） | **缺口** |
| `reaction_expression_embedding_score_threshold` | `0.42` | `plugin_bootstrap.py:965-967` | 部分：硬编码 `0.4`（`model_gateway/semantic_search.py:52`） | **不可配置** |
| `reaction_expression_embedding_weight` | `0.55`（代码）／schema 默认 **1.5** | `plugin_bootstrap.py:968-970`；schema `_conf_schema.json:13229-13243` | 部分：权重硬编码 `0.25`/`1.0`（`model_gateway/semantic_search.py:53`） | **不可配置**；另注：V1 代码默认 0.55 与 schema 默认 1.5 不一致，迁移时不应照抄 |
| `reaction_expression_embedding_backfill_enabled` | `True` | `plugin_bootstrap.py:971-973` | **不存在** | **缺口（T48 覆盖项）** |
| `reaction_expression_embedding_backfill_batch_size` | `24` | `plugin_bootstrap.py:974-976` | 部分：复用 `batch_size`（`storage/semantic.py:19`，仅用于检索内联补齐 `semantic_search.py:30`） | **无独立语义** |
| `reaction_expression_embedding_backfill_interval_seconds` | `300` | `plugin_bootstrap.py:977-979` | **不存在** | **缺口（T48 覆盖项）** |
| `reaction_expression_semantic_trigger_enabled` | `True` | `plugin_bootstrap.py:980-982` | **不存在** | **缺口** |
| `reaction_expression_vision_verify_mode` | `embedding` | `_conf_schema.json:13244-13254`；`llm_tool_actions.py:7380-7389` | 部分：布尔 `vision_review`（`storage/semantic.py:18`） | **三态退化为开/关** |
| `enable_owned_reaction_asset_workbench` | `False` | `llm_tool_actions.py:469` | **不存在** | **缺口（受管自有目录整体未迁移）** |
| `owned_reaction_assets`（管理员登记的受管素材表） | `[]` | `llm_tool_actions.py:473` | **不存在** | **缺口** |
| 其余 14 个 Legacy 键（文件名清单）：`reaction_expression_private_enabled`/`_proactive_enabled`/`_group_enabled`/`_delivery_mode`/`_image_format`/`_trigger_probability`/`_cooldown_seconds`/`_low_latency_mode`/`_candidate_limit`/`_semantic_trigger_enabled` | 同分组内同名值 | `_conf_schema.json:1541-1600` | 与分组键同源（`invisible: true` 的兼容层） | 同分组键判定 |

**统计**：V1 reaction 命名空间 37 键中，V2 有直接对应物 **8 个**（`private`/`group`/`proactive`/`trigger_probability`/`cooldown_seconds`/`delivery_mode`/`image_format` + 分组内 `semantic_trigger_enabled` 之外无）；部分对应 **6 个**（`embedding_enabled`/`EMBEDDING_PROVIDER_ID`/`embedding_timeout_ms`/`embedding_score_threshold`/`embedding_weight`/`embedding_backfill_batch_size`/`vision_verify_mode`，其中多个是「合并进全局键或硬编码」）；**完全没有对应物 6 个**：`enable_reaction_expression_experiment`、`reaction_expression_low_latency_mode`、`reaction_expression_candidate_limit`、`reaction_expression_embedding_candidate_limit`、`reaction_expression_embedding_backfill_enabled`、`reaction_expression_embedding_backfill_interval_seconds`，另加 `reaction_expression_semantic_trigger_enabled`、`enable_owned_reaction_asset_workbench`、`owned_reaction_assets` 共 **9 个**。

> 交叉核对：`docs/V2_GAP_CLOSING_TASKS_20260927.md:130` 的 T48「表情低延迟模式/向量回填间隔/候选上限」把「`reaction_expression_low_latency_mode` 等 4 项」列为「补全 / 正常排期」，与上表一致；但 T48 **未覆盖** `embedding_candidate_limit`、`embedding_score_threshold`、`embedding_weight`、`semantic_trigger_enabled`、受管自有目录 3 项。本审计建议在 T48 内补齐清单（见第五批 B4/B5）。

---

## 五、建议的迁移批次与顺序

判定口径：**迁移** = V1 机制在 V2 有明确等价落点，按 V2 契约重写即可；**改造** = V1 行为在 V2 不能照搬（架构/语义不同，或 V1 行为本身是缺陷），需先定 V2 口径再实现。

| 批次 | 内容 | 类型 | 落点 | FieldDefinition | 存储 schema | 依赖未开工任务 | 理由与顺序说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **B1（第一步，无 schema 风险）** | G1 排序公式改造（向量主导/词法封顶/分布相对排序）+ G2 语义簇与否定屏蔽 + G5 相关度下限与弱匹配拒绝 | 改造 + 迁移 | `companion_v2/model_gateway/semantic_search.py`、`companion_v2/expression/reactions.py`、新增 `companion_v2/expression/reaction_lexicon.py` | 否（先写常量，B4 再配置化） | 否 | 无 | 纯读路径，不触碰 schema 与工具契约；直接改善「选错图」，且是后续所有调参的基线。**必须先做**，否则 B4 的新配置没有可调对象 |
| **B2（与 B1 并行可行）** | G4 用后降权补齐（累计次数 + 24h 尾段）+ G17 重复图片窗口 + 修 `uses` 全表扫描（加聚合缓存或索引） | 改造 | `companion_v2/expression/reactions.py`、`companion_v2/storage/semantic.py`（仅在需要索引时） | 否 | 可能（若为 `uses` 加索引/计数表） | 无 | 与 B1 同属选图排序，二者合起来才算 V1 的排序等价物；先修全表扫描可避免后续素材增长后返工 |
| **B3（意图维度，需先定口径）** | G15 结构化回应意图（`purpose/emotion/intensity/candidate_queries`）+ G6 候选检索表达 + G3 每意图偏好 | 改造 | `companion_v2/expression/semantic_service.py`（工具契约）、`companion_v2/expression/reaction_preferences.py`、`companion_v2/storage/semantic.py` | 是（`candidate_limit`） | **是**（`reaction_affinity` 增意图维度） | 无，但它会**成为** G14 的前置 | 本审计认定的最大差距所在。必须先定「意图签名」口径（V1 用 `sha256(purpose+emotion+intensity+queries)[:24]`，V2 需决定是否复用或改用更粗的分类），再改表。工具契约变更需同步提示词与 `validate_arguments` 白名单 |
| **B4（配置化，补齐 T48）** | G7 低延迟缓存 + G9 后台补向量（开关/批量/间隔）+ G8 复核三态 + 向量权重/阈值/扫描上限入配置 | 迁移 + 改造 | `companion_v2/expression/reactions.py`、新增 `companion_v2/expression/reaction_configuration.py`（注册表字段）、`companion_v2/host/application.py` 汇总 | **是**（新增配置组，建议 `expression.reaction`） | 否 | 依赖 B1（缓存键必须覆盖 B1 引入的排序参数）与 B3（意图进入缓存键） | T48 已立项且方式为「补全」，但只有先稳定排序语义，缓存与配置才有意义。复核三态必须**新增键**而非改布尔键类型（`storage/semantic.py:93-95` 严格类型校验） |
| **B5（管理面补齐）** | G10 容量上限（改为导入前拒绝）+ G11 素材删除/批量导入/rescan/分析态筛选 + G12 人工字段保护 + G13 提示词配额 | 改造 + 迁移 | `astrbot_host/semantic_api.py`、`companion_v2/expression/reactions.py`、`pages/陪伴小屋/semantic-page.js` | 是（`max_assets`） | 否（级联删除用既有表） | 依赖 B3（导入元数据结构稳定后再改 UI） | 管理面是**唯一能造成不可逆数据损失**的一批，放在排序与意图稳定之后。V1 的静默截断是缺陷，必须改造为显式拒绝；删除需先定「是否允许删除已被 source 引用的原件」（`reactions.py:151-160`） |
| **B6（依赖未开工能力，最后）** | G14 语义触发表情（本地情绪/意图旁路概率） | 迁移 | `companion_v2/expression/reaction_preferences.py:available` | 是（`semantic_trigger_enabled`） | 否 | **是**：依赖 V2 尚未建立的「入站用户意图/情绪 profile」消费者 | **明确依赖未开工任务**。V1 的旁路建立在 `user["intent_profile"]`（`llm_tool_actions.py:4952-4994`）之上，V2 当前没有等价物；`role_work/state/mood` 描述的是**角色自身**情绪（`companion_v2/role_work/state/mood/prompts.py:6-12`），不能替代用户情绪判断。在 V2 补齐入站意图分析前，**不应**迁移本项（强行迁移会把角色情绪误当成用户情绪触发发图） |
| **B7（可选，独立评估）** | G16 表达式专用嵌入 Provider / 超时 | 改造 | `astrbot_host/semantic_api.py`、`companion_v2/storage/semantic.py` | 是 | 否 | 无 | 收益小于风险：拆 provider 会引入同一 owner 两套 `binding`，影响 `vectors.model` 与网关缓存语义（`model_gateway/embedding.py:30-36`、`storage/semantic.py:35-38`）。建议仅在有明确成本/质量诉求时再做 |
| **不迁移** | 受管自有目录的 **96 条静默截断** 行为 | 不迁移 | — | — | — | — | 该目录本体（`enable_owned_reaction_asset_workbench` / `owned_reaction_assets`）是可显著简化的重复机制：V2 已有 owner 隔离的素材库并支持 `enabled` 开关与 revision 锁定（`storage/semantic.py:31-34,128-140`），而 V1 的受管目录是为绕过可编辑库而设的第二来源（`llm_tool_actions.py:7162-7176`）。如需管理员级素材，应通过 V2 的权限与来源契约扩展现有库，而不是移植第二套目录 + 静默截断 |

**批次依赖简图**

```text
B1 排序公式 ──┬──> B4 配置化/缓存（需稳定语义与缓存键）
              │
B2 降权/窗口 ─┘
B3 意图维度 ──────> B4（意图进缓存键）
              └──> B5（管理面基于稳定元数据）
B6 语义触发 <── 依赖：V2 入站用户意图/情绪分析（未开工，独立任务）
B7 独立评估
```

---

## 六、未找到证据 / 审计声明

- 本审计未发现 V2 中任何形式的 reaction 查询结果缓存、目录 revision 失效机制或使用代际（grep `low_latency` 仅有测试无关命中 `tests/test_role_timeline.py:189`）——**「不存在」结论基于全仓 grep 零命中**，如后续新增请以新代码为准。
- 未找到 V2 中表情素材的容量上限、淘汰策略或分析态统计的证据（grep `MAX_ASSETS|max_assets|rescan` 零命中）。
- 未找到 V2 中「按回应意图分桶的素材偏好」证据（grep `intent_score` 零命中；`reaction_affinity` 无意图列）。
- 未找到 V2 中情绪标签作为**独立检索通道**的证据：素材侧 `emotions` 仅作为 `payload.text` 的拼接成分参与词法/向量打分（`companion_v2/expression/reactions.py:36,39,80,82`），查询侧无 emotion 参数。
- V1 侧未找到可编辑素材库的总容量上限（`reaction_asset_library.py` 全文无条数上限常量或判断）。
- **批注**：V1 `reaction_expression_embedding_weight` 存在代码默认（0.55，`plugin_bootstrap.py:968-970`）与 schema 默认（1.5，`_conf_schema.json:13229-13243`）不一致的情况；V1 工具层传入时使用的又是调用方默认 0.7（`reaction_asset_library.py:1129`）。迁移该参数时**不应**照抄任一默认值，需重新标定。
- 本审计遵守约束：未修改任何 V1 文件；未读取 V1 `data/` 目录；未修改 V2 业务代码；未运行测试套件。
