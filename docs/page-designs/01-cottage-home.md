# 01 · 小屋总览（`life/home`）

> **2026-09-29 首页改版（已实施，按设计稿批注）**：①左栏顶部在画面能力接入后显示**穿搭图卡**（`updateRailBrand`，`app.js:136-158`；图源合同 = integration manifest 的 `extensions` 清单中 image 内置拓展的 `cover`/`outfit_image` 字段，当前 manifest 无此字段→显示空帧说明；能力未接入则继续显示插件信息；**比例 1:1**）；②左栏专题配置上移且去组标题、能力配置组首位新增「状态」入口（`shell.js` RAIL_GROUPS）；③镜头复位（`data-voxel-reset`）与布置（`data-detail="arrange"`）收进场景容器右上角悬浮（`.stage-overlay`，原「全景/巡游/布置」为未接线死按钮，已移除）；④家具速览条从场景上方移到场景下方，点选后面板直接承载对应工作区（日记书桌/睡眠与梦境→life 工作区，生活挂历→状态工作台，成长花架→`growthMarkup()`，其余保留说明卡，`renderFurniturePanel`）——**这些家具工作区属于首页内容，未随本轮页面清空而移除**；⑤右栏只留「状态」「生活安排」两卡（拓展能力卡移除）；⑥场景比例放宽（`clamp(400px,54vh,620px)`）。其余页面的内容暂清见 [README.md](README.md) 变更记录③。详见 [02-state.md](02-state.md)。

代码位置：路由与导航 `pages/陪伴小屋/app.js:50-59`；首页面板 `renderHomePanel`（`app.js:364-388`）；右栏 `renderShellSide`（`app.js:314-322`）；生活观察四视图（`app.js:831-880`）；家具目录 `directory` 常量（`app.js:695-710`）。体素场景：`assets/voxel-room.js` + `assets/voxel-source/`，陈设编辑 `room-editor.js`。

## 一、页面功能

只读总览，回答三件事：她现在怎么样（状态）、今天发生了什么（记录与日程）、有哪些能力在用（家具与接入状态）。是全站的默认落地页，不承担任何业务配置。

## 二、展示部分（全部只读）

| 分区 | 内容 | 数据来源 |
| --- | --- | --- |
| 体素小屋 | 庭院、14 件家具、天气、时段、全景巡游；点选家具打开内容，目录反向定位 | 本地 Three.js 场景；天气/时段为环境预览（`STRUCTURE.md` 记录，代码见 `assets/voxel-room.js`） |
| 右栏 · 状态 | 「此刻在做什么」（life.activities 中 active 项）+ 心理能量/心情/健康/睡眠/饥饿/忙碌程度六项 + 「状态来源」行 | `product.stateCard`（`product-page.js:449-463`），数据来自 `loadSummary()` 并发 GET 各 `role()["*_api"]`（`:360-367`） |
| 右栏 · 生活安排 | life.activities 前 4 条（标题、时间、状态）+「完整记录」链接 | `product.scheduleCard`（`product-page.js:464-474`） |
| 今日日程 | 已完成/进行中/尚未发生的四项安排 | `loadSummary()` 的 life_api（首页与右栏共用数据） |
| 生活观察四视图 | `records` 日记与梦境（life.journals 前 4 条）、`timeline` 生活轨迹（activities）、`state` 状态变化（心情/身体/睡眠/饥饿/忙碌 + 能量）、`impact` 交互影响 | `observationFilters`（`app.js:831`），渲染 `:855-880`；全部出自 `loadSummary()` |
| 记忆概况 | 最近 3 条事实（representation/predicate）+「记忆工作区/人物与关系」入口 | `product.memoryCard`（`product-page.js:498-507`，memory_api `limit:3`） |
| 家具与能力目录 | 14 项：desk 日记书桌、calendar 生活挂历、bed 睡眠与梦境、lounge 阅读角、album 相框与相册、garden 成长花架、radio 见闻电台、content 创作书架、image 画面工作室、together 共处电话、game 游戏棋桌、screen 屏幕台、reality 现实设备台、live 直播与表演；按「待处理/可用」分组 + 筛选 + 搜索 | `app.js:695-710`，渲染 `:742-766`；可用性按 V2 内置拓展的装配、启停及运行状态呈现，目录来自 `manifest.extensions`（`:711-725`），明确不使用 config-snapshot 判状态 |

## 三、配置部分

**无业务配置组。** 唯一可写项与存储位置：

1. **布置房间**：家具摆放/收纳/布局撤销重做，按角色存浏览器 `state.roomLayouts[product.scopeKey()]`（`app.js:6,771`）；保存只写 localStorage，不写业务配置。
2. **外观偏好**（主题/密度/圆角/字号/动效）：`localStorage` 键 `companion-v2-theme/-density/-radius/-type-scale/-motion`（`product-page.js:53-59`）。

## 四、边界与空态（代码现状）

- **便签与提醒目前没有渲染面板**：`state.notes` 只是初始值（`app.js:36`），示例表单已删（`app.js:1602-1606` 注释）；搜索索引里的「便签」项会落到兜底「这件事在别处」（`app.js:1445-1473`）。首页不展示便签/提醒计数。
- 「交互影响」视图**有意空态**：需要带来源的互动记录，没有来源时不推算情绪变化（`app.js:878`）。
- 主动候选池、用量余额在首页无任何展示（无查询合同）。
- `config-snapshot.js` 只是发行版默认壳（botName「陪伴角色」、空 capabilities，`config-snapshot.js:3-8`），仅用于角色名兜底，不提供面板数据；真实数据一律来自页面桥请求，读不到时 `unavailableReason` 区分「正在读取/失败码/无此工作区/尚无记录」（`product-page.js:430,662-666`）。

## 五、后端情况

首页没有自己的路由；所有数据复用各领域只读路由（多目标模式按 target×role 生成，`astrbot_host/multi_api.py:83-100`）：

| 数据 | 路由 | 后端服务 |
| --- | --- | --- |
| 目标目录 | `GET /page/targets`（`page_api.py:20`） | `target_inventory`（multi_api.py:72） |
| 状态/生活/成长/记忆/关系 | `GET /state`、`/life`、`/growth`、`/memory`、`/relationships` | role_work/state、role_work/life、role_work/growth、memory、relationships 各 management（见各 API 文件头部 import） |
| 能力目录 | `GET /integration/manifest`（`integration_api.py:25`） | V2 内置拓展目录（只读，需 dashboard 身份 + ObjectAccessPolicy） |

## 六、相关设计稿与复核

- 状态与日程下钻 → [02-state.md](02-state.md)；日记下钻 → [03-diary.md](03-diary.md)；记忆下钻 → [04-memories.md](04-memories.md)；家具里的能力配置 → [06](06-perception.md)/[09](09-output.md)/[14](14-models.md) 等对应页。
- 复核首页面板：`grep -n "renderHomePanel\|observationFilters\|const directory" pages/陪伴小屋/app.js`。
