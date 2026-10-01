# T14 违禁词出站闸切片记录

## 范围

迁移 V1 的 `enable_forbidden_word_recall`、`recall_forbidden_words`、`recall_forbidden_scope` 和 `recall_forbidden_word_case_sensitive`，并按 V2 的封存配置与统一出站链路接入。

## 实现

- `ReplyTextPolicy` 负责有限 JSON 词表解析、空值/控制字符校验、大小写匹配和作用域判断。
- 普通回复在模型成稿经过群现实承诺处理后、分段前拦截，命中不会建立 `conversation_parts`。
- 已建立的普通回复分段在 `validate` 与 `_dispatch` 按封存配置逐段复核，命中阻止当前段及后续段。
- 主动消息在最终归因后复核；命中保存为 skip，不创建可发送正文；交付读取旧草稿时再次复核，防止历史草稿绕过策略。
- 配置字段通过 `TEXT_DEFAULTS` 自动进入统一 `FieldDefinition` 注册表，不在业务链中复制默认值。

## 约定

- 默认关闭；空词表不拦截；默认大小写不敏感。
- `bot_only` 与 `bot_and_group` 覆盖 Bot 出站，`group_only` 仅覆盖群 scope；策略函数同时接收 `scope_kind` 与 `is_bot_output`，不会把普通私聊入站消息误当作 Bot 出站。
- 命中使用结构化 `forbidden_word_blocked` 错误；主动消息使用 `presentation_reason=forbidden_word` 的 skip 记录，不改写正常正文。

## 验证

`tests.test_reply_text_processing`：11 项通过。包含默认关闭、群作用域、Bot 出站身份、大小写敏感和配置校验。

会话/主动完整测试暂受 AstrBot 运行环境 Pillow `_imaging` 二进制导入错误阻断，需修复该宿主依赖后再运行。
