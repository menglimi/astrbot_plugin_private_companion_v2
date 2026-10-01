# CORE-03 记忆提交与持久回执查询

后续[记忆公共能力分支](CORE_MEMORY_PUBLIC_BRANCH_20260924.md)已补齐延迟提交、pending 查账/查询、订阅恢复及宿主持久引用消费者；本记录下方同步提交验收数字保留为原批次证据。

2026-09-24。V2 已接通 `memory.proposal.v1` / `memory.proposal.submit` 的可信进程内同步提交，以及 `memory.operation-query.v1` / `memory.operation.get` 的只读查账。新增、纠正、撤回与 no-op 复用唯一 `MemoryWriter`、现有来源授权和 `memory_operations`，没有增加事实数据库或 schema 迁移。协议依据仍为[review 合同](../../astrbot_plugin_private_companion/docs/contracts/v1/README.md)。

## 宿主入口

- `app.memory_commands`：提供固定 provider id/generation、可信 scope 投影、`offer_source(context, SourceRef)` 和 `handle(context, request)`。调用只接受宿主已认证的 `TaskContext`，不从请求 JSON 还原可信身份。
- `app.provider_registry`：现在可发现、绑定、调用 `memory.query` 与 `memory.operation.get`。提交不注册到只读 registry，避免该层的调用后丢弃规则把已提交操作表现为可重试读取失败。
- 没有提供可信 `RuntimeIdentity` 的独立装配不启用这些 wire 入口。命令调用前及提交前检查宿主 running 状态、持久 supervisor generation、当前权限、配置版本及期限；旧宿主在被接管或停机后拒绝写入。

宿主取得真实入站 SourceRef 后，可按以下方式提交。`context`、`source` 和 `deadline` 均由可信应用服务提供；这不是模型可自行调用的身份或证据签发 API。

```python
from companion_v2.execution.models import stamp

commands = app.memory_commands
evidence = commands.offer_source(context, source, expires_at=deadline)
request = {
    "schema_version": "memory.proposal.v1",
    "capability_id": "memory.proposal.submit",
    "capability_version": "1.0",
    "provider_id": commands.provider_id,
    "provider_generation": commands.provider_generation,
    "request_id": "request-1",
    "trace_id": "trace-1",
    "idempotency_key": "remember-preference-1",
    "deadline_at": stamp(deadline),
    "scope": commands.scope_for_context(context),
    "budget": {"max_input_bytes": 16384, "max_output_bytes": 16384, "max_model_calls": 0},
    "payload": {
        "namespace": "personal", "visibility": "private", "purpose": "reply",
        "proposal_id": "proposal-1", "operation": "add",
        "target_atom_id": None, "expected_revision": None,
        "subject": {"kind": "companion.person", "ref": context.actor.subject.subject_id},
        "predicate": "饮用偏好", "object": "不喝咖啡",
        "representation": "用户不喝咖啡。", "retention": "durable",
        "attribution": "user", "polarity": "affirmed", "confidence": 1.0,
        "evidence_refs": [evidence],
    },
}
result = commands.handle(context, request)
```

查询回执沿用[只读绑定调用方式](CORE_READ_PROVIDER_REGISTRY_SLICE_20260924.md)，将 capability 改为 `memory.operation.get`、schema 改为 `memory.operation-query.v1`。payload 必须包含 `namespace`、`visibility=private`、`purpose=reply`，并在以下两种定位方式中选择一种：

```python
{"operation_id": original_operation_id}
# 或
{"capability_id": "memory.proposal.submit", "idempotency_key": "remember-preference-1"}
```

查账请求没有顶层 `idempotency_key`。原始 operation id 与原幂等键都按当前 owner、caller、namespace 隔离；返回结果不含事实正文或证据原文。查不到或目标不属于当前调用者时为 `rejected / target_unavailable`，不能据此断言原操作没有提交。

## 原子性与重放

写入和 wire 回执在同一个外层事务内完成。成功结果在 COMMIT 前完成序列化预算检查和权限复核，预算包括完整结果封套。期限、授权、配置、证据或预算检查失败时，事实、修订、变更序列、来源及操作回执一起回滚。`StorageRuntime.transaction(require_outermost=True)` 拒绝在已有写事务或读快照中执行命令，避免内层 savepoint 成功后谎报持久提交。

幂等键绑定 owner、caller、namespace 和原 capability；保留键前缀与既有内部调用隔离。`memory_operations.result_json.wire` 存放业务 payload 摘要与原始回执，不存额外正文。同键同 payload 返回原回执，同键不同 payload 返回 `idempotency_conflict`。payload 按规范 JSON 结构计算摘要；省略字段与显式填写默认字段仍属于不同 payload。request/trace、预算、deadline、当前 provider generation 不参与业务摘要。

已提交重放先查持久回执，不重新解析过期证据句柄；仍检查本次请求身份、授权、期限与预算。应用重启后使用新 generation 请求，结果封套使用当前 generation，`output.original_provider_generation` 保留原提交代。纠正或撤回不会改写旧提交回执。

SQLite 提交/回执异常保守返回 `uncertain`、`retryable=false` 与可用的 operation id，不自动重放。即使 COMMIT 实际已成功而确认丢失，也能通过独立查账取得持久结果。同步 deadline 在提交前合作式复核，不代表能抢占或撤销正在执行的 SQLite COMMIT。

## 证据与当前 profile

证据引用由现有 `memory_sessions` / `memory_handles` 支撑。`offer_source` 用来源正本及宿主入站事件确定 speaker 和 human/bot attribution，不接受客户端自报完整 SourceRef 或 speaker 作为证明。查询 wire 返回的 EvidenceRef 现在也使用可解析的宿主句柄，可直接用于后续提议。引用有效期取来源有效期与原 query session 期限的较早者；命令签发 session 最长 10 分钟。

提交前精确检查 handle 所属 context、owner、session 期限、来源版本、span hash、当前来源授权和随引用提供的 metadata。跨窗口证据句柄不能直接复用，durable 记忆仍可按既有同主体授权投影。遗忘、撤回和来源失效不会因为保留了旧句柄而被绕过。

本批支持 private / reply、开放词汇的字符串 object 与字符串 qualifiers、同步 add/correct/retract/no_op。correct 保留目标未暴露到 wire 的置顶、单值及依赖属性，并按目标 revision 做 CAS；retract 回执反映实际目标的 retention 和 validity。未提供 representation 时采用原 predicate 与 object 的文本组合；缺省 attribution/polarity 为 unknown，缺省或 null confidence 以内部保守值 0 表示。

后续分支已支持 `defer_until_boundary=true`，通过 `resolve_pending` 显式采用/丢弃，并同步更新原 wire 回执；查询可分页同会话 pending 草案。变更订阅、resync 与持久引用消费者已进入统一宿主，调用及验收见[公共能力分支记录](CORE_MEMORY_PUBLIC_BRANCH_20260924.md)。结构化 object/qualifiers、非空 types/extensions、其他 visibility/purpose 仍明确不可用；通用写能力注册表和跨进程 SDK 属于后续范围。本批没有增加 HTTP 路由、模型调用或平台发送。

## 验证

AstrBot 自带 Python、临时 `ASTRBOT_ROOT`、合成身份及模型/平台替身下完成定向验证：

- 核心范围累计 **140 个唯一测试 ID**：本批最初 139 项回归全部通过；完整结果预算修正后复验适配器及宿主 40 项，通过并包含新增的第 140 项。模块为 `test_memory_proposal_wire`、`test_memory_commands_host`、`test_memory_wire`、`test_memory_provider_host`、`test_provider_registry`、`test_memory_writer`、`test_memory_query`、`test_memory_boundaries`、`test_memory_incremental`、`test_memory_conversation`、`test_memory_polish`、`test_storage_runtime`、`test_host_application`。
- SDK 宿主 **50 项通过**：`test_astrbot_staging_host`、`test_astrbot_staging_bootstrap`、`test_astrbot_native`、`test_isolation`，覆盖加载、停机、路由注销及核心隔离。
- 新增 **27 项**提交/宿主测试包含在上述范围：并发幂等、过期证据重放、伪造与撤回证据、CAS、目标属性保留、owner/caller/namespace 隔离、未知提交查账、外层事务、完整封套预算、期限/配置/停机回滚及重启原代回执。
- 对实际返回的 **96 份**成功、拒绝、无权限、不可用、超时、partial 与 uncertain 回执执行 review 合同 Draft 2020-12 校验；`jsonschema` 仅用于验证，没有增加运行时依赖。

测试使用独立临时数据，不访问 V1 用户数据或重载在线插件。代码与文档按 UTF-8、无 BOM、LF 和末尾换行检查。
