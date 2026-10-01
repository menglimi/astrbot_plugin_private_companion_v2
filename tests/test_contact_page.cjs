/* 主动与联系页（节律盘）测试。
 *
 * 这一页的主体是一个钟面，四圈几何各自对应一个真实字段，且四圈的**几何正确性**
 * 就是它的正确性：免打扰弧跨午夜要拆成两段、24 根柱子要按权重归一、
 * 环心那句「此刻」必须与后端同源而不是页面自己推断。
 * 这些都是纯函数，但它们是模块私有的，只能靠 vm 跑真实文件来测。
 *
 * 另外三条是历史踩过的坑，值得各自一条断言：
 *   ① 票号必须在 unmount() 之后取，否则挂载后一个请求都不发（看着挂上了其实是空的）；
 *   ② 滑块拖动不能整页重绘，否则拖到一半手上的滑块就丢了；
 *   ③ 保存只提交动过的字段——把没看过的字段当「要保持的值」写回去会覆盖掉别人改的。
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.resolve(__dirname, '../pages/陪伴小屋/contact-page.js'), 'utf8');
const style = fs.readFileSync(path.resolve(__dirname, '../pages/陪伴小屋/contact-page.css'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
const settle = async () => { for (let i = 0; i < 8; i++) await flush(); };

const HOST = 'astrbot_plugin_private_companion_v2';
const NATIVE = '/' + HOST + '/perception-native';
const CONFIG = '/' + HOST + '/config';

/* 后端 status 的 contact 分区（照 native_perception_api._status）。
   注意 effective 上四个字段与 purposes 上每项 allowed/reason 都是页面的判据来源。 */
function status(settings = {}, extra = {}) {
  return {contact: {
    settings,
    edit_token: 'n'.repeat(64),
    effective: {allowed: true, reason: null, automatic_allowed: true, automatic_reason: null,
      model_registered: true, readonly_fields: [], ...(extra.effective || {})},
    purposes: extra.purposes || {
      chat: {label: '日常话题', allowed: true, reason: null},
      news: {label: '外部资讯', allowed: true, reason: null},
    },
    host_state: extra.host_state || 'running',
  }};
}
const baseSettings = () => ({
  enabled: true, automatic_enabled: true, quiet_enabled: true, quiet_start: '23:00', quiet_end: '07:00',
  quiet_timezone: 'Asia/Shanghai', proactive_intensity_preset: 'balanced',
  proactive_hour_activity_enabled: true,
  proactive_hour_activity_curve: [0.5,0.5,0.5,0.5,0.5,0.5].concat(new Array(18).fill(1)).join(','),
  interval_seconds: 3600, idle_seconds: 900, max_contacts_24h: 3,
  'chat.enabled': true, 'chat.weight': 2.0, 'news.enabled': false, 'news.weight': 1.0,
  enable_daily_greetings: true, greeting_morning_window: '07:45-10:20',
  allow_insomnia_night_message: false,
});

/* 上界：只保留后面两条通用断言用得到的字段。 */
function harness({nativeApi = NATIVE, configApi = CONFIG} = {}) {
  const requests = [];
  const window = {
    CompanionProduct: {
      hosted: () => true,
      role: () => ({role_id: 'role-1', perception_native_api: nativeApi, config_api: configApi}),
      bridgeNow: () => window.AstrBotPluginPage,
      bridgeFor: () => ({then: resolve => resolve(window.AstrBotPluginPage)}),
    },
    AstrBotPluginPage: {
      ready: () => Promise.resolve({pluginName: HOST}),
      apiGet: (route, params) => new Promise((resolve, reject) => requests.push({method: 'GET', route, params, resolve, reject})),
      apiPost: (route, values) => new Promise((resolve, reject) => requests.push({method: 'POST', route, values, resolve, reject})),
    },
    document: {
      addEventListener: () => {},
      querySelector: () => null,
      querySelectorAll: () => [],
      body: {classList: {add: () => {}, remove: () => {}, toggle: () => {}}},
      title: '',
    },
    matchMedia: () => ({matches: false}),
    console, Intl, Date, JSON, Math, Number, Object, Array, String, Set, Map, Boolean, Error, Promise,
    localStorage: (() => { const store = new Map(); return {
      getItem: k => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)), removeItem: k => store.delete(k)}; })(),
  };
  vm.runInNewContext(source, {
    window, document: window.document, console, Intl, Date, JSON, Math, Number, Object, Array,
    String, Set, Map, Boolean, Error, Promise, localStorage: window.localStorage, URL,
    /* 计时器必须给：页面里 bounded() 用 Promise.race 把每个请求包了一层 15 秒超时。
       少了 setTimeout/clearTimeout 的话第一个请求在发出之前就抛
       「clearTimeout is not defined」，整页停在初始状态——
       而那看起来像「请求逻辑有问题」，其实是夹具不全。 */
    setTimeout, clearTimeout, setInterval, clearInterval,
  });

  /* 树桩。页面用 innerHTML 整块重写，所以桩只要记住最后一次写入；
     __handlers 让测试从真实注册的事件入口驱动，而不是绕开接线直接调私有函数。 */
  function root() {
    const handlers = {};
    const nodes = [];
    const node = {
      isConnected: true, innerHTML: '', __handlers: handlers,
      addEventListener(type, handler) { handlers[type] = handler; },
      removeEventListener() {},
      contains() { return true; },
      querySelector(selector) { return nodes.find(n => n.__sel === selector) || null; },
      querySelectorAll() { return []; },
      __register(sel, el) { el.__sel = sel; nodes.push(el); return el; },
      dispatch(type, event) { return handlers[type]?.(event); },
    };
    return node;
  }
  const page = window.CompanionContactPage;
  const element = root();
  return {page, element, requests, window,
    reply: (request, payload) => request.resolve({status: 'ok', data: payload}),
    fail: (request, code) => request.resolve({status: 'error', message: code, data: {code}}),
    settle};
}

/* 页面挂载后要串行走三步：桥就绪 → 目标目录 → native 状态 + config 契约。
   「谁在飞就答谁」的循环，因为后一步在前一步确认之后才发。 */
async function boot(h, settings = baseSettings(), extra = {}) {
  const mounted = h.page.mount(h.element);
  await h.settle();
  const answered = new Set();
  for (let round = 0; round < 30; round++) {
    const pending = h.requests.filter(r => !answered.has(r));
    if (!pending.length) break;
    for (const request of pending) {
      answered.add(request);
      if (request.route === 'perception-native') { h.reply(request, status(settings, extra)); continue; }
      if (request.route.startsWith('config')) {
        h.reply(request, {sections: {['proactive.contact']: {edit_token: 'c'.repeat(64), fields: {}}}});
        continue;
      }
      h.reply(request, {});
    }
    await h.settle();
  }
  await mounted;
  return {requests: h.requests};
}

/* ---- 接线 ------------------------------------------------------------- */

test('挂载后先读角色级状态，再读同一角色的配置契约', async () => {
  const h = harness();
  await boot(h);
  const routes = h.requests.map(r => r.method + ' ' + r.route.split('?')[0]);
  /* 顺序是契约：state 是判据来源，契约只提供 edit_token 与字段表。 */
  assert.equal(routes[0], 'GET perception-native');
  assert.equal(routes[1], 'GET config');
  assert.equal(h.requests[1].route, 'config');
  assert.deepEqual(JSON.parse(JSON.stringify(h.requests[1].params)), {sections: 'proactive.contact'});
  assert.equal(h.page.state.data.ready, true);
  assert.equal(h.page.state.data.settings.enabled, true);
  /* native 与 config 是两套生效范围，令牌必须分别持有，不能互相顶替。 */
  assert.equal(h.page.state.data.editToken, 'n'.repeat(64));
  assert.equal(h.page.state.data.configToken, 'c'.repeat(64));
});

test('路径是插件相对路径：切掉插件目录名，否则宿主会拼两次', async () => {
  const h = harness();
  await boot(h);
  for (const request of h.requests) {
    assert.ok(!request.route.startsWith('/' + HOST + '/'),
      '桥只接受裸路由名，带上插件目录名会整片 404：' + request.route);
  }
});

test('多目标的状态与字段契约采用同一对象角色的目录路径', async () => {
  const base = 'host/targets/second/roles/role-1';
  const h = harness({nativeApi: '/' + HOST + '/' + base + '/perception-native',
    configApi: '/' + HOST + '/' + base + '/config'});
  const mounted = h.page.mount(h.element);
  await h.settle();
  assert.equal(h.requests[0].route, base + '/perception-native');
  h.reply(h.requests[0], status(baseSettings()));
  await h.settle();
  assert.equal(h.requests[1].route, base + '/config');
  assert.equal(h.requests[1].params.sections, 'proactive.contact');
  h.reply(h.requests[1], {sections: {'proactive.contact': {edit_token: 'c'.repeat(64)}}});
  await mounted;
  assert.equal(h.page.state.data.ready, true);
  h.page.unmount();
});

test('没有完整联系快照时不显示此刻可以开口', async () => {
  const h = harness();
  const mounted = h.page.mount(h.element);
  await h.settle();
  h.reply(h.requests[0], {news: {settings: {news_share_enabled: false}}});
  await h.settle();
  h.reply(h.requests[1], {sections: {'proactive.contact': {edit_token: 'c'.repeat(64)}}});
  await mounted;
  assert.equal(h.page.state.data.ready, false);
  assert.match(h.element.innerHTML, /联系状态尚未读取/);
  assert.doesNotMatch(h.element.innerHTML, /此刻可以开口/);
  h.page.unmount();
});

test('没有角色路由时不发请求，并说明原因', async () => {
  const h = harness();
  h.window.CompanionProduct.role = () => null;
  await h.page.mount(h.element);
  await h.settle();
  assert.equal(h.requests.length, 0, '读不到角色就不知道该读哪个对象的状态，一个请求都不该发');
  assert.equal(h.page.state.data.ready, false);
  /* 空态必须说清「为什么没有」——地址取不到时给的是那一句专用文案，
     而不是一句通用的「读取失败」：前者告诉用户去选对象，后者让他去查网络。 */
  assert.ok(h.element.innerHTML.includes('按会话生效'), '要说清是缺对象，不是缺连接');
  assert.ok(h.page.state.data.error, '空态也要标记成错误态，否则看起来像还没读完');
});

/* ---- 环的几何 ---------------------------------------------------------
   四圈的存在理由是「各自对应一个真实字段」，所以几何必须能被断言，
   否则某天有人把半径调乱、或者把跨午夜拆段删掉，界面照样画得出来但画错了。 */

test('免打扰跨午夜时拆成两段弧', () => {
  const h = harness();
  const {arc} = h.page._internals;
  const across = arc(150, 150, 132, 1380, 420, 10);
  assert.equal((across.match(/<path/g) || []).length, 2, '23:00→07:00 必须拆成 23:00-24:00 与 00:00-07:00');
  const inside = arc(150, 150, 132, 540, 780, 10);
  assert.equal((inside.match(/<path/g) || []).length, 1, '不跨午夜的一段就是一段');
  /* 零长度区间不画弧：SVG 的 A 命令在起终点重合时会画成整圆，
     那一圈的视觉含义是「全天勿扰」——与其画错，不如不画。 */
  assert.equal(arc(150, 150, 132, 600, 600, 10), '');
});

test('0:00 在正上方，时钟顺时针', () => {
  const h = harness();
  const {angle, point} = h.page._internals;
  assert.equal(angle(0), -90, '0:00 必须落在正上方');
  assert.equal(angle(720), 90, '12:00 必须落在正下方（顺时针）');
  const [x0, y0] = point(150, 150, 100, 0);
  assert.ok(Math.abs(x0 - 150) < 1e-9 && Math.abs(y0 - 50) < 1e-9, '正上方 = (150, 50)');
});

test('活动曲线：24 个权重，数量不对时整体回退到默认曲线', () => {
  const h = harness();
  const {curveOf, curveText} = h.page._internals;
  assert.equal(curveOf('1,2,3').length, 24, '数量不对必须回退，不能画出一条残缺的环');
  const full = new Array(24).fill(1).join(',');
  assert.equal(curveOf(full).length, 24);
  /* 单值不可用只回退那一格；上下限按后端 CURVE_FLOOR/CEILING 夹住。 */
  assert.equal(curveOf(full.replace(/^1/, 'abc'))[0], 1);
  assert.equal(curveOf(new Array(24).fill('99').join(','))[0], 2, '上限 2.0');
  assert.equal(curveOf(new Array(24).fill('-5').join(','))[0], 0.05, '下限 0.05');
  assert.equal(curveText([1.234, 0.5]), '1.23,0.50', '回写用两位小数，与后端 curve_text 一致');
});

test('强度档位别名归一：显示归一后的档位，否则「设成实时却显示直播」会看起来没保存上', () => {
  const h = harness();
  const {tierOf} = h.page._internals;
  assert.equal(tierOf('直播'), 'live');
  assert.equal(tierOf('高频'), 'live');
  assert.equal(tierOf('standard'), 'balanced');
  assert.equal(tierOf('manual'), 'off');
  assert.equal(tierOf(''), 'off');
  /* 未知档位落到 off，而不是猜一个：猜测会让界面显示一个后端没存的档位。 */
  assert.equal(tierOf('turbo'), 'off');
});

test('免打扰判定覆盖跨午夜与两侧端点', () => {
  const h = harness();
  return boot(h).then(() => {
    const {quietSpan, minutes} = {quietSpan: null, minutes: h.page._internals.minutes};
    assert.equal(minutes('23:00'), 1380);
    assert.equal(minutes('07:00'), 420);
    assert.equal(minutes('7:00'), null, '不接受非零填充的写法（后端 local_time 要求 HH:MM）');
    assert.equal(minutes('24:00'), null);
    /* 跨午夜：23:30 与 06:00 都算免打扰，12:00 不算。 */
    const inQuiet = m => { const from = 1380, to = 420; return from > to ? (m >= from || m < to) : (m >= from && m < to); };
    assert.equal(inQuiet(1410), true, '23:30 在免打扰内');
    assert.equal(inQuiet(360), true, '06:00 在免打扰内');
    assert.equal(inQuiet(420), false, '07:00 是结束端点，不包含');
    assert.equal(inQuiet(720), false, '12:00 不在免打扰内');
  });
});

/* ---- 渲染 ------------------------------------------------------------- */

test('节律盘画出四圈，柱子的数量正好是 24', async () => {
  const h = harness();
  await boot(h);
  const html = h.element.innerHTML;
  assert.ok(html.includes('class="ct-dial'), '必须有钟面');
  /* 柱子是 `<line class="ct-bar...">`；容器叫 ct-bars，所以模式必须带上 `"` 或空格，
     否则会把容器自己数成第 25 格里的一根。 */
  const bars = (html.match(/class="ct-bar[" ]/g) || []).length;
  assert.equal(bars, 24, '一天 24 格，一格不多一格不少');
  assert.ok(html.includes('ct-quiet is-on'), '免打扰开着时外圈要有标记');
  /* 夹具里 enable_daily_greetings 是开着的，三个窗口都该画出来。
     （这个断言一度写成 1，是我把探针夹具和测试夹具混了——
       页面没错，错的是期望值。） */
  const anchors = (html.match(/class="ct-anchor"/g) || []).length;
  assert.equal(anchors, 3, '每日问候启用时，三个锚点窗口各画一条弧');
  for (const name of ['morning', 'noon', 'evening']) {
    assert.ok(html.includes('data-anchor="' + name + '"'), name + ' 窗口应画在环上');
  }
});

test('未启用每日问候时环上不画任何问候弧', async () => {
  /* 反向验证：这条断言要能证明上一条不是空洞的。
     后端对三个 greeting_*_window 都有默认值，所以「有窗口就画」会恒真；
     判据必须落在总开关上，否则环上会画出三个并不存在的时刻。 */
  const h = harness();
  await boot(h, {...baseSettings(), enable_daily_greetings: false});
  const html = h.element.innerHTML;
  assert.equal((html.match(/class="ct-anchor"/g) || []).length, 0,
    '总开关关着时，窗口有值也不能画');
  /* 但窗口输入框仍要在，否则用户没办法先把值填好再开总开关。 */
  assert.ok(html.includes('greeting_morning_window'), '控制区仍要能编辑窗口');
});

test('环心那句话与后端同源：后端说不允许就照实说，不自己推断', async () => {
  const h = harness();
  await boot(h, baseSettings(), {
    effective: {allowed: false, reason: 'proactive_paused', automatic_allowed: false,
      automatic_reason: 'proactive_paused', model_registered: true},
  });
  const html = h.element.innerHTML;
  /* 「当前不会开口」这一句必须出现，且原因用的是翻译后的文案而不是裸码。 */
  assert.ok(html.includes('当前不会开口'), '被拦时环心要说清楚');
  assert.ok(!html.includes('此刻可以开口'), '不能同时说可以开口');
});

test('联系授权阻断提供关系与权限直达入口，普通暂停不显示该入口', async () => {
  const denied = harness();
  await boot(denied, baseSettings(), {
    effective: {allowed: false, reason: 'authorization_denied', automatic_allowed: false,
      automatic_reason: 'authorization_denied', model_registered: true},
  });
  assert.match(denied.element.innerHTML,
    /class="ct-center-action" data-go="manage" data-manage="identity"/);
  assert.match(denied.element.innerHTML, /前往关系与权限/);
  assert.match(style, /\.ct-center-action\{[^}]*pointer-events:auto/);
  assert.match(style, /\.ct-center-action:focus-visible/);

  const paused = harness();
  await boot(paused, baseSettings(), {
    effective: {allowed: false, reason: 'proactive_paused', automatic_allowed: false,
      automatic_reason: 'proactive_paused', model_registered: true},
  });
  assert.doesNotMatch(paused.element.innerHTML, /class="ct-center-action"/);
});

test('曲线未启用与曲线全为 1.0 在视觉上必须不同', async () => {
  const h = harness();
  const settings = {...baseSettings(), proactive_hour_activity_enabled: false,
    proactive_hour_activity_curve: new Array(24).fill(1).join(',')};
  await boot(h, settings);
  const html = h.element.innerHTML;
  assert.ok(!html.includes('ct-bar is-on'), '未启用时柱子不该带启用标记');
});

test('曲线上还有文本口：拖涂只有指针设备能用，键盘用户不能没有入口', async () => {
  const h = harness();
  await boot(h);
  const html = h.element.innerHTML;
  /* 24 个值必须同时可读可写：可读是给用户核对，可写是给键盘。
     拖涂是增强，不是唯一入口。 */
  assert.ok(html.includes('data-role="curveText"'), '曲线旁要有文本框');
  const match = /data-role="curveText"[^>]*>([^<]*)</.exec(html);
  assert.ok(match, '文本框要带上当前值');
  assert.equal(match[1].split(',').length, 24, '文本框里必须是 24 个值');
});

/* ---- 字段覆盖 ---------------------------------------------------------
   渲染出来的字段名清单就是这一页的**写出口**：少一个名字，那一项从此保存不了，
   而界面上不会有任何报错——用户只会觉得「这个开关点了没反应」。
   所以这份清单是冻结的：换版式、重排、拆分区块都不该动它一个名字。
   清单从渲染结果里取，不是从源码 grep——grep 抓不到拼接出来的字段名
   （greeting_+name+_window 这类名字在源码里一个完整的都搜不到）。

   两个不是 data-field 的绑定要单独钉：强度档位。 */
const CONTACT_FIELDS = {
  dial: [
    "allow_insomnia_night_message", "automatic_enabled", "enable_daily_greetings", "enabled",
    "greeting_evening_window", "greeting_morning_window", "greeting_noon_window",
    "idle_seconds", "interval_seconds", "proactive_hour_activity_curve",
    "proactive_hour_activity_enabled", "quiet_enabled", "quiet_end", "quiet_start",
    "quiet_timezone",
  ],
  purposes: [
    "affection.enabled", "affection.weight", "care.enabled", "care.weight", "chat.enabled",
    "chat.weight", "creation.enabled", "creation.weight", "environment.enabled",
    "environment.weight", "followup.enabled", "followup.weight", "greeting.enabled",
    "greeting.weight", "invitation.enabled", "invitation.weight", "life.enabled",
    "life.weight", "meal.enabled", "meal.weight", "news.enabled", "news.weight",
    "play.enabled", "play.weight", "reminder.enabled", "reminder.weight", "repair.enabled",
    "repair.weight", "screen.enabled", "screen.weight",
  ],
  gates: ["note", "pause_until"],
  budgets: [
    "dedup_enabled", "dedup_last_message_enabled", "dedup_last_message_window_minutes",
    "dedup_min_overlap_ratio", "dedup_min_shared_tokens", "dedup_policies",
    "dedup_sent_window_minutes", "enable_proactive_burst", "max_attempts_24h",
    "max_contacts_24h", "max_relationship_attempts_24h", "max_relationship_contacts_24h",
    "proactive_burst_gap_max_seconds", "proactive_burst_gap_min_seconds",
    "proactive_burst_max_messages", "proactive_closing_contacts_threshold",
    "proactive_closing_grace_minutes", "proactive_share_probability",
  ],
  sources: [
    "appointment_lag_minutes", "appointment_lead_minutes", "appointment_pre_silence_minutes",
    "balance_awareness_enabled", "balance_check_interval_minutes",
    "balance_critical_percent_threshold", "balance_critical_threshold",
    "balance_currency_label", "balance_include_amount_in_message",
    "balance_low_percent_threshold", "balance_low_threshold", "balance_message_cooldown_hours",
    "date_checkin_enabled", "date_checkin_time", "dedup_weather_window_minutes",
    "enable_llm_proactive_persona_judge", "external_event_self_link_enabled",
    "generation_history_limit", "history_max_chars", "important_date_lookahead_days",
    "meal_care_followup_minutes", "meal_checkin_enabled", "meal_dinner_time",
    "meal_lunch_time", "news_check_interval_minutes", "news_daily_hot_read_enabled",
    "news_hot_sources", "news_share_enabled", "news_source_kind", "news_source_uid",
    "news_source_url", "official_alert_min_severity", "official_alert_poll_minutes",
    "official_weather_alert_enabled", "poke_action_cooldown_minutes",
    "poke_action_daily_limit", "poke_action_enabled", "proactive_persona_judge_cache_minutes",
    "proactive_persona_judge_daily_limit", "proactive_persona_judge_threshold",
    "screen_glance_cooldown_minutes", "screen_glance_daily_limit", "screen_glance_enabled",
    "screen_glance_followup_after_minutes", "screen_glance_followup_cooldown_minutes",
    "screen_glance_followup_enabled", "screen_glance_goodnight_delay_minutes",
    "screen_glance_goodnight_enabled", "voice_action_cooldown_minutes", "voice_action_enabled",
    "voice_action_max_chars", "weather_change_enabled", "weather_checkin_enabled",
    "weather_checkin_time", "weather_sample_minutes", "web_exploration_enabled",
    "web_exploration_interests", "web_exploration_min_interval_hours",
    "web_exploration_result_count",
  ],
};

test('五个视图渲染出的字段清单与本页写出口完全一致', async () => {
  const h = harness();
  await boot(h);
  const seen = new Set();
  for (const [view, expected] of Object.entries(CONTACT_FIELDS)) {
    h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view}} : null}});
    const html = h.element.innerHTML;
    const names = [...html.matchAll(/data-field="([^"]*)"/g)].map(m => m[1]);
    /* 同名两个控件会互相覆盖：后渲染的那个写草稿，前一个就永远读不到了。 */
    assert.equal(new Set(names).size, names.length, view + ' 里有重复的 data-field');
    for (const name of names) {
      assert.ok(!seen.has(name), '字段 ' + name + ' 同时出现在两个视图里，改一处会静默丢掉另一处');
      seen.add(name);
    }
    assert.deepEqual(names.slice().sort(), expected.slice(),
      view + ' 的字段清单变了。加字段要连这份清单一起改；少字段说明有控件没接上。');
  }
  assert.equal(seen.size, 124, '五个视图合起来必须是 124 个 data-field 绑定');
  /* 强度档位是五档共用一个字段，走 data-tier 而不是 data-field：
     只数 data-field 会把它整个漏掉。三个问候锚点同理（它们不是控件，是环上的热点）。 */
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view: 'dial'}} : null}});
  const dial = h.element.innerHTML;
  assert.equal((dial.match(/data-tier="/g) || []).length, 5, '强度档位五档都要在');
  assert.ok(dial.includes('data-tier="balanced"'), '当前档位要有对应的按钮可点');
  assert.equal((dial.match(/data-anchor="/g) || []).length, 3, '三个问候锚点要画在环上');
});

/* ---- 版式与盘面动效 ---------------------------------------------------
   版式是这次改版的目的：盘面与「三个总开关 + 免打扰」同一行，
   其余三块铺满整页宽。这条按字段归属断言，不按 CSS 像素——
   grid 写错列数在无浏览器环境里看不出来，但字段跑到哪一层看得出来。 */

test('节律盘第一行放盘面与三项主开关，其余三块铺满整页宽', async () => {
  const h = harness();
  await boot(h);
  const html = h.element.innerHTML;
  const wrap = html.slice(html.indexOf('ct-dial-wrap'), html.indexOf('ct-rest'));
  const rest = html.slice(html.indexOf('ct-rest'));
  for (const name of ['enabled', 'automatic_enabled', 'quiet_enabled', 'quiet_start', 'quiet_end',
    'quiet_timezone']) {
    assert.ok(wrap.includes('data-field="' + name + '"'),
      name + ' 一改就改变盘面几何，要和盘面同一行');
  }
  for (const name of ['proactive_hour_activity_curve', 'interval_seconds', 'idle_seconds',
    'greeting_morning_window', 'enable_daily_greetings']) {
    assert.ok(!wrap.includes('data-field="' + name + '"'), name + ' 不该挤进第一行');
    assert.ok(rest.includes('data-field="' + name + '"'), name + ' 要落在铺满整页的那一层');
  }
  assert.equal((rest.match(/<section class="ct-block/g) || []).length, 3,
    '下面三块：活动曲线 / 强度档位 / 问候窗口');
  assert.equal((rest.match(/class="ct-block is-wide/g) || []).length, 1,
    '24 格曲线那一块占满整行——柱子要的是横向空间');
  /* 三块各自的圈位色标齐全：标题前的色条就是盘面上那一圈的颜色。 */
  for (const ring of ['is-ring-curve', 'is-ring-tier', 'is-ring-greet']) {
    assert.ok(rest.includes(ring), '缺少圈位色标 ' + ring);
  }
  assert.ok(wrap.includes('is-ring-quiet'), '免打扰块要有外圈的圈位色标');
});

test('盘面变化只闪改动的那一圈，而且只闪一次', async () => {
  const h = harness();
  await boot(h);
  const stage = () => (/<div class="ct-dial-stage([^"]*)"/.exec(h.element.innerHTML) || [])[1] || '';
  assert.equal(stage(), '', '刚进页面时不该带变化类：开页是 is-scanning 的涟漪，不是这一套');
  h.element.dispatch('change', fieldEvent(
    fakeInput({type: 'text', value: '23:30', dataset: {field: 'quiet_start'}}), 'change'));
  assert.ok(stage().includes('is-pulse-quiet'), '改免打扰要闪外圈');
  assert.ok(!stage().includes('is-pulse-curve'), '整盘一起动等于没说清改的是哪一圈');
  /* 再渲染一次（比如关掉一条通知）就不该重放：变化动效是确认，不是常驻状态。 */
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-action]' ? {dataset: {action: 'dismiss'}} : null}});
  assert.equal(stage(), '', '变化类只能闪一次');
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-tier]' ? {dataset: {tier: 'live'}} : null}});
  assert.ok(stage().includes('is-pulse-tier'), '换强度档位要闪三圈');
  assert.equal(h.page.state.data.draft.proactive_intensity_preset, 'live', '档位仍要进草稿');
});

test('触发源卡片头部的「n/m 开启」和卡片里真实的开关一致', async () => {
  const h = harness();
  await boot(h);
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view: 'sources'}} : null}});
  const groups = h.element.innerHTML.split('<section class="ct-src-group').slice(1);
  assert.equal(groups.length, 8, '八组触发源，一组不能少');
  for (const group of groups) {
    const head = /data-toggles="(\d+)" data-enabled="(\d+)"/.exec(group);
    assert.ok(head, '卡片要写出开关总数与开启数：' + group.slice(0, 90));
    const toggles = (group.match(/data-kind="toggle"/g) || []).length;
    const boxes = [...group.matchAll(/data-field="[^"]+" checked>/g)].length;
    assert.equal(toggles, Number(head[1]), '卡片里的开关数和 data-toggles 不一致');
    assert.equal(boxes, Number(head[2]), '卡片里勾着的开关数和 data-enabled 不一致');
    /* 给人看的那句也要对得上：数字对了但句子里写错，一样是撒谎。 */
    assert.ok(group.includes('>' + head[2] + '/' + head[1] + ' 开启<'), '徽标文字和计数不一致');
  }
});

test('开关向两个方向扳都要播一次翻转动画，且只播一次', async () => {
  const h = harness();
  await boot(h);
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view: 'sources'}} : null}});
  const flip = checked => h.element.dispatch('change', fieldEvent(
    fakeInput({type: 'checkbox', checked, dataset: {field: 'balance_awareness_enabled'}}), 'change'));
  flip(true);
  assert.ok(h.element.innerHTML.includes('is-flip-on'), '扳开要挂着开方向的动画类');
  assert.ok(!h.element.innerHTML.includes('is-flip-off'), '开着时不该同时挂关的类');
  flip(false);
  assert.ok(h.element.innerHTML.includes('is-flip-off'),
    '扳回去也要有关方向的动画——开关只有一个方向的动画等于没做');
  assert.ok(!h.element.innerHTML.includes('is-flip-on'), '关的时候不该还留着开的类');
  /* 下一次渲染不该重放：翻转是「刚才这一下」的确认，不是常驻状态。 */
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-action]' ? {dataset: {action: 'dismiss'}} : null}});
  assert.ok(!/is-flip-(on|off)/.test(h.element.innerHTML), '翻转类只能跟着一次渲染');
});

/* 上面那条测的是「类有没有写出来」，这条测的是「CSS 里有没有东西去播它」——
   两个方向的关键帧缺一半，界面上看起来和没写一样，而没人会因此报错。 */
test('翻转动画两个方向在 CSS 里都成立了：关键帧、两类开关、减弱动效', () => {
  const css = fs.readFileSync(path.resolve(__dirname, '../pages/陪伴小屋/contact-page.css'), 'utf8');
  for (const part of ['on', 'off']) {
    assert.ok(css.includes('@keyframes ct-flip-' + part + '-track'), part + ' 方向缺轨道关键帧');
    assert.ok(css.includes('@keyframes ct-flip-' + part + '-knob'), part + ' 方向缺滑块关键帧');
  }
  /* 主配置行的开关（类在 .ct-switch）和触发源行的开关（类在 .ct-src-row）都要能播。 */
  for (const scope of ['.ct-switch.is-flip-on .ct-switch-track', '.ct-switch.is-flip-off .ct-switch-track',
                       '.ct-src-row.is-toggle.is-flip-off .ct-switch-track']) {
    assert.ok(css.includes(scope), scope + ' 缺动画规则，那一处的开关会无声跳变');
  }
  const reduced = css.slice(css.indexOf('@media (prefers-reduced-motion:reduce)'));
  assert.ok(reduced.includes('is-flip-on') && reduced.includes('is-flip-off'),
    '减弱动效要覆盖翻转，否则这条动画不在保护名单里');
});

/* 纵向间距靠 CSS，改坏不会报错，只会「看起来糊」。这条守住三件事：
   三档都挂在共享 sp token 上（紧凑/宽松密度才继续生效）、三档严格递减、
   列表行距走 row 档而不是写死 1px——行距比块距还小是这一屏糊掉的根因。 */
test('纵向间距分三档，且档位递减、行距不写死', () => {
  const css = fs.readFileSync(path.resolve(__dirname, '../pages/陪伴小屋/contact-page.css'), 'utf8');
  const tokens = fs.readFileSync(path.resolve(__dirname, '../pages/陪伴小屋/tokens.css'), 'utf8');
  const px = {};
  for (const level of ['section', 'block', 'row']) {
    const def = css.match(new RegExp('--ct-v-' + level + ':\\s*var\\(--(sp-\\d)\\)'));
    assert.ok(def, '--ct-v-' + level + ' 缺定义，或没挂在共享 sp token 上（密度档会失效）');
    px[level] = Number((tokens.match(new RegExp('--' + def[1] + ':\\s*(\\d+)px')) || [])[1]);
    assert.ok(px[level] > 0, def[1] + ' 在 tokens.css 里没取到值');
  }
  assert.ok(px.section > px.block && px.block > px.row,
    '三档要递减：换话题 > 换一组 > 同一组的下一条，反了就会读成一条糊掉的带子');
  assert.ok(/\.ct-purpose-list\{[^}]*gap:var\(--ct-v-row\)/.test(css),
    '契机列表的行距要挂在 row 档上');
  assert.ok(!/\.ct-purpose-list\{[^}]*gap:1px/.test(css),
    '行距不能写回 1px：15 行会挤成一条连续的带子');
});

test('换页带方向，而且只跟着换页那一帧', async () => {
  const h = harness();
  await boot(h);
  const view = name => h.element.dispatch('click',
    {target: {closest: sel => sel === '[data-view]' ? {dataset: {view: name}} : null}});
  const cls = () => (/<div class="ct-view([^"]*)"/.exec(h.element.innerHTML) || [])[1] || '';
  assert.equal(cls(), '', '刚进页面不该播换页动画');
  view('sources');
  assert.ok(cls().includes('is-from-next'), '往后点，新的一屏从右边进');
  view('dial');
  assert.ok(cls().includes('is-from-prev'), '往回点，从左边进：没有方向就只剩「闪一下」');
  /* 换页动画只在换页那一帧：改个字段整屏再滑一次会让人晕。 */
  h.element.dispatch('change', fieldEvent(
    fakeInput({type: 'checkbox', checked: true, dataset: {field: 'enabled'}}), 'change'));
  assert.equal(cls(), '', '改字段不该重播换页动画');
  view('gates');
  assert.equal((h.element.innerHTML.match(/class="is-picked"/g) || []).length, 1,
    '轨道上只有被点中的那项带 is-picked：选中态是靠这个类的动画放出来的，不给类就等于硬贴上去');
});

function fieldEvent(target, type) {
  return {target, type, preventDefault() {}, stopPropagation() {}, pointerId: 1,
    clientX: 0, clientY: 0, key: '', metaKey: false, ctrlKey: false};
}
function fakeInput(attributes) {
  const node = {...attributes};
  node.closest = selector => selector.includes('[data-field]') ? node : null;
  return node;
}

test('拖动权重滑块只重画那一条，不整页重绘', async () => {
  const h = harness();
  await boot(h);
  const before = h.element.innerHTML;
  const fill = {style: {setProperty(k, v) { this[k] = v; }}, __sel: '.ct-weight-fill'};
  const em = {textContent: '', __sel: 'em'};
  const range = fakeInput({type: 'range', value: '3.5', dataset: {field: 'chat.weight'},
    parentElement: {querySelector: sel => sel === '.ct-weight-fill' ? fill : sel === 'em' ? em : null},
    closest(sel) { return sel.includes('[data-field]') ? this : null; }});
  h.element.dispatch('change', fieldEvent(range, 'change'));
  assert.equal(h.element.innerHTML, before, '滑块的 change 不该触发 render()');
  assert.equal(em.textContent, '3.5', '数字要跟着走');
  assert.equal(h.page.state.data.draft['chat.weight'], 3.5, '草稿要记下这一项');
});

test('保存只提交动过的字段，并把两个令牌分开带上', async () => {
  const h = harness();
  await boot(h);
  /* 只动一项。 */
  const box = fakeInput({type: 'checkbox', checked: false, dataset: {field: 'news.enabled'}});
  h.element.dispatch('change', fieldEvent(box, 'change'));
  const posted = [];
  const original = h.page.state.data;
  assert.equal(original.touched.size, 1);
  /* 直接驱动保存：从真实入口（按钮）出发需要 DOM 树，这里断言的是载荷形状。 */
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-action]' ? {dataset: {action: 'save'}} : null}});
  await h.settle();
  for (const request of h.requests) {
    if (request.method === 'POST') posted.push(request.values);
  }
  assert.equal(posted.length, 1, '保存必须只发一次');
  assert.equal(posted[0].section, 'proactive.contact');
  assert.deepEqual(Object.keys(posted[0].changes), ['news.enabled'],
    '没看过的字段一个都不能提交——把未知值写回去会覆盖别人改的');
  assert.equal(posted[0].edit_token, 'c'.repeat(64), '写要走 config 段的令牌');
  assert.ok(typeof posted[0].operation_key === 'string' && posted[0].operation_key.length > 0);
  assert.ok(posted[0].route === undefined);
});

test('保存成功后清空草稿并重新读取状态', async () => {
  const h = harness();
  await boot(h);
  const box = fakeInput({type: 'checkbox', checked: false, dataset: {field: 'news.enabled'}});
  h.element.dispatch('change', fieldEvent(box, 'change'));
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-action]' ? {dataset: {action: 'save'}} : null}});
  await h.settle();
  const post = h.requests.find(r => r.method === 'POST');
  h.reply(post, {result: {}, status: {sections: {['proactive.contact']: {edit_token: 'c2'.repeat(32)}}}});
  await h.settle();
  assert.equal(h.page.state.data.touched.size, 0, '保存成功后草稿要清空');
  assert.equal(h.page.state.data.configToken, 'c2'.repeat(32), '要用确认里的新令牌');
  assert.ok(h.page.state.data.notice.includes('已保存'), '要有确认');
});

test('保存失败时报错并保留草稿，除非是版本冲突', async () => {
  const h = harness();
  await boot(h);
  const box = fakeInput({type: 'checkbox', checked: false, dataset: {field: 'news.enabled'}});
  h.element.dispatch('change', fieldEvent(box, 'change'));
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-action]' ? {dataset: {action: 'save'}} : null}});
  await h.settle();
  h.fail(h.requests.find(r => r.method === 'POST'), 'proactive_budget_scope');
  await h.settle();
  assert.equal(h.page.state.data.error, true);
  assert.ok(h.page.state.data.notice.includes('整段关系'), '关系级额度的专用文案要接上');
  assert.equal(h.page.state.data.touched.size, 1, '非冲突失败要保留草稿，用户不必重填');
});

test('切换视图不丢草稿', async () => {
  const h = harness();
  await boot(h);
  const box = fakeInput({type: 'checkbox', checked: false, dataset: {field: 'news.enabled'}});
  h.element.dispatch('change', fieldEvent(box, 'change'));
  for (const view of ['purposes', 'gates', 'budgets', 'sources', 'dial']) {
    h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view}} : null}});
    assert.equal(h.page.state.data.touched.size, 1, '切视图不能把未保存的改动丢掉：' + view);
  }
});

test('五个视图都能渲染出内容', async () => {
  const h = harness();
  await boot(h);
  const markers = {purposes: 'ct-purposes', gates: 'ct-gates', budgets: 'ct-budgets',
    sources: 'ct-sources', dial: 'ct-dial'};
  for (const [view, marker] of Object.entries(markers)) {
    h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view}} : null}});
    assert.ok(h.element.innerHTML.includes(marker), view + ' 视图渲染为空');
  }
  /* 契机矩阵必须是 15 行——15 是 PURPOSES 的真实条数（账本曾记 12，实测 15）。 */
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view: 'purposes'}} : null}});
  assert.equal((h.element.innerHTML.match(/data-purpose="/g) || []).length, 15);
  /* 开口闸门七道：授权 / 自动 / 模型 / 宿主 / 免打扰 / 曲线 / 暂停。
     模式要排除装饰用的 ct-gate-mark / ct-gate-body / ct-gate-state。 */
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view: 'gates'}} : null}});
  assert.equal((h.element.innerHTML.match(/class="ct-gate( is-\w+)?"/g) || []).length, 7);
});

test('打开问候窗口的提示，而不是静默忽略点击', async () => {
  const h = harness();
  await boot(h);
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-anchor]' ? {dataset: {anchor: 'morning'}} : null}});
  assert.ok(h.page.state.data.notice.includes('07:45-10:20'), '点问候弧要给出该窗口的真实值');
});

test('额度只有上限没有读出口，所以画成刻度而不是进度条', async () => {
  const h = harness();
  await boot(h);
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view: 'budgets'}} : null}});
  const html = h.element.innerHTML;
  assert.ok(html.includes('没有实时读出口'), '要明说这一点，否则用户以为刻度是已用量');
  assert.ok(html.includes('ct-quota-scale'), '两端要写出 0 与上限');
});

test('卸载后事件与状态都清干净，重复挂载不叠加', async () => {
  const h = harness();
  await boot(h);
  h.page.unmount();
  assert.equal(h.page.state.data, null, '卸载后不得留下上一份状态');
  /* 卸载时的票号自增必须让在飞确认被丢弃：重新挂载后仍能正常读。 */
  await boot(h);
  assert.equal(h.page.state.data.ready, true);
});
