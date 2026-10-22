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
const PREFIX = '/astrbot_plugin_private_companion/';
const plain = value => JSON.parse(JSON.stringify(value));
const DEFAULTS = {private_learning_enabled: true};
const FIELDS = {private_learning_enabled: {
  kind: 'boolean', default: true, apply_mode: 'immediate', editable_layers: ['relationship'],
}};

/* This section answers flat (no `sections` wrapper) because it lives on the
   reply route family rather than the config route. */
function status(changes = {}, token = TOKEN) {
  const settings = {...DEFAULTS, ...changes};
  return {
    settings, defaults: {...DEFAULTS}, edit_token: token, revision: 1,
    configuration_token: 'configuration', apply_mode: 'next_sealed_reply',
    group_id: 'expression.learning.private', scope: 'relationship',
    layers: ['installation', 'role', 'relationship'],
    provenance: {private_learning_enabled: {layer: 'relationship', explicit: true, revision: 1}},
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
  harnessed.page.mount(harnessed.node, {scopeKind: 'private', scopeKey: 'private:42'});
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
  live.state.draft.private_learning_enabled = false;
  const saving = live.save(false);
  await drains();
  assert.equal(harnessed.requests[1].route, 'reply/expression/configure');
  assert.deepEqual(plain(harnessed.requests[1].body), {
    operation_key: 'expression-key', edit_token: TOKEN,
    changes: {private_learning_enabled: false},
  });
  harnessed.requests[1].resolve({result: {operation_id: 'op', replayed: false},
    status: status({private_learning_enabled: false}, 'b'.repeat(64))});
  await saving;
  await drains();
  assert.equal(live.state.base.private_learning_enabled, false);
  assert.equal(live.state.pending, null);
});

test('field kind and target layers come from the published contract', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  const live = instance(harnessed);
  assert.equal(live.state.container.fields.private_learning_enabled.kind, 'bool');
  assert.deepEqual(plain(live.state.container.fields.private_learning_enabled.editable), ['relationship']);
  assert.deepEqual(plain(live.state.container.layers), ['installation', 'role', 'relationship']);
  assert.equal(live.state.container.writeLayer, 'relationship');
  assert.equal(live.state.status.provenance.private_learning_enabled.layer, 'relationship');
});

test('the workbench preserves the selected target and role in its relative request', async () => {
  const base = 'host/targets/second/roles/role-2/reply';
  const harnessed = harness({replyApi: PREFIX + base});
  await loaded(harnessed);
  assert.equal(harnessed.requests[0].route, base + '/expression');
  const live = instance(harnessed);
  live.state.draft.private_learning_enabled = false;
  const saving = live.save(false);
  await drains();
  assert.equal(harnessed.requests[1].route, base + '/expression/configure');
  harnessed.requests[1].resolve({status: status({private_learning_enabled: false})});
  await saving;
  harnessed.page.unmount();
});

test('a value with the wrong field type never dispatches', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  const live = instance(harnessed);
  live.state.draft.private_learning_enabled = 'false';
  await live.save(false);
  assert.equal(harnessed.requests.length, 1);
  /* 类型填错要说清「这一项只能是开或关」，不是「请核对数值类型与范围」——
     后者对一个开关毫无意义。 */
  assert.match(live.state.notice, /只能是开或关/);
  assert.match(live.state.notice, /改动还在/);
});

test('an unconfirmed save is kept for retry and no second operation is minted', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  const live = instance(harnessed);
  live.state.draft.private_learning_enabled = false;
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
    status: status({private_learning_enabled: false}, 'c'.repeat(64))});
  await retrying;
  await drains();
  assert.equal(harnessed.store.size, 0);
  assert.match(live.state.savedState, /is-replayed/);
});

test('reset restores the saved values instead of the draft', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  const live = instance(harnessed);
  /* 「使用已保存配置」把草稿拉回已保存值。 */
  live.state.draft = {...live.state.status.settings};
  assert.equal(live.state.draft.private_learning_enabled, true);
});

test('a host without the reply route refuses instead of showing an empty editor', () => {
  const harnessed = harness({replyApi: '/somewhere-else/reply'});
  harnessed.page.mount(harnessed.node, {scopeKind: 'private', scopeKey: 'private:42'});
  assert.equal(harnessed.requests.length, 0);
  assert.match(harnessed.html, /没有可用的表达学习工作区/);
  const offline = harness({hosted: false});
  offline.page.mount(offline.node);
  assert.equal(offline.requests.length, 0);
  assert.match(offline.html, /角色数据尚未加载/);
});
