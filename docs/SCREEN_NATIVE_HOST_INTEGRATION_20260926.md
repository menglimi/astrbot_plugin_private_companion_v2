# Screen 原生提供方与 V2 宿主接入

日期：2026-09-26。范围为可选 Screen 插件的 V2 原生单次截图提供方，以及唯一 V2 本体中的发现、授权、采纳和模型上下文接线；未修改管理页面或 V1 用户数据。

## 已落地

Screen 的 `native_v2.enabled` 默认为关闭。启用原生模式后，插件只暴露 `screen.native` 提供方，不注册旧 LLM 工具、不启动自动观察或独立发送/日记任务；停机关闭提供方。提供方使用 Pillow 在本机采集一张有尺寸和字节上限的 JPEG，并在自己的 SQLite 中保存原请求、结果和图片字节。相同 invocation 只返回原回执；结果未知时不自动重采。设备、平台实例 ID、Bot 登录账号和 V2 Bot ID 必须显式绑定。配置中的 `platform` 对应 AstrBot 的 `platform_meta.id`，默认留空，不能填平台类型 `aiocqhttp` 来代替实例 ID。

V2 宿主按现有原生插件目录发现 Screen，只有明确登记能力、启用角色和授予原私聊 scope 权限后才可调用。每次设备调用前、读取原图前和采用时都复核原任务、提供方代际、角色、能力、身份和受众。成功图片由 Screen 领域保存为独立的 Source、Asset、Capture 和内容寻址原件，作为本轮模型图片材料；不变成可直接发送的出站图片，也不启动 Screen 旧版自动循环。

原件发布与末次宿主校验处于同一数据库事务。校验失败时 Source、Asset、Capture 记录回滚，模型不能读取该截图；提供方已成功执行的事实和 V2 操作回执仍保留，不能被改写成未执行。内容寻址目录可能留下无数据库引用的物理字节，提供方 SQLite 也保留原操作图片；本切片没有实现物理清理，不能将“不可治理读取”理解为“字节已删除”。

## 验证

使用 AstrBot 自带 Python、`backend/app` SDK 路径及临时 `ASTRBOT_ROOT`。Screen 的 `tests.test_config_lifecycle`、`tests.test_tool_context` 共 17 项通过；V2 的 `tests.test_native_screen_flow`、`tests.test_provider_registry`、`tests.test_native_provider_contract`、`tests.test_native_provider_host`、`tests.test_native_provider_sessions`、`tests.test_native_image_result_handler`、`tests.test_native_content_flow` 共 64 项通过。这些是两个定向批次，不与此前 Screen 10 项或其他切片重复累计。

测试覆盖原生模式入口/停机、旧入口关闭、绑定缺失、旧工具上下文兼容、真实提供方回执与重启去重、图片采纳及读取治理、采纳失败与末次校验失败回滚，以及共享注册器对 Image/Content 的定向回归。图片和模型均为合成替身；未触发真实截图、在线重载、真实视觉模型或 QQ 投递。

## 后续验收

2026-09-26 在独立 Python 进程和临时 V2 数据根中执行 `tools/accept_screen_capture.py --capture-once`，实际采集本机桌面一次：JPEG 为 2048 x 1152、317049 字节，SHA-256 为 `c79cccb7ee8051fc5eb19e0e1c64c36e6372665bf87e7ac83ee224e3c30d12b1`。V2 形成一条 committed 提供方回执和一条截图原件记录，续答模型输入包含 1 张图片，出站图片数为 0；重复同一事件没有重采。测试只输出元数据，截图字节没有写入报告，测试数据根在结束后清理。模型、发送端、身份与能力授予使用本地测试替身，没有调用真实视觉模型或 QQ，也未启动在线插件。

统一构建器已把 Screen 的 `native_v2/`、Image 的 `image_companion/` 和 Content 原生目录纳入包清单，并在验包时检查原生必需文件。新版 8 个插件 ZIP 与外层套件构建于 AstrBot 插件扫描目录之外；包哈希、逐文件哈希、语法和解压副本的 SDK 启停/路由注销检查通过。2026-09-25 的旧 ZIP 未覆盖。

仍需在受控测试账号上配置正确的平台实例 ID、Bot 登录账号、V2 Bot ID、设备和 Screen 能力授权，并在在线插件更新后进行显式私聊识屏验收，核对真实模型输入与旧后台任务状态；当前现场 Screen `native_v2` 仍关闭。此项不能由离线截图验收替代。

## 现场只读复核（2026-09-26）

本次仅使用命令行读取本机配置与 V2 数据库，没有打开浏览器或更改在线插件。Screen 配置现已启用 `native_v2`，设备、平台实例、Bot 账号与 V2 Bot ID 均已填写；感知接口报告提供方为 `native_v2`、只读、运行就绪。上段“仍关闭”是此前验收时的状态，不再代表当前配置。

授权准备前，V2 选择的运行档为 `qq-v2-stream-20260926`，其基础授权只含 `configuration.read`、`conversation.reply`、`text`。该运行档数据库中 `capability_descriptors`、`capability_installations`、`capability_role_selections`、`capability_authorizations` 和 `capability_settings` 均为零行，尚未登记或授权 `companion.screen`。带目标和角色的语义接口返回 `supervisor_fenced`，与 V2 未启动一致；Screen 提供方就绪不能据此推定 V2 已接管消息或能采纳截图。现场 V1 仍在处理消息，本次没有并行启动 V2。

## 现场授权准备（2026-09-26）

V2 宿主新增显式 `POST /api/plug/astrbot_plugin_private_companion_v2/staging/prepare-screen` 入口。它只接受当前加载的 Screen 原生声明与固定私聊运行档；在同一事务中登记、acquire 原生包，启用目标角色，授予 `screen.read`、`screen.process` 的精确 scope consent，以及这两项和 `extension.tool.invoke` 的身份权限。若提供方、已登记包、角色或授权曾被修改或撤销，入口返回错误，不覆盖现有决定；失败时回滚本次写入。入口不启动 V2 会话、截图或投递。

使用 AstrBot 自带 Python 的宿主与 Screen 定向回归共 28 项通过，包括重复调用、撤销保留、提供方变更、部分写入回滚以及热重载路由注销。文件按 UTF-8 无 BOM、LF 检查。仅通过命令行和本机 HTTP 对在线 V2 热重载后，首次准备返回 `prepared: true`、`replayed: false`、`started: false`，Screen 包版本为 3.3.0；再次调用返回 `replayed: true`。只读核对当前运行档数据库：Screen 安装为 active，目标角色启用，两个能力各有一条 active 私聊 consent，三项身份权限各一条。V2 会话仍为 `new`、`accepting: false`，状态没有平台发送。

下一步要先确认 V1 不再接管同一 QQ 私聊，再显式启动 V2，并用一条受控私聊核对真实截图、模型图片输入、一次回复及原操作回执。当前没有执行这一步，也没有触发真实截图或 QQ 消息；遇到未知结果不重发同一截图操作。

## 现场识屏失败与修复（2026-09-26）

02:55 的受控私聊中，V2 模型发起了 `screen.capture`，但原生调用在设备采集前返回 `external_not_started`、`not_committed`；Screen 提供方没有留下截图操作，V2 没有生成截图原件。用户收到的“没能看到屏幕”符合这条失败回执。Screen 提供方原先把发起人的 QQ 号当作 Bot 登录账号核对；现改为核对 `principal.account_id`，并将包版本升至 3.3.1。旧批次的操作未重放。

V2 新增受 Dashboard 身份约束的显式 `upgrade-screen` 入口，按旧包版本、哈希和修订号核对后升级，失败回滚，保留原角色与能力授权。同时修复撤销后再次授权投递的谱系校验，以及外来授权 ID 被误识别为固定授权的问题。AstrBot 自带 Python 运行的 V2 定向回归共 78 项通过；Screen 的配置生命周期与原生提供方定向测试共 8 项通过。

命令行热重载 Screen 与 V2 后，在线 Screen 显示 3.3.1，V2 独立运行档 `qq-v2-stream-20260926` 的 Screen 安装由 3.3.0、修订号 1 升至 3.3.1、修订号 2。`screen.read`、`screen.process` 原私聊授权保持 active，提供方报告 `native_v2` 就绪。升级自身未启动 V2、截图或发送消息。

曾临时停用 V1，在固定测试账号 `995051631` 上重新授予短时投递并启动 V2。等待期间未收到新的私聊测试消息，数据库仍只有 02:55 的旧批次，Screen 提供方操作数和 V2 截图数均为零，因此真实截图、模型图片输入和最终回复尚未获得在线端到端证据。随后已停止 V2、撤销投递并恢复 V1；最终状态为 V1 启用，V2 `stopped`、`accepting: false`、`authorization_revoked`。后续须用一条新的私聊识屏请求重新复验，不重放旧操作。
