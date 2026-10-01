# 用户习惯画像与私聊对话片段记忆切片（2026-09-27）

依据 [V2 缺口补全任务清单](V2_GAP_CLOSING_TASKS_20260927.md) 的 T26（用户习惯画像+吃什么推荐）与 T31（对话片段记忆·私聊）。
本片遵守 T25 已确立的口径（[群聊天记录片段整合进记忆链切片](GROUP_EPISODE_MEMORY_SLICE_20260927.md)）：**周期整理 → 有界材料 → 进入既有记忆/上下文链**，
不新建存储、不新建读取路径、不新建配置 owner，也不新增工具或平台调用。

## 为什么不照搬 V1

V1 把两份"用户画像"放在自己的 JSON 用户档案里，并各自维护计时状态：

| V1 机制 | V1 落点 | V1 计时/存储 |
| --- | --- | --- |
| 用户习惯画像 `behavior_habits.patterns` | `user_memory.py:5187-5300`（计数）、`:5375-5406`（合格判定）、`:5455-5501`（提示词注入） | `user["behavior_habits"]`，按 (时段, 类别, 签名) 计数；`user_habit_min_count`/`user_habit_max_items` |
| 本地陪伴画像周期整理 | `user_memory.py:10435-10549` | `last_memory_refresh_at` + `memory_refresh_interval_minutes` |
| 吃什么候选 `food_menu` | `daily_state.py:8393-8540` | 独立菜单状态：从"吃了什么"回复里学菜名、打分、标记已推荐 |
| 对话片段 `dialogue_episodes` | `user_memory.py:9576-9819` | `episode_message_count`/`last_episode_refresh_at` + `enable_dialogue_episode_memory` 等 4 项 |

V2 的这些材料已有唯一归属：`memory_views`（T25 的免迁移落法）、`memory/context.py` 的私聊材料通道、`memory/reflection.py` 的材料链。
再建一套 `runtime_metadata` 摘要缓存或第二份用户档案，就是用户点出的"并行第二套记忆"。因此本片：

- **习惯画像**落成一条 `memory_views` 行（`kind = user.habit.v1`），owner 与记忆正本一致（安装 + Bot + 角色 + 人类主体 + `"private"`，`memory/models.py:143`），
  经 `memory/context.py::contributions()` 作为**一份**有界材料进入私聊提示词；
- **私聊片段**落成反思链的**一份**有界材料（`dialogue.episode` / `recent_private_conversation`），与 T25 的 `group.episode` 同级、只是 scope 不同；
  唯一持久状态是一个 `runtime_metadata` 游标（T25 文档留下的"同一游标模型"由本片落地）。

## 本片落地

### T26 用户习惯画像 + 吃什么（[memory/habits.py](../companion_v2/memory/habits.py)）

- 归属：`owner_key(context)`（安装/Bot/角色/人类主体）+ `kind = user.habit.v1`，一行 `memory_views`，`source_json = {"owner": "memory.habits"}`。
- 取证：`HabitProfile.observe()`（`habits.py:431`）挂在**既有入站事务**里（`conversation/messages.py:225/273`，与相识卡同一批观察者），
  文本经 `memory.writer.access.source()` 读回原文（重新复核受众与遗忘标记），逐条写入：
  `count`、`days`（本地日去重，≤30）、`avg_minute`、`examples`（≤3）、`evidence`（≤8 条 `{event_key, source_owner, source_id, source_revision, received_at}`）。
  分类是确定性关键词规则（`classify_message`，移植 V1 `_classify_user_habit_message`），不调模型。
- 证据规则（移植 V1 `_qualified_user_behavior_habits`，`habits.py:231`）：需要 `habit_min_count` 次出现**且**跨 `habit_min_count` 个不同本地日，
  再叠加 V1 的新鲜度权重（≤7 天 1.0、≤30 天衰减到 0.2、更久 0），低于 `max(1.6, min_count*0.45)` 不合格；不确定的条目**只留在原始计数里**，不进提示词。
- 整理节奏：`habit_refresh_minutes`（V1 `memory_refresh_interval_minutes`，V1 用于"本地陪伴画像整理"）作为整理闸门——
  每条消息都计数（与 V1 一致），但陈旧证据清理、重排与上限淘汰最多每 N 分钟做一次；合格判定按读取即时计算，不引入 V1 没有的延迟。
- 吃什么推荐：不建菜单、不加工具。当本轮输入被判定为"在问吃什么/喝什么"（`meal_query`，确定性标记 + 功能讨论排除），
  且饮食节奏/口味类条目证据充分时，材料追加 `meal_question` + `recorded_eating_preferences` + `meal_guidance`；
  指导语明确"只参考这里列出的偏好、不要编造对方没提过的食物、线索不足就按平常聊天回应、不要假装记得"。
- 注入：`memory/context.py:24` 在封存时只记录本轮是否在问吃（`habit_capture`，只读，可安全位于封存事务内），
  `memory/context.py:308-314` 在真正构建提示词时读入当前画像并追加一条 `ContextContribution("memory:user-habits", "memory", "current_user_habits")`。
  画像缺失、证据不足或读取失败一律不产出材料，既有置顶/召回/覆盖材料的语义与顺序不变。

### T31 私聊对话片段（[memory/episodes.py](../companion_v2/memory/episodes.py)）

- 材料：`dialogue_episode_material()`（`episodes.py:183`）为**私聊 owner** 产出一份有界材料，
  经 `memory/reflection.py:339-347` 进入既有反思链（与 `group.episode` 并列，scope 互斥）。
- 行取样：`recent_dialogue_lines()`（`episodes.py:129`）取窗口内两侧发言——用户行经 `access.source()` 按原授权重读，
  Bot 行只取**已确认送达**（`conversation_parts.state='delivered'` + 回执匹配）的回复；最旧在前、单条 200 字、总量 40 行。
- 阈值：`dialogue_episode_refresh_messages`（消息数）**或** `dialogue_episode_refresh_minutes`（分钟，兼作再武装间隔，V1 同一键读两次：
  `user_memory.py:9594-9598` 的到期判定与 `:9744` 的 `refresh_seconds`）；另保留 V1 的 80 字符下限（`user_memory.py:9600`）。
- 游标与"重启后不重复整理"：`runtime_metadata` 键 `memory.episode.v1:<owner_key>` 记录 `covered_through`；
  `episode_due()`（`episodes.py:215`）先做便宜的窗口判定（已被覆盖的窗口直接跳过，不再取样），
  `mark_covered()` 只在**批次真正落地后**由 `memory/reflection.py:492` 推进（单调不回退），因此重启、同一窗口重放、修复批次都不会重复整理同一段。
- 摘要本身仍按既有机制落库：模型提议 → `memory_atoms/memory_views`，命名空间 `dialogue.episode:<digest(owner)>` 不与私聊事实混用。

## 配置字段一览（全部并入既有 `memory` 组，无新 owner、无新 consumer）

| 字段 | V1 键 | 默认 | 范围 | 真实消费者 |
| --- | --- | --- | --- | --- |
| `memory.habit_learning_enabled` | `enable_user_habit_learning` | 开 | — | `HabitProfile.available()`（入站不计数）、`habit_material()`（不产出）、`habit_capture()`（不封存本轮问吃标记） |
| `memory.food_menu_recommendation_enabled` | `enable_food_menu_recommendation` | 开 | — | `habit_material()` 是否追加问吃材料（画像本体仍产出） |
| `memory.habit_min_count` | `user_habit_min_count` | 3 | 2–20 | 合格判定：出现次数与去重天数下限（证据不足不产出画像） |
| `memory.habit_max_items` | `user_habit_max_items` | 24 | 8–80 | 计数写入后的上限淘汰 + 合格集合上限 |
| `memory.habit_refresh_minutes` | `memory_refresh_interval_minutes` | 360 | 30–4320 | 画像整理（陈旧证据清理/重排/淘汰）的节奏闸门 |
| `memory.dialogue_episode_memory_enabled` | `enable_dialogue_episode_memory` | 开 | — | `dialogue_episode_material()` 的总开关 |
| `memory.dialogue_episode_refresh_messages` | `episode_memory_refresh_messages` | 8 | 1–64 | 到期判定的消息数分支 |
| `memory.dialogue_episode_refresh_minutes` | `episode_memory_refresh_minutes` | 90 | 5–1440 | 到期判定的分钟分支（同一键兼作再武装间隔，同 V1） |
| `memory.max_dialogue_episodes` | `max_dialogue_episodes` | 12 | 1–32 | 材料里告知模型一轮可见的既有片段上限 |

字段声明只有一处：`memory/configuration.py:41`（`DIALOGUE_*` / `HABIT_*` 常量在 `:26-38`），
读取经既有 `MemorySettings.read()`（`memory/configuration.py` → `SparseConfigurationOwner`），校验经 `FieldDefinition.validate` 与
`habits.habit_settings()` / `episodes.dialogue_settings()` 双层把关；`habits.py`/`episodes.py` 不自带第二套声明。

## 接线点（外科式，共 4 处）

| 文件 | 改动 | 是否需主代理汇总 |
| --- | --- | --- |
| `companion_v2/memory/configuration.py` | 新增 9 个 `FieldDefinition`（并入既有 `memory` 组） | **不需要**：`host/application.py:147` 的 `extend_registry` 已覆盖整个组 |
| `companion_v2/memory/context.py` | `capture()` 封存本轮问吃标记；`contributions()` 追加一份习惯材料 | 不需要 |
| `companion_v2/memory/reflection.py` | 私聊分支追加 `dialogue.episode` 材料；`apply()` 后推进片段游标 | 不需要 |
| `companion_v2/conversation/messages.py` | `accept()` 的观察者由单个改为元组（相识卡 + 习惯画像），构造 `self.habits` | 不需要 |

**结论：主代理无需改 `host/application.py`**（不新增 import、不追加 `extra`、不追加 `owners`）——因为两处配置都并入既有 `memory` 组，
`HabitProfile` 的 settings 直接取自 `MemoryService.settings`（`host/application.py:203` 已装配）。

## 验证

新增两个测试文件（AstrBot 自带 Python + `PYTHONPATH=backend/app`）：

```powershell
cd C:\Users\99505\.astrbot\data\plugins\astrbot_plugin_private_companion_v2
$env:PYTHONPATH='C:/Users/99505/.astrbot/backend/app;C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/.p4-tmp'
$env:TEMP='...\.p4-tmp\temp'; $env:TMP=$env:TEMP
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -W ignore -m unittest `
  tests.test_user_habit_profile tests.test_private_dialogue_episode -q
```

- `tests/test_user_habit_profile.py`：配置登记与区间（含 `True` 被拒）、时段/类别分类、"一次发言不成画像"、跨天证据不足仍不确定、
  跨天重复后进入私聊提示词（含证据引用）、无饮食证据时只给软线索、owner/scope 隔离（群 scope 与另一人类主体）、
  画像不改变既有置顶与召回材料、两个开关各自的作用面、合格判定的新鲜度衰减。
- `tests/test_private_dialogue_episode.py`：四项设置登记与区间、双说话人指导语、阈值与周期（分钟分支 / 消息数分支 / 两者都不满足）、
  已被覆盖窗口不再整理、另一 owner 与群 scope 不产出、重启（同一数据根第二个句柄）后不重复整理、
  片段材料真正进入反思请求且批次落地后游标推进、同窗口重复取材料命名空间与内容稳定。
- 本片两个模块 **24 项全部通过**；与既有 `test_configuration`、`test_conversation_messages`、`test_memory_reflection`、
  `test_group_episode_material`、`test_group_memory` 同批回归见交付报告。

## 未迁移 / 设计差异

- **V1 `固定检索` 习惯类别不迁移**：它描述"用户爱问 Bot 当前状态"（今天穿了什么/在干嘛），V2 已有 `conversation/state_context.py` 与记忆召回承担，重复登记会变成第二套语义。
- **V1 吃什么候选菜单不迁移**：V1 的 `food_menu` 是从"吃了什么"回复里学菜名、打分并按 `last_recommended_at` 标记的独立菜单状态（`daily_state.py:8453-8540`）。
  本任务口径要求"吃什么推荐"只表达为提示词材料，因此 V2 用**已记录偏好**（饮食节奏 + 明确说过的口味）替代菜名库，不建库、不加工具、不调平台。
- **V1 饭点主动关心不迁移**（`enable_meal_care_proactive` 等 4 项）：涉及主动发送，属另一任务边界，本片不发送任何消息。
- **V1 的 30 天陈旧阈值、80 字符下限、单条 200 字/总量 40 行上限**保留为模块常量（同 T25 的 `MAX_SOURCE_LINES`/`MAX_SUMMARY_CHARS`），未登记为字段：V1 同样是硬编码，登记会造出没有 V1 对应的可调项。
- **T25 的群材料仍无游标**：本片落地的游标（`memory.episode.v1:<owner_key>`）目前只服务私聊 scope；群侧材料按反思窗口天然不重叠，未强行并入，避免改变已验收的群行为。

## 风险与后续

- 习惯计数写在入站事务里（与相识卡同位置），异常一律吞掉以保证"派生数据永不拒绝入站"；若观察者长期失败，画像只会为空，不会报错，需依赖 `memory_views` 的 `user.habit.v1` 行做现场核对。
- `habit_material` 每轮读一次配置与一行 `memory_views`（未加缓存）；数据量有界（≤ `habit_max_items` 条），未观测到热点。
- 片段材料依赖"已确认送达"的 Bot 行；送达回执缺失时材料只剩用户侧行，属预期降级而非错误。
- 页面（陪伴小屋）控件与真实现场验收待第②阶段；本片未接页面、未调用真实模型、未构建交付包。
