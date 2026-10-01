# 页面密度修复：配置字段网格与「芝麻字号」（2026-10-02）

起因是两张截图：①表达学习那组配置里，**每个数字字段独占一整行**——一行只有标题、说明、一个被拉伸到整幅宽的数字框，范围提示飘在最右边，九个字段要滚九屏；②「治理与维护」页**整页字号小得像芝麻**，密集到读不下来。两处都不是"看着别扭"，而是有明确成因与可判定的修法。

## 一、字段网格：单列堆叠 → 按宽度分列

**成因**：`workbench.css` 里 `.wb-fields{display:flex;flex-direction:column;gap:0}`，字段被写死成"一行一个"；`.wb-number input{flex:1}` 再把数字框拉满整幅。渲染内核 `workbench-page.js` 生成的每个字段是 `[层轨][主体][右侧状态]` 三栏，本身没有宽度假设——出问题的只是容器。

**改法**（只动 CSS）：

| 规则 | 之前 | 现在 |
|---|---|---|
| `.wb-fields` | `flex;flex-direction:column` | `grid;repeat(auto-fit,minmax(300px,1fr))`，列间距 `--sp-5`、行间距 0（保持分隔线连续） |
| 长控件 | 与标量字段同宽 | `.wb-field:has(textarea / .wb-word-editor / .wb-order-editor…)` → `grid-column:1/-1` 整幅通栏 |
| `.wb-number input` | `flex:1`（拉满整幅） | `flex:0 1 148px;min-width:104px`，范围提示紧挨输入框 |
| 右侧状态 | 单行 | 允许换行（单元格变窄后芯片与「恢复继承」不再挤控件） |
| ≤760px | 两栏 | `.wb-fields` 回落单列 |

列宽下限 300px 是"标签 + 数字框 + 范围"放得下、又不至于把说明挤成两行的下限；在 1400px 的内容区里九个字段排成 3 行而不是 9 行。

**护栏**：`tests/test_workbench_field_layout.cjs`（5 项）直接读 `workbench.css` 的声明来判定"必须分列、长控件必须通栏、窄屏必须回落单列、数字框必须有宽度上限"。起因就是这条规则此前**没有任何检查守着**，谁都能在不知情的情况下把它改回单列。

## 二、「芝麻字号」：写死的小字号 + 从未被判定

**成因有两层**：`maintenance-page.css` 里字号几乎全是写死的 px，其中 **165 处低于 10.5px**（7/8/9/10px，最小 7px）；更要紧的是这份文件**既不在 `audit_page_scale.py` 的 `MIGRATED` 名单里、也不在 `OTHERS` 名单里**——名单与事实脱节，于是它从来没进过任何判定，写多小都没人拦。

**改法**：

1. **迁到尺度令牌**：维护页 218 处字号、430 处间距、60 处圆角全部收进 `--fs-*`/`--sp-*`/`--r-*`。7/8/9/10px 这 165 处一律升到 `--fs-micro`(10.5px)；11–13px → `--fs-tiny`/`--fs-body`；大数字按角色归 `--fs-display`/`--fs-hero`（其中 `.maint-usage-total strong` 29→36、`.maint-cache-rate strong` 31→36 是本次放大最多的两处，若嫌大可改回 `--fs-display`，一行的事）。
2. **补上判定，防止再脱节**：`audit_page_scale.py` 新增【二】**任何页面 CSS 都不得声明低于最小档位的字号**——阈值从 `tokens.css` 的 `--fs-micro` **现算**（不写死 11）；豁免 `font-size:0`（折叠文本节点手法，文件里已有同类豁免先例）、相对量（`em/rem/%/ch`）与流体值（`vw/vh`、`calc/clamp/min/max`），因为它们没有绝对大小，硬判会产误报。命中列文件名与次数并计失败，**对所有页面 CSS 生效**，不只是已迁移的页。
3. **一并迁完同病相怜的页**：`styles.css`（43 处 <10px）、`output-page.css`（19）、`workspace-theme.css`（2）、`home.css`（1）、`navigation.css`、`workbench.css`、`config-editor.css`、`expression-config.css`。全站 `pages/陪伴小屋/*.css` 现在**没有任何低于 `--fs-micro` 的字号**。
4. **顺手修掉 `expression-config.css` 的真实缺陷**：它引用了不存在的 `var(--fs-small)`（token 早已并入 `--fs-body`），声明被静默丢弃、样式吃 fallback——这正是审计【二之二】"引用未声明令牌"要抓的形状。

迁移用仓库自带的 `tools/migrate_page_scale.py`，过程中修掉它三处缺陷（都写进了注释）：FONT 表只覆盖 9–36px，两端落进"未处理"看着像实测值；`SPACING_PROP` 正则漏 `column-gap`/`row-gap`，而审计的 SPACING 集合包含它们（这正是三处审计失败的根因）；`var(--r-sm,6px)` 这种给无条件声明的令牌写 px fallback 会被算成写死值。

## 三、验证

| 检查 | 结果 |
|---|---|
| `tools/audit_page_scale.py` | **exit 0「尺度审计通过」**（26 页零写死、令牌单源、档位间距、新【二】全过） |
| `tools/audit_theme_tokens.py` | 全部通过（六套色板令牌一致、无悬空引用） |
| `tools/audit_page_config_coverage.py` | 19 个分区 / 335 字段通过 |
| 前端检查 | `test_workbench_field_layout` **5/5**、`test_config_editor` **42/42**、`test_console_styles` 5/5、`test_maintenance_page` 4/4、`test_page_scale` 5/5、`test_section_wiring` 8/8、`test_app_globals` 3/3、`test_theme_registry` 16/16 |
| 页面产物 | `sync_framework_page.py --check` → `{"changed": []}` |
| 交付包 | `build_v2_release.py` + `verify_v2_release.py --host-check` 通过（8 包、哈希/CRC/语法、唯一公开页、宿主停机与路由注销、模型/平台调用 0）；核心包 SHA-256 `42d64ecabffbcb162a714f0212daeed1a5f93fbe8dcfd96c4a33d56d92f73c28` |
| 解包目录内复跑 | 三个审计全过 + 上面 8 个前端检查全绿 + `tests.test_qzone_extension` 54 项通过 |

**与本轮无关的既有失败（已归因，未修）**：`test_home_sidebar`、`test_learning_page`、`test_bridge_bootstrap`、`test_backup_page`、`test_decision_page`、`test_entrance` 六个 CJS 套件有失败。前五个**不读取任何本轮改动的文件**；`test_entrance` 读 `entrance.css`，但该文件与 `entrance.js`、`home-sidebar.js`、`shell.css` 自上一交付包以来**哈希未变**，它的失败断言是 JS 形状（`shellView==='state'` → `scheduleStatusBuild`），属其他切片的代码漂移。

## 四、已知与待决策

1. **`shell.css`** 仍是 `OTHERS` 唯一成员（18 字号 + 45 间距 + 8 圆角），本次未在范围内；它也有 `var(--r-*,12px)` 这类兜底写法。
2. **工作区样式表不在新判定范围**：`pages/{宿主管理,关系与权限}/style.css` 各 2 处 9px（以及 `pages/陪伴小屋/workspaces/*/style.css` 里的嵌入副本）。它们不走小屋的尺度令牌体系，审计按 `pages/陪伴小屋/*.css` 扫描。要不要把工作区也接小屋的 `--fs-*`，需要先定口径（涉及 5 个文件 136 处字号）。
3. **`perception-page-shell.css` 是 0 字节空文件但仍被 `index.html` 引用**——与本轮无关的一处观察，未处理。
4. **生成物快照未重建**：`shell-preview.html`（16.6MB 内联副本）里仍是旧字号与 `var(--fs-small)`；审计不判生成物，下次重建预览时自动跟上。
5. **没有像素级视觉验证**：本沙箱无 Playwright/Chromium，溢出与裁切结论来自规则层核对（固定高度 × 行高计算、`overflow:hidden` + `nowrap` 的组合、网格 `minmax` 全表对照、窄屏断点覆盖），不是浏览器截图。
