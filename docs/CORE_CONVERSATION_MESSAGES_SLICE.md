# CORE-08/CORE-02：持久输入、异步原角色回复与逐段回执

日期：2026-09-22。沿[本体功能路线](V1_CORE_FEATURE_PREREQUISITES.md)第 3 步，在[任务监督器](CORE_TASK_SUPERVISOR_SLICE.md)和[模型网关](CORE_MODEL_GATEWAY_SLICE.md)之上完成消息公共链的首批本地切片：显式输入合并、撤回/取消关联、异步原角色生成、顺序分段发送及已确认发送历史。本页记录该首批切片完成时的 v11 状态；当前 schema 已由后续的[原角色工具多轮续答切片](CORE_ROLE_TOOL_LOOP_SLICE.md)升至 `companion-v2.storage.v12`。

验证使用可信本地异步模型/发送替身、合成身份和临时 SQLite。没有加载 AstrBot、读取 V1 数据、调用真实模型或发送平台消息。现有同步 `ForegroundConversationKernel` / `LocalModelTransport` 保留，新链复用上下文装配和证据提示词组件；宿主尚未切换到新链。工具多轮续答的后续实现和边界见[工具续答切片](CORE_ROLE_TOOL_LOOP_SLICE.md)。

## 1. 当前链路与装配

| 阶段 | 入口与责任 |
| --- | --- |
| 受理与合并 | [ConversationMessages.accept](../companion_v2/conversation/messages.py)复核当前账号、完整私聊路由、人格和权限，持久保存原入站事件及资料引用。可信调用者显式指定同一开放批次，才能合并连续输入。 |
| 封存与排队 | `seal` 固定有序输入清单、资料引用和角色提示词，并在同一事务内提交 `conversation.reply` 任务。重复提交保持原任务，不能改写原输入、资料或截止时间。 |
| 异步生成 | [LocalReplyGenerator](../companion_v2/conversation/generation.py)从原 `TaskRun` 调用模型网关，保留原角色和资料；生成后复核当前授权、原输入及模型声明的依据，再原子保存分段正文和清单摘要。 |
| 分段发送 | [LocalConversationDelivery.queue_next](../companion_v2/conversation/delivery.py)只排入下一未完成段，支持 `not_before` 保留分段间隔。每段拥有独立任务和原操作号，前段确认送出后才继续。 |
| 回执与历史 | `record_receipt` 记原段的可信回执；只有 `delivered` 才写入 `conversation_sent_history`，同一段最多归档一次。`history` 按原会话/账号/人格分页读取。 |

装配时共用同一 `TaskSupervisor`、`StorageRuntime`、配置服务和模型网关，登记 `conversation.reply` 与 `conversation.deliver_part` 两种任务，分别连接 `validate_generation` / `validate` 及 `generate` / `deliver`。发送任务必须声明 `MESSAGE_DELIVERY`、固定 sender binding 和单次尝试。可运行装配见[消息测试夹具](../tests/test_conversation_messages.py)，不依赖真实宿主。

输入正文仍由 SourceRepository 管理，批次只保存引用和原输入摘要。每次使用重新检查原件版本、时效、受众与授权；合并输入也逐条检查摘要。已就绪的附加资料须有可重读的原件，调用者传来的旧正文不会写入批次。`DEFERRED` 维护材料保持待处理，前台不会等待无关维护任务完成。

当前每批最多 32 条输入、32 份附加资料；可信分段策略返回 1 至 64 段非空正文，总长不超过 65536 字符，拼接后必须与原草稿完全相同。默认单段，具体分段体验由后续适配器提供。资源上限和发送状态用于技术一致性，不代替模型的角色表达判断。

## 2. 撤回、取消与原角色

| 变化 | 已验证的本地行为 |
| --- | --- |
| 封存前撤回一条输入 | 保存撤回墓碑，剩余输入保持原顺序；重启或重复入站不能复活该事件。 |
| 生成期间撤回/取消，或资料撤权、过期、换绑、人格切换 | 后续复核使原结果失效，不生成可发送的分段；已经发生的模型用量保留。 |
| 分段之间撤回/取消 | 已送出部分保留原事实，待发送部分停止；发送中的效果继续等待原回执。 |
| 人格切换后撤回旧输入 | 当前人格上下文可办理撤回，但必须仍是原账号绑定、原作者和原路由；不能借换绑撤回另一主体的消息。 |
| 读取已发历史时原资料失效 | 保留发送事实，正文返回不可用；不会用新资料替换原依据。 |

撤回的依赖粒度目前是整个已封存批次，尚不支持按语义片段重写或在部分已发后自动生成替代回复。这里的墓碑只治理 conversation 输入与依赖的未发回复，不会全局撤销 SourceRepository 原件，也不等于完成画像、日记、学习规则等跨领域遗忘/删除。

事实检查复用 `GroundedDraftReviewer`，验证草稿显式声明的依据是否属于原封存材料；它不能检测所有未声明的虚构事实。原模型继续通过证据提示词理解资料、表达不确定性，本轮没有增加一次额外模型复核或自动改写调用。

## 3. 发送结果、迟到回执与恢复

进入 sender 前，在同一事务中复核原任务和来源、记录效果边界、预留原操作，并把该段标为 `dispatched`，随后才执行异步发送。该链不另写通用 outbox，避免同一段被两条发送路径消费。

| 原 sender 的结果 | 后续行为 |
| --- | --- |
| `accepted` | 只表示受理，任务保持待核对，正文不进入已发历史，下一段不能发送。 |
| `delivered` | 需要原平台引用与实际送出时间；同事务记原回执、完成状态和已发历史。当前证据仅来自本地替身，不证明用户已读。 |
| `not_sent` | 明确未送出，记失败；不自动重试同一段。 |
| `unknown`、异常、超时或取消 | 保留未知效果，不能推定未送出并重新发送；后续段等待原结果。 |
| 重启前已派发但未拿到结果 | `recover_dispatches` 将失联发送保留为 unknown，不重放。旧 worker 的停止与名额释放仍按监督器处理。 |
| 撤权或取消后收到可信迟到回执 | 按原段补记事实，不重读失效资料，不复活生成任务，不自动排入下一段。 |

回执核对原段、操作、会话身份、正文摘要、完整 sender binding、平台引用和送出时间。相同回执幂等，原回执身份不能更改结果，已确认结果不能被冲突回执覆盖。`record_receipt` 是可信 adapter 的内部入口，不是用户/模型工具，也不授权新发送。

`reconcile_task` 只把已知原回执关联到确认停止的 uncertain 任务；仍活跃的 worker 不得被对账覆盖。原操作账本与回执同步记录 accepted/unknown/completed，但通用账本的本地 commit 不能单独证明消息已送出。平台认证、自动查账轮询与真实发送适配器仍待接入。

## 4. 诊断与存储

[DiagnosticService](../companion_v2/diagnostics/service.py)的 execution 检查升至版本 4，可选接同一监督器下的 `ConversationMessages`。按精确生成/发送任务显示批次、输入/撤回数量、各段状态、派发/送出时间和已确认/待核对段数。任一段未决则保持 unknown，正文、提示词、平台消息号和原回执号不出现在诊断中。

sender 只有存在本地发送任务时才标为 `local_test_adapter`，实际阅读状态保持 unknown。已记录的分段间隔和本地模型等待可以成为诊断依据，但尚无真实用户首句延迟的测量结果。

内部 v10→v11 升级新增 `conversation_batches`、`conversation_inputs`、`conversation_parts`、`conversation_delivery_receipts`、`conversation_sent_history` 五张表及索引。[升级实现](../companion_v2/storage/runtime.py)保留原 v10 DDL/指纹，逐版本检查，事务内完成新表与版本提交；非空旧账、未知用量和预留继续保留，失败可整体回滚。后续 v11→v12 的模型轮次、来源句柄和工具回执迁移见[工具续答切片](CORE_ROLE_TOOL_LOOP_SLICE.md)。

这是 V2 内部数据库格式升级，不是 V1 插件用户数据自动迁移。任务/批次/回执的长期保留和归档尚未接入，不能将当前有界本地 profile 直接用于持续生产运行。

## 5. 验证证据

本轮新增 **31 项**测试：

- [消息链](../tests/test_conversation_messages.py)：27 项，覆盖合并输入与原角色、延后维护、撤回/取消、分段间隔、部分发送、回执去重/冲突、已发历史分页、超时/重启、迟到回执、worker 停止、多连接争抢、事务回滚、过期/撤权/换绑/人格切换、多 Bot 同号事件隔离和诊断脱敏。
- [v11 内部升级](../tests/test_conversation_storage.py)：4 项，覆盖非空 v10 未知账务保留、历史指纹、失败回滚/重试、半升级及更改原指纹的拒绝。

定向复核 31 项通过；**207 项**是本首批消息链的历史回归证据，不与后续工具续答测试相加。当前汇总和最新全量结果见[构建状态](BUILD_STATUS.md)。

```powershell
python -X utf8 -m unittest tests.test_conversation_messages tests.test_conversation_storage -q
python -X utf8 -m unittest tests.test_conversation_messages tests.test_conversation_storage tests.test_model_gateway tests.test_model_storage tests.test_execution tests.test_execution_runner tests.test_execution_diagnostics tests.test_storage_runtime tests.test_storage_migrations tests.test_configuration_storage tests.test_agenda_storage tests.test_object_access_storage tests.test_scope_storage tests.test_persona_storage tests.test_diagnostic_storage tests.test_execution_storage tests.test_management_access tests.test_diagnostics tests.test_diagnostic_repairs tests.test_diagnostic_tools tests.test_foreground_conversation tests.test_conversation_scope_and_role tests.test_isolated_conversation tests.test_isolation -q
python -X utf8 -m compileall -q companion_v2 tests
```

## 6. 下一段与剩余责任

原角色工具多轮续答已在后续切片完成：便签/提醒、精确来源读取和诊断结果现在关联到原消息任务，并复用权限、预算、取消状态和原角色配置；工具结果与最终已发内容分别记录。实现细节、v12 迁移和剩余外部 adapter 责任见[工具续答切片](CORE_ROLE_TOOL_LOOP_SLICE.md)。

后续还需自动入站防抖/调度、媒体与合并转发、群路由、流式生成、按语义依赖修订、跨领域遗忘、长期归档、公共 wire 适配及真实宿主/provider/sender。V1 选模规则、软预算、关系记忆、连续生活、主动偏好、管理页和自动迁移继续按既定路线推进。本轮不可据此接管生产对话或直接替换 V1。
