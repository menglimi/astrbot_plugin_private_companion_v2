# 模型失败分类与持久诊断

日期：2026-09-23。针对[现场第二批模型 unknown](CORE_ASTRBOT_STAGING_HOST_SLICE.md)缺少具体阶段的问题，新增模型调用失败分类、原子持久记录及授权查询。该改动让新调用可以定位失败阶段；历史批次没有保存的原因仍无法还原。

## 失败记录

`companion_v2/model_gateway/failures.py` 定义固定错误码和阶段。`ProviderResponse.failure` 只接受该枚举，不能放入模型正文、提示词、凭据、URL 或异常字符串。成功生成时没有失败分类；模型用量是否已知仍由独立字段表示。

| 阶段 | 错误码 | 能说明的事实 |
| --- | --- | --- |
| `preparation` | `request_preparation_failed` | 派发前准备或 owner 复核失败，返回 `not_started` 和零用量。 |
| `provider_request` | `provider_request_failed` | 原生查询调用失败；不能据此断言服务端未执行。 |
| `native_parse` | `native_response_parse_failed` | 已进入原生回复解析，解析抛出异常。 |
| `provider_recheck` | `provider_recheck_failed` | 原生调用返回后的 provider/client/configuration 复核失败。 |
| `role_recheck` | `role_recheck_failed` | 原生调用返回后的会话/人格复核失败。 |
| `response_validation` | `response_contract_rejected` | 回复或工具调用未通过既有 wire 合同校验；分类不保存被拒绝的内容。 |
| `gateway_adapter` | `adapter_failed` | 适配器抛错或未返回合法结果，网关无法确认处理结果。 |
| `gateway_wait` | `provider_wait_interrupted` | 等待被取消，包含执行器超时导致的取消。 |
| `gateway_recheck` | `request_recheck_failed` | 回执已结算，但当前任务、资料、授权或配置复核使生成结果被丢弃。 |
| `recovery` | `runtime_interrupted` | 恢复时发现旧运行代仍有已派发调用，无法确认结果。 |

AstrBot 适配器在原生解析回调中保留用量来源；解析、响应后复核或 wire 失败均继续返回 unknown。失败分类与实际用量分别保存，`unknown` 可以同时具有 `usage_state=settled`。新分类不会触发重试、备用模型或平台发送，也不会把拒绝的回复改成成功。

## 持久化与查询

V2 内部 schema 从 v14 升至 v15，新增 `model_call_failures(call_id, code, observed_at)`，外键归属于原 `model_calls`。用量结算与分类写入同一事务；每个调用保留首次分类，重复回执、迟到用量对账不会覆盖它。生成后复核失败及重启恢复也通过账本记录。

`LocalModelGateway.observe()`、公共诊断服务和 staging `/inspect?batch_id=...` 共用该记录，并继续检查原任务权限。每个 call 新增可空的 `failure` 字段。以下是合成测试示例：

```json
{
  "state": "unknown",
  "usage_state": "settled",
  "actual_tokens": 40,
  "failure": {
    "phase": "response_validation",
    "code": "response_contract_rejected",
    "observed_at": "2026-09-21T00:00:00+00:00"
  }
}
```

历史调用没有分类时返回 `failure=null`，不解释成成功，也不补猜原因。既有 unknown 调用仍不能重新生成；恢复只给尚处于 dispatched 的旧运行代调用记录恢复中断。

v14 及更早的迁移语句和指纹保持原值。升级原子执行，拒绝不完整的新表或被修改的迁移指纹；失败回滚后可重试打开。新建与旧库加载均验证 v15 结构。这里仅涉及 V2 自己的内部数据库格式。

## 验证

本轮在 AstrBot 自带 Python 下完成以下定向检查，三组 unittest 共 129 项通过，原生契约另有 12 项通过：

- 模型网关、失败诊断、AstrBot wire 和隔离：44 项。覆盖分类、已知/未知用量、重启后查询、原任务权限、对账幂等、撤权、取消、备用模型和未知结果不重放。
- 模型失败表及受影响的历史升级路径：50 项。覆盖有数据的 v14 升级、旧记录保留、失败回滚、未来表拒绝、指纹及此前迁移链。
- 宿主管理路由与 bootstrap：35 项。通过 `/inspect` 读取合成失败，确认分类与已结算用量可见，正文不可见且没有发送。
- AstrBot 4.27.2 原生契约：12 项，网络尝试 0 次。实际 SDK 类型配合 HTTP/WebSocket 替身，验证查询失败、原生解析失败与 wire 拒绝的分类。

另将现场 `sender-2` 的 v14 SQLite 以只读方式备份到系统临时目录，在副本上执行 v15 升级及重开：55 张既有业务表的记录摘要全部一致；5740 tokens 的 generated、5960 tokens 的 unknown 和一条已确认发送均保留，新失败表为空。原现场数据库文件哈希未改变，没有调用模型或重放历史批次。

复现命令在 V2 源码目录运行：

```powershell
$companionPython = 'C:/Users/99505/.astrbot/backend/python/python.exe'
& $companionPython -X utf8 -m unittest tests.test_model_gateway tests.test_model_failures tests.test_astrbot_model_wire tests.test_isolation -q
& $companionPython -X utf8 -m unittest tests.test_model_failure_storage tests.test_host_storage tests.test_model_storage tests.test_conversation_storage tests.test_storage_migrations tests.test_configuration_storage tests.test_agenda_storage tests.test_object_access_storage tests.test_scope_storage -q
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& $companionPython -X utf8 -m unittest tests.test_astrbot_staging_host tests.test_astrbot_staging_bootstrap -q
& $companionPython -X utf8 tools/run_native_contracts.py --host-source 'C:/Users/99505/.astrbot/backend/app'
```

上述自动测试之后，2026-09-23 已通过正常 Dashboard 登录和 V2 定向重载，在新的 `sender-3` profile 中确认在线核心运行 schema v15。新私聊批次在 provider 请求阶段失败，`provider_request_failed` 通过 `/inspect` 可见，撤权、停机并恢复关闭配置触发的重载后，该分类仍持久保留。实际用量未知，没有生成分段、工具调用或发送；这次请求的具体 HTTP 原因仍未记录。新批次、独立 provider 探测及收尾结果见[现场复验](CORE_ASTRBOT_DIAGNOSTICS_LIVE_20260923.md)。历史 `sender-2` 仍为 v14，旧第二批的根因仍未确认；本轮只得到请求失败分类的现场证据，既有单次 ACK 也不代表完整 Delivery 验收。
