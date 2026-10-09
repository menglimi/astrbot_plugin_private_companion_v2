/* 陪伴小屋 · 主动与联系（节律盘）
 *
 * 这一页管的是「她此刻会不会开口、按什么节律开口」。
 *
 * 与记忆页的区别——也是不能照搬记忆页版式的原因：
 *   记忆是**生命周期**（写入→更正→撤回→遗忘），所以记忆页是档案库、master-detail。
 *   联系是**时间上的分布**（一天里哪些小时允许开口、两次之间隔多久、连发几轮），
 *   所以这一页的主体是一个钟面：24 小时环形，四圈同心。
 *
 * 四圈对应四个真实字段，且只有这四圈是「一天」这个量纲上的东西：
 *   外圈 · 免打扰弧      quiet_enabled / quiet_start / quiet_end（可跨午夜）
 *   次圈 · 活动曲线      proactive_hour_activity_enabled / proactive_hour_activity_curve（24 权重）
 *   三圈 · 强度档位       proactive_intensity_preset（缩放间隔与门槛，不放宽额度）
 *   内圈 · 问候窗口       greeting_morning/noon/evening_window + 失眠窗口
 * 环心是**此刻**：现在处于哪一段、此刻能不能开口、不能的话是哪一条。
 *
 * 读出口是角色目录的 perception_native_api，其中 contact 来自 ContactManagement.status。
 * 它给 160 个 settings、15 个 purposes（各带 allowed + 唯一阻断原因）、
 * 以及 effective 上的四层判定。写出口是另一个：POST /config/configure 的
 * proactive.contact 段（native 那条只放行 6 个 news 字段，写不动其余 152 项）。
 *
 * 关于额度：budget.py 的滚动额度（max_contacts_24h 等）**只有写入口，没有读出口**。
 * 所以页面上这些一律画成「上限刻度」，不画成「已用量表」——不知道的就不画，
 * 比画一个假读数好。
 *
 * 动效分三层，都在 prefers-reduced-motion 下压到瞬时终态，信息一条不丢：
 *   ① 开页一次——24 根柱子从 0:00（正上方）向两侧荡开，在 12:00 会合，
 *      约一秒跑完就不再重复（涟漪，见 ct-bar-ripple 与 --i）；
 *   ② 改动确认——改了哪一圈就只闪哪一圈（PULSE_PART → is-pulse-*），
 *      整盘一起动等于什么都没说清；类由渲染时给出，不是渲染后往节点上加；
 *   ③ 状态常驻——时间游标、「此刻可以开口」的呼吸点。
 */
"use strict";
window.CompanionContactPage = (() => {
  const HOST = "astrbot_plugin_private_companion_v2";
  const PREFIX = "/" + HOST + "/";
  const STORE = "companion-contact-page-v1:";
  const HISTORY_PENDING = "__companion_contact_pending_v1";
  const HISTORY_PREVIOUS = "__companion_contact_previous_state_v1";
  const pendingWrites = new Map();
  const AUTO_RECOVERY_INITIAL_DELAY = 400;
  const AUTO_RECOVERY_MAX_DELAY = 30000;
  const AUTO_RECOVERY_MAX_EXPONENT = 8;
  let autoRecoveryKey = "";
  let autoRecoveryTimer = null;
  let autoRecoveryAttempts = 0;
  const GROUP = "proactive.contact";
  /* 15 类契机，归属三个语义桶——这个分法来自它们「凭什么开口」：
     关系本身、日程时刻、还是外部分享。矩阵按桶分行，不按字母序。 */
  const PURPOSE_BUCKETS = [
    {id:"bond",  label:"关系",  hint:"由关系状态驱动", purposes:[
      ["affection","想念与亲近"],["care","情绪关怀"],["play","轻松互动"],
      ["repair","关系修复"],["chat","日常话题"]]},
    {id:"daily", label:"日程",  hint:"由时刻或约定驱动", purposes:[
      ["greeting","问候与纪念"],["followup","接回旧话题"],["invitation","共同活动邀请"],
      ["reminder","约定与提醒"],["meal","饭点问候"]]},
    {id:"share", label:"分享",  hint:"由外部素材驱动", purposes:[
      ["life","分享自己的生活"],["creation","作品与阅读"],["news","外部资讯"],
      ["environment","环境与状态变化"],["screen","已授权屏幕观察"]]},
  ];
  const ALL_PURPOSES = PURPOSE_BUCKETS.flatMap(b => b.purposes);
  const PURPOSE_META = Object.fromEntries(PURPOSE_BUCKETS.flatMap(bucket =>
    bucket.purposes.map(([name, label]) => [name, {label, bucket}])));
  const TEST_INSTRUCTIONS = [
    {id:"affection", label:"想念与亲近", bucket:"关系", coverage:"ready",
      source:"近期双方有来有回、明确表达亲近的私聊",
      setup:"合成双方近期互相回应并明确表达亲近的对话；另备一组只有单向旧消息的负例。",
      instruction:"只根据双方真实表达的亲近感，判断是否适合留一句自然、不索取回应的话；不能凭沉默声称想念。",
      expect:"正文锚定原对话；没有明确亲近证据时选择 skip。"},
    {id:"care", label:"情绪关怀", bucket:"关系", coverage:"ready",
      source:"对方明确说出的感受",
      setup:"合成对方明确表达疲惫或难过的对话；另备普通沉默和情绪不明的负例。",
      instruction:"回应对方实际说出的感受，不诊断原因，不提供未经请求的方案，也不把沉默解释成低落。",
      expect:"不夸大情绪、不连续追问；缺少明确感受时选择 skip。"},
    {id:"play", label:"轻松互动", bucket:"关系", coverage:"ready",
      source:"双方都参与过的玩笑或共同话题",
      setup:"合成双方都接受的玩笑或共同梗；另备单方玩笑及严肃语境的负例。",
      instruction:"只有原语境确实轻松且双方都参与时，才延续一个低压力的小互动；不编造共同梗。",
      expect:"互动可自然结束；紧张、严肃或单方玩笑素材必须选择 skip。"},
    {id:"repair", label:"关系修复", bucket:"关系", coverage:"ready",
      source:"角色可核验的失误及对方指出的不适",
      setup:"合成角色具体失误和对方明确指出不适的对话；另备没有具体失误的负例。",
      instruction:"准确承认自己做错的具体部分，简短表达理解；不辩解、不要求原谅、不把修复责任推给对方。",
      expect:"只回应证据支持的失误；对方要求停止联系时必须选择 skip。"},
    {id:"chat", label:"日常话题", bucket:"关系", coverage:"ready",
      source:"已完成的最近一轮私聊与原始消息来源",
      setup:"构造已完成的真实私聊批次，推进到配置的空闲窗口；另备刚有新输入和重复话题的负例。",
      instruction:"从最近实际谈过的话题承接一点内容；避免“在吗”、空泛问候和复述刚发过的话。",
      expect:"授权、空闲、额度、活动曲线和去重按真实配置生效；不合适时选择 skip。"},
    {id:"greeting", label:"问候与纪念", bucket:"日程", coverage:"ready",
      source:"本地问候窗口、夜间窗口或管理员配置的纪念日期",
      setup:"分别构造早/午/晚窗口、夜间窗口和重要日期样例，并验证窗口边界。",
      instruction:"把日期或时段只当作开口机会；优先承接当前语境，不假设对方刚醒、吃饭、休息或正在等待。",
      expect:"只在有效窗口、静默和冷却规则允许时进入链路；不得机械套用固定问候。"},
    {id:"followup", label:"接回旧话题", bucket:"日程", coverage:"ready",
      source:"已确认投递记录、等待时间及之后是否有新输入",
      setup:"构造已确认投递、等待期已过且无新输入的记录；另测新输入、屏幕观察和冷却中的对照组。",
      instruction:"只承接原记录中仍有意义且未被新输入取代的话题，不暗示已读或催回复。",
      expect:"只在原话仍有效、等待期已过且无新输入时起草；跟进生产器会再次校验原始投递与冷却。"},
    {id:"invitation", label:"共同活动邀请", bucket:"日程", coverage:"ready",
      source:"对方明确提出的共同活动邀请与活动素材",
      setup:"合成包含明确共同活动邀请的私聊；另测只有共同兴趣、空闲未知及已拒绝的样例。",
      instruction:"把活动说成可商量的邀请，不伪造双方空闲、预约或承诺，不要求接受。",
      expect:"不把提议说成已预约；明确邀请才产生候选，只有共同兴趣或对方已拒绝时不发送。"},
    {id:"reminder", label:"约定与提醒", bucket:"日程", coverage:"ready",
      source:"当前有效、已接受且即将开始的日历约定",
      setup:"构造已接受且即将开始的约定；对照待确认、取消、过期和修订过的记录。",
      instruction:"只根据当前有效的已接受约定简短提醒，不说成已经发生，也不声称对方已收到或记得。",
      expect:"来源回执、版本、发生时间和配置窗口全部匹配才进入模型。"},
    {id:"meal", label:"饭点问候", bucket:"日程", coverage:"ready",
      source:"关系时区中的午餐或晚餐时间窗口",
      setup:"按关系时区构造午餐、晚餐窗口；另测窗口边界、暂停和重复候选。",
      instruction:"当地饭点只提供时间语境，不推断对方没吃饭、正在吃饭或需要提醒；没有自然话头就选择 skip。",
      expect:"使用配置时区和原始窗口；不默认盘问饮食或要求报平安。"},
    {id:"life", label:"分享自己的生活", bucket:"分享", coverage:"ready",
      source:"仍有效且允许分享的角色活动回执或日记记录",
      setup:"构造真实活动完成回执或角色日记；另测素材撤回和修订版本变化。",
      instruction:"只分享已完成且当前仍有效的具体片段；日记和梦境保持主观语境，不扩写成客观事实或对方经历。",
      expect:"原操作、修订、来源授权和受众复核通过才生成；旧候选在来源变化后失效。"},
    {id:"creation", label:"作品与阅读", bucket:"分享", coverage:"ready",
      source:"带有阅读范围的完成回执",
      setup:"构造完成阅读回执和可引用范围；对照只打开、未完成和范围已变更的记录。",
      instruction:"只说回执覆盖的阅读片段；个人感想明确是角色感受，不声称读完整本或把书中内容说成现实。",
      expect:"只有完成且回执有效时触发；不补写未提供的书名、章节或情节。"},
    {id:"news", label:"外部资讯", bucket:"分享", coverage:"ready",
      source:"带标题、原链接和发布时间的当前资讯条目",
      setup:"使用隔离资讯源返回当前条目；另测过期、重复、抓取失败及来源配置变化。",
      instruction:"只根据给定条目判断是否与关系语境相关；保留原发布时间，不声称亲历、看完全文或独立核实。",
      expect:"来源不完整或失效时不触发；准确归因由程序追加一次。"},
    {id:"environment", label:"环境与状态变化", bucket:"分享", coverage:"ready",
      source:"当前天气、天气变化、官方预警或 Bot 服务余额来源",
      setup:"分测当前观测、两次观测的变化、官方预警覆盖范围和服务余额；再测过期或范围不明素材。",
      instruction:"天气观测不等于预报，变化不等于灾害；预警只按官方原文与覆盖范围，余额不是用户欠款，不催充值。",
      expect:"严格使用来源地点、时效、覆盖范围和金额；依据不足时选择 skip。"},
    {id:"screen", label:"已授权屏幕观察", bucket:"分享", coverage:"ready",
      source:"同一私聊中仍有效的授权屏幕分析回执",
      setup:"构造同一私聊且授权有效的屏幕分析回执；另测撤权、来源撤回和冷却。",
      instruction:"只提及分析明确支持且适合分享的一点观察；不暴露无关屏幕内容，不推断用户意图或身份。",
      expect:"授权、来源、窗口和每日上限复核通过才进入模型；撤权或来源变化后立即失效。"},
  ];
  const TEST_COVERAGE = {ready:"生产器已接通", partial:"只有资格检查", missing:"尚无独立生产器"};
  const TEST_BUCKET_IDS = {关系:"bond", 日程:"daily", 分享:"share"};
  /* 强度档位。effects 只是**给界面看的**说明，真值在 configuration.py 的
     INTENSITY_PRESETS 里；这里写死的是「这个档位会怎么变」的文案，
     不参与任何计算。 */
  const TIERS = [
    {key:"off",         label:"关闭",   interval:1.0,  idle:1.0,  burst:0, chars:0},
    {key:"balanced",    label:"均衡",   interval:0.8,  idle:0.7,  burst:2, chars:300},
    {key:"high_private",label:"高频私聊", interval:0.5, idle:0.35, burst:3, chars:300},
    {key:"high_group",  label:"高频群聊", interval:0.9, idle:0.8,  burst:2, chars:240},
    {key:"live",        label:"实时",   interval:0.2,  idle:0.1,  burst:3, chars:400},
  ];
  const TIER_BY_KEY = Object.fromEntries(TIERS.map(t => [t.key, t]));
  /* 强度别名。后端 INTENSITY_ALIASES 会把 直播/高频 这类写法归一，
     页面显示时必须显示归一后的档位，否则「设了实时却显示直播」会让人以为没保存上。 */
  const TIER_ALIAS = {manual:"off",none:"off",default:"off","":"off",standard:"balanced",
    active:"high_private",private:"high_private",group:"high_group",online:"live",直播:"live",高频:"live"};
  const DEFAULT_CURVE = "0.22,0.16,0.12,0.10,0.10,0.14,0.28,0.50,0.66,0.72,0.78,0.92,1.0,0.94,"
    + "0.82,0.74,0.78,0.92,1.0,0.98,0.88,0.70,0.48,0.32";
  /* 三个问候锚点的默认窗口。只用于在环上画参考弧，真值读 settings。 */
  const ANCHORS = [["morning","morning_greeting","07:45","10:20"],["noon","noon_greeting","12:05","13:35"],
                   ["evening","evening_greeting","20:10","21:20"]];
  const errors = {
    dashboard_identity_required:"请从已登录的 AstrBot 管理界面打开陪伴小屋。",
    staging_not_initialized:"角色数据尚未就绪，请在「账号与会话」保存角色映射；已保存可重新读取状态。",
    staging_host_terminated:"插件已停止，请重新打开拓展页。",
    core_access_required:"当前账号没有联系设置权限。",
    authorization_denied:"当前对象尚未授予联系权限。",
    binding_revoked:"管理账号的授权已撤销。", binding_rebound:"管理账号的绑定已变化，请重新进入。",
    proactive_contact_scope_invalid:"主动联系偏好按会话生效，请选择一个已初始化的私聊对象。",
    proactive_contact_target_changed:"当前对象或角色绑定已变化，请重新读取。",
    proactive_contact_configuration_invalid:"请核对设置：数值需在各自范围内，枚举项需在下拉选项内。",
    proactive_contact_clock_invalid:"请填写二十四小时制的时刻，形如 23:00 或 07:45。",
    proactive_contact_window_invalid:"问候窗口形如 07:45-10:20，且必须当天内结束，不能跨午夜。",
    proactive_contact_timezone_invalid:"时区名无效，形如 Asia/Shanghai。",
    proactive_contact_pause_invalid:"暂停时刻需带时区偏移，或留空表示不暂停。",
    proactive_contact_curve_invalid:"活动曲线需要 24 个数值；写错的那一小时会回退，其余照常。",
    proactive_contact_list_invalid:"请填写逗号分隔的取值，且不能重复。",
    proactive_contact_dates_invalid:"重要日期需要一个 JSON 数组，最多 32 条。",
    proactive_contact_source_invalid:"资讯来源填写有误，请核对类型、标识或地址。",
    proactive_contact_revision_conflict:"设置已有其他更新，已读取最新值。",
    configuration_revision_conflict:"设置已有其他更新，请重新读取后再保存。",
    contact_configuration_invalid:"请核对联系设置：提交的字段或操作不完整。",
    invalid_contact_preference:"请核对联系设置的格式或范围。",
    proactive_budget_scope:"这两个额度限制整段关系，只能在安装 / 角色 / 关系层设置。",
    contact_relationship_budget_scope:"这两个额度限制整段关系，只能在安装 / 角色 / 关系层设置。",
    configuration_relationship_required:"这个对象还没有建立可写入的关系。",
    contact_recipient_changed:"联系对象已变化，请重新读取。",
    configuration_request_invalid:"请求与当前接口不匹配，请更新页面后重试。",
    configuration_group_unknown:"这个设置分组已不存在，请更新页面。",
    bridge_unavailable:"页面还没有接上 AstrBot。若这是从管理界面打开的插件页，刷新一次通常就好；若反复出现，请确认插件已启用。",
    bridge_timeout:"未收到服务确认，请刷新核对。",
    invalid_response:"服务返回的数据不完整，请刷新核对。",
    proactive_quiet_hours:"当前处于免打扰时段。", proactive_paused:"当前已暂停主动联系。",
    proactive_disabled:"主动联系总开关已关闭。", contact_automatic_disabled:"后台自动联系未开启。",
    model_task_unregistered:"请先登记主动联系模型。", host_not_running:"当前运行实例尚未启动。",
  };
  const CODE = /^[a-z][a-z0-9_]{2,60}$/;
  const denied = new Set(["dashboard_identity_required","core_access_required","binding_revoked",
    "binding_rebound","staging_host_terminated","proactive_contact_scope_invalid"]);
  const e = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const reason = code => errors[code] || "联系条件暂时无法核对，请重新读取状态。";
  const problem = code => Object.assign(new Error(reason(code)), {code});
  function recoveryFailure(code) {
    if (code === "bridge_timeout" || code === "bridge_unavailable") {
      return "自动核对暂时没有收到服务确认；原请求已保留，系统会继续核对。";
    }
    if (errors[code]) return "核对未完成：" + errors[code];
    const detail = CODE.test(code || "") ? `（错误码：${code}）` : "";
    return `核对请求未收到确认${detail}；原保存请求已保留。`;
  }
  function automaticNotice(effective) {
    if (!effective || effective.automatic_allowed !== false) return null;
    const code = typeof effective.automatic_reason === "string" ? effective.automatic_reason : "";
    /* 授权、宿主、暂停等原因已经由环心的主原因说明；只有自动联系
       自己还有一条额外阻断时才另列一行，避免「开关已开」却显示成
       「后台自动联系未开启」的假象。 */
    if (!code || code === effective.reason) return null;
    const text = reason(code);
    return {code, text: code === "contact_automatic_disabled"
      ? "后台自动联系未开启" : (text === "联系条件暂时无法核对，请重新读取状态。"
        ? "后台自动联系当前受限。" : "后台自动联系：" + text)};
  }
  /* 时刻 HH:MM → 一天中的分钟数。跨午夜的区间靠 from > to 判定，不做取模，
     因为后端明确要求「窗口必须当天内结束」，只有免打扰允许跨午夜。 */
  const minutes = value => {
    const m = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(typeof value === "string" ? value.trim() : "");
    return m ? Number(m[1]) * 60 + Number(m[2]) : null;
  };
  const hm = value => {
    const total = Math.round(value) % 1440;
    return String(Math.floor(total / 60)).padStart(2, "0") + ":" + String(total % 60).padStart(2, "0");
  };
  const curveOf = value => {
    const parts = String(value ?? "").replace(/，/g, ",").split(",");
    if (parts.length !== 24) return DEFAULT_CURVE.split(",").map(Number);
    return parts.map(p => { const n = Number(p); return Number.isFinite(n) ? Math.max(0.05, Math.min(2, n)) : 1; });
  };
  const curveText = list => list.map(w => w.toFixed(2)).join(",");
  const tierOf = value => {
    const raw = String(value ?? "").trim().toLowerCase();
    return TIER_BY_KEY[raw] ? raw : (TIER_ALIAS[raw] || "off");
  };
  /* 一天里的第几分钟（带小数）→ 环上的角度。0:00 在正上方，顺时针。 */
  const angle = minute => (minute / 1440) * 360 - 90;
  const point = (cx, cy, r, minute) => {
    const a = angle(minute) * Math.PI / 180;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  };
  /* 一段圆弧的 path。跨午夜（from > to）时拆成两段——SVG 的弧不会自动绕圈。 */
  function arc(cx, cy, r, from, to, width) {
    const spans = from > to ? [[from, 1440], [0, to]] : [[from, to]];
    return spans.map(([a, b]) => {
      if (b - a <= 0.5) return "";
      const [x1, y1] = point(cx, cy, r, a), [x2, y2] = point(cx, cy, r, b);
      const large = b - a > 720 ? 1 : 0;
      return `<path d="M${x1.toFixed(2)} ${y1.toFixed(2)} A${r} ${r} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}"`
        + ` fill="none" stroke-width="${width}"/>`;
    }).join("");
  }
  const ICON = {
    dial:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="12" cy="12" r="8.4"/><path d="M12 7.4V12l3.2 2"/></svg>',
    gate:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h16"/><path d="M7 8v8M17 8v8"/></svg>',
    seed:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v7"/><path d="M8.5 6.5 12 10l3.5-3.5"/><path d="M5 14h14v6H5z"/></svg>',
    quota:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M5 19V9M10 19V5M15 19v-6M20 19v-9"/></svg>',
    source:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h16M4 18h10"/><circle cx="18.5" cy="18" r="2"/></svg>',
    test:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4.5h6M8.5 10h7M8.5 14h7M8.5 18h4"/><path d="m8.5 8.5 1 1 1.7-2"/></svg>',
    copy:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h2"/></svg>',
    mute:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9v6h3l4 3V6L9 9z"/><path d="m16 9 4 6M20 9l-4 6"/></svg>',
    refresh:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12a7 7 0 1 1-2.1-5"/><path d="M19 4v4h-4"/></svg>',
    alert:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5M12 16h.01"/></svg>',
    check:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7"/></svg>',
    save:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4h11l3 3v13H5z"/><path d="M9 4v5h6"/></svg>',
    arrow:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h13"/><path d="m13 6 6 6-6 6"/></svg>',
    undo:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10h11a4 4 0 0 1 0 8H8"/><path d="m8 6-4 4 4 4"/></svg>',
    /* 外部触发源那一屏的分组图标。几何都用圆、矩形、直线拼，
       不用一条长贝塞尔画云或碗：16px 下曲线走形比抽象更难看。 */
    weather:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="9.2" cy="12.4" r="3.2"/><circle cx="14.4" cy="12.9" r="2.5"/><path d="M6.2 15.6h11.6"/></svg>',
    bell:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6.6 10.2a5.4 5.4 0 0 1 10.8 0c0 3.1.8 4.5 1.4 5.3H5.2c.6-.8 1.4-2.2 1.4-5.3z"/><path d="M10.2 18.4a2 2 0 0 0 3.6 0"/></svg>',
    meal:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4.2 11.4h15.6a7.8 7.8 0 0 1-15.6 0z"/><path d="M9.4 8.2c0-1.1.8-1.5.8-2.4M13.6 8.2c0-1.1.8-1.5.8-2.4"/></svg>',
    compass:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.2"/><path d="m14.9 9.1-1.8 3.9-3.9 1.8 1.8-3.9z"/></svg>',
    screen:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3.4" y="5" width="17.2" height="11.4" rx="1.8"/><path d="M9.4 19.8h5.2"/></svg>',
    context:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 6.4h14M5 11.2h9M5 16h7"/><circle cx="18" cy="16.4" r="2.4"/></svg>',
    purse:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3.6" y="7.4" width="16.8" height="11.2" rx="2"/><path d="M3.6 11.6h16.8"/><path d="M15.4 15.4h2.2"/></svg>',
  };
  /* 哪个字段属于盘面的哪一部分。改动后只闪那一片：
     整盘一起动等于什么都没说清，用户看不出自己改的是哪一圈。
     盘面之外没有的字段一律不进这张表（找不到就说明「不需要动画」）。 */
  const PULSE_PART = {
    quiet_enabled:"quiet", quiet_start:"quiet", quiet_end:"quiet",
    proactive_hour_activity_enabled:"curve", proactive_hour_activity_curve:"curve",
    enable_daily_greetings:"greet", allow_insomnia_night_message:"greet",
    insomnia_night_start:"greet", insomnia_night_end:"greet",
    greeting_morning_window:"greet", greeting_noon_window:"greet", greeting_evening_window:"greet",
    quiet_timezone:"cursor",
    enabled:"center", automatic_enabled:"center",
    proactive_intensity_preset:"tier",
  };
  let root = null, bridge = null, version = 0, data = null;
  /* 联系设置有不少页面内筛选与未保存草稿。路由切换会卸载本页，按当前
     角色/会话在内存保留这些普通字段；令牌不进入缓存，回来后由真实接口
     重新读取。 */
  const contactCache = new Map();
  let contactScope = "";
  function currentContactScope() {
    try { return window.CompanionProduct?.scopeKey?.() || "default"; } catch (_) { return "default"; }
  }
  function cacheContact() {
    if (!data || !contactScope) return;
    contactCache.set(contactScope, {
      ...data, editToken:"", configToken:"", busy:false, loading:false, contractLoading:false,
      contractError:"", contractErrorCode:"", materialsLoading:false, touched:[...data.touched],
      draft:{...data.draft}, pulse:new Set(), pulseNow:[], flip:null, flipNow:null, viewShift:null, viewShiftNow:null,
    });
  }
  function pendingWriteKey() {
    const identity = window.CompanionProduct?.identity?.() || {};
    return STORE + "pending:" + JSON.stringify([
      identity.installation_id || "", identity.operator_id || "", contactScope, data?.configPath || "",
    ]);
  }
  function writeHistoryPending(key, value) {
    try {
      const current = window.history.state;
      const state = current && typeof current === "object" && !Array.isArray(current)
        ? {...current} : current == null ? {} : {[HISTORY_PREVIOUS]: current};
      const pending = state[HISTORY_PENDING] && typeof state[HISTORY_PENDING] === "object"
        ? {...state[HISTORY_PENDING]} : {};
      if (value) pending[key] = JSON.stringify(value);
      else delete pending[key];
      if (Object.keys(pending).length) state[HISTORY_PENDING] = pending;
      else delete state[HISTORY_PENDING];
      const next = !Object.keys(state).length ? null
        : Object.keys(state).length === 1 && HISTORY_PREVIOUS in state ? state[HISTORY_PREVIOUS] : state;
      window.history.replaceState(next, "");
      return true;
    } catch { return false; }
  }
  function readHistoryPending(key) {
    try {
      const stored = window.history.state?.[HISTORY_PENDING]?.[key];
      return typeof stored === "string" ? JSON.parse(stored) : null;
    } catch { return null; }
  }
  function storePendingWrite() {
    const key = pendingWriteKey();
    // Sandboxed Dashboard pages may block both storage and history. Keep the
    // same operation in this page session while its original response is unknown.
    if (data?.pendingWrite) pendingWrites.set(key, JSON.stringify(data.pendingWrite));
    else pendingWrites.delete(key);
    try {
      if (data?.pendingWrite) {
        sessionStorage.setItem(key, JSON.stringify(data.pendingWrite));
        return true;
      }
    } catch {}
    if (data?.pendingWrite) {
      try {
        localStorage.setItem(key, JSON.stringify(data.pendingWrite));
        return true;
      } catch { return writeHistoryPending(key, data.pendingWrite) || pendingWrites.has(key); }
    }
    let removed = false;
    for (const storage of [() => sessionStorage, () => localStorage]) {
      try { storage().removeItem(key); removed = true; } catch {}
    }
    return writeHistoryPending(key, null) || removed;
  }
  function restorePendingWrite() {
    if (data?.pendingWrite) return data.pendingWrite;
    const key = pendingWriteKey();
    for (const read of [
      () => pendingWrites.get(key),
      () => sessionStorage.getItem(key),
      () => localStorage.getItem(key),
      () => readHistoryPending(key),
    ]) try {
      const stored = read();
      const value = typeof stored === "string" ? JSON.parse(stored) : stored;
      const body = value?.body;
      if (value?.route === data.configPath + "/configure" && body?.section === GROUP
          && typeof body.operation_key === "string" && body.operation_key.length > 0 && body.operation_key.length <= 128
          && typeof body.edit_token === "string" && body.edit_token.length === 64
          && body.changes && typeof body.changes === "object" && !Array.isArray(body.changes)
          && Object.keys(body.changes).length) return value;
    } catch {}
    return null;
  }

  function schedulePendingRecovery(ticket = version) {
    const operationKey = data?.pendingWrite?.body?.operation_key;
    if (!operationKey) return;
    if (autoRecoveryKey !== operationKey) {
      if (autoRecoveryTimer !== null) clearTimeout(autoRecoveryTimer);
      autoRecoveryKey = operationKey;
      autoRecoveryAttempts = 0;
    }
    if (autoRecoveryTimer !== null) return;
    const delay = Math.min(AUTO_RECOVERY_INITIAL_DELAY * (2 ** Math.min(autoRecoveryAttempts,
      AUTO_RECOVERY_MAX_EXPONENT)), AUTO_RECOVERY_MAX_DELAY);
    autoRecoveryTimer = setTimeout(() => {
      autoRecoveryTimer = null;
      if (!live(ticket) || data.pendingWrite?.body?.operation_key !== operationKey) return;
      if (!data.ready || data.busy || data.loading) {
        schedulePendingRecovery(ticket);
        return;
      }
      autoRecoveryAttempts = Math.min(autoRecoveryAttempts + 1, AUTO_RECOVERY_MAX_EXPONENT);
      void save();
    }, delay);
  }

  function clearPendingRecovery(operationKey) {
    if (autoRecoveryKey !== operationKey) return;
    if (autoRecoveryTimer !== null) clearTimeout(autoRecoveryTimer);
    autoRecoveryTimer = null;
    autoRecoveryKey = "";
    autoRecoveryAttempts = 0;
  }

  function blank() {
    return {view:"dial", purposeQuery:"", purposeBucket:"all", purposeFilter:"all",
      testQuery:"", testBucket:"all", testCoverage:"all", materialQuery:"", materialCategory:"all",
      nativePath:"", configPath:"",
      settings:null, effective:null, purposes:{}, hostState:"",
      materialItems:[], materialsLoaded:false, materialsLoading:false, materialsError:"",
       editToken:"", configToken:"", contractLoading:false, contractError:"", contractErrorCode:"",
      /* 草稿：只放用户真的改过的字段。提交时只发这些，未动的字段一个都不发——
         避免把「没看过的字段」当成「要保持的值」写回去。 */
      draft:{}, touched:new Set(), tierDraft:null, pendingWrite:null,
      /* pulse 是「下一次渲染要闪哪几片盘面」，pulseNow 是这一帧真正在闪的。
         两者分开是因为 render() 每次都会重写 DOM，类必须由渲染时的状态决定，
         当场往节点上加类会被紧接着的重写丢掉（切档位那次动画就是这么消失的）。 */
      pulse:new Set(), pulseNow:[],
      /* flip 是「这一次谁被扳动了、扳向哪一边」，flipNow 是这一帧要放动画的那一个。
         开关本体没有 transition 的落脚点：点一下就整块重写 DOM，新节点带着终态出生，
         再漂亮的 transition 也一帧都放不出来——于是「扳」这个动作在界面上是凭空跳变。
         所以两个方向都用一次性 keyframes 播：toggle() / srcToggle() 按 flipNow 写类。 */
      flip:null, flipNow:null,
      /* 换页方向：1 往后、-1 往回、null 没换页。轨道上被点中的那一项也要跟着
         响一下——轨道按钮同样是每次渲染新建的，transition 照样不响，
         所以选中态也得走一次性动画，不然点导航就是「啪」地贴上去。 */
      viewShift:null, viewShiftNow:null,
      busy:false, loading:false, ready:false, scanning:true,
      notice:"", error:false, savedAt:null};
  }
  const value = name => name in (data?.draft || {}) ? data.draft[name] : data?.settings?.[name];
  function rel(absolute) {
    if (typeof absolute !== "string" || !absolute.startsWith(PREFIX)) throw problem("invalid_response");
    const route = absolute.slice(PREFIX.length);
    if (!route || /[?#%\\:]/.test(route) || route.split("/").some(p => !p || p === "." || p === "..")) {
      throw problem("invalid_response");
    }
    return route;
  }
  async function bounded(promise) {
    let timeout;
    try {
      return await Promise.race([promise, new Promise((_, reject) => {
        timeout = setTimeout(() => reject(problem("bridge_timeout")), 15000);
      })]);
    } finally { clearTimeout(timeout); }
  }
  async function api(method, path, body) {
    const response = await bounded(method === "GET" ? bridge.apiGet(path, body) : bridge.apiPost(path, body));
    const wrapped = ["ok","error"].includes(response?.status) && response?.data !== undefined ? response
      : ["ok","error"].includes(response?.data?.status) && response?.data?.data !== undefined ? response.data : null;
    if (wrapped?.status === "error") throw Object.assign(problem(CODE.test(wrapped.data?.code || wrapped.message || "")
      ? (wrapped.data?.code || wrapped.message) : "invalid_response"), {confirmed:true});
    const value = wrapped ? wrapped.data : response;
    if (!value || typeof value !== "object") throw problem("invalid_response");
    return value;
  }
  function live(ticket) { return ticket === version && root?.isConnected; }
  function notice(message, error = false) { data.notice = message; data.error = error; }

  /* ---- 读 ------------------------------------------------------------- */
  async function load() {
    if (!data.nativePath || data.busy) return;
    const ticket = version;
    data.loading = true; render();
    try {
      const payload = await api("GET", data.nativePath);
      const status = payload.contact;
      if (!live(ticket)) return;
      if (!status?.settings || typeof status.settings !== "object") throw problem("invalid_response");
      const effective = status.effective;
      if (!effective || typeof effective !== "object"
          || typeof effective.allowed !== "boolean"
          || typeof effective.automatic_allowed !== "boolean") throw problem("invalid_response");
      data.settings = status.settings;
      data.effective = effective;
      data.purposes = status.purposes && typeof status.purposes === "object" ? status.purposes : {};
      data.hostState = typeof status.host_state === "string" ? status.host_state : "";
      data.editToken = typeof status.edit_token === "string" ? status.edit_token : "";
      data.ready = true; data.scanning = true;
      /* 成功读到一份新的联系快照后，旧的网络/保存错误已经没有继续
         挂在页面上的意义；保存成功提示（error=false）仍然保留。 */
      if (data.error) { data.notice = ""; data.error = false; }
    } catch (error) {
      if (!live(ticket)) return;
      data.settings = null; data.effective = null; data.purposes = {}; data.editToken = "";
      data.ready = false;
      notice(error.code ? reason(error.code) : "连接中断，已清空旧内容。请刷新核对。", true);
    } finally {
      if (live(ticket)) {
        data.loading = false; data.busy = false; render();
        if (data.ready && data.pendingWrite) schedulePendingRecovery(ticket);
      }
    }
  }
  /* 配置侧只要 edit_token 与字段契约——值仍旧从 native 那份读，
     两处读出的值必须一致，不一致就说明两端读的不是同一层。 */
  async function loadContract() {
    if (!data.configPath || data.contractLoading) return;
    const ticket = version;
    data.configToken = "";
    data.contractLoading = true;
    render();
    try {
      const payload = await api("GET", data.configPath, {sections: GROUP});
      if (!live(ticket)) return;
      const section = payload?.sections?.[GROUP];
      if (!section || typeof section !== "object"
          || typeof section.edit_token !== "string" || !section.edit_token) throw problem("invalid_response");
      data.configToken = section.edit_token;
      data.contractError = "";
      data.contractErrorCode = "";
    } catch (error) {
      if (live(ticket)) {
        data.contractErrorCode = typeof error.code === "string" ? error.code : "";
        data.contractError = data.ready
          ? "联系状态已读取；配置编辑信息未读到，保存暂不可用。"
          : "配置编辑信息未能读取，请稍后重试。";
      }
    } finally {
      if (live(ticket)) { data.contractLoading = false; render(); }
    }
  }
  async function loadMaterials() {
    if (!data.nativePath || data.materialsLoading) return;
    const ticket = version;
    data.materialsLoading = true;
    data.materialsError = "";
    render();
    try {
      const payload = await api("GET", data.nativePath + "/materials");
      if (!live(ticket)) return;
      if (!Array.isArray(payload?.items)) throw problem("invalid_response");
      data.materialItems = payload.items.filter(item => item && typeof item === "object"
        && typeof item.id === "string" && typeof item.title === "string");
      data.materialsLoaded = true;
    } catch (error) {
      if (!live(ticket)) return;
      data.materialItems = [];
      data.materialsLoaded = false;
      data.materialsError = error.code ? reason(error.code) : "素材暂时无法读取，请重试。";
    } finally {
      if (live(ticket)) { data.materialsLoading = false; render(); }
    }
  }
  /* ---- 写 -------------------------------------------------------------
     只提交 touched 里的字段。edit_token 必须用**刚刚读到的那一份**：
     配置页的令牌与 native 的令牌是两个生效范围，不能互相顶替
     （native 那条路由只写 news 六个字段，其余交给 config 段）。 */
  async function save() {
    if (!data.configPath || data.busy || (!data.pendingWrite && !data.touched.size)) return;
    if (!data.ready) { notice("还没有读到当前设置，不能保存。", true); render(); return; }
    if (!data.configToken && !data.pendingWrite) { notice("缺少配置令牌，请重新读取后再保存。", true); render(); return; }
    const ticket = version;
    data.busy = true;
    let pending = data.pendingWrite;
    let changes = pending?.body?.changes || {};
    if (!pending) {
      changes = {};
      for (const name of data.touched) if (name in data.draft) changes[name] = data.draft[name];
      pending = {route:data.configPath + "/configure", body:{
        section:GROUP, operation_key:operationKey(), edit_token:data.configToken, changes,
      }};
      data.pendingWrite = pending;
      if (!storePendingWrite()) {
        data.pendingWrite = null;
        data.busy = false;
        notice("当前浏览器无法安全记录这次保存请求，尚未提交。请检查页面存储后重试。", true);
        render();
        return;
      }
    }
    try {
      const payload = await api("POST", pending.route, pending.body);
      if (!live(ticket)) return;
      const receipt = payload?.result ?? payload;
      if (typeof receipt?.operation_id !== "string" || typeof receipt?.replayed !== "boolean") {
        throw problem("invalid_response");
      }
      const status = payload?.status?.sections?.[GROUP];
      const hasFreshConfigToken = typeof status?.edit_token === "string" && status.edit_token.length === 64;
      if (hasFreshConfigToken) {
        data.editToken = status.edit_token;
        data.configToken = data.editToken;
      }
      data.pendingWrite = null; storePendingWrite();
      clearPendingRecovery(pending.body.operation_key);
      data.touched.clear(); data.draft = {}; data.tierDraft = null;
      data.savedAt = Date.now(); data.busy = false;
      const savedNotice = "已保存 " + Object.keys(changes).length + " 项。改动从下一轮主动评估开始生效。";
      notice(savedNotice);
      await load();
      if (live(ticket) && !hasFreshConfigToken) await loadContract();
      if (live(ticket)) {
        const refreshed = data.ready;
        notice(refreshed ? savedNotice : "已保存 " + Object.keys(changes).length + " 项，但当前状态未能刷新；请稍后重新读取。", !refreshed);
        render();
      }
    } catch (error) {
      if (!live(ticket)) return;
      data.busy = false;
      const code = error.code || "";
      if (error.confirmed) {
        data.pendingWrite = null; storePendingWrite();
        clearPendingRecovery(pending?.body?.operation_key);
      }
      const unresolved = !!data.pendingWrite && !error.confirmed;
      notice(unresolved ? recoveryFailure(code) : reason(code), true);
      if (["configuration_revision_conflict", "proactive_contact_revision_conflict",
        "proactive_contact_target_changed"].includes(code)) {
        data.touched.clear(); data.draft = {}; data.tierDraft = null;
        await load();
        await loadContract();
        if (live(ticket) && !data.error) {
          notice("设置已有其他更新，已读取最新值。", false);
          render();
        }
      } else {
        /* notice() 只改状态；失败路径必须主动重画，否则用户点保存后
           看不到任何反馈，直到下一次切页或别的控件触发 render。 */
        render();
        if (data.pendingWrite) schedulePendingRecovery(ticket);
      }
    }
  }
  /* 幂等键：同一份草稿重复提交沿用同一个键，后端按 operation_key 去重，
     网络重试不会写成两次。键里带 native 路由（每个角色一套），
     所以不同角色不会撞到同一个键上。 */
  let opCounter = 0;
  function operationKey() {
    return STORE + data.nativePath + ":" + (data.savedAt || 0) + ":" + opCounter++;
  }
  function set(name, value) {
    if (data.pendingWrite) return;
    data.draft[name] = value; data.touched.add(name);
    if (name === "proactive_intensity_preset") data.tierDraft = tierOf(value);
    const part = PULSE_PART[name];
    if (part) data.pulse.add(part);
  }
  function resetDraft() { if (data.pendingWrite) return; data.touched.clear(); data.draft = {}; data.tierDraft = null; render(); }
  /* 这一帧要不要给这个开关播翻转动画、播哪个方向。
     方向由 flipNow 记述，这里只翻译成类，不改动词义。 */
  function flipClass(name) {
    const flip = data.flipNow;
    if (!flip || flip.name !== name) return "";
    return flip.on ? " is-flip-on" : " is-flip-off";
  }
  function dirty(name) { return data.touched.has(name); }

  /* ---- 此刻 -------------------------------------------------------------
     环心那句话必须与后端同源：能不能开口看 effective，具体卡在哪一条看
     purposes 的 reason。页面不自己推断「现在几点了应该在免打扰里吗」——
     时区在服务端，页面上的时钟是访客的钟，两者经常不是同一个。 */
  function currentMinute() {
    const zone = value("quiet_timezone");
    if (typeof zone !== "string" || !zone.trim()) return null;
    try {
      const parts = new Intl.DateTimeFormat("en-GB", {timeZone:zone, hour:"2-digit", minute:"2-digit",
        hour12:false}).formatToParts(new Date());
      const h = Number(parts.find(p => p.type === "hour")?.value);
      const m = Number(parts.find(p => p.type === "minute")?.value);
      return Number.isFinite(h) && Number.isFinite(m) ? h * 60 + m : null;
    } catch { return null; }
  }
  function quietSpan() {
    const from = minutes(value("quiet_start")), to = minutes(value("quiet_end"));
    if (from === null || to === null) return null;
    return {from, to};
  }
  function inQuiet(minute) {
    const span = quietSpan();
    if (span === null || !value("quiet_enabled") || minute === null) return false;
    const {from, to} = span;
    return from > to ? (minute >= from || minute < to) : (minute >= from && minute < to);
  }
  function currentWeight(minute) {
    if (!value("proactive_hour_activity_enabled") || minute === null) return null;
    return curveOf(value("proactive_hour_activity_curve"))[Math.floor(minute / 60) % 24];
  }
  /* 环心状态。四档，顺序即优先级：
     后端说不允许 → 看它给的原因；后端说允许但此刻在免打扰 → 说免打扰；
     曲线权重低 → 说节律；否则说可开口。 */
  function verdict() {
    if (!data.ready || !data.settings || !data.effective) {
      return {tone:"blocked", title:"联系状态尚未读取", detail:"读取设置后再判断当前联系条件。", code:"", automatic:false};
    }
    const automatic = automaticNotice(data.effective);
    const minute = currentMinute();
    const blocked = data.effective && data.effective.allowed === false;
    if (blocked) {
      const code = data.effective.reason;
      return {tone:"blocked", title:"当前不会开口", detail:reason(code),
        code:code || "", automatic};
    }
    if (inQuiet(minute)) {
      return {tone:"quiet", title:"免打扰中", detail:quietSpanText(),
        code:"proactive_quiet_hours", automatic};
    }
    const weight = currentWeight(minute);
    if (weight !== null && weight < 0.3) {
      return {tone:"low", title:"节律低谷", detail:"这一小时的活动权重 " + weight.toFixed(2)
        + "，低于 0.30；这条曲线只删格子，不放宽额度。", code:"", automatic};
    }
    return {tone:"open", title:"此刻可以开口", detail:minute === null
      ? "未设时区，只能按服务端的判定。" : "本地时间 " + hm(minute) + "，不在免打扰内。",
      code:"", automatic};
  }
  function quietSpanText() {
    const span = quietSpan();
    if (span === null) return "免打扰时段未设完整。";
    return span.from > span.to
      ? hm(span.from) + " 至次日 " + hm(span.to) + " 不打扰"
      : hm(span.from) + " 至 " + hm(span.to) + " 不打扰";
  }

  /* ---- 环的绘制 ---------------------------------------------------------
     四圈半径固定，只有「哪一圈在编辑」会改变描边权重。
     这不是装饰：一天只有 24 格，四圈都画粗了就分不清哪圈是免打扰。 */
  const R = {quiet:132, curve:112, anchor:94, tier:76};
  function dialSVG() {
    const cx = 150, cy = 150, minute = currentMinute();
    const span = quietSpan();
    const live = value("quiet_enabled") && span;
    const weights = curveOf(value("proactive_hour_activity_curve"));
    const curveOn = !!value("proactive_hour_activity_enabled");
    const peak = curveOn ? Math.max(...weights, 0.05) : 1;
    /* 曲线画成 24 个柱子，围成一圈。柱高按峰值归一，但**保留 0.05 的下限高度**，
       否则权重 0.10 的凌晨会看起来是「没有这一格」。
       --i 是「到 0:00 的环形距离」，涟漪与改动波都按它排队：
       波前从正上方出发、两侧同时走，在 12:00 会合——按下标排就只有单向推进。 */
    const bars = weights.map((w, hour) => {
      const ratio = curveOn ? Math.max(0.05, w / peak) : 1;
      const inner = R.curve - 9, outer = R.curve + 9;
      const r = inner + (outer - inner) * ratio;
      const [x1, y1] = point(cx, cy, inner, hour * 60 + 1);
      const [x2, y2] = point(cx, cy, r, hour * 60 + 1);
      const hot = curveOn && w >= peak * 0.75;
      return `<line x1="${x1.toFixed(2)}" y1="${y1.toFixed(2)}" x2="${x2.toFixed(2)}" y2="${y2.toFixed(2)}"`
        + ` class="ct-bar${curveOn ? " is-on" : ""}${hot ? " is-peak" : ""}"`
        + ` style="--i:${Math.min(hour, 24 - hour)}" data-hour="${hour}"/>`;
    }).join("");
    /* 三圈十二个刻度：0/6/12/18 写数字，其余只点一下。 */
    const ticks = Array.from({length:24}, (_, hour) => {
      const [x1, y1] = point(cx, cy, R.quiet + 6, hour * 60);
      const [x2, y2] = point(cx, cy, R.quiet + (hour % 6 === 0 ? 14 : 10), hour * 60);
      const major = hour % 6 === 0;
      const label = major ? (() => {
        const [lx, ly] = point(cx, cy, R.quiet + 27, hour * 60);
        return `<text x="${lx.toFixed(1)}" y="${(ly + 4).toFixed(1)}" class="ct-tick-label">${hour}</text>`;
      })() : "";
      return `<line x1="${x1.toFixed(2)}" y1="${y1.toFixed(2)}" x2="${x2.toFixed(2)}" y2="${y2.toFixed(2)}"`
        + ` class="ct-tick${major ? " is-major" : ""}"/>${label}`;
    }).join("");
    /* 问候窗口：只有**启用每日问候**时才画。
       原先的判据是 `enable_daily_greetings || value("greeting_x_window")`，
       而后端对这九个字段都有默认值，所以右边恒为真——三个窗口在未启用时
       照样画在环上。那是在暗示一个并不存在的时刻：用户会以为早上七点四十五
       会收到问候，而实际上总开关是关的。画不出的东西就不画。 */
    const greetingsOn = value("enable_daily_greetings") === true;
    const anchors = greetingsOn ? ANCHORS.map(([name, , fallbackFrom, fallbackTo], index) => {
      const raw = value("greeting_" + name + "_window");
      const parts = typeof raw === "string" ? raw.split("-") : [];
      const from = minutes(parts[0]) ?? minutes(fallbackFrom);
      const to = minutes(parts[1]) ?? minutes(fallbackTo);
      /* 后端要求窗口当天内结束（不能跨午夜），所以 from > to 是坏值，不画。 */
      if (from === null || to === null || from >= to) return "";
      /* --a 是三条弧的序号：改动波按早/午/晚依次亮起，顺序就是一天的顺序。 */
      return `<g class="ct-anchor" data-anchor="${name}" style="--a:${index}">`
        + `${arc(cx, cy, R.anchor, from, to, 7)}</g>`;
    }).join("") : "";
    const insomnia = value("allow_insomnia_night_message")
      ? `<g class="ct-insomnia" style="--a:3">${arc(cx, cy, R.anchor - 11,
          minutes(value("insomnia_night_start")) ?? 1380, minutes(value("insomnia_night_end")) ?? 360, 3)}</g>` : "";
    /* 游标：一条从环心指出的细线，末端一个小圆。它随真实时间走，
       reduced-motion 下不做扫描动画，只停在当前角度。 */
    const cursor = minute === null ? "" : (() => {
      const [x, y] = point(cx, cy, R.quiet + 16, minute);
      const [ix, iy] = point(cx, cy, 30, minute);
      return `<line class="ct-cursor-line" x1="${ix.toFixed(2)}" y1="${iy.toFixed(2)}"`
        + ` x2="${x.toFixed(2)}" y2="${y.toFixed(2)}"/>`
        + `<circle class="ct-cursor-dot" cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="3.6"/>`;
    })();
    return `<svg viewBox="0 0 300 300" class="ct-dial${data.scanning ? " is-scanning" : ""}"
      role="img" aria-label="${e(dialLabel(minute))}" data-role="dial">
      <circle cx="${cx}" cy="${cy}" r="${R.quiet}" class="ct-ring-base"/>
      <g class="ct-quiet${live ? " is-on" : ""}">${live ? arc(cx, cy, R.quiet, span.from, span.to, 10) : ""}</g>
      <g class="ct-bars">${bars}</g>
      ${anchors}${insomnia}${ticks}${cursor}
    </svg>`;
  }
  function dialLabel(minute) {
    return "一天的节律：免打扰" + (value("quiet_enabled") ? quietSpanText() : "未启用")
      + "；活动曲线" + (value("proactive_hour_activity_enabled") ? "已启用" : "未启用")
      + "；当前" + (minute === null ? "未设时区" : hm(minute) + " 时");
  }

  /* ---- 渲染 ------------------------------------------------------------ */
  const VIEWS = [["dial","节律盘",ICON.dial],["tests","消息测试",ICON.test],
                 ["purposes","契机矩阵",ICON.seed],
                 ["gates","开口闸门",ICON.gate],["budgets","额度与去重",ICON.quota],
                 ["sources","外部触发源",ICON.source],["materials","素材池",ICON.seed]];
  function headMarkup() {
    const v = verdict();
    const label = VIEWS.find(([id]) => id === data.view)?.[1] || "节律盘";
    const dirtyCount = data.touched.size;
    return `<header class="ct-head">
      <div class="ct-head-main">
        <h2>${e(label)}</h2>
        <span class="ct-verdict is-${v.tone}"><i class="ct-dot"></i>${e(v.title)}</span>
      </div>
      <div class="ct-head-actions">
        <button type="button" class="ct-btn ct-head-test" data-view="tests" aria-pressed="${data.view === "tests"}"
          title="打开消息测试">${ICON.test}<span>消息测试</span></button>
        ${dirtyCount && !data.pendingWrite ? `<button type="button" class="ct-btn" data-action="reset">${ICON.undo}<span>放弃 ${dirtyCount} 项改动</span></button>` : ""}
        ${data.pendingWrite ? "" : dirtyCount
          ? `<button type="button" class="ct-btn is-primary" data-action="save"${data.busy || data.contractLoading || !data.configToken ? " disabled" : ""}>${ICON.save}<span>保存</span></button>`
          : `<button type="button" class="ct-btn" data-action="refresh"${data.loading || data.busy || data.contractLoading ? " disabled" : ""}>${ICON.refresh}<span>重新读取</span></button>`}
      </div>
    </header>`;
  }
  function railMarkup() {
    return `<nav class="ct-rail" aria-label="联系工作台">${VIEWS.map(([id, text, icon]) =>
      `<button type="button" data-view="${id}" aria-pressed="${data.view === id}"`
      + `${data.view === id && data.viewShiftNow ? ' class="is-picked"' : ""}>
        <span class="ct-rail-icon">${icon}</span><span class="ct-rail-label">${e(text)}</span></button>`).join("")}</nav>`;
  }
  function noticeMarkup() {
    const notices = [];
    if (data.pendingWrite) {
      const pendingText = data.busy
        ? "保存请求处理中；系统会核对原操作结果。"
        : "保存结果尚未确认；系统会持续沿用同一操作标识核对，不会重复写入。";
      notices.push(`<div class="ct-notice is-error" role="status">${ICON.alert}`
      + `<span>${pendingText}`
      + `${data.error && data.notice ? `<small>${e(data.notice)}</small>` : ""}</span>`
      + `<button type="button" class="ct-notice-retry" data-action="retry-pending"`
      + `${data.busy || data.loading || !data.ready ? " disabled" : ""}>${ICON.refresh}`
      + `<span>${data.busy ? "处理中" : "立即核对"}</span></button></div>`);
    } else if (data.notice) notices.push(`<p class="ct-notice${data.error ? " is-error" : ""}" role="status">${data.error ? ICON.alert : ICON.check}`
      + `<span>${e(data.notice)}</span><button type="button" data-action="dismiss" aria-label="关闭">×</button></p>`);
    if (data.contractError) {
      const message = data.contractLoading
        ? "正在重新读取配置编辑信息；当前输入会保留。" : data.contractError;
      const detail = data.contractErrorCode ? ` title="接口错误码：${e(data.contractErrorCode)}"` : "";
      notices.push(`<p class="ct-notice is-error" role="status">${ICON.alert}`
        + `<span${detail}>${e(message)}</span><button type="button" class="ct-notice-retry" data-action="retry-contract"${data.contractLoading ? " disabled" : ""}>${ICON.refresh}<span>${data.contractLoading ? "读取中" : "重试"}</span></button></p>`);
    }
    return notices.join("");
  }
  function emptyMarkup() {
    if (data.loading) return `<div class="ct-empty"><span class="ct-spinner"></span>正在读取联系设置…</div>`;
    if (!data.nativePath) return `<div class="ct-empty">${ICON.alert}<strong>还没有可管理的私聊对象</strong>
      <p>请先选择已初始化的私聊对象与角色。</p></div>`;
    return `<div class="ct-empty">${ICON.alert}<strong>还没有读到设置</strong>
      <p>${e(data.notice || "请重新读取；若反复失败，先在账号与会话中确认 V2 已启动。")}</p>
      <button type="button" class="ct-btn" data-action="refresh">${ICON.refresh}<span>重新读取</span></button></div>`;
  }

  /* 节律盘视图。版式分两层：
     第一行是「盘面 + 三个总开关 + 免打扰」——这几项一改就立刻改变盘面几何，
     放在同一行才能做到「改完不用滚动就看见环变了」。
     下面一层（活动曲线 / 强度档位 / 问候窗口）铺满整页宽：
     它们本来就是「按一天铺开的数据」，24 根柱子要的是横向空间，
     挤进右栏只会把每根柱子压到十来像素。
     控件顺序按「改了会立刻改变环的哪一圈」排，不按字段在注册表里的顺序。 */
  function dialView() {
    const span = quietSpan();
    const tier = TIER_BY_KEY[data.tierDraft || tierOf(value("proactive_intensity_preset"))];
    const v = verdict();
    const interval = Number(value("interval_seconds"));
    const idle = Number(value("idle_seconds"));
    const effectiveInterval = Number.isFinite(interval) && interval > 0
      ? Math.max(1, Math.round(interval * tier.interval)) : null;
    const effectiveIdle = Number.isFinite(idle)
      ? Math.max(0, Math.round(idle * tier.idle)) : null;
    /* 这一帧要闪哪几片盘面。取出来就清空：动效只放一次，
       下一次渲染（哪怕什么都没改）不该重放。 */
    const pulse = data.pulseNow;
    return `<div class="ct-dial-wrap">
      <div class="ct-dial-stage${pulse.map(part => " is-pulse-" + part).join("")}">${dialSVG()}
        <div class="ct-center is-${v.tone}">
          <span class="ct-center-title">${e(v.title)}</span>
          <span class="ct-center-detail">${e(v.detail)}</span>
          ${["authorization_denied", "configuration_relationship_required"].includes(v.code)
            ? `<button type="button" class="ct-center-action" data-go="manage" data-manage="identity" aria-label="前往关系与权限，核对主动联系授权">前往关系与权限</button>` : ""}
          ${v.automatic ? `<span class="ct-center-flag">${ICON.alert}${e(v.automatic.text)}</span>` : ""}
        </div>
        ${data.scanning ? `<div class="ct-scan-hint">时间游标按 ${e(value("quiet_timezone") || "未设时区")} 走</div>` : ""}
      </div>
      <div class="ct-controls">
        ${fieldBlock("总开关", [
          toggle("enabled", "允许主动联系", "关闭时下面每一类契机都不会开口。"),
          toggle("automatic_enabled", "后台自动联系", "关闭后只有你自己触发的联系会发出，后台不再自行决定开口。"),
        ])}
        ${fieldBlock("免打扰 · 外圈", [
          toggle("quiet_enabled", "启用免打扰时段", "免打扰只决定「现在不开口」，不改动已登记的日程。"),
          timeRow("quiet_start", "开始", "quiet_end", "结束", span && span.from > span.to ? "跨午夜：" + hm(span.from) + " 至次日 " + hm(span.to) : ""),
          textRow("quiet_timezone", "时区", "Asia/Shanghai", "环上游标与免打扰判定都用这个时区。"),
        ], "is-ring-quiet")}
      </div></div>
    <div class="ct-rest">
      ${fieldBlock("活动曲线 · 次圈", [
        toggle("proactive_hour_activity_enabled", "按小时权重开口", "启用后这条曲线只会删掉落在低谷的格子，不放宽任何额度。"),
        curveEditor(),
      ], "is-wide is-ring-curve")}
      ${fieldBlock("强度档位 · 三圈", [
        tierPicker(tier),
        `<div class="ct-tier-effective" role="status" aria-live="polite">
          <span>当前生效</span>
          <strong>${effectiveInterval === null ? "—" : e(fmtDuration(effectiveInterval))}</strong>
          <small>两次联系至少间隔</small>
          <strong>${effectiveIdle === null ? "—" : e(fmtDuration(effectiveIdle))}</strong>
          <small>对话结束后至少等候</small>
        </div>`,
        numberRow("interval_seconds", "两次联系至少间隔（基础值）", "秒", 60, 604800,
          interval ? "当前档位实际约 " + fmtDuration(effectiveInterval) : ""),
        numberRow("idle_seconds", "对话结束后至少等候（基础值）", "秒", 0, 86400,
          idle !== undefined && Number.isFinite(idle) ? "当前档位实际约 " + fmtDuration(effectiveIdle) : ""),
      ], "is-ring-tier")}
      ${fieldBlock("问候窗口 · 内圈", [
        toggle("enable_daily_greetings", "启用每日问候", "三个窗口必须当天内结束，不能跨午夜。"),
        ...ANCHORS.map(([name, , from, to]) => textRow("greeting_" + name + "_window",
          {morning:"早间", noon:"午间", evening:"晚间"}[name], from + "-" + to, "形如 " + from + "-" + to)),
        toggle("allow_insomnia_night_message", "允许深夜一条", "深夜窗口显式有界，并按日限额。"),
      ], "is-ring-greet")}
    </div>`;
  }
  function fmtDuration(seconds) {
    if (!Number.isFinite(seconds)) return "—";
    if (seconds < 60) return seconds + " 秒";
    if (seconds < 3600) return (seconds / 60).toFixed(seconds % 60 ? 1 : 0) + " 分钟";
    return (seconds / 3600).toFixed(seconds % 3600 ? 1 : 0) + " 小时";
  }
  /* extra 只用来挂「这一块管哪一圈」的语义类（is-ring-*）与跨栏（is-wide），
     不改变块的内部结构——块里放什么仍由调用方逐个写出，看得见字段名。 */
  function fieldBlock(title, body, extra) {
    return `<section class="ct-block${extra ? " " + extra : ""}"><h3>${e(title)}</h3>${body.join("")}</section>`;
  }
  function toggle(name, label, help) {
    const on = value(name) === true;
    return `<label class="ct-switch${dirty(name) ? " is-dirty" : ""}${flipClass(name)}">
      <input type="checkbox" data-field="${e(name)}"${on ? " checked" : ""}>
      <span class="ct-switch-track"><i></i></span>
      <span class="ct-switch-text"><strong>${e(label)}</strong><small>${e(help)}</small></span></label>`;
  }
  function textRow(name, label, placeholder, help) {
    const current = value(name);
    return `<label class="ct-field${dirty(name) ? " is-dirty" : ""}">
      <span class="ct-field-label">${e(label)}</span>
      <input type="text" data-field="${e(name)}" value="${e(typeof current === "string" ? current : "")}"
        placeholder="${e(placeholder)}" autocomplete="off" spellcheck="false">
      ${help ? `<small class="ct-field-help">${e(help)}</small>` : ""}</label>`;
  }
  function timeRow(nameA, labelA, nameB, labelB, help) {
    const a = value(nameA), b = value(nameB);
    return `<div class="ct-field-pair${dirty(nameA) || dirty(nameB) ? " is-dirty" : ""}">
      <label class="ct-field"><span class="ct-field-label">${e(labelA)}</span>
        <input type="time" data-field="${e(nameA)}" value="${e(typeof a === "string" ? a : "")}"></label>
      <label class="ct-field"><span class="ct-field-label">${e(labelB)}</span>
        <input type="time" data-field="${e(nameB)}" value="${e(typeof b === "string" ? b : "")}"></label>
      ${help ? `<small class="ct-field-help">${e(help)}</small>` : ""}</div>`;
  }
  function numberRow(name, label, unit, min, max, help) {
    const current = value(name);
    return `<label class="ct-field ct-field-number${dirty(name) ? " is-dirty" : ""}">
      <span class="ct-field-label">${e(label)}<small>${e(min)}–${e(max)}</small></span>
      <span class="ct-input-unit"><input type="number" data-field="${e(name)}" value="${e(current ?? "")}"
        min="${min}" max="${max}" step="1" inputmode="numeric"><i>${e(unit)}</i></span>
      ${help ? `<small class="ct-field-help">${e(help)}</small>` : ""}</label>`;
  }
  /* 强度档位是一个**控件**，不是下拉：五档的差别是「更快 / 更多」，而这句话
     只有并排画出来才成立。选中的档位给一条随档位变长的底条。 */
  function tierPicker(tier) {
    const interval = Number(value("interval_seconds"));
    const idle = Number(value("idle_seconds"));
    return `<div class="ct-tiers" role="radiogroup" aria-label="强度档位">
      ${TIERS.map(t => {
        const on = t.key === tier.key;
        const effectiveInterval = Number.isFinite(interval) && interval > 0
          ? fmtDuration(Math.max(1, Math.round(interval * t.interval))) : "—";
        const effectiveIdle = Number.isFinite(idle)
          ? fmtDuration(Math.max(0, Math.round(idle * t.idle))) : "—";
        return `<button type="button" role="radio" aria-checked="${on}" data-tier="${t.key}"
          class="ct-tier${on ? " is-on" : ""}${dirty("proactive_intensity_preset") ? " is-dirty" : ""}"
          title="间隔 ×${t.interval}　等候 ×${t.idle}">
          <span class="ct-tier-bar" style="--fill:${(1 - t.interval) * 100}%"></span>
          <span class="ct-tier-label">${e(t.label)}</span>
          <span class="ct-tier-meta">间隔 ×${t.interval}</span>
          <span class="ct-tier-effective">约 ${e(effectiveInterval)} · 等候 ${e(effectiveIdle)}</span>
        </button>`;
      }).join("")}
    </div>`;
  }
  /* 24 小时曲线编辑器。画法和环一样，但这里是**可直接涂的**：
     按住横向拖过若干小时就改成那个高度。这比让用户改 24 个数字现实。
     下面再给一个文本口——拖涂只有指针设备能用，键盘用户否则完全改不了这一项，
     而它是这一页唯一一个「一天 24 格」的原始数据。 */
  function curveEditor() {
    const weights = curveOf(value("proactive_hour_activity_curve"));
    const on = !!value("proactive_hour_activity_enabled") || dirty("proactive_hour_activity_curve");
    const rows = weights.map((w, hour) => {
      const percent = Math.round((w / 2) * 100);
      return `<span class="ct-curve-col" data-hour="${hour}" title="${String(hour).padStart(2,"0")}:00 · 权重 ${w.toFixed(2)}">
        <i style="height:${percent}%"></i></span>`;
    }).join("");
    return `<div class="ct-curve${on ? " is-on" : ""}" data-role="curve">
      <div class="ct-curve-plot" data-role="curvePlot" role="group"
        aria-label="24 小时活动权重，0 时到 23 时">${rows}</div>
      <div class="ct-curve-axis">${[0,6,12,18].map(h => `<span style="--at:${(h / 24) * 100}%">${h}:00</span>`).join("")}</div>
      <div class="ct-curve-actions">
        <button type="button" class="ct-btn is-quiet" data-action="curve-default">${ICON.undo}<span>恢复默认曲线</span></button>
        <button type="button" class="ct-btn is-quiet" data-action="curve-flat">拉平</button>
      </div>
      <label class="ct-field ct-curve-text${dirty("proactive_hour_activity_curve") ? " is-dirty" : ""}">
        <span class="ct-field-label">按小时填写<small>0 时 → 23 时，逗号分隔</small></span>
        <textarea data-field="proactive_hour_activity_curve" data-role="curveText" rows="2"
          spellcheck="false" placeholder="${e(DEFAULT_CURVE)}">${e(curveText(weights))}</textarea>
      </label></div>`;
  }

  /* 契机矩阵视图：15 类契机 × 三列（开关 / 权重 / 暂缓）。
     权重不是数字输入而是**条形**——权重是相对值，绝对值没有意义，
     一列里并排画出来才知道谁是「主要的开口理由」。 */
  function purposesView() {
    const rows = PURPOSE_BUCKETS.map(bucket => {
      const items = bucket.purposes.map(([name, label]) => purposeRow(name, label));
      return `<section class="ct-bucket${bucket.id === "share" ? " is-wide" : ""}" data-purpose-bucket="${bucket.id}"><header>
          <h3>${e(bucket.label)}</h3><span>${e(bucket.hint)}</span>
          <em data-purpose-bucket-count="${bucket.id}">${bucket.purposes.length}/${bucket.purposes.length} 类</em></header>
        <div class="ct-purpose-list">${items.join("")}</div></section>`;
    }).join("");
    const enabled = ALL_PURPOSES.filter(([name]) => value(name + ".enabled") !== false).length;
    const allowed = ALL_PURPOSES.filter(([name]) => purposeStatus(name) === "available").length;
    const paused = ALL_PURPOSES.filter(([name]) => purposeStatus(name) === "paused").length;
    return `<div class="ct-purposes">
      <div class="ct-purposes-summary" aria-label="契机概况">
        <div class="ct-purpose-stat"><strong>${ALL_PURPOSES.length}</strong><span>类契机</span></div>
        <div class="ct-purpose-stat"><strong>${enabled}</strong><span>单项已开启</span></div>
        <div class="ct-purpose-stat"><strong>${allowed}</strong><span>当前可开口</span></div>
        <div class="ct-purpose-stat"><strong>${paused}</strong><span>暂缓中</span></div>
      </div>
      <div class="ct-purpose-tools">
        <label class="ct-purpose-search"><span>查找</span>
          <input type="search" data-purpose-search aria-label="搜索契机名称或限制原因"
            value="${e(data.purposeQuery)}" placeholder="名称、类别或限制原因">
        </label>
        <label class="ct-purpose-filter"><span>类别</span>
          <select data-purpose-bucket-filter aria-label="按契机类别筛选">
            <option value="all"${data.purposeBucket === "all" ? " selected" : ""}>全部类别</option>
            ${PURPOSE_BUCKETS.map(bucket => `<option value="${bucket.id}"${data.purposeBucket === bucket.id ? " selected" : ""}>${e(bucket.label)}</option>`).join("")}
          </select>
        </label>
        <label class="ct-purpose-filter"><span>当前状态</span>
          <select data-purpose-filter aria-label="按当前状态筛选">
            ${[["all","全部状态"],["enabled","单项已开启"],["disabled","单项已关闭"],
              ["available","当前可开口"],["paused","暂缓中"],["unavailable","当前不可开口"]]
              .map(([key, label]) => `<option value="${key}"${data.purposeFilter === key ? " selected" : ""}>${label}</option>`).join("")}
          </select>
        </label>
        <span class="ct-purpose-results" data-purpose-result-count>${ALL_PURPOSES.length} / ${ALL_PURPOSES.length} 类</span>
      </div>
      <div class="ct-purpose-groups">${rows}</div>
      <p class="ct-purpose-empty" hidden>没有匹配的契机</p>
    </div>`;
  }
  function testInstructionText(item) {
    return [
      `这是一条「${item.label}」主动联系候选。`,
      `素材来源：${item.source}`,
      `样例准备：${item.setup}`,
      "只使用本次提供的已核验素材，不把候选摘要当事实，不推断对方情绪、行程或需要。没有自然且值得发送的内容时返回 skip。",
      `类型要求：${item.instruction}`,
      "若发送，保持当前角色口吻，正文简短、不索取回复、不提测试或内部流程；严格遵守通用 JSON 合同，并给出 decision_confidence。",
      `通过条件：${item.expect}`,
    ].join("\n");
  }
  function testsView() {
    const counts = Object.fromEntries(["ready", "partial", "missing"].map(coverage => [
      coverage, TEST_INSTRUCTIONS.filter(item => item.coverage === coverage).length,
    ]));
    const cards = TEST_INSTRUCTIONS.map(item => `<article class="ct-test-card"
      data-test-card data-test-id="${e(item.id)}" data-test-bucket="${TEST_BUCKET_IDS[item.bucket]}"
      data-test-coverage="${e(item.coverage)}">
      <header class="ct-test-card-head">
        <div class="ct-test-title"><code>${e(item.id)}</code><h3>${e(item.label)}</h3></div>
        <span class="ct-test-coverage is-${e(item.coverage)}">${e(TEST_COVERAGE[item.coverage])}</span>
      </header>
      <dl class="ct-test-details">
        <div><dt>测试素材</dt><dd>${e(item.source)}</dd></div>
        <div><dt>样例准备</dt><dd>${e(item.setup)}</dd></div>
      </dl>
      <section class="ct-test-prompt"><h4>类型指令</h4><p>${e(item.instruction)}</p></section>
      <p class="ct-test-expect"><strong>通过条件</strong>${e(item.expect)}</p>
      <footer class="ct-test-actions"><button type="button" class="ct-btn ct-test-copy"
        data-test-copy="${e(item.id)}">${ICON.copy}<span>复制测试指令</span></button></footer>
    </article>`).join("");
    return `<div class="ct-tests">
      <div class="ct-test-overview">
        <p>15 类主动消息各有独立的素材准备、类型指令和验收条件。</p>
        <div class="ct-test-coverage-summary" aria-label="生产器覆盖情况">
          <span><i class="is-ready"></i>生产器已接通 <strong>${counts.ready}</strong></span>
          <span><i class="is-partial"></i>只有资格检查 <strong>${counts.partial}</strong></span>
          <span><i class="is-missing"></i>尚无独立生产器 <strong>${counts.missing}</strong></span>
        </div>
        <p class="ct-test-boundary">复制只生成测试文本，不调用模型，也不向真实会话投递。</p>
      </div>
      <div class="ct-test-tools">
        <label class="ct-test-search"><span>查找类型</span>
          <input type="search" data-test-search aria-label="搜索主动消息类型和测试指令"
            value="${e(data.testQuery)}" placeholder="名称、素材、指令或验收条件">
        </label>
        <label><span>消息类别</span><select data-test-bucket-filter aria-label="按消息类别筛选">
          <option value="all"${data.testBucket === "all" ? " selected" : ""}>全部类别</option>
          <option value="bond"${data.testBucket === "bond" ? " selected" : ""}>关系</option>
          <option value="daily"${data.testBucket === "daily" ? " selected" : ""}>日程</option>
          <option value="share"${data.testBucket === "share" ? " selected" : ""}>分享</option>
        </select></label>
        <label><span>生产器状态</span><select data-test-coverage-filter aria-label="按生产器状态筛选">
          <option value="all"${data.testCoverage === "all" ? " selected" : ""}>全部状态</option>
          <option value="ready"${data.testCoverage === "ready" ? " selected" : ""}>生产器已接通</option>
          <option value="partial"${data.testCoverage === "partial" ? " selected" : ""}>只有资格检查</option>
          <option value="missing"${data.testCoverage === "missing" ? " selected" : ""}>尚无独立生产器</option>
        </select></label>
        <span class="ct-test-result-count" data-test-result-count>${TEST_INSTRUCTIONS.length} / ${TEST_INSTRUCTIONS.length} 类</span>
      </div>
      <div class="ct-tests-grid">${cards}</div>
      <p class="ct-test-empty" hidden>没有匹配的消息类型</p>
    </div>`;
  }
  function testMatches(id) {
    const item = TEST_INSTRUCTIONS.find(candidate => candidate.id === id);
    if (!item) return false;
    if (data.testBucket !== "all" && TEST_BUCKET_IDS[item.bucket] !== data.testBucket) return false;
    if (data.testCoverage !== "all" && item.coverage !== data.testCoverage) return false;
    const query = data.testQuery.trim().toLocaleLowerCase();
    if (!query) return true;
    return [item.id, item.label, item.bucket, item.source, item.setup, item.instruction,
      item.expect, TEST_COVERAGE[item.coverage]].join(" ").toLocaleLowerCase().includes(query);
  }
  function updateTestFilters() {
    if (!root?.querySelectorAll) return;
    const cards = Array.from(root.querySelectorAll("[data-test-card]"));
    if (!cards.length) return;
    let visible = 0;
    for (const card of cards) {
      const show = testMatches(card.dataset.testId);
      card.hidden = !show;
      if (show) visible++;
    }
    const result = root.querySelector("[data-test-result-count]");
    if (result) result.textContent = visible + " / " + TEST_INSTRUCTIONS.length + " 类";
    const empty = root.querySelector(".ct-test-empty");
    if (empty) empty.hidden = visible > 0;
  }
  function purposeStatus(name) {
    const info = data.purposes[name] || {};
    if (value(name + ".enabled") === false) return "disabled";
    if (value("enabled") === false) return "unavailable";
    if (info.reason === "proactive_paused") return "paused";
    if (info.allowed === true) return "available";
    if (info.allowed === false) return "unavailable";
    return "unknown";
  }
  function purposeRow(name, label) {
    const info = data.purposes[name] || {};
    const enabled = value(name + ".enabled") !== false;
    const weight = Number(value(name + ".weight"));
    const status = purposeStatus(name);
    const pauseUntil = [value(name + ".pause_until"), value("pause_until")]
      .filter(until => typeof until === "string" && Date.parse(until) > Date.now())
      .sort((a, b) => Date.parse(b) - Date.parse(a))[0];
    const blocked = info.allowed === false && status === "unavailable" && info.reason !== "proactive_disabled";
    const scale = Math.max(0, Math.min(5, Number.isFinite(weight) ? weight : 1));
    return `<article class="ct-purpose${blocked ? " is-blocked" : ""}${enabled ? " is-on" : ""}"
      data-purpose="${e(name)}">
      <label class="ct-check">
        <input type="checkbox" data-field="${e(name)}.enabled"${enabled ? " checked" : ""}>
        <span class="ct-check-box">${ICON.check}</span>
        <span class="ct-purpose-name">${e(info.label || label)}</span></label>
      <div class="ct-weight" title="相对权重 ${Number.isFinite(weight) ? weight.toFixed(2) : "—"}">
        <input type="range" min="0.1" max="5" step="0.1" data-field="${e(name)}.weight"
          value="${Number.isFinite(weight) ? weight : 1}" aria-label="${e(label)} 相对权重">
        <span class="ct-weight-fill" style="--w:${(scale / 5) * 100}%"></span>
        <em>${Number.isFinite(weight) ? weight.toFixed(1) : "—"}</em>
      </div>
      <div class="ct-purpose-state">
        ${status === "disabled" ? `<span class="ct-chip">已关闭</span>`
          : status === "paused" ? `<span class="ct-chip is-paused">${pauseUntil ? "暂缓至 " + e(pauseUntil.slice(0, 16).replace("T", " ")) : "暂缓中"}</span>`
          : status === "unavailable" ? value("enabled") === false
            ? `<span class="ct-chip is-risk">总开关关闭</span>`
            : `<span class="ct-chip is-risk" title="${e(reason(info.reason))}">${e(shortReason(info.reason))}</span>`
          : status === "available" ? `<span class="ct-chip is-ok">可开口</span>`
          : blocked
          ? `<span class="ct-chip is-risk" title="${e(reason(info.reason))}">${e(shortReason(info.reason))}</span>`
          : `<span class="ct-chip">待核对</span>`}
      </div>
    </article>`;
  }
  function purposeMatches(name) {
    const meta = PURPOSE_META[name], info = data.purposes[name] || {};
    const query = data.purposeQuery.trim().toLocaleLowerCase();
    if (data.purposeBucket !== "all" && meta.bucket.id !== data.purposeBucket) return false;
    if (query) {
      const searchable = [name, meta.label, meta.bucket.label, info.label, info.reason,
        info.reason ? reason(info.reason) : ""]
        .filter(Boolean).join(" ").toLocaleLowerCase();
      if (!searchable.includes(query)) return false;
    }
    switch (data.purposeFilter) {
      case "enabled": return value(name + ".enabled") !== false;
      case "disabled": return value(name + ".enabled") === false;
      case "available": return purposeStatus(name) === "available";
      case "paused": return purposeStatus(name) === "paused";
      case "unavailable": return purposeStatus(name) === "unavailable";
      default: return true;
    }
  }
  function updatePurposeFilters() {
    if (!root?.querySelectorAll) return;
    const rows = Array.from(root.querySelectorAll(".ct-purpose"));
    if (!rows.length) return;
    const visibleByBucket = Object.fromEntries(PURPOSE_BUCKETS.map(bucket => [bucket.id, 0]));
    let visible = 0;
    for (const row of rows) {
      const show = purposeMatches(row.dataset.purpose);
      row.hidden = !show;
      if (show) { visible++; visibleByBucket[PURPOSE_META[row.dataset.purpose].bucket.id]++; }
    }
    for (const bucket of PURPOSE_BUCKETS) {
      const section = root.querySelector('[data-purpose-bucket="' + bucket.id + '"]');
      if (section) section.hidden = visibleByBucket[bucket.id] === 0;
      const count = root.querySelector('[data-purpose-bucket-count="' + bucket.id + '"]');
      if (count) count.textContent = visibleByBucket[bucket.id] + "/" + bucket.purposes.length + " 类";
    }
    const result = root.querySelector("[data-purpose-result-count]");
    if (result) result.textContent = visible + " / " + ALL_PURPOSES.length + " 类";
    const empty = root.querySelector(".ct-purpose-empty");
    if (empty) empty.hidden = visible > 0;
  }
  function shortReason(code) {
    if (!code) return "受阻";
    const text = reason(code);
    return text.length > 14 ? text.slice(0, 13) + "…" : text;
  }

  /* 开口闸门视图：后端判定的顺序，一圈一圈往外。
     这一屏回答的是「为什么此刻不开口」，所以先把 effective 摆第一。 */
  function gatesView() {
    const v = verdict();
    const gates = [
      {id:"allowed", title:"联系授权", ok:data.effective?.allowed !== false, code:data.effective?.reason,
       note:"由身份与关系授权决定；关闭总开关会同时撤销这条授权。"},
      {id:"automatic", title:"后台自动联系", ok:data.effective?.automatic_allowed !== false,
       code:data.effective?.automatic_reason, note:"只影响后台自行决定的开口，不影响你主动触发的。"},
      {id:"model", title:"主动联系模型", ok:data.effective?.model_registered !== false, code:"model_task_unregistered",
       note:"未登记模型时，即使前两闸都开也不会生成内容。"},
      {id:"host", title:"角色运行", ok:data.hostState === "running", code:"host_not_running",
       note:"角色未运行时所有后台判定暂停。"},
      {id:"quiet", title:"免打扰时段", ok:!inQuiet(currentMinute()), code:"proactive_quiet_hours",
       note:quietSpanText()},
      {id:"curve", title:"小时活动曲线", ok:(() => { const w = currentWeight(currentMinute()); return w === null || w >= 0.3; })(),
       code:"", note:value("proactive_hour_activity_enabled") ? "当前小时权重决定这一格是否保留。" : "未启用，不做小时过滤。"},
      {id:"pause", title:"临时暂停", ok:!value("pause_until"), code:"proactive_paused",
       note:value("pause_until") ? "已暂缓至 " + String(value("pause_until")).slice(0, 16).replace("T", " ") : "未设暂停。"},
    ];
    const blocked = gates.filter(g => !g.ok).length;
    return `<div class="ct-gates">
      <p class="ct-gates-sum${blocked ? " is-shut" : " is-open"}">${blocked ? `有 <strong>${blocked}</strong> 道闸门此刻是关的` : "全部闸门此刻都是开的"}</p>
      ${gates.map((g, i) => `<article class="ct-gate${g.ok ? " is-ok" : " is-shut"}" style="--i:${i}">
        <span class="ct-gate-mark">${g.ok ? ICON.check : ICON.alert}</span>
        <div class="ct-gate-body"><strong>${e(g.title)}</strong>
          ${g.ok ? "" : `<small>${e(g.code ? reason(g.code) : g.note)}</small>`}</div>
        <span class="ct-gate-state">${g.ok ? "开" : "关"}</span></article>`).join("")}
      <section class="ct-gate-settings-brief" aria-label="回复与补看设置">
        <div class="ct-gate-settings-copy">
          <span class="ct-gate-settings-eyebrow">回复与补看</span>
          <h3>忙碌延迟、休息判定与醒后补看</h3>
          <p>这里查看当前判定，下面统一调整对应规则。</p>
        </div>
        <button type="button" class="ct-btn is-primary ct-gate-settings-button" data-action="open-gate-settings">
          ${ICON.gate}<span>调整开口闸门</span>
        </button>
      </section>
      <section class="ct-block ct-gate-pause"><h3>临时暂停</h3>
        <label class="ct-field${dirty("pause_until") ? " is-dirty" : ""}">
          <span class="ct-field-label">暂缓全部联系至<small>留空表示不暂停</small></span>
          <input type="datetime-local" data-field="pause_until"
            value="${e(datetimeLocal(value("pause_until")))}">
          <small class="ct-field-help">清空后继承上级暂停设置。</small></label>
        <label class="ct-field${dirty("note") ? " is-dirty" : ""}">
          <span class="ct-field-label">补充联系偏好</span>
          <textarea data-field="note" rows="3" placeholder="只是写进提示词的材料，不改变权限、频率或去重">${e(value("note") || "")}</textarea></label>
      </section></div>`;
  }
  /* datetime-local 只吃本地无时区的串；后端要的是带偏移的 UTC。
     这里的转换只为了display正确，提交前统一走 toIso。 */
  function datetimeLocal(value) {
    if (typeof value !== "string" || !value) return "";
    const at = new Date(value);
    if (!Number.isFinite(at.getTime())) return "";
    const pad = n => String(n).padStart(2, "0");
    return at.getFullYear() + "-" + pad(at.getMonth() + 1) + "-" + pad(at.getDate())
      + "T" + pad(at.getHours()) + ":" + pad(at.getMinutes());
  }
  function toIso(local) {
    if (typeof local !== "string" || !local) return "";
    const at = new Date(local);
    return Number.isFinite(at.getTime()) ? at.toISOString() : "";
  }

  /* 额度与去重：额度**没有读出口**，所以画成上限刻度而不是用量表。 */
  function budgetsView() {
    const num = name => { const n = Number(value(name)); return Number.isFinite(n) ? n : null; };
    const quota = [
      ["max_contacts_24h", "24 小时内最多联系", "次", 100],
      ["max_attempts_24h", "24 小时内最多尝试", "次", 1000],
      ["max_relationship_contacts_24h", "整段关系 · 24 小时联系", "次", 1000],
      ["max_relationship_attempts_24h", "整段关系 · 24 小时尝试", "次", 10000],
    ];
    const dedup = [
      ["dedup_enabled", "启用重复抑制"],
      ["dedup_last_message_enabled", "与上一条原文比对"],
      ["dedup_sent_window_minutes", "已发内容窗口（分钟）", 1440],
      ["dedup_last_message_window_minutes", "上一条窗口（分钟）", 1440],
      ["dedup_min_shared_tokens", "最少共有词数", 4],
      ["dedup_min_overlap_ratio", "最低重合比例", 1],
    ];
    return `<div class="ct-budgets">
      <section class="ct-block"><h3>每日额度</h3>
        <p class="ct-note">这几个数只有上限，没有实时读出口——所以画成刻度，不画成进度条。</p>

        ${quota.map(([name, label, unit, max]) => {
          const current = num(name);
          return `<div class="ct-quota${dirty(name) ? " is-dirty" : ""}">
            <div class="ct-quota-head"><strong>${e(label)}</strong>
              <span class="ct-quota-value"><b>${current === null ? "—" : current}</b><i>${e(unit)}</i></span></div>
            <input type="range" min="0" max="${max}" step="1" data-field="${e(name)}"
              value="${current ?? 0}" aria-label="${e(label)}">
            <div class="ct-quota-scale"><span>0</span><span>${max}</span></div>
            ${(name.startsWith("max_relationship") ? `<small class="ct-field-help">关系额度请在安装、角色或关系层设置。</small>` : "")}
          </div>`;
        }).join("")}
      </section>
      <section class="ct-block"><h3>重复抑制</h3>
        ${dedup.map(([name, label, max]) => {
          if (typeof max === "undefined") return toggle(name, label, "关闭后同一内容可能在窗口内重复发出。");
          const current = num(name);
          return `<div class="ct-quota${dirty(name) ? " is-dirty" : ""}">
            <div class="ct-quota-head"><strong>${e(label)}</strong>
              <span class="ct-quota-value"><b>${current === null ? "—" : current}</b></span></div>
            <input type="range" min="0" max="${max}" step="${max <= 4 ? 1 : max <= 100 ? 5 : 30}"
              data-field="${e(name)}" value="${current ?? 0}" aria-label="${e(label)}">
            <div class="ct-quota-scale"><span>0</span><span>${max}</span></div></div>`;
        }).join("")}
        ${textRow("dedup_policies", "启用的去重策略", "semantic,content_fingerprint,life_event,event_revision",
          "逗号分隔，不能重复。可选：semantic / event_anchor / event_revision / conversation_anchor / daily_slot / content_fingerprint / life_event。")}
      </section>
      <section class="ct-block is-wide"><h3>连发与收尾</h3>
        ${toggle("enable_proactive_burst", "允许连发", "连发只接着一条普通话题继续；提醒、预警、问候和分享不会拖着连发走。")}
        ${numberRow("proactive_burst_max_messages", "一轮最多几条", "条", 2, 3, "")}
        ${numberRow("proactive_burst_gap_min_seconds", "两条之间最少", "秒", 10, 600, "")}
        ${numberRow("proactive_burst_gap_max_seconds", "两条之间最多", "秒", 10, 900, "实际间隔由这一轮的联系标识决定，同一轮不会重掷。")}
        ${numberRow("proactive_closing_grace_minutes", "收尾静默时长", "分钟", 0, 240, "连续开口到这个数后会主动停一段，等你回应或静默结束。")}
        ${numberRow("proactive_closing_contacts_threshold", "触发收尾的连续条数", "条", 1, 10, "")}
        ${numberRow("proactive_share_probability", "分享类开口概率", "%", 0, 100, "只作用于「分享自己的生活」与「作品与阅读」；提醒、预警和天气各有自己的授权，不受这个数影响。")}
      </section></div>`;
  }

  /* 外部触发源：这些不是「一天」上的东西，是「素材从哪来」。
     所以单独一屏，按获取方式分组，每组一张卡片：图标 + 组名 + 「n/m 开启」，
     组内一行一件事（标签在左、控件在右）。
     分组没动过——分法是按「谁在决定素材」，改了分组名等于重写语义；
     改的只是画法：原来每个字段竖排三行（标签 / 控件 / 说明），
     一屏扫下去全是左对齐的灰标签，读不出哪一行是哪一项。
     wide 的三组条目最多（14 / 9 / 9 条），占满整行、组内分两栏，
     否则它们会把同一行的短卡片拉出一大块空白。 */
  function sourcesView() {
    const known = [
      {id:"weather", icon:ICON.weather, title:"天气", hint:"定时采样；只有突变超过阈值才开口。", body:[
        srcToggle("weather_checkin_enabled", "定时天气问候", "要等定时点。"),
        srcText("weather_checkin_time", "问候时刻", "08:30", "本地时间，二十四小时制。"),
        srcNumber("weather_sample_minutes", "采样间隔", "分钟", 10, 1440, ""),
        srcToggle("weather_change_enabled", "天气突变时联系", "变化幅度超过阈值时才开口。"),
        srcNumber("dedup_weather_window_minutes", "同内容不重复时长", "分钟", 0, 2880, "突变与预警都走 event_revision 去重。"),
      ]},
      {id:"weather-alert", icon:ICON.bell, title:"官方预警", hint:"预警由官方发布，这里只管转不转、多久看一次。", body:[
        srcToggle("official_weather_alert_enabled", "转发官方气象预警", "预警由官方发布，这里只管转不转、多久看一次。"),
        srcNumber("official_alert_poll_minutes", "轮询间隔", "分钟", 1, 1440, ""),
        srcSelect("official_alert_min_severity", "最低预警级别",
          [["","不限制（全部转发）"],["minor","蓝色 · 一般"],["moderate","黄色 · 较重"],
           ["severe","橙色 · 严重"],["extreme","红色 · 特别严重"]]),
      ]},
      {id:"news", icon:ICON.source, title:"资讯", hint:"资讯来源、每日热点与去重时长。", body:[
        srcToggle("news_share_enabled", "分享资讯", "自然分享亮点和感想；追问时再给来源与原文。分段沿用表达设置。"),
        srcNumber("news_check_interval_minutes", "检查间隔", "分钟", 15, 1440, ""),
        srcSelect("news_source_kind", "来源类型", [["host","默认数据源"],["url","自定地址"],["uid","平台标识"]]),
        srcText("news_source_uid", "来源标识", "", "与类型匹配填写。"),
        srcText("news_source_url", "来源地址", "", "与类型匹配填写。"),
        srcToggle("news_daily_hot_read_enabled", "每日热点", ""),
        srcText("news_hot_sources", "热点来源", "weibo,hackernews", "逗号分隔，可选 weibo / hackernews。"),
      ]},
      {id:"meal", icon:ICON.meal, title:"三餐与纪念日", hint:"饭点问候与重要日期的提前量。", body:[
        srcToggle("meal_checkin_enabled", "饭点问候", ""),
        srcText("meal_lunch_time", "午餐时刻", "12:00", ""),
        srcText("meal_dinner_time", "晚餐时刻", "18:00", ""),
        srcNumber("meal_care_followup_minutes", "饭后追问窗口", "分钟", 1, 240, "吃到一半问完就不追问了。"),
        srcToggle("date_checkin_enabled", "纪念日问候", ""),
        srcText("date_checkin_time", "问候时刻", "09:00", ""),
        srcNumber("important_date_lookahead_days", "提前几天开始留意", "天", 0, 30, "0 表示只在当天问候。"),
      ]},
      {id:"explore", icon:ICON.compass, title:"网络探索与自关联", hint:"她自己去网上找素材，并把外部事件关联回来。", body:[
        srcToggle("web_exploration_enabled", "网络探索", ""),
        srcText("web_exploration_interests", "关注方向", "", "留空则不做定向探索。"),
        srcNumber("web_exploration_min_interval_hours", "最短探索间隔", "小时", 1, 168, ""),
        srcNumber("web_exploration_result_count", "每次取几条", "条", 1, 30, ""),
        srcToggle("external_event_self_link_enabled", "把外部事件关联到自己", ""),
      ]},
      {id:"screen", icon:ICON.screen, title:"屏幕与动作", hint:"屏幕观察有授权与每日上限；语音与戳一戳各自有冷却。", wide:true, body:[
        srcToggle("screen_glance_enabled", "已授权屏幕观察", "采集本身是设备侧的原生调用，可能被拒绝。"),
        srcNumber("screen_glance_daily_limit", "每日上限", "次", 0, 20, ""),
        srcNumber("screen_glance_cooldown_minutes", "冷却", "分钟", 0, 10080, ""),
        srcToggle("screen_glance_goodnight_enabled", "睡前看一眼", ""),
        srcNumber("screen_glance_goodnight_delay_minutes", "睡前延迟", "分钟", 1, 180, ""),
        srcToggle("screen_glance_followup_enabled", "未回应后跟进", ""),
        srcNumber("screen_glance_followup_after_minutes", "多久后跟进", "分钟", 10, 240, ""),
        srcNumber("screen_glance_followup_cooldown_minutes", "跟进冷却", "分钟", 30, 1440, ""),
        srcToggle("voice_action_enabled", "允许发语音", ""),
        srcNumber("voice_action_max_chars", "语音字数上限", "字", 6, 80, ""),
        srcNumber("voice_action_cooldown_minutes", "语音冷却", "分钟", 0, 1440, ""),
        srcToggle("poke_action_enabled", "允许戳一戳", ""),
        srcNumber("poke_action_daily_limit", "每日上限", "次", 0, 20, ""),
        srcNumber("poke_action_cooldown_minutes", "冷却", "分钟", 0, 1440, ""),
      ]},
      {id:"context", icon:ICON.context, title:"约定与生成上下文", hint:"约定前后的静默，以及开口前那一次自评。", wide:true, body:[
        srcNumber("appointment_lead_minutes", "约定提前量", "分钟", 0, 240, ""),
        srcNumber("appointment_lag_minutes", "约定延后量", "分钟", 0, 180, ""),
        srcNumber("appointment_pre_silence_minutes", "约定前静默", "分钟", 0, 240, "约定前先安静一段，避免连着说两遍。"),
        srcToggle("enable_llm_proactive_persona_judge", "开口前先自评", "多一次模型调用，按阈值决定这条要不要发。"),
        srcNumber("proactive_persona_judge_threshold", "自评阈值", "", 0, 100, ""),
        srcNumber("proactive_persona_judge_cache_minutes", "自评缓存", "分钟", 0, 720, ""),
        srcNumber("proactive_persona_judge_daily_limit", "自评每日上限", "次", 0, 100, ""),
        srcNumber("generation_history_limit", "带入的历史条数", "条", 0, 8, ""),
        srcNumber("history_max_chars", "历史字数上限", "字", 0, 8192, ""),
      ]},
      {id:"balance", icon:ICON.purse, title:"余额与其它", hint:"余额只影响说不说、说不说金额；两个阈值是绝对值与百分比双保险。", wide:true, body:[
        srcToggle("balance_awareness_enabled", "余额感知", ""),
        srcToggle("balance_include_amount_in_message", "在消息里说出金额", "关闭时只提「快用完了」，不报具体数字。"),
        srcText("balance_currency_label", "货币单位", "元", "不超过 20 字符。"),
        srcNumber("balance_check_interval_minutes", "检查间隔", "分钟", 5, 1440, ""),
        srcNumber("balance_low_threshold", "低余额阈值", "", 0, 1000000000, ""),
        srcNumber("balance_critical_threshold", "极低余额阈值", "", 0, 1000000000, ""),
        srcNumber("balance_low_percent_threshold", "低余额百分比", "%", 0, 100, ""),
        srcNumber("balance_critical_percent_threshold", "极低余额百分比", "%", 0, 100, ""),
        srcNumber("balance_message_cooldown_hours", "余额提醒冷却", "小时", 1, 168, ""),
      ]},
    ];
    const groups = known.map(sourceGroup).join("");
    const fields = (groups.match(/data-field="/g) || []).length;
    const toggles = (groups.match(/data-kind="toggle"/g) || []).length;
    const on = (groups.match(/data-on="1"/g) || []).length;
    const entries = [
      ["天气与官方预警", "地点、时效、突变采样和官方预警状态", "config-environment:perception-detail-place", ICON.weather],
      ["日期、饭点与约定", "重要日子、日历上下文和提醒素材", "config-environment:perception-detail-important-days", ICON.meal],
      ["资讯与网络探索", "来源、兴趣和外部检索状态", "config-news:perception-detail-external", ICON.source],
      ["设备观察与动作", "授权屏幕、手机、摄像头和动作回执", "config-screen:perception-detail-device-access", ICON.screen],
      ["余额感知", "服务余额状态与数据源配置", "config-balance:perception-detail-balance", ICON.purse],
    ];
    return `<div class="ct-sources">
      <section class="ct-source-guide"><div><strong>触发条件可在本页直接调整</strong><p>下面每张卡片的开关、时间、来源和阈值会直接写入主动联系设置。感知页提供按职责查看的状态汇总与更细的授权配置，可以从这里跳过去核对，两边不是单一入口。</p></div><div class="ct-source-guide-links">${entries.map(([title, detail, target, icon]) => `<button type="button" class="ct-source-guide-link" data-go="manage" data-manage="perception" data-perception-tab-target="${e(target)}"><span class="ct-src-icon">${icon}</span><span><b>${e(title)}</b><small>${e(detail)}</small></span><span class="ct-source-guide-arrow">查看感知状态 ${ICON.arrow}</span></button>`).join("")}</div></section>
      <div class="ct-source-summary" role="status">${fields} 项触发配置 · ${on}/${toggles} 个开关当前开启</div>
      ${groups}</div>`;
  }
  function sourceGroup(group) {
    const body = group.body;
    const html = body.join("");
    const half = group.wide ? Math.ceil(body.length / 2) : body.length;
    const rows = [body.slice(0, half), body.slice(half)].filter(list => list.length)
      .map(list => `<div class="ct-src-col">${list.join("")}</div>`).join("");
    const toggles = (html.match(/data-kind="toggle"/g) || []).length;
    const on = (html.match(/data-on="1"/g) || []).length;
    return `<section class="ct-src-group${group.wide ? " is-wide" : ""}" data-source="${e(group.id)}"
      data-toggles="${toggles}" data-enabled="${on}">
      <header class="ct-src-head"><span class="ct-src-icon">${group.icon}</span><h3>${e(group.title)}</h3>
        <em class="ct-src-badge${on ? " is-on" : ""}">${on}/${toggles} 开启</em></header>
      <p class="ct-src-hint">${e(group.hint)}</p><div class="ct-src-rows">${rows}</div></section>`;
  }
  function srcRow(name, label, help, kind, control) {
    return `<label class="ct-src-row${dirty(name) ? " is-dirty" : ""}" data-kind="${kind}">
      <span class="ct-src-label">${e(label)}${help ? `<small>${e(help)}</small>` : ""}</span>
      <span class="ct-src-control">${control}</span></label>`;
  }
  function srcToggle(name, label, help) {
    const on = value(name) === true;
    return `<label class="ct-src-row is-toggle${on ? " is-on" : ""}${dirty(name) ? " is-dirty" : ""}${flipClass(name)}"
      data-kind="toggle"${on ? ' data-on="1"' : ""}>
      <span class="ct-src-label">${e(label)}${help ? `<small>${e(help)}</small>` : ""}</span>
      <span class="ct-src-control"><span class="ct-switch"><input type="checkbox" data-field="${e(name)}"${on ? " checked" : ""}>
        <span class="ct-switch-track"><i></i></span></span></span></label>`;
  }
  function srcText(name, label, placeholder, help) {
    const current = value(name);
    return srcRow(name, label, help, "text", `<input type="text" data-field="${e(name)}" value="${e(typeof current === "string" ? current : "")}"
      placeholder="${e(placeholder)}" autocomplete="off" spellcheck="false" aria-label="${e(label)}">`);
  }
  function srcNumber(name, label, unit, min, max, help) {
    const current = value(name);
    const range = "可填 " + min + "–" + max + (unit ? "，单位 " + unit : "");
    return srcRow(name, label, help, "number", `<input type="number" data-field="${e(name)}" value="${e(current ?? "")}" min="${min}" max="${max}"
      step="1" inputmode="numeric" aria-label="${e(label)}" title="${e(range)}"><i>${e(unit)}</i>`);
  }
  function srcSelect(name, label, options) {
    const current = value(name);
    return srcRow(name, label, "", "select", `<select data-field="${e(name)}" aria-label="${e(label)}">${options.map(([v, text]) =>
      `<option value="${e(v)}"${String(current ?? "") === v ? " selected" : ""}>${e(text)}</option>`).join("")}</select>`);
  }
  function materialTime(value) {
    if (typeof value !== "string") return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN", {
      month:"numeric", day:"numeric", hour:"2-digit", minute:"2-digit",
    });
  }
  function materialCard(item) {
    const search = [item.category, item.purpose, item.title, item.detail, item.note, item.source]
      .filter(Boolean).join(" ").toLocaleLowerCase();
    const source = item.source || "已核验来源";
    return `<article class="ct-material-card" data-material-card data-category="${e(item.category || "")}" data-search="${e(search)}">
      <header class="ct-material-card-head"><span class="ct-material-category">${e(item.category || "素材")}</span>
        <span class="ct-material-purpose">${e(item.purpose || "")}</span></header>
      <h3>${e(item.title || "主动素材")}</h3>
      ${item.detail ? `<p class="ct-material-detail">${e(item.detail)}</p>` : ""}
      ${item.note ? `<p class="ct-material-note">${e(item.note)}</p>` : ""}
      <footer><span>${e(source)}</span><time datetime="${e(item.captured_at || "")}">${e(materialTime(item.captured_at))}</time>
        <span>${item.expires_at ? "有效至 " + e(materialTime(item.expires_at)) : "有效期未设"}</span></footer>
    </article>`;
  }
  function materialsView() {
    const items = Array.isArray(data.materialItems) ? data.materialItems : [];
    const count = items.length;
    const categories = [["all","全部类别"],["对话","对话"],["生活记录","生活记录"],
      ["约定","约定"],["环境与状态","环境与状态"],["资讯","资讯"],["屏幕观察","屏幕观察"]];
    let content = "";
    if (data.materialsLoading && !data.materialsLoaded) {
      content = `<div class="ct-material-empty"><span class="ct-spinner"></span><strong>正在读取素材</strong></div>`;
    } else if (data.materialsError) {
      content = `<div class="ct-material-empty is-error">${ICON.alert}<strong>素材读取失败</strong><p>${e(data.materialsError)}</p>
        <button type="button" class="ct-btn" data-action="refresh-materials"${data.materialsLoading ? " disabled" : ""}>${ICON.refresh}<span>重试</span></button></div>`;
    } else if (!count) {
      content = `<div class="ct-material-empty">${ICON.source}<strong>当前没有通过核验的主动素材</strong></div>`;
    } else {
      content = `<div class="ct-material-grid">${items.map(materialCard).join("")}</div>
        <p class="ct-material-filter-empty" hidden>没有匹配的素材</p>`;
    }
    return `<div class="ct-materials">
      <div class="ct-material-tools">
        <label class="ct-material-search"><span>查找素材</span>
          <input type="search" data-material-search aria-label="搜索主动素材" value="${e(data.materialQuery)}" placeholder="名称、内容或来源">
        </label>
        <label><span>来源类别</span><select data-material-category aria-label="按来源类别筛选">
          ${categories.map(([value, label]) => `<option value="${e(value)}"${data.materialCategory === value ? " selected" : ""}>${e(label)}</option>`).join("")}
        </select></label>
        <span class="ct-material-count" data-material-result-count>${count} 项素材</span>
      </div>
      ${data.materialsLoading && data.materialsLoaded ? `<p class="ct-material-updating" role="status">正在更新</p>` : ""}
      ${content}
    </div>`;
  }
  function updateMaterialFilters() {
    if (!root) return;
    const query = data.materialQuery.trim().toLocaleLowerCase();
    const category = data.materialCategory;
    const cards = [...root.querySelectorAll("[data-material-card]")];
    let visible = 0;
    for (const card of cards) {
      const matches = (category === "all" || card.dataset.category === category)
        && (!query || String(card.dataset.search || "").includes(query));
      card.hidden = !matches;
      if (matches) visible++;
    }
    const count = root.querySelector("[data-material-result-count]");
    if (count) count.textContent = visible + " / " + cards.length + " 项素材";
    const empty = root.querySelector(".ct-material-filter-empty");
    if (empty) empty.hidden = visible > 0 || cards.length === 0;
  }
  function body() {
    if (data.view === "tests") return testsView();
    if (data.view === "materials") return materialsView();
    if (!data.ready) return emptyMarkup();
    return {"dial":dialView, "purposes":purposesView, "gates":gatesView,
      "budgets":budgetsView, "sources":sourcesView}[data.view]();
  }
  /* 换页。方向按轨道上的先后：往后（往下）点，新的一屏从右边进来；
     往回点从左边进来。整块 DOM 会被重写，旧的一屏没有「离场」这一步——
     所以只有入场动画可写，方向就是唯一能说清「我是往哪边走的」的信息，
     没有方向的话两屏切换看起来只是闪了一下。 */
  function switchView(next) {
    const from = VIEWS.findIndex(([id]) => id === data.view);
    const to = VIEWS.findIndex(([id]) => id === next);
    data.viewShift = to > from ? 1 : to < from ? -1 : null;
    data.view = next;
    data.notice = "";
    if (next === "materials") void loadMaterials();
  }
  function render() {
    if (!root) return;
    /* 取这一帧要闪的盘面部分并立刻清空：动效是「刚刚改了什么」的一次确认，
       不是常驻状态。类由 dialView 写进 HTML，而不是渲染后往节点上加——
       这里是整块 innerHTML 重写，渲染后加类等于加在一个马上被丢弃的节点上。 */
    data.pulseNow = [...data.pulse]; data.pulse.clear();
    data.flipNow = data.flip; data.flip = null;
    /* 换页方向同样在这一帧消费掉：下一次渲染（比如改一个开关）不该重放
       入场动画，否则每动一下整屏都要再滑一次。 */
    data.viewShiftNow = data.viewShift; data.viewShift = null;
    const shift = data.viewShiftNow;
    const enter = shift ? (shift > 0 ? " is-from-next" : " is-from-prev") : "";
    root.innerHTML = `<div class="ct-app">${railMarkup()}<div class="ct-main">`
      + `<div class="ct-view${enter}">${headMarkup()}${noticeMarkup()}${body()}</div></div></div>`;
    if (data.pendingWrite) for (const field of root.querySelectorAll("[data-field]")) field.disabled = true;
    const gateSettingsArea = document.getElementById("contact-gate-settings-area");
    if (gateSettingsArea) gateSettingsArea.hidden = data.view !== "gates";
    if (data.view === "purposes") updatePurposeFilters();
    if (data.view === "tests") updateTestFilters();
    if (data.view === "materials") updateMaterialFilters();
    if (data.scanning && data.ready) {
      data.scanning = false;
      const dial = root.querySelector(".ct-dial");
      if (dial) { dial.classList.add("is-entering"); setTimeout(() => dial.classList.remove("is-entering"), 900); }
    }
  }

  /* ---- 交互 ------------------------------------------------------------ */
  let painting = null;
  function focusGateSettings() {
    const target = document.getElementById("contact-gate-settings");
    if (!target) return false;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches
      || ["low", "off"].includes(document.documentElement.dataset.motion);
    target.scrollIntoView({behavior: reduced ? "instant" : "smooth", block: "start"});
    if (!target.hasAttribute("tabindex")) target.tabIndex = -1;
    target.focus({preventScroll: true});
    return true;
  }
  function openGateSettingsView() {
    if (!root || !data) return false;
    if (data.view !== "gates") { switchView("gates"); render(); }
    return focusGateSettings();
  }
  function clicked(event) {
    const view = event.target.closest("[data-view]");
    if (view) { switchView(view.dataset.view); render(); return; }
    const testCopy = event.target.closest("[data-test-copy]")?.dataset.testCopy;
    if (testCopy) { copyTestInstruction(testCopy); return; }
    const action = event.target.closest("[data-action]")?.dataset.action;
    if (action === "refresh") {
      data.notice = ""; data.error = false; load(); loadContract();
      if (data.view === "materials") void loadMaterials();
      return;
    }
    if (action === "retry-contract") { void loadContract(); return; }
    if (action === "refresh-materials") { void loadMaterials(); return; }
    if (action === "open-gate-settings") { focusGateSettings(); return; }
    if (action === "save") { save(); return; }
    if (action === "retry-pending") { save(); return; }
    if (action === "reset") { resetDraft(); notice("已放弃未保存的改动。"); render(); return; }
    if (action === "dismiss") { data.notice = ""; render(); return; }
    if (action === "curve-default") {
      set("proactive_hour_activity_curve", DEFAULT_CURVE); notice("已恢复默认曲线，保存后生效。"); render(); return;
    }
    if (action === "curve-flat") {
      set("proactive_hour_activity_curve", curveText(new Array(24).fill(1)));
      notice("已拉平到 1.00，保存后生效：所有小时同等保留。"); render(); return;
    }
    const tier = event.target.closest("[data-tier]")?.dataset.tier;
    if (tier && TIER_BY_KEY[tier]) {
      /* 环的形变不在这里当场加类：render() 会立刻重写整块 DOM，
         加在旧节点上的动画一帧都放不出来（改版前这里就是这么写的，
         于是 ct-shift 是一条从没跑过的规则）。
         现在由 set() 记进 data.pulse，渲染时变成 .is-pulse-tier。 */
      set("proactive_intensity_preset", tier);
      render(); return;
    }
    const anchor = event.target.closest("[data-anchor]")?.dataset.anchor;
    if (anchor) {
      data.notice = "问候窗口 " + String(value("greeting_" + anchor + "_window") || "") + "；改下面那三个框。";
      render(); return;
    }
  }
  function changed(event) {
    const materialCategory = event.target.closest("[data-material-category]");
    if (materialCategory) {
      data.materialCategory = materialCategory.value;
      updateMaterialFilters();
      return;
    }
    const testBucket = event.target.closest("[data-test-bucket-filter]");
    if (testBucket) { data.testBucket = testBucket.value; updateTestFilters(); return; }
    const testCoverage = event.target.closest("[data-test-coverage-filter]");
    if (testCoverage) { data.testCoverage = testCoverage.value; updateTestFilters(); return; }
    const bucketFilter = event.target.closest("[data-purpose-bucket-filter]");
    if (bucketFilter) {
      data.purposeBucket = bucketFilter.value;
      updatePurposeFilters();
      return;
    }
    const purposeFilter = event.target.closest("[data-purpose-filter]");
    if (purposeFilter) {
      data.purposeFilter = purposeFilter.value;
      updatePurposeFilters();
      return;
    }
    const field = event.target.closest("[data-field]");
    if (!field) return;
    const name = field.dataset.field;
    if (field.type === "checkbox") {
      const on = !!field.checked;
      readField(name, on);
      /* 开与关都要录：两个方向的动画同样是一次 switch 动作，只播一半等于没播。 */
      data.flip = {name, on};
    }
    else if (field.type === "range") readField(name, Number(field.value));
    else if (field.type === "number") {
      const n = Number(field.value);
      readField(name, Number.isFinite(n) ? n : 0);
    } else if (field.type === "datetime-local") readField(name, toIso(field.value));
    else readField(name, field.value);
    /* 权重与额度的滑块：只重画那一条的填充，不整页重画——
       整页重画会把手上的滑块弄丢，拖到一半就断了。 */
    const range = field.type === "range" ? field : null;
    if (range) {
      const fill = range.parentElement?.querySelector(".ct-weight-fill");
      if (fill) fill.style.setProperty("--w", (Number(range.value) / 5) * 100 + "%");
      const em = range.parentElement?.querySelector("em");
      /* 权重是小数（0.1 步进），额度是整数（整步进）——判据是**步长**，不是 max。
         曾经写成 `range.max === "5"`：max 是字符串，恒不等于数字 5，
         于是权重永远被显示成整数，3.5 变成 4（草稿里存的是 3.5，界面却写 4）。 */
      if (em) em.textContent = Number(range.step) < 1 ? Number(range.value).toFixed(1) : String(range.value);
      const quota = range.closest(".ct-quota");
      const shown = quota?.querySelector(".ct-quota-value b");
      if (shown) shown.textContent = String(range.value);
      return;
    }
    render();
  }
  function readField(name, value_) { set(name, value_); }
  function input(event) {
    const materialSearch = event.target.closest("[data-material-search]");
    if (materialSearch) {
      data.materialQuery = materialSearch.value;
      updateMaterialFilters();
      return;
    }
    const testSearch = event.target.closest("[data-test-search]");
    if (testSearch) { data.testQuery = testSearch.value; updateTestFilters(); return; }
    const search = event.target.closest("[data-purpose-search]");
    if (search) {
      data.purposeQuery = search.value;
      updatePurposeFilters();
      return;
    }
    const field = event.target.closest("[data-field]");
    if (field && field.type === "range") changed(event);
  }
  async function copyTestInstruction(id) {
    const item = TEST_INSTRUCTIONS.find(candidate => candidate.id === id);
    if (!item) return;
    try {
      const clipboard = window.navigator?.clipboard;
      if (typeof clipboard?.writeText !== "function") throw new Error("clipboard unavailable");
      await clipboard.writeText(testInstructionText(item));
      notice(item.id + " 测试指令已复制；当前只复制文本，没有调用模型或真实投递。");
    } catch {
      notice("剪贴板权限不可用，请选中当前类型卡片中的指令手动复制。", true);
    }
    render();
  }
  /* 曲线拖涂。按下开始，横向移动换算成小时，纵向换算成权重——
     这是这一页唯一一个「直接画数据」的地方，因为 24 个数字确实没人愿意输。 */
  function plotRect() { return root?.querySelector('[data-role="curvePlot"]')?.getBoundingClientRect() || null; }
  function paintHour(clientX, clientY, rect) {
    if (data.pendingWrite) return;
    const x = Math.max(0, Math.min(rect.width - 0.01, clientX - rect.left));
    const hour = Math.min(23, Math.floor((x / rect.width) * 24));
    const y = Math.max(0, Math.min(rect.height, clientY - rect.top));
    const weight = Math.max(0.05, Math.min(2, (1 - y / rect.height) * 2));
    const list = curveOf(value("proactive_hour_activity_curve")).slice();
    if (Math.abs(list[hour] - weight) < 0.03) return;
    list[hour] = weight;
    data.draft["proactive_hour_activity_curve"] = curveText(list);
    data.touched.add("proactive_hour_activity_curve");
    const col = root.querySelector('.ct-curve-col[data-hour="' + hour + '"]');
    if (col) {
      const bar = col.querySelector("i");
      if (bar) bar.style.height = Math.round((weight / 2) * 100) + "%";
      col.title = String(hour).padStart(2, "0") + ":00 · 权重 " + weight.toFixed(2);
    }
    const read = root.querySelector('[data-role="curveText"]');
    if (read) read.value = curveText(list);
  }
  function pointerDown(event) {
    if (!event.target.closest('[data-role="curvePlot"]')) return;
    const rect = plotRect();
    if (!rect) return;
    painting = true;
    event.target.setPointerCapture?.(event.pointerId);
    paintHour(event.clientX, event.clientY, rect);
  }
  function pointerMove(event) {
    if (!painting) return;
    const rect = plotRect();
    if (rect) paintHour(event.clientX, event.clientY, rect);
  }
  function pointerUp() { painting = null; }
  function keydown(event) {
    if (event.key === "Escape" && data.notice) { data.notice = ""; render(); return; }
    /* ⌘/Ctrl + S 保存。这一页改动多，来回找按钮很烦。 */
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
      event.preventDefault(); save(); return;
    }
    const rail = event.target.closest("[data-view]");
    if (rail && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      const index = VIEWS.findIndex(([id]) => id === data.view);
      const next = (index + (event.key === "ArrowDown" ? 1 : VIEWS.length - 1)) % VIEWS.length;
      switchView(VIEWS[next][0]); render();
      root.querySelector('[data-view="' + data.view + '"]')?.focus();
    }
  }

  /* ---- 挂载 ------------------------------------------------------------ */
  async function whenBridgeReady(ticket, timeout = 10000) {
    if (window.AstrBotPluginPage?.apiGet) return window.AstrBotPluginPage;
    const product = window.CompanionProduct;
    if (product?.bridgeNow || product?.bridgeFor) {
      try {
        const found = product.bridgeNow?.() || await product.bridgeFor();
        if (found?.apiGet) return found;
      } catch { /* 交给下面的轮询 */ }
      if (window.AstrBotPluginPage?.apiGet) return window.AstrBotPluginPage;
    }
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const tick = () => {
        if (!live(ticket)) return;
        const found = window.AstrBotPluginPage;
        if (found?.apiGet) return resolve(found);
        if (Date.now() - started >= timeout) return reject(problem("bridge_unavailable"));
        setTimeout(tick, 80);
      };
      tick();
    });
  }
  function addresses() {
    /* 状态与配置都采用目录中当前对象、角色的路径，避免多目标时读写全局路由。 */
    const role = window.CompanionProduct.role?.();
    const native = role?.perception_native_api, config = role?.config_api;
    if (typeof native !== "string" || !native || typeof config !== "string" || !config) {
      throw problem("proactive_contact_scope_invalid");
    }
    data.nativePath = rel(native);
    data.configPath = rel(config);
  }
  async function mount(host) {
    /* 顺序有讲究：unmount() 会 ++version 并清掉 data，所以
       ① 先 unmount，② 再建新 data，③ 才取票号。
       在 unmount() 之前取票会让下面第一处 live(ticket) 立即为假，
       页面看着挂上了但其实一个请求都没发；
       在建 data 之前 render() 会读到 null —— 那是一条只在首次挂载时出现的崩溃。 */
    unmount();
    root = host; contactScope = currentContactScope();
    const cached = contactCache.get(contactScope);
    data = cached ? {...blank(), ...cached, touched:new Set(cached.touched || []), draft:{...(cached.draft || {})}, pulse:new Set(), pulseNow:[], flip:null, flipNow:null, viewShift:null, viewShiftNow:null} : blank();
    /* 页面切换只缓存草稿和筛选，不把旧的网络错误带回新的读取周期。 */
    if (data.error) { data.notice = ""; data.error = false; }
    const ticket = ++version;
    root.addEventListener("click", clicked);
    root.addEventListener("change", changed);
    root.addEventListener("input", input);
    root.addEventListener("keydown", keydown);
    root.addEventListener("pointerdown", pointerDown);
    root.addEventListener("pointermove", pointerMove);
    root.addEventListener("pointerup", pointerUp);
    root.addEventListener("pointercancel", pointerUp);
    render();
    try {
      bridge = await whenBridgeReady(ticket);
      if (!live(ticket)) return;
      const context = await bounded(bridge.ready());
      if (!live(ticket)) return;
      if (context?.pluginName !== HOST) throw problem("bridge_unavailable");
      addresses();
      data.pendingWrite = restorePendingWrite();
      await load(); await loadContract();
      if (data.view === "materials") await loadMaterials();
      if (live(ticket)) render();
    } catch (error) {
      if (!live(ticket)) return;
      notice(reason(error.code), true);
      render();
    }
  }
  function unmount() {
    ++version;
    if (autoRecoveryTimer !== null) clearTimeout(autoRecoveryTimer);
    autoRecoveryTimer = null;
    autoRecoveryKey = "";
    autoRecoveryAttempts = 0;
    cacheContact();
    if (!root) { data = null; bridge = null; contactScope = ""; return; }
    root.removeEventListener("click", clicked);
    root.removeEventListener("change", changed);
    root.removeEventListener("input", input);
    root.removeEventListener("keydown", keydown);
    root.removeEventListener("pointerdown", pointerDown);
    root.removeEventListener("pointermove", pointerMove);
    root.removeEventListener("pointerup", pointerUp);
    root.removeEventListener("pointercancel", pointerUp);
    root = null; bridge = null; data = null; contactScope = ""; painting = null;
  }
  /* `state` 只为测试驱动而暴露：这一页的 data 是模块私有的，
     测试要断言环的几何与阈值时没有别的入口。 */
  return {mount, unmount, openGateSettingsView,
    get state() { return {data}; },
    _internals:{minutes, hm, angle, point, curveOf, curveText, tierOf, arc, quietSpan}};
})();
