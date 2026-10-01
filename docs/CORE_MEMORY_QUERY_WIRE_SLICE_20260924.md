# CORE-03 只读记忆查询 wire 切片

本切片在 V2 记忆领域增加 `MemoryQueryWireV1`，把可信 `TaskContext` 下的私聊事实查询映射为评审版 `memory.query.v1` / `memory.result.v1` DTO，并将它作为首个只读能力注册到 V2 的进程内 provider registry。参考合同仍处于 review 阶段，字段定义见[合同总纲](../../astrbot_plugin_private_companion/docs/contracts/v1/README.md)、[查询 schema](../../astrbot_plugin_private_companion/docs/contracts/v1/schemas/memory-query.schema.json)和[结果 schema](../../astrbot_plugin_private_companion/docs/contracts/v1/schemas/memory-result.schema.json)。这是一段受宿主生命周期约束的核心适配器，不代表协议已发布或跨进程 SDK 已启用。

适配器只接受宿主传入的 `TaskContext`、宿主可信的 RuntimeScope 投影函数、固定 provider id/generation，以及有限默认预算和 token counter。`runtime_scope_from_task_context` 可在可信装配时以明确的 ecosystem、runtime 和 host 标识生成 scope；`MemoryService.bind_query_wire_v1` 提供适配器构造入口。请求携带的 scope 必须与投影完全一致；owner 始终由已授权 `TaskContext` 推导，不读取请求中的身份字段来选择记忆主体。当前 profile 仅允许 private scope、`visibility=private`、`purpose=reply`、current-only facts 和空扩展；主体筛选只映射已认证用户 `self` 或 V2 的 `entity:` 局部标签。来源在结果序列化前再次按当前授权和来源版本读取。

已映射 namespace、查询意图、主体、时间区间、`at_time`、retention、confidence floor、原记忆 revision、policy revision、检索 coverage 和真实证据片段。结果每页最多返回一个事实，避免适配器丢弃 V2 原分页游标已经消费的结果。证据条目数、字符数和 token 数取请求预算、provider 上限及当前记忆策略的交集；provider 必须明确 token counter 的口径。当前内置 `private-facts.utf8-budget.v1` profile 用 UTF-8 字节保守估算，并通过 warning 标注，不表示实际模型用量。输入/输出字节默认最多 65,536，可在受信任装配时收紧或放宽。证据超预算时只返回实际来源前缀，并以 `partial`、`missing` 和 warning 标注不完整。

后续公共能力分支已支持 `include_pending=true`：先分页事实，再分页当前 caller/owner/session 的 pending 草案；草案使用 `item_kind=proposal`，不生成 atom_id，且与事实页共享查询预算。历史 revision、非空 `types`、非 `reply` purpose 和扩展字段仍明确返回 unavailable；错误的版本、字段和预算返回受限错误结果。游标对应的内部 query session 绑定 `TaskContext`、trace、provider generation、scope、截止时间、预算和其余查询语义；续页须保留这些字段，只更换 request id 并回传 cursor。内部 session 最长 10 分钟，且每页重新复核来源权限。

`ReadProviderRegistry` 由 `CompanionApplication` 装配，负责有限发现、显式 provider 选择、绑定 lease、授权/owner/policy fence、请求/结果预算和释放；provider generation 由宿主注册时生成，不能由请求自报。调用前后重新校验 `TaskContext`、scope、记忆授权和 provider 代际；宿主停机、能力撤销或 owner/policy 变化会使旧绑定不可用。注册表是同进程可信装配 API，不是任意 Python 代码沙箱，也未接入独立 Dashboard 路由。

后续[事实增量召回切片](CORE_MEMORY_INCREMENTAL_RECALL_SLICE_20260924.md)已将本 wire 使用的默认事实词法路径改为分批建索引、按变更更新和有界候选复核；空页可携带续建游标，max_candidates 可收紧候选复核上限。FTS 排序仍有随数据量增长的成本，其他查询种类尚未增量化。[提交与持久回执切片](CORE_MEMORY_PROPOSAL_WIRE_SLICE_20260924.md)已接同步 `memory.proposal.v1` 与 `memory.operation.get`，查询证据引用也可用于提议；[记忆公共能力分支](CORE_MEMORY_PUBLIC_BRANCH_20260924.md)随后补齐 pending wire、变更订阅、resync 与宿主引用消费者。review 合同和跨进程稳定 SDK 仍未发布。群聊公共记忆、外部日志/备份的物理删除与线上真实模型验收仍沿原路线推进。

初始适配器定向验证：`tests.test_memory_wire` 与既有 `tests.test_memory_query`、`tests.test_memory_boundaries`、`tests.test_memory_conversation` 共 23 项通过。后续[provider 注册与宿主切片](CORE_READ_PROVIDER_REGISTRY_SLICE_20260924.md)在原 wire 测试增加 1 项类型/错误回执边界测试，新增 registry 与宿主消费 20 项，并完成核心 71 项、SDK 宿主 50 项验证。经 registry 调用的请求和成功/partial/unavailable 回执另通过 Draft 2020-12 校验；`jsonschema` 未加入运行时依赖。
