# 02 · 状态页（`life/state`，侧栏「生活」组）

> **2026-10-06 更新：** 已按 [状态子页设计图](status-page-20261006/IMPLEMENTATION.md) 完成 12 个子页面的配置区域并接入小屋：直接编辑、分组控件、相关设置与保存操作条。以下 2026-09-29 记录中的占位页、范围和行号为当时状态；本轮实际呈现与验证以新实施记录为准。

> **状态：部分实施（2026-09-29）。** 视图更名（`life/state`）与侧栏入口已落地；同日的「内容暂清」把**状态视图正文**也换成了占位说明（侧栏入口与视图本身保留；小屋「生活挂历」家具仍承载同一状态工作台，内容仍可达）。`role.state` 的归属迁移、决策 B3 引用卡与 `role.life` 迁日记页**未实施**（原 `renderRoleState` 工作台与 `renderViewPanel` 原文分别保留在 `app.js` 与备份 `data/companion_v2_page_backups/20260929-before-page-clear/`）。本稿取代原「02 · 日程」稿。

代码现状位置：视图分发 `renderViewPanel('schedule')`（`pages/陪伴小屋/app.js:423-427`）→ `renderRoleState()`（`app.js:1059`，挂载点 `#roleStateWorkspace`）→ `mountPanelWorkspaces` 挂 `CompanionStatePage`（`app.js:467`）。模块：`state-page.js`（宿主）、`calendar-editor.js`（日历编辑器）、`state-editor.js` + `state-maintenance.js`（编辑编排与字段库）。

## 一、页面功能

回答"她现在怎么样、接下来有什么已定的事"，并成为**身体与状态类配置的唯一入口**：

1. **看**：角色当前身体与心理状态（指标卡、共享睡眠日程、QQ 平台展示、临时状态）。
2. **管状态**：`role.state` 全部配置（身体/周期/心情/巡视/QQ 展示/自动规划）——设计变更：从决策 B3 迁入，本页是唯一可写归属（R1）。
3. **管计划**：角色计划的完整编辑（新建/改整组/只改一次/提醒/取消）。

改名理由（对应 2026-09-29 讨论结论）：饥饿/健康/生理期是**身体的维持与演化**，不是"决策"逻辑；它们与日历同属生活时间线——状态按时间演化、维护任务按 `maintenance_minutes` 间隔跑、生理期本质是周期日历。原「日程」页实际渲染的就是状态工作台+日历，名实不符。

## 二、导航与侧栏（已按 2026-09-29 设计稿实施）

- **左栏顺序调整**（`shell.js` RAIL_GROUPS）：专题配置移到最前且**不再显示组标题**；「状态」作为**能力配置组第一项**（设计稿批注落位），其后是感知…自我；设置组不变。
- 「状态」是 life 整页视图：rail 项渲染 `data-shell-view="state"`（`shell.selectView`），aria-pressed 跟随 `shell.view`；点击同步 `route/lifeTab` 与深链接（`app.js` 的 `data-shell-view` 处理器）。
- `navGroups`（「全部功能」对话框）首页组加入 小屋/状态；`searchIndex` 的「日程」项更名「状态」。
- 旧深链接 `#life/schedule` 在 `navigate`/`syncFromHash` 里别名到 `state`。
- 与初稿的差异：初稿提议在 rail 头部新增「生活」组（小屋/状态/日记）；按设计稿批注改为「能力配置组首位」，日记不进 rail（仍从首页面板与对话框进入）。

## 三、展示部分（state-page.js，现状实查，迁移后不变）

| 分区 | 内容 | 证据 |
| --- | --- | --- |
| 状态行 | `statusLabel` 徽标（disabled/unknown/unavailable）+ 版本 revision + 下次维护时间 | `state-page.js:171-173` |
| 指标卡 | 饥饿、健康、心理能量、睡眠感受、生理期阶段、心情/忙碌、情绪四轴 | `state-page.js:174-180`（构造 `:85-104`） |
| 共享睡眠日程 | 计划时间/时区/时长、执行窗口、下次入睡/醒来、当前执行状态 | `state-page.js:115-118` |
| QQ 平台展示回执 | 正在输入/自定义短状态的配置与生效原因、历史回执与请求标识 | `state-page.js:142-150`（原因映射 `:16-29`） |
| 当前临时状态 | conditions 列表 | `state-page.js:184` |
| 角色计划与日程 | 计划列表（含重复规则与例外），分页走 `status.calendar.next_cursor` | `calendar-editor.js:203-214,213` |

数据端点：目标目录 `GET page/targets`（`state-page.js:207`）；状态本体 `GET {state_api}`（带 `after_id` 游标，`:221`；15 秒自动刷新，仅读、页面可见、编辑器不在交互，`:194-197`）。

状态看板中的睡眠与忙碌入口会导航到「主动联系 → 开口闸门」，并自动切换到当前闸门判定及其设置区；睡眠作息仍在「日记与生活」维护。

## 四、配置部分

### `role.state`（61 项）— window 作用域，立即生效 — **唯一可写归属：本页**（设计变更）

字段定义 `companion_v2/role_work/state/configuration.py:18`；消费 `state/maintenance.py`、`humanized.py`。不走 `/config` 统一编辑器，编辑经状态工作台草稿编辑器 `state-editor.js`，统一 `POST {state_api}/command`（action 四种：`contact.configure`/`configure`/`cycle.align`/`calendar.presence`，`state-editor.js:38-49,138`），带 operation_key 幂等 + sessionStorage 待核对 + rebase（`:54-99,129-155`）。

按功能划分（字段库 `state-maintenance.js:7-58`）：

| 功能组 | 内容 | 代表字段 |
| --- | --- | --- |
| 状态维护 | 后台维护开关与间隔、日程读写开关、**饥饿与健康模拟** | `enabled`、`maintenance_minutes`、`calendar_enabled`、`hunger_enabled`（默认开）、`health_enabled`（默认开） |
| 日程与规划 | 角色全局日程开关、连续/编排模式、自动规划参数、年度日历、天气开关/地点/坐标/预警区域/时效与生活偏好；统一由本工作区编辑 | `calendar_enabled`、`schedule_simulation_mode`、`planning_*` |
| 生理期 | 模拟开关（默认关）、阶段模式（基础三阶段/六阶段）、周期时区、首次定位、波动与不适、表达偏好、六阶段 ×（天数/精力偏移 -50~30/表达引导 ≤512 字） | `cycle_*` 26 项；`cycle.align` 周期校准单独 action（`state-maintenance.js:119-127`） |
| 心情动力学 | 总闸、更新概率、单轮最大幅度、回归基线半衰期 | `mood_*` 4 项 |
| 每日巡视 | 开关、巡视时刻、记录保留天数 | `daily_state_patrol_*` 3 项（`humanized.py` 消费） |
| QQ 展示 | 正在输入/刷新秒数/自定义短状态、日程公开文案 | `typing_*`、`presence_*`（`state-editor.js:197-200`） |
| 联系节奏（contact 段） | **不在本页**——contact 段的可写归属是主动与联系页（`renderRoleState('contact')`，`app.js:1190`） | `state-contact.js` |

10 项有意不接（`cycle_*_mood` 六个氛围词等，闭包检查仍读其 80 字上限；`online_status_enabled` 因保存时撤销 grant 不平铺）。

### 日历命令（非配置组）

`calendar-editor.js`：`calendar.create/revise/exception(move\|skip)/remind/cancel` 五类 action（`:134-148`），表单字段与幂等/冲突机制见原稿（标题 ≤256、IANA 时区、频率/间隔/次数/时长 1–1440、DST 策略；sessionStorage 待核对 + rebase）。

### 本页不放

- `role.life`（23 项）→ 日记页（见 [03-diary.md](03-diary.md) 设计变更）。
- `proactive.contact` 节奏与额度 → 主动与联系页；决策 B4 仅引用卡。

## 五、边界与空态

- 状态页移除「人格状态归属」独立说明栏，当前角色名称保留在状态看板。配置开关只显示「已开启/已关闭」；看板底部读取真实维护回执，显示排队过期、执行失败、取消或结果未确认，避免把开关开启误报为维护正常。维护关闭或宿主暂停时不显示下次更新时间。
- 对象无 `state_api`：「该对象没有角色状态」（`state-page.js:163-164`）；授权类错误码清空目录并停表（`:198-203`）；桥超时 `bridge_unavailable`（`:269-279`）。
- 同一工作区组件挂两处会各自持草稿（`app.js:1177-1187` 注释结论）——本设计把 `#roleStateWorkspace`（state 段）收敛为**只在本页挂载**；contact 段只在主动与联系页。

## 六、实施清单（迁移时逐项落点，均为现状行号）

进度：**#1–8、#11 已实施**（2026-09-29）；#9、#10（决策 B3 引用卡、`role.life` 迁日记页）未实施；#12 文档持续同步。原「全景/巡游」两个 stage-bar 按钮实为未接线死按钮（无 data 属性、无监听），重排时以可用的 `data-voxel-reset` / `data-detail="arrange"` 重新接入场景右上角悬浮位。

| # | 改动 | 位置 |
| --- | --- | --- |
| 1 | `lifeTabs`：`['schedule','calendar-days','日程']` → `['state','activity','状态']` | `app.js:61` |
| 2 | `renderViewPanel`：case `schedule` → `state`，标题「状态」，副题含生理期与计划 | `app.js:423-427` |
| 3 | 首页按钮 `data-shell-view="schedule"`「日程与状态」→ `"state"`「状态与日程」 | `app.js:382` |
| 4 | 家具「生活挂历」`tab:'schedule'` → `'state'` | `app.js:697` |
| 5 | 观察页脚 `data-life="schedule"`「完整日程」→ `"state"`「状态与日程」 | `app.js:843` |
| 6 | `searchIndex`「日程」项 →「状态」 | `app.js:1486` |
| 7 | `shell.js`：`VIEWS` 的 `schedule` → `state`；`RAIL_GROUPS` 头部加「生活」组（小屋/状态/日记，前两项 `data-shell-view`） | `shell.js:46,127-150` |
| 8 | `navigate`/`syncFromHash`：`tab==='schedule'` 别名到 `'state'`；life 非首页时同步 `shell.selectView(tab)`，home 时清 view | `app.js:99-122` |
| 9 | 决策 B3：`renderRoleState()+configEditors('lifeConfigWorkspace',…)` → 两张引用卡（状态→本页、日记与作息→日记页） | `app.js:1142-1143` |
| 10 | `role.life` 统一编辑器迁日记视图（见 03 稿） | `app.js:428-435,1143,1255` |
| 11 | `navGroups` 首页组更名「生活」并加入 状态/日记 | `app.js:50-59` |
| 12 | 文档同步：本目录 README/01/03/07/12 | `docs/page-designs/` |

## 七、后端情况

- 路由：`GET /state`、`POST /state/command`（`astrbot_host/state_api.py:20-21`）→ `companion_v2/role_work/state/management.py` `StateManagement`（`state_api.py:8,37`）。
- 多目标模式：per-target `/host/targets/{target_id}/roles/<digest>/state`（`multi_api.py:83-100`）。路由不因页面改名而变。

## 八、相关设计稿

- 日记与作息 → [03-diary.md](03-diary.md)；联系节奏 → [12-contact.md](12-contact.md)；决策 B3 引用卡 → [07-decision.md](07-decision.md)；首页状态卡 → [01-cottage-home.md](01-cottage-home.md)。
- 复核现状：`grep -n "schedule" pages/陪伴小屋/app.js pages/陪伴小屋/shell.js | grep -v scheduleCard`。
