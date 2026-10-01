/* 配置工作台的薄适配层。
   本文件此前自带整套字段渲染、草稿存储与幂等重试；这些现在归
   workbench-page.js 统一负责。这里只保留「分区 → 标题/说明/字段顺序/文案」
   的声明，以及各分区的错误映射。

   保留 create(kinds, rootProvider) 签名，app.js 的 mountConfigEditor 无需改动。 */
"use strict";
window.CompanionConfigEditors = (() => {
  const PREFIX = "/astrbot_plugin_private_companion_v2/";

  /* 主动联系偏好（proactive.contact）是唯一一个四层组：安装 → 角色 → 关系 → 窗口。
     158 个字段平铺成一张卡没法用，所以按「一条链一段」拆成 22 段：
     总闸 → 节奏与额度 → 强度与连发 → 关系级配额 → 免打扰 → 重复抑制 → 开口判定，
     然后是三类契机，最后是各契机自己的触发源（问候、三餐、纪念日、天气、资讯、
     网络探索、自关联、余额、屏幕、语音与戳戳、约定、生成上下文）。
     段落 help 说的是「关掉哪一项时下面哪些项不再起作用」，不是功能简介。

     15 类契机的 45 个字段（开关 / 权重 / 暂缓）由下面这张表生成：45 个字段名
     手写一遍，漏一个不会有任何报错——内核把没声明的字段悄悄附到最后一段，
     缺标签只会让界面露出英文短名。 */
  const CONTACT_PURPOSES = [
    ["bond", "affection", "想念与亲近"], ["bond", "care", "情绪关怀"],
    ["bond", "play", "轻松互动"], ["bond", "repair", "关系修复"], ["bond", "chat", "日常话题"],
    ["daily", "greeting", "问候与纪念"], ["daily", "followup", "接回旧话题"],
    ["daily", "invitation", "共同活动邀请"], ["daily", "reminder", "约定与提醒"],
    ["daily", "meal", "饭点问候"],
    ["share", "life", "分享自己的生活"], ["share", "creation", "作品与阅读"],
    ["share", "news", "外部资讯"], ["share", "environment", "环境与状态变化"],
    ["share", "screen", "已授权屏幕观察"],
  ];
  /* 一段里的顺序是「一个契机的三个控件挨在一起」，不是按控件类型分组：
     调「饭点问候」的人不该在三个段落之间来回找。 */
  const purposeFields = bucket => CONTACT_PURPOSES.filter(([group]) => group === bucket)
    .flatMap(([, name]) => [name + ".enabled", name + ".weight", name + ".pause_until"]);
  const purposeLabels = (suffix, text) => Object.fromEntries(CONTACT_PURPOSES
    .map(([, name, label]) => [name + "." + suffix, label + " · " + text]));
  const CONTACT_PAUSE_FIELDS = ["pause_until",
    ...CONTACT_PURPOSES.map(([, name]) => name + ".pause_until")];
  const CONTACT_SECTIONS = [
    {id: "master", title: "总开关与补充偏好",
     help: "总闸关闭时下面各类契机都不会开口；补充偏好只是写进提示词的材料，不改变权限、频率或去重。",
     fields: ["enabled", "automatic_enabled", "note"]},
    {id: "rhythm", title: "开口节奏与每日额度",
     help: "先看间隔与安静门槛，再看每日额度；连续未回应会同时放宽间隔，达到阈值后停止常规联系。",
     fields: ["interval_seconds", "idle_seconds", "event_max_age_seconds", "max_contacts_24h",
              "max_attempts_24h", "unanswered_slowdown_start", "unanswered_pause_after",
              "unanswered_max_interval_multiplier"]},
    {id: "intensity", title: "强度档位与连发",
     help: "档位只缩放间隔与安静门槛、给一个长度提示，不放宽任何额度、权限或投递规则；连发只接着一条普通话题继续。",
     fields: ["proactive_intensity_preset", "proactive_intensity_body_chars", "enable_proactive_burst",
              "proactive_burst_max_messages", "proactive_burst_gap_min_seconds",
              "proactive_burst_gap_max_seconds", "proactive_hour_activity_enabled",
              "proactive_hour_activity_curve", "proactive_closing_grace_minutes",
              "proactive_closing_contacts_threshold", "proactive_share_probability"]},
    {id: "relationship_budget", title: "关系级每日配额",
     help: "这两项的保存层级是安装 / 角色 / 关系，不是这一次会话：它们限制同一对象与角色的整段关系，"
           + "所有会话加在一起。在窗口层保存会被拒绝，所以层轨上这两项没有窗口节点。",
     fields: ["max_relationship_contacts_24h", "max_relationship_attempts_24h"]},
    {id: "quiet", title: "免打扰与临时暂停",
     help: "免打扰与暂停只决定「现在不开口」，不改动已登记的日程；暂停按层继承——本层清空后，"
           + "祖先层更晚的到期时间仍然生效。",
     fields: ["quiet_enabled", "quiet_start", "quiet_end", "quiet_timezone", "pause_until"]},
    {id: "dedup", title: "重复与抑制",
     help: "关闭总闸后不再做任何内容去重；三条窗口分别管「刚说过的话」「已经发过的同类内容」与天气预警。",
     fields: ["dedup_enabled", "dedup_last_message_enabled", "dedup_last_message_window_minutes",
              "dedup_sent_window_minutes", "dedup_weather_window_minutes", "dedup_min_shared_tokens",
              "dedup_min_overlap_ratio", "dedup_policies"]},
    {id: "judgement", title: "开口判定与人格复核",
     help: "两道判定都在草稿写好之后：先看置信度门槛，再由模型复核是否符合人格；任何一道不通过都只丢弃这条草稿，不产生消息。",
     fields: ["silence_min_confidence", "silence_feedback_penalty",
              "enable_llm_proactive_persona_judge", "proactive_persona_judge_threshold",
              "proactive_persona_judge_cache_minutes", "proactive_persona_judge_daily_limit",
              "proactive_persona_judge_exempt_purposes"]},
    {id: "bond", title: "契机：情感与陪伴",
     help: "每一类都可以单独关闭、调权重、临时暂缓；权重只在多个合适话题之间做选择，不改变频率、额度或权限。",
     fields: purposeFields("bond")},
    {id: "daily", title: "契机：日常与约定",
     help: "问候、接回旧话题、共同活动、约定与饭点：这些契机依赖日程与已登记的约定，权重同样只在候选之间做选择。",
     fields: purposeFields("daily")},
    {id: "share", title: "契机：分享与外部",
     help: "分享自己的生活与作品、外部资讯、环境变化与屏幕观察：外部来源还要各自打开下面触发源里的总闸，这里只决定这一类契机是否参与。",
     fields: purposeFields("share")},
    {id: "greeting", title: "问候与失眠夜",
     help: "三个问候窗口按免打扰时区解释，必须在当天内结束；深夜开口另有总闸与每日次数，默认关闭。",
     fields: ["enable_daily_greetings", "greeting_morning_window", "greeting_noon_window",
              "greeting_evening_window", "greeting_idle_minutes", "allow_insomnia_night_message",
              "insomnia_night_start", "insomnia_night_end", "insomnia_night_daily_limit",
              "insomnia_require_sleep_state"]},
    {id: "meal", title: "三餐问候",
     help: "关闭总闸后两个饭点都不再问候；跟进时长决定饭点之后多久内还可以接着关心一句。",
     fields: ["meal_checkin_enabled", "meal_lunch_time", "meal_dinner_time",
              "meal_care_followup_minutes"]},
    {id: "date", title: "纪念日",
     help: "清单里的日期按公历或农历登记；提前天数让角色提前几天开始留意，0 表示只在当天问候。",
     fields: ["date_checkin_enabled", "date_checkin_time", "important_dates",
              "important_date_lookahead_days"]},
    {id: "weather", title: "天气与预警",
     help: "定时问候与突变联系是两条独立链路；官方预警只转发不低于所选级别的消息，数据源凭据由宿主环境变量提供。",
     fields: ["weather_checkin_enabled", "weather_checkin_time", "weather_change_enabled",
              "weather_sample_minutes", "official_weather_alert_enabled",
              "official_alert_poll_minutes", "official_alert_min_severity"]},
    {id: "news", title: "外部资讯源",
     help: "三个来源总闸与来源类型配合：搜索走网络探索、热榜走每日热榜、其余走分享新闻；"
           + "类型与 UID / 地址必须匹配，否则保存会被拒绝。",
     fields: ["news_share_enabled", "news_source_kind", "news_source_uid", "news_source_url",
              "news_check_interval_minutes", "news_daily_hot_read_enabled", "news_hot_sources",
              "news_hot_result_count"]},
    {id: "web", title: "网络探索",
     help: "探索按兴趣词搜索，结果只作为资讯契机；最短间隔与每次条数限制的是读取量，不是发送量。",
     fields: ["web_exploration_enabled", "web_exploration_interests",
              "web_exploration_min_interval_hours", "web_exploration_result_count"]},
    {id: "selflink", title: "外部事件与自身经历关联",
     help: "允许角色把外部事件与自己的经历联系起来说；权重影响它与其他候选的竞争，冷却时间避免同一件事被反复关联。",
     fields: ["external_event_self_link_enabled", "external_event_self_link_weight",
              "external_event_self_link_cooldown_hours"]},
    {id: "balance", title: "余额感知",
     help: "这里说的是 Bot 所用服务的经费状态，不是对方的账户余额；阈值同时按绝对值和百分比判断，两者取更保守的一条。",
     fields: ["balance_awareness_enabled", "balance_include_amount_in_message",
              "balance_currency_label", "balance_low_threshold", "balance_critical_threshold",
              "balance_low_percent_threshold", "balance_critical_percent_threshold",
              "balance_check_interval_minutes", "balance_message_cooldown_hours"]},
    {id: "screen", title: "屏幕观察",
     help: "屏幕观察是原生设备调用，可能被设备侧拒绝；观察、晚安后看一眼、未回应补看三条链路各有自己的开关与间隔。",
     fields: ["screen_glance_enabled", "screen_glance_daily_limit", "screen_glance_cooldown_minutes",
              "screen_glance_goodnight_enabled", "screen_glance_goodnight_delay_minutes",
              "screen_glance_followup_enabled", "screen_glance_followup_after_minutes",
              "screen_glance_followup_cooldown_minutes"]},
    {id: "action", title: "语音与戳一戳",
     help: "语音与戳一戳是两种平台动作，都需要对应能力可用；这里限制的是「主动做」的次数，不影响回复里的表达。",
     fields: ["voice_action_enabled", "voice_action_max_chars", "voice_action_cooldown_minutes",
              "poke_action_enabled", "poke_action_daily_limit", "poke_action_cooldown_minutes"]},
    {id: "appointment", title: "约定执行时机",
     help: "约定来自日程里对方已接受、尚未开始的条目；提前量决定何时开口，滞后量决定迟到多久仍可补说，静默期避免约定前被打扰。",
     fields: ["appointment_lead_minutes", "appointment_lag_minutes",
              "appointment_pre_silence_minutes"]},
    {id: "context", title: "生成上下文",
     help: "只影响起草时能看到多少历史与多长的材料，以及说话风格的补充；不改动权限、频率或投递规则。",
     fields: ["generation_history_limit", "history_max_chars", "style_prompt"]},
  ];
  /* 注册表只给 kind 与数值范围：HH:MM、HH:MM-HH:MM、IANA 时区、暂停时间点、
     24 小时曲线与三个逗号清单的形状都要由页面兜住，否则值会走到后端才被拒
     （后端拒绝时只回一个 invalid_contact_preference）。 */
  const CONTACT_CLOCKS = ["quiet_start", "quiet_end", "meal_lunch_time", "meal_dinner_time",
    "weather_checkin_time", "date_checkin_time", "insomnia_night_start", "insomnia_night_end"];
  const CONTACT_WINDOWS = ["greeting_morning_window", "greeting_noon_window", "greeting_evening_window"];
  const CONTACT_DEDUP_ROUTES = ["semantic", "content_fingerprint", "life_event", "event_revision",
    "event_anchor", "conversation_anchor", "daily_slot"];
  const CONTACT_HOT_SOURCES = ["weibo", "hackernews"];
  const CONTACT_SOURCE_KINDS = ["host", "disabled", "bilibili", "rss", "json", "search", "hot"];
  const CONTACT_INSTANT = /(Z|[+-]\d{2}:\d{2})$/;
  const contactWords = (value, pattern) => String(value).toLowerCase()
    .split(pattern).map(part => part.trim()).filter(Boolean);

  /* QQ 空间的七个主题。字段名、标签与场景目录都要与后端
     companion_v2/qzone/topics.py 的 TOPIC_SPECS 逐字对应：
     字段名错一个，注册表里那一项就没有控件（审计会报，页面会静默少一项）；
     场景目录错一个，保存时会被后端整组拒掉，却只说一句「设置不合法」。 */
  const QZONE_TOPIC_SECTIONS = [
    {prefix: "life_documentary", title: "生活纪实类", scenes: ["conversation", "role_activity", "date_marker"]},
    {prefix: "emotion_reflection", title: "情绪感悟类", scenes: ["conversation", "relationship", "free_expression"]},
    {prefix: "interest_hobby", title: "兴趣爱好类", scenes: ["conversation", "external_material", "role_activity"]},
    {prefix: "opinion_hot", title: "观点/热点类", scenes: ["external_material", "conversation"]},
    {prefix: "help_interaction", title: "求助/互动类",
     scenes: ["conversation", "agenda", "external_material", "relationship"]},
    {prefix: "ritual_memory", title: "仪式纪念类", scenes: ["date_marker", "relationship", "conversation"]},
    {prefix: "meaningless_status", title: "无意义水动态",
     scenes: ["free_expression", "conversation", "role_activity"]},
  ];
  /* 场景 id 的中文名，供 help 里写「可选值」用；与后端 topics.py 的 SCENES 一致。 */
  const QZONE_SCENES = {conversation: "对话", external_material: "外部资讯或材料", agenda: "日程与待办",
    role_activity: "角色活动与记录", relationship: "关系与互动", date_marker: "日期与纪念节点",
    free_expression: "自由表达"};
  const qzoneSceneWords = names => names.map(name => `${name}（${QZONE_SCENES[name]}）`).join("、");

  const QZONE_SECTIONS = [
    {id: "switches", title: "状态与动作",
     help: "关闭总闸时下面所有项都不起作用：不再发任何空间请求，也不再为它花模型额度。",
     fields: ["enabled", "like_enabled", "comment_enabled", "publish_enabled",
              "feed_recent_posts", "comment_recent_posts"]},
    {id: "throttle", title: "发布节流",
     help: "总闸与「允许发说说」都打开后才生效。这几项限制的是频率与条数，不放宽任何一项能力开关。",
     fields: ["action_min_interval_minutes", "max_actions_per_tick", "publish_max_daily"]},
    {id: "topics", title: "主题判定",
     help: "一条说说在写出正文之前必须先定主题与场景：这里决定谁来定、要不要人工确认，以及给模型的补充指引。",
     fields: ["topic_auto_enabled", "topic_require_confirmation", "topic_prompt_guidance"]},
    ...QZONE_TOPIC_SECTIONS.map(topic => ({
      id: topic.prefix,
      title: topic.title,
      help: `${topic.title}的发布条件：允许的场景只有 ${qzoneSceneWords(topic.scenes)}；关掉启用后这个主题一条都不发，其他主题不受影响。`,
      fields: [`${topic.prefix}_enabled`, `${topic.prefix}_scenes`, `${topic.prefix}_min_confidence`,
               `${topic.prefix}_daily_max`, `${topic.prefix}_cooldown_minutes`],
    })),
  ];
  /* 每个主题的 helps 里那串「可选值」是各主题自己的那一份，所以逐主题拼；
     共用一句示例会把「只能用该主题自己的场景」说成另一个主题的场景。 */
  function qzoneAudit(values) {
    for (const topic of QZONE_TOPIC_SECTIONS) {
      const name = `${topic.prefix}_scenes`;
      const value = values[name];
      /* 未改动的字段可能不在草稿里；那种情况下不判，免得把「没动过」当成错。 */
      if (typeof value !== "string") continue;
      const scenes = value.split(",").map(part => part.trim());
      if (scenes.some(scene => !topic.scenes.includes(scene))
          || new Set(scenes).size !== scenes.length) return "qzone_scene_list_invalid";
    }
    return null;
  }  function updateRoleProfileSummary(status) {
    const settings = status?.settings || {};
    const buttons = [...document.querySelectorAll("[data-profile-field]")];
    let filled = 0;
    let total = 0;
    for (const button of buttons) {
      let fields = [];
      try { fields = JSON.parse(button.dataset.profileFields || "[]"); } catch {}
      if (!fields.length) fields = [button.dataset.profileField];
      const trackedFields = fields.filter(name => name !== "world_adaptation_mode"
        || settings[name] !== "auto");
      const count = trackedFields.filter(name => typeof settings[name] === "string" && settings[name].trim().length > 0).length;
      const saved = count > 0;
      filled += count;
      total += trackedFields.length;
      button.dataset.complete = String(saved);
      button.setAttribute("aria-label", `${button.dataset.profileLabel}${saved ? `，已有 ${count} 项资料` : "，尚无资料"}，打开对应设定`);
    }
    const count = document.querySelector("[data-profile-count]");
    const progress = document.querySelector("[data-profile-progress]");
    const fill = document.querySelector("[data-profile-fill]");
    const label = document.querySelector("[data-profile-status]");
    if (count) count.textContent = `${filled} / ${total}`;
    if (progress) {
      progress.setAttribute("aria-valuemax", String(total));
      progress.setAttribute("aria-valuenow", String(filled));
    }
    if (fill) fill.style.width = `${total ? filled / total * 100 : 0}%`;
    if (label) label.textContent = `已有资料项 · ${buttons.length} 个设定分区`;

    const name = String(settings.name || "").trim();
    const title = document.querySelector("[data-profile-name]");
    if (title) title.textContent = name || title.dataset.profileFallback || "当前角色";
    const emblem = document.querySelector("[data-profile-emblem]");
    if (emblem) emblem.textContent = Array.from(name)[0] || emblem.dataset.profileFallback || "设";
    const first = (...keys) => keys.map(key => String(settings[key] || "").trim()).find(Boolean) || "待补充";
    const identity = document.querySelector('[data-profile-signal="identity"]');
    const appearance = document.querySelector('[data-profile-signal="appearance"]');
    const personality = document.querySelector('[data-profile-signal="personality"]');
    const world = document.querySelector('[data-profile-signal="world"]');
    const voice = document.querySelector('[data-profile-signal="voice"]');
    if (identity) identity.textContent = first("occupation", "species", "identity");
    if (appearance) appearance.textContent = first("appearance_points", "hair", "appearance");
    if (personality) personality.textContent = first("personality", "reaction_patterns", "speech_style");
    if (world) world.textContent = first("world_name", "tone", "world");
    if (voice) voice.textContent = first("speech_style", "first_person", "reaction_patterns");
  }

  /* 每个分区：标题、说明、字段顺序、字段标签与帮助。
     取值范围刻意不在页面声明——它由后端下发的 FieldDefinition 契约决定，
     避免页面写死一份会与校验器漂移的副本。 */
  const spec = {
    quota: {
      title: "生图每日额度",
      note: "按安装与角色生效，-1 表示不限，0 表示禁止；本地日按会话时区归零。",
      labels: {
        private_owner_max_daily: "本人私聊每日张数",
        private_friend_max_daily: "他人私聊每日张数",
        group_max_daily: "群聊每日张数",
        proactive_max_daily: "主动消息每日张数",
      },
      helps: {},
      order: ["private_owner_max_daily", "private_friend_max_daily",
              "group_max_daily", "proactive_max_daily"],
    },
    image_review: {
      title: "群图成图审核",
      note: "只作用于群受众的成图；审核不通过时可丢弃或改走私聊投递。",
      labels: {
        enable_group_nsfw_private_fallback: "审核不通过时降级私聊投递",
        group_nsfw_image_review_mode: "审核方式",
        group_nsfw_image_review_sensitivity: "判定尺度",
        group_nsfw_image_review_min_confidence: "判定置信度下限",
        group_nsfw_image_review_timeout_seconds: "单次审核超时（秒）",
        group_nsfw_image_review_max_dimension: "送审图片最长边像素",
        group_nsfw_image_review_max_images: "单次送审图片张数",
        group_nsfw_image_review_failure_action: "审核失败时",
        group_nsfw_image_review_custom_prompt: "审核提示词补充",
        review_provider: "审核模型扩展",
        review_dual_provider: "第二审核模型",
      },
      helps: {
        enable_group_nsfw_private_fallback: "该成员本身是已授权的私聊对象时才会改发私聊；否则保持阻止。",
        group_nsfw_image_review_mode: "选择具体的审核模型扩展后才会真正调用。",
        group_nsfw_image_review_max_dimension: "0 表示按原尺寸送审。",
        group_nsfw_image_review_failure_action: "审核失败与判定不通过是两件事，这里只决定失败时的动作。",
        group_nsfw_image_review_custom_prompt: "留空使用内置提示词；只补充判定尺度，不能放宽既有边界。",
      },
      /* 这些字段在注册表里是 TEXT，取值约束在 review_settings 的校验器里；
         选项必须与后端常量保持一致，否则保存会被拒绝。 */
      choices: {
        group_nsfw_image_review_mode: {single: "单模型", dual: "双模型复核"},
        group_nsfw_image_review_sensitivity: {lenient: "宽松", balanced: "标准", strict: "严格"},
        group_nsfw_image_review_failure_action: {private: "改走私聊投递", withhold: "暂不投递", block: "整条阻止"},
        review_provider: {"": "跟随任务路由"},
        review_dual_provider: {"": "不使用"},
      },
      order: ["enable_group_nsfw_private_fallback", "group_nsfw_image_review_mode",
              "group_nsfw_image_review_sensitivity", "group_nsfw_image_review_min_confidence",
              "group_nsfw_image_review_timeout_seconds", "group_nsfw_image_review_max_dimension",
              "group_nsfw_image_review_max_images", "group_nsfw_image_review_failure_action",
              "group_nsfw_image_review_custom_prompt", "review_provider", "review_dual_provider"],
    },
    reaction: {
      title: "表情检索",
      note: "决定表情素材怎么被检索与复用；视觉复核仍需扩展可用。",
      labels: {
        low_latency_enabled: "低延迟模式",
        embedding_backfill_enabled: "后台补齐向量",
        candidate_limit: "每轮候选素材数",
        embedding_candidate_limit: "向量检索候选上限",
        embedding_backfill_batch_size: "补齐批次大小",
        embedding_backfill_interval_seconds: "补齐间隔（秒）",
        embedding_weight: "向量权重",
        embedding_score_threshold: "向量相似度门槛",
        vision_verify_mode: "视觉复核",
      },
      helps: {
        low_latency_enabled: "开启后跳过较慢的复核路径，优先按时发出。",
        embedding_backfill_interval_seconds: "0 表示不按间隔补齐。",
        embedding_weight: "与词法分的相对权重；越大越偏语义相近。",
      },
      choices: {vision_verify_mode: {off: "不复核", embedding: "仅向量命中时复核", always: "每次复核"}},
      order: ["low_latency_enabled", "embedding_backfill_enabled", "candidate_limit",
              "embedding_candidate_limit", "embedding_backfill_batch_size",
              "embedding_backfill_interval_seconds", "embedding_weight",
              "embedding_score_threshold", "vision_verify_mode"],
    },
    busy_gate: {
      title: "忙碌时的回复与联系",
      note: "识别到角色正忙时，私聊回复会短暂顺延，普通主动联系会暂停到忙碌结束并经过缓冲；紧急关键词不等待。",
      labels: {
        busy_reply_gate_enabled: "启用忙碌处理",
        busy_reply_min_delay_seconds: "私聊回复最短顺延（秒）",
        busy_reply_max_delay_seconds: "私聊回复最长顺延（秒）",
        busy_reply_proactive_resume_buffer_minutes: "主动联系恢复缓冲（分钟）",
        busy_activity_keywords: "忙碌活动关键词",
        busy_exclude_keywords: "排除忙碌关键词",
        busy_urgent_keywords: "紧急关键词",
      },
      helps: {
        busy_reply_gate_enabled: "关闭后不再根据角色日程延后私聊回复，也不暂停普通主动联系。",
        busy_activity_keywords: "命中后判为忙碌。用逗号、空格或换行分隔，也可以用 JSON 数组；单条不超过 24 个字，最多 64 条。",
        busy_exclude_keywords: "命中后取消忙碌判定，优先级高于忙碌关键词。",
        busy_urgent_keywords: "命中后立即回复，即使在忙碌窗口内。",
        busy_reply_min_delay_seconds: "识别到忙碌时，本轮私聊回复至少顺延多久。",
        busy_reply_max_delay_seconds: "识别到忙碌时，本轮私聊回复最多顺延多久。",
        busy_reply_proactive_resume_buffer_minutes: "忙碌结束后的这段时间里不发起普通主动消息，避免刚忙完就被打断。",
      },
      order: ["busy_reply_gate_enabled", "busy_reply_min_delay_seconds",
              "busy_reply_max_delay_seconds", "busy_reply_proactive_resume_buffer_minutes",
              "busy_activity_keywords", "busy_exclude_keywords", "busy_urgent_keywords"],
    },
    budget: {
      title: "每日 Token 软限额",
      note: "只决定可选的后台工作是否开始；交互回复不受它影响。按安装与角色生效。",
      labels: {
        enable_daily_token_soft_limit: "启用每日软限额",
        daily_token_soft_limit: "每日软限额（token）",
      },
      helps: {daily_token_soft_limit: "达到后当天不再开始新的可选后台任务，已开始的会走完。"},
      order: ["enable_daily_token_soft_limit", "daily_token_soft_limit"],
    },
    recall: {
      title: "撤回原文转写",
      note: "只读取本窗口内已撤回的入站消息，用于理解上下文；不会把它们当成新的聊天内容。",
      labels: {
        transcribe_enabled: "允许读取撤回原文",
        transcribe_max_items: "单次最多读取条数",
        transcribe_text_chars: "单条原文最长字数",
        transcribe_window_minutes: "回溯时间窗（分钟）",
      },
      helps: {
        transcribe_enabled: "关闭时撤回消息只记为「已撤回」，不保留原文。",
        transcribe_window_minutes: "只回溯这段时间内撤回的消息；超出窗口的不会被读取。",
      },
      order: ["transcribe_enabled", "transcribe_max_items", "transcribe_text_chars",
              "transcribe_window_minutes"],
    },
    screen: {
      title: "屏幕解读与日记素材",
      note: "决定截到的画面能否被解读、以及能否作为日记素材；两项都默认关闭。",
      labels: {
        interpretation_enabled: "解读屏幕画面",
        journal_material_enabled: "允许作为日记素材",
        journal_material_max_chars: "单条素材最长字数",
      },
      helps: {
        interpretation_enabled: "关闭时截图仍会保存，但不做模型解读。",
        journal_material_enabled: "仍受日记本身的授权约束；关闭时不会绕过日记权限。",
      },
      order: ["interpretation_enabled", "journal_material_enabled", "journal_material_max_chars"],
    },
    person: {
      title: "熟人卡",
      note: "为已经认识的对象维护一张简要卡片，帮助角色记住相处背景。",
      labels: {
        acquaintance_enabled: "启用熟人卡",
        acquaintance_card_chars: "卡片最长字数",
      },
      helps: {acquaintance_card_chars: "卡片过长会挤占上下文，建议只留关键内容。"},
      order: ["acquaintance_enabled", "acquaintance_card_chars"],
    },
    private_access: {
      title: "私聊用户权限",
      note: "每个私聊用户的对话与主动权限是按人设置的，在「关系与权限」里逐人开关；这里只定「没人决定过的新用户从哪开始」，以及没有对话权限时回哪一句。",
      labels: {
        dialogue_default: "新用户默认可对话",
        proactive_default: "新用户默认可被主动联系",
        denied_reply: "没有对话权限时回的话",
        notice_cooldown_seconds: "同一人多久内只回一次",
        stranger_notice_enabled: "也婉拒陌生号",
        stranger_notice_daily_cap: "陌生号每天最多回几条",
      },
      helps: {
        dialogue_default: "关闭后，新出现的私聊用户不会得到回复，只会收到下面那句话。",
        proactive_default: "默认关闭：角色不会主动找刚认识的人说话，直到你在关系页为他打开。",
        denied_reply: "留空表示完全安静（不回话）。只有设置向导的本地草稿轮不会真的发出。",
        notice_cooldown_seconds: "默认 6 小时。填 0 表示对方每发一条就回一次。",
        stranger_notice_enabled: "陌生号指没有绑定、也不在任何目标里的账号：默认只回这一句，不建立任何身份、不写记忆。",
        stranger_notice_daily_cap: "每天总量上限，防止被反复打扰；填 0 表示一个陌生号都不回。",
      },
      choices: {},
      order: ["dialogue_default", "proactive_default", "denied_reply",
        "notice_cooldown_seconds", "stranger_notice_enabled", "stranger_notice_daily_cap"],
      sections: [
        {id: "defaults", title: "新用户默认权限",
         fields: ["dialogue_default", "proactive_default"]},
        {id: "denied", title: "无权限回复",
         fields: ["denied_reply", "notice_cooldown_seconds"]},
        {id: "strangers", title: "陌生号处理",
         fields: ["stranger_notice_enabled", "stranger_notice_daily_cap"]},
      ],
    },
    role_growth: {
      title: "成长与技能",
      note: "读取角色的成长记录，并决定成长目标能在多大程度上影响日程安排。",
      labels: {
        read_enabled: "读取成长记录",
        proposals_enabled: "允许提出成长建议",
      },
      helps: {
        read_enabled: "关闭后角色不再把成长记录作为参考。",
        proposals_enabled: "开启后角色可以基于实际进展提出新的成长方向。",
      },
      choices: {},
      order: ["read_enabled", "proposals_enabled"],
    },
    "role.growth.skills": {
      title: "技能领域",
      note: "技能属于角色本身，不随会话改变：在任意一个会话里设置后，角色与其他会话也保持同一套技能领域。个别会话可以单独覆盖，不影响角色级的值。",
      labels: {
        custom_skills: "自定义技能领域",
        schedule_influence_strength: "影响日程的强度",
      },
      helps: {
        custom_skills: "用逗号、换行分隔，也可以直接写 JSON 数组；最多 8 项，每项取前 24 字。第一次设置会把这份清单记为角色级，之后其他会话都继承它。",
        schedule_influence_strength: "0 不影响日程；数值越大，安排越倾向于为练习留出时间。同样按角色共享，可在本会话单独覆盖。",
      },
      choices: {schedule_influence_strength: {0: "不影响", 1: "轻微参考", 2: "留出练习时间",
                                              3: "优先安排相关活动"}},
      order: ["custom_skills", "schedule_influence_strength"],
      /* 保存层级必须说清：这个组的默认落点是角色级，只有本会话覆盖才写会话层。 */
      sections: [
        {id: "shared", title: "角色级技能领域", help: "这一组按角色保存，会话之间共享。",
         fields: ["custom_skills", "schedule_influence_strength"]},
      ],
    },
    role_profile: {
      title: "角色稳定档案",
      note: "按角色保存；姓名、外貌、性格与世界设定会进入新对话，并在该角色的窗口共享。",
      labels: {
        name: "姓名",
        species: "种族",
        birthday: "生日",
        age: "年龄感 / 旧版生日",
        gender: "性别",
        occupation: "职业 / 身份",
        identity: "身份经历补充（原有设定）",
        appearance_points: "外貌识别点",
        hair: "发型 / 发色",
        eyes: "瞳色",
        clothing: "服饰风格",
        image_identity_hint: "头像与图像识别线索",
        appearance: "外貌补充（原有设定）",
        personality: "性格描述（原有设定）",
        first_person: "自称与代词",
        speech_style: "说话方式",
        emotional_style: "情绪表达",
        social_distance: "社交距离与熟悉后的变化",
        reaction_patterns: "典型反应倾向",
        voice_examples: "口吻示例",
        signature_phrases: "标志性表达",
        daily_habits: "日常习惯",
        key_lore: "关键设定",
        character_extra: "其他角色补充",
        motivations: "价值与目标补充（原有设定）",
        core_values: "重视的事",
        desire: "核心欲望 / 长期目标",
        hobbies: "爱好",
        boundaries: "互动边界（原有设定）",
        taboos: "禁忌",
        world_name: "所处世界",
        era: "时代背景",
        tone: "基本法则 / 基调",
        rules: "特殊规则",
        scenes: "主要活动场景",
        network: "世界观关系网",
        world_extra: "其他世界补充",
        world: "世界设定补充（原有设定）",
        platform_group_chat: "群聊",
        platform_screen: "识屏",
        platform_bilibili: "B站",
        platform_qzone: "QQ空间",
        platform_library: "资料柜",
        platform_names: "平台称呼补充（原有设定）",
        world_adaptation_mode: "世界观适配模式",
        world_adaptation: "世界观适配指引",
      },
      helps: {
        name: "角色在设定中的姓名；上方角色展示会优先显示这里。",
        species: "人类、精灵、仿生人等；没有特殊种族时可留空。",
        birthday: "角色的出生日期或纪念日；不确定时可留空。",
        age: "填写年龄感或保留原有生日设定；新的明确生日也可填入“生日”字段。",
        gender: "角色自我认同的性别；不需要的设定可留空。",
        occupation: "职业、身份、所属组织或社会位置。",
        identity: "保留原来整段身份与经历文字；新字段不会覆盖它。",
        appearance_points: "体态、标志物、伤痕、配饰等一眼能认出的特征。",
        hair: "发型、发色，以及重要时的变化。",
        eyes: "瞳色、眼部特征或非人角色的视觉特征。",
        clothing: "日常服饰倾向；具体衣物可在「产出 · 衣柜」管理。",
        image_identity_hint: "头像、截图昵称、OC 别名、水印等难以归入外貌的识别线索。",
        appearance: "保留原来整段外貌文字；新字段不会覆盖它。",
        personality: "保留原来整段性格文字；可与说话方式、习惯字段并用。",
        first_person: "角色如何称呼自己，以及需要稳定使用的自称或代词。",
        speech_style: "语速、句长、口头禅、玩笑方式与情绪表达。",
        emotional_style: "角色通常怎样流露开心、担忧、吃醋、愤怒或安慰；写成倾向，不是固定台词。",
        social_distance: "对陌生人、朋友和亲近之人的相处距离，以及熟悉后会出现的变化。",
        reaction_patterns: "遇到夸奖、批评、冷场、撒娇或意见不合时，角色通常如何回应。",
        voice_examples: "写几句符合角色口吻的原创示例，展示节奏和措辞；不必写完整场景。",
        signature_phrases: "角色偶尔会用的标志性说法，以及需要避免频繁重复的表达。",
        daily_habits: "作息、偏爱的日常活动、反复出现的小习惯。",
        key_lore: "对角色身份、关系、能力或经历有持续影响的关键事实。",
        character_extra: "无法归入上方细项、但需要长期记住的角色补充。",
        motivations: "保留原来整段价值与目标文字；新字段不会覆盖它。",
        core_values: "角色做选择时最看重的原则或事物。",
        desire: "长期想要得到、守护、改变或完成的事。",
        hobbies: "兴趣、收藏、擅长或愿意主动聊起的事。",
        boundaries: "保留原来整段互动边界；关系与用户的具体资料仍在「关系与权限」。",
        taboos: "角色会避开的主题、行为或情境。",
        world_name: "世界、地区、组织或故事舞台的名称。",
        era: "时代、科技水平或历史阶段。",
        tone: "世界观的日常基调，例如温暖、严谨、荒诞或危机四伏。",
        rules: "魔法、科技、社会制度等会影响行动的稳定规则。",
        scenes: "常驻地点、日常活动场景或重要环境。",
        network: "阵营、组织或重要人物之间的关系脉络。",
        world_extra: "无法归入前面字段、但需要保持一致的背景。",
        world: "保留原来整段世界观文字；新字段不会覆盖它。",
        platform_group_chat: "例如 公会闲谈、舰桥频道；普通群聊可以留空。",
        platform_screen: "角色世界里对屏幕 / 识屏的称呼。",
        platform_bilibili: "角色世界里对 B 站或视频站的称呼。",
        platform_qzone: "角色世界里对 QQ 空间或动态墙的称呼。",
        platform_library: "角色世界里对资料柜 / 书柜的称呼。",
        platform_names: "保留原来的平台转写文字；逐个平台的对应称呼在上方填写。",
        world_adaptation_mode: "自动参考世界设定，也可以指定现代、幻想、科幻、自定义规则或关闭转写。",
        world_adaptation: "说明日程、资料柜、屏幕和外部平台如何用设定内说法自然表达；现代日常角色可留空。",
      },
      choices: {world_adaptation_mode: {auto: "自动", modern: "现代日常", fantasy: "幻想世界",
        sci_fi: "科幻世界", custom: "自定义", off: "关闭"}},
      rows: {identity: 4, appearance: 4, personality: 5, first_person: 2, speech_style: 3, motivations: 4, boundaries: 4,
             world: 5, platform_names: 4, world_adaptation: 4, image_identity_hint: 3, network: 3, world_extra: 3,
             key_lore: 3, character_extra: 3, emotional_style: 3, social_distance: 3,
             reaction_patterns: 4, voice_examples: 5},
      order: ["name", "species", "birthday", "age", "gender", "occupation", "identity", "key_lore", "character_extra", "appearance_points", "hair", "eyes",
        "clothing", "image_identity_hint", "appearance", "personality", "first_person", "speech_style", "emotional_style", "social_distance",
        "reaction_patterns", "voice_examples", "signature_phrases", "daily_habits", "motivations",
        "core_values", "desire", "hobbies", "boundaries", "taboos", "world_name", "era", "tone",
        "rules", "scenes", "network", "world_extra", "world", "platform_group_chat",
        "platform_screen", "platform_bilibili", "platform_qzone", "platform_library", "platform_names",
        "world_adaptation_mode", "world_adaptation"],
      scopeNote: "当前角色 · 所有会话共享",
      onStatus: updateRoleProfileSummary,
      sections: [
        {id: "identity", title: "基础身份", help: "姓名、种族、生日、年龄感、职业、关键经历与补充。", fields: ["name", "species", "birthday", "age", "gender", "occupation", "identity", "key_lore", "character_extra"]},
        {id: "appearance", title: "外貌与识别", help: "发型、瞳色、服饰和能稳定辨认角色的线索。", fields: ["appearance_points", "hair", "eyes", "clothing", "image_identity_hint", "appearance"]},
        {id: "personality", title: "性格与日常", help: "性格底色、日常习惯和角色做事的稳定倾向。", fields: ["personality", "daily_habits"]},
        {id: "voice", title: "口吻与反应", help: "用自称、情绪表达、典型反应和示例台词写出角色说话的感觉。", fields: ["first_person", "speech_style", "emotional_style", "social_distance", "reaction_patterns", "voice_examples", "signature_phrases"]},
        {id: "motivations", title: "价值与目标", help: "做选择的原则、长期目标与兴趣。", fields: ["motivations", "core_values", "desire", "hobbies"]},
        {id: "boundaries", title: "相处边界", help: "互动偏好、禁忌与关系资料入口。", fields: ["boundaries", "taboos"]},
        {id: "world", title: "世界蓝图", help: "世界、时代、规则、场景与人物网络。", fields: ["world_name", "era", "tone", "rules", "scenes", "network", "world_extra", "world"]},
        {id: "platform_names", title: "平台称呼与世界观适配", help: "选择转写模式，填写平台称呼与自定义规则。", fields: ["platform_group_chat", "platform_screen", "platform_bilibili", "platform_qzone", "platform_library", "platform_names", "world_adaptation_mode", "world_adaptation"]},
      ],
    },
    relationship_profile: {
      title: "当前关系资料",
      note: "按当前角色和私聊对象保存；仅用于这段关系的对话，不会带到其他用户或群聊。",
      labels: {
        default_nickname: "对用户的称呼",
        user_gender: "用户性别",
        user_birthday: "用户生日",
        user_occupation: "用户职业",
        role_relation: "用户与角色的关系",
        interaction: "相处方式",
        extra: "其他补充",
      },
      helps: {
        default_nickname: "角色平时如何称呼当前这位用户；没有固定称呼时留空。",
        user_gender: "只记录对方明确告诉你的内容；不确定时留空。",
        user_birthday: "生日或纪念日；不确定时留空。",
        user_occupation: "当前用户明确提供的职业；避免猜测。",
        role_relation: "例如朋友、搭档、家人；按你确认的关系填写。",
        interaction: "你们熟悉的相处节奏、互动习惯或需要留意的关系背景。",
        extra: "只对当前用户有效的其他补充；避免放入角色自身设定。",
      },
      rows: {default_nickname: 2, user_gender: 2, user_birthday: 2, user_occupation: 2,
             role_relation: 3, interaction: 4, extra: 4},
      order: ["default_nickname", "user_gender", "user_birthday", "user_occupation",
        "role_relation", "interaction", "extra"],
      scopeNote: "当前角色 × 当前私聊用户 · 跨窗口共享该关系",
      sections: [
        {id: "person", title: "这位用户", help: "称呼与对方明确提供的基本资料。", fields: [
          "default_nickname", "user_gender", "user_birthday", "user_occupation"]},
        {id: "relationship", title: "你们的相处", help: "当前角色与这位用户之间的关系和相处背景。", fields: [
          "role_relation", "interaction", "extra"]},
      ],
    },
    knowledge: {
      title: "世界知识与来源",
      note: "把本机世界书与知识库作为角色可引用的背景资料；导入只做增量，不覆盖已有条目。",
      labels: {
        import_enabled: "允许导入本机知识来源",
        import_paths: "世界书文件路径",
        source_ids: "知识库 / 文档标识",
        entry_limit: "单次导入条目上限",
        entry_char_limit: "单条素材最长字数",
        source_limit: "来源数量上限",
        candidate_char_budget: "单轮候选字符预算",
        inject_enabled: "允许在对话中引用知识",
        inject_max_entries: "每轮最多引用条数",
        inject_max_chars: "每轮引用字符上限",
        member_recognition_enabled: "启用成员线索",
        member_match_aliases: "成员线索匹配别名",
        member_inject_limit: "每轮成员线索条数",
        member_clue_chars: "单条成员线索字数",
      },
      helps: {
        import_enabled: "关闭时不会读取任何知识来源；已有的导入结果仍然保留。",
        import_paths: "相对 AstrBot 数据根解析，也可写绝对路径；留空时按 AstrBot 的常规位置（如 data/world_book）查找。分隔用换行、逗号、分号或全角逗号/分号。",
        source_ids: "只接受本机确实存在的标识，形如 kb:<知识库 ID> 或 doc:<知识库 ID>:<文档 ID>；写错的项会被静默跳过。分隔用换行、逗号、分号或全角逗号/分号——注意顿号不算分隔符。",
        candidate_char_budget: "检索阶段可扫描的字符总量，不是最终注入量；调小会让命中变少。",
        inject_enabled: "只决定是否把已导入的知识作为背景材料；不会让知识变成事实来源。",
        member_recognition_enabled: "成员线索只用于显示归因，不会写成成员事实，也不改变权限。",
        member_match_aliases: "允许用别名匹配到同一成员；关闭后只按准确名字匹配。",
      },
      order: ["import_enabled", "import_paths", "source_ids", "entry_limit", "entry_char_limit",
              "source_limit", "candidate_char_budget", "inject_enabled", "inject_max_entries",
              "inject_max_chars", "member_recognition_enabled", "member_match_aliases",
              "member_inject_limit", "member_clue_chars"],
      /* 导入侧与引用侧是两条独立的链：导入总闸关着时，导入参数不起作用；
         引用总闸关着时，引用参数不起作用。分组让页面直接说明这件事，
         而不是把十四个控件一视同仁地铺开。 */
      sections: [
        {id: "import", title: "世界书与资料来源", help: "只做增量导入，不覆盖已有条目；关闭导入总闸时，下面几项不起作用。",
         fields: ["import_enabled", "import_paths", "source_ids", "entry_limit", "entry_char_limit",
                  "source_limit", "candidate_char_budget"]},
        {id: "inject", title: "在对话中引用", help: "只决定是否把已导入的知识作为背景材料；关闭时下面几项不起作用，已导入的内容仍然保留。",
         fields: ["inject_enabled", "inject_max_entries", "inject_max_chars"]},
        {id: "members", title: "群聊成员线索", help: "只用于群聊中的显示归因，不会写成成员事实，也不改变权限。",
         fields: ["member_recognition_enabled", "member_match_aliases", "member_inject_limit",
                  "member_clue_chars"]},
      ],
    },
    life: {
      title: "日记、梦境与休息",
      note: "日记、睡眠与阅读的日程，加上日记与梦境的写作偏好和休息时段的回复判定。这些字段按窗口生效，但同一角色可在角色层统一覆盖。",
      labels: {
        enabled: "启用生活例程",
        diary_enabled: "每天自动写日记",
        diary_time: "写日记的时刻（HH:MM）",
        timezone: "生活例程时区",
        sleep_enabled: "按作息自动进入睡眠",
        sleep_time: "入睡时刻（HH:MM）",
        sleep_timezone: "作息时区",
        sleep_minutes: "睡眠时长（分钟）",
        reading_enabled: "启用阅读角",
        derive_enabled: "从日记提取衍生材料",
        diary_style_prompt: "日记风格补充",
        dream_theme_candidates: "梦境题材参考",
        dream_mixed_themes_enabled: "允许题材混搭",
        dream_intimate_theme_enabled: "允许亲密题材",
        dream_afterglow_mode: "醒后余韵强度",
        enable_rest_reply_simulation: "启用休息时段回复判定",
        rest_reply_mode: "判定方式",
        rest_reply_probability: "概率判定放行率（%）",
        rest_reply_llm_threshold: "模型判定放行分阈值",
        rest_reply_active_windows: "生效时段",
        rest_reply_awake_grace_minutes: "被唤醒后免重判（分钟）",
        enable_rest_backlog_reply: "记录休息期未回消息",
        rest_backlog_max_messages: "补看消息上限",
      },
      helps: {
        enabled: "关闭这一项时，日记、睡眠与阅读的日程都不再登记，下面各项都不起作用。",
        diary_enabled: "只登记一个每日写作日程；写成什么、写不写由角色按实际情况决定。",
        diary_time: "按下面的时区解释，24 小时制，形如 23:50。",
        timezone: "日记日程使用的 IANA 时区，如 Asia/Shanghai。",
        sleep_enabled: "开启后按入睡时刻自动进入睡眠，醒来时间由睡眠时长算出。",
        sleep_time: "按作息时区解释，24 小时制，形如 00:30。可以跨零点。",
        sleep_timezone: "作息可以独立于日记时区，例如角色作息按另一个城市算。",
        reading_enabled: "只登记阅读角是否可用；读了什么、读到哪由角色记录。",
        derive_enabled: "从日记正文提取摘要、梦境一类衍生材料；关闭时只保存原正文。",
        diary_style_prompt: "补充日记的写法偏好；留空使用默认风格。",
        dream_theme_candidates: "作为可选参考写进梦境提示词，最多取前 6 项；用逗号或顿号分隔。不必全部用上。",
        dream_mixed_themes_enabled: "允许梦境题材轻微混搭，仍要求叙述自然连贯。",
        dream_intimate_theme_enabled: "允许暧昧或亲密的梦境题材；仍是梦的记法，不构成现实事件。",
        dream_afterglow_mode: "决定醒后余韵写得多明显；自动按上下文决定。",
        enable_rest_reply_simulation: "关闭时休息时段不额外判定，按正常流程回复。",
        rest_reply_mode: "概率判定按下面的百分比放行；模型判定按边界分与模型分决定。",
        rest_reply_active_windows: "形如 23:00-08:30,12:20-13:40；结束时间早于开始时间视为跨零点。留空表示全天生效。",
        rest_reply_awake_grace_minutes: "被叫醒后的这段时间里不再重新判定，避免又被当成在睡。",
        enable_rest_backlog_reply: "开启后会记录休息期间收到的消息，醒来时作为补看材料；不会逐条补发。",
        rest_backlog_max_messages: "补看材料的条数上限，超出只保留最近的几条。",
      },
      choices: {rest_reply_mode: {probability: "概率判定", llm: "模型判定"},
                dream_afterglow_mode: {auto: "自动", "轻": "轻", "标准": "标准", "明显": "明显"}},
      /* 两个时刻字段用时间控件。注册表里它们是 TEXT，内核的 valid() 对 TEXT
         只判「是不是字符串」，所以 HH:MM 的形状由下面的 audit 兜住。
         时区也是 TEXT，但必须声明成单行——内核默认把 TEXT 画成 textarea。 */
      inputs: {diary_time: "time", sleep_time: "time", timezone: "line", sleep_timezone: "line"},
      audit: lifeAudit,
      order: ["enabled", "diary_enabled", "diary_time", "timezone",
              "sleep_enabled", "sleep_time", "sleep_timezone", "sleep_minutes",
              "reading_enabled", "derive_enabled",
              "diary_style_prompt", "dream_theme_candidates", "dream_mixed_themes_enabled",
              "dream_intimate_theme_enabled", "dream_afterglow_mode",
              "enable_rest_reply_simulation", "rest_reply_mode", "rest_reply_probability",
              "rest_reply_llm_threshold", "rest_reply_active_windows",
              "rest_reply_awake_grace_minutes", "enable_rest_backlog_reply",
              "rest_backlog_max_messages"],
      /* 例程（日记/睡眠/阅读）与写作偏好、休息判定是三条独立的链：
         总闸关着时例程不登记；写作偏好只影响文本；休息判定只管回复时机。 */
      sections: [
        {id: "routine", title: "生活例程", help: "关闭总闸时，日记、睡眠与阅读的日程都不再登记，下面各项都不起作用。",
         fields: ["enabled", "diary_enabled", "diary_time", "timezone", "reading_enabled", "derive_enabled"]},
        {id: "sleep", title: "睡眠作息", help: "人格共享作息；执行会选择已授权的有效窗口。",
         fields: ["sleep_enabled", "sleep_time", "sleep_timezone", "sleep_minutes"]},
        {id: "writing", title: "日记与梦境", help: "写作偏好，只影响日记与梦境的文本，不改变任何权限或事实。",
         fields: ["diary_style_prompt", "dream_theme_candidates", "dream_mixed_themes_enabled",
                  "dream_intimate_theme_enabled", "dream_afterglow_mode"]},
        {id: "rest", title: "休息时段回复判定", help: "关闭总闸时，下面各项都不起作用，休息时段按正常流程回复。",
         fields: ["enable_rest_reply_simulation", "rest_reply_mode", "rest_reply_probability",
                  "rest_reply_llm_threshold", "rest_reply_active_windows",
                  "rest_reply_awake_grace_minutes"]},
        {id: "backlog", title: "醒来后的补看材料", help: "只记录休息期间收到的消息作为补看材料，不会逐条补发。",
         fields: ["enable_rest_backlog_reply", "rest_backlog_max_messages"]},
      ],
    },
    library: {
      title: "书架",
      note: "按角色生效。书架只保存书目、来源引用与阅读状态；作品正文与图片由扩展持有，因此小说与漫画共用这同一套设置。",
      labels: {
        enabled: "启用书架",
        reviews_enabled: "允许写书评",
        reading_excerpt_chars: "单轮读取字数上限",
        manual_entries_enabled: "允许手工添加书目",
        max_entries_per_page: "每页列出条目数",
        rating_enabled: "允许给作品打分",
        preference_influence_enabled: "把阅读偏好写进提示词",
        preference_min_ratings: "形成偏好的最少打分数",
        preference_max_terms: "单次提示词最多列出的作品数",
        min_interval_hours: "两次主动开口的最短间隔（小时）",
        share_probability: "主动分享读书进展的概率",
        ask_probability: "主动询问对方阅读的概率",
      },
      helps: {
        enabled: "关闭后读取与写入都不可用；已保存的书目与阅读进度保留，重新开启即可继续。",
        reviews_enabled: "书评必须引用真实读过的位置作为依据；关闭只是不允许新写，已有书评保留。",
        reading_excerpt_chars: "一次回复里可引入的作品正文上限，避免整本书进入上下文。",
        manual_entries_enabled: "手工条目与扩展登记的书目并存；同名时以扩展登记的为准，手工条目不覆盖它。",
        max_entries_per_page: "书目列表的单页上限，只影响列出数量。",
        rating_enabled: "打分范围是 1 到 5。不打分的书评只是「读过」，不参与口味判断。",
        preference_influence_enabled: "偏好只作为口味参考注入，不是本轮要求，角色可以不同意；关闭后完全不注入。",
        preference_min_ratings: "打分数不到这个下限时什么都不注入——证据不足时沉默，比给一个更弱的猜测好。",
        preference_max_terms: "一次最多列出几部作品，按口味强弱取前几名；只影响注入，不改动已保存的书评。",
        min_interval_hours: "这个间隔记录在数据表里，重启不会被重置；间隔没到就不会开口，概率再高也一样。",
        share_probability: "先看间隔再看概率：间隔没到时，即使设为 1 也不会开口。",
        ask_probability: "与主动分享各自计时，一次分享不会占掉一次询问的机会。",
      },
      choices: {},
      order: ["enabled", "reviews_enabled", "reading_excerpt_chars",
              "manual_entries_enabled", "max_entries_per_page",
              "rating_enabled", "preference_influence_enabled",
              "preference_min_ratings", "preference_max_terms",
              "min_interval_hours", "share_probability", "ask_probability"],
      /* 总闸关着时其余各项都不起作用，所以先给开关，再给受它约束的上限。 */
      sections: [
        {id: "switches", title: "能力开关", help: "关闭书架后，下面各项都不起作用。",
         fields: ["enabled", "reviews_enabled", "manual_entries_enabled"]},
        {id: "limits", title: "读取与列出上限", help: "只影响单轮引入的正文字数与列表条数，不改变已保存的数据。",
         fields: ["reading_excerpt_chars", "max_entries_per_page"]},
        {id: "preference", title: "阅读偏好", help: "打分先攒够下限才形成口味；偏好只是参考，不是本轮要求。",
         fields: ["rating_enabled", "preference_influence_enabled",
                  "preference_min_ratings", "preference_max_terms"]},
        {id: "triggers", title: "主动开口的频率", help: "先看最短间隔，再看概率；间隔记录在数据表里，重启不重置。",
         fields: ["min_interval_hours", "share_probability", "ask_probability"]},
      ],
    },
    "content.authoring": {
      title: "原生创作",
      note: "按角色生效。有 Content 权限时，新作正文会直接保存进作品库；续写读取固定版本并保存候选稿。",
      labels: {
        enabled: "启用原生创作",
        direction_prompt: "创作方向",
      },
      helps: {
        enabled: "开启后，只有明确要求创作并留存作品时才会调用；关闭不会影响已经保存的 Content 作品。",
        direction_prompt: "写角色创作时长期遵循的题材、语气或表达偏好；会与每次具体要求一起提供。",
      },
      choices: {},
      order: ["enabled", "direction_prompt"],
      sections: [
        {id: "availability", title: "创作能力", help: "只在私聊提供；是否能保存仍由 Content 当前授权决定。",
         fields: ["enabled"]},
        {id: "direction", title: "创作方向", help: "长期偏好作为提示词材料，不改变作品权限或保存方式。",
         fields: ["direction_prompt"]},
      ],
    },
    wardrobe: {
      title: "衣柜",
      note: "按角色生效。衣物条目本身保存在数据表里，这里只决定能不能用、能说多少、一次能收几张图。",
      labels: {
        enabled: "启用衣柜",
        tendency: "穿衣倾向说明",
        prompt_enabled: "允许把衣柜写进提示词",
        prompt_max_items: "单次提示词最多列出的衣物件数",
        image_max_count: "一次穿搭请求最多识别的图片数",
        image_prompt: "穿搭识图要求",
      },
      helps: {
        enabled: "关闭后既不进提示词，也不接受新的识图入库；已保存的衣物条目保留，重新开启即可继续。",
        tendency: "用你自己的话描述角色的穿衣倾向，最多 800 字；超长会被拒绝而不是截断。",
        prompt_enabled: "关闭时衣柜完全不进提示词，条目仍可查看与维护。",
        prompt_max_items: "只限制一次写进提示词的件数，不删改已保存的条目。",
        image_max_count: "一次穿搭请求最多处理几张图，多出的图片不会被处理。",
        image_prompt: "识图入库时对衣物的额外要求，最多 800 字。",
      },
      choices: {},
      order: ["enabled", "tendency", "prompt_enabled", "prompt_max_items",
              "image_max_count", "image_prompt"],
      sections: [
        {id: "switches", title: "能力开关", help: "总闸关闭时，下面各项都不起作用。",
         fields: ["enabled", "prompt_enabled"]},
        {id: "material", title: "提示词材料", help: "决定衣柜能说多少，以及一次能收几张图。",
         fields: ["prompt_max_items", "image_max_count"]},
        {id: "words", title: "你自己的话", help: "倾向与识图要求都按原样使用，超长会被拒绝。",
         fields: ["tendency", "image_prompt"]},
      ],
    },
    "photo.reference": {
      title: "参考图",
      note: "按角色生效。参考素材按登记条目保存在资产表里，配置里不存文件路径；每张图都要带校验摘要，改动过的素材在使用时会被拒绝。",
      labels: {
        enabled: "启用参考图",
        daily_outfit_enabled: "启用每日穿搭",
        daily_outfit_rotation_days: "同一套穿搭的轮换间隔（天）",
      },
      helps: {
        enabled: "关闭后参考图既不能读取也不能新登记；已登记的素材保留，撤回仍然可用。",
        daily_outfit_enabled: "同意使用参考图，不等于同意每天都出一张穿搭图，所以这里是独立开关。",
        daily_outfit_rotation_days: "同一套衣服再次出现前至少要间隔多少天。",
      },
      choices: {},
      order: ["enabled", "daily_outfit_enabled", "daily_outfit_rotation_days"],
      sections: [
        {id: "switches", title: "能力开关", help: "两个开关互相独立：先允许参考图，再决定是否每天出穿搭。",
         fields: ["enabled", "daily_outfit_enabled"]},
        {id: "rotation", title: "轮换", help: "只影响同款出现的间隔，不改变已登记素材。",
         fields: ["daily_outfit_rotation_days"]},
      ],
    },
    group_participation: {
      title: "群聊参与",
      note: "决定角色在群里怎么旁听、何时接话，以及复读跟读的尺度。三项都不会自己发起对话——仍然要有一条群消息打开这一轮。",
      labels: {
        enable_group_social_context: "启用群聊氛围参考",
        enable_group_mood_detection: "识别群聊氛围",
        enable_group_roleplay_strength: "判断扮演强度",
        enable_group_moments: "记录本群名场面",
        enable_group_moment_portrait: "识别当前发言者线索",
        enable_group_joke_guard: "启用接梗护栏",
        enable_group_persona_denoise: "原人格去噪",
        enable_group_interjection: "允许主动插话",
        group_interject_min_interval_minutes: "两次插话最短间隔（分钟）",
        group_interject_max_daily: "每日插话上限",
        enable_group_interjection_feedback: "按反馈调整插话",
        group_interject_feedback_window_seconds: "反馈统计时间窗（秒）",
        enable_group_repeat_follow: "允许跟读复读",
        group_repeat_count_distinct_users_only: "只在多人重复时触发",
        group_repeat_trigger_threshold: "触发跟读的重复次数",
        group_repeat_follow_probability: "跟读概率",
        group_repeat_interrupt_probability: "打断复读的初始概率",
        group_repeat_interrupt_probability_step: "打断概率每次递增",
        group_repeat_interrupt_text: "打断复读时说的话",
        group_repeat_window_seconds: "统计重复的时间窗（秒）",
      },
      helps: {
        enable_group_social_context: "关闭时下面五项氛围参考都不起作用，角色只按对话本身理解群聊。",
        enable_group_mood_detection: "按可见的近句估计氛围倾向；只是参考，不代表任何成员的态度或性格。",
        enable_group_roleplay_strength: "在氛围基础上判断该玩闹还是该收敛，只影响表达幅度。",
        enable_group_moments: "记住群里反复出现的梗，供接梗时参考；不会写成成员的性格或事实。",
        enable_group_moment_portrait: "从当前发言者的可见表达里取一点线索，用于判断接梗的尺度。",
        enable_group_joke_guard: "可见窗口里出现明确不适或反对时，自动降低玩笑强度。",
        enable_group_persona_denoise: "回复前过滤掉会盖过原人格的腔调；关闭时可能更像通用助手。",
        enable_group_interjection: "关闭时下面四项都不起作用；开启也只是允许，仍要按间隔与上限判断。",
        group_interject_min_interval_minutes: "0 表示不限间隔；调小会让插话更频繁。",
        group_interject_max_daily: "0 表示不在群里主动插话。",
        group_interject_feedback_window_seconds: "统计这段时间里群友对插话的反应；调小只参考最近的反馈。",
        enable_group_repeat_follow: "关闭时下面七项都不起作用，角色不参与复读。",
        group_repeat_count_distinct_users_only: "开启后同一人连发多次不算数，必须多人重复才跟读。",
        group_repeat_trigger_threshold: "同一句话被重复到该次数后才考虑跟读；3 最敏感，20 最保守。",
        group_repeat_follow_probability: "0 到 1 之间；越大越容易跟一句。",
        group_repeat_interrupt_probability: "判定要不要用「打断语」收尾，而不是跟着复读。",
        group_repeat_interrupt_probability_step: "复读持续越久、打断概率越高，每一次按这个幅度累加。",
        group_repeat_interrupt_text: "不打字时用的一句短语，最多 80 个字，只能是一行。",
        group_repeat_window_seconds: "在这段时间内的重复才计入次数；调大更容易触发。",
      },
      order: ["enable_group_social_context", "enable_group_mood_detection",
              "enable_group_roleplay_strength", "enable_group_moments",
              "enable_group_moment_portrait", "enable_group_joke_guard",
              "enable_group_persona_denoise",
              "enable_group_interjection", "group_interject_min_interval_minutes",
              "group_interject_max_daily", "enable_group_interjection_feedback",
              "group_interject_feedback_window_seconds",
              "enable_group_repeat_follow", "group_repeat_count_distinct_users_only",
              "group_repeat_trigger_threshold", "group_repeat_follow_probability",
              "group_repeat_interrupt_probability", "group_repeat_interrupt_probability_step",
              "group_repeat_interrupt_text", "group_repeat_window_seconds"],
      /* 三条链各自独立：氛围参考有一层总闸，插话与跟读各有自己的总闸与预算。
         不分组的话，关掉总闸后调下面的数字会毫无反应，看着像坏了。 */
      sections: [
        {id: "atmosphere", title: "群聊氛围参考", help: "关闭这一项时，下面五项都不起作用，角色只按对话本身理解群聊。",
         fields: ["enable_group_social_context", "enable_group_mood_detection",
                  "enable_group_roleplay_strength", "enable_group_moments",
                  "enable_group_moment_portrait", "enable_group_joke_guard"]},
        {id: "denoise", title: "表达去噪", help: "只影响说话的腔调，不改变原人格、身份与授权。",
         fields: ["enable_group_persona_denoise"]},
        {id: "interjection", title: "主动插话", help: "关闭总闸时下面四项不起作用；开启也只是允许，仍受间隔与每日上限限制。",
         fields: ["enable_group_interjection", "group_interject_min_interval_minutes",
                  "group_interject_max_daily", "enable_group_interjection_feedback",
                  "group_interject_feedback_window_seconds"]},
        {id: "repeat", title: "复读跟读", help: "关闭总闸时下面七项都不起作用；跟读与打断二选一，按概率判定。",
         fields: ["enable_group_repeat_follow", "group_repeat_count_distinct_users_only",
                  "group_repeat_trigger_threshold", "group_repeat_follow_probability",
                  "group_repeat_interrupt_probability", "group_repeat_interrupt_probability_step",
                  "group_repeat_interrupt_text", "group_repeat_window_seconds"]},
      ],
    },
    /* 主动联系偏好：唯一一个四层组，也是最长的一个分区（158 项 / 22 段）。
       它此前四个触点全缺，92 个字段在任何页面上都点不到；段落声明在这里，
       段落之外的字段会被内核悄悄附到最后一段，所以 order 由段落拼出来。 */
    "proactive.contact": {
      title: "主动联系偏好",
      note: "按本对象与角色的这一段关系保存：默认写在窗口层，安装 / 角色 / 关系层的值会被继承下来。"
            + "改动从下一轮主动评估开始生效，不会立刻发消息。",
      labels: {
        enabled: "允许主动联系",
        automatic_enabled: "启用后台自动联系",
        note: "补充联系偏好",
        interval_seconds: "两次联系至少间隔（秒）",
        idle_seconds: "对话结束后至少等候（秒）",
        event_max_age_seconds: "生活事件可接续时长（秒）",
        max_contacts_24h: "本会话 24 小时内最多联系（次）",
        max_attempts_24h: "本会话 24 小时内最多尝试（次）",
        unanswered_slowdown_start: "连续未回应几次后开始放慢",
        unanswered_pause_after: "连续未回应几次后暂停（0 表示不暂停）",
        unanswered_max_interval_multiplier: "放慢后的最大间隔倍数",
        proactive_intensity_preset: "主动节奏档位",
        proactive_intensity_body_chars: "单条主动消息字数提示（0 表示按档位）",
        enable_proactive_burst: "允许连发续话",
        proactive_burst_max_messages: "一轮最多连发几条",
        proactive_burst_gap_min_seconds: "连发最短间隔（秒）",
        proactive_burst_gap_max_seconds: "连发最长间隔（秒）",
        proactive_hour_activity_enabled: "按本地小时曲线加权",
        proactive_hour_activity_curve: "24 小时活跃曲线（24 个 0.05–2 的权重）",
        proactive_closing_grace_minutes: "一轮结束后的静默时长（分钟）",
        proactive_closing_contacts_threshold: "连续联系几条后进入静默",
        proactive_share_probability: "分享自己生活与作品的概率（%）",
        max_relationship_contacts_24h: "同一关系 24 小时内最多联系（次）",
        max_relationship_attempts_24h: "同一关系 24 小时内最多尝试（次）",
        quiet_enabled: "启用免打扰时段",
        quiet_start: "免打扰开始",
        quiet_end: "免打扰结束",
        quiet_timezone: "免打扰时区",
        pause_until: "暂缓全部联系至（ISO 时间）",
        dedup_enabled: "启用重复抑制",
        dedup_last_message_enabled: "与角色最后一条回复比对",
        dedup_last_message_window_minutes: "最后一条回复的回看窗口（分钟）",
        dedup_sent_window_minutes: "已发同类内容的不重复时长（分钟）",
        dedup_weather_window_minutes: "天气与预警内容的不重复时长（分钟）",
        dedup_min_shared_tokens: "短话题最少共享词数",
        dedup_min_overlap_ratio: "长话题最低重叠比例",
        dedup_policies: "启用的去重路线",
        silence_min_confidence: "开口置信度门槛（0–1）",
        silence_feedback_penalty: "沉默反馈降权（0–1）",
        enable_llm_proactive_persona_judge: "草稿发出前做人格复核",
        proactive_persona_judge_threshold: "复核通过分阈值",
        proactive_persona_judge_cache_minutes: "复核结果缓存时长（分钟）",
        proactive_persona_judge_daily_limit: "每日复核次数上限",
        proactive_persona_judge_exempt_purposes: "免复核的契机",
        ...purposeLabels("enabled", "允许这类联系"),
        ...purposeLabels("weight", "相对权重"),
        ...purposeLabels("pause_until", "暂缓至（ISO 时间）"),
        enable_daily_greetings: "启用每日问候",
        greeting_morning_window: "早间问候窗口",
        greeting_noon_window: "午间问候窗口",
        greeting_evening_window: "晚间问候窗口",
        greeting_idle_minutes: "问候前至少安静（分钟）",
        allow_insomnia_night_message: "允许深夜失眠时段开口",
        insomnia_night_start: "失眠时段开始",
        insomnia_night_end: "失眠时段结束",
        insomnia_night_daily_limit: "失眠夜每日最多开口（次）",
        insomnia_require_sleep_state: "只在睡不着的状态下开口",
        meal_checkin_enabled: "启用三餐问候",
        meal_lunch_time: "午餐问候时刻",
        meal_dinner_time: "晚餐问候时刻",
        meal_care_followup_minutes: "饭点后仍可跟进关怀（分钟）",
        date_checkin_enabled: "启用纪念日问候",
        date_checkin_time: "纪念日问候时刻",
        important_dates: "重要日期清单（JSON）",
        important_date_lookahead_days: "提前几天开始留意",
        weather_checkin_enabled: "定时天气问候",
        weather_checkin_time: "天气问候时刻",
        weather_change_enabled: "天气突变时联系",
        weather_sample_minutes: "天气采样间隔（分钟）",
        official_weather_alert_enabled: "转发官方气象预警",
        official_alert_poll_minutes: "预警轮询间隔（分钟）",
        official_alert_min_severity: "最低预警级别",
        news_share_enabled: "启用新闻分享源",
        news_source_kind: "资讯来源类型",
        news_source_uid: "B 站 UID",
        news_source_url: "RSS / HTTPS JSON 地址",
        news_check_interval_minutes: "资讯检查间隔（分钟）",
        news_daily_hot_read_enabled: "启用每日热榜",
        news_hot_sources: "热榜来源",
        news_hot_result_count: "热榜每次取几条",
        web_exploration_enabled: "启用网络探索",
        web_exploration_interests: "探索兴趣词",
        web_exploration_min_interval_hours: "两次探索最短间隔（小时）",
        web_exploration_result_count: "每次探索取几条",
        external_event_self_link_enabled: "允许外部事件关联自身经历",
        external_event_self_link_weight: "关联权重",
        external_event_self_link_cooldown_hours: "两次关联最短间隔（小时）",
        balance_awareness_enabled: "允许因余额变化联系",
        balance_include_amount_in_message: "消息里带上具体金额",
        balance_currency_label: "货币单位文字",
        balance_low_threshold: "余额偏低阈值（绝对值）",
        balance_critical_threshold: "余额危险阈值（绝对值）",
        balance_low_percent_threshold: "余额偏低阈值（百分比）",
        balance_critical_percent_threshold: "余额危险阈值（百分比）",
        balance_check_interval_minutes: "余额检查间隔（分钟）",
        balance_message_cooldown_hours: "两次余额提醒最短间隔（小时）",
        screen_glance_enabled: "启用屏幕观察联系",
        screen_glance_daily_limit: "每日最多观察（次）",
        screen_glance_cooldown_minutes: "两次观察最短间隔（分钟）",
        screen_glance_goodnight_enabled: "晚安后主动看一眼",
        screen_glance_goodnight_delay_minutes: "晚安后等待时长（分钟）",
        screen_glance_followup_enabled: "未回应时补看一眼",
        screen_glance_followup_after_minutes: "未回应多久后补看（分钟）",
        screen_glance_followup_cooldown_minutes: "两次补看最短间隔（分钟）",
        voice_action_enabled: "允许主动发语音",
        voice_action_max_chars: "语音转写最长字数",
        voice_action_cooldown_minutes: "两条语音最短间隔（分钟）",
        poke_action_enabled: "允许主动戳一戳",
        poke_action_daily_limit: "每日最多戳一戳（次）",
        poke_action_cooldown_minutes: "两次戳一戳最短间隔（分钟）",
        appointment_lead_minutes: "约定前多久开口（分钟）",
        appointment_lag_minutes: "约定到点后仍可补说（分钟）",
        appointment_pre_silence_minutes: "约定前的静默时长（分钟）",
        generation_history_limit: "起草时参考的历史联系条数",
        history_max_chars: "历史材料最长字数",
        style_prompt: "主动开口的风格补充",
      },
      /* 只写「这一项为什么重要」和它跟别项的关系；单位已在标签里。 */
      helps: {
        enabled: "总闸只表示偏好允许。能不能真的开口还取决于这个对象是否持有主动联系授权：在上方「联系节奏」里开启时会一并签发，只改这里的开关不会签发授权。",
        automatic_enabled: "关闭时资讯、天气、余额、屏幕这些自动契机都不再发起；提醒与约定由日程自己负责，不受这里影响。",
        note: "写成自己的话，作为联系偏好写进提示词；不改变权限、频率或去重。",
        interval_seconds: "两次主动开口之间的最短间隔；连续未回应的次数越多，实际间隔按下面的倍数放大。",
        idle_seconds: "对方说完话后的这段安静时间里不会开口，避免刚聊完就又被找上。",
        event_max_age_seconds: "生活事件与日记素材超过这段时间就不再作为开口理由；提醒与预警有自己的时效。",
        max_contacts_24h: "上限就是上限：达到后当天不再开口，即使还有合适的话题。",
        max_attempts_24h: "尝试包含被判定为「沉默」而没有发出的机会，所以尝试数总是大于等于联系数。",
        unanswered_slowdown_start: "从这里开始，每多一次未回应就多放慢一档。",
        unanswered_pause_after: "连续未回应达到该次数后停止常规联系，直到对方再次开口；0 表示不暂停。",
        unanswered_max_interval_multiplier: "放慢的上限倍数，避免间隔无限增长。",
        proactive_intensity_preset: "档位缩放间隔与安静门槛、限制一轮的条数、给一个长度提示；它不会放宽任何额度或权限。",
        proactive_intensity_body_chars: "0 表示使用档位自带的长短提示。",
        enable_proactive_burst: "连发只接着一条普通话题继续：提醒、预警、问候与分享不会拖出一串消息。",
        proactive_burst_max_messages: "一轮的总条数上限；档位要求的条数更少时以档位为准。",
        proactive_burst_gap_min_seconds: "每轮的间隔由这两个值确定性地抽一次，重启后不会重新抽。",
        proactive_burst_gap_max_seconds: "比最小值小时按最小值处理。",
        proactive_hour_activity_enabled: "关闭时保持固定的时段网格，不做小时加权。",
        proactive_hour_activity_curve: "必须写满 24 个数字（0.05–2.00），按免打扰时区的小时对齐；数量不对会被拒绝，而不是悄悄回退到默认曲线。",
        proactive_closing_grace_minutes: "连续联系达到下面的条数后，安静这段时间再恢复普通机会；0 表示不进入收尾静默。",
        proactive_closing_contacts_threshold: "一轮连续联系达到该条数即进入收尾静默。",
        proactive_share_probability: "只作用于「分享自己的生活」与「作品与阅读」两类契机；提醒与预警不受影响，100 表示每次都发。",
        max_relationship_contacts_24h: "按同一对象与角色的整段关系计数，所有会话加在一起；这是关系级上限，不是这一次会话的上限，因此不在窗口层保存。",
        max_relationship_attempts_24h: "同样按整段关系计数，包含被判定为「沉默」而没有发出的尝试；同样不在窗口层保存。",
        quiet_enabled: "免打扰时段内不会开口，这是全局时段，不区分契机。",
        quiet_start: "24 小时制，形如 23:00；与结束时间相同表示全天免打扰。",
        quiet_end: "可以早于开始时间，表示跨午夜。",
        quiet_timezone: "IANA 时区名，如 Asia/Shanghai；小时活跃曲线也按这个时区对齐。",
        pause_until: "留空表示本层不设暂停，但祖先层更晚的到期时间仍然生效——在窗口层清空只会恢复本层，不会覆盖角色或关系层的暂停。填 UTC 时间点，形如 2026-09-28T12:00:00+00:00。",
        dedup_enabled: "关闭时不再做任何内容去重，重复话题会照常发出。",
        dedup_last_message_enabled: "与角色最后一条回复比对，避免把刚说过的话再说一遍。",
        dedup_last_message_window_minutes: "只回看这段时间内角色的最后一条回复。",
        dedup_sent_window_minutes: "这段时间内发过相同内容的联系不会重发。",
        dedup_weather_window_minutes: "天气问候、天气突变与官方预警共用这条更长的窗口。",
        dedup_min_shared_tokens: "短话题的判定门槛；共享词数不够就判为新话题。",
        dedup_min_overlap_ratio: "较长话题按重叠比例判定；0 表示不看比例，只看共享词数。",
        dedup_policies: "逗号分隔的路线名，只能填 semantic、content_fingerprint、life_event、event_revision、event_anchor、conversation_anchor、daily_slot；写错或重复会被拒绝。",
        silence_min_confidence: "模型给出的把握低于这个门槛时，这次机会记为沉默而不发送；0 表示不设门槛。",
        silence_feedback_penalty: "被忽略或打断后，同类机会的权重按这个幅度下调。",
        enable_llm_proactive_persona_judge: "草稿写完后先由模型复核是否符合人格；复核不通过就丢弃这条草稿。",
        proactive_persona_judge_threshold: "复核分低于该阈值即不通过。",
        proactive_persona_judge_cache_minutes: "相同草稿在这段时间内复用复核结论，避免反复调用模型。",
        proactive_persona_judge_daily_limit: "每天最多复核多少次，超出后按未复核处理。",
        proactive_persona_judge_exempt_purposes: "逗号分隔的契机名，可填 affection、care、play、repair、chat、greeting、life、creation、news、followup、invitation、reminder、environment、meal、screen。",
        ...Object.fromEntries(CONTACT_PURPOSES.map(([, name]) =>
          [name + ".pause_until", "留空表示本层不暂缓；祖先层更晚的到期时间仍然生效。填 UTC 时间点，形如 2026-09-28T12:00:00+00:00。"])),
        enable_daily_greetings: "关闭时三个问候窗口都不再开口。",
        greeting_morning_window: "本地时间 HH:MM-HH:MM，必须当天内结束，不能跨午夜。",
        greeting_noon_window: "本地时间 HH:MM-HH:MM，必须当天内结束，不能跨午夜。",
        greeting_evening_window: "本地时间 HH:MM-HH:MM，必须当天内结束，不能跨午夜。",
        greeting_idle_minutes: "对方刚说过话的这段时间里不问候，避免打断；0 表示不等待。",
        allow_insomnia_night_message: "深夜开口单独受这条总闸控制，默认关闭；它不会绕过免打扰与暂停。",
        insomnia_night_start: "24 小时制，形如 23:00；可以晚于结束时间表示跨午夜，两者相同表示不设深夜窗口。",
        insomnia_night_end: "深夜窗口按每日次数等分，每一份最多开口一次。",
        insomnia_night_daily_limit: "0 表示不在深夜开口。",
        insomnia_require_sleep_state: "开启后只有角色确实处于睡不着的状态（角色状态里的睡眠线索）才会开口。",
        meal_checkin_enabled: "关闭时两个饭点都不再问候。",
        meal_lunch_time: "按免打扰时区解释，24 小时制，形如 12:00。",
        meal_dinner_time: "按免打扰时区解释，24 小时制，形如 18:00。",
        meal_care_followup_minutes: "饭点问候后这段时间内还可以接着关心一句，超出就不再跟进。",
        date_checkin_enabled: "关闭时不再在纪念日问候。",
        date_checkin_time: "按免打扰时区解释，24 小时制，形如 09:00。",
        important_dates: "JSON 数组，每项形如 {\"month\": 5, \"day\": 20, \"label\": \"生日\"}；农历再加 \"calendar\": \"lunar\"（闰月写 \"leap_month\": true）。最多 32 项，形状写错会被拒绝而不是忽略。",
        important_date_lookahead_days: "提前这几天开始留意；0 只在当天问候。",
        weather_checkin_enabled: "按下面的时刻取一次当前天气并问候；需要先在感知页设置角色地点。",
        weather_checkin_time: "按免打扰时区解释，24 小时制，形如 08:30。",
        weather_change_enabled: "在两次采样之间天气变化明显时才有机会开口。",
        weather_sample_minutes: "采样越密越容易发现突变，但也会更频繁地读取天气。",
        official_weather_alert_enabled: "只转发角色地点所属区域的官方预警；需要先在感知页设置角色的预警城市与区域。",
        official_alert_poll_minutes: "轮询间隔；数据源凭据由宿主环境变量提供，没配好时预警源不会就绪。",
        official_alert_min_severity: "低于所选级别的预警不转发；「不限制」表示全部转发。",
        news_share_enabled: "只有来源类型不是搜索或热榜时，这个总闸才决定资讯契机是否开启。",
        news_source_kind: "类型与下面的 UID / 地址必须匹配：B 站动态要 UID，RSS 与 HTTPS JSON 要地址。",
        news_source_uid: "仅在来源类型为 B 站动态时填写，十进制数字。",
        news_source_url: "仅在来源类型为 RSS / Atom 或 HTTPS JSON 时填写，必须是 https 地址。",
        news_check_interval_minutes: "最短检查间隔；网络探索还会额外受它自己的最短间隔约束。",
        news_daily_hot_read_enabled: "来源类型为热榜时，这个总闸决定热榜契机是否开启。",
        news_hot_sources: "逗号分隔，只能填 weibo 或 hackernews，且不能重复；留空会被拒绝。",
        news_hot_result_count: "每次读取热榜取前几条。",
        web_exploration_enabled: "来源类型为搜索时，这个总闸决定探索契机是否开启。",
        web_exploration_interests: "写成一串兴趣词，作为搜索词与筛选参考；不改变任何外部发送。",
        web_exploration_min_interval_hours: "两次探索之间的最短间隔，避免反复抓取同一个主题。",
        web_exploration_result_count: "每次探索最多读取几条结果。",
        external_event_self_link_enabled: "关闭后外部事件不会与角色自己的经历联系起来说。",
        external_event_self_link_weight: "与其它候选竞争时的权重；越大越容易被选中。",
        external_event_self_link_cooldown_hours: "这段时间内不重复做同一种关联。",
        balance_awareness_enabled: "关闭时余额变化不再作为开口理由。",
        balance_include_amount_in_message: "开启后可以把具体金额说进消息里；这里说的是服务经费，不是对方的欠款。",
        balance_currency_label: "金额后面的单位文字，不超过 20 字。",
        balance_low_threshold: "剩余额度低于该值判为「偏低」。",
        balance_critical_threshold: "剩余额度低于该值判为「危险」；与偏低阈值同时生效时取更小的一条。",
        balance_low_percent_threshold: "按剩余比例判断偏低；总额未知时只看绝对值。",
        balance_critical_percent_threshold: "按剩余比例判断危险；与偏低比例同时生效时取更小的一条。",
        balance_check_interval_minutes: "多久读一次余额状态。",
        balance_message_cooldown_hours: "两次余额提醒之间的最短间隔，避免反复提同一件事。",
        screen_glance_enabled: "总闸；关闭时下面三条链路都不起作用。",
        screen_glance_daily_limit: "每天最多主动观察几次；0 表示不观察。",
        screen_glance_cooldown_minutes: "两次观察之间的最短间隔。",
        screen_glance_goodnight_enabled: "晚安之后隔一段时间看一眼对方是否已经休息。",
        screen_glance_goodnight_delay_minutes: "晚安后等待多久再看；太短会显得在盯着。",
        screen_glance_followup_enabled: "说出的话一段时间没有回应时，看一眼再决定要不要补一句。",
        screen_glance_followup_after_minutes: "未回应多久之后才看这一眼。",
        screen_glance_followup_cooldown_minutes: "两次补看之间的最短间隔，避免连续窥屏。",
        voice_action_enabled: "需要语音能力可用；只影响主动发出的语音，不影响回复里的语音。",
        voice_action_max_chars: "语音只念这段长度的文本，超出部分会被截断，空白会合并成空格。",
        voice_action_cooldown_minutes: "两条主动语音之间的最短间隔；0 表示不按间隔限制。",
        poke_action_enabled: "需要平台支持戳一戳；关闭时不使用这个动作。",
        poke_action_daily_limit: "每天最多主动戳几次，按免打扰时区的零点归零；0 表示不使用。",
        poke_action_cooldown_minutes: "两次戳一戳之间的最短间隔；0 表示不按间隔限制。",
        appointment_lead_minutes: "约定开始前多久开口；0 表示到点才说。",
        appointment_lag_minutes: "约定开始后仍可补说的时长；超出后这次机会直接作废，不会翻旧账。",
        appointment_pre_silence_minutes: "约定前的这段时间里不发别的主动消息，避免刚提醒完又被别的话题盖过；0 表示不静默。",
        generation_history_limit: "起草时最多参考几条已经发出的主动消息；0 表示不参考历史。",
        history_max_chars: "这些历史材料的总字数上限，防止挤占本轮上下文。",
        style_prompt: "用你自己的话补充主动开口的风格；留空使用默认。",
      },
      /* 枚举字段在注册表里都是 TEXT，取值合法性由 ContactField / NewsSource 校验；
         选项必须与后端常量一致，否则保存会被拒。 */
      choices: {
        proactive_intensity_preset: {off: "不调整", balanced: "均衡", high_private: "私聊更主动",
                                     high_group: "群聊更主动", live: "高频"},
        news_source_kind: {host: "宿主默认来源", disabled: "停用资讯源", bilibili: "B 站动态",
                           rss: "RSS / Atom", json: "HTTPS JSON", search: "网络搜索",
                           hot: "热榜"},
        official_alert_min_severity: {"": "不限制（全部转发）", minor: "蓝色 · 一般",
                                      moderate: "黄色 · 较重", severe: "橙色 · 严重",
                                      extreme: "红色 · 特别严重"},
      },
      /* 时刻用时间控件（值仍是字符串）；时区、时间点、清单这类短文本声明成单行，
         否则内核按 TEXT 默认画成多行框。 */
      inputs: {
        ...Object.fromEntries(CONTACT_PAUSE_FIELDS.map(name => [name, "line"])),
        quiet_timezone: "line",
        greeting_morning_window: "line", greeting_noon_window: "line", greeting_evening_window: "line",
        news_source_uid: "line", news_source_url: "line", news_hot_sources: "line",
        dedup_policies: "line", proactive_persona_judge_exempt_purposes: "line",
        balance_currency_label: "line",
        quiet_start: "time", quiet_end: "time", meal_lunch_time: "time", meal_dinner_time: "time",
        weather_checkin_time: "time", date_checkin_time: "time",
        insomnia_night_start: "time", insomnia_night_end: "time",
      },
      audit: contactAudit,
      /* 四层链上的值来自安装 / 角色 / 关系三层，默认那句「角色共享」会漏掉
         真正管着这一段关系的那一层。 */
      scopeNote: "安装 / 角色 / 关系共享 · 本会话可覆盖",
      sections: CONTACT_SECTIONS,
      /* order 由段落拼出来：手写一份 158 项的 order 只会与段落声明漂移，
         而漂移的表现是「字段没有控件」或「同一个字段出现两次」，都不报错。 */
      order: CONTACT_SECTIONS.flatMap(section => section.fields),
    },
    /* QQ 空间：角色级的公开动作开关、节流，以及七个主题各自的发布条件。
     *
     * 这一组里**没有凭据字段**，一个都没有：登录态由宿主账号或手动放置的凭据
     * 提供，页面上只能刷新它，不能在这里填。所以这些项回答三件事——角色能不能
     * 在空间里公开动作（总闸 + 三个能力开关）、一轮能做多少（间隔、条数、
     * 每日上限），以及一条说说要满足什么条件才发得出去（主题判定 + 七个主题）。
     * 值按角色共享，与 life / role_growth 同一个口径：窗口层只作为旧值的回落，
     * 卡片右上角那句由内核按继承链写，不需要自己声明 scopeNote。
     *
     * 注册表里这一组是 47 项：9 项全局 + 7 个主题各 5 项。主题那 35 项由下面
     * 两张表拼出来——47 个字段名手写一遍，漏一个不会有任何报错，只会让审计
     * 报「没有控件声明」；场景取值也必须与后端 topics.py 的 TOPIC_SPECS 一致，
     * 多写一个合法的场景 id 会在后端整组校验时被拒（那个场景不属于这个主题）。 */
    qzone: {
      title: "QQ 空间设置",
      note: "决定角色的 QQ 空间能力放不放行公开动作、一轮能做多少，以及发说说前必须确定的主题与场景。关闭总闸时下面几项都不起作用；登录凭据不在这一组里维护。",
      labels: {
        enabled: "启用 QQ 空间",
        like_enabled: "允许点赞",
        comment_enabled: "允许回复",
        publish_enabled: "允许发说说",
        feed_recent_posts: "每次刷空间读取条数",
        comment_recent_posts: "回复前回看自己的说说条数",
        action_min_interval_minutes: "两次同类公开动作最短间隔（分钟）",
        max_actions_per_tick: "单轮公开动作上限",
        publish_max_daily: "每日说说上限",
        topic_auto_enabled: "允许模型自行发布",
        topic_require_confirmation: "主题必须人工确认",
        topic_prompt_guidance: "补充表达指引",
        ...Object.fromEntries(QZONE_TOPIC_SECTIONS.flatMap(({prefix, title}) => [
          [prefix + "_enabled", title + " · 启用"],
          [prefix + "_scenes", title + " · 允许的场景"],
          [prefix + "_min_confidence", title + " · 置信度门槛"],
          [prefix + "_daily_max", title + " · 每日上限"],
          [prefix + "_cooldown_minutes", title + " · 最短间隔（分钟）"],
        ])),
      },
      helps: {
        enabled: "关闭后不再发任何空间请求，也不再为它花模型额度；页面上手动刷空间同样会被挡。",
        like_enabled: "关闭时点赞按钮不可用；已经点过赞的动态不受影响。",
        comment_enabled: "关闭时回复框不可用。回复是公开动作，未确认的结果不会自动重发。",
        publish_enabled: "关闭时不能发说说。发布同样是公开动作，还要受下面的间隔、每日上限与主题条件约束。",
        feed_recent_posts: "刷空间一次最多读多少条，好友动态与我的动态都在这个范围内，1 到 30。",
        comment_recent_posts: "回复前回看自己最近几条说说，用来判断上下文，1 到 20。",
        action_min_interval_minutes: "点赞、回复、发说说共用这一条间隔，5 到 1440 分钟；调小只是允许更频繁，不代表会真的更频繁。",
        max_actions_per_tick: "一轮里最多做几个公开动作，1 到 5。调大不会放宽间隔，也不会放宽每日上限。",
        publish_max_daily: "每天最多发几条说说，1 到 10；达到上限后当天不再发。",
        topic_auto_enabled: "开启后才允许模型在无需人工确认的情况下自行发布；默认关闭，关着时模型提出的主题必须有人确认。",
        topic_require_confirmation: "开启时模型提出的主题必须有人确认才能发布；默认开启，只有上面那项打开且这一项关闭，模型才可能不经过确认就发。",
        topic_prompt_guidance: "给模型的补充表达指引（例如口吻、篇幅、不要写什么）；只影响怎么写，不改主题目录、场景放行与任何授权。",
        ...Object.fromEntries(QZONE_TOPIC_SECTIONS.flatMap(({prefix, title, scenes}) => [
          [prefix + "_enabled", "关闭后这个主题的说说一律不发，模型提出的该主题会被拒；不影响其他主题。"],
          [prefix + "_scenes", `这个主题允许出现在哪些场景，用半角逗号分隔，只能填该主题自己的场景：${qzoneSceneWords(scenes)}。留空、重复或写了别的场景会被后端拒绝；多个场景之间没有优先级。`],
          [prefix + "_min_confidence", "主题判定置信度门槛，0 到 1 之间的小数；低于它就不发这一条。「发说说」里由人手动选择的主题按 1 处理。"],
          [prefix + "_daily_max", "这个主题每天最多发几条，0 到 10；0 表示这个主题今天一条都不发。与「每日说说上限」同时生效时，先撞到哪条算哪条。"],
          [prefix + "_cooldown_minutes", "这个主题两次发布之间的最短间隔，0 到 1440 分钟；0 表示不按主题单独限制间隔。"],
        ])),
      },
      order: QZONE_SECTIONS.flatMap(section => section.fields),
      /* 段落就是这条链：先看能不能公开动作，再看一轮做多少，然后看主题怎么判定，
         最后是七个主题各自的发布条件。总闸关着时后面几段调成什么都不起作用，
         所以第一段的 help 点明这一点。 */
      sections: QZONE_SECTIONS,
      /* 注册表把 {id}_scenes 当普通 TEXT，但它只能填该主题自己的场景 id。
         写错一个（例如给生活纪实类填了 free_expression）后端会拒掉整组保存，
         却只说一句「设置不合法」，所以在页面先按主题目录查一遍。 */
      audit: qzoneAudit,
    },
  };

  /* 跨字段/跨字段类型的校验：注册表只给 kind 与数值范围，
     HH:MM 时刻与 IANA 时区的形状得由页面兜住，否则值会走到后端才被拒。
     内核期望返回单个错误码字符串（不是数组）。 */
  const CLOCK=/^([01]\d|2[0-3]):[0-5]\d$/;
  const isZone=value=>{ try { new Intl.DateTimeFormat("zh-CN",{timeZone:String(value)}).format(); return true; } catch { return false; } };
  function lifeAudit(values) {
    for (const name of ["diary_time","sleep_time"])
      if (typeof values[name]==="string" && !CLOCK.test(values[name])) return "life_clock_invalid";
    for (const name of ["timezone","sleep_timezone"])
      if (typeof values[name]==="string" && !isZone(values[name])) return "life_timezone_invalid";
    return null;
  }

  /* 主动联系偏好里注册表管不住的形状更多：时刻、问候窗口、时区、暂停时间点、
     24 小时曲线与三个逗号清单。后端拒绝时只回一个 invalid_contact_preference，
     说不出是哪一项错，所以在页面就把明显不合法的值拦下来。
     这里的判定与 ContactField.validate 对齐，只有曲线一项比后端更严——
     后端在数量不是 24 时会静默换成默认曲线，静默改写比拒绝更难发现。 */
  function contactAudit(values) {
    for (const name of CONTACT_CLOCKS)
      if (typeof values[name]==="string" && !CLOCK.test(values[name]))
        return "proactive_contact_clock_invalid";
    for (const name of CONTACT_WINDOWS) {
      const value = values[name];
      if (typeof value!=="string") continue;
      const [start, end] = value.split("-");
      if (!CLOCK.test(start||"") || !CLOCK.test(end||"") || !(start < end))
        return "proactive_contact_window_invalid";
    }
    if (typeof values.quiet_timezone==="string" && !isZone(values.quiet_timezone))
      return "proactive_contact_timezone_invalid";
    for (const name of CONTACT_PAUSE_FIELDS) {
      const value = values[name];
      if (typeof value!=="string" || !value) continue;
      if (!CONTACT_INSTANT.test(value) || !Number.isFinite(Date.parse(value)))
        return "proactive_contact_pause_invalid";
    }
    if (typeof values.proactive_hour_activity_curve==="string") {
      const parts = values.proactive_hour_activity_curve.replace(/，/g, ",").split(",").map(part => part.trim());
      if (parts.length!==24 || parts.some(part => part==="" || !Number.isFinite(Number(part))))
        return "proactive_contact_curve_invalid";
    }
    if (typeof values.dedup_policies==="string") {
      const routes = contactWords(values.dedup_policies, /[,，;；\s]+/);
      if (new Set(routes).size!==routes.length || routes.some(route => !CONTACT_DEDUP_ROUTES.includes(route)))
        return "proactive_contact_list_invalid";
    }
    if (typeof values.news_hot_sources==="string") {
      /* 后端只按半角逗号切分，所以这里也不能把顿号当分隔符。 */
      const sources = contactWords(values.news_hot_sources, ",");
      if (!sources.length || new Set(sources).size!==sources.length
          || sources.some(source => !CONTACT_HOT_SOURCES.includes(source)))
        return "proactive_contact_list_invalid";
    }
    if (typeof values.proactive_persona_judge_exempt_purposes==="string") {
      const purposes = contactWords(values.proactive_persona_judge_exempt_purposes, /[,，;；\s]+/);
      const known = CONTACT_PURPOSES.map(([, name]) => name);
      if (new Set(purposes).size!==purposes.length || purposes.some(purpose => !known.includes(purpose)))
        return "proactive_contact_list_invalid";
    }
    if (typeof values.important_dates==="string") {
      try {
        const rows = JSON.parse(values.important_dates || "[]");
        if (!Array.isArray(rows) || rows.length > 32) return "proactive_contact_dates_invalid";
      } catch { return "proactive_contact_dates_invalid"; }
    }
    const kind = values.news_source_kind;
    if (typeof kind==="string" && !CONTACT_SOURCE_KINDS.includes(kind))
      return "proactive_contact_source_invalid";
    /* 类型与 UID / 地址不匹配时后端在整组校验里就会失败，先说清楚是哪一项。 */
    if (kind==="bilibili" && !/^[1-9][0-9]{0,19}$/.test(String(values.news_source_uid||"")))
      return "proactive_contact_source_invalid";
    if ((kind==="rss" || kind==="json") && !/^https:\/\/\S+$/i.test(String(values.news_source_url||"")))
      return "proactive_contact_source_invalid";
    return null;
  }

  const errors = {
    configuration_revision_conflict: "配置已经更新。草稿已保留，读取新版本后再核对。",
    invalid_configuration_value: "请核对数值类型与范围。",
    invalid_probability: "请填写 0 到 1 之间的小数。",
    invalid_precision: "数值精度超出允许范围。",
    invalid_weight: "该权重需为正数。",
    configuration_request_invalid: "请求格式有误，请刷新后重试。",
    busy_gate_settings_invalid: "繁忙闸门的关键词需要是短词，且每一项不超过 64 个。",
    qzone_scene_list_invalid: "QQ 空间主题的场景清单只能用半角逗号分隔、不能重复，且只能填该主题自己的场景；请对照该主题段落说明里的可选值。",
    image_quota_scope_invalid: "额度按安装与角色生效，请选择一个已初始化的私聊对象。",
    image_quota_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    image_review_scope_invalid: "群图审核按会话生效，请选择一个已初始化的私聊对象。",
    image_review_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    reaction_configuration_scope_invalid: "表情检索按会话生效，请选择一个已初始化的私聊对象。",
    reaction_configuration_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    busy_gate_scope_invalid: "繁忙闸门按会话生效，请选择一个已初始化的私聊对象。",
    busy_gate_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    model_budget_scope_invalid: "预算按安装与角色生效，请选择一个已初始化的私聊对象。",
    model_budget_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    recall_scope_invalid: "撤回原文转写按会话生效，请选择一个已初始化的私聊对象。",
    recall_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    recall_configuration_invalid: "请核对转写条数、字数与时间窗的取值范围。",
    screen_scope_invalid: "屏幕解读按会话生效，请选择一个已初始化的私聊对象。",
    screen_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    screen_configuration_invalid: "请核对开关与素材字数上限。",
    person_scope_invalid: "熟人卡按对象生效，请选择一个已初始化的私聊对象。",
    person_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    role_growth_scope_invalid: "成长与技能按会话生效，请选择一个已初始化的私聊对象。",
    role_growth_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    growth_target_changed: "当前对象或角色绑定已变化，请重新读取后再保存。",
    library_scope_invalid: "书架按角色生效，请选择一个已初始化的私聊对象。",
    library_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    library_configuration_invalid: "请核对开关与两项数量上限的取值范围。",
    reference_scope_invalid: "参考图按角色生效，请选择一个已初始化的私聊对象。",
    reference_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    photo_reference_configuration_invalid: "请核对两个开关与轮换天数（1 到 365）的取值范围。",
    wardrobe_scope_invalid: "衣柜按角色生效，请选择一个已初始化的私聊对象。",
    wardrobe_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    wardrobe_configuration_invalid: "请核对开关、两处文字（各不超过 800 字）与两项数量上限的取值范围。",
    knowledge_scope_invalid: "知识库按会话生效，请选择一个已初始化的私聊对象。",
    knowledge_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    knowledge_settings_invalid: "知识库设置不合法：单轮的引用字符上限不能小于单条素材的字数上限。",
    role_life_scope_invalid: "日记与梦境按会话生效，请选择一个已初始化的私聊对象。",
    role_life_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    rest_gate_settings_invalid: "休息判定设置不合法：判定方式只能选概率或模型，时段格式形如 23:00-08:30。",
    life_timezone_invalid: "请填写有效的 IANA 时区，例如 Asia/Shanghai。",
    life_clock_invalid: "请填写二十四小时制的时刻，形如 23:50 或 00:30。",
    group_participation_scope_invalid: "群聊参与按会话生效，请选择一个已初始化的私聊对象。",
    group_participation_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    group_participation_configuration_invalid: "请核对群聊参与设置：概率需在 0 到 1 之间，数字项需在各自范围内；打断语只能是一行、不超过 80 字。",
    /* 主动联系偏好：两个关系级额度按窗口写入会被后端拒绝，这条文案要说明去哪儿改。 */
    proactive_contact_scope_invalid: "主动联系偏好按会话生效，请选择一个已初始化的私聊对象。",
    proactive_contact_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    proactive_contact_configuration_invalid: "请核对主动联系设置：数值需在各自范围内，枚举项需在下拉选项内。",
    contact_relationship_budget_scope: "关系级配额（同一关系 24 小时内的联系与尝试上限）按安装 / 角色 / 关系层设置，不能按会话保存。",
    configuration_relationship_required: "主动联系偏好需要一个已绑定的角色和这个会话的真人关系；请先完成对象与角色的绑定。",
    invalid_contact_preference: "主动联系设置有字段不合法：时刻用 HH:MM，问候窗口用 HH:MM-HH:MM，时区用 IANA 名称，暂停时间点用带时区的 ISO 时间，活跃曲线写满 24 个数字，清单只能填允许的名字，重要日期要是 JSON 数组。",
    proactive_contact_clock_invalid: "请填写二十四小时制的时刻，形如 23:00 或 07:45。",
    proactive_contact_window_invalid: "问候窗口形如 07:45-10:20，且必须当天内结束，不能跨午夜。",
    proactive_contact_timezone_invalid: "请填写有效的 IANA 时区，例如 Asia/Shanghai。",
    proactive_contact_pause_invalid: "暂停时间点要带时区，形如 2026-09-28T12:00:00+00:00；留空表示本层不设暂停。",
    proactive_contact_curve_invalid: "活跃曲线必须写满 24 个 0.05 到 2.00 之间的数字，用逗号分隔。",
    proactive_contact_list_invalid: "清单里只能填允许的名字，用逗号分隔且不能重复；热榜来源只接受 weibo 与 hackernews。",
    proactive_contact_dates_invalid: "重要日期要写成 JSON 数组，最多 32 项。",
    proactive_contact_source_invalid: "资讯来源类型与 UID / 地址不匹配：B 站动态要十进制 UID，RSS 与 HTTPS JSON 要 https 地址。",
    dashboard_identity_required: "请从已登录的 AstrBot 管理界面打开小屋。",
    core_access_required: "当前账号没有管理权限。",
    staging_not_initialized: "请先在账号与会话中加载 V2 运行实例。",
    staging_host_terminated: "宿主已停止，请重新进入插件。",
    bridge_timeout: "连接超时，请核对连接后重试。",
    invalid_response: "返回数据不完整，请刷新核对。",
  };

  /* 配置接口地址取自 page/targets 下发的 config_api；
     回退到按 reply_api 推导，保证未升级的宿主目录仍可用。
   *
   * **必须判空**：`window.CompanionProduct` 是宿主注入后才有的一层，
   * 而它注入得比页面脚本晚（正常时序，不是异常）。原先这里直接读
   * `product.role()`，注入未完成时抛 TypeError——而调用它的
   * mountPanelWorkspaces() 是在 paintPanel() 里同步、无 try/catch 调的，
   * 一次抛错会让**整条面板挂载链**中断：这一页的配置分区没有，后面所有
   * 工作区也全都不会挂上。用户看到的就是「这些页面完全无法使用」。
   * 读不到就返回 null，由调用方渲染等待态，而不是把整页一起带走。 */
  function endpointFor(product) {
    if (!product || typeof product.role !== "function") return null;
    const fromManifest = product.role()?.config_api;
    if (typeof fromManifest === "string" && fromManifest.startsWith(PREFIX)) return fromManifest;
    const reply = product.role()?.reply_api;
    if (typeof reply === "string" && reply.startsWith(PREFIX) && reply.endsWith("/reply")) {
      return reply.slice(0, -"/reply".length) + "/config";
    }
    return null;
  }

  /* 一个挂载点承载多个分区；每个分区各持一个工作台实例，
     草稿互不共享，与后端「每分区独立 edit_token」的生效范围保持一致。 */
  function create(kinds, rootProvider, views = {}) {
    const product = window.CompanionProduct;
    const endpoint = endpointFor(product);
    const names = (kinds || []).filter(kind => Object.hasOwn(spec, kind));
    if (!names.length || !endpoint) return null;
    if (!window.CompanionWorkbench?.create) return null;

    const instances = names.map(kind => {
      const base = spec[kind];
      const view = views?.[kind];
      let current = base;
      if (Array.isArray(view?.sectionIds)) {
        const selected = new Set(view.sectionIds);
        const sections = (base.sections || []).filter(section => selected.has(section.id));
        if (!sections.length) return null;
        current = {...base, title:view.title || base.title, note:view.note ?? base.note,
          sections, order:sections.flatMap(section => section.fields || [])};
      }
      return window.CompanionWorkbench.create({
      group: kind,
      title: current.title,
      note: current.note || (kind === "quota" ? "−1 不限 · 0 禁止 · 按会话时区每日归零" : ""),
      labels: current.labels,
      helps: current.helps,
      /* 枚举选项必须转交内核：注册表里这些字段是 TEXT，
         取值合法性只有内核的 valid() 知道，漏传就会被当成任意文本放过。 */
      choices: current.choices || {},
      order: current.order,
      /* 卡片右上角的生效范围文案默认由内核按继承链推断；四层组（主动联系偏好，
         链里多一层关系）必须自己声明，否则会被说成「角色共享」而漏掉关系层。 */
      scopeNote: current.scopeNote || "",
      /* 段落声明同样必须转交：漏传时内核退回单段渲染，分组与依赖说明
         会被静默丢掉——看起来一切正常，只是少了几段。 */
      sections: current.sections || null,
      /* time 控件（值仍是字符串）与跨字段校验同样要转交内核。 */
      inputs: current.inputs || {},
      audit: current.audit || null,
      onStatus: current.onStatus || null,
      endpoint,
      /* 每分区各读一次：后端按 sections 过滤，避免一个分区解析失败牵连另一个。 */
      query: {sections: kind},
      mount: () => {
        const root = rootProvider();
        return root ? root.querySelector(`[data-config-host="${kind}"]`) : null;
      },
      });
    }).filter(Boolean);
    if (!instances.length) return null;

    return {
      /* 草稿由工作台自行从 sessionStorage 恢复。 */
      restore() {},
      paint() {
        const root = rootProvider();
        if (!root) return;
        root.classList.add("config-editors");
        root.textContent = "";
        for (const kind of names) {
          const holder = document.createElement("div");
          holder.dataset.configHost = kind;
          root.appendChild(holder);
        }
        for (const instance of instances) instance.mount();
      },
      read() { for (const instance of instances) void instance.refresh(); },
      stop() { for (const instance of instances) instance.stop(); },
      start() { for (const instance of instances) instance.start(); },
      get state() { return {instances}; },
    };
  }

  return {create, spec, errors, endpointFor};
})();
