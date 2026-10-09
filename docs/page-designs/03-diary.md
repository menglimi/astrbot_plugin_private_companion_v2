# 03 · 日记（`life` 视图 `diary`）

> **状态：设计目标（2026-09-29 信息架构调整）与现状并存**——本页新增承接 `role.life` 唯一可写归属（从决策 B3 迁入）、移除工作区内嵌表单；迁移未实施处均已标注，实施清单见 [02-state.md](02-state.md) 第六节。

代码位置：入口 `renderViewPanel('diary')`（`pages/陪伴小屋/app.js:428-435`）→ `product.workspace('life','archive')` 生成 iframe 并注入 `CompanionWorkspaceBundle.life`（`product-page.js:534-547,558-562`）。构建源：`pages/日记与生活/workspace.html` + 同目录 `app.js`；家具入口 desk/bed/lounge 也映射到本工作区的 archive/sleep/reading 页签（`app.js:1445-1461`）。

## 一、页面功能

日记、梦境、阅读、睡眠与执行记录的工作台：看四类私人记录的原文与来源，做显式的书写/作息操作与已知失败的_retry_；同时承载生活例程、睡眠与写作偏好。休息时回复判定与醒后补看移到主动联系页的开口闸门，和消息开口时机放在一起。

## 二、展示部分（life 工作区，iframe 内）

| 分区 | 内容 | 证据（构建源） |
| --- | --- | --- |
| 范围条 | 当前角色 / 私聊对象 / 运行状态 / 生活日程 | `pages/日记与生活/workspace.html:18-21` |
| 作息区 | 自动睡眠范围 / 唯一执行窗口 / 下次入睡 / 当前睡眠唤醒 | `workspace.html:23-28` |
| 页签四视图 | 日记与梦境 / 阅读书架 / 睡眠记录 / 执行记录 | `workspace.html:48-53` |
| 私人书写 | 日记正文、梦境记录、原文（add_text）、更正与撤回原文入口、提取索引、失败重试表单 | `workspace.html:54-81`；动作定义 `pages/日记与生活/app.js:66-115,183-192` |
| 阅读书架 | 阅读进度与书评（作品正文与图片由提供方持有） | `workspace.html` 阅读分区 |
| 执行记录 | 来自任务账本的执行条目 | 同上 |

数据端点：`GET …/life`（状态与记录）、3 秒轮询（`pages/日记与生活/app.js:157`）；iframe 内请求经父页白名单代理到 `relative(role().life_api)`（`product-page.js:582-583`）。

## 三、配置部分

> **设计变更（2026-09-29）**：`role.life` 的唯一可写归属从决策 B3 迁到**本页**；日记工作区的内嵌表单移除，消除双入口（R1）。

### `role.life`（日记、梦境与休息）— 23 项，window+role（共享 owner），立即生效

后端定义 `companion_v2/role_work/life/configuration.py:27`；消费 `role_work/life/rest_gate.py`、journal。

- **目标结构**：统一配置编辑器 `lifeConfigWorkspace`（spec 组 `life`，按 section 过滤）挂在本视图面板顶部——`renderViewPanel('diary')` 内、life 工作区 iframe 之上，走 `POST /config/configure`（section=`life` → `DiaryAndRestManagement`，`configuration_api.py:35-48`）。这里展示 `routine`、`sleep`、`writing`；`rest` 与 `backlog` 由主动联系页的开口闸门工作区挂载。
- **移除项**：工作区内嵌 `config-form`（`pages/日记与生活/workspace.html:31-47`：启用/时区/日记时间/入睡/阅读/摘要约 7 项，经 `send("configure")` 即 `POST {life_api}/command`，`pages/日记与生活/app.js:183`）——它是 23 项的子集，保留即双入口、两份草稿。移除后需重建 `workspace-bundle.js`（`tools/sync_framework_page.py`）。
- **现状**：编辑器已按页面职责过滤挂载；生活工作区表单仍由 iframe 提供记录与执行操作，配置保存统一走宿主配置接口。

### 23 项按功能划分（spec 标签实查）

| 功能簇 | 字段 |
| --- | --- |
| 总开关 | `enabled` 启用生活例程 |
| 日记写作 | `diary_enabled`、`diary_time`（HH:MM）、`timezone`、`diary_style_prompt` |
| 作息（角色共享，`RoleSharedSettingsOwner`） | `sleep_enabled`、`sleep_time`、`sleep_timezone`、`sleep_minutes` |
| 阅读 | `reading_enabled` |
| 梦境与衍生 | `derive_enabled`、`dream_theme_candidates`、`dream_mixed_themes_enabled`、`dream_intimate_theme_enabled`、`dream_afterglow_mode` |
| 休息时段回复判定（四段） | `enable_rest_reply_simulation`、`rest_reply_mode`、`rest_reply_probability`、`rest_reply_llm_threshold`、`rest_reply_active_windows`、`rest_reply_awake_grace_minutes` |
| 休息期补看 | `enable_rest_backlog_reply`、`rest_backlog_max_messages` |

前端兜底校验：`HH:MM` 用 `input[type=time]` + audit 正则；IANA 时区用 `Intl.DateTimeFormat` 试构造（`config-editor.js` audit 约定，audit 返回单个错误码字符串）。

## 四、边界与空态

- 没读到目录或对象无 `life_api` 时给「正在读取/该对象没有此私聊工作区」占位，不出空 iframe（`product-page.js:538-546`）。
- 嵌入态隐藏工作区里的宿主启停按钮（`embedded-bridge.js:54`）——启停只在宿主管理页做。
- 梦境是主观感受，不当现实事实；执行记录来自任务账本，不推算。

## 五、后端情况

- 路由：`GET /life`（读私日记与角色作息）、`POST /life/command`（管理）——`astrbot_host/life_api.py:21-22`。
- 服务：`companion_v2/role_work/life/management.py` `RoleLifeManagement`（`life_api.py:9,35`）。
- 多目标模式：per-target `/host/targets/{id}/roles/<digest>/life`（`multi_api.py:83-100`）。

## 六、相关设计稿与复核

- 状态与身体配置 → [02-state.md](02-state.md)（状态页）；决策 B3 现状 → [07-decision.md](07-decision.md)。
- 复核：`sed -n '/const SECTIONS/,/^}/p' astrbot_host/configuration_api.py`（`life` 条目）；`node` 导出 spec 的 `life` 组（命令见 [README.md](README.md) 第五节）。
