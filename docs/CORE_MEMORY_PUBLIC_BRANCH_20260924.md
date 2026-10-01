# 记忆公共能力分支：延迟提交、订阅恢复与宿主接入

2026-09-24。本记录对应用户确认的完整分支范围：延迟提交、订阅恢复和宿主接入。在原同步提交、事实查询及持久查账之上，三个部分已形成可信进程内使用链。事实仍由唯一 `MemoryWriter` 写入；订阅消费只处理引用，不触发提案、模型或平台发送。

## 交付内容

| 部分 | 当前行为 |
| --- | --- |
| 延迟提议 | `memory.proposal.submit` 接受 `defer_until_boundary=true`，保存 pending operation，返回 `commit_state=not_committed`，不生成 atom；要求原私聊 session，no-op 不进入队列 |
| 边界决定 | `app.memory_commands.resolve_pending(..., decision="accept"/"discard")` 显式提交或丢弃；重新核验来源、当前权限、有效期及 CAS；事实与原 wire 回执在同一外层事务内更新 |
| 查账与查询 | `memory.operation.get` 返回 pending 或最终回执并保留原 provider generation；`memory.query` 的 `include_pending=true` 先分页事实，再分页当前 caller/owner/session 的草案；草案使用 `item_kind=proposal`，没有 atom_id |
| 订阅控制 | `app.memory_subscriptions.handle` 接受 subscribe/ack/resync 标准封套；`poll` 返回有租约的引用批次或 `Outcome({"batch": None})`；订阅控制与只读 registry 分开装配 |
| 持久消费 | `app.memory_reference_views` 保存 inbox、staging、活动引用视图及 checkpoint；完整快照页加 W→C 尾部变更之后原子激活，再确认 snapshot ACK |
| 恢复与隔离 | 支持已确认检查点、消费已落盘但 ACK 未到，以及本地快照已激活但 ACK 未到的恢复；新订阅 fence 旧代；停机、接管、权限/配置变化、来源撤回及有效期边界使旧视图不可继续作为当前视图读取 |

宿主只有提供可信 `RuntimeIdentity` 才装配这三个入口。`ReadProviderRegistry` 仍提供 `memory.query` 与 `memory.operation.get`；只有显式声明 `supports_pending` 的只读能力才能返回 pending 回执，且不可标为可重试。没有注册写操作或订阅 ACK 为只读能力。

本批复用 `memory_operations`、`memory_changes`、`memory_sessions` 和 `runtime_metadata`。不增加 schema 迁移或第二份事实正本，兼容共享工作树现有 v25。`memory-stream-` 与 `memory-view-` 控制记录只保存引用和协议状态；cursor 的安装 lineage 与 HMAC 密钥持久保存，重启可验证。

## 多 Bot／多人格隔离核验

2026-09-24 补充核验：记忆事实和公共能力入口按稳定 owner 隔离。`companion_v2/memory/models.py:owner_key` 使用 `installation_id + bot_id + V2 role.subject_id + human subject_id + private` 生成归属键。不同 owner 的记录可以保存在同一个 V2 数据库中，读取、查询、写入和检索投影按归属过滤；这里是逻辑隔离，不是每个人格一份数据库。

| 场景 | 当前行为 |
| --- | --- |
| 同一用户、相同 V2 人格、不同逻辑 Bot | 事实读取与召回隔离，复用幂等键也得到不同操作 ID |
| 同一用户、同一 Bot、不同 V2 人格 | 事实、待提交提议、回执和订阅视图隔离 |
| 不同人类主体 | 即使各自在自己的窗口拥有记忆权限，也不共享私聊记忆 |
| 同一用户、Bot、V2 人格的不同私聊窗口 | durable 记忆可跨窗口召回，仍复核当前来源权限；session retention 保留原完整 scope 限制 |
| 同一窗口 A→B→A | 切换后旧角色上下文失效，B 无法读取 A 的事实；切回 A 并重新取得当前可信上下文后可读取 A 的长期记忆 |
| 拿到其他 owner 的 operation ID、subscription ID、batch 或 checkpoint | 不能查账、采用/丢弃提议、读取订阅/持久视图或恢复其他 owner 的投影；失败不改变原 owner 的记录 |

延迟提议的查询还限定 caller 和原 session，公共边界采用/丢弃复核完整原 `TaskContext`。`memory.operation.get` 按 owner、caller、namespace 查账；无权访问和未知操作均不返回回执。订阅、持久消费与恢复进一步绑定可信 context、owner、caller、权限/配置版本及安装 lineage，所以长期事实可跨窗口使用不代表窗口之间可以直接搬用订阅检查点。相同 subscribe 幂等键、subscriber generation 和 consumer 名称在不同 Bot／人格下得到独立视图，原 owner 的新增事件不会进入其他视图。

**人格配置边界：AstrBot 原生 persona ID／名称不是记忆归属键。** `NativePrivateBridge` 将 `(bot_id, AstrBot persona_id)` 映射为 `HostPersona.role`，真正进入 owner 的是该 V2 role 的 subject ID；当前 staging 由 `target.role_id` 指定。因此同一 Bot、同一用户下，两个原生人格若显式映射到相同 `role_id`，会被视为同一个记忆人格，符合来源权限的长期记忆可以共享。需要独立记忆的人格必须配置不同 `role_id`；仅改显示名称或提示词不会创建新的记忆分区。未登记的人格及提示词与登记版本不符的情况，原生桥会要求更新可信映射。

Bot 同样使用显式逻辑 `bot_id`；平台账号本身不进入稳定 owner。需要互相隔离的 Bot 应有不同 `bot_id`，同一逻辑 Bot 的多个已认证账号可继续使用其同一 owner。关系记忆单独按 `RoleOwnerRef(installation_id, bot_id, persona_id) + human subject` 保存，并由服务复核角色、私聊及来源权限。群聊没有接入这个私聊记忆 profile。

本轮补充 8 项隔离测试：直接读取/查询 2 项、延迟提议/查账/同键操作 3 项、订阅与持久消费 3 项；同时加强 A→B→A 切换验证。使用 AstrBot 自带 Python、临时 `ASTRBOT_ROOT` 和合成 V2 数据完成 **86 项定向测试，全部通过，无跳过**：记忆边界 10、pending 18、订阅 13、订阅边界 23、公共能力宿主 2、AstrBot 原生桥 10、关系记忆 10。真实返回协议对象 **451 份**通过 schema 校验（86 memory-result、256 subscription-result、19 change-batch、90 checkpoint）。本轮涉及的 7 个测试/辅助/文档文件通过 UTF-8 无 BOM、LF 和末尾换行检查，其中 5 个 Python 文件通过 AST 检查。

本轮没有修改运行时的隔离策略或数据结构，也没有访问 V1 用户数据。上述为核心、进程内公共入口及宿主替身验证；当前 AstrBot 宿主仍是单目标 staging，多 Bot／多人格同时在线运行尚未完成现场验收。

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -B -X utf8 tools/verify_memory_public_branch.py --contracts 'C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/docs/contracts/v1/schemas' --tests test_memory_boundaries test_memory_pending_wire test_memory_subscriptions test_memory_stream_edges test_memory_stream_host test_astrbot_native test_relationship_memory test_relationship_memory_service
```

## 延迟提交的宿主调用

先按[原提交示例](CORE_MEMORY_PROPOSAL_WIRE_SLICE_20260924.md)构造请求及由宿主签发的证据引用，再设置：

```python
from datetime import timedelta
from companion_v2.execution.models import stamp

request["payload"]["defer_until_boundary"] = True
pending = app.memory_commands.handle(context, request)
assert pending["status"] == "pending"
operation_id = pending["output"]["operation_id"]

# 在可信边界作出明确决定；不要因计时器到期或查账而自动采用。
resolved = app.memory_commands.resolve_pending(
    context, operation_id, decision="accept",  # 放弃时改为 discard
    deadline_at=stamp(app.tasks.now() + timedelta(seconds=30)),
)
```

`context` 必须来自宿主可信身份与原会话。原证据句柄到期后，已保存提议仍可用其原始证据复核；来源撤回和事实有效期到期仍阻止采用。普通反思流程经原 Writer 采用/丢弃该操作时，也会同步更新原 wire 回执。

操作返回 `uncertain / retryable=false` 时，使用[持久查账接口](CORE_MEMORY_PROPOSAL_WIRE_SLICE_20260924.md)核对同一个 operation id；不能另造幂等键重放事实。提交前预算或 deadline 失败会回滚事实及回执。已完成操作重复决定只返回最终回执。

`include_pending` 的事实页与草案页使用同一个有界 query session，不重新获得一份调用预算。续页保留原 trace、deadline、scope、预算及查询语义；原事实游标与草案游标共存。提议提交、丢弃或记忆/配置 revision 改变后，旧草案游标失效。撤回提议不会作为肯定草案展示。

## 订阅、快照与实时消费

以下示例在已启动宿主中运行；`context` 是可信 `TaskContext`，`consumer_id` 是宿主为该消费者固定的逻辑标识。示例只演示成功路径；任一控制失败应按下方恢复规则处理。

```python
from datetime import timedelta
from uuid import uuid4
from companion_v2.execution.models import stamp

streams = app.memory_subscriptions
views = app.memory_reference_views
consumer_id = "relationship-memory-view"

def control(kind, payload, *, key=None):
    request = {
        "schema_version": {"subscribe": "memory.subscribe.v1",
                           "ack": "memory.ack.v1", "resync": "memory.resync.v1"}[kind],
        "capability_id": "memory.changed." + kind, "capability_version": "1.0",
        "provider_id": streams.provider_id, "provider_generation": streams.provider_generation,
        "request_id": "request-" + uuid4().hex, "trace_id": "trace-" + uuid4().hex,
        "scope": streams.scope_for_context(context),
        "deadline_at": stamp(app.tasks.now() + timedelta(seconds=30)),
        "budget": {"max_input_bytes": 65536, "max_output_bytes": 65536, "max_model_calls": 0},
        "payload": payload,
    }
    if key is not None:
        request["idempotency_key"] = key
    result = streams.handle(context, request)
    if result["status"] != "succeeded":
        raise RuntimeError(result["reason_code"])
    return result["output"]

subscription = {
    "namespace": "personal", "visibility": "private", "purpose": "reply",
    "subscriber_generation": "consumer-" + uuid4().hex,
    "projection_kind": "references", "view_kind": "current_projection",
    "change_kinds": ["added", "corrected", "retracted", "expired"],
    "limits": {
        "max_batch_items": 64, "max_batch_bytes": 65536,
        "max_inflight_bytes": 65536, "max_inflight_batches": 1,
        "lease_ms": 30000, "max_retry_attempts": 3,
        "max_snapshot_bytes": 1048576, "max_staging_bytes": 2097152,
        "max_retained_log_bytes": 1048576,
        "recovery_deadline_at": stamp(app.tasks.now() + timedelta(hours=1)),
    },
    "start": {"mode": "snapshot"},
}
subscribe_key = "subscribe-" + uuid4().hex
bound = control("subscribe", subscription, key=subscribe_key)
target = {k: bound[k] for k in ("subscription_id", "subscriber_generation")}
views.bind(context, consumer_id, bound).unwrap()
page = control("resync", {**target, "action": "start"}, key="snapshot-" + uuid4().hex)
while True:
    views.stage_page(context, consumer_id, page).unwrap()
    if page["next_page_cursor"] is None:
        break
    page = control("resync", {
        **target, "action": "page", "snapshot_id": page["snapshot"]["snapshot_id"],
        "snapshot_epoch": page["snapshot"]["snapshot_epoch"], "page_cursor": page["next_page_cursor"],
    })

def consume_one():
    batch = streams.poll(context, **target,
        deadline_at=stamp(app.tasks.now() + timedelta(seconds=30))).unwrap()["batch"]
    if batch is None:
        return False
    checkpoint = views.apply_batch(context, consumer_id, batch).unwrap()
    control("ack", {**target, "lease_id": batch["lease"]["lease_id"],
        "target": {"kind": "batch", "batch_id": batch["batch_id"]}, "checkpoint": checkpoint})
    return True

while consume_one():  # snapshot_tail 到达服务端在最后一页签发的 C
    pass
checkpoint = views.activate(context, consumer_id).unwrap()
control("ack", {
    **target, "lease_id": page["activation_lease"]["lease_id"],
    "target": {"kind": "snapshot", "snapshot_id": page["snapshot"]["snapshot_id"],
               "completion_token": page["completion"]["completion_token"]},
    "checkpoint": checkpoint,
})
current = views.read(context, consumer_id).unwrap()
# 后续由调用方按需执行 consume_one() 消费 live 批次，再 read()。
```

快照在 W 固定引用集；分页期间新变化经 W→C tail 进入 staging，snapshot_tail ACK 不会提前激活。C 以后的变化在最终 snapshot ACK 后进入 live。旧引用存在但服务端尚未追上 owner 当前 revision 时，`read` 返回 `consumer_projection_behind`，不把缓存冒充当前视图。事件和快照仅含 atom id/revision，不携带事实正文；读取正文仍走原 Memory 授权入口。

消费者事务把引用应用、inbox 去重和 checkpoint 一起保存。同一批跨租约重发保留 batch/event id，只有 lease 更新；空批次和经过过滤的批次仍推进权威 cursor。`current_projection` 必须包含全部四类变化并以 snapshot 或 resume 开始；`notifications` 可过滤并从 live 开始，不能用其结果宣称拥有完整当前事实投影。

## 恢复与资源回收

重启后用新宿主入口与同一个 `consumer_id` 读取 `views.recovery_checkpoint(context, consumer_id)`。只有 `state=active` 的持久 checkpoint 可放入新 subscribe 请求的 `start={"mode": "resume", "checkpoint": ...}`；为该次恢复生成新的 subscriber generation 和 subscribe 幂等键，再 `views.bind`。更换 provider generation 后，已验证的安装 lineage、owner、caller、视图及权限/配置 binding 必须一致。恢复成功后保留原 snapshot、projection generation 和 cursor，可以继续接下一批。

staging 的 pages/tail checkpoint 不可冒充 active；重启中断在这两个阶段时重新 snapshot。权限、配置或来源变化，未来 valid_from 已到点，未确认 snapshot 的 epoch 已过期，或日志超过恢复预算时，必须重新建立完整投影。resume 返回 `resync_required` 后可在新订阅上发新的 resync start。若本地活动投影已丢失，`bind` 会返回 `consumer_checkpoint_unavailable`，需要新建 snapshot 订阅，不能仅凭外部拷贝的 checkpoint 宣称空视图已恢复。

subscribe/resync start 的幂等键应保存在调用方恢复状态中。未知控制提交不会重试事实；可核对同键控制或本地 checkpoint。相同活动 start key 重取相同页，已经结束或失效的 epoch 不能通过旧 key 复活。旧批次、旧租约、旧 generation、伪造的未来 cursor 和未发出的 page/batch 均无法 ACK。消费或 ACK 的提交确认丢失后，重新读取 checkpoint / 重复同批 ACK 可恢复。

当前 profile 为单 in-flight、顺序派发，最多 64 项/64 KiB 每批、3 次租约重发；snapshot 最长 10 分钟，订阅恢复期限最长一天。完整快照候选最多 8192 个，pending 查询候选最多 256 个；超额明确失败或要求重同步，不激活部分投影。默认 snapshot 1 MiB、staging 2 MiB、replay backlog 1 MiB；请求上限与 provider 上限取较小者。激活租约与普通租约同样受期限限制：超过租约可用仍有效的已激活 checkpoint 重新订阅，未完成或已过期 epoch 则新建快照。

每个安装最多 64 个订阅和 64 个本地消费视图；新建时清理本命名空间的过期记录。每订阅保存最多 32 个 resync start key、8 份 ACK 记录；inbox 保存最近 32 批。新 epoch 额度耗尽时使用新订阅。`views.close(context, consumer_id)` 删除该消费记录并 fence 对应订阅代，服务端记录已过期清理后也能关闭孤立消费记录；`streams.close_subscription` 可停止指定订阅。fenced 服务端记录保留至恢复期限，以防旧键复活，仍占订阅名额。上述是协议状态预算，不是事实历史数据库的磁盘总配额，也未作 RSS/WAL 生产压力验收。

## 验证与范围

原分支交付时，受影响范围按测试 ID 去重 **274 项全部通过，无跳过**，其中交付新增 50 项；后续隔离核验新增 8 项并完成上方 86 项定向验证。以下保留原交付实际执行批次，不与后续定向批次或原提交切片的 190 项历史数字直接相加：

- 主回归 272 项通过，覆盖记忆查询/Writer/反思与恢复、命令/provider、统一宿主、存储，以及 AstrBot 加载、停机、路由注销和核心隔离。
- 补齐 resume 的未来 valid_from 与未确认 snapshot 到期校验后，最后 35 项订阅/边界/宿主测试全部通过；其中 33 项与主回归重叠，新增 2 个测试 ID。
- 主回归真实协议对象 482 份通过 schema 校验：163 memory-result、227 subscription-result、18 change-batch、74 checkpoint。最后复验 334 份通过：3 memory-result、235 subscription-result、18 change-batch、78 checkpoint；这两批统计单独保留，不当作不同协议场景数。

新增四组测试是 `test_memory_pending_wire`（15）、`test_memory_subscriptions`（13）、`test_memory_stream_edges`（20）、`test_memory_stream_host`（2）。涵盖待提交查账、来源撤回/有效期/CAS、同会话草案与共享预算、提交前回滚/提交后确认丢失、快照并发变化、页乱序与旧 epoch、重复批次/租约/ACK、跨重启继续消费、配置双向变更、自然有效期、容量与过期回收。宿主链明确断言相关消费过程没有模型或 sender 调用。

本批 31 个源码、测试、脚本与文档通过 UTF-8 无 BOM、LF、末尾换行、无尾随空白检查；Python AST、文档 Python 示例语法及相对文档链接检查通过。最后移除未使用 import 后，相同 35 项定向测试再次通过，测试和协议对象计数不重复累计。

可复现命令（在 V2 工程目录）：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -B -X utf8 tools/verify_memory_public_branch.py --contracts 'C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion/docs/contracts/v1/schemas'
```

[验证脚本](../tools/verify_memory_public_branch.py)在导入 SDK 前使用临时 ASTRBOT_ROOT；按测试 ID 去重，包装真实接口返回值进行 Draft 2020-12 和日期格式校验，并重新计算 13 个 review schema 的合同指纹。锁定指纹为 `3a41420f40fcd7dc8b8e2d990c8c5b3bd47cde8a998c88339daa9c71dadaaee2`。验证依赖 `jsonschema`/`referencing`，没有增加插件运行依赖。

本分支完成的是可信进程内 API 和内置持久引用消费者。跨进程 SDK、通用写能力目录、第三方包实际消费者、review 合同正式发布及生产规模验收仍在后续范围。协议设计 fixture 的原始 `not_run` 状态未修改，本批本地测试不能充当双宿主互通或完整压力测试证据。测试使用临时 V2 数据、合成来源、模型及发送替身；未在线重载、真实模型调用、QQ 发送或读取/迁移 V1 用户数据。
