# 框架 × 设计稿 出入审计（2026-09-29）

对象：本插件本体（`main.py` / `astrbot_host/` / `companion_v2/` / `pages/陪伴小屋/` / `tools/`）与其**框架级设计稿**。
方法：逐条抽设计稿里**可验证的声明** → 到代码里找对应实现（脚本 / grep / import 探针 / 实跑定向测试）→ 三值判定：**一致** / **文档滞后**（代码已做到、文档没跟上）/ **规则与实现冲突**（文档说不能做、代码在做）。
范围：本文只记录与更正，**不改业务代码**。

设计稿清单（本文核对的）：
`AGENTS.md`、`docs/REPOSITORY_LAYOUT.md`、`docs/REGISTRATION_UNIFICATION_20260925.md`、`docs/NAV_SEGMENT_PLAN_20260925.md`、`docs/SIDEBAR_NAV_AUDIT_20260925.md`、`docs/PAGE_DISPLAY_AND_CONFIG_DESIGN_20260928.md`（职责与归属）、`docs/PAGE_DISPLAY_AND_CONFIG_DESIGN_20260929.md`（V1 结构与呈现层）、`docs/V2_NATIVE_SURFACE_AUDIT_20260927.md`、`docs/V2_BUILD_PROGRESS_PERCENT_20260927.md`、`docs/V2_GAP_CLOSING_TASKS_20260927.md`、`docs/DESIGN_VS_IMPLEMENTATION_AUDIT_20260927.md`、`docs/FRAMEWORK_PROGRESS_AUDIT_20260924.md`、`docs/DESIGN_CONFORMANCE_AUDIT_20260921.md`、`pages/陪伴小屋/{STRUCTURE.md,V1_TO_V2_UI_AUDIT.md,V1_PAGE_INVENTORY.json}`，以及字面意义上的"设计稿"：`astrbot_plugin_content_companion/design-previews/companion-v2/`。

分工：三路并行只读复核（配置与任务表 / 09-27 偏差条目 / 早期框架审计）+ 本人独立复核框架不变量与页面接线，并复跑引用的命令。
沙箱说明：`TemporaryDirectory` 在本沙箱内建出的 0700 目录不可写，直接用 AstrBot Python 跑测试会在 `setUp` 报 `PermissionError`；本人用 `build/tmp/run_focused_suite.py`（只放宽该 mode）实跑，并行复核因未用该 runner 而以源码为证据。本文凡标〔实跑〕的都是真实执行结果。

---

## 一、结论摘要

| 级 | 出入 | 证据 | 影响 |
| --- | --- | --- | --- |
| **P0** | **核心隔离门是红的**：`companion_v2/legacy/migration.py` 直接做文件与 SQLite I/O（`read_text` / `rglob` / `sqlite3.connect`），未登记进 `APPROVED_IO_BY_MODULE` | `companion_v2/foundation/isolation.py:81-84`「Any later exception needs a named policy」；`legacy/migration.py:159,171,188`；`tests/test_isolation.py`〔实跑〕**1 项失败** | 静态隔离闸门失效，G0 关卡不再可信 |
| **P0** | **三份设计稿与 legacy 迁移实现冲突** | `AGENTS.md:13`「不要读取、迁移或修改 V1 用户数据」；`docs/REPOSITORY_LAYOUT.md:105`「`legacy/` 保存兼容合同及映射定义，**不自动读取**」；而实现是**主动定位并只读 V1 数据再写入 V2**（`_conf_schema.json` 的 `legacy` 段、`astrbot_host/legacy_api.py` 三条路由、`companion_v2/legacy/migration.py` 发现→试算→执行） | 规则与产品功能互相打脸：要么补命名策略与例外条款，要么把读取移出核心 |
| **P1** | **「清除已保存的生图密钥」只实现了一半** | `pages/陪伴小屋/models-page.js:718-731` 只遍历 draft 里已存在的键，而提供方 `image_native_configuration.py:24` 从 payload 剔除 `api_key`（只留 `api_key_set`）→ 勾选「清除」(`:775-781` 写 `__clear_key`) 永远进不到 `:721-727` 的清除分支；`tests/`、`tools/` 对该控件零覆盖 | 管理员勾选并保存后密钥仍在（除非同时往密钥框敲入任意字符）——B11 的用户可见目标未达成 |
| **P1** | **主动识屏在页面上无法开启** | 字段 `proactive.contact.screen_glance_enabled`（`companion_v2/proactive/configuration.py:232`，默认 `False`）不在 `pages/陪伴小屋/state-contact.js` 的硬编码字段表，`config-editor.js` 的分组表与 `astrbot_host/configuration_api.py:31-40` 的 `SECTIONS` 都不含 `proactive.contact`；`docs/V2_CONFIG_SURFACE_20260928.csv` 记 `missing` | 晚安识屏/沉默窥屏是 PROACTIVE 锚点的唯一生产者，链已接通但实际不可达 |
| **P1** | **群公共记忆：后端已通、前端零消费点** | `astrbot_host/group_memory_api.py:49`（6 条路由）+ `page_api.py:58`、`multi_api.py:84` 下发 + `tests/test_group_memory_host_api.py`；`pages/` 全域 grep `group_memory_api\|group-memory\|群公共记忆` **0 命中** | V1「群聊」页的核心管理能力在唯一公开页上没有入口 |
| **P1** | **页面结构在本轮审计期间被重构，两份页面设计稿随即失去基线**：分区编号（A1/B2/C3…）与「已接入/部分接入/待接入」状态点**已不再进 DOM**（`app.js:898-925` 的注释自述："那是给开发者看的实现进度表，不是用户要的东西"），空分区整块跳过，`boundaryCard` 只剩 **1 处**调用 | 实测：`pages/陪伴小屋/app.js` 里 `'[ABCDEL]\d'` 字面量 **0 处**；`consoleSection([title,summary,body])`、`consoleSections` 只渲染有内容块 | `docs/PAGE_DISPLAY_AND_CONFIG_DESIGN_20260928.md`（§1.1 分区锚点、R5 编号规则）与 `_20260929.md` 的整章结构说明、`docs/V2_BUILD_PROGRESS_PERCENT_20260927.md:33` 的验收清单 R 组（"6 个能力页、5 个专题页"）都按旧骨架写，需同步改写 |
| P2 | 契约面数字全面滞后（见 §3） | 路由 **89** 条 / 19 模块（文档写 63 / 14）；`TaskRegistration(TaskDefinition(...))` **19 处**（文档写 14 种）；schema **v44**（文档写 v41，线上库仍 v40）；配置 **604 字段 / 38 组**（账本 CSV 602 行，`audit_v2_native_surface.py` 仍打印 15 组 / 422 字段） | 排期与验收基准错位 |
| P2 | **收口/任务文档的「页面接入待第②阶段」注记与 owed 计数已过期** | 104 条逐条对账：一致 70 / **文档滞后 28** / 声明未落实 1 / 未找到证据 5；典型是 T01/T06/T09/T15/T28/T53 的控件其实已挂载，而 `V1_V2_CONFIG_VERIFIED_20260927.csv` 的 owed 实为 **29 行**（文档反复引用 114 行） | 按旧注记排期会重复安排已完成的活 |
| P2 | 导航设计稿有四份、没有现行版本链 | `NAV_PAGES_V4_20260925.md`、`NAV_SEGMENT_PLAN_20260925.md`（自称替代第二版）、`NAV_LEAN_PLAN_20260925.md`、`SIDEBAR_NAV_AUDIT_20260925.md`；实现是 `app.js` 的 4 组 17 项 | 读者无法判断哪份有效 |
| P2 | 字面设计稿（Content 预览）严重落后 | 与 `pages/陪伴小屋/` 同名 31 个文件中**仅 8 个逐字节一致**、23 个不同；规范源另有 **24 个文件预览里根本没有**（config-editor / workbench-page / setup-guide / perception-native-page / backup-page / tokens 等） | 以预览为设计基线会漏掉整个配置工作台层 |

其它已确认**一致**的硬约束：根目录 Python 文件只有 `main.py`；`metadata.yaml:name` ＝ 目录名 ＝ `PLUGIN_NAME` ＝ `@register` 实参；`companion_v2` 不 import `astrbot_host`；只有 `pages/陪伴小屋` 带 `index.html`（其余四个目录只有 `workspace.html`，符合"唯一公开页"）；`staging.enabled` 默认 `false`、`delivery_mode` 默认 `preview`，加载路径只调 `load_existing()`，不自动初始化/发送。

---

## 二、框架层：注册、目录、隔离、依赖

| # | 设计稿声明（出处） | 代码现状 | 判定 |
| --- | --- | --- | --- |
| 1 | 根目录只保留 `main.py`，其余按领域入包（`AGENTS.md`） | `ROOT/*.py` ＝ `['main.py']`〔实跑〕 | 一致 |
| 2 | 目录名、`metadata.name`、`PLUGIN_NAME`、注册装饰器四处同名（`AGENTS.md`、`REGISTRATION_UNIFICATION`） | 均为 `astrbot_plugin_private_companion_v2`；`@register(PLUGIN_NAME, …)` | 一致 |
| 3 | 唯一公开 Dashboard Page 为「陪伴小屋」 | `pages/` 下 5 个目录，只有 `陪伴小屋/index.html`；其余四个是 `workspace.html` + `app.js` + `style.css`，由 `tools/sync_framework_page.py` 嵌入 | 一致 |
| 4 | 核心不得导入 `astrbot` / `astrbot_host`（`REPOSITORY_LAYOUT.md:141`） | 反向 import 扫描：无 | 一致 |
| 5 | 核心不做文件/数据库 I/O；新增例外须登记命名策略（`isolation.py:81-84`） | `companion_v2/legacy/migration.py` 未登记 → `tests/test_isolation.py` 红〔实跑〕 | **规则与实现冲突（P0）** |
| 6 | `legacy/` 只保存兼容合同与映射定义，不自动读取（`REPOSITORY_LAYOUT.md:105`） | 同模块主动 rglob/read_text/connect，且 `_conf_schema.json.legacy.v1_root` 留空时**自动在同级目录寻找 V1** | **规则与实现冲突（P0）** |
| 7 | V2 使用独立数据根；不读/迁/改 V1 数据（`AGENTS.md:13`） | 迁移是**只读 V1、单向写 V2**、默认不自动执行（`allow_auto_apply` 默认 false），但确实读取 V1 数据 | **需用户裁决**：改规则或改实现 |
| 8 | 可加载副本、备份、worktree 放在一级扫描目录之外（`AGENTS.md`） | `_private_companion_backups/`（同级）根层无 `main.py`/`metadata.yaml`，不是可加载插件 | 一致（仅登记） |
| 9 | 根目录不保存运行产物（`AGENTS.md`、`REPOSITORY_LAYOUT.md:149`） | 根下存在 `.p4-tmp/`(75)、`.verify-shards/`(83)、`build/tmp/*`(数百个 0700 临时目录)、空的 `probe-vtacdwe2/`、`__pycache__/`、`.pytest_cache/` | **文档滞后/卫生问题**：多为工具与并行窗口产物，建议清理并加 `.gitignore` 之外的物理清理纪律 |
| 10 | 交付包/发布工件可复现（`REGISTRATION_UNIFICATION` 引用 `verified/`、`snapshot/` 校验文件） | 插件目录下无 `verified/`、`snapshot/`；`data/dist` 是 AstrBot 前端 dist | **文档滞后**（切片工件属临时工作区，已不可复现，建议标注） |

---

## 三、契约面：路由、任务、schema、配置

| # | 设计稿声明 | 现状（实测） | 判定 |
| --- | --- | --- | --- |
| 1 | 宿主 API 路由 63 条 / 14 个模块（`V2_NATIVE_SURFACE_AUDIT_20260927.md:13`） | **89 条 / 19 个模块**（`acquaintance 1, backup 6, configuration 2, group_memory 6, group_reply 3, growth 4, integration 1, legacy 3, life 2, memory 19, model 15, native_perception 3, page 1, perception 2, relationships 2, reply 6, semantic 2, setup 9, state 2`）＋ `web_api` 的 staging 控制面 11 条 | 文档滞后（+26 条、+5 模块） |
| 2 | 后台任务种类 14（同上:14） | `TaskRegistration(TaskDefinition(...))` **19 处**（另 `delivery/service.py:92` 按 kind 展开多条） | 文档滞后 |
| 3 | 存储 schema `v41`（`MEMORY_REFLECTION_DREAM_FUSION_DESIGN_20260927.md:95,331`、`V2_NATIVE_SURFACE_AUDIT_20260927.md:15`） | 代码 `SCHEMA_VERSION` 最终为 **v44**（`storage/schema.py:1625`，v41→v44 四条迁移与指纹齐备）；**线上运行档仍是 v40**（`runtime_metadata.schema_version`） | 文档滞后；线上库下次打开要连做 4 次迁移（机制齐备，建议留一份快照） |
| 4 | 已注册配置组 15 / 字段 364（同上:11-12） | **38 组 / 604 字段**（`tools/build_v2_inventory.py` 的发现式统计，skipped 0）；`tools/audit_v2_native_surface.py` 仍打印 **15 组 / 422 字段** | 文档与**工具**双重滞后 |
| 5 | 页面可写分区 15 个（`audit_page_config_coverage.py` 输出） | `SECTIONS` **16 个**（新增 `role.growth.skills`）＋ `SPEC` 16 ＋ 实际挂载 16，三方对账现已全绿〔实跑〕 | 工具滞后 1 个分区；`busy_gate` 空档已被另一窗口补上 |
| 6 | 配置组 → 路由映射表（`tools/audit_v2_config_surface.py`） | 该表的 `ROUTES`/`CONSUMERS` 仍是 09-27 版：23 个被发现的组里多数标「宿主表单以外没有写入合同」，而它们早已在 `SECTIONS` 里 | 工具滞后（会误导覆盖面判断） |
| 7 | 注册表无重复注册 | 重复提供者 4 处：`expression.configuration`、`expression.reaction_configuration`、`knowledge.configuration`（均为 `field_names`）＋ `memory.episode_settings`（`configuration_fields`） | 一致但需登记（同名提供方重复注册，未来易漂移） |
| 8 | 后加字段一律按"存储形状复现"处理，不进必填列表（本轮新立的约定） | `staging_config.py` 已有 `POLICY_LATE_FIELDS` + `SHAPE_SENSITIVE_BLOCKS`；但 `SEGMENTATION_LATE_FIELDS` 仍**无人引用**（segmentation 的省略规则仍是"所有等于默认的键"，与常量名声明的语义不符） | 实现内部不一致（低危，形状问题已被上一轮修法覆盖） |

---

## 四、页面与导航

| # | 设计稿声明 | 现状 | 判定 |
| --- | --- | --- | --- |
| 1 | 侧边栏"默认 7 个入口，按需 2 个"（`NAV_SEGMENT_PLAN_20260925.md:44`） | `app.js` 是 **4 组 17 项**（小屋；能力配置 6；专题配置 6；设置 4），且另有 `NAV_PAGES_V4_20260925.md` 等三份导航稿 | 设计稿已被实现超越，**无现行版本链** |
| 2 | `manageTabs` 里有 5 个页签已无入口（`growth/base/state/reply/preferences`） | 仍存在且仍无 rail/`configLink` 指向 | 一致（缺陷仍在，属设计稿差异清单第 1 条） |
| 3 | 分区编号唯一、不跨页复用（`PAGE_DISPLAY_AND_CONFIG_DESIGN_20260928.md` R5） | **编号已不进 DOM**（`app.js:898-925`），重复 `L3` 与跨页 `B1/B2/B4/D5/E1/E3/E4/E5` 随之消失 | 设计稿滞后：R5 在当前实现里已不适用，应改写为"标题 + 内容"结构 |
| 4 | 没有合同的区块要给边界卡说明"为什么现在没有"（`_20260929.md` §1.2） | 现改为**空块整块跳过**（`consoleSections` 过滤空 body），`boundaryCard` 全页只剩 1 处调用 | 设计意图被反转：需在稿里写明"宁可不渲染也不塞解释卡" |
| 5 | 每个配置组只有一个可写归属页（R1） | `memory` 组只在决策页挂载（`renderDecision()` 内含 `memorySettingsHost`，记忆页只挂事实工作台）——该项**已符合**；`proactive.contact` 的控件仍在决策 B4 与主动与联系页各挂一次 | 部分达成（contact 段仍需收敛） |
| 6 | 群公共记忆有管理入口（`V1_V2_FUNCTIONAL_GAP_AUDIT` G03） | 后端 6 条路由齐备，页面零消费点 | **实现缺口（P1）** |
| 7 | 主动识屏可从页面开启（`SCREEN_PERCEPTION_AND_RECALL_PRODUCTION_20260927.md`） | `screen_glance_enabled` 无控件 | **实现缺口（P1）** |
| 8 | 「清除已保存的密钥」可用（B11 的修复记录） | 控件在，但勾选路径不生效 | **实现缺口（P1）** |

---

## 五、字面设计稿：Content `design-previews/companion-v2`

- 该目录 `page-build.json` 的 `source` 仍写 `astrbot_plugin_private_companion_v2/pages/陪伴小屋`，即它是规范源的**副本**；
- 同名 31 文件：**8 个逐字节一致、23 个不同**；规范源另有 **24 个文件**它没有（`config-editor.*`、`workbench-page.*`、`setup-guide.*`、`perception-native-page.js`、`backup-page.*`、`appearance-page.css`、`expression-page.js`、`memory-settings-section.js`、`tokens*.css`、`entrance.*`、`theme.*`、`shell*`、若干预览页）；
- 按 `AGENTS.md` 它"仅为开发预览"，且 `BUILD_STATUS` 多轮记着"`--preview` 同步未做"——结论：**它可以不追平，但任何"按设计稿核对界面"的动作都不能以它为基线**；若要保留其价值，建议要么跑一次 `tools/sync_framework_page.py --preview`，要么在目录里放一份 `STALE.md` 写明滞后范围。

---

## 六、三路并行复核摘要

### 6.1 早期框架审计（`DESIGN_CONFORMANCE_AUDIT_20260921.md`、`FRAMEWORK_PROGRESS_AUDIT_20260924.md`）

39 条缺口逐条复核：**绝大多数已解决**（多 Bot 作用域、角色 owner、统一权限目录 64 条动作、诊断答疑四模式、修复建议流程、核心身份可无 grant 读写配置、冷归档、表达学习、预览回滚、混合查询增量化、群 Reply 媒体、生图/改图）。**仍未解决的四类**：
1. 第三方拓展的**真实下载/装卸/依赖恢复**（`capabilities/repositories.py:143,246,321,337` 状态机在，全库无 HTTP 下载实现）；
2. **跨进程记忆 SDK** 与第三方实际消费者；
3. **全量 V1 字段/规则承接与替换发行**（迁移器已建，替换发行未做）；
4. 大量**真实平台/模型现场验收**（按性质不可由代码判定）。

其中 11 项内容已**彻底过期**，最典型：
- schema 版本：文档写 v5 / v30，实测 **v44**；
- `metadata.yaml` 版本：文档写 0.2.0，实测 **2.0.0**；
- 「答疑服务尚未实现」整节、「`ScopeRef` 只有四字段」、「冷归档/表达学习/预览回滚未实现」均已落地；
- 「群公共记忆管理页未完成」应改述为**后端已通、前端未接**。

### 6.2 09-27 偏差审计的 13 条（`DESIGN_VS_IMPLEMENTATION_AUDIT_20260927.md`）

**9 条仍成立**：B1（端口 `lookup()` 生产零调用）、B2（`executor()` 死代码，行号漂移到 `native_extensions/__init__.py:285-286`）、B3（`execution_integrated` 恒 False）、B4（聚合超 64 清空全部原生声明）、B5（发现期无端口存在性校验）、B13（Image 侧自反比较，本仓外）、B15（`delivery.py:135/139` 重复定义 + 调不存在的 `manifest`）、B16（`review.py` 重复 `review_key`）、B17（群图审核模型档键名与任务种类不一致 → 生产调用必 `model_task_unregistered`）。
**4 条已修复**：B9（识屏 Pipeline 已有生产入口，但 `ScreenCaptureService` 仍无生产调用点）、B10（主动/日记两条链已能取到数据）、B11（控件已加，但见 N1）、B12（生图额度日界与 `date_perception.calendar_timezone` 同源）。
**新发现 4 条**：N1（§一 P1 的清除密钥缺陷）、N2（`COMPANION_PROVIDER_STATUS_20260927.md:138-140` 与 `IMAGE_EXTENSION_GAP_DESIGN_20260927.md:199-201` 仍把已修的 B9–B12 当待办）、N3（B9 残留未在文档注明）、N4（§一 P1 的主动识屏不可达）。

### 6.3 配置与任务表声明（104 条逐条对账）

结论分布：**一致 70 / 文档滞后 28 / 声明未落实 1 / 未找到证据 5**。

口径提醒（先看这条）：账本 `docs/V2_CONFIG_SURFACE_20260928.csv` 的 `state` 是**「字段名是否命中页面语料」**，不是「字段是否注册」（`tools/build_v2_inventory.py:279-295` 的 `classify()`）；`intended` 是人工清单 `INTENDED_OMISSIONS`。用它证「已进页面」成立，用它判「未注册」会误判。

| # | 出入 | 证据 | 判定 |
| --- | --- | --- | --- |
| 1 | **C2 批（参考图 / 衣柜 / 参考资产）已大面积落地**，文档仍按"待做"写 | `companion_v2/references/{wardrobe,configuration,service,models,repositories}.py`、`storage/reference_asset_schema.py:84-86`（limit=24）、`astrbot_host/configuration_api.py:39`、`configuration/management.py:336,355`、`pages/陪伴小屋/app.js:1111` 挂载 | 文档滞后 |
| 2 | **书架二期 12 字段与消费者齐备** | `library/configuration.py:33-41`（rating_enabled / preference_* 5 项 / min_interval_hours 18 / share 0.18 / ask 0.16）＋ `library/preferences.py:6-8,51-53`、`service.py:170-177`、`triggers.py:44-54` | 文档滞后 |
| 3 | **「页面接入待第②阶段」这句注记在多处已过期** | T01/T06/T09/T15/T28/T53 名下的控件实际已挂载：`app.js:1101`（quota+image_review）、`:1103`（budget）、`silence_min_confidence`/`silence_feedback_penalty`＝covered 于 `state-contact.js`、`automatic_solar_terms_enabled`＝covered、`expression.learning` 10/10 covered；**T10 三开关仍 missing，那句仍准确** | 文档滞后（高发点） |
| 4 | **文档自己推翻了自己的两项**：`meal_care_followup_minutes`、`daily_plan_time` 由"功能缺口"改判 | 账本改为 renamed-equivalent / not-migrated-by-design；`tests/test_calendar_planning.py:468-473` 明示 `daily_plan_time` 已 retired；meal 仅对齐 45 分钟槽宽，V1「未回应补问一次」语义仍未实现（口径存疑，建议复核） | 文档滞后＋口径待定 |
| 5 | **"5 处账本未回写"只剩 2 处；owed 总数是 29 不是 114** | `weather_refresh_minutes`、`skill_growth_rate` 已回写；仍 owed 的是 `group_high_intensity` 7 行、`group_slang_topic` 4 行；`docs/V1_V2_CONFIG_VERIFIED_20260927.csv` 实测 owed **29 行** | 文档滞后（数字差 4 倍） |
| 6 | **唯一"声明未落实"**：T06 写目标文件 `proactive/silence.py` | 该文件不存在；真实落点 `proactive/configuration.py:343-345` ＋ `proactive/service.py:355,449,509`（"已完成首版"本身成立） | 声明未落实（路径） |
| 7 | 行号漂移与缓存串过期 | 装配点实为 `astrbot_host/controller.py:373-375`、`multi_controller.py:137-139`（文档写 283/129）；`role_work/growth/configuration.py:27-33`（文档写 19-25）；`pages/陪伴小屋/index.html:100` 实为 `semantic-page.js?v=bridge-bootstrap-20260929`（文档写 `?v=slang-web-reference-20260928`） | 文档滞后 |
| 8 | 硬约束写"当前 v41" | `storage/schema.py:1624` 已是 `SCHEMA_VERSION_V44`（`runtime.py:1071` 有 V43→V44 迁移） | 文档滞后（与 §3 一致） |
| 9 | 5 条聚合数字找不到出处 | 文档 B「合并回归 130 项/129 通过」、Python 3.10 TimeoutError 定性、文档 C「销号 40 项」、文档3「53 处文件引用 + 40 个测试模块」、文档 C「group_participation 全部动作 shareable=False」（`object_access.py` 的 shareable=False 清单里查不到该动作） | 未找到证据 |

抽样验证通过的高价值条目（说明这批文档主体是可靠的）：天气链（`planning_config.py:14,27,104-116` 等逐行命中）、转发链（`_conf_schema.json:694,700,706` ＋ 6 处入口 ＋ `ForwardIntakePolicyTests` 恰好 5 例）、黑话链（`semantic-page.js:34-36` ＝ 15 项且注释同步）、13 个测试模块的用例数与文档一致（仅 T01 差 1）、`tools/sync_framework_page.py --check` 空差异、T27/T28/T48/T01/T13/T17/T20/T53 的字段数逐项 import 确认。

**不属于"滞后"、而是结论本身需要重判的 5 条**（比数字过期更要紧）：

| # | 问题 | 证据 | 需要你定的事 |
| --- | --- | --- | --- |
| 10 | **文档 C 的 C3-2 前提不成立**：它以「V2 没有『主用户』概念」为理由建议销号 `auto_voice` 4 项 | `conversation/media/quota.py:33` 有 `"private_owner": "primary user private chat"`、`:81` `return "private_owner" if row["tier"] == "core"` —— V2 **有**核心档/主用户概念 | 账本 4 行仍 `owed`；请重判这 4 项，别按"无此概念"销号 |
| 11 | **`meal_care_followup_minutes` 口径存疑**（文档 B 判"功能缺口"、账本判 renamed-equivalent） | 代码只把它当**槽宽**用：`proactive/meal_events.py:13` `WINDOW=45min`、`:27` 改读配置、`:52-70` 只按槽选一次；V1 的"未回应后补问一次"路径未见实现 | 要么补实现，要么把账本改回 owed 并在文档写明"只迁了槽宽" |
| 12 | **C2-1 不应整组勾完** | `enable_p5_structured_reference_assets` 仍 `owed`；群话题线现已由 V2 按群与角色记录有界摘要并接入配置页，不能再作为“无 V2 实现”的例子；黑话联网释义仍是独立欠项 | 只把话题线从缺口例子中移除，P5 与黑话联网释义仍单独留出 |
| 13 | **C2-4 的表述过宽**：文档写"V2 没有按任务类型指派该维度" | V2 有 per-task provider 面（15 个 `model.<task>` 组各 8 字段全 covered，含 `provider`）；缺的只是 V1 的三个辅助档（DETAIL_ENHANCEMENT / HISTORY_SUMMARY / DAILY_REVIEW，已判 not-migrated-by-design） | 表述收窄为"缺那三个辅助任务档" |
| 14 | **T45/T51 与文档 C §四.4 的落差** | `component_order`（`reply_settings.py:78`）与 `reply_quote_*` 4 项（`:78-83`）在 CSV 仍 `missing`（没有页面控件），而文档 C 把这两组算作"落地 + 页面" | 要么补控件，要么改文档口径 |

欠账现状（回写时照这个清单）：仍 `owed` 的 29 行＝`forward*` 3、`group_high_intensity` 7、`group_slang_topic` 4、`photo_action` p5 1、`reactive_poke` 7、`auto_voice` 4、`legacy_compat` 3。另有两处口径不一致值得一并统一：T50（转述）文档写"排后（依赖 T27）"，账本已按 `not-migrated-by-design` 销号；`group_member_safety_*` 8 个 V1 键**未**注册为配置字段（现为代码内策略 `hits.py:18-62`），与"配置项承接"的读法有张力。

---

## 七、建议处理顺序

1. **先裁决 legacy 迁移的规则归属**（P0）：二选一 ——
   (a) 给 `companion_v2.legacy.migration` 登记命名策略（`APPROVED_IO_BY_MODULE` 加 `read_text/rglob/connect` 并写明"只读 V1、单向写 V2、默认不自动执行"），同步改 `REPOSITORY_LAYOUT.md:105` 与 `AGENTS.md:13` 的措辞；
   (b) 把定位与读取搬到 `astrbot_host/legacy_*`，核心只留 `ConfigIntent` 转换逻辑（改动更大，但守住"核心无 I/O"的原设计）。
   两种都能让 `tests/test_isolation.py` 回到绿——**不能靠删测试解决**。
2. **修 3 个用户可见的实现缺口**：清除密钥（`models-page.js` 一行分支）、主动识屏开关（`proactive.contact` 的 `screen_glance_*` 加进联系页字段表）、群公共记忆前端入口（`group_memory_api` 已有路由，只缺控件）。
3. **回写三份收口/任务文档**（第三路复核的直接建议）：把 C2 批与书架二期标为已落地；把「页面接入待第②阶段」逐条改成实际落点（仅 T10 三开关仍成立）；`owed` 由 114 改为 **29**（只剩 `group_high_intensity` 7 行、`group_slang_topic` 4 行）；T06 目标路径改为 `proactive/configuration.py:343-345`；顺手核对 `meal_care_followup_minutes` 的 renamed-equivalent 口径（V1 是"未回应补问一次"，V2 只配槽宽）。
4. **统一一次文档数字**（P2）：路由 89/19、任务 19+、schema v44、配置 604/38、`SECTIONS` 16；顺手把 `tools/audit_v2_native_surface.py` 与 `tools/audit_v2_config_surface.py` 的清单改为"从装配派生"（前者的 import 清单与后者的 ROUTES 表都是手写的，已经过期两轮）。
5. **给导航与页面设计稿定"现行版本"**：四份导航稿（NAV_PAGES_V4 / NAV_SEGMENT_PLAN / NAV_LEAN_PLAN / SIDEBAR_NAV_AUDIT）保留一份、其余标"历史版"；两份页面设计稿按**新骨架**改写（标题 + 内容；编号与状态点不进 DOM；空块跳过而不是塞边界卡），否则下一轮又会按已废弃的 A–L 编号排期。
6. **给字面设计稿定去向**：在 Content 预览目录写 `STALE.md` 说明滞后范围，或跑一次 `tools/sync_framework_page.py --preview`。
7. **清一次运行产物**：`.p4-tmp/`、`.verify-shards/`、`build/tmp/*`、空 `probe-*/`、`__pycache__/`、`.pytest_cache/`。
8. **线上运行档升级前留快照**：库在 v40、代码在 v44，下次打开会连做 4 次迁移；建议先用备份能力做一份安装级快照再启动。

---

## 八、可复跑命令

```powershell
$py = "E:\astrbot\backend\python\python.exe"
$env:PYTHONPATH = "E:\astrbot\backend\app;C:\Users\99505\.astrbot\data\plugins\astrbot_plugin_private_companion_v2"
Set-Location "C:\Users\99505\.astrbot\data\plugins\astrbot_plugin_private_companion_v2"

& $py -X utf8 build\tmp\framework_invariants.py      # 注册身份 / 隔离扫描 / 依赖方向 / 配置面
& $py -X utf8 build\tmp\check_section_wiring.py      # SECTIONS ↔ spec ↔ app.js 三方对账
& $py -X utf8 tools\build_v2_inventory.py            # 账本（组与字段）
& $py -X utf8 tools\audit_page_config_coverage.py    # 分区覆盖自检
& $py ".\build\tmp\run_focused_suite.py" tests.test_isolation tests.test_astrbot_staging_config
& node tests\test_setup_guide.cjs                    # 迁移 UI 的页面契约
```

以上脚本只读工作区、不连宿主、不调模型、不发送消息。
