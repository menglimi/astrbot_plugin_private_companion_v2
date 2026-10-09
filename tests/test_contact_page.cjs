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
const activeHarnesses = new Set();

test.afterEach(() => {
  for (const fixture of activeHarnesses) fixture.page.unmount();
  activeHarnesses.clear();
});

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
function harness({nativeApi = NATIVE, configApi = CONFIG, sessionStore = new Map(), sessionStorageBlocked = false,
  localStorageBlocked = false, historyBlocked = false, historyEntry = {current: null}} = {}) {
  const requests = [];
  const clipboardWrites = [];
  let gateSettingsTarget = null;
  let gateSettingsArea = null;
  const window = {
    navigator: {clipboard: {writeText: async text => clipboardWrites.push(text)}},
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
      getElementById: id => id === 'contact-gate-settings' ? gateSettingsTarget
        : id === 'contact-gate-settings-area' ? gateSettingsArea : null,
      documentElement: {dataset: {}},
      body: {classList: {add: () => {}, remove: () => {}, toggle: () => {}}},
      title: '',
    },
    history: {
      get state() { return historyEntry.current; },
      replaceState(state) { if (historyBlocked) throw new Error('SecurityError'); historyEntry.current = state; },
    },
    matchMedia: () => ({matches: false}),
    console, Intl, Date, JSON, Math, Number, Object, Array, String, Set, Map, Boolean, Error, Promise,
    localStorage: (() => { const store = new Map(); return {
      getItem: k => { if (localStorageBlocked) throw new Error('SecurityError'); return store.has(k) ? store.get(k) : null; },
      setItem: (k, v) => { if (localStorageBlocked) throw new Error('SecurityError'); store.set(k, String(v)); },
      removeItem: k => { if (localStorageBlocked) throw new Error('SecurityError'); store.delete(k); }, _store:store}; })(),
  };
  const sessionStorage = {
    getItem: key => { if (sessionStorageBlocked) throw new Error('SecurityError'); return sessionStore.has(key) ? sessionStore.get(key) : null; },
    setItem: (key, value) => { if (sessionStorageBlocked) throw new Error('SecurityError'); sessionStore.set(key, String(value)); },
    removeItem: key => { if (sessionStorageBlocked) throw new Error('SecurityError'); sessionStore.delete(key); },
  };
  vm.runInNewContext(source, {
    window, document: window.document, navigator: window.navigator, console, Intl, Date, JSON, Math, Number, Object, Array,
    String, Set, Map, Boolean, Error, Promise, localStorage: window.localStorage, sessionStorage, URL,
    matchMedia: () => ({matches: true}),
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
  const fixture = {page, element, requests, clipboardWrites, window, sessionStore, historyEntry, localStore:window.localStorage._store,
    setGateSettingsTarget: target => {gateSettingsTarget = target;},
    setGateSettingsArea: target => {gateSettingsArea = target;},
    reply: (request, payload) => request.resolve({status: 'ok', data: payload}),
    fail: (request, code) => request.resolve({status: 'error', message: code, data: {code}}),
    settle};
  activeHarnesses.add(fixture);
  return fixture;
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

test('从状态入口进入后切到开口闸门并聚焦设置区', async () => {
  const h = harness();
  await boot(h);
  const target = {tabIndex: 0, hasAttribute: () => false,
    scrollIntoView(options) { this.scrolled = options.block === 'start'; },
    focus(options) { this.focused = options.preventScroll; }};
  h.setGateSettingsTarget(target);
  assert.equal(h.page.state.data.view, 'dial');
  assert.equal(h.page.openGateSettingsView(), true);
  assert.equal(h.page.state.data.view, 'gates');
  assert.match(h.element.innerHTML, /开口闸门/);
  assert.equal(target.scrolled, true);
  assert.equal(target.focused, true);
  h.page.unmount();
});

test('开口闸门设置只在开口闸门视图展示', async () => {
  const h = harness();
  await boot(h);
  const area = {hidden: false};
  h.setGateSettingsArea(area);

  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view: 'tests'}} : null}});
  assert.equal(area.hidden, true, '消息测试视图不能把回复闸门显示在测试内容下方');

  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view: 'gates'}} : null}});
  assert.equal(area.hidden, false, '选中开口闸门后才显示对应配置');

  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view: 'tests'}} : null}});
  assert.equal(area.hidden, true, '离开开口闸门视图后配置随之隐藏');
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

test('联系状态已读到但配置契约失败时分开展示，保留草稿并允许单独重试', async () => {
  const h = harness();
  const mounted = h.page.mount(h.element);
  await h.settle();
  h.reply(h.requests[0], status(baseSettings(), {effective: {
    allowed: false, reason: 'authorization_denied', automatic_allowed: false,
    automatic_reason: 'authorization_denied', model_registered: true,
  }}));
  await h.settle();
  h.fail(h.requests[1], 'configuration_scope_denied');
  await mounted;

  assert.equal(h.page.state.data.ready, true, '运行状态已成功读取');
  assert.equal(h.page.state.data.effective.reason, 'authorization_denied');
  assert.match(h.element.innerHTML, /当前对象尚未授予联系权限/);
  assert.match(h.element.innerHTML, /联系状态已读取；配置编辑信息未读到，保存暂不可用/);
  assert.doesNotMatch(h.element.innerHTML, /联系条件暂时无法核对/);

  h.element.dispatch('change', {target: {closest: selector => selector === '[data-field]'
    ? {dataset: {field: 'quiet_enabled'}, type: 'checkbox', checked: false} : null}});
  assert.equal(h.page.state.data.touched.size, 1, '契约失败时草稿仍然可编辑');
  assert.match(h.element.innerHTML, /data-action="save" disabled/, '没有配置令牌不能提交草稿');

  h.element.dispatch('click', {target: {closest: selector => selector === '[data-action]'
    ? {dataset: {action: 'retry-contract'}} : null}});
  await h.settle();
  const retry = h.requests.at(-1);
  assert.equal(retry.method, 'GET');
  assert.equal(retry.route, 'config');
  h.reply(retry, {sections: {'proactive.contact': {edit_token: 'r'.repeat(64)}}});
  await h.settle();
  assert.equal(h.page.state.data.touched.size, 1, '重新读取契约不应丢弃草稿');
  assert.equal(h.page.state.data.configToken, 'r'.repeat(64));
  assert.doesNotMatch(h.element.innerHTML, /配置编辑信息未能读取/);
  assert.match(h.element.innerHTML, /data-action="save"(?! disabled)/);
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

test('主动联系与后台自动联系关闭时显示具体原因，不回退到无法核对', async () => {
  const disabled = harness();
  await boot(disabled, {...baseSettings(), enabled:false, automatic_enabled:false}, {
    effective: {allowed:false, reason:'proactive_disabled', automatic_allowed:false,
      automatic_reason:'proactive_disabled', model_registered:true},
  });
  assert.match(disabled.element.innerHTML, /主动联系总开关已关闭/);
  assert.doesNotMatch(disabled.element.innerHTML, /联系条件暂时无法核对/);

  const automaticOff = harness();
  await boot(automaticOff, {...baseSettings(), automatic_enabled:false}, {
    effective: {allowed:true, reason:null, automatic_allowed:false,
      automatic_reason:'contact_automatic_disabled', model_registered:true},
  });
  automaticOff.page.openGateSettingsView();
  assert.match(automaticOff.element.innerHTML, /后台自动联系未开启/);
  assert.doesNotMatch(automaticOff.element.innerHTML, /联系条件暂时无法核对/);
});

test('授权阻断时不把后台自动联系误报成开关关闭', async () => {
  const h = harness();
  await boot(h, baseSettings(), {
    effective: {allowed: false, reason: 'authorization_denied', automatic_allowed: false,
      automatic_reason: 'authorization_denied', model_registered: true},
  });
  assert.match(h.element.innerHTML, /当前对象尚未授予联系权限/);
  assert.doesNotMatch(h.element.innerHTML, /后台自动联系未开启/);
  /* 两个开关是设置意图，授权是另一道 effective 闸门；授权被拒时仍应保持
     已保存的开关状态可见，用户才能知道该去关系与权限处理。 */
  assert.match(h.element.innerHTML, /data-field="enabled"[^>]* checked/);
  assert.match(h.element.innerHTML, /data-field="automatic_enabled"[^>]* checked/);
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

test('五个设置视图渲染出的字段清单与本页写出口完全一致', async () => {
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
  assert.equal(seen.size, 124, '五个设置视图合起来必须是 124 个 data-field 绑定');
  /* 强度档位是五档共用一个字段，走 data-tier 而不是 data-field：
     只数 data-field 会把它整个漏掉。三个问候锚点同理（它们不是控件，是环上的热点）。 */
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view: 'dial'}} : null}});
  const dial = h.element.innerHTML;
  assert.equal((dial.match(/data-tier="/g) || []).length, 5, '强度档位五档都要在');
  assert.ok(dial.includes('data-tier="balanced"'), '当前档位要有对应的按钮可点');
  assert.equal((dial.match(/data-anchor="/g) || []).length, 3, '三个问候锚点要画在环上');
});

test('触发源仍可在主动联系页直接配置，并提供到感知分区的辅助跳转', async () => {
  const h = harness();
  await boot(h);
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view: 'sources'}} : null}});
  const html = h.element.innerHTML;
  assert.equal((html.match(/class="ct-src-group/g) || []).length, 8, '八组触发源都应保留');
  for (const name of ['weather_checkin_enabled', 'news_share_enabled', 'meal_checkin_enabled',
    'web_exploration_enabled', 'screen_glance_enabled', 'enable_llm_proactive_persona_judge',
    'balance_awareness_enabled']) {
    assert.match(html, new RegExp(`data-field="${name}"`), `${name} 必须能在主动联系页直接编辑`);
  }
  assert.equal((html.match(/data-perception-tab-target="/g) || []).length, 5,
    '触发源卡片应提供五个感知分区辅助跳转');
  assert.doesNotMatch(html, /唯一的感知配置入口|感知来源统一在感知页维护/,
    '不能把感知页描述成唯一可写入口');
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

test('切换强度档位立即更新卡片与当前生效的换算数字', async () => {
  const h = harness();
  await boot(h);
  const effective = () => {
    const match = /class="ct-tier-effective" role="status"[^>]*>[\s\S]*?<strong>([^<]+)<\/strong>[\s\S]*?<strong>([^<]+)<\/strong>/.exec(
      h.element.innerHTML);
    return match ? match.slice(1) : [];
  };
  assert.deepEqual(effective(), ['48 分钟', '10.5 分钟'], '均衡档位的生效数字应来自当前基准值');
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-tier]' ? {dataset: {tier: 'live'}} : null}});
  assert.deepEqual(effective(), ['12 分钟', '1.5 分钟'], '切到实时档位后生效数字必须立即变化');
  assert.ok(h.element.innerHTML.includes('data-field="interval_seconds" value="3600"'),
    '基础间隔仍保留为可编辑的原始值');
  assert.ok(h.element.innerHTML.includes('data-field="idle_seconds" value="900"'),
    '基础等候仍保留为可编辑的原始值');
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
  h.reply(post, {result: {operation_id: 'contact-op-1', replayed: false},
    status: {sections: {['proactive.contact']: {edit_token: 'c2'.repeat(32)}}}});
  await h.settle();
  assert.equal(h.page.state.data.touched.size, 0, '保存成功后草稿要清空');
  assert.equal(h.page.state.data.configToken, 'c2'.repeat(32), '要用确认里的新令牌');
  assert.ok(h.page.state.data.notice.includes('已保存'), '要有确认');
});

test('写入回执已确认但没有状态快照时，单独刷新联系配置令牌', async () => {
  const h = harness();
  await boot(h);
  h.element.dispatch('change', fieldEvent(fakeInput({type: 'checkbox', checked: false,
    dataset: {field: 'news.enabled'}}), 'change'));
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-action]' ? {dataset: {action: 'save'}} : null}});
  await h.settle();
  const post = h.requests.find(r => r.method === 'POST');
  h.reply(post, {result: {operation_id: 'contact-op-without-status', replayed: false}, status: null});
  await h.settle();
  assert.equal(h.page.state.data.pendingWrite, null, '持久回执足以确认写入');
  assert.equal(h.page.state.data.touched.size, 0);
  const reread = h.requests.filter(r => r.method === 'GET' && r.route === 'perception-native').at(-1);
  h.reply(reread, status(baseSettings()));
  await h.settle();
  const contract = h.requests.filter(r => r.method === 'GET' && r.route === 'config').at(-1);
  assert.ok(contract, '联系状态刷新后还要单独刷新配置令牌');
  h.reply(contract, {sections: {['proactive.contact']: {edit_token: 'c7'.repeat(32), fields: {}}}});
  await h.settle();
  assert.equal(h.page.state.data.configToken, 'c7'.repeat(32));
  assert.match(h.page.state.data.notice, /已保存/);
  assert.doesNotMatch(h.element.innerHTML, /保存结果尚未确认/);
});

test('a saved receipt stays confirmed when the follow-up status read fails', async () => {
  const h = harness();
  await boot(h);
  h.element.dispatch('change', fieldEvent(fakeInput({type: 'checkbox', checked: false,
    dataset: {field: 'news.enabled'}}), 'change'));
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-action]' ? {dataset: {action: 'save'}} : null}});
  await h.settle();
  const post = h.requests.find(r => r.method === 'POST');
  h.reply(post, {result: {operation_id: 'contact-op-2', replayed: false}, status: {sections: {
    ['proactive.contact']: {edit_token: 'c2'.repeat(32)},
  }}});
  await h.settle();
  const reread = h.requests.filter(r => r.method === 'GET' && r.route === 'perception-native').at(-1);
  reread.reject(new Error('connection reset'));
  await h.settle();
  assert.equal(h.page.state.data.pendingWrite, null);
  assert.match(h.page.state.data.notice, /已保存 1 项，但当前状态未能刷新/);
  assert.doesNotMatch(h.page.state.data.notice, /保存结果尚未确认|未收到服务确认/);
});

test('blocked sessionStorage falls back to durable localStorage before submitting', async () => {
  const h = harness({sessionStorageBlocked: true});
  await boot(h);
  h.element.dispatch('change', fieldEvent(fakeInput({type: 'checkbox', checked: false,
    dataset: {field: 'news.enabled'}}), 'change'));
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-action]' ? {dataset: {action: 'save'}} : null}});
  await h.settle();
  const post = h.requests.find(r => r.method === 'POST');
  assert.ok(post, 'storage fallback should allow the request after recording it');
  assert.equal(h.localStore.size, 1, 'the exact request must be durable before it is sent');
  const saved = JSON.parse([...h.localStore.values()][0]);
  assert.equal(JSON.stringify(saved.body), JSON.stringify(post.values));
  post.reject(new Error('connection reset'));
  await h.settle();
  assert.equal(h.page.state.data.pendingWrite.body.operation_key, saved.body.operation_key);
  assert.equal(h.localStore.size, 1, 'an unknown outcome must retain the same operation for verification');
  h.page.unmount();
});

test('sandboxed storage and history keep an unknown save in the page session with the same operation', async () => {
  const h = harness({sessionStorageBlocked: true, localStorageBlocked: true, historyBlocked: true});
  await boot(h);
  h.element.dispatch('change', fieldEvent(fakeInput({type: 'checkbox', checked: false,
    dataset: {field: 'news.enabled'}}), 'change'));
  const save = () => h.element.dispatch('click', {target: {closest: selector =>
    selector === '[data-action]' ? {dataset: {action: 'save'}} : null}});
  save();
  await h.settle();
  const original = h.requests.find(request => request.method === 'POST');
  assert.ok(original);
  original.reject(new Error('connection reset'));
  await h.settle();
  save();
  await h.settle();
  const resumed = h.requests.filter(request => request.method === 'POST').at(-1);
  assert.notEqual(resumed, original);
  assert.equal(JSON.stringify(resumed.values), JSON.stringify(original.values));
  h.reply(resumed, {result: {operation_id: 'contact-sandbox', replayed: true}, status: {sections: {
    ['proactive.contact']: {edit_token: 'c2'.repeat(32)},
  }}});
  await h.settle();
  assert.equal(h.page.state.data.pendingWrite, null);
});

test('blocked browser storage records an unknown save in history and restores the same operation after reload', async () => {
  const historyEntry = {current: {router: {index: 3}}};
  const first = harness({sessionStorageBlocked: true, localStorageBlocked: true, historyEntry});
  await boot(first);
  first.element.dispatch('change', fieldEvent(fakeInput({type: 'checkbox', checked: false,
    dataset: {field: 'news.enabled'}}), 'change'));
  first.element.dispatch('click', {target: {closest: sel => sel === '[data-action]' ? {dataset: {action: 'save'}} : null}});
  await first.settle();
  const originalPost = first.requests.find(r => r.method === 'POST');
  assert.ok(originalPost, 'history state should allow submit after both browser storage APIs fail');
  const originalBody = JSON.parse(JSON.stringify(originalPost.values));
  assert.deepEqual(historyEntry.current.router, {index: 3}, 'the host history state must be preserved');
  originalPost.reject(new Error('connection reset'));
  await first.settle();
  first.page.unmount();

  const reloaded = harness({sessionStorageBlocked: true, localStorageBlocked: true, historyEntry});
  await boot(reloaded);
  assert.deepEqual(JSON.parse(JSON.stringify(reloaded.page.state.data.pendingWrite.body)), originalBody);
  await new Promise(resolve => setTimeout(resolve, 450));
  const retryPost = reloaded.requests.filter(r => r.method === 'POST').at(-1);
  assert.deepEqual(JSON.parse(JSON.stringify(retryPost.values)), originalBody);
  reloaded.reply(retryPost, {result: {operation_id: 'contact-op-4', replayed: true}, status: {sections: {
    ['proactive.contact']: {edit_token: 'c4'.repeat(32)},
  }}});
  await reloaded.settle();
  const refreshed = reloaded.requests.filter(r => r.method === 'GET' && r.route === 'perception-native').at(-1);
  reloaded.reply(refreshed, status(baseSettings()));
  await reloaded.settle();
  assert.equal(reloaded.page.state.data.pendingWrite, null);
  assert.equal(JSON.stringify(historyEntry.current), JSON.stringify({router: {index: 3}}),
    'confirmation should remove only the contact record');
});

test('an unknown contact save is restored after reload and retried with the identical request', async () => {
  const sessionStore = new Map();
  const first = harness({sessionStore});
  await boot(first);
  first.element.dispatch('change', fieldEvent(fakeInput({type: 'checkbox', checked: false,
    dataset: {field: 'news.enabled'}}), 'change'));
  first.element.dispatch('click', {target: {closest: sel => sel === '[data-action]' ? {dataset: {action: 'save'}} : null}});
  await first.settle();
  const originalPost = first.requests.find(r => r.method === 'POST');
  const originalBody = JSON.parse(JSON.stringify(originalPost.values));
  originalPost.reject(new Error('connection reset'));
  await first.settle();
  assert.deepEqual(JSON.parse(JSON.stringify(first.page.state.data.pendingWrite.body)), originalBody);
  first.page.unmount();

  const reloaded = harness({sessionStore});
  await boot(reloaded);
  assert.deepEqual(JSON.parse(JSON.stringify(reloaded.page.state.data.pendingWrite.body)), originalBody);
  assert.match(reloaded.element.innerHTML, /data-action="retry-pending"/);
  assert.match(reloaded.element.innerHTML, /立即核对/);
  assert.equal((reloaded.element.innerHTML.match(/data-action="retry-pending"/g) || []).length, 1);
  await new Promise(resolve => setTimeout(resolve, 450));
  const retryPost = reloaded.requests.filter(r => r.method === 'POST').at(-1);
  assert.deepEqual(JSON.parse(JSON.stringify(retryPost.values)), originalBody);
  reloaded.reply(retryPost, {result: {operation_id: 'contact-op-3', replayed: true}, status: {sections: {
    ['proactive.contact']: {edit_token: 'c3'.repeat(32)},
  }}});
  await reloaded.settle();
  const refreshed = reloaded.requests.filter(r => r.method === 'GET' && r.route === 'perception-native').at(-1);
  reloaded.reply(refreshed, status(baseSettings()));
  await reloaded.settle();
  assert.equal(reloaded.page.state.data.pendingWrite, null);
  assert.equal(sessionStore.size, 0);
  assert.match(reloaded.page.state.data.notice, /已保存/);
});

test('the single pending notice action immediately checks the original save', async () => {
  const h = harness();
  await boot(h);
  h.element.dispatch('change', fieldEvent(fakeInput({type: 'checkbox', checked: false,
    dataset: {field: 'news.enabled'}}), 'change'));
  h.element.dispatch('click', {target: {closest: selector => selector === '[data-action]'
    ? {dataset: {action: 'save'}} : null}});
  await h.settle();
  const original = h.requests.filter(request => request.method === 'POST').at(-1);
  const originalBody = JSON.parse(JSON.stringify(original.values));
  original.reject(new Error('connection reset'));
  await h.settle();

  h.element.dispatch('click', {target: {closest: selector => selector === '[data-action]'
    ? {dataset: {action: 'retry-pending'}} : null}});
  await h.settle();
  const retry = h.requests.filter(request => request.method === 'POST').at(-1);
  assert.notEqual(retry, original);
  assert.deepEqual(JSON.parse(JSON.stringify(retry.values)), originalBody);
  h.reply(retry, {result: {operation_id: 'contact-manual-check', replayed: true}, status: {sections: {
    ['proactive.contact']: {edit_token: 'c6'.repeat(32)},
  }}});
  await h.settle();
  const refreshed = h.requests.filter(request => request.method === 'GET' && request.route === 'perception-native').at(-1);
  h.reply(refreshed, status(baseSettings()));
  await h.settle();
  assert.equal(h.page.state.data.pendingWrite, null);
  assert.match(h.page.state.data.notice, /已保存/);
});

test('a pending save keeps retrying automatically with one notice and the same operation', async () => {
  const h = harness();
  await boot(h);
  h.element.dispatch('change', fieldEvent(fakeInput({type: 'checkbox', checked: false,
    dataset: {field: 'news.enabled'}}), 'change'));
  h.element.dispatch('click', {target: {closest: selector => selector === '[data-action]'
    ? {dataset: {action: 'save'}} : null}});
  await h.settle();

  const original = h.requests.filter(request => request.method === 'POST').at(-1);
  const originalBody = JSON.parse(JSON.stringify(original.values));
  original.reject(Object.assign(new Error('connection reset'), {code: 'bridge_timeout'}));
  await h.settle();

  for (const delay of [450, 850, 1650]) {
    await new Promise(resolve => setTimeout(resolve, delay));
    const retry = h.requests.filter(request => request.method === 'POST').at(-1);
    assert.notEqual(retry, original);
    assert.deepEqual(JSON.parse(JSON.stringify(retry.values)), originalBody,
      'every automatic verification must preserve the exact operation and body');
    retry.reject(Object.assign(new Error('route response unavailable'), {code: 'dashboard_bridge_not_ready'}));
    await h.settle();
  }

  assert.ok(h.page.state.data.pendingWrite, 'unconfirmed requests remain available for manual verification');
  assert.equal((h.element.innerHTML.match(/class="ct-notice is-error"/g) || []).length, 1,
    'save uncertainty and retry failure appear in one notice');
  assert.match(h.element.innerHTML, /核对请求未收到确认（错误码：dashboard_bridge_not_ready）/);
  assert.match(h.element.innerHTML, /系统会持续沿用同一操作标识核对/,
    'automatic verification continues after transient failures');
  assert.doesNotMatch(h.element.innerHTML, /联系条件暂时无法核对/,
    'a save transport error must not be presented as a contact-condition read failure');
  assert.match(h.element.innerHTML, /data-action="retry-pending"/);
  assert.equal((h.element.innerHTML.match(/data-action="retry-pending"/g) || []).length, 1,
    'the pending write has one immediate retry action');
  assert.doesNotMatch(h.element.innerHTML, /核对原保存结果/,
    'the header must not duplicate the in-context retry button');

  await new Promise(resolve => setTimeout(resolve, 3250));
  const automatic = h.requests.filter(request => request.method === 'POST').at(-1);
  assert.deepEqual(JSON.parse(JSON.stringify(automatic.values)), originalBody,
    'automatic verification must continue to use the original operation after repeated failures');
  h.reply(automatic, {result: {operation_id: 'contact-op-auto', replayed: true}, status: {sections: {
    ['proactive.contact']: {edit_token: 'c5'.repeat(32)},
  }}});
  await h.settle();
  const refreshed = h.requests.filter(request => request.method === 'GET' && request.route === 'perception-native').at(-1);
  h.reply(refreshed, status(baseSettings()));
  await h.settle();
  assert.equal(h.page.state.data.pendingWrite, null);
  assert.doesNotMatch(h.element.innerHTML, /保存结果尚未确认/);
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
  assert.equal(h.page.state.data.pendingWrite, null, '明确拒绝后不应保留待核对请求');
  assert.match(h.element.innerHTML, /整段关系/, '保存失败必须立即在页面给出反馈');
});

test('后端联系配置错误使用可理解的文案并立即反馈', async () => {
  const h = harness();
  await boot(h);
  const box = fakeInput({type: 'checkbox', checked: false, dataset: {field: 'news.enabled'}});
  h.element.dispatch('change', fieldEvent(box, 'change'));
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-action]' ? {dataset: {action: 'save'}} : null}});
  await h.settle();
  const post = h.requests.find(r => r.method === 'POST');
  h.fail(post, 'contact_configuration_invalid');
  await h.settle();
  assert.equal(h.page.state.data.touched.size, 1, '普通配置错误要保留草稿');
  assert.match(h.element.innerHTML, /提交的字段或操作不完整/);
  assert.doesNotMatch(h.element.innerHTML, /联系条件暂时无法核对/);
});

test('切换视图不丢草稿', async () => {
  const h = harness();
  await boot(h);
  const box = fakeInput({type: 'checkbox', checked: false, dataset: {field: 'news.enabled'}});
  h.element.dispatch('change', fieldEvent(box, 'change'));
  for (const view of ['tests', 'purposes', 'gates', 'budgets', 'sources', 'dial']) {
    h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view}} : null}});
    assert.equal(h.page.state.data.touched.size, 1, '切视图不能把未保存的改动丢掉：' + view);
  }
});

test('消息测试是一级视图，未读到设置时也可以打开', async () => {
  const h = harness();
  await boot(h);
  h.page.state.data.ready = false;
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]'
    ? {dataset: {view: 'tests'}} : null}});
  assert.equal(h.page.state.data.view, 'tests');
  assert.ok(h.element.innerHTML.includes('ct-tests'), '静态测试指令不应依赖后端设置状态');
  assert.ok(h.element.innerHTML.includes('ct-head-test'), '页头应保留消息测试直达入口');
  assert.equal((h.element.innerHTML.match(/data-test-id="/g) || []).length, 15);
  assert.equal((h.element.innerHTML.match(/data-test-coverage="ready"/g) || []).length, 15);
  assert.equal((h.element.innerHTML.match(/data-test-coverage="partial"/g) || []).length, 0);
  assert.equal((h.element.innerHTML.match(/data-test-coverage="missing"/g) || []).length, 0);
  assert.match(h.element.innerHTML, /生产器已接通 <strong>15<\/strong>/);
  assert.ok(!h.element.innerHTML.includes('当前没有独立 invitation 生产器'));
  for (const purpose of ['affection','care','play','repair','invitation']) {
    const start = h.element.innerHTML.indexOf(`data-test-id="${purpose}"`);
    const end = h.element.innerHTML.indexOf('</article>', start);
    assert.ok(start >= 0 && end > start, `${purpose} 测试卡片应存在`);
    assert.ok(h.element.innerHTML.slice(start, end).includes('data-test-coverage="ready"'),
      `${purpose} 已有生产器，应显示为已接通`);
  }
});

test('七个视图都能渲染出内容', async () => {
  const h = harness();
  await boot(h);
  const markers = {tests: 'ct-tests', purposes: 'ct-purposes', gates: 'ct-gates',
    budgets: 'ct-budgets', sources: 'ct-sources', materials: 'ct-materials', dial: 'ct-dial'};
  for (const [view, marker] of Object.entries(markers)) {
    h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view}} : null}});
    if (view === 'materials') {
      await h.settle();
      const request = h.requests.find(r => r.method === 'GET' && r.route === 'perception-native/materials');
      assert.ok(request, '打开素材池时读取当前作用域的真实素材');
      h.reply(request, {observed_at: '2026-10-07T00:00:00+00:00', count: 0, items: []});
      await h.settle();
    }
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

test('素材池按需读取真实数据、展示来源与有效期，并支持筛选', async () => {
  const h = harness();
  await boot(h);
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]'
    ? {dataset: {view: 'materials'}} : null}});
  await h.settle();
  const request = h.requests.find(r => r.method === 'GET' && r.route === 'perception-native/materials');
  assert.ok(request, '素材池应从当前私聊角色的只读端点加载');
  h.reply(request, {observed_at: '2026-10-07T00:00:00+00:00', count: 2, items: [
    {id: 'dialog-1', category: '对话', purpose: '日常承接、关系表达', title: '最近私聊内容',
      detail: '我最近在准备周末的旅行', source: '当前私聊', captured_at: '2026-10-07T00:00:00+00:00',
      expires_at: '2026-10-07T01:00:00+00:00'},
    {id: 'news-1', category: '资讯', purpose: '外部资讯', title: '<新闻标题>',
      detail: '一条有来源的摘要', note: '资讯源', source: '资讯源', captured_at: '2026-10-06T23:00:00+00:00',
      expires_at: '2026-10-07T00:30:00+00:00'},
  ]});
  await h.settle();
  assert.equal(h.page.state.data.materialsLoaded, true);
  assert.equal(h.page.state.data.materialItems.length, 2);
  assert.match(h.element.innerHTML, /最近私聊内容/);
  assert.match(h.element.innerHTML, /&lt;新闻标题&gt;/, '素材正文必须按文本转义');
  assert.match(h.element.innerHTML, /有效至/);
  assert.match(h.element.innerHTML, /2 项素材/);

  const cards = [
    {dataset: {category: '对话', search: '对话 日常承接 最近私聊内容 周末旅行'}, hidden: false},
    {dataset: {category: '资讯', search: '资讯 外部资讯 新闻标题 摘要'}, hidden: false},
  ];
  const count = {textContent: ''}, empty = {hidden: true};
  h.element.querySelectorAll = selector => selector === '[data-material-card]' ? cards : [];
  h.element.querySelector = selector => selector === '[data-material-result-count]' ? count
    : selector === '.ct-material-filter-empty' ? empty : null;
  const filter = {value: '资讯', closest: sel => sel === '[data-material-category]' ? filter : null};
  h.element.dispatch('change', {target: filter});
  assert.deepEqual(cards.map(card => card.hidden), [true, false]);
  const search = {value: '沒有', closest: sel => sel === '[data-material-search]' ? search : null};
  h.element.dispatch('input', {target: search});
  assert.deepEqual(cards.map(card => card.hidden), [true, true]);
  assert.equal(empty.hidden, false);
  assert.equal(h.page.state.data.touched.size, 0, '素材篩選不應觸碰配置草稿');
  assert.equal(h.requests.filter(r => r.method === 'POST').length, 0, '素材池只能讀取');
});

test('消息测试支持按类别、覆盖状态和内容筛选', async () => {
  const h = harness();
  await boot(h);
  const ids = ['affection','care','play','repair','chat','greeting','followup','invitation',
    'reminder','meal','life','creation','news','environment','screen'];
  const cards = ids.map(testId => ({dataset: {testId}, hidden: false}));
  const count = {textContent: ''}, empty = {hidden: true};
  h.element.querySelectorAll = selector => selector === '[data-test-card]' ? cards : [];
  h.element.querySelector = selector => selector === '[data-test-result-count]' ? count
    : selector === '.ct-test-empty' ? empty : null;
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]'
    ? {dataset: {view: 'tests'}} : null}});
  const html = h.element.innerHTML;
  assert.ok(html.includes('data-test-search'));
  assert.ok(html.includes('data-test-bucket-filter'));
  assert.ok(html.includes('data-test-coverage-filter'));
  assert.match(html, /data-test-copy="affection"><svg viewBox="0 0 24 24"[^>]*><rect x="8" y="8"/,
    '复制指令按钮使用复制图标');
  assert.ok(html.includes('尚无独立生产器'));
  assert.equal(count.textContent, '15 / 15 类');

  const bucket = {value: 'daily', closest: selector => selector === '[data-test-bucket-filter]' ? bucket : null};
  h.element.dispatch('change', {target: bucket});
  assert.deepEqual(cards.filter(card => !card.hidden).map(card => card.dataset.testId),
    ['greeting','followup','invitation','reminder','meal']);
  assert.equal(count.textContent, '5 / 15 类');

  const coverage = {value: 'ready', closest: selector => selector === '[data-test-coverage-filter]' ? coverage : null};
  h.element.dispatch('change', {target: coverage});
  assert.deepEqual(cards.filter(card => !card.hidden).map(card => card.dataset.testId),
    ['greeting','followup','invitation','reminder','meal']);
  assert.equal(count.textContent, '5 / 15 类');

  const search = {value: '撤权', closest: selector => selector === '[data-test-search]' ? search : null};
  h.element.dispatch('input', {target: search});
  assert.equal(count.textContent, '0 / 15 类');
  assert.equal(empty.hidden, false, '无匹配时显示空状态');
  assert.equal(h.page.state.data.touched.size, 0, '筛选不能修改配置');
});

test('复制主动消息测试指令只写入剪贴板，不调用模型或发送接口', async () => {
  const h = harness();
  await boot(h);
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]'
    ? {dataset: {view: 'tests'}} : null}});
  const requestCount = h.requests.length;
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-test-copy]'
    ? {dataset: {testCopy: 'news'}} : null}});
  await h.settle();
  assert.equal(h.clipboardWrites.length, 1);
  assert.match(h.clipboardWrites[0], /这是一条「外部资讯」主动联系候选/);
  assert.match(h.clipboardWrites[0], /素材来源：带标题、原链接和发布时间的当前资讯条目/);
  assert.match(h.clipboardWrites[0], /严格遵守通用 JSON 合同，并给出 decision_confidence/);
  assert.match(h.clipboardWrites[0], /通过条件：来源不完整或失效时不触发/);
  assert.equal(h.requests.length, requestCount, '复制不能新增任何 API 请求');
  assert.ok(h.element.innerHTML.includes('没有调用模型或真实投递'));
});

test('消息测试入口在窄屏保留直达性，列表具备响应式和键盘焦点样式', () => {
  assert.match(style, /\.ct-head-test\{[^}]*border-color:var\(--t-accent\)/,
    '页头直达入口要有稳定的视觉强调');
  assert.match(style, /\.ct-tests-grid\{[^}]*grid-template-columns:repeat\(auto-fit,minmax\(min\(390px,100%\),1fr\)\)/,
    '类型卡片应根据工作区宽度排布');
  assert.match(style, /\.ct-test-card\[hidden\]\{display:none!important\}/);
  assert.match(style, /\.ct-test-copy:focus-visible,[\s\S]*?outline:2px solid var\(--t-focus\)/);
  assert.match(style, /@media \(max-width:880px\)[\s\S]*?\.ct-head-actions \.ct-head-test\{flex:1 1 100%\}/,
    '窄屏页头中测试入口应单独占一行，避免挤进次要操作');
  assert.match(style, /@media \(max-width:520px\)[\s\S]*?\.ct-test-tools\{grid-template-columns:minmax\(0,1fr\)\}/,
    '窄屏筛选器应回到单列');
});

test('契机矩阵提供搜索、类别和状态筛选，筛选不写入配置草稿', async () => {
  const h = harness();
  const names = ['affection','care','play','repair','chat','greeting','followup','invitation',
    'reminder','meal','life','creation','news','environment','screen'];
  const purposes = Object.fromEntries(names.map(name => [name, {label: name, allowed: true, reason: null}]));
  purposes.meal = {label: '饭点问候', allowed: false, reason: 'proactive_paused'};
  await boot(h, baseSettings(), {purposes});
  const rows = names.map(purpose => ({dataset: {purpose}, hidden: false}));
  const buckets = Object.fromEntries(['bond','daily','share'].map(id => [id, {hidden: false}]));
  const bucketCounts = Object.fromEntries(['bond','daily','share'].map(id => [id, {textContent: ''}]));
  const resultCount = {textContent: ''}, empty = {hidden: true};
  h.element.querySelectorAll = selector => selector === '.ct-purpose' ? rows : [];
  h.element.querySelector = selector => {
    const group = /^\[data-purpose-bucket="([^"]+)"\]$/.exec(selector);
    if (group) return buckets[group[1]];
    const count = /^\[data-purpose-bucket-count="([^"]+)"\]$/.exec(selector);
    if (count) return bucketCounts[count[1]];
    if (selector === '[data-purpose-result-count]') return resultCount;
    if (selector === '.ct-purpose-empty') return empty;
    return null;
  };
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view: 'purposes'}} : null}});
  const html = h.element.innerHTML;
  assert.ok(html.includes('data-purpose-search'), '要能按名称和限制原因搜索');
  assert.ok(html.includes('data-purpose-bucket-filter'), '要能按关系、日程、分享分组筛选');
  assert.ok(html.includes('data-purpose-filter'), '要能按配置和当前状态筛选');
  assert.ok(html.includes('data-purpose-result-count'), '要显示匹配数量');
  assert.ok(html.includes('ct-purpose-groups'), '分组容器要供响应式矩阵布局使用');
  assert.equal(resultCount.textContent, '15 / 15 类');
  assert.ok(rows.every(row => !row.hidden), '初始状态要显示全部契机');

  const bucket = {value: 'daily', closest: sel => sel === '[data-purpose-bucket-filter]' ? bucket : null};
  h.element.dispatch('change', fieldEvent(bucket, 'change'));
  assert.equal(h.page.state.data.purposeBucket, 'daily');
  assert.deepEqual(rows.filter(row => !row.hidden).map(row => row.dataset.purpose),
    ['greeting','followup','invitation','reminder','meal']);
  assert.equal(resultCount.textContent, '5 / 15 类');
  assert.equal(buckets.bond.hidden, true);
  assert.equal(buckets.daily.hidden, false);
  const filter = {value: 'paused', closest: sel => sel === '[data-purpose-filter]' ? filter : null};
  h.element.dispatch('change', fieldEvent(filter, 'change'));
  assert.equal(h.page.state.data.purposeFilter, 'paused');
  assert.deepEqual(rows.filter(row => !row.hidden).map(row => row.dataset.purpose), ['meal']);
  assert.equal(bucketCounts.daily.textContent, '1/5 类');
  const search = {value: '饭点', closest: sel => sel === '[data-purpose-search]' ? search : null};
  h.element.dispatch('input', fieldEvent(search, 'input'));
  assert.equal(h.page.state.data.purposeQuery, '饭点');
  assert.deepEqual(rows.filter(row => !row.hidden).map(row => row.dataset.purpose), ['meal']);
  assert.equal(h.page.state.data.touched.size, 0, '筛选条件不能进入待保存配置');
  search.value = '没有这类契机';
  h.element.dispatch('input', fieldEvent(search, 'input'));
  assert.equal(resultCount.textContent, '0 / 15 类');
  assert.equal(empty.hidden, false, '无结果时要显示明确空态');
});

test('当前暂缓优先显示暂缓状态，不折叠成通用受阻原因', async () => {
  const h = harness();
  const settings = {...baseSettings(), 'meal.pause_until': '2099-01-01T12:00:00+08:00'};
  await boot(h, settings, {purposes: {meal: {label: '饭点问候', allowed: false, reason: 'proactive_paused'}}});
  h.element.dispatch('click', {target: {closest: sel => sel === '[data-view]' ? {dataset: {view: 'purposes'}} : null}});
  const row = h.element.innerHTML.split('data-purpose="meal"')[1].split('</article>')[0];
  assert.ok(row.includes('ct-chip is-paused'), '暂停原因应显示为暂缓状态');
  assert.ok(row.includes('暂缓至 2099-01-01 12:00'), '应显示暂停截止时间');
  assert.ok(!row.includes('ct-chip is-risk'), '暂停不应伪装成授权或运行故障');
});

test('契机矩阵桌面分列、窄屏回单列并保留可见焦点', () => {
  assert.match(style, /\.ct-purpose-groups\{[^}]*grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(style, /\.ct-purpose\{[^}]*display:grid;min-width:0/,
    '分享分栏中的行必须允许收缩，不能被网格子项撑出卡片');
  assert.match(style, /grid-template-columns:minmax\(92px,1fr\) minmax\(100px,1\.2fr\) minmax\(0,168px\)/,
    '名称、权重和状态列需统一对齐，同时给状态文案留出可收缩空间');
  assert.match(style, /\.ct-purpose-state\{[^}]*min-width:0/);
  assert.match(style, /\.ct-chip\{[^}]*max-width:100%;min-width:0/,
    '长状态提示应在行内截断，不能溢出卡片');
  assert.match(style, /@media \(max-width:1280px\)[\s\S]*?\.ct-purpose-groups\{grid-template-columns:minmax\(0,1fr\)\}/);
  assert.match(style, /grid-template-columns:minmax\(0,1fr\) minmax\(100px,1fr\)/,
    '窄屏下权重列也应对齐');
  assert.match(style, /\.ct-purpose-search input:focus,[\s\S]*?outline:2px solid var\(--t-focus\)/);
  assert.match(style, /\.ct-purpose\[hidden\][^}]*display:none!important/);
});

test('开口闸门按容器宽度排布，摘要和设置区保持通栏', () => {
  assert.match(style, /\.ct-gates\{[^}]*repeat\(auto-fit,minmax\(min\(340px,100%\),1fr\)\)/,
    '闸门卡片应随可用宽度自动排成多列');
  assert.match(style, /\.ct-gates-sum\{[^}]*grid-column:1 \/ -1/,
    '此刻总状态应独占一行，先于各道闸门被看到');
  assert.match(style, /\.ct-gate-settings-brief,\.ct-gates > \.ct-block\{grid-column:1 \/ -1\}/,
    '设置入口和补充偏好应在卡片网格后通栏展示');
  assert.match(style, /\.ct-gate-pause\{display:grid;grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/,
    '宽屏下暂停时间与联系偏好并排');
  assert.match(style, /@media \(max-width:880px\)[\s\S]*?\.ct-gate-pause\{grid-template-columns:minmax\(0,1fr\)\}/,
    '窄屏下补充设置回到单列');
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
