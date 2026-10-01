# 群 Reply 音视频与合并转发原件

2026-09-25。在[群图片与引用](CORE_GROUP_MEDIA_20260924.md)、[群直接音视频](CORE_GROUP_AUDIO_VIDEO_20260925.md)和[转发节点音视频](CORE_GROUP_FORWARD_MEDIA_20260925.md)之上，群 Reply 现在可以引用直挂语音、视频和包含媒体的合并转发。原件捕获、当前模型输入、工具续答、跨成员历史、来源治理和重启恢复使用同一套已有服务。

## 已落地行为

- 固定当前 Bot 连接，用 `get_group_msg_history(self_id, group_id, message_seq, count=1, reverse_order=False, parse_mult_msg=True)` 读取一条原群消息。核对群号、账号、消息号和非匿名发送者；Reply 自带的显示正文、发送者和内联节点不作为原件依据。
- 在第一次附件异步读取前冻结文字、提及、媒体定位与完整转发节点树。音视频直接组件及嵌套节点均在每次读取前后检查原连接，完成后再次检查当前角色。未安装对应解码器、节点不完整、连接替换或超额输入不产生来源和成员授权。
- 复用 QQ SILK / PCM WAV 原件及完整音频视图；视频保存 MP4 原件，最多提供四帧有序 PNG 采样，不声称已检查视频音轨。普通文字/图片引用保持原描述符格式。
- 当前引用者、原消息发送者/转发者、节点显示账号与昵称分别保留。显示身份仍未认证；提示词说明历史附件不属于当前引用者的自述，发送时间不等于录制时间，节点资料不证明真实作者或本人经历。
- 直接附件、引用直挂附件、引用内转发和当前直接转发共用卡片、节点、文字、图片、音视频、采样帧、时长及保留字节预算。工具续答保留同一组实际媒体与来源证据。
- 对已在 V2 接纳的原群消息，先核验原群、账号、Bot、角色、会话和成员，再以原成员授权重新读取原件。正文、音视频描述和完整转发节点清单必须一致；已知私聊、其他群、其他角色或成员独立 session 的资料不能重新归为当前群引用。
- 引用来源关联原输入及所有原媒体、节点与采样帧来源。即便引用另存了完整附件副本，原件撤回、资产/来源撤权、原成员撤权或原件字节损坏仍会阻断引用和已封存群历史。已确认的 Bot 纯文字回复不能被额外附加音视频或转发节点。
- 后续群历史只保留原文字、`quotations`、含节点路径的 `forwarded_records` 及 `historical_metadata_only` 附件元数据；不重新发送旧音频或视频帧。原材料失效后移除其派生历史，无依赖的群友发言继续可见。已经取得的投递回执保留，unknown 发送在重启后不重发。

## 目录与存储

`companion_v2/adapters/astrbot/quote_content.py` 负责群聊/私聊共有的内容冻结和附件捕获；`group_quotes.py` 与 `quotes.py` 保留各自的定向读取和身份校验。群捕获总预算归 `group.py`，真实解码器由 `astrbot_host/quotes.py` 注入。

`conversation/quotes/group_originals.py` 负责已知群原件关联；`conversation/group_media.py` 负责历史元数据投影；引用与转发的媒体仍由已有 `quotes/`、`forwards/`、`media/audio/`、`media/video/` 服务管理。无 schema 迁移、独立媒体库或根级业务文件，根目录 Python 仍仅 `main.py`。

测试按责任放入 `tests/test_astrbot_group_quote_media.py`、`test_group_quote_media.py`、`test_group_quote_governance.py`、`test_astrbot_group_quote_entry.py`，合成夹具归 `group_quote_media_support.py`。真实 SDK 引用验收复用 `group_forward_entry_process.py` 的 `run(quoted=True)` 模式。

## 验证

新增 17 项测试。最终定向范围共 17 个模块、168 项测试及 120 个 subtest，按测试 ID 去重后均有通过记录。整批先得到 165 项和全部子用例通过，三项在四秒测试等待处超时；针对测试等待合同调整后，三项及一项保留默认等待的普通图片用例复验 4/4 通过。此记录不表述为整批一次全过。整批运行前后核对 58 个源码/测试文件，复验前后核对 11 个相关文件，均未在各自测试期间变化。

范围：`test_astrbot_group_quote_media`、`test_group_quote_media`、`test_group_quote_governance`、`test_astrbot_group_quote_entry`、`test_group_media`、`test_group_audio_video`、`test_group_conversation_context`、`test_astrbot_group_host`、`test_astrbot_group_forwards`、`test_conversation_quotes`、`test_astrbot_quote_host`、`test_astrbot_quoted_forwards`、`test_conversation_quoted_forwards`、`test_astrbot_history`、`test_astrbot_multi_host`、`test_astrbot_group_audio_video_entry`、`test_isolation`。另外独立运行 `group_media_entry_process` 和 `group_forward_entry_process` 默认模式，均通过。

运行环境为 AstrBot 自带 Python，测试进程设置 `PYTHONPATH=C:/Users/99505/.astrbot/backend/app`，SDK 导入前设置临时 `ASTRBOT_ROOT`。只使用合成图片、SILK/WAV/MP4、模型替身和本地 reverse WebSocket ACK。

专项覆盖直挂与嵌套媒体冻结、错误原群/账号/消息、缺失解码器、读取中连接替换、混合预算、原件篡改/附件缺失回滚、三层归因、工具续答、跨成员原件权限、确认 Bot 原件防伪、撤回及再导入、资产与来源撤权、原成员撤权、字节损坏、重启复读和未知发送不重放。

真实 SDK 流程使用 `main.py`、真实群消息/Reply/Record/Video/Forward 类型以及真实 reverse WebSocket 编解码，完成三成员原消息→引用→历史，验证本地发送 ACK、终止、数据库关闭、管理路由注销和核心模块释放。普通群图片/引用和原群转发入口也纳入受影响验收。

测试调整保留说明：八帧混合视频及原件历史超过默认模型测试 profile 的保守输入估算，专项显式声明更大的合成 profile，没有修改生产默认额度。撤回断言修正为失效派生材料不可见、无依赖的群友发言保留。SDK 引用验收两次触及旧四秒等待；诊断测得引用与后续历史分别约 4.1 / 5.8 秒成功完成，因此测试等待辅助器新增可选参数，群引用媒体夹具、该 SDK 专项及既有的三层确认引用测试显式使用十五秒；其他调用仍默认四秒，生产超时不变。复验中三个重流程整项耗时约 21.3 / 15.3 / 8.7 秒，包含各自多个批次，普通图片用例约 1.6 秒。

## 下一步

群聊图片出站已由[后续切片](CORE_GROUP_IMAGE_DELIVERY_20260925.md)接通原群受众、原图选择、图文回执、确认历史与再次引用。接下来推进生成/编辑图片的产物采用与投递。管理/拓展页由另一任务继续推进；真实 QQ 返回格式、实际模型识别和客户端效果仍需独立现场验收。本次没有在线重载、真实 QQ/模型调用或 V1 数据访问。
