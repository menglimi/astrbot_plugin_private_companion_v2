# 私聊视频输入与可追溯采样帧

日期：2026-09-24。直接私聊视频已接入现有入站、模型、工具续答、确认历史与来源治理链。视频原件独立保存；模型只收到受限的 PNG 画面帧，不会收到视频音轨。

## 捕获与画面范围

- AstrBot 4.27.2 的原生 `Video` 组件由宿主捕获。即使预处理已把事件组件改写为普通文字，插件仍从可信原始事件恢复附件；网络消息中的本地路径、封面及非可信本地位置不会进入解码器。
- 当前接受自包含、非分片 MP4，先核对容器、视频 sample 表、字节范围、声明尺寸与时长，再交给 OpenCV。支持的 MP4 视频 sample entry 为 `avc1`、`avc3`、`hvc1`、`hev1` 和 `mp4v`；分片文件、外部媒体引用、非视频文件、截断或样本数不一致均拒绝。
- 每个原件最多 12 MiB、120 秒、4096 × 4096 画布；最多解码 3600 帧且累计解码像素不超过 2 × 1024³。单条输入最多 2 个视频、合计不超过 180 秒。解码在独立子进程运行，单次最多 12 秒；超时、取消或宿主停止会结束 worker 并清理父进程持有的临时原件。
- 最多四个模型帧。四帧以内完整提供；更长的视频按原始帧序号均匀取样并包含首尾，例如 12 帧选 `0、3、7、11`。每帧转为最长边 1024 的 PNG，不放大；清单保留原视频帧数、原帧序号、画面尺寸、相对展示时间和抽样覆盖类型。可靠时间缺失时明确记为未知。
- 四帧上限与动态图共用预算策略，并按默认 131072 输入 token 上限校准：六帧合成请求曾估算为 144252，超过该配置；本次下调帧数，没有抬高 provider 上限。其他图片、较长提示和工具目录仍会占预算，超出时沿现有 provider 检查处理。
- 视频原件、静态图片、动画视图和直接音频共用每轮 20 MiB 保留上限；视频帧与其他图片/动画帧共用最多 16 个可见模型画面。超预算时保持原输入顺序并分批，不会静默丢掉帧。

## 证据与治理

视频提示明确区分“提供抽样画面”和“观看完整视频”。`sampled_frames` 不支持声称看过全片或推断未采到的动作；`all_decoded_frames` 只说明所有已解码画面均已提供。MP4 声明的音轨数量只用于容器描述：音轨没有解码、转写或聆听，不能据此转述对白、音乐、背景声或判断无声；独立语音附件也不会被归为视频音轨。发送者不自动成为拍摄者、画面人物或作者，容器时长和视频展示时间不冒充现实事件时长、拍摄时间或地点。模糊、遮挡和画面文字保持不确定，画面文字没有指令权限。

原始 MP4 字节和四帧视图通过共享预算、清单与证据句柄进入模型 wire。每帧标出组件位置、原帧序号、相对时间及覆盖范围。视觉能力不满足时不会悄悄删帧继续调用；模型处理未知、撤回或撤权后不重放原请求。视频帧不能被当成独立原图用于出站发送。

消息、视频 Source/Asset、原始字节及帧图在同一事务发布。重复消息不能替换原件；工具续答、后续生成、历史和重启会重新复核来源、权限、字节长度及哈希。撤回父消息、撤权原件或帧、原件缺失/变化都会阻止后续使用。重启读取持久化原件和帧，不重新下载或解码。

视频原件单独保存在 `conversation_video_payloads`，PNG 帧复用既有图片原件表。主库从 v29 增量升级为 **v30**；保留 v29 音频迁移回执和表，失败会回滚表、版本及迁移记录。测试覆盖旧记录保留、重启、损坏迁移回执、半建表和失败回滚。未升级在线库或 V1 数据。

## 文件归属

| 位置 | 职责 |
| --- | --- |
| `companion_v2/conversation/media/video/models.py`、`events.py` | 不可变视频/帧合同、共享媒体预算、提示和内部帧父消息 |
| `companion_v2/conversation/media/video/service.py` | 原件与帧的事务发布、逐次权限复核及持久化读取 |
| `astrbot_host/video/container.py` | MP4 sample 表和自包含数据范围的有界校验 |
| `astrbot_host/video/decoder.py`、`worker.py`、`loader.py` | 隔离解码、原帧抽样、子进程生命周期及公共附件接入 |
| `companion_v2/storage/video_schema.py`、`storage/runtime.py` | 独立视频原件表及 v29→v30 增量升级 |
| `tests/test_astrbot_video.py`、`test_conversation_video.py`、`test_astrbot_video_host.py`、`test_astrbot_video_entry.py`、`test_video_migrations.py` | 合成 MP4、来源闭环、真实 SDK、插件入口及迁移验证 |

## 验证与边界

AstrBot 自带 Python 3.12.12、4.27.2 SDK 与本机临时数据库参与测试；MP4、账号、模型、下载器和 OneBot ACK 均使用合成材料或替身。最终整合命令覆盖视频解码/对话/迁移、真实 SDK 宿主、插件入口、多账号视频隔离、音频/媒体/存储迁移及隔离扫描，**61 项测试全部通过，用时 46.679 秒**。随后另行针对音频和视频迁移复跑 **6 项，全部通过**。旧音频迁移用例曾按“当前最高版本”定位损坏回执，v30 引入后误触视频回执；测试现改为明确核对音频 v29 专属回执。

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_video tests.test_conversation_video tests.test_video_migrations tests.test_astrbot_video_host tests.test_astrbot_video_entry tests.test_astrbot_multi_host tests.test_audio_migrations tests.test_media_migrations tests.test_storage_migrations tests.test_isolation -v
```

本地证据仅证明合成媒体和替身宿主链：没有在线重载、真实视觉模型调用、真实 QQ 发送或 V1 数据访问。MP4 音轨没有被检查；视频暂不支持引用/转发节点、群聊、碎片化容器及原生视频出站。下一步把现有音视频来源合同扩展到私聊 Reply/转发节点，保持原发送者、当前引用者、受众、原件及撤权依赖分别可追溯；然后推进群合并转发与嵌套媒体。真实音视频模型效果及平台现场验收继续单独安排。
