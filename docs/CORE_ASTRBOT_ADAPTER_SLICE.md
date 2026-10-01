# CORE-ASTRBOT AstrBot 4.27.2 适配器切片

更新时间：2026-09-22。本切片记录 V2 对 AstrBot 4.27.2 的首批真实适配。适配器是显式 opt-in 的连接层，已经在隔离宿主环境验证，但尚未注册为 AstrBot 插件，也不会接管现役 V1。

## 已接入的边界

- `companion_v2/adapters/astrbot/native.py` 只接受已登记的 `AiocqhttpMessageEvent` 私聊事件：平台必须是 `aiocqhttp`，场景必须是 `FriendMessage`，消息必须是有界纯文本；群聊、线程、媒体和转发会在入站边界被拒绝。它同时读取并复核登录账号、Bot、发送者、会话、当前人格和人格提示词，把这些值投影为不可变的 V2 运行范围。
- `companion_v2/adapters/astrbot/inbound.py` 和 `application.py` 将冻结的宿主快照交给统一 V2 装配。捕获失败不会写入半份来源或批次；生成和发送前再次复核原账号、平台客户端、会话和人格。
- `companion_v2/adapters/astrbot/model_wire.py` 将 V2 工具映射为稳定别名，严格校验模型 JSON、工具参数、claims 和证据句柄。模型只能看到宿主已经提供的资料，工具仍由 V2 持有并执行。
- `companion_v2/adapters/astrbot/provider.py` 复用已验证的 AstrBot OpenAI 兼容 provider 解析器，将 V2 的一次模型尝试接到原生客户端；V2 关闭 SDK 重试并保留实际用量，未知结果不自动换调用编号重做。
- `companion_v2/adapters/astrbot/onebot.py` 通过当前账号的 reverse WebSocket 发送私聊纯文本。只有拿到真实 `message_id` 才记录为 `delivered`；超时或异常记录为 `unknown`，不会自动重发，也不会把宿主布尔返回值当成送达证据。

适配器不把主动权交给 AstrBot 的默认会话或默认 persona。Bot、登录账号、发送者、完整会话、受众和角色绑定都来自同一宿主快照；任何一项在等待期间变化，原操作都会失效并保留可审计的失败或未知状态。

## 原生契约验证

使用 AstrBot 自带 Python，在临时数据根和无网络环境运行：

```powershell
C:\Users\99505\.astrbot\backend\python\python.exe -X utf8 tools/run_native_contracts.py --host-source C:\Users\99505\.astrbot\archive\astrbot-4.27.2-audit
```

首批结果为 **7/7 通过**；随后[受控试运行切片](CORE_ASTRBOT_STAGING_SLICE.md)增加配置采用/预览、原生回执及未知结果重开三项，当前 **10/10 通过**，网络尝试为 **0**。覆盖真实 SDK 类型、事件字段、账号/人格隔离、工具续答、模型 503 单次请求、缺失用量、非法工具参数、reverse WebSocket 成功送达和超时未知回执。测试使用 `httpx.MockTransport`、内存 WebSocket peer 和临时 AstrBot 数据根，不代表生产模型、生产账号或生产网络已经接通。

## 尚未开放的内容

- V2 仍没有 `metadata.yaml`、插件入口或发布身份，因此 AstrBot 扫描不会加载它；当前适配器必须由可信装配显式创建。
- 目前只验证 OneBot 私聊纯文本。群聊/系统任务、媒体/转发、流式输出、真实后台主动投递、阅读证据和其他平台均未接入。
- 没有读取 V1 数据、运行 V1 配置迁移或替换生产发送链；V1 的自动兼容迁移仍是直接替换资格之前的独立关卡。
- 宿主字段和 SDK 类型已经有 4.27.2 契约证据，但生产 provider、真实 reverse WebSocket、管理页和移动设备仍需单独的受控验收，不能由本地替身测试代替。

受控 staging loader 已作为显式 API 实现，配置采用、草稿预览、原操作回执和停止/重开证据见[试运行记录](CORE_ASTRBOT_STAGING_SLICE.md)。可信配置解析、首次身份初始化与只读加载随后由[bootstrap 切片](CORE_ASTRBOT_STAGING_BOOTSTRAP_SLICE.md)补齐。实际宿主管理入口及 provider/平台验收仍待推进；群聊、媒体和迁移仍按各自关卡推进，当前不能注册并接管 V1。
