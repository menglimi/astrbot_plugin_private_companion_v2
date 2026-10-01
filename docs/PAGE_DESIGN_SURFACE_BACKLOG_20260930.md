# 拓展页剩余面的真实读写面

日期：2026-09-30。用途：**动手写某一页之前先读它对应的一节**。
每条都来自本仓当前源码，不是设计稿里的设想。与
`V2_CONFIG_SURFACE_20260928.csv` 的分工是：那份记"字段有没有落地"，
这份记"页面该画什么、数据从哪来、和邻页怎么分界"。

## 已交付（从零创作，四页）

memory / contact / learning / models。规格见各自 `*-page.css|js` 与
`docs/page-designs/*-preview.html`。

## 已有独立页但未按新规格重做（八页）

下表是这次要处理的主体。**左列是 app.js 的容器 id**——
挂载一律走"容器在就挂、不在就卸"，不要写 `manageTab === 'x'` 那种分支
（外壳重排过一次，按 tab 名判断的写法已经全部失效）。

| 页面 | 容器 id | 后端 API | 前端现状 |
| --- | --- | --- | --- |
| 角色状态 | `#roleStateWorkspace` | `state_api.py` | `state-page.js` 286 行 |
| 回复 | `#replyWorkspace` | `reply_api.py` | `reply-page.js` 397 行 |
| 表达学习 | `#expressionWorkspace` | `reply_api.py` 的 `/expression*` | `expression-page.js` 118 行 |
| 语义 | `#semanticWorkspace` | `semantic_api.py` | `semantic-page.js` 195 行 |
| 感知提供方 | `#perceptionProviderWorkspace` | `perception_api.py` | `perception-page.js` 211 行 |
| 原生感知 | `#nativeEnvironmentWorkspace` 等 5 个 | `native_perception_api.py` | `perception-native-page.js` |
| 产出/能力 | `#productWorkspace` 系 | `configuration_api.py` | `product-page.js` 683 行 |
| 工作台 | `#workbenchWorkspace` 系 | 多域 | `workbench-page.js` 816 行 |
| 备份 | `#backupWorkspace` | `backup_api.py` | `backup-page.js` 438 行 |

## 完全没有独立页（由 app.js 的 consoleSections 兜着）

这些是这次要找 "多融入创意设计" 的地方——它们现在是一堆控件平铺。

### 感知 `renderPerception` → `perception_api.py`

- `GET  /perception` / `POST /perception`（读/存提供方设置）
- `PROVIDERS = {"screen": "astrbot_plugin_screen_companion",
  "reality": "astrbot_plugin_reality_companion"}`（`perception_api.py:19`）
- **边界**：这一页只管"提供方接进来没有、地址是什么"；
  原生感知自己的开关与新闻诊断在 `native_perception_api.py`，是另一页。
  两页画同一批 offering 就会重复。

### 决策 `renderDecision` / 行动 `renderAction` / 产出 `renderOutput`

目前由 `render*Original()` 生成 consoleSections。真实数据来源要先确认：
这三页很可能读 `configuration_api.py` 的 `image_review` / `busy_gate` /
`reaction` / `budget` 四段（见下文配置族）。**动手前必须实测一次**
`GET /config?sections=` 返回了什么，别照名字编。

### 表达 `renderExpression` → `reply_api.py`

- `GET /reply/expression`、`POST /reply/expression/configure`
- 与"表达学习"页（`expression-page.js`）的分界要定清楚：
  一个是当前表达设置，一个是学习记录，而两者都在 `reply_api.py` 里。

### 自我 `renderGovernance`

无专表端点，数据来自人物设定与关系。**这一页的素材最薄**，
需要先确认它到底能读到什么，否则会做成空壳。

### 人物设定工坊 `renderPersonaPage` → `persona_workshop_api.py`

- `GET /persona`（当前人格与其草稿历史）
- `POST /persona/command`，action ∈ `{save, restore}`；
  字段 `expected_current / name / note / persona_id / text / version_id`
- 这是一个**版本历史 + 草稿**的状态机，不是单纯一个文本框。

### 关系与权限 `renderIdentityPage` → `relationships_api.py` + `object_access`

- `GET /relationships`、`POST /relationships/command`（审阅关系理解）
- 权限拓扑另外来自 `identity_policy`，要确认有没有读出口。

### 治理与维护 `renderMaintenancePage`

数据来自诊断族。`docs/ALIGN_DIAGNOSTICS_AND_REPAIR_SLICE.md` 说明完整诊断控制面
**尚未完成**，所以这一页能画的只有已落地那部分，别画未来功能。

### 开始使用 `renderSetupPage` → `setup_api.py`（七条，最完整）

```
GET  /setup/status      首次配置进度
GET  /setup/targets     找到这个 bot 能触达的会话
POST /setup/target      为绑定目标选人格
POST /setup/start       启动角色并等一条消息
GET|POST /setup/review  读它准备好的回复
POST /setup/connect     完成配置并开始真实发送
POST /setup/disconnect  停止真实发送
```
注意 `docs/SETUP_*.md` 里的教训：**页面路径必须相对**（绝对路径会让前缀叠两次，
全族 404），且 `delivery_mode` 有离开指纹的存量兼容陷阱。

### 宿主管理 `renderHostPage` → `multi_api.py` / `web_api.py`

- `multi_api.py`：`/host/status`、`/host/preview`、`/host/batches`、`/host/targets/`、
  `/host/{profile}`
- `web_api.py`：`staging` 前缀（单目标）
- **两套宿主模式**（单目标 staging vs 多目标共享宿主）是这一页最容易画错的地方，
  见 `docs/CORE_HOST_MANAGEMENT_PAGE_20260924.md`。

### 外观与设置 `renderAppearancePage` → `appearance-page.css` + `theme.js`

无后端 API：主题、密度、圆角、字号、动效全是 `:root` 上的 `data-*` 属性。
真实来源是 `tokens.css` 的六套色板与 `theme.js` 的写入。
**这一页已有 63 行 CSS 但无独立 JS**，要补。

### 资料与维护 `renderData` → `legacy_api.py` + `backup_api.py`

- `legacy_api.py`：`GET /legacy`（发现 V1 数据）、`GET /legacy/plan`（只读转换）、
  `POST /legacy/apply`（写入）
- `backup_api.py`：`/backup/create`、`/backup/inspect`、`/backup/restore/preview`、
  `/backup/restore`、`/backup/pending`
- 迁移三步的"先看后做"保证落在 `plan_token` 上（见
  `docs/` 里 V1 迁移那批记录）：**没有 plan 就不能 apply**，页面必须体现这条闸门。

## 配置族（多页共用，别各画一套）

`configuration_api.py`：`GET /config?sections=` + `POST /config/configure`。
`SECTIONS` 五个：quota / image_review / busy_gate / reaction / budget。
回执**包一层** `{result, status}`——与 reply/expression/memory 的扁平回执不同。

## 每页动手前的固定四步

1. 实测端点：真跑一次 `GET`，把返回体的字段抄下来（别照名字猜）。
2. 定该域专属视觉语言：这一页的数据**形状**决定它该怎么画，
   不是套一个通用卡片网格（见 `feedback_no_uniform_templates`）。
3. 定与邻页的边界：两页画同一批数据是这一批最容易犯的错。
4. 写完之后跑四项：`node --check`、缓存串、`sync_framework_page.py`、该页测试 +
   `audit_page_scale.py`（新页若用 `--fs-*` 就必须进 `MIGRATED`，否则审计会报）。
