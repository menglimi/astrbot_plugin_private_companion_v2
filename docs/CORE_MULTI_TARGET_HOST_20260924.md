# 多 Bot／多人格共享宿主落地记录

同日后续已接入[多目标状态、日历与周期管理](CORE_MULTI_TARGET_STATE_20260924.md)：`/host/status` 的每个私人 target/role 同时提供 `memory_api` 和 `state_api`。状态入口复用原命令合同，QQ 展示结果按原上下文投影，启动绑定与重载回执已经验证。

2026-09-24。本记录对应“陪伴插件新框架落地”中多 Bot／多人格宿主的实现范围。它把多个明确配置的 AstrBot 私聊目标接入同一个 Companion V2 安装和运行时，并保留每个目标的身份、人格上下文、记忆管理入口和投递授权边界。

## 已落地的宿主边界

- `multi_settings.py` 解析共享安装 ID、平台账号、逻辑 Bot、私聊参与者、原生 persona 与 V2 `role_id`。目标路由由平台实例、账号和参与者组成；冲突、重复映射、缺失人格和能力配置在初始化前拒绝。
- `multi_authority.py` 持久化 `astrbot.multi.manifest.v1`，为每个 target 固定原生身份、角色绑定和公共能力 grant。初始化只允许首次绑定或同一配置重放；已初始化的身份不能静默改绑。OneBot 投递授权保存为 target 级、有限期、可撤销记录。
- `multi_session.py` 装配一个 `AstrBotCompanionHost` 和一个 SQLite runtime，多个 target 共用模型与任务基础设施。每个 target 仍有独立 intake lock；原生 conversation ID 会再加 V2 role 标记，防止人格切换时混入旧上下文。
- `multi_controller.py` 接通 probe、initialize、load_existing、start、stop、terminate、事件 admission 和按 target 投递授权。AstrBot 插件入口根据 `multi_host.enabled` 选择多目标宿主或原有单目标 staging 宿主。
- `multi_api.py` 注册 `/host/status`、`/host/probe`、`/host/initialize`、`/host/start`、`/host/stop`、按 target 的 authorize/revoke delivery，以及 `/host/targets/<target>/roles/<role>/memory...` 管理路由。每个路由闭包携带不可变 target/role，不依赖全局“当前选中目标”。重载和终止只注销本实例拥有的路由。

## 记忆与人格隔离规则

长期记忆的 owner 仍由以下稳定身份组成：

`installation_id + bot_id + V2 role.subject_id + human subject_id + private`

平台账号、AstrBot 原生 persona ID 或 persona 显示名称不是记忆隔离键。原生 persona 只负责在宿主 admission 时解析到配置的 V2 role：

- 同一逻辑 Bot、同一用户下，不同原生 persona 映射到相同 `role_id` 时共享同一 owner 和长期记忆。
- 需要独立记忆的人格必须使用不同 `role_id`；只改 persona 名称、提示词或显示文本不会自动创建分区。
- 不同逻辑 Bot 即使使用同一用户和同一原生 persona，也有不同 owner。需要共享记忆时必须显式复用相同逻辑 Bot 和 role 语义，并通过现行来源权限。
- 同一 owner 的不同私聊 conversation 可以召回 durable 记忆；session retention、待提交提议、操作回执、订阅和持久引用仍带原 scope/caller 约束，不能因为长期 owner 相同而跨窗口搬运。
- A→B→A 切换会使离开的 role 上下文失效；切回 A 后重新获取可信上下文，可以读回 A 的长期记忆。B 不能读取 A 的事实、pending 操作或回执。

## 事件与投递边界

只有同时匹配已配置的平台实例、Bot 登录账号、私聊参与者、FriendMessage 形态和当前原生客户端的事件才会被接管。未配置参与者的事件不会写入 V2 数据库，也不会创建授权或任务。

preview 模式只保存生成稿。`onebot_private` 模式必须先由 Dashboard 对具体 target 授权，发送前再次核验该 target 的身份、scope、权限和授权期限；授权 target A 不会使 target B 能够发送。撤销或过期会关闭该 target 的新投递，并让尚未派发的发送边界失败。

## 验证结果

新增多目标测试覆盖配置冲突、共享 runtime、Bot／role owner 隔离、人格切换、pending 和操作回执、重启恢复、逐 target 投递授权、并发 admission、未配置参与者和身份撤销；公共记忆专项继续覆盖订阅、ACK/resync 和持久消费恢复。Dashboard 路由专项还验证了：

- 七个共享宿主控制入口按管理员身份工作；
- 四组 target/role memory API 指向各自的不可变 target/role；
- probe → initialize → start → stop 可以通过路由完成；
- preview 下的 target 投递授权不会越过投递模式限制；
- 终止或显式注销后 `registered_web_apis` 不残留旧路由。

本次 `tests.test_astrbot_multi_host` 共 12 项通过；宿主生命周期与隔离回归共 79 项通过；公共记忆边界、pending、订阅、流消费、原生和关系记忆专项共 86 项通过。测试使用 AstrBot 自带 Python、临时 `ASTRBOT_ROOT`、临时 V2 数据库以及合成平台、模型和发送器；没有读取、迁移或修改 V1 数据，也没有向真实 QQ 发送消息。

## 当前范围

这已经是插件内部新框架的多目标宿主落地和可审查本地证据。真实 AstrBot 多账号同时在线、跨进程插件重载、真实模型/OneBot ACK、生产数据恢复和长时间压力仍需现场验收。它们不改变当前已经固定的 owner 和授权边界。
