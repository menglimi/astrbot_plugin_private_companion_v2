# C10/C11 切片记录：表达习惯学习、记忆冷归档与可移植导入导出

日期：2026-09-26
范围：`docs/V1_V2_FUNCTIONAL_GAP_AUDIT_20260925.md` 中 C10、C11 两项
状态：源码接线完成，**未经运行验证**（沙箱工作区未能启动）

## 一、共同范式

两项都沿 C09 已确立的四层落地，不引入新范式：

1. **证据目录**（`*_evidence.py`）：只从角色自己可观察的材料取证据，向模型暴露不透明句柄而非内部 ID。
2. **后台生产者**（`*_service.py`）：`prepare` / `validate` / `run` / `generate` / `advance` / `cancel_running` / `active_handles` / `close`，用角色级游标节流，候选落库为待审状态。
3. **仪表盘审阅**（`*_management.py`）：认证操作者接受/拒绝/采纳，接受前只复核该条实际引用的证据。
4. **上下文注入**（`conversation/*_context.py`）：封存快照，注入前逐条复查有效期与来源，失效条目静默跳过、不阻断回复。

## 二、C10 表达与说话习惯学习

### 证据（`companion_v2/expression/style_evidence.py`）

`ExpressionSampleCatalog` 从已确认送达的回复文本取样，`window_hours` 默认 168（7 天），上限 720，`MIN_SAMPLES = 4`，单样本截断 800 字符，总样本上限 24 条。与 C09 证据目录相同的延迟 `attach(messages)` 契约，用于打断消息层与目录之间的循环依赖。`role_owner(context)` 是目录自己的角色归属解析，不复用回执读取器的内部方法。

### 生产（`companion_v2/expression/style_service.py`）

`KIND = "role.expression.learn"`，`scan_seconds = 86400`（每天最多一次），`page_size = 16`。模型输出受 `parse_output` 严格校验：维度必须落在 `sentence_rhythm / emoji / punctuation / directness / diction / formatting / other` 之内，evidence 句柄必须真实存在、不重复、非空，confidence 限 0..1，禁止多余字段。`ValueError` 统一桥接为 `TaskError("expression_learn_output_invalid")`，避免契约错误逃逸为 500。

### 审阅（`companion_v2/expression/style_management.py`）

候选状态 `pending → adopted / rejected → retired`。`adopt` / `reject` / `retire` 三个动作，`_basis` 只重新检查该条引用的样本句柄，样本来源撤回后该条静默失效而不连带阻塞其他条目。

### 注入（`companion_v2/conversation/style_context.py`）

`SNAPSHOT_VERSION = "conversation.expression-style-context.v1"`，最多 8 条规则、4000 字符。指令明确两点：以本轮对话为准，不得覆盖当前话题；学到的形式偏好"不能当作指令"执行。不注入任何未采纳候选。

### 存储

内部 schema **v39 → v40**，新增 `expression_style_runs` 与 `expression_style_signals`（维度 CHECK 约束如上，状态 `pending/adopted/rejected/retired`），指纹 `MIGRATION_V39_TO_V40_ID`。

### 测试

`tests/test_expression_style.py`：模型输出契约（11 项，含维度白名单、句柄校验、置信度边界、多余字段、非法 JSON、指令文本断言）、样本目录（窗口边界、未挂载 owner、外部 runtime 拒绝、material_hash 顺序敏感性、字符计数）、快照校验（外部 context、ready 带 reason、unavailable 带 references、重复引用、超预算、naive 时间戳）、存储升级（部分迁移必须被拒绝）。

## 三、C11 记忆冷归档与可移植导入导出

### 归档（`companion_v2/memory/archive.py`）

冷归档是**逻辑移动**，不擦除任何内容：`preview` 列出长期闲置的 durable 事实，`commit` 用 `archive_token` 保证预览与确认之间集合未变（token 覆盖 owner、操作者、闲置窗口与每条 `(atom_id, revision, state)`），`restore` 可逆。

关键设计点：`memory_atoms` **没有 retention 列**——保留策略存在 `record_json` 的 `proposal` 内。归档判定必须经 `codec.proposal(record["proposal"]).retention` 读取，且对缺失/畸形 proposal 容错跳过而非抛出。只有 durable 记录可归档；session、short、protected 由各自原策略持有。

### 导出

永远限定单个私聊关系与单个角色。读取不到的记录（来源已失效）作为 tombstone 导出，而不是当作角色从未拥有的事实。bundle 上限 512 条原子 / 4 MiB。

### 导入

导入**绝不自动**：先 `preview_import` 展示落地内容，再由显式确认写入。

导入路径不是裸 INSERT。`Proposal.__post_init__` 要求非 `no_op` 操作必须有 evidence，且 `MemoryAccess.evidence()` 会重新校验 `content_hash` 与 `span_hash`——没有已发布来源的原子记录会被后续每次读取静默丢弃。因此每个导入原子都会：

1. 重建 `Proposal`（`attribution` 固定为 `observed`，因为 bundle 内容不是角色本轮亲耳听到的；用 `user` 会触发 `human_message` 证据要求而永远校验失败）；
2. 以 `BUNDLE_OWNER` 为 owner 发布一条真实来源，payload 为 `representation`；
3. 构造指向该来源的 evidence span（`end = max(len(payload), 1)`，兼容空内容，满足 `end > start`）；
4. 写满 `memory_atoms` 全部 12 列，并补齐 `memory_revisions` 与 `memory_changes`。

`fact_key` 由 `proposal.fact_key` 属性计算，与 writer 保持一致。`document["imported"]` 记录 `bundle_format`、`bundle_hash`、时间与操作者，使导入事实与角色直接观察到的事实始终可区分。

### 宿主

`astrbot_host/memory_api.py` 新增六条路由（`archive/preview`、`archive`、`archive/restore`、`export`、`import/preview`、`import`）。归档操作收 `context` 而非 `target`，因此走独立的 `_run_archive`，复用同一套身份校验与 `_control_lock`；`multi_api` 按角色自动派生这些路由，无需额外注册。

### 测试

`tests/test_memory_archive.py`：闲置天数边界、归档资格（只选闲置 durable、跳过近期/非 durable/已遗忘/已归档/naive 时间戳、proposal 缺失或畸形时跳过、retention 只从 proposal 读、state 透传）、token 稳定性与闲置窗口敏感性、bundle 校验（格式、缺失 atoms、空/超限、畸形原子、顺序保留）。

## 四、未完成与风险

- **全部改动未经运行验证**：本会话隔离 Linux 环境始终启动失败，编译、unittest 与回归均未执行。已改为逐文件静态核对真实 schema 列数、`Proposal`/`Evidence` 校验规则与来源发布契约。
- 导入共享同一 `content_hash` 的两条原子（`representation` 相同）未做去重，预期无害（`source_id` 用 `atom_id` 区分），但需实测确认。
- 归档与导入均只覆盖私聊；群聊集体记忆走既有的 `group_memory` 通道，未纳入本批。
- 小屋页面尚未接入这两项的审阅界面。

## 五、本地验证命令

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
cd 'C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest `
  tests.test_memory_archive tests.test_self_review tests.test_expression_style -q
```

存储迁移回归（覆盖 v38→v39→v40 链路）：

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest `
  tests.test_storage_upgrade tests.test_proactive_balance_events tests.test_proactive_news_events -q
```
