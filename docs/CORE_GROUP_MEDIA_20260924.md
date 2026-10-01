# 群图片与引用消息的来源闭环

2026-09-24。本切片在[群公共记忆](CORE_GROUP_MEMORY_20260924.md)和[群共享上下文](CORE_GROUP_CONTEXT_20260924.md)之后，将群图片、动态图帧及 Reply 引用文字/图片接入可信入站、模型证据、工具续答、文字投递和恢复链。群仍默认 preview，真实群发送继续使用原逐群授权。

## 已落地行为

- 群消息可包含 Plain、At、静态图、GIF/APNG/动态 WebP 及一个 Reply，纯图片输入也可接纳。引用原件支持文字、At 和图片；图片及抽帧沿用既有原件库、容器校验、预算和视觉请求格式。
- Reply 的显示正文、声称发送者和 SDK 转换时间不作为原件依据。宿主使用当前账号的 `get_group_msg_history` 按群号与消息号读取一项，核验 self ID、群号、消息 ID、消息类型、非匿名发送者及一致的身份字段；不会退回无群范围的 `get_msg`、私聊历史或扩大读取页。
- 原发送者、发送时间和当前引用者分别保存。对原件当时的发送账号归因，不认定内容已核实，也不以被引用者身份执行操作。发送时间未知则保留未知。
- 网络/图片准备在数据库事务前完成。消息字段和读取结果在附件等待前冻结，完成后复核原账号连接与人格；准备超时、停机、人格变更或连接替换不会接纳迟到的输入。
- 原始群组件也参与范围检查。AstrBot 预处理可能将 Record 转成 Plain；尚未接入的语音、视频和转发不能通过预处理文本伪装成有原件依据的群文字。
- 当前图片按原位置进入模型，工具续答保持同一组原件和证据。群共享历史只展示图片的附件元数据，并明确标记 `historical_metadata_only`；历史引用保留原发送者/引用者，旧图元数据不被表述为本轮重新看到的画面。
- 群合并转发按原群、当前转发者和精确外层消息号读取；文本与图片节点先冻结再捕获，嵌套节点保留路径和显示发送者归因。历史再次进入提示时只保留转发元数据，不重新读取或发送旧图片；群转发中的语音、视频和宿主预处理伪装继续拒绝。

## 归属与撤回依赖

群引用遇到已接纳原件时，先按账号、平台和原消息号查找元数据，再核验完全相同的群/角色/session/conversation 和原发言者。已知私聊、其他群、其他人格或独立成员 session 的原件不能重新发布为当前群资料。内容、图片描述及原件字节须与既有版本一致；同号歧义或篡改会使整个入站事务回滚。

跨成员引用通过群受众视图复核原发言者身份、权限和来源，当前引用者不获得原 Source 的直接读取权。引用来源在统一依赖表中连接引用消息本身、已知原输入及图片/动画证据。引用已确认 Bot 回复时，再核验原投递回执、原上下文及生成所用材料，并链接原依赖；已知 Bot 回复不能改称为另一成员的发言。

原消息撤回会持久撤销派生引用；原发言者撤权、图片资产失效、原件字节变化会在下一次读取、模型续答或发送复核时阻断使用。历史和嵌套引用共用有界依赖检查，异常递归不能无限读取。已有投递回执保留，本地生成/引用成功不代表群成员已读。

来源、图片字节、输入和群身份受理沿既有事务原子提交；发布失败不留下半条输入或新成员权限。重启使用原件库恢复模型材料，重复入站不重复写入或调用模型，未知投递不自动重发。

群记忆仍只为当前本人纯文本输入提供写入句柄；图片解释和引用他人的原话不能直接成为当前成员的长期陈述。群图片入站不开放私聊记忆、私人角色工具或群图片出站。

## 目录与存储

- `companion_v2/adapters/astrbot/group.py` 冻结群组件和装配捕获；`group_quotes.py` 负责单群定向原件读取及 At 表达。
- `companion_v2/adapters/astrbot/group_forwards.py` 负责精确外层群历史、嵌套节点冻结和图片原件捕获；`astrbot_host/forwards.py` 装配私聊/群 Forward 读取器。
- `conversation/quotes/group_originals.py` 复核已知成员/确认 Bot 原件，并返回依赖；`quotes/originals.py` 按场景分发，保留原私聊合同。
- `conversation/group_media.py` 提供历史附件元数据和原件复核；`group_context.py` / `group_history.py` 复用其来源及依赖预算。
- `astrbot_host/quotes.py` 装配真实 SDK 群读取器，`native.py` / `multi_session.py` 传入独立 `group_quote_loader`；`NativeAdapterTypes` 在末尾增加可选字段，原位置参数保持兼容。
- 群记忆的句柄与提示词调整归 `memory/group/`。专项、夹具与独立进程入口分别放在 `tests/test_group_media.py`、`group_media_support.py`、`group_media_entry_process.py`。

复用现有图片表、Source/Asset、来源依赖及会话记录，无 schema 升级，不新增根级业务文件。并行语音切片的 v29 存储与宿主接线保留。

## 定向验收

受影响范围按测试 ID 去重 **143 项全部通过**，其中原群媒体专项 **24 项**、群合并转发增量 **4 项**。补齐原始组件检查和转发读取器后，群媒体、群宿主、群转发及相关私聊/宿主回归均通过；前后复验不重复累计，没有运行无关全库。

| 模块 | 项数 |
| --- | ---: |
| `test_group_media` | 24 |
| `test_astrbot_group_forwards` | 4 |
| `test_group_conversation_context` / `test_astrbot_group_host` / `test_group_memory` | 14 + 12 + 16 |
| `test_conversation_quotes` / `test_astrbot_quote_host` / `test_astrbot_image_host` | 24 + 6 + 4 |
| `test_astrbot_multi_host` / `test_astrbot_staging_host` | 12 + 15 |
| `test_astrbot_group_delivery` / `test_astrbot_group_native_delivery` / `test_isolation` | 11 + 2 + 3 |

专项覆盖静态图与动画 wire、跨成员历史、引用和图序、群定向路由、SDK 声称字段不采用、已知原件一致性、私聊/群/人格/session 隔离、原消息撤回及派生引用、Bot 归因、生成期间原作者撤权、资产撤销与字节损坏、原子回滚、异步冻结、账号/人格变更、准备超时与停机、共享预算、工具续答、未知投递及重启恢复。

收尾期间共享树并行接入私聊视频，独立入口一度因 `astrbot_host/media_components.py` 尚未落盘而导入失败。依赖齐备后真实 SDK 入口重新通过；群媒体、群记忆与多目标宿主 **52 项最终复验通过**，用时 80.167 秒。这些测试已包含在上述 143 项中，未将并行视频功能记为本切片成果。

另通过[独立进程入口脚本](../tests/group_media_entry_process.py)：真实 AstrBot 4.27.2 插件 namespace 导入、初始化/启动、真实 SDK 群图片与 Reply 事件、两成员原件/引用归因、带图片证据的模型请求、真实 reverse WebSocket 群定向读取编解码及两次本地发送 ACK、终止、数据库关闭、路由注销和核心模块释放。

验证使用 `C:/Users/99505/.astrbot/backend/python/python.exe -X utf8`，仅为测试进程设置 `PYTHONPATH=C:/Users/99505/.astrbot/backend/app`，SDK 导入前设置临时 `ASTRBOT_ROOT`。在工程根可运行 `python -X utf8 -m tests.group_media_entry_process` 复验入口。所有图片、身份、模型、原件响应和 ACK 均为合成；没有访问或迁移 V1 数据、在线重载、真实模型调用或 QQ 群发。真实平台原件响应兼容及视觉语义仍需现场验收。

本切片 22 个实现、测试及文档文件通过 UTF-8、无 BOM、LF、末尾换行和尾部空白检查；16 个 Python 文件通过 AST/编译，215 个本地文档链接及配置 JSON 校验通过。源码根 Python 仍仅 `main.py`，核心隔离扫描包含在定向回归中。

## 下一步

继续补齐群转发来源撤回/撤权的跨重启证据和更广的预算/异常恢复场景；群语音/视频、图片出站、媒体长期记忆及记忆管理另行推进。
