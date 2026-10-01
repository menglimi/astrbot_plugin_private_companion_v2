# 私聊引用消息与静态引用图

日期：2026-09-24。本切片补齐近期 Private #255/#256 对照中缺失的 `Reply` 入站：当前用户可以引用本私聊中用户或机器人账号之前发送的文字、静态 PNG/JPEG/WebP，引用正文作为独立来源进入对话，图片沿用原件治理。完成的是本地完整链和真实 SDK 组件接线，尚无真实 QQ 现场验收。

后续[历史读取兼容与恢复补验](CORE_PRIVATE_FORWARDS_SLICE_20260924.md#2026-09-24-历史读取兼容与恢复补验)补齐响应容器归一化、异常消息号和超时分类，使用真实 SDK 的本地 ACK 合同复核引用/转发解包；150 项相关定向回归通过，其中新增 14 项。包含本引用链，但不是额外 150 项引用专测或真实平台验收。

后续[Reply 引用合并转发](CORE_QUOTED_FORWARDS_SLICE_20260924.md)已支持原消息中的展开转发、节点图和动画帧；普通引用清单及指纹保持兼容。210 项相关定向回归通过，其中新增 29 项，范围与下述历史批次重叠，不相加。

## 归属读取

AstrBot `Reply.chain` 不保留原私聊对象；其 `time` 可能是 SDK 转换时刻，不能直接用来确定原发送时间。NapCat `get_msg` 的 `user_id` 是发送者，机器人消息的这个字段也不能证明接收对象。

因此捕获只冻结原生 `Reply.id` 和组件位置，然后通过已固定账号的 reverse WebSocket 执行一次 `get_friend_msg_history`：`user_id` 为当前私聊对象，`message_seq` 为原消息 ID，`count=1`。最初关闭合并转发展开；后续引用转发切片改为 `parse_mult_msg=true`，在同次读取中捕获展开节点。返回必须恰有一条、消息 ID 匹配、`self_id` 匹配、为好友私聊，发送者必须是当前对象或当前机器人账号。读取与图片准备前后检查同一 API/连接；不改用全局 `get_msg`、其他账号或扩大历史页兜底。

2026-09-24 只读检查的 NapCat 源码依据：

- [GetMsg.ts](https://github.com/NapNeko/NapCatQQ/blob/main/packages/napcat-onebot/action/msg/GetMsg.ts) 将原消息交给 `parseMessage`。
- [OneBot msg.ts](https://github.com/NapNeko/NapCatQQ/blob/main/packages/napcat-onebot/api/msg.ts) 的 `initializeMessage` 将顶层 `user_id` 和 `sender.user_id` 都设置为原发送者；`self_id` 是当前账号。
- [GetFriendMsgHistory.ts](https://github.com/NapNeko/NapCatQQ/blob/main/packages/napcat-onebot/action/go-cqhttp/GetFriendMsgHistory.ts) 从参数 `user_id` 单独选择 peer，消息序号只决定起点。
- [Core msg.ts](https://github.com/NapNeko/NapCatQQ/blob/main/packages/napcat-core/apis/msg.ts) 的 `getMsgHistory` 调用 `getMsgsIncludeSelf(peer, msgId, count, ...)`。

该路径要求 OneBot 实现提供上述按对象定向的历史合同及数组格式。只提供标准 `get_msg`、返回缺少身份信息或无法命中原 ID 的实现会明确拒绝本次引用；尚未宣称所有 OneBot 实现兼容。AstrBot 版本仍固定在原已验证的 4.27.2 合同。

## 来源、原件与生命周期

- 当前消息只保留用户本轮正文和引用占位。引用正文单独保存为 `conversation.quote`，清单记录原消息 ID、原发送账号、原发送时间、引用位置、脱敏指纹及图片清单。未知时间保持未知，不使用 `Reply.time` 补造。
- 提示词区分当前引用者、原发送账号、作者和拍摄者；机器人账号曾发送不等于当前人格创作或亲历。引用不是本轮用户自述，也不授予其中的文字指令权限。日记的当前用户输入来源不混入引用正文。
- 引用文字沿用本地脱敏与 HMAC 重放冲突；原始密钥文字、下载 URL 和 base64 不写进事件 JSON/文字来源。图片字节进入现有 v25 原件表，父来源是引用来源，直接图与引用图的组件位置不会冲突。
- 当前消息、引用 Source、图片 Source/Asset、原字节与依赖同事务提交；任一失败全部回滚。新 `QuoteConversationEvent` 只用于带引用输入，既有纯文字/直接图片的序列化形状及重放哈希保留。
- 若原用户消息已进入 V2，按已有路由元数据和事件主键找到原件，复核正文、图片及原角色，引用依赖原来源。已知原件属于另一个宿主会话时拒绝重新归属。已确认的 V2 机器人回复按投递回执和原回复来源关联；未知投递不冒充已确认记录。
- 生成、工具续答、发送和已确认回复的记忆引用继续重读引用及原图。原消息撤回沿依赖撤销引用；资产撤权、原件缺失、正文或字节变化会阻止使用。重启恢复读取持久原件，不重新访问历史 API 或下载图片。
- 网络和图片准备位于 SQLite 入站事务之外。单目标入站锁保持消息顺序；停机后才完成的准备不能接纳消息。未知模型/发送结果仍不自动重放。

尚未接入的外部历史消息没有 V2 的原来源可关联，本切片保留首次定向读取的快照及其当前引用来源治理，不轮询 QQ 撤回，也不声称已取得未接入的实时撤回通知。

## 预算与范围

每条消息支持一个单层 `Reply`，原消息可包含文字和静态 PNG/JPEG/WebP。引用图与当前直接图共用最多 8 图、20 MiB 总原件预算；每图仍为 5 MiB、单边 8192、16 × 1024 × 1024 像素。整轮合并也计入引用图，超额另开批次。整条消息附件准备合计最多 25 秒。

优先识别原生 `base64://`，即使同时有 URL 也保留 base64 原件；不走文件名正则或 `Path`。本引用切片交付时尚未支持动态图；后续[动态图切片](CORE_PRIVATE_ANIMATION_SLICE_20260924.md)已复用引用链接入 GIF/APNG/动态 WebP，原件及派生帧共享其预算。外层直接合并转发已由[转发切片](CORE_PRIVATE_FORWARDS_SLICE_20260924.md)接入，Reply 原消息内的展开转发由[引用转发切片](CORE_QUOTED_FORWARDS_SLICE_20260924.md)接入。嵌套 Reply、节点内 Reply 和语音/视频仍未支持，不静默丢弃部分引用；群媒体需另行建立来源与受众合同。

## 文件归属

| 位置 | 职责 |
| --- | --- |
| `conversation/quotes/models.py` | 不可变引用清单、事件、归因提示词 |
| `conversation/quotes/service.py` | 引用正文脱敏、事务发布、原件读取及提示贡献 |
| `conversation/quotes/originals.py` | 已接纳原消息与已确认投递的来源依赖 |
| `adapters/astrbot/quotes.py` | 注入客户端的定向读取、协议校验和原图片定位 |
| `adapters/astrbot/history.py` | 引用/转发共享的有界响应解包，原消息身份检查仍由各读取器负责 |
| `astrbot_host/quotes.py` | 真实 SDK 客户端类型与图片加载器装配 |
| `tests/test_conversation_quotes.py`、`test_astrbot_quote_host.py` | 核心链、边界和真实 Reply 类型/宿主生命周期 |

核心路径均在 `companion_v2/` 内，无新增根级业务文件、数据库或日志；复用 v25 表，本批无 schema 迁移。

## 验证

AstrBot 自带 Python、临时 V2 数据库和临时 SDK 数据根运行 **110 项定向测试全部通过，用时 42.367 秒**，其中新增 **25 项**引用测试：核心 22 项、真实 SDK 宿主 3 项。

覆盖用户/机器人引用、原时间及发送者、正文归因、约 2.7 MB 合成 PNG 的 base64 原字节、直接/引用图顺序和共享预算、事务失败回滚、脱敏后重放冲突、原件撤回/撤权、已确认回复依赖、工具续答、记忆来源、重启、账号/角色变化、未知不重放、SDK 停机与入站顺序。既有图片、入站、模型 wire、宿主生命周期/路由注销、恢复和核心隔离同时通过。

运行命令：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_conversation_quotes tests.test_astrbot_quote_host tests.test_conversation_images tests.test_astrbot_image_host tests.test_astrbot_media tests.test_astrbot_native tests.test_astrbot_inbound_adapter tests.test_astrbot_model_wire tests.test_astrbot_staging_host tests.test_host_recovery tests.test_isolation -q
```

本机证据目录：`C:/Users/99505/AppData/Local/Temp/v2-private-quotes-jwy__xsg/`，包含 `modules.json`、`verification.log` 和 `result.json`。此前 17 项开发阶段通过记录被本批覆盖，不相加。修改的源码通过 UTF-8 无 BOM、LF、末尾换行及 Python 3.10 语法解析检查；后者不代替实际 3.10 运行验收。

合成 API、模型和发送器覆盖本地调用链，没有在线重载、真实模型/QQ 调用或 V1 数据读取。#255/#256 可标为“V2 引用静态图本地场景已补齐，现场待验收”；角色图片生成/出站仍是另一段未完成的能力，不能由引用输入代证。后续[动态图切片](CORE_PRIVATE_ANIMATION_SLICE_20260924.md)已接入可追溯帧，[合并转发切片](CORE_PRIVATE_FORWARDS_SLICE_20260924.md)已接入节点显示归因、受众和原件治理；更多嵌套组件与现场验收继续补齐。
