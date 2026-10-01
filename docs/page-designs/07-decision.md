# 06 · 决策（`manage/decision`，B 段）

> **状态：设计目标（2026-09-29 信息架构调整）与现状并存**——B3 由「状态工作台 + role.life 编辑器」改为两张引用卡（状态类配置迁状态页与日记页）；现状代码仍未迁移，逐条标注，实施清单见 [02-state.md](02-state.md) 第六节。

代码位置：`renderDecision`（`pages/陪伴小屋/app.js:1136-1156`）。模块：`memory-settings-section.js`（B1 记忆策略）、`state-page.js`/`state-editor.js`/`state-maintenance.js`（B3 现状挂的状态工作台，迁移后归状态页）、`config-editor.js` spec（B1 person、B5 group_participation）。

## 一、页面功能

回答"角色**怎么判断**"：记什么、记多少（B1）；关系理解去哪审（B2）；身体与心理状态怎么维护（B3）；什么时候主动开口（B4，引用卡）；在群里怎么参与（B5）。

## 二、展示与配置（五个分区）

### B1 记忆策略

- 展示：`consoleMountHead('启停与上限','保存后立即生效')` + 工作台加载态（`app.js:1139`）。
- **`memory` 34 项**（installation/role/window，立即生效）：`#memorySettingsHost` 经 `GET /memory/settings` + `POST /memory/settings/command` 读写（`memory-settings-section.js:120-121`，工作台 `CompanionWorkbench.create({group:"memory"})`，字段名出站改写为 `memory.*`）。分四段：
  | 段 | 内容 |
  | --- | --- |
  | core 记忆与注入 | 启停、注入条数/字符上限等 |
  | reflection 定时整理 | 反思调度节奏 |
  | episode 经历整理 | 经历阈值与整理（episode_settings.py 的 4 项在此组） |
  | habit 习惯与推荐 | 习惯阈值 |
- **`person` 2 项**（installation/role/window，立即生效，通道 `/config`）：`acquaintance_enabled` 启用熟人卡、`acquaintance_card_chars` 卡片最长字数。挂载 `configEditors('personConfigWorkspace',['person'])`（`app.js:1139`）。
- 跳转：「事实与来源」→ memory 页（纠错/钉选/遗忘在治理工作台，改动回流到这里，`app.js:1139`）。

### B2 关系与理解

只有一张跳转卡「相识目录与授权 → identity 页」（`app.js:1141`）——关系理解的审阅/采用在 identity 页的 relationships 工作区（见 [05-identity-relationships.md](05-identity-relationships.md)），本页不重复挂工作区。

### B3 角色自身（设计变更：改为引用卡）

- **设计目标**：本分区不再持有任何控件，只放两张引用卡——
  - 「状态与身体 → 状态页」：饥饿/健康/生理期/心情动力学/巡视/QQ 展示（`role.state` 61 项）的展示与编辑都在状态页（[02-state.md](02-state.md)）。理由：这些是**身体的维持与演化**，不是"怎么判断"的决策逻辑；状态与日历同属生活时间线。
  - 「日记与作息 → 日记页」：`role.life` 23 项（写作偏好、作息、休息时段回复判定）迁日记页（[03-diary.md](03-diary.md)）。
- **现状（未实施）**：`renderRoleState()`（`app.js:1143`）= 状态工作台（`#roleStateWorkspace`，展示面板：指标卡、共享睡眠日程、QQ 展示回执、临时状态，见 [02-state.md](02-state.md) 第三节）；`role.state` 61 项经 `state-editor.js` 九类草稿编辑，统一 `POST {state_api}/command`（action：`contact.configure`/`configure`/`cycle.align`/`calendar.presence`，`state-editor.js:38-49,138`），operation_key 幂等 + sessionStorage 待核对 + rebase（`:54-99,129-155`）；字段库五组（状态维护/自动规划/生理期参数/心情动力学/每日状态巡视，`state-maintenance.js:52-58,196-197`）+ QQ 展示设置（`state-editor.js:197-200`）。**10 项有意不接**（`cycle_*_mood` 6 项等，闭包检查仍读其 80 字上限；`online_status_enabled` 因保存时撤销 grant 不平铺）。
- **现状（未实施）**：`configEditors('lifeConfigWorkspace',['life'])` 也挂在本分区（`app.js:1143`）——与日记工作区内嵌表单构成双入口，按本设计一并迁出。

### B4 主动与沉默

只有一张跳转卡「联系节奏与免打扰 → contact 页」（`app.js:1149-1151`）。代码注释明说原因：同一工作区挂两处会各自持草稿，用户会看到旧值；每个配置组只有一个可写归属页（`app.js:1177-1187` 注释）。

### B5 群聊参与

- 说明头「三条独立闸门：三项都不会自己发起对话，仍要等一条群消息打开这一轮」（`app.js:1151`）。
- **`conversation.group_participation` 20 项**（installation/role/window，立即生效，通道 `/config`）：`configEditors('groupParticipationConfigWorkspace',['group_participation'])`。按功能划分：
  | 功能簇 | 字段 |
  | --- | --- |
  | 氛围与线索 | `enable_group_social_context` 群聊氛围参考、`enable_group_mood_detection` 识别群聊氛围、`enable_group_roleplay_strength` 扮演强度、`enable_group_moments` 记录名场面、`enable_group_moment_portrait` 识别发言者线索、`enable_group_persona_denoise` 原人格去噪 |
  | 主动插话 | `enable_group_interjection`、`group_interject_min_interval_minutes`、`group_interject_max_daily`、`enable_group_interjection_feedback`、`group_interject_feedback_window_seconds` |
  | 跟读与打断复读 | `enable_group_repeat_follow`、`group_repeat_count_distinct_users_only`、`group_repeat_trigger_threshold`、`group_repeat_follow_probability`、`group_repeat_interrupt_probability`、`..._probability_step`、`group_repeat_interrupt_text`、`group_repeat_window_seconds` |
  | 接梗护栏 | `enable_group_joke_guard` |
- 群唤醒一整套 `group_wakeup_*` 24 项、群冷场守卫 4 项、三条群安全闸 3 项都在 `conversation.presentation` 组里，当前可经表达 D1 的回复工作台编辑（见 [10-expression.md](10-expression.md)）。

## 三、接入方法小结

| 组 | 通道 | 幂等/冲突机制 |
| --- | --- | --- |
| memory | `GET /memory/settings` + `POST /memory/settings/command` | expected_edit_token + operation_key（经 CompanionWorkbench） |
| person、group_participation | `POST /config/configure`（section=person/group_participation） | operation_key + edit_token（`configuration_api.py:108-141`） |
| role.state | `POST /state/command`（action=configure 等）——**设计变更后归状态页**，本页只留引用卡 | operation_key + expected_revision/view_token（`state-editor.js:134-138`） |
| role.life | `POST /config/configure`（section=life）——**设计变更后归日记页** | 同 person |

## 四、边界与空态

- B2/B4 只有跳转卡，是 R1 收敛后的**有意留白**，不是缺陷。
- 状态工作台空态见 [02-state.md](02-state.md) 第五节；`configEditors` 在无 `reply_api`（未初始化对象）时只渲染提示行「先在宿主管理中初始化一个对象与角色…」+ 重新读取（`app.js:1226-1231`）。

## 五、后端情况

| 路由 | 服务 |
| --- | --- |
| `/memory/settings`、`/memory/settings/command`（`memory_api.py:34-35`） | memory 组 owner（`memory/configuration.py`） |
| `/state`、`/state/command`（`state_api.py:20-21`） | `role_work/state/management.py` `StateManagement` |
| `/config` 的 person、life、group_participation 组 | `AcquaintanceManagement`、`DiaryAndRestManagement`、`GroupParticipationManagement`（`configuration_api.py:35-48`） |

## 六、相关设计稿与复核

- 记忆治理工作台 → [04-memories.md](04-memories.md)；联系节奏 → [12-contact.md](12-contact.md)；状态面板与配置细节 → [02-state.md](02-state.md)。
- 复核分区：`sed -n '1136,1156p' pages/陪伴小屋/app.js`。
