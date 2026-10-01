# 生理期连续性优化实施记录

2026-09-24。承接[优化核查](ROLE_CYCLE_OPTIMIZATION_REVIEW_20260924.md)，已修复其中 5 项复现问题，并实现感受延续、按需表达和一次性自然初始化。实现仍属于 V2 `role_work/state/`，沿用原人格、共享后台任务、状态版本表、来源链与 state 管理 API。

## 行为变化与证据

| 原问题 | 当前行为 | 回归证据 |
| --- | --- | --- |
| 生成或分段发送跨午夜时，状态投影改变导致回复被拦 | 新快照保存 `projection_version=2` 和观测时间；周期按观测时间投影，权限、来源、当前版本和实际活动仍复核 | `CycleReplyTests` 的跨午夜生成、分段发送，以及人工改期、撤权、撤回用例 |
| 调整周期长度会重算已过去的周期 | 保留当前方案，成功维护保存下一周期才生效的 `pending_plan` | 已经过 58 天时由 28 天改为 30 天，仍为第 3 周期第 3 天；到第 84 天开始第 4 周期才改为 30 天。覆盖再次修改、取消、离线及重启 |
| 撤回无关心情聊天会丢掉周期起点 | 周期保存独立依据；旧感受仍失效，维护只恢复仍有效的周期材料 | CORE 定位第 10 天后撤回笑话，2 天后共享维护恢复为第 12 天；真正起点来源撤回仍失效 |
| 模型可以覆盖人工“不适用” | `decision_origin=manual` 保持人工决定，`cycle.align` 的 `auto` 显式释放 | 领域和已认证 API 覆盖不适用、未知、自动释放、旧版本冲突及回执重放 |
| 关闭周期仍注入完整周期说明 | 周期提示与通用状态提示分开；普通回复仅添加可用周期材料的当前阶段说明 | 关闭时普通回复和后台维护均无完整周期提示；适用性未知/不适用时普通回复不添加；经期回复不注入 PMS 等其他阶段提示 |

新快照还会提供 `observed_at`，提示词明确这是本轮观测时间。旧快照保留原合同和原有验证行为，不回写已有回复；旧文字周期和旧时钟仍可读。临时条件到期与人工写入不属于自然周期推进，仍可能使尚未发送的旧回复失效。

## 周期方案与初始化

`cycle_initialization` 默认 `natural`：首次确认适用时，按角色、私聊归属、当地日期和方案确定一个位置并保存。它仅用于模拟初始化，不表示观察到的现实月经。后续写入及重启沿用锚点，不重新抽取。可选 `first_day` 从第 1 天开始，或 `unknown` 保持适用但没有日期/阶段。未建锚点的自动模式可在维护时采用新的初始化设置；已有锚点需显式管理定位才会改变。

时钟保存 `segment_start_date`、`segment_start_number` 和当前 `phases`；待生效方案保存 `effective_date`、`cycle_number`、`phases`。投影无需补跑离线模型即可跨过已保存的生效边界。成功维护会将已到期方案作为当前方案继续保存，未来再修改时仍从下一周期开始。

配置修改先进入后台维护，成功后才成为持久的待生效方案；维护失败或尚未运行时不会改动已保存方案。生效前可再次修改或取消，直接恢复当前方案的设置即可取消；已生效后再调整则排到下一个边界。三阶段/六阶段切换同样在下一周期采用。立即定位使用原 `cycle.align`，并采用当前配置的方案和时区。

## 管理 API 与人工选择

仍使用 `POST /astrbot_plugin_private_companion_v2/state/command`，配置用 `configure` 的 `changes.cycle_initialization`。管理操作需要原 `expected_revision`、`view_token`、稳定 `operation_key` 和 CORE 身份；接口不会接受调用者替换目标角色。

恢复自动判断的命令主体：

```json
{
  "action": "cycle.align",
  "operation_key": "cycle-auto-1",
  "expected_revision": 4,
  "view_token": "使用 GET 返回的 state.view_token",
  "data": {"applicability": "auto", "day": null}
}
```

此命令清除人工决定、旧日期、周期文字及感受，保存为自动模式的 `unknown`。下一次成功维护依完整原人格重新判断，并采用初始化设置。人工的 `applicable`、`not_applicable`、`unknown` 均持续优先；模型普通状态输出不能隐式解除。

## 同一次感受的延续

原 `cycle` 文字/null 和 `{applicability,description}` 合同继续有效，新增可选结构：

```json
{
  "applicability": "applicable",
  "description": "仍有一点腰酸，比刚才轻一些",
  "feeling": {"episode_id": "使用 previous_simulation.cycle_feeling.episode_id", "trend": "easing"}
}
```

新感受使用 `episode_id=null`；同一次感受引用原 ID。`trend` 支持 `continuing`、`easing`、`worsening`、`ended`、`uncertain`。返回 `state.cycle_feeling` 包含 ID、`started_at`、`observed_at`、`last_confirmed_at`、趋势和描述；未确认延续不会刷新最近确认时间，新未确认感受的确认时间为 null。已经结束的感受不能以同一 ID 重新开启。

感受只在周期适用且不适模拟开启时保存/投影。省略或使用 `feeling=null` 表示本次没有这类感受记录；重新定位会清除它。引用原感受前会复核其来源，来源撤回后不能借旧 ID 继续使用原感受。新合法观察可保存新的感受，不复用被撤回的文字。

提示词要求延续已有感受、不因半小时维护或切换阶段另造症状，临时条件不反复顺延，不凭到期或阶段变化宣布治愈。是否提及结合当前话题、是否被问及及最近的表达。语义仍交给原人格和模型，不添加症状词表、固定精力扣分、每月必然不适或机械拒答。

## 来源与兼容

周期独立来源存于原版本记录的 `cycle_sources`。人工定位创建自己的管理依据；自然携带时钟和采用配置只依赖先前周期依据，不把本次心情聊天加进时钟来源。模型首次确认或改变适用性仍依赖该次判断所用材料。普通状态的派生来源继续依赖周期依据，保证真正的周期来源撤回会影响消费者。

无关聊天撤回后，普通状态整体仍为不可用；下一次合法维护可通过独立周期依据恢复。不会让原心情或不适绕过撤回。旧记录缺少独立周期来源时，保守使用原状态的完整来源，无法自动拆出未经证明的来源边界。无需新增数据库表、schema 迁移或读取 V1 数据。

## 验证与当前范围

使用 AstrBot 自带 Python、临时 V2 数据库与 SDK 数据根、模拟模型/发送器。执行：

```text
tests.test_role_cycle
tests.test_role_cycle_optimization
tests.test_role_state
tests.test_role_state_api
tests.test_role_state_configuration
tests.test_role_presence
tests.test_conversation_messages
tests.test_isolation
```

新增 22 项回归（优化文件 21 项、API 1 项），更新既有用例对有意变更的方案生效时机和观测快照的预期。**103/103 项同批通过，耗时 30.184 秒。** 这是本地材料、计算、来源、提示词接线和发送边界验证，不是模型自然表达的现场评测。

周期和不适默认开关不变。页面继续由原页面任务接入，本批没有在线重载、真实模型或 QQ 调用。后续已完成[可选的每轮阶段差异](ROLE_CYCLE_VARIATION_20260924.md)，总周期长度仍按配置；跨窗口共享身体时间线和群内表达尚未实现，当前周期仍按原私聊角色与用户归属保存。上面的 103 项为本批原测试证据，后续结果单独记录。
