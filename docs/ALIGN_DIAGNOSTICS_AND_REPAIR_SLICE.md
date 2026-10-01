# ALIGN-03：诊断、答疑与修改建议的本地闭环

日期：2026-09-21。范围：独立 V2 工程、合成身份与临时 SQLite。按[符合性检查](DESIGN_CONFORMANCE_AUDIT_20260921.md)的 ALIGN-03，接通已有记录到诊断材料、原角色答疑和配置修改建议；没有注册真实宿主、调用真实模型、连接设备、发送消息或读取 V1 用户库。

本轮完成进入 CORE-08/CORE-02 所需的最小本地切片。完整诊断控制面、自然语言工具循环、实际 worker/provider/sender 轨迹和 L3 探测仍待后续，不能把本轮记作 UI07 或替换发行全部完成。

后续进展：已完成 [CORE-08 任务监督器与本地异步执行](CORE_TASK_SUPERVISOR_SLICE.md)，执行检查可按原会话查询精确任务的实际记录；真实 provider/sender 仍未接入。下文 v8、36 项新增与 177 项回归保留为 ALIGN-03 当时的验收快照，当前汇总见 [构建状态](BUILD_STATUS.md)。

## 1. 四种模式与实际证据

[DiagnosticService](../companion_v2/diagnostics/service.py)按需读取已有 owner 的公共服务；[合同](../companion_v2/diagnostics/models.py)保存检查名称、版本、级别、范围、权限、成本、时效及无副作用声明。结果包含 `pass/warn/fail/unknown/not_applicable`、实际开始/结束时间、单调时钟耗时、脱敏详情和带版本摘要的证据引用。

| 模式 | 当前可用材料 | 明确边界 |
| --- | --- | --- |
| explain | 配置继承、概率单位、竞争权重、能力选择、操作回执和修复流程的登记说明。 | 身份/角色校验后返回说明，检查结果列表为空；不能说已检查运行状态。 |
| self_check | 指定字段组的来源、显式值、配置版本、消费者代次和采用状态；指定能力的包选择、角色启用、本人同意和范围设置版本；授权的本地数据库版本可读性。 | 配置正文/提示词值不进入诊断报告；安装记录不证明能力已装载，保留同意不授予原件读取权。数据库可读不代表做过完整性扫描、备份验证或 V1 迁移。 |
| incident | 指定操作号、完整目标 scope、最多 24 小时时间窗内的创建/最近更新时间与本地操作状态；该操作的 outbox 状态计数。 | 不是完整事件时间线；outbox 是当前快照，没有历史状态转换时刻。原操作在时间窗之后又发生变化时，该窗口内的状态为 unknown。缺少记录不能断言从未开始，completed 不能证明外部效果或用户已收到。 |
| repair_proposal | 持久保存原配置检查、明确字段差异、影响目标、原人格/版本、采用方式、理由、过期时间与回退说明。 | 只保存计划；确认和取消分别经过可信控制面服务，诊断模型没有自动确认入口。 |

配置的 `consumer_not_started` 为 unknown，`failed` 为 fail，等待下一任务/重启或待采用为 warn，只有当前消费者报告 `applied` 才是对应检查的 pass。服务实例重建后，过去进程的采用记录不会被当成当前消费者已启动。

能力未获取是 not_applicable；已获取也仍将实际就绪/设备在线记为 unknown。执行检查明确针对本隔离服务：worker/provider/sender 尚未接入，没有运行延迟证据。不会用静态说明补造回复耗时、主动拦截原因或设备结果。

Finding 关联支持证据，反对证据为空时保留空列表；只给本地观测的定性证据等级，不生成故障概率。复杂原因假设和完整失败轨迹需后续领域提供证据。

## 2. 范围、成本和受众

- 每次查询明确选择一个配置组、一个能力、一个原操作等有限项目；没有整库历史、源码扫描、网络调用或永久轮询。
- L0/L1 使用固定的本地读者；L2 必须提供明确时间窗。本轮未开放外部插件检查注册或 L3 执行，只有可供后续注册采用的 Check/Result 合同和内置目录。
- 每项记录 500 ms 的本地结果预算，超时结果降为 unknown。该预算不能抢占任意同步插件函数，也不宣称已实现网络/设备探测的超时取消；后者随 CORE-08 受监督任务执行器接入。
- 原报告最多保留 32 份、有效期 60 秒；使用前重验身份、原 Bot/账号/会话、人格 revision、权限和实际资料版本。过期/变更时要求新检查，不偷偷用新资料替换原报告。没有后台刷新缓存。
- 运行诊断和建议首批通过本人私聊受众返回；群聊可使用静态 explain。跨窗口的配置目标仍按公共权限授权，CORE 管理其他目标不代表模型可以换人格续答。群内经过逐对象过滤的运行报告及私密路由后续补齐。
- 配置与能力读取沿公共权限；通用 operation ledger 缺少领域 owner 信息，因此当前通用查账仅开放给安装 CORE。非核心用户的便签/提醒原操作继续走已有领域查账服务，不因诊断入口扩大权限。

## 3. 建议确认、取消和重启

[RepairProposalService](../companion_v2/diagnostics/repairs.py)保存不可变计划与 review token。首批支持单组、1～32 个明确赋值字段；恢复继承、跨组计划、能力下载/卸载、自动回退及自然语言确认解析不在本轮实现范围。概率沿字段注册校验 `0..1`，不猜测百分比；`False`、零值等不会被默认值替换。

[ConfigurationService.preview_changes](../companion_v2/configuration/service.py)与正式 patch 共用字段校验、权限及持久 owner。预览展示 owner 隐含的实际字段变化：例如能力设置首次写入会令整组值成为显式值，建议不能只列出用户手动选择的一项。正式确认仍调用同一配置服务，没有第二份能力开关或影子配置。

回退说明保留原显式值和继承关系，需要重新检查后才可执行。能力设置首次创建尚不支持恢复成“没有设置记录”，此时明确记录无法精确回到原状态，只提供恢复原有效值的候选，不生成无效的恢复继承指令。

确认要求原 proposal ID、原审阅 revision（1）和准确 review token；同时重验真实操作者、原会话/人格快照、当前权限、配置/继承/owner 版本、检查依据及 TTL。默认有效 15 分钟、最长 30 分钟。A→B→A、同用户换 Bot/账号、账号换绑、撤权/降级、配置或采用状态变化不能把旧计划应用到新上下文。

权限核对、原操作预留、配置写入、操作完成和建议终态在同一 SQLite 事务中提交。最终写建议失败时，配置与操作一起回滚。重启保留计划；重复确认只返回原回执，即便之后配置又被修改，也不会再次覆盖。回执只证明 `local_configuration_saved`，不为当前采用状态代证。

取消不修改配置，不启动补偿动作；关闭的建议不能改走另一终态。过期或已变更但仍有当前权限的待确认建议可以取消。失效状态和变更状态在读取视图中分别为 expired/stale，不复活旧建议。

保存的检查依据也单独复核当前权限：不能在降级后借仍可读的普通字段组读取旧建议中的核心操作记录。确认/取消及历史回执返回均保留此受众边界。

## 4. 原角色答疑

[DiagnosticRoleSession](../companion_v2/conversation/diagnostic_tools.py)保留原事件、角色指令、角色绑定与上下文，将真实报告和建议作为资料提供给同一个模型接口。本地测试模型只生成一次续答草稿，不另建“客服人格”。

生成前、后重验原问题/引用原件、受众、身份、角色、报告时效、配置与权限。生成中取消、换角色、配置变化或私密原件混入群上下文时，不返回该草稿。语义解释依靠提示词说明证据边界，按问题自然组织语言，不强制五段模板，不用关键词封锁代替表达能力。

模型可解释建议及历史回执；此适配不提供 confirm/cancel 的模型工具调用接口。未来页面/命令根据真实用户对准确差异的确认调用服务，再交回原角色解释结果。真实宿主的认证、工具 schema 注册、调用循环和消息投递仍未接入。

## 5. 内部存储升级与验证

V2 内部 schema 升至 `companion-v2.storage.v8`，新增 `diagnostic_repair_proposals`。v7 的定义与迁移指纹继续独立保留；非空 v7 升级保持原领域记录，未知操作不改成成功。半升级、结构错误或迁移指纹不符拒绝打开，升级失败原子回滚，可修复后重试。这里不是 V1 插件用户数据迁移。

本轮新增 **36 项**测试：

- [诊断检查](../tests/test_diagnostics.py)：10 项，覆盖实际采用、重启、脱敏、范围/权限、能力不等于就绪、原操作时间窗、unknown、时效和结果预算。
- [修改建议](../tests/test_diagnostic_repairs.py)：16 项，覆盖精确差异、原操作重试、重启、撤权/过期/降级、跨 Bot/人格、变更失效、值校验、owner 共用及原子回滚。
- [v8 升级](../tests/test_diagnostic_storage.py)：3 项，覆盖非空全领域记录保留、失败回滚和半升级/指纹检查。
- [原角色续答](../tests/test_diagnostic_tools.py)：7 项，覆盖原模型上下文、生成中变更/取消、过期、群受众和建议不自动应用。

受影响模块最后一次集中回归 **177 项通过（22.897 秒）**，编译通过。包括既有 700/1500 字段配置规模约束和各历史内部 schema 升级；未放宽查询上限。早期批次与本批次重叠，不相加为测试总数。

```powershell
python -m unittest tests.test_diagnostics tests.test_diagnostic_repairs tests.test_diagnostic_storage tests.test_diagnostic_tools tests.test_configuration tests.test_capability_configuration tests.test_management_access tests.test_capabilities tests.test_configuration_storage tests.test_storage_runtime tests.test_storage_migrations tests.test_agenda_storage tests.test_object_access_storage tests.test_scope_storage tests.test_persona_storage tests.test_persona_resolution tests.test_object_access tests.test_persistent_identity tests.test_agenda_tools tests.test_foreground_conversation tests.test_isolation -q
python -m compileall -q companion_v2 tests
```

## 6. 下一步

继续 CORE-08/CORE-02：先做按完整 scope/原角色关联的有界任务与 attempt 状态、取消/超时/恢复，再接模型路由、提示词来源和预算；随后接输入合并、逐段回执与真实已发历史。将实际任务/模型阶段作为新的诊断依据，替换对应 unknown，而不是把静态接入状态当运行结果。

前台回复不串行等待无关后台维护；沿用户已确定的目标保留分段体验，同时让排队、模型调用、资料准备和输出阶段的延迟可查。真实模型、平台与设备验收仍单独进行，当前不能声明可直接替换 V1。
