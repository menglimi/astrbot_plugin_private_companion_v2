# V2 回复语音配置与组合预览

日期：2026-09-26。陪伴小屋的「表达」工作区已接入语音设置，与流式、分段及图片位置一同保存到当前私聊对象、角色和会话范围。此批为源码交付；在线插件需要先加载新版代码，之后在小屋保存语音配置不需要重载。

## 当前行为

- 支持语音启停、触发方式、正文或模型标签、首段/末段/每段、文字与语音或完整覆盖时仅语音、组件位置、中日英及外语文字模式。
- 可设置通用与各语种 TTS Provider、触发概率、冷却、字数上限、超时、关键词和表达提示词。目录只公开 AstrBot Provider ID；音色和凭据仍由 AstrBot 提供方配置管理。留空跟随原会话的 AstrBot TTS；没有读取 V1 配置或用户数据。
- 输入批次封存时一次性固定语音、流式、分段与图片位置。工具续答和逐段投递使用同一份配置，过程中保存新值不会改变本轮。旧快照未记录语音字段时沿用宿主策略；新快照始终包含语音字段。
- 单目标及多目标宿主均持有惰性语音适配器，宿主启动时关闭语音也可从页面开启。无候选朗读时不调用 TTS。没有对象覆盖值时保留宿主私聊/群聊概率默认值；本页仅开放已有的私聊管理入口。
- 离线预览复用正式标签处理、分段、候选朗读和组件计划，支持末段 0 至 8 张图片，分别展示合成成功与未触发/失败后的顺序。它不请求模型、合成音频或发送消息，也不预测真实触发概率、冷却和客户端效果。
- `voice_only` 只在合成成功且朗读完整覆盖可见文字时隐藏文字；部分朗读及合成失败保留图文。模型语音标签不出现在预览正文。
- 新生成的每段回复记录语音候选原因、TTS 合成结果、实际组件顺序和文字是否隐藏；管理页同时展示独立的分段投递回执。未发送的后段仍显示待处理，QQ 回执未知时不推断为已送达，也不自动重发。历史段不回填，页面明确显示「语音诊断未记录」。存储迁移为 v35，保留已有的 v34 官方预警迁移。
- 保存沿用版本检查与持久操作键。响应丢失时核对原操作；切换对象不会串用草稿或回执。提供方目录暂不可用不阻断配置读取，已保存但缺席目录的 ID 仍保留并标注。

修复了诊断接口在输入收集阶段读取 `contributions_json=[]` 时按对象访问导致的错误。此时 `captured` 为 `null`，页面显示「尚未固定配置」；历史缺快照记录另行标示。

## 验证

使用 AstrBot 自带 Python、安装的 SDK 和临时 `ASTRBOT_ROOT`；模型、音频及 OneBot 传输均为合成替身。定向范围共 **55 个测试**：首轮 52 通过，修复上述诊断错误及两处新测试夹具/断言后，失败的 3 项全部复验通过。未将复验重复计数。

组合场景在同一条流式工具续答链中覆盖：宿主初始关闭语音、管理设置开启并指定 Provider、封存后修改配置、三段回复与两张逆序图片、第二段 TTS 失败、段间重启恢复，以及下一轮关闭语音。另覆盖未知 ACK 停止后段、单/多宿主热启停、对象隔离、身份验证、目录只读、幂等保存、旧快照和路由注销。

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2;C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest `
  tests.test_astrbot_staging_host.AstrBotStagingHostTests.test_hot_reload_stops_before_storage_close_and_unregisters_owned_routes `
  tests.test_reply_management tests.test_reply_web_api `
  tests.test_segmented_stream_delivery tests.test_segmentation_host_settings `
  tests.test_voice_reply tests.test_delivery_components tests.test_astrbot_voice_reply `
  tests.test_astrbot_reply_streaming `
  tests.test_astrbot_multi_host.MultiHostTests.test_dashboard_routes_bind_each_target_memory_api_and_unregister_cleanly
```

浏览器使用实际 SDK iframe bridge 与合成 API，回复工作区的 **4 组组合检查通过**：日语候选朗读/双图/降级预览、丢失保存响应后的跨对象核对、配置冲突及不可用 Provider 保留、1440/390/320px 布局和移动端保存后重载。浏览器与夹具服务均无错误。窄屏和桌面语音主控/细节截图已人工检查。

```powershell
$env:NODE_PATH = 'C:/Users/99505/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
& 'C:/dev/nodejs/node.exe' tools/check_product_page.cjs build/reply-voice-20260926 'C:/Users/99505/.astrbot/backend/app/astrbot/dashboard/plugin_page_bridge.js' --reply-only
```

结果与截图位于忽略目录 `build/reply-voice-20260926/`。此参数只验证回复工作区，不代表整个小屋导航或全部能力已验收。

逐段语音诊断补齐后，使用同一 AstrBot Python 又完成 41 项存储迁移、语音决策、管理查询和 OneBot 定向测试，以及 11 项流式组合与管理 API 测试。组合测试逐段核对工具续答、双图、第二段无音频降级、段间重启、未知 ACK 停止后段和下一轮关闭语音的诊断与回执状态。页面构建清单已同步，`tools/sync_framework_page.py --check` 无差异；回复工作区浏览器 5 组组合检查通过，浏览器和夹具服务均无错误，并检查了桌面与 320px 截图。新报告和截图位于忽略目录 `build/reply-voice-diagnostics-20260926/`。

## 边界与下一步

本批未重载在线插件、调用真实 TTS/模型或向 QQ 发送，也未更新已有安装包。当前流式仍是完整接收和校验后逐段发送，不提前发送半段正文。真实音频格式、延迟和 QQ 混合组件表现仍待现场验收。

下一步在新版 V2 插件加载后，用一次真实 TTS/QQ 对话联合核对分段、双图、外语语音和输入中状态，并对照小屋的逐段诊断确认合成状态与 QQ 回执。主动语音、独立文本转换、MiMo、Fish 专有情绪与本机播放不属于本次被动回复设置范围。
