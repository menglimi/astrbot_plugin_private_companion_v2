# 七个可选伴侣的 V2 原生重构依赖审计

日期：2026-09-25。范围：Content、Image、Together、Game、Screen、Reality、Live 的本地源码和 V2 装配。本文保留本批实施前的静态依赖审计，并记录本批收尾进度。最初审计阶段只读源码，没有导入或启动插件、读取运行数据或 V1 用户资料；后续实现与合成验证分别记录如下。目录发现、独立领域实现和完整宿主执行链按各自证据计入进度。

> **当前结论（2026-10-11）**：七项能力已经迁入 V2 内部 native extension。本文后续的“提供方尚未原生化”“保留各自插件身份”等表述属于实施前审计记录；当前旧伴侣插件只可作为迁移或外部兼容状态来源，不是 V2 运行依赖，也不提供 V2 的执行入口。

## 本批收尾进度

| 提供方 | 当前已实现 | 收尾或下一步 |
| --- | --- | --- |
| Image | 独立原生 owner、统一 provider registry，以及 V2 私聊/群聊生成、编辑、产物采用和投递链已实现；额度与撤权回执补验、最终私聊/群聊 10 项及无 V1 隔离复验均通过 | 下一步补入站/跨来源编辑资源合同与真实后端/QQ 现场验收。详见 [V2 原生 Image 生成、采用与投递](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/docs/CORE_NATIVE_IMAGE_DELIVERY_20260925.md) |
| Content | 独立作品领域、存储、不可变版本操作和统一原生协议 adapter 已完成；提交后撤权/取消保留控制回执，最终 60 项合成专项通过 | 尚未接入 Content `main.py`、V2 宿主消费者和来源撤回传播；详见 [Content 独立实现记录](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/docs/CONTENT_NATIVE_SLICE_20260925.md) |
| Screen、Game、Together、Reality、Live | 本批完成旧入口依赖盘点与首片划分 | 五个提供方尚未原生化，仍需按下方依赖与验收目标逐个实施 |

Image 的当前完成范围是源码与合成宿主链路，真实后端和 QQ 客户端效果另行现场验收。Content 的 60 项证明独立领域和协议适配器成立，尚不能证明已加载插件的作品执行与本体派生来源撤回成立。本文保留的旧入口证据用于解释新路径必须绕开的依赖；本批新增原生代码的状态以上表及各自实施记录为准。

> **2026-09-27 复核补记（只更正事实，不改历史结论）**：上表 Content 行的「尚未接入 Content `main.py`、V2 宿主消费者」与「Screen、Game、Together、Reality、Live 五个提供方尚未原生化」两处已过时——`astrbot_plugin_content_companion/main.py:116` 已有 `companion_v2_native()`，`astrbot_host/native_extensions/content.py` 与 `companion_v2/conversation/content/access.py` 已实现宿主消费者；五家也已在 `tools/build_v2_release.py:30-34` 登记 `native_v2/provider.py`。当前真实缺口是**深度不一**而非「未原生化」，逐家动作清单与缺口见[七个可选伴侣对照表](COMPANION_PROVIDER_STATUS_20260927.md)。另本文 `external_tools.py:79` 的行号锚点已漂移到 `:89`（`ExtensionToolDescriptor`）。

> **2026-09-27 复核补记（只更正事实，不改历史结论）**：上表 Content 行的「尚未接入 Content `main.py`、V2 宿主消费者和来源撤回传播」与「Screen、Game、Together、Reality、Live 五个提供方尚未原生化」两处已过时，且与本仓库 `CORE_NATIVE_GAP_CLOSURE_20260925.md` 自相矛盾——`astrbot_plugin_content_companion/main.py:116` 已有 `companion_v2_native()`，`astrbot_host/native_extensions/content.py` 与 `companion_v2/conversation/content/access.py` 已实现宿主消费者；五家已在 `tools/build_v2_release.py:30-34` 登记 `native_v2/provider.py` 并有各自原生测试。当前真实缺口是**深度不一**而非「未原生化」，逐家动作清单见[七个可选伴侣对照表](COMPANION_PROVIDER_STATUS_20260927.md)。另本文 `external_tools.py:79` 的行号锚点已漂移到 `:89`（`ExtensionToolDescriptor`）。


本批实施前，V2 已有外部工具的持久子任务、能力包、可信来源与提供方绑定合同，七个可选伴侣当时只接了状态目录。该状态目录调用 `companion_v2_status`，并设置 `execution_integrated=False`：`astrbot_host/integration_registry.py:56`（2026-09-27 复核修正行号，原文写 :53）。这是原静态盘点的证据；Image 本批另建的原生 owner、registry 与执行链不以该旧目录字段判定完成。

“V2 原生”应按执行归属验收：V2 解析可信身份、目标、角色和授权，持久记录原任务、输入来源、产物采用与发送回执；能力提供方负责明确的后端或设备动作。停用 V1 后这条链必须独立成立。七个提供方保留各自插件身份，V2 本体保持 `astrbot_plugin_private_companion_v2`；不为领域功能另注册第二个本体，不重建已经统一的页面入口。

下表及后续七个提供方章节均为**本批实施前的旧入口基线与首片目标**。其中 Image、Content 的缺口已经分别推进到上方所列阶段，不能将原基线表当作收尾时的全量待办。

| 提供方 | 实施前可复用部分 | 实施前主要缺口 | 首片优先级 |
| --- | --- | --- | --- |
| Image | 已有不直接依赖 V1 的预编译计划、后端通信、持久执行与对账模块 | 旧入口仍依赖 V1；原生执行器默认共用既有任务库；V2 采用/发送链待绑定 | P0，本轮主线 |
| Content | 创作提示和项目算法；有界作品读取与 revision | 默认迁移旧资料、读取旧配置；QQ 空间仍委托 V1 页面 API；模型与项目状态未归 V2 | P1，可与 Image 并行 |
| Screen | 本机采集、远端收图、视频拆装；V2 已有本地原件处理链 | 未发现直接 V1 核心导入，但自有模型、日记、长期记忆与主动调度仍独立；跨设备/角色归属未绑定 | P1，可独立推进 |
| Game | 棋类/纸牌规则与房间状态机 | 生活、记忆、主动邀请仍接旧接口；QQ 身份和内存房间未映射 V2 scope/角色/恢复 | P2 |
| Together | 小说解析、章节与进度、房间消息结构、媒体传输 | 场景/语音/连续对话依赖 V1；长期记忆接旧桥；房间授权和模型调用独立 | P2，与 Game 共用活动合同后各自落地 |
| Reality | 米家通信、单帧采集、音频处理、移动端协议；已有快照依赖追踪 | 默认迁移 V1；标为 native 的快照 owner 仍强制绑定 V1 实例与 `legacy_user_id` | P2，先只读快照 |
| Live | B 站/Twitch 事件客户端、VTS 通信、字幕与参数调度 | 直接调用 V1 内部方法、写 V1 `data`，主动开播/停止注册旧调度；记忆并接多套旧提供方 | P3，先事件输入 |

优先级表示依赖顺序，不表示后面的能力可以跳过，也不代表其他任务已承诺接单。每个首片都应形成可以单独验证的端到端结果，再扩展该提供方的其余能力。

## 旧入口基线：Image 执行算法与运行实例

已有模块需要分别判断，不能把文件名中的 `native` 当作 V2 验收结论。

| 模块 | 实际证据 | 复用决定 |
| --- | --- | --- |
| `image_native_client.py` | [NativeClient](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_native_client.py:20) 接收 backend/config/directory，使用 aiohttp 和本插件的 ComfyUI/workflow/图片检查；直接依赖链未发现 V1 核心导入。[提交](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_native_client.py:98)、poll、下载、取消及 SD generate/edit 都有独立方法 | 可保留为后端通信实现。向它传入冻结参数、明确引用字节和新工作目录；不调用旧 runtime 的提示重写、回退或自动分享链 |
| `image_native_plan.py`、`image_preparation.py` | [配置读取](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_native_plan.py:21) 和 [端点快照](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_native_plan.py:57) 只要求 plugin-like config/data_dir；[预备服务](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_preparation.py:119) 通过可信 host ports 工作 | 计划编译、profile、引用位置、冻结指纹可复用。V2 负责输入来源、角色实体、配置版本和授权票据，不用旧 owner.data 补上下文 |
| `image_management_preparation.py` | [ManagementAuthority](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_management_preparation.py:23) 提供 authorize/resolve_reference/check_current；[binding](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_management_preparation.py:38) 不比较 V1 插件身份；[公开装配入口](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/main.py:166) 可注入 authority | 是可承接 V2 的窄合同，属于宿主绑定，不是已经接入 V2。V2 需要实现自己的 authority 和引用字节读取，并固定绑定 generation/lifecycle |
| `image_native_execution.py` | [执行器](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_native_execution.py:21) 本身未导入 V1；[start](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_native_execution.py:82) 固定原 preparation，[引用读取](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_native_execution.py:202) 核对 SHA-256，[reconcile](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_native_execution.py:328) 对账已存在任务，不自动再次提交 | 可以复用执行算法或作为提供方内的持久子操作，不必一概只留 transport；必须满足下述命名空间、身份和采用边界。它不能替代 V2 原任务、来源与投递账本 |
| `image_operations.py`、`image_edit_region.py` | [操作库](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_operations.py:38) 持久化 jobs/parts/deliveries；[begin](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_operations.py:85) 校验幂等 key 与冻结指纹；[区域编辑](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_edit_region.py:31) 处理后端输入和输出合成 | 原子落盘、字节验证、区域合成可保留。采用结果仍需形成 V2 的独立来源与版本；不能只把本地路径塞入对话 |

实施前识别出完整复用执行器必须解决的四个具体问题：

1. **新存储命名空间。** [main.py:197](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/main.py:197) 返回插件级 `_native_execution` 单例；它默认打开 `plugin.data_dir/native_image_operations`。[操作库构造](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_operations.py:63) 会立即更新旧 generation 的未完成任务和 sending 回执。因此不能直接拿在线旧实例或旧 data_dir 做 V2 初始化；需要新目录、独立 binding/执行器生命周期，且不复制旧任务、引用和产物。
2. **可信身份完整映射。** [执行访问](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_native_execution.py:46) 要求 `owner_key/persona_key/manage_all`，而库只以 `owner + idempotency_key` 去重。V2 adapter 必须从可信 TaskContext 派生安装、账号、角色、主体和作用域；不能把 QQ 号或模型提交的 owner 当授权。`scope_key/authority_revision` 由 [binding.authorize](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_management_preparation.py:84) 映射，引用通过当前 V2 Sources 复核。
3. **一条可恢复的调用链。** V2 任务 ID、提供方 generation、冻结计划指纹与 provider operation ID 必须持久关联；崩溃后按原幂等 key 查询原操作。[lookup_execution](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_native_execution.py:130) 已支持寻找调用方尚未来得及保存 ID 的原操作；没有后端 locator 的 unknown 不升级为可重试。
4. **产物采用与发送分开落账。** [read](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_native_execution.py:152) 会复核原输入和字节，适合转为受治理的 V2 产物；[deliver](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/image_native_execution.py:162) 是旧 callback/audience 字符串合同，不能据它认定已满足 V2 群受众、图文指纹与 ACK。发送沿用 V2 已验收的 delivery，避免两个组件同时发送。

旧入口仍不能用作 V2 主链：[execute_task](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/main.py:317) 转到 `generate_for_companion`；后者 [先检查 V1](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/main.py:616)。[retained_media](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/main.py:364) 要求 owner 等于 V1 API 的 `_plugin`。初始化 [默认重用旧设置与资产](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/main.py:685)，[image_data_for](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/main.py:980) 会从 owner.data 拷贝图像上下文。V2 链应完全绕开这些方法。

**实施前首片验收目标：** 在新目录中完成一个固定路线的 generate 和一个有明确原件的 edit，经 V2 子任务执行、保存字节与 lineage、角色采用、现有私聊/群聊授权发送及重启查账。专项至少覆盖 V1 API 不存在、跨账号/角色引用拒绝、提交前撤权、提交后 unknown 不重发、有 locator 的对账、产物篡改/失效、ACK 前后重启；使用本地后端替身与合成图片，不发送真实 QQ。本批已实现的链路和待补验项目见开头的 Image 收尾进度。

## 旧入口基线：Content 作品算法、宿主与资料入口

可保留 [CreativeMixin 的项目生成](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/creative.py:617)、[片段生成](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/creative.py:1175)、审核和手动修订的提示及纯转换逻辑。它们调用宿主方法，不能整体视为纯后端。`companion/story_read.py` 的 [有界目录](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/companion/story_read.py:58) 和 [版本固定的原文读取](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/companion/story_read.py:98) 可作为读取算法；当前结果明确标为 `legacy_projection`，不等于 V2 新作品仓库。

必须解除的耦合：

- [StandaloneCreativeHost.__init__](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/main.py:260) 构造时即加载本地状态并调用迁移；[_migrate_legacy_state](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/main.py:312) 会读取旧核心 `companions.json`，[_legacy_config](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/main.py:326) 读取 V1 配置。开关 [默认 True](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/main.py:516)，不能用“V1 当前停用”代替删除新路径上的迁移依赖。
- [状态和命令](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/main.py:119) 仍把 V1 可用作为运行条件；[模型调用](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/main.py:363) 直接调用 AstrBot `llm_generate`，绕过 V2 TaskContext、预算和统一模型回执。
- [QQ 空间操作](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/main.py:716) 直接委托 V1 `page_api`，当前 Content 不是独立 QQ 空间后端；[封面可用性](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion/main.py:434) 还调用 Image 的旧 capability_status。

**实施前首片验收目标：** 从 V2 授权输入创建一个新作品项目，生成并采用第一段，修改后按原 revision 分页读取；V2 模型网关、来源、scope 和操作 ID 全链一致，重启不重写同一段。不启动旧迁移，不引用旧项目。封面随后接 Image 新产物；QQ 空间发布作为独立外部动作后续拆出，不纳入首片“已完成”。本批已经完成独立作品领域和统一协议 adapter；完整宿主消费与来源撤回链仍按开头所列范围接入。

## 旧入口基线：Screen 的独立执行体系

对 `main.py`、`core/`、`remote_client.py` 的直接字符串与导入检查未发现 `astrbot_plugin_private_companion` 或旧 memory bridge；不能把其他六个伴侣的 V1 依赖结论套用到它。可保留 [本机截图](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_screen_companion/remote_client.py:96)、[RemoteScreenReceiver](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_screen_companion/core/remote_receiver.py:23) 的有界收图/视频组装协议，并把 SDK 日志和平台依赖留在提供方或宿主层。

这里需要统一的是身份、来源和运行职责：

- [远端缓存](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_screen_companion/core/remote_receiver.py:31) 只有全局 latest image/window/meta，token 验证不能代替 V2 安装/账号/角色/设备来源绑定；[工作上下文接口](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_screen_companion/main.py:157) 明确不使用传入的 user_id 作为状态归属。
- [启动流程](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_screen_companion/main.py:973) 自己启动 scheduler、日记、自定义任务、活动追踪和窗口陪伴；[memory](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_screen_companion/core/memory.py:300) 自己保存日记与长期记忆；[识屏模型调用](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_screen_companion/core/media.py:4236) 也直接进入 provider。把整个主类挂在 V2 下会保留两套调度与记忆。
- V2 已有 [ScreenProcessingPipeline](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/screen/pipeline.py:49)：带原件 coverage、可信身份、操作去重和当前授权复核。应补真实采集端口，不重写已存在的领域所有权。

**首个可验收切片：** 一次显式授权采集，通过提供方返回合成截图/真实采集端口的同一合同，保存为 V2 Screen 原件，再由统一模型网关解释并采用。覆盖设备和角色切换、过期截图、采集期间撤权、提供方重启、重复操作只读取原结果。自动识屏、日记和主动发言随后接 V2 的原生调度，首片不启动旧后台循环。

## 旧入口基线：Game 规则、作用域与持久边界

[GomokuGame](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_game_companion/gomoku.py:29)、[TicTacToeGame](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_game_companion/tictactoe.py:26) 等规则引擎没有 V1 宿主依赖；[RoomManager](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_game_companion/room_manager.py:64) 注入 event_callback，房间转换可以继续由 Game 管理。其 TrustedIdentityStore 的 token 摘要和有效期逻辑可参考，但 [身份只记录 QQ/name](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_game_companion/trusted_identity.py:17)，不是 V2 的绑定证明。

必须解除的耦合：[_private_companion_api](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_game_companion/main.py:2947) 提供生活场景；[外部活动通知](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_game_companion/main.py:2981)、[游戏余韵写入](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_game_companion/main.py:3051)、[主动邀请注册](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_game_companion/main.py:3153) 都接旧核心；[记忆](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_game_companion/main.py:2932) 依赖旧 MemoryCompanion。房间链接 [直接 context.send_message](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_game_companion/main.py:3299)，需要改为 V2 投递意图。[房间当前仅在内存](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_game_companion/room_manager.py:108)，[close_all](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_game_companion/room_manager.py:1909) 明确无持久恢复。

**首个可验收切片：** 由 V2 原请求创建一个井字棋房间，授权玩家落子，完成一局并保存结局原件；活动占用、结果采用与链接发送归 V2。重复创建不出第二房间，其他角色/群/账号不能接管，停机后有明确的已结束或可恢复状态，不能重新开局假装原局恢复。该片可复用纯规则，暂不引入模型型海龟汤或旧主动邀请。

## 旧入口基线：Together 房间、场景、记忆与模型 owner

可保留 [NovelLibrary](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/novel_library.py:141) 的新目录书籍解析、章节、原文及进度算法，以及 [RoomSession](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/models.py:76) 的播放事件结构和取消语义。[RoomTicketStore](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/models.py:32) 为内存 ticket，字段只有 mode/user_id/time；需要 V2 scope、角色、账号、provider generation 和持久操作关联，不能把它当现成统一授权。

必须解除的耦合：

- [场景](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/main.py:4587)、[Bot 身份](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/main.py:4610)、[共同活动](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/main.py:1719)、[实时连续上下文](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/main.py:1777) 都依赖 V1 API。
- [长期记忆桥](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/main.py:4011) 读 remember_you/MemoryCompanion；[共同经历](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/main.py:4356) 直接写旧桥，scope 固定 private。应改为 V2 的授权查询与带证据提议，而非把同一个 user_id 当所有房间的记忆主体。
- [模型调用](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/main.py:3861) 和用量独立管理；[TTS](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/main.py:5327) 可调用旧核心合成桥。V2 路径要走统一模型/语音任务。
- `BilibiliMediaResolver` 的网络解析可以拆用，但 [cookie 来源](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/media.py:401) 默认读取另一个插件配置，不能称为只依赖显式参数的纯 transport；需要显式凭据提供端口，不在审计或 V2 首片里读取它。

**首个可验收切片：** 在新数据根导入合成短篇，V2 授权同一角色与用户创建共读会话、读取一段、更新进度、生成一条回应并结束活动。原文版本/阅读进度/房间事件可查，重复事件不重复生成和记忆写入；撤权和角色切换阻断后续读取。观影下载、实时音视频、TTS 和 Live 联动按后续切片接入。

## 旧入口基线：Reality 的 native 快照 owner 与 V1 绑定

[MiHomeClient](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/mihome_client.py:111) 依赖显式 data_manager 和 mijiaAPI，可保留设备协议与结果解析；它带 AstrBot 日志和设备副作用，放在提供方/宿主侧。[单帧采集](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/reality_touch_camera.py:599) 使用 OpenCV 并在 finally 释放设备，可抽成独立 port；视觉分析随后交 V2 模型。音频重采样、设备枚举可同样迁用，旧唤醒/主动播放调度不应整体带入。

关键耦合证据：

- [initialize](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/main.py:555) 启动旧迁移循环，[_try_legacy_migration](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/main.py:756) 调用 V1 `export_reality_touch_legacy_state` 并拷贝 users/config；V2 路径必须使用全新的 owner/store，不触发此流程。
- [snapshot_owner](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/main.py:266) 名为 native RV-1，但 [MobileSnapshotOwner.bind](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/mobile_snapshot_owner.py:88) 强制 `host_api is gateway._private_companion_api()` 并调用 V1 `_get_reality_snapshot_access`。[请求解析](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/mobile_snapshot_owner.py:228) 再次比对旧实例，并读取 `claims['legacy_user_id']`。[会话授权](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/mobile_snapshot_owner.py:185) 仍读旧 `get_reality_touch_host_context`。
- [SnapshotDependencies](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/snapshot_dependencies.py:12) 的 generation、过期、撤销/确认机制值得保留；但上面的身份、epoch 和订阅提供方要重新绑定 V2，不能只改发现插件名。

**首个可验收切片：** 一个已绑定设备在临时目录上报合成 telemetry，V2 按原设备/主体/用途读取有时效的只读快照并采用为来源；设备换绑、撤销、generation 变化和过期均使旧引用失效。先验收只读上报，再接明确授权的单帧采集；米家控制、播放和闹钟各自拥有外部动作回执及 unknown 处理，不因成功读取快照就默认获准执行。

## 旧入口基线：Live 事件、表演与真实开播

可保留 [LiveDanmakuEvent](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_live_stream_companion/bilibili_live.py:81)、B 站客户端、[TwitchIrcClient](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_live_stream_companion/twitch_live.py:64) 的监听/事件归一化，以及 [VTSClient](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_live_stream_companion/vts_client.py:40)、字幕和参数发送端口。部分模块只依赖 SDK logger，属于提供方通信实现，不应放进 V2 核心包。

V1 耦合最深的部分在 main.py：[_private_companion_extension_api](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_live_stream_companion/main.py:878) 直接 import 旧核心，[开播/停止能力](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_live_stream_companion/main.py:889) 注册到 V1 主动框架；[_get_private_companion_plugin](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_live_stream_companion/main.py:3449) 取得旧内部实例；[直播状态 store](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_live_stream_companion/main.py:4692) 在其 data 中原位 setdefault；[事件](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_live_stream_companion/main.py:4710) 与 [小结](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_live_stream_companion/main.py:5408) 直接拿旧 `_data_lock` 并保存旧资料。这里需要新领域仓库与来源提议，不适合保留旧 writeback 回调。此外仍有 LivingMemory 和 Bilibili AI Bot 的独立记忆链，不能与 V2 同时重复写入同一经历。

**首个可验收切片：** 重放一段合成弹幕/礼物事件，通过提供方稳定事件 ID 进入 V2 独立直播会话，按直播平台/房间/账号/角色隔离，形成有界上下文和一次回应草稿；重复推送、乱序、断线续接和撤销均可核对。字幕/VTS 展示随后通过独立目标授权与回执接入；真实开播/停播、OBS 推流不属于该首片。

## 分工边界与共同验收

公共合同由本体整合方维护：[外部工具执行](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/conversation/external_tools.py:79) 已有固定 package/binding/source_owner 和 side_effect；[只读 provider registry](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/capabilities/read_providers.py:119) 已有 discovery/binding/lease。优先扩展现有合同所缺的端口，避免每个提供方各造一套权限、通用任务和来源系统。

| 责任 | 实施边界 | 可独立推进的产物 |
| --- | --- | --- |
| V2 整合 / Image 主线 | V2 原任务、生成与编辑产物、采用与投递；提供方绑定、状态声明 | Image 首片及跨账号/角色/群治理专项 |
| Content 领域 | 新作品 owner/版本/原文；创作模型调用改走 V2；解除初始化迁移 | 新作品首段生成、采用、修改、重启查账 |
| Screen 领域 | 采集 port、设备 binding、Screen 来源接线 | 单次截图→原件→处理→采用；不启动旧自有日记循环 |
| 活动领域（Game/Together） | 共用活动 ticket/event 生命周期，各自保留领域规则与内容仓库 | 单局井字棋与一次共读；旧记忆/主动桥移出新路径 |
| Reality / Live 提供方 | 报告明确的设备/直播事实与外部动作结果；不写本体内部 data | 只读 telemetry 与合成直播事件输入 |

领域实现继续按目录归属放在 `companion_v2/<领域>/`，AstrBot 注册、SDK 与跨插件装配放在 `astrbot_host/`；提供方内部也应按 transport/contracts/runtime 等职责收拢，不向 V2 或既有插件根目录再堆辅助脚本。现有小屋页面与注册整合由原任务处理，本文不改变其归属。

每个首片的完成证据必须同时包含：V1 核心/旧 memory bridge 不存在时可执行；临时独立数据根；可信主体/角色/账号/受众隔离；来源或授权撤销能阻断后续采用/动作；重复原请求可查原结果；提交后未知状态不会重放真实副作用；提供方换代/停机使旧 binding 失效。模型语言和表达调整优先使用提示词，身份、授权和真实副作用由程序执行合同保证。

以上依赖审计记录的是实施前的源码读取和分工依据，不是七个提供方的收尾验收。Image 与 Content 本批新增实现以开头所链实施记录为准；下方另记本次已经落盘的群聊 Image 接线。其他五个提供方仍按上述首片逐个实施，不能把基线表的“可复用”改写为“已完成”。

## 本次落地：群聊 Image 工具与原件历史

[群聊工具目录与回执分派](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/conversation/tool_loop.py) 在群记忆之外只提供当前授权的 `image.generate` / `image.edit`。结果仍由外部工具 owner 核对原子任务、提供方绑定、来源和原回执，不能经过群记忆校验器冒充本地结果。[执行入口](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/execution/service.py) 允许群前台扩展调用，[群宿主授权](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/astrbot_host/group_authority.py) 签发可撤销的工具调用权；提供方安装、角色启用与个人能力授权仍须分别满足，撤销可选工具权不会阻断普通群聊。

[群上下文补充](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/memory/group/tools.py) 与 [已确认历史](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/companion_v2/conversation/group_history.py) 根据每条工具记录的实际 owner 重读。生成图片即使只供角色参考、最终没有附图，其清单和图片资产仍是文字回复的依赖；撤销后原封存历史不可继续使用。

`GroupReplyHistory.source_evidence` 在原群成员、角色和来源授权下复核 sealed snapshot，返回引用及哈希供生成图片清单建立依赖；读取者不会获得直接读取其他成员原件的权限。历史、引用和生成图复核共用一次读取预算。只在同一只读快照内复用已完整通过的祖先，缓存仍比较原引用和全部合并输入的时间边界，调用结束或失败即恢复上下文。

定向验证：[test_group_native_image_tools.py](C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/tests/test_group_native_image_tools.py) **13 项通过，另含 2 个参数子用例**。覆盖目录授权、群受众伪造、Image/群记忆混用、重复编辑原回执、未知操作换编号不重放、其他外部动作拒绝、目录捕获后撤权、提供方换代、没有原子任务的成功回执拒绝、未附图的文字历史撤销，以及共享预算/缓存边界。三轮已确认生成历史在预算 6 时仅完整读取三个回复，预算 5 时明确拒绝；复核缓存无法隐藏合并输入中较晚的一条消息。

受影响部分的回归为 `test_group_memory.py`、`test_group_conversation_context.py`、`test_external_tools.py`、`test_group_media.py`、`test_group_quote_governance.py`：**84 项通过，另含 15 个参数子用例**，用时 191.37 秒。运行前后所涉实现文件哈希一致；仅出现 AstrBot SDK 的 `audioop` 弃用提醒。该计数单独记录，主整合任务需去重后汇总，不能与其他任务重复运行的同名用例相加。

这些测试使用 AstrBot 自带 Python、临时 `ASTRBOT_ROOT`、临时 V2 SQLite 存储、合成图片与本地提供方/发送器，不调用真实模型、QQ 或旧插件数据。默认宿主装配和提供方执行闭环见开头所链 Image 记录。下一步在 Image 收尾补验后，将 Content 已完成的原生作品领域接入现有插件入口、V2 消费者和来源撤回传播；当前群聊结果不能代表其他六个提供方已经完成 V2 重构。
