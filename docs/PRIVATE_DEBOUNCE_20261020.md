# 私聊连续输入防抖（2026-10-20）

## 问题

普通私聊由 AstrBot 核心管线处理。此前每条私聊事件独立进入 `prepare_core_reply` 和模型请求，用户连发“在吗”“我想问你个事”“就是那个”会得到多轮回复；这正是上一轮[拟人化打磨](HUMAN_LIKENESS_POLISH_20261020.md)中尚未解决的“逐条应答”。

本次增加**纯文本私聊的连续输入防抖**：同一私聊 target 的输入进入一个 pending 轮次，最新原生事件负责承载最终回复。每条输入先解析会话上下文和回复设置；静默窗口内的后续文本并入该轮并重置等待。静默结束后，插件把合并正文写入最新事件，再执行完整回复准备、核心模型请求和发送前授权，因此合并回复保留最新消息的原生 ID 与事件序号。

为了在静默窗口开始前读到窗口配置，`prepare_core_reply` 拆出了只做 capture、身份/权限核验和回复设置读取的 `prepare_core_reply_context`。它返回 `CoreReplyPlan`；完整回复准备在静默窗口结束后执行，并在 intake 锁内复核 target/context。若人格或窗口已切换，不会沿用旧身份授权结果。

## 窗口规则

窗口由三条边界控制：

- 每条窗口最短 `private_debounce_min_ms`，默认 1500 ms；
- 每条窗口最长 `private_debounce_max_ms`，默认 4000 ms；
- 从该轮第一条消息起的总上限 `private_debounce_total_ms`，默认 8000 ms。

窗口长度按**最后到达的消息**的非空白字符数自适应：

```text
n = 最后一条消息的非空白字符数
base = max_ms
floor = min_ms
ratio = min(1, n / 60)
quiet = base - (base - floor) * ratio

以 。！？!? 或换行结尾：quiet -= 0.2s
以 ，、；：…… 或没有句末标点结尾：quiet += 0.3s / 0.2s
quiet = clamp(quiet, min_ms, max_ms)
```

效果：

- “在吗”“🥺”等极短消息接近 4 秒；
- 10–20 字的消息约 3.4–3.8 秒（句末有明确标点时略低）；
- 60 字以上、语义已完整的长消息接近 1.5–1.7 秒；
- 以逗号、省略号或悬空短句结尾时稍微多等，以句号、问号或换行结尾时稍微少等；
- 连续发送时每次新消息重置窗口，但总等待从第一条起不超过 8 秒。

## 合并行为

- 每个私聊 target 独立维护一个 pending 轮次；第一条消息确定总时限，最新到达的原生事件拥有最终回复。
- 每条输入通过 `prepare_core_reply_context` 捕获自身身份和上下文，读取该角色的 `conversation.presentation` 窗口策略。只有仍为最新 owner 的事件可以继续等候和提交该轮；较早事件完成异步检查后会被标记为并入，不会覆盖最新事件。
- 后续纯文本消息加入 pending、重置窗口，并在 `InboundNoReplyLedger` 记一条 `suppressed`，原因代码 `private_debounce_merged`；它们不会各自准备或各自回复。
- 静默窗口结束后，把 pending 中的文本按顺序合并为一条消息，更新最新 owner 事件的 `message_str` 和 Plain 组件，再以该事件的计划执行完整准备、核心决策、发送前复核和发送路径。最终模型请求和发送授权都使用同一条最新原生事件。
- 新输入在旧事件执行异步准入或等待期间到达时，会取得该轮 owner 并唤醒旧等待者；只有最新 owner 能 `finish`。如果旧事件的回复开关检查晚于新事件返回关闭，它只能取消自己，不能中止最新事件的 pending。
- 停机时关闭防抖管理器并唤醒窗口等待任务。`finish` 在锁内取快照，保证消息要么并入本轮，要么开启下一轮，不会被静默丢弃。
- 只处理**完全由 Plain 组成**的私聊消息。图片、语音、视频、文件、引用、合并转发、At、表情和其他组件立即走原路径；命令在防抖之前已经分流。
- 非纯文本消息不会取消正在等待的文本轮次；文本轮次仍按自己的窗口回复，媒体按原路径回复。

## 配置

配置在 `conversation.presentation`，按角色共享并可在当前窗口覆盖；入口是「陪伴小屋 → 决策 → 参与节奏 → 私聊节奏 · 连续输入」：

| 字段 | 默认 | 范围 | 说明 |
| --- | --- | --- | --- |
| `private_debounce_enabled` | 开 | 布尔 | 总开关；关闭后每条私聊独立回复。 |
| `private_debounce_min_ms` | 1500 | 1500–4000 | 每条窗口下限；长消息靠近该值。 |
| `private_debounce_max_ms` | 4000 | 1500–4000 | 每条窗口上限；短消息靠近该值。 |
| `private_debounce_total_ms` | 8000 | 2000–8000 | 从第一条起的总上限，不会超过 8 秒。 |

`reply_settings.validate` 校验范围与 `min <= max <= total`；非法值拒绝保存。字段不进入 staging 身份指纹，调整节奏不会重钉身份。窗口在 `prepare_core_reply_context` 中读取，正式准备与静默计时并行；读取失败时 `debounce=None`，按普通核心回复处理。

## 边界与已知取舍

- **计划使用最新事件**：静默结束后才做完整回复准备，记忆和知识召回使用合并后的正文；计划中的原生 event ID、权限复核和最终发送仍绑定最新事件。
- **合并输入时序**：`debounced_inputs` 保留每条真实输入的 `received_at`。`private_reply_context` 用最早一条输入作为前后对话边界，同时逐条保留时间；输入之间已经发出的助手消息会出现在 `after_input`，可供模型判断后续那条输入是否在承接它。
- **总上限只约束防抖等待**：模型准备、模型调用和发送耗时不在 8 秒内；8 秒是“等对方补话”的上限。
- 真实 QQ 客户端的到达顺序、输入状态和“正在输入”连续性未在本轮验证；宿主测试使用合成事件和本地替身。

## 日志与诊断

- `私聊防抖并入上一轮`（DEBUG）：后续文本加入 pending，不暴露正文。
- `私聊防抖合并`（INFO）：本轮实际合并了多条文本，记录 `event_id`、target、消息条数和合并字符数。
- `私聊防抖合并` 的入站台账原因代码为 `private_debounce_merged`，极性为 `suppressed`，不会当成“预期未回”刷平台日志。

## 验证

- `tests/test_private_debounce.py`：策略窗口、长短消息顺序、句末标点、上下限、连续输入总上限、旧 owner 取消保护、关闭唤醒和回复配置校验。
- `tests/test_main_core_reply.py::test_private_text_burst_uses_latest_event_for_merge_and_authorization`：窗口内两条输入只准备一次，合并正文、最终事件 ID 与发送授权均属于最新事件。
- `tests/test_main_core_reply.py::test_stale_event_reply_disabled_does_not_abort_latest_pending`：旧事件的回复开关异步返回关闭时，最新 pending 仍能正常提交。
- `tests/test_private_reply_context.py`：合并消息保留各自到达时间，并以最早输入作为时序边界。
- `tests/test_astrbot_staging_config.py`：25 项通过，确认 staging 合同未受 `CoreReplyPlan` 拆分影响。
- `tests/test_main_core_reply.py` 全组通过；`tests/test_private_closing.py`、`tests/test_segment_spacing.py`、`tests/test_core_reply_perception.py` 仍通过。
- 未调用真实模型、QQ 或 Laya；未重载在线插件。
