# CORE-05：日记与梦境归档、修订和删除

日期：2026-09-23。接续[角色活动持久化](CORE_ROLE_LIFE_PERSISTENCE_SLICE.md)，新增 `RoleJournalService`，通过统一宿主的 `application.role_journal` 使用已有 V2 数据库和时钟。本文保留归档基础切片的范围与测试证据；随后完成的素材语义、写作提示词和受管理生成见[历史审查与写作实现](CORE_JOURNAL_WRITING_REVIEW_20260923.md)。定时调度和聊天/页面入口仍待接入。

## 已落地的行为

- 日记与梦境按 `installation + bot + persona + kind + local_date` 分别归档，每类每天一份当前记录；日期使用 ISO 格式，时区显式保存。`JournalKey.at()` 将带时区的时间换算为角色当地日期，记录不会随重启或当前会话换窗口改绑日期、原 scope 或时区。
- 正文保留换行和段落；日记文体是自由字段，没有日期取模轮换、关键词删改、固定故事节点或最低篇幅规则。梦境明确标记完整梦、碎片或余韵，允许正文为空而只保留醒后感觉。
- 每次写入保留来源引用的原 scope 和版本、实际活动的版本快照，以及所采用日记/梦境的准确版本。活动处于计划、进行或暂停状态会原样保存；后续活动自然推进不改变过去的快照，也不把计划自动改为已发生。
- 正文保存和摘要/梦境碎片/连续性提取分开提交。衍生材料必须绑定当前正文版本；人工改动后，迟到正文或衍生结果会遇到版本冲突，不能覆盖新记录。
- 正文改动清除该日期的当前衍生缓存。采用它的后续梦境或连续性记录在读取时检查完整依赖；旧版本变化、日期删除、原 Source 撤回或过期都会使相关正文和衍生材料停止被读取。重新生成必须明确采用新的有效版本。
- 删除可以作用于还没有正文的日期，形成删除标记；后来的自动写入无法补回。删除已有记录会清空该日正文和当前衍生缓存，保留日期及不含正文的操作回执。恢复是独立的 `restore` 操作，必须提供替代正文和当前删除版本。

梦境和日记继续属于角色主观写作。该服务不会将其发布成事实 Source，不会修改关系账户、用户记忆或活动完成状态。梦里出现某个人的行为，也不会通过保存动作成为该用户的现实经历。

## 接口与文件归属

实现放入 `companion_v2/role_work/journal/`：`models.py` 定义归档、输入和衍生材料合同，`codec.py` 恢复原始引用，`service.py` 提供事务、依赖检查和删除语义，`__init__.py` 导出内部接口。根目录没有增加 Python 文件。

| 接口 | 用途 |
| --- | --- |
| `head(key)` | 读取无正文的版本和 active/deleted/absent 状态。未保存日期的 revision 为 0。 |
| `list_days(owner, kind=..., after_date=..., limit=..., include_deleted=...)` | 按日期分页读取归档元数据，默认隐藏删除日期；元数据存在不等于其正文依赖仍有效。 |
| `save(draft, expected_revision=..., operation_id=...)` | 创建或修订当前正文；相同操作重试返回原回执，更换参数或过期版本不能写入。 |
| `get(key, observed_at=...)` | 检查当前正文、全部日记依赖和原 Source 有效性后读取。 |
| `save_derivatives(material, expected_revision=..., operation_id=...)` | 单独提交摘要、梦境碎片和连续性材料，校验父正文版本及衍生材料自身版本。 |
| `derivatives(key, observed_at=...)` | 检查父正文和全部依赖，再返回当前衍生材料；尚未提取时返回空。 |
| `delete(context, expected_revision=..., operation_id=...)` | 清除该日正文/当前衍生材料并保存删除标记，包括尚未写入正文的日期。 |
| `restore(draft, expected_revision=..., operation_id=...)` | 显式重开删除日期，写入新的替代内容；不会取回旧缓存。 |

所有修改与公共 `OperationRepository` 的接受/完成回执在同一 V2 事务内提交。原回执只保存日期、版本、动作和状态，没有旧正文；重复原操作只能查到原处理结果，当前内容仍需经过 `get`/`derivatives`。外层事务失败时，正文、材料和回执一起回滚。

这些是可信 owner 内部接口，不直接向模型或当前聊天受众开放。跨窗口拥有同一角色，不代表窗口里的每个参与者都有权读取整篇日记；后续工具、管理页和分享仍需复核当前身份及各来源受众。`SourceRepository.validate_reference()` 只提供当前来源有效性检查，不提供受众读取授权。

## 存储 v17 与验证

v17 新增 `role_journals`、`role_journal_derivatives`、`role_journal_operations`，保留 v16 及更早的迁移指纹。角色活动、原模型账本和其他已有领域数据在非空升级中保持；升级失败回滚，较旧库夹带未来表或篡改迁移指纹会被拒绝。staging 已有的 `REQUIRED_TABLES` 空库检查自动覆盖这批新表。

使用 AstrBot 自带 Python 和临时 V2 数据根，三组定向测试独立合计 **166 项通过**，其中新增 **22 项**。重复运行不累加：

| 测试组 | 数量 | 证据 |
| --- | --- | --- |
| 日记/梦境、角色生活及统一宿主 | 67 | 当地日期、段落、余韵、活动快照、双连接修订冲突、衍生版本、预先删除、显式恢复、跨级依赖失效、来源撤回、角色隔离、事务回滚与宿主重开。 |
| 历史存储升级 | 63 | 旧非空数据库至 v17 的模型、消息、工具、任务、配置、日程、权限与人格数据保持及失败回滚。 |
| AstrBot 宿主/bootstrap | 36 | SDK 装配、加载/停机、路由注销、初始化与已有会话兼容。 |

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_journal tests.test_role_journal_host tests.test_role_journal_storage tests.test_role_life tests.test_role_life_host tests.test_role_life_storage tests.test_isolation tests.test_host_application tests.test_host_recovery tests.test_host_external_tools -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_model_failure_storage tests.test_host_storage tests.test_model_storage tests.test_conversation_storage tests.test_storage_migrations tests.test_configuration_storage tests.test_agenda_storage tests.test_object_access_storage tests.test_scope_storage tests.test_external_tool_storage tests.test_execution_storage tests.test_diagnostic_storage tests.test_persona_storage -q
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_staging_host tests.test_astrbot_staging_bootstrap -q
```

自动测试使用合成正文、来源和原生替身，没有读取 V1 用户数据、调用真实模型或发送 QQ 消息。本批没有重载在线插件或升级在线 profile；宿主重启证据来自临时库关闭后重建。

## 下一切片

后台写作与衍生提取已在[后续切片](CORE_JOURNAL_WRITING_REVIEW_20260923.md)接入现有任务/模型公共链，保留原人格、素材语义和版本复核。当前有角色活动台账、文本产物及授权入站对话三类按日分页素材；产物的显式创作/阅读标签和经过授权、哈希复核的正文入口已接入。写作动作与作品正文分条、同源；阅读资料收存不等于已经阅读或读完，旧无标签记录仍按通用产物处理。对话按对方表达保留来源，撤回会传播到引用它的日记。[阅读回执与当日汇集](CORE_ROLE_READING_AND_COLLECTION_SLICE.md)已补齐原文片段/哈希/完成时间、来源依赖、同一快照内的全页汇集和超额明确选用。接下来接授权明确的睡眠/每日触发、超额选用策略和真实阅读执行端，再做真实文风评估；图片/音频产物、资料纠正的外部事件订阅、聊天/页面入口和全量历史正文版本浏览仍待完成。
