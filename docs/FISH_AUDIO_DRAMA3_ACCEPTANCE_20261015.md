# Fish Audio Drama 3 适配

2026-10-15，对照 [Drama 3 官方产品页](https://fish.audio/zh-CN/drama-3/)、[Drama 3 文档](https://docs.fish.audio/features/text-to-speech/drama-3)及 [TTS API](https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech)。

## 实现

- 使用官方模型 ID `drama-3`，列在模型页语音 Provider 的模型选项首位；更新、克隆与已有配置共用原生 Provider 管理流程。
- 官方沿用 `POST /v1/tts`、`model` 请求头、原 `reference_id` 及 JSON/MessagePack 请求。AstrBot 4.28.2 的 FishAudio 适配器已支持这一契约，因此继续调用它的 `get_audio`，不修改宿主 SDK，也不重写一个发送客户端。
- 只有实际选中的已加载 FishAudio Provider 使用 Drama 3 时，才为本轮主链及同主链朗读格式整理补充表演提示。按角色语气和对话选用方括号自然语言指令、声音与停顿，以及 `<whisper>`、`<emphasis>`、`<soft>`、`<fast>`、`<slow>`、`<stress>`、`<forceful>`。
- 控制语法仅在朗读片段内部参与显示清理，普通正文和代码中的同名标签不变。合成原文保留控制指令；可见文字、仅语音模式的文字比较、送达历史使用无控制语法的朗读原文。
- 长句按实际朗读字符与自然停顿分块，分块和核心回复分段都重新闭合并恢复仍生效的局部标签。方括号指令作为整体保留，不把指令内部的逗号当成句子停顿。
- 真实接口返回的流式 WAV 使用占位数据长度 `0xffffff00`、RIFF 长度 `0xffffff24`。读取音频后，只对这一流式标记及标准 `0xffffffff` 标记按实际字节数补全长度；PCM 内容不变，不写回 Provider 原音频文件。平台语音和模型页试听共用该读取流程。
- 保持已有模型、声线、语言绑定、概率、授权及配置；不批量切换线上 Provider。未新增插件后台模型调用，表演提示仍在 AstrBot 主回复链。

## 验证方法

定向测试覆盖模型配置保存、错误模型名拒绝、实际已选 Provider 的能力提示、核心请求与同主链整理、可见正文及译文清理、嵌套局部标签分块与原生 MessagePack 请求的精确 `model` 请求头。使用 AstrBot 自带 Python，从新交付包解包候选运行，宿主数据根指向临时目录。

真实验证使用 `tools/verify_fish_audio_provider.py`：只复制现有 Provider 配置到本地测试实例，并覆盖该副本的模型字段。音频保存到外部验收目录，不向平台发送消息，不写回配置。真实调用结果以对应 `fish-audio-probe.json` 为准。
