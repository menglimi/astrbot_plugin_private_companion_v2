# 缓存诊断设计稿 ↔ 插件现状对照（需补齐清单）

> 落地状态（2026-10-10）：下文保留审阅时的历史缺口，当前实现已补齐后端统计与前端设计。
> 完整请求估算已包含参考材料；事件已提供严重度、会话摘要、八位指纹和最多 20 条展示；
> 六个签名维度已有稳定命中率及可判定基数。确认覆盖、趋势、环比和两组拉链图已接入真实字段。
> 实现、数据口径及验证范围见 [落地记录](implementation-20261010.md)。

- 设计稿：`docs/page-designs/cache-diagnostics-20261009/index.html`
- 对照基准：`pages/陪伴小屋/maintenance-page.js` 的 `cacheMarkup()` / `cacheDiagnosticStats()`
  （2042–2171 行）、`companion_v2/model_gateway/management.py` 的 `_cache_diagnostic_summary()`
  （51–209 行）、`companion_v2/model_gateway/cache_diagnostics.py`（111–254 行）
- 结论分三类：**A 已有支撑**（可直接落码）、**B 口径错误**（改前端即可）、**C 需后端补齐**。
- 本清单**不删 UI**：C 类保留在设计稿里，等后端补齐后直接接线。

---

## A. 已有数据支撑（无需后端改动）

| 设计区块 | 真实字段 / 来源 | 代码位置 |
|---|---|---|
| 命中率总览 `68.4%` + 进度条 | `stats.cacheRate` = `cached / cacheInput` | maintenance-page.js:826 |
| 有效输入缓存命中 `x / y` | `stats.cached` 与 `cached+creation+other` 派生 | 同上 |
| 四项度量：缓存读取 / 缓存写入 / 普通输入 | `stats.cached` / `stats.creation` / `stats.other` | 2158 |
| 确认覆盖 | `stats.cacheCoverage` = `cacheCalls / knownCalls`（**百分比**） | 827 |
| Token 构成四段（命中 / 写入 / 普通输入 / 输出） | `cached / creation / other / output` | 2051 |
| Provider 表现：命中率 + 有可计算确认次数 + 写入量 | `cache_input_tokens` / `cache_reported_calls` / `cache_creation_tokens` | 2058 |
| 低命中清单（输入 ≥ 1,000 Token 且命中率 < 20%，最多 5 条） | 与真实过滤条件完全一致 | 2045–2047 |
| 请求上下文 5 项（材料 / 消息 / system / 工具 / 完整请求）+ 延后 · 不可用 · 媒体 | `context_*` / `message_*` / `system_*` / `tool_*` / `request_*` 全套 | 2166–2170 |
| 签名诊断后 3 项（材料尾部收缩 · 资料可用性 · 变化后命中率） | `context_tail_trims` / `context_availability_changes` / `cache_hit_drop_after_change_calls` + 可比均值 | 2164 |
| 签名状态四种（等待首次调用 / 尚未采集 / 等待可比 / 观察到变化） | `signatureState` + `signatureStatus` | 2110–2115 |
| 事件前后快照（材料条数 · 字数 · 字节 · 估算 · 延后 · 不可用 + 消息 / system / 工具 / 媒体） | `signature_snapshot()` | cache_diagnostics.py:228 |
| 事件样本池 80 条 | `event_sample_limit: 80`、`deque(maxlen=80)` | management.py:75 / 208 |

---

## B. 口径错误或前端可自算（改前端即可，不动后端）

| # | 设计稿现状 | 真实口径 | 处理 |
|---|---|---|---|
| B1 | 确认覆盖写成 `86,432`（Token 数） | 是**百分比**（覆盖率，不是 Token） | 改成 `78.4%` 一类百分比 |
| B2 | 完整请求标注「= 前四项合计」 | `request_est_tokens = system + message + tool`，**不含参考材料** | 文案改为「system + 消息 + 工具文本估算」；若业务上应含材料，则升级为 C 类新增字段 |
| B3 | 低命中清单只有任务 / 提供方 / 时间 / 命中率 | 真实还带**输入 Token 量** | 补一列输入量 |
| B4 | 变化类型码 `tools_change` / `material_prefix_change` / `material_tail_shrink` / `material_availability_change` | 真实枚举：`tool_definition_change` / `context_prefix_change` / `context_tail_trim` / `context_availability_change` | 全量改真名；并补上真实存在的 `provider_change`、`system_order_drift`、`tool_order_drift`、`context_order_drift`、`context_reset`、`model_change` |
| B5 | 事件一行一个类型 | `changes` 是**数组**，一次调用可同时命中多种变化 | 改成多 chip 并列 |
| B6 | 事件列表 12 行、备注「可扩至 20 条」 | 前端 `slice(0, 5)`，样本池 80 | 改 5 行 + 「最近 80 条事件样本」说明 |
| B7 | 上下文各项百分比（54.5% 等） | 后端只给估算 Token，百分比需前端派生 | 可算，但分母口径必须与 B2 一致 |
| B8 | 四项度量的 sparkline 迷你趋势 | `data.daily` 已有 `cached_input_tokens` / `cache_creation_tokens` | 前端按日取点即可，无需后端 |
| B9 | 命中率「相比上个周期 +12.6%」 | 现有 `usageComparison()` 只比 Token 总量 | 前端按上一窗口聚合 `cached/input` 可算出；若要求与后端同口径则转 C 类 |

---

## C. 需要后端补齐（保留 UI，等接线）

| # | 设计要的东西 | 现状 | 需要补什么 | 落点 | 代价 |
|---|---|---|---|---|---|
| **C1** | 事件「严重度」`high / medium` | 事件 dict 无 severity 字段 | 新增严重度判定并输出（建议按变化类型分级：provider_change / model_change → 高；order_drift → 中；availability → 低） | `management.py:197` event dict 加 `severity`；分级表放 `cache_diagnostics.py` | 小 |
| **C2** | 事件「会话」列（`8e3f3ae9`） | 事件只带 `day / at / kind / provider / previous_provider` | 取 `conversation_id` / `session_id` 写入事件 | `management.py:95–106` SELECT 与 `:197` event；schema 已有该字段（`schema.py:652`） | 中 |
| **C3** | 「前后变化」哈希对照（`tool f27a5c1e → 8d4a7e22`） | `signature_snapshot()` 刻意只输出体量与估算，**不输出哈希**（隐私策略：只存哈希、体量、估算，不存正文） | 若确需展示，扩展快照输出哈希字段——哈希本身不含正文，不违反现有策略，但属于放宽 | `cache_diagnostics.py:228 signature_snapshot` | 小（需产品拍板） |
| **C4** | 签名诊断前 5 项的「稳定时命中率 %」（稳定前缀 / system / 工具定义 / 材料顺序 / 材料前缀） | 后端只有**变化次数**与总体可比 delta，**没有按签名维度分组的命中率** | 新增按维度聚合：对每个维度记录「与前一次相同」的调用的 `cached` / `input`，才能算该维度稳定时的命中率 | `management.py` daily 新增各维度分子分母字段（约 6 组）+ 前端展示 | 中～大（要先定分组键与分母） |
| **C5** | 签名卡小字「有效请求 287,441 / 241,337 / 512,883」 | 只有 `*_changes` 与 `*_calls`，没有「该维度可判定基数」 | 采集时记录各维度可判定基数 | 同 C4 | 中 |
| **C6** | 事件列表扩到 12 / 20 条 | 前端 `slice(0, 5)`，样本池 `maxlen=80` | 提高前端 slice 上限（20 条在 80 条池内可行） | `maintenance-page.js:2090` + `management.py:75` | 小 |
| **C7** | 命中率环比（若要求后端同口径） | 缓存诊断 daily 只按所选范围汇总 | 返回上一周期同口径聚合 | `management.py` 增加上周期聚合；或按 B9 前端算 | 小 |

---

## 建议的推进顺序

1. **先修 B 类**（半天内，纯前端）：口径错了会让落码后的页面比现在的设计稿更假；B2 的「完整请求」口径要请产品确认是否应含参考材料。
2. **再补 C1 / C2 / C6**（小代价，收益直接）：严重度、会话 ID、事件条数都是设计里已经画出来、只差字段的东西。
3. **C3 单独拍板**：哈希对照要不要放，是隐私策略问题，不是工作量问题。
4. **C4 / C5 是最大的一块**：它决定「请求前缀签名诊断」这张卡到底是「变化计数器」还是「稳定命中率看板」。当前后端是前者；设计稿画的是后者。要做后者，得先定义清楚每个维度的分组键和分母，否则算出来的百分比没有意义。
