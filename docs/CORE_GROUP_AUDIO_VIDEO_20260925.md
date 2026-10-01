# 群聊直接语音与视频输入

2026-09-25。本步将群内直接发送的 QQ SILK、PCM WAV 语音和 MP4 视频接入 V2 宿主，复用既有媒体原件、模型请求、来源治理和投递服务。群仍默认 preview，实际群投递沿用原逐群授权。

## 已落地行为

- 原始 OneBot 消息的账号、群号、消息号、发送者与 SDK 路由一致后，才恢复 Record、Video 及同条消息的文字、At、图片、Reply、Forward。即使宿主已将语音转为 Plain，也只采用原消息组件，不将宿主生成的转写、路径或说明文字当作用户原文。
- `NativeAdapterTypes.group_component_reader` 独立注入群恢复器，保留私聊 reader 和既有位置参数兼容。附件位置与定位信息再次和原群组件核对；原始组件缺失或不一致时不受理。
- 原件读取和解码发生在身份与来源入库之前，受准备超时限制；完成后复核角色与原账号连接，停机不接纳晚到输入。语音、视频、视频采样帧和新成员授权随原输入原子提交。
- 语音提供完整的单声道 PCM WAV 视图，保留 SILK/WAV 原件及转换清单。视频保存 MP4 原件，最多向模型提供四帧均匀采样画面，明确 `audio_status=not_inspected`，不宣称听过视频音轨或看完所有动作。模型提示分别说明发送者、录音者、说话者及拍摄者不能混同。
- 工具续答复用同一组媒体内容和证据；工具回执可以更新其他上下文。直接附件与共享树中已接入的转发节点附件共用音频数、视频数、帧数、时长和保留字节预算。
- 后续群聊只投影 `historical_metadata_only` 附件信息，不重新将旧音频或视频帧发送给模型；依然复核原件字节、资产、原发送者权限和完整来源依赖。历史指纹按文字/图片、直接音频、直接视频、引用、转发的顺序重建，避免含直接音视频的历史被误判为变化而丢失。
- 撤回原输入会撤销原语音、视频及帧来源；撤权或资产失效、原件/PCM 视图/视频帧损坏会阻断已封存历史消费。依赖这些材料的旧 Bot 回复也不再进入后续上下文，已取得的投递回执保留。重启保留原件和治理状态，unknown 投递不重复生成或重发。
- 同一群号下的平台账号、Bot、角色、原会话和成员独立 session 继续隔离；群媒体不成为私聊记忆，也不把媒体解释直接写为某位群友的长期陈述。

## 目录与存储

- `companion_v2/adapters/astrbot/group.py`：冻结群路由、原件定位、异步准备、统一预算和准备后复核。
- `companion_v2/conversation/group_media.py`：直接音视频的历史指纹、元数据投影、原件及来源依赖重读。
- `astrbot_host/media_components.py`：从原始私聊/群聊消息恢复真实 SDK 组件；核心不导入 AstrBot。
- `companion_v2/adapters/astrbot/staging.py`、`astrbot_host/native.py`、`astrbot_host/multi_session.py`：独立群组件恢复端口与宿主装配。
- `tests/test_group_audio_video.py`：合成 SDK 组件、来源治理、失败回滚、预算与重启场景。
- `tests/group_audio_video_entry_process.py`、`tests/test_astrbot_group_audio_video_entry.py`：独立进程中的真实 `main.py`、SDK 群事件、本地 OneBot ACK 与终止清理。

复用现有 v29 音频表、v30 视频表和图片帧表，无新增 schema 或根级业务文件。群转发节点的实现来自共享树，本轮验证其与直接附件的组合行为，没有另建媒体库。

## 定向验收

按测试 ID 去重 **97 项通过**：

| 模块 | 项数 |
| --- | ---: |
| `test_group_audio_video` | 9 |
| `test_astrbot_group_audio_video_entry` | 1 |
| `test_group_media` | 25 |
| `test_astrbot_group_forwards` | 12 |
| `test_group_conversation_context` | 14 |
| `test_astrbot_group_host` | 12 |
| `test_astrbot_audio_host` | 5 |
| `test_astrbot_video_host` | 3 |
| `test_astrbot_multi_host` | 13 |
| `test_isolation` | 3 |

新增专项首轮的 8 项边界用例通过；工具续答用例修正了“所有上下文必须完全不变”的测试假设，改为复核实际媒体与来源保持一致，随后该用例及独立插件入口 2 项通过。其余 8 个受影响模块 87 项全部通过，用时 122.996 秒。上述计数不重复累计复验。

真实入口脚本验证 AstrBot 4.27.2 插件 namespace 加载、初始化/启动、STT 前群 SILK/MP4 恢复、两位成员接续、模型 wire、两次本地 reverse WebSocket 发送 ACK、终止、数据库关闭、路由注销及核心模块释放。

运行环境为 `E:/astrbot/backend/python/python.exe -X utf8`，仅测试进程设置 `PYTHONPATH=E:/astrbot/backend/app`，SDK 导入前设置临时 `ASTRBOT_ROOT`。可在 V2 工程根运行：

```powershell
$env:PYTHONPATH='E:\astrbot\backend\app'
& 'E:\astrbot\backend\python\python.exe' -X utf8 -m unittest tests.test_group_audio_video tests.test_astrbot_group_audio_video_entry
```

全部身份、媒体、模型、历史和回执均为合成；没有真实 QQ 或模型请求、在线重载、鼠标接管和 V1 用户数据访问。测试证明宿主接线、请求格式和治理行为；真实平台原件响应、模型音视频支持及语义效果仍需现场验收。

## 下一步

接通群 Reply 引用中的语音、视频：按原群与精确消息号读取原件，分开原发送者和当前引用者，并把引用链接入现有撤回/撤权、历史和预算复核。该入口随后由[群 Reply 原件切片](CORE_GROUP_QUOTE_MEDIA_20260925.md)接通；群图片/音视频出站、媒体自动记忆和群公共记忆管理页面仍有后续工作。
