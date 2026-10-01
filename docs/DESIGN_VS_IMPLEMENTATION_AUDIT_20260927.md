# 设计稿 × 实现 偏差审计（提供方与原生合同，2026-09-27）

对象：七个可选提供方的相关设计稿，以及 V2 原生提供方总合同这一组文档。方法：逐字读设计稿 → 提取可验证声明 → 在读代码里找对应实现 → 三值判定（**一致 / 偏差 / 设计稿未实现**）。每条结论必须带 `文件:行号`。

分工：四路并行只读审计（原生总合同 / Content+Image / Reality+Together+Screen / Game+Live）+ 本人独立复核关键条目，并复跑文档里引用的命令。**本文只做记录与更正，不改业务代码。**

结果分布：**已更正 6 条**（文档侧，本轮已改）、**待决策 18 条**（B0a–B16；其中 B0a–B0d 会影响用户可见行为、B9/B10 是"设计稿未实现"、B15/B16 是顺带发现的代码缺陷）、**文档缺口 3 条**、**只读不可判定 7 类**。

复跑口径：所有结论仅来自代码与文件结构；文档自评（"已完成/已接通"）不作为证据；测试计数与真实平台效果一律不判定。

## 一、已更正的偏差（本轮已改文档）

| # | 偏差 | 证据 | 影响 | 处理 |
| --- | --- | --- | --- | --- |
| A1 | 情绪设计稿把单轮允许区间写成 `[回落值 ± max_delta]`，实际还叠加"向基线一侧不得越过 `baseline ± max_delta`" | `companion_v2/role_work/state/mood/models.py` 的 `bounds()`；实测同参数下文档公式给 `[6.381, 10.381]`、代码给 `[6.381, 10]` | 读文档实现会放宽一档 | 已按实测改写[情绪设计稿](CORE_ROLE_MOOD_DYNAMICS_DESIGN_20260925.md)第 3.3 节 |
| A2 | **象棋是第五种玩法且已全面接线，权威稿只写四种** | 提供方 `native_v2/provider.py:48-51,55-61,380-404`（`game.xiangqi.*` + `native_v2_xiangqi_enabled`）；本体 `memory/game_ingestion.py:19-20`、`host/application.py:306-309`；`tests/test_game_memory_ingestion.py:121-141` | 验收 E13 按"四种"写会漏一项能力；记忆生产器实际消费**三种棋类** | 已在[权威稿](GAME_LIVE_NATIVE_20260926.md)与[对照表](COMPANION_PROVIDER_STATUS_20260927.md)加复核补记 |
| A3 | 状态稿动作数写 21，且同文逐项枚举自身合计 22 | 提供方 `native_v2/provider.py` 常量实测：`game.` 前缀 23 个，去掉 `PROVIDER_ID` = **22**（4+4+4+5+5） | 交付与验收对账基准错一位 | 已改为 22 个（五种玩法） |
| A4 | 协调稿称"Together、Game、Screen、Reality、Live 原生执行尚未完成" | `tools/build_v2_release.py:30-34` 已为五家登记 `native_v2/provider.py`；五家各有原生测试 | 排期读者低估进度 | 已在[协调稿](NATIVE_REFACTOR_COORDINATION_20260925.md)加复核补记 |
| A5 | 依赖审计称"Content 尚未接入 main.py、V2 宿主消费者"，且与 `CORE_NATIVE_GAP_CLOSURE_20260925.md` 自相矛盾 | `astrbot_plugin_content_companion/main.py:116`；`astrbot_host/native_extensions/content.py`；`companion_v2/conversation/content/access.py` | 误判 Content 消费端缺失 | 已在[依赖审计](NATIVE_REFACTOR_DEPENDENCY_AUDIT_20260925.md)加复核补记 |
| A6 | 依赖审计引用的 `integration_registry.py:53` 与 `external_tools.py:79` 行号漂移 | 实际 `integration_registry.py:56`、`external_tools.py:89` | 仅溯源定位 | 已更正行号 |

## 二、待决策偏差（未改代码，代码属其他窗口的在建面）

### 行为级（会影响用户可见结果，建议优先定）

| # | 偏差 | 证据 | 影响面 | 建议 |
| --- | --- | --- | --- | --- |
| B0a | **屏幕图被发给出站选择的 `sendable_image` 句柄** | `adapters/astrbot/model_wire.py:98` 对**全部** `request.images` 建有句柄、`:118-119` 逐张写 `sendable_image`；而 `conversation/media/reply.py:60` 把 `owner=="screen"` 从可选集合剔除、`:61-62` 直接抛 `reply_images_unavailable` | 触发条件窄（同一轮既有入站图片、又发起识屏、模型按提示回选屏幕图），后果是**整轮回复生成失败**（`conversation/generation.py:156`），而不是静默丢弃该图 | 二选一：`model_wire.py` 只对 `original.source.owner != "screen"` 写句柄；或让 `reply.select` 忽略屏幕引用而不报错 |
| B0b | **Screen 对"设备调用前被拒"记 unknown 而非未提交** | 提供方 `native_v2/provider.py:158-175` 把宿主 `before_dispatch()` 放在 try 内，任何异常 → `unknown/unknown`；设备确实未采集（采集在 `:159-160` 之后） | 撤销授权后"立即拒绝"成立，但账本记为"可能已执行"，妨碍用户与诊断判断"这次到底有没有截屏"；同位置 Reality/Together 都落 `failed/not_committed` | 单独捕获 `before_dispatch()` 异常返回 `failed`，只在采集开始后使用 unknown |
| B0c | **`work` 模式可能被静默降级，回执仍报 `work`** | 提供方 `main.py:1921-1932` 在 Screen 工作协同不可用时把 `work` 改成 `call`（判定 `:1320-1322`）；而 create 回执的 `mode` 取自票据（`provider.py:419-422`） | V2 被告知建成 work 房间、实际按通话运行；`together.room.snapshot` 又会回报 `mode:"call"`，同一批数据自相矛盾 | 对 `ticket.native_v2 is not None` 的房间豁免该降级，或在 create 阶段直接拒绝 work |
| B0d | **操作日志损坏会连带关闭无关的 V1 功能** | `OperationStore._load` 抛错（Reality `provider.py:113-125`、Together `:115-127`），而 `main.py` 构造处**未捕获**（Reality `:636-639`、Together `:449-457`） | 与设计稿"停止加载提供方"的范围不符：Together 的房间服务后台任务不会启动，V1 房间功能随之中断；Screen 则捕获并降级 | 按 Screen 的做法 try/except 记告警后继续初始化其余部分 |

### 契约与结构级

| # | 偏差 | 证据 | 影响面 | 建议 |
| --- | --- | --- | --- | --- |
| B1 | 合同声明端口提供 `lookup()`，但 V2 生产代码**零调用** | 生产只用 `execute` 与 `read_artifact`（`astrbot_host/native_extensions/__init__.py:192,197,211`）；`.lookup(` 命中全部在测试 | "崩溃后按原幂等键补读回执"的恢复路径在本体不存在 | 二选一：在合同里写明"本体不调用 lookup，仅提供方与独立验收使用"，或加一个不参与重试决策的只读桥接 |
| B2 | `NativeExtensionRegistry.executor()` 是死代码 | 定义于 `astrbot_host/native_extensions/__init__.py:279-280`，全仓无调用；真实路径是 `adapters/astrbot/application.py:27-33` | 无运行时影响，但易被误当作装配入口 | 删除或加 docstring 标注已被取代 |
| B3 | `execution_integrated` 恒为 `False`，且被测试冻结 | `astrbot_host/integration_registry.py:56` 唯一赋值点，全仓无置 `True`；`tests/test_product_integration.py:42` 断言为 False | 只看集成清单/页面的读者会一律看到"未接入执行"，与"Image/Content 已原生接入"的事实矛盾 | 若保留该字段，改由注册表声明推导；否则删除并同步测试 |
| B4 | 聚合声明超 64 时**清空全部原生声明** | `astrbot_host/native_extensions/discovery.py:113-115` 把 `entries` 整体清空并记 `native_catalog_capacity`；`tests/test_native_tool_catalog.py:63-74` 已把"无部分目录"固化为预期 | 提供方增多后一次超限即全部原生能力消失，失败粒度比模型目录更粗 | 保持"不截断"语义的前提下，把容量判定移交给模型目录的按上下文筛选；或发现期只报 issue 不清空 |
| B5 | 合同"其余端口按能力实现"缺发现期校验 | `discovery.py:54-55` 只强制 `execute` 是协程；`read_artifact`/`lookup` 缺失时降级为 `native_adoption_unavailable` 的撤销来源（`__init__.py:243-246`） | 提供方漏实现时表现为"产物不可用"而非装配期报错 | 在发现期对声明的能力做一次端口存在性检查 |
| B6 | Game 参数不校验 `game_id` 长度 | 提供方 `native_v2/provider.py:448-450,456-461` 只校验类型；Live 有上限（`session_id ≤ 64`、`after_event_id ≤ 160`） | 低：受宿主 64 KiB 文档预算约束，超长只会查不到对局 | 补 `1 <= len(game_id) <= 128`，或在权威稿注明 Game 侧不设上限 |
| B7 | Live 两个平台子开关默认 `true` | 提供方 `_conf_schema.json:33-42`、`main.py:279-280`、`native_v2/provider.py:35-37` 的 `True` 兜底 | 与跨提供方合同"新增能力默认关闭"的口径有出入；总开关默认 false 仍兜住不暴露 | 权威稿写明子开关默认为 true；或改默认值与合同对齐 |
| B8 | Reality 设备目录多出两个未声明字段 | `mihome_web_api.py:497-498` 额外返回 `cache_updated_at` 与 `logged_in`（账号是否已登录），该 payload 整份进入模型上下文；凭证/DID/型号/设备原名确实未下发 | 低；但 `logged_in` 可被读作声明中排除的"登录信息" | 去掉这两个字段，或把它们补进设计稿的字段枚举 |

### 设计稿未实现（需要决定"补装配"还是"改文档"）

| # | 声明 | 证据 | 现状 |
| --- | --- | --- | --- |
| B9 | Screen 切片声称"接 V2 模型网关和现有 `ScreenProcessingPipeline`，用受控设备完成截图→原件→解释→采用验收" | `ScreenProcessingPipeline`/`ScreenCaptureService` 只出现在 `companion_v2/screen/__init__.py` 与 `tests/`，**无生产调用点**；真实链路走提供方 `native_v2/provider.py` + `host/native_extensions/screens.py` + `conversation/media/screen.py` | 两条并行实现，文档描述的那条未被使用 |
| B10 | G6 声称"Screen 理解与反馈"可被留意/回复/主动/日记/沉默消费 | 解释与锚点的唯一写入点是 `screen/repositories.py:303-322`，唯一调用者是 `screen/pipeline.py:141`（即 B9 里那条没有生产入口的链）；消费方已接线（主动 `proactive/screen_events.py:108-116`、日记 `screen/journal_materials.py:40`） | 主动与日记两条链路在真实运行中**永远取不到数据**，只有"回复"可达 |

### Content / Image（第三路审计）

| # | 偏差 | 证据 | 影响面 | 建议 |
| --- | --- | --- | --- | --- |
| B11 | **陪伴小屋无法清除已保存的 Image 密钥**（文档称"留空保留，勾选清除才删除"） | 页面 `pages/陪伴小屋/models-page.js:716` 对 `api_key` 只在非空时提交，无清除控件（V1 面板 `native-image.js:160,383-384` 有复选框）；后端本可接受空串（`image_native_configuration.py:61-62`） | 中：管理员无法从唯一公开页面清除已存的 SD/ComfyUI 密钥 | 补"清除已保存的密钥"复选框，勾选时提交 `api_key:""` |
| B12 | 生图额度的日界时区与 `date_context` 不同源 | 配额用 `conversation/media/quota.py:48,107-112` 的 `messages.timezone_name`，生产装配从不传参（`messages.py:114` 默认值）；`date_context` 用可配置的 `calendar_timezone`（`messages.py:432`、`perception_settings.py:15`） | 低：非默认时区下配额零点与角色当地日错位 | 两者共用同一时区解析 |
| B13 | `image.edit` 的 provider generation 检查是自反比较、恒真 | 同一份 metadata 的 `provider_generation` 被传回再自比（`adapter.py:149-152` → `owner.py:133`）；真正的交叉校验只有 `store.py:153-155` 的回执校验 | 低：无越权，仅声明不实 | 期望值改取 operation 行 |
| B14 | Content 宿主切片文档的 `resolved_target.contributor` 示例形状失真 | 文档写 `{installation_id, kind:"bot", subject_id}`，本体实际发 `{"kind":"role_output","role":…,"requested_by":…}`（`conversation/content/access.py:94-96`） | 低：Content 不校验其内部字段，无运行时影响 | 更正示例 |

Content 侧另有 26 项声明核为一致，含撤回传播（锚点 revoke → `sources/dependencies.py:120-136` 递归 → 续答/投递前 `validate_reference` 全失败）、CAS/幂等、私聊专属受众、`enabled=false` 不开库。

Image 侧"同源编辑确实通了"，缺失分别是：入站/跨来源缺宿主受权资源合同装配（`types.py:53-68` 已能承载，但 `adapter.py:147-152` 只从自有 store 取图）、多参考被 `types.py:109-110` 的"恰好一个引用"硬约束挡住、蒙版在参数白名单（`adapter.py:91-93`）与 `backends.py:100-105` 被显式拒绝。

## 二之二、顺带发现的代码缺陷（非设计稿声明，已复核）

| # | 缺陷 | 证据 | 现状 |
| --- | --- | --- | --- |
| B15 | `LocalConversationDelivery.enqueue_fallback` **重复定义**，且生效的那份调用不存在的方法 | `conversation/delivery.py:135` 与 `:139` 同名定义（后者覆盖前者）；生效版 `:141` 调 `self.manifest(part)`，而全仓无 `manifest` 方法定义 | **当前无调用者**（全仓仅这两处定义，`grep enqueue_fallback` 无调用点），真正生效路径是 `delivery.py:277-282` 走 `image_fallback.enqueue`，故暂不触发故障；一旦有人调用即 `AttributeError` |
| B16 | `media/review.py` 重复定义 `review_key`（两份相同，无行为影响） | `conversation/media/review.py:338-346` | 清理项 |
| B17 | 群图审核的模型档**键名与任务种类不一致**，生产调用会以 `model_task_unregistered` 失败 | `conversation/media/review_service.py:30`（`KIND = "conversation.image_review"`）与 `:33`（`PROFILE_KIND = "image_review"`）；`ModelRouter.resolve` 按 `task.spec.kind` 取档（`model_gateway/routing.py:74`），`astrbot_host/multi_session.py:205` 只登记了 `image_review` 档 | 2026-09-27 第十二轮发现（在为识屏解读新增同构模型档时对照）：`tests/test_group_image_review.py` 只覆盖配置字段，未覆盖真实网关调用，因此该缺口此前未被测试捕获。修法二选一：把 `PROFILE_KIND` 改成任务种类（配置组随之变为 `model.conversation.image_review.*`，需处理既有 `model.image_review.*` 值），或给 `resolve` 增加显式档别名并在装配处登记 |

## 三、文档缺口

| # | 缺口 | 证据 |
| --- | --- | --- |
| C1 | **Live 提供方仓库没有任何 V2 原生端口记录**：`README.md`/`CHANGELOG.md` 全文无 `native_v2` 字样 | 用户从插件文档看不到只读承诺、三个开关与 `cursor_reset` 契约 |
| C2 | Game 提供方 `README.md` 的原生章节滞后（仍写"其他三种游戏尚未进入 V2 原生链"） | 与 A2 同因 |
| C3 | Reality / Together 提供方仓库同样无 V2 原生设计稿（V2 侧另有协调稿） | 见[对照表](COMPANION_PROVIDER_STATUS_20260927.md)第三节 |

## 四、只读条件下**无法判定**的声明（不得当作已验证）

1. 文档自报的一切测试计数与通过结论（39/21/11/3/4、19 项、74/26 项、22/65/123/38/43/49 项等）——本轮不跑测试。
2. 真实外部效果：SD/ComfyUI 生图、真实 QQ/OneBot 发送与授权记录、真实 B 站/Twitch 直播、真实米家设备、真实房间服务器、真实桌面截图环境、Pikafish 引擎真机。
3. 快照哈希与冻结关系（V2 600 文件 / Image 19 文件 inventory、`generated.py` 与 `external_tools.py` 的 SHA-256）。
4. 提供方 `generation` 跨重启稳定性——本体只把它当不透明串（`companion_v2/capabilities/native.py:61-62`），测试夹具传固定值，单元测试层面无法体现该语义。
5. `untrusted_public_input` 是否真能阻止模型把弹幕当指令——该标记在本体**无任何消费方**（grep 零命中），只剩能力说明与结果标记两层软约束。
6. 同数据根多进程/多实例的原子性（Game 用进程内锁）。
7. AstrBot 实际加载时 `star.version` 的取值来源与格式（宿主用它校验 manifest 版本）。

## 五、次要观察（不计偏差，供后续改动避坑）

- Game 的 `CLOSE` 动作绕过各自玩法开关（`native_v2/provider.py:492-493,624`）；经宿主不可达（关闭后工具不在 manifest，宿主缺 entry 即拒），属纵深防御缺口。
- 象棋开关打开但引擎缺失时仍声明 4 个 action，调用必失败（`:380-404` vs `:617-621`）。
- Live 版本号在 `main.py:406` 硬编码 `"1.8.1"`，与 metadata 一致但无校验；只改 metadata 会让整个 Live 提供方被判 `native_declaration_invalid` 并静默消失。
- `companion_v2/games/` 是同一批规则的第二份实现（4 种、无象棋），生产零导入、仅测试使用；存在未来误用与漂移风险。
- `tests/test_astrbot_multi_live_acceptance.py` 是 multi-target 宿主验收，与 Live 提供方**无关**；把两者并列会高估 Live 覆盖率。
- Game 的旧主动邀请仍会注册（`main.py:671` 走 V1 `register_proactive_ability`）；"开启原生开关"不等于插件只跑原生链。
- Live 事件数据类含 `raw`/`user_id`/`amount`，提供方只取 5 字段，越界字段不外泄（正面确认，记录以免后续改动误取）。
