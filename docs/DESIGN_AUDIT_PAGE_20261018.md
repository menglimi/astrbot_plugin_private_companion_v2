# 拓展页设计审计：不合理之处

日期：2026-10-18。范围：唯一公开拓展页「陪伴小屋」（`pages/陪伴小屋/`）加四个嵌入工作区。只读审计，不改代码。

一句话结论：**功能面已经很全，问题不在"缺功能"**，而在四层——进入路径、离开保护、同一件事的多种做法、以及中英混排与术语漂移。

## 一、会让用户丢东西或找不到（优先修）

### 1. 草稿守卫是"点名制白名单"，新增编辑面没被纳入

离开页面时的判断只问三个来源：

```js
// app.js:227
function pageLeaveDecision(){
  if(window.CompanionStatePage?.canLeave?.()===false)return false;
  return window.CompanionWeatherSourcePage?.canLeave?.()??true;
}
// app.js:1058 guardUnsaved / app.js:1082 beforeunload 都只问工作台
pending = window.CompanionWorkbench?.dirtyEditors?.() || [];
```

也就是说只有「工作台内核 + 状态页（含日历编辑器）+ 天气源页」会拦。下面这些**有草稿、有保存按钮，但换页/关标签页时不问一声**：

| 页面 | 证据 |
| --- | --- |
| 房间布置（布局、撤销重做） | `room-editor.js` 有 draft 与保存，0 处脏标记 |
| 角色档案草稿 | `role-profile-draft.js`：draft 125 次、保存 19 次、守卫 0 |
| 模型与连接 | `models-page.js`：draft 286 次、保存 103 次、守卫 0 |
| 感知页（分段表单） | `perception-native-page.js`：draft 36、保存 12、守卫 0（草稿只存在内存里，切分段能留住，切页就没了） |
| 语义校验 | `semantic-page.js`：draft 14、保存 11、守卫 0 |
| 开始使用向导 | `setup-guide.js`：draft 27、保存 21、守卫 0 |

后果：编辑到一半点左栏另一项，改动静默消失；关标签页时只有状态页和天气源页会弹系统确认。

### 2. 状态页与日记不在左栏

`shell.js:93-117` 的 `RAIL_GROUPS` 全是 `[id, icon, label]` 三元组，`kind` 永远为空，所以 17 个条目全是 `data-shell-section`；而 `VIEWS = ["directory","observation","state","diary"]` 四个视图**没有任何左栏入口**。注释（`shell.js:92`）说这是刻意的："状态由首页右侧看板进入，避免与人格总览重复占位"。

但状态页是**最大的配置面之一**（85 个注册字段、13 个功能图块 + 4 张环境卡），「外观与设置」这种低频页却在左栏。结果：用户一旦离开状态页，只能回首页再点右栏「查看与更新」或底部「状态与日程」。日记同理。

### 3. 移动端左栏只剩图标

```css
/* shell.css:286 */ .shell-nav-link span { display: none; }   /* ≤760px */
/* shell.css:221 */ #homeShell .shell-nav-title, #homeShell .shell-nav-link span { display: none; }
```

17 个入口在 ≤760px 全部退化成 17 个图标，名称只留在 `title` 属性里（触屏没有 hover）。图标里还有一半是自选的 lucide 近义图标（`orbit` 表示事实与经历、`shapes` 表示产出），没标签就是猜。

### 4. 「全部功能」浮层是死 UI

`index.html` 里有 `<dialog id="navigationDialog">`，`app.js:4674` 也有 `data-open-navigation` → `showModal()` 的处理器，但**全页没有任何元素带 `data-open-navigation`**（0 处）。一个完整的浮层导航、写好了打开/关闭/跳转三条分支，却没有任何入口。`STRUCTURE.md:74` 自己记着"待接线项"。

### 5. 二级状态不进 URL

一级路由是好的：`navigate()` 用 `history.pushState/replaceState` 写 `#manage/expression/voice` 这类地址（`app.js:279-282`），`syncFromHash()` 也能还原（`app.js:319-328`）。但下面这些"页内状态"不在 URL 里，刷新一律回该页默认视图：

- 状态页打开了哪个功能图块（`activeFeature`）
- 记忆页「记录 / 设置」路由（`memoryWorkspaceRoute`，`app.js:4283` 的处理器里改）
- 感知页分段（`activatePerceptionTab('config-*')`）
- 任意工作台里打开了哪个配置分段

于是"把某一页发给别人"只能给到一级页面，对方还要自己点两层。

## 二、同一件事有几种做法（一致性）

### 6. 改配置有三种交互范式

| 范式 | 例子 | 落点 |
| --- | --- | --- |
| 整页工作台 + 分段 + 底部保存 | 大多数配置（30 个 `mountConfigEditor`） | `workbench-page.js` |
| 页面内业务浮层 | `state-home-settings`（状态设置）、`roleProfileDraftDialog`、`roleProfileMigrationDialog`、`growth-confirm` | 各自模块 |
| 页面内就地卡片 → 打开表单 | 状态页 13 个图块、感知页 3 个分段 | `state-page.js`、`perception-native-page.js` |

三种范式的保存/取消/重置位置、脏提示、失败回执都不一样。用户要为同一件事（改一项设置）学三套。

### 7. 术语漂移（同一概念多个名字）

| 概念 | 出现的写法（次数） |
| --- | --- |
| 回复闸门 | 开口闸门 8、回复阀门 3、回复闸门 1、闸门 17 |
| 正在输入 | 正在输入 12、输入提示 10、输入状态 2 |
| 状态维护 / 每日巡视 | 状态维护 19、后台状态维护 4、每日状态巡视 3、巡视 24（**这是两个不同功能**，却共用"维护/巡视"四个字） |
| 角色 / 人格 | 角色 809、当前人格 38、人格共享 12（`state-page.js:410` 的「人格共享」作用域标签） |
| 产出 / 创作 / 作品 | 产出 34、创作 27、原生创作 5、作品封面 1 |

其中"状态维护 vs 每日巡视"最危险：两者分别是 `state.maintenance_minutes`（后台推进状态）与 `daily_state_patrol`（定时巡视记录），首页却只显示一句"状态维护已开启 · 每 N 分钟更新"。

### 8. 中英混排的装饰性眉标，同一个文件里都不统一

`maintenance-page.js` 有 14 处英文大写眉标，同时又有中文眉标（运行配置、当前排查范围、组件检测）：

```
SOURCE / BRIDGE UNAVAILABLE · CACHE / EXTERNAL SOURCE · PROCESS / MEMORY
DIAGNOSTICS / 01 · CACHE / 02 · SIGNALS / 02 · CHECKS / 03 · TOKENS / 00 · TRACE / 03
REPLY / 7 DAYS · DAILY / P50 · OBSERVABILITY · COMPANION / SIGNAL ROOM
```

其他页面的眉标是中文（`contact-page.js`：「回复与补看」），状态页又是第三种写法：`state-page.js:391` 用 `STATE · ${title}`，但同一行的 `patrol` 分支写成「维护」，于是同一排图块里只有它一个中文。

`app.js` 还有三处：`QZONE EXTENSION`(2891)、`CAPABILITIES`(3067)、`WORLD / SOURCES`(3442)。

### 9. 内部需求编号漏到界面

`maintenance-page.js:1546` 的段落标签是 `REQ-041 / 本次管理请求`，`:1676` 的常见问题标题是「REQ-041 结果为什么只显示状态？」。需求编号对用户没有意义，还暗示"这页是按需求单拼的"。

### 10. 加载与动作文案各写一套

| 动作 | 现有写法 |
| --- | --- |
| 保存进行中 | 正在保存…（20）、正在保存（3）、保存中（3） |
| 读取进行中 | 正在读取…（12）、正在读取（11+2） |
| 取消 | 取消（22）、取消编辑（2）、放弃草稿（3）、放弃改动（确认框）、回去保存（确认框） |

同类文案没有共用组件：空状态类文案 170 处（暂无／尚无／还没有／没有任何）、"正在…"145 处，都散在 34–38 个文件里手写。

### 11. 断点没有尺度

全站 CSS 出现 **43 个不同宽度**：360/380/400/420/430/480/500/520/560/620/640/650/680/700/720/740/760/761/800/820/850/860/880/881/900/901/920/950/960/980/990/991/1000/1050/1080/1100/1120/1121/1180/1190/1280/1440/1740。

其中 5 组是 ±1px 的成对补丁（760/761、880/881、900/901、990/991、1120/1121），说明是在边界上反复打补丁。高频档位是 650(32 次)、760(30)、520(16)、900(16)、1100(10)——看起来真正需要的只有 4–5 档。

### 12. Tab 语义只做了一半

全页 `role="tab"` 31 处、`role="tabpanel"` 26 处、`aria-controls` 24 处。方向键导航是实现了的，但存在 tab 找不到对应 tabpanel 的情况（26 vs 31），读屏器会说"标签页"却报不出面板。图标这边是好的：`aria-hidden="true"` 117 次对 `data-lucide` 111 次，覆盖到位。

## 三、信息架构与承载

### 13. 概念被切碎，没有一处能看全景

- **天气**分三处：数据源在 `_conf_schema.weather`（感知页的「天气数据源」工作区，`app.js:1797`）、模拟在 `role.state.planning_weather_*`（状态页天气图块）、主动关心在 `proactive.contact.weather_checkin_*` / `official_weather_alert_*`（主动联系）。
- **记忆**分三处：策略 `memory.*`（事实与经历 → 记忆策略）、熟人卡 `person.learning.*`（关系与权限 → 成员编辑器）、来源与经历（记忆页的另一路由）。

用户问"为什么它今天没提天气"时，要同时看三个页面才知道是哪一层关了。

### 14. 单页承载过重，没有分层

左栏 17 个条目 + 4 个首页视图 + 23 个配置分区 + 709 个注册字段。没有"基础 / 进阶"或"常用 / 全部"的分层，也没有把 23 个分区按"第一次就能用"和"调优才需要"区分开。第一次进来的用户面对的是完整控制台。

### 15. 文档漂移

`pages/陪伴小屋/STRUCTURE.md` 是 2026-09-24 的，仍在描述：14 项家具目录、"生活观察不另设一级页面"、三列生活观察布局。现状是 17 项左栏、状态与日记作为二级视图、away 模式 PiP。文档里唯一还准确的自述是第 74 行那个"死浮层待接线"。

### 16. 仓库卫生

`pages/陪伴小屋/shell-preview.html`（19.7 MB）与 `shell-preview-mock.html`（19.3 MB）**被 git 跟踪**。虽然已经在 `tools/build_v2_release.py` 的 `EXCLUDED_FILES` 里（不进交付包），但 39 MB 生成快照留在源码目录与仓库历史里，和"源码目录不放生成物"的工程约定相反。

## 四、核对过、不建议改

- **左栏三组结构**本身是对的（专题配置 / 能力配置 / 设置），问题只是移动端丢标签（第 3 条），不需要重排。
- **away 模式下的 PiP**：面板让位、房间缩到右下角，是有意的取舍，不是 bug。
- **跳过链接、面板标题焦点交接、`aria-current`**：上一轮已补齐，检查过是对的。
- **只读诊断**（展示通道回执、拓展装配状态、余额/用量）：都是运行数据，不是配置缺口，不该改成可编辑。
- **忙碌 / 位置只读并给跳转**：页面写明了"忙碌是日程的产物""位置由对话内容自然形成"，理由成立。
- **主题令牌化**：六套色板一致性由 `audit_theme_tokens.py` 守着，现状全绿。

## 五、已按此顺序做完的部分（2026-10-18 晚）

| # | 动作 | 实际落点 | 状态 |
| --- | --- | --- | --- |
| 1 | 草稿守卫改成注册制 | 新增 `pages/陪伴小屋/page-guards.js`；`app.js` 的 `pageLeaveDecision` / `guardUnsaved` / `beforeunload` 统一走 `dirtyDrafts()`；六个编辑面导出 `isDirty()`（房间布置在 app.js 里比较布局快照） | ✅ |
| 2 | 状态页与日记进左栏 | `shell.js` 新增「生活」组（`kind="view"`），左栏变 4 组 19 项 | ✅ |
| 3 | 移动端保留标签 | `shell.css` ≤760px 改成图标+文字两行、`min-width:58px`，仍是可横滑的一条 | ✅ |
| 4 | 接上「全部功能」浮层 | `index.html` 的 `rail-foot` 加入口；`shell.js` 导出 `railGroups()`，浮层与左栏共用同一份分组与标签（旧的 `navGroups` 只保留左栏没有的二级页） | ✅ |
| 5 | 去英文眉标与内部编号 | `maintenance-page.js` 14 处英文眉标改中文、`REQ-041` 两处去掉；`app.js` 三处（`QZONE EXTENSION`/`CAPABILITIES`/`WORLD / SOURCES`）；`state-page.js` 的 `STATE ·` | ✅ |
| 6 | 统一动作/加载文案 | 「保存中」三处补省略号、「正在读取」两处补省略号（按钮进行态统一 `保存中…`，状态文案统一 `正在保存…`） | ✅（只做同义收敛，未强并为 34 个文件的单一组件） |
| 7 | 术语对齐 | 「回复阀门／回复闸门」4 处统一为「回复方式」；「后台状态维护」与「每日状态巡视」各自写明区别 | ✅ |
| 8 | 断点收敛 | 不做规则合并：43 个宽度里除 8 档页面尺度外，其余是**单组件容器阈值**（如感知页三列在 800/860 逐级降两列），合并会改布局。改为在 `shell.css` 顶部写明页面尺度与「组件阈值不属于页面尺度、要收敛得改 `@container`」 | ✅（改为定档与说明） |
| 9 | 二级状态进 URL | `#manage/memory/settings`、`#manage/perception/<分段>`、`#life/state/<图块>`；`navigationDestination` 加白名单、`navigate` 里补应用、`currentNavigationHref` 用 `secondarySubtab()` 读数；状态页新增 `openFeature()` 与路由事件 | ✅ |
| 10 | 补 tabpanel / aria-controls | 语义页「表情／群词义」与维护页「Token 统计来源」两组补全（tablist + tab + 一个 tabpanel）；模型页三组 tab 仍是纯筛选按钮，**未改**（要改得为它们的内容容器加 id，属于 models-page 的单独一次改动） | 部分 |
| 11 | 更新 STRUCTURE.md、处理快照 | 顶部加 2026-10-18 增补；重写「全局导航」与新增「离开页面前的未保存提示」；`shell-preview*.html` 加进 `.gitignore` 并从索引移除（本地保留） | ✅ |

### 仍需后续处理

- **模型页三组 tab**（`data-img-view`/`data-model-tab`/`data-model-sub`）：按钮是筛选开关，样式靠 `aria-selected` 驱动；要么给内容容器补 id + `role="tabpanel"`，要么整体降级为 `aria-pressed` 并同步改 CSS，两者都要单独回归这个大文件。
- **断点真正收敛**：把 `semantic-page.css`、`maintenance-page.css`、`models-page.css` 里的组件阈值改成 `@container`（维护页已有 `@container maint-diagnostics` 的先例）。
- **加载/空状态组件化**：本次只统一了同义文案，170 处空状态与 145 处「正在…」仍是各文件手写。


| 11 | 更新 `STRUCTURE.md`；`shell-preview*.html` 移出 git 或改名为 `.gitignore` 的生成物 | 文档 / 仓库 | 小 | 低 |

第 5、10、11 项是纯文案与标记，可以一次做完；1、2、4、9 是行为改动，建议合并成一次提交；3、8 会动布局，要单独跑移动端与平板回归。

## 六、未验证 / 边界

- 没有做真机/截图回归：断点数量、文案计数、术语计数都是对源码的静态统计（脚本在 `build/design-audit/`，不进交付包）。改完之后只跑了结构/行为测试与三项页面审计，没有在浏览器里逐屏点过。
- 第 6 条的"三种范式"是按代码入口分的，没有统计各页面真实使用频率；也许某个浮层几乎没人用。
- 第 14 条"单页承载过重"是判断而非测量：没有做任务完成率或首次可用性测试。
- 断点只做了定档与说明（`shell.css` 顶部），没有合并任何组件阈值——`@container` 迁移需要逐页回归。
- 移动端改成"图标 + 文字"后，一条横向滚动条的实际手感（19 个入口、每项约 58px）没有在真机上验证。
- 第 9 条只覆盖三个二级状态；工作台内的分段切换仍不进地址栏。
- 第 10 条只补了语义页与维护页两组，模型页三组仍是筛选按钮式的 `role="tab"`。
- 本轮为验证改动的测试改动：`test_maintenance_page.cjs`（`REQ-041` → 中文标签、`SOURCE / NOT CONNECTED` → `来源 / 未连接`）、`test_role_profile_apply.cjs`（注入 test seam 的锚点跟着新的 `return` 行）、`tools/check_product_page.cjs`（四组 19 项导航）。
