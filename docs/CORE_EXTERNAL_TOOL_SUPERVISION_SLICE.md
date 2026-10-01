# CORE-02/08 外部工具独立监督与宿主目录映射

更新时间：2026-09-22。本切片在独立 V2 数据根内完成外部工具契约、受监督执行、原角色续答和 AstrBot 可信目录端口的映射。测试使用本地替身；真实 AstrBot 加载器、设备和平台尚未连接。

## 行为与边界

原角色可按问题选择已授权的拓展工具。能力安装须处于 active，当前固定包须与可信目录一致，指定 Bot/人格须启用，指定用户在完整会话范围内须有该能力的同意记录。还会检查公共身份策略、原账号绑定和原人格版本。`proactive_enabled` 与 `thought_weight` 不参与用户请求工具的准入，权重仍只用于多念头竞争。

首次打开模型会话时记录可用动作及目录摘要。工具执行时再检查当前权限；本轮未提供的工具即使随后被启用，也不能接受模型猜出的调用。内置工具和外部工具的动作名必须唯一，外部声明不能覆盖便签、来源或诊断 owner。

```text
可信宿主声明 -> 固定能力包 / provider 绑定 -> 当前会话可用目录
原角色模型请求 -> 持久调用屏障 -> 精确子任务 -> 外部 provider
                                          -> 原回执 + 受治理 SourceRef
原角色续答 <- 当前权限和原件重检 <----------+
          -> 逐段交付前重检 -> 已发历史读取时重检
```

## 代码入口

- [external_tools.py](../companion_v2/conversation/external_tools.py)：声明、provider、调用/响应契约、准入、调用账本、原件校验及回执核对。
- [AstrBot tools.py](../companion_v2/adapters/astrbot/tools.py)：`AstrBotToolPort`、可信声明和 `map_tools`。不导入 AstrBot，也不将任意宿主函数自动暴露给模型。
- [runner.py](../companion_v2/execution/runner.py)：队列 runner 与精确子任务 runner 共用超时、取消、停止证据和名额管理。
- [tool_loop.py](../companion_v2/conversation/tool_loop.py)：内外部目录去重、异步执行、原角色材料装配及脱敏观察。

组合顺序为：构造 `ExternalToolExecutor`（或 `map_tools`），将其 `registrations` 与消息/交付任务一起注册进同一个 `TaskSupervisor`，创建 `ConversationMessages`，调用 executor 的 `attach(messages)`，最后构造 `LocalRoleTools(messages, external=executor)`。停机时 await executor 的 `close()`；未停止的 worker 保留名额。

宿主端口只能接可信、支持取消的异步实现。每次调用带原 `TaskContext`，宿主从该上下文取身份、角色和路由，不从模型参数取这些信息。声明查询是有界同步读取；invoke 是异步调用。包、声明或 provider generation 变化会使旧绑定失效。

## 结果与恢复

每次外部调用占用独立前台子任务，最多尝试一次。父回复已占一个名额，因此当前实现需要另一个空闲前台名额；不足时返回明确失败并取消未派发的子任务，之后的队列扫描也不会偷偷执行它。精确领取不会顺便执行其他已排队任务。

只读成功返回 `succeeded/none`；副作用成功要求实际 `operation_id` 和 `receipt_ref`，返回 `succeeded/committed`。provider 明确未执行时以原回执证明 `failed/not_committed`。异常、超时、取消、回执不匹配或无法接受的材料保持 `unknown`，不自动重试或换 provider。同一调用编号只能复用原参数和结果；同一轮中也不能通过更换编号重做参数相同的未知调用。

响应必须对应原 invocation、会话摘要、参数摘要和 provider。成功正文由能力包声明的数据 owner 发布为精确 `SourceRef`，同时固定受众、内容摘要与版本；正文不复制到通用工具回执表。续答、交付和历史都重新检查原件有效期、撤权、授权、安装和 provider。失效原件不会被新一次读取替代。

实际回执可在撤权或取消期间补记，但任务不会因此自动复活。迟到返回的协程真正停止后才释放名额；`reconcile` 只接受已保存的原回执，在当前权限下修正停止后的未知子任务，不再次调用 provider，也不生成或发送消息。该入口属于可信宿主恢复路径，不向模型暴露。

重启后，完成的子任务及原回执可以重新核验。若子任务已完成而父工具投影尚未保存，以原子任务记录恢复读取；父模型任务仍遵守已有生成屏障，不能重开模型会话。没有原 owner/provider 的成功结果不能进入发送或历史正文。

## 有界输入与观察

当前源码在 2026-09-25 将模型目录统一为最多 64 项，内外部工具按当前原上下文授权筛选，详见[工具目录修复](CORE_TOOL_CATALOG_20260925.md)；本片最初的 32 项注册全集检查已被替换。每轮、每次回复的调用数仍遵守既有工具循环上限。参数使用封闭 JSON Schema 子集：显式类型、嵌套 object/array、required 和 enum，object 必须禁止额外字段；不支持的 Schema 特性在注册时拒绝，宿主须先规范化声明。现有参数、单结果和本轮材料字节上限继续生效，计数包含外部原件。

观察只展示注册动作、状态、effect、是否存在回执及子任务状态；不输出 provider 参数、私密正文、错误详情或原人格提示词。

## 存储与验证

内部 schema v12→v13 新增 `extension_tool_invocations`，关联父模型任务、调用、批次、子任务、固定声明/provider、参数、状态、效果、原操作/回执和结果来源。provider 范围内的 operation 与 receipt 不得被另一次调用冒用。旧版本指纹保持固定，非空升级、失败回滚、半迁移及未来表均检查。

新增测试见 [外部工具](../tests/test_external_tools.py)、[宿主映射](../tests/test_astrbot_tools.py) 和 [v13 迁移](../tests/test_external_tool_storage.py)，涵盖：

- 原角色读取/副作用续答、重复调用、未知调用不重放、原件过期/撤回与历史治理；
- 暂停/换包/丢弃、Bot/人格停用、精确用户撤权、账号换绑及跨 Bot/账号隔离；
- 公共身份授权与能力同意共同生效，主动开关/权重不影响用户请求工具；
- 无名额不派发、精确任务不消费旁支、取消与迟到 worker 的名额/回执核对；
- 重启保留原结果、缺失 owner/provider、来源/回执替换、材料超限；
- 宿主声明去重、禁止覆盖内置工具、声明撤载/换代；
- 非空 v12 数据升级、迁移失败回滚及 v12/v13 指纹拒绝。

本轮共新增 35 项测试。最后一次全量隔离回归为 **440 项通过（74.412 秒）**；`compileall`、UTF-8 与本地 Markdown 链接检查通过。所有执行、调用、发送和授权数据均为临时隔离夹具，不包含真实宿主或设备验证。

## 后续接入

后续已完成[宿主组合根、生命周期与自动输入合并](CORE_HOST_LIFECYCLE_AND_BATCHING_SLICE.md)，接下来完成真实宿主事件/provider/sender 字段适配。真实能力包下载安装、完整管理页、群聊/系统任务、阻塞或不可信拓展的进程隔离、任务归档和 V1 数据迁移仍按各自路线交付。本文 440 项为外部工具切片当时快照；当前结果不代表可以直接替换 V1。
