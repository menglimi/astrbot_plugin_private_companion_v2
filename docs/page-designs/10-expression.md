# 09 · 表达（`manage/expression`，D 段）

代码位置：`renderExpressionOriginal`（`pages/陪伴小屋/app.js:1560`）；D1 挂载回复工作区，D3 挂载表情检索配置，D4/D5 用真实入口跳到组件、联系与生活工作区。

## 一、页面功能

回答"角色**怎么说话和发送**"：文本形态、群聊回应判断、语音、表情素材、平台组件与时机。回复配置以 V1 D1–D5 为索引，86 项 `conversation.presentation` 全部进入一个有 11 个内部模块的回复工作台；内部模块共用草稿、版本与保存回执，D2/D4/D5 的入口会直接选中对应模块。

## 2026-10-01 对照更新

V1 的 D1–D5 仍用作导航骨架；下面较早的审计表记录的是改版前状态。当前页面对应关系如下：

| V1 模块 | 当前呈现 | 状态 |
| --- | --- | --- |
| D1 文字形态与注入 | 分段、语气、文字整理、群聊回应判断、群聊参与节奏、安全边界、图片上下文；支持离线预览与回复诊断 | `conversation.presentation` 共 86 项，测试断言每项恰好出现在一个配置模块 |
| D2 语音 | 直达共享回复工作台的「语音与朗读」模块，TTS 提供方从服务目录读取 | V2 已接入的语音合同可配置；本机播放、直播字幕和专有提供方适配仍属独立范围 |
| D3 表情与配图 | 表情检索的 9 个会话配置项；素材与语义工作区直达感知 A2 | 已有功能全部可达 |
| D4 平台动作 | 本轮引用、群聊 @、组件顺序、发送前检查；主动语音/戳一戳跳主动联系，QQ 短状态跳生活状态 | 跨会话转述与主动引用触发没有 V2 对应实现，不提供假开关 |
| D5 时机与编排 | 分段间隔；休息时段与醒后补看跳日记与生活；免打扰、繁忙顺延与主动联系跳主动联系 | 对应设置归各自领域维护，入口保留在表达页 |

V1 的「违禁词撤回」字段名保留在 API 合同中，但 V2 在发送前拦截命中内容，不会删除已发送消息，页面按真实行为标注。撤回消息转写是输入侧读取，归到感知 A2「对话里的信息」。

## 二、初始展示审计（改版前）

| 分区 | 内容 | 证据 |
| --- | --- | --- |
| D1 回复与分段 | 工作台读取 `reply_api` 返回的快照 `{settings, edit_token, recent, tts, configuration_token}`；「消息预览」面板；「最近回复诊断」（当前对象与角色最近 10 轮：每轮配置快照、模型调用 tokens/时延、分段回执） | `reply-page.js:165-171,197-247` |
| D1 预演 | 「预览当前草稿」→ `POST {reply_api}/preview`（载荷 `{settings, text, image_count}`，不调用模型，只计算组件序列） | `reply-page.js:249-292` |
| D2 语音 | 跳转卡「音色与合成提供方 → models 页」（和分段共用一份设置） | `app.js:1162` |
| D3 表情与配图 | 编辑器挂载头说明（低延迟模式跳过较慢的复核路径；候选池与向量权重只影响检索与复用） | `app.js:1163` |
| D4 撤回与平台动作 | 挂载头说明（只读本窗口内已撤回的入站消息，默认关闭） | `app.js:1164` |
| D5 时机与编排 | 跳转卡「联系节奏与可达对象 → contact 页」 | `app.js:1165` |

## 三、初始配置清单（改版前）

### ① `conversation.presentation`（86 项，window，下一轮生效）— 通道 ② `/reply` 工作台

`reply-page.js:357-378` 经 `CompanionWorkbench.create(group:"conversation.presentation")` 读写 `GET /reply` + `POST /reply/configure`，三分区「分段 / 拟人回复 / 语音回复」（`reply-page.js:74-87`），TTS 提供方 catalog 动态取（`:369-374`）。按功能划分（字段前缀实查）：

| 功能簇 | 项数 | 代表字段 |
| --- | ---: | --- |
| 分句基础 | 10 | `enabled`、`llm_controlled`、`rules_enabled`、`rule_mode`、`rule_regex`、`split_words`、`match_width_variants`、`threshold`、`min_segment_chars`、`max_segments` |
| 群唤醒判定 | 24 | `group_wakeup_*`：直呼词/上下文词/兴趣词+概率/提问阈值/机器人名/主成员/群主直呼/冷群判定/冷却秒数等 |
| 语音回复 | 18 | `voice_*`：总开关、生成/分段/投递模式、位置、语言、外语处理、`voice_probability`、冷却、单段字数上限、超时、`provider_id` 与 zh/ja/en 分语言 provider、`extra_prompt` |
| 内容清理与替换 | 7 | `content_cleanup_*` 5 + `content_replacements`、`content_replacement_enabled`（发送前文本清理，text_processing.py:152-184） |
| 护栏开关 | 6 | 上下文图片说明、违禁词撤回、群注入防护、群隐私防护、群现实承诺防护、humanized 表达 |
| 引用与 @提及 | 5 | `reply_quote_*` 4 + `reply_mention_speaker_enabled` |
| 群冷场守卫 | 4 | `group_air_guard_*`（连续机器人发言上限、礼貌循环上限、窗口秒数） |
| 违禁词召回 | 3 | `recall_forbidden_*`（范围、大小写敏感、词表） |
| 上下文图片 | 3 | `enable_context_image_captioning`、`context_image_caption_max_items`、`image_position` |
| 其他 | 6 | `prompt`、`streaming`、`part_gap_ms`、`component_order`（出报文组件顺序）、`framework_error_guard_enabled`、`style_prompt`、`humanized_expression_prompt` |

后端：`conversation/reply_settings.py:226` → ReplySettings（同文件 `:261`）、分句、语音、群唤醒消费。

### ② `expression.reaction`（表情检索）— 9 项，window，立即生效，通道 `/config`

挂载 `configEditors('reactionConfigWorkspace',['reaction'])`（`app.js:1163`）：`low_latency_enabled` 低延迟模式、`embedding_backfill_enabled` 后台补齐向量、`candidate_limit` 每轮候选素材数、`embedding_candidate_limit`、`embedding_backfill_batch_size`、`embedding_backfill_interval_seconds`、`embedding_weight` 向量权重、`embedding_score_threshold` 相似度门槛、`vision_verify_mode` 视觉复核。后端 `expression/reaction_configuration.py:42`。

### ③ `conversation.recall`（撤回原文转写）— 4 项，window，下一轮生效，通道 `/config`

挂载 `configEditors('recallConfigWorkspace',['recall'])`（`app.js:1164`）：`transcribe_enabled`、`transcribe_max_items`、`transcribe_text_chars`、`transcribe_window_minutes`。后端 `conversation/recall_settings.py:16`。

### 当前归属补充

- `expression.learning` 10 项：在学习与反思 L1 编辑（走 `/reply/expression`），D1 提供直达入口 → [13-learning.md](13-learning.md)。
- TTS 提供方来自宿主目录，音色绑定仍由模型路线负责；主动语音/戳一戳在主动联系页，QQ 短状态在生活状态页。
- 撤回原文转写的 4 项设置属于感知 A2，不是出站平台动作。

## 四、边界与空态

- 未连桥/端点非法/无对象角色/工作台未载各有提示（`reply-page.js:328-346`）；「暂无预览」（`:206`）、「还没有本轮上下文的回复记录」（`:245`）。
- 错误码表含 `reply_preview_invalid`、`reply_images_changed` 等（`:93-105`）；示例/图片数改动使预览失效（`:294-303`）。

## 五、后端情况

| 路由 | 服务 |
| --- | --- |
| `GET /reply`、`POST /reply/configure`、`POST /reply/preview`（`astrbot_host/reply_api.py:22-24`） | `conversation/reply_management.py` `ReplyManagement`（`reply_api.py:8,81`） |
| `GET /reply/recalls`（召回诊断，`:28`） | `conversation/recall_management.py` `RecallManagement`（`:7,134`） |
| `/config` 的 reaction、recall 组 | `ReactionRetrievalManagement`、`RecallManagement`（`configuration_api.py`） |

## 六、相关设计稿与复核

- 表情素材本体在感知页 A2 → [06-perception.md](06-perception.md)；时机与节奏 → [12-contact.md](12-contact.md)；语音绑定 → [14-models.md](14-models.md)。
- 复核：`sed -n '1160,1166p' pages/陪伴小屋/app.js`；presentation 字段簇 `grep -o "group_wakeup_[a-z_]*\|voice_[a-z_]*" companion_v2/conversation/reply_settings.py | sort -u`。
