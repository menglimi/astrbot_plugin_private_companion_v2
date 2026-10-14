# 主链 TTS 与表情附件验收（2026-10-14）

## 实际问题与修复

- V1 的自动语音行为由开关与全局/私聊/群聊概率共同决定，旧迁移误读为仅请求时触发，并把继承概率 `-1` 转成 `-0.01`。组合迁移已修正；匹配这组错误结果的现场 V2 配置已备份后恢复为 `always / -1 / -1`。V1 用户数据未写入。
- AstrBot 在 LLM 请求 hook 前选择流式。语音与可用表情现在在准入时准备完整回复；语音协议独立注入系统提示，重复 hook 不重复追加，分段前保存朗读内容。日语朗读与中文译文替换仍保持对应关系。
- 主链可由模型选择隐藏表情意图，检索角色图库并发送可用原件；已有图片或本轮已经使用表情检索工具时避免重复附图。开关、概率、冷却、用户偏好和角色图库仍生效。
- 长语音按自然停顿拆成 Provider 请求，全部合成成功后再发送；合成失败保留正文。QQ 语音独立消息，表情按配置前置、后置或同条发送，GIF 不转静态图，QQ 表情格式保留 `sub_type=1`。
- AstrBot 原生发送工具使用同一媒体准备与授权链；逐条记录实际发送返回。已发前缀不重放，发送异常或未知结果不自动重试；新 SDK 将异常转成字符串时仍保留原始异常合同。
- 对话正文生成继续使用 AstrBot 主链，不计入插件模型预算；自动表情检索复用本域既有预算与授权流程。

## 已完成的源码与真实来源验证

使用 AstrBot 自带 Python、SDK 4.28.2、临时 `ASTRBOT_ROOT`，以下源码定向测试 **108/108** 通过：

```text
tests.test_core_reply_voice
tests.test_core_reply_reaction_delivery
tests.test_core_reply_native_send
tests.test_core_reply_pipeline
tests.test_main_core_reply
tests.test_astrbot_voice_reply.NativeVoiceProviderTests
tests.test_core_reply_owner_tools.CoreReplySemanticOwnerToolTests
tests.test_configuration_migration
```

覆盖真实 SDK ResultDecorate/Respond 分段管线、跨分段语音标签、日语与译文替换、长语音、原 GIF、QQ 表情格式、语音与表情联合发送、原生发送工具、关闭与拒绝偏好、空图库、权限撤销、部分发送失败及未知结果不重放。

真实 FishAudio Provider `fishaudio_tts2`，模型 `s2.1-pro-free`，通过 SDK 与 `NativeVoiceReply.render()` 合成日语，耗时 **1672 ms**，生成 **188460 字节**有效 RIFF/WAV。生成音频存于 `D:/codex/artifacts/companion-v2-tts-reactions-20261014/tts-japanese-preview.wav`。

只读校验已保存角色图库的 **241/241** 张启用 GIF，原件及动画帧哈希均通过；源图库数据库未修改。

## 新交付包验证

从当前源码构建自包含插件包，输出目录为 `D:/codex/artifacts/companion-v2-tts-reactions-20261014/release`。解包目录为同产物根下的 `verified`，使用该目录运行包内测试，`PYTHONPATH` 仅含解包候选与 `backend/app`，避免工作区源码补足漏打包模块。

包验收执行 `tools/verify_v2_release.py --host-check`，检查文件哈希、语法、唯一公开页、单 Star、七项原生内部能力、迁移合同、宿主加载与停机、路由注销；再从候选包运行上述 TTS/表情定向测试。实际结果分别以 `verified/package-verification.json` 和 `candidate-tests.json` 为准，最终包哈希以 `release/release-manifest.json` 与 `SHA256SUMS.txt` 为准。

现场通过正式 `/api/v1` 插件重载接口应用修复，重载及保存配置核验结果单独存于产物目录，不包含认证密钥。

## 验证边界

本轮真实外部调用为 TTS 合成；平台发送定向用例使用测试替身，没有向 QQ 或真人发送测试消息。真实合成与原件校验不能作为线上 QQ 已送达证明。新包定向验证不替代全量测试树。

完整配置备份可能含凭据，仅保留在插件扫描目录外的本地产物目录；不放入插件包，不展示其内容。
