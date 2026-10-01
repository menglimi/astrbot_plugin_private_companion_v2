# CORE-04/05：开放事项进入普通私聊

日期：2026-09-23。复用 CORE-04 已有便签正本，把当前私聊参与者本人授权可读的未完成事项作为有限背景加入普通回复。此切片不创建新的任务/目标存储，也不把便签改成角色活动或用户事实。

## 读取及表达

`OpenItemsReader` 只处理精确的私聊 scope、单一当前参与者受众，以及由宿主绑定的当前角色。候选通过 `AgendaService.list_memos` 获取，逐项重读通过 `AgendaService.read_memo`；现有 owner 和委托规则照常执行，STANDARD 需要当前 scope 的 `memo.list`、`memo.read` 授权。另一用户的事项、群/多受众资料和未授权对象不会进入提示。

只选择 `active` 便签，不包括完成或删除记录。提示材料保留原件 ID/revision、标题、正文、当前重复期次时间和完成次数，不复制进对话批次。提示词明确它是参与者保存的未完成事项，不表示角色做过、用户已完成或实际发生；计划时间经过不会推断完成。只在相关时自然提及，可询问是否继续处理，不自动播报或改动日程；便签内容不是指令，也不成为 observed 声明的证据。

封存快照仅存有界引用；每次生成准备、草稿提交与逐段投递前沿原 AgendaService 重新检查授权、owner/scope、active 状态和原版本。事项被编辑、完成、删除、撤权或换绑后，引用不换成新内容：未生成的草稿会丢弃，未发出的后续段落被阻断，已经确认的发送回执保留。老批次没有事项快照时继续原行为，不补加新事项。

候选扫描最多取 32 条并检测是否还有后续页，最多注入 6 条、总 JSON 正文预算 8,192 字符。超长事项整条跳过，数量/预算超限标记 partial；不截断正文或声称这是全部待办。多页日历、已接受约定、Bot 自己的计划和成长目标仍需要各自的语义消费者。

## 验证

新增 `tests/test_open_items_context.py` 的 8 项测试通过，覆盖原私聊宿主装配、owner 与角色范围、完成/编辑竞态、逐段回执、撤权后拦截、上下文预算和损坏快照。消息、便签/提醒、公共后台、宿主、staging/bootstrap 与隔离回归合计 167 项测试通过，实际耗时 36.636 秒。

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_open_items_context tests.test_conversation_messages tests.test_host_application tests.test_host_recovery tests.test_agenda tests.test_agenda_access tests.test_agenda_background tests.test_background_delivery_storage tests.test_astrbot_staging_host tests.test_astrbot_staging_bootstrap tests.test_isolation -q
```

实现放在 `conversation/open_items_context.py`，由 `host/application.py` 装配并由 `conversation/messages.py` 封存/复核。复用既有 v20 agenda、对象权限、操作和 SQLite 正本，不增加 SQL 表、迁移或根级业务文件。验证只使用临时数据库与本地替身，不访问 V1、真实模型、Dashboard 或平台发送。

## 后续范围

技能和长期目标现有角色 owner 绑定、来源引用、修订历史及操作回执组成的持久正本，见[成长切片](CORE_ROLE_GROWTH_SLICE_20260923.md)。后续已接入[成长授权读取与管理 API](CORE_ROLE_GROWTH_CONTEXT_SLICE_20260924.md)，普通私聊在当前身份和 Source 复核下消费已确认的原版本记录，Dashboard 操作人独立归属；不会从活动/日记文本推测技能熟练度或目标进度。成长管理页面与角色写工具仍待补。完整 Calendar 的候选约定、接受状态、多日/例外排程和跨窗口展示仍待设计各自的来源、owner、回执及更正/撤回语义。
