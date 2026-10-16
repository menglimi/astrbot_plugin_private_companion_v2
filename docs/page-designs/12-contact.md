# 12 · 主动与联系（`manage/contact`）

> **归档设计说明：** 本文中的关系级额度和模型尝试上限已于 2026-10-16 退役，不能作为当前页面或配置合同。当前唯一主动次数上限是每个私聊窗口每日实际联系数；参见[当前自动联系合同](../CORE_AUTOMATIC_CONTACT_AND_HISTORY_SLICE.md)。

代码位置：`renderContactPage`（`pages/陪伴小屋/app.js`）；主动联系工作台挂载 `contactPreferencesWorkspace`，开口闸门状态挂载 `contactWorkspace`，下方统一挂载 `replyGateConfigWorkspace`（`busy_gate` 的 reply/contact 分段与 `role.life` 的 rest/backlog 分段）；联系节奏仍由 `CompanionStatePage` 的 contact 段提供。

## 一、页面功能

"她什么时候来找我"——陪伴的核心配置页，也是最大的配置类（`proactive.contact` 160 项 + `busy_gate` 7 项）。页面先给出节律和当前闸门判定，再提供主动联系偏好与开口闸门设置；忙碌回复延迟、主动联系恢复、休息时回复判定和醒后补看集中在开口闸门。

> 代码注释记录了历史：本页正文曾调用从未定义的 `renderPreferences()` 导致整页渲染中断；160 项大组曾四层全缺（后端 GroupEditor/SECTIONS/spec/挂载点），现已补齐，按 23 段渲染。

## 二、展示部分

| 分区 | 内容 | 证据 |
| --- | --- | --- |
| 联系节奏（现状与快速修改） | `state-contact.js` 渲染「主动联系偏好」只读摘要：联系开关、当前条件、间隔与额度、沉默门槛、免打扰、暂停截止、宿主/模型状态、关系共享上限（只读提示）、各联系目的当前条件 details | `state-contact.js:121-135` |
| 主动联系偏好（完整设置面） | 挂载头「四层继承：默认写入窗口层，安装/角色/关系层的值会被继承；两个关系级配额只能在安装/角色/关系层设置」+ 23 段编辑器；外部触发源按天气、预警、资讯、饭点/纪念日、网络探索、设备动作、生成上下文和余额分组，均可在本页直接编辑 | `/config` |
| 开口闸门 | 先显示当前授权、模型、宿主、免打扰、曲线与暂停判定；设置区再编辑忙碌回复延迟、主动联系恢复、休息回复判定与醒后补看，并提供直达入口 | `/config` |

生效口径：联系节奏改动**从下一轮主动评估开始生效**；开启总开关时会一并签发这个对象的主动联系授权（`app.js:1190` 挂载头文案）。

触发源的直接编辑与「感知」页是互补关系：主动联系页负责该角色何时采用天气、资讯、设备、余额等材料作为开口契机；感知页负责按来源查看实况、授权和更细的上下文配置。主动联系页的来源卡片同时提供到感知二级分区的状态跳转，但跳转不会替代本页控件。

## 三、配置部分

### ① `proactive.contact`（160 项）— installation+role+relationship+window，立即生效，通道 `/config`

挂载 `configEditors('contactPreferencesWorkspace',['proactive.contact'])`（`app.js:1192`）；`SECTIONS` 为 `ProactiveContactManagement`（`configuration_api.py:35-48`）。按功能划分（字段前缀实查，`proactive/configuration.py:220`）：

| 功能簇 | 项数 | 内容 |
| --- | ---: | --- |
| 联系目的 `purpose.*` | 45 | 15 个目的（想念/关怀/互动/修复/闲聊/问候/分享生活/作品阅读/资讯/接旧话题/邀请/提醒/环境变化/饭点/屏幕观察）× 各自 `enabled`/`weight`/`pause_until`（PURPOSES 定义 `:19-25`） |
| 全局开关 | 4 | `enabled`、`pause_until`、`note`、`style_prompt`（+`automatic_enabled`） |
| 节奏引擎 `proactive_*` | 14 | burst 突发（gap min/max、max_messages）、closing 收尾（contacts_threshold、grace_minutes）、hour_activity 小时活跃曲线、intensity 强度档、persona_judge 人格评审（threshold/daily_limit/cache/exempt）、share_probability |
| 余额感知 `balance_*` | 9 | 开关、查询间隔、低/临界阈值两套、币种标签、是否带金额、冷却 |
| 资讯 `news_*` | 8 | 间隔、开关、热读、hot_result_count、hot_sources、source_kind/uid/url |
| 屏幕瞥视 `screen_glance_*` | 8 | 开关、日限、冷却、followup 三项、goodnight 延迟/开关 |
| 去重 `dedup_*` | 8 | 总开关、last_message 三项、min_overlap_ratio、min_shared_tokens、policies、sent_window、weather_window |
| 时段锚点 | 13 | `quiet_*` 4（静默时段+时区）、`greeting_*` 4（早/午/晚窗口+idle）、`insomnia_*` 4 + `allow_insomnia_night_message`、`enable_daily_greetings` |
| 事件源 | 21 | `meal_*` 4、`weather_*` 4、`web_exploration_*` 4、`official_*` 3（气象预警）、`external_event_self_link_*` 3、`date_checkin_*` 2、`important_date*` 2、`appointment_*` 3（部分计 21 内有交叠，见注册表） |
| 动作类 | 6 | `voice_action_*` 3、`poke_action_*` 3 |
| 节流与预算 | 10 | `max_contacts_24h`、`max_attempts_24h`、两个关系级 `max_relationship_*_24h`（窗口层禁写）、`unanswered_*` 3 未回应降速、`silence_*` 2、`interval_seconds`、`idle_seconds`、`event_max_age_seconds`、`generation_history_limit`、`history_max_chars` 等 |

四层继承实现：`with_contact_fields`（`proactive/configuration.py:351-357`）；关系级配额的窗口层禁写（`:369-373`，编辑器字段合同同步去掉 window 节点 `configuration/management.py:404-413`）。

### ② `conversation.busy_gate`（繁忙回复闸门）— 7 项，window，立即生效，通道 `/config`

挂载 `configEditors('replyGateConfigWorkspace',['busy_gate'])` 的 `reply` 与 `contact` 分段（`SECTIONS` 的 `BusyGateManagement`）。字段（spec 标签实查）：

| 字段 | 含义 |
| --- | --- |
| `busy_reply_gate_enabled` | 启用繁忙延后 |
| `busy_reply_min_delay_seconds` / `..._max_delay_seconds` | 最短/最长延后（秒） |
| `busy_reply_proactive_resume_buffer_minutes` | 忙碌结束后主动恢复缓冲（分钟） |
| `busy_activity_keywords` | 忙碌关键词（命中判忙；单条 ≤24 字、最多 64 条） |
| `busy_exclude_keywords` | 排除关键词（优先级更高） |
| `busy_urgent_keywords` | 紧急关键词（立即回复） |

### ③ `role.life` 的开口闸门分段

`rest` 分段负责休息时回复判定，`backlog` 分段负责醒后补看材料。它们与 `busy_gate` 一起挂在 `replyGateConfigWorkspace`，日记页只展示 `routine`、`sleep`、`writing` 三个分段。

### ④ 联系节奏的快速修改（`role.state` 组的 contact 段）

`renderRoleState('contact')` 挂的是状态工作台 contact 段：`state-contact.js` 定义节奏/沉默/免打扰/联系目的/天气（CAP 五级预警）字段的表单与校验（6 位小数、datetime→ISO），提交 `POST {state_api}/command` action=`contact.configure`。**注意与 ① 的分工**：contact 段是"此刻为什么没来找你"的现状与快捷修改；主动联系页的来源卡片仍提供完整触发条件的直接编辑，感知页只按来源筛选同一合同的相关分段。总开关签发主动联系授权仍由 contact 状态命令负责。

## 四、边界与空态

- 候选池与执行历史**没有查询合同**：页面不展示"下一次会说什么/候选列表"。
- `configEditors` 在无对象时渲染提示行（`app.js:1226-1231`）。
- 决策 B4、表达 D5 都只放跳转卡指向本页（R1 已收敛，`app.js:1149-1151,1165`）。

## 五、后端情况

- `/config` 的 `proactive.contact`、`busy_gate` 组 → `ProactiveContactManagement`、`BusyGateManagement`（`configuration_api.py:35-48`）。
- 组定义 `companion_v2/proactive/configuration.py:220`；消费 `proactive/service.py`、`scheduling.py`（余额感知 `balance_events.py`、天气 `weather_events.py`、屏幕 `screen_events.py` 是**主动联系的触发事件源**，不是感知输入——同两份数据、两个用途，感知页那侧是环境注入）。
- contact.configure → `role_work/state/management.py` `StateManagement`。

## 六、相关设计稿与复核

- 联系节奏现状面板与状态工作台共用 → [02-state.md](02-state.md)、[07-decision.md](07-decision.md)；天气/新闻的环境注入侧与触发条件互相跳转 → [06-perception.md](06-perception.md)。
- 复核功能簇：`grep -oE "^\s{4}[a-z_]+" companion_v2/proactive/configuration.py | sort | uniq -c | head -40`；三方对账（SECTIONS↔spec↔挂载）命令见 `docs/PAGE_DISPLAY_AND_CONFIG_DESIGN_20260929.md` §七。
