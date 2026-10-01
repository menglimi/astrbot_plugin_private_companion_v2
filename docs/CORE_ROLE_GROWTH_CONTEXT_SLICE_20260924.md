# CORE-05 后续：角色成长授权读取与管理 API

日期：2026-09-24。角色技能/长期目标现可由普通私聊读取，并通过已认证的 AstrBot Dashboard API 显式提议、确认、修订、暂停、恢复、完成目标或退出。此切片复用 v22 正本、当前身份体系及 source 治理，不增加数据库表。

`RoleGrowthContextReader` 从可信成长 ledger 选取当前角色、当前完整私聊 scope 中处于 `active` 或 `paused` 的记录。调用必须通过当前任务身份授权，受众必须是当前已认证人类且为精确单人私聊。所有 source 引用在候选读取和提示重建时分别复核：必须属于同一个完整私聊 scope，并且在读取时仍有效、未撤回、source 依赖有效且当前参与者仍属于其 audience。

对话封存只存成长 ID 与 revision，不持久化成长文字。重建提示时重新读取同一 role owner 下的记录，并重验 revision、state、scope、更新时间、当前身份和所有 source。身份/role binding 撤销或变化、source 撤回/过期/受众变化、成长记录被修订时，原引用不会回退到新版本或未经复核的正文。新修订按账本合同回到 `proposed`，不会继续作为 active 提示材料。

单轮最多选取 8 条成长记录和 10,000 个字符；候选扫描每种可读状态最多 32 条，超额时保留 `selection_partial` 提示信息。记录采用确定性 ID 排序。普通对话只会看到明确确认的 active/paused 项；提案与闭合项不会被选中。提示说明成长材料是角色的主观记录，不构成用户目标或现实能力证明；目标不被表达成已经完成的行动，资料文字不被当作指令。该消费者不会把成长正文作为 `SourceRef` 事实证据提供。

读取动作注册为非分享型 `role.growth.read`，沿用公共三级权限：STANDARD 参与者需要该动作在精确 scope 下的有效 grant；IMPORTANT 的自有私聊和 CORE 仍按已有策略判断。宿主既有私聊任务边界同时要求当前身份、绑定、角色选择、原私聊路由及单一受众。来源读取只检查治理状态与受众，不读取 source 原文；source 引用仍保留在成长正本供完整审计。普通对话在封存前读取不可用时可继续回复；已经选入的材料在生成中或逐段发送前失效时，旧草稿/未发部分失效，已发生的回执和用量保留。

## 管理合同

`role_work/growth/management.py` 实现领域管理门面；`astrbot_host/growth_api.py` 仅处理宿主登录、参数解码和当前 pinned profile。操作人由 `request.username` 经既有 `dashboard_operator` 映射为独立人类 `SubjectRef`，写入 proposed/confirmed/changed 归属。操作人须有当前 CORE 权限，调用须通过 `role.growth.manage`；聊天参与者仍是资料受众，不能把操作者冒充成参与者。撤销/降级的管理员不会自动恢复，API Key 不视为人类管理员。

目标由已装载 profile 提供；每次读写验证原参与者、Bot/账号路由、角色绑定和精确私聊 scope。GET 列表在读快照中返回按 ID 分页的当前记录、当前不可用原因和视图凭据；来源失效时标题/描述/进展置空。POST 的变更在一个事务内完成授权、来源复核、版本检查和回执写入。初次提案也有持久回执；重复 operation key 的参数必须相同，重启或后续修订后重试不会新增记录或恢复旧正文。旧命令回执返回原 `applied_revision`，`item` 总是经过当前来源校验的最新记录。

| 入口/动作 | 参数与行为 |
| --- | --- |
| `GET /astrbot_plugin_private_companion_v2/growth` | 可选 `kind`、`state`、`limit`（1..50）和 `after_id`；返回 `create_token`、记录 `view_token`、revision、可用动作及下一页 cursor。 |
| `POST /astrbot_plugin_private_companion_v2/growth/command`：`propose` | 使用列表 `create_token` 作为 `view_token`，提供 `operation_key`、`kind`、`title` 和 1..8 个完整原 `SourceRef`；`description`、`progress_note` 可省略。起始为 `proposed`。 |
| `confirm` / `resume` / `pause` / `complete` | 提供记录 `growth_id`、`expected_revision`、`view_token`、`operation_key`。确认仅适用 proposed，恢复仅适用 paused，完成仅适用 active/paused 的目标；技能没有 complete。 |
| `revise` | 同上，并提供完整 `title`、`description`、`progress_note`；可提供新来源，省略时沿用原 revision 的来源。修订后重新 proposed 并清空确认；来源失效时可提供新有效来源重新提案。 |
| `withdraw` / `retire` | 同上。withdraw 用于 proposed，retire 用于未闭合记录；退出时可保留失效来源的原引用而不显示正文。二者都落为 retired，完整历史保留。 |

SourceRef 参数必须完整匹配 V2 当前来源正本的 ID、owner、scope、version、issued_at 和 expires_at；服务不接受新正文冒充已有证据。旧视图不能跨操作人、角色、参与者、scope 或权限版本使用。请求正文不能指定 operator、目标 context、直接状态或确认归属。路由与现有插件生命周期一起注册/注销，停机后允许管理已装载的 profile，终止后拒绝访问。

管理确认不会自动授予参与者成长读取权限，也不会启动日记、模型或平台发送。后续[成长工具与授权设置](CORE_ROLE_GROWTH_TOOLS_AND_ACCESS_20260924.md)已补齐 STANDARD 读取/提案开关及角色提案工具，并在现有列表和 command 路由中提供 `access` 视图与 `configure` 命令。管理页面、来源选择器由另一窗口接续。退出保留审计历史，不等于物理擦除。完整自我时间线、跨 scope 成长共享和 V1 数据迁移仍不在本切片内。

## 验证

新增定向测试覆盖身份与读 grant 撤销、跨人/跨 scope/角色切换、来源撤回/过期/受众拒绝、版本竞态、提示预算、生成期间修订、已发回执保持、重启后的原引用重读、操作重放与冲突、独立管理归属、无权限/伪参数/重复字段拒绝，以及宿主路由注销。测试仅使用临时 V2 数据根和本地替身，无真实模型调用、平台发送或 V1 用户资料访问。

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_growth_storage tests.test_role_growth_context tests.test_role_growth_context_host tests.test_role_growth_management tests.test_role_growth_api -q
```

成长领域共 40 项（含既有正本 5 项）已通过。扩展验证执行 193 项，其中 191 项通过，2 项失败是旧宿主测试仍断言 17/19 条路由及旧名单；当前共享树包含本批成长 2 条和同期记忆管理新增 3 条，共 22 条。修正路由断言后，对宿主生命周期和成长 API 的 22 项复验全部通过；没有重跑整个集合。这些数字有交集，不累加为独立测试总数。

扩展验证命令：

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_growth_storage tests.test_role_growth_context tests.test_role_growth_context_host tests.test_role_growth_management tests.test_role_growth_api tests.test_storage_migrations tests.test_object_access tests.test_management_access tests.test_conversation_messages tests.test_role_life_context tests.test_relationship_context tests.test_host_application tests.test_astrbot_staging_host tests.test_relationship_management_host tests.test_isolation -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_staging_host tests.test_role_growth_api -q
```

22 份本批改动文件的 UTF-8、无 BOM、LF、末尾换行及 Python 语法检查通过；源码根 Python 仍只有 AstrBot 要求的 `main.py`。本批未在线重载插件，以上是隔离数据根下的实现与宿主合同证据。
