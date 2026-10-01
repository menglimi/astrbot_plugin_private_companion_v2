# 私聊合并转发与节点来源治理

日期：2026-09-24。本切片接入 AstrBot 原生 `Forward`：私聊中的合并转发可以包含多位显示发送者、文字、静态图片、GIF/APNG/动态 WebP 以及已展开的嵌套记录。直接图片、普通 Reply 引用和合并转发可在同一输入中使用，原位置与节点顺序进入统一对话链。完成的是本地实现及真实 SDK 组件接线，尚无真实 QQ 转发或视觉模型现场验收。

后续[Reply 引用合并转发](CORE_QUOTED_FORWARDS_SLICE_20260924.md)复用本领域的节点冻结、来源和媒体服务，支持引用原消息中的展开转发。210 项相关定向回归通过，其中新增 29 项；下文原批及历史补验计数保留各自时点含义，不与新批次相加。

## 定向读取与平台合同

首次捕获冻结原生 Forward 的位置、标识符和外层消息 ID，随后在固定账号的 reverse WebSocket 上执行一次 `get_friend_msg_history`：当前好友为 `user_id`，外层消息 ID 为 `message_seq`，`count=1`、`reverse_order=false`、`parse_mult_msg=true`。

返回必须恰有一条，外层消息 ID、机器人账号、好友私聊类型及当前发送者全部匹配；随后按出现顺序匹配所有 Forward 组件的数量和标识符。网络等待前后及图片准备前后都核对同一 API、客户端集合和账号连接。模型、重启恢复及工具续答不再访问历史 API。

采用该路径的具体原因：NapCat 的转发组件 `id` 取外层 `msg.msgId`，同一条消息内的多个组件可能共用 ID；其 `get_forward_msg` 实现只取外层第一组件，无法可靠区分同消息内的多份卡片。按好友与外层消息定向读取后，V2 分别消费每个组件自己的展开内容，同 ID 不合并、不替换正文。该场景已有两份不同正文的回归验证。

2026-09-24 只读核对的协议依据：

- [NapCat GetFriendMsgHistory.ts](https://github.com/NapNeko/NapCatQQ/blob/main/packages/napcat-onebot/action/go-cqhttp/GetFriendMsgHistory.ts)：好友 peer 单独选择，`parse_mult_msg` 传入消息解析，返回数组消息。
- [NapCat msg.ts](https://github.com/NapNeko/NapCatQQ/blob/main/packages/napcat-onebot/api/msg.ts)：转发组件使用外层消息 ID，内层 `data.content` 按原消息展开；内层消息 ID 标注为只供查看。
- [NapCat GetForwardMsg.ts](https://github.com/NapNeko/NapCatQQ/blob/main/packages/napcat-onebot/action/go-cqhttp/GetForwardMsg.ts)：按 ID 读取后只取首组件，内层数字 ID 可能不可读取。

因此本切片要求平台提供上述定向历史合同、准确的外层身份字段和展开的节点数组；不扩页、不换账号，也不以全局 `get_msg` 或逐个内层 ID 查询兜底。AstrBot SDK 合同仍为已验证的 4.27.2，不宣称所有 OneBot 实现兼容。

## 归因、顺序与受众

- 外层转发者是当前已认证的私聊参与者。节点的账号、昵称、时间仅是记录中显示的值；合并转发允许自定义这些字段，即使显示账号等于当前用户或 Bot，也不据此认证本人、角色、作者或经历。
- 节点正文作为 `conversation.forward_node` 独立来源，外层输入只保存本轮文字和转发占位。日记的当前用户输入来源不会混入节点正文，不将节点文字自动归入用户事实、偏好、承诺或人格经历。
- 根级节点路径为 `(节点序号,)`，每层嵌套追加 `(父节点中的组件位置, 子节点序号)`。节点按前序保存；图片按外层组件、节点路径及节点内组件位置排序。动态图的原帧序号、相对时间及覆盖声明继续沿用媒体合同。
- 提示词区分外层转发者、节点显示身份、嵌套记录和真正作者。模型只能说明本次返回的内容；原受众、未返回的历史以及时间未知处保持未知，记录中的文字没有新的指令权限。
- 所有根、节点、图片及帧均继承当前私聊的实际受众和授权。节点的群号、显示账号、昵称或展示用消息 ID 不授予其他人的读取权，不切换记忆主体，也不凭这些字段关联已知 V2 用户消息。

平台已省略的记录无法由本切片反推，因此覆盖声明为 `returned_nodes`，不声称已取得完整原群聊或未返回的历史。嵌套数据缺失、格式不支持或超出处理预算会拒绝本次捕获，不静默跳过部分节点。

## 持久化与生命周期

来源依赖为外层输入 → 转发根 → 节点 → 嵌套子节点或图片 → 动画帧。根清单封存节点路径、显示归因和内容指纹；正文与昵称分别脱敏，使用既有来源机制保留脱敏后的重放冲突。事件和提示不保存下载 URL、原始资源定位符或 base64；图片字节继续保存在 v25 原件表。

全部节点先冻结成不可变计划，再进入图片等待；其他中间件或异步过程修改原树不能改写已捕获的节点。网络读取发生在 SQLite 入站事务外，外层消息、转发根、节点、图片和依赖在同一事务内发布，失败全部回滚。

每次生成、工具续答、发送和已确认回复的记忆引用都会重读并核对来源、受众、原节点正文及图片/帧。撤回外层消息会沿依赖撤销派生来源；图片/帧撤权或原件变化会阻止继续使用，包括模型已生成但尚未发送的情形。未知模型或投递结果仍不自动重放。

重启使用已持久化的节点和帧快照，不重新查询历史、下载或解码。停机后完成的准备不能再入站，后来的文字不能越过待完成转发。远端 QQ 原记录的后续变化没有自动同步或撤回订阅，不能把本地快照治理等同于实时平台同步。

## 预算与边界

| 项目 | 当前范围 |
| --- | --- |
| 合并转发 | 单输入/整轮最多 4 个外层组件、共 32 个返回节点 |
| 嵌套 | 最多 4 层，含外层节点；使用定向读取返回的展开内容，不追加内层查询 |
| 节点内容 | 每节点最多 128 个组件；单输入/整轮正文与显示昵称合计最多 65536 字符，单个昵称最多 256 字符 |
| 图片 | 直接图、Reply 图及节点图共用最多 8 个原件、16 个模型图片/帧和 20 MiB 原件及派生帧预算 |
| 单图及动画 | 沿用[动态图切片](CORE_PRIVATE_ANIMATION_SLICE_20260924.md)：5 MiB 原件、256 解码帧、64 × 1024² 累计画布像素、最多 4 个合成视图 |
| 准备时限 | 一条输入的引用、转发读取与图片准备共 25 秒；单次图片下载仍为 15 秒 |
| 模型 | 沿用已有输入估算与配置上限；合法的媒体/文字组合仍可能超过具体模型预算 |

整轮合并同时核对节点数、文字及图片预算，超出则另开批次；请求重建时再次核对。单条超额输入不截断节点。处理预算在 SDK 返回数据后检查，不声称限制了 OneBot 服务端展开过程或 SDK 接收完整 JSON 时的资源消耗。

当前支持节点文字、图片和已展开的嵌套转发/Node；节点中的 Reply、语音、视频和其他组件仍未实现。外层可以同时带 Reply；“Reply 引用一条合并转发”已由[引用转发切片](CORE_QUOTED_FORWARDS_SLICE_20260924.md)接入。群聊前台已有独立 preview 切片，群媒体、图片生成/出站及语音视频沿后续路线推进。

## 文件归属与兼容

| 位置 | 职责 |
| --- | --- |
| `companion_v2/conversation/forwards/models.py` | 捕获、持久清单、节点路径、提示词和共享预算 |
| `companion_v2/conversation/forwards/service.py` | 脱敏、原子发布、依赖及逐次读取 |
| `companion_v2/adapters/astrbot/forwards.py` | 注入客户端的定向读取、外层匹配和节点冻结 |
| `astrbot_host/forwards.py` | 真实 SDK 客户端及媒体加载器装配 |
| `tests/forward_support.py`、`test_astrbot_forwards.py`、`test_conversation_forwards.py`、`test_astrbot_forward_host.py` | 合成夹具、协议边界、完整对话链及真实 SDK/生命周期 |

仅带 Forward 的输入使用新事件类型；既有纯文本、图片和 Reply 的持久序列化及重放哈希保持。复用 v25 来源、依赖和原件表，没有 schema 迁移。根级 Python 仍只有 `main.py`，管理/拓展页面按用户分工由另一窗口负责。

## 验证

新增转发专项共 34 项：适配器 16 项、对话与治理 15 项、真实 SDK 宿主 3 项。覆盖定向身份/消息核对、同 ID 多卡片、嵌套、混合静态/动态图顺序、不可变捕获、预算、脱敏重放冲突、回滚、撤回/撤权、工具与记忆、恢复、未知不重放和停机顺序。

最终 **226 项定向测试全部通过，用时 80.434 秒，无失败、错误或跳过**，覆盖 20 个受影响模块，包含上述 34 项新增测试。静态图、引用、动态图、原生入站、模型 wire、工具续答、统一宿主、staging、停机/路由注销、恢复及核心隔离同时通过。

测试使用 AstrBot 自带 Python 3.12.12、临时 SDK 数据根和临时 V2 数据库，平台、模型和发送器均为合成替身。没有在线重载、真实模型/QQ 调用或 V1 数据读取。

复验命令：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_forwards tests.test_conversation_forwards tests.test_astrbot_forward_host tests.test_astrbot_animation tests.test_conversation_animation tests.test_astrbot_animation_host tests.test_conversation_images tests.test_conversation_quotes tests.test_astrbot_image_host tests.test_astrbot_quote_host tests.test_astrbot_media tests.test_astrbot_native tests.test_astrbot_inbound_adapter tests.test_astrbot_model_wire tests.test_astrbot_tools tests.test_astrbot_staging_host tests.test_astrbot_staging tests.test_host_application tests.test_host_recovery tests.test_isolation -q
```

本机证据目录：`C:/Users/99505/AppData/Local/Temp/v2-private-forwards-_awdpupm/`。`modules.json`、`final-tests.json`、`final-verification.log` 和 `final-result.json` 保存最终范围、逐项日志与结果。较早的 224 项记录使用修正前的读取方式，仅作开发历史，不与最终批次相加。

## 2026-09-24 历史读取兼容与恢复补验

本轮将引用和转发共用的历史响应解析放在 [adapters/astrbot/history.py](../companion_v2/adapters/astrbot/history.py)。接收四种明确的容器形式：直接消息数组、`{"messages": [...]}`、`{"data": [...]}`、`{"data": {"messages": [...]}}`。只解包一层；同时出现两个载荷、递归套层、非数组或显式失败/待处理状态会拒绝。无论容器形式如何，原有“只返回一条、固定账号与好友、核对原消息 ID、组件顺序与数量”的校验继续执行，失败不会转向全局消息查询、其他账号或更大的历史页。

只读检查本机 `aiocqhttp.api_impl` 确认：`WebSocketReverseApi.call_action` 经 `_handle_api_result` 先去掉标准响应的 `data` 外壳，SDK 已丢弃的字段无法由适配器复核。新增真实 SDK 回归使用本地 ACK 对象，通过实际 `ResultStore` 分别交回对象形式和数组形式的 action data，引用及转发均成功读取。额外包装形式属于注入读取器的合成兼容覆盖，不代表已验证其他 OneBot 实现或真实 QQ 数据。

另修正了以下边界：

- 转发的非数字外层消息号返回 `host_forward_invalid`，不会再误报引用错误；返回的消息号不合法按 `host_forward_scope_mismatch` 处理。双负号等格式不再从整数转换处抛出通用捕获错误；合法有符号 ID 的合同保留。
- `freeze_nodes` 遇到明确组件类型时只接受 `node` 包装。带其他类型但碰巧拥有 `message/content` 的对象，不能再冒充展开消息；根层和嵌套层均在图片准备前检查。
- 总附件准备超时返回 `host_media_timeout`，宿主人格查找冒出的超时返回 `host_capture_timeout`；读取器直接收到 `TimeoutError` 时分别返回 `host_quote_timeout` / `host_forward_timeout`。SDK 转成普通网络错误的情形仍返回对应 `unavailable`，不通过异常文字猜测类型。总准备预算仍为 25 秒，取消不会发布已准备的部分引用、节点或图片。

混合媒体恢复新增了跨重启场景：两条“直接图 + 引用图 + 转发动画”合并成 6 个原件、12 个模型视图；重启从原件恢复后再加入 1 个转发动画，共 7 个原件、16 个视图，仍属同一轮。下一张静态图会因第 17 个模型视图另开批次。恢复原批次期间没有历史 API 读取或重新解码。

节点内 Reply 暂不扩展。节点显示的账号、群号及消息号都不能证明原始 peer、Bot 账号和受众；把它的 Reply ID 交给当前好友历史查询，可能读取另一条同号私聊消息。因此本轮保留明确的 `host_forward_unsupported`，并验证带 Reply/未展开组件的记录在下载图片前整体失败，且只发生一次外层定向读取。该补验时“Reply 引用完整转发”仍待接入，随后已由[引用转发切片](CORE_QUOTED_FORWARDS_SLICE_20260924.md)补齐；语音/视频及图片出站继续补齐来源或发送合同。

最终 **150 项定向测试通过，用时 65.391 秒，零失败、零错误、零跳过；相对上一批新增 14 项**。范围包含历史响应、转发、引用、直接图、动画、SDK 宿主启停/路由注销、入站和核心隔离。原 226 项与本批范围不同且重叠，不相加。复验命令：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_history tests.test_astrbot_forwards tests.test_conversation_forwards tests.test_astrbot_forward_host tests.test_conversation_quotes tests.test_astrbot_quote_host tests.test_conversation_images tests.test_astrbot_image_host tests.test_astrbot_native tests.test_conversation_animation tests.test_astrbot_animation_host tests.test_astrbot_staging_host tests.test_astrbot_inbound_adapter tests.test_isolation -q
```

本机证据目录：`C:/Users/99505/AppData/Local/Temp/v2-media-history-48z6dsf9/`；`modules.json`、`tests.json`、`new-tests.json`、`verification.log` 和 `result.json` 保存本轮范围与结果。本轮 11 个 Python 文件通过 UTF-8 无 BOM、LF、末尾换行及 Python 3.10 AST 检查。未变更持久事件形状或 v25 schema，根级 Python 仍仅 `main.py`。使用临时 SDK/V2 数据根及合成内容，无在线重载、真实模型/QQ 调用或 V1 数据读取。
