# V2 原生能力提供方最小合同

2026-09-25。协议版本 `companion.native-provider.v1`。本合同供本体宿主、Image 原生执行器及独立验收共同使用；提供方不导入另一个插件的核心 Python 类型。

## 公开入口

已加载且启用的 AstrBot 插件实例提供同步方法 `extension_api.companion_v2_native()`，返回当前实例持有的稳定端口对象。端口提供：

```python
def manifest() -> dict: ...
async def execute(request: dict, *, before_dispatch) -> dict: ...
async def lookup(request: dict, *, before_dispatch) -> dict: ...
async def read_artifact(request: dict, *, before_dispatch) -> bytes: ...
```

Image 的 `execute` 可选接收 `host_references=()` 与异步回调 `fetch_reference(handle, content_hash, *, role)`。它们是执行参数，不是新的端口方法，也不进入请求/响应封套；不支持该扩展的提供方继续只接收 `request` 与 `before_dispatch`。

`manifest()` 只读、同步、有界。`execute` 为必需，其余两项按能力实现。`lookup` 只能读取原操作回执，不能补发、重试或生成；当前宿主注册表不提供自动 lookup/replay 流程。`read_artifact` 只读取原操作的不可变产物，不接收任意 URL/本地路径。执行前调用同步 `before_dispatch()`，若抛错立即停止；所有真正 I/O 前再次调用该回调。回调仅在本次 awaited 调用期间有效，返回后不可保留复用。`companion_v2_status()` 仅用于状态目录，不能替代本入口。

Image 执行参数中的 `host_references` 是宿主为当前私聊调用签发的只读 offer 序列，每项严格包含 `reference_handle`、`reference_id`、`source_key`、`content_hash`、`position`。提供方不得从模型 arguments 自行构造这些 offer。`fetch_reference` 每次读取前由提供方调用 `before_dispatch()`，并以匹配的 handle、SHA-256 和用途（如 `edit_source` / `edit_mask`）读取字节；宿主重新核对 scope、受众、来源与调用上下文并立即消费该 handle。句柄只在原次 awaited 执行期间有效且只能消费一次；重试或恢复必须重新由宿主授权并签发，不得持久化或复用旧句柄。此扩展当前只提供本轮已授权的私聊图片，不代表任意跨插件素材均可读取。

## 声明

```json
{
  "schema": "companion.native-provider.v1",
  "plugin_id": "astrbot_plugin_image_companion",
  "provider_id": "image.native",
  "generation": "stable-package-and-backend-config-revision",
  "package": {
    "extension_id": "image",
    "package_id": "astrbot_plugin_image_companion",
    "publisher_id": "menglimi",
    "package_version": "0.5.0",
    "artifact_hash": "sha256-of-native-package-artifact",
    "capabilities": ["image.generate"],
    "dataset_owners": ["image.native"]
  },
  "tools": [{
    "action": "image.generate",
    "capability": "image.generate",
    "source_owner": "image.native",
    "description": "生成图片并返回原操作与产物回执；发送由 V2 负责。",
    "parameters": {"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"], "additionalProperties": false},
    "side_effect": "external_network",
    "timeout_seconds": 60
  }]
}
```

`plugin_id` 与当前 Star 的目录身份一致，`package_id` 与之相同，`package_version` 必须与 Star 版本一致。`generation` 由包版本、artifact hash 和后端配置 revision 推导，正常重启必须复用同一世代，不能使用随机进程 ID；配置或包变化会改变世代。端口关闭和租约撤销独立使旧运行实例失效。宿主还核对 Star、插件实例、extension_api 和端口对象身份及完整声明；旧注册表即使看到相同 generation，也拒绝被新对象偷换，必须创建新的注册表。所有 action 唯一，复用现有闭合参数 schema 与统一 64 项目录预算；实际模型目录按原上下文授权和当前可用性收集，不因未授权工具阻塞本体构造，详见[工具目录修复](CORE_TOOL_CATALOG_20260925.md)。

发现和 `load_existing` 只读取声明；显式启动单/多目标宿主时，以事务登记当前提供方的声明目录，任一冲突会整体回滚。这些操作均不自动 acquire、启用角色或授予 capability 权限。加载状态和目录登记不表示取得执行权限。

## 请求与响应

宿主把原 `TaskContext`、`ProviderBinding` 转为普通 JSON：

```text
request = {
  schema, invocation_id, parent_task_id, tool_call_id, action,
  origin_key, context, binding, arguments, arguments_hash, deadline_at
}
```

`context` 为原 actor/role_binding/audience 的 JSON，`binding` 为 capability/provider/version/generation；目标身份不从模型 arguments 取值。`arguments_hash` 是 V2 原 JSON 规范化摘要，提供方原样返回，无需导入 core 算法。

```text
response = {
  schema, invocation_id, origin_key, arguments_hash, binding,
  state: succeeded | failed | unknown,
  effect: none | committed | not_committed | unknown,
  operation_id: string | null,
  receipt_ref: string | null,
  result: JSON object | null,
  artifacts: [
    {artifact_id, operation_id, content_hash, mime_type, size_bytes}
  ]
}
```

`schema` 都为 `companion.native-provider.v1`。响应绑定字段必须逐项等于原请求。成功响应必须有 `result` 对象；失败/未知不带成功材料或产物。effect 与已声明 SideEffect 遵循已有 ExternalToolResponse 合同；有副作用成功须保留 operation_id/receipt_ref，未知绝不自动重放。

`artifacts` 只传元数据，`content_hash` 使用原始 bytes 的 SHA-256 小写十六进制，`size_bytes` 是真实字节数，`operation_id` 必须与响应一致。宿主使用 `read_artifact({**原 request, operation_id, artifact_id, content_hash}, before_dispatch=...)` 读取 bytes，并核对大小及哈希；不会把 base64 放进模型提示，也不会从产物标识推断文件路径。

## 宿主装配与领域采用

`astrbot_host.native_extensions.NativeExtensionRegistry(context, ...)` 实现现有 AstrBotToolPort：`declarations()`、`current_declaration(host_tool_id)`、`invoke(host_tool_id, invocation)`。`attach(application)` 安装原运行代/权限护栏；`close()` 立即使旧注册表失效。`register_catalog(observed_at=...)` 在显式管理调用或宿主显式启动时登记声明，不 acquire 或授权。每次重建 session 使用新的注册表，无声明时不创建 ExternalToolExecutor。

通过构造参数 `result_handlers={action: handler}` 注册同步领域回调 `handler(invocation, native_result)`；默认包含 `image.generate` / `image.edit` / `image.mask_edit`。`native_result` 是本体内部对象，含 `result` JSON、`operation_id`、`receipt_ref` 和已核对的 artifacts（artifact_id/operation_id/content_hash/mime_type/size_bytes/content bytes）。回调返回 core 内部的 `ExternalToolResponse`，Image 领域可附 `images`；宿主核对原绑定及产物元数据，真实发送只由 V2 sender 执行。无产物的成功结果由宿主创建有原 owner、scope、audience 的 SourceRecord，正文保留提供方操作标识和结果 JSON。

调用前、实际 I/O 前、产物读取前后及结果采用前复核当前实例、声明、包选择、角色、权限、截止时间及运行代。原生角色另外通过宿主 bridge 在异步边界前后核对。`ExternalToolInvocation.before_dispatch` 为向后兼容的可选同步回调，核心绑定原 child/parent task 校验和能力授权；原生端口要求实际调用。

宿主收到返回值后，先按未被提供方修改的原请求校验完整回执，再复核读取与采用权限。已校验的成功回执不会因随后撤权、实例更换、期限届满、任务取消、制品损坏或采用器失败而改成 unknown：保留原 `succeeded/effect/operation_id/receipt_ref`，返回 `images=()` 及撤销态 SourceRecord，其正文为 `{"native": 原始 metadata, "adoption": {"state": "unavailable", "code": 具体错误码}}`。该 Source 只供留据，不能进入模型材料或发送；不存在采用器时也采用此规则。尚未收到回执的取消仍传播，错绑或格式不合法的响应不构造成功材料。

提供方也必须保留已经获得的真实后端控制回执：后置撤权检查不能吞掉已完成的 operation/receipt，也不能把它重写成 unknown。落账后可返回控制回执；继续读取制品、lookup 的新 I/O 和任何新后端请求仍须重新通过当前 guard。核心将回执持久化与图片采用分开，采用不可用时不建立空图片清单。

合成验收可向 context.get_all_stars() 返回 `root_dir_name/name/version/activated/star_cls.extension_api` 的合成 Star；提供方实例只暴露上述普通对象协议，V2 管理测试沿用 CapabilityRepository 的 register/acquire/set_role_enabled/set_authorization，不使用 V1 数据或在线插件重载。
