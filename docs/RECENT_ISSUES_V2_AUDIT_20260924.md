# 近期 GitHub issues 与 V2 实现对照

核对日期：2026-09-24。读取主陪伴仓库最近 issues、正文及评论，并检查 Content、Memory 和 Image 仓库近期条目。本次重点为主仓库最新 4 个 open issue、相关的已关闭 #252，以及 Memory #32。Content 未返回 issue；Image #11 为生图结果视觉复核设计请求，属于尚待实际接入的生图拓展，不以静态图片输入能力代证。

结论：V2 已消除记忆写入中正文与哈希分开更新的同类竞争路径；直接静态图片输入避开了两个 base64 根因。随后[私聊引用切片](CORE_PRIVATE_QUOTES_SLICE_20260924.md)补齐引用文字/静态图的本地完整链，110 项定向测试通过，其中新增引用测试 25 项；真实 QQ 仍待验收。学习批量审核、群聊生图投递和完整大库响应性尚不能标为已解决。原仓库的 open/closed 是 V1 状态，不等于 V2 验收结果。

媒体后续补验：[历史读取兼容与恢复](CORE_PRIVATE_FORWARDS_SLICE_20260924.md#2026-09-24-历史读取兼容与恢复补验)补齐引用/转发响应形式、错误分类及跨重启混合媒体预算，150 项定向测试通过，其中新增 14 项。真实 SDK 的本地 ACK 证明解包接线；#255/#256 的真实 QQ 现场状态与 #252 的图片出站缺项不因此改变。

随后[Reply 引用合并转发](CORE_QUOTED_FORWARDS_SLICE_20260924.md)补齐引用原消息中的展开节点、静态图和动画帧；原账号定向读取、三层归因、已知原件撤权、工具/记忆依赖和跨重启预算均接入。210 项定向回归通过，其中新增 29 项；#255/#256 的本地覆盖扩大，但不替代真实 QQ 验收，也不解决 #252 的图片出站场景。本段未重新查询远端 issue 状态。

最新[私聊已有原图出站](CORE_PRIVATE_IMAGE_DELIVERY_20260924.md)接入图文单次派发、统一指纹/回执、确认图片历史及迟到对账；真实 SDK 的本地 WebSocket ACK、丢失 ACK、停机与恢复已验证。群文本投递也已单独落地，但 #252 的原群聊生图/上传场景仍待接入，本段没有重新查询远端 issue 状态，也没有真实 QQ 图片验收。

## 逐项结论

| Issue | GitHub 状态 | V2 判断 | 依据及剩余边界 |
| --- | --- | --- | --- |
| [Private #261：学习审核批量通过只处理第一条](https://github.com/menglimi/astrbot_plugin_private_companion/issues/261) | open，9 月 22 日 | 尚未验收 | 当前关系页面维护单个 selected 对象并逐条审阅；没有与旧学习队列对应的批量审批闭环。Issue 正文和评论为空，无法据此断言旧问题的具体原因。管理/拓展页由原任务处理 |
| [Private #256：引用图片 base64 正则 O(n²)，阻塞约 80 秒](https://github.com/menglimi/astrbot_plugin_private_companion/issues/256) | open，9 月 20 日 | V2 引用静态图本地场景已补齐；现场待验收 | V2 没有旧 `looks_like_image_source` 路径；明确解析 base64 前缀，Pillow 校验在线程中运行。新增约 2.7 MB 合成 PNG 的 Reply 捕获、持久化和原字节复核通过。真实 QQ 客户端/平台仍需验收，旧约 18 毫秒数据仅为加载器单次测量 |
| [Private #255：base64 被当成本地路径，引用图被跳过](https://github.com/menglimi/astrbot_plugin_private_companion/issues/255) | open，9 月 20 日 | V2 引用静态图本地场景已补齐；现场待验收 | 原图先按协议解码，不转 `Path`；Reply 从当前账号按好友定向历史读取并核对原 ID，引用正文、原发送者、原件及受众已接线。已有原图可私聊图文出站，需要平台提供定向历史合同；角色实际图片生成/改图与真实 QQ 验收仍未完成 |
| [Private #254：记忆并发写入的 content_hash 与 content 不一致](https://github.com/menglimi/astrbot_plugin_private_companion/issues/254) | open，9 月 20 日 | 新写入链的同类根因已解决，有并发证据 | V2 使用统一 MemoryWriter 和独立数据库；不可变提案的正文/哈希、事实版本、来源、变更和回执在同一外层事务提交。两个独立数据库连接反复竞争同一版本，始终只有一个成功，另一个返回版本冲突；所有已提交历史正文与哈希一致。未修复、导入或验证 V1 受损数据 |
| [Memory #32：大库同步 SQLite / 全量扫描堵死事件循环](https://github.com/menglimi/astrbot_plugin_memory_companion/issues/32) | open，更新至 9 月 19 日 | 部分缓解，仍有架构缺口 | 默认 facts 词法查询已分批增量建索引并按命中读正本；sources、experiences、all 及向量 facts 仍经同步完整候选收集。StorageRuntime 仍用同步 SQLite/RLock；索引初始化有同步 quick_check。未取得 600 MB 级、锁竞争及热重载心跳验收 |
| [Private #252：群聊生图工具超时，但图片后来已发送](https://github.com/menglimi/astrbot_plugin_private_companion/issues/252) | closed，9 月 18 日 | 私聊原图的统一回执已覆盖；原业务场景未完成 | 公共发送/外部工具的取消与超时记录 unknown，不推定未发送；迟到回执按原操作核对，未知不重放。私聊已有原图的图文指纹、确认历史及跨重启迟到对账通过真实 SDK 本地 ACK 验证；群文本路由也已落地。群图片、实际生图/上传与原问题的平台现场仍未完成 |

## 代码证据

- 图片协议与校验：[宿主加载器](../astrbot_host/media.py)，尤其 `load_native_image`；[原生捕获](../companion_v2/adapters/astrbot/native.py) 现接 Plain/Image/Reply；[引用定向读取](../companion_v2/adapters/astrbot/quotes.py)核对原账号、对象与消息 ID；[SDK 图片准备](../companion_v2/adapters/astrbot/provider.py)复核原件，避免宿主另行处理。
- 记忆写入：[MemoryWriter.submit / _commit](../companion_v2/memory/writer.py) 在事务中从同一提案生成正文及哈希；[StorageRuntime.transaction](../companion_v2/storage/runtime.py) 使用连接锁、BEGIN IMMEDIATE、嵌套 savepoint 和失败回滚。[来源发布](../companion_v2/sources/repositories.py)在一个 INSERT 中保存正文、哈希和版本。
- 并发复验：[test_memory_boundaries.py](../tests/test_memory_boundaries.py) 新增 `test_two_connections_keep_content_hash_history_and_receipts_consistent_under_contention`，覆盖两个独立连接和 8 轮同版本竞争，核验 9 份已提交版本及回执。
- 大库剩余路径：[MemoryQuery._documents / query](../companion_v2/memory/query.py)；`kind == facts and vector is None` 才走[增量事实索引](../companion_v2/memory/fact_index.py)。其他分支先收集全部候选，再同步[搜索索引](../companion_v2/memory/search.py)。单次返回数量限制不能约束前面的全量读取耗时。
- 当前页面：[关系与记忆 app.js](../pages/关系与记忆/app.js) 以单条 ID/revision 提交审阅，不构成学习队列批量通过验收。
- 取消/迟到回执：[对话投递](../companion_v2/conversation/delivery.py)、[公共后台投递](../companion_v2/delivery/service.py)、[外部工具](../companion_v2/conversation/external_tools.py)。[OneBot sender](../companion_v2/adapters/astrbot/onebot.py) 当前支持单次私聊图文，绑定[有序原件指纹](../companion_v2/delivery/media.py)；群 sender 继续使用独立授权的文本合同。

## 本地验证

使用 AstrBot 自带 Python 和临时 V2 数据库，52 项定向回归全部通过，用时 16.772 秒：

- `tests.test_memory_boundaries`（含新增双连接竞争）、`tests.test_memory_incremental`、`tests.test_memory_writer`。
- `tests.test_astrbot_media`、`tests.test_astrbot_native.NativeInputTests`。
- 外部工具的超时、取消不重放和迟到回执 3 项；对话投递实际 worker 取消及迟到回执 1 项。

核验时另用 1 项临时诊断探针验证 `Reply + Image`：当时入站返回 `host_media_unsupported`，图片加载器未调用。后续引用切片已补齐该缺口，原探针保留为修复前证据；新增验证范围和平台限制见[引用切片](CORE_PRIVATE_QUOTES_SLICE_20260924.md)。

合成随机像素 PNG 的 base64 加载测量：

| PNG 原件字节 | base64 定位字符串长度 | 完整加载与原件核对 |
| --- | --- | --- |
| 307,965 | 410,629 | 5.880 毫秒 |
| 1,082,119 | 1,442,837 | 8.076 毫秒 |
| 2,704,736 | 3,606,325 | 17.660 毫秒 |

上述为当前机器各 1 次加载器测量，证明大 base64 在该入口成功处理并保持原件，不是完整私聊延迟、事件循环抖动上限或跨机器性能保证。未执行 V1 的耗时正则复现，也未读取用户图片或旧数据库。

只读 GitHub 查询未修改、关闭或评论任何 issue；没有在线重载、真实模型调用或 QQ 发送。本机证据目录：`C:/Users/99505/AppData/Local/Temp/v2-recent-issues-pgcc90zp/`，包含 issue 快照、`verification.log`、`reply-scene.log` 和 `base64-measurements.json`。

## 后续优先级

1. 媒体线已接引用/转发、静态/动态图输入与私聊已有原图出站；继续语音/视频、实际生图/改图及更多嵌套组件。真实 QQ 验收须检查定向历史 API、原消息命中、节点覆盖、视觉输出和图文显示，不能用替身结果代证。
2. 记忆线补其余查询的增量取数，以及数据库/索引启动、维护与锁竞争对宿主事件循环的影响。使用合成大库验证启动、重载、查询及心跳；当前 52 项小库测试不能替代。
3. 管理页任务在接学习队列时增加多选逐项结果、版本冲突、部分失败和重试验证，以 #261 为验收项。
4. 私聊原图已补 #252 所涉及的未知、迟到对账及图片历史语义。后续群图片和实际生图接线继续复用原操作，补真实群场景“调用超时、平台后来送达”的平台验收。
