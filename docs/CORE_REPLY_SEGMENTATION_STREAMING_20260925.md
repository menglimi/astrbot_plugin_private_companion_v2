# V1 回复分段与流式请求落地

2026-09-26 补充：[小屋语音配置与组合预览](CORE_REPLY_VOICE_SETTINGS_20260926.md)已将流式、分段、图片位置和语音策略纳入按对象/角色保存的配置快照。此页面保存无需更换运行档或重载，原宿主配置和历史验收记录保留如下；本体仍为 V2。

日期：2026-09-25。作用范围为 V2 接管的私聊、群聊普通回复，包含工具续答和原图尾段投递。

## 已实现

- 兼容 V1 的 `<<PRIVATE_COMPANION_SPLIT>>` 消息边界和 `{{split_marker}}` 提示词占位符。模型决定边界，提示词建议聊天短句分段、长文与代码保持连贯；可自定义提示词。
- 恢复只有单侧黏连正文的标记；行内、引用、代码、转义和占位符形态只清理，不据此拆开消息。连续、首尾标记不会产生空消息。普通换行不自动成为模型边界。
- 可选按句子或段落补充分段，配置长度阈值、最小段长和最多消息数。优先保留模型边界，再处理最长正文；超出段数时合并尾段，不丢正文。
- 保持围栏代码（包括变长、未闭合围栏）、引用、列表、表格、链接和行内格式完整；普通正文、Unicode 和原有换行保持不变。分段控制行本身不进入消息或确认历史。
- 复用现有持久分段、间隔、回执和重启恢复。下一段须等待上一段确认送达；未知回执停止余段，重启和重复入站均不重发。选中的图片只附在最后一段。
- 单目标 staging、多 Bot 私聊与群聊宿主均接通配置。新增选项保持默认关闭，旧运行档的序列化文档及指纹不变。
- 「陪伴小屋」已接入回复设置、草稿校验、离线分段预览、配置 CAS/幂等保存和最近 10 轮诊断；预览不调用模型、不发送消息，保存只影响下一轮封存回复。

## 流式语义

使用安装的 AstrBot OpenAI 兼容提供方 `_query_stream`，原生 SDK 负责累计响应。V2 只发起一次请求，关闭 SDK 重试；独立核对原始流的响应 ID、choice、结束原因、正文和完整工具参数，检测原生累计器吞掉错误后产生的缺字或残稿。

**收齐并校验完整响应后才生成发送分段，不进行逐 token 或提前半段发送。** 完整 JSON、claims、来源、人格、提供方和任务有效性检查仍然成立。工具参数完整且通过原合同后才执行工具；续答再走同一流式链，推理、JSON 外壳和工具增量不进入 QQ。

空流、缺少结束信号、截断、拒绝、坏 JSON、流中异常、响应 ID 变化、结束后仍输出正文、累计器内容不一致均不发布可发送稿件，也不自动改用非流式重试。取消、撤回和原任务到期关闭流；正常完成和异常也关闭底层流。

独立保留用量尾包和 `choices[].usage`，即使原生最终解析失败仍可结算已收到的实际用量。缺失或不一致的用量保持未知，不能记成零。私人书写、记忆反思等其他输出协议沿用原有非流式路径。

## 配置

在插件配置的「对话模型使用流式请求」和「回复分段」中开启。示例为现有配置的局部字段，不替代目标、人格和授权设置：

```json
{
  "model": {"streaming": true},
  "segmentation": {
    "enabled": true,
    "llm_controlled": false,
    "rules_enabled": true,
    "rule_mode": "words",
    "threshold": 500,
    "min_segment_chars": 5,
    "max_segments": 5,
    "prompt": ""
  },
  "runtime": {"part_gap_seconds": 2}
}
```

规则字数阈值表示自动分段的正文上限；超过上限时保留整段，模型明确给出的边界仍保留。规则分段会合并过短的气泡。分段词采用每行一项的编辑格式，配置仍保存为 JSON 字符串数组。

沿用宿主的固定运行档规则：初始化前配置；已经初始化的运行档不允许悄悄替换指纹，改变这些选项需使用匹配的新运行档。此轮未改变真实运行配置或自动启动插件。

## 实现位置

- `companion_v2/conversation/segment_control.py`、`segmentation.py`：标记清理、Markdown 保护、规则和提示词。
- `companion_v2/conversation/generation.py`：原对话生成、工具续答提示、完整稿审查及分段清单。
- `companion_v2/adapters/astrbot/streaming.py`、`provider.py`：单次流式请求、原始增量核对、用量与清理。
- `astrbot_host/settings.py`、`native.py`、`multi_settings.py`、`multi_session.py` 及 staging 配置/装配：单目标与共享宿主接线、旧指纹兼容。
- `_conf_schema.json`：流式与分段选项。复用原数据库结构，没有新的存储迁移。

## 验证

使用 AstrBot 自带 Python 和真实 AstrBot 4.27.2/OpenAI SDK，API 与 OneBot 传输使用合成替身，SDK 数据根和所有运行库均在临时目录；未使用真实模型额度或向真实 QQ 发消息。

流式、分段、宿主配置专项 **31 项均已通过**（原 30 项整组通过，补充 SSE 用例及更新的 9 项分段规则测试再定向通过）；回复管理页面与配置诊断另有 **3 项均已通过**，合计 **34 项**：

```powershell
$env:PYTHONPATH="$PWD;C:/Users/99505/.astrbot/backend/app"
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_reply_segmentation tests.test_astrbot_reply_streaming tests.test_segmented_stream_delivery tests.test_segmentation_host_settings tests.test_reply_management -q
```

覆盖 1/2/7/29/整条字符块下流式与非流式一致，跨块标记和 Unicode、工具参数增量与坏参数拒绝、累计器丢字、无结束信号和各种失败、usage 尾包及 choice 用量、取消/撤回/超时、人格/提供方变化、真实 SDK 工具续答到逐段投递、发送间隔、未知回执及重启不重发、图文尾段、单/多目标/群聊及配置重载。额外使用真实 OpenAI HTTP 客户端和本地 MockTransport，将 SSE 事件及中文/emoji 的 UTF-8 编码拆为 1/11/64 字节包，验证实际 SSE 解码、正文还原和底层流关闭。

相关回归运行 `tests.test_conversation_messages`、`tests.test_astrbot_model_wire`、`tests.test_astrbot_staging_config`、`tests.test_astrbot_staging_bootstrap`、`tests.test_astrbot_staging_host`、`tests.test_isolation`：**87 项中 86 通过、1 未通过**。唯一失败为共享工作树的 `storage/semantic.py:42 [unapproved_data_access] sqlite3.connect`；该文件不是本次分段改动，新增分段及流适配代码没有扫描违规。宿主加载、停机、路由注销及原对话行为回归通过。

测试日志在系统临时目录的 `companion-segmentation-stream-tests.log`、`companion-segmentation-sse-tests.log`、`companion-segmentation-regression-tests.log`。本记录不将存在独立隔离问题的整个工作树标为全绿。

## 后续

下一步针对选定真实模型做流式接口联调，并在 QQ 现场核对分段间隔、逐段回执、输入中状态和未知回执后的停止行为；本地 mock 已覆盖协议边界，不替代真实平台验收。

本轮没有宣称 V1 全量配置平移：按会话单独配置、任意正则/替换清理、主动消息与 TTS 专用分段仍需各自 owner 接线。若需要生成时立即发送首段，应先设计每段独立的证据审查和取消协议，不能将当前完整稿校验绕开。
