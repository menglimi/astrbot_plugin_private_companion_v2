# CORE-08：持久任务监督器与本地异步执行

日期：2026-09-21。按 [本体功能路线](V1_CORE_FEATURE_PREREQUISITES.md)第 3 步，完成模型/消息链所需的首批任务基础：持久排队、有限并发、原角色与权限复核、取消/超时、重启恢复及实际任务诊断。验证仅使用合成身份、受控异步函数和临时 V2 数据库，没有加载宿主、调用真实模型、发送消息或读取 V1 用户数据。

这是内部本地任务 profile。它遵循 [原执行合同](../../astrbot_plugin_private_companion/docs/COMPANION_CONTRACTS_AND_VERTICAL_SLICE.md)中的原任务、尝试、提交边界和未知状态约束，但尚未实现公共 TaskEnvelope 的全部字段与 wire 适配，不能据此宣称 CORE-08、公共执行协议或替换发行已经完成。

后续更新（2026-09-22）：已完成[本地模型网关、配置来源与用量账本](CORE_MODEL_GATEWAY_SLICE.md)及[持久输入、异步原角色回复与逐段回执](CORE_CONVERSATION_MESSAGES_SLICE.md)，新增原模型 plan、分层预算、消息批次/回执和相应诊断，内部 schema 进入 v11。以下保留本任务切片交付时的 v9、112 项回归及当时的待办记录；当前状态以[构建状态](BUILD_STATUS.md)和后续切片为准。

## 1. 当前可运行的链路

[TaskSupervisor](../companion_v2/execution/service.py)以 SQLite 为正本，受理可信调用者提交的任务引用；[LocalTaskRunner](../companion_v2/execution/runner.py)领取任务并运行已登记的异步处理器。[数据模型](../companion_v2/execution/models.py)区分任务种类、前后台通道、效果类型、提供方绑定、输入引用和预算。

1. 登记有限的任务种类、版本、领域 owner、权限动作、预算及只读输入校验器。校验器负责原输入/对象/能力的当前授权；任务准入不能代替领域检查。
2. `start(expected_generation=...)` 接管监督器；同一代其他本地工作连接使用 `attach`，不重复换代。
3. `submit` 保存原请求与幂等键。`claim` 在同一写事务中核对名额、领取并创建 attempt；`begin` 再检查后进入执行。
4. `run_once(lane)` 执行一次领取；处理器可以复核原任务，并在调用领域动作前使用 `begin_effect` 记录提交边界。领域真正受理后，才用 `record_operation` 保存 owner 签发的操作号。
5. `finish` 复核当前输入/身份/角色/权限，保存真实结果、原回执引用和尝试记录；取消、超时和失联走独立路径。诊断读取同一记录，不另建推测的执行状态。

首批限定本人私聊，保存完整安装/平台/Bot/账号/会话范围、原账号绑定、原角色 revision 和受众。换 Bot、换绑、撤权、临时人格到期以及 A→B→A 都不能借原任务继续。STANDARD 用户仍须有精确动作授权；同一角色的群聊、系统维护和跨域 owner 投影需要后续适配。

上述登记、调度、停止证明与对账是可信运行时/控制面 API，不是模型工具。任务只保存输入、结果和回执的引用；正文及原件治理继续归对应 owner。语义如何理解和表达仍由角色模型结合材料完成，不在监督器中加入场景词表或角色行为阈值。

## 2. 标识与版本责任

| 记录 | 当前责任 |
| --- | --- |
| task + idempotency key | 同一逻辑请求跨重试和重启仍是原任务。更换建议 task ID 不会产生第二次动作；相同键改变输入、角色依据或定义时报告冲突。 |
| attempt | 每次实际领取有独立编号、领取/开始/结束时刻、停止依据及结果引用，尝试预算不因重启重置。 |
| supervisor generation | 持久 CAS 签发，隔离旧控制者回写；不证明旧协程或远端请求已经停下。 |
| provider binding | 明确 capability/provider/version/generation，与监督器代次分别保存。有副作用的任务必须提供，定义或绑定改变不能静默复用旧任务。 |
| operation ID | 只接受领域 owner 的真实受理号；受理前保持 null，不预先伪造。重试不能换成另一个操作号。 |
| task revision | 每次状态变化递增；取消与对账要求准确版本，旧请求不能覆盖新状态。 |

attempt 分别保留前次和后次 owner 回执、结果记录时间及原操作号。重试等待期间取消仅结束任务，不把上一轮已执行的尝试改写成“从未开始”。

## 3. 提交、取消、未知与恢复

| 场景 | 当前行为 |
| --- | --- |
| 排队或领取后尚未开始时取消 | 直接 cancelled；尚未开始的 attempt 有明确停止依据，可释放名额。 |
| 正在运行时请求取消 | 先 cancelling。后续不允许再进入提交边界；实际已提交的可信成功回执仍可记 succeeded，不能用取消抹掉效果。 |
| 调用领域动作 | 先持久保存 `effect=unknown`，再交给 owner；每个 attempt 只能进入一次原子效果边界。效果已知需要回执，成功提交还需要原操作号。 |
| 已知失败且没有提交 | owner 明确报告可重试时，沿原 task/operation 按退避再次排队；受原截止时间和尝试次数限制。 |
| 超时、失联或执行异常 | 开始过的任务先记 uncertain，旧 worker 的名额继续保留。跨过效果边界后，即便本地协程已停，也不能推断远端动作未发生。 |
| 实际协程终止 | 停止证明才释放物理执行名额。未提交时可记 cancelled/expired/failed；已跨效果边界保持 uncertain，不自动重做。 |
| 重启接管 | 已领取但从未开始的 attempt 可沿原预算重新排队；running/cancelling 变 uncertain；原排队任务仍可领取。旧代结果不能直接回写。 |
| 对未知操作查账 | 原 worker 确认停止后，当前可信 owner 可将原操作的对账结果交给 `reconcile`。仍检查当前身份、原角色、动作权限、定义及 revision，但不要求旧输入重新变有效，也不执行新动作。 |

`acknowledge_stopped` 只记录停止证明和释放名额，不安装迟到结果；旧控制者也可以提供真实停止证据。原操作未知时没有自动重发路径。当前没有远端 receipt 查询适配器，不能把这个可信对账入口当作已经实现平台查账。

取消与停止不是抹除：已经结束的尝试、真实回执和已提交效果都保留。首批处理原子结果，不支持部分提交；分段投递的逐段效果和历史归档须随后续 Delivery 适配完成。

## 4. 有界资源与执行条件

- 前台和后台各自有物理名额，默认各 2；另有每种任务及每种任务在完整 scope 内的并发限制，默认分别 2 和 1。旧代尚未停止的 worker 继续占名额。
- 每条通道默认保留 64 个排队/进行中任务名额，重试沿原预约位置，不被后来提交挤掉。同一 scope 满额的任务不会挡住有限候选页内其他可运行 scope。
- 默认最多保留 2048 个任务，目前没有归档/回收；到容量上限明确返回 `task_queue_full`，不删除未知动作腾位置。正式持续运行前须接保留策略。
- 固定登记 1～64 种任务；领取与恢复单页默认 32、最多 100。任务截止时间在未来 7 天内；每次超时最多 3600 秒、尝试最多 8 次、退避最多 3600 秒。它们是当前内部上限，不是模型可自行扩张的参数。
- attempt 租约与逻辑截止时间都有效，当前不续租。runner 另用单调时钟执行超时，避免单靠墙钟回拨让协程无限运行。
- 运行中的句柄有登记和命名，等待期间短间隔复核撤权/取消；停止最多等待 1 秒。拒绝合作的协程保留句柄与名额，迟到返回不能覆盖未知状态；`close` 返回仍未停止的句柄。
- 当前只支持可信、可取消的 async I/O 处理器；处理器负责管理并等待自己的子任务。同步阻塞代码和不可信插件需要进程隔离，不在本执行器能力内。

`run_once` 是本地执行入口，没有自动轮询后台、宿主生命周期或定时调度集成。短同步读取也不强制全部写入任务账本。前后台名额独立已具备本地证据；共享模型、网络和 token/费用预算尚未接入，因此不宣称真实被动首句已不受后台竞争影响。

## 5. 诊断与存储

[DiagnosticService](../companion_v2/diagnostics/service.py)接受同一 StorageRuntime 上的任务监督器，并继续复用原 ConfigurationService 实例。`DiagnosticQuery.execution_task_id` 选择原会话中的精确任务，展示实际状态、代次、attempt、排队时间、已观测的单调执行耗时、效果及名额占用；未记录的时长保持空值，输入/结果正文不输出。

只登记监督器但未选任务时仍是 unknown；选中任务后，uncertain 仍是 unknown，其他本地状态最多为 warn。provider、sender 和用户实际收到的结果仍未接入，不能从本地 succeeded 推出已经发送。任务变化或名额释放使旧诊断依据失效；报告不跨 Bot/账号/原角色/受众复用。

V2 内部 schema 升至 `companion-v2.storage.v9`，新增 `task_supervisor`、`execution_tasks`、`execution_attempts`、`execution_events` 及领取/恢复/名额索引。[升级实现](../companion_v2/storage/runtime.py)保留独立 v8 DDL 与指纹；新建及旧内部版本升级都进入 v9，非空资料保留、失败回滚和半升级检查已验证。这仍是 V2 内部格式升级，不是 V1 用户库的自动迁移。

## 6. 验证证据

本轮新增 **34 项**测试：

- [任务监督器](../tests/test_execution.py)：19 项，覆盖双连接争抢、前后台与 scope 限额、幂等/预算、原角色/撤权、取消、重启、未知结果、前次回执保留及校验异常脱敏。
- [异步执行器](../tests/test_execution_runner.py)：9 项，覆盖实际执行计时、超时/取消/撤权、迟到结果、父协程取消、活跃 worker 关闭及异常后的未知效果。
- [任务诊断](../tests/test_execution_diagnostics.py)：3 项，覆盖原任务读取、脱敏、状态变化失效、跨范围拒绝及未接入状态。
- [v9 存储升级](../tests/test_execution_storage.py)：3 项，覆盖非空 v8 升级、旧指纹/待确认建议保留、失败回滚及半升级拒绝。

最后一次受影响回归 **112 项通过（15.699 秒）**，编译通过。含既有诊断/修改建议/原角色答疑、历史内部数据库升级及隔离检查；早期批次与本批重叠，不累加成总数。

```powershell
python -m unittest tests.test_execution tests.test_execution_runner tests.test_execution_diagnostics tests.test_execution_storage tests.test_diagnostics tests.test_diagnostic_repairs tests.test_diagnostic_tools tests.test_diagnostic_storage tests.test_storage_runtime tests.test_storage_migrations tests.test_configuration_storage tests.test_agenda_storage tests.test_object_access_storage tests.test_scope_storage tests.test_persona_storage tests.test_isolation -q
python -m compileall -q companion_v2 tests
```

## 7. 下一步与未完成项

下一段仍在 CORE-08/CORE-02 第 3 步：先接模型任务路由、配置/提示词来源、提供方能力与预算预留/结算，再接输入合并、撤回关联、原角色工具循环和实际分段回执/已发历史。所有阶段向同一诊断服务提供真实证据；保留分段体验，前台不等待无关维护。

共享 token/费用预算、父子任务预算、等待/检查点/期次、部分效果、任务归档、公共 wire schema、群聊/系统任务、自动调度、真实模型与 sender、宿主取消及远端对账尚未实现。它们不会因本轮本地执行通过而自动获得交付资格。当前仍不可替换 V1，也没有真实回复延迟改善的测量结论。
