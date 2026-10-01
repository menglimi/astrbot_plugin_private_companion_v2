# 框架异常文本拦截切片（2026-09-27）

依据 [V2 缺口补全任务清单](V2_GAP_CLOSING_TASKS_20260927.md) T03（E3 程序级，用户批注未提出异议，清单标记"直接做"）。迁移 V1 `enable_framework_error_leak_guard`（默认开启）的出站防护语义，按 V2 表达管线改造。

## 语义

- **内部身份锚点剥离**（V1 `_strip_internal_identity_anchors`）：出站文本中的 `[QQ:123456789]` 与独立的 `QQ:123456789`/`QQ：123456789` 锚点（5–12 位数字）被移除；不再做空白折叠与首尾清理，避免破坏 V2 的分段与 Markdown 保护语义。
- **框架异常转储整体替换**（V1 防泄漏目的的 V2 改造）：命中 Python traceback 头部（`Traceback (most recent call last):`）或同一文本内出现两条及以上 `File "...", line N, in ...` 栈帧行时，整段替换为安全文案 `（这条回复没有正常生成，按安全策略不予展示。）`。单条栈帧行（如正常讨论代码）不触发，保持保守。
- 开关：`conversation.presentation` 组新增 `framework_error_guard_enabled`（bool，默认 True，同 V1 默认）。关闭时文本原样通过（含锚点），与 V1 行为一致。

## 接线

- `conversation/text_processing.py`：`ReplyTextPolicy.framework_guard(text) -> (text, replaced)` 纯函数；`framework_error_guard_enabled` 经 `TEXT_DEFAULTS` 自动进入统一配置注册表（reply_settings 现有机制，无新 owner）。
- 被动回复与群回复：`conversation/reply_preparation.py` 的 `prepare_reply()` 在内容替换之前先过闸；命中转储时短路为单一安全分段，跳过分段/语音计划。
- 主动消息：`proactive/service.py` 成稿落库前的呈现块先过闸，替换发生在 `payload_hash` 计算与去重之前——存储稿、清单哈希、去重与实际发送保持同一文本；命中时 `presentation_reason` 记 `framework_guard` 供诊断。
- 不覆盖主动消息之外的其它后台文本（日记、提醒等非聊天正文）。

## 验证

- 新增 `tests/test_framework_guard.py` 7 项通过（AstrBot 自带 Python）：锚点剥离、开关关闭原样通过、traceback 整体替换、无头部多条栈帧替换、单条栈帧+正常代码讨论不触发、`prepare_reply` 命中短路为单段安全文案、`prepare_reply` 仅剥离锚点不替换。
- 受影响回归：`tests.test_conversation_messages` + `tests.test_reply_management` 34 项、`tests.test_proactive_dedup`（主动成稿链）随 43 项批次通过；`tests.test_image_quota` 8 项复验通过。
- 既有失败（与本片无关，临时回退 `prepare_reply` 改动复验确认）：`tests.test_astrbot_reply_streaming.test_partial_empty_truncated_refused_malformed_and_mixed_streams_never_publish`（SSE finish_reason 映射，未触及本片链路）；另有 [生图额度切片](IMAGE_QUOTA_SLICE_20260927.md) 记录的三项既有失败。

## 边界

- 未重载在线插件、未调用真实模型/QQ、未构建交付包；`conversation.presentation` 新字段的陪伴小屋页面接入属第②阶段。
- 检测模式保持保守（traceback 头 + ≥2 栈帧），避免误伤正常代码讨论；后续如需覆盖 AstrBot 专有错误串，按现场证据再扩模式表。
