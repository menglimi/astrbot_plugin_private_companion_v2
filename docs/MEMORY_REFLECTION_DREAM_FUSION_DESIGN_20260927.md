# 记忆反思与梦境压实融合设计（2026-09-27）

状态：设计稿。仅设计，不含实现代码，不改动任何业务源码。
范围：把「记忆反思（抽取新事实/经历）」与「梦境压实（对已沉淀记忆合并去重、重写摘要）」并入同一条离线批处理链，并给出时点、存储、审阅、日记边界、群边界与不可碰规则。
口径：所有关于 V2 现状的陈述均带 `文件:行号`；未在代码中核实的写「未核实」。本稿未运行任何测试套件。

---

## 0. 结论摘要

| # | 问题 | 结论 |
| --- | --- | --- |
| 1 | 融合口径 | 同一批次（同一条 `memory_reflections` 行 + 同一调度窗口 + 同一续接 job）内分 **S0 选材 → S1 抽取 → S2 压实候选 → S3 审阅落地** 四段；S1、S2 是两次独立的模型调用，各自独立回执；S2 只读「已沉淀且当前可授权读取的事实」，不读原始对话新料 |
| 2 | 时点 | **复用**现有 `memory.reflection_timezone` / `memory.reflection_time`，不新增「梦境时段」；只新增「压实节奏/阈值」类字段。梦境写作的时段留在 `role.life`（睡眠窗口），两者**不共享**时点 |
| 3 | 存储 | **第一期不新增表、不升 schema 版本（保持 v41）**。复用 `memory_reflections.manifest_json` / `receipts_json` / `result_json`、`memory_operations`（`state='pending'`）、`runtime_metadata`。若后续确需独立候选审计表，再按 v40→v41 的既有模板升 v42 |
| 4 | 候选与审阅 | 压实候选 = 一条 `defer_until_boundary=True` 的普通记忆提议（`state='pending'`）；采纳 = `commit_pending`（内部走 `correct`/`retract`，只新增修订版本，不改写旧版本）；驳回 = `discard_pending`；撤回 = 追加一条反向操作并保留原回执，永不删除历史 |
| 5 | 与日记链 | 硬隔离：日记/梦境正文不是事实来源，压实不读 `role_journals`，日记链也不读 `memory_atoms`；不共享时点 |
| 6 | 群记忆 | **第一期不纳入**。群记忆是 `memory_views` 成员陈述，只有本人可修订（`group/service.py:137-140`），合并会制造「全群共识」；群侧周期整理已由 `memory/group/episodes.py` 承担 |
| 7 | 不可碰 | 15 条确定性排除规则（见 §7），核心是：pinned / protected / session / short / 已遗忘 / 已归档 / 证据或来源失效 / 守卫命中 / 同批自产 / 群 scope |
| 8 | 验收 | 34 条定向测试条目（见 §8） |

---

## 1. V2 现状核实

### 1.1 记忆反思子系统

**任务与生命周期**

- 任务种类 `KIND = "memory.reflect"`，`Lane.BACKGROUND`，`SideEffect.LOCAL`，`timeout_seconds=180`，`max_attempts=1`，`concurrency=1`（`companion_v2/memory/reflection.py:31`、`reflection.py:47-48`）。
- 模型档案文案已声明「按原人格整理已授权资料，有来源地更新认识，**允许不修改**」（`reflection.py:34-36`）。
- 批次幂等键：`batch_id = "memory-reflection-" + digest([owner_key(context), request_id])`（`reflection.py:90`）；请求指纹 `request_hash` 覆盖窗口、角色指令、预算与 `schedule_ref`（`reflection.py:91`）。
- 已存在批次重放：同 `owner_key` + 同 `request_hash` 返回原状态，否则 `memory_reflection_conflict`（`reflection.py:92-102`）。
- 原始上下文绑定：`_row()` 要求存储的 `context_json` 与当前 `context.key` 一致，否则 `memory_reflection_unavailable`（`reflection.py:60-65`）。

**状态机**（`memory_reflections.state`，共 9 个值，`memory_schema.py:56` 无 CHECK 约束）

`selecting → prepared → running → received → modelled → complete`，分支态 `empty` / `failed` / `partial`（`reflection.py:208-261`、`reflection.py:512-514` 的中文标签表）。

- `running` 是**未知调用**态，明确拒绝重放（`reflection.py:232-233`）。
- `selecting` 阶段的每次推进都保存批次、游标、已选证据与预算（`reflection_selection.py:132-165`）。
- `complete`/`empty` 后 `finish_parent()` 只解决其链接的父批次，回执保持完整（`reflection_recovery.py:145-168`）。

**材料与输出格式**

- 材料种类：`reflection_source`（原文片段）、`existing_fact`、`correction_receipts`、`proposal_format`、`pending_proposals`、`coverage`（`reflection.py:263-335`），群 scope 追加 `group.member_safety/daily_hits`（`reflection.py:291-322`）。
- 输出结构固定为 `{summary, proposals[], pending_decisions[]}`（`reflection_output.py:26-45`）：
  - `proposals[].operation ∈ {add, correct, retract, no_op}`（`reflection_output.py:30`）；
  - `pending_decisions[].decision ∈ {accept, discard}`（`reflection_output.py:42-44`）；
  - `proposals` 与 `pending_decisions` 各上限 32 条（`reflection_output.py:122`、`:125-126`）。
- 解析极严：`finish_reason` 必须是 `stop`，重复 JSON 字段、非有限数、未知顶层键、重复 `item_id`、冲突 target 一律拒绝（`reflection_output.py:87-127`、`reflection_output.py:273-301`）。
- 校验产物为 `{summary, proposals, pending_decisions, rejected}`；被拒项进入 `rejected`，可修复项受 `REPAIRABLE` 白名单约束（`reflection_output.py:302-316`、`reflection_recovery.py:12-15`）。
- 落地时逐项按 `operation_key = batch_id + ":" + item_id` 幂等提交；失败项回到 `rejected` 并整体标记 `partial`（`reflection.py:449-472`）。

**材料占用与并发**

- 三种占用关系：`evidence` / `pending` / `pending_evidence`（`storage/reflection_schema.py:14-24`、`reflection_schema.py:28-34`）。
- 占用状态集合 `HELD_STATES = (selecting, prepared, running, received, modelled, failed, partial)`（`reflection_inputs.py:8-9`）。
- 片段键含来源 owner/ID、版本、区间、片段哈希与说话者归因（`reflection_inputs.py:12-18`）。
- 选材上限：候选检查 128 条（`reflection_selection.py:20`）、相关事实最多 `min(8, query_items)`（`reflection_selection.py:122-123`）、默认 `maximum_sources=32` / `maximum_chars=24000`（`reflection.py:68-69`）。
- 事实暴露给模型的上限与「未逐个读过」声明：`unexamined_fact_count` + `fact_count_basis = active_heads_not_individually_read`（`reflection_selection.py:126-129`）。

**调度与续接**

- `next_due()` 用 `ZoneInfo` + `time.fromisoformat` 计算下一次本地时刻，收窄到 UTC（`scheduling.py:17-27`）。
- `sync_configuration()` 从统一配置派生 `zone = memory.reflection_timezone`、`local_time = memory.reflection_time`（`scheduling.py:41-72`，字段读取在 `scheduling.py:65-66`）。
- `configure()` 的入参默认值即 `zone="Asia/Shanghai"`、`local_time="23:50"`、`enabled=True`（`scheduling.py:74-99`）。
- `memory_schedules` 行持有 `pending_batch`、`covered_until`、`revision`、`enabled`（`memory_schema.py:12-17`）。
- `_settle()` 只在真正覆盖完成时才推进 `covered_until`；仍有未覆盖/占用/不可用则保留并 1 分钟后再排（`scheduling.py:167-193`）。
- 后台容量来自共享池：`capacity = limits.background_slots - len(workers)`（`scheduling.py:118-121`）。
- 显式续接 job：`job_id = "memory-continue-" + digest([operator.subject, context.key, request_id])`，状态 `queued/complete/blocked`（`reflection_jobs.py:32-50`、`storage/reflection_job_schema.py:11`）。
- 启动恢复只修本地状态与唤醒时间，绝不在恢复扫描里派发模型（`checkpoints.py:1`、`checkpoints.py:100`）。

**失败与修复**

- `STALE_INPUTS` 含 `memory_reflection_stale`、`memory_settings_changed`、`memory_pending_changed`、`memory_schedule_changed`、`source_revoked`、`source_expired`、`memory_evidence_forgotten`、`memory_revision_conflict`、`memory_evidence_changed`（`reflection_recovery.py:16-18`）。
- 陈旧输入使批次进入 `partial`/`failed` 并隔离（`reflection_recovery.py:21-45`）；自动修复默认开启（`reflection.py:369-385`）。
- 「新记忆变更必须先重新反思」的硬闸门：`self._sequence(context) != receipts["sequence"]` → `memory_reflection_stale`（`reflection.py:182-183`）。
- `repair_material()` 只重发未落地项，不重放已保存项（`reflection_recovery.py:133-142`）。

**配置字段**（`companion_v2/memory/configuration.py:28-31`）

| 字段 | 类型 | 默认 | 应用 | 现有 UI 标签 |
| --- | --- | --- | --- | --- |
| `memory.reflection_enabled` | BOOLEAN | `False` | IMMEDIATE, core_only | 定时整理 |
| `memory.reflection_timezone` | TEXT | `"Asia/Shanghai"` | IMMEDIATE, core_only | 整理时区 |
| `memory.reflection_time` | TEXT | `"23:50"` | IMMEDIATE, core_only | 每日整理时间 |
| `memory.reflection_response_format` | TEXT | `"text"` | IMMEDIATE, core_only | 模型返回格式 |
| `memory.reflection_auto_repair` | BOOLEAN | `True` | IMMEDIATE, core_only | 允许修复未完成整理项 |

校验：`response_format ∈ {text, json_object, json_schema}`，时区必须可 `ZoneInfo()`，时钟不得自带时区（`configuration.py:49-55`）。设置读取返回 `(values, token)`，token 由字段值 + `source_revision` 摘要而成（`configuration.py:64-69`），并被批次用作 `settings_token` 失效判据（`reflection.py:121`、`reflection.py:161-162`）。

### 1.2 存储现状

主库 schema 版本 **v41**：`SCHEMA_VERSION_V41 = "companion-v2.storage.v41"`，`SCHEMA_VERSION = SCHEMA_VERSION_V41`（`companion_v2/storage/schema.py:1581-1582`）。

| 表 | 定义位置 | 关键列 |
| --- | --- | --- |
| `memory_reflections` | `storage/memory_schema.py:54-60` | `batch_id, owner_key, request_hash, context_json, manifest_json, state, result_json, receipts_json, task_id, created_at, updated_at` |
| `memory_schedules` | `memory_schema.py:12-17` | `schedule_id, owner_key, revision, context_json, settings_json, enabled, next_at, covered_until, pending_batch` |
| `memory_reflection_inputs` | `storage/reflection_schema.py:28-33` | `(batch_id, kind, input_key)` 主键 + 查询索引 |
| `memory_reflection_jobs` | `storage/reflection_job_schema.py:5-18` | `job_id, batch_id, owner_key, context_json, operator_json, state, next_at, result_code` |
| `memory_atoms` | `memory_schema.py:18-25` | `atom_id, owner_key, namespace, subject, fact_key, single_value, revision, state, scope_json, record_json, source_json` |
| `memory_revisions` | `memory_schema.py:26-30` | 全历史，`state ∈ active/superseded/invalidated` |
| `memory_operations` | `memory_schema.py:31-37` | `operation_id, owner_key, caller_id, namespace, payload_hash, proposal_json, context_json, state, result_json` |
| `memory_changes` | `memory_schema.py:38-42` | `sequence` 自增，`kind ∈ added/corrected/retracted/forgotten` |
| `memory_guards` | `memory_schema.py:43-47` | `(owner_key, fact_key, evidence_key)` 主键，`reason` |
| `memory_views` | `memory_schema.py:48-53` | 经历、相识卡、群陈述共用 |
| `role_journals` | `storage/schema.py:1112` | `kind` CHECK 仅允许 `('diary', 'dream')` |

升级链模板（升版时照抄）：`storage/group_safety_schema.py:1-21` 定义 `*_STATEMENTS` / `*_TABLES` → `storage/schema.py:1574-1586` 组装 `V41_MIGRATION_STATEMENTS` / `V41_REQUIRED_TABLES` / 指纹 → `storage/runtime.py:968-979` 的 `_migrate_v40_to_v41` 与 `runtime.py:981-986` 的 `_validate_v41_migration_record` → 打开时链条 `runtime.py:915-966`（含 `runtime.py:920-925` 的版本相等与必需表检查）。

**不升版本的先例**：群记忆切片就明确「不新增 SQL 表或 schema 升级」（`docs/CORE_GROUP_MEMORY_20260924.md:11`）；`runtime_metadata` 被多个领域当作免迁移的持久状态位使用，例如群片段摘要 `memory/group/episodes.py:147-160`、`:183-187`，活动摄取 `memory/activity_ingestion.py:133-165`，表达轮换 `expression/style_rotation.py:68`、`:141-144`。

### 1.3 记忆条目与写入

- 保留策略枚举：`session / short / durable / protected`（`memory/models.py:99`）；`short` 必须带 `valid_to`（`models.py:135-136`）；`protected` 需要 `memory.protect` 能力（`writer.py:100-101`）。
- 展示模式：`relevant / pinned`（`models.py:101`）。
- 事实族键：`fact_key = digest([namespace, subject, predicate, qualifiers])`（`models.py:138-140`）。
- owner：安装 + Bot + 角色 subject + 人类 subject + `"private"`（`models.py:143-146`）。
- 单值唯一索引：`memory_single_idx ON memory_atoms(owner_key, fact_key) WHERE single_value = 1 AND state = 'active'`（`memory_schema.py:25`）。
- 「只增不改写」的实际语义：`correct` 写新 revision 并把旧 revision 标 `superseded`（`writer.py:281-289`），`retract` 把 atom 标 `invalidated` 并保留旧 `source_json`（`writer.py:290-296`），任何情况下都不覆盖已有修订正文。
- `correct` 的身份约束：`(subject, predicate, qualifiers)` 必须与目标一致，否则 `memory_target_mismatch`（`writer.py:258-260`）——**这条直接决定了压实只能在同一 `fact_key` 族内改写 `object`/`representation`**。管理员命令同理，其 `value` 只允许 `{object, representation}`（`management.py:222-227`）。
- CAS：`_head()` 要求 revision 精确相等且 `state='active'`（`writer.py:48-57`）。
- 证据二次授权：`_validate_proposal()` 逐条 `access.evidence()`，并禁止用派生记忆自我认证（`evidence.source.owner.startswith("memory.")` → `memory_derived_evidence`）（`writer.py:98-105`）。
- 归属规则：`attribution="user"` + `subject="self"` 的 add/correct 必须有人类原文证据（`writer.py:106-108`）；`attribution="bot"` + `subject="self"` 被拒绝（`writer.py:113-114`）。
- 复用禁止：`memory_guards` 命中旧的 fact_key + evidence_key 时，不能仅凭旧证据恢复被纠正/遗忘的结论（`writer.py:117-122`）。
- 延迟提交：`defer_until_boundary=True` 使提议停在 `state='pending'`，等待 `commit_pending` 或 `discard_pending`（`writer.py:152`、`writer.py:177-192`、`writer.py:231-245`）。
- 回执不含正文：`_receipt()` 明确「Receipts deliberately contain no remembered body or original evidence text」（`writer.py:162-165`）。
- 遗忘：逻辑遗忘 + `memory_guards(reason='forgotten')` + 撤销全部相关来源 + 写 `kind='forgotten'` 变更（`writer.py:321-361`、`writer.py:373-403`）。
- 变更序号：`memory_changes(sequence AUTOINCREMENT)`，`changes()` 按 `sequence` 分页（`writer.py:405-413`）。
- 冷归档先例（唯一就地改 `record_json` 的地方，且只加 `archive` 标记、不动记忆正文）：`archive.py:135-188`，其中就地写入在 `archive.py:166-171`。

### 1.4 检索与召回

- 查询会话有预算：`turn_calls` / `turn_chars`（`query.py:70-82`）；会话绑定 `context_key` 与过期时间（`query.py:34-50`）。
- pinned 选择独立于相似度与保留策略（`memory/pinned.py:11-35`，SQL 条件在 `pinned.py:18`）。
- 事实增量投影 `FactIndex.advance()` 每步 `sync_items = 256`，候选 `candidate_items = 128`（`fact_index.py:15-16`、`fact_index.py:82-139`）。
- 事实候选排序走 FTS5 `bm25`，并强制 `retention != 'session' OR scope = 当前 scope`（`fact_index.py:147-183`，会话隔离在 `fact_index.py:162-163`）。
- 对象/来源投影 `RecallIndex`：`sync_items = 256`、`candidate_items = 128`、`vector_items = 256`、`projection_version = 2`（`recall_index.py:36-42`）。
- 本轮上下文快照先放 pinned、再放相关经历（共享同一预算）、再放相关事实（`memory/context.py:23-75`）。
- 工具面：`MUTATIONS = {memory.proposal.submit, memory.forget, memory.experience.save}`（`memory/tools.py:23`）；提议 schema 允许字段见 `tools.py:25-36`。

### 1.5 群记忆

- 群陈述存在 `memory_views`，`kind = "group.public.statement.v1"`，owner 为 `memory.group`（`memory/group/service.py:17-18`）。
- 群 owner 含安装/平台/Bot/账号/群号/原生 session/角色，不含成员（`memory/group/access.py:14-24`）。
- 只有原发言者本人能修订或撤回自己的陈述（`group/service.py:136-140`）。
- 群记忆访问要求 `group.memory.read` / `group.memory.write`，且必须是群 scope（`group/access.py:11`、`group/access.py:31-37`）。
- 本轮上下文只放「不重放、只引用」的快照：`MAX_ITEMS = 4`、`MAX_BYTES = 16384`（`group/context.py:12-13`、`group/context.py:32-55`）。
- 群周期整理已由 `group/episodes.py` 承担：默认 `enable_group_episode_memory=True`、`group_episode_refresh_minutes=180`、`group_episode_min_messages=12`、`max_group_episodes=10`（`group/episodes.py:39-46`），到期判据 `due()` 在 `group/episodes.py:162-173`，落盘在 `runtime_metadata`（`group/episodes.py:183-187`）。
- 安全命中（T08）是确定性规则证据：策略常量含 `reflection_hit_limit=128`（`group/hits.py:24-37`），幂等落盘 `persist_hits()`（`group/hits.py:126-133`），反思批次把它当材料而非事实（`reflection.py:291-322`）。
- 群成员相识卡另有独立域 `memory/person/`，且约定 `memory/` 与 `memory/group` 不得 import `memory/person`（`docs/REPOSITORY_LAYOUT.md:97`）。

### 1.6 日记与梦境写作（`role.life`）

- 配置组 `role.life`，字段与默认值：`enabled=False`、`diary_enabled=True`、`diary_time="23:50"`、`timezone="Asia/Shanghai"`、`sleep_enabled=False`、`sleep_time="00:30"`、`sleep_timezone="Asia/Shanghai"`、`sleep_minutes=480`、`reading_enabled=False`、`derive_enabled=True`、`diary_style_prompt=""`、`dream_theme_candidates=""`、`dream_mixed_themes_enabled=False`、`dream_intimate_theme_enabled=False`、`dream_afterglow_mode="auto"`（`companion_v2/role_work/life/configuration.py:12-21`）。
- **`enable_enhanced_dreams` 在 V2 源码中不存在**（全仓 `*.py` 零命中），它是 V1 字段：`plugin_bootstrap.py:819` 读取、`daily_state.py:3700-3702` 消费。V2 的等价物就是上列 4 个 `dream_*` 字段（T34 已完成，见 `docs/V2_GAP_CLOSING_TASKS_20260927.md:97`）。
- 梦境由「睡眠完成」触发，而不是时钟：`RoleLifeRuntime.advance()` 只对 `work.kind == "sleep"` 且 `state is COMPLETED` 且未生成过的活动启动 `self.dream(...)`（`role_work/life/runtime.py:292-294`）；`dream()` 组装事件并调用 `journal_triggers.sleep_completed(...)`（`life/runtime.py:238-250`）。
- 日记由 `role.life` 的每日注册驱动：`register_daily(... timezone=settings["timezone"], local_time=settings["diary_time"])`（`life/runtime.py:126-129`），调度器 `next_daily()`（`journal/scheduling.py:18-24`）与 `advance()`（`journal/scheduling.py:74-101`）。
- 写作任务种类：`role.journal.diary` / `role.journal.dream` / `role.journal.derive` / `role.journal.select`（`journal/writing.py:30-34`），并发 2、超时 180（`writing.py:89-93`）。
- 提示词：`DIARY`（`journal/prompts.py:29-35`）、`DREAM`（`prompts.py:37-44`）、`DERIVE`（`prompts.py:46-55`）；梦境题材强化后缀由 `dream_instruction(settings)` 生成，仅对 `JournalKind.DREAM` 追加（`prompts.py:75-93`、`prompts.py:107-109`）。
- `recent_journal` 只读 `role_journals` 的正文版本，且明确「摘要/碎片不是独立记忆」（`writing.py:103-123`、`writing.py:308-316`）。
- 日记/梦境**不发布为事实 Source**：切片文档明文规定（`docs/CORE_ROLE_JOURNAL_SLICE.md:14`）；写入走 `self.journal.save`（`writing.py:367-369`），不经过 `MemoryWriter`。
- 素材语义枚举含 `action/creative_text/published_text/reading/conversation/plan/reflection`（`journal/materials.py:14-22`），上限 `MAX_JOURNAL_MATERIALS = 64`（`materials.py:11`）。
- **T17 已定**：识屏材料融合进日记链（`docs/V2_GAP_CLOSING_TASKS_20260927.md:67`、`:115`、`:151`）；采集器已把 `screen` 作为一类素材读取器（`journal/collection.py:78-88`，注入点在 `collection.py:52-62`），识屏侧生产者只接纳用户显式标记为日记素材的锚点（`companion_v2/screen/journal_materials.py:14-22`、`:33-44`）。

### 1.7 宿主路由与页面

- 私聊记忆 API 前缀 `/astrbot_plugin_private_companion_v2/memory`（`astrbot_host/memory_api.py:18`）；路由清单见 `memory_api.py:26-44`，其中反思相关三条：`GET /reflections`、`POST /reflections/retry`、`POST /reflections/queue`（`memory_api.py:31-33`）。
- 反思入口统一经 `ReflectionManagement(session.application, operator)` + 固定目标 `session.profile.target`（`memory_api.py:46-57`）；后台续接入队在 `memory_api.py:99-100`，前台修复在 `memory_api.py:101-105`。
- 群记忆有独立 API 与独立目标解析（`astrbot_host/group_memory_api.py:9`、`:15`、`:47-49`），由 `astrbot_host/multi_api.py:71`、`:154-156` 挂载。
- 页面：`pages/陪伴小屋/memory-page.js` 的错误码文案含 `memory_reflection_*`（`memory-page.js:13-19`），工作区含「整理与修复 / 事实治理 / 来源与经历 / 记忆设置 / 范围清理」五个分区（`memory-page.js:227`），设置项标签已覆盖全部 `memory.reflection_*`（`memory-page.js:201`）。

---

## 2. V1 参考机制核实（只读）

> 结论先行：**V1 没有「事实级压实」**。V1 的 `companion_memory` 只有「按签名去重 + 新条插队 + 超限截断」，没有任何合并/重写既有条目的离线批处理。与「梦境压实」语义最接近的真实机制是 **梦境碎片池**（权重 + 衰减 + 模糊键去重 + 加权抽样），以及**每日终盘巡视**（跨日报告与柔性纠偏注入）。V1 里真正做「合并/去重/写回」的是表达规则合并与日记重复修复。

### 2.1 `dreaming.py`（梦境碎片与日记质量）

| 机制 | 真实实现 | 位置 |
| --- | --- | --- |
| 碎片归一化 | 文本清洗 + 有效性判定 + 权重夹取到 `[0.2, 6.0]` | `dreaming.py:295-322` |
| **衰减** | `decay = pow(0.72, age_hours / 24)`，`effective = weight * decay` | `dreaming.py:325-331` |
| **合并去重** | 模糊键 = 去非中英文数字后小写截 36 字符；同键丢弃；`effective_weight < 0.12` 丢弃；同文本保留权重更高者；按 (权重, 时间) 降序截断到 **48** | `dreaming.py:334-362` |
| 抽取上限 | 单次最多取 12 条、保留 8 条 | `dreaming.py:365-389` |
| 兜底碎片 | 从当日状态/天气/日程取种子，权重 `max(1.0, 2.4 - index*0.4)`，最多 5 条 | `dreaming.py:392-433` |
| **写回策略** | `merge_dream_fragment_pool()` = 旧池 + 新条 → 重新归一化（即「全量重算后覆盖」） | `dreaming.py:436-439` |
| 加权抽样 | `random.choices` 按有效权重不放回抽，最多 6 条 | `dreaming.py:442-457` |
| 组合成记忆碎片 | 池优先，不足再从最近 4 篇日记的 `share_seed/summary` 补 | `dreaming.py:460-475` |
| 题材表 | `dream_theme_specs()`：默认 8 个题材；读 `dream_theme_candidates`（逗号分隔）；暧昧题材受 `enable_intimate_dream_theme` 门控 | `dreaming.py:555-577` |
| 强化梦境抽选 | `generate_enhanced_dream_pick()`：先用碎片池，池空则用「人格 + 天气 + 活动 + 醒来只剩残影」兜底；混搭开关 `enable_mixed_dream_themes` 且随机 `< 0.35` 才混 | `dreaming.py:580-600` |
| 日记重复检测阈值 | `share_ratio ≥ 0.58` 或 `all_ratio ≥ 0.48` 或 `cross_ratio ≥ 0.62` 或关键词重合 `≥ 4` → 判重 | `dreaming.py:248-276`（阈值在 `:274`） |
| 重复修复写回 | `_repair_duplicate_daily_diary()`：直接替换 `summary/body/share_seed`（就地覆盖式写回） | `dreaming.py:279-292` |
| 相似度算法 | `difflib.SequenceMatcher(None,a,b).ratio()`，长度 < 8 直接 0 | `dreaming.py:205-210` |

V1 调度侧证据：日记保存后立刻合并碎片池（`daily_state.py:826-836`），并按 `max_diary_entries`（默认 **14**）截断日记列表（`daily_state.py:810-811`）；强化梦境开关在每日状态生成的抽选处生效（`daily_state.py:3699-3702`，`_generate_enhanced_dream_pick` 定义在 `daily_state.py:4745`），余韵强度档在 `daily_state.py:4461` 读取。

### 2.2 `daily_review.py`（每日终盘巡视）

| 机制 | 真实实现 | 位置 |
| --- | --- | --- |
| 触发 | 自有 `_daily_review_loop()` 异步循环，带 `_stop_event`；异常退避 30 分钟 | `daily_review.py:1716-1764` |
| **时点** | `daily_review_time` 默认 `"04:00"`，解析为分钟数；目标日 = 「已过配置时刻则昨天，否则前天」 | `daily_review.py:216-232`、`daily_review.py:1789-1793` |
| 时区 | `environment_perception_timezone`，默认 `Asia/Shanghai`，`ZoneInfo` 失败回落同值 | `daily_review.py:205-214` |
| 补跑窗口 | `_daily_review_pending_dates(max_days=3)`：从最近完成日 +1 补到今天，最多取 `min(7, max_days)` 天 | `daily_review.py:1677-1714` |
| 失败冷却 | `failed/paused` 时优先 `retry_after`，旧记录回落到固定冷却常量 | `daily_review.py:1771-1786` |
| 材料聚合 | 三类样本：审计 case、主动消息日志、被动未回复样本，逐条按日期匹配 | `daily_review.py:527-580`、`daily_review.py:564-574` |
| **聚类/去重** | `_daily_review_case_cluster_key()` 由 kind/scene/role/outcome/category/reason + 语音/完整标记组成；**非异常** case 还追加 `inbound|output` 的 sha256 前 10 位 | `daily_review.py:508-525` |
| 脱敏 | 6-20 位连续数字替换为占位；`api_key/token/secret/...` 与 `Bearer` 掩码 | `daily_review.py:244-264` |
| 输出与写回 | 报告按日存 `daily_review_reports`；指导项经 `_activate_daily_review_guidance()` 生效 | `daily_review.py:234-239`、`daily_review.py:1393` |
| **注入策略** | 开关 `daily_review_auto_apply_guidance` 默认 **True**；注入前检查 `active_until` 过期；最多 8 条；带 marker 去重；文案显式声明「不能覆盖当前用户意图/人格/安全规则/事实边界」 | `daily_review.py:1795-1836` |
| 指导有效期 | `_daily_review_guidance_expiry()` | `daily_review.py:1377` |

### 2.3 `user_memory.py`（用户记忆：写入、去重、召回）

| 机制 | 真实实现 | 位置 |
| --- | --- | --- |
| 事实签名 | 去非中英文数字 → 小写 → 截 **80** 字符 | `user_memory.py:297-300` |
| 候选分类 | 关键词打分 → `kind ∈ {preference, boundary, important}`，`weight = min(5, 1 + score + (explicit ? 2 : 0))`；临时语境、软性玩笑边界、口嗨一律不保留 | `user_memory.py:3362-3411` |
| **写回策略** | 新条 `insert(0)` → **按签名去重** → 截断到 `max_companion_memory_items`（默认 **36**）；`updated_at` 随写 | `user_memory.py:3448-3464`（去重在 `:3456-3461`，上限在 `:3463`） |
| 读取兼容 | `_cleanup_companion_memory_items()` 每次读取都重新归一化并回写 `memory["items"]` | `user_memory.py:302-315` |
| 召回打分 | 时间衰减（≤36h 加 2.0，≤168h 加 1.0）+ 提示词 token 命中每条加 2.5；重复签名跳过；列表尾部再加权（最新 +3.0、近三条 +1.0）；取 top-3 后按原序号回排 | `user_memory.py:4182-4242` |
| 对话片段周期整理 | `enable_dialogue_episode_memory` 门控；**消息数 ≥ 8 或 距上次 ≥ 90 分钟**任一满足才跑；窗口 24 小时、最多 70 行 | `user_memory.py:9576-9599` |
| 片段写回 | 摘要与 `episodes[-1].summary` 相同则不追加；`del episodes[:-max_dialogue_episodes]`（默认 **12**） | `user_memory.py:9794-9799` |
| 未完话头写回 | 按 `text` 去重后追加，`del current_loops[:-12]` | `user_memory.py:9800-9818` |
| 表达规则合并 | `merge_into_id` 字段让模型优先复用已有规则而非新增；`_merge_learned_expression_rules()` 负责真实合并 | `user_memory.py:9645-9651`、`user_memory.py:2575`、`user_memory.py:9835-9841` |
| 原子落盘 | 片段与新规则在 `self._data_lock` 内改内存，再一次 `_save_data_sync(sections={"users", ...})` | `user_memory.py:9785-9863` |

V1 用户记忆**没有**「离线合并多条既有事实」的实现：`_memory_fact_signature` 只用于阻止同文本重复写入，超限策略是**按插入顺序截断最旧**（`user_memory.py:3462-3463`），不是按价值/相似度合并。这一点对本设计很关键：V2 的压实层必须自建候选与审阅语义。

### 2.4 `memory_companion_adapter.py`（外部记忆桥）

- 外向写回统一走 outbox，带 `idempotency_key`、`version`、`source_refs`，返回体含 `deduplicated` 字段（`memory_companion_adapter.py:815-885`，关键参数在 `:859-870`）。
- 梦境碎片确实**反向进入记忆**：`_memory_companion_record_dream_fragment()` 受 `enable_memory_companion_dream_fragment` 门控，写入 `record_persona_life(..., importance=0.48, tags=["dream","dream_fragment","persona_life","梦境碎片"], session_id="private_companion:dream")`（`memory_companion_adapter.py:3401-3446`）。
- 该桥是**可选外部插件**能力，V2 不迁入（`docs/V2_GAP_CLOSING_TASKS_20260927.md:160`：livingmemory/外部记忆桥 12 项由 V2 自有记忆替代）。

---

## 3. 问题 1：融合口径与阶段划分

### 3.1 口径选择

**同一批次、四段执行、两次模型调用。** 「同一个离线批处理」指的是复用同一条 `memory_reflections` 行、同一个调度窗口、同一条续接 job；而不是把抽取与压实塞进一次模型调用。

理由（全部有代码依据）：

1. `REFLECTION_SCHEMA` 是封闭结构，顶层只允许 `summary/proposals/pending_decisions`，且 `proposals` 上限 32（`reflection_output.py:115-126`）。压实候选若挤入同一数组，会与抽取项共享 32 条预算，并让 `item_id` 命名空间与 `repair_item_ids` 机制（`reflection.py:132-140`、`reflection_output.py:229-230`、`:311-314`）语义重叠。
2. 抽取输入是新原文，压实输入是已沉淀事实；把两者混在一次调用里会让「未核实的新料」与「改写既有记忆」共存于同一份输出，一旦解析失败 `REFLECTION_SCHEMA` 的整批拒绝语义（`reflection_output.py:273-301`）会同时废掉两类结果。
3. 现有 `_generate()` 的失败语义是「有返回则记为 failed 可恢复、无返回则保持 unknown 不重放」（`reflection.py:350-367`）。两次独立调用可以让压实失败**不回滚**已成功的抽取落地（`reflection.py:423-473` 逐项幂等）。
4. 压实必须读「当前已沉淀事实」，而抽取的 `manifest["memory_sequence"]` 在 `selecting` 完成时就被冻结（`reflection_selection.py:159`），且 `_validate_inputs()` 用 `memory_changes.sequence` 判定陈旧（`reflection.py:182-183`）。S2 必须在 S1 落地后**重新取一次序号**才成立。

### 3.2 阶段划分

| 阶段 | 名称 | 输入 | 输出 | 幂等键 |
| --- | --- | --- | --- | --- |
| **S0** | 选材（现有，不改） | 当前来源分区索引快照、窗口 `[start, end)`、预算 | `manifest.evidence[]`、`manifest.facts[]`、`manifest.pending[]`、`manifest.memory_sequence` | 批次 `batch_id` = `"memory-reflection-" + digest([owner_key, request_id])`（`reflection.py:90`）；片段占用键 `span_key()`（`reflection_inputs.py:12-18`） |
| **S1** | 反思抽取（现有模型调用，不改） | S0 材料 + `correction_receipts` + `pending_proposals` + 格式 schema | `{summary, proposals[], pending_decisions[], rejected[]}` | 任务 `task_id = row["task_id"] or "memory-extract-task-" + digest(batch_id)`（`reflection.py:245`）；逐项 `operation_key = batch_id + ":" + item_id`（`reflection.py:457`） |
| **S2** | 压实候选（**新增模型调用**） | §7 规则筛出的**事实族**（同 `fact_key` 的活跃原子 + 各自证据片段）+ 自 S1 落地后的新 `memory_sequence` + 上一轮压实指纹 | `{families: [{family_key, atoms[], action, merged, citations[], rationale, risk}], summary}`，`action ∈ {rewrite, retire, keep}` | 任务 `task_id = "memory-compact-task-" + digest([batch_id, round])`；候选 `candidate_id = "compact-" + digest([owner_key, family_key, 排序后的 (atom_id, revision)])` |
| **S3** | 审阅落地（**新增，无模型**） | S2 候选 | 每条 `memory_operations` 记录（`state='pending'`）或已落地的 `correct`/`retract` 回执 | `operation_key = batch_id + ":compact:" + item_id`（与 S1 同构，避免命名冲突） |

**S2 材料边界（关键设计约束）**

- S2 只读 `memory_atoms` 中 `state='active'` 的行与其 `record_json.proposal`；每族最多引用 `memory.compaction_max_atoms_per_family` 个原子。
- S2 读证据片段必须走 `access.evidence()`（`access.py:87-92`），与 S1 完全相同的授权路径；任何一条读不到就把该族整体剔除并记 `unavailable_families`，而不是降级换料（沿用 `reflection_selection.py:103-104` 的 `unavailable_sources` 精神与 `docs/CORE_SELF_REVIEW_20260926.md:36-37` 的「未通过复核一律拒绝，不降级」口径）。
- S2 **不得**读 `conversation_inputs` 原始消息全文（那是 S1 的职责），也不得读 `role_journals`（见 §6）。
- S2 输出不得包含 `operation="add"`：压实只做「收敛」，新事实一律由 S1 负责。这条要在 S3 校验时硬性拒绝。

**S2 与 S1 的次序与短路**

- S2 仅在 S1 到达 `complete` 或 `empty` 后启动（`reflection.py:221-223` 已有 `complete`/`empty` 的收口点）。
- S1 为 `failed`/`partial` 时**不启动 S2**：既有的自动修复链（`reflection.py:369-385`）与显式修复（`reflection.py:387-411`）会先接管；压实不能建立在未知的抽取结果之上。
- S2 可以被 `memory.compaction_enabled=False` 或节奏闸门（§4）单独短路，此时批次仍在 S1 后正常 `complete`。

**S2 失败语义（复用既有词汇，不新增批次状态）**

- 派发前失败：写 `manifest.compaction.state = "blocked"` + `manifest.compaction.blocked_code`，批次仍 `complete`（复用 `selection.blocked_code` 的既有做法，`reflection_selection.py:151-155`、`reflection_jobs.py:110-112`）。
- 有返回但解析失败：记 `manifest.compaction.issues`，可进入下一轮（压实不是一次性正确的事）；不把整个反思批次拖成 `partial`。
- 派发后无返回：记 `manifest.compaction.state = "unknown"` 且**永不重放**（对齐 `reflection.py:233` 与 `reflection_jobs.py:125-126`）。

---

## 4. 问题 2：时点

### 4.1 结论

**复用现有反思调度，不新增「梦境时段」配置。** 只新增「压实节奏/阈值/落地方式」字段。

### 4.2 理由

1. `memory_schedules` 是「一个 owner 一行」结构：`schedule_id` 主键、`next_at`、`covered_until`、`pending_batch`（`memory_schema.py:12-17`）。要再加一个 wall clock，就得要么再造一个 `schedule_id` 命名空间（现有 `advance()` 只扫 `schedule_id LIKE 'memory-daily-%'`，`scheduling.py:107`；`next_wake()` 只取 `MIN(next_at)`，`scheduling.py:202`），要么加列——两者都会让「同一 owner 同一时刻两个后台作业写同一批事实」成为可能。
2. 压实与抽取**不能并发**：`_validate_inputs()` 的陈旧判据是 owner 级 `memory_changes.sequence`（`reflection.py:182-183`），任何人插入新变更都会让另一个作业的批次变 `partial`。共用一个批次天然消除这个竞态。
3. 现有调度已具备完整的持久化与恢复语义：`configure()` 写 `next_at`/`covered_until`（`scheduling.py:91-95`），`_settle()` 只在真正覆盖完成时推进窗口（`scheduling.py:177-189`），启动恢复只修本地状态（`checkpoints.py:100`）。复用即免费获得这些保证。
4. 「梦境时段」在 V2 里已经有归属：它是 `role.life` 的**睡眠窗口**（`sleep_time="00:30"` + `sleep_minutes=480`，`life/configuration.py:14`；身体时钟推进在 `life/runtime.py:296-307`），梦境写作由睡眠完成事件触发（`life/runtime.py:292-294`）。这是**写作**关注点，不是**记忆治理**关注点，不应进入 `memory` 配置组。

### 4.3 字段建议（配置组 `memory`，沿用 `companion_v2/memory/configuration.py:28-31` 的登记方式）

| 字段名 | 类型 | 默认值 | 范围/枚举 | 配置组 | 层级 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| `memory.compaction_enabled` | BOOLEAN | `False` | — | `memory` | 窗口级（`ConfigLayer.WINDOW`，见 `configuration.py:45-46`） | 与 `reflection_enabled` 默认关闭口径一致（`configuration.py:28`） |
| `memory.compaction_apply_mode` | TEXT | `"review"` | `review` / `auto_low_risk` | `memory` | 窗口级 | `review` 只产候选待人审；`auto_low_risk` 仅对 §7 低风险族自动采纳 |
| `memory.compaction_min_interval_hours` | INTEGER | `24` | 1–720 | `memory` | 窗口级 | 距上次成功压实的节奏闸门 |
| `memory.compaction_min_idle_days` | INTEGER | `14` | 0–3650 | `memory` | 窗口级 | 族内每条原子距上次更新至少 N 天；`0` 表示不要求（对照归档 `DEFAULT_IDLE_DAYS=180`，`archive.py:42`） |
| `memory.compaction_min_family_size` | INTEGER | `2` | 2–8 | `memory` | 窗口级 | 少于该规模不构成「压实」 |
| `memory.compaction_max_families` | INTEGER | `8` | 1–32 | `memory` | 窗口级 | 每批族数上限（32 与 `REFLECTION_SCHEMA` 的 proposals 上限对齐，`reflection_output.py:122`） |
| `memory.compaction_max_atoms_per_family` | INTEGER | `8` | 2–16 | `memory` | 窗口级 | 单族引用原子上限 |
| `memory.compaction_max_evidence_chars` | INTEGER | `12000` | 2000–48000 | `memory` | 窗口级 | S2 证据字符预算（区间对齐 `maximum_chars`，`reflection.py:88`） |

- **不新增** `memory.compaction_response_format`：复用 `memory.reflection_response_format` 及其校验（`configuration.py:49-51`），避免同一 provider 出现两个互相冲突的格式开关。若将来 S2 换用不同 provider，再单列。
- **不新增**「梦境时段」字段到 `memory` 组，也不新增到 `role.life` 组：`role.life` 的睡眠/日记时段已完整（`life/configuration.py:13-18`），T34 的 4 个梦境字段也已就位（`configuration.py:17-18`、`docs/V2_GAP_CLOSING_TASKS_20260927.md:97`）。
- 字段生效方式：`ApplyMode.IMMEDIATE` + `core_only=True`，与既有 5 个反思字段完全一致（`configuration.py:28-31`）；设置变更经 `settings_token` 使未派发批次失效（`reflection.py:161-162`、`:177-178`）。

### 4.4 与「梦境时段」的关系（回答「是否共享时点」）

**不共享。** 三条理由：

1. 两个作业的写入目标不同：压实写 `memory_atoms/memory_revisions/memory_operations`，梦境写 `role_journals/role_journal_derivatives`（`storage/schema.py:1112`），没有事务或次序依赖。
2. 授权档案不同：压实需要 `memory.propose`/`memory.correct`/`memory.retract`（`writer.py:141`、`access.py:27-39`）；梦境写作需要 `role.journal.write`（`journal/triggers.py:59`）。共享时点会把两套授权绑在同一个失败域上。
3. 语义不同：压实是治理动作，应当发生在「人还醒着、还能审阅」的时刻；梦境写作应当绑定**模拟睡眠**而非管理员时钟（`life/runtime.py:292-294`、`life/runtime.py:167-170` 的注释「已醒来，梦境由独立任务记录」）。

**唯一需要注意的耦合**：两者都从同一个后台容量池取名额（`scheduling.py:118-121` 与 `journal/scheduling.py:80-81` 都用 `limits.background_slots`）。若把日记时间与反思时间都设为 `23:50`（默认值，`life/configuration.py:13` 与 `memory/configuration.py:28`），两者会竞争名额——结果是排队而非错误（`scheduling.py:122-135` 每轮重新取到期行；`journal/scheduling.py:82-101` 同理）。实施时建议在页面提示这一点，而不是靠改代码解决。

---

## 5. 问题 3：存储影响

### 5.1 结论：第一期不新增表、不升 schema 版本（保持 v41）

`SCHEMA_VERSION = "companion-v2.storage.v41"`（`storage/schema.py:1581-1582`）。以下四个复用点覆盖全部新状态：

| 需要持久化的东西 | 复用位置 | 依据 |
| --- | --- | --- |
| 压实阶段与游标 | `memory_reflections.manifest_json.compaction`（JSON blob，无列约束） | `memory_schema.py:55`；`manifest_json` 已被选材阶段自由扩展（`reflection.py:112-140`、`reflection_selection.py:161-165`） |
| 压实幂等回执 | `memory_reflections.receipts_json.items`，键前缀 `compact:` | `receipts_json` 已按 `item_id` 存任意回执（`reflection.py:437-442`、`:454-459`） |
| 压实候选（待人审） | `memory_operations` 一行，`state='pending'`，`proposal_json` 存提议，`result_json` 存回执 | `memory_schema.py:31-37`；pending 语义由 `defer_until_boundary=True` 产生（`writer.py:152`） |
| 压实节奏游标 | `runtime_metadata` 键 `memory.compaction.v1:<owner_key>` | 先例：`group/episodes.py:147-160`、`:183-187`；`activity_ingestion.py:133-165` |

**为什么不升版本是安全的**（逐条核实）：

1. 不新增表、不新增列、不新增索引 → `_validate_table_shapes()` 与 `V41_REQUIRED_TABLES` 不变（`runtime.py:922-925`、`runtime.py:971`）。
2. `memory_reflections.state` 没有 CHECK 约束（`memory_schema.py:54-59`），但本设计仍**坚持只用既有 9 个状态值**：`describe()` 的标签表（`reflection.py:512-514`）、`ReflectionManagement.list()` 的 `state NOT IN ('complete','empty')` 过滤（`reflection_management.py:45-46`）、`checkpoints._reflection()` 的分支（`checkpoints.py:85-92`）、`scheduling._settle()` 的分支（`scheduling.py:169-193`）全部按既有词汇判断；新增状态值会让这四处静默漏判。
3. `manifest_json` 的未知键安全：`describe()` 只读取它显式列出的键（`reflection.py:511-528`），`repair_material()` 只读 `rejected/issues/raw_output`（`reflection_recovery.py:133-142`）。老代码遇到含 `compaction` 键的 manifest 不会报错。
4. 备份/恢复只校验必需表与 `schema_version`（`storage/backup.py:93`、`:169`、`:328`），版本不变则既有 bundle 与恢复路径不受影响。

### 5.2 何时才需要新表与 v42

只有下列需求同时成立时才值得升版：

- 需要「压实候选」独立审计（驳回也要留痕，且不能被 `discard_pending` 把 `proposal_json` 置空——`writer.py:243` 正是这么做的）；
- 需要按族指纹快速跳过未变族，而不想每轮解码 `manifest_json`；
- 需要 `view_token` 式 CAS（对照群安全命中的做法：`group/management.py:71-73`、`:246-247`）。

若决定升版，改动清单（照抄 v40→v41 模板）：

| 落点 | 内容 |
| --- | --- |
| 新文件 `companion_v2/storage/compaction_schema.py` | `COMPACTION_STATEMENTS` / `COMPACTION_TABLES`，形态对照 `storage/group_safety_schema.py:1-21` |
| `storage/schema.py`（在 `:1586` 之后追加） | `V42_MIGRATION_STATEMENTS`、`V42_REQUIRED_TABLES`、`V42_SCHEMA_STATEMENTS`、`SCHEMA_VERSION_V42`、`MIGRATION_V41_TO_V42_ID`、`MIGRATION_V41_TO_V42_FINGERPRINT`，并同步 `REQUIRED_TABLES` / `SCHEMA_STATEMENTS` / `SCHEMA_VERSION` |
| `storage/runtime.py` | 新增 `_migrate_v41_to_v42()`（对照 `runtime.py:968-979`）与 `_validate_v41_migration_record()`（对照 `runtime.py:981-986`），并接入 `runtime.py:915-966` 的打开链与校验循环 |
| `tests/execution_support.py` | 增加 `remove_v42` 回退夹具（既有 `remove_v38` 先例见 `docs/CORE_SELF_REVIEW_20260926.md:64`） |
| 备份 | `storage/backup.py` 的版本断言会自动跟上；需在迁移测试中覆盖「非空库 v41→v42 保留 + 失败回滚」 |

拟议新表（仅在升版时使用，字段名仅供评审）：

`memory_compaction_candidates(candidate_id PK, owner_key, batch_id, family_key, stage, action, payload_json, atom_refs_json, decision, decided_by, decided_at, result_json, created_at, updated_at)` + 索引 `(owner_key, family_key, created_at)` 与 `(owner_key, decision, candidate_id)`。

---

## 6. 问题 4：候选与人工审阅

### 6.1 与「只增不改写既有记忆」惯例的兼容方式

现有惯例（逐条核实）：`correct` 产生**新 revision** 并把旧 revision 标 `superseded`（`writer.py:281-289`）；`retract` 把 atom 标 `invalidated` 但保留旧 `source_json`（`writer.py:290-296`）；遗忘也只写墓碑（`writer.py:342-352`）。唯一就地改 `record_json` 的路径是冷归档，且它只追加 `archive` 标记、不动记忆正文（`archive.py:166-171`）。

因此压实落地必须是**操作组合**而不是「覆盖正文」：

| 候选动作 | 落地为 | 语义 |
| --- | --- | --- |
| `rewrite`（同族收敛为一条更准的表述） | 1 条 `correct`（target = 族内规范原子，只改 `object`/`representation`） + N 条 `retract`（吸收掉的冗余原子） | 每个操作各自有 `memory_operations` 回执；历史修订全保留 |
| `retire`（纯冗余，无需改写） | 1 条 `retract` | 停止使用，不删数据 |
| `keep` | 不落地，只记 `receipts["compact:<item_id>"] = {"state":"skipped"}` | 「允许不修改」（`reflection.py:34-36` 已声明） |
| `rekey`（跨族合并，需改 `predicate`/`subject`/`qualifiers`） | **第一期不做** | `correct` 明确禁止改身份字段（`writer.py:258-260`），跨族合并只能是人工的 `add` + `retract` |

**幂等**：S3 落地前先查 `receipts_json.items` 是否已有 `compact:<item_id>`，有则跳过（同 `reflection.py:437-442` 的写法）。

### 6.2 审阅动作与状态机

```
proposed ──accept──▶ adopted ──revert──▶ reverted
   │                    ▲
   ├──reject──▶ rejected│
   └──withdraw─▶ withdrawn
```

| 状态 | 产生方式 | 存储表现 | 依据 |
| --- | --- | --- | --- |
| `proposed` | S3 以 `defer_until_boundary=True` 提交普通提议 | `memory_operations.state='pending'`，`proposal_json` 有值 | `writer.py:152`、`writer.py:210-219` |
| `adopted` | 审阅者采纳 → `commit_pending()` | `state ∈ {persisted, skipped}`；`result_json` 含 `atom_id`/`revision` | `writer.py:177-192`、`writer.py:300-305` |
| `rejected` | 审阅者驳回 → `discard_pending()` | `state='discarded'`，**`proposal_json` 被置空** | `writer.py:231-245` |
| `withdrawn` | 模型在后续批次的 `pending_decisions` 里给 `discard` | 同上（复用 `pending_decisions` 通道） | `reflection_output.py:42-44`、`reflection.py:432-448` |
| `reverted`（撤回已采纳） | 审阅者对已采纳结果提交**反向新操作**：冗余原子重新 `add`、改写原子 `correct` 回原表述 | 新增 `memory_operations` 行；旧回执保留 | `writer.py:281-296` 的纯追加语义 |

**关键设计取舍（明确写下）**：

- **不新增「撤回」专用状态**。理由：`discard_pending` 会把 `proposal_json` 置空（`writer.py:243`），因此「驳回过的候选」除了 `result_json` 之外不留正文；如果要在后续批次里避免反复提出同一候选，必须靠 §5.1 的 `runtime_metadata` 族指纹拒绝标记，而不是靠 `memory_operations`。
- **`auto_low_risk` 模式的边界**：只允许 `retire` 且满足全部条件才自动采纳——同族原子全部 `attribution != "user"`、`retention == 'durable'`、`context_mode == 'relevant'`、无 `memory_guards` 命中、且族内没有任何原子在本批被 S1 触碰。其余一律停在 `proposed`。
- **`rejected` 的复用预防**：族指纹 `digest([family_key, 排序后的 (atom_id, revision)])` 写入 `runtime_metadata.memory.compaction.v1:<owner_key>.rejected[]`（有界，例如最多 64 条，超出丢最旧）。指纹变化（原子有新增/修订）即视为新候选，允许再提。

### 6.3 审阅入口（复用既有宿主与页面）

- 服务层：`MemoryManagement.list/revisions/command`（`memory/management.py:57-76`、`:170-186`、`:213-275`）已覆盖读取、修订历史与 pin/correct/retract/forget。
- 反思层：`ReflectionManagement.list/prepare_retry/enqueue`（`reflection_management.py:27-51`、`:53-64`、`:70-82`）。
- 路由层：`astrbot_host/memory_api.py:26-44` 的既有 18 条路由；最小改造是让 `GET /reflections` 的 `describe()` 输出里多一个 `compaction` 摘要块（`reflection.py:511-528` 已是自由字典），不新增路由即可让页面读取。
- 页面：`pages/陪伴小屋/memory-page.js:227` 的「整理与修复」工作区已经渲染 `receipts`、`unresolved_items`、`issues`（数据来自 `reflection.py:515-522`）；压实候选项可作为该工作区的一个子列表呈现，第二期再考虑独立分区。

---

## 7. 问题 5：与日记链的关系

### 7.1 互不干扰的四条硬边界

| # | 边界 | 代码依据 |
| --- | --- | --- |
| 1 | 日记/梦境正文不发布为事实 Source；压实**不读** `role_journals` | 切片明文「不会将其发布成事实 Source」（`docs/CORE_ROLE_JOURNAL_SLICE.md:14`）；写作写 `role_journals`（`journal/writing.py:367-369`），与 `MemoryWriter` 无交集 |
| 2 | 压实**不写**任何日记/梦境行；唯一写路径是 `MemoryWriter.submit` | `writer.py:135-160` |
| 3 | 日记链**不读** `memory_atoms`；`recent_journal` 只来自 `role_journals` 的正文版本 | `journal/writing.py:103-123`、`writing.py:308-316`、`journal/prompts.py:106` |
| 4 | 派生材料（摘要/碎片/连续性）自称「主观书写的索引，不是事实记忆」，且不得升级为事实 | `journal/prompts.py:46-55`；对照写入器禁止派生证据自我认证（`writer.py:103-104`） |

第 4 条落到规则上是：**压实候选引用的每条证据，其 `source.owner` 不得以 `memory.` 开头**（`writer.py:103-104`），因此经历视图（`memory_views`，`experiences.py:92-99`）与任何摘要都不可能成为「重写事实」的依据。

### 7.2 是否共享时点

**不共享**（理由见 §4.4）。补充两条与日记链直接相关的观察：

- 日记的默认时点是 `role.life.diary_time = "23:50"`（`life/configuration.py:13`），与反思默认 `memory.reflection_time = "23:50"`（`memory/configuration.py:28`）**恰好重合**。这不是错误，但会在同一分钟同时占用后台名额（`scheduling.py:118-121`、`journal/scheduling.py:80-81`）。设计上不做耦合，实施时建议在页面或文档里提示「同一时刻会串行排队」。
- 梦境时点由**睡眠完成事件**决定，而不是任何时钟（`life/runtime.py:292-294`、`life/runtime.py:167-170`）。因此「梦境时段」在 V2 已经存在，只是它属于 `role.life` 的模拟身体时钟，与记忆治理无关。

### 7.3 T17 识屏材料的落位

识屏材料按 T17 已定的方向融合进日记链（`docs/V2_GAP_CLOSING_TASKS_20260927.md:67`、`:115`、`:151`）：采集器已把 `screen` 与 activities/artifacts/readings/conversations 并列读取（`journal/collection.py:78-88`），素材语义枚举也已固定（`journal/materials.py:14-22`）。

识屏侧的准入是**用户显式标记**：`ScreenJournalMaterialProducer.for_day()` 只取 `screen_feedback_anchors.feedback_kind = 'journal'` 的行，逐条复核来源 scope、日期与当前 `role.journal.write` 授权，并把它落成 `MaterialKind.REFLECTION`（`companion_v2/screen/journal_materials.py:14-22`、`:33-44`、`:56-68`），文案自带「模型解读，不等同于屏幕原文」（`screen/journal_materials.py:64`）。

本设计**不改变**这条链，也不让识屏材料进入 `memory.compact`：识屏是**素材**（主观书写输入，且是模型解读而非原件），不是**已沉淀事实**。若将来要让识屏材料参与事实抽取，应走 S1 的来源选择（`reflection_selection.py:58-110`）而不是 S2 压实。

---

## 8. 问题 6：群记忆边界

### 8.1 结论：第一期不纳入

群侧整理**已经**由另一条链承担，且语义与私人压实冲突：

| 冲突点 | 依据 |
| --- | --- |
| 群记忆不是事实原子，而是成员陈述视图 | `group/service.py:17`、`group/service.py:80-100`、`memory_schema.py:48-53` |
| 只有原发言者本人能修订/撤回自己的陈述 | `group/service.py:136-140`、`group/service.py:112-119` |
| 明确禁止把单人说法提升为全群共识；相反观点分别归因 | `docs/CORE_GROUP_MEMORY_20260924.md:21`、`docs/CORE_GROUP_MEMORY_20260924.md:34` |
| 群 owner 不含成员、跨成员共享，合并会制造「谁说的」归属问题 | `group/access.py:14-24` |
| 群周期整理已存在（摘要型，非事实型，且自带过期） | `group/episodes.py:85-98`、`group/episodes.py:162-173`、`group/episodes.py:189-202` |
| 群成员风控已按「规则命中 + 每日反思阶段统一判断」落地，反思批次只把命中当证据 | `docs/V2_GAP_CLOSING_TASKS_20260927.md:81`、`reflection.py:291-322`、`group/hits.py:3-5` |

### 8.2 本设计在群侧的确切边界

1. **S2 对群 scope 硬关闭**：`context.scope.kind is ScopeKind.GROUP` 时跳过 S2。`reflection.py:291` 已经有同一判据的分支，实施时复用即可。
2. **S1 不变**：群批次仍按现状抽取/提交（现有实现已支持群 scope 的安全命中材料），本设计不扩大其写入面。
3. **不允许跨群/跨成员聚合**：`group_owner_key()` 含群号与原生 session（`group/access.py:22-24`），压实的族划分完全在 `owner_key` 内进行；群 owner 的键空间与私人 owner 不同（`models.py:143-146` 对比 `group/access.py:22-24`），因此即使将来开放也不会互相污染。
4. **不建成员画像**：`memory/person/` 已承担相识卡，且约定 `memory/` 与 `memory/group` 不得 import 它（`docs/REPOSITORY_LAYOUT.md:97`）；压实不得产出任何按成员归因的聚合结论。
5. **第二期可选方向**（明确推迟，不在本期实现）：面向群管理员提供「陈述收敛」审阅——只允许**同一作者同一 `fact_key`** 的自我重复整理，且落地只能走 `GroupMemoryManagement.retract()` 的既有路径（`group/management.py:228-282`），保留管理员操作回执与 `attribution="administrator_action"`（`group/management.py:273-276`）。

---

## 9. 问题 7：不可碰清单（确定性规则）

以下规则全部是布尔判定，实施时应当放在一个纯函数里并被 S2 选族与 S3 落地各调用一次（两次都要查，因为中间可能有人改了数据）。

**A. 批次级前置**

| # | 规则 | 依据 |
| --- | --- | --- |
| A1 | `context.scope.kind is ScopeKind.GROUP` → 全局跳过 | `group/access.py:31-33`、`reflection.py:291` |
| A2 | `memory.compaction_enabled == False` → 跳过 | 新字段（§4.3） |
| A3 | 距上次成功压实 < `compaction_min_interval_hours` → 跳过 | 新字段 + `runtime_metadata` 游标 |
| A4 | 批次自身不在 `complete`/`empty` → 跳过 | `reflection.py:221-223` |

**B. 原子级排除（任一条命中即从族中剔除；族内一旦有原子不可碰，整族跳过）**

| # | 规则 | 依据 |
| --- | --- | --- |
| B1 | owner 不匹配 → `memory_unavailable` | `writer.py:49-52` |
| B2 | `state != 'active'` | `writer.py:55-56` |
| B3 | `record_json.forgotten` 为真 | `writer.py:63-64`；`management.py:191-192` |
| B4 | 已冷归档（`record_json.archive.state == 'archived'`） | `archive.py:79-81`、`archive.py:166-168` |
| B5 | `proposal.retention != 'durable'`（排除 `session`/`short`/`protected`） | `models.py:99`；对照 `archive.py:90-97` 只允许 durable |
| B6 | `proposal.retention == 'session'` 且 `scope != context.scope` | `writer.py:66-68` |
| B7 | `proposal.retention == 'protected'` → 永不自动采纳，只可人工审阅 | `writer.py:100-101`、`writer.py:253-255` |
| B8 | `proposal.context_mode == 'pinned'` → 排除 | `pinned.py:11-35`；pin/unpin 只改 `context_mode`（`management.py:256-263`） |
| B9 | `valid_to` 已过（`at >= valid_to`） | `writer.py:69-70` |
| B10 | `valid_from` 未到（`at < valid_from`） | `writer.py:71-72` |
| B11 | 任一证据读不通（`access.evidence()` 抛错）→ 族整体剔除 | `access.py:87-92`、`writer.py:74-76` |
| B12 | 任一证据 `source.owner` 以 `memory.` 开头（派生记忆） | `writer.py:103-104` |
| B13 | `memory_guards` 命中该 `fact_key` + 任一证据键，且 reason 为 `forgotten`/`retracted` | `writer.py:117-122`；`access.py:49-51` |
| B14 | 由本批 S1 新建或修订的原子（比对 `memory_changes.sequence > manifest.memory_sequence`） | `reflection.py:58`、`reflection_selection.py:159` |
| B15 | 原子更新时间晚于 `now - compaction_min_idle_days` | 新字段；对照 `archive.py:83-107` 的 idle 判据 |

**C. 操作级约束（S3 生成操作时必须满足）**

| # | 规则 | 依据 |
| --- | --- | --- |
| C1 | 只允许 `correct` / `retract` / 不操作；禁止 `add` | `reflection_output.py:30` 允许 add，故必须在 S3 显式禁止（S1 独占 add） |
| C2 | `correct` 必须保持 `(subject, predicate, qualifiers)` 不变，且 namespace 与目标一致 | `writer.py:256-260` |
| C3 | 合并后不得降低 `attribution`，不得改变 `subject` | `writer.py:106-108`、`writer.py:113-114` |
| C4 | 不得引用另一族的原子作 target | `writer.py:258-260` + `models.py:138-140` 的族定义 |
| C5 | 同一 `fact_key` 已有 `state='pending'` 的提议 → 族跳过（避免两个结论并存） | `writer.py:210-219` |
| C6 | 族内不得产生两个活跃的 `single_value=1` 原子 | `memory_schema.py:25` 唯一索引 |
| C7 | 已被驳回且族指纹未变的候选不得重复提出 | §6.2 的拒绝指纹 |
| C8 | 已采纳过的候选（`receipts.items["compact:"+item_id]` 存在）不得重复采纳 | `reflection.py:437-442` |

---

## 10. 问题 8：验收清单（将来实现时覆盖，本稿不实现）

**S2 选族（12 项）**

1. 同 `fact_key` 的 2 条活跃 durable 原子被选入同一族；不同 `fact_key` 不混族。
2. 族内任一原子为 `pinned` 时整族被跳过，另一个正常族仍被处理。
3. `protected` 原子只出现在「待人工审阅」列表，`auto_low_risk` 模式下不被自动采纳。
4. `short` 保留且 `valid_to` 已过期的原子被排除，且不导致整批失败。
5. `session` 保留且 scope 与当前 scope 不同的原子被排除，不抛 `memory_session_mismatch` 到批次层。
6. 已 `forgotten` 的原子被排除，且不泄露其正文到材料。
7. 已 `archived` 的原子被排除；同一族的未归档成员不受影响。
8. 证据来源被撤销（`source_revoked`）的原子使整族剔除，并记入 `unavailable_families`。
9. 证据 `source.owner` 以 `memory.` 开头的原子（派生来源）被排除。
10. `memory_guards` 命中 forgotten 的 `fact_key` 被排除，即使证据本身仍可读。
11. 本批 S1 刚落地的原子（sequence 晚于 `manifest.memory_sequence`）不被 S2 触碰。
12. 族数超过 `compaction_max_families` 时按确定性顺序截断，且重复运行选出同一批。

**S2 模型调用与解析（8 项）**

13. `compaction_enabled=False` 时批次在 S1 后正常 `complete`，不产生任何压实记录。
14. S1 为 `failed`/`partial` 时不启动 S2。
15. S2 输出含 `operation="add"` 时整条候选被拒，其余候选仍可落地。
16. S2 返回非法 JSON / 重复字段 / 非有限数时记 `compaction.issues`，批次状态不受影响。
17. S2 派发后无返回时记 `state="unknown"`，重启后**不重放**该调用。
18. S2 任务 `task_id` 在同一 `(batch_id, round)` 下稳定；重复进入不会第二次派发。
19. S2 材料只含事实与证据，逐字节断言不含 `conversation_inputs` 原文与 `role_journals` 正文。
20. 设置 token 在 S1 与 S2 之间变化时 S2 不启动，且批次仍可用原回执查询。

**S3 落地与幂等（7 项）**

21. `review` 模式下候选只产生 `state='pending'` 的 `memory_operations`，`memory_atoms` 一个字节都不变。
22. 采纳 `rewrite` 后：规范原子 revision +1 且旧 revision 为 `superseded`，被吸收原子为 `invalidated`，`memory_changes` 各写一条。
23. 采纳 `retract` 后：原子 `state='invalidated'`，旧 `source_json` 与 `memory_revisions` 完整保留。
24. 同一 `compact:<item_id>` 重复落地只返回原回执，不产生第二次修订。
25. 驳回后 `state='discarded'` 且 `proposal_json` 为空，`result_json` 仍可查。
26. 采纳过程中证据被撤销 → 操作失败并返回既有错误码，不写半个结果。
27. 撤回（revert）走新增反向操作：新 `memory_operations` 行 + 新修订，历史修订数单调增加。

**审阅与状态机（4 项）**

28. `auto_low_risk` 只对满足 §6.2 全部条件的 `retire` 自动采纳；含 `attribution="user"` 的族必须停在 `pending`。
29. 被驳回的族指纹在原子未变时不再被提出；原子 revision 变化后可以重新提出。
30. 同一族在两个连续批次中不会同时存在两条互相冲突的 `pending` 提议。
31. 页面读取的 `compaction` 摘要与 `receipts`/`unresolved_items` 字段在 `complete` 与 `partial` 两种状态下都结构一致。

**边界与隔离（3 项）**

32. 群 scope 批次完全不进入 S2（断言 `manifest` 无 `compaction` 键）。
33. 压实前后 `role_journals`、`role_journal_derivatives` 的行数与内容哈希不变。
34. 跨 owner 隔离：另一个 owner 的原子、证据、`runtime_metadata` 游标均不可见、不可写。

---

## 11. 风险与未核实项

| 项 | 说明 |
| --- | --- |
| 压实质量 | 现有提示词与 schema 无法保证合并后的表述保持原意；缓解手段是默认 `review` 模式 + 禁止跨族 `rekey`，而不是提高模型自由度 |
| 候选反复提出 | `discard_pending` 会清空 `proposal_json`（`writer.py:243`），所以拒绝记忆只能放在 `runtime_metadata`；该键需要自带条数上限，否则会长期增长 |
| 后台名额竞争 | 反思与日记默认都在 `23:50`（`memory/configuration.py:28`、`life/configuration.py:13`），同刻只会排队（`scheduling.py:118-121`、`journal/scheduling.py:80-81`），不构成正确性问题 |
| `round` 语义 | 「同一批次内压实最多跑几轮」本稿未定；建议首期固定 1 轮，把 `round` 只作为幂等键的一部分预留 |
| 未核实 | `memory.reflection_time` 在页面上是否已按 `time` 输入渲染：`pages/陪伴小屋/memory-page.js:201` 有 `key.endsWith("reflection_time")` 的分支，但渲染产物未逐行核对 |
| 未核实 | `tests/execution_support.py` 中 `remove_vN` 夹具的确切命名与数量（仅在文档 `docs/CORE_SELF_REVIEW_20260926.md:64` 见到引用） |
| 未核实 | V1 `_DAILY_REVIEW_FAILURE_COOLDOWN_SECONDS` 的常量定义行（只核实了使用处 `daily_review.py:1782-1786` 与 30 分钟退避 `daily_review.py:1764`） |

---

## 12. 字段与表清单（汇总）

**新增配置字段（8 项，全部在 `memory` 组，`ApplyMode.IMMEDIATE` + `core_only`，登记位置 `companion_v2/memory/configuration.py:28-31` 之后）**

- `memory.compaction_enabled`（BOOLEAN，默认 `False`）
- `memory.compaction_apply_mode`（TEXT，默认 `"review"`，枚举 `review` / `auto_low_risk`）
- `memory.compaction_min_interval_hours`（INTEGER，默认 `24`，范围 1–720）
- `memory.compaction_min_idle_days`（INTEGER，默认 `14`，范围 0–3650）
- `memory.compaction_min_family_size`（INTEGER，默认 `2`，范围 2–8）
- `memory.compaction_max_families`（INTEGER，默认 `8`，范围 1–32）
- `memory.compaction_max_atoms_per_family`（INTEGER，默认 `8`，范围 2–16）
- `memory.compaction_max_evidence_chars`（INTEGER，默认 `12000`，范围 2000–48000）

**复用（第一期，不改 schema，仍为 v41）**

- `memory_reflections`（`manifest_json.compaction` / `receipts_json.items["compact:*"]` / `result_json`）
- `memory_operations`（`state='pending'` 承载候选，`discarded`/`persisted` 承载决定）
- `runtime_metadata`（键 `memory.compaction.v1:<owner_key>`，含 `last_success_at` / `last_batch_id` / `rejected[]` 族指纹）
- `memory_reflection_jobs`、`memory_schedules`、`memory_reflection_inputs`（完全沿用）

**仅在决定升 v42 时才新增的表（1 张）**

- `memory_compaction_candidates(candidate_id PK, owner_key, batch_id, family_key, stage, action, payload_json, atom_refs_json, decision, decided_by, decided_at, result_json, created_at, updated_at)` + 索引 `(owner_key, family_key, created_at)`、`(owner_key, decision, candidate_id)`

**新增任务种类（1 个）**

- `memory.compact`（`Lane.BACKGROUND`、`SideEffect.LOCAL`、`max_attempts=1`、`concurrency=1`，与 `memory.reflect` 同形，依据 `reflection.py:31`、`reflection.py:47-48`）
