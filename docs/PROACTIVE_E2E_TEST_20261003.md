# 主动消息「完全模拟发送」端到端测试（2026-10-03）

本文记录这套端到端用例的**边界**：替换了哪个外部端口、哪些部分是真跑的、
怎么运行，以及它能证明什么、不能证明什么。

- 用例：`tests/test_proactive_end_to_end.py`
- 干跑脚本：`tools/run_proactive_sim.py`
- 样本与说明：`fixtures/proactive/`（`README.md`、`news_feed_sample.json`、
  `news_feed_juya_20261004.xml`）

## 1. 唯一的两个外部端口

这条链上真正会碰到外部世界的只有两处，测试只替换这两处：

| 端口 | 生产实现 | 测试替身 | 替换掉的是什么 |
| --- | --- | --- | --- |
| 新闻来源 | `astrbot_host/news.py` 的 `NewsRssPort` / `NewsJsonPort` 等 | `RecordedNewsPort`（真录制回放）、`SyntheticNewsPort`（手写近似） | 只有 HTTP 这一跳 |
| 平台发送 | `astrbot_host/onebot.py` 的 `OneBotPrivateSender` | `RecordingSender` | 只有平台 API 这一跳 |

平台发送是**唯一的外部副作用点**：整条链最终都汇到
`companion_v2/delivery/service.py:225` 的 `await self.sender.send(envelope)`。
`RecordingSender` 保留生产 sender 的调用顺序（先过 `envelope.before_dispatch()`
派发栅栏，再做"平台调用"，最后签发 `DeliveryReceipt`），所以它记录下来的就是
"如果平台可用，实际会发出去的那份 envelope"。

## 2. 真跑的部分（没有打桩）

| 环节 | 位置 |
| --- | --- |
| 新闻契机选择 | `proactive/news_events.py:239` `NewsContactEvents.select` |
| 契约分支（15 类契机） | `proactive/scheduling.py:158` `ContactSchedule._plan`（新闻在 `:256`） |
| 取源、窗口拒收、来源发布 | `proactive/news_events.py:308` `prepare`（24h 窗口在 `:354`） |
| 压制、预算、草稿封存、分片 | `proactive/service.py:380` `contact`、`:537` `_generate` |
| 归因后缀 | `proactive/news_events.py:28` `attribution_suffix`，由 `service.py:616` 追加到最后一片 |
| 排程 / 三态 / 回执 / 幂等 / 重启恢复 | `delivery/service.py:159` `queue`、`:222` `deliver`、`:236` `record_receipt`、`:295` `recover_dispatches` |
| 分片推进（第二片） | `proactive/service.py:812` `delivery_confirmed`，由 `host/application.py:736` 按秒调用 |

时钟、数据根与宿主：

- 合成宿主：`AstrBotCompanionHost`（`companion_v2/adapters/astrbot/application.py`），
  真注册表、真 provider 契约、真存储运行时。
- 临时数据根：`tempfile.TemporaryDirectory`，用例结束即删。
- 时钟：`tests/proactive_support` 一系的确定时钟（`DeterministicClock`）。
  录制样本的绝对时间与确定时钟基线不同，所以回放时整条时间轴平移
  （`RECORDED_ALIGNMENT_LEAD`），**原始响应体一个字节都没有改写**。

## 3. 新闻样本

`fixtures/proactive/news_feed_juya_20261004.xml` 是一次真实
`GET https://daily.juya.uk/rss.xml` 的原始响应体（593568 字节，sha256
`5a5145d6…bfcf2a`），由真解析器 `astrbot_host.news_parsing.parse_rss_news` 解析成
10 条。`news_feed_sample.json` 保存这次录制的清单。

生产端口现在在 `NewsJsonPort._read` 的会话级请求头中声明稳定的
`AstrBotCompanionV2/2.0` `User-Agent`（`astrbot_host/news.py`）；此前缺少请求头时
该站点可能返回 403 的问题已修复。录制脚本仍显式声明
`CompanionV2FixtureRecorder/1.0`，用于保持夹具可复现。样本证明的是"真实响应体
长什么样、真解析器把它变成什么"；另有一次当前网络直读在 2026-10-07 返回
`橘鸦AI早报` 的 10 条条目，确认默认 RSS 端口可以拿到真实资讯。

`SyntheticNewsPort` 是**手写近似样本，非录制**，只用于需要固定文案的断言
（分片与 TTS 渲染态、图片反应、拒收条件）；它与录制样本走同一个来源端口契约。

## 4. 用例覆盖

| 用例 | 覆盖 | 断言要点 |
| --- | --- | --- |
| `test_recorded_news_opportunity_reaches_the_platform_envelope` | 真录制样本走完整条链 | 目标对象、正文（含程序追加的归因）、分片、`delivery` 状态、回执引用、平台引用、尝试次数、来源对收件人可见 |
| `test_suppression_when_the_conversation_has_not_gone_idle` | 刚聊过 | 没有 envelope，且读得到 idle 门槛与已过时间 |
| `test_suppression_during_quiet_hours_names_the_reason` | 免打扰 | 没有 envelope，`preferences.reason("news") == "proactive_quiet_hours"` |
| `test_suppression_when_the_delivery_budget_is_exhausted` | 超频 | 没有 envelope，`contact_delivery_budget` |
| `test_explicit_failure_is_one_bounded_attempt_and_a_failed_receipt` | 明确失败 | 任务定义 `max_attempts=1`、只有一次尝试、回执 `not_sent`、再等一个窗口也不重放 |
| `test_platform_timeout_is_unknown_and_a_restart_never_replays_it` | 平台超时 | 状态 `unknown`、操作 `unknown`、无回执；重启后 `recover_dispatches()` 为空且不重放；晚到的可信回执仍落成 `delivered` |
| `test_same_idempotency_key_with_another_payload_is_refused` | 幂等键冲突 | 同 key 换 payload / 换时间被 `delivery_idempotency_conflict` 拒；换 key 落到另一条草稿身份 |
| `test_same_contact_opportunity_cannot_change_its_original_inputs` | 契机层冲突 | 同一机会换 `event_id` / `settings_hash` 被 `contact_news_changed` 拒 |
| `test_source_failure_opens_a_durable_breaker_and_its_window_release_recovers` | 熔断 | 失败后 `retry_after = at + 5min` 落库；窗口内端口不再被调用；窗口到期放行一次；来源恢复后自行送达 |
| `test_segmented_envelope_matches_the_sealed_parts_voice_and_poke_render` | 分片 + TTS/戳一戳渲染态 | 两片逐条对齐封存记录，归因只在最后一片；`build_component_plan` 的渲染结果与封存 `voice`/`poke` 一致 |
| `test_image_reaction_envelope_keeps_original_position_and_hash` | 图片渲染态 | 真选图 → `ImageDeliveryEnvelope` 带原图与位置，封存/投递行/回执同一份 payload |

## 5. 怎么跑

```powershell
$env:PYTHONPATH="C:/Users/99505/.astrbot/backend/app;C:/Users/99505/.astrbot/data/plugins"
$env:PYTHONIOENCODING="utf-8"
$env:TEMP="C:/Users/99505/.astrbot/tmp"; $env:TMP="C:/Users/99505/.astrbot/tmp"

# 端到端用例（另有既有的相邻投递/契机套件可一起跑）
C:/Users/99505/.astrbot/backend/python/python.exe -m unittest tests.test_proactive_end_to_end -v

# 打印"将要发送的 envelope"，默认一条都不发
C:/Users/99505/.astrbot/backend/python/python.exe -X utf8 tools/run_proactive_sim.py
C:/Users/99505/.astrbot/backend/python/python.exe -X utf8 tools/run_proactive_sim.py --json
C:/Users/99505/.astrbot/backend/python/python.exe -X utf8 tools/run_proactive_sim.py --source live-feed
C:/Users/99505/.astrbot/backend/python/python.exe -X utf8 tools/run_proactive_sim.py --record-fixture
```

### `--live` 为什么默认不可用

`--live` 需要**同时**满足三件事才会继续，缺一即停：

1. 显式加上 `--live`；
2. 环境变量 `COMPANION_V2_PROACTIVE_SIM_LIVE=1`；
3. 用 `--live-target` 明确写出收件对象。

即使三条都满足，脚本目前仍然会停下并提示：真发送端口**尚未接线**——
本仓库里唯一走过真平台的主动消息路径是插件自己的管理员投递测试
（`/astrbot_plugin_private_companion_v2/setup/proactive-diagnostic`）。
把真 sender 接进这个脚本是后续工作，不是这次交付的内容。

## 6. 能证明什么 / 不能证明什么

**能证明**

- 在给定的偏好、时钟与来源内容下，"如果平台可用"会发出去的那一份 envelope 是
  确定的：目标对象、正文（含只在最后一片追加的归因）、分片顺序、图片与语音/戳一戳
  的渲染态、以及参与 `payload_hash` 的封存内容。
- 压制（刚聊过 / 免打扰 / 超频）真的会把整条链挡在发送之前，而且原因是可读的。
- 明确失败只尝试一次；超时落成 `unknown` 并且重启后不重放；晚到的可信回执仍然算数。
- 同 key 不同内容会被拒；熔断窗口内的重复取源不会发生，窗口到期会恢复。

**不能证明**

- **系统时间**：确定时钟掩盖了真实调度抖动、超时竞争与跨秒边界的行为。
- **宿主适配层**：`AstrBotCompanionHost` 之上还有 `astrbot_host/` 的真适配
  （真 `AstrBot` 加载、真 `OneBot` 反连、真权限与会话）。这些不在本用例范围内。
- **平台语义**：`RecordingSender` 模拟的是"接口被正确调用 + 回执可信"，
  不证明消息在具体平台上真的可见、真的过了审核、真的按同一个顺序到达。
- **真网络**：录制回放不覆盖 DNS、TLS、限流、重定向与站点风控；第 3 节的现场直读
  只证明检查时刻的默认 RSS 可用，后台维护仍会记录失败并按间隔重试。
- **模型内容质量**：用例里的模型回答是固定的。文案是否自然、是否与人格一致，
  不由本套用例判定（那是提示词与人工核对的事）。
- **并发**：本套用例是单窗口、单条链。多窗口共享额度、并发排程竞争不在范围内。

## 7. 与既有用例的分工

- `tests/test_proactive_*`：各契机的合成端口行为（是否取源、如何退避、如何校验来源）。
- `tests/contact_schedule_support.py` 一系：调度与投递的阶段状态机。
- 本套用例：把上面两层与**真解析器 + 真排程 + 真投递**串起来，只把两个外部端口
  换成可打印、可编程的替身，并断言最终 envelope 的具体内容。
