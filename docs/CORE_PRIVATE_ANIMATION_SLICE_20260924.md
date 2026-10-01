# 私聊动态图与可追溯帧覆盖

日期：2026-09-24。本切片在静态图片及 Reply 引用链上接入 GIF、APNG、动态 WebP。当前私聊直接图片和被引用图片都可保留完整编码原件，并将带原帧序号、相对时间和覆盖范围的 PNG 视图交给模型。完成的是本地对话、真实 SDK 组件与请求格式接线；真实视觉模型效果及 QQ 现场仍待验收。

## 原件、帧与提示

- 原 GIF/APNG/WebP 字节不重编码。每个选中帧由 Pillow 完成 disposal/blend 合成后提取为 RGBA PNG，最长边缩至 1024，不放大；保留透明度，不能把局部更新矩形直接当完整画面。
- 最多 4 个显示帧时提供全部；超过 4 帧按原帧序号均匀选择 4 帧，包含首尾。例如 10 帧选择 `0、3、6、9`，声明 `sampled_frames`。APNG 独立默认封面参与完整性验证，但不当动画首帧或发送给模型。
- 帧时间记录容器内的相对播放时间。缺少时长时保留未知，后续累计时间也保持未知；循环次数不解释为现实事件发生次数。该切片没有音轨或实时播放能力。
- 提示词要求只描述提供帧可见的内容，不补造未提供帧、帧间动作或缩小后无法辨认的细节；截图文字没有指令权限。发送者、作者、拍摄者和画中人保持区分，容器时间不冒充拍摄时间。
- 动画原件和每帧都作为独立 Source/Asset 保存，依赖为原消息或引用 → 动画 → 帧。清单记录原件与帧的字节数、SHA-256、原始尺寸、帧序号、起点/时长、覆盖范围及渲染配置。
- 直接图与 Reply 引用图复用同一媒体服务。引用帧继续携带原发送账号、当前引用者及原消息 ID，引用读取仍受当前账号/好友定向历史合同约束，不信任 `Reply.chain` 中的正文或身份。

## 完整性与生命周期

发现并修复了解码库的容错边界：部分尾部截断 GIF/APNG 会被正常 `seek/load` 当作较短或完整动画。宿主现在先对 GIF 长度前缀块和终止标记、APNG 全部块长度/CRC及声明帧数与实际帧控制数量做有限校验；WebP 使用 libwebp 对 RIFF 的校验和帧数。GIF 不调用会遍历整文件的 `n_frames`。

预先取得可信帧数后，一次顺序遍历同时验证所有显示帧并保存选中的合成视图，包括未选中帧的解码检查。提前 EOF、损坏帧和不一致的帧数不能变成较少帧的“完整覆盖”。解码与缩放在工作线程中完成；失败或取消不返回半份捕获结果。

消息、原件及所有帧在同一外层事务中发布，任一步失败全部回滚。生成、工具续答、发送和已确认回复的记忆引用继续复核原件及全部帧的来源、权限与字节；帧撤权、原件损坏或缺失阻止后续使用。原消息撤回会沿依赖传播，未知模型/投递结果仍不自动重放。

重启从已持久化的 PNG 视图恢复，不重新下载、解码或用另一套抽帧结果替换原视图。静态图片清单和既有事件的序列化形状保留；复用 v25 `conversation_image_payloads` 表，本批没有 schema 迁移。

模型 wire 仅展开选中的 PNG 帧，每帧旁携带证据句柄、原组件位置、原帧序号、时间和动画覆盖范围。SDK 准备使用独立副本，并与原多模态消息完整比较，防止原图仍在但帧归因/时间被丢弃，或准备过程原地修改比较基准。SDK 合同仍固定 AstrBot 4.27.2。

## 预算

| 项目 | 范围 |
| --- | --- |
| 单原件 | 5 MiB；单边最多 8192；画布最多 16 × 1024² 像素 |
| 解码 | 最多 256 个显示帧；累计画布最多 64 × 1024² 像素，APNG 默认封面计入像素预算 |
| 动画视图 | 最多 4 帧；每帧最长边 1024；每帧最多 5 MiB |
| 单输入及整轮 | 最多 8 个附件原件、16 个实际模型图片/帧；原件与派生帧合计最多 20 MiB；直接图与引用图共用 |
| 等待 | 单次下载 15 秒；单条输入的附件准备共 25 秒 |
| 模型预留 | 每个实际图片/帧 16384 tokens，另计文字、工具目录和上下文；仍逐次检查 provider 配置的输入上限 |

4 帧是按本地实际工具目录和默认 131072 输入预算选取的上限：原 6 帧方案在合成长动画整轮请求中估算达到 144026，尚未发起模型请求就超额。改为 4 帧后，该整轮夹具通过，provider 上限没有调高。多动画、长人格或额外上下文仍可能超过模型配置；16 帧是媒体接纳上限，不保证所有合法媒体组合都适合默认模型预算。超出媒体合并预算另开批次，不静默丢帧。

## 文件归属

| 位置 | 职责 |
| --- | --- |
| `companion_v2/conversation/media/animation.py`、`codec.py` | 动画与帧合同、覆盖范围和清单恢复，无 Pillow/SDK 导入 |
| `companion_v2/conversation/media/service.py` | 原件及帧的事务发布、逐次授权重读和证据贡献 |
| `astrbot_host/animation_container.py`、`animation.py` | 有界容器校验、真实解码、合成与缩放 |
| `companion_v2/adapters/astrbot/model_wire.py`、`provider.py` | 展开实际帧、预算预留及 SDK 准备核对 |
| `tests/animation_support.py`、`test_astrbot_animation.py`、`test_conversation_animation.py`、`test_astrbot_animation_host.py` | 合成夹具、容器/像素验证、对话与引用闭环、真实 SDK 宿主 |

业务、宿主、测试和证据继续各归其目录；根级 Python 仍只有 `main.py`。

## 验证与后续

最终 **159 项定向测试全部通过，用时 45.201 秒，无失败、错误或跳过**，覆盖 17 个模块；新增 **37 项**包含其中：容器与帧验证 14 项、对话/引用链 19 项、真实 SDK 动画宿主 4 项。

验证包含 GIF disposal、APNG 透明叠加及默认封面、WebP 帧时间、短动画全帧与长动画首尾抽样、缩放、截断文件、未选中帧损坏、帧数/像素/合并预算、原件与帧回滚、撤回/撤权、生成后撤权阻止发送、未知不重放、工具续答、记忆依赖、重启复用、SDK 原地改写拦截、真实 Image/Reply 组件及停机。静态图、引用、模型 wire、工具、记忆输出适配、入站、宿主加载/路由注销/恢复、原表兼容和核心隔离同时通过。

使用 AstrBot 自带 Python 3.12.12，SDK 导入及 V2 数据库均指向临时目录，API、模型及发送器为本地替身。没有在线重载、真实模型/QQ 调用或 V1 数据读取。

复验命令：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_animation tests.test_conversation_animation tests.test_astrbot_animation_host tests.test_conversation_images tests.test_conversation_quotes tests.test_astrbot_image_host tests.test_astrbot_quote_host tests.test_astrbot_media tests.test_astrbot_native tests.test_astrbot_inbound_adapter tests.test_astrbot_model_wire tests.test_astrbot_tools tests.test_astrbot_memory_output tests.test_astrbot_staging_host tests.test_host_recovery tests.test_media_migrations tests.test_isolation -q
```

本机证据目录：`C:/Users/99505/AppData/Local/Temp/v2-private-animation-h3ykz3t5/`，保存模块清单、159 个测试 ID、完整 `verification.log`、`result.json`、本批文件哈希及规范检查结果。28 个本批文件通过 UTF-8 无 BOM、LF、末尾换行与文档链接检查；21 个 Python 文件通过 Python 3.10 语法解析，核心没有 Pillow/宿主导入，源码根没有运行产物。语法解析不代替实际 Python 3.10 运行验收。开发阶段测试与该批次重叠，不相加为总量或完成率。

后续[合并转发切片](CORE_PRIVATE_FORWARDS_SLICE_20260924.md)已接入显示发送者、外层转发者、节点顺序、受众和原件依赖，复用本切片的动画帧服务。节点内 Reply、引用转发的展开、视频/语音、群路由及图片生成/出站仍属后续能力；#255/#256 继续标记为相关 V2 本地输入场景有证据，真实平台与视觉输出待验收。管理/拓展页沿用户指定分工由另一窗口推进。
