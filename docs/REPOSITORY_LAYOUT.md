# 文件组织与依赖规则

更新时间：2026-10-10。V2 根目录只提供 AstrBot 插件入口和工程导航，功能代码按宿主边界和领域归属组织。

普通聊天的 AstrBot 核心接入集中在 `astrbot_host/core_reply*.py`：背景、原生工具和媒体、真实发送复核、后台观察及统计分别维护。原生消息和领域工具的数据适配归 `companion_v2/conversation/native_*.py`，核心用量与效率投影归 `companion_v2/model_gateway/`，新增持久表归 `companion_v2/storage/`。核心领域不反向导入 SDK；具体执行归属见 [核心回复路径](V2_CORE_REPLY_PATH_DESIGN.md)。

Content、Image、Screen、Reality、Together、Game、Live 是同一 V2 插件内的七项原生拓展。`astrbot_host/native_extensions/builtins.py` 组装这些模块，`__init__.py` 管理能力注册及生命周期；`settings.py`、`image_settings.py` 管理 V2 内部配置，`service.py` 提供宿主服务接线。运行代码、默认设置、schema、网页和供应商运行资产全部随单个 V2 ZIP 交付；`main.py` 保持唯一 Star 及插件注册入口。新单包构建和验收状态见 [整合验收](INTEGRATION_ACCEPTANCE_V2_0.md)。

群复读的两个固定动作由 `conversation/repeat_actions.py` 保存决策、每日额度及发送状态，由 `astrbot_host/group_repeat.py` 复核授权并通过原生群事件发送原句、打断语或本地打断图。复读入口不调用模型，不产生普通接话窗口；其配置与观察仍由 `conversation/participation.py` 和唯一「陪伴小屋」页面管理。

群基础唤醒由 `conversation/group_admission.py` 管理，未点名求助评分归 `conversation/group_questions.py`；Laya 问题与紧凑输入归 `decision/prompt.py`，宿主事实捕获归 `astrbot_host/core_reply_decision.py`。群核心发送补充分段归 `astrbot_host/core_reply_segmentation.py`，无 SDK 的增量文本边界归 `conversation/stream_segments.py`。定向测试与真实权重合成检查分别归 `tests/test_group_wakeup_boundaries.py`、`tests/test_core_group_segmentation.py` 和 `tools/check_group_laya_live.py`；日志诊断见 [群高频回复修复](GROUP_REPLY_WAKEUP_20261010.md)。

```text
astrbot_plugin_private_companion_v2/
├── main.py                  # AstrBot 注册、事件转发、加载与终止
├── metadata.yaml            # 插件身份和宿主版本要求
├── _conf_schema.json        # AstrBot 约定的配置 schema
├── pyproject.toml           # 核心包构建与依赖声明
├── README.md / AGENTS.md    # 使用导航与工程约定
├── astrbot_host/            # 依赖真实 AstrBot SDK 的集成层
│   ├── controller.py       # 固定 profile、授权、会话与停机
│   ├── multi_settings.py   # 多 Bot／多人格 target、账号与 role 映射
│   ├── group_settings.py   # 独立群目标配置及场景边界
│   ├── group_authority.py  # 原发言者、群受众与前台授权的原子受理
│   ├── group_delivery.py   # 独立群发送授权、原批次模式及授权版本
│   ├── multi_authority.py  # 共享安装的身份、人格绑定与投递授权
│   ├── multi_session.py    # 多 target 共享 runtime、入站锁和发送边界
│   ├── multi_controller.py # 多 target probe、初始化、启停与恢复
│   ├── multi_api.py        # 多 target Dashboard 控制、记忆、状态与生活路由
│   ├── settings.py         # 宿主配置解析与共享配置错误
│   ├── native.py           # 原生类型装配、账号/人格/provider 探测
│   ├── native_extensions/  # 七项内部拓展的 SDK 接线、配置与生命周期
│   │   ├── builtins.py    # 唯一 V2 宿主内组装 Content/Image/Screen/Reality/Together/Game/Live
│   │   ├── image_native/ # 生图及编辑后端、运行配置和内部图片 API
│   │   ├── screen_provider.py # 本地单次截图与原件回执
│   │   ├── reality/      # 设备/手机服务、配置及设备测试资产
│   │   ├── together/     # 共读/观影/通话服务及内部房间网页
│   │   ├── game/         # 游戏房间服务、配置和网页
│   │   └── live/         # 直播/VTS 服务及 blivedm、SoulLink 运行资产
│   ├── media.py            # 原生图片验证及公共附件下载边界
│   ├── media_components.py # 私聊/群聊原始音视频组件恢复，隔离宿主预处理文字
│   ├── audio/              # Record 原件恢复、音频加载、可取消解码进程
│   ├── animation.py        # 动态图解码、合成与帧缩放
│   ├── animation_container.py # 动画容器完整性及帧数校验
│   ├── forwards.py         # 原生 Forward 定向读取及图像/音视频加载器装配
│   ├── life_api.py         # 日记与生活的 Dashboard 鉴权入口
│   └── web_api.py          # Dashboard 路由、响应序列化及注销
├── companion_v2/           # 可脱离 AstrBot 导入的领域核心
│   ├── foundation/         # 公共引用、结果、隔离检查
│   ├── identity_policy/    # 身份、人格归属、授权
│   ├── storage/            # V2 数据根、事务、schema 与内部升级
│   ├── sources/            # 来源与原件治理
│   ├── configuration/      # 统一配置与采用回执
│   ├── execution/          # 任务、共享等待、尝试、取消与恢复
│   ├── model_gateway/      # 路由、预算与调用用量
│   ├── conversation/       # 输入、生成、工具续答与逐段投递
│   │   ├── media/         # 图片/动画、audio 语音合同、原件发布及授权重读
│   │   ├── quotes/        # 引用归因、定向原件、音视频及依赖治理
│   │   └── forwards/      # 合并转发节点归因、受众与图像/音视频原件依赖
│   ├── agenda/             # 便签和提醒
│   ├── delivery/           # 共享投递、图文封套/指纹、回执及 QQ 展示
│   ├── memory/             # 有证据的事实、经历、反思、召回及管理
│   │   └── group/        # 群成员陈述、独立读写权限、引用快照及群工具
│   ├── games/              # 可脱离宿主的对局状态与规则算法
│   ├── knowledge/          # 世界书与知识库格式解析，不负责检索授权/注入
│   ├── role_profile/       # 角色级身份、性格、互动边界与世界设定及对话快照
│   ├── integration/        # 外部后端请求参数的纯映射合同
│   ├── proactive/          # 主动候选、事件与外部材料响应解析
│   ├── expression/         # 表达候选学习及反应素材
│   ├── role_work/          # 角色活动、进度及产物引用
│   │   ├── models.py      # 记录、生命周期与内存夹具 ledger
│   │   ├── codec.py       # 原引用与持久记录反序列化
│   │   ├── ledger.py      # 统一 V2 事务上的持久角色生活服务
│   │   ├── reading.py     # 可信阅读完成登记、范围/原文校验及公共权限
│   │   ├── reader.py      # 实际阅读模型任务与完成提交
│   │   ├── work_models.py # 原角色的持久阅读/睡眠执行意图
│   │   ├── life/          # 多上下文协调、持久日程、生活执行、管理边界
│   │   ├── journal/       # 日记/梦境的材料、提示词、写作及归档服务
│   │   ├── growth/        # 技能/目标正本、版本回执、授权配置、角色工具及管理服务
│   │   └── timeline/      # 原领域历史读取、分页、角色时间线工具与来源复核
│   ├── capabilities/       # 能力目录、管理与进程内 provider discovery/binding
│   ├── content/            # 内部作品提供方、版本与采用/撤回领域服务
│   ├── reality/            # 现实设备能力合同
│   ├── together/           # 共处能力合同及共读书库
│   ├── live/               # 直播及呈现能力合同
│   ├── diagnostics/        # 诊断与修改建议
│   ├── host/               # 与具体宿主无关的运行时装配
│   └── adapters/astrbot/   # 注入原生对象的窄适配合同
├── tests/                  # 自动测试和复用测试辅助器
├── fixtures/               # 合成示例及静态测试材料
├── tools/                  # 手动运行的验证与开发工具
├── pages/                  # 按页面目录组织的 AstrBot 管理界面
└── docs/                   # 状态、设计、对照和验收证据
```

低成本迁移合同切片的归属和验收范围见[交付记录](LOW_COST_MIGRATION_CONTRACTS_20260926.md)。`conversation/date_context.py` 只投影本轮本地日期材料；`agenda/annual_calendar.py` 只读解析显式提供的逐年日历。`knowledge/parsing.py` 不做检索权限或上下文注入；`memory/mmr.py` 仅排序经既有流程筛选的候选。`proactive/external_materials.py` 归一化 provider-neutral 天气/新闻响应，不抓取外部数据；`model_gateway/replacement_rules.py` 和 `integration/nai_image.py` 分别是纯路由匹配与请求参数映射，不调用模型/provider。复盘、表达学习与 Content 创作合同均只产出校验后的候选或草稿，不自动保存、采用或发送。

记忆实现按私聊主体、Bot 与角色绑定；事实/经历治理、检索、反思和查询工具归 `companion_v2/memory/`。`fact_index.py` 维护可重建的事实增量投影，`fact_query.py` 负责候选分页、正本复核与续页预算；`wire_binding.py` 共用可信 scope/预算/封套校验，`proposal_wire.py`、`operation_receipts.py` 与 `wire_operations.py` 负责同步/延迟提交、统一回执更新及持久查账，`pending_query.py` 负责同会话草案分页，`wire_evidence.py` 负责原 session 证据引用。`subscriptions.py` 与 `stream_store.py`、`stream_validation.py`、`stream_visibility.py`、`stream_delivery.py`、`stream_consumer.py` 分别负责订阅控制、持久状态、协议校验、来源复核、批次/租约和持久引用消费者。宿主管理 API 归 `astrbot_host/memory_api.py`，数据库表和升级归 `companion_v2/storage/`。验收见[记忆实施记录](CORE_MEMORY_IMPLEMENTATION_20260923.md)与[公共能力分支](CORE_MEMORY_PUBLIC_BRANCH_20260924.md)。

纯游戏状态与规则归 `companion_v2/games/`，目前包含井字棋、五子棋、贪心骰子和二十一点。该目录不负责房间、访客身份、活动占用、平台连接、持久化或外部发送；相应业务接线须另行定义 V2 合同。范围和定向验收见[游戏规则切片](CORE_GAME_RULES_SLICE_20260926.md)。

多 Bot／多人格共享宿主由 `astrbot_host/multi_settings.py` 解析显式 target、账号和原生 persona 映射；`multi_authority.py` 固定安装身份、参与者、V2 role 绑定及每个 target 的投递授权；`multi_session.py` 让多个 target 共用一个 V2 runtime，同时按 target 保留 intake lock、conversation scope 和 sender 边界；`multi_controller.py` 提供 probe、initialize、load、start、stop、terminate 与恢复；`multi_api.py` 注册共享宿主控制路由及每个 target/role 的 memory、state、life API。核心 owner 仍使用安装、逻辑 Bot、V2 role 和人类主体，原生 persona ID 只用于解析当前 role；相同 `role_id` 共享记忆，不同 `role_id` 隔离。[多目标状态管理](CORE_MULTI_TARGET_STATE_20260924.md)复用 `state_api.py` 与可信目标视图；展示回执归属和持久回执恢复归 `delivery/presence.py`，当前人格的启动绑定归 `multi_session.py`。

[同一角色共享自动睡眠排程](CORE_SHARED_ROLE_SLEEP_SCHEDULE_20260924.md)沿用 `role_work/life/configuration.py` 的角色共享 owner，`coordinator.py` 负责稳定选择唯一执行窗口并投影执行窗口标识/下一次入睡时间；`management.py` 继续持有旧 owner 回执兼容。`pages/日记与生活/` 只负责展示共享范围、执行窗口与排程，不复制配置正本；共享睡眠、重启恢复和页面隔离验证分别归 `tests/test_role_sleep_configuration.py` 与 `tools/check_life_page.cjs`。

[角色状态总览](CORE_ROLE_STATE_PAGE_20260925.md)位于 `pages/陪伴小屋/state-page.js` 和 `state-page.css`，经管理页路由挂载，采用 `astrbot_host/page_api.py` 给出的当前授权目标及对应 `state_api`；睡眠计划/执行投影和角色模拟状态继续归 `role_work/life/management.py`、`role_work/state/management.py`。[QQ 展示编辑](CORE_QQ_PRESENTATION_EDITING_20260925.md)归 `state-editor.js`，管理草稿、CAS 冲突与原请求核对；保留来源、例外和提醒的公开文案窄命令归 `agenda/calendar.py`，认证字段白名单归 `astrbot_host/state_api.py`。V2 `pages/陪伴小屋/` 为规范页面源，修改后用 `tools/sync_framework_page.py` 构建并以 `--check` 验证；Content 作品模块通过小屋内部入口管理，历史设计预览单独保留。合成目标、权限撤销、对象隔离、XSS 与窄屏浏览器验收归 `tools/check_state_page.cjs`，编辑场景归其调用的 `tools/check_state_editor.cjs`。

[多目标生活管理](CORE_MULTI_TARGET_LIFE_20260924.md)复用 `astrbot_host/life_api.py` 和 `role_work/life/management.py`；`role_work/life/coordinator.py` 管理按可信上下文分开的执行器、共享配置 generation 及统一停机，`runtime.py` 保留每个窗口的阅读/睡眠和日记排程。集成与恢复测试归 `tests/test_astrbot_multi_life*.py`，SDK 独立进程入口验收归 `tests/multi_life_entry_process.py`。

[后台生活任务排队](CORE_BACKGROUND_FAIRNESS_20260924.md)由 `execution/waiting.py` 管理原任务的实时等待和上一代未开始任务清理，`execution/runner.py` 管理等待句柄与领取后执行；宿主统一注入阅读、私人书写和状态维护。状态排程的分页续扫归 `role_work/state/maintenance.py`，各领域继续持有和复核原输入。

[同一角色跨窗口身体状态与睡眠连续性](CORE_SHARED_ROLE_BODY_20260924.md)的角色正本与旧窗口记录采用策略归 role_work/state/ownership.py，原始及传递来源复核归 evidence.py，生理参数范围归 settings_scope.py；life/body_clock.py 从活动正本投影实际睡眠，life/coordinator.py 选择唯一自动睡眠执行窗口，conversation/state_context.py 发布授权视图并固定历史观测。

群聊增量由 `astrbot_host/group_settings.py` 和 `group_authority.py` 管理群目标与原发言者授权；`companion_v2/adapters/astrbot/group.py` 负责 OneBot 原消息、群/成员 session 和当前 persona 的冻结校验，`identity_policy/group_audience.py` 提供显式集体受众。`astrbot_host/group_delivery.py` 保存逐群发送授权和受理时的原批次意图；`adapters/astrbot/onebot_group.py` 固定群受众和 API 路由，与 `onebot.py` 共用窄 reverse WebSocket 传输及回执规则。群目标共用前台任务/模型/逐段投递链，管理 API 提供独立授权、批次和回执查询，不暴露私聊 memory API。详见[入站切片](CORE_GROUP_PREVIEW_20260924.md)和[投递切片](CORE_GROUP_DELIVERY_20260924.md)。

[群公共记忆](CORE_GROUP_MEMORY_20260924.md)归 `companion_v2/memory/group/`：`access.py` 固定群 owner 和原发言证据，`service.py` 使用公共记忆表及事务保存成员陈述/版本/回执，`context.py` 管理引用快照与本轮更新证明，`tools.py` 提供群专用查询、保存、本人修订撤回和查账。`conversation/group_history.py` 复核派生 Bot 历史依赖，`messages.py` / `tool_loop.py` 装配消费者；专项与独立 SDK 入口模拟放在 `tests/test_group_memory.py` / `group_memory_entry_process.py`。本切片不新增存储迁移或根级业务文件。

[群成员相识](CORE_PERSON_ACQUAINTANCE_20260927.md)归 `companion_v2/memory/person/`：按 bot、伴侣与人类 subject 保存跨群、跨私聊的相识正本（`memory_views` kind `person.acquaintance.v1`，免迁移），`access.py` 派生 owner 并经受信绑定表解析原生账号，`service.py` 在受理事务内幂等计数并投影发言者卡，`tools.py` 暴露只读 `acquaintance.recall`，`configuration.py` 注册 `person` 配置组；宿主在 `astrbot_host/multi_session.py` 从已认证事件记录平台称呼。依赖方向：`memory/` 与 `memory/group` 不得 import `memory/person`。

[群图片与引用](CORE_GROUP_MEDIA_20260924.md)的捕获归 `adapters/astrbot/group.py`，群定向原件读取归 `group_quotes.py`；真实 SDK 类型及读取器由 `astrbot_host/quotes.py`、`native.py` 和 `multi_session.py` 装配。`conversation/quotes/group_originals.py` 复核已知群成员/确认 Bot 原件，`conversation/group_media.py` 提供历史附件视图和原件检查；群历史继续有界遍历原依赖。图片/动画/引用存储复用原服务，不新增表。专项与独立入口脚本归 `tests/test_group_media.py` / `group_media_entry_process.py`。

[群合并转发与嵌套节点](CORE_GROUP_FORWARDS_SLICE_20260925.md)的固定群历史读取归 `adapters/astrbot/group_forwards.py`，由 `astrbot_host/forwards.py`、`native.py` 和 `multi_session.py` 装配原生 Forward 类型及读取器。[节点音视频扩展](CORE_GROUP_FORWARD_MEDIA_20260925.md)复用 `conversation/forwards/` 清单、`conversation/media/audio/`、`video/` 原件与图片帧服务，群直接附件和转发节点在 `group.py` 复核合计预算。`conversation/group_media.py` 将历史投影为文本及有原归因的媒体元数据，不重放旧音频或旧画面。原输入撤回通过已有 Source 依赖链撤销节点及附件，无新增存储表或根级业务文件。专项测试位于 `tests/test_astrbot_group_forwards.py`，独立 SDK / 本地 ACK 验收归 `tests/group_forward_entry_process.py`；合成节点媒体夹具复用 `tests/forward_support.py`。

[群引用媒体](CORE_GROUP_QUOTE_MEDIA_20260925.md)复用现有 Quote/Forward/Audio/Video 来源服务；`conversation/quotes/group_originals.py` 比对已知群原件并关联原成员、节点和媒体依赖，`conversation/group_media.py` 保留历史三层归因与附件元数据。专项归 `tests/test_astrbot_group_quote_media.py`、`test_group_quote_media.py`、`test_group_quote_governance.py`；夹具归 `group_quote_media_support.py`，真实 SDK 入口复用 `group_forward_entry_process.py` 的引用模式，由 `test_astrbot_group_quote_entry.py` 独立进程验收。

`companion_v2` 还包含 `legacy/`、`sharing/`、`proactive/`、`screen/` 等已有领域目录；新增领域按相同方式组织。`legacy/` 保存兼容合同及映射定义，不自动读取 V1 数据。

[QQ 空间拓展](QZONE_EXTENSION_LANDING_20261002.md)归 `companion_v2/qzone/`：`protocol.py` 只做 Cookie/`g_tk`、宽松 JSON 与四个端点的请求构造（纯函数，不联网），`feed.py` 把 `msglist`、H5/旧版 HTML 动态与评论解析成统一记录，`references.py` 管「扫到才可动」的不透明动态引用，`policy.py` 管熔断、间隔、每日上限与去重（状态写 `memory_views`，不新增表），`service.py` 编排四项动作与本地回执，`capability.py` 声明固定能力包与模型工具面。安装/角色启用/会话同意/身份授权归 `companion_v2/capabilities/qzone_access.py`；HTTP 会话、OneBot 凭据获取与请求头归 `astrbot_host/qzone_client.py`、`qzone_transport.py`；Dashboard 路由归 `astrbot_host/qzone_api.py`（单目标与多目标按角色前缀各挂一次）。该领域不读 V1 数据、不持有插件配置里的凭据、不直接发 QQ 消息（发送仍归 `delivery/` 与宿主 sender）；模型工具接线尚未完成，见落地记录第五节。

[静态图片私聊](CORE_PRIVATE_IMAGES_SLICE_20260924.md)按宿主与领域分层：`astrbot_host/media.py` 获取并校验原件；`conversation/media/` 保存不可变清单、Source/Asset 依赖及原字节复核；原生适配器通过注入加载器接线。图片原件表及 v24→v25 升级归 `storage/media_schema.py` 和统一 runtime，测试位于 `tests/test_*image*.py`、`test_astrbot_media.py`、`test_media_migrations.py`。没有新增根级业务文件或运行产物。

[私聊引用文字与静态图](CORE_PRIVATE_QUOTES_SLICE_20260924.md)归 `conversation/quotes/`：清单与归因提示、来源发布与读取、已接纳原件依赖分别放在 `models.py`、`service.py`、`originals.py`。`adapters/astrbot/quotes.py` 使用注入客户端核验按好友定向的原消息；真实 SDK 装配归 `astrbot_host/quotes.py`，图片仍复用 `conversation/media/`，不另建原件库。

[动态图与帧覆盖](CORE_PRIVATE_ANIMATION_SLICE_20260924.md)沿媒体领域补充 `animation.py` 的不可变帧合同与 `codec.py` 的兼容恢复。Pillow 解码、容器完整性及像素处置留在 `astrbot_host/animation.py`、`animation_container.py`；核心服务仅消费捕获结果。直接图与引用图复用原件表和逐次授权；合成动画、闭环和 SDK 测试在 `tests/*animation*.py`，没有新增根级文件。

[合并转发节点治理](CORE_PRIVATE_FORWARDS_SLICE_20260924.md)归 `conversation/forwards/`：`models.py` 定义节点路径、显示归因、清单及提示；`service.py` 负责脱敏、原子发布和依赖重读。注入客户端的好友定向历史读取和树冻结归 `adapters/astrbot/forwards.py`，真实 SDK 装配归 `astrbot_host/forwards.py`；复用图片及动画服务，不增加独立存储或根级业务文件。

引用/转发的历史响应容器归一化放在 `adapters/astrbot/history.py`；账号、好友、消息号和节点校验仍留在各读取器。异常协议专项放在 `tests/test_astrbot_history.py`，真实 SDK 的本地 ACK 与混合媒体恢复用例继续放在既有宿主/转发测试中；没有新增根级模块或运行产物。

[Reply 引用合并转发](CORE_QUOTED_FORWARDS_SLICE_20260924.md)仅在 `conversation/quotes/forward_models.py` 扩展引用清单、内部父视图和归因提示，纯文本/图片引用保持旧格式。宿主复用 `adapters/astrbot/forwards.py` 冻结并捕获节点图像、音频和视频；`conversation/forwards/media_events.py` 将节点媒体归入原有来源授权链，图片/视频采样帧与音频都由现有服务重读。协议与治理专项归 `tests/test_astrbot_quoted_forwards.py`、`test_conversation_quoted_forwards.py`，不新增独立数据库或根级文件。群直接转发与节点音视频使用上述群适配器；群 Reply 内转发及音视频使用[群引用原件合同](CORE_GROUP_QUOTE_MEDIA_20260925.md)，共有冻结与捕获放在 `adapters/astrbot/quote_content.py`，群/好友路由核验仍由各自读取器负责。

[私聊原图出站](CORE_PRIVATE_IMAGE_DELIVERY_20260924.md)的选择提示、草案、来源清单和描述投影放在 `conversation/media/reply.py`；图文指纹与发送封套归 `delivery/media.py`。模型句柄与 OneBot 私聊编码留在 `adapters/astrbot/model_wire.py`、`onebot.py`，宿主仅装配能力、转发加载器和现有预览后端。图片继续复用原 Source/Asset 字节库，出站清单只保存引用及描述，不增加 SQL 表；专项及合成测试放在 `tests/*image_delivery*.py`，日志与备份放系统临时目录。

[群聊原图出站](CORE_GROUP_IMAGE_DELIVERY_20260925.md)继续复用上述选择、来源清单及图文封套；群集体受众和路由由 `delivery/media.py`、`adapters/astrbot/onebot_group.py` 复核。确认图文历史及有界原件重读归 `conversation/group_history.py`，Bot 图文再次引用归 `conversation/quotes/group_originals.py`。群专项、治理及 SDK 入口验收分属 `tests/test_group_image_delivery.py`、`test_group_image_delivery_governance.py`、`test_astrbot_group_image_delivery_entry.py`，复用 `group_media_entry_process.py`；没有另建插件、媒体库或根级模块。

[角色活动历史与自我时间线](CORE_ROLE_TIMELINE_SLICE_20260924.md)归 `role_work/timeline/`，分别处理原领域读取、按域索引查询、分页和工具参数。活动版本写入继续由 `role_work/ledger.py` 与原状态/操作共用事务；v22→v23 升级补录归 `storage/activity_history.py`，只接受现存 V2 活动头和已完成回执。宿主与对话层仅注册消费者，不新增根级业务文件。

日记与生活的完整调用链及使用入口见 [本轮验收](CORE_ROLE_LIFE_END_TO_END_20260923.md)。页面位于 `pages/日记与生活/`，没有将业务实现或运行产物放回源码根目录。

## 依赖方向

[记忆显式修复的后台续接](CORE_MEMORY_BACKGROUND_REPAIR_20260924.md)归 `memory/reflection_jobs.py`，保存原执行范围和独立操作者，由 `memory/scheduling.py` 复用宿主唤醒与停机；`reflection_management.py` 管理显式登记，`astrbot_host/memory_api.py` 提供固定目标的异步接口。v28 请求表和索引归 `storage/reflection_job_schema.py` 及公共升级链，不在页面或 AstrBot 入口保存独立任务状态。

[日历、角色状态与 QQ 展示](CORE_STATE_CALENDAR_AND_QQ_PRESENCE_20260924.md)分别归 `agenda/calendar.py` 和 `calendar_tools.py`、`role_work/state/`、`delivery/presence.py` 与 `adapters/astrbot/presence.py`。认证 HTTP 入口位于 `astrbot_host/state_api.py`，存储迁移归 `storage/state_schema.py`；管理页面直接接入这组 API，不另造领域逻辑。

[QQ 展示诊断](CORE_QQ_PRESENTATION_DIAGNOSTICS_20260925.md)归 `delivery/presence_diagnostics.py`，只读组合当前准入、公开文案与原会话任务条件；`presence.py` 继续负责原请求时间、回执归属与账号去重，状态管理 API 复用上述投影。

[状态维护参数与周期校准](CORE_STATE_MAINTENANCE_EDITING_20260925.md)的字段、表单及共享范围说明归 `pages/陪伴小屋/state-maintenance.js`，复用 `state-editor.js` 的草稿、冲突和原请求核对。`role_work/state/service.py` 负责相关参数令牌、事务内校验及回执稳定性，`management.py` 发布令牌，`astrbot_host/state_api.py` 维护既有命令入口字段；浏览器专项归 `tools/check_state_maintenance.cjs`。不新增本体、页面注册或存储表。

[生理期拟人与连续周期](CORE_ROLE_CYCLE_20260924.md)、[连续性优化](ROLE_CYCLE_OPTIMIZATION_20260924.md)及[每轮阶段差异](ROLE_CYCLE_VARIATION_20260924.md)归 `role_work/state/`：`cycle.py` 负责模拟日期、阶段、初始化及下一周期方案；`cycle_variation.py` 管版本化的阶段差异算法和本轮方案；`cycle_state.py` 管独立周期来源；`cycle_feelings.py` 管同一次感受的引用与时间；`cycle_prompts.py` 管维护和按当前阶段选取的拟人提示。持久化、维护和管理命令继续由同目录既有服务负责；`conversation/state_context.py` 封存本轮观测时间并复核权限和当前版本，沿用 state API 与版本表。

`main.py → astrbot_host → companion_v2`。根入口通过相对导入加载宿主子包，AstrBot 热重载按插件命名空间回收这些模块；入口继续管理核心包的独立搜索路径。`companion_v2/host` 是公共装配层，`astrbot_host` 才是依赖真实 SDK 的宿主实现，两者职责不同。`web_api.py` 拥有路由表与响应信封，并在模块层组装各 `*_api` 模块；因此这些模块只能在处理函数内导入 `outcome_response`，模块层反向导入会构成循环导入，让插件在 `main.py` 加载阶段直接失败。

核心内的 AstrBot 适配器通过显式注入对象工作，不导入 SDK，也不持有 Dashboard 路由。静态隔离检查拒绝核心导入 `astrbot` 或 `astrbot_host`；入口检查保证根目录不会继续增加业务 Python 模块。

## 增加文件时

- 根据业务数据的归属选择领域目录；模型、任务和发送分别使用现有公共服务。
- 同一职责的代码保留在一起；当配置解析、HTTP 路由或平台探测独立变化时，在所属包内拆分。
- 避免根级转发模块和通用 `utils.py`、`helpers.py` 成为功能堆积点。
- 新增测试按受测领域命名；需要再细分时按领域建立子包，并更新对应运行命令。
- 运行配置和 SQLite 保存在 AstrBot 的 `plugin_data/astrbot_plugin_private_companion_v2/profiles/`；临时验证与备份使用系统临时目录。不得写回源码根或放入 `fixtures/`。

## 本轮整理范围

原根级 `astrbot_staging_host.py` 已按四个职责拆入 `astrbot_host/`；`main.py`、宿主测试与隔离检查同步采用新路径。既有领域模块保留归属，不为统一文件名制造额外兼容层。目录拆分本身未迁移运行库；随后[模型失败诊断](CORE_MODEL_FAILURE_DIAGNOSTICS_SLICE.md)引入 v15，分类归 `model_gateway/failures.py`，持久化升级仍归 `storage/`，不增加根级业务文件。

本批 [CORE-05](CORE_ROLE_LIFE_PERSISTENCE_SLICE.md)将活动/产物的持久服务放入 `role_work/ledger.py`，记录恢复放入同领域 `codec.py`，由 `host/application.py` 装配；v16 表与升级仍归 `storage/`。角色生活测试放入 `tests/test_role_life*.py`，实施证据放入 `docs/`，根目录 Python 文件仍只有 `main.py`。

后续[日记/梦境](CORE_ROLE_JOURNAL_SLICE.md)使用 `role_work/journal/` 子包：`models.py` 定义日期与版本合同，`codec.py` 保留原引用，`service.py` 负责记录、衍生依赖和删除。v17 升级放在 `storage/`，测试与合成辅助器放在 `tests/test_role_journal*.py` 和 `tests/journal_support.py`。[写作实现](CORE_JOURNAL_WRITING_REVIEW_20260923.md)继续按职责增加同目录的 `materials.py`（素材语义）、`prompts.py`（写作约束）、`writing_output.py`（输出结构）和 `writing.py`（受管理生成与提交）；公共模型/任务基础仍由原领域提供。

[阅读完成与当天汇集](CORE_ROLE_READING_AND_COLLECTION_SLICE.md)沿用角色活动 JSON 和原操作回执：`role_work/reading.py` 负责可信完成报告，`journal/reading_materials.py` 只投影已读范围，`journal/collection.py` 在同一读取快照内遍历领域素材并保留明确选用入口。宿主仅做装配，根目录仍只保留 `main.py`。

[每日/睡眠触发与素材选用](CORE_JOURNAL_TRIGGER_AND_SELECTION_SLICE.md)继续放在 `role_work/journal/`：`selection.py` 负责原候选 ID 的提示和结构校验，`triggers.py` 负责当日接纳、流程和显式重试，`scheduling.py` 负责可信宿主的每日注册及唤醒。它们复用共享任务、操作与模型账本，宿主只装配并管理生命周期；没有新增根级业务文件或数据库表。

[后台协调与提醒投递](CORE_BACKGROUND_AND_AGENDA_DELIVERY_SLICE.md)把共享发送合同放入 `delivery/models.py`，公共投递 owner 和回执放入 `delivery/service.py`，有界协调器归 `host/background.py`；提醒扫描与原件读取归 `agenda/background.py`。v19 表与升级归 `storage/`，历史发送路径继续兼容导出公共模型，不增加根级业务文件。

[主动联系偏好与执行](CORE_PROACTIVE_CONTACT_SLICE.md)归 `proactive/`：配置字段与暂停解析在 `configuration.py`，当前联系判断在 `preferences.py`，输入合同与提示词分别在 `contact_models.py`、`prompts.py`，共享任务/模型及投递消费者在 `service.py`。公共 `ConfigTarget` 新增关系地址，旧地址保持兼容；v20 迁移仍归 `storage/`，不增加页面或根级业务文件。

[自动联系与后台历史接续](CORE_AUTOMATIC_CONTACT_AND_HISTORY_SLICE.md)记录私聊机会调度和预算演进，当前联系预算由 `proactive/budget.py` 按私聊窗口统计：模型调用次数与确认发送次数分开计，每个窗口按免打扰时区的本地日刷新；待确认投递暂占联系容量，可信回执确认未发送后释放。跨窗口关系额度已退役，历史记录见[旧关系级额度切片](CORE_RELATIONSHIP_CONTACT_BUDGET_SLICE.md)。公共历史回执投影放在 `delivery/history.py`，正文读取仍由主动/提醒 owner 提供。普通对话与主动生成保存原投递引用并重新授权读取，宿主共用原唤醒与停机链；保持 v20 schema，复用既有任务、配置和回执正本。

自动联系的可信事件来源按原件 owner 分开：`proactive/events.py` 消费已完成阅读/睡眠活动回执，`proactive/journal_events.py` 消费私聊日记/梦境的提交回执。两者各自管理扫描节奏和来源复核，分别由 `tests/test_proactive_activity_events.py` 与 `tests/test_proactive_journal_events.py` 验证。

[连续生活进入普通私聊](CORE_ROLE_LIFE_CONTEXT_SLICE_20260923.md)按职责拆为 `role_work/life/context.py`（角色生活读取与来源授权）和 `conversation/life_context.py`（有界引用快照、提示约束及原件重读）；既有 `conversation/messages.py` 负责封存接线，`host/application.py` 负责共享服务装配。相关测试放在 `tests/test_role_life_context*.py`。本切片复用 v20 内部 schema，不新增表或根级 Python 文件。

[角色技能与长期目标](CORE_ROLE_GROWTH_SLICE_20260923.md)归 `role_work/growth/`，按稳定角色 owner 保存提案、显式状态变化、文字进展、修订历史及操作回执；`context.py` 是当前参与者/角色/scope/source 的受授权读取边界，`conversation/growth_context.py` 封存 ID/revision 并在实际提示重建时复核。`growth/management.py` 负责人类管理，`tools.py`/`tool_sources.py` 负责角色工具及本轮原件，`configuration.py`/`access_management.py` 负责统一配置授权和管理者入口。`astrbot_host/growth_api.py` 负责 Dashboard 身份及 pinned profile 接线；职责和 API 见[成长授权消费与管理](CORE_ROLE_GROWTH_CONTEXT_SLICE_20260924.md)与[角色工具及授权设置](CORE_ROLE_GROWTH_TOOLS_AND_ACCESS_20260924.md)。v21→v22 表和升级归 `storage/`；本次复用已有表，未增加根级业务文件。

[记忆拓展](../companion_v2/memory/)归 `memory/`：`models.py` 定义事实、证据与策略；`writer.py`/`service.py` 管提议、授权、版本和提交；`query.py`/`search.py` 提供限额检索与独立可重建索引；`context.py`、`tools.py` 接入原对话；`experiences.py` 管经历摘要与对象导航；`reflection.py`/`scheduling.py` 承载每日增量反思；`management.py`/`configuration.py` 统一管理。权威数据表由 `storage/memory_schema.py` 定义，并通过 v20→v21 迁移加入，保留主动联系的 v19→v20 合同。宿主路由适配位于 `astrbot_host/memory_api.py`。长期记忆按安装、Bot、角色和可信用户归属，可在同一归属的私聊会话间授权召回；session 记忆保留原会话范围。群聊公共记忆和外部物理擦除不在此实现切片，V1 其余能力的承接边界见[专项对照](CORE_MEMORY_V1_PARITY_AUDIT_20260923.md)。

[私聊语音原件](CORE_PRIVATE_AUDIO_20260924.md)归 `conversation/media/audio/`：`models.py` 保存原件/音频视图合同与共享预算，`events.py` 组合旧媒体事件，`service.py` 负责原子发布及授权重读；`astrbot_host/audio/` 负责预处理前原始 Record 恢复、公共附件加载及短进程完整 PCM/SILK 解码。语音表和 v28→v29 升级归 `storage/audio_schema.py` 及统一 runtime，不把音频塞进图片表。专项和合成用例放在 `tests/*audio*.py`；测试日志、备份、SDK 临时根仍放系统临时目录。

[私聊视频原件与采样帧](CORE_PRIVATE_VIDEO_20260924.md)归 `conversation/media/video/`：`models.py` 定义清单、覆盖和统一视频预算，`events.py` 合并消息合同，`service.py` 发布原件并复核帧来源；`astrbot_host/video/` 负责 MP4 有界容器校验、OpenCV worker、原始组件恢复和受限附件加载。独立原件表及 v29→v30 升级归 `storage/video_schema.py` 与统一 runtime；抽样 PNG 复用图片服务和图片表。视频容器、会话、真实 SDK、多账号及迁移用例归 `tests/*video*.py`，不增加根级业务模块。

[群聊直接语音与视频](CORE_GROUP_AUDIO_VIDEO_20260925.md)复用上述音视频领域服务：`adapters/astrbot/group.py` 校验群路由、冻结原始组件并计算直接/引用/转发共享预算；`conversation/group_media.py` 重建含音视频的历史指纹、复核原件并投影附件元数据。真实 SDK 恢复位于 `astrbot_host/media_components.py`，通过独立 `group_component_reader` 接入多目标宿主；专项和入口验收归 `tests/test_group_audio_video.py` 与 `tests/*group_audio_video_entry*.py`。复用现有存储，不增加根级文件；[群 Reply 音视频引用](CORE_GROUP_QUOTE_MEDIA_20260925.md)已接通。
