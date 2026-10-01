# P2 批次切片（2026-09-27）：B 段记忆/关系/角色/主动缺口

依据 [V2 缺口补全任务清单](V2_GAP_CLOSING_TASKS_20260927.md) 的 **P2** 推进。本批按用户既定口径「充分参考 V1 实现 → 在 V2 框架约束下改造」，并把逐项测试合并为**收口时一次统一回归**。

## 范围与结论

| 编号 | 任务 | 状态 | 切片记录 |
| --- | --- | --- | --- |
| T25 | 群聊片段记忆 | 本批之前已完成（并行工作流） | [群片段](GROUP_EPISODE_MEMORY_SLICE_20260927.md) |
| T26 | 用户习惯画像 + 吃什么推荐 | **已完成首版** | [习惯画像与私聊片段](USER_HABIT_AND_DIALOGUE_EPISODE_SLICE_20260927.md) |
| T27 | 世界书/知识库自动导入 + 群成员识别 | **已完成首版** | [知识导入](KNOWLEDGE_IMPORT_SLICE_20260927.md) |
| T28 | 表达学习配置化 | 本批之前已完成（并行工作流） | [拟人与表达学习](HUMANIZED_AND_EXPRESSION_LEARNING_SLICE_20260927.md) |
| T29 | 群观察画像族 | **已完成首版** | [群观察与群节奏](GROUP_OBSERVATION_AND_RHYTHM_SLICE_20260927.md) |
| T31 | 私聊对话片段记忆 | **已完成首版** | [习惯画像与私聊片段](USER_HABIT_AND_DIALOGUE_EPISODE_SLICE_20260927.md) |
| T32 | 技能成长配置 | 本批之前已完成 | [配置缺口小批](CONFIG_GAP_BATCH_20260927.md) |
| T33 | 休息回复闸门 + 醒后补看 | **已完成首版** | [休息闸门与拟人状态](REST_GATE_AND_HUMANIZED_STATE_SLICE_20260927.md) |
| T34 | 梦境题材与余韵 | 本批之前已完成 | [配置缺口小批](CONFIG_GAP_BATCH_20260927.md) |
| T35 | 拟人状态强度 + 每日巡视 | **已完成首版** | [休息闸门与拟人状态](REST_GATE_AND_HUMANIZED_STATE_SLICE_20260927.md) |
| T36 | 群聊主动插话 | **已完成首版** | [群观察与群节奏](GROUP_OBSERVATION_AND_RHYTHM_SLICE_20260927.md) |
| T37 | 群复读跟读/打断复读 | **已完成首版** | [群观察与群节奏](GROUP_OBSERVATION_AND_RHYTHM_SLICE_20260927.md) |
| T38 | 主动节奏增强 | **已完成首版** | [主动节奏与人格判定](PROACTIVE_RHYTHM_AND_PERSONA_SLICE_20260927.md) |
| T39 | 预约主动执行 | **已完成首版** | [主动节奏与人格判定](PROACTIVE_RHYTHM_AND_PERSONA_SLICE_20260927.md) |
| T40 | 早午晚锚点问候 + 失眠深夜 | **已完成首版** | [主动节奏与人格判定](PROACTIVE_RHYTHM_AND_PERSONA_SLICE_20260927.md) |
| T41 | 主动人格判定 | **已完成首版** | [主动节奏与人格判定](PROACTIVE_RHYTHM_AND_PERSONA_SLICE_20260927.md) |
| T42 | 主动生成上下文 | 本批之前已完成 | [配置缺口小批](CONFIG_GAP_BATCH_20260927.md) |

至此 **P2 全部 17 项（T25–T42）均有代码 + 配置 + 定向测试 + 切片记录**。

## 本批共同口径（与 P4 一致的 V2 化原则）

1. **不新建第二套体系**：周期整理类能力（T26/T31）一律复用 T25 已确立的「周期整理 → 有界材料 → 进入既有记忆/上下文链」抽象；观察/插话/片段都是**派生材料**，读取阶段零写入、决定时落盘。
2. **免迁移优先**：本批**未新增任何数据库表、未升级 schema**（仍为 v41）。新增持久形态一律落在既有 `memory_views` / `runtime_metadata` / `proactive_contacts` / `background_deliveries` / `configuration_values` 上。
3. **配置必须有真实消费者**：新增配置全部进统一注册表（有的并入既有组，有的新建组），逐字段在切片文档里写明消费者；没有消费者的 V1 字段不登记并写明理由。
4. **不越过既有边界**：资料不是事实或授权来源（T27 成员线索只作显示归因）；观察材料不得写成成员事实、不得推断成员、不得产生处置动作（T29）；状态强度只影响表达，不改身份/权限/记忆范围（T35）；主动判定只决定是否发送（T41）。
5. **时机类闸门一律写持久计时正本**：T33 的休息延后与 P4 的 T52 繁忙闸门同一口径（写 `conversation_flows.due_at`，同步抬升 `deadline_at`，不在协程里 sleep），两者取上界。

## 本批宿主接线（主代理完成）

| 接线 | 位置 |
| --- | --- |
| `knowledge` 组登记 + `knowledge_context(runtime)` 注入会话装配 | `companion_v2/host/application.py` |
| `conversation.group_participation` 组登记（T29/T36/T37 共 20 字段） | `companion_v2/host/application.py` |
| `rest_deferral` + `accept(defer_seconds=max(busy, rest))`（T33） | `companion_v2/host/application.py` |
| `persona_judge_profile` 模型档（T41） | `astrbot_host/multi_session.py`、`companion_v2/adapters/astrbot/staging.py` |
| T26/T31、T38–T40：复用既有组（`memory`、`proactive.contact`），**无需**汇总改动 | — |

## 未迁移项汇总（本批）

| 项 | 理由 |
| --- | --- |
| T26 V1 `food_menu` 菜名库与打分、30 天陈旧/80 字下限等常量 | 按任务口径改为提示词材料；常量 V1 亦硬编码 |
| T27 成员自登记（`worldbook_self_registration*`）与待确认观察 | V2 禁止写成员画像；后者需模型写入 |
| T27 跨用户记忆桥、`atrelay_*` | 属其他任务域（T50 等） |
| T29 按成员玩笑敏感度画像、名场面引用信号 | 会员画像边界 / V2 无成员级引用归因 |
| T33 V1「睡眠期不回复」与 `asyncio.sleep`、`REST_WAKEUP_PROVIDER_ID` | V2 口径为「已接受输入不丢」→ 有界延后；模型调用默认关闭且 accept 同步 |
| T33 群聊生效 | 与 T52 同口径：群聊保持既有 `short_input_wait`/插话窗口 |
| T36 `GROUP_INTERJECT_PROVIDER_ID`、打断用本机表情包路径、引用群插话开关 | V2 无功能级 provider 消费者 / 无本机资产 / 已由 P4 `reply_quote_group_enabled` 覆盖 |
| T38 `enable_proactive_decorating_hooks`、`enable_precise_platform_send`、`check_interval_seconds` | V2 单一投递链 + 未知不重放；节奏由宿主唤醒与 interval/idle 承担 |
| T40 深夜消息豁免免打扰 | V2 有意不豁免（默认因此不可达，需显式调整免打扰窗口） |
| T41 V1 判定 `rewrite/defer` 结果、判定供应商 ID 字段 | 判定只决定是否发送；V2 走 `model.*` 档位路由 |

## 验证

统一回归（AstrBot 自带 Python + `backend/app` 入 `PYTHONPATH`；全部合成事件、模型替身与本地 reverse WebSocket ACK）：

```powershell
cd C:\Users\99505\.astrbot\data\plugins\astrbot_plugin_private_companion_v2
$env:PYTHONPATH='<AstrBot>/backend/app;<plugin>/.p4-tmp'     # .p4-tmp 仅提供沙箱临时根垫片
$env:TEMP='<plugin>\.p4-tmp\temp'; $env:TMP=$env:TEMP
& '<AstrBot>/backend/python/python.exe' -X utf8 -W ignore -m unittest `
  tests.test_user_habit_profile tests.test_private_dialogue_episode tests.test_knowledge_import `
  tests.test_group_participation_rhythm tests.test_group_observation_family `
  tests.test_proactive_rhythm_and_greetings tests.test_proactive_appointments_and_judge `
  tests.test_rest_reply_gate tests.test_humanized_state tests.test_host_application tests.test_isolation `
  tests.test_conversation_messages tests.test_configuration tests.test_memory_reflection `
  tests.test_group_episode_material tests.test_group_memory tests.test_group_participation `
  tests.test_group_participation_hints tests.test_group_safety_guards tests.test_knowledge_retrieval `
  tests.test_low_cost_contracts tests.test_proactive_contacts tests.test_proactive_reactions `
  tests.test_proactive_voice_poke tests.test_contact_scheduling tests.test_proactive_calendar_events `
  tests.test_role_state tests.test_role_body tests.test_astrbot_shared_body tests.test_role_sleep_configuration `
  tests.test_dream_preferences tests.test_reply_segmentation tests.test_host_recovery
```

**结果：Ran 394 tests / OK（383.3 秒）**，无失败、无跳过。其中本批新增定向测试 114 项：`test_user_habit_profile` + `test_private_dialogue_episode` 24、`test_knowledge_import` 13、`test_group_participation_rhythm` 10、`test_group_observation_family` 8、`test_proactive_rhythm_and_greetings` 14、`test_proactive_appointments_and_judge` 17、`test_rest_reply_gate` + `test_humanized_state` 28。

`compileall companion_v2 astrbot_host main.py` 退出 0；新增/修改文件的 UTF-8 无 BOM、LF、末尾换行校验通过。

**已知与本批无关的既有失败**（各工作流已用因果探针确认，去掉本批新增默认键/停用本批新代码后同样失败，属并行工作流或既有断言过期）：`test_proactive_preferences`（`len(PURPOSES)` 断言 14、实测 15）、`test_proactive_management`（13、实测 15）、`test_proactive_news_events`（并行流改动 `news_events.py` 后候选口径变化）、`test_role_cycle_variation` 的 `missing_variation_fields`、`test_astrbot_background_fairness` 的 `queued_diary`、`tests.test_astrbot_group_delivery` 的 fingerprint 断言（P4 已记录）。

## 边界

未接「陪伴小屋」页面（第②阶段统一接入；新字段已在统一配置注册表内，可直接显示）；未重载在线插件、未调用真实模型/TTS/QQ、未构建交付包；未读取或修改 V1 用户数据；未新增表或 schema 迁移。真机上仍待验收：群观察/插话/复读手感、知识导入的真实文件与内容、休息闸门与醒后补看的体感、主动节奏与锚点问候的时段表现、人格判定的实际通过率。

> 测试环境备注：本机 DSH 沙箱会把 `tempfile.mkdtemp` 的 `0o700` 目录映射成创建进程也无法写入的目录；`.p4-tmp/` 提供 `sitecustomize.py` 垫片（`os.mkdir` mode 归一为 `0o777`）与可写 `TEMP` 根。它是本地脚手架、不属于交付内容，沙箱 ACL 使其中部分临时目录无法删除，可在沙箱外整体删除。
