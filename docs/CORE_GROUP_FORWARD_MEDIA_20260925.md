# 群转发节点音视频与历史来源复核

日期：2026-09-25

## 行为与范围

群合并转发及嵌套节点现在可以携带 QQ SILK / PCM WAV 语音和 MP4 视频。原群、Bot 账号、外层消息号及实际转发者仍由固定 OneBot 连接核验；节点账号与昵称只作显示归因，不认证说话者、录音者或拍摄者。节点路径和组件顺序进入已有不可变清单。

当前回合复用音频原件与完整 PCM 视图，视频保留原件并提供最多四张有序 PNG 采样帧。提示明确区分独立语音和视频音轨；视频音轨仍未检查，不能据此推断对白或声响。工具续答复用相同媒体与来源证据。

后续群成员接话时，历史只呈现节点文字和附件元数据。语音、视频的历史附件直接复用原件归因，包括节点来源、外层转发者、显示账号、采样覆盖及音轨状态；不会重新向模型发送旧音频或旧视频帧，也不授予下一位成员直接读取原附件的权限。

## 实现与整合

- `adapters/astrbot/group_forwards.py` 按已安装的 loader 启用节点音视频，冻结所有节点后再下载媒体；使用既有 `capture_forward_cards` 复核原件及共享预算。
- `astrbot_host/forwards.py` 接入原音视频 loader，并传递群捕获层已占用的图片预算 `retained`。修复真实 SDK 装配中遗漏这一参数的问题；测试使用注入读取器时不能覆盖这一缺口，独立入口现已覆盖。
- `conversation/group_media.py` 复核完整来源、收集音视频和采样帧证据，将当前转发的媒体贡献转换为历史元数据。已封存历史在媒体撤权后读取失败；新的历史快照跳过不可用转发及依赖它的回复。
- 共享工作树同时接入群直接音视频。本切片整合它与转发节点的合计数量、音频时长、视频时长、字节和帧预算，避免两条捕获路径各自通过后超出总额。群历史指纹按图片、直接音频、直接视频、引用和转发的既有顺序核对；群 Reply 内音视频仍等待独立原件合同。

复用现有 Source、Asset、音频、视频和图片帧表，无 schema 迁移。实现仍位于原领域目录，源码根 Python 仅保留 `main.py`。

## 验证

最终定向范围为 13 个模块、157 项测试与 52 个 subtest。首轮 156 项及全部子用例通过，既有 `test_nested_confirmed_replies_and_quotes_share_one_ancestry_budget` 在四秒测试等待上限处超时；不改生产代码、不调整等待上限，独立复验通过（整项约 4.77 秒，包括多个批次）。因此该范围按测试 ID 去重后均有通过记录；不将一次复验表述为整批一次全过。运行前后核对群捕获、转发读取、历史投影、宿主装配及相关夹具的 SHA-256，所核对文件未在测试期间变化。

新增工具续答测试首次将含工具结果的完整上下文也要求相等，断言过宽；改为比较实际媒体内容与 conversation 来源材料。较早的新测试曾直接 `json.dumps(PromptMaterial)`，已改用可序列化的 payload。早期“预处理伪装”测试失败发生在共享源码仍被修改时，后来复验通过，没有证据将其归因于 pytest 进程并行本身；最终稳定源码回归也覆盖该项。

专项覆盖嵌套音视频、四帧采样、工具续答及本地确认投递；跨成员历史与原件受众；健康原件重启复读且不重新请求平台；外层撤回后重启仍撤销节点、音视频和帧来源；撤销音频视图、视频原件、采样帧资产或音频来源后已封存历史失效；原转发者撤权阻断下一位成员基于旧材料的发送；直接和转发媒体共享预算；未安装解码器和解码期间连接替换不接纳输入。

本批测试模块：`test_astrbot_group_forwards`、`test_group_media`、`test_group_conversation_context`、`test_astrbot_group_host`、`test_conversation_forwards`、`test_conversation_quoted_forwards`、`test_astrbot_forwards`、`test_astrbot_quoted_forwards`、`test_astrbot_audio_host`、`test_astrbot_video_host`、`test_astrbot_quote_host`、`test_astrbot_multi_host`、`test_isolation`。

独立脚本 `tests/group_forward_entry_process.py` 已通过真实 AstrBot 4.27.2 插件 namespace 加载、初始化及启动，真实 SDK 群 Forward / Image 类型与 reverse WebSocket 编解码，群定向展开读取、音频及四帧视频输入、下一位成员元数据历史、两次本地发送 ACK、停机、数据库关闭、路由注销和核心模块释放。

使用 AstrBot 自带 Python，SDK 导入前设置临时 `ASTRBOT_ROOT`；仅用合成媒体、模型替身和本地 ACK，无真实 QQ / 模型请求、在线重载或 V1 数据访问。供应商音频兼容性、真实平台返回格式和识别效果仍需现场验收。

复验入口：在工程目录设置 `PYTHONPATH=C:/Users/99505/.astrbot/backend/app`，运行 `C:/Users/99505/.astrbot/backend/python/python.exe -X utf8 -m tests.group_forward_entry_process`。

收尾检查覆盖 14 个实现、测试和文档文件：UTF-8、无 BOM、LF、末尾换行及无尾部空白通过；8 个 Python 文件 AST / 编译检查、225 个本地文档链接通过。根目录 Python 文件仍仅 `main.py`，核心隔离测试包含在上述定向范围内。

## 下一步

后续[群 Reply 音视频与合并转发原件](CORE_GROUP_QUOTE_MEDIA_20260925.md)已完成下述扩展，新的下一步是群聊图片出站的原群受众与投递回执。以下保留本切片完成时的计划。

扩展群 Reply 原消息合同，支持引用已知群语音、视频及合并转发：核对原发送者与当前引用者、链接已接纳原件，覆盖跨成员授权、撤回、撤权、重启和仅元数据的群历史。继续复用既有媒体与转发领域，不将群公共资料写入私人记忆。真实 QQ / 模型现场验收在支持边界稳定后统一安排。
