# C 类范围与验收标准（2026-09-28）

依 `docs/V1_V2_CONFIG_VERIFIED_20260927.csv` 的 `owed` 114 行。
用户已定：**不做生图提示词编排层**（约 18 项按「设计不迁入」销号）。本文只列真需动手的部分，逐组给验收标准。

## 零、先说方法：账本会过期，验收标准必须对着代码写

本轮在定范围前做了代码核查，**已发现 5 处账本与现状不符**：

| 账本记的 | 实测 |
| --- | --- |
| `weather_refresh_minutes` = owed | B 批已落地为 `role.state.planning_weather_max_age_minutes`，账本未回写 |
| `group_high_intensity` 7 项 = owed | 已按等价销号（air guard + fatigue），账本未回写 |
| `group_slang_topic` 4 项 = owed | 联网链已落地，账本未回写 |
| `skill_growth_rate` = owed | B 批已按「决定不注册」销号，账本未回写 |
| `PURPOSES` 为固定 12 项 | 实为 **15** 项，含 `creation`/`meal`/`environment` |

结论：**每组的验收标准都要写明「对照代码核验」这一步**，不能只勾账本；每组完工后必须回写
`verified_verdict`，否则下一轮又会把已完成项当欠债。

## 一、范围总览

| 组 | 项数 | 性质 | 建议批次 |
| --- | --- | --- | --- |
| photo_action（参考图+穿搭） | 7 | 功能缺口·资产链 | C2 |
| wardrobe（衣柜） | 8 | 功能缺口·资产链 | C2 |
| reading_archive（书架二期） | 13 | 功能缺口·可挂既有体系 | C2 |
| model_assignment（按任务指派） | 5 | 功能缺口·配置面 | C2 |
| 散点 6 项 | 6 | 逐项定 | C2 |
| relay_bridge（转述） | 5 | 功能缺口·**跨授权边界，需先表态** | 待定 |
| auto_voice（主用户语音） | 4 | 功能缺口·概率链 | C3 |
| voice_playback（本机播放） | 6 | 本机侧，建议销号 | 销号 |
| legacy_compat（分段合并） | 3 | 逐项定 | C3 |
| photo_action 提示词系列 | 18 | **设计不迁入（已定）** | 销号 |
| experimental_motivation 关系惩罚 | 10 | 已属不迁入类目 | 销号 |
| qzone 3 项 | 3 | 已属不迁入类目 | 销号 |

真需动手：**约 48 项**（含散点），分 C2 / C3 两批；销号 40 项。

---

## 二、C2 批：可挂既有体系（建议先做）

这一批的共同点：不需要新端口、新权限体系，落在已有的配置/存储/提示词层上。

### C2-1 参考图链（photo_action 7 项）

**现状（代码核验）**：`grep -rniE "reference_image|daily_outfit"` 在 `companion_v2/`、`astrbot_host/`
命中 **1** 次，且是 `astrbot_host/integration_catalog.py` 的一句描述。**无实现**；
`companion_v2/legacy/surface_ledger.py:173` 的 `private.command.reference_images` 只是静态登记。

**涉及的 7 项**：`enable_photo_reference_image`、`enable_p5_structured_reference_assets`、
`photo_structured_reference_assets`(list)、`photo_reference_catalog`(list)、
`photo_persona_reference_image_path`、`photo_reference_library`(list, 上限 24)、`enable_daily_outfit_photo`。

**做法**：参考图是**角色资产**，应走既有 `ReadProviderRegistry`（与书架同范式），
不在配置里存路径。V1 的"本地路径或 URL"直接落配置，V2 不能沿用——
配置文本里放文件路径会绕过资产所有权与可见性检查。

**验收标准**

1. **不是登记即实现**：`capability.image_reference` 在 surface_ledger 里有登记**且**有可 bind 的真实
   能力实现；反向验证——把实现注释掉，发现接口应失败而非静默通过。
2. 参考素材以**登记条目**存在（引用 + SHA-256 + 职责 role），**不落配置文本**；
   验证：配置快照里搜不到任何本地绝对路径。
3. 摘要校验有效：篡改素材文件后本次使用被拒（反向验证：改一个字节 → 拒绝）。
4. 条数上限 24（V1 口径）在**注册时**拒绝而非使用时报错。
5. `enable_photo_reference_image` 关闭后，生成的请求里**不含**参考图引用（断言请求体）。
6. `enable_daily_outfit_photo` 关闭时**不产生**当日穿搭生成任务（断言任务表为空）。

**依赖**：Image originals 链（已在 `docs/IMAGE_EXTENSION_GAP_DESIGN_20260927.md` 设计）。

### C2-2 衣柜（wardrobe 8 项）

**现状**：`grep -rniE "wardrobe|outfit"` 命中 **3** 次，全部在 `surface_ledger.py`（静态登记）。
**无实现**。

**涉及的 8 项**：`enable_wardrobe`、`wardrobe_tendency`(text, 上限 800)、`enable_wardrobe_prompt`、
`wardrobe_prompt_max_items`(12)、`wardrobe_image_max_count`(3)、`wardrobe_image_prompt`(text)、
`WARDROBE_VISION_PROVIDER_ID`、`wardrobe_items`(list, 数据本体)。

**做法**：V1 把 `wardrobe_items` 放在配置里（`invisible:true`，"由命令或面板维护"）——
这是**把数据当配置存**。V2 不应沿用：衣物条目是有生命周期的数据，应进存储表，
配置只留开关与上限。`WARDROBE_VISION_PROVIDER_ID` 属"提供方凭据/指派"类，
按既定取向不进 V2 配置文本，改用通用视觉提供方。

**验收标准**

1. 衣物条目进**存储表**（角色级），字段含名称/描述/标签/来源；验证：插件重启后条目仍在，
   且配置快照里**不含**条目内容。
2. `wardrobe_tendency` 上限 800：超长在**写入时**拒绝，不是截断。
3. `enable_wardrobe_prompt` 关闭后衣柜**不进**提示词（断言提示词材料集合）。
4. `wardrobe_prompt_max_items` 生效：造 20 件衣物、上限设 12，断言注入恰 12 条且顺序稳定。
5. `wardrobe_image_max_count` 生效：一次投 5 张图、上限 3，断言只处理 3 张。
6. `enable_wardrobe` 关闭后：既不进提示词，也**不接受**新的识图入库（两个入口都测）。
7. **配置收紧不损坏存量**：把上限从 12 降到 5，已有 20 件衣物**仍可读**（这是 V2 存储升级四件套的既有要求）。

**依赖**：视觉提供方链（已有）；参考图链可与 C2-1 共用资产表。

### C2-3 书架二期（reading_archive 13 项）

**现状**：A 批已落地条目/来源引用/进度/书评/同意与两项只读能力。
`companion_v2/library/models.py` 的 `ArchiveReview` **已有 `rating` 字段**——所以 V1 的"评分"机制
在本体上已存在，缺的是**评分聚合与偏好注入**。

分三小类：

**C2-3a 偏好注入链（4 项）**：`enable_reading_archive_rating`、
`enable_reading_archive_preference_influence`、`reading_archive_preference_min_ratings`(5)、
`reading_archive_preference_max_terms`(8)。
- 验收：评分可聚合为偏好词条；累计评分**未达** `min_ratings` 时**不注入**（下界边界两侧都测）；
  注入词条数**恰为** `max_terms` 上限内；`enable_reading_archive_preference_influence` 关闭时
  提示词材料里**不含**偏好段；关闭 `enable_reading_archive_rating` 后**不再产生**新评分，
  但**已有评分仍可读**（不删数据）。

**C2-3b 低频触发（3 项）**：`reading_archive_min_interval_hours`(18)、
`reading_archive_share_probability`(0.18)、`reading_archive_ask_probability`(0.16)。
- 验收：新增 `proactive.contact` 用途（见 C2-4 的方法）；间隔未到**不产生**候选（两侧边界）；
  概率 0 时永不触发、1 时必触发（用固定随机源断言，不靠统计）；
  节流状态落存储，重启后**仍生效**（否则重启即绕过）。

**C2-3c 候选筛选（3 项）**：`reading_archive_default_keywords`(默认"纯爱,恋爱,同人")、
`reading_archive_blocked_tags`(默认"連載中,長篇,青年漫")、`reading_archive_max_photo_count`(60)。
- **需要你先表态**：V2 的阅读材料由 operator 显式投喂（`role_work/life/management.py`），
  **没有外部检索源**。这三项只对"去外部找材料"有意义。
- 若保留：关键词与屏蔽标签作用于**候选筛选层**，验收为"命中 blocked 标签的候选不入库，
  且拒绝原因可查"。
- 若不保留：销号，理由是 V2 无检索源。**这一条我不替你定。**

**C2-3d 明确销号建议（3 项）**：`enable_reading_archive_vision`、
`enable_reading_archive_page_comments`、`enable_reading_archive_ask_recommendation`。
前两项依赖"页边短批注 + 页面图像"对象，V2 阅读对象是纯文本 `SourceRecord`；
后一项依赖上面的检索源。建议归入不迁入。

### C2-4 按任务类型指派提供方（model_assignment 5 项）

**现状**：V2 有完整 `RouteRule`（`model_gateway/replacement_rules.py`，按关键词/优先级选提供方），
但**没有"按任务类型指派"这个维度**。V1 的 `DETAIL_ENHANCEMENT_PROVIDER_ID`、
`HISTORY_SUMMARY_PROVIDER_ID`、`DAILY_REVIEW_PROVIDER_ID` 无对应物。
另两项 `sensitive_replacement_keywords`、`deepseek_peak_match_keywords` 是路由匹配词表。

**验收标准**

1. 任务类型 → 提供方 的映射**存在且可配置**；验证：为某任务指定提供方 A，
   断言该任务的请求实际发往 A（读审计表，不看日志）。
2. 未配置的任务类型回落既有默认提供方，**行为不变**（对照测试）。
3. 指定的提供方不存在时**拒绝写入**，不是使用时静默降级。
4. 匹配词表（`sensitive_replacement_keywords`）新增词后命中生效；
   **内置高置信词始终保留**（清空用户词表后内置词仍生效）。
5. `deepseek_peak_match_keywords` 的匹配面覆盖 Provider ID、名称、模型名、类型、API Base 五处
   （逐项测，漏一处即失败）。

### C2-5 六个散点

| 项 | 现状核实 | 验收标准 |
| --- | --- | --- |
| `basic_config.persona_inner_voice_prompt` | V2 其余四个通道都有字段，**独缺内部动机通道**（账本判断与代码一致） | 新增该字段；开启后内部动机材料带该风格；**断言不外发**（消息体里搜不到该文本） |
| `memory_habit_config.meal_care_followup_minutes` | V2 **无**"饭点未回应补问"路径（B 批已核实） | 先补这条路径（单次低压补问 + 间隔可配）；未回应**恰好补问一次**，第三次不补 |
| `life_schedule_config.daily_plan_time` | V2 **无**每日日程生成时刻判定（B 批已核实） | 到点才生成；同一天**只生成一次**（幂等）；时刻可配且非法值拒绝 |
| `schedule_detail_config.important_date_lookahead_days` | V2 只做当日问候，**无提前天数** | 未来 N 天重要日期可注入；N=0 时不注入；跨月末/年末边界正确 |
| `humanized_state_config.enable_group_cycle_awareness` | 群聊**不带**角色身体/周期材料（`messages.py:595-597` 群聊分支只存 `group_context`/`group_memory`，周期材料只在 `private` 分支捕获） | 群聊能拿到周期材料且**仅**在开关开时；关闭时群聊材料集合不含周期字段 |
| `weather_config.weather_refresh_minutes` | **B 批已落地** | 仅需回写账本 `verified_verdict`，无需实现 |

---

## 三、C3 批与建议销号

### C3-1 relic_bridge 转述（5 项）——**建议你先表态**

`grep -rniE "relay|atrelay"` 在 `companion_v2/`、`astrbot_host/` 命中 **0**（"转述"仅出现在
提示词措辞里）。V2 **完全没有转述模块**。

这一项与其他不同：**转述是把 A 群的话带到 B 群，跨了授权边界**。
V2 的群聊是独立授权域，`conversation.group_participation` 全部动作不可共享
（`shareable=False`）。所以问题不是"难不难做"，而是**V2 要不要这个能力**。

- 若做：必须新授权动作、逐次显式确认（V1 的 `atrelay_sensitive_confirm` 是必要条件不是可选）、
  多目标上限、且**不写入长期记忆与群黑话**（否则转述内容会污染接收群的理解）。
  验收：跨群转述需独立权限；未确认的敏感内容不直发；转述不产生接收群的记忆条目。
- 若不做：5 项销号，理由"跨授权域能力，V2 不迁移"。

### C3-2 auto_voice（4 项）

V2 有通用 `voice_probability`（`conversation/reply_settings.py:238`），无"主用户"概念。
- 先核实 V2 是否有"主用户/主人"角色概念。有 → 4 项可迁（关键词触发、概率抬升、专属提示词），
  验收为"命中关键词后语音概率取 max 抬升"且"概率 0 时仍不触发"。
- 无 → 销号。

### C3-3 legacy_compat（3 项）

`segmented_proactive_send_as_forward` / `_private_` / `_group_`：分段消息是否合并成转发发送。
需核 V2 `conversation.outbound_plan` 是否已有分段发送与合并策略。
- 有分段无合并 → 补合并开关（群/私聊分档）。
- 无分段机制 → 销号。

### C3-4 建议直接销号（40 项）

| 类目 | 项数 | 理由 |
| --- | --- | --- |
| photo_action 提示词系列（style/negative_prompt/fixed_prompt） | 18 | **用户已定**：V2 取消编排层 |
| voice_playback | 6 | 本机侧（在跑 AstrBot 的电脑上播放/字幕 overlay），既定不迁入 |
| experimental_motivation 关系惩罚系列 | 10 | 已属"亲密度数值化系统"不迁入类目 |
| qzone | 3 | 已属"QQ 空间全链"不迁入类目 |
| reading_archive 视觉/批注/征求推荐 | 3 | 依赖 V2 不存在的对象（页面图像、外部检索源） |

---

## 四、逐组验收的通用判据（每组都要过）

除各组专条外，每组完工必须同时满足：

1. **真实消费者**：新配置字段有实际读取点。无消费者的字段不注册
   （B 批既定规则）。验证：改字段值，断言行为变化；改了没变化即无消费者。
2. **默认值等于原行为**：未编辑该字段的安装行为零变化。
   验证：默认值下跑既有测试，全过。
3. **收紧不损坏存量**：`SparseConfigurationOwner.read` 对缺失键回落 `field.default`
   （`configuration/owners.py:72-73` 的 `value, source, source_revision = field.default, None, 0`
   后逐层覆盖）。验证：新字段加入后旧配置可读。
4. **落地 + 页面**：配置在管理页可读写、错误码有中文映射、缓存串更新、
   `sync_framework_page.py --check` 无漂移。
5. **反向验证**：每条关键断言都要能通过"故意改坏"证明其非空洞。
   （本轮书架页已用此法证明作用域断言有效。）
6. **回写账本**：完工后更新 CSV 的 `verified_verdict` 与 `verified_landing`。
   本轮已因未回写而重复评估 5 处。

## 五、待你定的三件事

1. **转述链（relay_bridge）**：做还是销号？这是跨授权域能力。
2. **书架候选筛选三项**：V2 无外部检索源，保留筛选层还是销号？
3. **C2 批内部顺序**：我建议 参考图 → 衣柜（两者共用资产表）→ 书架二期 → 散点，
   你也可以先要散点（成本最低、见效最快）。
