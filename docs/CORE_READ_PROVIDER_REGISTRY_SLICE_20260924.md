# CORE-03 只读 provider 注册与宿主接线

2026-09-24。V2 的 `memory.query.v1` 已从独立 wire 适配器接入 `CompanionApplication.provider_registry`，成为第一个可经发现、显式绑定和调用的进程内读取能力。能力注册不复制事实库；查询仍使用同一个 `MemoryService`、身份策略、来源正本和检索索引。本批没有增加页面、数据库表或 schema 迁移。

## 运行入口

- `capabilities/read_providers.py`：可信宿主注册、有限能力目录、显式 provider/version 绑定、句柄期限、预算、结果关联复核及释放。
- `memory/provider.py`：内置 `companion_v2.memory` 提供方，连接现有 `memory.query.v1` / `memory.result.v1`。
- `adapters/astrbot/application.py`：把原入站适配器使用的可信 `RuntimeIdentity` 传入公共应用。宿主 ID 必须匹配当前认证 principal；请求 scope 不能决定 owner。
- `host/application.py`：装配 registry 和 Memory provider，实际调用受 `require_running` 与持久 supervisor generation 约束；进入 draining 或 faulted 时关闭 registry。未提供 RuntimeIdentity 的独立装配保留内部领域 API，不虚构 wire 身份。

以下是可信应用服务的最小调用方式。`context` 必须由宿主先完成身份、参与者、角色与受众解析，不能从未经认证的 HTTP JSON 还原：

```python
from companion_v2.capabilities.read_providers import ReadLimits
from companion_v2.execution.models import stamp

registry = app.provider_registry
available = registry.discover(context, capability_id="memory.query").unwrap()
bound = registry.bind(
    context,
    capability_id="memory.query",
    capability_version="1.0",
    provider_id="companion_v2.memory",
    limits=ReadLimits(16384, 20000),
    ttl_seconds=120,
).unwrap()
request = {
    "schema_version": "memory.query.v1",
    "capability_id": "memory.query",
    "capability_version": "1.0",
    "provider_id": bound.provider.provider,
    "provider_generation": bound.provider.generation,
    "request_id": "request-1",
    "trace_id": "trace-1",
    "deadline_at": stamp(bound.expires_at),
    "scope": bound.scope,
    "required_features": [],
    "budget": {"max_input_bytes": 16384, "max_output_bytes": 20000, "max_model_calls": 0},
    "payload": {
        "namespace": "personal", "visibility": "private", "purpose": "reply",
        "query_intent": "上次提到的饮用偏好",
    },
}
outcome = registry.invoke(context, bound.binding_ref, request)
registry.release(context, bound.binding_ref)
```

registry 的控制错误使用 V2 `Outcome.failure`；通过准入后，`Outcome.value` 才是领域 `memory.result.v1`，其 `status` 仍须独立判断。控制入口是本地 Python API，不宣称实现 review 的 `control-request` / `control-result` wire。

## 准入与失效

注册只接受受信任装配的同步读取 handler，generation 由 registry 随机签发。重复同键注册拒绝覆盖，替换须先注销原 registration；旧 registration 无法删除新代。不同提供方保留独立键，bind 必须明确提供方与精确版本，不按登记顺序选择或自动回退。

发现不分配句柄，只返回当前获授权的指定能力。绑定固定 `TaskContext.key`、可信 scope、稳定 owner、provider generation、权限/配置依据及字节预算。每次 invoke 前后重验当前身份、人格、授权、宿主 generation 和原 registration；撤权、配置变化、scope 变化或 provider 替换时丢弃旧结果。身份策略目前沿用公共 policy revision，因此相关全局 revision 变化可能保守地要求其他读取者重新绑定。

内置 Memory 的开关沿用统一记忆配置。由能力包提供的其他读取服务可以携带固定 `CapabilityPackageDescriptor`；其安装版本/hash、角色启用状态和精确 capability/scope consent 都在发现、绑定与调用时复核。注册 descriptor 不会自动安装能力或授予权限。

目录最多 32 项，绑定默认最多 256 个，期限默认 300 秒、上限 600 秒；bind 时惰性回收过期句柄，无每句柄定时器。请求期限不得超过绑定期限，预算不得超过协商值。释放幂等，调用者只能释放自己的绑定。停机先关闭准入并释放 registry 引用，再沿原宿主流程收束领域任务；重启产生新 generation，稳定记忆 owner 不改变。

内置查询 profile 为 `private-facts.utf8-budget.v1`：仅支持私聊、reply purpose、current-only facts，沿用已有 namespace、主体、时间、retention 与 confidence 过滤。每页最多一个事实；证据默认上限 8 条、2400 字符、800 个预算单位，并与当前记忆策略及请求取交集。当前没有模型 tokenizer 依赖，`evidence_tokens` 按 UTF-8 字节作保守估算，成功/partial 回执带 `evidence_tokens_estimated_utf8_bytes` warning，不能当作模型实际用量。直接装配 wire 的其他可信适配器仍可提供自己的明确 token counter。

## 验证

AstrBot 自带 Python 3.12 下：

1. 核心组 **71 项通过**：`tests.test_provider_registry`、`tests.test_memory_provider_host`、`tests.test_memory_wire`、`tests.test_memory_query`、`tests.test_memory_boundaries`、`tests.test_memory_conversation`、`tests.test_host_application`、`tests.test_host_recovery`。
2. 宿主组 **50 项通过**：`tests.test_astrbot_staging_host`、`tests.test_astrbot_staging_bootstrap`、`tests.test_astrbot_native`、`tests.test_isolation`。进程设置 `PYTHONPATH=C:\Users\99505\.astrbot\backend\app`，并在 SDK 导入前把 `ASTRBOT_ROOT` 指向临时目录。
3. 新增 registry/宿主消费 **20 项**，另在原 wire 测试增加 scope revision 类型及超长关联 ID 回归；均包含在上述组内。覆盖真实合成事实读取、provider 更换、未知版本/features、跨主体使用、释放、到期、容量、包准入、权限/配置变化、处理期间撤权、非法结果、期限/字节预算、停机、重启与 supervisor 接管。
4. 本机 `jsonschema` 对经 registry 调用的请求及 succeeded/partial/unavailable 回执通过 Draft 2020-12 校验。未增加运行时依赖。

测试只用临时 V2 数据库、合成身份和模型/平台替身；新宿主查询测试明确断言读取期间模型与 sender 调用数均为零。SDK 加载、停止、路由注销及核心隔离均包含在宿主组中，没有重载在线插件或读取 V1 用户数据。

## 后续范围

这是可信进程内同步读取的首批装配，不覆盖第三方包下载/装卸、跨进程调用身份、通用能力控制 wire、注册 heartbeat/CAS 更新或完整 SDK。领域权限仍由原 owner 负责；没有开放额外 HTTP 路由。

后续[事实增量召回切片](CORE_MEMORY_INCREMENTAL_RECALL_SLICE_20260924.md)已接通默认事实词法查询的分批建索引、按变更更新、有界候选读取及空页续建回执。原文、经历、混合/向量查询仍沿旧读取路径；FTS 排序与来源依赖验证仍有数据量成本，同步 deadline 尚无抢占式 SQL 取消。[提交与持久回执切片](CORE_MEMORY_PROPOSAL_WIRE_SLICE_20260924.md)已把 `memory.operation.get` 注册为第二个只读能力，并通过独立本地命令门面接入同步提交。[记忆公共能力分支](CORE_MEMORY_PUBLIC_BRANCH_20260924.md)随后补齐 pending wire 与订阅/resync：仅显式 `supports_pending=True` 的能力可返回 pending 字典回执，必须带 reason 且 retryable=false；订阅控制和持久引用消费者使用独立宿主入口，不进入只读 registry。其他查询种类的增量化仍待实施。原查询切片的历史证据见[wire 记录](CORE_MEMORY_QUERY_WIRE_SLICE_20260924.md)。
