const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.resolve(__dirname, '../pages/陪伴小屋/setup-guide.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
const settle = async () => { for (let i = 0; i < 12; i += 1) await flush(); };

function harness({status, responses = {}, mode = 'single', targets = []}) {
  const calls = [];
  const listeners = {};
  let html = '';
  let currentStatus = status;
  const node = {
    addEventListener: (name, fn) => { listeners[name] = fn; },
    removeEventListener: name => { delete listeners[name]; },
  };
  Object.defineProperty(node, 'innerHTML', {get: () => html, set: value => { html = value; }});
  const product = {
    request(method, route, body) {
      calls.push({method, route, body});
      const key = method + ' ' + route;
      let result = responses[key];
      if (Array.isArray(result)) result = result.length > 1 ? result.shift() : result[0];
      if (result instanceof Error) return Promise.reject(result);
      if (result !== undefined) return Promise.resolve(result);
      if (method === 'GET' && route === 'setup/status') return Promise.resolve(currentStatus);
      return Promise.resolve({});
    },
    targetsMode: () => mode,
    targets: () => targets,
    relative(address) {
      const prefix = '/astrbot_plugin_private_companion_v2/';
      assert.ok(address.startsWith(prefix));
      return address.slice(prefix.length);
    },
  };
  const document = {querySelector: () => null};
  const sandbox = {window: {CompanionProduct: product}, document, Promise, Set, Map, String,
    Number, Object, Array, RegExp, Error, Date, JSON, Math};
  vm.runInNewContext(source, sandbox);
  return {
    calls,
    get html() { return html; },
    mount: () => sandbox.window.CompanionSetup.mount(node),
    click(action) {
      listeners.click({target: {closest(selector) {
        if (selector === '[data-setup-action]') return {dataset: {setupAction: action}};
        if (selector === '[data-setup-legacy-action]') return {dataset: {setupLegacyAction: action}};
        return null;
      }}});
    },
    change(name, value, dataset = {}) {
      listeners.change({target: {name, value, dataset}});
    },
    updateStatus: value => { currentStatus = value; },
  };
}

const readyStatus = extra => ({step: 'complete', ready: true, mode: {accounts: 'single', personas: 'single'},
  completed: ['model', 'knowledge', 'relationships'], skipped: [], proactive_test: {state: 'delivered'}, ...extra});

test('first-run stages show mode, binding, model, knowledge, relationships, then active test', async () => {
  const page = harness({status: {step: 'mode', mode: null, ready: false}});
  page.mount();
  await settle();

  const positions = ['运行模式', '核心管理员窗口', '插件模型', '世界知识', '关系教学', '主动消息测试']
    .map(label => page.html.indexOf(label));
  assert.ok(positions.every(index => index >= 0));
  assert.deepEqual([...positions].sort((a, b) => a - b), positions);
  assert.match(page.html, /单账号/);
  assert.match(page.html, /多人格/);
  assert.doesNotMatch(page.html, /十年|预览模式|review|授权有效期/);
});

test('confirming the core window advances to model without preparing early', async () => {
  const page = harness({status: {step: 'binding', mode: {accounts: 'single', personas: 'single'},
    mode_requires_reload: false, binding: {pending: true, account_id: '100', participant_id: '200'},
    binding_confirmed: false, ready: false}});
  page.mount();
  await settle();
  assert.match(page.html, /companion_bind/);
  assert.match(page.html, /确认此窗口/);
  page.click('confirm-binding');
  await settle();

  assert.ok(page.calls.some(item => item.method === 'POST' && item.route === 'setup/binding/confirm'));
  assert.ok(!page.calls.some(item => item.route === 'setup/prepare'));
});

test('fixed profile binding conflicts remain visible after plugin reload', async () => {
  const reason = '固定运行档的绑定条件发生变化，请检查：Bot 账号、私聊对象。模型参数变化不会阻止连接。';
  const page = harness({status: {step: 'model', mode: {accounts: 'single', personas: 'single'},
    host: {last_failure: {code: 'staging_profile_conflict', reason}},
    model: {provider_id: 'native-model', providers: [{id: 'native-model', name: 'Fixture model'}]},
    ready: false}});
  page.mount();
  await settle();

  assert.match(page.html, /Bot 账号、私聊对象/);
  assert.match(page.html, /模型参数变化不会阻止连接/);
});

test('model choice is saved before the guide advances to knowledge', async () => {
  const model = {step: 'model', mode: {accounts: 'single', personas: 'single'}, ready: false,
    model: {provider_id: '', providers: [{id: 'native-model', name: 'Fixture model'}]}};
  const page = harness({status: model, responses: {
    'GET setup/status': [model, {...model, step: 'knowledge', completed: ['model']}],
    'POST setup/model': {provider_id: 'native-model'},
  }});
  page.mount();
  await settle();
  assert.match(page.html, /主文本 Provider/);
  page.change('setup-provider', 'native-model');
  page.click('save-model');
  await settle();

  const save = page.calls.find(item => item.method === 'POST' && item.route === 'setup/model');
  assert.deepEqual(JSON.parse(JSON.stringify(save.body)), {provider_id: 'native-model'});
  assert.ok(!page.calls.some(item => item.route === 'setup/prepare'));
  assert.match(page.html, /填写世界知识/);
});

test('V1 is not inspected automatically and discovery lists conversion dispositions', async () => {
  const discovery = {v1_root: 'V1-data-root', findings: [
    {source_id: 'private.host_configuration', state: 'ready', detail: '可以迁移到 V2。'},
    {source_id: 'private.core_profiles', state: 'no_handler', detail: '暂缺转换器。'},
    {source_id: 'memory.timeline_and_governance', state: 'read_only', detail: '保持原位可读。'},
  ]};
  const page = harness({status: readyStatus(), responses: {'GET legacy': discovery}});
  page.mount();
  await settle();

  assert.equal(page.calls.some(item => item.route === 'legacy'), false);
  assert.match(page.html, /检查 V1 配置/);
  page.click('legacy-scan');
  await settle();
  assert.match(page.html, /可转换/);
  assert.match(page.html, /暂缺转换器/);
  assert.match(page.html, /只读保留/);
  assert.match(page.html, /V1-data-root/);
});

test('multi-target migration waits for a target and role, then uses that role route', async () => {
  const route = 'host/targets/t-first/roles/role-digest/legacy';
  const catalog = [{target_id: 't-first', bot_id: 'bot-a', roles: [{role_id: 'r-first',
    persona_ids: ['persona-a'], legacy_api: '/astrbot_plugin_private_companion_v2/' + route}]}];
  const page = harness({status: readyStatus({mode: {accounts: 'multiple', personas: 'multiple'}}),
    mode: 'multi', targets: catalog, responses: {[`GET ${route}`]: {findings: [], v1_root: 'selected-root'}}});
  page.mount();
  await settle();
  assert.equal(page.calls.some(item => item.route === route), false);
  assert.match(page.html, /data-setup-legacy="target"/);
  assert.match(page.html, /data-setup-legacy="role"/);

  page.change('', 't-first', {setupLegacy: 'target'});
  page.change('', 'r-first', {setupLegacy: 'role'});
  page.click('legacy-choose');
  await settle();
  assert.ok(page.calls.some(item => item.method === 'GET' && item.route === route));
  assert.equal(page.calls.some(item => item.route === 'legacy'), false);
  assert.match(page.html, /selected-root/);
});

test('completed setup is a one-time receipt with a direct route to daily use', async () => {
  const page = harness({status: readyStatus({host: {accepting: false}})});
  page.mount();
  await settle();

  assert.match(page.html, /首次设置已完成/);
  assert.match(page.html, /不需要重新走向导/);
  assert.match(page.html, /data-go="life"/);
  assert.match(page.html, /<details class="setup-legacy-disclosure">/);
  assert.match(page.html, /首次设置已保留，当前运行实例尚未接收消息/);
  assert.match(page.html, /data-setup-action="reconnect-host"/);
  assert.doesNotMatch(page.html, /setup-step-count|选择运行规模|绑定核心管理员窗口/);
});

test('a running completed setup does not ask the user to reconnect or repeat setup', async () => {
  const page = harness({status: readyStatus({host: {accepting: true}})});
  page.mount();
  await settle();

  assert.match(page.html, /V2 正在接收消息/);
  assert.doesNotMatch(page.html, /data-setup-action="reconnect-host"/);
  assert.doesNotMatch(page.html, /选择运行规模|绑定核心管理员窗口|setup-step-count/);
});

test('migration apply sends the reviewed plan token and refuses locally without a plan', async () => {
  const discovery = {v1_root: 'V1-root', findings: [{source_id: 'private.host_configuration', state: 'ready'}]};
  const plan = {v1_root: 'V1-root', findings: discovery.findings, change_count: 2, plan_token: 'reviewed-token',
    scope_status: [{scope: 'role.state', available: true}], intents: [], differences: [], warnings: []};
  const result = {v1_root: 'V1-root', written_count: 2, written: ['role.state.weather'], skipped: []};
  const page = harness({status: readyStatus(), responses: {
    'GET legacy': discovery,
    'GET legacy/plan': plan,
    'POST legacy/apply': result,
  }});
  page.mount();
  await settle();
  page.click('legacy-apply');
  await settle();
  assert.equal(page.calls.some(item => item.route === 'legacy/apply'), false);

  page.click('legacy-scan');
  await settle();
  page.click('legacy-plan');
  await settle();
  page.click('legacy-apply');
  await settle();
  const applied = page.calls.find(item => item.method === 'POST' && item.route === 'legacy/apply');
  assert.deepEqual(JSON.parse(JSON.stringify(applied.body)), {plan_token: 'reviewed-token'});
  assert.match(page.html, /已写入 2 项 V2 设置/);
});
