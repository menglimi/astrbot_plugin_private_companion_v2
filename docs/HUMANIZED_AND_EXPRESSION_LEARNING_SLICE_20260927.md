# 拟人表达、表达学习分布、决策页沉默切片（2026-09-27）

> 历史切片。2026-10-08 表达学习已改为从当前窗口的原始用户消息取样，配置扩展为 22 项，接入素材审核、三档强度和回复／主动消息发送前复核。下文原“只观察 Bot 自己回复”的说明仅描述旧实现，不再代表现状。当前功能、差异与验证记录见 [V1 表达学习对照](EXPRESSION_V1_ALIGNMENT_20261008.md)。

范围：用户点名的四项 + 两项文档交付。口径取自本轮用户批注：**拟人 Prompt 用各渠道既有风格组承载**、**表达学习的分布问题用"用后降权"解决**、**决策页 B4 挂真实控件**、**以 v1 现有实现为参考改造而非空白重写**、**攒批统一测试而非逐项跑**。

## 一、拟人回复 Prompt：可选开关 + 可自定义

### 结论：不需要新范式

注入点本来就在：`ReplyTextPolicy.instruction`（`companion_v2/conversation/text_processing.py:227`）已经是 `conversation.presentation` 组的 T44 载体，并且：

- 被动回复经 `conversation/generation.py:58` 读封存快照 → `text_policy(...).instruction` 前置进本轮 instruction；
- 主动消息经 `proactive/service.py:267` 把 `TEXT_DEFAULTS` 里的键封存进 `presentation_settings`，再在 `:330` 注入；
- 群聊走同一份 `conversation.presentation`（`conversation/messages.py:591` 对私聊与群聊都写入 `reply_settings`）。

所以加"开关 + 自定义文本"只是在同一组加两个字段，页面补控件。

### 交付

| 落点 | 内容 |
| --- | --- |
| `companion_v2/conversation/humanized_expression.py`（新） | `enable_humanized_expression` / `humanized_expression_prompt` 的语义、默认文本、4000 字上限与控制字符校验；`instruction` 属性在关闭时返回空串，所以"关掉"等于整段不注入 |
| `companion_v2/conversation/text_processing.py` | 两个新字段进 `ReplyTextPolicy`；`style_prompt` 上限由 2000 提到 4000，与拟人文本一致；`instruction` 在风格补充之后追加拟人块 |
| `companion_v2/conversation/reply_settings.py` | 无需改动：字段经 `TEXT_DEFAULTS` 自动登记为 `FieldDefinition`（共 76 项） |
| `pages/陪伴小屋/reply-page.js` | 新增「拟人回复」分区：开关 + 正文文本框；交付物校验同步加入 `style_prompt`（此前页面不认这个后端已有字段）与两个新字段 |

默认文本（可用，也可整段替换）：

> 以下要求只决定怎么说，不改变要表达的意思、事实、来源与权限边界。
> 像平时聊天那样回应：优先口语化、简短、一次只讲一件事，不做列表式罗列，不写小标题，不输出多余的前后缀、称呼堆叠、括号补充或 emoji 标签。
> 不要每次先复述或总结对方说的话，不要用「首先/其次/总之」「希望对你有帮助」「还有什么可以帮到你」这类服务话术，也不要为了一句寒暄补一段解释。
> 允许句子长短不一、允许直接接上一句。情绪、判断和不确定都照实说，不必包装成中立的说明文。
> 同一轮里不要重复上一轮已经说过的措辞；没有新内容时，宁可少说一句。

### 与 MaiBot 的有意差异

MaiBot 的拟人化包含"刻意保留打错字、连发碎句、大小写不一致"。**本实现不含这些**：V2 的出站文本经分段、违禁词与出站清洗链路，投递后不可撤回；要求模型故意打错字会直接损伤已送达文本。已实现的是不会破坏文本的那部分（简短、口语、不啰嗦、不复述、少服务腔、允许不整齐）。

### 安全边界

拟人块是**管理员设定的呈现偏好**，注入时显式声明"不是新的事实、授权或来源，也不能覆盖本轮的具体要求"。它挂在 `request.instruction`（第二个 system 消息）而不是 `role_instruction`；后者是 host 人格锚点、按字节写进批哈希（`conversation/messages.py` 的 `role_instruction` 列），不能改。开关关闭时块完全消失，不残留空行。

## 二、T28 表达学习配置化 + 分布修复

### 2.1 常量配置化（原 T28 待办）

新增配置组 `expression.learning`（`companion_v2/expression/configuration.py`，owner 与 consumer 同名，`layers=(WINDOW,)`，`ApplyMode.IMMEDIATE`），10 个字段全部 `FieldDefinition` 化，注册进 `host/application.py`：

| 字段 | 默认 | 范围 | 原硬编码位置 |
| --- | --- | --- | --- |
| `group_learning_enabled` | False | — | 群聊学习此前不存在 |
| `window_hours` | 168 | 1–720 | `style_evidence.MAX_WINDOW_HOURS` 上限、`ExpressionSampleCatalog.window_hours` 默认 |
| `sample_limit` | 24 | 4–64 | `style_evidence.SAMPLE_LIMIT` |
| `min_samples` | 4 | 1–16 | `style_evidence.MIN_SAMPLES` |
| `sample_chars` | 800 | 40–4000 | `style_evidence.MAX_SAMPLE_CHARS` |
| `rules_per_turn` | 8 | 1–16 | `style_context.MAX_RULES` |
| `payload_chars` | 4000 | 500–16000 | `style_context.MAX_PAYLOAD_CHARS` |
| `rotation_candidate_limit` | 24 | 1–64 | 新增轮换池 |
| `rotation_decay_hours` | 336 | 1–8760 | 新增用后降权窗口 |
| `scan_interval_minutes` | 1440 | 5–10080 | `ExpressionStyleService.scan_seconds` |

跨字段规则（单批不能小于样本下限、候选池不能小于每轮注入数）在 `ExpressionConfigurationOwner.preview_set/write` 里校验——通用补丁路径只逐字段校验范围，不补这两条的话会写进一份"看起来已保存、实际被读回默认值"的配置。

### 2.2 群聊学习（此前完全不运行）

`style_evidence._authorize` 此前硬要求 `scope.kind is PRIVATE`，群聊学习根本不执行。现在分两种作用域：

- **私聊**：仍只取"发给同一位参与者"的回复；
- **群聊**：取该群内 Bot **自己**的全部已确认回复（`conversation_sent_history` + 送达回执），**不按触发者过滤**——群回复面向集体受众，按触发者过滤会丢掉大部分群内表达，这正是群学习看起来是空的原因。

群学习的扫描入口不在 `state_maintenance.bindings`（`host/application.py:405` 对群作用域提前返回，群上下文从不绑定）。因此 `ExpressionStyleService` 直接从 `conversation_batches` 还原每个群的最新上下文与角色绑定，并用 `_bound()` 重新校验角色是否仍然当前；群学习按 `group_learning_enabled` 显式开关，默认关闭。

群聊批次新增了 `expression_style` 快照，而 `group_history` 对 `contributions_json` 做的是**严格键集合校验**，会让历史群回复变成"无法阅读的历史"。已把它加入允许集合，并只做形状校验、不再重解样本句柄——否则一条规则退役就会把一条**已经送达**的群回复从历史里删掉。

### 2.3 分布修复：学了很多却只用几条

原实现按 `decided_at DESC` 取 8 条，等于"最近采纳的永远被用"，学得越多、越用不到。

新机制照抄 v1 的梦境碎片池（`astrbot_plugin_private_companion/dreaming.py:325` 的有效权重、`:442` 的加权无重复抽样），落在 `companion_v2/expression/style_rotation.py`：

- 每条已采纳规则记录 `injections` 与 `last_injected_at`，存在 `runtime_metadata`（每个"角色×窗口×规则"一行，**不升 schema**）；
- **从未用过**的规则权重 `5.0`，永远优先于任何用过的规则；
- 用过的规则权重 = `pow(0.72, 等待天数) × max(0.05, 4/(4+使用次数))`：0.72 是 v1 的**每日比例**（不是半衰期），使用次数饱和到 0.05 的地板；
- 抽样是**按权重不放回**，不是取前 N 条，所以轮到的是整个池子而不是头部几条；
- 权重没有下限淘汰：使用多只降低概率，**不会**把管理员采纳过的规则永久排除。

抽样在 `capture` 时以 `[context.key, captured_at, rules_per_turn, decay_hours]` 为种子抽一次并写进封存快照，所以同一轮重读（`validate_generation`、投递前复核）永远得到同一批规则；注入后记一次使用，下一轮自然轮到别人。

审阅视图（`style_management.list`，`state="adopted"`）现在额外返回 `injections` 与 `last_injected_at`，让"哪几条一直在被用"在页面上可见。

### 2.4 页面接入

- 表达页 D1（`#manage/expression`）已有 `ReplyManagement` 工作区，新增「拟人回复」分区；
- 学习页 L1 新增「表达学习」工作区（`pages/陪伴小屋/expression-page.js`，新增 `<script>`）：取样、注入、轮换三组数字 + 群聊开关，含"未确认保存保留待核对"的回执语义；
- 读写走既有 `/reply` 路由族新增的两个动作（`/reply/expression`、`/reply/expression/configure`），因此**私聊、多目标、每个群**都自动可用，不新增路由前缀、不新增注册点。

## 三、决策页 B4：行为规划与沉默真实控件

`#manage/decision` 的 B4 由"没有查询接口"的边界卡改为真实工作区：`renderRoleState('contact')` 复用 `state-page` + `state-editor` 的联系安排组件（`proactive.contact` 组，读写经 `state/command` 的 `contact.configure`），并保留"候选池没有查询接口、不推算不伪造"的边界说明。

`state-contact.js` 补上此前**后端已存在但页面没有控件**的两项：

- `silence_min_confidence`（开口置信度门槛，默认 0.66）；
- `silence_feedback_penalty`（沉默反馈降权，默认 0.2）。

为此新增 `probability` 控件类型（0–1、允许 0，与 `weight` 的">0"语义区分），并在摘要行显示"开口门槛 / 沉默降权"。

## 三之二、把「有合同没控件」的字段一次接到页面

上一轮的原生面审计（[V2_NATIVE_SURFACE_AUDIT_20260927.md](V2_NATIVE_SURFACE_AUDIT_20260927.md) 第三节）实测出**31 个字段有真实读写合同、页面却看不到也改不了**。本轮一次接完，不逐组开工。

### 接入的四组

| 配置组 | 字段 | 层级 | 落点 |
| --- | --- | --- | --- |
| `conversation.media_quota` | 4 | 安装 + 角色 | 产出页 C1「生图治理」 |
| `conversation.image_review` | 11 | 会话（窗口） | 产出页 C1「生图治理」 |
| `expression.reaction` | 9 | 会话（窗口） | 表达页 D3 |
| `model.budget` | 2 | 安装 + 角色 | 治理页 E4「每日软限额」 |

`conversation.busy_gate`（7）另有 T52 切片在做，本轮不动，避免与并行工作冲突。

**这四组本来就都有 owner、FieldDefinition 与真实消费者**（`host/application.py:169-175` 逐个注册），缺的只是宿主读写路由；所以本轮不需要新设计，只需要把已有的 patch 合同接到页面上。层级差异是硬约束而不是选择：额度与软限额**没有窗口层**（`quota.py:30-32`、`budget.py:36-39` 都写明了理由——一次对话不该能改全天的额度），因此它们按角色层读写，控件也如实标注作用范围。

### 后端

新增 `companion_v2/configuration/management.py`：一个 `GroupEditor` 基类按组自身 `layers` 决定目标（`WINDOW` 层走窗口目标并复核实名参与者与角色绑定，否则走角色层），四个子类各自绑定组常量。`status()` 只回短字段名（页面看不到全限定 field id），`configure()` 走 `ConfigurationService.patch`，带 operation key 幂等、edit token CAS 与 `check_generation`，并把 `ConfigurationError` 桥接成 `TaskError` 以免契约错误逃逸成 500。

新增 `astrbot_host/configuration_api.py`：`/config`（GET，可按 `?sections=` 取子集）与 `/config/configure`（POST，带 `section`）。多目标侧由 `multi_api.configuration_routes()` 把同一组路由挂到每个角色的路径上；单目标侧在 `web_api.py` 注册。这一处踩到一个坑：`removeprefix` 会把 `/config` 一起吃掉（生成的是角色根路径而不是 `/config`），改为**前缀替换**后才正确。

### 前端

新增 `pages/陪伴小屋/config-editor.js` + `config-editor.css`：一个按分区渲染的小编辑器，`create(kinds, rootProvider)` 返回 `read/paint/save/act`。

- READ 一次取回多个分区，**在写状态之前先逐分区校验**——被拒的分区不能留下半个草稿（草稿的 token 从未被接受，接着存只会撞 CAS）；
- 各分区**各自持有 edit token**：角色层的额度与窗口层的审核是两个目标，令牌不可互换；测试里专门验了交叉使用会被拒；
- 未确认的保存按既有约定留在 `sessionStorage` 供核对，重试复用同一 operation key；
- 草稿超范围一律不派发，只提示。

### 顺带修掉的两项（本就登记在生图设计稿里）

1. **密钥可以清除了**。`models-page.js:716` 原本是"留空即保留"，因此**没有办法清除已存密钥**；现在每个已配置密钥旁多一个「清除已保存的密钥」勾选，勾选即在 diff 里显式提交空值，未勾选时空值仍然表示保留（避免半填表单误清）。
2. **配额日界与角色日历同源了**。`ImageQuotaGate` 原取 `messages.timezone_name`（装配处从不传参，等于恒为 `Asia/Shanghai`），而角色日历用可配的 `conversation.perception.calendar_timezone`；现在优先读后者、读不到再回落。非默认时区下两者原本会在不同午夜归零。

### 顺带发现并修掉的一个既有缺陷

写新测试时发现 `_used()` 把 `_day_start()` 的 **datetime 直接绑进 SQL**：Python sqlite3 会把 datetime 渲染成 `'2026-09-20 16:00:00'`（空格分隔、无微秒），而库里存的是 `stamp()` 的 `'2026-09-20T16:00:00.000000+00:00'`。文本比较下空格(0x20) < `T`(0x54)，于是**任何早于当天的记录都被判定为"在当天之后"**，配额只增不减、永不归零（限了张数就永久锁死，直到改配置）。既有测试样本都落在同一天，所以一直没暴露。现在 `_used` 显式 `stamp(...)` 后再比较，并加了跨时区/跨日界的回归。

### 验证

- 新增 `tests/test_configuration_api.py` 4 项：四分区读取与角色/窗口作用域、角色与窗口各自独立保存且跨目标隔离、重放幂等、交叉令牌被拒、非法请求与未知字段被拒、单目标也注册路由。
- 新增 `tests/test_config_editor.cjs` 6 项：一次读取两分区并各持令牌、被拒分区不留半个草稿、只发本分区变更与本分区令牌、未确认保存留待核对且不生成第二个操作、超范围不派发、`config_api` 缺失时回落到 reply 路由族。
- `tests/test_image_quota.py` 新增日界随时区变化的用例（UTC+14 与 UTC+8 对同一条尝试给出不同结论）。
- 统一批次 13 模块 **204 项通过**；页面检查器 `test_config_editor.cjs` 6、`test_reply_page.cjs` 6、`test_expression_page.cjs` 4、`test_models_page.cjs` 24、`tools/check_state_contact.cjs` 11 全部通过。

## 四、文档交付

- `docs/V1_EMOTION_REACTION_MIGRATION_AUDIT_20260927.md`：v1↔v2 表情包/反应图片系统迁移差距审计（v1 的 37 个 `reaction_*` 配置键中 8 个已对应、6 个部分对应、9 个无对应物；三条主要退化：缺"按回应意图"的偏好维度、向量只作等权加分而无分布相对排序、缺低延迟缓存与容量淘汰）。**只出审计，未改代码。**
- `docs/MEMORY_REFLECTION_DREAM_FUSION_DESIGN_20260927.md`：反思与梦境压实融合设计稿（S0 选材 → S1 抽取 → S2 压实候选 → S3 审阅落地；第一期不新增表、不升 schema，压实只产 `correct`+`retract` 组合操作，候选默认待人审；群侧第一期不纳入）。**只出设计，未写实现。**

## 五、验证

统一批次（AstrBot 自带 Python，`PYTHONPATH=<astrbot>/backend/app`）：

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest `
  tests.test_expression_style tests.test_style_prompts tests.test_proactive_text_presentation `
  tests.test_reply_management tests.test_reply_web_api tests.test_conversation_messages `
  tests.test_host_application tests.test_group_participation tests.test_reply_text_processing `
  tests.test_group_safety_guards tests.test_group_reply_host_api -q
```

结果：**159 项，1 error**。唯一失败是 `test_reply_web_api.SingleReplyWebAPITests.test_single_host_enables_voice_without_reload`，报 `staging_intent_invalid: the pinned staging configuration is unreadable or invalid`；同时刻独立运行 `tests.test_astrbot_staging_config`（6 项，1 failure / 5 errors）与 `tests.test_astrbot_staging_host`（20 项，15 failures）同样失败，原因是本工作树**多窗口并行**：另一窗口正在改 `companion_v2/adapters/astrbot/staging.py` 与 staging 配置形状（期间还出现过 `NameError: BudgetSoftPolicy is not defined`）。与本切片无关，本轮未改动 staging 相关文件。

页面检查器（Node，直接执行以避免沙箱禁止 `node --test` 的子进程管道）：

- `tests/test_reply_page.cjs` 6 项通过（含拟人开关与超长正文拦截）；
- `tests/test_expression_page.cjs` 4 项通过（新增：读写路径、非法组合拦截、未确认保存保留待核对、重置基线）；
- `tools/check_state_contact.cjs` 11 项通过（新增：沉默两项控件与范围校验）。该检查器原有 1 项因 `renderPreferences` 已改为多行而被正则断言卡住，本轮一并放宽。

## 六、未完成与风险

- **未接真实模型与现场验收**：拟人块的模型效果、群学习在真实群的产出质量、轮换在多规则下的实际分布，都需要带真实 provider 与真实群验证。合成测试只证明合同与分布算法成立。
- **审阅控件未上页**：已采纳规则的 `injections` / `last_injected_at` 已在管理 API 返回，但列表页工作区留到页面批次。
- **群学习的成本**：群聊学习默认关闭；开启后每个群按 `scan_interval_minutes`（默认 24 小时）产生一次后台模型调用。
- **`MIN_EFFECTIVE_WEIGHT` 恒为 0**：当前没有"淘汰冷规则"的能力，只有降权。
