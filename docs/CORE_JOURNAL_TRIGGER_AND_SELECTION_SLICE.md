# CORE-05 日记触发、睡眠完成入口与素材选用

日期：2026-09-23。接续[阅读回执与当天汇集](CORE_ROLE_READING_AND_COLLECTION_SLICE.md)，本切片把每日/睡眠事件、当天候选、超额选用及原角色正文写作接成闭环。由统一宿主装配，定时注册默认为空；没有启用在线任务、读取 V1 数据或发送 QQ 消息。

## 入口与生命周期

`application.journal_triggers.daily(...)` 为明确日期启动日记；未来日期拒绝，明确指定的历史日期只执行本次调用，不扫描补写旧日。触发前检查当前运行代、身份/角色、完整私聊 scope、`role.journal.write` 权限，以及触发 Source 的读取 grant、受众和原文哈希。原人格提示继续传入原写作服务。

`application.journal_schedule.register_daily(...)` 提供可信宿主的每日注册。宿主已有的 `_drive` 取对话与日记的最近唤醒时间，日记的候选选择和正文继续使用共享后台名额、模型路由及预算，没有新增轮询线程、provider 或平台发送链。注册使用 IANA 时区与当地时刻，默认 23:50；重复注册相同 ID 保留原截止时间，修改参数需先撤除原注册。夏令时重叠只选第一次，缺失时刻按该时区偏移转换到实际存在的时间。

注册是本次宿主的实时绑定，保存在内存；重启必须由宿主取得当前授权和人格后重新注册。注册时若当天时刻已过，从次日开始。运行期间若唤醒延迟跨过数日，只考虑当天到点事件，不补发停机期间的日期。`remove(id)` 撤除后续日期并取消该注册的进行中调用。

`application.journal_triggers.sleep_completed(...)` 是可信生活执行端的完成报告入口，必须显式提供开始、结束时间及原事件来源；开始早于结束，结束不晚于事件接收时间与当前时间。梦境按睡眠结束的当地日期归档，输入带有“报告了睡眠完成”的 ACTION 及原 Source。它不解析聊天关键词、不凭墙钟认定入睡、不推进活动状态，也不把报告当成已经记住完整梦境。此入口尚未连接真实生活执行器；普通入站消息不会自动调用它。

宿主停止或驱动故障时，调度 wrapper、触发调用和写作 worker 一起取消并纳入句柄清点。尚未退出的调用阻止自有数据库提前关闭；后台写作不占用前台对话名额。

## 同日去重与重试

素材汇集前先使用现有 `operations` 账本登记 `role.journal.trigger`。首次操作身份由角色 owner、日记/梦境种类和日期确定，同一天多个 tick、多个注册或重复睡眠报告共用一次首次尝试。回执绑定原任务上下文，角色或账号绑定版本变化时不能套用旧回执。原 scope、权限上下文、时区和人格摘要保留在参数哈希；另一个私聊窗口不能接管同日操作或读取原回执。已有正文或删除墓碑在汇集前直接跳过；模型返回后仍使用原版本提交，不能覆盖迟到的人工修订。

`JournalTriggerReceipt` 返回操作 ID、状态及已建立的选择/写作任务 ID，不携带私人正文：

| 状态 | 含义 |
| --- | --- |
| `written` | 原写作任务成功；重复调用只返回该任务元数据。当前正文仍须按归档服务检查来源与版本。 |
| `failed` | 本次已结束但未写成。可查共享任务原因；创建子任务前失败的重开回执只有 `journal_preparation_failed`，不持久化异常正文。 |
| `accepted` | 原调用已被接纳，可能仍在运行或曾在持久化接纳后中断；重复调用不重新汇集。 |
| `unknown` | 取消、未停止的尝试或模型处理结果未知；不启动替代生成。 |
| `active` / `deleted` | 日期已有正文/删除墓碑；本次未建立触发操作。 |

已知失败只有在调用方显式提供 `retry_of=原操作ID` 与 `retry_id=新请求ID` 时才启动新尝试。每个原操作只有一个直接重试分支，相同重试请求仍幂等；修改重试 ID 不能凭同一原操作制造额外分支。重试重新汇集当前材料，仍须目标不存在、授权有效。已成功、仍在运行、未结清或模型处理未知的原操作不能重试。中断后不恢复内存候选或选择结果，也不把过期调用视为已知失败后自行再生成。

`journal_triggers.inspect(context, target, operation_id)` 只读查询已授权范围内的触发状态及子任务 ID，不返回正文、不重新调用模型。

## 超额候选选择

64 条以内直接使用已有全部选用合同。超过 64 条且调用方未指定 `material_ids` 时，先执行独立后台任务 `role.journal.select`；`writing_profiles(...)` 现在同时注册选择、日记、梦境及衍生提取四种 profile。原生 AstrBot wire 已接受独立的 `journal_selection` JSON 格式，没有聊天 claims 或工具目录。

选择提示提供本次完整候选的 ID、语义类别、日期、origin、出处和原文本；提示要求按变化与感受取舍，关注同源回声，同时考虑列表末尾，不按固定关键词、编号或日期取模。模型只返回最多 64 个不重复的原候选 ID；程序校验结构、数量和出处，不筛文学用词，也不让模型改写或重新分类原材料。选择后按 ID 取回原对象、原 SourceRef 和活动版本，再交给 `write_collected(...)`；选择任务与正文任务顺序使用同一后台名额。

选择和正文运行期间都复核已采用来源的当前读取权限、受众、原文哈希及活动版本。非法 ID、模型失败、撤权、人工编辑或删除会阻止后续正文；没有选择兜底、前 64 条截取或第二次隐式选择。调用方明确指定 `material_ids` 可直接使用原候选并跳过选择模型。

选择结果只在本次被等待的调用中可用。成功正文保存所选原材料，任务保存结果摘要与调用账本；直接重放选择请求只返回任务元数据，不能恢复丢失的选择输入。此实现仍是一次完整候选请求，没有分层压缩或大库存批量选择；大型库存的上下文容量及延迟尚未实测，超出模型/预算能力时保留失败，不静默丢弃后页。

## 可信宿主用法

以下上下文、原人格和来源事件由可信宿主提供，不能直接用任意聊天字符串替代完成报告：

```python
application.journal_schedule.register_daily(
    "private-diary", task_context, authorized_event,
    role_instruction=original_persona_instruction,
    timezone="Asia/Shanghai", local_time="23:50",
).unwrap()

receipt = (await application.journal_triggers.daily(
    task_context, authorized_event, local_date=local_date,
    timezone="Asia/Shanghai", role_instruction=original_persona_instruction,
)).unwrap()

dream_receipt = (await application.journal_triggers.sleep_completed(
    task_context, sleep_event, started_at=sleep_started_at,
    completed_at=sleep_completed_at, timezone="Asia/Shanghai",
    role_instruction=original_persona_instruction,
)).unwrap()

# 仅在查明原调用已知失败后，由调用方明确发起。
retried = await application.journal_triggers.daily(
    task_context, authorized_event, local_date=local_date,
    timezone="Asia/Shanghai", role_instruction=original_persona_instruction,
    retry_of=receipt.operation_id, retry_id=explicit_retry_request_id,
)
```

## 验证与文件组织

AstrBot 自带 Python 下，26 项新增触发/调度测试通过；模型 wire 13 项、日记/来源/活动/宿主相关 99 项，以及真实 SDK 宿主/bootstrap 与前台合同 41 项，共 179 个不同测试 ID 获得通过证据。日记迁移组首次运行时遇到共享工作区升级 v19 后的历史夹具不同步；夹具更新后，单独复验该组 4 项全部通过，重复运行不累计为新测试数。

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_journal_triggers tests.test_role_journal_scheduling tests.test_astrbot_model_wire -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_journal tests.test_role_journal_materials tests.test_role_journal_collection tests.test_role_journal_writing tests.test_role_journal_host tests.test_role_journal_storage tests.test_role_reading tests.test_host_application tests.test_host_recovery tests.test_isolation -q
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_staging_host tests.test_astrbot_staging_bootstrap tests.test_foreground_conversation -q
```

覆盖同日并发与重复 tick、跨私聊隔离、已存在/删除日期、65 条候选末项被选用、非法 ID、显式选用、选择回放仅返回元数据、已知失败显式重试、未知结果禁止重试、重启不重放、睡眠完成日期/时间、选择和正文期间撤权、人工编辑冲突、共享后台容量、前台可用、真实短定时唤醒、夏令时、跨日延迟、注册撤除及停机句柄清点。

新文件位于 `role_work/journal/selection.py`、`triggers.py`、`scheduling.py`；原写作服务与公共宿主只增加对应装配和生命周期，测试在 `tests/test_role_journal_triggers.py`、`test_role_journal_scheduling.py`。根级 Python 仍只有 `main.py`。没有新增 SQL 表或迁移，沿用共享工作区的 schema；当前 v19 是后台提醒/投递切片引入，保留其装配及关系记忆消费者。

下一步是把这些可信入口连接到持久的宿主日程配置、真实阅读/睡眠执行端及管理入口，再做授权的真实模型文风与重复率评估。本轮仅验证临时 V2 库和模型替身，不能据此声称在线定时生成已启用或文学质量已验收。
