# 2026-10-10 真实场景验收记录

本轮目标是按真实使用路径验收当前源码构建的 V2 包。测试优先使用 AstrBot 自带 Python、真实 SDK 消息类型、插件生命周期和 OneBot 反向 WebSocket 编码；外部 QQ、生产模型和生产 TTS 未在本轮发送或调用。

## 交付包

- 8 包输出：`C:\Users\99505\.astrbot\releases\companion-v2-real-acceptance-20261010`
- 解包验收：`C:\Users\99505\.astrbot\releases\companion-v2-real-acceptance-20261010-verified`
- 核心包：`astrbot_plugin_private_companion_v2-2.0.0.zip`
- 核心包 SHA-256：`39b6ba7c7bbd4cf6e7c9adcb03cce49f9c68375ba6ba23205a14c05081dcd483`
- 核心包 1,854 个文件，唯一公开页为「陪伴小屋」；默认关闭；正式投递默认 `onebot_private`。

`tools/verify_v2_release.py --host-check` 通过：哈希、CRC、Python 语法、唯一公开页、AstrBot 宿主加载/停机、4 条生活路由注销、自动启动检查、模型会话发现、原生回复开关、天气路由和隔离数据根均通过。宿主检查中的模型调用和平台调用均为 0。

## 解包包回归

使用 AstrBot 自带 `backend\python\python.exe`，`ASTRBOT_ROOT` 指向临时目录，`PYTHONPATH` 同时包含解包本体和 `backend\app`：

| 套件 | 结果 | 覆盖 |
| --- | --- | --- |
| 动画宿主 | 4/4 | GIF/APNG/WEBP 抽帧、转发引用归因、停止时不落库不投递 |
| 群图工具 | 13/13 | 群工具目录、权限、图像结果、公共记忆查询、撤权与历史失效 |
| 原生图片投递 | 13/13 | 双账号、原图/转发/引用、分段、TTS 失败回退、未知 ACK 阻断后续图片、重启不重放 |
| 群 OneBot 投递 | 3/3 | 真实 AstrBot 群事件、精确账号/群号、反向 WebSocket ACK、失败/超时保持 unknown |
| 群参与 | 19/19 | 被提及、旁听、静默、插话、投递回执与撤回边界 |
| Laya 合同 | 通过 | 合同字段、跳过机器人引用、私聊不暴露 interject |
| 插件重载 | 通过 | PluginManager 生命周期、路由不重复、停机清理 |

以上合计 53 项通过。消息生成、正文处理、分段调度、TTS 降级、图片素材封存和本地 OneBot 帧均实际经过宿主路径。动画测试的旧 `preview` 断言已改为当前正式投递回执；群图测试的旧 `group.memory.legacy.query` 断言已改为在无 legacy 服务时确认该工具不进入目录。

## Laya 实测结论

此前使用 AstrBot 环境和 Laya 0.4.0 权重做的重复输入测试保留以下结论：

- 明确的“我还没说完/请等待补充”稳定得到 `unfinished / wait`。
- 明确的“不用回复/只记一下”稳定得到 `silent`，但 `turn_state` 仍有 `unfinished` 误判。
- 普通完整问题（例如日食、巴黎首都）仍会被判到 `unfinished / clarify / reply_form` 缺省路径，且偶尔错误给出 `tool_need=tts`。
- 机器人消息引用已经在规则层跳过 Laya，不调用决策模型。

因此 Laya 目前可作为“是否等待、是否沉默、分段形式和表达提示”的分类器，但完整问题分类尚未达到可放行标准；本轮没有把这些误判隐藏在总通过数中。

## 日志发现

开发者追踪已能输出事件事实、Laya 决策、回复提示词摘要、模型原始回复摘要、正文处理阶段、分段结果和投递回执。媒体合成事件会出现一次可选习惯/相识派生记录的 `TaskError` 警告；它被隔离在可选观察器内，不阻断入站、模型生成或投递。群撤回/失效注入中旧任务出现 `group_input_unavailable`，随后保持失败且不发送，这是预期的安全结果。

## 尚未等同于外部实测的部分

- 没有连接真实 QQ/NapCat OneBot，也没有向四个群发送消息；本轮 ACK 由本地 reverse-WebSocket 测试 socket 生成。
- 主回复模型、TTS、图像后端由测试提供方或隔离替身提供，未调用生产凭据或外部服务。
- 迁移验收中的 70 项是迁移合同和合成 V1 夹具；本轮没有读取或写入现役 V1 用户数据，因此不能把它写成真实数据迁移收据。
- 图片、TTS 和群路径真实经过 AstrBot SDK，但真实 QQ 客户端显示、真实网络断连和生产服务耗时仍需单独记录。

后续进入外部阶段时，应先使用独立测试账号和明确的 QQ 投递授权，逐条记录真实 message ID、OneBot 回执、模型/TTS 服务版本和时间，再补写本记录对应的外部证据。
