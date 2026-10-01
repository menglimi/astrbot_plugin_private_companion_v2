# 真实活动进入主动联系（2026-09-25）

本片把已提交的阅读完成与睡眠结束回执接入 V2 主动联系。原有自动联系只产生 `chat` 念头；新增候选分别使用 `creation`、`life` 目的，并继续由原角色决定发送或跳过。

## 使用行为

- 开启 `proactive.contact.enabled` 和 `automatic_enabled` 后，在原私聊完成且达到空闲时间时检查真实活动。
- 阅读材料只包含回执确认的已读字符区间，区分原文与角色主观读后感。书中情节不能作为用户经历或现实事实。
- 睡眠回执只说明这一段睡眠结束，不推导梦境、起床或其他完成活动。
- 继续携带原窗口最后一条真实输入、原人格与可用的已确认发送历史。
- 有有效活动时优先提出该活动；模型可以跳过。没有活动时才保留原有日常话题机会。
- 关闭 `chat` 不会同时关闭 `creation`、`life`。各目的开关、暂停、静默时段、窗口和关系额度仍在生成与发送前复验。
- 新增 `event_max_age_seconds`，默认 3600，允许 60 至 86400 秒；过期事件不补发。空闲时间和两次联系间隔仍独立生效。

## 实现边界

`companion_v2/proactive/events.py` 的 `ActivityContactEvents` 读取原 `role_activity_revisions`。活动必须同时具有：

1. 与当前角色、原窗口和 `TaskContext.key` 相符的执行意图。
2. 当前不可变的完成版本。
3. 原 `role.life` 已完成操作及一致的持久操作结果。
4. 阅读时仍可读取的原来源、匹配的哈希、长度和实际消费范围。

仅有 `completed` 字样、计划、进行中、暂停、取消或到期时间都不能构成候选。生成后与发送边界还会复验原活动、来源、时效和最近对话，新的用户输入会使旧主动稿失效。

原文片段被发布为有固定版本的 `proactive.activity` 来源，并通过现有 `source_dependencies` 连接原书本文本。原文撤回会使候选、待发稿和已发历史的正文同步不可再用。机会过期本身不会伪造过去已确认发送记录的撤回。

后续加固：来源内部保存原活动 ID、版本、原操作 ID 和活动摘要，每次读取都核对原角色完成操作及对应内容。重启后仍可复核；原操作变为未知或调度器停机关闭来源 owner 时，旧来源立即不可读。内部回执只供治理核验，不作为模型材料。

每个活动机会沿用持久任务和主动记录去重；同一原来源版本的同一已读区间只自动提出一次。跳过、取消和中断任务不会因重启重新调用模型。阅读同一本书的不同实际区间可以形成不同候选。

查询按原角色和近期时间范围使用现有 `role_activity_history_time_idx`，每页最多 16 条，空页或末页后至少间隔 30 秒。过滤整页后继续游标，不被大量计划条目阻断。游标缓存最多 1024 个上下文，不保存正文；重启后持久任务继续负责去重。

## 装配

`ContactSchedule` 新增可选 `role_life` 参数。宿主 `CompanionApplication` 已完成正式装配：

```python
self.contact_schedule = ContactSchedule(
    self.proactive, self.messages, notify=self.notify, role_life=self.role_life
)
```

不增加表、不迁移 V1 数据；新增字段进入现有统一配置目录。没有注册主动模型配置或尚未开启自动联系时不会调用模型。

## 验证

通过真实 `CompanionApplication` 装配运行，未替换调度器或活动账本：

```powershell
$env:PYTHONPATH='E:\astrbot\backend\app;C:\Users\99505\.astrbot\data\plugins'
& 'E:\astrbot\backend\python\python.exe' -X utf8 -m pytest -q `
  tests/test_proactive_activity_events.py tests/test_contact_scheduling.py `
  tests/test_proactive_preferences.py --tb=short
```

结果为 **50 passed，5 subtests passed，exit 0**，用时 58.25 秒。其中新增活动事件 18 项，原主动调度和偏好回归 32 项。

专项场景包括：真实片段与原人格、睡眠事实、伪完成与取消、相同已读区间去重、跳过后重启、过期后重启、目的开关和额度、生成中与实际发送边界的撤回、跨角色和窗口隔离、索引分页与轮询节流、已发历史来源撤回、主动稿取消、顽固模型在停机后返回。

全部使用临时 V2 数据库及合成模型、发送回执；未调用真实模型、QQ、V1 数据或在线重载。后续新增来源跨重启、原回执失效、owner 关闭及模型材料净化场景；与规划、活动记忆及三项 SDK 宿主用例联合复验 **67 项通过**，详见[联动记录](CORE_PLANNING_ACTIVITY_INTEGRATION_20260925.md)。

## 小屋主动管理后端

新增 `companion_v2/proactive/management.py`，供现有小屋管理端接入：

```python
manager = ContactManagement(app, original_private_context)
manager.status(operator)
manager.configure(operator, {
    "operation_key": "稳定操作编号",
    "edit_token": "原页面配置令牌",
    "changes": {"enabled": True, "automatic_enabled": True},
})
```

两接口均返回 `Outcome`。状态包含 `settings`、`edit_token`、`effective`、`purposes`、`host_state`；配置成功包含 `operation_id`、`replayed` 与最新 `status`。`effective.readonly_fields` 指明本窗口不能覆盖的关系级联系和尝试额度。配置字段使用短键，类型、范围、时区和目的沿用现有注册表校验。

- 核心管理员身份必须先验证，之后才可读取配置。管理员操作身份不替代真实私聊参与者；原平台、账号、窗口、受众和角色仍逐次复验。
- 只有显式写入 `enabled` 且该操作首次提交时，才发放或撤销 `proactive-managed:` 前缀的本域授权；只改备注、自动开关或用途不会偷偷发放授权。
- 授权给原参与者，既不授予管理员自己，也不改变普通/重要/核心等级。关闭时只撤本域创建的授权，不撤其他管理路径已授予的权限。
- 配置与权限变更在同一事务内；中途失败全部回滚。配置编辑令牌过期、跨角色令牌或错误类型不会部分提交。
- 丢失响应后使用原参数和原操作编号，可返回原回执；重启同样有效。旧操作重放不会重新授予后来被撤销的授权，后续管理员撤权也不能用原回执绕过。

`tests/test_proactive_management.py` **14 passed，exit 0**，用时 5.34 秒。覆盖先鉴权、普通参与者精确授权、独立授权保留、回执恢复、撤权后重放、请求冲突、过期编辑、关系额度只读、事务回滚、角色重绑、伪造参与者与重启。页面及 API 的统一装配由主任务完成，本后端没有新增独立入口。

## 下一步

由主任务把 `ContactManagement` 接入现有小屋的状态 API 和配置表单，验证前后端使用同一编辑令牌与操作回执。其后可按同样的可信来源合同增加日记摘要、记忆接续和计划进展候选；私人日记全文、梦境内容及预约提醒不能直接当成本片已实现能力。预约提醒继续由日历的独立交付链负责。
