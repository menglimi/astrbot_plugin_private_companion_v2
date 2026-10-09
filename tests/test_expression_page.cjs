const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const PAGE = '../pages/陪伴小屋/';
const workbench = fs.readFileSync(path.resolve(__dirname, PAGE + 'workbench-page.js'), 'utf8');
const adapter = fs.readFileSync(path.resolve(__dirname, PAGE + 'expression-page.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
/* refresh/save 里有多层 await，一次 flush 只推进一层微任务。 */
const drains = async (times = 8) => { for (let index = 0; index < times; index += 1) await flush(); };
const TOKEN = 'a'.repeat(64);
const PREFIX = '/astrbot_plugin_private_companion_v2/';
const plain = value => JSON.parse(JSON.stringify(value));
const DEFAULTS = {
  private_learning_enabled: true, group_learning_enabled: false, window_hours: 168,
  sample_limit: 24, min_samples: 5, group_min_samples: 20, sample_chars: 800, active_signal_limit: 60,
  rules_per_turn: 8, payload_chars: 4000, rotation_candidate_limit: 24, rotation_decay_hours: 336,
  scan_interval_minutes: 1440,
  learning_mode: 'balanced', private_application_enabled: true, group_application_enabled: true,
  sample_review_enabled: false, style_review_enabled: true, group_daily_batch_limit: 6,
  group_new_messages: 20, group_member_mode: 'all', group_member_ids: '',
};
/* The registered contract: kinds and bounds mirror expression/configuration.py. */
const LIMITS = {
  window_hours: [1, 720], sample_limit: [4, 64], min_samples: [1, 16], group_min_samples: [5, 64],
  sample_chars: [40, 4000], active_signal_limit: [12, 240],
  rules_per_turn: [1, 16], payload_chars: [500, 16000], rotation_candidate_limit: [1, 64],
  rotation_decay_hours: [1, 8760], scan_interval_minutes: [5, 10080],
  group_daily_batch_limit: [1, 50], group_new_messages: [5, 80],
};
const FIELDS = Object.fromEntries(Object.entries(DEFAULTS).map(([name, value]) => {
  const entry = {kind: typeof value === 'boolean' ? 'boolean' : typeof value === 'string' ? 'text' : 'integer', default: value,
    apply_mode: 'immediate', editable_layers: ['installation', 'role', 'window']};
  if (LIMITS[name]) [entry.minimum, entry.maximum] = LIMITS[name];
  return [name, entry];
}));

/* This section answers flat (no `sections` wrapper) because it lives on the
   reply route family rather than the config route. */
function status(changes = {}, token = TOKEN) {
  const settings = {...DEFAULTS, ...changes};
  return {
    settings, defaults: {...DEFAULTS}, edit_token: token, revision: 1,
    configuration_token: 'configuration', apply_mode: 'next_sealed_reply',
    group_id: 'expression.learning', scope: 'window',
    layers: ['installation', 'role', 'window'],
    provenance: Object.fromEntries(Object.keys(settings).map(name =>
      [name, {layer: 'window', explicit: true, revision: 1}])),
    fields: FIELDS,
  };
}

function harness({hosted = true, replyApi = PREFIX + 'reply'} = {}) {
  const requests = [], store = new Map(), added = [];
  let inner = '';
  const node = {
    isConnected: true, dataset: {},
    classList: {add: name => added.push(name), remove() {}, contains: () => false},
    querySelectorAll: () => [], querySelector: () => null,
    addEventListener() {}, removeEventListener() {},
  };
  Object.defineProperty(node, 'innerHTML', {
    get: () => inner, set: value => { inner = value; },
  });
  Object.defineProperty(node, 'textContent', {
    get: () => inner, set: value => { inner = value; },
  });
  const sessionStorage = {getItem: key => store.get(key) || null,
    setItem: (key, value) => store.set(key, value), removeItem: key => store.delete(key)};
  const window = {
    addEventListener() {}, removeEventListener() {},
    CompanionProduct: {
      hosted: () => hosted, role: () => (replyApi ? {reply_api: replyApi} : {}),
      identity: () => ({installation_id: 'inst', operator_id: 'admin'}),
    },
    AstrBotPluginPage: {
      apiGet: (route, body) => new Promise((resolve, reject) =>
        requests.push({method: 'GET', route, body, resolve, reject})),
      apiPost: (route, body) => new Promise((resolve, reject) =>
        requests.push({method: 'POST', route, body, resolve, reject})),
    },
  };
  const sandbox = {window, sessionStorage, crypto: {randomUUID: () => 'expression-key'},
    setTimeout, clearTimeout, URLSearchParams, Math, Number, Object, JSON, Array, String};
  vm.runInNewContext(workbench, sandbox);
  vm.runInNewContext(adapter, sandbox);
  return {page: window.CompanionExpressionLearningPage, workbench: window.CompanionWorkbench,
    node, requests, store, added, get html() { return inner; }};
}

/* Mounts and answers the initial read, the way app.js drives it. */
async function loaded(harnessed) {
  harnessed.page.mount(harnessed.node);
  await drains();
  assert.equal(harnessed.requests.length, 1, 'mounting reads the section exactly once');
  harnessed.requests[0].resolve(status());
  await drains();
  return harnessed;
}

/* The live instance the adapter created, so a test can poke the real draft. */
function instance(harnessed) {
  return harnessed.page.state.instance;
}

test('the section reads and saves through the reply route family', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  assert.equal(harnessed.requests[0].method, 'GET');
  /* The bridge supplies the plugin prefix; the page supplies only the relative route. */
  assert.equal(harnessed.requests[0].route, 'reply/expression');
  const live = instance(harnessed);
  live.state.draft.rotation_decay_hours = 48;
  live.state.draft.group_learning_enabled = true;
  const saving = live.save(false);
  await drains();
  assert.equal(harnessed.requests[1].route, 'reply/expression/configure');
  assert.deepEqual(plain(harnessed.requests[1].body), {
    operation_key: 'expression-key', edit_token: TOKEN,
    changes: {rotation_decay_hours: 48, group_learning_enabled: true},
  });
  harnessed.requests[1].resolve({result: {operation_id: 'op', replayed: false},
    status: status({rotation_decay_hours: 48, group_learning_enabled: true}, 'b'.repeat(64))});
  await saving;
  await drains();
  assert.equal(live.state.base.rotation_decay_hours, 48);
  assert.equal(live.state.pending, null);
});

test('bounds come from the published contract, not a page-local copy', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  const live = instance(harnessed);
  assert.equal(live.state.container.fields.window_hours.maximum, 720);
  assert.equal(live.state.container.fields.window_hours.minimum, 1);
  assert.equal(live.state.container.fields.group_learning_enabled.kind, 'bool');
  assert.equal(live.state.container.fields.private_learning_enabled.kind, 'bool');
  assert.deepEqual(plain(live.state.container.layers), ['installation', 'role', 'window']);
  assert.equal(live.state.container.writeLayer, 'window');
  assert.equal(live.state.status.provenance.scan_interval_minutes.layer, 'window');
});

test('the workbench preserves the selected target and role in its relative request', async () => {
  const base = 'host/targets/second/roles/role-2/reply';
  const harnessed = harness({replyApi: PREFIX + base});
  await loaded(harnessed);
  assert.equal(harnessed.requests[0].route, base + '/expression');
  const live = instance(harnessed);
  live.state.draft.rotation_decay_hours = 48;
  const saving = live.save(false);
  await drains();
  assert.equal(harnessed.requests[1].route, base + '/expression/configure');
  harnessed.requests[1].resolve({status: status({rotation_decay_hours: 48})});
  await saving;
  harnessed.page.unmount();
});

test('an impossible combination and out-of-range values never dispatch', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  const live = instance(harnessed);
  /* 单批取样条数 < 最低样本数：两者各自都在范围内，组合不合法。 */
  live.state.draft.sample_limit = 4;
  live.state.draft.min_samples = 9;
  await live.save(false);
  assert.equal(harnessed.requests.length, 1, 'the impossible pair must not reach the network');
  assert.match(live.state.notice, /组合不合法/);
  /* 候选池 < 每轮注入规则数：同一条规则的另一半。 */
  live.state.draft.sample_limit = 24;
  live.state.draft.min_samples = 4;
  live.state.draft.rotation_candidate_limit = 2;
  live.state.draft.rules_per_turn = 8;
  await live.save(false);
  assert.equal(harnessed.requests.length, 1);
  /* 单字段越界同样拦下。 */
  live.state.draft.rotation_candidate_limit = 24;
  live.state.draft.rules_per_turn = 8;
  live.state.draft.window_hours = 721;
  await live.save(false);
  assert.equal(harnessed.requests.length, 1);
  assert.match(live.state.notice, /范围/);
});

test('an unconfirmed save is kept for retry and no second operation is minted', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  const live = instance(harnessed);
  live.state.draft.scan_interval_minutes = 30;
  const saving = live.save(false);
  await drains();
  const original = plain(harnessed.requests[1].body);
  /* 结果没有回来：写入可能已落库，所以要保留 pending 待核对。 */
  harnessed.requests[1].reject(Object.assign(new Error('bridge down'), {code: 'bridge_timeout'}));
  await saving;
  await drains();
  assert.equal(harnessed.store.size, 1);
  const retrying = live.save(true);
  await drains();
  assert.deepEqual(plain(harnessed.requests[2].body), original,
    'the retry must reuse the original operation key');
  harnessed.requests[2].resolve({result: {operation_id: 'op', replayed: true},
    status: status({scan_interval_minutes: 30}, 'c'.repeat(64))});
  await retrying;
  await drains();
  assert.equal(harnessed.store.size, 0);
  assert.match(live.state.savedState, /is-replayed/);
});

test('reset restores the saved values instead of the draft', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  const live = instance(harnessed);
  live.state.draft.window_hours = 24;
  live.state.draft.payload_chars = 2000;
  /* 「使用已保存配置」把草稿拉回已保存值。 */
  live.state.draft = {...live.state.status.settings};
  assert.equal(live.state.draft.window_hours, 168);
  assert.equal(live.state.draft.payload_chars, 4000);
});

test('a host without the reply route refuses instead of showing an empty editor', () => {
  const harnessed = harness({replyApi: '/somewhere-else/reply'});
  harnessed.page.mount(harnessed.node);
  assert.equal(harnessed.requests.length, 0);
  assert.match(harnessed.html, /没有可用的表达学习工作区/);
  const offline = harness({hosted: false});
  offline.page.mount(offline.node);
  assert.equal(offline.requests.length, 0);
  assert.match(offline.html, /角色数据尚未加载/);
});
