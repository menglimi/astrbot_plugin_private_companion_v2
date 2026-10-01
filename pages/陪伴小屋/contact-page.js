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
 * 它给 158 个 settings、15 个 purposes（各带 allowed + 唯一阻断原因）、
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
    staging_not_initialized:"V2 数据尚未加载。请先在账号与会话中加载已初始化的配置，再刷新。",
    staging_host_terminated:"V2 宿主已停止，请重新打开拓展页。",
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
    proactive_budget_scope:"这两个额度限制整段关系，只能在安装 / 角色 / 关系层设置。",
    contact_relationship_budget_scope:"这两个额度限制整段关系，只能在安装 / 角色 / 关系层设置。",
    configuration_relationship_required:"这个对象还没有建立可写入的关系。",
    contact_recipient_changed:"联系对象已变化，请重新读取。",
    configuration_request_invalid:"请求与当前接口不匹配，请更新页面后重试。",
    configuration_group_unknown:"这个设置分组已不存在，请更新页面。",
    bridge_unavailable:"页面还没有接上 AstrBot。若这是从管理界面打开的插件页，刷新一次通常就好；若反复出现，请确认插件已启用。",
    bridge_timeout:"未收到服务确认，请刷新核对。",
    invalid_response:"服务返回的数据不完整，请刷新核对。",
  };
  /* 后端把阻断原因与机器码混在同一个字段上：reason 可能是
     `proactive_quiet_hours` 这样的码，也可能是一句可直接展示的话。
     用形状判，不猜词表。 */
  const CODE = /^[a-z][a-z0-9_]{2,60}$/;
  const denied = new Set(["dashboard_identity_required","core_access_required","binding_revoked",
    "binding_rebound","staging_host_terminated","proactive_contact_scope_invalid"]);
  const e = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const reason = code => errors[code] || (code ? "需要核对：" + code : "暂无具体原因");
  const problem = code => Object.assign(new Error(reason(code)), {code});
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
    mute:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9v6h3l4 3V6L9 9z"/><path d="m16 9 4 6M20 9l-4 6"/></svg>',
    refresh:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12a7 7 0 1 1-2.1-5"/><path d="M19 4v4h-4"/></svg>',
    alert:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5M12 16h.01"/></svg>',
    check:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7"/></svg>',
    save:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4h11l3 3v13H5z"/><path d="M9 4v5h6"/></svg>',
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

  function blank() {
    return {view:"dial",
      nativePath:"", configPath:"",
      settings:null, effective:null, purposes:{}, hostState:"",
      editToken:"", configToken:"",
      /* 草稿：只放用户真的改过的字段。提交时只发这些，未动的字段一个都不发——
         避免把「没看过的字段」当成「要保持的值」写回去。 */
      draft:{}, touched:new Set(), tierDraft:null,
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
    const wrapped = ["ok","error"].includes(response?.status) ? response
      : ["ok","error"].includes(response?.data?.status) ? response.data : null;
    if (wrapped?.status === "error") throw problem(CODE.test(wrapped.data?.code || wrapped.message || "")
      ? (wrapped.data?.code || wrapped.message) : "invalid_response");
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
      data.settings = status.settings;
      data.effective = status.effective && typeof status.effective === "object" ? status.effective : null;
      data.purposes = status.purposes && typeof status.purposes === "object" ? status.purposes : {};
      data.hostState = typeof status.host_state === "string" ? status.host_state : "";
      data.editToken = typeof status.edit_token === "string" ? status.edit_token : "";
      data.ready = true; data.scanning = true;
    } catch (error) {
      if (!live(ticket)) return;
      data.settings = null; data.effective = null; data.purposes = {}; data.editToken = "";
      data.ready = false;
      notice(error.code ? reason(error.code) : "连接中断，已清空旧内容。请刷新核对。", true);
    } finally {
      if (live(ticket)) { data.loading = false; data.busy = false; render(); }
    }
  }
  /* 配置侧只要 edit_token 与字段契约——值仍旧从 native 那份读，
     两处读出的值必须一致，不一致就说明两端读的不是同一层。 */
  async function loadContract() {
    if (!data.configPath) return;
    const ticket = version;
    try {
      const payload = await api("GET", data.configPath, {sections: GROUP});
      if (!live(ticket)) return;
      const section = payload?.sections?.[GROUP];
      if (!section) return;
      data.configToken = typeof section.edit_token === "string" ? section.edit_token : "";
    } catch (error) {
      if (live(ticket)) notice(error.code ? reason(error.code) : "配置字段契约未读到，保存仍可用。", true);
    }
  }
  /* ---- 写 -------------------------------------------------------------
     只提交 touched 里的字段。edit_token 必须用**刚刚读到的那一份**：
     配置页的令牌与 native 的令牌是两个生效范围，不能互相顶替
     （native 那条路由只写 news 六个字段，其余交给 config 段）。 */
  async function save() {
    if (!data.configPath || data.busy || !data.touched.size) return;
    if (!data.ready) { notice("还没有读到当前设置，不能保存。", true); render(); return; }
    if (!data.configToken) { notice("缺少配置令牌，请重新读取后再保存。", true); render(); return; }
    const ticket = version;
    data.busy = true;
    const changes = {};
    for (const name of data.touched) if (name in data.draft) changes[name] = data.draft[name];
    try {
      const payload = await api("POST", data.configPath + "/configure", {
        section:GROUP, operation_key:operationKey(), edit_token:data.configToken, changes});
      if (!live(ticket)) return;
      const status = payload?.status?.sections?.[GROUP];
      if (status) {
        data.editToken = typeof status.edit_token === "string" ? status.edit_token : data.editToken;
        data.configToken = data.editToken;
      }
      data.touched.clear(); data.draft = {}; data.tierDraft = null;
      data.savedAt = Date.now(); data.busy = false;
      notice("已保存 " + Object.keys(changes).length + " 项。改动从下一轮主动评估开始生效。");
      await load();
    } catch (error) {
      if (!live(ticket)) return;
      data.busy = false;
      const code = error.code || "";
      notice(reason(code), true);
      if (code === "proactive_contact_revision_conflict" || code === "proactive_contact_target_changed") {
        data.touched.clear(); data.draft = {}; data.tierDraft = null;
        await load();
      } else if (!code) render();
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
    data.draft[name] = value; data.touched.add(name);
    if (name === "proactive_intensity_preset") data.tierDraft = tierOf(value);
    const part = PULSE_PART[name];
    if (part) data.pulse.add(part);
  }
  function resetDraft() { data.touched.clear(); data.draft = {}; data.tierDraft = null; render(); }
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
    const minute = currentMinute();
    const blocked = data.effective && data.effective.allowed === false;
    if (blocked) {
      const code = data.effective.reason;
      return {tone:"blocked", title:"当前不会开口", detail:reason(code),
        code:code || "", automatic:data.effective.automatic_allowed === false};
    }
    if (inQuiet(minute)) {
      return {tone:"quiet", title:"免打扰中", detail:quietSpanText(),
        code:"proactive_quiet_hours", automatic:data.effective?.automatic_allowed === false};
    }
    const weight = currentWeight(minute);
    if (weight !== null && weight < 0.3) {
      return {tone:"low", title:"节律低谷", detail:"这一小时的活动权重 " + weight.toFixed(2)
        + "，低于 0.30；这条曲线只删格子，不放宽额度。", code:"", automatic:data.effective?.automatic_allowed === false};
    }
    return {tone:"open", title:"此刻可以开口", detail:minute === null
      ? "未设时区，只能按服务端的判定。" : "本地时间 " + hm(minute) + "，不在免打扰内。",
      code:"", automatic:data.effective?.automatic_allowed === false};
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
  const VIEWS = [["dial","节律盘",ICON.dial],["purposes","契机矩阵",ICON.seed],
                 ["gates","开口闸门",ICON.gate],["budgets","额度与去重",ICON.quota],
                 ["sources","外部触发源",ICON.source]];
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
        ${dirtyCount ? `<button type="button" class="ct-btn" data-action="reset">${ICON.undo}<span>放弃 ${dirtyCount} 项改动</span></button>
          <button type="button" class="ct-btn is-primary" data-action="save"${data.busy ? " disabled" : ""}>${ICON.save}<span>保存</span></button>`
        : `<button type="button" class="ct-btn" data-action="refresh"${data.loading || data.busy ? " disabled" : ""}>${ICON.refresh}<span>重新读取</span></button>`}
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
    if (!data.notice) return "";
    return `<p class="ct-notice${data.error ? " is-error" : ""}" role="status">${data.error ? ICON.alert : ICON.check}`
      + `<span>${e(data.notice)}</span><button type="button" data-action="dismiss" aria-label="关闭">×</button></p>`;
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
          ${v.automatic ? `<span class="ct-center-flag">${ICON.alert}后台自动联系未开启</span>` : ""}
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
        ``,
        numberRow("interval_seconds", "两次联系至少间隔", "秒", 60, 604800,
          interval ? "档位换算后约 " + fmtDuration(Math.max(1, Math.round(interval * tier.interval))) : ""),
        numberRow("idle_seconds", "对话结束后至少等候", "秒", 0, 86400,
          idle !== undefined && Number.isFinite(idle) ? "档位换算后约 " + fmtDuration(Math.max(0, Math.round(idle * tier.idle))) : ""),
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
    return `<div class="ct-tiers" role="radiogroup" aria-label="强度档位">
      ${TIERS.map(t => {
        const on = t.key === tier.key;
        return `<button type="button" role="radio" aria-checked="${on}" data-tier="${t.key}"
          class="ct-tier${on ? " is-on" : ""}${dirty("proactive_intensity_preset") ? " is-dirty" : ""}"
          title="间隔 ×${t.interval}　等候 ×${t.idle}">
          <span class="ct-tier-bar" style="--fill:${(1 - t.interval) * 100}%"></span>
          <span class="ct-tier-label">${e(t.label)}</span>
          <span class="ct-tier-meta">间隔 ×${t.interval}</span>
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
      return `<section class="ct-bucket"><header>
          <h3>${e(bucket.label)}</h3><span>${e(bucket.hint)}</span>
          <em>${bucket.purposes.length} 类</em></header>
        <div class="ct-purpose-list">${items.join("")}</div></section>`;
    }).join("");
    const allowed = ALL_PURPOSES.filter(([name]) => data.purposes[name]?.allowed).length;
    return `<div class="ct-purposes">
      <div class="ct-purposes-sum">${ALL_PURPOSES.length} 类契机中 <strong>${allowed}</strong> 类此刻可开口</div>
      ${rows}</div>`;
  }
  function purposeRow(name, label) {
    const info = data.purposes[name] || {};
    const enabled = value(name + ".enabled") !== false;
    const weight = Number(value(name + ".weight"));
    const paused = typeof value(name + ".pause_until") === "string" && value(name + ".pause_until");
    const blocked = info.allowed === false;
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
        ${blocked
          ? `<span class="ct-chip is-risk" title="${e(reason(info.reason))}">${e(shortReason(info.reason))}</span>`
          : paused ? `<span class="ct-chip is-paused">暂缓至 ${e(paused.slice(0, 16).replace("T", " "))}</span>`
          : enabled ? `<span class="ct-chip is-ok">可开口</span>`
          : `<span class="ct-chip">已关闭</span>`}
      </div>
    </article>`;
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
      {id:"host", title:"宿主运行", ok:data.hostState === "running", code:"host_not_running",
       note:"宿主未运行时所有后台判定暂停。"},
      {id:"quiet", title:"免打扰时段", ok:!inQuiet(currentMinute()), code:"proactive_quiet_hours",
       note:quietSpanText()},
      {id:"curve", title:"小时活动曲线", ok:(() => { const w = currentWeight(currentMinute()); return w === null || w >= 0.3; })(),
       code:"", note:value("proactive_hour_activity_enabled") ? "当前小时权重决定这一格是否保留。" : "未启用，不做小时过滤。"},
      {id:"pause", title:"临时暂停", ok:!value("pause_until"), code:"proactive_paused",
       note:value("pause_until") ? "已暂缓至 " + String(value("pause_until")).slice(0, 16).replace("T", " ") : "未设暂停。"},
    ];
    const blocked = gates.filter(g => !g.ok).length;
    return `<div class="ct-gates">
      <p class="ct-gates-sum">${blocked ? `有 <strong>${blocked}</strong> 道闸门此刻是关的` : "全部闸门此刻都是开的"}</p>
      ${gates.map((g, i) => `<article class="ct-gate${g.ok ? " is-ok" : " is-shut"}" style="--i:${i}">
        <span class="ct-gate-mark">${g.ok ? ICON.check : ICON.alert}</span>
        <div class="ct-gate-body"><strong>${e(g.title)}</strong>
          ${g.ok ? "" : `<code>${e(g.code || "—")}</code>`}</div>
        <span class="ct-gate-state">${g.ok ? "开" : "关"}</span></article>`).join("")}
      <section class="ct-block"><h3>临时暂停</h3>
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
        srcToggle("news_share_enabled", "分享资讯", ""),
        srcNumber("news_check_interval_minutes", "检查间隔", "分钟", 15, 1440, ""),
        srcSelect("news_source_kind", "来源类型", [["host","宿主提供"],["url","自定地址"],["uid","平台标识"]]),
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
    /* 导语里的两个数是**数出来的**，不是写死的：条目数或开关数变了它自己会跟上，
       写死的话改完字段就会开始撒谎。 */
    const fields = (groups.match(/data-field="/g) || []).length;
    const toggles = (groups.match(/data-kind="toggle"/g) || []).length;
    const on = (groups.match(/data-on="1"/g) || []).length;
    return `<div class="ct-sources">
      
      ${groups}</div>`;
  }
  /* 一张触发源卡片。头部那两个数是给用户看的「这一组开了几项」，
     也写成 data-* 供自检比对——否则加一个开关忘了改头部，卡片会开始撒谎。
     条目多的组（wide）在卡片内部分两栏：14 行单栏会把同一行的短卡片拉出
     一大块空白。分栏在这里**显式切成两个列容器**，不交给 CSS 自动分栏——
     自动分栏时「每列第一行不要上边线」这条没法用选择器表达，
     第二栏的第一行会平白多一条横线，两栏顶边对不齐。 */
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
      <header class="ct-src-head">
        <span class="ct-src-icon">${group.icon}</span>
        <h3>${e(group.title)}</h3>
        <em class="ct-src-badge${on ? " is-on" : ""}">${on}/${toggles} 开启</em>
      </header>
      
      <div class="ct-src-rows">${rows}</div></section>`;
  }
  /* 触发源的紧凑行：标签在左、控件在右，一行一件事。
     这是与主配置区并列的第二套字段版式，所以是另一组函数，而不是给
     toggle/textRow/numberRow 加一个「紧凑」开关——一个函数两套版式，
     迟早会有一行悄悄退回竖排，而两套版式长得都「没错」，没人看得出来。 */
  function srcRow(name, label, help, kind, control) {
    return `<label class="ct-src-row${dirty(name) ? " is-dirty" : ""}" data-kind="${kind}">
      <span class="ct-src-label">${e(label)}${help ? `<small>${e(help)}</small>` : ""}</span>
      <span class="ct-src-control">${control}</span></label>`;
  }
  function srcToggle(name, label, help) {
    const on = value(name) === true;
    /* data-on 只标在开着的行上：头部那两个数就是数它数出来的。 */
    return `<label class="ct-src-row is-toggle${on ? " is-on" : ""}${dirty(name) ? " is-dirty" : ""}${flipClass(name)}"
      data-kind="toggle"${on ? ' data-on="1"' : ""}>
      <span class="ct-src-label">${e(label)}${help ? `<small>${e(help)}</small>` : ""}</span>
      <span class="ct-src-control"><span class="ct-switch">
        <input type="checkbox" data-field="${e(name)}"${on ? " checked" : ""}>
        <span class="ct-switch-track"><i></i></span></span></span></label>`;
  }
  function srcText(name, label, placeholder, help) {
    const current = value(name);
    return srcRow(name, label, help, "text",
      `<input type="text" data-field="${e(name)}" value="${e(typeof current === "string" ? current : "")}"
        placeholder="${e(placeholder)}" autocomplete="off" spellcheck="false" aria-label="${e(label)}">`);
  }
  function srcNumber(name, label, unit, min, max, help) {
    const current = value(name);
    /* 取值范围不再拼进说明行：这一屏有近 60 项，每行都挂一段「0–1440」，
       扫过去全是数字噪声，行高还被撑得参差不齐。范围由输入框的
       min/max 兜底，越界会被夹回去；想核对时悬停输入框看 title。
       说明行只留真正有信息量的那句话。 */
    const range = "可填 " + min + "–" + max + (unit ? "，单位 " + unit : "");
    return srcRow(name, label, help, "number",
      `<input type="number" data-field="${e(name)}" value="${e(current ?? "")}" min="${min}" max="${max}"
        step="1" inputmode="numeric" aria-label="${e(label)}" title="${e(range)}"><i>${e(unit)}</i>`);
  }
  function srcSelect(name, label, options) {
    const current = value(name);
    return srcRow(name, label, "", "select",
      `<select data-field="${e(name)}" aria-label="${e(label)}">${options.map(([v, text]) =>
        `<option value="${e(v)}"${String(current ?? "") === v ? " selected" : ""}>${e(text)}</option>`).join("")}</select>`);
  }

  function body() {
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
    if (data.scanning && data.ready) {
      data.scanning = false;
      const dial = root.querySelector(".ct-dial");
      if (dial) { dial.classList.add("is-entering"); setTimeout(() => dial.classList.remove("is-entering"), 900); }
    }
  }

  /* ---- 交互 ------------------------------------------------------------ */
  let painting = null;
  function clicked(event) {
    const view = event.target.closest("[data-view]");
    if (view) { switchView(view.dataset.view); render(); return; }
    const action = event.target.closest("[data-action]")?.dataset.action;
    if (action === "refresh") { data.notice = ""; load(); loadContract(); return; }
    if (action === "save") { save(); return; }
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
    const field = event.target.closest("[data-field]");
    if (field && field.type === "range") changed(event);
  }
  /* 曲线拖涂。按下开始，横向移动换算成小时，纵向换算成权重——
     这是这一页唯一一个「直接画数据」的地方，因为 24 个数字确实没人愿意输。 */
  function plotRect() { return root?.querySelector('[data-role="curvePlot"]')?.getBoundingClientRect() || null; }
  function paintHour(clientX, clientY, rect) {
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
      data.view = VIEWS[next][0]; render();
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
    root = host; data = blank();
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
      await load(); await loadContract();
      if (live(ticket)) render();
    } catch (error) {
      if (!live(ticket)) return;
      notice(error.code ? reason(error.code) : String(error?.message || "未完成"), true);
      render();
    }
  }
  function unmount() {
    ++version;
    if (!root) { data = null; bridge = null; return; }
    root.removeEventListener("click", clicked);
    root.removeEventListener("change", changed);
    root.removeEventListener("input", input);
    root.removeEventListener("keydown", keydown);
    root.removeEventListener("pointerdown", pointerDown);
    root.removeEventListener("pointermove", pointerMove);
    root.removeEventListener("pointerup", pointerUp);
    root.removeEventListener("pointercancel", pointerUp);
    root = null; bridge = null; data = null; painting = null;
  }
  /* `state` 只为测试驱动而暴露：这一页的 data 是模块私有的，
     测试要断言环的几何与阈值时没有别的入口。 */
  return {mount, unmount,
    get state() { return {data}; },
    _internals:{minutes, hm, angle, point, curveOf, curveText, tierOf, arc, quietSpan}};
})();
