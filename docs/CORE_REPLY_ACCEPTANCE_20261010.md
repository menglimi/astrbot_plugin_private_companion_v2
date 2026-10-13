# 普通回复回归 AstrBot 核心管线：本次交付验收

2026-10-10。普通私聊和获准群聊使用 AstrBot 当前会话的模型、历史、工具循环、流式、装饰、分段、TTS 和平台发送。V2 补充背景、表达偏好和领域工具，观察工作在后台执行。当前路径说明见 [设计记录](V2_CORE_REPLY_PATH_DESIGN.md)。

## 源码阶段检查

- 核心回复、准入、原生工具、图片、原生发送、统计、后台观察及群回复：126 项通过。
- 模型页、治理页和回复页：95 项通过。
- 效率投影、热重载、会话目录、实际模型配置 API 和旧配置装配检查执行了 57 项。首次有一条测试因误引用局部变量 `bootstrap` 失败，修为 `self.bootstrap` 后该项单独复验通过；完整组合从下述新解包副本再次执行。
- 修改文本检查采用 UTF-8、无 BOM、LF、末尾换行，并检查 Python AST、JSON 和 diff 空白。

## 当前交付及独立结果文件

本次只构建 V2 本体，可选伴侣继续使用各自安装和能力提供方身份。

- 构建目录：`D:\codex\artifacts\companion-v2-core-reply-20261010-final`
- 本体包：`astrbot_plugin_private_companion_v2-2.0.0.zip`
- 解包验收目录：`D:\codex\artifacts\companion-v2-core-reply-20261010-final-verified-2`
- 包哈希和文件清单：构建目录的 `release-manifest.json`、`SHA256SUMS.txt`，以及包内 `RELEASE_FILES.json`。
- 宿主加载、停机、路由注销及迁移验收结果：解包目录的 `package-verification.json`。
- 解包回归结果：`D:\codex\artifacts\companion-v2-core-reply-20261010-checks\candidate-python-core.json`、`candidate-python-host.json` 和 `candidate-pages.json`，完整日志在同目录。

本文随候选源码构建，解包阶段是否通过以这些实际生成的结果文件为准。旧交付包、源码检查和历史记录不能替代新包验收。

## 验收范围

| 范围 | 检查行为 |
| --- | --- |
| 核心管线 | 真实 ProcessStage、ResultDecorateStage、RespondStage 保留正文、自然段、其他插件图片及原生流式；不进入旧 V2 普通回复批次。 |
| 原生工具 | 真实 ToolLoopAgentRunner 的工具续答、full/skills-like 模式、原始调用 ID；日历、关系、记忆、成长、天气、图片与表情使用真实领域 owner。 |
| 原生发送 | 真实 SendMessageToUserTool 和 Context；原窗口范围、撤权、平台未找到、异常未知、未知不重放、共享 Context 不被修改。 |
| 群回复 | 群参与与旁听、原发言者、后续发言、引用、工具直接发送、空流、媒体流、部分成功和错误阶段收尾。 |
| 后台观察 | SQLite 记录阻塞或失败时核心发送继续；同事件 FIFO 顺序；停机收尾；会话目录写入离开事件循环。 |
| 配置 | 实际窗口风格和拟人开关进入核心提示；附加提示和业务模板沿原 API 保存；回复页的正文处理、TTS、群引用/@与组件排序在核心发送前按本轮快照执行。 |
| Token | 核心、历史 V2、插件及合计各计一次；逐请求与汇总/末次用量分开；真实费用未知不填零。 |
| 缓存 | 仅 Provider 实报缓存量参与命中率；SDK 默认零不当实报；请求检测只保存结构摘要、哈希、长度和数量。 |
| 效率 | 首次及末次发送返回、生成时间、TTFT 和工具耗时分列；流式按真实时间排序，空流不算发送，汇总用量不伪造请求次数。 |
| 包及宿主 | 新解包副本的哈希、CRC、语法、唯一公开小屋；真实 SDK 加载、停机、路由注销、旧配置和迁移合成夹具。 |

Python 使用 AstrBot 自带运行环境。每个检查进程的 `ASTRBOT_ROOT` 指向临时目录，`PYTHONPATH` 包含当前被测副本和 `backend/app`；新包检查不导入工作树源码。

## 外部验证范围

本轮模型与平台 IO 使用本地替身，未调用生产 Provider、TTS 或图像后端，未发送真实 QQ 消息，也未读取或修改 V1 用户数据。实际 QQ 客户端显示、真实生产回复耗时和外部缓存回执仍需要在运行环境中观察，不能用本地通过数替代。

将当前本体重载后，普通聊天的模型、流式、分段、TTS、引用和 @ 在 AstrBot 中设置；小屋提示词目录仍可编辑 V2 实际生效的附加提示、风格与拟人模板。小屋页面资源带本次版本标记，以刷新旧缓存。
