# 群聊天记录片段整合进记忆链切片（2026-09-27）

依据 [V2 缺口补全任务清单](V2_GAP_CLOSING_TASKS_20260927.md) T25（群聊片段记忆）。用户批注：**避免与记忆拓展重复实现，新框架下的「记忆」应当整合**。本片按该口径改造，不以 V1 的独立缓存/存储照搬。

## 为什么不照搬 V1

V1 在 `group_observation.py` 里维护每群一份 `last_episode_refresh_at` 状态和独立摘要缓存，按间隔刷新后写回群上下文。V2 里「群材料」已经有唯一归属：

- `memory/group/service.py` 的 `GroupMemory`：群记忆记录（成员陈述，按 `owner_key` 归因）；
- `memory/group/context.py` 的 `GroupMemoryContext.capture()`：**只**从 `memory_views` 里 `active` 的群记忆记录取参考，带预算与分页；
- `memory/reflection.py` 的群分支：已经为群作用域附加有界材料（`group.member_safety` / `daily_hits`）。

如果在 `runtime_metadata` 里再建一套「片段摘要」读写路径，就是并行的第二套记忆——正是用户点出的重复。因此本片**不新增存储、不新增读取路径、不新增 owner**：群片段作为**既有记忆反思的一份有界材料**进入那条链，摘要本身按既有 atom/view 机制落库与回读。

## 本片落地内容

- [memory/episode_settings.py](../companion_v2/memory/episode_settings.py)：四项设置的校验与读取，加上群片段的**有界材料生产者**：
  - `settings_for(runtime, context)`：按该群精确窗口读生效设置；
  - `recent_group_lines(...)`：只取该群**已确认送达**的回复（`p.state='delivered'` 且回执 `receipt_ref` 匹配），按 `p.delivered_at` 落窗口，按账号/Bot/角色归属，最旧在前，单条截断 200 字、总量 40 条；说话人归属保留；
  - `episode_material(...)`：开关关闭、非群作用域、窗口不可用、或新材料不足 `group_episode_min_messages` 时一律返回 `None`——**附加材料永不阻断反思**；
  - `episode_namespace(context)`：每群一个命名空间，群动态描述不会与任何私聊事实混在同一个 fact 空间。
- [memory/configuration.py](../companion_v2/memory/configuration.py)：四项设置并入**既有 `memory` 组**，与既有 17 项同一 `consumer_id`/`owner_id="configuration"`/`IMPORTANT` 边界、`apply_mode=IMMEDIATE`、`core_only=True`，因此不需要新 owner、不改变既有组的注册合同。
- [memory/reflection.py](../companion_v2/memory/reflection.py)：在**既有群分支**里追加一份 `group.episode` / `recent_group_activity` 材料，与 `daily_hits` 同级。

| 设置项（沿用 V1 命名） | 默认 | 边界 | V1 出处 |
| --- | --- | --- | --- |
| `memory.group_episode_memory_enabled` | 开 | — | `enable_group_episode_memory`（V1 默认 True） |
| `memory.group_episode_refresh_minutes` | 180 | 30–1440 | `group_episode_refresh_minutes`（同 V1） |
| `memory.group_episode_min_messages` | 12 | 1–64 | V1 群片段整理的 `len(recent) < 12` 门槛 |
| `memory.max_group_episodes` | 10 | 1–32 | `max_group_episodes`（同 V1） |

材料的 `guidance` 明确约束：群动态描述不得写成任何成员的事实、身份、关系或承诺，不得据此推断成员性格或立场，也不产生对成员的处理动作；只为确实有持续价值的内容写条目，且只引用本轮提供的 handle。

## 验证

- 新增 `tests/test_group_episode_material.py` **8 项**：字段并入既有 `memory` 组且与 `configuration_fields()` 逐字段相同（防止出现第二套声明）、区间按声明生效（含 `True` 被拒）、guidance 禁止把群动态读成成员事实、命名空间按群稳定且不同群不同、私聊作用域不产出材料、材料只在确认送达条数达到门槛后出现且受 40 条上限、窗口外回复不进材料、开关关闭后不再产出。
- 统一回归（AstrBot 自带 Python + `PYTHONPATH=backend/app`）：`test_group_episode_material`、`test_configuration`、`test_host_application`、`test_conversation_messages`、`test_group_image_review`、`test_image_quota`、`test_conversation_image_delivery`、`test_storage_migrations`、`test_memory_reflection` 共 **145 项，144 项通过**。
- 唯一失败 `test_host_application.test_two_bots_same_native_message_keep_separate_role_and_delivery`（`until()` 超时）**与本片无关**：把 `episode_material` 整体短路为 `None` 后仍以同样的超时失败，属改动前状态。
- `compileall` 报出一处**非本片文件**的语法错误：`tests/test_busy_reply_gate.py:96` 字符串未闭合（T52 繁忙回复闸门的在建测试，属并行写入中的半成品），未改动。

## 边界与后续

- **未做**：材料目前只影响反思提示，尚未把「刷新间隔到了没有」做成调度侧的到期判断（V1 的 `last_episode_refresh_at`）。V2 的等价物应当是反思/记忆调度的既有游标，而不是新增状态列——留待与 T31（私聊片段）同批按同一游标模型落地，避免又出现两套计时。
- **未做**：T31 私聊片段。私聊侧的 V1 参数是 `episode_memory_refresh_messages`(8) / `episode_memory_refresh_minutes`(90) / `max_dialogue_episodes`(12)，应按同一模式并入 `memory` 组。
- 未接小屋页面、未调用真实模型、未重载在线插件、未构建交付包。
