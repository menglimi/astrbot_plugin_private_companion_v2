# CORE-03：角色关系记忆首批持久切片

日期：2026-09-23。沿[本体实施路线](V1_CORE_FEATURE_PREREQUISITES.md)推进角色关系与记忆修订的基础记录。本切片只实现关系背景与情绪事件，不接日记/梦境工作流，也不修改另一窗口正在推进的内容。

## 记录责任

`companion_v2/relationships/` 由关系记忆领域负责。

- 关系键由稳定角色 owner 与已解析的人类 Subject 组成。Bot、账号、会话、窗口和当前绑定版本不会取代这对关系主体，因此同一角色在不同私聊中能查找自己的同一段关系记录。不同角色或不同人分别隔离。
- 记录分为关系背景 `context` 与情绪事件 `emotion_episode`。后者明确描述角色或人类哪一方的情绪。内容是角色基于材料的主观解释，不宣称为客观心理诊断。
- 每条记录保留精确私聊 scope、一个或多个不可变 SourceRef、创建/观察/更新时间、明确状态及单调 revision。源正文不复制到本领域。
- 生命周期为 proposed → reviewed → adopted → retracted；提出后可直接撤回，审阅或采用后的记录可撤回；更正会创建下一 revision 并重新回到 proposed。历史版本保留用于复核。过期、撤回或受众变更的 source 不会因其仍在记忆中而重新获得读取资格。
- 按角色与人类成对分页，列表可按状态/记录类型过滤；只有采用视图返回 adopted 项。此视图仍是可信内部索引，不构成聊天受众授权。

`PersistentRelationshipMemoryLedger` 是存储原语，不会自行解析用户、写入记忆、调用模型或发送内容。`RelationshipMemoryService` 是当前私聊服务入口：重验已认证人类、私聊路由参与者、当前角色绑定和每项关系记忆动作权限；读取与审阅前重新检查每个 SourceRef 的当前状态、有效期和受众，但不返回来源正文。审阅、采用、撤回分别保留实际执行人的稳定人类 Subject；采用还必须已有归属明确的审阅记录。服务已由宿主装配，后续[普通对话消费者](CORE_RELATIONSHIP_CONTEXT_SLICE.md)将当前私聊已采用记录接入提示材料，并在生成与投递前复核；用户管理入口仍待接入。

本领域不持有用户客观事实/偏好、角色自我活动、表达学习规则或日记正文。情绪是有来源的情境记录，不从一次心情推断稳定人格，也不设置硬阈值、分数或自动阶段升级。模型/提示词仍负责理解意图和自然表达；身份、来源、版本和审阅状态由代码校验。

## 持久格式与验证

V2 内部 schema 从 v17 原子升级至 v18，增加 `relationship_memories`、`relationship_memory_revisions` 和 `relationship_memory_operations`。活动和已有 v17 日记数据原样保留；历史迁移 ID/指纹不变。新表有唯一 owner/subject 键、修订历史和操作外键。局部迁移失败时，表、版本及迁移回执一起回滚。

使用 AstrBot 自带 Python 执行本领域/迁移、宿主组合、便签/配置/对象权限/范围存储、诊断、角色活动以及日记非存储功能回归，共 **132 项通过**；关系记录单测和迁移专测共 10 项，已计入该总数。

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_relationship_memory tests.test_relationship_memory_storage tests.test_host_application tests.test_host_recovery tests.test_role_life tests.test_role_life_storage tests.test_storage_migrations tests.test_diagnostics tests.test_agenda_storage tests.test_configuration_storage tests.test_object_access_storage tests.test_scope_storage tests.test_role_journal tests.test_role_journal_materials tests.test_role_journal_writing tests.test_role_journal_host -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m compileall -q companion_v2
```

测试只使用临时 V2 库、合成角色/来源和本地执行替身；未读 V1 数据、未调用模型或平台。日记 schema 专项的其他窗口文件中还有一条旧断言把 v16→v17 的目标与当前 `SCHEMA_VERSION` 常量比较；现常量已是 v18，需改用固定 `SCHEMA_VERSION_V17`，本轮未编辑该文件。此存储批次当时没有建立 AstrBot 聊天工具、提示词消费者或管理 API，也未验证实际聊天表达效果。提示词消费的后续实施与独立验证见[关系记忆接入普通对话](CORE_RELATIONSHIP_CONTEXT_SLICE.md)。

## 下一步

继续 CORE-03：补齐面向用户的可信提议、审阅、采用、更正与撤回交互，明确它与用户客观记忆、偏好及表达学习规则的边界。普通对话已消费当前完整私聊中的已采用记录，并固定、复核原版本；公开审核 API、跨会话投影、相关性召回与其他衍生摘要的失效传播仍待接入。

后续可信管理切片已增加 `relationships/management.py` 与 `astrbot_host/management_identity.py`、`relationships_api.py`：SDK Dashboard 登录身份独立于关系对象，CORE 管理员的审阅、采用、更正、撤回均留真实主体与原版本。列表按完整 scope 分页，来源失效不返回正文但可撤回；更正人字段兼容旧 JSON，原本人修订的幂等哈希保持兼容。核心与宿主的相关 69 项验证已完成，后续 v19 宿主回归继续覆盖身份与路由生命周期。页面工作按当前要求暂停，本体运行框架继续按后台职责推进。
