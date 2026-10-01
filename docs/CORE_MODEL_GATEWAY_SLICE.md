# CORE-08/CORE-02：本地模型网关、配置来源与用量账本

日期：2026-09-22。按[本体功能路线](V1_CORE_FEATURE_PREREQUISITES.md)第 3 步，在[持久任务监督器](CORE_TASK_SUPERVISOR_SLICE.md)上接入首批模型基础：按任务选择本地提供方、保留原角色与资料、记录配置采用、原子预留 token/费用，以及按回执结算和诊断。本轮新增 31 项测试，最后一次受影响回归 179 项通过，编译通过。

后续更新（2026-09-22）：[消息公共链](CORE_CONVERSATION_MESSAGES_SLICE.md)已接持久输入合并/撤回、复用前台装配与证据提示词的异步生成、逐段本地回执和已发历史；内部 schema 进入 v11，execution 诊断检查升至版本 4，207 项受影响回归通过。以下保留本模型切片交付时的 v10、179 项回归和当时待办；当前下一段为原角色工具多轮续答，状态以[构建状态](BUILD_STATUS.md)为准。

验证仅使用可信本地异步替身、合成身份和临时 V2 数据库，没有调用真实模型、加载 AstrBot、连接平台或读取 V1 用户数据。现有同步 `ForegroundConversationKernel` / `LocalModelTransport` 尚未改接新网关；通过的是 runner 处理器调用网关的本地链，不是主对话、自动工具循环或真实发送已经接通。

## 1. 当前链路与职责

[LocalModelGateway](../companion_v2/model_gateway/service.py)与任务监督器、配置服务、预算账本共用同一个 StorageRuntime。

1. 原任务复核完整身份、原角色、输入和权限后，[ModelRouter](../companion_v2/model_gateway/routing.py)读取任务字段组，确定提供方、提示词和输出上限，在同一事务内记录采用回执及原 plan。
2. 可信本地 adapter 根据请求估算预留上限。[BudgetLedger](../companion_v2/model_gateway/budget.py)在写事务中逐层检查预算、预留额度并持久记录 dispatch，然后才进入异步提供方。
3. [LocalTaskRunner](../companion_v2/execution/runner.py)负责总截止时间、取消和停止；网关沿原 task/attempt 记录调用结果，用量不明时保留预留。
4. 回执到达后先按原账户结账，再复核任务、输入、身份、角色和配置消费者代次。失效草稿不能继续使用，已发生用量仍须保存。
5. 返回 `ModelCompletion` 仅表示草稿及账务状态。网关不发送消息，不将草稿写成已发表达；逐段实际发送和历史归档属于后续消息公共链。

一个任务保存一份原 plan，最多包含主提供方和一个显式备用提供方。已有 plan 的任务不重新生成；失败、重启或改配置不能绕过原调用记录。后续工具多轮调用需要正式的子任务/调用关联，不能直接循环复用这个单轮入口。

## 2. 原角色、配置与采用

[ModelEnvelope](../companion_v2/model_gateway/models.py)保留完整原 `PromptRequest`，任务提示词单独附加。原角色提示词、原回复指令和原资料不会被任务提示词覆盖；语义理解与表达继续由原角色模型完成。

| 项目 | 当前行为 |
| --- | --- |
| 字段与消费者 | 每种任务登记 `model.<kind>.provider`、`fallback`、`prompt`、`max_output_tokens`，消费者统一为 `model_gateway`，生效边界为 `NEXT_TASK`。 |
| 配置继承 | 安装、Bot 内角色、完整窗口逐层继承，复用公共配置服务和权限。相同人格 ID 在不同 Bot 中的覆盖互不串用。 |
| 显式值 | 空提示词是显式清空，空备用字段是停用备用；恢复继承需显式 reset。未知 provider、重复备用或输出超出 adapter 能力会报告错误，不暗换默认值或静默截小。 |
| 提供方能力 | 调用前校验任务要求的能力与输出上限；提供方绑定保存 capability/provider/version/generation。当前只是可信本地 adapter。 |
| 当前与后续任务 | 已采用 plan 不因普通配置编辑而改变；新任务读取新配置。消费者重启换代会阻止旧 plan 的继续调用和结果使用。 |
| 原任务依据 | 保存配置来源层、显式状态、来源 revision、resolution token、角色 revision、请求/提示词摘要和原 provider binding。账本不保存提示词、资料或回复正文。 |

`ModelTaskProfile` 和 `LocalProvider` 由可信运行时登记；登记不是模型工具权限。资料是否有效和当前可用由原任务的领域输入校验器复核。同步估算和输入校验必须可信且有界，本轮不提供阻塞代码或不可信插件的进程隔离。

本轮接入统一配置的是路由、任务提示词及输出上限。`BudgetPolicy` 仍由可信运行时提供固定配置，没有额度管理页、用户调参工具或完整软预算提示。

## 3. 预算、回执与恢复

`Amount` 明确区分整数 token 与百万分之一美元 `cost_microusd`，不接受浮点数、布尔值或按数值猜测单位。实际用量与调用前预留分别保存；模型生成成功不证明费用已知。

| 范围 | 当前额度归属 |
| --- | --- |
| installation | 同一安装共用。 |
| bot | 同一安装内的 Bot 共用。 |
| role | 同一 Bot 内角色共用，不跨 Bot 混账。 |
| window | 完整安装/平台/Bot/账号/会话 scope，不含当前人格；换人格不会刷新窗口额度。 |
| background | 后台额外受安装级总上限限制，仍同时受前四层约束。 |

以上账户固定使用原 plan 创建时的 UTC 日期。逐层预留在同一写事务完成，token 或费用任一不足都整体回滚；双连接争抢最后额度不会出现部分占额。同一日修改策略不能偷偷重置消耗，当前返回策略冲突，正式调整路径仍待接入。后台总上限提供安装级控制，不代表每个 Bot/角色/窗口都已经拥有独立前台保留额度。

| 结果或中断 | 账务与后续行为 |
| --- | --- |
| 有草稿、有实际用量回执 | 保存实际用量并释放对应预留；实际超额照实记录，后续准入使用真实消耗。 |
| 有草稿、用量缺失 | 可以返回仍有效的草稿，用量保持 unknown，原预留继续保留。 |
| 明确未处理请求 | 必须附明确零用量与回执，才可尝试配置中的一个备用提供方；备用也重新检查原任务、消费者及额度。 |
| 异常、取消、超时或处理结果未知 | 不推定零费用，不自动调用备用，不重新生成原任务。 |
| 撤权、换绑、切换人格、原输入过期或消费者换代 | 迟到用量仍结算，草稿标为 discarded，不能作为有效回复继续使用。 |
| 重启前仅 reserved、从未 dispatch | 当前监督器依据本地从未派发记录释放为零，不实际重试调用。 |
| 重启前已经 dispatch | 处理结果改为 unknown，预留保留，等待可信 adapter 提供原回执。 |

`reconcile_usage` 是可信 adapter 的补账入口，校验完整 provider binding，可在撤权或重启后结算原账；它不是用户工具，也不安装草稿。相同已结算回执幂等，不同用量/回执冲突；后到的缺失用量不能覆盖已对账记录，补账不能复活 discarded 草稿。

这里的备用是有限的技术调用恢复。V1 的按关系选模型、用户规则换模、拒答后换模和余额关注仍是待实现的兼容责任，没有被此备用规则替代。

## 4. 诊断与存储

[DiagnosticService](../companion_v2/diagnostics/service.py)的 execution 检查升至版本 3，可在原任务投影中展示 provider、配置来源、预留/实际用量、超预留标记和调用等待时间。诊断继续沿原 scope、账号、角色、受众与当前权限读取；输出不含提示词、原资料、回复正文或原回执号。

调用耗时的依据是 `local_wait_until_receipt_or_interruption`，仅表示本地开始等待至收到回执或中断，不是用户首句延迟。任一调用用量未知时，诊断保持 unknown，即使本地任务已 succeeded。提供方明确标为 `local_test_adapter`，sender 仍为 `not_connected`。

内部 schema 升至 `companion-v2.storage.v10`，新增 `model_requests`、`model_budget_accounts`、`model_calls` 和 `model_call_accounts`，保存原 plan、预算账户、调用/回执及原账户关联。[升级实现](../companion_v2/storage/runtime.py)保留独立 v9 DDL 和指纹，验证非空升级、失败回滚、半升级拒绝及历史版本升级。这是 V2 内部格式升级，尚未实施 V1 用户数据自动迁移。

## 5. 验证证据

本轮新增 **31 项**测试：

- [模型网关与预算](../tests/test_model_gateway.py)：28 项，覆盖原角色/资料保持、配置来源/采用、Bot/角色隔离、费用与 token 限额、双连接竞争、有界备用、用量未知、撤权/过期/取消/超时、迟到结算、消费者换代、重启恢复和诊断脱敏。
- [v10 存储升级](../tests/test_model_storage.py)：3 项，覆盖非空 v9 升级保留原未知操作和旧指纹、升级失败回滚，以及半升级/指纹不符拒绝。

最后一次受影响回归 **179 项通过（23.400 秒）**，编译通过。包含既有任务、配置/权限、诊断/建议/原角色答疑、内部存储升级及隔离检查。早期批次与此批重叠，不累加为总数；本轮未重跑全部框架测试。

```powershell
python -X utf8 -m unittest tests.test_model_gateway tests.test_model_storage tests.test_execution tests.test_execution_runner tests.test_execution_diagnostics tests.test_storage_runtime tests.test_storage_migrations tests.test_configuration_storage tests.test_agenda_storage tests.test_object_access_storage tests.test_scope_storage tests.test_persona_storage tests.test_diagnostic_storage tests.test_execution_storage tests.test_configuration tests.test_management_access tests.test_diagnostics tests.test_diagnostic_repairs tests.test_diagnostic_tools tests.test_isolation -q
python -X utf8 -m compileall -q companion_v2 tests
```

## 6. 下一段与剩余责任

下一段继续第 3 步的消息公共链：将现有前台核接入异步任务/网关，接输入合并、撤回与取消关联、原角色工具续答，再建立逐段实际回执及只归档已发历史的接口。先用本地发送替身验证部分成功、取消、重启和多 Bot/角色隔离，保留分段体验；实际用户延迟须到宿主及真实 provider 接入后测量。

CORE-08 后续还包括 provider 冷却/速率治理、软预算、父子任务预算、部分用量、非 USD 换算、正式额度调整、任务/账本归档及自动调度。关系/用户规则选模、拒答后换模和余额关注需要兼容映射；群聊/系统任务、公共 wire 适配和真实 provider/宿主也未接入。

当前完成的是模型基础的首批本地切片，尚不可接管生产对话或直接替换 V1。
