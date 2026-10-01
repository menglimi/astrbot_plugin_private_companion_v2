# CORE-05：角色活动持久化与宿主接入

日期：2026-09-23。沿[本体实施路线](V1_CORE_FEATURE_PREREQUISITES.md)第 4 步，完成连续生活的首批基础：角色活动、已保存进度和产物引用进入 V2 正本，由统一宿主持有。活动暂停后关闭宿主、重开数据库，仍能读到原版本和进度，再通过显式操作恢复。完整日记、梦境、关系记忆及生活调度仍待接入。

## 领域归属与接口

实现位于 `companion_v2/role_work/`：`models.py` 定义记录和状态变更，`codec.py` 恢复持久记录，`ledger.py` 提供 `PersistentRoleLifeLedger`。`CompanionApplication.role_life` 使用应用已有的 `StorageRuntime` 和注入时钟；未引入另一套数据库、任务循环或根级业务模块。原 `RoleLifeLedger` 保留给现有内存场景，状态转换复用同一函数。

| 接口 | 已实现行为 |
| --- | --- |
| `add_activity(activity)` / `activity(id, owner=...)` | 保存和读取活动；新记录从 revision 1 开始，保留创建 scope、开始时间、说明、checkpoint 和更新时间。同 owner 下的相同记录可重复登记，ID 不能改绑。 |
| `activities_for_role(owner, state=..., limit=..., after_id=...)` | 按角色所有者查询，可筛选状态；按 activity ID 排序，以原 ID 翻页，默认 50 条，上限 100 条。 |
| `transition_activity(id, owner=..., expected_revision=..., state=..., operation_id=..., checkpoint=..., observed_at=...)` | 保存进度和状态，使用 revision 比较更新；省略 checkpoint 保留原值，空字符串表示清空，省略时间使用宿主时钟。 |
| `add_artifact(artifact, owner=...)` / `artifact(id, owner=...)` | 登记与读取产物的原 Source/Asset 引用；绑定已有活动，保留原版本、scope 和角色所有者。图片必须携带 AssetRef，登记产物不会顺带完成活动。 |
| `artifacts_for_role(...)` / `artifacts_for_scope(...)` | 分页查询可信内部产物目录，保留每件原件的窗口归属。 |

角色所有者是 `RoleOwnerRef(installation_id, bot_id, persona_id)`，不随当前聊天窗口变化。同一角色可以查到自己在不同窗口留下的活动；不同安装、Bot 或角色各自隔离，两个 owner 可以使用相同 activity/artifact ID。

这些接口供可信框架内部使用。owner 目录不是面向当前聊天受众的授权读取接口；活动说明、checkpoint 和产物引用尚未自动注入提示词，也未直接暴露为聊天工具或管理 API。以后对外展示或分享必须经当前身份及原 Source/Asset 权限复核，不能用同角色跨窗口可查来代替受众许可。

## 状态、事务与重启

活动具有 `planned`、`active`、`paused`、`completed`、`cancelled` 状态。计划可开始或取消；进行中可保存进度、暂停、完成或取消；暂停后可保存进度、恢复、完成或取消。终态不重新激活。变更仅由显式调用提交，墙钟经过和宿主重启都不会自动增加进度、完成计划或生成停机期间的经历。

状态变更复用公共 `OperationRepository`，将活动新版本、原操作结果和 COMPLETED 回执提交在同一事务内。相同 operation ID 与参数重试返回第一次的结果，即使活动后来已继续推进，也不覆盖当前记录；更换参数、旧 revision 或外层事务失败均不能留下半条活动更新。时间不能早于该活动已记录的更新时间。

宿主停止后重开，共用装配可以读取原暂停进度并显式恢复；这一过程不启动模型或发送。已有普通对话链运行也不会顺带修改生活活动。本批验证覆盖同进程内关闭后重建宿主和数据库连接，以及两个数据库连接的过期写入冲突；没有宣称生活 worker 已具备跨进程任务恢复。

## V2 内部存储 v16

新增 `role_activities`、`role_artifacts`、`role_life_operations` 三张表。活动和产物以 owner key 与原 ID 为复合主键；产物通过复合外键关联活动，状态查询和原 scope 目录具有索引，操作结果关联公共 operations。

保留 v15 及更早版本的 schema 指纹，新增 v15→v16 原子升级；非空旧记录保留、失败回滚、未来表拒绝和 v16 指纹检查均有覆盖。这是 V2 自身格式升级，没有读取或迁移 V1 用户数据。staging 首次初始化同时改用当前 `REQUIRED_TABLES` 检查空库，已有角色活动的库会返回 `staging_bootstrap_store_in_use`，原记录不变且不调用原生模型或平台。

## 验证范围

使用 AstrBot 自带 Python，在临时 V2 数据根执行三组定向测试，独立总计 **146 项通过**，其中本批新增 **16 项**。历史运行及重复执行不累加。本批未重载在线插件或升级在线 profile。

| 测试组 | 数量 | 主要覆盖 |
| --- | --- | --- |
| role life、相关领域与统一宿主 | 60 | 暂停/恢复、原回执重试、两连接版本冲突、外层回滚、跨窗口 owner、产物原引用、宿主重建、普通会话兼容及隔离。 |
| 历史存储升级 | 50 | 模型、宿主、会话、配置、日程、对象权限及 scope 的历史非空库升级；保留 v15 历史指纹。 |
| AstrBot 宿主与 bootstrap | 36 | SDK 装配、加载/停机/路由注销及初始化；已有角色生活数据拒绝重初始化。 |

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_life tests.test_role_life_host tests.test_role_life_storage tests.test_proactive_sharing tests.test_multibot_scope tests.test_isolation tests.test_host_application tests.test_host_recovery tests.test_host_external_tools -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_model_failure_storage tests.test_host_storage tests.test_model_storage tests.test_conversation_storage tests.test_storage_migrations tests.test_configuration_storage tests.test_agenda_storage tests.test_object_access_storage tests.test_scope_storage -q
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_staging_host tests.test_astrbot_staging_bootstrap -q
```

## 下一框架切片

后续 [日记与梦境归档切片](CORE_ROLE_JOURNAL_SLICE.md)已完成日期、来源、版本与删除记录，并将内部 schema 推进至 v17；上文 v16 和 146 项是本活动切片完成时的证据。下一步接后台生成和生活推进，保存任务依据和实际进度。CORE-03 的关系/记忆修订、完整身体/睡眠状态、技能/目标、管理和工具入口仍按各自责任补齐。角色生活记录已持久化不等于完整连续生活已实现，也不等于 G5 或替换发行通过验收。
