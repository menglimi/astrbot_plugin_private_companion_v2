# Game / Live V2 原生接入

2026-09-26。Game 和 Live 仍是两个现有可选伴侣提供方，不另注册 V2 本体或公开 Dashboard Page。启用并初始化后，二者通过各自的 `extension_api.companion_v2_native()` 向唯一 V2 宿主提供同步能力声明和异步执行端口。V2 宿主继续负责原任务权限、角色复核与回执采用。

## Game

首片为聊天内可执行的井字棋，不复用 V1 WebUI 房间、QQ 访客票据、旧主动邀请、旧记忆或旧投递。Game 自有配置 `native_v2.tictactoe_enabled` 默认关闭，启用后独立于旧网页房间的 `server.enabled` 和 `tictactoe.enabled`；关闭时不向 V2 注册原生端口。`game.tictactoe.create` 创建或接续当前 V2 作用域的未结束对局；`game.tictactoe.move` 按 `game_id`、0 起始行列提交玩家落子并由成熟规则引擎应手；`game.tictactoe.snapshot` 查询棋盘；`game.tictactoe.close` 结束对局。

第二片新增独立默认关闭的 `native_v2.gomoku_enabled` 和 `game.gomoku.create/move/snapshot/close`。五子棋复用 Game 自身成熟的十五路棋盘与 Bot 决策引擎，坐标从 0 到 14；同一身份可分别保有一局井字棋和一局五子棋，开关、读写与棋局查询分别隔离。旧版本持久井字棋记录无 `game_type` 时继续按井字棋重放，五子棋也由同一原子账本恢复。

第三片接入默认关闭的 `native_v2.pig_dice_enabled` 与 `game.pig_dice.create/roll/hold/snapshot/close`。掷骰竞分复用现有 50 分规则和 Bot 决策，玩家每次掷骰或存分后在同一次操作内完成 Bot 回合；骰点逐次记录并由账本重放，返回最近事件与当前分数。第四片接入默认关闭的 `native_v2.blackjack_enabled` 与 `game.blackjack.create/hit/stand/snapshot/close`。二十一点使用现有六副牌规则引擎，V2 暂为单人、无下注、Bot 做庄；庄家底牌和完整牌堆在结算前不会进入工具结果，自动补牌和结算属于同一次已提交操作。四种聊天游戏都不复用旧网页房间。浏览器棋盘、多人席位与活动占用仍待后续接线。

Game 自有 `native_v2/games.json` 原子保存对局和写操作回执。作用域取完整 V2 上下文，排除可轮换的 `policy_revision`；Bot、人格、账号、会话不同不能读取或操作彼此对局。相同 invocation ID 只返回原回执，换上下文或参数拒绝。重启后按落子、骰点或二十一点已提交动作重建局面；二十一点原始牌堆只保存在 Game 提供方本地账本。账本损坏时拒绝加载，不能当作新局继续。Game 的旧房间和用户数据保持原状。

V2 记忆生产器只消费当前私聊身份的四种游戏终态成功回执：两种棋类的 `move`、掷骰竞分的 `roll/hold`、二十一点的 `create/hit/stand`（开局天然二十一点也可能直接结算）。它先复核外部工具子任务、现行 Game 授权和已发布的原生来源，再将有逐句证据的终局摘要写为经历；经历来源依赖原回执，撤回或遗忘原来源后不可再用。游玩过程、主动邀请、主观关系变化与未确认操作不会被写成经历。生产器有独立游标，重启后按当前已绑定身份继续补齐；旧版提供方声明不再可用时跳过相应未投影回执，以免挡住新版对局，不读取 V1 记忆。

## Live

Live 自有 `native_v2.enabled` 默认关闭；`bili_events_enabled` 与 `twitch_events_enabled` 分别控制可向 V2 暴露的平台。关闭的平台不进入事件工具的参数枚举，状态中的场次和房间信息也不暴露；两个平台均关闭时只保留状态工具。

`live.status.read` 只读 B 站/Twitch 监听状态；`live.events.recent` 只读当前正在监听的公开房间最近五分钟最多 12 条事件。每次监听启动生成不含房间信息的短期 `session_id`，停播立即失效；事件带稳定的 `event_id`。调用方保存返回的 `session_id` 与 `latest_event_id`，下次用 `session_id` 和 `after_event_id` 增量读取；场次变更或游标已从缓存淘汰时返回 `cursor_reset=true` 并从当前场次近期事件重新读取。输出裁剪为场次、平台、事件 ID、事件类型、昵称、正文和时间，不包含原始事件、用户 ID、凭据或 V1 观众档案。停播或换场后旧缓存不继续暴露。观众文本在能力说明和结果中标为不可信引用材料。

Live 原生端口不启动监听、OBS 推流、VTS 动作、旧自动回复，也不写 V1 记忆。V2 直播主动接话、语音/字幕/形象逐端回执、现场高光与结局记忆仍需单独的会话和呈现接线。

Game 和 Live 的工具参数声明已使用 V2 宿主支持的封闭 JSON Schema 子集；井字棋坐标和事件条数用枚举表达范围，字符串长度继续由提供方校验。此前仅通过 manifest 解析的声明无法进入宿主目录，现已补齐实际注册器检查。此前首批 3 项最小合同测试覆盖 Live 场次切换/停播/游标淘汰、参数拒绝及 Game/Live 同时发现。其他功能补齐后统一做原生合同、Game 跨重启/跨作用域/重复请求及终局记忆、Live 缓存边界和宿主生命周期验收；真实直播与平台投递不由离线夹具代替。

当前处于统一流程的第 1 阶段。Game/Live 原生接入已有四种独立聊天游戏与直播平台开关。二十一点、掷骰竞分和资讯边界的本批 12 项最小合同测试通过；真实 QQ、直播、浏览器房间和最终插件包未验。其余三种游戏、直播主动接话与 TTS/字幕/形象逐端呈现仍需补齐；完成代码及配置后再统一接入「陪伴小屋」、构建新包并测试。

> **2026-09-27 复核补记（只更正事实，不改历史结论）**：本文写于象棋落地之前，现已落后于代码两处——① 提供方 `native_v2/provider.py:48-51,55-61,380-404` 已加入第五种玩法**象棋**（`game.xiangqi.create/move/snapshot/close`，独立开关 `native_v2_xiangqi_enabled`，依赖 Pikafish 引擎），动作总数由 21 变 **22**，因此「四种独立聊天游戏」「两种棋类」的表述应读作**五种玩法、三种棋类**；② V2 记忆生产器 `companion_v2/memory/game_ingestion.py` 与 `host/application.py:306-309` 已消费象棋终局（`tests/test_game_memory_ingestion.py` 有断言）。逐家动作清单见[七个可选伴侣对照表](COMPANION_PROVIDER_STATUS_20260927.md)。本文「其余三种游戏」按提供方 README 的七种口径仍然成立。
