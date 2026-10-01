# V2 原生面盘点：不在 v1 迁移表内的能力（2026-09-27）

用户问题：`V2_GAP_CLOSING_TASKS_20260927.md` 那张表是**从 v1 配置项出发**列的迁移/改造/补全任务。**反过来看**——V2 自己长出来的原生能力现在什么状态？

口径：全部以工作区实际代码、注册表、宿主路由、测试与切片文档为准；**"源码在位"与"现场验收通过"分开写**。本文只做盘点，不改业务代码。

## 一、表面规模（脚本实测，不是估算）

| 维度 | 数量 | 证据 |
| --- | --- | --- |
| 已注册配置组 | **15** | `tools/audit_v2_native_surface.py` 输出；复刻 `companion_v2/host/application.py:150-160` 的装配 |
| 已注册配置字段 | **364** | 同上（`FieldRegistry.fields`） |
| 宿主 API 路由 | **63** | 14 个 `*WebAPI.routes()` 实枚举（`/reply` 5、`/model` 15、`/memory` 19、`/state` 2、`/life` 2、`/growth` 4、`/semantic` 2、`/perception` 2、`/perception-native` 3、`/acquaintance` 1、`/backup` 6、`/integration` 1、`/page` 1）+ 每群目标另派生 `/groups/.../reply`、`/groups/.../memory` |
| 后台任务种类（`TaskDefinition`） | **14** | `conversation.reply`、`conversation.deliver_part`、`proactive.compose`、`memory.reflect`、`role.state.maintain`、`calendar.plan`、`role.growth.progress`、`role.self_review`、`role.expression.learn`、`role.reading.consume`、`role.journal.write`、`role.journal.select`、`conversation.image_review`、外部工具 owner 自注册 |
| 存储 schema | `companion-v2.storage.v41` | `companion_v2/storage/schema.py:1582` |
| 生成输出契约（`output_format`） | **11** 种 | `conversation/foreground.py:349` 白名单 |

按段分布：`proactive.contact` **122** 字段（占全部配置面 33%）、`conversation.presentation` 84、`role.state` 56、`memory` 21、`role.life` 15、`conversation.image_review` 11、`expression.learning` 10、`conversation.perception` / `expression.reaction` 各 9、`model.conversation.reply` 8、`conversation.busy_gate` 7、`conversation.media_quota` 4、`role.growth` 4、`model.budget` 2、`person` 2。

字段级实测（`--fields`）两例，避免把"整组是原生"当成结论：

- `memory` 21 项 = 上下文/核心/检索预算 + 反思自动修复 + 反思响应格式 + **`group_episode_memory_enabled` / `group_episode_min_messages` / `group_episode_refresh_minutes` / `max_group_episodes`**（后四项是本轮原生/未入表项，挂在既有 `memory` 组里，因此该组是"移植 + 原生"混合）；
- `model.conversation.reply` 8 项 = `provider`、`fallback`、`prompt`、`max_output_tokens`、`timeout_seconds`、`fallback_on_refusal`、`replacement_rules`、`replacement_scope`，是 V2 模型网关自建的"任务 × Provider"矩阵，v1 的 `model_assignment_config`（43 键）是另一套形状。

## 二、纯原生能力（v1 没有对应键，也不在任何迁移任务里）

"纯原生"的判据：字段名或机制在 v1 的 1010 键进度表里查不到。抽查确认：`busy_activity_keywords`、`group_episode_min_messages`、`group_episode_memory_enabled` 均 **NOT_IN_V1_SCHEMA**；`enable_group_episode_memory` / `group_episode_refresh_minutes` / `max_group_episodes` / `busy_reply_max_delay_seconds` 在 v1 有键但**从未进入任务表**（见第四节）。

| V2 原生能力 | 落地证据 | 配置面 | 宿主写入合同 | 定向测试 | 切片文档 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 任务监督器 + 三通道执行器（前台/后台/模型） | `companion_v2/execution/`（supervisor、runner、service） | 无（按安装限额） | — | 全仓执行类用例 | `CORE_TASK_SUPERVISOR_SLICE.md` | 源码在位，页面无入口 |
| 模型网关：任务 × Provider 路由矩阵 + 替换规则 + 用量账本 | `model_gateway/routing.py`、`budget.py` | `model.conversation.reply` 8 + `model.budget` 2 | `/model`、`/model/configure` | `test_daily_token_soft_limit.py`、`test_model_replacement_stream.py` | `CORE_MODEL_GATEWAY_SLICE.md`、`DAILY_TOKEN_SOFT_LIMIT_SLICE_20260927.md` | **已接入**；`model.budget` 无独立路由，随模型页读 |
| 前台租约 + 证据封存 + 本地 outbox 六阶段 | `conversation/foreground.py`（`ForegroundStage`） | 无 | — | `test_foreground_conversation.py` 等 | `CORE_CONVERSATION_MESSAGES_SLICE.md` | 源码在位 |
| 人物相识卡（跨窗口同一个人） | `memory/person/` | `person` 2 | `/acquaintance`（**只读**） | `test_person_acquaintance.py` | `CORE_PERSON_ACQUAINTANCE_20260927.md` | 页面可读；写入只在内部 |
| 生图张数额度四档 | `conversation/media/quota.py` | `conversation.media_quota` 4 | **无** | `test_image_quota.py` | `IMAGE_QUOTA_SLICE_20260927.md` | 字段生效；**页面无控件** |
| 群图安全审核 + 私聊回退 | `conversation/media/review.py`、`review_service.py`、`fallback.py` | `conversation.image_review` 11 | **无** | `test_group_image_review.py` 18 项 | `GROUP_IMAGE_REVIEW_SLICE_20260927.md` | 字段生效；**页面无控件** |
| 繁忙回复闸门 | `conversation/busy_gate.py` | `conversation.busy_gate` 7（含 3 个原生关键词字段） | **无** | `test_busy_reply_gate.py` | `BUSY_REPLY_GATE_SLICE_20260927.md` | 源码 + 测试在位；页面无控件 |
| 群成员风控（规则命中 + 每日反思裁决） | `memory/group/hits.py` + v41 表 + `/groups/.../memory/safety` | 无字段（确定性规则） | 群记忆管理入口 | `test_group_member_safety.py` | `GROUP_MEMBER_SAFETY_SLICE_20260927.md` | **已接入**；真实群验收待现场 |
| 群聊片段记忆（按群周期整理，进既有反思链） | `memory/group/episodes.py`、`memory/episode_settings.py` | 并入 `memory` 组（`group_episode_*`） | `/memory/settings/command` | `test_group_episode_material.py` 8 项 | `GROUP_EPISODE_MEMORY_SLICE_20260927.md` | **已接入**；片段刷新到期判断未做 |
| 群词义（黑话）学习 + 语境召回 + 人工纠正优先 | `memory/group/slang.py`、`expression/semantic_service.py` | 并入语义配置 | `/semantic` | `test_semantic_integration.py` 等 | `V1_EMBEDDING_USES_AND_V2_ADOPTION_20260925.md` | **已接入**；无采纳/排除词表 |
| 表情反应资产库（原生 owner + 混合检索 + 视觉复核） | `expression/reactions.py`、`reaction_preferences.py` | `expression.reaction` 9 | **无**（语义页管素材，不管这组） | `test_reaction_retrieval_settings.py` | `REACTION_PERFORMANCE_AND_CONFIG_20260927.md`、`V1_EMOTION_REACTION_MIGRATION_AUDIT_20260927.md` | 并发窗口刚完成 B1/B2/B4 |
| 表达学习（取样 → 待审候选 → 采纳 → 轮换注入） | `expression/style_*.py` | `expression.learning` 10 | `/reply/expression/configure` | `test_expression_style.py` 47 项 | `HUMANIZED_AND_EXPRESSION_LEARNING_SLICE_20260927.md` | **已接入**（本批）；审阅列表控件待上页 |
| 感知设置（日历/农历/节气/黄历/平台标识/模型路由） | `conversation/perception_settings.py`、`date_context.py`、`agenda/annual_calendar.py` | `conversation.perception` 9 | `/perception`、`/perception-native` | `test_perception_host_api.py`、`test_solar_term_context.py` | `CORE_PERCEPTION_20260926.md`、`SOLAR_TERM_ALMANAC_SLICE_20260927.md` | **已接入**；自动节气 provider 默认关闭 |
| 拟人表达 Prompt（本批新增） | `conversation/humanized_expression.py` | 并入 `conversation.presentation` 2 | `/reply/configure` | `test_style_prompts.py` | `HUMANIZED_AND_EXPRESSION_LEARNING_SLICE_20260927.md` | **已接入** |
| 群聊防注入 / 隐私边界 / 现实承诺三闸 | `conversation/participation_prompts.py`、`text_processing.py` | 并入 `conversation.presentation` 3 | `/reply/configure` | `test_group_safety_guards.py` | `GROUP_SAFETY_GUARDS_SLICE_20260927.md` | **已完成** |
| 七个可选伴侣的原生执行链 | `astrbot_host/`（screen/reality/together/game/live/content/image） | 各提供方自持 | `/page/targets` 能力目录 | `test_astrbot_multi_live_acceptance.py` 等 | `NATIVE_REFACTOR_DEPENDENCY_AUDIT_20260925.md`、`GAME_LIVE_NATIVE_20260926.md`、`REALITY_TOGETHER_NATIVE_20260926.md` | 深度不一：Live 只读、Game 四种玩法、Screen 单次截图 |

## 三、原生面里**唯一一类真正的系统性缺口**：配置有合同、页面没入口

`tools/audit_v2_config_surface.py` 实测出来的映射（配置组 → 页面可写路由）：

| 配置组 | 字段 | 页面可写路由 |
| --- | --- | --- |
| `conversation.presentation` | 84 | `/reply/configure` ✅ |
| `proactive.contact` | 122 | `/state/command`（`contact.configure`）✅ |
| `role.state` | 56 | `/state/command`（`configure`）✅ |
| `memory` | 21 | `/memory/settings/command` ✅ |
| `role.life` | 15 | `/life/command` ✅ |
| `conversation.perception` | 9 | `/perception` ✅ |
| `expression.learning` | 10 | `/reply/expression/configure` ✅ |
| `role.growth` | 4 | `/growth/command` ✅ |
| `model.conversation.reply` | 8 | `/model/configure` ✅ |
| `conversation.busy_gate` | 7 | **—** ❌ |
| `conversation.image_review` | 11 | **—** ❌ |
| `conversation.media_quota` | 4 | **—** ❌ |
| `expression.reaction` | 9 | **—** ❌ |
| `model.budget` | 2 | **—**（随模型页读） |
| `person` | 2 | `/acquaintance` **只读** |

即：**33 个字段（`busy_gate` 7 + `image_review` 11 + `media_quota` 4 + `reaction` 9 + `budget` 2）只能通过 AstrBot 插件表单改，小屋页面看不到也改不了**。这四项都属于"已有真实读写合同、只是没接控件"，与 `AGENTS.md` 的"先补齐领域功能与生效配置，再统一接入陪伴小屋"第②阶段相符——不是设计缺口，是排期缺口。

另有一类"能力在位但没有查询/审阅合同"：主动候选池、用量聚合、表情素材的采纳/排除词表、表达候选的审阅列表页。这些在页面上目前只给边界说明，不伪造数据。

## 四、从 v1 出发的表**没有覆盖到**的东西

用 `tools/audit_v1_task_coverage.py` 交叉核对：v1 逐项进度表共 **1010** 个键，任务表正文里被反引号点名的只有 **54** 个。子类级状态与键级核对的差距是结构性的：

- `V1_V2_CONFIG_PROGRESS_20260926.csv` 里 **949/1010 行仍是"待逐项核对"**，只有 55 行有真实结论（"已接入（源码）"12、"已改造接入"10、"部分接入"24 等）。也就是说**键级账本基本没开始填**，子类级的"部分接入"不能反推每个键。
- 任务表用 `T25`（群片段）、`T52`（繁忙闸门）这类编号覆盖了一批键，但**编号粒度大于键**。例如：
  - **T25** 只点了一句"群聊片段记忆"，而 v1 的 `enable_group_episode_memory`、`group_episode_refresh_minutes`、`max_group_episodes` 在表里没有出现过；
  - **T52** 只点"繁忙回复闸门"，而 `busy_reply_min_delay_seconds`、`busy_reply_max_delay_seconds`、`busy_reply_proactive_resume_buffer_minutes` 同样没在表里出现；
  - **T48** 只列"表情低延迟模式等 4 项"，而 `reaction_expression_embedding_weight`、`_embedding_score_threshold`、`_candidate_limit`、`_semantic_trigger_enabled` 与受管自有目录 3 项都不在 T48 的清单里（另一窗口已完成 T48，可对照 `REACTION_PERFORMANCE_AND_CONFIG_20260927.md`）。
- 因此"任务表没提到"≠"没人做"，也≠"没人打算做"。真正的判据只有两个：**代码里有没有消费者**、**CSV 里那一行有没有结论**。前者现在可以脚本化核对（`audit_v2_config_surface.py`），后者需要继续按子类把 949 行逐项填掉。

## 五、结论

1. **原生面不小**：15 组 364 字段、63 条宿主路由、14 种后台任务、11 种输出契约、v41 存储。其中 33% 的配置面集中在 `proactive.contact` 一组。
2. **原生功能的状态普遍是"源码 + 测试 + 切片文档齐备，页面或现场验收待补"**，与我方切片记录一贯口径一致。已完成到"页面可读写"的只有 9 组。
3. **最值得先动的原生缺口是那 33 个"有合同没控件"的字段**——它们不需要新设计，只需要在既有页面（行动页 C4 / 产出页 C1 / 表达页 D3 / 模型页 E4）挂上控件，属于第②阶段统一接入的自然工作包。
4. **不要用任务表判断覆盖率**。表是按 v1 键编的编号；键级真实状态以 CSV 的 `V2配置项进度` 为准，而它有 94% 还是空白。建议下一批先做键级核对脚本（已有 `audit_v2_config_surface.py` 可扩展成"键 → 字段 → 消费者 → 路由"四列），再谈补哪些键。

## 六、可复跑命令

```powershell
$env:PYTHONPATH='C:/Users/99505/.astrbot/backend/app;C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 tools/audit_v2_native_surface.py
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 tools/audit_v2_config_surface.py
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 tools/audit_v1_task_coverage.py
```

三个脚本只读工作区、不连宿主、不调模型、不发送消息。
