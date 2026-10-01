# V1 → V2 全面提升对比报告（2026-09-28）

> 依据**实际代码**逐项核对产出（不采信任何自评/交接结论）。
> V2 源：`astrbot_plugin_private_companion_v2`；V1 源：`_private_companion_backups/_worktree_pr215_20260909`。
> 每条结论均给出可复核落点（文件 / 行）。**第 9 节为诚实标注的"尚未补齐项"，请勿忽略。**

---

## 0. 总览：一句话结论

V2 相对 V1 的核心提升**不是功能变多，而是把 V1 的"巨型扁平单块"重构成"有边界、有版本、有 Result、无回退通道"的可验证架构**。代价是：**V2 当前代码量与功能覆盖仍小于 V1**（约 1/3 生产行数），大量 v1 能力尚未迁入。

| 总体指标 | V1 | V2 | 变化 |
| --- | --- | --- | --- |
| `.py` 文件总数 | 651 | 912 | +40% |
| 生产代码行数（不含 tests） | 281,595 | 90,898（core 78,115） | **-68%**（功能尚未迁完） |
| 测试代码行数 | 127,927 | 71,385 | -44% |
| **测试 / 生代码行数比** | **0.45** | **0.91** | **≈2.0×** |
| 非测试文件平均行数 | ~1,322 | ~168 | **≈7.9× 下降** |
| 最大的单个文件 | 31,314 行（`page_api.py`） | 1,956 行（`storage/runtime.py`） | **16× 下降** |
| 根目录 `.py` 文件数 | **182** | **1**（仅 `main.py`） | 几乎清零 |
| `main.py` 行数 | 21,355 | 119 | **179× 下降** |
| `FieldDefinition(` 注册数 | 0 | 53（27 个文件） | 从无到有 |
| `_conf_schema.json` | 576,863 B / **742 扁平键** | 22,278 B / **8 分组** | 收敛为结构化 |

> 文件数变多、行数变少：典型的**拆分解耦**特征（单文件上帝类 → 多模块协作）。

---

## 1. 工程结构：从"根目录垃圾堆"到"领域包"

### V1 现状（反面）
插件根目录直接堆了 **182 个 `.py`**，涵盖 `activity_capture.py`、`affect_modulation.py`、`agenda_*.py`、`daily_state.py`、`dreaming.py`、`emotion_*.py`、`migration_*.py`、`proactive*.py`、`qzone_*.py`、`token_budget.py`、`worldbook.py` 等全部业务。仅有 `companion/`、`domains/`、`storage/`、`pages/`、`scripts/` 五个附带代码的子目录。

伴随的是一批**上帝文件**（证据：行数量测）：

| V1 巨型文件 | 行数 |
| --- | --- |
| `page_api.py` | 31,314 |
| `main.py` | 21,355 |
| `proactive_message.py` | 19,523 |
| `daily_state.py` | 18,861 |
| `user_memory.py` | 11,169 |
| `proactive_engine.py` | 10,841 |

### V2 现状
根目录只有 `main.py`（119 行）+ 元数据/配置（`metadata.yaml`、`_conf_schema.json`、`pyproject.toml` 等）。业务全部收进 `companion_v2/<领域>/`，共 **20+ 领域包 / 442 个模块**：

`adapters/ astrbot/` `agenda` `capabilities` `configuration` `conversation/(content,forwards,media,quotes)` `delivery` `diagnostics` `execution` `expression` `foundation` `games` `host` `identity_policy` `integration` `knowledge` `legacy` `library` `memory/(group,person)` `model_gateway` `proactive` `product` `relationships` `role_work/(growth,journal,life,state,timeline)` `screen` `sharing` `sources` `storage`

**最大文件仅 1,956 行**（`companion_v2/storage/runtime.py`）。

### 额外提升：可重载 / 多实例隔离
`main.py` 不只是"变短"，还承担了 V1 没有的工程纪律：

- 启动前自检同名包来源（L31–33）：若 `companion_v2` 已从别的路径加载 → 直接 `RuntimeError`，防止多插件实例串源。
- `sys.path` 由本插件临时注入，`terminate()` 时（L109–119）**移除 `sys.path` 条目并把 `companion_v2*` 模块从 `sys.modules` 弹出**，保证热重载干净、不残留脏模块。

---

## 2. 存储与迁移：从"一次性 JSON→SQLite 切换"到"41 级版本链 + fail-fast 护栏"

### V1
`storage/` 只有 7 个文件；其中 `storage/migration.py` **全文 66 行**，职责仅是「有 SQLite 就用 SQLite，否则把 JSON 数据灌进去」（`migrate_json_to_backend_if_needed`）。**没有 schema 版本概念，没有增量迁移，没有回滚。**（唯一的谨慎点是 L50–54：拒绝用空库覆盖疑似中断迁移的数据。）

### V2
- **显式版本链**：`companion_v2/storage/schema.py` 定义 `SCHEMA_VERSION_V1` … `SCHEMA_VERSION_V41`（L9–48+）。
- **每表一个 schema 模块**：`*_schema.py` 十余个小文件（`memory_schema.py`、`memory_recall_schema.py`、`reflection_schema.py`、`reflection_job_schema.py`、`expression_style_schema.py`、`group_safety_schema.py`、`growth_progress_schema.py`、`media_schema.py`、`reading_archive_schema.py`、`self_review_schema.py`、`state_schema.py`、`audio_schema.py`、`video_schema.py`）。
- **每一步迁移的四级校验**（`companion_v2/storage/runtime.py` L418–480 实证）：
  1. **双向检查**——既缺少目标表即失败，`V(N+1)_REQUIRED_TABLES.difference(VN_REQUIRED_TABLES).intersection(existing_tables)` 出现未来表也失败（防乱序）。
  2. `_validate_table_shapes(...)` 校验列结构。
  3. `_validate_integrity(connection)` 完整性约束。
  4. `_validate_vN_migration_record(...)` 核验迁移记录。
  任一不过 → `raise StorageOpenError("V2 data root has an incomplete vN-to-v(N+1) migration")`，**绝不静默接受半迁移状态**。
- **工程约定**：新增一张表 = 一个新 schema 版本 = 必须配套"回滚到上一版本再重开"的迁移测试（已有实证案例：v40→v41 落地后 `tests/test_expression_style.py` 的 v39 回滚夹具未同步，重开即报 `incomplete v40-to-v41 migration`，已修复）。

---

## 3. 配置治理：从"742 个扁平键"到"8 分组 + 53 处强注册（禁止硬编码）"

| 维度 | V1 | V2 |
| --- | --- | --- |
| 配置载体 | 单一 `_conf_schema.json`，**576,863 B / 742 顶层键** | `_conf_schema.json` **22,278 B / 8 分组** + 代码内注册 |
| `FieldDefinition(` | **0 处**（全仓零命中） | **53 处 / 27 个文件** |
| 定义位置 | 集中在一个巨型 JSON | 分布在各领域 `configuration.py`（capabilities / knowledge / expression / screen / proactive / library / conversation / model_gateway 等） |

V2 的制度性约束（已落 doc 并在多任务上执行）：

1. 可调阈值 / 窗口 / 上下限 / 概率 / 强度 / 间隔 / 档位，**必须**经 `FieldDefinition` 注册；
2. **每条定义必须有真实消费者**，无消费者宁可不登记、记为设计差异（避免"注册了但没人读"的假开关）；
3. 三级继承（安装 / Bot / 角色）+ 单位与概率语义统一。

> **诚实标注（未完成项）**：该铁律尚未 100% 落地——`companion_v2/expression/style_evidence.py` 的 `MAX_SAMPLE_CHARS` / `MIN_SAMPLES` / `MAX_WINDOW_HOURS` 与 `conversation/style_context.py` 的 `MAX_RULES` 仍是硬编码常量。这正是 T28「表达学习配置化」被复核退回待办的根因。见第 9 节。

---

## 4. 错误与"未知"处理：从"try/except + 隐式空值"到类型级 Result

V2 在 `companion_v2/foundation/outcome.py` 定义了 `Outcome[T]`：

```python
@dataclass(frozen=True)
class Outcome(Generic[T]):
    value: T | None = None
    failure: Failure | None = None
    def __post_init__(self):
        if (self.value is None) == (self.failure is None):
            raise ValueError("Outcome requires exactly one of value or failure")
```

**在构造期就强制"值与失败恰好一个"**，从类型层面消灭了 V1 常见的"返回 `{}`/`None` 到底是没数据还是失败"的歧义。`Failure(code, reason)` 是稳定且非敏感的机器可读码，调用侧统一收敛为：

```python
result = await self.staging.load_existing()
if result.failure is not None:
    logger.warning("... %s", result.failure.code)   # main.py L77–79
```

同类语义在全仓复用：如 `agenda_operation_incomplete`、`configuration_operation_incomplete`、`memory_index_unavailable`、`staging_delivery_grant_changed`——**永远诚实报"不确定"，不谎称停止/成功**（对应核销铁律第 8 条）。V1 无等价机制。

---

## 5. 身份 / 授权 / 归属：owner 铁律有代码实体

V2 新建 `companion_v2/identity_policy/`，核心 `directory.py` 的类注释第一句即写明：

> `IdentityDirectory` — **Versioned account links and grants with no identity fallback path.**

即"**没有身份回退通道**"。具体设施：

- `UntrustedIdentityClaim` 把**未经验证的声称**单独建模，与 `ResolvedIdentity` 严格区分；
- 分层模型：`AuthenticatedHostPrincipal` / `AuthorizationTier` / `CapabilityGrant` / `GrantState` / `BindingState`；
- `policy_revision` 版本化 + `snapshot()` / `from_snapshot()`，**支持重启回放**（让品类覆盖可测试的确定性）；
- 配合 `memory/person/*`（个人域）与 `memory/group/*`（群体域，含 `hits.py` 风控记录、`slang.py` 群黑话）实现分工归属。

此外 `main.py` L86–102 建立了**投递边界**：命中 `claims(event)` 后立刻 `event.stop_event()`，禁止 AstrBot 普通回复管线绕过 V2 投递边界；未授权/未受理只记 `failure.code`，不重放。

V1 虽有 `identity_namespace.py`、`private_scope_isolation.py`，但没有 tier / grant / untrusted-claim 的分层实体，也没有等价的投递边界接管。

---

## 6. 领域能力重组实例（同一能力的体量对比）

| 能力域 | V1 形态 | V2 形态 |
| --- | --- | --- |
| 主动消息 | `proactive_message.py` **19,523 行**单文件 | `proactive/service.py` **806** + `proactive/configuration.py` **410** + `models` |
| 主动引擎 | `proactive_engine.py` 10,841 行 | 已并入 `proactive/` 领域（`scheduling` / `configuration` / `service`） |
| 每日状态 | `daily_state.py` **18,861 行** | `role_work/state/*` 拆分（`state/configuration.py` 仅 **125** 行） |
| 用户记忆 | `user_memory.py` **11,169 行** | `memory/` 包约 **50 个模块**：`reflection` 569 / `writer` 413 / `habits` 472 / `archive` 373 / `search` 258 / `subscriptions` 331 / `episodes` 241 / `query` 258 + `recall_*` 系列 + `group/*` + `person/*` |
| 每日反思 | `daily_review.py` 1,715 行 | `memory/reflection.py` 569 + `reflection_jobs/output/selection/recovery` 等专门化模块 |

**V2 新增、V1 无对等的子系统**（已验证存在）：

- `diagnostics/`（service 335 / repairs 198 / models 206）——**修复提案**（repairs）可用于自愈建议，属可观测闭环；
- `memory/stream_store|stream_delivery|stream_consumer|stream_visibility|stream_validation`——事件流式存储与投递；
- `memory/recall_vectors.py`——向量召回；
- `identity_policy/`——身份策略（见 §5）；
- `execution/`（685）、`delivery/history`（投递历史）、`model_gateway/budget`（配额）+ `routing`（路由）；
- `screen/`（识屏）、`games/`（游戏域）、`library/`（资料库域）、`product/`（版本门面）。

---

## 7. 测试强度（密度与异步覆盖）

| 指标 | V1 | V2 |
| --- | --- | --- |
| tests 文件数 | 438 | 371 |
| assert 类出现次数 | 17,705 | 13,796 |
| **异步测试函数** | 1,315 | **1,915**（+46%） |
| 测试 / 生产行数比 | 0.45 | **0.91** |

> 解读：V1 绝对断言数更多是因为代码总量大；但按**生产代码密度**计，V2 测试强度约为 V1 的 **2 倍**，且异步/并发场景覆盖显著更多（流式、事务、并发写入等）。

---

## 8. 管理页面

| 维度 | V1 | V2 |
| --- | --- | --- |
| 页面组织 | `pages/` 仅 2 子目录；`page_api.py` **31,314 行**；`standalone_webui.py` 986 行 | `pages/` **5 组**：陪伴小屋（36 文件 / 991 KB）、关系与权限、关系与记忆、宿主管理、日记与生活（各约 31 KB，3 文件） |
| 单体巨型 API 文件 | 有（31k 行） | 无，按组分拆 |
| 按需/懒加载设计 | 未见 | `pages/陪伴小屋/page-build.json` 含 `workspaces: host/life/relationships/identity` 分组清单，便于分区加载 |

---

## 9. 诚实标注：V2 **尚未**补齐的部分

对比不能只讲好的。以下为本次核对确认的真实差距：

1. **功能覆盖仍显著小于 V1**：V1 生产代码 281,595 行，V2 core 78,115 行（约 **28%**）。缺口清单（`docs/V2_GAP_CLOSING_TASKS_20260927.md`）中 T25（群片段记忆）、T31（私聊片段记忆）、T35（拟人状态强度+每日巡视）等实测**未开工**；T28（表达学习配置化）被复核退回待办。这是"v1 代码：**可用但要按 V2 约束重写**"的架构性债务。
2. **"禁止硬编码"未彻底执行**：`expression/style_evidence.py` 的 `MAX_SAMPLE_CHARS` / `MIN_SAMPLES` / `MAX_WINDOW_HOURS`、`conversation/style_context.py` 的 `MAX_RULES` 仍为硬编码 → 这正是 T28 被复核退回待办的直接根因。
3. **性能预算目前是"规格"而非"已验证"**：首屏 ≤300 KiB、单页 API ≤3 次 / ≤100 KiB、暖态堆增量 ≤10 MiB、后台不轮询等，仅在 `docs/CONFIGURATION_CONSISTENCY_AND_PANEL_PERFORMANCE.md`（L150 / L155 / L187）有明文规定，**本次全仓扫描未找到 enforcing 的自动化测试**。页面虽有分区/懒加载设计，但陪伴小屋总体资源 991 KB，若无首屏控制机制容易踩线。
4. **V1 部分领域 V2 未接**：`qzone_*`（QQ 空间社交馈送）、`desktop_pet_bridge`（桌面宠物）、`nai_image_bridge`（NovelAI）、`photo_reference_*`（图参考记忆）、`p4_*/p5_*/p6_*`（安全 attestation），已在资产索引中标注为"范围待定/避免误迁移"。

---

## 10. 提升清单（按确定性排序）

| # | 提升点 | 关键证据 |
| --- | --- | --- |
| 1 | 根目录治理：182 个散落 `.py` → 仅 `main.py` | 行数量测；V2 根只有 `main.py` |
| 2 | 上帝文件拆解：最大文件 31,314 → 1,956 行；平均模块 1,322 → 168 行 | §1 表格 |
| 3 | `main.py` 从 21,355 行巨物 → 119 行纯入口，且具备多实例隔离 + 卸载清理 | `main.py` L31–33、L109–119 |
| 4 | 存储：66 行一次性切换 → V1…V41 版本链 + 每步四级校验 + fail-fast | `storage/schema.py` L9–48；`storage/runtime.py` L418–480 |
| 5 | 配置：742 扁平键巨型 JSON → 8 分组 + 53 处 `FieldDefinition` 强注册 | `_conf_schema.json` 量测 + grep |
| 6 | 错误语义：`Outcome[T]` 强制"值/失败恰好一个"，统一 `failure.code` | `foundation/outcome.py` L20–48 |
| 7 | 身份：显式 tier/grant/untrusted-claim 模型，"no identity fallback path" | `identity_policy/directory.py` L26–58 |
| 8 | 投递边界：`claims()` + `event.stop_event()` 禁止绕过 | `main.py` L92–102 |
| 9 | 测试密度翻倍（0.45 → 0.91），异步用例 1,315 → 1,915 | §7 |
| 10 | 新增可观测/自愈、流式记忆、向量召回、识屏、游戏、资料库等子系统 | §6 存在性验证 |

---

*核对口径：仅采信可复跑量测与源码；未运行的 (`performance`) 性能项标注为"规格未验证"。本次分析所用临时脚本已清理，未污染插件根目录。*
