# 合并转发阅读开关迁移切片

日期：2026-10-03。V1 的 `enable_forward_message_adaptation` 是合并消息自然阅读总开关。V2 已有原生转发节点冻结、受众治理、来源追溯与结构化上下文；此前解析和提示词始终启用，配置项迁移不完整。

V2 在 `conversation.presentation.forward_message_adaptation_enabled` 提供等价开关，默认开启以保持已有回复行为。配置经既有 `ReplyManagement` 读写，并在每轮回复封存时捕获；关闭后不读取合并转发节点、不附加节点媒体和对应转发阅读提示。已封存旧回复快照缺少该字段时按开启处理，避免升级后改变正在运行或恢复中的回复语义。入站仍按原合同冻结并治理节点来源；该开关控制模型上下文使用，不绕过来源身份、预算和撤回校验。

V1 参考：`forward_message.py` 的 `_format_forward_message_context_prompt_section()` 在读取转发描述符前检查总开关。V2 沿用该开关语义，并保留 V2 的节点身份不可信、来源与受众隔离及工具续答治理。

实现落点：`companion_v2/conversation/reply_settings.py` 注册并校验配置；`companion_v2/conversation/messages.py` 在上下文构建时执行封存值；定向回归为 `tests.test_reply_management.ReplyManagementTests.test_forward_reading_setting_is_validated_and_sealed_per_batch` 与 `tests.test_conversation_forwards.ConversationForwardTests.test_forward_reading_can_be_disabled_in_the_sealed_reply_snapshot`。

配置与完整回复链仍按上述封存语义执行。陪伴小屋的「理解 → 图片与合并转发理解」同时提供阅读开关和宿主级摄取上限；上限对后续新消息即时生效，当前处理中的输入保留开始时的值。单目标与多目标均注册宿主设置路由；重复的插件配置表单入口隐藏。定向测试覆盖页面路由、上限保存、校验、实时桥接和封存值。本切片不表示 57 项总迁移验收完成。
