# 13 · 学习与反思（`manage/learning`，L 段）

代码位置：`renderLearningPage`（`pages/陪伴小屋/app.js:1214-1220`）；表达学习挂载点 `#expressionWorkspace`（`renderExpressionLearning` `app.js:1207-1209`，`app.js` 挂 `CompanionExpressionPage`）；growth/library 编辑器挂载 `app.js:1253,1256`。模块：`expression-page.js`（118 行薄适配层）。

> 代码注释（`app.js:1210-1213`）：旧版本页有 10 张 boundaryCard 全是归属说明；现在只留三块有真实端点的（表达学习、成长与技能、书架），其余改为指向真实页面的入口行。旧 `growth` 死页签已删；`product.growthMarkup()` 已导出但**无挂载点**（全目录 grep 仅 product-page.js 自身）。

## 一、页面功能

角色从经历里学到什么：表达与说话习惯学习（取样→候选→人工采纳→轮换降权）、成长与技能开关、书架与阅读偏好。

## 二、展示与配置（三个分区）

### L1 表达与说话习惯学习

- 说明头「取样与轮换：从角色自己已确认送达的回复里取样，转成待审候选；只有人工采纳的规则才会注入，且用过之后会被降权」（`app.js:1216`）。
- **`expression.learning` 10 项**（window，立即生效）——`expression-page.js` 是薄适配层：只声明标题/说明/字段顺序/文案与组合约束，读写经 `CompanionWorkbench.create(group:"expression.learning")` 走 `GET {reply_api}/expression` + `POST {reply_api}/expression/configure`（`expression-page.js:67-71,101-113`）。保存前页面派发组合约束 audit：`sample_limit ≥ min_samples`、`rotation_candidate_limit ≥ rules_per_turn`，违反报 `expression_settings_invalid`（`:57-63`）。
- **`role.growth` 2 项**（window，立即生效）+ **`role.growth.skills` 2 项**（window+role 共享 owner，立即生效）：`configEditors('growthConfigWorkspace',['role_growth','role.growth.skills'],'成长与技能')`（`app.js:1216`）。字段：`read_enabled` 读取成长记录、`proposals_enabled` 允许提出成长建议；`custom_skills` 自定义技能领域、`schedule_influence_strength` 影响日程的强度。
- 跳转：「风格提示词与表达规则 → expression 页」——候选的采纳/驳回/退役与已采纳规则的使用次数**当前没有独立控件**，只有这句入口说明（`app.js:1216`）。
- 成长进度的审阅动作（确认/修订/暂停，`POST {growth_api}/command`）在首页 growthCard 的对话框里（`product-page.js:632-644`），待审进度列表走 `GET /growth/progress`（`astrbot_host/growth_api.py:49`）。

### L3 书架与阅读

- 说明头「书架只保存书目、来源引用与阅读状态，作品正文与图片由提供方持有，所以小说与漫画共用同一套设置」（`app.js:1217`）。
- **`library` 12 项**（role，下一轮生效）：`configEditors('libraryConfigWorkspace',['library'])`。按功能划分：
  | 功能簇 | 字段 |
  | --- | --- |
  | 书目管理 | `enabled` 启用书架、`manual_entries_enabled` 允许手工添加书目、`max_entries_per_page` 每页条目数 |
  | 书评与打分 | `reviews_enabled`、`rating_enabled` |
  | 偏好注入 | `preference_influence_enabled` 把阅读偏好写进提示词、`preference_min_ratings` 形成偏好的最少打分数、`preference_max_terms` 单次提示词最多列出的作品数 |
  | 主动分享 | `reading_excerpt_chars` 单轮读取字数上限、`min_interval_hours` 两次主动开口最短间隔、`share_probability` 主动分享进展概率、`ask_probability` 主动询问对方阅读概率 |
- 后端 `library/configuration.py:14` → `role_work/reader.py` 消费。

### 记忆沉淀与每日反思

只有挂载头说明（「来源 → 新记忆条目；增量、重复安全，不回写改写已成型记忆」）+ 跳转卡「反思结果与记忆治理 → memory 页」（`app.js:1218`）。反思调度的节奏当前随 `memory` 组的 reflection 段（决策 B1），本页无独立控件。

## 三、边界与空态

- 表达候选审阅列表无独立控件（只有跳转说明）；黑话/群词义的管理在感知页 A2 的语义工作台（`/semantic` 的群词义 tab），本页没有。
- 未连桥/无对象/工作台未载三种提示（`expression-page.js:87-98`）。

## 四、后端情况

| 路由 | 服务 |
| --- | --- |
| `GET /reply/expression`、`POST /reply/expression/configure`（`astrbot_host/reply_api.py:25-26`） | `expression/configuration.py` 的 expression.learning owner（经 `ReplyManagement`） |
| `GET /growth`、`POST /growth/command`、`GET /growth/progress`、`POST /growth/progress/command`（`growth_api.py:47-50`） | `role_work/growth/management.py`、`access_management.py`、`progress_management.py`（`growth_api.py:11-13`） |
| `/config` 的 role_growth、role.growth.skills、library 组 | `RoleGrowthManagement`、`RoleGrowthSkillsManagement`、`LibraryManagement`（`configuration_api.py:35-48`） |

## 五、相关设计稿与复核

- 表达规则本体 → [10-expression.md](10-expression.md)；语义/黑话 → [06-perception.md](06-perception.md)；反思结果 → [04-memories.md](04-memories.md)；成长进度审阅 → [01-cottage-home.md](01-cottage-home.md)（首页 growthCard）。
- 复核：`sed -n '1214,1220p' pages/陪伴小屋/app.js`。
