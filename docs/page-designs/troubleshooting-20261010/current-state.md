# 排障页现状清单（2026-10-10）

来源：`pages/陪伴小屋/maintenance-page.js`（`diagnosticsMarkup()` 起，行 1712），
样式在 `maintenance-page.css`。以下只记客观事实，不做评价；评价见文末「待决」。

## 一、页面骨架：单列纵向六段

真实布局是单列堆叠（`.maint-dashboard-grid` 两列栅格是死 CSS，JS 从不输出该 class）。
排障面板 `maint-diagnostics-panel` 内部顺序：

| # | 区块 | 函数 | 关键内容 |
|---|---|---|---|
| 0 | 面板头 | `diagnosticsMarkup` | eyebrow `DIAGNOSTICS / 01` + h3「排障与测试」；右侧状态徽标（N 项错误/关注/运行正常）、「清除本次结果」、「重新检查」 |
| 0.5 | 结果提示 | `state.diagnosticNotice` | 测试结果提示，15 分钟 TTL 自动清除（`DIAGNOSTIC_RESULT_TTL_MS`） |
| 1 | OVERVIEW | `categoriesMarkup` + `categoryFocusMarkup` | 结论行 + **12 个分类按钮** + 当前分类工作区（note / 3 项 facts / 跳转按钮） |
| 2 | SIGNALS / 02 | `diagnosticItems` 渲染 | 严重程度筛选（全部/错误/警告/信息）+ 问题条目（mark / 标题 / detail / 动作按钮） |
| 3 | CHECKS / 03 | `proactiveTestMarkup` + `memoryDiagnosticMarkup` + `integrationsMarkup` | 主动消息测试、内存增长检测、链路与扩展测试（文本 Provider / TTS / 图片工具） |
| 4 | EVIDENCE / 04 | `timelineMarkup` + `operationsMarkup` | 事件时间线 + 运行快照 + 模型任务路由审计 + 「运行证据台」details（7 类证据，按分类过滤） |
| 5 | FAQ | `diagnosticFaqMarkup` | 按分类的问答，每条带一个跳转按钮；非 `all` 分类时默认 `open` |

## 二、真实数据合同

### 12 个分类（`diagnosticCategories`，行 122）
`all / model / identity / tasks / delivery / proactive / image_generation / voice / storage / prompt / budget / cache`
每项 `[key, 名称, 描述]`，另由 `categoryEvidence()` 给一个证据短语。

### 信号（`diagnosticItems`，行 1132）
`add(severity, category, title, detail, action)`，severity ∈ `error / warn / info`。
真实会产生条目的分类只有 **model / identity / tasks / budget / cache / storage / delivery / voice / image_generation**。
**`prompt` 与 `proactive` 不会产生任何信号**——它们在 `diagnosticItems` 里没有分支，
只在 `categoryEvidence` / `operationsMarkup` 里有只读证据。

信号来源字段：
- `stats.failures / active / unconfirmed / unknown`（调用回执）
- `data.providers[]`（V2 文本适配器）
- `data.runtime.identity_scope{dashboard_operator, role_access, token_ledger}`
- `state.modelStatus.tasks[]{kind, fields.provider.value, fields.fallback.value, fields.max_output_tokens.value, capabilities[], application_state}` × `modelStatus.providers[]{id, capabilities, max_output_tokens}`
- `data.budget{limit_tokens, spent_tokens, held_tokens, soft_limit_enabled, soft_limit_tokens}`
- `stats.cacheRate / cacheCoverage / cacheTelemetryCalls`
- `data.runtime.storage{journal_mode, foreign_keys, synchronous, busy_timeout_ms, page_count}`
- `data.runtime.conversation[]{no_reply, failed_parts, unknown_parts, pending_parts, flow_state, flow_reason, input_count, part_count, delivered_parts}`
- `data.runtime.inbound_no_replies[]{reason_code, scope, event_ref, code, observed_at}`
- `state.integrations.voice.providers[]` / `state.integrations.image.actions[]{action, registered, current}`

### 分类工作区（`categoryFocusMarkup`，行 1246）
每类 3 项 facts + 0~2 个跳转按钮 + 一句 note（note 是**边界声明**，如"仅展示校验状态，不输出身份、账号或会话标识"）。

### 事件时间线（`timelineMarkup`，行 1330）
从 `recentRows(data)` 取前 12 条生成调用事件，再叠加 `inbound_no_replies` 与 `runtime.conversation`；
按时间倒序，**`slice(0, 16)`**（静默截断，无"还有 N 条"提示）。
按 `state.category` + `state.severity` 双重过滤。

### 运行快照（行 1728）
7 项：`all/identity/tasks/model/delivery/voice/image_generation`，各带值与 `ok/warn/unknown` 状态。

### 运行证据台（`operationsMarkup`，行 1370，`<details open>`）
按分类 `show([...])` 过滤，7 类：
1. 统一身份与隔离（3 行：管理身份 / V2 管理授权 / Token 账本）
2. V2 SQLite 存储（同步级别 / 锁等待 / 外键 / 数据库页 + 只读检查按钮）
3. 消息收口与投递（`flows.slice(0, 6)`）
4. 未回复记录（最多保留 500 条）
5. 消息聚合与防抖追踪（`debounce_trace`：安静窗 / 合并上限 / 收口时限）
6. 上下文注入来源（`materials.slice(0, 8)`：owner / purpose / state / uses）
7. 主动触达记录（`proactive{calls, latest_at}`）

每类下方都有 `.maint-evidence-note` 边界声明。

### 三类主动检测（CHECKS / 03）
| 检测 | 副作用 | 结果字段 |
|---|---|---|
| 文本 Provider 探测 | **调用 Provider，可能计费** | `latency_ms / code / stage / exception_type / error / request_id` |
| TTS 合成 | 生成短音频，**不发给联系人**，可能计费 | 同上 + `audio_base64 / audio_mime_type`（可试听） |
| 原生图片工具 | 只验注册，**不提交生成请求** | `registered / current` |
| SQLite 完整性 | 只读 `quick_check` + 外键核对 | `integrity[] / foreign_key_issues` |
| 主动消息测试 | 端到端，12 个目的可选，需 `confirm_delivery` | `stages[]`（14 段）/ `skip_reason` / `decision_confidence` / `silence_threshold` / `budget_usage` / `failure_title` / `explanation` |
| 内存增长检测 | 每 10 秒采样一次、共 3 分钟（18 样本），离开页面停止 | `rss_bytes / rss_source / python_tracing_active / python_heap_current_bytes`；阈值 4 MiB 关注 / 16 MiB 增长嫌疑 |

### 未确认与未知的处理（不可违背的边界）
- 结果未知**不自动重放**（避免重复计费 / 重复回复）
- 投递回执未知**不自动重发**
- 不展示消息正文、用户与群号、身份与会话标识
- 不保存宿主令牌与音频原文（缓存隔离：`maintenanceCache` + `currentMaintenanceScope()`）

## 三、客观问题清单（待用户点哪些是真问题）

### 设计稿缺口对照（2026-10-10 03:30，V2 后端 + v1 面板逐项核对后）

**V2 真有而设计稿 v1 缺失（已全部补进 index.html）：**

| # | 缺失功能 | 真实实现 | 设计稿补法 |
|---|---|---|---|
| 1 | 全局「重新检查」 | `data-refresh` + `state.loading`，同步状态三态（已连接/正在同步/同步异常） | 页头右侧刷新按钮（spin loading 态）+ `syncLive` 状态点，点击重放渲染 |
| 2 | 跨子页跳转 | 信号 action → `data-set-call-filter`（failed/uncertain/cache-low）与 `data-focus-panel` | 证据卡 actions：route 卡「查看失败调用」、calls 卡「查看未确认记录」、cache 卡已有；`probe:kind` 直达检测抽屉对应卡并高亮闪烁（`openProbe`） |
| 3 | FAQ 常见问题 | 每分类一组 FAQ，答案末尾带定位按钮（真实文案 1540–1575 行） | 新增 05 板「常见问题」9 条真实文案，按当前分类过滤，按钮可直达探测卡 / 证据卡 / 最近调用 |
| 4 | TTS 试听 | `audio_base64` → `<audio controls>` 内联回放 | TTS 卡 note 说明成功态提供内联试听；演示保持无 Provider（不造假控件） |
| 5 | 内存采样细节 | `rss_source`（Windows 工作集 / Linux /proc）、`python_tracing_active` / `python_heap_current_bytes`、页面隐藏自动停止 | 结果区补「采样来源」「Python 堆：未开启追踪」「离开本页自动停止」三行 |
| 6 | 磁贴动态状态 | 磁贴状态是 ok/unknown/warn 计算（1730–1735 行），不是纯信号计数 | 磁贴名前状态点 `data-tone`（error/warn/info/unknown/ok）；voice 演示为 unknown |
| 7 | 余额接口可用性 | `balance` API（available/configured） | 预算证据卡 stats 补「余额接口：已配置 · 可用」 |
| 8 | 同步状态指示 | `maint-live`（已连接/正在同步/同步异常） | 页头 `syncLive` 状态点 |

**v1 有而 V2 无后端合同（链路测试已于 10-10 进设计稿，其余待产品拍板）：**

| v1 能力 | 位置 | 备注 |
|---|---|---|
| 链路测试 | `chain_tests`（proactive_message / image_generation_text2img / image_generation_selfie / tts_generation）+ `normalize_diagnostic_result` 信封 + 测试诊断弹窗（步骤 / 诊断记录 / 结果预览 / 复制诊断） | **已进设计稿**（10-10）：抽屉分「链路测试 + 单点探测」双区；主动消息链 = V2 现有合同（14 阶段），文生图 / 自拍 / TTS 链带「后端待补」徽标；后端合同落码时补 |
| 警告抑制 | `suppressed_warning_types` + 屏蔽管理器 + summary「已屏蔽 N 类」 | V2 后端无此字段 |
| 提示词注入追踪 | `troubleshootingPromptInjectionMarkup`（module 分组注入明细） | V2 只保留来源元数据 |
| 主动触达强度 | `troubleshootingProactiveIntensityMarkup` | V2 只有触达计数 |
| ok 作为信号级别 | summary「错误/警告/信息/正常」四级 | V2 ok 只是计算状态，不进信号清单 |

### 原问题清单

| # | 现象 | 位置 |
|---|---|---|
| P1 | 分类切换是**全页重算**：选一个分类后，overview / signals / checks / evidence 四段同时变，但没有任何区块标注"这里变了" | `diagnosticsMarkup` 各段共用 `state.category` |
| P2 | 12 个分类按钮**完全等权平铺**，且每块都带数量 + 证据短语，信息与 SIGNALS 区的条目重复 | `categoriesMarkup` |
| P3 | 焦点跳转（`data-focus-panel` / `data-focus-target`）跨越大半页跳到 CHECKS / EVIDENCE，跳转后上下文丢失，高亮是一次性的 | `categoryFocusMarkup` actions |
| P4 | `prompt` / `proactive` 两类**永远没有信号**，选中后 SIGNALS 是一整块空态，与普通"筛没了"无法区分 | `diagnosticItems` 无对应分支 |
| P5 | CHECKS 区与分类耦合：非 `all/model/tasks/voice/image_generation` 时显示空态"此问题类型没有安全的主动测试"，占一整块 | `integrationsMarkup` |
| P6 | 多处静默截断：时间线 `slice(0,16)`、flows `slice(0,6)`、materials `slice(0,8)`，无"还有 N 条" | 各处 |
| P7 | 运行快照 7 项与 overview facts 信息重复（如 Provider 数量出现两次） | 行 1728 vs 行 1266 |
| P8 | FAQ 在非 `all` 分类时**默认展开**，占一屏篇幅 | `faqOpen` |
| P9 | 内存检测是唯一耗时 3 分钟的交互，却与另外两个即时测试并排塞在同一区块，权重被拉平 | CHECKS 区 |
