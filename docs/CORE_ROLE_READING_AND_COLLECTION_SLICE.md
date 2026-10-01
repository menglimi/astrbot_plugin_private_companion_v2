# CORE-05 阅读完成回执与当日素材汇集

日期：2026-09-23。接续[素材分类与授权原文](CORE_JOURNAL_WRITING_REVIEW_20260923.md)，已将阅读完成登记、已读片段投影和当天候选素材汇集装配到统一宿主。数据仍使用独立 V2 库；没有真实阅读 worker、日程循环或线上模型调用。

后续[每日/睡眠触发与超额选材](CORE_JOURNAL_TRIGGER_AND_SELECTION_SLICE.md)已复用本切片汇集器接入统一宿主。下文“尚未接触发/自动选择”描述的是本切片完成时的边界；当前状态以该后续记录为准。

## 阅读完成登记

`application.role_reading.record_completion(...)` 是可信阅读执行端的登记合同。执行端必须提供原 SourceRef、读到的内容哈希、实际阅读字符范围、完成时间，以及原活动版本和操作 ID。该入口核对当前身份/角色、完整私聊 scope、独立的 `role.reading.record` 权限与来源受众，复核原文哈希及非空范围后，复用 `role_life` 的事务和操作回执完成活动。

`RoleActivity.reading` 中的 `RoleReadingReceipt` 保存完整原文长度、零起点且右侧不包含的 `[start_offset, end_offset)` 字符范围（以 Python 的 Unicode 字符索引计算）、内容哈希和完成时间，不复制正文。只有进行中或暂停活动可按既有生命周期完成，计划和取消活动不能直接被标记为读完；完成时间必须处于活动已开始、未晚于当前时间的范围内，不能倒退到已有进度之前。它表示可信执行端报告读过该范围，不证明理解，也不代表整本书或外部作品已经全部读完。

活动、阅读回执和原操作结果在同一事务提交。相同请求重试保留原版本和时间；更改范围、来源或时间时不能复用原操作 ID。重开只恢复原回执，不发起阅读，不根据停机时长补造经历。原 Source 撤回或过期后不能作为可用阅读材料继续投影。

`reading` 是活动 JSON 中的可选字段。缺少它的旧活动、旧操作结果和旧日记活动快照恢复为 `None`；没有阅读回执的旧状态变更继续使用原参数哈希。没有新增 SQL 表、schema 版本或迁移指纹，保留 CORE-03 的 v18 存储与关系记忆消费者。

## 阅读动作与已读片段

`application.journal_material_producer.for_day(...)` 将有回执的完成活动输出为 ACTION，明确阅读范围、实际完成日期和原 Source。即使活动没有文字描述也能保留这一完成事实。

`application.journal_reading_material_producer.for_day(task_context, journal_context, ...)` 在当前写作权限和 Source 受众下，从原文中截取回执对应的实际阅读片段；不会把片段前后的未读内容一起标为已读。长片段只预览前 8192 个字符并标明节选。原文长度和哈希须与回执一致，日期按完成时间及目标时区计算，所以昨天收存、今天读过的资料可以进入今天的材料。

阅读动作、已读片段和同源产物内容使用相同 origin，保留不同 material id、相同 SourceRef 及实际活动版本。写作和直接归档均拒绝丢失阅读原 Source 的活动依赖，防止只有活动快照时绕过来源撤回。提示词要求把读过某个片段、理解内容和读完整部作品分开表达，不增加正文关键词封禁。

## 当天汇集与明确选用

`application.journal_material_collector.for_day(task_context, journal_context, page_size=50)` 在一个 SQLite 读取快照内遍历活动、产物目录、分类原文、已读片段和授权入站对话五个入口。所有入口沿各自游标扫描到结束；过滤后空页的游标仍会继续。收集结果保留目标 scope/角色/日期、原任务上下文标识、收集时间及各入口页数；遇到权限或来源失败时不返回伪装成完整结果的部分材料。

`JournalDayMaterials.materials` 保存本次候选集，跨页新增记录在下一次收集时才能看见。完全相同的 material id 只保留一次，冲突内容或卡住的游标会报错。同源但不同材料仍保留原分类和 origin，不将它们当成多个独立事实。

`select()` 在候选不超过已有写作合同的 64 条容量时选用全部。候选超过容量时，`requires_selection=True`，调用方提供明确的 material id 元组交给 `select(ids)`；不会静默使用首页或前 64 条，也不会用关键词猜哪些更值得写。选用结果保留原来源/活动引用，可直接作为 `journal_writer.write(..., materials=selected.materials)` 的输入。生成前和提交前继续由既有写作链复核来源、版本和权限。

示例中的变量由可信宿主与阅读执行端提供：

```python
receipt = application.role_reading.record_completion(
    task_context, activity_id=activity_id, source=original_source,
    content_hash=read_content_hash, start_offset=read_start, end_offset=read_end,
    completed_at=read_completed_at, expected_revision=activity_revision,
    operation_id=reading_operation_id,
).unwrap()

candidates = application.journal_material_collector.for_day(task_context, journal_context)
# selected_ids 为本次明确选用的候选 ID；None 表示全部，超额时需明确提供。
selected = candidates.select(selected_ids)
result = await application.journal_writer.write(
    task_context, trigger_event, journal_context,
    role_instruction=original_persona_instruction,
    materials=selected.materials, request_id=writing_request_id,
)
```

收集只覆盖已登记到 V2 且属于该完整会话范围的材料，不能称为角色当天全部生活经历。当前仍遍历 owner 的分页库存，尚未评估大型历史库的扫描耗时。没有自动选用超额候选，没有接真实阅读执行器或每日/睡眠触发，也未将这些内部接口直接暴露为聊天工具或管理页面。

## 验证与目录

使用 AstrBot 自带 Python，169 项定向测试通过：阅读/汇集/活动 26 项，日记及相关来源、权限和宿主 106 项，真实 SDK 宿主/bootstrap 合约 37 项。新增 14 项覆盖完成回执重开、原请求重试与参数冲突、计划/取消不完成、错误范围/哈希/时间不落库、当前权限/范围/受众与撤回、实际已读片段、日期跨午夜、阅读源依赖、文本变更、宿主停机、过滤空页续读、65 条候选的完整收集与显式选用、并发写入下的一致快照，以及收集后进入共享写作链。

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_reading tests.test_role_journal_collection tests.test_role_life -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_journal tests.test_role_journal_materials tests.test_role_journal_writing tests.test_role_journal_host tests.test_role_journal_storage tests.test_role_life_host tests.test_role_life_storage tests.test_object_access tests.test_host_application tests.test_host_recovery tests.test_isolation -q
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_staging_host tests.test_astrbot_staging_bootstrap -q
```

阅读登记放在 `role_work/reading.py`，素材汇集和阅读投影分别位于 `role_work/journal/collection.py`、`reading_materials.py`。测试位于 `tests/test_role_reading.py`、`test_role_journal_collection.py`，根目录没有新增业务文件。测试仅使用临时 V2 库和合成文本，未访问 V1 用户数据、调用真实模型或重载在线插件。下一步是明确授权的每日/睡眠触发和超额候选的选用策略，再接真实阅读执行端及文风评估。
