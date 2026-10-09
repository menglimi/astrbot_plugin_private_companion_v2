# 事实与经历：把 V2 的记录和外部记忆插件分开（2026-10-02）

用户提了两件连着的事：页面叫「记忆与经历」容易让人以为它管的是**记忆插件**；而 V2 自己记的东西其实是**事实与经历**。于是这一轮做两件事——改名，以及在该说清楚的地方把两者分开说。

## 一、改名：记忆与经历 → 事实与经历

活代码里共 33 处，16 个文件：

| 位置 | 说明 |
|---|---|
| `pages/陪伴小屋/app.js`（14 处） | 侧栏分组、路由页标题、面包屑、两个 tab、aria-label、跳转按钮、命令面板条目 |
| `pages/陪伴小屋/shell.js`、`appearance-page.js` | 导航条目与外观页的示例导航 |
| `pages/陪伴小屋/memory-page.js`（3 处）、`memory-page.css`、`memory-settings-section.js` | 页面注释、面包屑与 `document.title` |
| `companion_v2/product/__init__.py` | 领域产品标签（后台一处 `"label"`） |
| `tools/build_surface_preview.py`、`check_product_page.cjs`、`check_memory_preview.cjs`、`build_memory_preview.py`、`memory_preview.tpl.html` | 预览生成器与它们的期望 |
| `tests/test_memory_page.cjs`、`README.md`、`STRUCTURE.md`、`docs/page-designs/*` | 注释与当前描述 |

同时把**页面内**几处「说 V2 自己的库、却写成记忆」的标签也统一了：`aria-label="记忆工作区"` → 「事实与经历工作区」、`aria-label="记忆页面"` → 「事实与经历页面」、首页卡「记忆整理与遗忘」 → 「事实整理与遗忘」、首页分区「认知与记忆」 → 「认知与事实」、工具提示「查看记忆事实、经历…」 → 「查看事实、经历…」。

**保留**「记忆策略」「统一记忆策略」「记忆沉淀与每日反思」这些名字：它们指的是 V2 自己的记录与整理流程（配置组也叫 `memory`），不是外部插件；改名的代价大于收益，改用一句话说清边界（下节）。历史文档（`docs/` 里带日期的设计稿、审计 CSV）不改——它们是当时的记录。

## 二、说清边界：V2 的事实 ≠ 外部记忆插件

- **归属横幅**（`memory-page.js`）：外部提供时说明「那是外部的记忆插件，与这一页记下的事实和经历不是同一份库，两边各存各的」；V2 提供时说明「这一页管的是 V2 自己的事实与经历，与〈…〉的库不是同一份——那是外部记忆插件，不是这里的记录」。原有断言（`长期记忆现在由〈X〉提供`、`长期记忆现在由 V2 提供`、`与〈X〉的库不是同一份`）全部保留。
- **配置卡片说明**（`memory-settings-section.js`）：`note` 从空字符串改成「这里调的是 V2 自己记什么、记多少、多久整理一次，与外部记忆插件的库无关——外部记忆插件是否提供长期记忆、用了多少，由它自己的账本负责。」这是用户最可能误解的一处：在「记忆策略」里调注入上限，很容易以为在调记忆插件。
- **账本行**（`maintenance-page.js`）：三处「记忆插件」改成「**外部**记忆插件」（列表项、Token 行、账本脚注），治理与维护页里它和角色预算本来就是分开记账的。

## 三、顺带收口：`shell.css` 迁入令牌，OTHERS 清空

改名过程中审计的自发现规则（【二之二】：引用了 `--fs-*` 却不在 `MIGRATED` 名单）把 `shell.css` 抓了出来——它一直在用字号令牌，却从没进过名单，属半迁移。用 `tools/migrate_page_scale.py` 迁干净（字号 10、间距 62、圆角 2），另修掉 8 处 `var(--r-md, 12px)` 这种「给无条件声明的令牌写 px 兜底」（改成 `var(--r-md, var(--r-sm))`，与 `styles.css` 的既有做法一致），然后进名单。`OTHERS` 现在**为空**：`pages/陪伴小屋/*.css` 全部走尺度令牌。
`tools/audit_theme_tokens.py` 的硬编码色值基线里 `config-editor.css` 已是 0，按该工具自己的纪律（只许减不许增、清零就删条目）把这条基线删掉。

## 四、验证

| 检查 | 结果 |
|---|---|
| `tools/audit_page_scale.py` | **尺度审计通过**（26 页零写死；OTHERS 空） |
| `tools/audit_theme_tokens.py` | 全部通过（六套色板一致、无悬空引用；基线已收紧） |
| 前端检查 | `test_memory_page` **15/15**、`test_maintenance_page` 4/4、`test_section_wiring` 8/8、`test_workbench_field_layout` 5/5、`test_config_editor` 42/42、`test_console_styles` 5/5、`test_page_scale` 5/5、`test_app_globals` 3/3、`test_theme_registry` 16/16 |
| Python（包内） | `tests.test_memory_ownership` **21/21**（归属横幅的两支文案断言都在） |
| 产物 | `sync_framework_page.py --check` → `{"changed": []}` |
| 残留 | 活代码里 `记忆与经历` **0 处**；`事实与经历` 20 处 |
| 交付包 | 构建 + `verify_v2_release.py --host-check` 通过（唯一公开页、宿主停机与路由注销、模型/平台调用 0），核心包 SHA-256 `219a634e913b4ef86c89421643c8e1fe193b74bdf94b6a4c6e1ba2b99b770632` |

## 五、未做 / 需要你知道

1. **生成物没重建**：`pages/陪伴小屋/shell-preview.html`、`v2-surface-preview.html`、`_exp-no-home.html` 里还留着旧标签（它们是 `tools/build_page_preview.py` 一类工具产出的 16MB 级快照，审计不判生成物）。下次重建预览时自动跟上。
2. **`tools/check_product_page.cjs` 跑不了**：它 `require("playwright")`，本机没装——它里面的期望（导航列表）已经改成「事实与经历」，等有 Playwright 时再跑。
3. **全量回归的既有失败与本轮无关**（另行说明）：宿主媒体/预览、presence、token 记账等家族的断言仍按已移除的 `preview` 模式与旧 presence 行为写，属仓库既有的测试漂移，`docs/BUILD_STATUS.md` 2026-10-01 条目已记过一次。
