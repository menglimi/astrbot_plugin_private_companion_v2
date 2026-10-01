# 七个拓展建设情况：整体盘点（2026-09-27）

对象：Content、Image、Screen、Together、Reality、Game、Live 七个**能力提供方**（选项插件）。方法：不采信任何文档自评，只采信①各仓库真实文件与代码、②本体侧生产调用点、③本机可复现的装配与测试结论。

> 2026-10-01 Image 更新：当前版本为 0.5.0；现有原生生成/编辑链新增当前私聊多参考与 `image.mask_edit` 局部编辑。下方盘点保留 2026-09-27 时的测试文件数量和其他提供方状态；Image 当前专项与本体回归结果见 [Image 提供方状态](COMPANION_PROVIDER_STATUS_20260927.md) 及本次交付包验收。

## 一、总表

| 拓展 | 版本 | 声明动作 | 本体侧专门消费者 | 提供方门禁 | 提供方测试文件 | 准入 | 结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Content** | 0.2.3 | 7 | ✅ `native_extensions/content.py`（章节标题兼容读取） | 插件 `enabled`（默认 true） | 8 | 已接线 | E05 待测 / E06 待重评 |
| **Image** | 0.5.0 | `generate`/`edit`/`mask_edit`（按后端能力） | ✅ `native_extensions/images.py` + `image_settings.py` | `native_v2.enabled`（默认 **false**） | 38（2026-09-27） | 已接线 | E02 待测；E03 当前私聊参考与蒙版已接线 |
| **Screen** | 3.3.1 | 1 | ✅ `native_extensions/screens.py`（6.1 KB） | `native_v2.enabled`（默认 **false**） | 4 | 已接线 | E07 待测 |
| **Together** | 0.9.0 | **7**（房态 3 只读 + 建/关/邀/加入） | ⚠️ 仅 `together.room.create` 一处特判 | 无独立开关（`server` 组控制） | 25 | 已接线；邀请投递缺 | E09 待测 |
| **Reality** | 0.4.1 | **7**（只读 4 + 控制 3） | ✅ **新增只读领域校验**（本轮） | 家居模块 `enabled`（默认 **false**） | 9 | 已接线 | E11 待测 |
| **Game** | 0.2.8 | **22**（五种玩法：tictactoe/gomoku/xiangqi/pig_dice/blackjack） | ⚠️ `game_ingestion.py` 覆盖 9 个终局相关动作 + `application.py` 编排开关 | `native_v2.*` 各玩法（默认 **false**） | 22 | 源码已接线 | E13 待测 |
| **Live** | 1.8.1 | **2**（`live.status.read`、`live.events.recent`） | ✅ **新增只读领域校验**（本轮） | `native_v2.enabled`（默认 **false**） | 4 | 已接线 | E15 待测 |

> 上一版表格的 Reality 写成 4、Together 写成 3，是**按动作前缀计数**得出的，与提供方 `_ACTIONS` 集合不符；本版按 `native_v2/provider.py` 的 `_ACTIONS` 与 manifest 实测更正。声明的动作里只有部分有本体消费，见第二节。

交付面：`companion-v2-20260927-content2` 含 **8 个包**（本体 2.0.0 + 七家 `native-provider`），全包哈希与语法校验通过、宿主加载/停机/路由注销通过。目录名与常识不同，易踩：Live 是 `astrbot_plugin_live_stream_companion`，Image 的原生入口在 `astrbot_plugin_image_companion/image_companion/native_v2/`。

## 二、按"有没有本体消费者"的真实分层

本体不替提供方做领域裁决，所以"有专门消费者"不等于"没消费者就没接线"。但两类差别是实质的：

**有专门领域消费者（4 家）** —— 结果要被本体核对、采纳或落库：
- **Image**：`IMAGE_ACTIONS` 当前三个动作，采纳器把验证后的原件送进既有 V2 来源、图片与 sender 流程；多参考和蒙版输入经本轮一次性授权句柄传递。
- **Screen**：有截图准入（`preflight`）与采纳，屏幕图有专门的所有权与出站拦截；
- **Content**：7 个动作的结果核对、版本锚点、撤回同步、续写握手都在本体；
- **Reality / Live（本轮新增）**：只读结果由 `companion_v2/capabilities/native_reads.py` 的领域读取器核对，见下。

**只有编排开关或目录项（2 家）** —— 结果由通用原生通道处理，本体不做领域核对：
- **Game**：动作实测 **22 个 / 五种玩法**，本体侧只有 `game_ingestion.py` 的 **9 条**动作→玩法映射（用于终局经历摄取）+ `application.py:338-341` 的编排开关；`create/close/snapshot` 等走通用通道；
- **Together**：`together.room.create` 一处特判（建房需要本体侧的 `host_persona`/`host_execution`，与提供方要求一致）；其余 6 个动作走通用通道。**`together.room.invite` 只创建邀请、不发送**（提供方只回 invitation_id 与期限），投递仍需 V2 侧单独完成，这是 E10 的实体缺口。

## 二之二、本轮新增：只读提供方的领域校验

`companion_v2/capabilities/native_reads.py` 为 Reality 的 4 个只读动作与 Live 的 2 个只读动作装上领域读取器（通用通道已保证 scope/受众/owner/哈希，所以这里只管领域才知道的三件事）：

1. **凭据绝不进上下文**：设备目录与平台状态可以带标识与账号状态，但 token/cookie/password 一类键在任意深度出现即**直接拒绝**，不是静默过滤；
2. **直播游标必须前进**：`after_event_id` 的存在意义就是"停播/重启后不重复投递"。已投递过的事件再次出现即 `native_read_replayed` 拒绝；从一个本关系从未收到过的游标续读、或一页里重复自己的 event_id，同样拒绝；
3. **观众文本只是材料**：`live.events.recent` 的每条事件必须带稳定 `event_id`，且不得把自己的文本标成 `trusted`/`instruction` 之外的语义。

状态记在 `runtime_metadata` 的键前缀下（每个关系 + 平台一个已投递集合），不升 schema。

验证：`tests/test_native_extensions_registry.py` 的策略与游标用例，加上 `tests/test_native_provider_host.py` 的**宿主级端到端**用例——真实应用装配、真实授权、真实子任务，走完一次 `live.events.recent` 后断言回执为 `succeeded/none` 且已投递集合落库。

这四家的共同含义：**它们的回执、产物与拒绝语义只由提供方与通用通道保证，本体没有领域级校验**。做验收时要按这个区别设计检查点（E11/E13/E14/E15/E16 尤其）。

## 三、门禁现状（一个容易误判的风险）

七家中 **五家的原生能力默认关闭**（Image、Screen、Game、Live、Reality 都靠各自的开关或模块 `enabled`，默认 false），这是符合"新增能力默认关闭"的正确形态。

例外两个，需要知情而不是当缺陷：
- **Content** 的 `enabled` 默认 **true**——即装即开。它对私聊专属受众有边界约束，但"默认开启"这一点与其余五家的口径不一致；
- **Together 没有独立原生开关**，其原生声明不受专项开关控制，能力由 `server` 组决定。

## 四、验收面

`V2_REAL_WORLD_ACCEPTANCE_CHECKLIST.md` 的 E01–E17 **十七行结果列全部为「待测」**——真实平台、真实模型、真实设备的结论一条都没有。准入列分布：7 行「已接线」、4 行「已接线+限定语」、5 行「待补齐」（E04 相册衣柜、E06 封面/分享/QQ 空间、E08 定时观察、E14 其余游戏与房间、E16 直播呈现）。

需要按本批复核修正的两行：
- **E06**：原「待补齐」应改为「续写握手已实现并验证；封面关联与分享材料已实现但**无生产入口**；QQ 空间未做」。准入语要和实现级别一致，不能笼统写已接线；
- **E13**：写的是"四种聊天游戏"，而实测 Game 有**五种玩法/22 个动作**（象棋在列）。E13 任务描述需要同步，否则验收会漏测象棋。

## 五、已知偏差（承接[设计稿偏差审计](DESIGN_VS_IMPLEMENTATION_AUDIT_20260927.md)）

本轮未新增代码改动，只做盘点。仍在册的严重项摘要：

1. **Screen 的"理解与反馈"消费链断在半路**——解释与锚点的唯一写入点在没有生产入口的链上，主动与日记两条消费链在真实运行中取不到数据（审计 B9/B10）；
2. **屏幕图被发给出站选择的 `sendable_image` 句柄**——模型照提示回选会导致整轮回复失败（审计 B0a，未改）；
3. **Together 的 `work` 模式可能被静默降级为 `call`**，而回执与快照对同一批数据给出不同模式（审计 B0c）；
4. **Reality/Together 的操作日志损坏会让插件构造失败**，连带关闭无关的 V1 功能（审计 B0d）；
5. **陪伴小屋无法清除已保存的 Image 密钥**（审计 B11）；
6. **Content 封面关联与分享材料没有生产入口**（本文第一节与[编排契约](CONTENT_AUTHORING_ORCHESTRATION_20260927.md)第零节）。

## 六、结论

- **建设完成度**：七家都是"源码 + 定向测试 + 切片文档"齐备，动作都在提供方侧真实声明，交付包完整；**本体侧 5 家有领域级核对/采纳**（Content、Image、Screen，以及本轮新增的 Reality、Live 只读校验），另 2 家停在编排开关或通用通道（Game、Together）。
- **建设缺口**：① Together 的**邀请投递**（`together.room.invite` 只建邀请不发送）；② 2 个已实现的 Content 部件（封面关联、分享材料）缺生产入口；③ 5 行准入「待补齐」（E04/E06/E08/E14/E16）。
- **本轮否定的一处"缺口"**：Game 的 `closed`（开局后收场）**本来就不该写经历**——`tests/test_game_memory_ingestion.py` 明确断言关闭的对局不产生记忆。我一度把它当缺口补上，被测试挡下后撤回；现在把这条意图写进了 `game_ingestion.py` 的注释，避免下次再被误判。
- **验收缺口**：17/17 待测，且 E06/E13 两行的任务描述需要按本轮复核改写。
- **口径提示**：本表"准入"只表示"代码与本体接线就位"，**不表示任何现场效果**。把准入当验收会重复历史上"文档自评替代验证"的错误。
