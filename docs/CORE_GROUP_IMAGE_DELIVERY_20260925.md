# 群聊原图出站与确认图文历史

2026-09-25。在[私聊原图投递](CORE_PRIVATE_IMAGE_DELIVERY_20260924.md)和[群引用媒体](CORE_GROUP_QUOTE_MEDIA_20260925.md)之上，群回复现在可选择本轮提供的图片原件，按原账号和原群发送图文，保存统一回执，并允许其他成员引用已确认的 Bot 图文。全部实现继续归现有 V2 本体。

## 行为与来源

- 模型可选直接图、引用图、转发节点图和完整动画；工具续答保持同一组 `sendable_image` 句柄。图片按选择顺序附在最后一段文字后，静态图及动画均发送完整原字节。未选择图片时保留普通文字回复合同。
- 群图文复用 `ImageDeliveryEnvelope`、有序图文指纹和 `conversation.reply_images` 来源清单。清单只保存来源引用和描述，复用已有 Source/Asset、图片原件及动画帧，不增加表或 schema 迁移。
- `PromptRequest`、原图选择与 OneBot 群 sender 同时声明图片能力；封套必须保留当前群的集体受众。群号、账号、Bot、人格、成员独立 session、入站时冻结的投递意图及有限群授权继续由原路径复核。
- 提示词要求只附任务需要的原图，说明群受众、原发送者与显示归因；引用或转发不表示机器人创作、拍摄或认同，拿到回执前不声称发送成功。
- 发送器在原生人格查询返回后再次检查授权、来源、资产、原连接及停止状态，随后一次提交 `[text, image, ...]`。原件/动画帧撤权、清单损坏或丢失不会降级为只发送文字。

## 历史、再次引用与恢复

确认群历史用图文指纹核对原回执，在对应段落提供 `historical_metadata_only` 图片描述；后续纯文字消息不会因此再次获得旧图片字节或发送句柄。原 Bot 文字和图片仅作为历史，不成为新的事实证明。

群历史读取已封存输入中的图片原件，由既有有界依赖遍历复核输入哈希、原成员权限、角色、会话、材料及工具结果。原图选择不再次编译整份历史，避免为恢复图片重复递归。引用和历史共用原祖先预算；只有完整验证通过才向内部引用读取器返回根回复的图片，祖先图片不会混入。

再次引用已确认的 Bot 图文时，比对原文字、图片数量、顺序及描述。篡改、漏图、换序或额外附加音视频/转发会回滚接纳。出站清单、原图与动画帧来源保留在依赖中；原件撤回或原成员撤权后，即使引用保存过副本，历史及后续引用仍不可读取，跨重启有效。

未知 ACK 不确认历史，也不重发或重新生成。迟到回执必须匹配原操作、账号、上下文及图文指纹，纯文字指纹不能确认图片。分段第一段已确认、最后图文尚待发时，恢复只发送原待发部分，保持原字节及选择；已有回执保留。预览批次不能因为之后切换模式或取得新授权而升级为发送。

## 文件归属

| 文件 | 职责 |
| --- | --- |
| [conversation/media/reply.py](../companion_v2/conversation/media/reply.py) | 群/私聊原图选择、出站来源清单及仅重读图片的内部路径 |
| [conversation/foreground.py](../companion_v2/conversation/foreground.py)、[messages.py](../companion_v2/conversation/messages.py) | 显式原图回复合同及 sender 能力接线 |
| [delivery/media.py](../companion_v2/delivery/media.py)、[onebot_group.py](../companion_v2/adapters/astrbot/onebot_group.py) | 集体受众封套、图文指纹及原群发送 |
| [group_history.py](../companion_v2/conversation/group_history.py)、[group_context.py](../companion_v2/conversation/group_context.py) | 确认图文历史、元数据提示及有界来源复核 |
| [quotes/group_originals.py](../companion_v2/conversation/quotes/group_originals.py) | 已确认 Bot 图文的原件核验与引用依赖 |

测试按职责放在 `tests/test_group_image_delivery.py`、`test_group_image_delivery_governance.py`、`test_astrbot_group_image_delivery_entry.py`，合成夹具归 `group_image_delivery_support.py`。真实 SDK 验收复用 `group_media_entry_process.py` 的 `run(deliver_images=True)` 模式，默认入口保留原群图片输入验收。根级 Python 仍只有 `main.py`。

## 验证

新增 17 项专项覆盖预览、静态图/动画排序、末段附图、工具续答、群/账号/session 隔离、Bot 图文再次引用、祖先预算、撤回/撤权、损坏清单/字节、停止、未知 ACK 与迟到对账、分段重启和预览不可升级。

开发中保留了三次修正：首轮 9 项被旧 `PromptRequest` 私聊限定拦截，补齐群显式合同后 8 项通过；剩余分段测试显式装配可信分段策略后通过。治理首轮 15 项通过，停机恢复测试因确定性时钟没有前进而等待超时；推进测试时钟后该项和新增 SDK 入口 2/2 通过。未改变生产等待或恢复规则。

最终定向范围为 **14 个模块、110 项测试及 67 个 subtest，按测试 ID 去重后均有通过记录**。整批耗时 256.33 秒，109 项及全部子用例通过；既有私聊 SDK 转发用例在历史读取处返回 `host_forward_unavailable`。不改源码的独立复验 1/1 通过，其完整 SDK 模块再次复验 8/8 通过（19.52 秒），失败未再复现。这里保留原失败，不表述为整批一次全过。默认群媒体 SDK 入口另行通过，确认复用脚本没有破坏原输入验收。

范围：`test_group_image_delivery`、`test_group_image_delivery_governance`、`test_astrbot_group_image_delivery_entry`、`test_conversation_image_delivery`、`test_astrbot_image_delivery_host`、`test_astrbot_image_delivery_native`、`test_group_conversation_context`、`test_group_media`、`test_group_quote_media`、`test_group_quote_governance`、`test_astrbot_group_delivery`、`test_astrbot_group_native_delivery`、`test_astrbot_group_quote_entry`、`test_isolation`。新增专项 17 项包含在上述总数内，不重复累计。

整批验证前后核对 560 个 Python 源码/测试文件，复验核对 327 个文件，均未在对应运行期间变化。本机证据目录为 `C:/Users/99505/AppData/Local/Temp/v2-group-image-validation-61jpe78t/`：`source-manifest.json`、`pytest.xml`、`verification.json` 保存整批及原失败；`transport-recheck.*`、`followup.*` 和 `default-entry.log` 保存复验；`final-result.json` 按 ID 汇总，`quality.json` 保存编码、语法、目录与链接检查。所有本批文本通过 UTF-8/无 BOM/LF/末尾换行检查，受影响 Python 通过 Python 3.10 AST 与当前解释器编译检查，本地文档链接有效。

真实 SDK 验收在独立进程导入实际 `main.py`，使用真实 `AiocqhttpMessageEvent`、Image/Reply 和 `WebSocketReverseApi`，完成成员发图→Bot 图文 ACK→另一成员引用 Bot 图文并再次附图→第三位成员接话只取得历史元数据；同时检查停止、路由注销及核心模块释放。模型替身与本地内存 ACK 无外部网络发送。

测试使用 AstrBot 自带 Python，SDK 导入前切换到临时 `ASTRBOT_ROOT`。本批没有真实 QQ/模型调用、在线重载、V1 用户数据访问或页面业务修改。

## 协调与下一步

本体继续为 `astrbot_plugin_private_companion_v2`，产品名“我会永远陪着你 V2.0”。注册名对齐与唯一公开小屋入口已由原协调任务收尾，见[统一记录](REGISTRATION_UNIFICATION_20260925.md)；本任务没有改动 `main.py`、metadata、页面或在线重载。三个内部工作区沿协调方案采用 `workspace.html`，不重新创建旧公开入口。分工回执见[注册协调回执](REGISTRATION_COORDINATION_20260925_01a0c791.md)。

下一步接入 Image 伴侣的生成/编辑图片产物采用：外部执行、产物保存、角色采用与最终投递分别留据，继续共用原受众、来源治理、指纹和未知结果不重放。目前这里只能发送本轮已有原图；生成/编辑新图、群语音/视频出站及实际 QQ 客户端效果仍未在本片完成。Private #252 的原群生图场景不能仅凭原图投递通过而宣称已解决。
