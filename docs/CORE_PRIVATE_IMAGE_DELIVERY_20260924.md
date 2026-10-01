# 私聊原图出站与统一投递回执

后续进展（2026-09-25）：[群聊原图出站](CORE_GROUP_IMAGE_DELIVERY_20260925.md)已复用本合同，补齐群受众、确认图文历史和 Bot 图文再次引用。下文保留本切片交付时的范围及验证记录。

2026-09-24。本切片把本轮可见的图片原件接入现有私聊回复链：模型可选择直接图、引用图、转发节点图和完整动画原件，文字与原图通过一次 OneBot `send_private_msg` 提交，并共用原操作、内容指纹及回执。单目标 staging 与多账号共享宿主均已接线；未生成或编辑新图片，也未接群图片发送。

## 选择、保存与发送

- 最终回复保留 `text`、`claims`，可选 `images` 数组引用当前请求明确提供的 `sendable_image` 句柄；省略或空数组继续使用原文字合同。提示词要求只选择任务需要的原图，避免把收到的图全部回送，明确发送原件不等于生成/改图，未拿到回执前不声称已送达。
- 只提供本轮封存请求中的完整原件。普通文字证据、动画抽帧、其他请求句柄、URL、路径和 base64 不能作为发送选择。复用现有最多 8 张原件及媒体预算；图片顺序按选中的句柄，附在最后一段回复之后。
- 图片清单保存为 `conversation.reply_images` 来源，记录原件引用、描述和最后一段 ID，与回复 parts 同事务发布。清单依赖原图片及全部帧来源，不复制原字节，也不新增数据库表或 schema 迁移。
- 图文内容指纹包含有序原件清单；发送器、回执、确认历史及记忆来源核对同一个指纹。原文字回复的内容和批次指纹保持原形状，旧 sender 默认不声明图片能力，不能静默丢掉图片。
- 私聊 OneBot sender 在原人格查询返回后复查授权、原账号客户端和来源/资源状态，再一次发送 `[text, image, ...]`。静态图保留原字节，动画发送完整 GIF/APNG/动态 WebP，发送/恢复不再解码或抽帧。

## 回执、治理与恢复

预览返回图片来源 ID、MIME、尺寸、字节数和指纹，不包含 base64、路径或下载地址；预览没有发送记录，不进入确认历史。确认送达后，历史的对应最后一段携带图片描述。记忆中的确认回复仍保留 Bot 归因，并依赖本次出站清单及原图证据。

用户再次引用已确认的 Bot 图文消息时，核对已发送文字、图片数量/顺序和原件描述，并关联确认回复与出站清单。原件撤回/撤权会传播到引用和记忆；清单丢失、内容变化或动画帧撤权时，整条图文不可发送，不降级成纯文字。

发送动作进入等待后，错误、失败响应和丢失 ACK 保持 unknown，不自动重试；重启不重新调用模型、不重新选择图片、不重发已尝试的部分。迟到回执按原账号、上下文、操作和图文指纹核对；只有文字的旧指纹不能确认图片投递。停止后仍可登记原回执，恢复时显式对账，不创建新发送。

共享宿主还补齐 `forward_type / forward_loader` 装配，直接转发和 Reply 原图可沿原账号贯通。回归同时修复单目标启动期间的停机竞态：原生人格查询返回后，先复核生命周期，再绑定生活/状态/展示服务，关闭后的宿主不会继续绑定。

## 文件归属

| 路径 | 职责 |
| --- | --- |
| [conversation/media/reply.py](../companion_v2/conversation/media/reply.py) | 选择提示、原图草案、来源清单、授权重读及描述投影 |
| [delivery/media.py](../companion_v2/delivery/media.py) | 有序图文指纹、图片发送封套与字节校验 |
| [model_wire.py](../companion_v2/adapters/astrbot/model_wire.py) | 可发送原件句柄及模型响应解码 |
| [onebot.py](../companion_v2/adapters/astrbot/onebot.py) | 一次原账号私聊图文请求和平台回执 |
| [generation.py](../companion_v2/conversation/generation.py)、[delivery.py](../companion_v2/conversation/delivery.py) | 原子发布、逐段派发及恢复 |
| [sent_sources.py](../companion_v2/memory/sent_sources.py)、[quotes/originals.py](../companion_v2/conversation/quotes/originals.py) | 确认记忆及已发送图文的引用依赖 |

SDK 共享宿主接线和元数据预览归 `astrbot_host/`，专项与合成夹具归 `tests/test_conversation_image_delivery.py`、`test_astrbot_image_delivery_host.py`、`test_astrbot_image_delivery_native.py`、`image_delivery_support.py`。根级 Python 仍仅 `main.py`，没有新增根级业务、数据库、日志或备份。管理/拓展页面由原任务继续推进，本切片仅补已有后端投影。

## 验证与边界

使用 AstrBot 自带 Python 3.12.12、临时 `ASTRBOT_ROOT` 和合成 V2 数据库，定向范围按 ID 去重 **363 项最终均有通过记录**，其中新增 **27 项**。首轮 363 项运行 205.953 秒，361 项通过；新旧 sender 恢复测试的预期码修正，以及上文启动/停机竞态修复后，受影响 107 项在 64.532 秒内全部通过，无失败、错误或跳过。最后批次覆盖单目标启动、bootstrap、加载/停机/路由注销和全部新增专项；不重复累计测试数量。

本机证据为 `C:/Users/99505/AppData/Local/Temp/v2-image-delivery-dlmobl_9/`：`modules.json`、`tests.json`、`new-tests.json`、`verification.log`、`result.json` 保存首轮；`followup-*` 和 `followup.log` 保存修复后的范围和结果；`final-results.json` 按 ID 汇总，保留最初两项失败记录。`plugin-entry.py`、`plugin-entry.log` 和 `plugin-entry-result.json` 保存独立插件入口验收，`quality.json` 保存编码、Python 3.10 语法、目录/依赖隔离及本地文档链接检查。

复验新增专项：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_conversation_image_delivery tests.test_astrbot_image_delivery_host tests.test_astrbot_image_delivery_native -q
```

新增 27 项覆盖有序图文、完整动画、引用/转发、工具续答、事务回滚、来源/资产/帧撤权、清单损坏、停止、恢复、未知回执和迟到对账、旧 sender 兼容，以及两个账号、人格和有限授权隔离。真实 SDK `AiocqhttpMessageEvent`、`Image`、`Forward`、`Reply` 与 `WebSocketReverseApi` 使用本地内存 ACK，无外部网络发送。插件入口独立进程验证 `main.py` 收到图文后单次 ACK，停机后 63 条管理路由全部注销。

本次无在线插件重载、真实模型调用、真实 QQ 消息或 V1 用户数据访问。剩余为语音/视频、实际生图/改图及产物采用、群图片、节点内 Reply 的可信原会话合同，以及真实视觉与 QQ 平台验收。Private #252 的原群聊生图场景仍未完成；本次仅把其“超时但后来送达”的回执语义扩展到私聊已有原图。
