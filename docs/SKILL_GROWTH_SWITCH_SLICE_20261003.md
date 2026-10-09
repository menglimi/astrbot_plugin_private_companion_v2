# 技能成长总开关迁移切片

日期：2026-10-03。V1 的 `enable_skill_growth_simulation` 控制技能成长模拟。V2 原先已有技能记录、进展提案和日程影响配置，但没有一个总开关把自动消费统一关停。

V2 在 `role.growth.skills.enabled` 增加角色/会话层开关，默认开启以维持既有行为。关闭后技能记录仍保留并可管理，但自动进展提案、日程规划材料与状态维护材料不再消费技能记录；技能成长目标仍按原策略处理。技能自定义领域和日程影响强度也在总开关关闭时不注入自动设置。

实现落点：`companion_v2/role_work/growth/configuration.py` 注册开关；`growth/progress.py`、`agenda/planning_inputs.py`、`role_work/state/maintenance.py` 在自动消费点执行开关。回归覆盖 `tests.test_growth_skill_settings`、`tests.test_calendar_planning`、`tests.test_humanized_state`。

配置行为与唯一公开页面「陪伴小屋」的技能成长总开关均已接入，控件默认开启并沿角色/会话配置层级保存。本切片不表示 57 项总迁移验收完成。
