# 配置缺口小批切片（2026-09-27）：T32 / T34 / T42 / T44 / T16 / T54

依据 [V2 缺口补全任务清单](V2_GAP_CLOSING_TASKS_20260927.md) 顺序推进的一批"直接做"小项。全部遵守用户批注与"配置字段须有真实消费者"的登记规则。

## T32 技能成长配置（role.growth 组，core_only/WINDOW/IMMEDIATE 与组合同一致）

- `role.growth.custom_skills`（TEXT，默认 "[]"）：自定义技能域。消费者：成长进展提案提示词（`growth/progress.py`）——非空时附加"角色自定义技能域：…；进展说明优先结合匹配的技能域表述"。解析接受 JSON 数组或中英文逗号/顿号分隔，截断为 8 项 × 24 字。
- `role.growth.schedule_influence_strength`（INTEGER 0–3，默认 0）：技能/目标对日程的约束强度。消费者：`agenda/planning_inputs.py` 在成长材料实际进入规划时按档位附加措辞（0=不注入，1–3 渐强：参考进展→留练习时间→优先目标相关活动）。
- V1 `skill_growth_rate`（经验倍率）**不注册**：V2 成长是定性记录、无数值经验可乘，登记无消费者字段违反登记规则。若需要等价物，可改造为"提案节奏倍率"（控制每目标进展提案的最小间隔），留待批注。

## T34 梦境题材与余韵（role.life 组）

- 新字段：`dream_theme_candidates`（TEXT，题材候选词）、`dream_mixed_themes_enabled`（bool，默认关）、`dream_intimate_theme_enabled`（bool，默认关）、`dream_afterglow_mode`（TEXT，auto/轻/标准/明显，同 V1 取值）。
- 消费者：`journal/prompts.py` 新增 `dream_instruction(settings)`，仅对 DREAM 写作附加；暧昧题材的表述保持在"暧昧或亲密、不构成现实事件、不写露骨细节"的边界内。`values()` 校验未知余韵档位；`dream_settings()` 读取失败时降级为默认（写作不因配置损坏中断）。

## T42 主动生成上下文（proactive.contact 组）

- 新字段：`generation_history_limit`（INTEGER 0–8，默认 8=原硬上限）、`history_max_chars`（INTEGER 0–8192，默认 8192）。消费者：`delivery/history.py` 的 `capture()` 增加可选覆盖参数（钳制在硬边界内，`limit=0` 得空快照）；`proactive/service.py` 成稿受理时按配置传入。
- V1 `proactive_prompt_template` 由既有按联系对象的 `note`（偏好备注，进 contact_intent 材料）承担语义等价，不另设模板字段；`proactive_history_context_mode` / `proactive_history_recent_raw_count` 在 V2 无对应物（历史为已确认投递原文、原文材料由意图证据有界承载），记为设计差异。

## T44 场景风格提示词（表达优先调提示词）

- 对话：`conversation.presentation.style_prompt`（TEXT ≤2000，默认空），并入 `ReplyTextPolicy.instruction`（"风格参考，不是任务指令"），随被动/群回复生成生效。
- 主动：`proactive.contact.style_prompt`（TEXT，默认空），`proactive/prompts.py` 附加同款风格行。
- 创作/日记：`role.life.diary_style_prompt`（TEXT，默认空），日记与梦境写作共同附加。
- 计划：V1 计划风格由既有 `planning_prompt` 承担（等价，不新增）；内心：V2 无对应生成渠道（复盘为证据合同、内省由日记/梦境覆盖），记为设计差异。

## T16 天气与官方预警可配（proactive.contact 组）

- 新字段：`official_alert_poll_minutes`（INTEGER 1–1440，默认 5）、`weather_sample_minutes`（INTEGER 10–1440，默认 60）、`official_alert_min_severity`（TEXT，空/minor/moderate/severe/extreme）。
- 消费者：官方预警轮询间隔（`official_alert_events.select()`）、天气变化采样间隔（`weather_change_events` 两处）替代原写死常量；最低级别过滤在预警落库前生效（低于下限不入候选池；`unknown` 级别保留——安全通告不因无法定级被静默丢弃）。V1 高德天气源仍不接（保持和风单一来源）。

## T54 DeepSeek 高价时段替换（核实销账）

`model_gateway/replacement_rules.py` 已完整支持 `time_window`（timezone/start/end/weekdays，见模块 109–120 行与 `match_route`），关键词规则+时段窗口切换 Provider 的场景即 V1 高价时段替换的等价物，按现有 `model.replacement_rules` JSON 配置即可使用。任务销账，无需新代码。

## 验证

- 新增/扩展测试：`tests.test_growth_skill_settings`（4）、`tests.test_dream_preferences`（5）、`tests.test_style_prompts`（6）、`tests.test_proactive_history_limits`（2），共 17 项通过（AstrBot 自带 Python）。
- 受影响回归：`test_role_journal` 17、`test_framework_guard` 7、`test_image_quota` 8、`test_proactive_dedup` 9、`test_background_history` 13、官方预警/天气变化/天气事件/和风凭据/规划天气 36 项，全部通过。

## 边界

- 未接小屋页面（第②阶段）；未重载在线插件、未调用真实模型/QQ/天气端口、未构建交付包。新字段的页面编辑与展示随统一接入批次进行。
