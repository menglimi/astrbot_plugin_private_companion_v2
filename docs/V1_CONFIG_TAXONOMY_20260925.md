# V1 配置项分类清单（按能力分段框架）

日期：2026-09-25
来源：`astrbot_plugin_private_companion/_conf_schema.json`

## 一、口径

- 该 schema 共 748 个顶层键，展开后 1701 个叶子。其中 **701 条顶层「Legacy flat config」扁平项与分组内叶子重复**（交集 691），是旧版迁移残留。
- **去重后唯一配置项为 1010 条**：分组内 1000 条 + 仅存在于顶层、未归入任何组的 10 条（标记为 `__flat_only__`）。
- 分类依据是每条的 `description` 语义，不依赖所属组名。组名与语义不符的已在第四节单独标出。

## 二、分类体系

沿用「环境接入 / 角色内核 / 产出 / 投递 + 治理横切」四段框架，下分 21 个子类：

| 段 | 子类 | 含义 | 条数 |
|---|---|---|---|
| 环境接入 | A1 | 环境与世界源 | 29 |
|  | A2 | 交互源 | 48 |
|  | A3 | 媒体理解增强 | 44 |
|  | A4 | 外部资讯源 | 32 |
| 角色内核 | B1 | 认知与记忆 | 73 |
|  | B2 | 关系与情感 | 98 |
|  | B3 | 角色自我 | 72 |
|  | B4 | 决策与主动 | 144 |
| 产出 | C1 | 图像生成 | 55 |
|  | C2 | 创作与作品 | 18 |
|  | C3 | 生活行为 | 8 |
|  | C4 | 社交发布 | 10 |
| 投递 | D1 | 文本形态与注入 | 70 |
|  | D2 | 语音 | 44 |
|  | D3 | 表情与配图 | 22 |
|  | D4 | 平台动作 | 31 |
|  | D5 | 时机与编排 | 13 |
| 治理 | E1 | 身份与权限 | 18 |
|  | E2 | 模型分配 | 44 |
|  | E3 | 内容风控 | 51 |
|  | E4 | 资源与预算 | 37 |
|  | E5 | 存储与部署 | 19 |
|  | E6 | 遗留与兼容 | 30 |
| | | **合计** | **1010** |

## 三、分类清单

### A 段（环境接入）

#### A1 环境接入·环境与世界源 — 29 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `weather_alert_api_key` | Legacy flat config: 和风天气预警 API Key（旧别名） | __flat_only__ |
| `enable_almanac_perception` | 轻量黄历感知 | basic_config |
| `enable_environment_perception` | 启用环境感知 | basic_config |
| `enable_holiday_perception` | 感知节假日/工作日 | basic_config |
| `enable_lunar_perception` | 感知农历 | basic_config |
| `enable_model_perception` | 感知当前模型配置 | basic_config |
| `enable_platform_perception` | 感知平台与消息类型 | basic_config |
| `enable_solar_term_perception` | 感知节气 | basic_config |
| `enable_worldview_perception` | 感知世界观适配 | basic_config |
| `environment_perception_timezone` | 环境感知时区 | basic_config |
| `holiday_country` | 节假日地区 | basic_config |
| `enable_weather_alerts` | 气象预警感知 | weather_config |
| `enable_weather_context` | 启用天气上下文 | weather_config |
| `mobile_location_weather_sensitivity` | 地点事件天气联动敏感度 | weather_config |
| `weather_alert_api_host` | 和风天气预警 API Host（旧兼容字段） | weather_config |
| `weather_alert_min_severity` | 最低气象预警级别 | weather_config |
| `weather_alert_refresh_minutes` | 气象预警刷新间隔（分钟） | weather_config |
| `weather_alert_token` | 和风天气预警凭据（旧兼容字段） | weather_config |
| `weather_amap_api_key` | 高德地图 API Key | weather_config |
| `weather_amap_city` | 高德城市编码 | weather_config |
| `weather_api_host` | 和风天气 API Host | weather_config |
| `weather_api_key` | 天气 API Key | weather_config |
| `weather_city` | 天气城市（推荐） | weather_config |
| `weather_lat` | 天气纬度 | weather_config |
| `weather_location` | 天气地点（城市/区县/LocationID） | weather_config |
| `weather_lon` | 天气经度 | weather_config |
| `weather_refresh_minutes` | 天气缓存刷新间隔（分钟） | weather_config |
| `weather_source` | 天气数据源 | weather_config |
| `weather_token` | 和风天气凭据（JWT / API Key） | weather_config |

#### A2 环境接入·交互源 — 48 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `enable_forward_message_adaptation` | 启用合并消息自然阅读 | forward_message_config |
| `forward_message_max_chars` | 合并消息注入字数上限 | forward_message_config |
| `forward_message_max_messages` | 合并消息最多读取条数 | forward_message_config |
| `forward_message_mode` | 合并消息适配方式 | forward_message_config |
| `forward_message_parse_nested` | 展开嵌套合并消息 | forward_message_config |
| `enable_group_high_intensity_mode` | 群聊高强度收口模式 | group_high_intensity_config |
| `group_high_intensity_cooldown_seconds` | 高强度收口持续秒数 | group_high_intensity_config |
| `group_high_intensity_max_merge_messages` | 高强度最大合并消息数 | group_high_intensity_config |
| `group_high_intensity_merge_scope` | 高强度合并范围 | group_high_intensity_config |
| `group_high_intensity_merge_seconds` | 高强度合并等待秒数 | group_high_intensity_config |
| `group_high_intensity_wakeup_threshold` | 高强度唤醒阈值 | group_high_intensity_config |
| `group_high_intensity_wakeup_window_seconds` | 高强度统计窗口秒数 | group_high_intensity_config |
| `enable_group_companion` | 启用群聊陪伴观察 | group_observation_config |
| `enable_group_history_injection` | 启用群聊历史消息注入 | group_scene_config |
| `enable_group_scene_awareness` | 启用群聊场景感知 | group_scene_config |
| `group_scene_recent_limit` | 群聊上下文消息数 | group_scene_config |
| `group_scene_recent_max_chars` | 群聊上下文最大注入字数 | group_scene_config |
| `SMART_MESSAGE_DEBOUNCE_PROVIDER_ID` | 智能收口小模型 Provider ID | message_debounce_config |
| `enable_message_debounce` | 启用消息收口防抖 | message_debounce_config |
| `enable_semantic_message_debounce` | 旧版语义收口开关 | message_debounce_config |
| `enable_smart_message_debounce` | 启用智能文本收口 | message_debounce_config |
| `forward_message_debounce_seconds` | 转发补话等待秒数 | message_debounce_config |
| `image_message_debounce_seconds` | 图片补话等待秒数 | message_debounce_config |
| `message_debounce_max_merge_messages` | 最大合并消息数 | message_debounce_config |
| `semantic_message_debounce_seconds` | 旧版语义收口等待秒数 | message_debounce_config |
| `smart_message_debounce_examples_limit` | 智能收口样本提示数量 | message_debounce_config |
| `smart_message_debounce_learning_window_seconds` | 智能收口误判学习窗口 | message_debounce_config |
| `smart_message_debounce_model_timeout_seconds` | 智能收口模型超时秒数 | message_debounce_config |
| `smart_message_debounce_wait_seconds` | 智能收口等待秒数 | message_debounce_config |
| `text_message_debounce_max_wait_seconds` | 文本收口最长等待秒数 | message_debounce_config |
| `text_message_debounce_seconds` | 文本补话等待秒数 | message_debounce_config |
| `inbound_message_debounce_seconds` | 重复消息防抖秒数 | proactive_reach_config |
| `enable_qzone_comment_inbox` | 空间评论收件箱 | qzone_config |
| `qzone_comment_inbox_interval_minutes` | 评论检查间隔（分钟） | qzone_config |
| `qzone_comment_inbox_max_replies_per_tick` | 每轮最多回复数 | qzone_config |
| `qzone_comment_inbox_recent_posts` | 扫描最近说说数 | qzone_config |
| `enable_reactive_poke` | 启用被动戳一戳 | reactive_poke_config |
| `reactive_poke_normal_replies` | 预设回复列表 | reactive_poke_config |
| `reactive_poke_normal_reply_probability` | 不调用 LLM 的回复概率 | reactive_poke_config |
| `reactive_poke_prompts` | 被戳提示词列表 | reactive_poke_config |
| `reactive_poke_trigger_probability` | 触发回复总概率 | reactive_poke_config |
| `enable_recall_cancel_reply` | 撤回触发消息时取消回复 | recall_config |
| `enable_recall_enhancement` | 启用撤回增强 | recall_config |
| `enable_recall_message_cache` | 缓存撤回消息用于转述 | recall_config |
| `recall_message_cache_max_items` | 撤回消息缓存上限 | recall_config |
| `recall_message_cache_text_chars` | 撤回缓存文本长度 | recall_config |
| `recall_message_cache_ttl_seconds` | 撤回消息缓存秒数 | recall_config |
| `recall_message_image_cache_max_mb` | 撤回图片磁盘上限 MB | recall_config |

#### A3 环境接入·媒体理解增强 — 44 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `enable_experimental_bluetooth_wakeup` | 启用现实触及 | experimental_motivation_config |
| `enable_reality_touch_camera` | 启用摄像头单帧读取 | experimental_motivation_config |
| `enable_reality_touch_camera_proactive_curiosity` | 启用主动视觉好奇 | experimental_motivation_config |
| `reality_touch_camera_analysis_timeout_seconds` | 摄像头有限状态分析超时（秒） | experimental_motivation_config |
| `reality_touch_camera_capture_timeout_seconds` | 摄像头读取超时（秒） | experimental_motivation_config |
| `reality_touch_camera_index` | 摄像头索引 | experimental_motivation_config |
| `reality_touch_camera_min_interval_seconds` | 摄像头最小读取间隔（秒） | experimental_motivation_config |
| `reality_touch_camera_proactive_cooldown_minutes` | 主动单帧行为冷却（分钟） | experimental_motivation_config |
| `reality_touch_camera_proactive_max_daily` | 主动单帧每日上限 | experimental_motivation_config |
| `reality_touch_camera_proactive_min_tier` | 允许直接主动单帧的最低强度档位 | experimental_motivation_config |
| `forward_message_image_limit` | 合并消息视觉图片上限 | forward_message_config |
| `forward_message_image_vision` | 合并消息图片交给视觉模型 | forward_message_config |
| `forward_message_image_vision_timeout_seconds` | 合并消息图片视觉等待秒数 | forward_message_config |
| `enable_group_image_understanding` | 群聊图片理解增强 | group_observation_config |
| `group_image_max_images` | 单条群消息识图上限 | group_observation_config |
| `group_image_vision_wait_seconds` | 群聊回复等待图片理解秒数 | group_observation_config |
| `context_image_caption_max_items` | 单轮上下文补全图片数 | message_debounce_config |
| `context_image_caption_timeout_seconds` | 上下文图片补全等待秒数 | message_debounce_config |
| `enable_context_image_captioning` | 上下文图片摘要补全 | message_debounce_config |
| `enable_private_image_gif_enhancement` | 启用 GIF 动图强化 | message_debounce_config |
| `enable_private_image_self_recognition` | 启用图片转述增强 | message_debounce_config |
| `enable_private_image_vision_cache` | 启用重复图片转述缓存 | message_debounce_config |
| `private_image_gif_max_frames` | GIF 表情包抽帧数 | message_debounce_config |
| `private_image_provider_failure_cooldown_seconds` | 识图模型失败后冷却秒数 | message_debounce_config |
| `private_image_provider_timeout_seconds` | 单个识图模型超时秒数 | message_debounce_config |
| `private_image_self_recognition_hint` | 图片转述增强：特殊图像身份线索 | message_debounce_config |
| `private_image_vision_cache_max_items` | 重复图片转述缓存上限 | message_debounce_config |
| `private_image_vision_custom_prompt` | 自定义视觉转述提示词 | message_debounce_config |
| `private_image_vision_max_chars` | 视觉转述最大字符数 | message_debounce_config |
| `private_image_vision_provider_priority` | 识图增强模型优先级 | message_debounce_config |
| `private_image_vision_wait_seconds` | 单图延迟等待识图秒数 | message_debounce_config |
| `enable_reading_archive_vision` | 资料识图 | reading_archive_config |
| `enable_goodnight_screen_check` | 晚安识屏提醒 | screen_action_config |
| `enable_screen_glance_action` | 允许主动看一眼屏幕 | screen_action_config |
| `enable_unanswered_screen_peek_followup` | 主动后沉默可额外窥屏 | screen_action_config |
| `goodnight_screen_check_delay_minutes` | 晚安识屏等待分钟 | screen_action_config |
| `screen_peek_cooldown_minutes` | 主动识屏冷却分钟数 | screen_action_config |
| `screen_peek_max_daily` | 每日主动识屏最多次数 | screen_action_config |
| `unanswered_screen_peek_after_minutes` | 主动后沉默窥屏等待分钟数 | screen_action_config |
| `unanswered_screen_peek_cooldown_minutes` | 沉默窥屏冷却分钟数 | screen_action_config |
| `wardrobe_image_max_count` | 单次识图添加上限 | wardrobe_config |
| `wardrobe_image_prompt` | 衣柜识图描述提示词 | wardrobe_config |
| `enable_yesterday_screen_diary_context` | 读取昨日屏幕观察日记 | weather_config |
| `screen_diary_context_max_chars` | 昨日屏幕日记上下文字数 | weather_config |

#### A4 环境接入·外部资讯源 — 32 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `bilibili_boredom_min_interval_hours` | 刷 B 站最小间隔（小时） | bilibili_config |
| `enable_bilibili_boredom_watch` | 无聊时触发刷 B 站 | bilibili_config |
| `enable_bilibili_integration` | 启用 B站 AI Bot 协同 | bilibili_config |
| `enable_group_slang_web_search` | 黑话释义联网参考 | group_slang_topic_config |
| `group_slang_web_search_results` | 每词搜索摘要条数 | group_slang_topic_config |
| `group_slang_web_search_terms` | 黑话联网候选扫描数 | group_slang_topic_config |
| `ai_daily_prefer_text_version` | AI 日报/早报优先文字版 | news_config |
| `ai_daily_source_uid` | 兼容旧版 AI 早报 UID | news_config |
| `ai_daily_sources` | AI 日报/早报定时来源 | news_config |
| `bilibili_share_cooldown_hours` | B 站视频分享冷却（小时） | news_config |
| `enable_ai_daily_watch` | 追踪每日 AI 日报/早报 | news_config |
| `enable_news_boredom_read` | 无聊时看新闻 | news_config |
| `enable_news_integration` | 启用新闻阅读 | news_config |
| `news_max_items_per_source` | 单源最多读取条数 | news_config |
| `news_min_interval_hours` | 看新闻最小间隔（小时） | news_config |
| `news_sources` | 新闻源 | news_config |
| `enable_reading_archive_boredom_read` | 空闲时资料归档 | reading_archive_config |
| `enable_reading_archive_integration` | 启用资料归档素材 | reading_archive_config |
| `reading_archive_default_keywords` | 资料归档默认搜索关键词 | reading_archive_config |
| `reading_archive_max_photo_count` | 资料归档页数上限 | reading_archive_config |
| `reading_archive_min_interval_hours` | 资料归档最小间隔（小时） | reading_archive_config |
| `WEB_EXPLORATION_API_BASE_URL` | 主动搜索自定义接口地址 | web_exploration_config |
| `WEB_EXPLORATION_API_KEY` | 主动搜索自定义接口 API Key | web_exploration_config |
| `WEB_EXPLORATION_API_MODEL` | 主动搜索自定义接口模型 | web_exploration_config |
| `enable_news_daily_hot_read` | 每日获取热点 | web_exploration_config |
| `enable_web_exploration` | 启用主动搜索 | web_exploration_config |
| `enable_web_exploration_boredom_search` | 空档时自主搜索 | web_exploration_config |
| `news_hot_max_items` | 热点候选数量 | web_exploration_config |
| `news_hot_sources` | 热点来源 | web_exploration_config |
| `web_exploration_interests` | 探索兴趣倾向 | web_exploration_config |
| `web_exploration_max_results` | 网页搜索结果数 | web_exploration_config |
| `web_exploration_min_interval_hours` | 网页探索最小间隔（小时） | web_exploration_config |

### B 段（角色内核）

#### B1 角色内核·认知与记忆 — 73 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `enable_auto_user_profile_creation` | 新用户最小档案 | basic_config |
| `portrait_global_mode` | 全局智能画像模式 | basic_config |
| `enable_livingmemory_integration` | 启用外部记忆插件协同 | external_memory_config |
| `enable_memory_companion_bridge` | 独立启用 MemoryCompanion Bridge | external_memory_config |
| `enable_memory_companion_cross_window_emotion` | 跨窗口情绪连续性 | external_memory_config |
| `enable_memory_companion_dream_fragment` | 梦境碎片写入 | external_memory_config |
| `enable_memory_companion_emotional_drift` | 情绪漂移联动 | external_memory_config |
| `enable_memory_companion_feature_context` | 功能上下文读取 | external_memory_config |
| `enable_memory_companion_open_loop_search` | 未完成话题取材 | external_memory_config |
| `enable_memory_companion_private_recall` | 私聊选择性长期召回 | external_memory_config |
| `enable_new_framework_reflection_writer` | 启用新框架每日反思归档 | external_memory_config |
| `enable_new_framework_s4_trial` | 启用 S4 工作便笺试用 | external_memory_config |
| `livingmemory_tool_name` | 记忆召回工具名 | external_memory_config |
| `memory_companion_context_max_chars` | 上下文最大字符数 | external_memory_config |
| `memory_companion_context_timeout_seconds` | 记忆上下文超时（秒） | external_memory_config |
| `memory_companion_context_top_k` | 上下文召回条数 | external_memory_config |
| `enable_group_joke_guard` | 群聊接梗边界护栏 | group_observation_config |
| `enable_group_moment_portrait` | 名场面互动线索 | group_observation_config |
| `enable_group_moments` | 群聊名场面记忆 | group_observation_config |
| `enable_group_mood_detection` | 群聊氛围感知 | group_observation_config |
| `enable_group_persona_denoise` | 群聊人格降噪 | group_observation_config |
| `enable_group_roleplay_strength` | 群聊扮演强度自适应 | group_observation_config |
| `enable_group_social_context` | 群聊社交氛围总开关 | group_observation_config |
| `enable_group_relationship_graph` | 启用群友互动图 | group_relationship_config |
| `enable_worldbook_member_recognition` | 启用群聊关系网 | group_relationship_config |
| `worldbook_auto_import` | 启动时自动刷新关系网 | group_relationship_config |
| `worldbook_auto_pending_observations` | 低频生成待确认观察 | group_relationship_config |
| `worldbook_config_paths` | 关系网配置文件路径 | group_relationship_config |
| `worldbook_member_inject_limit` | 关系节点单次注入上限 | group_relationship_config |
| `worldbook_member_match_aliases` | 允许称呼辅助匹配 | group_relationship_config |
| `worldbook_self_registration` | 允许群聊自登记节点 | group_relationship_config |
| `worldbook_self_registration_block_reply` | 自登记拒绝回复 | group_relationship_config |
| `worldbook_self_registration_block_words` | 自登记拒绝词 | group_relationship_config |
| `enable_group_episode_memory` | 启用群聊片段记忆 | group_slang_topic_config |
| `enable_group_member_profiles` | 启用群内成员观察 | group_slang_topic_config |
| `enable_group_slang_learning` | 启用群内黑话/梗学习 | group_slang_topic_config |
| `enable_group_slang_meanings` | 启用群内黑话语义解释 | group_slang_topic_config |
| `enable_group_topic_threads` | 启用群聊话题线程 | group_slang_topic_config |
| `roleplay_knowledge_source_ids` | 角色设定：AstrBot 知识库选择 | life_schedule_config |
| `roleplay_user_profile_prompt` | 角色设定：用户与关系补充 | life_schedule_config |
| `enable_companion_memory` | 启用本地陪伴画像 | memory_habit_config |
| `enable_expression_learning` | 启用跨会话表达方式学习 | memory_habit_config |
| `enable_expression_manual_review` | 观察素材手动审核 | memory_habit_config |
| `enable_expression_style_review` | 表达发送前审核 | memory_habit_config |
| `enable_food_menu_recommendation` | 启用吃什么候选 | memory_habit_config |
| `enable_user_habit_learning` | 启用用户习惯画像 | memory_habit_config |
| `expression_group_application_ids` | 群聊使用对象 ID | memory_habit_config |
| `expression_group_application_mode` | 群聊使用范围 | memory_habit_config |
| `expression_group_learning_daily_batch_limit` | 群聊语义归纳每日批次上限 | memory_habit_config |
| `expression_group_learning_min_new_messages` | 每批最少新增群消息 | memory_habit_config |
| `expression_group_learning_source_ids` | 群聊学习来源 ID | memory_habit_config |
| `expression_group_learning_source_mode` | 群聊学习来源 | memory_habit_config |
| `expression_learning_mode` | 表达应用模式 | memory_habit_config |
| `expression_private_application_mode` | 私聊使用范围 | memory_habit_config |
| `expression_private_application_user_ids` | 私聊使用对象 ID | memory_habit_config |
| `expression_private_learning_source_ids` | 私聊学习来源 ID | memory_habit_config |
| `expression_private_learning_source_mode` | 私聊学习来源 | memory_habit_config |
| `max_companion_memory_items` | 本地画像条目上限 | memory_habit_config |
| `max_learned_expression_items` | 每来源学习资料上限 | memory_habit_config |
| `memory_refresh_interval_minutes` | 本地画像整理间隔（分钟） | memory_habit_config |
| `user_habit_max_items` | 习惯条目上限 | memory_habit_config |
| `user_habit_min_count` | 习惯成型次数 | memory_habit_config |
| `enable_reading_archive_preference_influence` | 评分偏好影响私聊 | reading_archive_config |
| `enable_reading_archive_rating` | 资料阅读评价 | reading_archive_config |
| `reading_archive_preference_max_terms` | 偏好注入最多词条 | reading_archive_config |
| `reading_archive_preference_min_ratings` | 偏好生效最少评分数 | reading_archive_config |
| `group_episode_refresh_minutes` | 群聊片段整理间隔（分钟） | relay_bridge_config |
| `group_slang_summary_minutes` | 群内黑话语义整理间隔（分钟） | relay_bridge_config |
| `max_group_episodes` | 最多保留群聊片段数量 | relay_bridge_config |
| `max_group_recent_messages` | 群聊最近消息保留数 | relay_bridge_config |
| `max_group_relationship_edges` | 最多保留群友互动边 | relay_bridge_config |
| `max_group_slang_terms` | 群内常见词保留数 | relay_bridge_config |
| `max_group_topic_threads` | 最多保留群聊话题线程数 | relay_bridge_config |

#### B2 角色内核·关系与情感 — 98 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `LLM_PROVIDER_ID` | 主模型 / 日程模型（留空用 AstrBot 默认） | basic_config |
| `acquaintance` | 初识 | basic_config |
| `auto_profile_platforms` | 自动建档平台 | basic_config |
| `close` | 亲近 | basic_config |
| `deeply_bonded` | 深度联结 | basic_config |
| `deeply_distant` | 极度疏离 | basic_config |
| `default_enable_configured_targets` | 启动时预热私聊目标 | basic_config |
| `default_interaction_band` | 新档案默认互动状态 | basic_config |
| `distant` | 疏离 | basic_config |
| `enable_custom_relationship_stage_policy` | 启用好感度系统 | basic_config |
| `enable_group_relationship_affinity` | 允许测试群贡献统一好感度 | basic_config |
| `enable_relationship_stage_provider_routing` | 按亲密度阶段选择对话模型 | basic_config |
| `familiar` | 熟悉 | basic_config |
| `group_relationship_affinity_allowlist` | 好感度测试群白名单 | basic_config |
| `group_relationship_daily_net_cap` | 每人每群每日净变化上限 | basic_config |
| `group_relationship_person_daily_absolute_cap` | 每人跨群每日绝对量上限 | basic_config |
| `group_relationship_scope_daily_absolute_cap` | 每群全体每日绝对量上限 | basic_config |
| `group_relationship_window_absolute_cap` | 每人每群窗口绝对量上限 | basic_config |
| `group_relationship_window_minutes` | 群好感度滚动窗口（分钟） | basic_config |
| `intimate` | 亲密 | basic_config |
| `normal_interaction_band_cap` | 普通用户互动温度上限 | basic_config |
| `owner_exclusive` | 专属联结 | basic_config |
| `owner_exclusive_address_style` | 主要用户专属称呼尺度 | basic_config |
| `owner_exclusive_label` | 主要用户专属关系名称 | basic_config |
| `owner_exclusive_proactive_limit` | 主要用户专属主动阶段上限 | basic_config |
| `owner_exclusive_tone` | 主要用户专属基础表达 | basic_config |
| `owner_group_interaction_projection` | 主要用户群聊互动状态降级 | basic_config |
| `owner_group_relationship_projection` | 主要用户群聊长期关系降级 | basic_config |
| `relationship_decay_early_per_day` | 回落前段每日扣分 | basic_config |
| `relationship_decay_grace_days` | 自然回落宽限天数 | basic_config |
| `relationship_decay_late_per_day` | 回落后段每日扣分 | basic_config |
| `relationship_decay_middle_per_day` | 回落中段每日扣分 | basic_config |
| `relationship_event_window_minutes` | 亲密度事件去重窗口（分钟） | basic_config |
| `relationship_negative_event_cap` | 单次负向亲密度上限 | basic_config |
| `relationship_positive_daily_cap` | 每日正向亲密度上限 | basic_config |
| `relationship_positive_event_cap` | 单次正向亲密度上限 | basic_config |
| `relationship_positive_stage_cap_key` | 普通用户正向亲密度阶段上限 | basic_config |
| `relationship_stage_policy` | 亲密度阶段策略数据 | basic_config |
| `strongly_distant` | 强烈疏离 | basic_config |
| `enable_dialogue_episode_memory` | 启用对话片段记忆 | emotion_relationship_config |
| `enable_intent_emotion_analysis` | 启用本地意图/情绪快判 | emotion_relationship_config |
| `enable_open_loop_tracking` | 启用未完成约定追踪 | emotion_relationship_config |
| `enable_relationship_analysis` | 启用模型关系站位分析 | emotion_relationship_config |
| `enable_relationship_state_machine` | 启用关系距离感 | emotion_relationship_config |
| `episode_memory_refresh_messages` | 对话片段整理消息数阈值 | emotion_relationship_config |
| `episode_memory_refresh_minutes` | 对话片段整理时间阈值（分钟） | emotion_relationship_config |
| `max_dialogue_episodes` | 最多保留对话片段数量 | emotion_relationship_config |
| `emotion_judgement_mode` | 模型复核范围 | experimental_motivation_config |
| `emotional_gate_hurt_threshold` | 伤心触发阈值 | experimental_motivation_config |
| `emotional_gate_max_hurt_minutes` | 最长收敛分钟 | experimental_motivation_config |
| `emotional_gate_recovery_per_hour` | 每小时缓和量 | experimental_motivation_config |
| `emotional_gate_refuse_threshold` | 生气触发阈值 | experimental_motivation_config |
| `enable_emotion_simulation` | 启用情绪模拟 | experimental_motivation_config |
| `enable_llm_emotion_judgement` | 启用模型复核情绪变化 | experimental_motivation_config |
| `enable_reaction_expression_experiment` | 启用表情表达实验 | experimental_motivation_config |
| `enable_relationship_boundary_apology` | 允许道歉修复 | experimental_motivation_config |
| `enable_relationship_boundary_bottom_line` | 启用底线递进处理 | experimental_motivation_config |
| `enable_relationship_boundary_feedback` | 启用档位边界判断 | experimental_motivation_config |
| `enable_relationship_boundary_owner_report` | 允许向主要用户转达 | experimental_motivation_config |
| `enable_relationship_boundary_stage` | 启用越界阶段推进 | experimental_motivation_config |
| `enable_relationship_boundary_vent` | 允许向亲近对象吐槽 | experimental_motivation_config |
| `enable_relationship_violation_penalties` | 启用关系底线余波 | experimental_motivation_config |
| `relationship_boundary_apology_duplicate_limit` | 同类道歉有效次数 | experimental_motivation_config |
| `relationship_boundary_apology_restore_ratio` | 道歉恢复比例 | experimental_motivation_config |
| `relationship_boundary_apology_speedup_multiplier` | 道歉后恢复加速倍数 | experimental_motivation_config |
| `relationship_boundary_bottom_line_baseline` | 角色专属底线基线 | experimental_motivation_config |
| `relationship_boundary_cold_minutes` | 冷静阶段最长分钟 | experimental_motivation_config |
| `relationship_boundary_owner_report_probability_bottom_line` | 底线事件转达概率 | experimental_motivation_config |
| `relationship_boundary_owner_report_probability_light` | 轻度事件转达概率 | experimental_motivation_config |
| `relationship_boundary_owner_report_probability_mid` | 中度事件转达概率 | experimental_motivation_config |
| `relationship_boundary_owner_report_probability_severe` | 严重事件转达概率 | experimental_motivation_config |
| `relationship_boundary_penalty_bottom_line` | 踩底线扣分 | experimental_motivation_config |
| `relationship_boundary_penalty_light` | 轻度越界扣分 | experimental_motivation_config |
| `relationship_boundary_penalty_mid` | 中度越界扣分 | experimental_motivation_config |
| `relationship_boundary_penalty_severe` | 严重越界扣分 | experimental_motivation_config |
| `relationship_boundary_recover_ratio_light` | 轻度事件可恢复比例 | experimental_motivation_config |
| `relationship_boundary_recover_ratio_mid` | 中度事件可恢复比例 | experimental_motivation_config |
| `relationship_boundary_recover_ratio_severe` | 严重事件可恢复比例 | experimental_motivation_config |
| `relationship_boundary_stage_avoid_points` | 开始回避的累计值 | experimental_motivation_config |
| `relationship_boundary_stage_forbid_points` | 明确拒绝的累计值 | experimental_motivation_config |
| `relationship_boundary_stage_reflect_points` | 冷静反思的累计值 | experimental_motivation_config |
| `relationship_boundary_tier_adaptive` | 按关系档位调节 | experimental_motivation_config |
| `relationship_boundary_tone_bottom_line` | 踩底线反应 | experimental_motivation_config |
| `relationship_boundary_tone_communicate` | 高关系档位反应策略 | experimental_motivation_config |
| `relationship_boundary_tone_confession` | 收到表白时的反应 | experimental_motivation_config |
| `relationship_boundary_tone_light` | 轻度越界反应 | experimental_motivation_config |
| `relationship_boundary_tone_mid` | 中度越界反应 | experimental_motivation_config |
| `relationship_boundary_tone_severe` | 严重越界反应 | experimental_motivation_config |
| `relationship_boundary_tone_silent` | 低关系档位反应策略 | experimental_motivation_config |
| `relationship_boundary_vent_probability_bottom_line` | 底线事件倾诉概率 | experimental_motivation_config |
| `relationship_boundary_vent_probability_light` | 轻度事件倾诉概率 | experimental_motivation_config |
| `relationship_boundary_vent_probability_mid` | 中度事件倾诉概率 | experimental_motivation_config |
| `relationship_boundary_vent_probability_severe` | 严重事件倾诉概率 | experimental_motivation_config |
| `relationship_boundary_vent_scene_template` | 倾诉场景模板 | experimental_motivation_config |
| `relationship_boundary_vent_targets` | 倾诉对象 | experimental_motivation_config |
| `relationship_violation_recovery_minutes_per_point` | 关系底线点恢复速度 | experimental_motivation_config |
| `bot_relationship_cards` | 关系网角色卡 | photo_action_config |
| `enable_bot_relationship_network` | Bot 关系网 | photo_action_config |

#### B3 角色内核·角色自我 — 72 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `worldview_adaptation_mode` | 世界观适配模式 | basic_config |
| `worldview_adaptation_prompt` | 自定义世界观适配提示 | basic_config |
| `dream_afterglow_mode` | 梦境余韵影响强度 | dream_diary_config |
| `dream_theme_candidates` | 梦境题材候选（逗号分隔） | dream_diary_config |
| `enable_enhanced_dreams` | 启用强化梦境生成 | dream_diary_config |
| `enable_intimate_dream_theme` | 允许暧昧/春梦题材 | dream_diary_config |
| `enable_mixed_dream_themes` | 允许梦境题材轻微混搭 | dream_diary_config |
| `advanced_cycle_discomfort_chance` | 不适出现概率 | humanized_state_config |
| `advanced_cycle_discomfort_simulation` | 生理期不适模拟 | humanized_state_config |
| `advanced_cycle_discomfort_types` | 可模拟的不适类型 | humanized_state_config |
| `advanced_cycle_follicular_days` | 卵泡期持续天数 | humanized_state_config |
| `advanced_cycle_follicular_energy` | 卵泡期精力变化 | humanized_state_config |
| `advanced_cycle_follicular_mood` | 卵泡期情绪底色 | humanized_state_config |
| `advanced_cycle_follicular_prompt` | 卵泡期状态描述 | humanized_state_config |
| `advanced_cycle_link_intensity` | 精力变化跟随拟人状态强度 | humanized_state_config |
| `advanced_cycle_luteal_days` | 黄体期持续天数 | humanized_state_config |
| `advanced_cycle_luteal_energy` | 黄体期精力变化 | humanized_state_config |
| `advanced_cycle_luteal_mood` | 黄体期情绪底色 | humanized_state_config |
| `advanced_cycle_luteal_prompt` | 黄体期状态描述 | humanized_state_config |
| `advanced_cycle_menstrual_days` | 月经期持续天数 | humanized_state_config |
| `advanced_cycle_menstrual_energy` | 月经期精力变化 | humanized_state_config |
| `advanced_cycle_menstrual_mood` | 月经期情绪底色 | humanized_state_config |
| `advanced_cycle_menstrual_prompt` | 月经期状态描述 | humanized_state_config |
| `advanced_cycle_ovulation_days` | 排卵期持续天数 | humanized_state_config |
| `advanced_cycle_ovulation_energy` | 排卵期精力变化 | humanized_state_config |
| `advanced_cycle_ovulation_mood` | 排卵期情绪底色 | humanized_state_config |
| `advanced_cycle_ovulation_prompt` | 排卵期状态描述 | humanized_state_config |
| `advanced_cycle_pms_days` | PMS 期持续天数 | humanized_state_config |
| `advanced_cycle_pms_energy` | PMS 期精力变化 | humanized_state_config |
| `advanced_cycle_pms_mood` | PMS 期情绪底色 | humanized_state_config |
| `advanced_cycle_pms_prompt` | PMS 期状态描述 | humanized_state_config |
| `advanced_cycle_pre_ovulation_days` | 排卵前期持续天数 | humanized_state_config |
| `advanced_cycle_pre_ovulation_energy` | 排卵前期精力变化 | humanized_state_config |
| `advanced_cycle_pre_ovulation_mood` | 排卵前期情绪底色 | humanized_state_config |
| `advanced_cycle_pre_ovulation_prompt` | 排卵前期状态描述 | humanized_state_config |
| `advanced_cycle_start_offset` | 手动设置当前周期日 | humanized_state_config |
| `enable_advanced_cycle_strategy` | 启用六阶段周期策略 | humanized_state_config |
| `enable_cycle_state` | 启用生理期模拟 | humanized_state_config |
| `enable_group_cycle_awareness` | 允许在已授权群聊中使用最低限度的 Bot 周期语气边界 | humanized_state_config |
| `enable_health_state` | 启用健康/不适状态 | humanized_state_config |
| `enable_humanized_states` | 启用拟人化身体/梦境状态 | humanized_state_config |
| `enable_hunger_state` | 启用饥饿/胃口状态 | humanized_state_config |
| `enable_rest_reply_simulation` | 启用休息回复闸门 | humanized_state_config |
| `humanized_state_intensity` | 拟人状态强度 | humanized_state_config |
| `rest_reply_active_windows` | 休息闸门生效时段 | humanized_state_config |
| `rest_reply_awake_grace_minutes` | 醒后免重判分钟数 | humanized_state_config |
| `rest_reply_llm_threshold` | 模型醒来阈值 | humanized_state_config |
| `rest_reply_mode` | 休息回复判定模式 | humanized_state_config |
| `rest_reply_probability` | 休息中概率回复（%） | humanized_state_config |
| `daily_plan_item_count` | 每日日程条目数 | life_schedule_config |
| `daily_plan_prompt` | 自定义每日日程提示词 | life_schedule_config |
| `daily_plan_time` | 每日生成日程时间 | life_schedule_config |
| `enable_daily_plan` | 启用每日拟人化日程 | life_schedule_config |
| `schedule_persona_prompt` | 日程专用角色设定 | life_schedule_config |
| `schedule_worldview_prompt` | 日程专用世界观/生活背景 | life_schedule_config |
| `daily_review_auto_apply_guidance` | 自动应用低风险次日纠偏 | schedule_detail_config |
| `daily_review_retention_days` | 巡视报告保留天数 | schedule_detail_config |
| `daily_review_time` | 每日巡视时间 | schedule_detail_config |
| `detail_enhancement_lead_minutes` | 提前强化日程段（分钟） | schedule_detail_config |
| `enable_daily_case_review_experiment` | 实验性：启用每日逐案复盘 | schedule_detail_config |
| `enable_daily_review` | 启用每日终盘巡视 | schedule_detail_config |
| `enable_detail_enhancement` | 启用日程细节强化模式 | schedule_detail_config |
| `enable_postprocessing_trace` | 保存后处理效果排查记录 | schedule_detail_config |
| `important_date_lookahead_days` | 重要日期默认提前提醒天数 | schedule_detail_config |
| `enable_personal_goal_auto_progress` | 按已完成日程自动推进 | skill_growth_config |
| `enable_personal_goals` | 启用非创作型个人目标 | skill_growth_config |
| `enable_skill_growth_passive_injection` | 被动回复技能认知 | skill_growth_config |
| `enable_skill_growth_schedule_influence` | 技能约束日程表现 | skill_growth_config |
| `enable_skill_growth_simulation` | 启用技能成长模拟 | skill_growth_config |
| `skill_growth_custom_skills` | 自定义技能列表（兼容旧配置） | skill_growth_config |
| `skill_growth_rate` | 技能成长倍率 | skill_growth_config |
| `skill_growth_schedule_influence_strength` | 技能约束强度 | skill_growth_config |

#### B4 角色内核·决策与主动 — 144 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `balance_message_cooldown_hours` | 低余额主动冷却（小时） | balance_awareness_config |
| `default_proactive_daily_limit` | 新用户每日主动上限 | basic_config |
| `default_proactive_enabled` | 新用户默认主动权限 | basic_config |
| `enable_proactive_only_mode` | 仅保留主动能力 | basic_config |
| `quiet_hours` | 免打扰时间 | basic_config |
| `bilibili_share_probability` | 视频私聊分享概率 | bilibili_config |
| `allow_insomnia_night_message` | 允许失眠时深夜主动消息 | daily_creative_config |
| `enable_daily_greetings` | 启用早午晚锚点问候 | daily_creative_config |
| `greeting_idle_minutes` | 问候前空闲门槛（分钟） | daily_creative_config |
| `proactive_share_probability` | 主动分享可做事项概率 | daily_creative_config |
| `enable_experimental_motivation_model` | 启用驱力-诱因-唤醒调度 | experimental_motivation_config |
| `enable_maslow_motivation_experiment` | 启用需求强化功能 | experimental_motivation_config |
| `enable_maslow_schedule_influence` | 允许影响日程生成 | experimental_motivation_config |
| `enable_personality_iteration_auto_tune` | 允许自主调节参数 | experimental_motivation_config |
| `enable_personality_iteration_experiment` | 启用角色贴合校准 | experimental_motivation_config |
| `maslow_motivation_strength` | 需求强化影响强度 | experimental_motivation_config |
| `new_framework_s4_daily_model_calls` | S4 每日后台模型请求上限 | external_memory_config |
| `new_framework_s4_daily_photo_calls` | S4 相册每日生图请求上限 | external_memory_config |
| `new_framework_s4_max_context_chars` | S4 后台接续上下文字符上限 | external_memory_config |
| `new_framework_s4_max_job_model_calls` | S4 单个后台任务的模型请求上限 | external_memory_config |
| `new_framework_s4_min_interval_minutes` | S4 后台接续最短间隔（分钟） | external_memory_config |
| `new_framework_s4_persona_ids` | S4 试用角色 | external_memory_config |
| `new_framework_s4_provider_id` | S4 后台模型 Provider ID | external_memory_config |
| `enable_group_interjection` | 允许群聊主动插话 | group_interject_config |
| `enable_group_interjection_feedback` | 启用群聊插话反馈学习 | group_interject_config |
| `enable_group_repeat_follow` | 允许群聊复读跟读 | group_interject_config |
| `group_interject_max_daily` | 每群每日最多主动插话次数 | group_interject_config |
| `group_interject_min_interval_minutes` | 群聊主动插话最小间隔（分钟） | group_interject_config |
| `group_repeat_count_distinct_users_only` | 复读只计不同用户 | group_interject_config |
| `group_repeat_follow_probability` | 复读跟读初始概率（%） | group_interject_config |
| `group_repeat_interrupt_image_path` | 复读打断表情包路径 | group_interject_config |
| `group_repeat_interrupt_probability` | 复读打断初始概率（%） | group_interject_config |
| `group_repeat_interrupt_probability_step` | 复读概率共同递增（%） | group_interject_config |
| `group_repeat_interrupt_text` | 复读打断文本 | group_interject_config |
| `group_repeat_trigger_threshold` | 复读触发阈值 | group_interject_config |
| `enable_group_image_wakeup` | 图片命中唤醒 Bot | group_observation_config |
| `enable_group_bot_name_wakeup` | Bot 名字作为强唤醒词 | group_wakeup_config |
| `enable_group_wakeup_cold_group` | 启用冷群唤醒 | group_wakeup_config |
| `enable_group_wakeup_enhancement` | 启用群聊唤醒强化 | group_wakeup_config |
| `enable_group_wakeup_question` | 启用解惑唤醒 | group_wakeup_config |
| `group_wakeup_cold_group_idle_minutes` | 冷群判定分钟 | group_wakeup_config |
| `group_wakeup_cold_group_threshold` | 冷群强度阈值 | group_wakeup_config |
| `group_wakeup_context_words` | 弱相关唤醒词 | group_wakeup_config |
| `group_wakeup_cooldown_seconds` | 唤醒冷却秒数 | group_wakeup_config |
| `group_wakeup_debounce_pending_penalty` | 收口等待兴趣降权 | group_wakeup_config |
| `group_wakeup_direct_words` | 强唤醒词 | group_wakeup_config |
| `group_wakeup_fatigue_decay_minutes` | 唤醒疲劳恢复分钟 | group_wakeup_config |
| `group_wakeup_fatigue_limit` | 唤醒疲劳阈值 | group_wakeup_config |
| `group_wakeup_generated_keyword_limit` | 自动兴趣词上限 | group_wakeup_config |
| `group_wakeup_interest_keywords` | 手动兴趣关键词 | group_wakeup_config |
| `group_wakeup_interest_probability` | 兴趣唤醒概率 | group_wakeup_config |
| `group_wakeup_log_limit` | 唤醒记录上限 | group_wakeup_config |
| `group_wakeup_owner_direct_words` | 主要用户专属强唤醒词 | group_wakeup_config |
| `group_wakeup_question_threshold` | 解惑强度阈值 | group_wakeup_config |
| `group_wakeup_short_text_wait_seconds` | 短唤醒补话等待秒数 | group_wakeup_config |
| `group_wakeup_topic_interest_max_boost` | 话题兴趣权重上限 | group_wakeup_config |
| `include_schedule_in_messages` | 允许主动消息偶尔带上当前日程背景 | life_schedule_config |
| `enable_meal_care_proactive` | 启用饭点主动关心 | memory_habit_config |
| `meal_care_followup_minutes` | 吃饭补问等待分钟 | memory_habit_config |
| `meal_care_max_daily` | 每日最多饭点关心次数 | memory_habit_config |
| `meal_care_min_interval_hours` | 饭点关心最短间隔小时 | memory_habit_config |
| `enable_external_event_self_link` | 外界信息自我关联 | news_config |
| `external_event_idle_minutes` | 外部消息分享空闲下限（分钟） | news_config |
| `external_event_idle_strong_minutes` | 强自我关联时空闲下限（分钟） | news_config |
| `external_event_self_link_cooldown_hours` | 自我关联冷却（小时） | news_config |
| `external_event_self_link_override_min_desire` | 意愿放宽·最低分享欲 | news_config |
| `external_event_self_link_override_min_relevance` | 意愿放宽·最低相关度 | news_config |
| `external_event_self_link_override_probability` | 意愿放宽·分享概率保底 | news_config |
| `external_event_self_link_probability` | 自我关联分享欲倍率 | news_config |
| `external_event_share_min_total` | 外部消息统一评分下限 | news_config |
| `external_link_share_cooldown_hours` | 主动外链统一冷却（小时） | news_config |
| `external_share_require_source_link` | 外部共享强制带来源链接 | news_config |
| `news_share_cooldown_hours` | 新闻分享冷却（小时） | news_config |
| `news_share_probability` | 新闻私聊分享概率 | news_config |
| `web_exploration_share_cooldown_hours` | 主动搜索分享冷却（小时） | news_config |
| `check_interval_seconds` | 检查间隔（秒） | private_followup_config |
| `enable_group_air_reply_guard` | 启用群聊读空气防互刷 | private_followup_config |
| `enable_group_conversation_followup` | 启用群聊连续对话保持 | private_followup_config |
| `enable_proactive_burst` | 主动消息爆发式发送 | private_followup_config |
| `friend_unanswered_max_cooldown_hours` | 次要用户未回应最长冷却（小时） | private_followup_config |
| `group_air_guard_max_bot_replies` | 窗口内最大 Bot 回复数 | private_followup_config |
| `group_air_guard_polite_loop_limit` | 礼貌收尾循环上限 | private_followup_config |
| `group_air_guard_window_seconds` | 读空气检测窗口秒数 | private_followup_config |
| `group_conversation_followup_max_turns` | 群聊连续续接上限 | private_followup_config |
| `group_conversation_followup_seconds` | 群聊上下文续接判断秒数 | private_followup_config |
| `idle_minutes` | 空闲多久后可主动问候（分钟） | private_followup_config |
| `min_interval_minutes` | 同一用户最小主动间隔（分钟） | private_followup_config |
| `proactive_burst_gap_max_seconds` | 爆发消息最大间隔（秒） | private_followup_config |
| `proactive_burst_gap_min_seconds` | 爆发消息最小间隔（秒） | private_followup_config |
| `proactive_burst_max_messages` | 爆发式发送最多消息数 | private_followup_config |
| `proactive_hour_activity_curve` | 主动小时活跃曲线 | private_followup_config |
| `proactive_unanswered_max_interval_multiplier` | 未回应最大间隔倍率 | private_followup_config |
| `proactive_unanswered_pause_after` | 未回应几次后暂停普通主动 | private_followup_config |
| `proactive_unanswered_slowdown_start` | 未回应几次后开始降频 | private_followup_config |
| `require_private_opt_in` | 限制私聊命令管理入口 | private_followup_config |
| `timer_pre_silence_minutes` | 预约前静默窗口（分钟） | private_followup_config |
| `proactive_dedup_enabled` | 启用发送前相似度去重 | proactive_dedup_config |
| `proactive_dedup_last_message_enabled` | 对比最后一条 Bot 消息 | proactive_dedup_config |
| `proactive_dedup_last_message_window_minutes` | 最后一条 Bot 消息去重窗口（分钟） | proactive_dedup_config |
| `proactive_dedup_min_overlap_ratio` | 大签名最小重叠比例 | proactive_dedup_config |
| `proactive_dedup_min_shared_tokens` | 小签名最少共享锚点数 | proactive_dedup_config |
| `proactive_dedup_policies` | 应用去重的路由策略 | proactive_dedup_config |
| `proactive_dedup_sent_window_minutes` | 已发送主动话题去重窗口（分钟） | proactive_dedup_config |
| `proactive_dedup_weather_window_minutes` | 天气话题长时窗口（分钟） | proactive_dedup_config |
| `PROACTIVE_PERSONA_JUDGE_PROVIDER_ID` | 主动人格判定模型 | proactive_generation_config |
| `enable_llm_proactive_message` | 主动消息发送前调用 LLM 生成文本 | proactive_generation_config |
| `enable_llm_proactive_persona_judge` | 主动计划人格/世界观判定 | proactive_generation_config |
| `enable_proactive_chat_integration` | 联动 Proactive Chat | proactive_generation_config |
| `proactive_chat_bridge_collision_window_seconds` | 调度防撞窗口（秒） | proactive_generation_config |
| `proactive_chat_bridge_review_mode` | Proactive Chat 联动复核模式 | proactive_generation_config |
| `proactive_generation_history_limit` | 主动生成召回消息数 | proactive_generation_config |
| `proactive_history_context_mode` | 主动消息历史整理模式 | proactive_generation_config |
| `proactive_history_max_chars` | 主动上下文字符上限 | proactive_generation_config |
| `proactive_history_recent_raw_count` | 最近原文消息数 | proactive_generation_config |
| `proactive_persona_judge_cache_minutes` | 主动人格判定缓存（分钟） | proactive_generation_config |
| `proactive_persona_judge_max_daily` | 主动人格判定每日模型上限 | proactive_generation_config |
| `proactive_persona_judge_send_threshold` | 主动人格判定放行阈值 | proactive_generation_config |
| `proactive_prompt_template` | 主动消息提示词模板 | proactive_generation_config |
| `proactive_reply_context_hours` | 主动消息回复上下文保留时间（小时） | proactive_generation_config |
| `max_daily_messages` | 每日主动消息配额 | proactive_reach_config |
| `proactive_closing_grace_minutes` | 主动收束留白分钟数 | proactive_reach_config |
| `proactive_intensity_preset` | 主动强度预设 | proactive_reach_config |
| `proactive_preempt_queue_enabled` | 主动候选挤占时入池排队 | proactive_reach_config |
| `proactive_preempt_queue_expire_hours` | 排队候选最长存活小时数 | proactive_reach_config |
| `proactive_share_priority` | 外部分享类主动优先级 | proactive_reach_config |
| `qzone_life_publish_allow_insomnia_night` | 失眠时允许凌晨说说 | qzone_config |
| `qzone_life_publish_intra_day_gap_minutes` | 同日说说最小间隔（分钟） | qzone_config |
| `qzone_life_publish_max_daily` | 每日自动说说上限 | qzone_config |
| `qzone_life_publish_min_interval_hours` | 生活说说跨日最小间隔（小时） | qzone_config |
| `qzone_life_publish_probability` | 生活说说触发概率 | qzone_config |
| `qzone_life_publish_similarity_threshold` | 说说去重相似阈值 | qzone_config |
| `qzone_life_publish_window_mode` | 发布时段模式 | qzone_config |
| `qzone_life_publish_windows` | 自定义发布窗口 | qzone_config |
| `enable_reading_archive_ask_recommendation` | 向用户征求推荐 | reading_archive_config |
| `reading_archive_ask_probability` | 征求推荐触发概率 | reading_archive_config |
| `reading_archive_share_probability` | 阅读后主动提起概率 | reading_archive_config |
| `personal_goal_share_cooldown_hours` | 目标进展分享冷却（小时） | skill_growth_config |
| `personal_goal_stall_days` | 停滞提醒天数 | skill_growth_config |
| `enable_proactive_quote_trigger_message` | 群回复/主动引用触发消息 | timer_config |
| `max_proactive_plan_lag_minutes` | 主动候选过期重排时间（分钟） | timer_config |
| `enable_environment_change_proactive` | 环境突变主动消息 | weather_config |
| `environment_change_check_minutes` | 环境突变检测间隔（分钟） | weather_config |
| `environment_change_cooldown_minutes` | 环境突变消息冷却（分钟） | weather_config |
| `web_exploration_share_probability` | 探索后私聊分享概率 | web_exploration_config |

### C 段（产出）

#### C1 产出·图像生成 — 55 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `enable_new_framework_s4_album` | S4 角色活动相册拍照 | external_memory_config |
| `BACKUP_EXTERNAL_IMAGE_API_BASE_URL` | 备选在线图片 API 地址 | photo_action_config |
| `BACKUP_EXTERNAL_IMAGE_API_KEY` | 备选在线图片 API Key | photo_action_config |
| `BACKUP_EXTERNAL_IMAGE_API_MODEL` | 备选在线图片模型 | photo_action_config |
| `COMFYUI_SELFIE_WORKFLOW_NAME` | 主动自拍工作流名 | photo_action_config |
| `COMFYUI_TEXT2IMG_WORKFLOW_NAME` | 主动拍照文生图工作流名 | photo_action_config |
| `EXTERNAL_IMAGE_API_BASE_URL` | 在线图片 API 地址 | photo_action_config |
| `EXTERNAL_IMAGE_API_KEY` | 在线图片 API Key | photo_action_config |
| `EXTERNAL_IMAGE_API_MODEL` | 在线图片模型 | photo_action_config |
| `backup_external_image_api_custom_headers` | 备选在线生图自定义请求头 | photo_action_config |
| `backup_external_image_api_platform` | 备选在线生图模型平台 | photo_action_config |
| `backup_external_image_api_size` | 备选在线生图尺寸 | photo_action_config |
| `backup_external_image_api_timeout_seconds` | 备选在线生图超时时间（秒） | photo_action_config |
| `comfyui_photo_wait_seconds` | 主动拍照等待生图秒数 | photo_action_config |
| `custom_photo_tool_extra_params` | 生图工具的额外参数（JSON） | photo_action_config |
| `custom_photo_tool_kind_param` | 生图工具的类型参数名 | photo_action_config |
| `custom_photo_tool_name` | 自定义生图函数工具名 | photo_action_config |
| `custom_photo_tool_prompt_param` | 生图工具的提示词参数名 | photo_action_config |
| `custom_photo_tool_reference_param` | 生图工具的参考图参数名 | photo_action_config |
| `enable_backup_external_image_api` | 启用备选在线图片 API | photo_action_config |
| `enable_natural_language_photo_generation` | 允许规则快判生图/改图 | photo_action_config |
| `enable_p5_structured_reference_assets` | Q5 受管结构化参考素材（多图） | photo_action_config |
| `enable_photo_reference_image` | 人设/穿搭参考图一致性 | photo_action_config |
| `enable_photo_text_action` | 允许主动拍照/生图 | photo_action_config |
| `enable_user_requested_photo_generation` | 允许用户请求生图 | photo_action_config |
| `external_image_api_custom_headers` | 在线生图自定义请求头 | photo_action_config |
| `external_image_api_endpoints` | 在线生图 API 优先级队列 | photo_action_config |
| `external_image_api_platform` | 在线生图模型平台 | photo_action_config |
| `external_image_api_size` | 在线生图尺寸 | photo_action_config |
| `external_image_api_timeout_seconds` | 在线生图超时时间（秒） | photo_action_config |
| `natural_language_photo_extra_prompt` | 规则快判生图附加提示词 | photo_action_config |
| `natural_language_photo_generation_max_daily` | 规则快判生图/改图每日上限 | photo_action_config |
| `natural_language_photo_generation_mode` | 非指令生图处理方式 | photo_action_config |
| `photo_action_max_daily` | 每日主动生图最多次数 | photo_action_config |
| `photo_generation_backend` | 主动生图后端 | photo_action_config |
| `photo_generation_edit_fixed_prompt` | 改图固定附加提示词 | photo_action_config |
| `photo_generation_edit_negative_prompt` | 改图负面提示词 | photo_action_config |
| `photo_generation_fixed_prompt` | 全局固定附加提示词（兼容） | photo_action_config |
| `photo_generation_negative_prompt` | 全局自定义负面提示词 | photo_action_config |
| `photo_generation_negative_prompt_mode` | 负面提示词策略 | photo_action_config |
| `photo_generation_prompt_format` | 生图提示词表达方式 | photo_action_config |
| `photo_generation_scene_presets` | 生图场景预设 | photo_action_config |
| `photo_generation_selfie_fixed_prompt` | 自拍/人像固定附加提示词 | photo_action_config |
| `photo_generation_selfie_negative_prompt` | 自拍/人像负面提示词 | photo_action_config |
| `photo_generation_style` | 主动生图风格 | photo_action_config |
| `photo_generation_style_custom_prompt` | 主动生图自定义风格说明 | photo_action_config |
| `photo_generation_text2img_fixed_prompt` | 文生图固定附加提示词 | photo_action_config |
| `photo_generation_text2img_negative_prompt` | 文生图负面提示词 | photo_action_config |
| `photo_persona_reference_image_path` | 人设参考图路径或图片 URL | photo_action_config |
| `photo_reference_catalog` | 规范参考图目录 | photo_action_config |
| `photo_reference_catalog_user_cleared` | 用户主动清空规范参考图目录 | photo_action_config |
| `photo_reference_catalog_version` | 规范参考图目录版本 | photo_action_config |
| `photo_reference_library` | 带注释的参考图库 | photo_action_config |
| `photo_structured_reference_assets` | Q5 受管素材清单 | photo_action_config |
| `proactive_photo_text_probability` | 主动带图触发概率 | photo_action_config |

#### C2 产出·创作与作品 — 18 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `creative_chars_per_session` | 每次创作字数 | daily_creative_config |
| `creative_direction_prompt` | 创作方向提示词 | daily_creative_config |
| `creative_hidden_mode` | 创作默认低调进行 | daily_creative_config |
| `creative_inspiration_probability` | 创作灵感触发概率 | daily_creative_config |
| `creative_max_active_projects` | 最多同时创作项目数 | daily_creative_config |
| `creative_share_probability` | 小说节点透露概率 | daily_creative_config |
| `enable_creative_work_read_guard` | 启用创作原文读取保护 | daily_creative_config |
| `enable_creative_writing` | 启用私下创作行为 | daily_creative_config |
| `enable_creative_cover_generation` | 为创作内容生成封面 | photo_action_config |
| `enable_reading_archive_page_comments` | 资料页边批注 | reading_archive_config |
| `daily_diary_creativity` | 日记写实程度 | schedule_detail_config |
| `daily_diary_custom_direction` | 日记创作方向 | schedule_detail_config |
| `daily_diary_form` | 日记写作形式 | schedule_detail_config |
| `daily_diary_generate_share_seed` | 从日记提取自然分享素材 | schedule_detail_config |
| `daily_diary_length` | 日记篇幅 | schedule_detail_config |
| `daily_diary_time` | 每日写日记时间 | schedule_detail_config |
| `enable_daily_diary` | 启用每日 Bot 日记 | schedule_detail_config |
| `max_diary_entries` | 保留 Bot 日记数量 | schedule_detail_config |

#### C3 产出·生活行为 — 8 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `daily_outfit_photo_prompt` | 每日穿搭额外提示词 | photo_action_config |
| `daily_outfit_rotation_days` | 穿搭轮换冷却天数 | photo_action_config |
| `enable_daily_outfit_photo` | 每日穿搭照片 | photo_action_config |
| `enable_wardrobe` | 启用角色衣柜 | wardrobe_config |
| `enable_wardrobe_prompt` | 把衣柜写入角色提示词 | wardrobe_config |
| `wardrobe_items` | 具体衣物条目（由命令或面板维护） | wardrobe_config |
| `wardrobe_prompt_max_items` | 注入提示词的衣物条数上限 | wardrobe_config |
| `wardrobe_tendency` | 整体服饰倾向 | wardrobe_config |

#### C4 产出·社交发布 — 10 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `enable_qzone_emotional_vent_publish` | 公开心情动态 | experimental_motivation_config |
| `qzone_emotional_vent_cooldown_hours` | 心情动态冷却小时 | experimental_motivation_config |
| `qzone_emotional_vent_probability` | 心情动态触发概率 | experimental_motivation_config |
| `qzone_emotional_vent_threshold` | 心情动态触发阈值 | experimental_motivation_config |
| `enable_qzone_generated_image_publish` | 主动说说可带生成图 | qzone_config |
| `enable_qzone_integration` | 启用 QQ 空间动态层（本体兼容） | qzone_config |
| `enable_qzone_life_publish` | 低频发布生活说说 | qzone_config |
| `qzone_generated_image_probability` | 主动说说带图概率 | qzone_config |
| `qzone_publish_image_style_prompt` | 空间配图提示词 | qzone_config |
| `qzone_publish_style_prompt` | 说说风格提示词 | qzone_config |

### D 段（投递）

#### D1 投递·文本形态与注入 — 70 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `task_prompt_overrides` | 插件内部任务模型自定义提示词 | __flat_only__ |
| `default_nickname` | 默认称呼 | basic_config |
| `default_nickname_strategy` | 默认称呼来源 | basic_config |
| `default_style` | 默认语气 | basic_config |
| `enable_persona_voice_channels` | 启用分通道人格风格 | basic_config |
| `persona_conversation_voice_prompt` | 对话风格 | basic_config |
| `persona_creative_voice_prompt` | 创作风格 | basic_config |
| `persona_inner_voice_prompt` | 内心活动风格 | basic_config |
| `persona_planning_voice_prompt` | 计划风格 | basic_config |
| `persona_proactive_voice_prompt` | 主动开口风格 | basic_config |
| `reply_style_prompt` | 回复风格提示词 | basic_config |
| `enable_group_context_injection` | 群聊回复前注入观察上下文 | group_observation_config |
| `enable_passive_state_continuity_anchor` | 私聊被动状态连续性锚点 | humanized_state_config |
| `enable_passive_state_delta_injection` | 被动状态增量注入 | humanized_state_config |
| `inject_passive_states` | 被动回复前注入拟人状态 | humanized_state_config |
| `passive_injection_position` | 动态提示词注入位置 | humanized_state_config |
| `enable_llm_controlled_segmenting` | LLM 自主分段 | legacy_compat_config |
| `enable_qq_official_segmented_reply` | 允许 qq_official 使用分段 | legacy_compat_config |
| `enable_segmented_plugin_rules` | 插件规则分段 | legacy_compat_config |
| `enable_segmented_proactive_chat_profiles` | 私聊和群聊独立配置 | legacy_compat_config |
| `enable_segmented_proactive_content_cleanup` | 主动分段内容清理 | legacy_compat_config |
| `enable_segmented_proactive_content_replacement` | 主动分段内容替换 | legacy_compat_config |
| `enable_segmented_proactive_reply` | 分段发送 | legacy_compat_config |
| `llm_controlled_segmenting_prompt` | 自主分段提示词 | legacy_compat_config |
| `segmented_proactive_at_strategy` | @ 组件位置 | legacy_compat_config |
| `segmented_proactive_chat_scope` | 分段会话范围 | legacy_compat_config |
| `segmented_proactive_component_order` | 组件先后顺序 | legacy_compat_config |
| `segmented_proactive_content_cleanup_rule` | 主动分段内容清理正则 | legacy_compat_config |
| `segmented_proactive_content_cleanup_scope` | 主动分段内容清理范围 | legacy_compat_config |
| `segmented_proactive_content_cleanup_words` | 主动分段内容清理词列表 | legacy_compat_config |
| `segmented_proactive_content_replacements` | 主动分段内容替换规则 | legacy_compat_config |
| `segmented_proactive_face_strategy` | 平台表情位置 | legacy_compat_config |
| `segmented_proactive_group_enabled` | 群聊启用分段 | legacy_compat_config |
| `segmented_proactive_group_interval_max` | 群聊最大间隔秒数 | legacy_compat_config |
| `segmented_proactive_group_interval_method` | 群聊分段间隔方式 | legacy_compat_config |
| `segmented_proactive_group_interval_min` | 群聊最小间隔秒数 | legacy_compat_config |
| `segmented_proactive_group_log_base` | 群聊对数间隔底数 | legacy_compat_config |
| `segmented_proactive_group_max_segments` | 群聊最多分段数 | legacy_compat_config |
| `segmented_proactive_group_min_segment_chars` | 群聊短片段合并阈值 | legacy_compat_config |
| `segmented_proactive_group_scope` | 群聊分段作用范围 | legacy_compat_config |
| `segmented_proactive_group_send_as_forward` | 群聊分段后合并发送 | legacy_compat_config |
| `segmented_proactive_group_threshold` | 群聊不分段字数阈值 | legacy_compat_config |
| `segmented_proactive_image_strategy` | 图片组件位置 | legacy_compat_config |
| `segmented_proactive_interval_max` | 主动分段最大间隔秒数 | legacy_compat_config |
| `segmented_proactive_interval_method` | 主动分段间隔算法 | legacy_compat_config |
| `segmented_proactive_interval_min` | 主动分段最小间隔秒数 | legacy_compat_config |
| `segmented_proactive_log_base` | 主动分段对数底数 | legacy_compat_config |
| `segmented_proactive_match_width_variants` | 自动匹配全角/半角标点 | legacy_compat_config |
| `segmented_proactive_max_segments` | 主动文本最多分段数 | legacy_compat_config |
| `segmented_proactive_min_segment_chars` | 主动短片段合并阈值 | legacy_compat_config |
| `segmented_proactive_other_strategy` | 其他附件位置 | legacy_compat_config |
| `segmented_proactive_private_enabled` | 私聊启用分段 | legacy_compat_config |
| `segmented_proactive_private_interval_max` | 私聊最大间隔秒数 | legacy_compat_config |
| `segmented_proactive_private_interval_method` | 私聊分段间隔方式 | legacy_compat_config |
| `segmented_proactive_private_interval_min` | 私聊最小间隔秒数 | legacy_compat_config |
| `segmented_proactive_private_log_base` | 私聊对数间隔底数 | legacy_compat_config |
| `segmented_proactive_private_max_segments` | 私聊最多分段数 | legacy_compat_config |
| `segmented_proactive_private_min_segment_chars` | 私聊短片段合并阈值 | legacy_compat_config |
| `segmented_proactive_private_scope` | 私聊分段作用范围 | legacy_compat_config |
| `segmented_proactive_private_send_as_forward` | 私聊分段后合并发送 | legacy_compat_config |
| `segmented_proactive_private_threshold` | 私聊不分段字数阈值 | legacy_compat_config |
| `segmented_proactive_regex` | 主动分段正则表达式 | legacy_compat_config |
| `segmented_proactive_scope` | 分段作用范围 | legacy_compat_config |
| `segmented_proactive_send_as_forward` | 分段后以合并消息发送 | legacy_compat_config |
| `segmented_proactive_split_mode` | 主动分段模式 | legacy_compat_config |
| `segmented_proactive_split_words` | 主动分段词列表 | legacy_compat_config |
| `segmented_proactive_threshold` | 主动文本不分段字数阈值 | legacy_compat_config |
| `segmented_proactive_voice_strategy` | 语音组件位置 | legacy_compat_config |
| `enable_llm_streaming` | 插件内部 LLM 调用使用流式 | model_assignment_config |
| `enable_mai_style_integration` | 启用互动与表达基座 | private_understanding_config |

#### D2 投递·语音 — 44 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `auto_voice_cooldown_seconds` | 自动语音冷却秒数 | auto_voice_config |
| `auto_voice_enabled` | 自动语音转换 | auto_voice_config |
| `auto_voice_full_conversion_enabled` | 自动语音完整转换 | auto_voice_config |
| `auto_voice_max_chars` | 自动语音最大字数 | auto_voice_config |
| `auto_voice_probability` | 自动语音触发概率(旧) | auto_voice_config |
| `main_user_mention_voice_keywords` | @主用户语音关键词 | auto_voice_config |
| `main_user_mention_voice_probability` | @主用户关键词触发概率(%) | auto_voice_config |
| `main_user_mention_voice_prompt` | @主用户关键词提示词 | auto_voice_config |
| `main_user_voice_probability` | 主用户触发概率(%) | auto_voice_config |
| `voice_action_max_chars` | 主动语音最大字数 | auto_voice_config |
| `enable_tts_enhancement` | TTS强化 | voice_action_config |
| `enable_voice_action` | 允许主动发语音 | voice_action_config |
| `tts_constraint_mode` | TTS约束强度 | voice_action_config |
| `tts_conversion_provider_id` | TTS文本转换模型Provider ID | voice_action_config |
| `tts_conversion_scope` | TTS转换范围 | voice_action_config |
| `tts_delivery_mode` | TTS发送形态 | voice_action_config |
| `tts_extra_prompt` | TTS补充规则 | voice_action_config |
| `tts_fishaudio_emotion_mode` | Fish Audio 情绪控制 | voice_action_config |
| `tts_fishaudio_model` | Fish Audio 模型适配 | voice_action_config |
| `tts_foreign_text_mode` | 外语语音文字显示 | voice_action_config |
| `tts_frequency_control_mode` | TTS频率控制模式 | voice_action_config |
| `tts_generation_mode` | TTS生成路径 | voice_action_config |
| `tts_group_min_interval_seconds` | 群聊TTS最小间隔秒数 | voice_action_config |
| `tts_group_trigger_probability` | 群聊TTS触发概率(%) | voice_action_config |
| `tts_message_scope` | TTS消息生效范围 | voice_action_config |
| `tts_mimo_style_prompt` | MiMo Voice Clone 临时风格 | voice_action_config |
| `tts_mimo_tool_name` | MiMo Voice Clone 工具名 | voice_action_config |
| `tts_mimo_voice_name` | MiMo Voice Clone 音色 | voice_action_config |
| `tts_private_min_interval_seconds` | 私聊TTS最小间隔秒数 | voice_action_config |
| `tts_private_trigger_probability` | 私聊TTS触发概率(%) | voice_action_config |
| `tts_provider_id_en` | 英语TTS Provider ID | voice_action_config |
| `tts_provider_id_ja` | 日语TTS Provider ID | voice_action_config |
| `tts_provider_id_zh` | 中文TTS Provider ID | voice_action_config |
| `tts_session_min_interval_seconds` | TTS会话最小间隔秒数 | voice_action_config |
| `tts_synthesis_backend` | TTS语音合成后端 | voice_action_config |
| `tts_trigger_keywords` | 关键词触发TTS | voice_action_config |
| `tts_trigger_probability` | TTS全局触发概率(%) | voice_action_config |
| `tts_voice_language` | TTS语音语种 | voice_action_config |
| `enable_tts_live_subtitle_sync` | 同步到直播打字机字幕 | voice_playback_config |
| `enable_tts_local_playback` | TTS生成后本机播放 | voice_playback_config |
| `enable_tts_local_playback_live_only` | 直播时仅播放直播回应消息 | voice_playback_config |
| `tts_live_subtitle_url` | 直播字幕推送地址 | voice_playback_config |
| `tts_local_playback_min_interval_seconds` | 本机播放最小间隔秒数 | voice_playback_config |
| `tts_local_playback_volume` | 本机播放音量 | voice_playback_config |

#### D3 投递·表情与配图 — 22 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `reaction_expression_candidate_limit` | 表情检索说法上限 | experimental_motivation_config |
| `reaction_expression_cooldown_seconds` | 表情表达冷却秒数 | experimental_motivation_config |
| `reaction_expression_delivery_mode` | 表情表达发送方式 | experimental_motivation_config |
| `reaction_expression_embedding_backfill_batch_size` | 表情补向量批量 | experimental_motivation_config |
| `reaction_expression_embedding_backfill_enabled` | 后台补齐表情向量 | experimental_motivation_config |
| `reaction_expression_embedding_backfill_interval_seconds` | 表情补向量最短间隔 | experimental_motivation_config |
| `reaction_expression_embedding_candidate_limit` | 表情向量扫描上限 | experimental_motivation_config |
| `reaction_expression_embedding_enabled` | 启用表情语义召回 | experimental_motivation_config |
| `reaction_expression_embedding_score_threshold` | 表情语义相似度阈值 | experimental_motivation_config |
| `reaction_expression_embedding_timeout_ms` | 表情嵌入超时毫秒 | experimental_motivation_config |
| `reaction_expression_embedding_weight` | 表情语义加权分 | experimental_motivation_config |
| `reaction_expression_group_enabled` | 允许群聊表情表达 | experimental_motivation_config |
| `reaction_expression_image_format` | 表情包图片格式 | experimental_motivation_config |
| `reaction_expression_low_latency_mode` | 低延迟选择模式 | experimental_motivation_config |
| `reaction_expression_private_enabled` | 允许私聊表情表达 | experimental_motivation_config |
| `reaction_expression_proactive_enabled` | 允许主动消息表情表达 | experimental_motivation_config |
| `reaction_expression_semantic_trigger_enabled` | 允许语义节点触发表情表达 | experimental_motivation_config |
| `reaction_expression_trigger_probability` | 表情表达触发概率 | experimental_motivation_config |
| `reaction_expression_vision_verify_mode` | 发送前视觉复核表情包 | experimental_motivation_config |
| `allow_generate_photo_on_reaction_turns` | 表情表达授权轮保留生图工具 | photo_action_config |
| `enable_owned_reaction_asset_workbench` | Q6 自有反应图素材工作台 | photo_action_config |
| `owned_reaction_assets` | Q6 自有反应图素材清单 | photo_action_config |

#### D4 投递·平台动作 — 31 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `enable_poke_action` | 允许主动戳一戳 | poke_action_config |
| `poke_action_cooldown_minutes` | 主动戳一戳冷却分钟数 | poke_action_config |
| `poke_action_max_times` | 每次主动戳一戳最多次数 | poke_action_config |
| `enable_qq_custom_presence_sync` | 同步 QQ 自定义短状态 | presence_sync_config |
| `enable_qq_presence_sync` | 同步 QQ 在线状态 | presence_sync_config |
| `reactive_poke_back_probability` | 反戳概率 | reactive_poke_config |
| `reactive_poke_back_prompts` | 反戳提示词列表 | reactive_poke_config |
| `reactive_poke_back_times` | 普通反戳次数 | reactive_poke_config |
| `reactive_poke_interval` | 反戳动作间隔秒数 | reactive_poke_config |
| `reactive_poke_super_poke_probability` | 超级反戳概率 | reactive_poke_config |
| `reactive_poke_super_poke_times` | 超级反戳次数 | reactive_poke_config |
| `enable_forbidden_word_recall` | 违禁词自动撤回 | recall_config |
| `enable_recall_transcribe_command` | 允许命令转述撤回消息 | recall_config |
| `recall_forbidden_scope` | 违禁词撤回范围 | recall_config |
| `recall_forbidden_word_case_sensitive` | 违禁词大小写敏感 | recall_config |
| `recall_forbidden_words` | 撤回违禁词表 | recall_config |
| `atrelay_default_relay_style` | 默认转述方式 | relay_bridge_config |
| `atrelay_member_cache_minutes` | 群成员列表缓存分钟 | relay_bridge_config |
| `atrelay_multi_target_limit` | 多目标转述单次上限 | relay_bridge_config |
| `atrelay_require_worldbook_first` | 优先使用关系网解析 @ 对象 | relay_bridge_config |
| `atrelay_sensitive_confirm` | 敏感转述发送前确认 | relay_bridge_config |
| `cross_user_memory_owner_only` | 仅主要用户可查询跨用户互动 | relay_bridge_config |
| `enable_atrelay_llm_rewrite` | 使用模型转述正文 | relay_bridge_config |
| `enable_atrelay_tools` | 启用跨群转述与 @ 群友工具 | relay_bridge_config |
| `enable_cross_user_memory_bridge` | 启用跨用户记忆互通 | relay_bridge_config |
| `enable_quote_group_interjection` | 引用群主动插话触发消息 | timer_config |
| `enable_quote_group_reply` | 引用普通群回复触发消息 | timer_config |
| `enable_quote_private_proactive` | 引用私聊主动触发消息 | timer_config |
| `quote_group_reply_once_per_target` | 连续同对象只首条引用 | timer_config |
| `quote_skip_short_reply_chars` | 短回复不引用阈值 | timer_config |
| `quote_target_strategy` | 引用目标策略 | timer_config |

#### D5 投递·时机与编排 — 13 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `busy_reply_max_delay_seconds` | 繁忙回复最长延迟（秒） | humanized_state_config |
| `busy_reply_min_delay_seconds` | 繁忙回复最短延迟（秒） | humanized_state_config |
| `busy_reply_proactive_resume_buffer_minutes` | 忙完后主动缓冲（分钟） | humanized_state_config |
| `enable_busy_reply_gate` | 启用繁忙回复闸门 | humanized_state_config |
| `enable_rest_backlog_reply` | 醒后补看私聊 | humanized_state_config |
| `rest_backlog_max_messages` | 醒后最多补看条数 | humanized_state_config |
| `enable_reply_interception_forward` | 启用回复拦截转发 | proactive_reach_config |
| `reply_interception_forward_plugin_blocks` | 转发插件阻断消息 | proactive_reach_config |
| `reply_interception_forward_proactive_blocks` | 转发主动消息拦截 | proactive_reach_config |
| `reply_interception_forward_rewrites` | 转发回复改写 | proactive_reach_config |
| `reply_interception_forward_target_umo` | 拦截转发目标会话 | proactive_reach_config |
| `enable_precise_platform_send` | 主动消息优先使用精确平台发送 | timer_config |
| `enable_proactive_decorating_hooks` | 主动消息走装饰钩子 | timer_config |

### E 段（治理）

#### E1 治理·身份与权限 — 18 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `bot_name` | Bot 名字 / 页面展示名 | basic_config |
| `bot_scope_ids` | Bot 作用域 ID 列表 | basic_config |
| `bot_scope_mode` | Bot 作用域模式 | basic_config |
| `enable_multi_persona_mode` | 开启多人格支持模式 | basic_config |
| `multi_persona_ids` | 多人格 ID 列表 | basic_config |
| `plugin_specific_persona_id` | 插件主人格 ID | basic_config |
| `private_user_aliases` | 私聊身份别名归并 | basic_config |
| `private_user_delivery_aliases` | 私聊主动发送目标映射 | basic_config |
| `target_platform` | 未见过用户的兜底平台 | basic_config |
| `target_user_ids` | 私聊目标用户 ID | basic_config |
| `group_access_mode` | 群聊启用模式 | group_observation_config |
| `group_blacklist_ids` | 群聊陪伴黑名单群 ID | group_observation_config |
| `group_whitelist_ids` | 群聊陪伴白名单群 ID | group_observation_config |
| `grants` | 核心／重要用户授权（JSON） | operation_access |
| `group_operations` | 重要／普通用户可在群内使用的操作 | operation_access |
| `public_operations` | 普通用户可用操作 | operation_access |
| `photo_generation_allowed_scopes` | 旧版生图使用范围 | photo_action_config |
| `QZONE_COOKIE` | QQ 空间手动 Cookie | qzone_config |

#### E2 治理·模型分配 — 44 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `model_fallback_overrides` | Legacy flat config: 模型卡片备用 Provider | __flat_only__ |
| `model_timeout_overrides` | Legacy flat config: 模型任务超时覆盖 | __flat_only__ |
| `model_token_limit_overrides` | Legacy flat config: 模型卡片单次 Token 上限 | __flat_only__ |
| `REACTION_EXPRESSION_EMBEDDING_PROVIDER_ID` | 表情嵌入模型覆盖 | experimental_motivation_config |
| `REST_WAKEUP_PROVIDER_ID` | 休息醒来判断模型ID | humanized_state_config |
| `COMPANION_MEMORY_PROVIDER_ID` | 本地陪伴画像整理模型（留空跟随陪伴通用模型） | model_assignment_config |
| `COMPLEX_REASONING_PROVIDER_ID` | 复杂推理模型 | model_assignment_config |
| `CREATIVE_MODEL_PROVIDER_ID` | 创作模型 | model_assignment_config |
| `CREATIVE_OUTLINE_PROVIDER_ID` | 创作大纲模型（留空跟随私下创作模型） | model_assignment_config |
| `CREATIVE_PROVIDER_ID` | 私下创作模型（留空跟随陪伴通用模型） | model_assignment_config |
| `CREATIVE_REVIEW_PROVIDER_ID` | 创作审校/分析模型（留空跟随私下创作模型） | model_assignment_config |
| `DAILY_PLAN_PROVIDER_ID` | 日程生成模型（留空跟随陪伴通用模型） | model_assignment_config |
| `DAILY_REVIEW_PROVIDER_ID` | 每日终盘巡视模型（留空优先使用复杂推理模型） | model_assignment_config |
| `DEEPSEEK_PEAK_REPLACEMENT_PROVIDER_ID` | DeepSeek 高价时段替代模型 | model_assignment_config |
| `DETAIL_ENHANCEMENT_PROVIDER_ID` | 细节强化模型（留空跟随主模型） | model_assignment_config |
| `DIALOGUE_EPISODE_PROVIDER_ID` | 私聊片段记忆整理模型（留空跟随陪伴通用模型） | model_assignment_config |
| `DREAM_DIARY_PROVIDER_ID` | 日记与梦境模型（留空跟随陪伴通用模型） | model_assignment_config |
| `EMBEDDING_PROVIDER_ID` | 通用语义嵌入模型 | model_assignment_config |
| `EMOTION_JUDGEMENT_PROVIDER_ID` | 情绪变化判断模型（留空自动回退） | model_assignment_config |
| `FAST_RESPONSE_PROVIDER_ID` | 快速响应模型 | model_assignment_config |
| `FORWARD_MESSAGE_PROVIDER_ID` | 合并消息转述模型 | model_assignment_config |
| `GROUP_EPISODE_PROVIDER_ID` | 群聊片段记忆整理模型（留空跟随陪伴通用模型） | model_assignment_config |
| `GROUP_FOLLOWUP_JUDGE_PROVIDER_ID` | 群聊续接判断模型 | model_assignment_config |
| `GROUP_INTERJECT_PROVIDER_ID` | 群聊主动插话模型（留空跟随陪伴通用模型） | model_assignment_config |
| `GROUP_MEMBER_SAFETY_PROVIDER_ID` | 群成员风控判定模型 | model_assignment_config |
| `GROUP_SLANG_PROVIDER_ID` | 群内黑话释义模型（留空跟随陪伴通用模型） | model_assignment_config |
| `HISTORY_SUMMARY_PROVIDER_ID` | 昨日对话摘要模型（留空跟随日程模型） | model_assignment_config |
| `MAI_STYLE_PROVIDER_ID` | 互动与表达基座通用模型（留空跟随主模型） | model_assignment_config |
| `NARRATION_PROVIDER_ID` | 工具结果转述模型（留空则不单独转述） | model_assignment_config |
| `PHOTO_PROMPT_PROVIDER_ID` | 主动生图提示词模型（留空跟随主模型） | model_assignment_config |
| `PLUGIN_VISION_PROVIDER_ID` | 插件识图模型（私聊/群聊/合并消息/识屏） | model_assignment_config |
| `READING_ARCHIVE_VISION_PROVIDER_ID` | 资料归档视觉模型 | model_assignment_config |
| `RELATIONSHIP_ANALYSIS_PROVIDER_ID` | 关系站位分析模型（留空跟随陪伴通用模型） | model_assignment_config |
| `RESPONSE_REVIEW_PROVIDER_ID` | 回复/主动复核模型（留空用默认） | model_assignment_config |
| `SENSITIVE_REPLACEMENT_PROVIDER_ID` | 敏感拒答替换模型 | model_assignment_config |
| `SMART_SILENCE_PROVIDER_ID` | 智能沉默判定模型（留空跟随回复复核） | model_assignment_config |
| `TROUBLESHOOTING_PROVIDER_ID` | 插件答疑/排障模型（留空优先使用复杂推理模型） | model_assignment_config |
| `VOICE_PROMPT_PROVIDER_ID` | 主动语音文案文本模型（留空跟随陪伴通用模型） | model_assignment_config |
| `model_replacement_rules` | 关键词模型替换规则 | model_assignment_config |
| `model_replacement_scope` | 模型替换策略作用范围 | model_assignment_config |
| `provider_config_mode` | 模型配置模式 | model_assignment_config |
| `NEWS_PROVIDER_ID` | 新闻整理模型（留空跟随主动转述/主模型） | news_config |
| `WARDROBE_VISION_PROVIDER_ID` | 衣柜识图模型 | wardrobe_config |
| `WEB_EXPLORATION_PROVIDER_ID` | 主动搜索决策/整理模型（留空跟随新闻整理/主模型） | web_exploration_config |

#### E3 治理·内容风控 — 51 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `enable_flirt_content_tier` | 允许含蓄暧昧档 | basic_config |
| `enable_group_third_party_portrait_guard` | 群聊第三方画像保护 | basic_config |
| `enable_outbound_secret_redaction` | 发送前敏感凭据脱敏 | basic_config |
| `enable_relationship_content_tiers` | 关系内容尺度 | basic_config |
| `enable_store_control_tag_sanitization` | 保存时清理非标准控制标签 | basic_config |
| `outbound_secret_redaction_trusted_domains` | 出站脱敏受信域名 | basic_config |
| `bilibili_share_min_score` | 视频分享最低评分 | bilibili_config |
| `enable_framework_error_leak_guard` | 拦截框架异常文本外发 | emotion_relationship_config |
| `enable_passive_response_review` | 启用被动回复复核 | emotion_relationship_config |
| `enable_passive_topic_suppression` | 启用普通回复重复话题抑制 | emotion_relationship_config |
| `enable_proactive_message_review` | 主动私聊发送前终审 | emotion_relationship_config |
| `enable_response_self_review` | 旧版回复/主动复核总开关 | emotion_relationship_config |
| `enable_smart_silence` | 启用智能沉默 | emotion_relationship_config |
| `passive_review_mode` | 被动回复复核模式 | emotion_relationship_config |
| `passive_review_strength` | 被动回复复核强度 | emotion_relationship_config |
| `passive_topic_memory_hours` | 普通回复话题记忆时长（小时） | emotion_relationship_config |
| `proactive_review_hard_risk_threshold` | 硬拦截风险阈值 | emotion_relationship_config |
| `proactive_review_history_limit` | 主动终审召回消息数 | emotion_relationship_config |
| `proactive_review_low_score_threshold` | 低价值分数阈值 | emotion_relationship_config |
| `proactive_review_mode` | 主动消息终审模式 | emotion_relationship_config |
| `proactive_review_pressure_threshold` | 打扰压力阈值 | emotion_relationship_config |
| `proactive_review_strength` | 主动复核强度 | emotion_relationship_config |
| `response_review_max_chars` | 被动回复长度阈值 | emotion_relationship_config |
| `response_review_mode` | 旧版回复复核模式 | emotion_relationship_config |
| `smart_silence_judge_mode` | 智能沉默判断模式 | emotion_relationship_config |
| `smart_silence_min_confidence` | 智能沉默最低置信度 | emotion_relationship_config |
| `smart_silence_model_timeout_seconds` | 智能沉默超时秒数 | emotion_relationship_config |
| `enable_group_injection_guard` | 群聊防注入 | group_observation_config |
| `enable_group_member_safety` | 启用群成员风控 | group_observation_config |
| `group_member_safety_audit_limit` | 每位成员保留审计记录数 | group_observation_config |
| `group_member_safety_block_hours` | 自动静默时长（小时） | group_observation_config |
| `group_member_safety_exempt_managers` | 自动豁免管理者和主要用户 | group_observation_config |
| `group_member_safety_hidden_marker_mode` | 回复模型隐性风控标签 | group_observation_config |
| `group_member_safety_min_confidence` | 风险记录最低置信度 | group_observation_config |
| `group_member_safety_review_mode` | 成员风控审核范围 | group_observation_config |
| `group_member_safety_strike_threshold` | 自动静默所需风险次数 | group_observation_config |
| `group_member_safety_strike_window_days` | 风险次数统计窗口（天） | group_observation_config |
| `intercept_astrbot_group_context` | 拦截AstrBot群聊对话注入 | group_observation_config |
| `enable_group_privacy_guard` | 启用群聊隐私防串味边界 | group_relationship_config |
| `enable_group_reality_promise_guard` | 阻止群聊现实承诺 | group_scene_config |
| `enable_sensitive_model_replacement` | 启用敏感拒答模型替换 | model_assignment_config |
| `sensitive_replacement_keywords` | 敏感拒答匹配词 | model_assignment_config |
| `enable_group_nsfw_private_fallback` | 群聊成图安全审核与私聊回退 | photo_action_config |
| `group_nsfw_image_review_custom_prompt` | 审核补充规则 | photo_action_config |
| `group_nsfw_image_review_failure_action` | 审核失败处理 | photo_action_config |
| `group_nsfw_image_review_max_dimension` | 审核图片最长边像素 | photo_action_config |
| `group_nsfw_image_review_min_confidence` | 群聊成图审核最低置信度 | photo_action_config |
| `group_nsfw_image_review_mode` | 群聊成图审核模式 | photo_action_config |
| `group_nsfw_image_review_sensitivity` | 群聊成图审核严格度 | photo_action_config |
| `group_nsfw_image_review_timeout_seconds` | 群聊成图安全审核超时秒数 | photo_action_config |
| `reading_archive_blocked_tags` | 资料归档过滤标签 | reading_archive_config |

#### E4 治理·资源与预算 — 37 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `balance_api_auth_header` | 鉴权请求头名称 | balance_awareness_config |
| `balance_api_auth_scheme` | 鉴权前缀 | balance_awareness_config |
| `balance_api_custom_headers` | 余额接口自定义请求头 | balance_awareness_config |
| `balance_api_key` | 余额接口 API Key | balance_awareness_config |
| `balance_api_url` | 余额接口地址（可选覆盖） | balance_awareness_config |
| `balance_check_interval_minutes` | 余额检查间隔（分钟） | balance_awareness_config |
| `balance_critical_percent_threshold` | 危急余额比例（%） | balance_awareness_config |
| `balance_critical_threshold` | 危急余额阈值 | balance_awareness_config |
| `balance_currency_label` | 余额单位 | balance_awareness_config |
| `balance_include_amount_in_message` | 允许人格参考具体余额 | balance_awareness_config |
| `balance_json_path` | 余额 JSON 路径 | balance_awareness_config |
| `balance_low_percent_threshold` | 低余额比例（%） | balance_awareness_config |
| `balance_low_threshold` | 低余额阈值 | balance_awareness_config |
| `balance_request_timeout_seconds` | 余额接口超时（秒） | balance_awareness_config |
| `balance_total_json_path` | 总额度 JSON 路径 | balance_awareness_config |
| `balance_used_json_path` | 已用额度 JSON 路径 | balance_awareness_config |
| `balance_value_divisor` | 余额数值除数 | balance_awareness_config |
| `enable_balance_awareness` | 启用余额感知 | balance_awareness_config |
| `daily_token_limit` | 每日插件 Token 限额 | basic_config |
| `daily_token_soft_limit` | 每日 Token 软限额 | basic_config |
| `enable_daily_token_soft_limit` | 启用每日 Token 软限额 | basic_config |
| `deepseek_peak_match_keywords` | DeepSeek Provider 匹配关键词 | model_assignment_config |
| `deepseek_peak_timezone` | DeepSeek 高价时段时区 | model_assignment_config |
| `deepseek_peak_windows` | DeepSeek 高价时段 | model_assignment_config |
| `enable_deepseek_peak_replacement` | 启用 DeepSeek 高价时段替换 | model_assignment_config |
| `command_photo_generation_max_daily` | 用户请求生图/改图每日上限 | photo_action_config |
| `enable_generated_photo_cleanup` | 自动清理生图归档 | photo_action_config |
| `enable_local_photo_load_guard` | 电脑高负荷时延后本地生图 | photo_action_config |
| `generated_photo_max_mb` | 生图归档磁盘上限 MB | photo_action_config |
| `generated_photo_retention_days` | 生图归档保留天数 | photo_action_config |
| `local_photo_cpu_busy_percent` | 本地生图 CPU 忙碌阈值 | photo_action_config |
| `local_photo_defer_minutes` | 本地生图忙时延后分钟数 | photo_action_config |
| `local_photo_memory_busy_percent` | 本地生图内存忙碌阈值 | photo_action_config |
| `photo_generation_group_max_daily` | 群聊生图每日上限 | photo_action_config |
| `photo_generation_private_friend_max_daily` | 其他陪伴用户私聊生图每日上限 | photo_action_config |
| `photo_generation_private_owner_max_daily` | 主要用户私聊生图每日上限 | photo_action_config |
| `photo_generation_proactive_max_daily` | Bot 主动生图每日上限 | photo_action_config |

#### E5 治理·存储与部署 — 19 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `page_font_family` | Legacy flat config: 拓展页面字体 | __flat_only__ |
| `page_theme` | Legacy flat config: 拓展页面主题 | __flat_only__ |
| `enable_standalone_webui` | 启用独立陪伴 WebUI | basic_config |
| `standalone_webui_access_token` | 独立 WebUI 访问令牌 | basic_config |
| `standalone_webui_host` | 独立 WebUI 监听地址 | basic_config |
| `standalone_webui_port` | 独立 WebUI 端口 | basic_config |
| `standalone_webui_session_ttl_hours` | 独立 WebUI 会话有效期（小时） | basic_config |
| `storage_backend` | 主数据保存方式 | basic_config |
| `storage_sqlite_path` | SQLite 数据文件路径 | basic_config |
| `enable_new_framework_dev_e2e` | 启用新框架开发端到端接线 | external_memory_config |
| `new_framework_dev_e2e_inject_memory_context` | 注入新框架记忆参考 | external_memory_config |
| `new_framework_dev_e2e_max_memory_items` | 新框架记忆摘要条数 | external_memory_config |
| `new_framework_dev_e2e_policy_revision` | 新框架开发授权策略版本 | external_memory_config |
| `new_framework_dev_e2e_timeout_seconds` | 新框架开发链路超时（秒） | external_memory_config |
| `new_framework_dev_e2e_user_ids` | 新框架开发测试用户 ID | external_memory_config |
| `external_image_download_proxy` | 在线图片网络代理 | photo_action_config |
| `external_image_download_use_environment_proxy` | 在线图片网络继承环境代理 | photo_action_config |
| `photo_generation_trace_backup_count` | 生图日志轮转备份数 | photo_action_config |
| `photo_generation_trace_max_size_kb` | 生图日志单文件大小（KB） | photo_action_config |

#### E6 治理·遗留与兼容 — 30 条

| 配置项 | 说明 | V1 所属组 |
|---|---|---|
| `_command_photo_quota_semantics_version` | 内部迁移标记：用户请求生图额度语义版本 | __flat_only__ |
| `_photo_generation_scope_quota_semantics_version` | 内部迁移标记：生图范围额度语义版本 | __flat_only__ |
| `enable_body_monitor_integration` | Legacy flat config: 联动 Body Monitor | __flat_only__ |
| `enable_p4_b_legacy_score_isolation` | 隔离旧版关系分数写入 | basic_config |
| `enable_p5_b1_bridge_gate` | 启用 P5-B1 Bridge 闸门 | external_memory_config |
| `enable_p5_b1_recall_gate` | 启用 P5-B1 召回闸门 | external_memory_config |
| `enable_p5_source_observer` | 启用 P5 来源观察 | external_memory_config |
| `COMFYUI_PHOTO_WORKFLOW_NAME` | 主动拍照工作流名（兼容旧配置） | legacy_compat_config |
| `DIARY_PROVIDER_ID` | 旧版日记模型 | legacy_compat_config |
| `DREAM_PROVIDER_ID` | 旧版梦境模型 | legacy_compat_config |
| `allow_photo_text_action` | 旧版主动发图开关 | legacy_compat_config |
| `allow_poke_action` | 旧版戳一戳开关 | legacy_compat_config |
| `allow_screen_peek_action` | 旧版主动识屏开关 | legacy_compat_config |
| `allow_voice_action` | 旧版主动语音开关 | legacy_compat_config |
| `creative_base_chars_per_hour` | 旧版创作字数 | legacy_compat_config |
| `enable_hot_trend_sources` | 旧版热榜开关 | legacy_compat_config |
| `enable_maintenance_token_saver` | 旧版 Token 节省开关 | legacy_compat_config |
| `enabled_proactive_actions` | 旧版主动能力列表 | legacy_compat_config |
| `hot_trend_max_items` | 旧版热榜条数 | legacy_compat_config |
| `hot_trend_sources` | 旧版热榜来源 | legacy_compat_config |
| `maintenance_token_soft_limit` | 旧版 Token 软限额 | legacy_compat_config |
| `require_target_group` | 只观察配置的目标群（旧开关） | legacy_compat_config |
| `target_group_ids` | 群聊陪伴目标群 ID（旧配置，等同白名单） | legacy_compat_config |
| `timezone` | 旧版时区 | legacy_compat_config |
| `hdsi_experiment_binding_revision` | HDSI 绑定修订号 | reactive_poke_config |
| `hdsi_experiment_continuity_scope` | HDSI 持续生活共享范围 | reactive_poke_config |
| `hdsi_experiment_group_ids` | HDSI 试验群 ID | reactive_poke_config |
| `hdsi_experiment_mode` | HDSI 试验模式 | reactive_poke_config |
| `hdsi_experiment_user_ids` | HDSI 试验私聊用户 ID | reactive_poke_config |
| `hdsi_experiment_window_modes` | HDSI 窗口选择 | reactive_poke_config |

## 四、跨段与难分类项

以下组内的配置项**不属于同一段**，按组归类会失真。逐条判定后的落位见第三节，此处说明错位点：

| V1 组 | 横跨段 | 说明 |
|---|---|---|
| `basic_config`（94 条） | A1 + B2 + B3 + B4 + D1 + E1 + E3 + E4 + E5 + E6 | 最混杂的一组：环境感知、关系阶段、人格风格、主动配额、身份目标、脱敏、预算、存储都在里面。 |
| `experimental_motivation_config`（89 条） | A3 + B2 + B4 + C4 + D3 | 组名叫实验性动机，实际混入表情投递、摄像头感知、需求驱力、QQ 空间发布四类。 |
| `photo_action_config`（88 条） | C1 + C3 + E3 + E4 + B2 | 主为图像生成，混入穿搭产出、成图审核、配额清理与关系网角色卡。 |
| `legacy_compat_config`（69 条） | D1 + E6 | 分段发送是投递形态，其余几乎全是旧版残留字段。 |
| `humanized_state_config`（53 条） | B3 + D1 + D5 + E2 | 拟人状态属内核，状态注入属投递形态，繁忙/补看属投递时机。 |
| `model_assignment_config`（43 条） | E2 + A3 + E4 + E3 + D1 | 模型分配为主，但识图模型同时服务感知，高价时段替换是成本治理。 |
| `external_memory_config`（31 条） | B1 + C1 + B4 + E5 + E6 | 记忆协同为主，混入 S4 相册生图、后台调度与开发端到端接线。 |
| `message_debounce_config`（29 条） | A2 + A3 | 组名叫消息收口，但过半条目是识图转述增强，实质属媒体理解。 |
| `group_observation_config`（27 条） | A2 + A3 + B1 + E1 + E3 | 群观察组同时含名单权限、成员风控、图片理解与社会理解。 |
| `weather_config`（23 条） | A1 + A3 + B4 | 天气与历法是环境源，屏幕日记是媒体理解，突变主动是决策。 |
| `qzone_config`（19 条） | C4 + A2 + B4 + E1 | 说说发布是产出，评论收件箱是入站源，发布节奏是决策，Cookie 是凭据。 |
| `balance_awareness_config`（19 条） | E4 + B4 | 余额查询与阈值是资源治理，主动提醒与冷却是主动决策。 |
| `reactive_poke_config`（17 条） | A2 + D4 | 被戳是入站事件，反戳是出站平台动作；同一组配置横跨两端，且两端在 V2 的落地进度完全不同步。 |
| `schedule_detail_config`（17 条） | B3 + C2 + E3 | 日记生成是产出，巡视复盘横跨自我反思与质检。 |
| `relay_bridge_config`（16 条） | D4 + B1 + E3 | 跨群转述是出站动作，群片段与关系边是记忆，敏感确认是风控。 |
| `recall_config`（12 条） | A2 + D4 + E3 | 撤回通知入站、违禁词主动撤回出站、缓存与审计属治理。 |
| `timer_config`（10 条） | B4 + D4 + D5 | 主动调度是决策，引用是投递动作，精确发送与装饰钩子是编排。 |
| `__flat_only__`（10 条） | E2 + E5 + E6 + A1 + D1 | 未归入任何组的顶层遗留项，语义各不相同。 |
| `wardrobe_config`（8 条） | C3 + A3 + E2 | 衣柜条目是角色资产产出，识图建条目是感知，识图模型是模型分配。 |

### 单条层面的典型跨段项

| 配置项 | 落位 | 为什么难分 |
|---|---|---|
| `reactive_poke_back_probability` | D4 | 被戳配置组里的反戳动作，是出站而非入站 |
| `reactive_poke_trigger_probability` | A2 | 同组的被戳响应概率，是入站事件处理 |
| `enable_forbidden_word_recall` | D4 | 与撤回增强同组，但它是主动撤回己方消息，属出站 |
| `enable_recall_enhancement` | A2 | 同组的入站通知处理 |
| `private_image_vision_custom_prompt` | A3 | 位于消息收口组，实为识图转述增强 |
| `reaction_expression_delivery_mode` | D3 | 位于实验性动机组，实为表情投递形态 |
| `reality_touch_camera_index` | A3 | 位于实验性动机组，实为摄像头感知 |
| `qzone_comment_inbox_interval_minutes` | A2 | 位于 QQ 空间组，是入站评论扫描而非发布 |
| `wardrobe_image_prompt` | A3 | 位于衣柜组，是识图建条目而非衣柜资产 |
| `PLUGIN_VISION_PROVIDER_ID` | E2 | 服务识图感知，但本质是模型分配 |
| `persona_conversation_voice_prompt` | D1 | 人格风格与回复风格同为表达形态，与 B3 角色自我相邻 |
| `inject_passive_states` | D1 | 把 B3 自身状态注入到回复，桥接内核与投递 |
| `busy_reply_min_delay_seconds` | D5 | 由自身忙状态驱动，但配置的是发送时机 |
| `enable_daily_review` | B3 | 自我复盘，同时具备质检属性，与 E3 相邻 |
| `enable_environment_change_proactive` | B4 | 由环境源触发，但配置的是主动决策 |
| `new_framework_s4_album` | B4 / C1 | 后台记忆接续里的相册拍照，跨记忆与图像生成 |
| `bilibili_share_min_score` | E3 | 分享阈值看似决策，实为内容质量门禁 |
| `photo_generation_allowed_scopes` | E1 | 生图范围实为授权范围 |
| `reading_archive_blocked_tags` | E3 | 资料标签过滤属内容风控 |
| `include_schedule_in_messages` | B4 | 日程属自我，但"是否带进主动消息"是决策 |

## 五、几点观察

1. **投递段被严重低估**：V1 里 `segmented_*` 分段相关配置散落在 `legacy_compat_config`，约 60 条，名义上是"遗留兼容"，实际是当前仍在使用的输出形态控制。
2. **产出的大头是图像**：`photo_action_config` 88 条几乎独占产出段，其余创作/社交/生活加起来不足 40 条。
3. **治理段条目密集**：模型分配 43 条 + 各类风控/预算/权限，治理类配置接近总盘的三分之一，V1 的功能复杂度大量沉淀在这里。
4. **环境接入段配置薄**：天气 23 条、新闻 25 条、搜索 13 条，加起来不足 70 条——但这是 V2 缺口最大的一段，说明缺的不是配置而是接入代码。
