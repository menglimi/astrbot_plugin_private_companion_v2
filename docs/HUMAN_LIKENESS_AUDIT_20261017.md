# 拟人感审计

日期：2026-10-17。范围：`astrbot_plugin_private_companion_v2` **在对话层面像不像一个人**——不评估人格文本写得好不好，只看机制上哪里会出戏。

## 一、结论（三条）

1. **出厂时 V2 不提供任何人格文本**，每轮恒常驻的 V2 文本是约 **970 字规则**（`【陪伴感知与自然表达】` 880 + `【对话附加提示】` 90），"她是谁"完全依赖用户在 AstrBot 里自己写人格。没写，就是一个持有一堆守则的通用模型。
2. **"人味"的零件基本都在，默认几乎全关**：正在输入、在线状态、回戳、角色身体与情绪、主动联系、夜间不回、忙碌延迟、群聊自主接话——八个开关默认全关；唯一专门反"客服腔"的 540 字表达约束默认不注入。
3. **节奏只有一半**：分段之间有间隔（默认按文本长度的对数曲线，2–6 秒），但**首条回复零延迟**、**私聊没有合并窗口**（每条消息各起一轮）、**没有已读**。默认听感是"发一句、立刻回一段、然后按固定的拍子分段"。

## 二、出厂默认：五个"人"的开关都是关的

| 维度 | 默认 | 证据 |
| --- | --- | --- |
| 正在输入 | 关 | `role_work/state/configuration.py:34` `typing_enabled=False`（实现完整：`delivery/presence.py:77-94`，`adapters/astrbot/presence.py:46-48` 调 `set_input_status`，4 秒续租） |
| 在线/自定义状态 | 关 | 同处 `presence_enabled` / `online_status_enabled=False` |
| 回戳 | 关 | `conversation/pokes.py:35-41` `enabled=False, back_probability=0.0` |
| 角色身体与情绪（energy/hunger/sleep/mood） | 关 | `role_work/state/configuration.py:24` `"enabled": False`、`:39` `"mood_enabled": False` |
| 主动联系 | 双重关 | `proactive/configuration.py:228` `"enabled": False` + `:278-279` `automatic_enabled=False` |
| 夜间休息不回 | 关 | `role_work/life/rest_gate.py:73` `enable_rest_reply_simulation=False`（概率 18 已很保守，但没开） |
| 忙碌延迟 | 关 | `conversation/busy_gate.py:86` |
| 群聊自主接话 | 关 | `conversation/participation.py:62`（间隔 180 分钟、每日 2 次，同样保守） |
| 表达引导（反客服腔） | 不注入 | `humanized_expression.py:28` 模式默认 `free`（返回空串）+ `text_processing.py:185` `enable_humanized_expression=False` |
| 私聊表情/贴纸 | 发不出 | `storage/semantic.py:11-20` 概率 0.2、冷却 180s 是开的，但 `reactions_collection_private_enabled=False`，素材库冷启动为空 |

两项开关串联的地方（主动联系要 `enabled` + `automatic_enabled`；角色状态要 `enabled` + `mood_enabled`）意味着默认安装后基本一个都不会开。这些默认值各有正当理由（不打扰、不假装有身体），**缺的是一个"低打扰但活着"的出厂档**，而不是某一项开关开错了。

## 三、人格：V2 一个字都不提供

现网默认走 AstrBot 核心管线（`astrbot_host/core_reply_configuration.py:22` `"execution_path": "astrbot_core"`）。V2 往 system prompt 里追加的东西只有四块：

| 块 | 出厂 | 约字符 | 来源 |
| --- | --- | --- | --- |
| AstrBot 选中人格 + 示例对话 | 取决于用户 | 0–数千 | AstrBot 自己构造；V2 只做指纹校验（`core_reply.py:356-357`） |
| `【陪伴感知与自然表达】` | **恒出现** | **880**（正文 866） | `core_reply_perception.py:13-19`，`inject_core_reply_perception_policy` 每轮无条件注入 |
| `【表达偏好】` | **默认 0** | 0 / 开启后 540 | `core_reply_context.py:220-230` → `text_processing.py:249-266` |
| `【对话附加提示】` + 默认任务提示 | **恒出现** | 99（90 + 标签） | `astrbot_host/settings.py:162` |
| `【角色稳定档案】` | **默认 0** | 0 / 201+ | `role_profile/context.py:117-126` |

三处可能的"她"，出厂都是空的：

1. **AstrBot 人格**：`persona_instruction` 原样透传，`None` → `""`（`companion_v2/adapters/astrbot/native.py:115-130`）；`persona_id` 默认 `""`（跟随会话当前人格）。
2. **V2 角色稳定档案**（姓名/性格/说话方式/社交距离/口吻示例/边界…字段很全，`role_profile/configuration.py:18-71`）：文本字段默认全 `""`，`capture()` 在所有字段为空时 `return None`（`context.py:93-94`）→ 默认不注入。
3. **关系档案**（`relationships/profile.py:17-45`）：7 个字段默认全 `""`。

所以出厂的默认 system prompt ≈ **970 字规则 + 0 字人格**。默认任务提示（90 字）与感知守则里其实有正向要求（"自然、具体地说清意思""闲聊不复述、不写客服式收尾""合适时可以第一人称带出感受"），但比例上规则是人格的无穷倍。

## 四、三条结构性"助手腔"

1. **背景资料塞进最后一条用户消息。** `astrbot_host/core_reply_perception.py:14-15` 用 `<companion_v2_context>…</companion_v2_context>` 包住记忆/关系/生活/状态等资料，追加在用户消息尾部（`main.py:743`）。system prompt 里只剩守则，模型看到的是"用户消息附带一份资料"，天然把回复定位成"处理这份资料"而不是"听对方说话"。
2. **自管回复链的 JSON 合同要求"逐字自证"。** `companion_v2/adapters/astrbot/model_wire.py:22-39`（778 字）要求"最终回复只输出一个 JSON 对象"、"statement 必须逐字复制 text 中连续出现的原文片段，保留原标点；不能概括、改写或补充"。该链路的静态骨架约 **2,991 字**，人格只有 `system[0]` 一条，模型最后读到的是 JSON 合同而不是人物。（默认走核心管线，这条路只在自管模式下生效。）
3. **背景块与规则块都是"不…不…"句式。** `复述` 全仓出现 26 次，除一处决策标签外全是"不要/不机械/避免"；`作为AI`／`首先`／`分点`／`希望对你有帮助` 各 0 次——用词层面是干净的，代价是提示词通篇自我监控，正向示范只有默认任务提示那 90 字。

## 五、节奏：听得出的机械感

1. **首条回复零延迟。** `core_reply_segmentation.py:266-285`：`if state["sent"]:` 为真才 `await asyncio.sleep(gap)`，首条永远立即发；V2 自有通道首条 `due_at = now`（`flow.py:478`）。全仓没有 `first_delay`／`reply_delay`／`read_delay` 一类配置——用户感到的停顿等于 provider 的吞吐抖动。
2. **私聊没有合并窗口。** `_conf_schema.json:682-691` `quiet_seconds=0`、`maximum_wait_seconds=0` → `flow.py:160,170` 令 `due_at = now`。用户连发"在吗""我想问你个事"会收到两轮独立回复。
3. **分段间隔是一条几乎平坦的曲线。** `segmentation.py:20-37`：`gap = min(60, max(0.1, ln(字数+1)/ln(2.1) + 抖动·0.5))`。实测（含 0–0.5 秒抖动）：4 字 2.17s、10 字 3.23s、20 字 4.10s、50 字 5.30s、100 字 6.22s、1000 字 9.31s。字数翻倍只多 0.93 秒，听感就是节拍器。
4. **上下界配置在 `log` 模式下是死的。** `segmentation.py:25-26` 算了 `lower/upper`，`:31-36` 的 log 分支不用；默认 `part_gap_min_ms=1500`／`max_ms=3500` 完全不生效。运营者在页面上调这两个数不会有任何变化。
5. **纯标点/表情的气泡贴脸连发。** `segmentation.py:33-34` 用 `sum(char.isalnum())` 数字符，`"……"`、`"🥺"` 得 0 → `ln(1)=0` → 间隔只剩 `max(0.1, 抖动·0.5)`，即 **0.1–0.6 秒**。
6. **中英文计时单位不一致。** 同一行代码：全 ASCII 用 `len(text.split())`（词数），否则用字符数。`hahahahaha` 算 1 → 0.93 秒；10 字中文 → 3.23 秒。
7. **三处各写一份 gap 计算。** `core_reply_segmentation.py:271`（用当前 part）、`flow.py:475-478`（用 previous_text）、`proactive/service.py:954-970`（第三份）。同一条回复走被动与主动通道的节奏对不上，改一处另两处不变。
8. **默认"一句话一个气泡"。** `segmentation.py:160-171`：`llm_controlled=False`，模型**从不被告知**分段协议（`core_reply_segmentation.py:51-52` 直接返回空串），只剩标点规则在 `。！？!?…~～` 处硬切，上限 5 条、可见字数超 500 就不再切。三段话必然变成三个等距到达的气泡——"AI 分段"最典型的指纹。
9. **私聊开分段会关掉流式。** `core_reply_segmentation.py:248-263`：`enable_streaming=False`，"先收齐再发"。长回复要等整段生成完（8–15 秒）才有第一条，然后按上面那条平坦曲线喷出。

## 六、失败、兜底与固定台词

1. **两条链路对失败的处理不一致，而且默认那条是沉默。**
   - 核心链路（默认）：模型失败／超时／额度耗尽 → 写入 `InboundNoReplyLedger`（`flow.py:189-235`、`diagnostics/inbound.py:28`），**用户一个字都收不到**。
   - 自管链路：有一句角色化兜底 `MODEL_FAILURE_NOTICE = "刚刚我这边卡住了，没能接住你的消息。你再发我一次，我马上接着聊。"`（`conversation/generation.py:31`）。
   也就是说，写好的人话兜底只在非默认路径上；默认路径是"掉线"而不是"人在忙"。
2. **9 条用户可见的硬编码文案**，其中默认可达的三条最伤：
   - `"禁止复读"`（`participation.py:73`，群复读打断，概率 0.10）——同一句会在每个群反复出现。
   - `"老大不让我和陌生人说话哦"`（`relationships/private_access.py:44`，6 小时冷却 `:47`）——陌生人 6 小时内只能听到这一句。
   - `"这类现实操作需要可验证的外部人员或工具处理，我不能把未确认的结果说成已经完成。"`（`text_processing.py:139`，群聊现实承诺守卫**默认开**，`reply_settings.py:86`）——整段正文被替换成免责声明。
   - 另有 `"（这条回复没有正常生成，按安全策略不予展示。）"`（`text_processing.py:138`，罕见但极出戏）。
3. **戳一戳的回应 100% 走硬编码**（`pokes.py:16` 三句预设，`model_reply_enabled` 默认 false），只是默认没开。
4. **主动联系是"JSON 任务"输出。** `proactive/prompts.py:246` 要求「仅输出任务要求的 JSON 对象，不添加 Markdown 围栏。」，同一请求末尾挂 `FINAL_PROMPT_GUARD`（272 字，"只输出任务要求的最终结果"）。最该像人的那条消息，是在最像任务的提示下生成的。（好在固定开场与收尾在提示词层被明确禁止并点名，例如"不用'好久没见''一直没联系'一类暗示长期分离的开场"、"不固定套用早安、午安、晚安"。）

## 七、关系距离与称呼

- 可用字段：`role_relation`、`interaction`、`extra`（自由文本）、`social_distance`（"熟悉后的变化"，静态描述）、相识卡计数器 `msg_count/active_days/first_seen/last_seen`（`memory/person/service.py:105-122`）。
- **没有"相处阶段"字段**，也没有"刚认识 vs 很熟"的表达梯度；`expression` 里的 `relationship_stages`（stranger/familiar/close）只用于**匹配已采纳的表达规则**，不是当前关系声明。
- 称呼的唯一兜底是**中性表达**：`addressing.py:7` "拿不准时省略称呼或使用中性表达""不要为了显得熟悉而强行套用昵称"。保护是对的，但结果是"越不确定越像客服"。反向约束（"不假装熟悉""称呼不得超出记录"）齐全，缺正向分支。

## 八、做得好的地方

- **私聊表达学习默认开启并应用**（`expression/configuration.py:52,67`），提示词写明"相似场景借鉴、不逐字照搬、不改变要表达的意思"，且每轮只注入 1–2 条并轮换（`style_context.py:30-34`）。
- **mood/状态 → 措辞的线是通的**（`state/service.py:24-28` 629 字 + `mood/prompts.py:5-8`），注入器克制（强度分档、facet 与字数上限、"不机械播报数值"），缺的只是 `role.state.enabled` 默认值。
- **六类背景都带"这不是用户发言、不改授权、不补造经历"的边界**，挡掉了更致命的出戏（把资料当成用户事实）。
- **`silent` 动作默认可用**（`messages.py:680-682`）——模型可以选择不说话，这点比多数陪伴插件好。
- **固定开场/收尾在提示词层被点名禁止**，且给出了具体句式；`作为AI`／`首先`／`分点` 等典型 AI 腔词在全仓 0 命中。
- **分段间隔确实随文本长度变化**，不是固定值。

## 九、建议的改动顺序（性价比）

前三项都不改逻辑，只改默认值与一段文案，但会改变所有用户的线上行为，**需要产品决定**，本轮只记录不动手。

| # | 动作 | 落点 | 理由 |
| --- | --- | --- | --- |
| 1 | 出厂给一个人格：`role.profile` 的 `name/personality/speech_style/boundaries` 写默认值，或首启向导强制填写 | `role_profile/configuration.py:72-79`、`context.py:93-94` | 人格为 0 字时，后面所有调优都是给通用模型加规则 |
| 2 | 打开表达引导（`enable_humanized_expression` 默认 True，或 `prompt_style_mode` 默认 `guided`） | `humanized_expression.py:28`、`text_processing.py:185` | 540 字已写好，不注入等于没有；顺序已在 task_prompt 之前，无需改动装配 |
| 3 | 打开"正在输入"，并让首条发送前真的等一小段（`clamp(0.8 + 字数/12, 0.8, 6.0)·抖动`） | `state/configuration.py:34`、`core_reply_segmentation.py:266-274` | 一个信号同时解决"秒回"和"看不见她"；实现已在 |
| 4 | 私聊合并窗口默认 1.5–2.5 秒，最长等待 6–8 秒 | `_conf_schema.json:682-691` | 消除"逐条应答"，允许对方把话补完 |
| 5 | 间隔曲线改线性+真抖动、让 min/max 生效、`chars=0` 用可见长度兜底、三处实现合一 | `segmentation.py:20-37`、`core_reply_segmentation.py:271`、`flow.py:475`、`proactive/service.py:954` | 去掉节拍器与贴脸连发，成本低 |
| 6 | 默认 `llm_controlled=True`（或 `max_segments=2`、阈值 200） | `segmentation.py:161,171` | 从"每句一泡"改为按语义分段 |
| 7 | 打开角色状态与情绪（`enabled` / `mood_enabled`），先从小强度用起 | `state/configuration.py:24,39` | "她有身体"是拟人感的地基 |
| 8 | 打开休息门，并接上 `backlog_prompt`（"刚看到"） | `rest_gate.py:73,566-591`（后者是死代码，全仓无调用） | 顺带修死代码，得到最像人的一句话 |
| 9 | 核心链路的失败也给一条限频的角色化兜底 | `flow.py:189-235` 旁 | 把"掉线"变成"人在忙"；可直接复用 `generation.py:31` 那句 |
| 10 | 换掉三句最伤的固定文案（"禁止复读"、现实承诺免责声明、框架守卫） | `participation.py:73`、`text_processing.py:138-139` | 出戏最重的几句 |
| 11 | 把 `【陪伴感知与自然表达】` 从 880 字压到 300 以内，Provider/模型口径移到按需工具 | `core_reply_perception.py:13-19` | 它是出厂唯一恒常驻的 V2 文本，其中三成与日常闲聊无关 |
| 12 | 补关系阶段字段，并给称呼指令加"熟了就直呼"的正向分支 | `relationships/profile.py:17-45`、`addressing.py:7` | 距离不变，称呼就永远是中性 |

## 十、补记：本机"正在输入"的实际位置与现状（2026-10-17 23:25 只读核查）

第四节说它"默认关"，但**这台机器上已经是开的**。同时这个开关很难找到，记下来方便下次。

### 在哪里打开（页面路径）

1. 首页底部「状态与日程」（或右栏「此刻的状态 → 查看与更新」）进**状态页**；
2. 顶部图块 **「QQ 状态」**（副标题「正在输入提示 · 自定义短状态」，值显示「N 项已开启」）；
3. 面板底部的按钮 **「配置 QQ 状态」**；
4. 表单三项：**启用正在输入提示** / 输入提示刷新间隔（秒）/ 启用 QQ 自定义短状态 → 保存。

难找的原因：图块点进去是**只读**的「展示通道」（只报状态与诊断），真正的开关在「配置 QQ 状态」按钮后面；而且状态页不在左栏导航里，只能从首页底部入口或家具「生活挂历」进入。

### 实际配置（profile `qq-v2-stream-20260926`，角色「星缘」）

| 字段 | 层 | 会话 | 值 |
| --- | --- | --- | --- |
| `role.state.enabled` | role | 星缘 / staging-role | true |
| `role.state.typing_enabled` | window | 私聊 **3996218846** | true |
| `role.state.presence_enabled` | window | 私聊 3996218846（两个会话）、私聊 **2477398235** | true |

授权（`identity_grants`）：`platform.typing` 仅 1 条（`onebot-user:3996218846`）；`platform.presence` 3 条（3996218846 ×2、2477398235）。

### 两个由此得出的机制事实

1. **开关与授权都是按会话（窗口层）的。** `sync_window_grants`（`role_work/state/configuration.py:73-89`）只在目标层为 `window` 且本次保存确实改动了相关选项时，才为该会话的人签发 `platform.typing`；在别的私聊窗口里开关没开、授权没有，`delivery/presence.py:81` 的授权检查会直接拦下，脉冲记一条 `presence_authorization_changed` 后停止。
2. **自定义短状态确实在工作**：`platform_presence_operations` 里 5 条 `accepted`，最后一条 20:59「在家休息」。说明 aiocqhttp 的反向 API 通道是通的（`set_diy_online_status` 走的同一条 `call_action`），"正在输入"用的是 `set_input_status`，同一通道。

### 生效判据（不用看日志）

「QQ 状态」面板的「展示通道」会写清每条通道的判定：`已开启 · 授权通过` / `已开启 · 授权待核对`（缺授权）/ `展示端口不可用`（适配器不支持）/ `已开启 · 当前空闲`（没有进行中的回复）。另外它只在**生成期间**脉冲（`typing_refresh_seconds` 默认 4 秒续租），回复很快时可能一闪而过。

## 十一、未验证 / 边界

- 没有真实 QQ/OneBot 环境直接观察客户端是否真的显示"正在输入"；构建侧证据只到"通道可用、授权在、调用返回 accepted"（`delivery/presence.py:89`、`adapters/astrbot/presence.py:46-48`）。本机的自定义短状态返回 `accepted`，说明反向 API 通道是通的。
- AstrBot 未绑定人格时它自己的默认人格内容不在本仓库，无法核实"出厂是否在事实上是一个通用助手人格"；本审计只确认 V2 不补人格。
- 模型失败时 AstrBot 核心自身是否另有回复不在本仓库；但"插件侧零输出"已由 `InboundNoReplyLedger` 路径确认。
- 主动联系的真实体验（多久一次、是否重复）需要线上数据，本文只做静态判断。
- 本次审计只读，未修改任何代码；唯一的脚本是 `build/human-audit/measure_instructions.py`（把指令块按源码字面量量长度），不进交付包。

## 十二、2026-10-20 后续

已在不改默认开关的前提下补两项：常驻感知提示增加"篇幅跟对方走、不必每轮提问/总结/清单化"；`log` 分段间隔恢复配置上下限、按非空白可见字符计时并给纯标点/表情一个真实停顿。首条延迟、私聊合并窗口、拟人表达默认值、默认语义分段、失败兜底、状态/正在输入默认档和固定文案仍未动，按影响排序见[本轮拟人化打磨](HUMAN_LIKENESS_POLISH_20261020.md)。
