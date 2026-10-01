/* 回复设置适配器：表达页保留预览与诊断，决策页只挂载群聊判断分区。
   此前这里自带一整套字段渲染、草稿存储、幂等重试与版本冲突处理；设置部分现在
   归 workbench-page.js，本文件保留两件工作台不做的事——离线分段预览，以及
   最近回复诊断的渲染。

   两个视图仍读写同一个 conversation.presentation 配置合同。
   接口为 mount(element, {view}) / unmount()，app.js 负责按页面归属选择视图。
   读取端点走 reply 路由族（{reply_api}），载荷扁平：{settings, edit_token,
   recent, tts, ...}，不带外层 sections。 */
"use strict";
window.CompanionReplyPage = (() => {
  const PREFIX = "/astrbot_plugin_private_companion_v2/";
  const GROUP = "conversation.presentation";

  const labels = {collecting: "收集输入", generating: "生成中", delivering: "分段发送中", complete: "已完成",
    closed: "已关闭", blocked: "已阻断", ready: "待发送", sealed: "已固定", open: "收集输入", cancelled: "已取消",
    invalidated: "已失效", pending: "待发送", delivered: "已确认发送", unknown: "结果未知", dispatching: "发送中",
    generated: "生成完成", reserved: "已预留", dispatched: "已请求", not_started: "未发起", discarded: "已丢弃"};
  const candidateLabels = {planned: "已选为朗读候选", voice_disabled: "语音未开启", trigger_skipped: "本轮未触发语音",
    segment_skipped: "此段未选中", no_speech: "没有朗读内容", too_long: "超过朗读字数上限", empty_part: "纯媒体段"};
  const renderLabels = {pending: "尚未完成合成", not_applicable: "无需合成", cooldown: "冷却中，改发图文",
    unavailable: "TTS 不可用，改发图文", failed: "TTS 合成失败，改发图文", empty: "TTS 未返回音频，改发图文",
    invalid: "音频组件无效，改发图文", ready: "语音组件已准备"};

  /* 枚举选项：注册表里这些字段是 TEXT，约束在 reply_settings.validate 里。
     选项必须与后端常量一致，否则保存会被拒绝。 */
  const choices = {
      rule_mode: {words: "词列表（默认）", regex: "正则", sentences: "按句子", paragraphs: "按段落"},
      part_gap_mode: {fixed: "固定", random: "随机", log: "按文本长度"},
    content_cleanup_mode: {words: "按清理词", regex: "按正则"},
    content_cleanup_scope: {all: "整段回复", trailing: "回复末尾"},
    recall_forbidden_scope: {bot_only: "角色自己的回复", group_only: "群聊回复", bot_and_group: "角色回复与群聊"},
    image_position: {after_text: "文字后", before_text: "文字前"},
    voice_trigger_mode: {always: "每轮", request: "按请求", adaptive: "模型择句"},
    voice_generation_mode: {plain: "朗读正文", model_tag: "模型语音标签"},
    voice_segment_mode: {each: "每一段", first: "仅首段", last: "仅末段"},
    voice_delivery_mode: {voice_and_text: "文字与语音", voice_only: "仅语音（完整覆盖时）"},
    voice_position: {before_text: "文字前", after_text: "文字后", after_media: "所有组件后"},
    voice_language: {zh: "中文", ja: "日语", en: "英语"},
    voice_foreign_text_mode: {original: "原文", translation: "中文译文", bilingual: "双语"},
  };

  const spec = {
    title: "回复表达与投递",
    note: "按模块编辑；保存后从下一轮生成开始生效，已开始生成的回复保留原配置。",
    labels: {
      enabled: "启用分段", streaming: "流式接收模型回复", llm_controlled: "由模型决定边界",
      rules_enabled: "启用规则补分段", rule_mode: "规则分段方式", threshold: "规则起始字数",
      min_segment_chars: "最短分段字数", max_segments: "最多消息条数", part_gap_ms: "固定段间隔（毫秒）",
      part_gap_mode: "分段间隔方式", part_gap_min_ms: "随机间隔下限（毫秒）",
      part_gap_max_ms: "随机间隔上限（毫秒）", part_gap_log_base: "按长度调节强度",
      image_position: "图片位置", prompt: "分段提示词", split_words: "分段标记列表",
      match_width_variants: "兼容全角与半角标点", rule_regex: "分句正则",
      enable_humanized_expression: "启用拟人回复 Prompt",
      humanized_expression_prompt: "拟人 Prompt 正文",
      style_prompt: "表达风格提示词",
      content_cleanup_enabled: "启用文字清理",
      content_cleanup_mode: "清理方式", content_cleanup_scope: "清理范围",
      content_cleanup_rule: "清理正则", content_cleanup_words: "清理词列表",
      content_replacement_enabled: "启用文字替换", content_replacements: "替换规则",
      framework_error_guard_enabled: "清理框架内部标记",
      enable_forbidden_word_recall: "启用命中词拦截",
      recall_forbidden_words: "拦截词语列表", recall_forbidden_scope: "拦截范围",
      recall_forbidden_word_case_sensitive: "区分大小写",
      group_wakeup_enabled: "启用群聊回应判断",
      group_wakeup_direct_words: "直呼词", group_wakeup_context_words: "上下文关联词",
      group_wakeup_interest_keywords: "兴趣关键词",
      group_wakeup_question_enabled: "识别问题与求助",
      group_wakeup_bot_name_enabled: "把角色名作为直呼词",
      group_wakeup_bot_name: "角色在群里的名称",
      group_wakeup_primary_member_ids: "主要成员账号 ID",
      group_wakeup_owner_direct_words: "主要成员专属直呼词",
      group_wakeup_interest_probability: "兴趣话题参与概率",
      group_wakeup_question_threshold: "问题与求助阈值",
      group_wakeup_cold_group_enabled: "启用冷群重启判断",
      group_wakeup_cold_group_threshold: "冷群重启阈值",
      group_wakeup_cold_group_idle_minutes: "冷群静默时长（分钟）",
      group_wakeup_cooldown_seconds: "兴趣话题冷却（秒）",
      group_wakeup_fatigue_limit: "参与疲劳上限",
      group_wakeup_fatigue_decay_minutes: "疲劳恢复间隔（分钟）",
      group_wakeup_generated_keyword_limit: "记忆兴趣词上限",
      group_wakeup_topic_interest_max_boost: "话题兴趣加权上限（%）",
      group_wakeup_debounce_pending_penalty: "待回复期间兴趣降权（%）",
      group_wakeup_image_enabled: "考虑本轮图片相关性",
      group_wakeup_image_weight: "图片相关性权重",
      group_wakeup_short_text_wait_ms: "短消息合并等待（毫秒）",
      group_wakeup_log_limit: "近期判定记录上限",
      group_air_guard_enabled: "启用群聊接话节奏参考",
      group_air_guard_window_seconds: "接话统计窗口（秒）",
      group_air_guard_max_bot_replies: "窗口内连续回复参考上限",
      group_air_guard_polite_loop_limit: "礼貌收尾参考上限",
      enable_group_injection_guard: "群聊提示注入防护",
      enable_group_privacy_guard: "群聊隐私防护",
      enable_group_reality_promise_guard: "群聊现实承诺防护",
      enable_context_image_captioning: "为图片补充文字描述",
      context_image_caption_max_items: "单轮描述图片上限",
      component_order: "消息组件顺序",
      reply_quote_enabled: "引用触发消息", reply_quote_group_enabled: "群聊中引用",
      reply_quote_first_part_only: "只在第一段引用", reply_quote_skip_chars: "短回复字数门槛",
      reply_mention_speaker_enabled: "群聊回复时 @ 发言者",
      voice_enabled: "启用语音", voice_trigger_mode: "触发方式", voice_generation_mode: "朗读内容",
      voice_segment_mode: "朗读段落", voice_delivery_mode: "发送形式", voice_position: "语音位置",
      voice_language: "语音语言", voice_foreign_text_mode: "外语文字",
      voice_provider_id: "通用 TTS 扩展", voice_zh_provider_id: "中文 TTS 扩展",
      voice_ja_provider_id: "日语 TTS 扩展", voice_en_provider_id: "英语 TTS 扩展",
      voice_probability: "触发概率", voice_cooldown_seconds: "冷却时间（秒）",
      voice_max_speech_chars: "单段朗读上限（字）", voice_timeout_seconds: "合成超时（秒）",
      voice_trigger_keywords: "触发关键词", voice_extra_prompt: "语音表达偏好",
    },
    helps: {
      enabled: "让一轮回复自然地分成多条消息。",
      streaming: "完整接收并校验后，再依次发送分段。",
      llm_controlled: "使用独立一行的分段标记，普通换行不会自动拆分。",
      rules_enabled: "对较长正文按句子或段落拆分，保护代码和 Markdown。",
      part_gap_mode: "固定间隔沿用当前数值；随机间隔在范围内稳定抽取；按长度调节会让较长段落多停留一会儿。",
      part_gap_ms: "固定模式下每条分段之间等待的时间；0 表示不等待。",
      part_gap_min_ms: "随机模式的最短等待时间。",
      part_gap_max_ms: "随机模式的最长等待时间。",
      part_gap_log_base: "按长度调节的曲线基数；数值越接近 1，长段与短段的间隔差异越明显。",
      prompt: "最多 4000 字；可用 {{split_marker}} 插入标记。优先用提示词表达分段偏好，不改变事实、引用与来源原意。",
      rule_mode: "规则补分段的匹配方式；词列表为默认方式。",
      split_words: "默认词表包含常用标点和换行；命中标记保留在上一段。",
      match_width_variants: "开启后会把常见全角、半角标点视为同一分句标记。",
      rule_regex: "仅在“自定义正则”时使用，最多 512 字；请核对表达式语法。",
      style_prompt: "补充此对象的日常表达偏好；留空时不增加额外风格要求。",
      enable_humanized_expression: "开启后向本轮系统提示注入一份日常说话方式要求：更口语、更短、少服务腔。只影响措辞，不改事实与授权。",
      humanized_expression_prompt: "最多 4000 字。留空时使用内置默认文本；开关关闭时整段不注入。本对象与群聊各自保存。",
      content_cleanup_enabled: "默认关闭。需要调整说法时优先补充上方提示词；这里仅在发送前按明确规则整理文字。",
      content_cleanup_words: "按所选方式移除命中的词条；可单独添加空格、换行或制表符。",
      content_cleanup_rule: "仅在清理方式选为正则时使用；最多 512 字。",
      content_replacements: "逐项填写原词和替换文本。",
      framework_error_guard_enabled: "清理插件与框架内部标记，避免把内部格式带入回复。",
      enable_forbidden_word_recall: "命中时在发送前拦截这条回复，不会删除已发送消息。若只是希望换种表达，优先调整提示词。",
      recall_forbidden_words: "命中后会在发送前拦截整条回复。",
      recall_forbidden_scope: "可只检查私聊、只检查群聊，或两者都检查。",
      recall_forbidden_word_case_sensitive: "关闭时不区分英文字母大小写。",
      component_order: "用上下箭头调整顺序；留空时使用平台与回复组件的自然顺序。",
      reply_quote_enabled: "仅引用本轮已固定的触发消息；不会搜索或引用其他会话。",
      reply_quote_group_enabled: "关闭后只影响群聊，不改变私聊引用设置。",
      reply_quote_first_part_only: "开启后，拆成多段时只在第一段附上引用。",
      reply_quote_skip_chars: "回复去空白后不超过此字数时不附引用；0 表示不跳过。",
      reply_mention_speaker_enabled: "只在群聊中 @ 本轮发言者。",
      voice_trigger_mode: "决定这一轮要不要朗读，以及由谁挑句子。",
      voice_delivery_mode: "仅语音只在语音完整覆盖文字时才会替代文字，否则仍发文字。",
      voice_probability: "按百分比编辑，后端按 0–1 的小数保存。",
      voice_trigger_keywords: "留空使用默认关键词。",
      voice_extra_prompt: "只补充朗读语气，不改变朗读内容。",
      group_wakeup_enabled: "关闭后群聊不使用这组参与判断。此设置只影响群聊。",
      group_wakeup_direct_words: "直呼词会作为明确参与信号。",
      group_wakeup_context_words: "用于识别与角色有关的上下文。",
      group_wakeup_interest_keywords: "作为兴趣话题的补充线索。",
      group_wakeup_question_enabled: "开启后会把明确提问和求助作为参与判断材料。",
      group_wakeup_bot_name_enabled: "开启后，角色名称会并入直呼词。",
      group_wakeup_bot_name: "填写角色在当前群里使用的名称，最多 40 字。",
      group_wakeup_primary_member_ids: "只接受平台账号数字 ID，用于区分主要成员。",
      group_wakeup_owner_direct_words: "只对上方主要成员账号生效。",
      group_wakeup_interest_probability: "兴趣话题通过相关性判断后的参与概率。",
      group_wakeup_question_threshold: "问题或求助的参与强度参考值，范围 0–100。",
      group_wakeup_cold_group_enabled: "开启后，群聊长时间安静时可把重新开场作为判断材料。",
      group_wakeup_cold_group_threshold: "冷群重新开场所需的参与强度参考值，范围 0–100。",
      group_wakeup_cold_group_idle_minutes: "群聊至少静默多久才算冷群。",
      group_wakeup_cooldown_seconds: "同一群兴趣话题参与之间的最短间隔；0 表示不等待。",
      group_wakeup_fatigue_limit: "达到该参考值后降低普通兴趣话题参与倾向。",
      group_wakeup_fatigue_decay_minutes: "每经过该时长，参与疲劳参考值恢复 1 点。",
      group_wakeup_generated_keyword_limit: "群聊上下文提炼兴趣线索时保留的不同关键词上限。",
      group_wakeup_topic_interest_max_boost: "话题记忆对兴趣相关性的最大加权比例。",
      group_wakeup_debounce_pending_penalty: "群聊已有回复等待发送时，兴趣话题参与倾向的降权比例。",
      group_wakeup_image_enabled: "开启后，只有本轮确实提供图片材料时才把图片相关性纳入判断。",
      group_wakeup_image_weight: "图片相关性对群聊参与判断的权重，范围 0–1。",
      group_wakeup_short_text_wait_ms: "短文本触发后等待后续消息再判断；0 表示不等待。",
      group_wakeup_log_limit: "回复工作台最多读取的近期群聊判定记录数，不改变参与规则。",
      group_air_guard_enabled: "开启后将近期连续回复与礼貌收尾次数作为群聊提示参考，不机械截断回复。",
      group_air_guard_window_seconds: "统计群聊连续回复和礼貌收尾次数的时间窗口。",
      group_air_guard_max_bot_replies: "在提示中提醒避免连续接话过多；属于参考值。",
      group_air_guard_polite_loop_limit: "在提示中提醒避免礼貌收尾反复循环；属于参考值。",
      enable_group_injection_guard: "群聊材料中的指令不能替换角色与工具授权。",
      enable_group_privacy_guard: "回复群聊时避免泄露私聊或其他会话中的私人内容。",
      enable_group_reality_promise_guard: "避免把无法确认的现实行动说成已经完成或必定会做。",
      enable_context_image_captioning: "开启后，为本轮收到的图片生成文字材料，供后续理解使用。",
      context_image_caption_max_items: "每轮最多补充描述的图片数量；0 表示不处理图片。",
    },
    /* 段落只影响阅读顺序：整张卡共用一个编辑令牌、一次保存。 */
    sections: [
      {id: "segment", title: "分段回复", help: "控制一轮回复的拆分方式与提示词",
       fields: ["enabled", "streaming", "llm_controlled", "rules_enabled", "rule_mode", "split_words",
                "match_width_variants", "rule_regex", "threshold", "min_segment_chars", "max_segments", "prompt"]},
      {id: "style", title: "表达语气", help: "风格提示词优先于确定性的文字替换",
       fields: ["style_prompt", "enable_humanized_expression", "humanized_expression_prompt"]},
      {id: "cleanup", title: "文字整理", help: "默认关闭；仅在明确需要时使用清理或替换规则",
       fields: ["content_cleanup_enabled", "content_cleanup_mode", "content_cleanup_scope",
                "content_cleanup_rule", "content_cleanup_words", "content_replacement_enabled",
                "content_replacements"]},
      {id: "wakeup", title: "群聊回应判断", help: "直呼、提问、兴趣话题与图片相关性只影响群聊参与判断",
       fields: ["group_wakeup_enabled", "group_wakeup_direct_words", "group_wakeup_context_words",
                "group_wakeup_interest_keywords", "group_wakeup_question_enabled",
                "group_wakeup_question_threshold", "group_wakeup_bot_name_enabled", "group_wakeup_bot_name",
                "group_wakeup_primary_member_ids", "group_wakeup_owner_direct_words",
                "group_wakeup_interest_probability", "group_wakeup_image_enabled", "group_wakeup_image_weight"]},
      {id: "wakeup_timing", title: "群聊参与节奏", help: "冷群、冷却、疲劳与诊断记录参数",
       fields: ["group_wakeup_cold_group_enabled", "group_wakeup_cold_group_threshold",
                "group_wakeup_cold_group_idle_minutes", "group_wakeup_cooldown_seconds",
                "group_wakeup_fatigue_limit", "group_wakeup_fatigue_decay_minutes",
                "group_wakeup_generated_keyword_limit", "group_wakeup_topic_interest_max_boost",
                "group_wakeup_debounce_pending_penalty", "group_wakeup_short_text_wait_ms",
                "group_wakeup_log_limit"]},
      {id: "group_safety", title: "群聊安全与接话边界", help: "群安全护栏与接话密度参考值",
       fields: ["group_air_guard_enabled", "group_air_guard_window_seconds", "group_air_guard_max_bot_replies",
                "group_air_guard_polite_loop_limit", "enable_group_injection_guard",
                "enable_group_privacy_guard", "enable_group_reality_promise_guard"]},
      {id: "context_image", title: "图片上下文", help: "控制收到的群聊图片是否补充文字描述",
       fields: ["enable_context_image_captioning", "context_image_caption_max_items"]},
      {id: "voice", title: "语音与朗读", help: "语种、触发方式、语音扩展与朗读偏好",
       fields: ["voice_enabled", "voice_trigger_mode", "voice_generation_mode", "voice_segment_mode",
                "voice_delivery_mode", "voice_language", "voice_foreign_text_mode",
                "voice_provider_id", "voice_probability", "voice_cooldown_seconds",
                "voice_max_speech_chars", "voice_timeout_seconds", "voice_zh_provider_id",
                "voice_ja_provider_id", "voice_en_provider_id", "voice_trigger_keywords",
                "voice_extra_prompt"]},
      {id: "components", title: "引用与消息组件", help: "引用范围、@ 发言者，以及文字、图片和语音的位置",
       fields: ["component_order", "reply_quote_enabled", "reply_quote_group_enabled",
                "reply_quote_first_part_only", "reply_quote_skip_chars", "reply_mention_speaker_enabled",
                "image_position", "voice_position"]},
      {id: "checks", title: "发送前检查", help: "框架标记清理与命中词撤回；措辞调整优先使用提示词",
       fields: ["framework_error_guard_enabled", "enable_forbidden_word_recall", "recall_forbidden_words",
                "recall_forbidden_scope", "recall_forbidden_word_case_sensitive"]},
      {id: "timing", title: "消息节奏", help: "分段之间的等待时间",
       fields: ["part_gap_mode", "part_gap_ms", "part_gap_min_ms", "part_gap_max_ms", "part_gap_log_base"]},
    ],
    segmentedChoices: ["rule_mode", "part_gap_mode"],
    inputs: {
      split_words: "word-list", content_cleanup_words: "word-list", recall_forbidden_words: "word-list",
      content_replacements: "replacement-list", component_order: "order-list",
      group_wakeup_direct_words: "word-list", group_wakeup_context_words: "word-list",
      group_wakeup_interest_keywords: "word-list", group_wakeup_primary_member_ids: "word-list",
      group_wakeup_owner_direct_words: "word-list",
    },
    visibility: {
      split_words: {rules_enabled: true, rule_mode: "words"},
      match_width_variants: {rules_enabled: true, rule_mode: "words"},
      rule_regex: {rules_enabled: true, rule_mode: "regex"},
      threshold: {rules_enabled: true}, min_segment_chars: {rules_enabled: true},
      max_segments: {rules_enabled: true},
      part_gap_ms: {part_gap_mode: "fixed"},
      part_gap_min_ms: {part_gap_mode: "random"},
      part_gap_max_ms: {part_gap_mode: "random"},
      part_gap_log_base: {part_gap_mode: "log"},
    },
    listFields: {
      split_words: {maxItems: 80, maxLength: 40, unique: "exact", specials: ["newline"]},
      content_cleanup_words: {maxItems: 80, maxLength: 200, specials: ["space", "newline", "tab"]},
      recall_forbidden_words: {maxItems: 80, maxLength: 200},
      group_wakeup_direct_words: {maxItems: 24, maxLength: 40, unique: "casefold", trim: true},
      group_wakeup_context_words: {maxItems: 24, maxLength: 40, unique: "casefold", trim: true},
      group_wakeup_interest_keywords: {maxItems: 24, maxLength: 40, unique: "casefold", trim: true},
      group_wakeup_primary_member_ids: {maxItems: 16, maxLength: 20, unique: "exact", numericIds: true, trim: true},
      group_wakeup_owner_direct_words: {maxItems: 24, maxLength: 40, unique: "casefold", trim: true},
      content_replacements: {maxItems: 80, fromMaxLength: 200, toMaxLength: 500},
    },
    rows: {prompt: 4, style_prompt: 5, humanized_expression_prompt: 6,
      rule_regex: 3, content_cleanup_rule: 3, content_replacements: 4, component_order: 3,
      voice_trigger_keywords: 2, voice_extra_prompt: 3},
  };
  const decisionSectionIds = new Set(["wakeup", "wakeup_timing", "group_safety"]);
  const perceptionSectionIds = new Set(["context_image"]);
  function specFor(view) {
    const sections = spec.sections.filter(section => {
      if (view === "decision") return decisionSectionIds.has(section.id);
      if (view === "perception") return perceptionSectionIds.has(section.id);
      return !decisionSectionIds.has(section.id) && !perceptionSectionIds.has(section.id);
    });
    const title = view === "decision" ? "群聊回应决策"
      : view === "perception" ? "图片上下文理解" : spec.title;
    return {...spec,
      title,
      note: view === "decision"
        ? "这些设置决定群聊中何时回应、参与节奏与安全边界；保存后用于之后开始的判断。"
        : view === "perception"
          ? "控制群聊图片是否补充文字描述，作为本轮理解材料。"
          : spec.note,
      sections,
      order: sections.flatMap(section => section.fields),
    };
  }

  /* 后端把机器码放在信封的 message 上（页面桥只转发 message），所以取码要同时
     看 data.code 与 message；reason 里是可直接展示的原因句，遇到人话就原样保留。 */
  const errors = {
    reply_configuration_invalid: "请核对参数范围和提示词长度。",
    reply_preview_invalid: "请填写 1–65536 字的有效正文。",
    reply_request_invalid: "请求格式有误，请刷新后核对。",
    reply_images_changed: "图片与当前草稿不再一致，请刷新后重新预览。",
    staging_not_initialized: "请先在账号与会话中加载 V2 运行实例，再回到本页。",
    staging_host_terminated: "V2 宿主已停止，请重新打开插件页面。",
    dashboard_identity_required: "请从已登录的 AstrBot 管理页面打开陪伴小屋。",
    core_access_required: "当前管理账号没有陪伴小屋的查看权限。",
    recall_request_invalid: "撤回请求格式有误，请刷新后重试。",
    bridge_timeout: "连接超时，请核对连接后重试。",
    invalid_response: "返回的数据不完整，请刷新核对。",
  };
  const isCode = value => typeof value === "string" && /^[a-z][a-z0-9_]{2,60}$/.test(value);
  const localized = (problem, fallback) => errors[problem?.code]
    || (isCode(problem?.message) ? errors[problem.message] : problem?.message)
    || fallback;

  const e = v => String(v ?? "").replace(/[&<>"']/g, c =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const error = (code, confirmed = false) => Object.assign(new Error(code), {code, confirmed});
  const imageLabel = v => (v === "before_text" ? "图片在文字前" : "图片在文字后");
  const choiceText = (name, value) => choices[name]?.[value] || value;

  const sample = "刚刚看到一片很好看的云。\n<<PRIVATE_COMPANION_SPLIT>>\n想慢慢讲给你听。";

  let root = null, instance = null, version = 0, route = null, activeSections = spec.sections;
  const state = {example: sample, imageCount: 0, preview: null, status: null,
    busy: false, loading: false, denied: false, notice: "", bad: false};

  const live = ticket => ticket === version && root?.isConnected;
  const anchor = name => root?.querySelector(`[data-reply-part="${name}"]`);

  /* 设置卡片的挂载点，以及它下方的预览与诊断。 */
  const parts = () => ({
    settings: root?.querySelector('[data-reply-part="settings"]'),
    preview: root?.querySelector('[data-reply-part="preview"]'),
    diagnostics: root?.querySelector('[data-reply-part="diagnostics"]'),
  });

  function summary(v) {
    return `${v.streaming ? "流式接收" : "完整响应"} · `
      + (v.enabled ? `${v.llm_controlled ? "模型分段" : "规则分段"}，最多 ${v.max_segments} 条` : "单条回复")
      + ` · 段间 ${v.part_gap_ms / 1000} 秒 · ${imageLabel(v.image_position)} · `
      + `${v.enable_humanized_expression ? "拟人 Prompt 已开启" : "拟人 Prompt 关闭"} · `
      + (v.voice_enabled
        ? `${choiceText("voice_language", v.voice_language)}语音 · ${choiceText("voice_segment_mode", v.voice_segment_mode)}`
        : Object.hasOwn(v, "voice_enabled") ? "语音关闭" : "语音未记录");
  }

  async function api(method, endpoint, body) {
    let timer;
    try {
    /* 等桥就绪，而不是当场读 window.AstrBotPluginPage。
       主页面此前不引页面桥 SDK，桥是在 product.connect() 里动态补上的；
       这一页若在它补好之前就发请求，读到的是 undefined，用户看到的是
       「未连接」——一个只在几百毫秒窗口里出现的假故障。 */
      const bridge = window.CompanionProduct.bridgeNow() || await window.CompanionProduct.bridgeFor();
      const response = await Promise.race([
        method === "GET" ? bridge.apiGet(endpoint) : bridge.apiPost(endpoint, body),
        new Promise((_, reject) => {timer = setTimeout(() => reject(error("bridge_timeout")), 15000);}),
      ]);
      const wrapped = ["ok", "error"].includes(response?.status) ? response
        : ["ok", "error"].includes(response?.data?.status) ? response.data : null;
      if (wrapped?.status === "error") throw error(wrapped.data?.code || (isCode(wrapped.message) ? wrapped.message : "") || "invalid_response", true);
      const value = wrapped ? wrapped.data : response;
      if (!value || typeof value !== "object" || Array.isArray(value)) throw error("invalid_response");
      return value;
    } finally { clearTimeout(timer); }
  }

  /* 读取由工作台负责；这里只订阅它的结果，用来渲染预览、诊断与保存摘要。 */
  function adopt(status) {
    state.status = status || null;
    if (!status) return;
    /* 预览用的草稿设置取自工作台当前草稿，保证「预览当前草稿」名副其实。 */
    renderPreview();
    renderDiagnostics();
  }

  function draftSettings() {
    return instance?.state?.draft || state.status?.settings || null;
  }

  function previewMarkup(p) {
    const order = items => items.map(k => ({text: "文字", image: "图片", voice: "语音"}[k])).join(" → ");
    return `<p class="reply-preview-meta">离线预览 · ${p.count} 条消息 · ${p.characters} 字 · `
      + `段间等待至少 ${p.minimum_spacing_ms / 1000} 秒 · ${imageLabel(p.image_position)}</p><ol>`
      + p.parts.map((text, index) => {
        const c = p.components[index];
        return `<li><pre>${e(text)}</pre>`
          + (c.speech
            ? `<div class="reply-speech"><small>候选朗读</small><pre>${e(c.speech)}</pre>`
              + `<small>触发并合成成功：${e(order(c.success_order))}</small>`
              + `<small>未触发或合成失败：${e(order(c.fallback_order))}</small></div>`
            : `<p class="reply-preview-meta">${e(order(c.fallback_order))}</p>`)
          + `</li>`;
      }).join("") + `</ol>`
      + (p.voice.enabled ? `<p class="reply-preview-meta">TTS 扩展：${e(p.voice.provider_id || "跟随 AstrBot")}</p>` : "")
      + `<details><summary>本次表达提示词</summary><pre>`
      + e([p.instruction, p.voice.instruction].filter(Boolean).join("\n\n") || "无附加提示词")
      + `</pre></details>`;
  }

  function renderPreview() {
    const host = anchor("preview");
    if (!host) return;
    const locked = state.busy || state.loading || state.denied || !state.status;
    host.innerHTML = `<section class="reply-preview"><h3>消息预览</h3>`
      + `<label>示例正文<textarea data-reply-part-input="example" rows="7" ${state.busy ? "disabled" : ""}>${e(state.example)}</textarea></label>`
      + `<label class="reply-image-count">末段图片数<input data-reply-part-input="image-count" type="number" min="0" max="8" step="1" value="${e(state.imageCount)}" ${state.busy ? "disabled" : ""}></label>`
      + `<button class="button" data-reply-action="preview" ${locked || state.busy ? "disabled" : ""}>预览当前草稿</button>`
      + `<div id="reply-preview-result" aria-live="polite">`
      + (state.preview ? previewMarkup(state.preview) : '<p class="reply-muted">暂无预览</p>') + `</div></section>`;
  }

  function diagnosticMarkup(item, token) {
    const c = item.captured, stream = c?.settings?.streaming;
    const collecting = ["collecting", "open"].includes(item.state);
    const partMarkup = part => {
      const recorded = part.candidate_reason !== null && part.candidate_reason !== undefined;
      const candidate = recorded ? candidateLabels[part.candidate_reason] || "语音状态未知" : "语音诊断未记录";
      const render = recorded ? ` · ${renderLabels[part.render_state] || "合成状态未知"}` : "";
      const order = Array.isArray(part.component_order) && part.component_order.length
        ? ` · 组件：${part.component_order.map(k => ({text: "文字", image: "图片", voice: "语音"}[k] || "未知")).join(" → ")}` : "";
      const hidden = part.text_hidden === 1 ? " · 文字已隐藏" : "";
      return `<li>第 ${e(part.sequence)} 段 · ${e(part.chars)} 字 · ${e(labels[part.state] || part.state)}`
        + `<small class="reply-part-detail">${e(candidate + render + order + hidden)}`
        + `${part.speech_chars ? ` · 候选 ${e(part.speech_chars)} 字` : ""}</small></li>`;
    };
    return `<details class="reply-record"><summary><span>${e(labels[item.state] || item.state)}</span>`
      + `<span>${c ? (stream ? "流式接收" : "完整响应") : collecting ? "尚未固定配置" : "旧记录 · 接收模式未记录"}</span>`
      + `<time>${e(item.created_at)}</time></summary>`
      + `<p>${c ? `${e(summary(c.settings))} · ${c.configuration_token === token ? "与当前配置一致" : "采用此前配置"}`
        : collecting ? "输入仍在收集中，配置尚未固定。" : "旧记录未保存回复配置快照。"}</p>`
      + `<p>${e(item.reason || "")}</p><ul>`
      + item.calls.map(call => `<li>模型：${e(labels[call.state] || call.state)}`
        + `${call.failure_code ? ` · ${e(call.failure_code)}` : ""} · 用量 `
        + `${call.actual_tokens === null ? "未知" : e(call.actual_tokens) + " tokens"}`
        + `${call.latency_ms === null ? "" : ` · ${Math.round(call.latency_ms)} ms`}</li>`).join("")
      + item.parts.map(partMarkup).join("") + `</ul><small>记录编号：${e(item.batch_id)}</small></details>`;
  }

  function renderDiagnostics() {
    const host = anchor("diagnostics");
    if (!host) return;
    const status = state.status;
    host.innerHTML = `<section class="reply-diagnostics"><header><h3>最近回复诊断</h3>`
      + `<span>当前对象与角色 · 最近 10 轮</span></header>`
      + ``
      + (status?.recent?.length
        ? status.recent.map(item => diagnosticMarkup(item, status.configuration_token)).join("")
        : `<div class="reply-empty">${status ? "还没有本轮上下文的回复记录。开始一次对话后，点击读取当前状态查看。" : "连接已初始化的 V2 运行实例后可查看。"}</div>`)
      + `</section>`;
  }

  async function preview() {
    const ticket = version;
    if (state.busy || state.loading || state.denied || !state.status) return;
    if (instance?.state?.pending) {
      state.notice = "先核对上次未确认的保存结果，再预览。";
      state.bad = true;
      renderPreview();
      return;
    }
    const settings = draftSettings();
    if (!settings || !Number.isInteger(state.imageCount) || state.imageCount < 0 || state.imageCount > 8) {
      state.notice = errors.reply_preview_invalid;
      state.bad = true;
      renderPreview();
      return;
    }
    state.busy = true;
    state.notice = "正在计算预览…";
    renderPreview();
    try {
      const p = await api("POST", route + "/preview",
        {settings: {...settings}, text: state.example, image_count: state.imageCount});
      if (!Array.isArray(p.parts) || !p.parts.length || p.parts.some(v => typeof v !== "string")
          || p.mode !== "offline_preview" || !p.voice || !Array.isArray(p.components)
          || p.components.length !== p.parts.length
          || p.components.some(c => !c || typeof c.speech !== "string"
            || [c.success_order, c.fallback_order].some(order => !Array.isArray(order)
              || order.some(k => !["text", "image", "voice"].includes(k))))) {
        throw error("invalid_response");
      }
      if (!live(ticket)) return;
      state.preview = p;
      state.notice = "预览已更新，使用当前草稿。";
      state.bad = false;
    } catch (problem) {
      if (!live(ticket)) return;
      state.preview = null;
      state.notice = localized(problem, "预览失败，请重试。");
      state.bad = true;
    } finally {
      state.busy = false;
      if (live(ticket)) renderPreview();
    }
  }

  function onInput(event) {
    const el = event.target;
    const name = el?.dataset?.replyPartInput;
    if (!name) return;
    if (name === "example") state.example = el.value;
    else state.imageCount = el.valueAsNumber;
    state.preview = null;
    const result = root?.querySelector("#reply-preview-result");
    if (result) result.textContent = "示例已改变，请重新预览。";
  }

  function onClick(event) {
    const action = event.target.closest("[data-reply-action]")?.dataset.replyAction;
    if (action === "preview") void preview();
  }

  function unmount() {
    version++;
    if (instance) instance.unmount();
    if (root) {
      root.removeEventListener("input", onInput);
      root.removeEventListener("click", onClick);
      root.textContent = "";
    }
    instance = null; root = null; route = null; activeSections = spec.sections;
    state.status = null; state.preview = null; state.notice = ""; state.bad = false;
  }

  function selectSection(id, {scroll = true} = {}) {
    if (!activeSections.some(section => section.id === id)) return false;
    const target = [...(root?.querySelectorAll?.("[data-wb-section]") || [])]
      .find(tab => tab.dataset.wbSection === id);
    if (!target) return false;
    target.click();
    if (scroll) {
      const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
      root?.scrollIntoView?.({behavior: reduced ? "instant" : "smooth", block: "start"});
    }
    return true;
  }

  function mount(element, options = {}) {
    const host = element;
    const pageSpec = specFor(options.view);
    unmount();
    if (!host) return;
    root = host;
    activeSections = pageSpec.sections;
    if (!pageSpec.sections.length) {
      root.innerHTML = '<div class="reply-empty">当前视图没有可编辑的回复设置。</div>';
      return;
    }
    const product = window.CompanionProduct;
    if (!product?.hosted?.()) {
      root.innerHTML = `<div class="reply-empty"><h2>${e(pageSpec.title)}</h2>`
        + '<p>请从 AstrBot 打开陪伴小屋，连接 V2 运行实例后调整分段并预览。</p></div>';
      return;
    }
    const endpoint = product.role()?.reply_api;
    const identity = product.identity?.() || {};
    /* 端点会成为请求路径的一部分，所以除了前缀还要求它是干净的路径段：
       不含查询串、百分号、反斜杠与 . / .. 段。 */
    if (typeof endpoint !== "string" || !endpoint.startsWith(PREFIX) || !identity.operator_id
        || /[?#%\\:]/.test(endpoint)
        || endpoint.split("/").slice(1).some(part => !part || part === "." || part === "..")) {
      root.innerHTML = options.view === "decision"
        ? '<div class="reply-empty">当前对象没有可用的群聊回应决策设置工作区。请先选择已初始化的会话对象和角色。</div>'
        : options.view === "perception"
          ? '<div class="reply-empty">当前对象没有可用的图片上下文设置工作区。请先选择已初始化的会话对象和角色。</div>'
          : '<div class="reply-empty">当前对象没有可用的回复设置工作区。请先选择已初始化的私聊对象和角色。</div>';
      return;
    }
    if (!window.CompanionWorkbench?.create) {
      root.innerHTML = '<div class="reply-empty">配置工作台未加载，无法编辑回复设置。</div>';
      return;
    }
    /* 桥只接受插件相对路径；工作台入口则保留完整路径做自身校验。 */
    route = endpoint.slice(PREFIX.length);
    root.innerHTML = '<div data-reply-part="settings"></div>'
      + (options.view === "expression" || !options.view
        ? '<div data-reply-part="preview"></div><div data-reply-part="diagnostics"></div>' : "");
    root.addEventListener("input", onInput);
    root.addEventListener("click", onClick);
    instance = window.CompanionWorkbench.create({
      group: GROUP,
      title: pageSpec.title,
      note: pageSpec.note,
      labels: pageSpec.labels,
      helps: pageSpec.helps,
      choices,
      sections: pageSpec.sections,
      navigationLimit: pageSpec.sections.length,
      rows: pageSpec.rows,
      segmentedChoices: spec.segmentedChoices,
      inputs: spec.inputs,
      visibility: spec.visibility,
      listFields: spec.listFields,
      order: pageSpec.order,
      endpoint: PREFIX + route,
      /* TTS 扩展目录要等读取之后才知道，所以选项由函数现取。 */
      catalogs: {
        voice_provider_id: () => providerOptions("跟随 AstrBot"),
        voice_zh_provider_id: () => providerOptions("使用通用扩展"),
        voice_ja_provider_id: () => providerOptions("使用通用扩展"),
        voice_en_provider_id: () => providerOptions("使用通用扩展"),
      },
      mount: () => parts().settings,
      /* 工作台拿到新快照后，预览与诊断跟着重画。 */
      onStatus: adopt,
    });
    instance.mount();
    if (options.view !== "decision") {
      renderPreview();
      renderDiagnostics();
    }
  }

  /* 扩展目录来自读取结果；当前值不在目录里时补一条标注，
     避免把不可用的选择静默改写成别的扩展。 */
  function providerOptions(fallback) {
    const options = {"": fallback};
    for (const item of state.status?.tts?.providers || []) {
      if (typeof item?.id === "string" && item.id) options[item.id] = item.id;
    }
    return options;
  }

  return {mount, unmount, choices, selectSection,
    get state() { return {instance, example: state.example, imageCount: state.imageCount,
      preview: state.preview, notice: state.notice, bad: state.bad}; }};
})();
