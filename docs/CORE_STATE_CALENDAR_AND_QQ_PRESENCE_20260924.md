# 日历、角色状态与 QQ 展示接入

共享宿主现已提供[每个私人 target/role 的状态入口](CORE_MULTI_TARGET_STATE_20260924.md)，从 `/host/status` 中读取 `state_api` 后使用同一 GET/POST 合同。请求固定到目标和人格，命令不接受查询参数；QQ 展示回执按原上下文过滤，重启可恢复原回执而不重复发送。

后续补齐见[生理期拟人与连续周期](CORE_ROLE_CYCLE_20260924.md)：本记录最初的 `cycle` 文字槽已增加可选结构化适用性、持久时间线、三阶段/六阶段和 `cycle.align` 管理命令。以下保留首批实现与测试证据。

2026-09-24。本批承接 V1 的 TIME01–07、STATE04–08 与输入状态展示相关功能，完成独立 V2 数据、统一宿主、角色工具和认证管理 API 的本地闭环。没有迁移 V1 用户数据，没有在线重载或调用真实模型、QQ 账号。

## 已实现

| 范围 | 当前行为 |
| --- | --- |
| 日历 | 角色计划、用户自述候选、待确认约定分别归属；完整修订历史、版本冲突检查、操作重试回执。复用日/周/月/年重复规则、时区、月末和 DST 策略，支持单期改期或跳过。 |
| 约定和提醒 | 角色工具只能提出约定；人类管理入口显式接受，记录真实管理员身份，不能伪装成私聊用户的同意。修订或移动约定后重新确认。未来已接受期次可交给原 Agenda 提醒链；改动时取消旧提醒，发送前复核日历和来源。到点不自动宣称已完成。 |
| 角色状态 | 精力、饥饿、健康、睡眠感受、忙碌、情绪、位置、可选周期、公开短状态、带到期时间的临时影响。缺少资料保持未知；关闭的身体维度不进入回复。临时影响到期不证明康复。 |
| 状态维护 | 原人格和最近合法聊天、已有模拟状态、计划及实际活动作为材料，经共享后台任务、模型网关和预算生成。默认 30 分钟一次，可从管理 API 请求立即维护；前台回复期间不提交会改变原材料的状态。坏 JSON、撤权或资料变化保留旧状态，不补造成功。 |
| 睡眠与回复 | 独立 `role.life.read` 授权后读取实际睡眠活动与醒来记录。普通私聊只消费有权限的原状态版本；低精力、饥饿和忙碌由提示词解释，没有数值拒答门槛。 |
| QQ 正在输入 | 每个原账号与收件人一个连续任务，覆盖收集消息、模型/工具等待和分段间隔。连续消息复用任务；默认 4 秒刷新，配置可在 1–10 秒内调整，取消、撤权、结束和停机停止刷新，无 90 秒截断。刷新是续租请求，不反复发送停止/开始切换；只调用 `set_input_status(user_id, event_type=1)`，不猜测其他 API。 |
| QQ 自定义状态 | 优先使用当前已接受角色计划显式填写的 `presence`，否则使用已启用的角色模拟短状态。最多 8 字，不直接公开私人标题、约定正文或健康字段。使用 `set_diy_online_status(face_id=21, face_type=1, wording=...)`。 |
| 外部动作 | 仅安装在 `onebot_private` 宿主，复核固定投递授权、独立展示授权、原账号、人格和实际 reverse WebSocket；await 后、请求前再次核验。账号有多个状态拥有者或计划冲突时不随意选择。请求先落盘，相同短状态的成功、失败、unknown 均不自动重放。 |

当前所有开关默认关闭；主开关内饥饿和健康默认启用，周期默认关闭。配置由 CORE 管理者编辑，和精确私聊授权在同一事务生效；私聊用户的重要等级不能替代这些展示/状态授权。`preview` 可以维护本地状态，始终不安装 QQ 展示端口。

已发送回复回读其当时的状态和活动版本，正常维护、精力变化及临时影响到期不会使历史正文失效；当前权限和原始来源撤回继续生效，未发送回复仍复核本轮原状态。状态来源采用可追溯的派生来源引用，原聊天撤回会同时使后续推导状态失效；下一次维护可从仍合法的材料重新开始。日历工具结果进入已发送回复的记忆原文时也保留原材料依赖，不能借工具或记忆绕过撤回。

## 管理 API 交接

`GET /astrbot_plugin_private_companion_v2/state` 返回 `settings`、`edit_token`、有效权限、当前状态、日历分页、未来七天期次、维护排程/结果、展示结果和宿主状态。支持 `after_id` 和 `limit`。身份取自已登录 Dashboard 的 `request.username`，目标取自已初始化的 pinned profile；请求不能指定用户、账号、角色或 scope。

`POST /astrbot_plugin_private_companion_v2/state/command` 使用 UTF-8 JSON，拒绝重复和未知字段。所有命令必带稳定的 `operation_key`。

| action | 其余字段 |
| --- | --- |
| `configure` | `edit_token`, `changes`；可修改 `enabled`, `maintenance_minutes`, `hunger_enabled`, `health_enabled`, `cycle_enabled`, `calendar_enabled`, `typing_enabled`, `typing_refresh_seconds`, `presence_enabled`。 |
| `state.write` | 状态视图的 `view_token`, `expected_revision`, 完整 `data`，可选原始 `sources`。 |
| `maintain` | 状态视图的 `view_token`, `expected_revision`。返回 `scheduled`，后续结果查 GET；复用原后台队列，不在 HTTP 请求内直接调用模型。 |
| `calendar.create` | GET 的 `create_token` 作为 `view_token`，`expected_revision: 0`, `id`, `data`，可选 `sources`。 |
| `calendar.revise` | 原日历项的 `view_token`, `expected_revision`, `id`, 完整 `data`，可选 `sources`。 |
| `calendar.accept` / `calendar.cancel` | 原日历项的 `view_token`, `expected_revision`, `id`。 |
| `calendar.exception` | 原日历项的 `view_token`, `expected_revision`, `id`, `data: {sequence, start}`；`start` 为带时区时间，null 表示跳过。 |
| `calendar.remind` | 原日历项的 `view_token`, `expected_revision`, `id`, `sequence`。 |

状态 `data` 包含 `energy, hunger, health, sleep, busy, mood, location, cycle, presence, conditions`。`energy` 为 0–100 整数或 null；其他描述为文本或 null；`conditions` 为 `{kind, text, expires_at}` 数组。它们均为角色模拟材料。

日历 `data` 包含 `kind, title, detail, schedule, duration_minutes, presence`。`schedule` 使用既有 Schedule 合同：`anchor`（带时区）、`timezone_name`、`frequency`（once/daily/weekly/monthly/yearly）、`interval`、`count`（整数或 null）、`fold`、`gap_policy`（reject/shift_forward）。修改结果中的 `revision` 对应新版本，继续编辑前刷新 GET。

统一小屋页面可直接消费这些路由；本批没有增加另一套页面或改动正在推进的管理 UI。

## 存储与生命周期

- 本批新增 v23→v24 的日历/状态正本、版本历史、操作回执、维护排程与平台状态请求表。保留工作树已有的后续 v25 迁移。
- 主装配位于 `companion_v2/host/application.py`，AstrBot 预检和端口装配位于 `companion_v2/adapters/astrbot/staging.py`。后台重启必须重新绑定可信人格，不单靠持久提示词启动工作。
- 下次维护时间在发起模型前推进；同请求重试查询原任务，未知结果不会因重启重复发起。关闭宿主统一取消模型维护、输入提示和自定义状态任务，再关闭存储。
- 所有数据按原私聊 scope、角色和用户归属。本批没有实现跨窗口共享一份身体状态，也没有宣称完整 V1 状态算法对等。

## 验证

使用 AstrBot 自带 Python、临时 V2 数据根和模拟模型/平台端口。

- 新增 `test_role_state`、`test_role_presence`、`test_role_state_api`、`test_state_storage_migrations` 共 **35 项**；与会话原始链、时间线和成长工具的相关历史回归一起，最终同批运行 **65/65 通过（30.831 秒）**。包括真实宿主类型装配、周期维护、手动排程、低精力正常回复、独立睡眠权限、同轮日历工具修订、输入提示跨 90 秒等待、分段续持、QQ 原参数、发送前改期、unknown 去重、管理鉴权及路由注销。
- 相关既有回归共 **85 项**：host application/recovery、staging host、storage migrations、agenda background、growth tools host、life context host、isolation。首轮 84 项通过，既有 `test_full_batch_and_prompt_change_start_ordered_successors` 的 3 秒等待超时；未修改该测试，单独复验通过。加上最终批次新增覆盖的 27 项原会话用例、1 项时间线用例及本批 35 项，去重后 **148 项均有通过记录**。
- 首轮发现并修正了默认精确授权边界、工具测试调用参数、两个测试预期与迁移夹具导入/表名问题；验证日志没有被当成全部一次通过。

## 仍需后续验收

QQ 客户端是否持续显示输入提示仍需对应 NapCat/QQ 版本现场观察；本地测试证明任务不重建、不反复关开及请求正确，不能保证客户端的显示时长。缺少当前合法文案时不猜状态，也不主动清除无法确认归属的手工 QQ 状态。实际提醒到达、模型对状态变化的语义质量、完整管理页面和跨窗口状态归并仍未由本批测试证明。
