# 拓展页外壳设计整改记录

日期：2026-10-17。范围：唯一公开拓展页「陪伴小屋」的外壳（左栏、小屋区、下方面板、主题令牌），以及审计过程中查出的打包与配置面问题。

本文只记录**本轮实际改了什么、证据是什么、哪些没改**。功能合同（API、鉴权、数据根）一条没动。

同一轮之后还有一次针对**配置编辑体验**的整改（吸底保存条、字段级错误、Ctrl/⌘+S、离开前拦截未保存草稿），单独记在[配置编辑体验整改](CONFIG_EXPERIENCE_20261017.md)。

## 一、先说结论

外壳有四个可见缺陷是**结构性的**，不是审美偏好：

| 缺陷 | 实测（1440×900） | 根因 |
| --- | --- | --- |
| 左栏只涂了 158px，右边空 62px | `.rail` 盒宽 158，栅格列 220 | `navigation.css:1` 写死 `width:158px`；`shell.css` 的栅格项 `justify-self:stretch` 在宽度确定后退化为 start |
| 配置页上方 250px 空白，面板被推到 y=436 | 小屋 154px 占了 405px 行高，面板只有 194px 高 | `.shell-body` 用两行 `auto` + `align-items:start`：栅格把剩余空间平摊给自动行（`align-content:normal` 等价 stretch），行被拉高、行内元素不拉伸 |
| 手机左栏 126px 高、17 个图标排三行，品牌名竖排 | 占 390×844 的 15% | `#shellNav` 是块级容器，三个 `.shell-nav-group` 各占一行；`.shell-nav-link` 又带 `width:100%` |
| 手机进入配置页后，面板上方还有 151px 空带 | 面板 y=277，左栏只到 126 | 同一处 stretch 行为；缩略态小屋脱离文档流后没人填那条带子 |

另外两类问题是**可访问性硬指标**，不是风格问题：

- 焦点环合成后只有 **1.34–2.20:1**（WCAG 1.4.11 要求 3:1），六套主题全部不达标。原因是 `--t-focus` 带 24–40% alpha，且 `styles.css` 还留着一处裸色 `#9297df`（2.42:1）。
- 弱化文字 `--t-text-faint` 在五套主题上只有 **3.03–3.91:1**，正文级字号要求 4.5:1。
- 「跳到主要内容」指向 `<main id="main" hidden>`：从外壳重排起 `#main` 在首页路由一直是 hidden，键盘用户第一个 Tab 落到一个按下去什么都不发生的链接上。
- 面板标题栏的 `subtitle` 参数**从未被渲染**：`shell.css` 里为它写的 `.shell-panel-head p` 一条规则都不生效，`manageSubtitles` 的二十条说明文案全是死数据，于是每个配置页的标题栏只剩一个名词。

## 二、改了什么

### 外壳布局（`shell.css` / `navigation.css`）

1. **左栏宽度交还栅格**：`navigation.css` 删掉 `.rail{width:158px}`，`#homeShell .rail` 显式 `width:auto`。三档实测：1440→220/220、900→68/68、390→375/375（列宽与盒宽相等）。
2. **缩略态改成「面板独占一行 + 右下角画中画」**：
   - `.shell-body` 缩略态改为 `grid-template-areas:"panel"`、`grid-template-rows:minmax(min-content,1fr)`、`align-items:stretch`。用 `min-content` 下界而不是 `minmax(0,1fr)`：内容长时行照常长高、页面照常滚动，短时撑满视口。
   - 小屋 `position:fixed` 到右下角 176×104（`--shell-pip-w/h` 单一来源），悬停/聚焦恢复亮度，`:focus-visible` 有实色环。
   - `.shell-panel` 改 `display:flex` + 正文 `flex:1`，短页面板也铺到底。
   - 面板正文底部留出画中画高度，最后一行控件不会被压住。
   - 删除 `.stage-overlay.away-only` 与 `#backHome`：缩略态本来有三颗「回到小屋」（场景里一颗、面板标题栏一颗、画中画上再一颗）。现在画中画本身可点可聚焦（`app.js` 已给它 `role=button` 与 `aria-label`），标题栏保留带文字的那颗。
3. **手机（≤760）**：
   - `#homeShell` 行高改 `auto minmax(0,1fr)`，左栏不再被 stretch 拉高。
   - 左栏压成 **50px** 单行横滑条：品牌只留图标、三组之间竖分隔线、隐藏滚动条、每个按钮 40×40。实测 126→50。
   - 首页信息顺序改为「小屋 → 此刻的状态与今日安排 → 家具目录」：`.stage-region` 在非布置态用 `display:contents` 拆开，速览条排到右栏之后。
   - 家具速览条改单行横滑（原来七件家具换三行、占 150px）。
   - 缩略态小屋移出视口并 `visibility:hidden`（DOM、尺寸、相机机位都留着），手机上不再为一张 150px 的缩略图让位；返回入口是面板标题栏与左栏品牌。
4. **面板标题栏**：`panelHead()` 补渲染 `<p>` 说明，新增 `.shell-panel-copy` 容器、图标着色、窄屏说明降一档字号；标题栏按钮 `white-space:nowrap`（此前「回到小屋」被压成竖排两行）。
5. **导航分组**：第一组不再是 `untitled`，补上「专题配置」；三组都有标题。选中态改用 `aria-current="page"` 驱动样式并加 3px 竖标（移动端为下划线），`aria-pressed` 仍同步写入供既有脚本读取。
6. **天气栏（`home.css`）**：手机改两行栅格——图标 + 地点/天气 + 刷新，时钟单独一行横排并加分隔线。原来四列挤在 390px 里，一句说明折三行、右侧三行时间各自成行。
7. **断点收口**：`navigation.css` 的 650 分支与 `.mobile-nav` / `#mainNav`（DOM 里不存在）整段删除，手机断点统一到 760；「全部功能」浮层的 `bottom:84px` 是给已不存在的 76px 底栏留的位，改为常规间距。

### 可访问性

8. `--t-focus` 六套主题全部改成不透明强调色；`styles.css` 的裸色 `#9297df` 换成 `var(--t-focus)`。实测焦点环 **4.66–8.95:1**。
9. `--t-text-faint` 五套主题上调到 **4.50–5.05:1**（对 surface 与 canvas 双达标）。
10. 暗色主题 `--t-on-solid` 由深色文字改纯白：夜读 3.95→4.66、深林 3.68→4.86。
11. 跳转链目标跟着外壳状态走（首页指 `#shellSide`，配置页指 `#shellPanel`），两处容器加 `tabindex="-1"`；样式改用令牌。
12. 面板换页时若焦点在左栏，交接到新面板标题（`tabindex=-1` + `preventScroll`）；面板内部刷新（轮询、保存回执）不抢焦点。
13. 新增六个此前**只被引用、从未声明**的令牌（`--t-status-success/warning/error`、`--t-surface-hover`、`--t-accent-soft`、`--t-on-accent`），接到既有语义令牌上，并删掉 6 处 `var(--x, #hex)` 兜底色值——兜底只解决"不空"，不解决"跟着主题走"。

### 修掉的过期注释与死代码

14. `shell.css` 顶部注释描述的旧三行结构、`navigation.css` 里"配置页外壳已迁到 console.css"的过期结论、`audit_page_scale.py` 关于 0 字节 CSS"被 index.html 引用着"的过期结论，都按当前事实改写。
15. 删除 `perception-page-shell.css`（0 字节、无人引用）与 `semantic-page.css.backup`（97KB 备份）。

## 三、打包与审计问题（同一轮）

| 问题 | 证据 | 处置 |
| --- | --- | --- |
| 14.06 MB 生成物被打进插件 ZIP（压缩后 10.19 MB，占整包 25.2%） | `theme-preview.html` 单文件 13.9 MB、压缩后占 25.2%；另有 `v2-surface-preview.html`、`_probe-timeline.html`、`_migration_bridge.*`、0 字节 CSS | 删除；`build_theme_preview.py` 默认输出改到 `build/`；`build_v2_release.py` 的 `EXCLUDED_FILES` 补齐生成物条目 |
| 打包体积 | 入包 raw 74.13 MB / deflate 40.37 MB → **59.35 MB / 30.03 MB**，ZIP 约 40.6 MB → **30.4 MB（−25%）** | 同上 |
| `_migration_bridge.html/.js` 是手工诊断页，硬编码了 `backup/create`、`legacy/apply`、`host/start` 等写路由，任何能打开 Dashboard 的人都能直接触发，绕过正常界面 | 文件内 19 条白名单路由；全仓零引用 | 删除（安全项，不只是减重） |
| 主题审计长期红 | `audit_theme_tokens.py` 报 6 个悬空令牌 + 5 个文件超基线；`navigation.css` 基线 20 已降到 17 | 悬空令牌归零；`confirmation-dialog.css` 遮罩改用 `--scrim`；缓存图表数据序列色作为**明确例外**写进基线并注明理由。现「全部通过」 |
| 缓存分析图的 8 个色值 | `maintenance-page.css` 数据序列色（绿/青/紫/金） | 保留为基线例外：图表数据编码换主题会改变同一张图的读法 |
| `test_w1_fixture_harness.py` 导入即失败 | 依赖两个已内建的独立 provider 目录，`unittest` 发现阶段整轮判错 | 加 `skipUnless`，现 13 项跳过、exit 0 |
| 三个默认值与 `_conf_schema.json` 不一致 | `daily_token_soft_limit` 0 vs 800000（0 在软限额里等于"不限"，等于把开关开了却没限）；`profile_id` "preview-1" vs "main"；`feed_url` "" vs 默认 RSS | 三处都对齐 schema，注释写明后果 |

## 四、验证

- 布局不变量：25 组（5 条路由 × 5 档宽度 1440/1280/900/390/320）全部通过——没有横向溢出、左栏盒宽等于栅格列宽、缩略态面板从主体顶部开始、手机导航条 ≤64px（实测 50）、手机上小屋的可见性跟随 away 状态、面板标题栏有说明文字。
- 键盘：Tab 到左栏可见实色焦点环（截图 `build/design-audit/verify-shots/focus-ring.png`）；跳转链目标可解析。
- 页面审计：`audit_page_scale.py` 通过；`audit_theme_tokens.py` **全部通过**（此前 3 项失败）。
- 清单：`sync_framework_page.py --check` 为空。
- 前端测试：`tests/test_shell.cjs` 15、`tests/test_theme_registry.cjs` 16、`tests/test_home_environment.cjs` 5、`tests/test_entrance.cjs` 42，全部通过。
- 浏览器检查：`tools/check_layout_polish.cjs` 通过。
- 打包：用 `build_v2_release.sources()` 实算入包集合（未写盘），2,228 文件。

对照截图在 `build/design-audit/shots-before/` 与 `shots-after/`（同一路由、同一视口）。该目录在 `.gitignore` 的 `build/` 下，不进版本库。

## 五、发现但**没有**改的

按证据强弱排列，前三条是明确的缺陷。

1. **`check_product_page.cjs` / `check_navigation_page.cjs` 无法通过**：两者都在等 `#cottage` iframe 里的 `[data-host-badge].host-connected`、`[data-native-extension-host="live"]`，而 `[data-host-badge]` 在全仓**只被读、从未被渲染**（`app.js:336`、`memory-page.js:281`、`state-page.js:689` 三处读的都是不存在的元素）。基线 `HEAD` 上同样失败，属既有失效的验收脚本，不是本轮回归。顺带说明这三处守卫是死代码。
2. **`#navigationDialog`（全部功能）打不开**：`#navigationList` 有内容、`data-nav-route` 有处理，但没有任何元素带 `data-open-navigation`。它用的是 `app.js` 的 `navGroups`（四组：小屋/塑造角色/互动能力/连接与运行），与左栏的 `RAIL_GROUPS`（三组）是两套导航模型——接上之前需要先决定用哪一套。
3. **字体 9.4 MB 首屏无 preload、未子集化**：MiSans 两个字重各 4.8/4.9 MB，占首屏 15.6 MB 的 63%。子集化需要构建期工具链与字形覆盖评估（生僻字、Emoji 组合），不适合在本轮顺手做。
4. **死 CSS 与未引用样式表**：按本轮统计，`styles.css` 约 45%、`semantic-page.css` 约 44% 的规则选择器在页面 HTML/JS 里零引用；`topic-page.css`、`workspace-theme.css` 既不在 `index.html` 的引用列表、也没有被其它样式表 `@import`（`workspace-theme.css` 里的 `.extension-*` 因此没有生效来源）。清理要逐条核对动态拼接的类名，`prune_dead_css.py` 有工具但需人工复核，未在本轮动手。
5. **断点仍有 42 个不同宽度值**：本轮只统一了手机断点（650→760）与左栏相关分支，其余页面的 43 个值没有动——收益不确定、回归面很大。
6. **`data-room-asset` 写入后无人读取**、`styles.css` 的 `.rail-link`/`.topbar` 等旧外壳样式仍在，属同一批未清理的历史层。
7. **`docs/BUILD_STATUS.md`（292 KB 手工流水）与 4 个 `docs/page-designs/*-preview.html`**：后者已从安装包排除（`contact-rhythm` 例外，它是生成器读的模板）；前者定位待定，属文档策略而非代码问题。
8. **根目录运行产物**：`build/` 126 MB、`.verify-shards/` 25.6 MB（其中约 40 个子目录 ACL 拒绝枚举）、`data/` 里有活 SQLite。都已在 `.gitignore` 且不入包，但违反"源码根不放运行产物"的约定。`.verify-shards` 的 ACL 异常需要单独修复，本轮没有动。
9. **错误处理面**：生产代码 978 处 `except Exception`、157 处静默 `pass`；3 处把原始响应体/WS body 写日志（`bilibili_live.py:1502`、`blivedm/clients/ws_base.py:493`、`web.py:153`）。与本轮主题无关，未改。

## 六、下一步

1. 决定「全部功能」用哪套导航模型，接上 `data-open-navigation`，把两套导航合并成一份数据源。
2. 修或退役 `check_product_page.cjs` / `check_navigation_page.cjs`（它们现在必然会失败，等于两个失效的验收口）。
3. 字体子集化 + `preload as=font`，或首屏改用系统字体栈。
4. 死 CSS 清理与断点收敛，按页面分批做，每批跑一次定向检查。
5. 版本号与 CHANGELOG 在下次出包时统一写（本轮改动尚无版本号，`metadata.yaml` 仍是 2.2.0）。
