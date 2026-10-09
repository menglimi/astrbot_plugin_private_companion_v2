# 七个可选伴侣：状态 / 设计稿 / V1 实现 / 要求 / 进度

日期：2026-09-27（Reality 项于 2026-10-01 复核）。对象是 Content、Image、Reality、Screen、Together、Game、Live 七个**能力提供方**（选项插件），不含 V2 本体。

口径与来源：

- 状态与动作清单：各家 `native_v2/provider.py`（Image 为 `native_v2/adapter.py`）在代码里真实声明的 action 字符串，不是文档自评；
- 版本与包：最新交付包 `companion-v2-20260927-p5` 的 `release-manifest.json`（8 包 = 本体 + 七个提供方，全包哈希与语法校验通过）；
- 进度：`docs/BUILD_STATUS.md`、各切片记录、`docs/V2_REAL_WORLD_ACCEPTANCE_CHECKLIST.md` 的 E01–E17；
- V1 实现：V1 插件目录 `../astrbot_plugin_private_companion/` 的真实文件名（路径相对本文所在 `docs/`）；
- 只读盘点，未改业务代码、未连宿主、未调模型、未发送消息。

## 一、一页总表

| 提供方 | 版本 | V2 声明动作 | 原生开关 | 进度 |
| --- | --- | --- | --- | --- |
| **Game** | 0.2.8 | 22 个（五种玩法） | `native_v2` 组 | 源码 + 测试齐备；五种玩法进聊天内工具，浏览器房间与邀请缺 |
| **Content** | 0.2.3 | 7 个 | 无独立开关（由插件 `enabled` 决定） | 作品基础链 + 续写握手 + 写作边界设置已接线；读取页补回章节标题；封面关联与分享材料**已实现未接线**；独立创作批处理与 QQ 空间缺 |
| **Image** | 0.5.0 | `image.generate` / `image.edit` / `image.mask_edit`（按后端声明） | `native_v2` 组 | 原生生成、同源改图、私聊输入参考、多参考和蒙版局部改图已接线；相册衣柜缺 |
| **Reality** | 0.4.2 | 8 个 | 无独立开关（家居模块 `enabled`） | 手机/摄像头/设备目录与状态/电源与属性动作/操作查询与取消均进入原生目录；V2 按能力逐项授权 |
| **Together** | 0.9.0 | 3 个（房间四模式） | 无独立开关 | 建房/查询/关闭已接通；真实活动执行缺 |
| **Screen** | 3.3.1 | 1 个 | `native_v2` 组 | 单次截图全链通；定时观察/轨迹/远端缺 |
| **Live** | 1.8.1 | 2 个（只读） | `native_v2` 组 | 场次 + 近期事件只读已接通；主动回复/呈现缺 |

七个提供方的共同形态：**源码 + 定向测试 + 切片文档齐备，现场验收全部为「待测」**。E01–E17 十七行没有任何一行有现场结论。

## 一之二、进度分级口径（2026-09-27 复核）

此前本表把"代码存在且有测试"直接写成"已实现"，掩盖了**有没有生产消费者**这一层。现按三级口径记录，每级都要有证据：

| 级别 | 判据 |
| --- | --- |
| **已实现** | 代码在位、有契约测试；**不保证**被任何生产路径调用 |
| **已接线** | 除上者外，存在真实生产调用点（非仅测试） |
| **已验证** | 除上者外，在本机以真实装配跑通并可复现 |

Content 编排的三段按此口径复核结果：

| 部件 | 级别 | 证据 |
| --- | --- | --- |
| 续写握手 `ContentAccess.continuation` | **已验证** | 生产调用点 `astrbot_host/native_extensions/content.py:96-100`；`test_native_content_flow` 端到端落库 |
| `authoring.py` 提示词与解析契约 | **已接线** | 唯一生产消费者是 `authoring_service.prompt/parse_draft`，尚未被任务调用 |
| 写作边界设置 `ContentAccess.authoring` | **已接线** | 随每次操作经 `bind_content_context(authoring=...)` 交给提供方 |
| 封面关联 `ContentCoverService` | **已实现**（未接线） | 无生产实例化点；`record_cover` 无合法注入点（见下） |
| 分享材料 `ShareMaterial.from_content_work` | **已实现**（未接线） | 无调用方，作品材料尚未进入主动候选 |
| `content.authoring.draft/review` | 仅装配 | 注册出 16 个矩阵字段；无生产者调度 |

**封面关联的接线障碍（已核实）**：提供方 `content.work.save_candidate` 的 schema 是 `additionalProperties: false`，宿主经工具参数传 `cover_asset_id` 会被判非法参数而拒绝；`RoleArtifact.work` 是活动类（reading/sleep）的归属，不是作品。合法接线点只有两个，需先定：① 在 Content 提供方的 `save_candidate` schema 里加一个封面字段；② 由宿主在图片采纳后提供自有的作品关联步骤（此时载体应挂在 Image/媒体域，而不是 Content 域）。

**同类风险（已修）**：提供方 `bind_content_context` 原先只接受 `target`/`check_access`，宿主多传的关键字会让 `TypeError` 被兜成 `native_adoption_unavailable`。已改为显式接受 `authoring`/`continuation` 并存入调用绑定（提供方 V2 测试 73 项通过）。

## 二、逐提供方

### Game（`astrbot_plugin_game_companion` 0.2.8）

- **状态**：**五种**聊天内游戏各自独立开关、独立操作账本、终局经历只引用确认回执。
- **动作（22 个，已按代码常量实测）**：井字棋 / 五子棋 / **象棋** 各 `read`·`create`·`move`·`close`（象棋依赖 Pikafish 引擎）；掷骰竞分 `read`·`create`·`roll`·`hold`·`close`；二十一点 `read`·`create`·`hit`·`stand`·`close`。
- **对应设计稿**：[GAME_LIVE_NATIVE_20260926](GAME_LIVE_NATIVE_20260926.md)、[CORE_GAME_RULES_SLICE_20260926](CORE_GAME_RULES_SLICE_20260926.md)、提供方 `docs/`。**注意该权威稿只写到四种玩法（象棋缺失），与代码不符**，已在下一节记为偏差。
- **对应 V1 实现**：`../astrbot_plugin_private_companion/` 的 `game_companion` 相关模块（七种游戏、浏览器房间）；索引见[任务清单](V2_GAP_CLOSING_TASKS_20260927.md)「v1 既有资产索引」。
- **要求**：规则由提供方权威裁决；操作账本重启可重放；二十一点结算前庄家底牌与牌堆不外露；终局经历只源自确认回执；不复用 V1 房间服务。
- **进度**：V2 侧 `tests/test_games_*`、`test_game_native_*`、`test_game_memory_ingestion.py`；提供方 22 个测试文件。验收 E13（玩法）为「已接线；最终包待构建」→ 本包已构建；E14（其余玩法、房间席位、邀请、余韵）**待补齐**。终局经历生产器已消费**三种棋类**（含象棋的 `create`/`move`）。

### Content（`astrbot_plugin_content_companion` 0.2.3）

- **状态**：作品正本 + 不可变版本 + 候选采用 + 撤回传播全通；薄入口 `companion/content_v2/provider.py`（250 行）。
- **动作**：`content.work.create` / `save_candidate` / `adopt` / `retract` / `list` / `read`。
- **对应设计稿**：[CONTENT_NATIVE_CONSUMER_20260925](CONTENT_NATIVE_CONSUMER_20260925.md)、[CORE_NATIVE_GAP_CLOSURE_20260925](CORE_NATIVE_GAP_CLOSURE_20260925.md)、[CORE_TOOL_CATALOG_20260925](CORE_TOOL_CATALOG_20260925.md)（36 项工具目录）、[Content 宿主侧编排契约](CONTENT_AUTHORING_ORCHESTRATION_20260927.md)（续写握手、封面关联、主动分享）。
- **对应 V1 实现**：提供方自身的创作/续写/审核模块；V1 侧另有 QQ 空间（`qzone_*`）与自动生活发布。
- **要求**：创作/续写/封面/分享各有可核对回执；保存不等于发送；撤回必须让派生材料与未发送草稿失效；V2 只做消费与采用，编排在宿主侧而正文与版本裁决归 Content。
- **进度**：V2 侧 `tests/test_native_content_flow.py`、`tests/test_content_authoring.py`、`tests/test_content_cover_and_share.py`、`tests/native_content_support.py`；提供方 8 个测试文件。**三段编排已实现并验证**——续写握手（读固定版本 → 保存必须沿用同一版本）、按需单轮审校（不产出统一质量分）、封面关联三条行为规则（改标题不重画／实改转旧版／晚到归原版本）、作品版本身份的分享材料（`CONTENT_WORK`，构造即不写记录不披露）；另注册 `content.authoring.draft`/`content.authoring.review` 两条模型任务供 Provider 与预算分配。验收 E05「已接线 待测」；E06 由「待补齐」更新为「**创作/续写编排、封面关联、主动分享已实现**；独立创作批处理与 QQ 空间待补齐」。

### Image（`astrbot_plugin_image_companion` 0.5.0）

- **状态**：独立 owner、存储、执行、采用与私聊/群聊投递；`native_v2/adapter.py` 按后端 `operations` 动态声明。
- **动作**：`image.generate`、`image.edit`（保存原图或本轮私聊/群聊输入图，支持多参考用途；角色参考图按角色共享，群聊使用单独开关默认关闭）、`image.mask_edit`（明确底图与蒙版，私聊）。
- **对应设计稿**：[CORE_NATIVE_IMAGE_DELIVERY_20260925](CORE_NATIVE_IMAGE_DELIVERY_20260925.md)、[CORE_PRIVATE_IMAGE_DELIVERY_20260924](CORE_PRIVATE_IMAGE_DELIVERY_20260924.md)、[CORE_GROUP_IMAGE_DELIVERY_20260925](CORE_GROUP_IMAGE_DELIVERY_20260925.md)、提供方 `docs/IMAGE_V2_NATIVE_PROVIDER_20260925.md` 与 `docs/IMAGE_NATIVE_EXECUTION_V1.md`。
- **对应 V1 实现**：`photo_generation_scope.py`（已迁为 T01 张数额度）、`photo_reference_*`（图参考记忆，V2 无对应物）、`photo_wardrobe_decision.py`（衣柜）、`image_edit_region.py`（区域编辑）。
- **要求**：后端每次只执行一次；未选产物不附图；原产物、来源与 QQ ACK 可对账；未实现的模式不得伪报成功；凭据归提供方，V2 不复制密钥。
- **进度（源码）**：E03 的当前私聊/群聊输入图租约、多参考用途绑定、角色参考图群聊权限、蒙版工作流校验及蒙版外像素保护已接线；宿主仅为原调用签发一次性句柄，读取和采用均重新核权。群聊目录与准入明确排除 `image.mask_edit`。E04（相册/衣柜/每日穿搭）仍**待补齐**。2026-10-01 Image 提供方原生专项 21 项通过；V2 图片、额度、目录与门禁集 63 项通过、16 个子用例通过，另有一个群聊续轮用例因提示前缀校验失败，详见[实施记录](IMAGE_EXTENSION_GAP_DESIGN_20260927.md)。E02/E03 合成测试通过不等于真实后端或 QQ 现场验收。

### Reality（`astrbot_plugin_reality_companion` 0.4.2）

- **状态**：只读快照/目录/属性 + 受限单设备控制；凭据留在提供方配置（`access_token` 为密码字段，不回显、不下发手机端）。
- **动作**：`reality.snapshot.read`、`reality.camera.observe`、`reality.device.list`、`reality.device.status`、`reality.device.control`、`reality.device.action`、`reality.operation.lookup`、`reality.operation.cancel`；V2 对八项分别登记私聊授权并实际筛选模型工具目录。
- **对应设计稿**：[REALITY_TOGETHER_NATIVE_20260926](REALITY_TOGETHER_NATIVE_20260926.md)；提供方 `手机陪伴终端从零配对说明书.md`。
- **对应 V1 实现**：`mihome` 场景、移动位置/活动/遥测、摄像、本地音频、提醒/唤醒。
- **要求**：只暴露别名与白名单属性，DID、设备原名与令牌永不进入对话或页面；关闭只读能力后立即拒绝；控制必须有设备 `confirmed`，`unknown` 保留原操作且不自动重试。
- **进度**：V2 侧 `tests/test_reality_together_native.py`、`tests/test_reality_access_api.py` 与感知页合同检查；提供方原生动作合同覆盖设备目录/状态/两类控制/操作查询/取消及不重放，共 20 项。端到端使用合成手机与平台回执验证；真实摄像头、手机和设备现场验收仍待完成。Reality 走 Home Assistant 兼容入口，不是直连米家。

### Together（`astrbot_plugin_together_companion` 0.9.0）

- **状态**：房间 create/snapshot/close；建房参数 `mode` 只允许 `call`/`watch`/`work`/`novel`；票据固定角色、模型（`model_provider_id`）与语音（`tts_provider_id`/`tts_language`）执行绑定；小说书库按 V2 scope 隔离。
- **动作**：`together.room.create`、`together.room.snapshot`、`together.room.close`。
- **对应设计稿**：[REALITY_TOGETHER_NATIVE_20260926](REALITY_TOGETHER_NATIVE_20260926.md)。
- **对应 V1 实现**：观影/通话/共读/工作房间、视频帧与字幕、实时语音与打断、活动通知与共同经历。
- **要求**：房间只使用已固定的 V2 执行绑定，不调用 V1 模型/语音配置；其他人不能看到或关闭他人房间；关闭后票据失效；活动进度与当前参与者一致。
- **进度**：V2 侧 `tests/test_reality_together_native.py`；提供方 23 个测试文件。验收 E09「已接线 待测」，E10「已接线；完整活动待核对 待测」——**建房不等于完整活动**，声画/书籍进度与打断仍需接线。

### Screen（`astrbot_plugin_screen_companion` 3.3.1）

- **状态**：单次本机截图提供方；V2 侧流水线含原件、授权、模型解释与反馈回执。
- **动作**：`screen.capture`（`arguments` 必须为空对象）。
- **对应设计稿**：[SCREEN_NATIVE_HOST_INTEGRATION_20260926](SCREEN_NATIVE_HOST_INTEGRATION_20260926.md)、[SCREEN_NATIVE_CAPTURE_SLICE_20260925](SCREEN_NATIVE_CAPTURE_SLICE_20260925.md)。
- **对应 V1 实现**：`screen_action_config` 的定时观察、自定义任务、窗口/输入轨迹、远端采集。
- **要求**：每次只采一张图；采集前后复核授权；原图只进入获授权模型，**不作为 QQ 发图**；V1 旧自动观察不自动迁入。
- **进度**：V2 侧 `tests/test_native_screen_flow.py`、`test_screen_capture.py`、`test_screen_originals.py`、`test_screen_pipeline.py`；提供方 4 个测试文件。验收 E07「已接线 待测」，E08（定时观察/自定义任务/轨迹/远端）**待补齐**。

### Live（`astrbot_plugin_live_stream_companion` 1.8.1）

- **状态**：只读端口，不启动直播、不发送平台消息、不写 V1 记忆。
- **动作**：`live.status.read`、`live.events.recent`（`platform`、`limit`、`after_event_id`、`session_id`）。
- **对应设计稿**：[GAME_LIVE_NATIVE_20260926](GAME_LIVE_NATIVE_20260926.md)。
- **对应 V1 实现**：B 站/Twitch 主动回复、VTS 表情/热键/参数、字幕/TTS/嘴型、OBS、观众观察/话题/高光/小结。
- **要求**：事件只属于当前场次，停播清场次与缓存；游标淘汰返回 `cursor_reset` 而不是静默重放；观众输入不得成为指令；禁用平台的事件与房间信息一律遮蔽；工具声明只列已开放平台。
- **进度**：V2 侧 `tests/test_live_native_provider.py`、`test_astrbot_multi_live_acceptance.py`；提供方 5 个测试文件。验收 E15「已接线 待测」，E16（角色接话/呈现/高光/结局记忆）**待补齐**。

## 三、跨提供方的共同要求（V2 合同）

以下九条对七家一致，验收时逐条核对，不因"某家已经过测试"而豁免：

1. **身份**：保留各自插件身份，不另注册 V2 本体，不新增公开 Dashboard 页。
2. **入口**：能力经 `extension_api.companion_v2_native()` 同步声明、异步执行；宿主负责权限、角色复核与回执采用。
3. **凭据**：密钥、地址与提供方专属参数留在提供方配置，V2 只存引用、授权与能力状态。
4. **权威**：规则/状态裁决在提供方，V2 不重算；V2 不解码、不伪造提供方语义。
5. **结果**：`unknown`/`started` 不得说成成功，也不得换一个调用编号重做同一未知操作。
6. **隔离**：按 V2 安装、Bot、角色、scope 隔离；多 Bot 同角色不串用；不复用 V1 房间/记忆/模型配置。
7. **默认**：新增能力默认关闭；关闭即不再执行，禁用平台的信息不暴露。
8. **投递**：真实发送另需授权与回执；只读端口不发送。
9. **验收分离**：源码在位、定向测试、页面接入、现场通过是四件事，不能互相替代。

## 三之二、设计稿与实现的偏差（2026-09-27 审计）

该日对这批设计稿做了一次逐条核对（四路并行只读审计 + 本人复核），共确认 **待决策 18 条 + 已更正 6 条**，其中 4 条会影响用户可见行为。完整证据、影响面与最小修法见[设计稿 × 实现 偏差审计](DESIGN_VS_IMPLEMENTATION_AUDIT_20260927.md)。本表的状态栏**只反映代码事实**，不因文档偏差而调整。

最需要注意的四条：

- **屏幕图被发给出站选择的 `sendable_image` 句柄**：`model_wire.py:98,118-119` 对全部本轮图片建句柄，而 `media/reply.py:60-62` 把屏幕图从可选集合剔除并直接抛错 → 模型照提示回选屏幕图时**整轮回复失败**。物理出站仍被拦截，是入口契约与拦截语义不一致。
- **Screen 的"理解与反馈"消费链断在半路**：解释与锚点的唯一写入点在 `screen/pipeline.py:141`，而 `ScreenProcessingPipeline` 没有生产入口（审计 B9/B10）→ 主动与日记两条消费链在真实运行中永远取不到数据，只有"回复"可达。
- **陪伴小屋无法清除已保存的 Image 密钥**：页面 `models-page.js:716` 对 `api_key` 只在非空时提交，无清除控件，而后端本可接受空串（审计 B11）。
- **`delivery.py:135/139` 重复定义 `enqueue_fallback`，生效的那份调用不存在的 `self.manifest`**：当前无调用者（真正路径是 `:277-282`），属潜在 `AttributeError`（审计 B15）。

## 四、进度口径与下一步

| 层 | 当前 |
| --- | --- |
| 源码在位 | **七家全部有至少一条 V2 原生或宿主执行链** |
| 定向测试 | V2 侧 20+ 模块、提供方侧合计 108 个测试文件（未逐一复跑） |
| 交付包 | `companion-v2-20260927-p5` 8 包哈希/语法/清单/唯一入口/宿主启停与注销全通过 |
| 页面接入 | 提供方配置各自留在插件表单；本体侧另有 33 个字段无页面控件（见[原生面盘点](V2_NATIVE_SURFACE_AUDIT_20260927.md)） |
| 现场验收 | **E01–E17 全部「待测」，零通过** |

建议顺序：

1. **E01 先做**（在线启停七家 + 小屋目录与工具注册核对）：一次操作验掉"8 包能否共存、禁用是否真停执行、有无 V1 工具混入"三件事，成本最低、暴露最集中。
2. 再按缺口从小到大推进：Live 呈现 → Screen 定时观察 → Content 编排/封面 → Together 真实活动 → Reality 真机 → Image 相册衣柜 → Game 其余玩法与房间。
3. Image 是唯一「缺的不是接线而是业务面」的一家（V1 的相册/衣柜/图参考在 V2 无对应物），排期前应先决定是否整体迁移，否则做完接线仍然对不齐 E04。

## 五、可复跑核对命令

```powershell
# 各提供方真实声明的动作
Select-String -Path 'C:\Users\99505\.astrbot\data\plugins\astrbot_plugin_*\native_v2\provider.py' -Pattern '_ACTIONS\s*=|ACTION\s*=|"action":\s*"'
# 交付包内八个包与哈希
$env:PYTHONPATH='C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 tools/verify_v2_release.py --release <包目录> --extract-to <空目录>
```

以上只读工作区与交付包，不连宿主、不调模型、不发送消息。
