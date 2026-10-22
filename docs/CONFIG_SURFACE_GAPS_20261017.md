# 配置面缺口审计：哪些"只读"其实该可配

日期：2026-10-17。起因：查"输入模拟"时发现它**已经有值、也差不多能改**，但在页面里几乎找不到；顺着这个问题把"页面上只能看、不能改"的配置整体过了一遍。

## 一、方法

把三类写入口与注册表逐一比对，而不是靠手感：

| 面 | 数量 | 来源 |
| --- | --- | --- |
| V2 配置注册表 | **709 字段 / 32 分区** | 逐模块导入 `*configuration_fields()`（脚本 `build/human-audit/enumerate_fields.py`，`regex`/`httpx` 缺失处做了 shim） |
| 工作台 spec（页面最主力的编辑器） | 433 字段 / 23 分区 | `config-editor.js` 的 `spec`，用 node + `vm` 直接取真对象 |
| 专用页面编辑器 | state / memory / presentation / perception / learning / member-editor / host-options / 拓展面板 | 各模块里的字段清单（含 `["name","标签","bool",…]` 数组式和 `"cycle_"+key+"_days"` 动态式生成） |
| AstrBot 插件表单 | 108 键 / 14 组 | `_conf_schema.json` |
| 拓展设置 schema | 154 键 / 4 个拓展 | `native_extensions/*/settings-schema.json` |

判据：一个字段只要出现在**任一**写入口就算可配；"页面里提到了、但没有任何入口"才是只读。

## 二、结论：真正没有入口的只有 8 个字段

> **状态（同日晚已补齐）**：前 3 行已补控件，见第五节。第 4–8 行核实为有意只读。

| 字段 | 默认 | 用户在哪看到 | 现状 | 判断 |
| --- | --- | --- | --- | --- |
| `role.state.online_status_enabled` | false | 「QQ 状态」把"在线状态"和正在输入、自定义短状态并列讲；DB 里两个会话已是 `true` | 状态表单只渲染**正在输入**与**自定义短状态**两个勾；AstrBot 表单里也没有 | **已补**：状态设置表单第三勾 + 展示面板第三行；grant 由 `sync_window_grants` 自动跟 |
| `content.authoring.cover_enabled` | false | 产出页（Content）只有"启用"和"方向提示" | 全仓 0 次提及：不在 spec、不在表单、不在拓展 schema | **已补**：`cover_assets.py:52` 定义、`:217` 消费（`if not settings["cover_enabled"]: return`）——功能存在但此前打不开 |
| `content.authoring.max_covers_per_work` | 2 | 同上 | 同上 | **已补**（与上一项同段） |
| `role.state.mood_cross_window` | true | 情绪面板 | 无入口 | 有意只读，理由已登记：跨窗口共享，操作员难判断影响 |
| `role.state.mood_interest_window_minutes` | 120 | 情绪面板 | 无入口 | 有意只读，理由已登记：与更新概率强耦合 |
| `role.state.mood_neutral_band` | 3 | 情绪面板 | 无入口 | 有意只读，理由已登记：默认值够用 |
| `knowledge.import_enabled` / `import_paths` | — | 世界知识 | 无入口 | 有意只读，理由已登记：旧世界书导入保留在后端合同，页面只管理官方知识库来源 |
| `conversation.presentation.rules_enabled` | true | 表达页 | 无入口 | 不算缺口：兼容位，`reply-page.js:556-562` 强制为 true，规则补段已无条件生效 |

另有 **58/108 个插件表单键**在页面上没有挂载点（`voice_reply`/`poke`/`forward`/`balance` 的一部分已有专用页，其余只能去 AstrBot 的插件配置里改）。这类不算"只读"，但同样存在"用户不知道该去哪儿改"的问题。

## 三、比"漏字段"更普遍的问题：能改，但搜不到（已修）

这是"输入模拟找不到"的真正成因，也是这次审计最值得修的一处。

1. **全局搜索当时只索引三个来源**（工作台 spec 433、回复页、宿主选项页）。于是 `role.state` **85**、`memory` **30**、`conversation.perception` **11**，合计 **126 个可编辑字段搜不到**：搜"正在输入""生理期""熟人卡""记忆注入"都不会命中。
   → 已接入三个专用编辑器的 `searchEntries()`，现在能搜到（见第五节第 1 项）。
2. **覆盖面自检当时只覆盖 20 个分区 / 350 字段**。注册表 32 个分区 709 个字段，**359 个字段没有任何覆盖面断言**（含 `conversation.presentation` 124、`role.state` 85、`role_profile` 52、`memory` 30、`expression.learning.*` 29、`image.output` 17、`conversation.perception` 11）：漏了控件自检也不会变红。
   → 现在 **32 个分区 / 709 字段全覆盖**，与注册表逐项对齐（见第五节第 2 项）。
3. **"有意只读"没地方登记**：`INTENTIONAL` 只对 `MODULES` 里的分区生效，另外 12 个分区的只读决策散在代码注释里。
   → `INTENTIONAL` 现在也解释了 `expression.learning` 里由表达页分段承接的两个开关；其余只读项写在本文件第二节。

## 四、只读是合理的（核对过，不用改）

- **忙碌 / 位置**：状态页明写"忙碌是日程的产物""位置由对话内容自然形成"，并给出跳转（改日程 / 改开口闸门）。
- **展示通道诊断**：「QQ 状态」面板的受理回执与运行状态是诊断信息，不是配置。
- **拓展装配状态**：拓展面板显示装配/就绪/开关，配置在各自的设置里；页面提供跳转。
- **首页右栏 8 个状态格、日程、天气、余额、用量、诊断**：都是运行数据，不是配置项。
- **`conversation.presentation.rules_enabled`**：兼容位，已强制生效。

## 五、已补齐的位置（2026-10-17 晚）

原则：控件放在原来只能看的地方旁边，文案全部中文，且与后端实际行为对齐。

### 1. 全局搜索接入三个专用编辑器（126 个字段）

| 位置 | 改动 |
| --- | --- |
| `pages/陪伴小屋/state-maintenance.js` | 新增 `searchEntries()`：按 `titles`/`fields(kind)` 摊平状态字段（89 条 / 82 个字段 / 12 个分段），另补「QQ 展示设置」4 条（含新加的在线状态） |
| `pages/陪伴小屋/memory-settings-section.js` | 新增 `searchEntries()`：30 个记忆策略字段，按 `sections` 归段 |
| `pages/陪伴小屋/perception-native-page.js` | 新增 `searchEntries()`：感知页 `model` 段 11 个字段（`news` 段的字段其实属主动联系、spec 里已可搜，不重复索引） |
| `pages/陪伴小屋/state-page.js` | 新增 `openEditor(kind, field)`：切到对应图块 → 打开编辑表单 → 聚焦到那个输入框（与"点图块→点配置"同一条路径） |
| `pages/陪伴小屋/app.js` | 搜索索引加上这三个来源；`configSearchLocation()` 给 `role.state` / `memory` / `conversation.perception` 各一条落点；`openSearchSetting()` 增加三条跳转（记忆先切到「设置」路由、感知先切分段再按 `data-perception-field` 聚焦） |

### 2. 覆盖面自检补齐到全部 32 个分区

- `MODULES` 补 5 个原本有 spec 却没断言的分区：`image.output`、`expression.learning`、`role_profile`、`relationship_profile`、`content.authoring`。
- 新增 `DEDICATED_EDITORS`：9 个由专用编辑器承接的分区（`memory`、`conversation.presentation`、`conversation.perception`、`role.state`、`expression.learning.{private,group,role}`、`role.growth`、`person.learning`）断言"承接页面还在、字段名还在"，不做逐字段断言（这些页面按模板拼名字）。
- `INTENTIONAL` 补 `expression.learning` 的两个范围开关（由表达页「私聊学习 / 本群学习」两段承接），并去掉已补上控件的 `online_status_enabled`。
- `backend_fields()` 支持需要参数的 `reply_settings.configuration_fields()`（用出厂 `SegmentationPolicy()` 展开全量）。
- 结果：**32 个分区 / 709 字段**全部纳入自检，与注册表一一对齐（7 项有意不接、3 项其他页面维护、259 项专用编辑器承接）。

### 3. 「QQ 状态」三条通道并列且都可配

| 位置 | 改动 |
| --- | --- |
| `pages/陪伴小屋/state-editor.js` | `fields` 常量加 `online_status_enabled`；「QQ 展示设置」表单加第三个勾**启用 QQ 在线状态**；帮助文字改成三条通道的关系（在线状态优先于短状态、日程公开文案最高优先、同一时刻只报一种） |
| `pages/陪伴小屋/state-page.js` | 图块「QQ 状态」的"N 项已开启"改为统计三条；「展示通道」加**在线状态**一行（后端 `presentation_diagnostics.online_status` 早就在返回，只是页面没渲染），模式值译成中文（在线／离开／忙碌／隐身），三条通道的"空闲"说法分开写（在线状态空闲是"这轮没轮到它"，不是"没有待展示文案"）；展示确认里按请求内容区分**在线状态**与**自定义短状态**，模式类请求不再显示空的"请求文案" |

### 4. 产出页补上封面开关

`pages/陪伴小屋/config-editor.js` 的 `content.authoring` spec：

- 标签：**允许作品带封面**、**同一版本最多保留的封面数**（1–8）；
- 帮助按 `cover_assets.py` 的实际行为写：关掉只是停止新的封面、已存的不删；达到上限后新的不保存、旧的照旧；作品换版本后旧封面记为历史版本、不占名额；
- 新增「作品封面」段（`id: cover`），`note` 补一句封面按开关单独生成；
- `companion_v2/conversation/content/cover_assets.py` 增加整组访问器 `group_fields()`，供覆盖面自检一次比对正文与封面四字段。

### 5. 验证

- `python tools/audit_page_config_coverage.py` → `全部 32 个分区覆盖自检通过（共 709 字段…）`
- `python tools/sync_framework_page.py --check` → 无输出
- `python tools/audit_page_scale.py` → `尺度审计通过`；`python tools/audit_theme_tokens.py` → `全部通过`
- `node tests/test_state_*.cjs`、`test_memory_settings_workbench`、`test_native_perception_page`、`test_config_editor`、`test_reply_page`、`test_product_workspaces`、`test_expression_page`、`test_shell`、`test_app_globals` 全部通过

## 六、未验证 / 边界

- 判定基于"字段名出现在该模块里"。动态拼名（`"cycle_"+key+"_days"`、`Object.keys(homeFeatures).map(name=>name+"_enabled")`）与数组式定义（`["almanac_enabled","提供黄历宜忌","bool",…]`）都按**可配**处理，并逐类抽查确认；没有逐字段点击验证。
- 专用编辑器那 9 个分区只断言"页面在、字段名在"，不是逐字段断言：它们的字段名由模板拼出（`cycle_*`、`home_only_special_*`、`expression_*` 前缀），静态比对会误报。要逐字段断言，得让这些编辑器导出自己的字段清单。
- 新增的搜索落点只验证到"条目能生成、目标页面与钩子在"（node 里跑过 `searchEntries()`：状态 89 条 / 记忆 30 条 / 感知 11 条）；真机点击跳转未做浏览器回归。
- 模型族（`model_gateway.routing`）与能力族（`capability_*`）字段未纳入本次 709 的统计口径（它们由模型页与拓展面板承接，另算 207 + 14）。
- 真机运行中的实际可写性还取决于授权与配置层（installation/role/window）；本文只判断"有没有入口"。
- 本次脚本都在 `build/human-audit/`（不进交付包）：`enumerate_fields.py`、`field_coverage.py`、`run_coverage.py`（带 `regex` shim 跑自检）、`check_search.cjs`（验证三条新索引）。
