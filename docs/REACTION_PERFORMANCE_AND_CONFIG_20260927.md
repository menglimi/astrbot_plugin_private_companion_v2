# 表情检索性能与配置切片（T48：B1 + B2 + B4）

日期：2026-09-27
范围：缺口清单 T48「表情低延迟模式/向量回填间隔/候选上限」，即 [V1→V2 表情迁移审计](V1_EMOTION_REACTION_MIGRATION_AUDIT_20260927.md) 第五节的 **B1 + B2 + B4**。**不含** B3（意图维度/G3+G6+G15）、B5（管理面/G10~G13）、B6（语义触发/G14）、B7（独立嵌入 provider/G16）。
取证口径：只按代码行号引用，未修改任何 V1 文件，未读取 V1 用户数据。

## 一、V1 参考位置 → V2 落点

| 机制 | V1 位置 | V2 落点 |
| --- | --- | --- |
| 向量主导 / 非主导双公式 | `reaction_asset_library.py:1240-1251`、`1306-1327` | `companion_v2/model_gateway/semantic_search.py`（`CatalogSearch._rank`） |
| 词法中和封顶、簇加分封顶 | `reaction_asset_library.py:1319-1320` | 同上（`VECTOR_LED_LEXICAL_CAP`、`VECTOR_LED_SEMANTIC_BONUS_CAP`） |
| 本地语义簇与否定前缀 | `reaction_asset_library.py:45-59`、`1298-1305`、`1162-1169` | 新增 `companion_v2/expression/reaction_lexicon.py` |
| 相关度下限与弱匹配拒绝 | `reaction_asset_library.py:1354-1370` | `semantic_search.py`（`relevance_floor_delta`/`minimum_relevance`）+ `expression/reactions.py` 常量 |
| 用后降权双分量 | `reaction_asset_library.py:1331-1340` | `expression/reactions.py:ReactionLibrary._rank` |
| 重复图片窗口 | `llm_tool_actions.py:6374-6383` | `expression/reactions.py:ReactionLibrary._ranked`（窗口内排除） |
| 低延迟查询缓存与 revision 失效 | `llm_tool_actions.py:5839-5931`、`7227-7244`、`7287-7288` | `expression/reactions.py` 的 `_cache_key`/`_cached_lookup`/`_remember_lookup` |
| 复核三态 | `llm_tool_actions.py:7379-7392`、`_conf_schema.json:13244-13254` | `expression/reactions.py:_review` + 新配置键 `vision_verify_mode` |
| 后台补向量（开关/批量/间隔/inflight） | `llm_tool_actions.py:5789-5837` | `expression/semantic_service.py:schedule_reaction_backfill` + `semantic_search.py:CatalogSearch.backfill` |
| 配置键 | `plugin_bootstrap.py:946-979` | 新增 `companion_v2/expression/reaction_configuration.py`（组 `expression.reaction`） |

## 二、B1 排序（向量主导 + 词法封顶 + 下限拒绝）

### 2.1 两种向量模式（`semantic_search.py`）

`CatalogSearch.search` 新增可选关键字参数，**默认值精确复现改造前的行为**（记忆与黑话检索零回归）：

```text
lexical_weight   = 0.25   # 原 lexical * 0.25
embedding_weight = 1.0    # 原 max(0, cosine) 的系数
embedding_score_threshold = 0.0   # 原公式没有阈值死区
admission_similarity      = 0.4   # 原入选门槛 cosine >= 0.4
lexical_fallback_weight   = 1.0   # 原候选无向量时 score 里的 +lexical
```

- 非主导（默认）：`bonus = weight * max(0, (cos - threshold) / max(0.01, 1 - threshold))`，仅当 `cos >= threshold`。
- 主导：当**带向量的候选数 ≥ `vector_led_min_candidates`（V1 为 8）且最高余弦 ≥ 阈值**时进入。按本轮分布相对排序：`bonus = weight * clamp((cos - 中位数) / max(0.02, 最高 - 中位数), -1, 1)`；词法项封顶 `0.5`，簇加分封顶 `0.3`（非主导时为 `0.7`）。无量/过期向量的候选保持中性（不加不减）。
- 返回项新增 `basis ∈ {embedding, hybrid, keyword_semantic, keyword}` 与 `clusters`，检索摘要新增 `ranking ∈ {vector_led, blended}`；`basis` 是复核三态的唯一判据。

scale 说明（与 V1 的差异）：V1 的词法是「加权求和」（整句命中 1.7），V2 的词法是归一化比例 × 权重（默认 ≤ 0.25），因此 V2 的 0.5 词法封顶在默认权重下**结构上不会触发**（`min(lexical*0.25, 0.5)`）；它保护的是显式提高 `lexical_weight` 的调用方（测试用 `lexical_weight=2.0` 覆盖了这条路径）。审计要求的是「让词法只做同簇破平」这一语义，V2 用同一限额表达。

### 2.2 本地语义簇与否定屏蔽（`reaction_lexicon.py`）

- 原样迁移 V1 的 10 个沟通向簇（`CLUSTERS`）与否定前缀正则（`NEGATION`）。
- **与 `memory/search.py:terms()` 的 CJK bigram 对齐**：`query_terms()` 用与 `terms()` 相同的十六进制编码做子串判断，去掉「因为否定别名被切碎」而出现的 bigram（例：`不开心` 不再产出 `开心` 的 bigram）。
- **避免重复计分**：`shared_clusters(query, document)` 先取共享簇，再剔除「别名在查询与素材两侧都字面出现」的簇——那些已由词法层计分，簇加分不再叠加（`shared_clusters("开心","开心") == ()`，而 `shared_clusters("高兴","开心") == ("开心喜悦",)`）。
- 簇命中同时**参与入选判定**（`if lexical or clusters or cosine >= admission_similarity`），因此没有可用嵌入 provider 时「安慰」仍能找到「抱抱」素材（V1 的同义兜底语义），得分为簇加分 `0.4`、`basis=keyword_semantic`。
- 该模块被注入 `search(shared_clusters=...)`，`model_gateway` 不反向 import `expression`（保持仓库依赖方向）。

### 2.3 相关度下限与弱匹配拒绝

- 相对下限保留 V1 的 `0.65`：`floor = 最高分 - 0.65`，低于即丢弃；有查询词时再抬到绝对下限。
- 绝对下限取 `0.08` 而**不是**照抄 V1 的 `0.22`：V1 的 0.22 处于「一个 2 字 token 命中 = 0.38」的求和尺度，V2 的词法项归一化后满值只有 0.25，照抄会把所有「部分命中」一并拒绝（审计 G5 明确要求「不得让现有测试大面积找不到」）。0.08 ≈ 三词查询命中一个词（0.083）或一次簇命中（0.4）。
- 全部候选都在下限之下时返回空 `items`（而不是硬塞一张不相关的图），`complete` 仍为 `True`。

## 三、B2 用后降权与轮换

`ReactionLibrary._rank`（V1 `reaction_asset_library.py:1331-1340` 完整双分量 + V2 既有的亲和度偏置）：

```text
penalty  = min(使用次数, 20) * 0.004
         + 1.1 * (1 - 年龄/6h)          # 年龄 < 6h
         + 0.18 * (1 - (年龄-6h)/18h)   # 6h <= 年龄 < 24h
排序分   = 检索分 - penalty + clamp(亲和度, -3, 3) * 0.08
```

- **重复图片窗口**：`max(600, 冷却秒 * 3)`（V1 `llm_tool_actions.py:6374-6383`）内用过的原件在 `_ranked` 中被排除。
- **V2 契约选择（偏离 V1 的静默失败）**：若排除后候选为空（单素材库），则保留原候选集，只施加惩罚。理由：V2 每轮只投递一张且"不发表情"是合法结果，但单素材库在窗口内会**永久静默**；V1 的窗口建立在「素材库通常有多张」的前提上。该降级只影响候选集合，不改变投递、来源封存或回执语义。
- **修掉 `uses` 全表无 LIMIT 分组扫描**：改为只对**正在排序的候选 id** 聚合 `COUNT(*)`/`MAX(used_at)`（`WHERE owner=? AND id IN (...)`），由主键 `(owner,id,batch)` 前缀索引直接回答。**未新增索引、未改 schema、未改 `PRAGMA user_version`**。语义差异：V1 的 `usage_count` 是终生计数，V2 仍是终生计数（候选级查询即可得到，无需窗口近似）。

## 四、B4 配置化（`expression.reaction`）

字段登记在 `companion_v2/expression/reaction_configuration.py`，遵循 `expression/configuration.py` 范式：`GROUP`/`OWNER`/`LAYERS=(WINDOW,)`/`configuration_fields()`/`ReactionConfigurationOwner`/`read_snapshot(runtime, context) -> (settings, revision)`。`ApplyMode.IMMEDIATE`、`core_only=False`。

| 字段 | 类型 | 默认 | 范围 | 消费者 |
| --- | --- | --- | --- | --- |
| `low_latency_enabled` | BOOLEAN | `True`（V1 同值） | — | `reactions._select` 的检索缓存读/写 |
| `candidate_limit` | INTEGER | `6`（V1 同值） | 1–24 | 传入检索的候选池上限 + 参与复核的候选条数（`min(3, 值)`） |
| `embedding_weight` | WEIGHT | `1.0` | 0.05–3.0 | `search(embedding_weight=...)`；取 V2 现状量级（原公式余弦系数 1.0），**不照抄** V1 的 0.55 / 1.5 / 0.7 三个互相冲突的默认值 |
| `embedding_score_threshold` | PROBABILITY | `0.42` | 0–1 | 同时作为向量加分阈值与入选门槛（`admission_similarity`） |
| `embedding_candidate_limit` | INTEGER | `1200`（V1 同值） | 20–5000 | `search(embedding_candidate_limit=...)`：参与向量比较的条数上限，超出者保持中性 |
| `embedding_backfill_enabled` | BOOLEAN | `True`（V1 同值） | — | `SemanticService.schedule_reaction_backfill` 开关 |
| `embedding_backfill_batch_size` | INTEGER | `24`（V1 同值） | 1–100 | 单次后台补齐的条数上限（内部分块 ≤24 文本/请求） |
| `embedding_backfill_interval_seconds` | INTEGER | `300`（V1 同值） | 0–86400 | 同 owner 两次补齐之间的最小间隔（0 = 不节流） |
| `vision_verify_mode` | TEXT | `embedding`（V1 同值） | off/embedding/always | `reactions._review` 的复核门 |

**`vision_verify_mode` 是新增键**：`storage/semantic.py:93-95` 用 `type(value) is not type(DEFAULTS[k])` 做严格类型校验，把既有布尔 `vision_review` 改成枚举会拒绝所有已存值。布尔键保留为**总开关**：`vision_review=False` 时任何模式都不复核。

`ReactionConfigurationOwner` 存在的理由：注册表对 TEXT 只校验类型，`alwayss` 这类拼写错误会被原样存下并**静默改变复核门**；owner 在 `preview_set`/`write` 时用读路径同一个 dataclass 复校，越界与非法枚举直接拒绝；存储值被外部写坏时 `read_snapshot` 降级为默认值，不会让一轮对话失败。

### 4.1 低延迟缓存

- 键 = `digest(["reaction-lookup.v1", owner, 归一化 intent, 目录条数, Σitems.revision, vectors 条数, embedding binding, settings.revision, 配置组 revision])`。
- 失效条件：目录导入/编辑/启停（`items.revision` 与条数）、惰性重建或后台补齐导致的向量状态变化（`vectors` 条数）、嵌入 provider/模型绑定变化（`gateway.port.binding`）、语义设置变化（`settings.revision`）、本组任何写入（配置组 revision）。
- TTL `20s`、上限 64 条（LRU 逐出）；`SemanticService.close()`/`configure()` 清空。
- **只跳过检索**：命中后每轮仍重新做用量排序、重复窗口、亲和度、复核与 `validate`，因此缓存不改变投递形态、来源封存、回执或"用后降权"的时效性。

### 4.2 复核三态语义

| 模式 | 行为 |
| --- | --- |
| `off` | 不复核，直接信任元数据匹配 |
| `embedding` | 仅当该候选的 `basis == "embedding"`（向量主导了匹配依据，V1 `match_basis` 等价物）时复核 |
| `always` | 每个候选都复核 |

- **不通过时的 V2 契约：换下一名**（最多 `min(3, candidate_limit)` 名），而不是 V1 的「整轮不发」。理由：V2 一次 `reaction.search` 只投递一张图且已在 `offer` 中封存来源，V1 的整轮拒绝是为了保护其会话级预约令牌；换下一名既保留「看图不过就不发这张」的安全意图，又不会因为一次复核失败就让正常回复缺图。
- 复核异常（provider 不可用/超时/返回非法）仍为 `unavailable` 且**fail-open**：不阻断投递（保持 V2 现状语义）。
- **与低延迟解耦**：V1 的低延迟模式会连带跳过发送前复核（`llm_tool_actions.py:7386-7389`）。V2 刻意分开——低延迟只作用于检索缓存，复核由 `vision_review`（总开关）+ `vision_verify_mode`（三态）独立控制。若把两者耦合，默认开启低延迟的安装将永久失去复核能力，而 V2 的复核失败本身是 fail-open 的，不存在 V1 那种延迟代价。

### 4.3 后台补向量接线

- 复用**既有**后台注册表：`SemanticService.background`（记忆 `schedule_memory` 用的同一个 dict）+ 每 owner 的 `self.locks` 串行 + `close()`/`configure()` 的统一取消；**没有新建线程或计时器**。键为 `reaction-backfill:<owner>`（带命名空间前缀，`prepare_memory` 仍按 owner 找到记忆任务）。
- 触发点在检索路径（`reactions._select` 每次顺带调度，V1 `llm_tool_actions.py:7199-7213` 同构），同 owner 在飞时不重复调度，间隔未到只花一次字典查询。
- `CatalogSearch.backfill(owner, kind, limit=...)`：只挑「启用、有文本、当前 binding 下无有效向量」的条目，按 `limit` 截断后分块（≤24 文本/请求）嵌入并 `put_vector`（写入前复核 revision 与 payload 哈希）。与检索内联补齐可能重叠，但写入幂等（`put_vector` 校验后 `INSERT OR REPLACE`），且后台任务在 owner 锁下与黑话学习/记忆补齐互斥。
- 失败记入 `service.errors["reaction_backfill"]`（错误码或异常类型名），成功时清除。
- **宿主接线点**：本次未改 `host/application.py`；调度挂在 `SemanticService` 自身，`attach_semantics` 后即可用，无需额外的宿主唤醒。后续若要并入 `BackgroundCoordinator` 的规划器，接线点是 `SemanticService.active_handles` 已把该任务计入 `semantic:*`，无需新增注册。

## 五、未迁移项与理由

| 项 | 状态 | 理由 |
| --- | --- | --- |
| **G3 每意图偏好**（`intent_scores`/`intent_signature`） | 未迁移 | `reaction_affinity` 需增意图维度（新表或复合主键）→ `PRAGMA user_version` 升级与旧行填充；且 V2 尚无「意图签名」口径（依赖 B3 的结构化回应意图）。本批明确不含 B3。 |
| **G6 候选检索表达**（`candidate_queries`） | 未迁移 | 属工具契约变更（`FIELDS`/`validate_arguments`/提示词同步），归 B3。 |
| **G15 结构化回应意图**（purpose/emotion/intensity） | 未迁移 | 同属 B3；本批只让单字符串 `intent` 进入新的排序与缓存键。 |
| **G14 语义触发表情**（旁路概率） | 未迁移 | 依赖未开工的「入站用户意图/情绪 profile」消费者；V2 的 `role_work/state/mood` 是角色自身情绪，不能替代。强迁移会把角色情绪误当用户情绪触发发图（B6）。 |
| **G16 独立嵌入 provider / 超时** | 未迁移 | 拆分 provider 会让同一 owner 出现两套 binding，影响 `vectors.model` 与网关缓存语义（B7，收益小于风险）。 |
| **G10/G11 容量上限、删除、批量导入、rescan、分析态筛选** | 未迁移 | 管理面批次（B5）：V1 的静默截断是缺陷，需先定「导入前拒绝」与「已投递证据引用下能否删除」的口径。 |
| **G12 人工字段保护**（`manual_fields`） | 未迁移 | 与 `edit` 动作同批（B5），`payload` 内加键虽不需 schema 变更，但需与页面同步。 |
| **G13 视觉分析提示词配额** | 未迁移 | 提示词调整需重跑已标注素材才有意义，归 B5。 |
| **G8 的复核描述缓存**（`_reaction_vision_description_cache`） | 部分未迁移 | 三态与「复核结果进复核元数据」已迁移；V1 的进程内一句话描述缓存（`llm_tool_actions.py:6968-6985`）未迁移——V2 复核提示词是一次性的，缓存需要新的提示词段与失效口径（按 revision），收益（省一次识图）不抵新增的进程内状态面。 |
| 受管自有目录 96 条静默截断 | 不迁移 | 审计已判定为缺陷（应改造为显式拒绝），归 B5。 |
| 低延迟跳过复核 | 不迁移 | 见 4.2 的理由（默认开启会永久失去复核，且 V2 复核 fail-open）。 |
| 低延迟运行指标（`lookups/cache_hits/latency_ms`） | 未迁移 | V2 没有等价运行时指标消费者（`semantic_api` 状态只报 `gateway.metrics`）；登记无消费者的字段违反登记规则。缓存命中情况可通过 `_cached_lookup` 的返回在调试中断点观察。 |

## 六、测试

命令（AstrBot 自带 Python，临时目录指向 `.p4-tmp\temp`）：

```powershell
cd C:\Users\99505\.astrbot\data\plugins\astrbot_plugin_private_companion_v2
$env:PYTHONPATH='C:/Users/99505/.astrbot/backend/app;C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/.p4-tmp'
$env:TEMP='C:\Users\99505\.astrbot\data\plugins\astrbot_plugin_private_companion_v2\.p4-tmp\temp'; $env:TMP=$env:TEMP
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -W ignore -m unittest `
  tests.test_reaction_retrieval_settings tests.test_semantic_integration tests.test_semantic_host_api `
  tests.test_proactive_reactions tests.test_expression_style tests.test_isolation tests.test_group_memory
```

新增 `tests/test_reaction_retrieval_settings.py`（25 项）覆盖：配置字段登记/边界/枚举守卫/装配后真实读写、向量主导与词法封顶、非主导阈值、记忆侧默认参数零回归、相关度下限与弱匹配拒绝、扫描上限中性、语义簇与否定屏蔽、双分量降权、重复窗口与单素材不静默、缓存命中与四类失效、复核三态与失败换人、后台补齐批量/节流/单飞/开关/失败上报/重配置清理。

结果（同一命令，最后一次实际运行）：

```text
Ran 124 tests in 169.112s
OK
```

分模块项数：`tests.test_reaction_retrieval_settings` 25（新增）、`tests.test_semantic_integration` 21、`tests.test_semantic_host_api` 6、`tests.test_proactive_reactions` 6、`tests.test_expression_style` 47、`tests.test_isolation` 3、`tests.test_group_memory` 16。

### 观测到的偶发失败（与本切片无关，照实记录）

1. 并行工作流正在编辑 `companion_v2/host/application.py` 期间，曾出现一次 `AttributeError: 'CompanionApplication' object has no attribute 'busy_deferral'`（`accept` 已引用、方法尚未落盘）；再次运行时消失。
2. `tests.test_expression_style.ExpressionRotationTests.test_frequent_use_is_a_lower_probability_not_a_lock_out` 在一次混跑中失败（`4.198e-05 not greater than 0.8`），单独运行 47 项全通过，随后同一条混跑命令亦通过——`expression/style_rotation.py` 属其他工作流。
3. `tests.test_semantic_integration` 中三个多轮 reaction 用例（`test_confirmed_reaction_is_deprioritized_on_the_next_reply`、`test_automatic_probability_zero_keeps_explicit_reaction_request`、`test_late_reaction_receipt_accounts_once_after_catalog_revision`）在部分运行里命中 `HostFixture.until(seconds=3)` 的墙钟预算（`TimeoutError`，批次实际状态为 `delivering`、文本与图片都已投递）。已做归因测量：在**屏蔽**本切片新增读路径（配置读取 + 缓存键 + 后台调度）后，同一用例的一轮等待为 2.453s / 2.844s，含本切片时为 2.656s / 2.750s；`ReactionLibrary._select` 单次耗时 141/219ms（含检索与复核）对 94/16ms。即该用例本身在 3 秒预算边缘运行，本切片只贡献其中约 0.05–0.2s；同一用例单独运行、以及 124 项混跑均通过。不是本切片引入的逻辑缺陷。

## 七、接线

`companion_v2/host/application.py` 的登记（主代理已完成，`docs/V2_GAP_CLOSING_TASKS_20260927.md` 与 `docs/BUILD_STATUS.md` 仍由主代理统一更新）：

```python
from companion_v2.expression.reaction_configuration import (ReactionConfigurationOwner,
    configuration_fields as reaction_configuration_fields)
# extra 元组追加
*reaction_configuration_fields(),
# owners 追加
ReactionConfigurationOwner(runtime),
```

未改 `_conf_schema.json`、`main.py`、`pages/陪伴小屋/*`、`astrbot_host/semantic_api.py`：新键通过既有 `ConfigurationService` 读写，语义页 `configure` 仍只走 `SemanticStore`（新键不落在该 store，故页面不会出现「未知字段」错误；页面暴露留待统一接入批次）。

## 八、边界与残留风险

- 未构建交付包、未重载在线插件、未调用真实模型或平台端口。未改 `_conf_schema.json`、`main.py`、`astrbot_host/**`、`pages/**`。
- `candidate_limit` 默认 6 使内部候选池由原先硬编码的 12 降为 6：现有集成测试全部通过，但素材规模很大时可能牺牲召回；需要更大池时按窗口调高即可（上限 24）。
- 绝对下限 0.08 是按 V2 归一化词法尺度换算的估值，未经真实素材标定；如出现"该发却没发"，先看 `ranking`/`basis`/`clusters` 三个新返回字段，再调 `embedding_score_threshold`。
- 后台补齐与检索内联补齐可能对同一条目重复嵌入（幂等写入）；若要彻底串行，需要在检索路径内也持有 owner 锁，代价是回复延迟。
- 每轮新增约 9 次小 SQLite 读（配置快照 + 缓存键两处聚合 + 候选级用量聚合），实测在测试环境内 `_select` 整体 16–219ms；若未来目录很大，`_cache_key` 的两处聚合仍是 O(目录行数) 的索引扫描，可改为 `MAX(revision)` 单行读取（当前聚合同时覆盖条数变化，故保留）。
- 低延迟缓存是进程内状态：重启即失效（可接受，V1 同样是进程内）；`id(provider)` 之类的键已被 `binding()` 取代，因此更换 provider 配置也会正确失效。
