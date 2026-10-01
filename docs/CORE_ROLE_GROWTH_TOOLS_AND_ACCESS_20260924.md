# CORE-05 后续：成长角色工具与读取权限

本切片完成成长功能的非页面部分：角色可在普通私聊工具续答中查询、提交和修订待确认提案；CORE 管理者可为当前 pinned profile 的参与者单独设置读取及提案权限。管理页与来源选择器由另一个窗口继续，本批只增加其可调用的后端合同。

## 角色工具

| 工具 | 输入 | 实际效果 |
| --- | --- | --- |
| `role.growth.list` | 可选 `kind`、`state`、`limit`（默认 5，1..20）、`after_id` | 查询当前角色、Bot、完整私聊 scope 的记录摘要，包括待确认和已闭合项。 |
| `role.growth.propose` | `kind`、`title`、`evidence_handles`；可选 `description`、`progress_note` | 保存 `proposed` 提案，返回持久操作回执，不产生确认。 |
| `role.growth.revise` | `growth_id`、`expected_revision`、完整 `title/description/progress_note` 和 `evidence_handles` | 按原版本修订仍为 `proposed` 的提案。人类已确认的记录须另提新提案供审阅。 |

工具由 `LocalRoleTools` 装配到原角色模型会话。身份、角色、受众和实际操作归属来自原批次；模型不能传入 operator、scope、SourceRef、confirmed_by 或目标账户。工具提交归属当前参与者的会话，不等于参与者本人已明确确认；`confirmed_by` 保持空值。角色没有确认、暂停、完成、退休或权限修改工具；现有已认证人类管理 API 继续承担这些操作。

`growth_evidence_handles` 将本轮已封存输入映射为 `growth-input-<position>`，用途对应 `current_source` 或 `merged_input:<event_key>`。宿主额外提供的原件映射为 `growth-source:<host handle>`；读取时复用原 capability。1..8 个唯一 handle 只能在当前批次解析，来源须为同一精确 scope，并在写入前重验当前权限、内容治理和受众。记录只保存原来源引用。

查询完整保留标题，描述及进展各最多展示 1024 字符，并通过 `truncated_fields` 明示摘要。单次材料预算 48,000 UTF-8 字节，分页在最后实际处理的记录后续读；无权/失效来源条目计入 `skipped`，`selection_partial` 不代表内容完整。省略项不能解释为不存在。未确认提案可通过主动工具查询获得，但不会进入自动的 active/paused 成长提示。

工具回执沿用原批次及调用编号生成稳定 operation ID，与成长修订和工具调用结果同事务提交。重复调用返回首次回执；unknown/started 不重放。回执仅报告 `applied_revision`、当时的 `applied_state` 与待确认状态，不复制提案正文，也不把早期回执称为当前状态。

## 续答、发送与来源治理

查询结果在每次模型续答、逐段发送和历史正文读取时，重验原身份、read/propose 权限、角色绑定、完整 scope、记录版本及所有来源。后续本轮修订必须由实际成长回执证明连续版本链；旧查询整体标为 `superseded`，模型可重新查询。同轮更新不能刷新其他领域的提示，不能接受另一窗口或人类并发改动，更不能把旧 confirmed 成长材料悄悄换成新版本。

已发送回复进入记忆原文时，成长工具使用的来源也登记到 `source_dependencies`。撤回原件会使派生原文失效；实际发送回执仍保留。成长文字本身不会被包装成 observed 事实证据。表达风格和“主观进展不等于现实能力、提案不等于确认”的边界由中文工具提示约束。

## 管理页可直接使用的后端合同

既有路由不变。`GET /astrbot_plugin_private_companion_v2/growth` 保留原 `items/create_token/next_cursor` 等字段，新增：

```json
{
  "access": {
    "settings": {"read_enabled": false, "proposals_enabled": false},
    "effective": {
      "read_enabled": {"allowed": false, "reason": "authorization_missing"},
      "proposals_enabled": {"allowed": false, "reason": "authorization_missing"}
    },
    "edit_token": "本次读取返回的编辑令牌"
  }
}
```

`reason` 是实际授权错误码，不保证为示例值；可用时为 `null`。设置默认 false，表示此配置入口未额外发放 STANDARD grant。有效权限同时考虑当前身份等级和其他独立授权，因此页面须区分 `settings` 与 `effective`：CORE/IMPORTANT 仍遵守公共等级策略；关闭本入口只撤销它自己发出的授权，不撤销其他入口的独立授权。提案实际可用需同时具备 read 和 propose。

`POST /astrbot_plugin_private_companion_v2/growth/command` 新增命令：

```json
{
  "action": "configure",
  "operation_key": "本次操作的稳定唯一编号",
  "edit_token": "GET 返回的 access.edit_token",
  "changes": {"read_enabled": true, "proposals_enabled": true}
}
```

`changes` 可只含其中一项，但必须非空且值为 boolean。配置命令不用成长记录的 `view_token`。成功返回 `operation_id`、`replayed` 和当前 `access`；旧编辑令牌报冲突。重试原操作保留同一个 key 和原参数，返回原回执及当前权限视图；若后来已经关闭，重试不会重新开启。配置不调用模型或发送消息。

字段注册于统一配置的 WINDOW 组 `role.growth`，owner 为 `role.growth.access`，仅 CORE 可配置。`GrowthConfigurationOwner` 同事务修改稀疏设置和精确参与者/scope 的 read/propose grants；通用配置入口与 reset 也经过同一 owner。授权写入失败会回滚设置和操作回执。角色工具不能调用配置服务。

## 文件归属与验证

- `companion_v2/role_work/growth/tools.py`：工具合同、查询、提案、回执和原结果复核。
- `companion_v2/role_work/growth/tool_sources.py`：本轮来源 handle 的可信映射。
- `companion_v2/role_work/growth/configuration.py`：统一配置字段及授权写入 owner。
- `companion_v2/role_work/growth/access_management.py`：已认证管理者的权限视图和设置服务。
- 对话工具注册及宿主装配复用既有模块；HTTP 适配继续归 `astrbot_host/growth_api.py`。

没有新增数据库表或 schema 版本，根目录没有新增 Python 文件。验证使用 AstrBot 自带 Python、临时 V2 数据根和本地模型/发送替身，不访问 V1 用户资料，不调用真实模型或平台。

新增测试模块：`test_role_growth_tools`（12 项）、`test_role_growth_access`（7 项）、`test_role_growth_access_api`（2 项）、`test_role_growth_tools_host`（2 项），共 23 项通过。覆盖宿主完整工具续答、同轮修订链、幂等及 unknown、无权/跨 scope/伪来源、配置原子回滚、通用配置与 reset、旧操作重试、重启、派生记忆来源撤回，以及不得借成长刷新替换其他 owner 提示。

相关验证分批执行：成长既有 API/宿主上下文和工具续答 29 项通过；访问设置/成长宿主/记忆对话 16 项通过；扩展宿主/工具/配置/记忆恢复 143 项中，141 项通过，2 项旧生命周期测试仍依赖固定的路由数量/名单。共享代码的路由已增至 24 条，测试改为核对实际 handler 归属和替换实例隔离；随后宿主 15 项复验全部通过，没有重跑完整 143 项集合。各批数字有重叠，不累计为独立总数。

定向复现命令：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_growth_tools tests.test_role_growth_access tests.test_role_growth_access_api tests.test_role_growth_tools_host -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_growth_tools tests.test_role_tool_loop tests.test_host_application tests.test_host_external_tools tests.test_astrbot_staging_host tests.test_astrbot_staging_bootstrap tests.test_configuration tests.test_configuration_storage tests.test_management_access tests.test_memory_recovery -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_staging_host -q
```

既有成长读取/API 测试的历史证据见[上一切片](CORE_ROLE_GROWTH_CONTEXT_SLICE_20260924.md)。
