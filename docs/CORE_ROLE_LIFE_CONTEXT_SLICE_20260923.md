# CORE-05：连续生活进入普通私聊

日期：2026-09-23。接续[日记、梦境、阅读与睡眠的完整使用链](CORE_ROLE_LIFE_END_TO_END_20260923.md)，将当前角色的活动状态、实际阅读回执、日记和梦境接入普通私聊回复提示。该切片只读取 V2 已记录的资料，不触发写作、阅读、睡眠或其他后台任务。

## 读取边界

`RoleLifeContextReader` 只读取当前经验证的参与者、角色 owner、完整私聊 scope 和单一受众。生活资料有单独的 `role.life.read` 授权；生活设置启停会同步发放或撤销。每个来源在读取时重新核对完整 scope、当前受众、有效期与内容哈希。日记同时检查角色归属、当地日期及递归来源/日记依赖。

可投影的活动只描述账本实际记录的状态、说明、检查点和时间。计划、暂停、取消和完成保持原语义；预计唤醒时间不会生成已醒或睡眠经历。阅读只标记可信完成回执给出的原文字符区间，计划阅读不会变成已读。日记和梦境作为角色主观记录提供，衍生摘要固定其原版本，不能作为用户现实事实或 observed 声明的证据。

## 封存与复核

`ConversationMessages.seal` 将有界原件引用及 revision 固定在既有消息批次中，不把日记正文复制进批次。准备提示时按这些引用重新读取选中的原件；活动、正文或被选中的衍生材料发生变化，或授权/来源失效时，本轮不会静默换成新版本。生成后的草稿提交及每段发送继续经过同一复核链；已确认发送的回执保留，后续未发送内容会被阻止，历史正文按既有来源依赖治理隐藏。

每轮最多检查 32 条当前范围活动和 32 个日记日，最多选入 6 项活动及 4 项日记/梦境，总提示材料不超过 12,000 个字符。原文和可用衍生材料作为完整候选择一，不截断正文；超出数量或预算时记录 partial 状态。没有合适资料时普通回复继续运行；旧批次没有生活快照时保持原内容，不补入新生活资料。

提示约束强调自然参考、相关时才提及，不逐条播报台账；材料中的文本不是指令。收存或计划阅读不代表读过，梦境不代表共同现实经历，墙钟经过不会补造生活。原角色提示保持原文，系统不会因生活材料自动拒绝回复。

## 验证

使用 AstrBot 自带 Python 与临时 V2 数据根，相关消费者、对话/统一宿主、staging 和隔离回归共 **123 项测试通过**。覆盖权限启停与撤销、来源撤回/过期/哈希冲突、跨范围/角色/受众隔离、日记修订/删除、衍生材料固定、预算与选择、旧批次兼容、生成中失效、逐段投递及重启恢复。宿主和平台端口使用替身；未调用真实模型或发送平台消息，也未读取 V1 数据。

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_life_context tests.test_role_life_context_host tests.test_conversation_messages tests.test_host_application tests.test_host_recovery tests.test_astrbot_staging_host tests.test_astrbot_staging_bootstrap tests.test_isolation -q
```

新增消费边界分别位于 `role_work/life/context.py` 和 `conversation/life_context.py`；统一装配与消息封存沿用现有 `host/application.py`、`conversation/messages.py`。新增测试归入 `tests/test_role_life_context*.py`，没有根级业务文件、数据库表或 schema 迁移。

## 后续范围

本批没有实现成长轨迹、技能或长期目标、开放事项与完整 Calendar，也没有扩展到跨会话生活共享。它把已持久化的首批连续生活材料用于同一完整私聊中的普通回复；更多领域资料应按各自来源、受众和操作回执接入，不能从墙钟推断未记录的经历。
