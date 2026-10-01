# V2 情绪系统：概率更新与衰减回归（设计合同）

本次把上游 MaiMBot 的两层情绪机制改造为 V2 的情绪系统：ChatMood 的"概率更新 + 定时回归"与 S4U 的四轴数值（Joy/Anger/Sorrow/Fear，1-10）。

上游实现不属于本仓库：`mood_manager.py`、`ChatMood`、`MoodRegressionTask` 在 worktree 内零命中（含七个能力提供方、`astrbot_host/` 与页面脚本）。本文只吸收其**机制**，落点必须是 V2 已有的状态正本、版本历史、派生来源与跨窗口投影规则，不引入第二套并行情绪状态。

状态：设计与实现已完成，交付包 `companion-v2-20260927-mood` 已构建并通过宿主检查；实现清单、验证与遗留见第八、九、十一节。

已确认决策：

1. **数值作者**：程序只给有界建议，模型写正本（第 3.4 节；单轴单轮区间由代码硬约束）。
2. **跨窗口可见性**：可选的 `mood_cross_window`；开启后随 global 模式跨窗口共享数值轴，默认关闭（第 4.1 节）。

## 一、目标与非目标

目标：

- 情绪是**数值化、会流动、会衰减**的：一次夸奖不会让角色亢奋一整天，一次不愉快不会永久低落。
- 更新是**概率性**的：不是每条消息都改情绪，兴趣越高波动越大，久无交互或间隔越久越倾向回归基线。
- 情绪只做**语气滤镜**：它改变表达的浓度与倾向，不改变人格、事实、判断与是否回应的开关。
- 数值以外的东西全部沿用现有合同：来源、溯源、撤回、跨窗口、历史快照。

非目标：

- 不做情感诊断，不推断用户情绪，不把数值当作事实证据（继续遵守"一次心情、沉默或玩笑不自动成为人格或偏好"）。
- 不新增 SQL 表或 schema 迁移。
- 不另建与 `role_state` 并行的情绪存储，不新增第二个可写状态的角色。
- 不复刻上游的 `valence/arousal` 环形模型。

## 二、数据结构

`role_state.values.mood` 由当前的"≤256 字符文本或 null"扩展为文本、null 或结构对象：

```json
{
  "baseline": 6,
  "joy": 7,
  "anger": 1,
  "sorrow": 2,
  "fear": 1,
  "intensity": "mild",
  "description": "被刚才那段话逗乐了，整体轻松"
}
```

- 四个轴与 `baseline` 均为 1–10 的整数；四轴可独立升降（被夸 Joy↑ 与被吓到 Fear↑ 允许同时发生）。
- `baseline` 是角色本人的情绪基线，默认 6；由模型在维护中缓慢调整，人工 `state.write` 可显式校准。
- `intensity` 只可为 `mild`、`moderate`、`strong` 或 null；它描述强度的自然语言档位，避免把 `10` 直接当作台词。
- `description` 继承现有文本槽的约束（≤256 字符），语义仍是"这一次观测到的情绪描述"。
- 兼容：字符串形式继续合法（旧记录与旧管理调用），读取时按"仅文字、无数值"投影，不注入语气块。

### 与 `emotion_episode` 的分工（必须写死，否则两套表示会打架）

| | `role_state.values.mood` | `relationships` 的 `emotion_episode` |
| --- | --- | --- |
| 语义 | 角色此刻的**环境情绪底色** | 一次**关系事件**触发的、带归属的主观情绪片段 |
| 归属 | 只有角色自己 | 必须显式 `emotion_subject` 为 `role` 或 `human` |
| 生命周期 | 半小时维护持续重写、随时间衰减回归 | 一次性写入，人工审阅采用后长期保留 |
| 消费 | 每轮回复的语气注入块 | 关系背景材料（`relationship_context`） |
| 可否数值化 | 是（本设计） | **否**，永不携带数值轴 |

结论：数值轴只存在于 `mood`；`emotion_episode` 保持纯文本与归属合同不变。

## 三、更新动力学

### 3.1 更新途径只保留一条

不做"每条消息触发概率更新"，也不新增独立情绪调度任务。更新仍由现有 `role.state.maintain` 后台维护（默认 30 分钟一次）执行，理由：

- 该任务已持有 `previous_simulation`、材料来源、版本 CAS、预算与 life cycle；另起调度会变成第二个可写者，破坏单写者与幂等回执假设。
- "概率 + 兴趣"不必等于"每条消息一次"，把它实现为**每个维护周期一次有界更新**即可得到同样的可观察行为。

### 3.2 兴趣与时间信号的程序化输入

维护任务新增一段**由代码计算**的材料（不是程序直接写状态，见 3.4）：

- `gap_seconds`：距上一次维护或上一次真实互动的间隔。
- `messages_since_maintenance`：本窗口自上次维护以来的入站消息数（复用现有 `conversation_inputs` 读取路径）。
- `interest`：弱信号，0–1 之间的分档值，来源为消息长度、疑问/请求标记、是否 `@` 角色、是否连续追问；**语义判断仍由模型做**，代码只给粗分档与它据以分档的原始计数。
- `body`：`energy`、`sleep`、`cycle_timeline` 的当前投影——身体低谷与周期不适本身就能推高 Sorrow/Fear。

### 3.3 动力算子（纯函数，`role_work/state/mood/models.py`）

1. **衰减回归**：`value += (baseline - value) * (1 - 0.5 ** (elapsed / half_life))`，即相对基线的半衰期回归。这一步取代上游的 `MoodRegressionTask`，而且比上游更可解释（半衰期是配置项，而不是任务周期）。回归**不设上限**——半衰期的含义就是强情绪会自己淡下去。
2. **有界加速**：单轮允许区间由 `mood.bounds()` 给出，实测三条规则叠加（`role_work/state/mood/models.py`，本文 2026-09-27 复核）：
   - 以回落值为中心上下各留一个 `mood_update_max_delta`；
   - **向基线一侧额外限位**：不得越过 `baseline ± max_delta`，避免"回落值离基线很远时一步冲过基线"；
   - 最后钳到 1–10。
   实测：`joy=9`、`baseline=6`、半衰期 90 分钟、30 分钟后回落值 8.381，允许区间为 `[6.381, 10]`；同样参数下 `joy=7` 被拒。回落本身不受此限——强情绪仍会自己淡下去。
3. **中性带**：四轴全部不超过 `mood_neutral_band` 时，`neutral=true`，注入块退化为"保持平常"，情绪不再着色。
4. **静默回归**：没有任何新消息时兴趣分档为 0，回落值就是本轮唯一可达位置附近的值，情绪自然平复，不需要额外的定时任务。

所有算子都是纯函数：输入只有上一轮数值、时间、兴趣与配置，不读数据库、不读时钟；因此可以被契约测试直接断言。

### 3.4 谁写数值：程序给边界，模型写正本（已确认）

**程序不直接写 `values.mood`**。维护调用得到上一轮数值、算好的回落参考与允许区间（`mood_settlement`）作为材料，由模型输出最终数值；代码校验 1–10 整数、轴完整性、单轮区间与来源，越界即拒绝该次维护（沿用 `TaskError` 合同，不静默截断，也不改动旧记录）。

这样保留了两条既有不变量：唯一状态作者仍是模型 + 显式人工操作；数值变化始终有本轮材料与来源背书。代价是数值曲线由模型遵循度决定，而不是程序保证的曲线——因此单轮区间必须由代码硬约束。

人工 `state.write`（operator）是显式校准，不做单轮区间校验，可随时设定任意合法数值。

### 3.5 概率闸门

每个维护周期独立掷一次：`mood_update_probability` 为 0 时永不移动数值（只允许首次建立），为 1 时每轮都可以移动，其余按概率。闸门关闭时提示词要求保持上一轮各轴数值、只更新 `description`；回落参考仍然出现在材料里，因此"情绪随时间平复"在没有新消息时照常发生。

## 四、存储、来源与投影

- 正本仍写入 `role_state_records.record_json`。新增可选键 `mood_dynamics`（与既有 `cycle_clock`、`cycle_feeling` 同级），保存 `updated_at`、`half_life_minutes`、`interest_level`、`cross_window`、本轮采用的 `reference` 与 `previous_axes`，便于事后解释与撤回传播。
- `values.mood` 保持投影出口：读取时对象形式照原样返回，字符串形式照原样返回；只有结构化且启用时才附带 `mood_dynamics`。
- 来源沿用 `write()` 现有派生来源：`mood` 的数值与文字共用本轮 `sources`，不新增来源类型。
- 来源撤回：相关聊天来源撤回后，依赖它的 `mood_dynamics` 与数值轴一并失效，回落到文字槽的现有保守行为。

### 4.1 跨窗口可见性（已确认：随 global 模式）

V2 的 global 模式就是"角色本体由 role owner 持有"（`records.storage(context) == "role"`，跨窗口共用身体）；window 模式则是窗口私有的旧记录。规则因此写成：

- **local**（本窗口写的版本）：`mood` 与 `description` 照常可见。
- **非 local**：`mood` 与数值轴只有在 `mood_cross_window` 打开、本体是 `role`、且该版本的 `sources` 已经按身体共享（`body_shared` 证书）时才会投影；此时**只给数值、基线、回落参考，不给 `description`**，并在 `mood_dynamics.cross_window=true` 与注入块里注明"可能来自其他窗口"。
- 其余情况沿用既有置空列表：`mood`、`location`、`busy`、`presence` 一律置空；`align_cycle` 的同类置空同样覆盖结构化 mood。

这条规则保证"共用身体"不等于"共用私聊内容"：一段只在本窗口说过的私聊，不会因为情绪被数值化就泄漏到另一个窗口。

## 五、注入：情绪是语气滤镜，不是内容开关

注入仍走"材料 + 提示词"，不新增独立注入块类型：

1. `role_state` 材料里已含 `simulation.values.mood` 与 `mood_dynamics`，模型能看到数值本身。
2. 在 `cycle_prompts.reply_instruction` 的现有路径上补一段**情绪语义**（对所有会话生效，不再要求先启用周期）：
   - 数值只描述语气与浓度，不覆盖原人格、当前事实与判断，不改变是否回应。
   - 情绪不必说出来；结合话题、是否被问及和最近已说过的内容决定是否提及，无关话题不反复播报心情。
   - 四轴可同时偏离（例如 Joy 与 Fear 同时偏高是允许的），不强行选一个"当前情绪"。
   - 强数值不产生戏剧化台词或攻击性，不把负面情绪归咎于用户。
3. 中性带的语义与现有 `conditions` 一致：只表示"不必着色"，不表示"已经康复"，也不删除已记录的数值。

这与既定的"表达习惯作为一等注入块"一致：改语气不改推理路径。落地为 `role_work/state/mood/prompts.py` 的 `REPLY`／`NEUTRAL`／`maintenance` 三段文案，由 `conversation/state_context.py` 的 `instruction()` 在 `role_state` 材料后拼接。

## 六、配置项（并入 `role.state` 组，已落地）

| 字段 | 默认值 | 含义 |
| --- | --- | --- |
| `mood_enabled` | false | 启用数值情绪系统；关闭时 `mood` 退回纯文字槽，数值轴不进入材料，但记录里的数值不删除。 |
| `mood_cross_window` | false | 随 global 模式允许其他窗口读取数值轴（永不含 `description`），见 4.1。 |
| `mood_update_probability` | 0.6 | 单个维护周期发生数值更新的概率；0 只回落不更新。 |
| `mood_interest_window_minutes` | 120 | 计算兴趣分档的回看窗口（5–1440）。 |
| `mood_update_max_delta` | 2 | 单轴单轮允许的额外步长（1–4）；回落本身不受此限。 |
| `mood_decay_half_life_minutes` | 90 | 相对基线回归的半衰期（5–1440）。 |
| `mood_neutral_band` | 3 | 1–4；四轴全部不超过该值时视为中性。 |

落地位置：`role_work/state/configuration.py` 的 `DEFAULTS`、`configuration_fields()` 与 `validate_mood_settings()`；`mood_update_probability` 用 `ValueKind.PROBABILITY`（自带 0–1 校验），其余为 `ValueKind.INTEGER` 并显式给出上下界，越界由 `ConfigurationError` 拒绝。

不修改 `_conf_schema.json`：`role.state` 组走 Dashboard 的 core-only 配置通道，与周期、平台展示配置同一入口。

## 七、管理接口、页面与兼容

- 管理 API 仍只有 `GET .../state` 与 `POST .../state/command`：读取投影新增 `mood_dynamics`（`updated_at`、`baseline`、`axes`、`reference`、`interest_level`、`neutral`、`cross_window`）；`state.write` 接受结构化 `mood`。
- 人工覆盖：`mood` 属于 `values`，人工 `state.write` 可显式给出数值，跳过单轮区间校验；不新增命令，也不改变既有授权与 CAS。
- 页面：`pages/陪伴小屋/state-page.js` 的角色状态面板在启用时增加"情绪四轴"卡片（喜/怒/哀/惧、基线、回落参考、中性带与跨窗口标记），沿用既有只读通道，不新建页面。
- 历史：已发出的回复保留当时的数值与 `mood_dynamics`；`projection_version` 未改变语义（新增字段是附加项），未知版本仍走保守路径。

## 八、实现清单（已完成）

1. `role_work/state/mood/models.py`：校验、`decayed`、`bounds`、`validate_update`、`document`、`project`。
2. `role_work/state/mood/prompts.py`：维护输出契约、语气注入块、中性文案与 programmatic 材料行。
3. `role_work/state/service.py`：`validate_state` 接受结构化 mood；`write()` 接入上一轮数值与单轮区间校验并写入 `mood_dynamics`；`_project()` 输出投影并执行 4.1 的跨窗口规则；`align_cycle()` 的置空覆盖结构化 mood。
4. `role_work/state/maintenance.py`：结构兴趣分档、回落参考与概率闸门、`mood_settlement` 材料、输出契约。
5. `role_work/state/configuration.py`：七个配置字段与范围校验。
6. `conversation/state_context.py`：语气注入块（从 `simulation.mood_dynamics` 读取）。
7. `pages/陪伴小屋/state-page.js`：四轴与基线展示。
8. 顺带修复两处阻断性缺陷（详见第十一节）。

## 九、验证与边界

- `tests/test_role_mood.py` 新增 **15 项**：
  - `MoodModelTests`（6）：契约边界、中性带、半衰期衰减、单轮加速上限与不受限的回落、首次建立数值、配置范围校验。
  - `MoodStateTests`（4）：结构化写入与投影、单轮跳变拒绝、文字/人工写入兼容与校准、关闭开关不删除数值、global 本体不共享未共享来源的情绪。
  - `MoodMaintenanceTests`（5）：概率闸门保持数值但回落仍可见、开闸轮收到回落参考并在区间内移动一步、首次结构化建立后越界被拒、语气注入块只在结构化非中性时出现、中性带退化为"保持平常"。
- 回归：工作树内 `tests.test_role_state`、`test_role_cycle`、`test_role_cycle_optimization`、`test_role_cycle_variation`、`test_role_mood`、`test_expression_style`、`test_role_state_api`、`test_relationship_context`、`test_relationship_memory` 同批 **173 项**，其中 172 通过。
- 交付包：`companion-v2-20260927-mood`，`verify_v2_release.py --host-check` 通过（哈希与语法、宿主加载、停机与路由注销、默认关闭）；在该包解压副本上重跑状态/周期/情绪/API/表达用例 **132 项**，情绪与状态相关全部通过。

## 十、与周期表达的关系

`cycle` 的 `cycle_*_mood` 表达偏好与情绪数值是两条通道，本批保持互不覆盖：周期提示词提供"这个阶段可以怎样"，情绪数值提供"此刻有多浓"。若希望周期不适自动抬升 Sorrow/Fear，应在周期提示词里显式写明，而不是由代码偷偷加分。

## 十一、顺带修复与遗留问题

顺带修复（都在改动路径上，不修就无法完成本批验证）：

1. `companion_v2/conversation/reply_settings.py`：字段种类映射缺少 `float`，任何新增概率型默认值都会让宿主构建 `KeyError: <class 'float'>` 而无法启动；已补上 `float -> PROBABILITY`。
2. `companion_v2/expression/configuration.py`：`field_names()` 返回字符串元组，而 `SparseConfigurationOwner.read()` 需要 `FieldDefinition`，表达学习配置读取会抛 `AttributeError: 'str' object has no attribute 'field_id'`；已改为返回 `configuration_fields()`。

遗留（本批未触碰，属既有失败）：

- `tests.test_role_cycle_variation.CycleVariationClockTests.test_existing_clock_with_pending_plan_and_missing_variation_fields_stays_fixed`：`cycle.evolve` 会在无差异的旧时钟投影里补出 `phase_expression`，测试期望旧投影保持原样。
- `tests.test_expression_style.ExpressionRotationTests` 的轮换顺序用例（"最近用过"与"很久没用"次序）。
