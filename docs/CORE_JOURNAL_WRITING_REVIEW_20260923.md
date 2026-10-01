# 历史日记、梦境审查与 V2 写作落地

日期：2026-09-23。根据用户“检查过往梦境与日记，看看有什么问题并改进”的要求，本次仅为审查只读访问旧插件记录。改进落在独立 V2 的 `role_work/journal/`，没有改写、导入历史正文，也没有将历史正文复制到测试夹具或本文。

后续[每日/睡眠触发与素材选用](CORE_JOURNAL_TRIGGER_AND_SELECTION_SLICE.md)已把当天汇集和写作任务接通，新增 `role.journal.select` profile；本文的三类任务及待接调度描述保留为当时的切片边界。

## 审查范围与发现

检查了当前存储中的 14 篇日记（2026-09-08 至 09-21）、20 条梦境碎片，以及 4 个日期的梦境：当前 09-22 一份、备份快照中的 06-28、07-05、08-27 各一份。这不是完整的逐日梦境史；旧实现只保留单一当前完整梦境。

| 问题 | 证据与判断 | V2 对应改动 |
| --- | --- | --- |
| 兜底冒充正常日记 | 8/14 篇（约 57%）套用同一条“确定记录＋缺少细节”的兜底结构，尽管各自证据列表仍有 3～8 项。8 篇中 6 篇有非空但不能按 JSON 解析的原始结果；具体触发路径未确定，不能归因于某个模型或关键词。 | 生成、格式校验或提交失败只留任务结果，不创建兜底正文，不自动再次调用模型。 |
| 作品内容升格为亲历 | 多篇日记把实际小说续写中的人物动作、对话与消息间隔写成自己的现场经历。发布过一段生活文字也被当作正文事件发生的证据。旧证据收集器将动作与内容一起标为“已确认”。 | 材料区分真实动作、创作、发布内容、阅读、计划和感想；动作与内容分条、共用来源线索，不通过文字生成新的事实记录。 |
| 同源内容反复回流 | 创作段落进入日记、碎片和梦，纸面痕迹等少数意象反复出现；旧碎片只标记来自日记，不能识别其更早的作品来源。 | 保存 material id、语义类别、origin、日期及原 Source/活动引用；碎片保留 material id；近期上下文读有版本的原正文，保留上游日记关系，不把多个摘要当成独立记忆。 |
| 梦的视角及余韵边界不稳 | 较早梦多用第一人称，最新梦无说明切换第三人称；余韵添加醒后的新动作，缺少独立活动依据。 | 提示词保持原人格、第一人称，改变视角需自然交代；余韵侧重感觉和联想，新动作需要真实材料。 |
| 强制完整梦和机械文体 | 旧提示要求完整梦、至少三个节点、规定篇幅，并拒绝记不清；日记文体按日期等信息取模。 | 文体随内容选择，梦可完整、片段或仅余韵；不要求固定节点、最低字数、固定成长结尾或意象轮换。 |

旧实现另有“系统、模型”等关键词检查，存在误伤正常科技阅读的可能。本次样本不足以证明它直接导致了那 8 篇兜底，因此没有把可能性写成已确认原因。V2 的内容表达通过提示词引导，程序只验证输出结构、出处、版本和执行权限。

## 已实现的写作闭环

`application.journal_writer.write(...)` 与 `derive(...)` 使用同一任务监督器、后台名额、模型网关、任务配置和预算账本。宿主停机时同时停止写作 worker 与外层调用，未退出的句柄阻止数据库提前关闭。没有创建第二套 provider 或定时循环。

- 三类独立后台任务：`role.journal.diary`、`role.journal.dream`、`role.journal.derive`。角色提示原样保留；写作任务有自己的结构化输出合同，不套聊天回复的 text/claims 格式，也不提供工具目录。
- 先提交正文；衍生材料由另一次显式调用生成。摘要或碎片失败不覆盖已存正文，也不清掉已存的旧衍生结果。
- `JournalMaterial` 的分类由可信素材生产者提供，模型不能自行把虚构内容改标为事实。创作动作与作品段落应分开提供；Source 存在并不代表 Source 里的每句话都是现实事件。
- 默认读取至目标日期、且与本次目标拥有完全相同会话 scope 的最近有效日记/梦境，最多 8 份，用于承接与避免重复。稳定角色 owner 跨私聊窗口共享，但私人正文不会因此串窗；显式 `recent` 中跨 scope 的引用会在模型调用前拒绝。历史正文仍标为主观材料；不会递归把全部历史正文塞入提示，也不额外叠加摘要和碎片。显式传入 `recent` 可固定本次参考版本。
- 生成前、调用期间及提交前复核原来源、人格与权限；保存时使用原目标版本。人工编辑、删除墓碑、来源撤回、父正文变更均能阻止迟到结果提交。
- 相同请求只返回原任务元数据，失败、未知或完成后的请求均不会自动重新生成。调用准备材料只在本次被等待的调用期间保留；任务/模型结果持久化。重启不恢复未完成的写作输入，也不自动重放。后台名额不足时，本次任务取消并记录 `owner_unavailable`，后续调度者可以明确发起新请求。
- 成功正文保存原素材语义及引用；衍生碎片的 `fragment_origins` 指向父正文内 material id。删除仍清掉当前正文及衍生材料；回执不携带旧正文。主观内容不发布为事实 Source，不修改用户记忆或活动完成状态。

## 入口与兼容

宿主内部使用方式（变量由可信宿主提供，示例不含真实用户材料）：

```python
result = await application.journal_writer.write(
    task_context, trigger_event, journal_context,
    role_instruction=original_persona_instruction,
    materials=classified_materials,
    expected_revision=0,
    request_id="stable-writing-request",
)
# 检查 result 中的任务确实 succeeded 后，按需单独提取。
entry = application.role_journal.get(journal_context.key)
derived = await application.journal_writer.derive(
    task_context, trigger_event, entry.reference,
    role_instruction=original_persona_instruction,
    expected_revision=0,
    request_id="stable-extraction-request",
)
```

普通装配需把 `writing_profiles(provider_id, max_output_tokens=...)` 与对话 profile 一起交给共享字段注册表和模型路由。AstrBot staging 已装配这三类 profile；`role.journal.write` 是独立任务动作，STANDARD 参与者必须已有该范围的精确 grant。默认 staging 初始化不增加这一 grant；合成集成测试通过显式 capabilities 配置验证写作及撤权。

这是可信宿主入口，不是聊天工具、Dashboard 页面或任意受众读取 API。当前有显式分页的角色活动、文本产物和授权对话素材；带可信标签的创作/阅读原文也已接入独立授权入口。后续[阅读回执与汇集切片](CORE_ROLE_READING_AND_COLLECTION_SLICE.md)已补齐实际阅读报告、同一快照内的当天全页汇集及明确选用。真实阅读执行器、超额自动选用、图片/音频产物、睡眠触发、每日生成调度和对外分享仍需下一阶段接入。此次未启用线上生成，也未重载现有插件。

### 角色活动台账素材适配器

`application.journal_material_producer.for_day(context, limit=50, after_id=None)` 已接入统一宿主。它分页扫描同一角色 owner 的活动目录，再只保留与目标完整会话 scope 相同、按目标时区落在目标日期的记录；材料带有活动原版本引用。`PLANNED` 与 `CANCELLED` 明确分类为 PLAN，其他生命周期状态分类为 ACTION，并在文本中保留当前状态；没有描述和检查点的活动不会被提升成日记事实。它不读取对话正文，也不会把计划改写成已发生经历。

`JournalMaterialPage.activity_refs` 提供本页对应的唯一活动引用，可与本页材料一起传入 `JournalDraft`。页大小最多 64，以符合写作输入合同；`next_cursor` 沿活动 ID 顺序继续扫描。过滤后即使本页为空，只要 `next_cursor` 非空就还需继续。该入口只覆盖可信活动台账，不能代表当天全部经历；对话输入由独立的授权对话适配器接入，带显式标签的产物正文使用下述独立入口。调用方必须在构造日记草稿时保留材料和对应引用，并遵守每份草稿最多 64 项的输入边界。

`application.journal_artifact_material_producer.for_day(...)` 单独扫描精确 scope 的角色产物目录，不读取原件正文。未分类文本沿用原 ACTION 描述、material id 和 origin；明确的创作文本记为完成写作动作；阅读标签只记“收存了一份阅读材料”，不推断已经阅读或读完。`JournalMaterialPage.source_refs` 与 `activity_refs` 可用于构造草稿依赖。写入后若原 Source 被撤回，日记因来源依赖失效而不可继续读取。图片、音频产物仍未接入；阅读完成报告现通过独立的 role_reading 服务登记。

新增文件均放在 `role_work/journal/`：`materials.py`、`prompts.py`、`writing_output.py`、`writing.py`、`material_producer.py`；存储合同和服务继续使用同目录原文件。`CompanionApplication` 装配 `application.journal_material_producer` 与 `application.journal_artifact_material_producer`，根目录没有新增业务文件。

本切片新增的是 JSON 记录内可选语义字段，不变更 SQL 表结构或既有迁移指纹。旧记录缺少材料标签时按未知出处的主观书写读取，不推断事实；空扩展字段保持旧操作参数哈希，已有原操作回执可以继续幂等返回。随后 CORE-03 关系记忆切片将整体 schema 从 v17 升至 v18，本切片没有新增迁移。

### 已授权对话素材

`application.journal_conversation_material_producer.for_day(task_context, journal_context, ...)` 将当前任务范围内、仍有效且未撤回的入站消息分页为 `conversation` 材料。它检查精确角色、完整会话 scope、操作者授权、来源受众和原始内容哈希；日期依据接收时间和目标时区，页内按接收时间排序。文本明确标为“对方当时表达”，提示词要求保留转述语境，不把对方陈述自动升级为已核实事实或角色亲历。长消息仅在素材预览中保留开头，日记依赖仍指向完整原 Source。

消息撤回同时撤销其原 Source，使已保存日记和依赖该来源的其他内容按既有来源失效规则停止读取。分页只覆盖当前完全相同会话 scope 中已登记的输入；不跨窗口拼接，也不把语义上提到“读书/看文章”的聊天自动分类成阅读事实。实际阅读完成现由可信执行端经 role_reading 登记，不能从对话正文推断。

### 创作与阅读原件的显式分类

`RoleArtifact.journal_meaning` 使用独立于图片/文本/音频媒介的 `RoleArtifactJournalMeaning` 枚举：`UNCLASSIFIED`、`CREATIVE_TEXT`、`READING`。可信产物生产者创建记录时提供该标签；同一产物 ID 不能通过重试改换标签。旧 JSON 缺少字段时恢复为 `UNCLASSIFIED`，重复登记旧产物不会改写原记录。不按活动名称、正文关键词、文件名或模型输出推测类别；SQL 表、schema v18 与既有迁移指纹保持。

`application.journal_artifact_material_producer.contents_for_day(task_context, journal_context, limit=50, after_id=None)` 已由统一宿主装配。它在同一读取快照内核对当前任务身份、角色、精确私聊范围、`role.journal.write` 权限及原 Source 的有效性和受众；读取原文还使用该 capability 的当前 grant。正文哈希须与 `execution.digest(payload)` 一致。未分类产物、其他媒介、其他日期/会话及空正文不会作为原文素材返回；无效或撤回来源会使本次读取失败。

正文以 `creative_text` 或 `reading` 输出；创作动作由 `for_day` 返回，作品内容由 `contents_for_day` 返回，二者保留不同 material id 和相同来源 origin。已分类材料的 origin 按完整来源 scope、owner、source id 与版本 lineage 生成，同源的不同目录条目或版本不会被包装成独立证据。两种投影都保留原 SourceRef 和活动版本引用，能直接进入已有写作、归档和碎片出处链。

两入口各自按原产物 ID 分页，每条产物最多产生一条材料，页大小 `1..64`；即使本页过滤为空，也继续使用非空游标。调用方应分别扫描目录和正文，合并选用素材时仍遵守每份草稿最多 64 项。后续 journal_material_collector 已在同一快照内扫描全部分页并提供明确选用；超额候选的自动挑选仍未实现，不能只读取首页就称为当天全部材料。

长原文只预览前 8192 个字符并明确标注节选，依赖仍指向完整原 Source。提示词区分收存日期、实际阅读进度和原文事件日期，要求不补写缺失原文或节选之外的内容；衍生提取也保留“收存/待阅读”的语境。这些表达约束通过提示词实现，没有增加正文关键词封禁。当前标签不充当发布回执，也不充当实际阅读完成回执；可信活动中的明确进度仍按原状态单独供给。

## 验证

使用 AstrBot 自带 Python，全部数据为临时 V2 库和合成内容。上一轮素材生产、对话来源、写作、归档、宿主与关系记忆相关定向回归共 122 项通过，其中素材适配器专项 10 项。覆盖精确 scope/日期、计划状态语义、活动/产物/对话分页、文本产物目录不读取正文、对话时间排序及对方语义标签、撤回来源使既有日记失效、Source/活动引用配对、空材料忽略及页大小上限。关系记忆接入将内部 schema 推进至 v18；本切片没有新增 SQL 表或迁移。

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_journal_materials tests.test_conversation_messages -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_host_application tests.test_astrbot_inbound_adapter -q
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_native tests.test_astrbot_staging tests.test_astrbot_staging_host -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_journal_storage tests.test_relationship_memory tests.test_relationship_memory_service tests.test_relationship_memory_storage -q
```

覆盖素材分类和出处经过 prompt/保存/重开仍保留、科技阅读词语不拦截、仅余韵/碎片梦、最近原稿承接、正文与提取分离、非法碎片出处拒绝、人工修订/删除/撤回阻止迟到提交、失败不伪造正文、不自动重放、后台名额及前台可用、宿主停机/自有库关闭、旧 v17 内容/操作哈希兼容、原生结构化合同、staging 精确授权与撤权、加载及路由注销。

本轮产物分类与授权原文入口的定向回归共 **133 项通过**：角色生活/素材 28 项、写作及相关共享/宿主 68 项、真实 SDK 宿主/bootstrap 合约 37 项，其中新增 10 项。新增覆盖旧 JSON 缺字段重开与幂等、不允许原 ID 改换标签、目录和正文分条/同源、重复来源保持同源标识、分页空页续读及每产物单条输出、午夜后的当地日期过滤、未知/其他媒介不读原文、原文哈希变更/来源撤回/受众拒绝/当前 grant 与身份撤回、长文节选，以及分类原文经过写作和独立碎片提取后仍依赖原 Source。

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_life tests.test_role_journal_materials -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_journal_writing tests.test_role_life_host tests.test_role_life_storage tests.test_proactive_sharing tests.test_multibot_scope tests.test_host_application tests.test_host_recovery tests.test_isolation -q
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_staging_host tests.test_astrbot_staging_bootstrap -q
```

产物标签只增加 JSON 记录字段；未迁移在线 profile。新增实现仍位于 `role_work/`、`role_work/journal/` 与统一宿主装配，测试继续在 `tests/`，没有增加根级业务文件。

这些测试证明流程和数据边界，不证明模型一定写得更自然。真实文风、重复率和语义遵循度仍需在后续授权的模型样本上评估。本次没有真实模型调用或 QQ 发送；历史原文保持不变。
