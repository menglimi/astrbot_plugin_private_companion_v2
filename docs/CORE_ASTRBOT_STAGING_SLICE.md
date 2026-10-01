# CORE-ASTRBOT 受控试运行装配

日期：2026-09-22。本切片在既有 [AstrBot 适配器](CORE_ASTRBOT_ADAPTER_SLICE.md)和[统一宿主装配](CORE_HOST_LIFECYCLE_AND_BATCHING_SLICE.md)之上增加显式试运行入口。完成的是隔离环境中的启动、原生事件接收、配置采用、预览/回执检查与停止恢复；尚未注册插件、连接生产模型或向真实账号发送消息。

## 入口与责任

[AstrBotStagingSession](../companion_v2/adapters/astrbot/staging.py)接收调用者显式提供的 V2 `StorageRuntime`、宿主 context、`StagingProfile` 和 `NativeAdapterTypes`。导入模块和创建对象都不会注册宿主处理器、访问网络或打开默认数据目录。

`StagingProfile` 固定一组完整私聊目标：安装、宿主、平台、登录账号、Bot、会话、发送者、原人格版本和受众。V2 身份、窗口参与者、人格绑定及所需权限须由可信测试装配事先建立；加载器复用公共身份/配置服务检查，不根据收到的消息补建身份或授权。宿主 SDK 类型和已验证版本由调用者提供，领域核继续不导入 AstrBot。

运行参数还包括原生 provider ID、费率、五层预算、输出上限、任务提示词、消息合并和队列策略。费率只用于估算成本，不代表提供商账单。启动后的配置修改继续使用 `application.configuration` 的正式差异提交、当前权限和采用回执；人格提示词来自原宿主人格，任务提示词与输出上限从 V2 当前配置解析，修改只影响随后开始的任务。

## 预览与投递

| 模式 | 行为 | 可证明的结果 |
| --- | --- | --- |
| `preview`（默认） | 调用选定模型，保留原草稿；本地发送端明确返回 `not_sent`，不触及 OneBot。 | `preview(batch_id)` 可在当前权限和来源仍有效时读取草稿；`sent=False`，已发送历史为空。 |
| `onebot_private` | 使用固定账号和完整私聊目标，调用现有 OneBot sender。 | 只有有效 `message_id` 才确认送达；超时/异常保留 `unknown`，不能把受理或模型完成当成送达。 |

预览沿用当前 Delivery 的“确认未发送”结果，因此底层 part 为 `failed`、flow 为 `blocked`；这不表示生成失败，也不会要求重试发送。`inspect()` 单独提供 `preview_ready` 与不可读原因，读取时再次核对原件、工具结果、撤回和当前授权。来源撤回后草稿不再可读，历史用量和未发送回执仍保留。

`inspect(batch_id)` 返回配置解析标识、当前采用状态、模型实际用量/未知状态、原投递 operation、逐段平台引用及回执。摘要不包含消息正文、人格/任务提示词、密钥或提供商端点；需要看草稿时使用独立的 `preview()`。`confirmed_delivery` 表示选定批次有原生适配器确认的发送回执，阅读状态仍为 unknown。测试里的合成回执不构成生产平台验收。

模型端口新增 `transport`，原生适配器写入 `astrbot_openai`；模型计划及公共诊断从端口/持久计划读取该标识，不再把原生调用统一描述为本地替身。旧本地端口的默认值保持 `local_test_adapter`。

## 启动、停止与恢复

启动先做不取得执行租约的只读权限预检，再核对宿主当前人格、客户端和模型配置。宿主 await 返回后重新检查权限，随后才固定试运行指纹并通过既有 CAS 原子取得任务/模型运行代。执行入口继续要求当前运行代和实际领取，预检不能执行任务。

试运行指纹通过既有 Operation Repository 原子持久保存，仅保存摘要，不保存原生 provider 配置。首次使用拒绝接管已有对话/任务的数据库；后续必须保持原目标、提供方配置、人格、发送模式、费率及运行参数。新的进程实例 ID 可以变化，目标/模式等不能借重启替换。尤其不能把已有预览库改成真实发送库。调整这类试运行参数应准备独立测试库，不能清除指纹来接管旧任务。

原生宿主预检不持有生命周期锁等待，`close()` 可以立即关闭入站；迟到的预检或事件捕获结果不能重新启动或发布消息。执行中的模型取消、迟到用量与回执沿既有 supervisor/runner 处理。数据库和宿主客户端由外部调用者持有；返回 `draining` 时须继续保留数据库直到实际句柄结束，不能直接关闭共享客户端。

相同资料/配置的恢复保留原消息、操作、用量和未知结果，重复入站回到同一批次。已撤销的绑定/权限不会由加载器恢复；新消费者不能沿用旧运行代的“已采用”状态。当前恢复证据包括同进程重新打开 SQLite、重建装配和替换运行实例；本轮未新增独立进程强退试验或真实宿主热重载证据。

内部 schema 仍为 v14，没有新增表或 V1 数据迁移。

## 调用顺序

下例运行于持有可信对象的独立宿主测试装配中，不是自动扫描生产数据的命令。完整合成装配见[定向测试](../tests/test_astrbot_staging.py)，真实 SDK 类型组合见[原生契约夹具](../tools/native_contract_cases.py)。

```python
session = AstrBotStagingSession(
    staging_runtime, staging_context,
    profile=profile, native_types=native_types,
)
startup = await session.start(
    expected_task_generation=expected_task_generation,
    expected_model_generation=expected_model_generation,
)
startup.unwrap()
batch_id = (await session.receive(authenticated_native_event)).unwrap()
# 自动调度执行；由调用者的测试控制流程等待完成，再读取摘要/预览。
summary = session.inspect(batch_id).unwrap()
shutdown = await session.close()
# 确认 shutdown.state == "stopped" 后，由原 owner 关闭 staging_runtime。
```

## 实际验证

最终验证使用 AstrBot 自带 Python **3.12.12**，临时 V2 数据根、合成身份和替代网络端口。

```powershell
& 'C:\Users\99505\.astrbot\backend\python\python.exe' -X utf8 -m unittest tests.test_astrbot_staging tests.test_isolation tests.test_execution tests.test_host_application tests.test_host_recovery tests.test_host_external_tools tests.test_model_gateway tests.test_model_storage tests.test_execution_diagnostics -q

& 'C:\Users\99505\.astrbot\backend\python\python.exe' -X utf8 tools/run_native_contracts.py --host-source 'C:\Users\99505\.astrbot\archive\astrbot-4.27.2-audit'
```

- **101 项定向测试通过（20.678 秒）**，其中本切片新增 18 项：启动前检查、预览/发送分离、持久模式与提供方固定、配置采用、撤权、来源撤回、账号/窗口隔离、重复与未知回执恢复、并发启动和停止期间迟到结果等。
- **10 项 AstrBot 4.27.2 原生契约通过（4.013 秒）**，其中新增 3 项覆盖试运行配置采用与预览、原生送达引用、超时后的非空重开。真实 SDK 使用 `httpx.MockTransport`，WebSocket 使用内存 peer，**网络尝试为 0**。
- 开发过程中曾跑原有 497 项测试，496 通过，1 项静态隔离扫描将相对 `.onebot` 导入识别为外部包。已改为完整的 V2 内部导入；上述最终定向范围含静态隔离复验。另一次新增测试的用量断言把 40 token 写成 30，已按 fixture 的实际输入/输出修正。此后按影响范围复验，没有将旧全量结果作为当前版本全量通过证明。

这些结果证明 API 装配及原生类型/解析链成立；真实 provider 响应、账号会话、平台网络、外部插件工具与跨进程异常退出仍需对应环境的证据。

## 后续

后续[配置与首次初始化切片](CORE_ASTRBOT_STAGING_BOOTSTRAP_SLICE.md)已补齐可信本地装配 API、显式初始化与只读加载，以及 unknown 已提交后独立进程退出的恢复证据。实际 provider/账号/路由现场核对、真实平台回执、V1 旧发送者围栏和生产切换仍按 G8–G10。群聊/媒体、完整角色生活、关系记忆、跨域 owner 投影及兼容选模仍分别推进，不因这些试运行入口而升级替换发行资格。
