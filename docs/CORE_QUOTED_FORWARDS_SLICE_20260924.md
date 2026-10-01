# Reply 引用合并转发

日期：2026-09-24。私聊 `Reply` 可以引用包含合并转发的原消息；普通引用及转发节点支持静态图片、GIF/APNG/动态 WebP、语音和视频。一次定向读取完成冻结与捕获，现有对话链负责生成、工具续答、撤回/撤权检查、确认回复依赖和重启恢复。视频向模型提供有界采样帧，不提供音轨；语音提供完整受限音频视图。实现使用既有媒体来源、授权读取和预算合同，不新增数据库表或迁移。合成闭环及真实 AstrBot SDK 接线已完成，真实 QQ 与模型效果尚待验收。

## 读取合同

只从原生 Reply 冻结组件位置和消息 ID。固定当前 Bot 账号及好友，用 `get_friend_msg_history(self_id, user_id, message_seq, count=1, reverse_order=False, parse_mult_msg=True)` 读取一次。返回必须恰有一条、匹配原消息号及自账号、属于好友私聊，原发送者只能是当前好友或当前 Bot。

原消息可包含文字、图片、`record`、`video` 和已展开的 Forward。复用 `adapters/astrbot/forwards.py` 中的冻结及捕获函数，按各卡片自己的 `data.content` 解析；同 ID 的不同卡片保持独立内容与组件位置。外层引用及全部节点的图片、音频、视频定位符先整体冻结，再开始附件读取；API 对象、客户端集合和连接在历史读取及各附件等待前后复核。等待期间的账号、连接或人格变化不能转成已接纳输入。

不消费 `Reply.chain` 的正文或显示身份，也不逐个查询 `get_forward_msg`、全局 `get_msg` 或节点显示 ID。节点内 Reply 和原消息中的嵌套 Reply 缺少可信原 peer/受众合同，仍明确拒绝；未展开节点及其他不支持组件在附件读取前拒绝整份引用。这里只保证保留本次返回的节点，原受众与未返回历史保持未知。

## 归因与原件治理

- 当前引用者仍是唯一的入站 principal；引用不会改变记忆主体。提示中分别说明当前引用者、原私聊消息的转发账号、节点显示账号/昵称及未知真正作者。语音录制者、说话者与视频拍摄者/画面人物也保持未知，除非原件本身能证实。
- 原消息发送时间和节点显示时间分别保留。Bot 曾转发资料不代表当前角色创作、亲历或认同；节点文字不作为本轮用户自述或新的指令。这些语义由归因材料和提示词表达。
- 来源依赖为当前输入 → 引用原消息 → 转发根 → 节点 → 图片/音频/视频及视频采样帧，嵌套节点继续依赖父节点。所有媒体来源继承当前私聊受众，保持原子发布和失败回滚；原消息撤回或来源授权失效时，派生媒体不能继续读取。
- 若原用户转发已进入 V2，必须对照已接纳正文、卡片及全部节点清单，并重读原图片/帧、语音和视频；引用链接入原消息及其节点和媒体来源。原消息撤回、原资产撤权或内容改变会阻止继续读取和重新导入。已知原件属于另一宿主会话时不重新归属。
- 工具续答保留同一组引用证据和模型图片；合法增加的工具结果独立加入。已确认回复的记忆来源依赖这些原件，生成后撤权会阻止发送，未知模型或投递结果不自动重放。
- 尚未进入 V2 的外部原消息只保留首次定向读取快照，没有 QQ 远端撤回订阅或后续变化同步。

模型图片按当前组件 → 引用内部组件 → 转发节点路径 → 节点内部组件排序。节点先后以及嵌套前后的图片不会被合并成同一层顺序；帧保留原转发者、当前引用者和原消息号。

## 预算与兼容

直接转发与引用内转发共享最多 4 张外层卡片、32 个节点及 65536 字符的节点正文/显示昵称预算。图片/动画继续共用原件、模型帧和字节预算；音频遵循每轮最多 4 条、累计 120 秒，视频最多 2 条、累计 180 秒，每段视频最多提供 4 个抽样帧，并与其他媒体共用留存字节/帧预算。单条超额输入明确失败，整轮合并超额另开批次，跨重启继续从持久清单恢复。

不含音视频的引用及节点仍使用原 `CapturedQuote` / `QuoteDescriptor` 与 `ForwardNodeDescriptor`，旧事件不增加空媒体字段，序列化形状与内容指纹保持。含音视频的条目使用扩展描述符；恢复时按字段存在性分派，因此已有事件及节点可读取，无 schema 迁移。复用现有来源、依赖、Asset、音频和视频原件表。

## 文件归属

| 位置 | 职责 |
| --- | --- |
| `companion_v2/conversation/quotes/forward_models.py` | 扩展引用清单、内部转发父视图及三层归因提示 |
| `conversation/quotes/models.py`、`service.py`、`originals.py` | 兼容恢复、引用来源、音视频授权读取及已知原件复核 |
| `conversation/forwards/models.py`、`service.py`、`media_events.py` | 转发预算、节点媒体来源、音视频归因及授权重读 |
| `adapters/astrbot/quotes.py`、`forwards.py`、`native.py` | 一次定向读取，冻结/捕获图像、音频、视频，账号复核及共享预算 |
| `conversation/flow.py`、`messages.py` | 持久批次预算、请求顺序、来源重读与提示装配 |
| `tests/test_astrbot_quoted_forwards.py`、`test_conversation_quoted_forwards.py` | 协议、归因、治理和恢复专项 |

上述相对领域路径均位于 `companion_v2/`。真实 SDK/停机/顺序补验归既有 `tests/test_astrbot_quote_host.py`，合成数据归 `tests/forward_support.py`。根级 Python 仍只有 `main.py`，运行证据在系统临时目录，管理/拓展页面保持另一窗口负责。

## 验证

AstrBot 自带 Python 3.12.12、临时 SDK 数据根和临时 V2 数据库运行 **210 项定向测试，全部通过，用时 79.700 秒，零失败、错误或跳过**。其中新增 **29 项**：捕获协议 10 项、对话/来源/恢复 16 项、真实 SDK 宿主 3 项。覆盖媒体、原生入站、群聊 preview、共享宿主加载/停机/路由注销、恢复及核心隔离；没有跑无关全库。

复验命令：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_quoted_forwards tests.test_conversation_quoted_forwards tests.test_conversation_quotes tests.test_astrbot_quote_host tests.test_astrbot_forwards tests.test_conversation_forwards tests.test_astrbot_forward_host tests.test_conversation_images tests.test_conversation_animation tests.test_astrbot_animation_host tests.test_astrbot_native tests.test_astrbot_inbound_adapter tests.test_astrbot_group_host tests.test_astrbot_staging_host tests.test_host_application tests.test_host_recovery tests.test_isolation -q
```

本机证据：`C:/Users/99505/AppData/Local/Temp/v2-quoted-forwards-_bxg1j2n/`。`modules.json`、`tests.json`、`new-tests.json`、`verification.log`、`result.json` 保存范围与逐项结果；`quality.json` 保存编码、Python 3.10 语法及文档链接检查。本轮仅使用合成平台/模型/发送器，没有在线重载、真实模型/QQ 调用或 V1 用户数据访问。既往 226 项及 150 项批次与本批重叠，不相加。

## 2026-09-24 音视频增量复验

本次在上述引用/转发闭环中接入 Reply 直挂与转发节点的 `record`、`video`。外层 Reply 和所有展开节点先冻结媒体定位符，再复用现有音频/视频 loader 捕获原件；普通合并转发走同一节点媒体路径。Prompt 可取得经过授权重读的 `PromptAudio` 与采样帧 `PromptVideo`，提示材料标明原转发账号、当前引用者和未经验证的节点显示身份。纯文本/图片 descriptor 保持原形；音视频字段只出现在对应媒体 descriptor。

使用 AstrBot 自带 Python 3.12.12、SDK `PYTHONPATH` 和测试临时数据根运行 **150 项定向测试与 32 个 subtest，全部通过**，耗时 94.34 秒。范围包含引用、普通及引用内转发、音视频对话合同、音频/视频宿主、媒体治理与群媒体拒绝；只有 AstrBot SDK 的 `audioop` 弃用警告。新增音视频跨重启用例确认不会再次读取平台原件，且群语音、群视频、群转发仍在捕获边界被拒绝。未在线重载、调用真实模型/QQ 或访问 V1 数据。

复验命令：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
$env:ASTRBOT_DATA_DIR = (Join-Path $env:TEMP 'companion-v2-test-data')
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m pytest -q tests/test_astrbot_quote_host.py tests/test_astrbot_forward_host.py tests/test_astrbot_quoted_forwards.py tests/test_conversation_quotes.py tests/test_conversation_forwards.py tests/test_conversation_quoted_forwards.py tests/test_conversation_audio.py tests/test_conversation_video.py tests/test_astrbot_audio_host.py tests/test_astrbot_video_host.py tests/test_group_media.py tests/test_astrbot_group_host.py
```

下一步推进群合并转发及嵌套媒体，并保留真实 QQ/模型能力验收作为独立任务。节点内 Reply 因缺少可信原会话合同继续明确拒绝；本地框架闭环不代表完整 V1 替换或相关 issue 全部解决。
