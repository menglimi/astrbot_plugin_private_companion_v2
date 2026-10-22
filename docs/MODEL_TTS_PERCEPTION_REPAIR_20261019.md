# 模型与语音感知修复（2026-10-19）

## 问题与原因

截图中聊天模型能够说明自己使用的 DeepSeek 配置，却说“语音那套更看不到”。这次按 V1 的 TTS 感知能力对照修复 V2，不调整其他插件的群消息分段。

V2 核心请求原先只提供聊天 Provider、输入能力和本轮材料，没有提供实际朗读 Provider 的配置。另一个缺口是语音策略经过触发条件或概率筛选后，本轮未触发的语音配置没有随 prepared 上下文保留。

## 修复

- 在真正的 `prepare_companion_core_request` 请求链中提供独立的 `chat_route` 与 `tts_route`，区分聊天模型和朗读引擎。
- 按实际语音渲染路径读取语种专用 Provider、插件指定 Provider 或 AstrBot 会话默认 TTS；提供已加载 Provider 的型号、语种和呈现配置，以及不可用原因。不请求音频合成，不提供密钥、接口地址或参考音色 ID。
- 保留已启用但本轮未触发的陪伴语音策略。区分陪伴语音启用、本轮触发及原生 TTS 开关，避免把陪伴本轮未触发说成原生 TTS 未启用。
- 固定表达规则仍留在 system；动态配置留在临时 user 材料，不写入历史，也不随型号变化改变稳定 system 前缀。用提示词引导模型据实回答配置，不用硬编码替换最终回复。

## 检验

使用 AstrBot 自带 Python 与真实 SDK，SDK 数据根在导入前指向临时目录。从新 ZIP 解包目录运行 13 项定向回归，覆盖真实主入口、配置准备、SDK 消息组装、私聊与群聊会话选择、语种覆盖、Drama 3、未触发语音、不可用 Provider、临时材料不落历史与动态配置不改变稳定前缀。13 项均通过。

新包宿主生命周期检查通过：自动启动、实际 SDK 入口加载、停机与路由注销；测试的模型调用和平台调用均为零。包校验覆盖文件哈希、Python 语法、唯一注册及唯一公开页面。完整报告放在 `D:/codex/artifacts/companion-v2-model-perception-20261019`。

真实模型探针从解包后的插件主请求钩子进入 AstrBot SDK Provider 请求，使用本机保存的默认配置及截图中的 DeepSeek v4.1 路由，在隔离会话内询问聊天模型和朗读模型。返回能够分别说明 `deepseek-v4.1-flash-expires-on-0910` 与 FishAudio 的 `s2.1-pro-free`，不再声称读取不到语音配置。

本机保存的默认 TTS 配置为 `fishaudio_tts2` / `s2.1-pro-free`；Drama 3 的覆盖使用真实 FishAudio 适配器配合测试配置，不代表当前默认 TTS 已改为 Drama 3。探针没有修改实际配置，没有执行发送工具、向 QQ 发消息或合成语音。本轮没有启动 Laya。

## 生效方式

交付包为 `D:/codex/artifacts/companion-v2-model-perception-20261019/release/astrbot_plugin_private_companion-7.0.0.zip`，准确文件哈希见同目录 `release-manifest.json` 和 `SHA256SUMS.txt`。构建快照位于插件扫描目录之外，保留原工作树已有修改及根目录开发临时文件；开发临时文件不打入插件包。

当前运行实例未执行热重载。安装交付包或在 AstrBot 重载该插件后生效。本次没有重新执行 V1 用户数据迁移；修复不修改 V1 数据。
