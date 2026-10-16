const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const sourcePath = process.env.COMPANION_SETUP_GUIDE_SOURCE
  ? path.resolve(process.env.COMPANION_SETUP_GUIDE_SOURCE)
  : path.resolve(__dirname, '../pages/陪伴小屋/setup-guide.js');
const source = fs.readFileSync(sourcePath, 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
const settle = async () => { for (let i = 0; i < 12; i += 1) await flush(); };

function harness({status, responses = {}, targets = [], bridgeResponses = {}, configEditorsAvailable = true}) {
  const calls = [];
  const bridgeCalls = [];
  const editorCalls = [];
  const editorStops = [];
  const replyMounts = [];
  const stateMounts = [];
  const listeners = {};
  let html = '';
  let currentStatus = status;
  const mountHosts = {
    '#setupAdvancedEditorHost': {},
    '#setupQuickReplyHost': {},
    '#setupQuickDecisionHost': {},
    '#setupQuickStateHost': {},
  };
  const node = {
    addEventListener: (name, fn) => { listeners[name] = fn; },
    removeEventListener: name => { delete listeners[name]; },
    querySelector: selector => mountHosts[selector] || null,
  };
  Object.defineProperty(node, 'innerHTML', {get: () => html, set: value => { html = value; }});
  const product = {
    request(method, route, body, options) {
      calls.push({method, route, body, options});
      const key = method + ' ' + route;
      let result = responses[key];
      if (Array.isArray(result)) result = result.length > 1 ? result.shift() : result[0];
      if (result instanceof Error) return Promise.reject(result);
      if (result !== undefined) return Promise.resolve(result);
      if (method === 'GET' && route === 'setup/status') return Promise.resolve(currentStatus);
      return Promise.resolve({});
    },
    targets: () => targets,
    role: () => configEditorsAvailable ? {reply_api: '/astrbot_plugin_private_companion_v2/reply/current',
      model_api: '/astrbot_plugin_private_companion_v2/model'} : null,
    scopeKey: () => 'installation-a:target-a:role-a',
    unwrap: response => response,
    relative(address) {
      const prefix = '/astrbot_plugin_private_companion_v2/';
      assert.ok(address.startsWith(prefix));
      return address.slice(prefix.length);
    },
  };
  const document = {querySelector: () => null};
  const bridge = {apiPost(route, body) {
    bridgeCalls.push({route, body});
    const result = bridgeResponses[route];
    return Promise.resolve(typeof result === 'function' ? result(body) : result || {});
  }};
  const configEditors = configEditorsAvailable ? {create(kinds, rootProvider, views) {
    editorCalls.push({kinds: [...kinds], host: rootProvider(), views});
    return {restore() {}, paint() {}, read() {}, stop() { editorStops.push([...kinds]); }};
  }} : null;
  const sandbox = {window: {CompanionProduct: product, CompanionConfigEditors: configEditors,
    CompanionWorkbench: configEditorsAvailable ? {create() {}} : null, AstrBotPluginPage: bridge,
    CompanionReplyPage: {mount(element, options) { replyMounts.push({element, options}); }, unmount() {}},
    CompanionStatePage: {mount(element, options) { stateMounts.push({element, options}); }, unmount() {}}}, document, Promise, Set, Map, String,
    Number, Object, Array, RegExp, Error, Date, JSON, Math, setTimeout, clearTimeout};
  vm.runInNewContext(source, sandbox);
  return {
    calls,
    bridgeCalls,
    get html() { return html; },
    mount: () => sandbox.window.CompanionSetup.mount(node),
    mountMigration: () => sandbox.window.CompanionSetup.mountMigration(node),
    click(action) {
      listeners.click({target: {closest(selector) {
        if (selector === '[data-setup-action]' && !action.startsWith('legacy-')) return {dataset: {setupAction: action}};
        if (selector === '[data-setup-legacy-action]' && action.startsWith('legacy-')) return {dataset: {setupLegacyAction: action}};
        return null;
      }}});
    },
    clickLegacyDestination(kind, personaId, destinationId = '') {
      listeners.click({target: {closest(selector) {
        if (selector === '[data-setup-legacy-batch-add]' && kind === 'add') {
          return {dataset: {setupLegacyBatchAdd: personaId}};
        }
        if (selector === '[data-setup-legacy-batch-remove]' && kind === 'remove') {
          return {dataset: {setupLegacyBatchRemove: personaId, destinationId}};
        }
        return null;
      }}});
    },
    clickBlock(block) {
      listeners.click({target: {closest: selector => selector === '[data-setup-advanced-block]'
        ? {dataset: {setupAdvancedBlock: block}} : null}});
    },
    change(name, value, dataset = {}, extra = {}) {
      listeners.change({target: {name, value, dataset, ...extra}});
    },
    updateStatus: value => { currentStatus = value; },
    editorCalls,
    editorStops,
    replyMounts,
    stateMounts,
  };
}

const readyStatus = extra => ({step: 'complete', prepared: true, ready: true,
  completed: ['model', 'knowledge', 'relationships'], skipped: [], proactive_test: {state: 'delivered'}, ...extra});

async function plannedMultiDestinationPage(firstApplyResponse) {
  const firstRoute = 'host/targets/t-first/roles/r-first/legacy';
  const secondRoute = 'host/targets/t-second/roles/r-second/legacy';
  const targets = [
    {target_id: 't-first', display_name: '账号一', roles: [{role_id: 'r-first', role_name: '角色一',
      legacy_api: '/astrbot_plugin_private_companion_v2/' + firstRoute}]},
    {target_id: 't-second', display_name: '账号二', roles: [{role_id: 'r-second', role_name: '角色二',
      legacy_api: '/astrbot_plugin_private_companion_v2/' + secondRoute}]},
  ];
  const plan = (token, personaId) => ({plan_token: token, source_persona_id: personaId,
    source_fingerprint: 'source-fingerprint', archive: {fingerprint: 'archive-fingerprint'},
    reaction_assets: {batch_count: 1}, journals: {batch_count: 0},
    reference_images: {batch_count: 1}, wardrobe_items: {batch_count: 1, image_count: 1},
    worldbook: {general_count: 0, member_count: 0, base_entries_matches: false, base_members_matches: false}});
  const basePlan = {plan_token: 'base-plan', archive: {fingerprint: 'archive-fingerprint'},
    persona_sources: [{persona_id: 'persona-a', label: 'V1 人格：persona-a', state: 'ready'}],
    reaction_assets: {batch_count: 1}, journals: {batch_count: 0}, worldbook: {general_count: 0, member_count: 0},
    group_networks: [], memory_database: {state: 'absent'}, warnings: []};
  const firstResult = firstApplyResponse === undefined ? {source_persona_id: 'persona-a', errors: [],
    reaction_created: 1, reaction_remaining: 0, journal_created: 0, journal_remaining: 0,
    journal_derivatives_remaining: 0} : firstApplyResponse;
  const page = harness({status: readyStatus(), targets, responses: {
    ['GET ' + firstRoute + '/data-plan']: [basePlan, plan('preview-first', 'persona-a'), plan('fresh-first', 'persona-a')],
    ['GET ' + secondRoute + '/data-plan']: [plan('preview-second', 'persona-a'), plan('fresh-second', 'persona-a')],
    ['POST ' + firstRoute + '/data-apply']: firstResult,
    ['POST ' + secondRoute + '/data-apply']: {source_persona_id: 'persona-a', errors: [],
      reaction_created: 1, reaction_remaining: 0, journal_created: 0, journal_remaining: 0,
      journal_derivatives_remaining: 0},
  }});
  page.mountMigration();
  await settle();
  page.change('', 't-first', {setupLegacy: 'target'});
  page.change('', 'r-first', {setupLegacy: 'role'});
  page.click('legacy-data-plan');
  await settle();
  return {page, firstRoute, secondRoute};
}

test('first-run stages start with binding, then model, knowledge, relationships and active test', async () => {
  const page = harness({status: {step: 'binding', mode: {accounts: 'multiple', personas: 'multiple'}, ready: false}});
  page.mount();
  await settle();

  const positions = ['核心管理员窗口', '插件模型', '世界知识', '关系教学', '主动消息测试']
    .map(label => page.html.indexOf(label));
  assert.ok(positions.every(index => index >= 0));
  assert.deepEqual([...positions].sort((a, b) => a - b), positions);
  assert.match(page.html, /多个人格/);
  assert.doesNotMatch(page.html, /选择运行规模|单账号|单目标运行实例/);
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

test('binding diagnostics show readable labels instead of raw internal details', async () => {
  const page = harness({status: {step: 'model', host: {last_failure: {code: 'staging_profile_conflict',
    reason: 'internal profile / installation-id', details: ['staging-role', 'dashboard:hash']}}, ready: false}});
  page.mount();
  await settle();
  assert.match(page.html, /绑定条件发生变化/);
  assert.doesNotMatch(page.html, /internal profile|installation-id|staging-role|dashboard:hash/);
  page.updateStatus({step: 'binding', settings_error: 'staging_settings_invalid', ready: false});
  page.click('refresh');
  await settle();
  assert.match(page.html, /运行设置尚未就绪/);
  assert.doesNotMatch(page.html, /staging_settings_invalid/);
  page.updateStatus({step: 'binding', binding: {pending: true, platform_id: 'default',
    account_id: 'internal-bot', participant_id: 'internal-subject', persona_id: '[%None]'}, ready: false});
  page.click('refresh');
  await settle();
  assert.match(page.html, /QQ · OneBot/);
  assert.match(page.html, /默认人格/);
  assert.doesNotMatch(page.html, /default|internal-bot|internal-subject|\[%None\]/);
});

test('setup uses loaded providers directly for task routing', async () => {
  const model = {step: 'model', mode: {accounts: 'single', personas: 'single'}, ready: false,
    prepared: false, model: {provider_id: '', providers: [
      {id: 'native-model', name: 'Fixture model'}, {id: 'secondary-model', name: 'Second model'}]}};
  const prepared = {...model, prepared: true, model: {...model.model, provider_id: 'native-model'}};
  const task = {kind: 'proactive.compose', lane: 'background', capabilities: ['text'], edit_token: 'a'.repeat(64),
    fields: {provider: {value: 'native-model'}, fallback: {value: ''}}};
  const knowledge = {...prepared, step: 'knowledge', completed: ['model']};
  const page = harness({status: model, responses: {
    'GET setup/status': [model, prepared, knowledge],
    'GET model': {data: {status: 'ok', data: {providers: [
      {id: 'native-model', name: 'Fixture model', capabilities: ['text']},
      {id: 'secondary-model', name: 'Second model', capabilities: ['text']}], tasks: [task]}}},
    'POST setup/model': {provider_id: 'native-model'},
    'POST model/configure': {task, replayed: false},
  }});
  page.mount();
  await settle();
  assert.match(page.html, /初始主 Provider/);
  assert.doesNotMatch(page.html, /setup-additional-provider|初始 Provider 之外最多/);
  page.change('setup-provider', 'native-model');
  page.click('save-model');
  await settle();

  const save = page.calls.find(item => item.method === 'POST' && item.route === 'setup/model');
  assert.deepEqual(JSON.parse(JSON.stringify(save.body)), {provider_id: 'native-model'});
  assert.match(page.html, /任务模型路由/);
  assert.match(page.html, /主动联系/);
  page.change('', 'secondary-model', {setupModelTask: 'proactive.compose', setupModelField: 'provider'});
  page.click('save-task:proactive.compose');
  await settle();
  const route = page.calls.find(item => item.method === 'POST' && item.route === 'model/configure');
  assert.deepEqual(JSON.parse(JSON.stringify(route.body)), {kind: 'proactive.compose',
    operation_key: route.body.operation_key, edit_token: 'a'.repeat(64),
    changes: {provider: 'secondary-model', fallback: ''}, reset: []});
  assert.ok(!page.calls.some(item => item.route === 'setup/prepare'));
  assert.match(page.html, /世界知识/);
});

test('persona drafting and acquaintance-card saving stay inside the setup guide', async () => {
  const profile = {edit_token: 'b'.repeat(64), settings: {name: '', key_lore: ''}};
  const status = {step: 'knowledge', prepared: true, ready: false,
    mode: {accounts: 'single', personas: 'single'}, model: {provider_id: 'native-model', providers: []}};
  const page = harness({status, responses: {
    'GET setup/profile': {role_profile: profile, relationship_profile: profile},
    'GET setup/status': status,
    'POST setup/profile/save': {saved: true},
  }, bridgeResponses: {'setup/profile-draft': body => ({target: body.target,
    draft: {fields: {name: '航海者', key_lore: '熟悉潮汐和星图'}, notes: ['请核对推断']},
    source: {name: '当前人格', source_preview: '以海图辨认方向'},
    knowledge: [{title: '群岛航路', source: 'V2 世界资料'}], limits: {name: 200, key_lore: 2000}})}});
  page.mount();
  await settle();
  page.change('', '补充：她从小学会读海图', {profileSupplement: ''});
  page.click('generate-profile');
  await settle();

  assert.equal(page.bridgeCalls.length, 1);
  assert.equal(page.bridgeCalls[0].body.target, 'role_profile');
  assert.match(page.html, /V2 世界资料/);
  page.change('', '海图学者', {profileField: 'name'});
  page.click('save-profile');
  await settle();
  const saved = page.calls.find(item => item.method === 'POST' && item.route === 'setup/profile/save');
  assert.equal(saved.body.target, 'role_profile');
  assert.deepEqual(JSON.parse(JSON.stringify(saved.body.changes)), {name: '海图学者', key_lore: '熟悉潮汐和星图'});
  assert.match(page.html, /已保存 2 项角色设定/);
  assert.doesNotMatch(page.html, /data-go="manage"/);
});

test('V1 is not inspected until a target and persona are selected', async () => {
  const discovery = {v1_root: 'V1-data-root', findings: [
    {source_id: 'private.host_configuration', state: 'ready', detail: '可以迁移到 V2。'},
    {source_id: 'private.core_profiles', state: 'data_ready', detail: '日记、世界书和素材导入器已就绪。'},
    {source_id: 'private.work_and_delivery', state: 'documented_skip', detail: '旧投递结果不会重放。'},
    {source_id: 'memory.timeline_and_governance', state: 'data_ready', detail: '完整记忆库快照可归档。'},
  ]};
  const route = 'host/targets/t-first/roles/r-first/legacy';
  const targets = [{target_id: 't-first', account_name: '账号一', roles: [{role_id: 'r-first',
    role_name: '默认人格', legacy_api: '/astrbot_plugin_private_companion_v2/' + route}]}];
  const page = harness({status: readyStatus(), targets, responses: {['GET ' + route]: discovery}});
  page.mountMigration();
  await settle();

  assert.equal(page.calls.some(item => item.route === 'setup/status'), false,
    'the standalone migration workspace must not depend on first-run state');
  assert.match(page.html, /先选来源、写入目标和配置范围/);
  assert.match(page.html, /setup-migration-context/);
  assert.match(page.html, /V1 只读/);
  assert.equal(page.calls.some(item => item.route === 'legacy'), false);
  assert.equal(page.calls.some(item => item.route === route), false);
  page.change('', 't-first', {setupLegacy: 'target'});
  page.change('', 'r-first', {setupLegacy: 'role'});
  page.change('', 'all', {setupLegacy: 'configuration-scope'});
  assert.match(page.html, /检查 V1 配置/);
  page.click('legacy-scan');
  await settle();
  const scan = page.calls.find(item => item.route === route);
  assert.deepEqual(JSON.parse(JSON.stringify(scan.body)),
    {configuration_scope: 'all'});
  assert.deepEqual(JSON.parse(JSON.stringify(scan.options)), {timeoutMs: 300000});
  assert.match(page.html, /可转换/);
  assert.match(page.html, /可导入数据/);
  assert.match(page.html, /按边界跳过/);
  assert.match(page.html, /完整记忆库快照可归档/);
  assert.match(page.html, /V1-data-root/);
});

test('multi-target migration waits for a target and role, then uses that role route', async () => {
  const route = 'host/targets/t-first/roles/role-digest/legacy';
  const catalog = [{target_id: 't-first', bot_id: 'bot-a', roles: [{role_id: 'r-first',
    persona_ids: ['persona-a'], legacy_api: '/astrbot_plugin_private_companion_v2/' + route}]}];
  const page = harness({status: readyStatus(), targets: catalog,
    responses: {[`GET ${route}`]: {findings: [], v1_root: 'selected-root'}}});
  page.mountMigration();
  await settle();
  assert.equal(page.calls.some(item => item.route === route), false);
  assert.match(page.html, /data-setup-legacy="target"/);
  assert.match(page.html, /data-setup-legacy="role"/);

  page.change('', 't-first', {setupLegacy: 'target'});
  page.change('', 'r-first', {setupLegacy: 'role'});
  page.click('legacy-scan');
  await settle();
  const scanned = page.calls.find(item => item.method === 'GET' && item.route === route);
  assert.ok(scanned);
  assert.deepEqual(JSON.parse(JSON.stringify(scanned.body)), {configuration_scope: 'proactive'});
  assert.equal(page.calls.some(item => item.route === 'legacy'), false);
  assert.match(page.html, /selected-root/);
});

test('a slow migration scan shows its phase while the extended request is pending', async () => {
  const route = 'host/targets/t-first/roles/r-first/legacy';
  const targets = [{target_id: 't-first', roles: [{role_id: 'r-first',
    legacy_api: '/astrbot_plugin_private_companion_v2/' + route}]}];
  let finishScan;
  const scanResponse = new Promise(resolve => { finishScan = resolve; });
  const page = harness({status: readyStatus(), targets, responses: {[`GET ${route}`]: scanResponse}});
  page.mountMigration();
  await settle();
  page.change('', 't-first', {setupLegacy: 'target'});
  page.change('', 'r-first', {setupLegacy: 'role'});

  page.click('legacy-scan');
  const scan = page.calls.find(item => item.method === 'GET' && item.route === route);
  assert.deepEqual(JSON.parse(JSON.stringify(scan.options)), {timeoutMs: 300000});
  assert.match(page.html, /正在只读检查 V1 来源/);

  finishScan({findings: [], v1_root: 'selected-root'});
  await settle();
  assert.doesNotMatch(page.html, /正在只读检查 V1 来源/);
});

test('completed setup is a one-time receipt with a direct route to daily use', async () => {
  const page = harness({status: readyStatus({host: {accepting: false}})});
  page.mount();
  await settle();

  assert.match(page.html, /首次设置已完成/);
  assert.doesNotMatch(page.html, /运行模式|共享运行实例|单目标模式/);
  assert.match(page.html, /不需要重新走向导/);
  assert.match(page.html, /data-go="life"/);
  assert.doesNotMatch(page.html, /setup-legacy-disclosure|data-setup-legacy-action|V1 配置与运行数据迁移/);
  assert.match(page.html, /首次设置已保留，当前运行实例尚未接收消息/);
  assert.match(page.html, /data-setup-action="reconnect-host"/);
  assert.doesNotMatch(page.html, /setup-step-count|选择运行规模|绑定核心管理员窗口/);
});

test('quick setup edits common V2 settings in place without leaving the start page', async () => {
  const task = {kind: 'proactive.compose', lane: 'background', capabilities: ['text'], edit_token: 'a'.repeat(64),
    fields: {provider: {value: 'fast-model'}, fallback: {value: ''}}};
  const page = harness({status: readyStatus({model: {provider_id: 'base-model', providers: [
      {id: 'base-model', name: 'Base model'}, {id: 'fast-model', name: 'Fast model'}]}}), responses: {
    'GET model': {providers: [
      {id: 'fast-model', name: 'Fast model', capabilities: ['text']},
      {id: 'careful-model', name: 'Careful model', capabilities: ['text']}], tasks: [task]},
    'POST model/configure': {task, replayed: false},
  }});
  page.mount();
  await settle();
  assert.match(page.html, /data-setup-action="advanced-open"/);
  page.click('advanced-open');

  for (const label of ['回复与分段', '人物与资料', '日程与作息', '主动联系', '群聊参与', '模型路由']) assert.match(page.html, new RegExp(label));
  assert.match(page.html, /id="setupQuickReplyHost"/);
  assert.match(page.html, /id="setupQuickStateHost"/);
  assert.doesNotMatch(page.html, /data-go=|data-manage=/);
  assert.equal(page.replyMounts.at(-1).options.expressionModule, 'expression-text');
  assert.equal(page.replyMounts.at(-1).options.section, 'segment');

  page.clickBlock('relationships');
  assert.deepEqual(page.editorCalls.at(-1).kinds, ['role_profile', 'relationship_profile', 'knowledge', 'private_access']);
  assert.equal(page.editorCalls.at(-1).views.knowledge.navigationLimit, 0);
  page.clickBlock('life');
  assert.equal(page.stateMounts.at(-1).options.feature, 'planning');
  assert.deepEqual([...page.editorCalls.at(-1).views.life.sectionIds], ['routine', 'sleep']);
  page.clickBlock('action');
  assert.deepEqual(page.editorCalls.at(-1).kinds, ['proactive.contact']);
  page.clickBlock('group');
  assert.equal(page.replyMounts.at(-1).options.view, 'decision');
  assert.deepEqual(page.editorCalls.at(-1).kinds, ['group_participation']);
  page.clickBlock('runtime');
  await settle();
  assert.match(page.html, /陪伴通用模型/);
  assert.match(page.html, /data-setup-model-task="proactive.compose"/);
  assert.doesNotMatch(page.html, /data-go=|data-manage=/);
  page.change('', 'careful-model', {setupModelTask: 'proactive.compose', setupModelField: 'provider'});
  page.click('save-task:proactive.compose');
  await settle();
  const saved = page.calls.find(item => item.method === 'POST' && item.route === 'model/configure');
  assert.equal(saved.body.kind, 'proactive.compose');
  assert.equal(saved.body.changes.provider, 'careful-model');
  page.click('advanced-close');
  assert.match(page.html, /首次设置已完成/);
});

test('quick model routes expose a retry after a failed read without retrying in a loop', async () => {
  const routeData = {providers: [{id: 'fast-model', name: 'Fast model', capabilities: ['text']}], tasks: []};
  const page = harness({status: readyStatus(), responses: {
    'GET model': [new Error('route unavailable'), {data: routeData}],
  }});
  page.mount();
  await settle();
  page.click('advanced-open');
  page.clickBlock('runtime');
  await settle();
  assert.equal(page.calls.filter(item => item.route === 'model').length, 1);
  assert.match(page.html, /route unavailable/);
  page.click('retry-model-routes');
  await settle();
  assert.equal(page.calls.filter(item => item.route === 'model').length, 2);
  assert.match(page.html, /当前没有这些后台任务的模型路由/);
});

test('a running completed setup does not ask the user to reconnect or repeat setup', async () => {
  const page = harness({status: readyStatus({host: {accepting: true}})});
  page.mount();
  await settle();

  assert.match(page.html, /V2 正在接收消息/);
  assert.doesNotMatch(page.html, /data-setup-action="reconnect-host"/);
  assert.doesNotMatch(page.html, /选择运行规模|绑定核心管理员窗口|setup-step-count/);
});

test('an unknown test can be confirmed as received without submitting another send', async () => {
  const status = readyStatus({step: 'proactive_test', ready: false,
    proactive_test: {state: 'unknown', attempt_id: 'existing-test'}});
  const confirmed = readyStatus({host: {accepting: true}, proactive_test: {
    state: 'received', attempt_id: 'existing-test', confirmed_at: '2026-10-02T04:17:47Z'}});
  const page = harness({status, responses: {'GET setup/status': [status, confirmed],
    'POST setup/proactive-test/confirm': {state: 'received', ready: true}}});
  page.mount();
  await settle();
  assert.match(page.html, /已收到测试消息/);
  assert.doesNotMatch(page.html, /data-setup-action="proactive-test"/);
  page.click('confirm-test-received');
  await settle();
  const call = page.calls.find(item => item.route === 'setup/proactive-test/confirm');
  assert.deepEqual(JSON.parse(JSON.stringify(call.body)), {attempt_id: 'existing-test'});
  assert.equal(page.calls.some(item => item.route === 'setup/proactive-test'), false);
  assert.match(page.html, /首次设置已完成/);
  assert.match(page.html, /你已确认收到测试消息/);
  assert.doesNotMatch(page.html, /平台已确认发送测试消息/);
});

test('the proactive test requires explicit consent and polls the real delivery result', async () => {
  const initial = {step: 'proactive_test', ready: false, proactive_test: null};
  const started = {...initial, proactive_test: {state: 'started', attempt_id: 'attempt-1'}};
  const delivered = readyStatus({proactive_test: {state: 'delivered', attempt_id: 'attempt-1',
    finished_at: '2026-10-02T04:17:47Z'}});
  const page = harness({status: initial, responses: {
    'GET setup/status': [initial, started, delivered],
    'POST setup/proactive-test': {state: 'started', attempt_id: 'attempt-1', ready: false},
  }});
  page.mount();
  await settle();
  page.change('', '', {setupProactiveOptIn: ''}, {checked: true});
  page.click('proactive-test');
  await settle();

  const call = page.calls.find(item => item.method === 'POST' && item.route === 'setup/proactive-test');
  assert.deepEqual(JSON.parse(JSON.stringify(call.body)), {enable_proactive: true});
  assert.match(page.html, /首次设置已完成/);
  assert.equal(page.calls.filter(item => item.method === 'POST' && item.route === 'setup/proactive-test').length, 1);
});

test('migration apply sends the reviewed plan token and refuses locally without a plan', async () => {
  const route = 'host/targets/t-first/roles/r-first/legacy';
  const targets = [{target_id: 't-first', roles: [{role_id: 'r-first',
    role_name: '星缘', legacy_api: '/astrbot_plugin_private_companion_v2/' + route}]}];
  const discovery = {v1_root: 'V1-root', findings: [{source_id: 'private.host_configuration', state: 'ready'}]};
  const plan = {v1_root: 'V1-root', findings: discovery.findings, change_count: 3, plan_token: 'reviewed-token',
    scope_status: [{scope: 'role.state', available: true}, {scope: 'plugin_config', available: true}],
    intents: [{group_id: 'role.state', values: {planning_enabled: true}, confidence: {planning_enabled: 'high'},
      sources: {planning_enabled: ['life_schedule_config.enable_daily_plan']}},
    {group_id: 'plugin', target_kind: 'plugin_config', values: {'poke.enabled': true}, confidence: {'poke.enabled': 'high'},
      sources: {'poke.enabled': ['reactive_poke_config.enable_reactive_poke']}}],
    differences: [{audit: true, disposition: 'manual_required', source_key: 'reactive_poke_config.reactive_poke_back_prompts',
      explain: 'V2 没有被动反戳提示词配置。'}], warnings: []};
  const result = {v1_root: 'V1-root', written_count: 3, written: ['role.state.weather', 'poke.enabled'],
    restart_required: true, skipped: []};
  const page = harness({status: readyStatus(), targets, responses: {
    ['GET ' + route]: discovery,
    ['GET ' + route + '/plan']: plan,
    ['POST ' + route + '/apply']: result,
  }});
  page.mountMigration();
  await settle();
  page.click('legacy-apply');
  await settle();
  assert.equal(page.calls.some(item => item.route === route + '/apply'), false);
  page.change('', 't-first', {setupLegacy: 'target'});
  page.change('', 'r-first', {setupLegacy: 'role'});
  page.click('legacy-apply');
  await settle();
  assert.equal(page.calls.some(item => item.route === route + '/apply'), false);

  assert.match(page.html, /主动消息与天气基础设置/);
  page.click('legacy-scan');
  await settle();
  const scan = page.calls.find(item => item.route === route);
  assert.deepEqual(JSON.parse(JSON.stringify(scan.body)),
    {configuration_scope: 'proactive'});
  assert.deepEqual(JSON.parse(JSON.stringify(scan.options)), {timeoutMs: 300000});
  page.click('legacy-plan');
  await settle();
  const planned = page.calls.find(item => item.route === route + '/plan');
  assert.deepEqual(JSON.parse(JSON.stringify(planned.body)),
    {configuration_scope: 'proactive'});
  assert.deepEqual(JSON.parse(JSON.stringify(planned.options)), {timeoutMs: 300000});
  assert.match(page.html, /拟写入字段与数值/);
  assert.match(page.html, /配置未自动迁移（1）/);
  assert.match(page.html, /reactive_poke_config\.reactive_poke_back_prompts/);
  assert.match(page.html, /仍待实现 1/);
  assert.match(page.html, /role\.state\.planning_enabled/);
  assert.match(page.html, /poke\.enabled/);
  assert.match(page.html, /插件设置需重启生效/);
  assert.match(page.html, /life_schedule_config\.enable_daily_plan/);
  page.click('legacy-apply');
  await settle();
  const applied = page.calls.find(item => item.method === 'POST' && item.route === route + '/apply');
  assert.deepEqual(JSON.parse(JSON.stringify(applied.body)), {
    plan_token: 'reviewed-token', configuration_scope: 'proactive'});
  assert.deepEqual(JSON.parse(JSON.stringify(applied.options)), {timeoutMs: 300000});
  assert.match(page.html, /已写入 3 项 V2 设置/);
  assert.match(page.html, /请重启插件使插件级配置生效/);
});

test('migration can use an explicitly selected V1 directory through scan, plan and apply', async () => {
  const root = 'C:\\AstrBot\\plugin_data\\astrbot_plugin_private_companion';
  const route = 'host/targets/t-first/roles/r-first/legacy';
  const planRoute = route + '/plan';
  const targets = [{target_id: 't-first', roles: [{role_id: 'r-first',
    role_name: '星缘', legacy_api: '/astrbot_plugin_private_companion_v2/' + route}]}];
  const discovery = {v1_root: root, findings: [{source_id: 'private.host_configuration', state: 'ready'}]};
  const plan = {v1_root: root, findings: discovery.findings, change_count: 1, plan_token: 'selected-root-token',
    scope_status: [{scope: 'role.state', available: true}], intents: [], differences: [], warnings: []};
  const page = harness({status: readyStatus(), targets, responses: {
    ['GET ' + route]: discovery,
    ['GET ' + planRoute]: plan,
    ['POST ' + route + '/apply']: {v1_root: root, written_count: 1, written: ['role.state.weather'], skipped: []},
  }});
  page.mountMigration();
  await settle();
  page.change('', 't-first', {setupLegacy: 'target'});
  page.change('', 'r-first', {setupLegacy: 'role'});
  page.change('', root, {setupLegacy: 'root'});
  page.click('legacy-scan');
  await settle();
  assert.deepEqual(JSON.parse(JSON.stringify(page.calls.find(item => item.route === route).body)),
    {configuration_scope: 'proactive', v1_root: root});
  page.click('legacy-plan');
  await settle();
  assert.deepEqual(JSON.parse(JSON.stringify(page.calls.find(item => item.route === planRoute).body)),
    {configuration_scope: 'proactive', v1_root: root});
  page.click('legacy-apply');
  await settle();
  const applied = page.calls.find(item => item.method === 'POST' && item.route === route + '/apply');
  assert.deepEqual(JSON.parse(JSON.stringify(applied.body)), {
    plan_token: 'selected-root-token', configuration_scope: 'proactive', v1_root: root});
});

test('data migration uses current-target availability and reports capped group imports', async () => {
  const route = 'host/targets/t-first/roles/r-first/legacy';
  const targets = [{target_id: 't-first', roles: [{role_id: 'r-first', role_name: '星缘',
    legacy_api: '/astrbot_plugin_private_companion_v2/' + route}]}];
  const plan = {
    plan_token: 'data-plan-token',
    reaction_assets: {total: 0, ready: 0, batch_count: 0, batch_bytes: 0},
    journals: {total: 0, ready: 0, batch_count: 0, already_present: 0, samples: [], conflicts: []},
    worldbook: {total: 3, available_count: 0, general_count: 0, member_count: 0,
      disabled_member_count: 0, group_count: 3, selected_group_entry_count: 0,
      requires_id_confirmation: false, groups: [{source_group_id: '789', entry_count: 3}],
      rejected: [], samples: []},
    profile_data: {private_user_profiles: 0, worldbook_profiles: 0, dream_fragments: 0},
    work_delivery: {}, world_assets: {}, persona_sources: [],
    group_networks: [{source_group_id: '789', member_count: 256, edge_count: 80,
      omitted_member_count: 4, omitted_edge_count: 179, rejected_member_count: 0,
      rejected_edge_count: 0}],
    group_target_available: false, target_private_available: true, warnings: [],
  };
  const page = harness({status: readyStatus(), targets,
    responses: {['GET ' + route + '/data-plan']: plan}});
  page.mountMigration();
  await settle();
  page.change('', 't-first', {setupLegacy: 'target'});
  page.change('', 'r-first', {setupLegacy: 'role'});
  page.click('legacy-data-plan');
  await settle();

  const dataPlan = page.calls.find(item => item.route === route + '/data-plan');
  assert.deepEqual(JSON.parse(JSON.stringify(dataPlan.options)), {timeoutMs: 300000});

  assert.match(page.html, /当前目标可导入 0 条/);
  assert.match(page.html, /data-setup-legacy="import-worldbook"[^>]*disabled/);
  page.change('', '789', {setupLegacy: 'data-group'});
  page.click('legacy-data-plan');
  await settle();
  assert.match(page.html, /另有 4 位成员、179 条互动边超过 V2 上限/);
});

test('data migration does not present an unplanned memory database as empty', async () => {
  const route = 'host/targets/t-first/roles/r-first/legacy';
  const targets = [{target_id: 't-first', roles: [{role_id: 'r-first', role_name: '星缘',
    legacy_api: '/astrbot_plugin_private_companion_v2/' + route}]}];
  const page = harness({status: readyStatus(), targets});
  page.mountMigration();
  await settle();
  page.change('', 't-first', {setupLegacy: 'target'});
  page.change('', 'r-first', {setupLegacy: 'role'});

  assert.match(page.html, /独立记忆库（试算后显示规模）/);
  assert.match(page.html, /仅迁入通过身份映射和治理检查的历史资料/);
  assert.doesNotMatch(page.html, /独立记忆库（0 条 \/ 0 MB）/);
});

test('single-target migration exposes references and can import wardrobe text without gallery images', async () => {
  const route = 'host/targets/t-first/roles/r-first/legacy';
  const targets = [{target_id: 't-first', roles: [{role_id: 'r-first', role_name: '星缘',
    legacy_api: '/astrbot_plugin_private_companion_v2/' + route}]}];
  const plan = {plan_token: 'reference-plan', source_persona_id: '',
    reaction_assets: {batch_count: 0}, journals: {batch_count: 0}, worldbook: {general_count: 0, member_count: 0},
    reference_images: {ready: 1, batch_count: 1, rejected: []},
    wardrobe_items: {ready: 1, batch_count: 1, image_count: 0, rejected: []},
    persona_sources: [{persona_id: '', label: '主角色（companions.json）', state: 'ready'}],
    archive: {state: 'absent'}, memory_database: {state: 'absent'},
    target_private_available: true, group_target_available: false, group_networks: []};
  const page = harness({status: readyStatus(), targets, responses: {
    ['GET ' + route + '/data-plan']: [plan, plan],
    ['POST ' + route + '/data-apply']: {source_persona_id: '', errors: [],
      reference_images: {reference_created: 0, reference_remaining: 0,
        wardrobe_created: 1, wardrobe_remaining: 0, wardrobe_images_skipped: 0}},
  }});
  page.mountMigration();
  await settle();
  assert.match(page.html, /从 V1 安全迁入 V2/);
  page.change('', 't-first', {setupLegacy: 'target'});
  page.change('', 'r-first', {setupLegacy: 'role'});
  page.click('legacy-data-plan');
  await settle();
  page.change('', '', {setupLegacy: 'import-reference-images'}, {checked: true});
  assert.match(page.html, /图片随角色使用，不按 V1 私聊用户区分/);
  page.change('', '', {setupLegacy: 'import-reference-images'}, {checked: false});
  page.change('', '', {setupLegacy: 'import-wardrobe-items'}, {checked: true});
  page.change('', '', {setupLegacy: 'confirm-reference-persona-mapping'}, {checked: true});
  page.click('legacy-data-apply');
  await settle();

  const applied = page.calls.find(item => item.method === 'POST' && item.route === route + '/data-apply');
  assert.equal(applied.body.import_reference_images, false);
  assert.equal(applied.body.import_wardrobe_items, true);
  assert.equal(applied.body.confirm_reference_persona_mapping, true);
  assert.match(page.html, /衣柜新增 1 件/);
});

test('learning relationship profiles are counted and can be selected without original worldbook entries', async () => {
  const route = 'host/targets/t-first/roles/r-first/legacy';
  const targets = [{target_id: 't-first', roles: [{role_id: 'r-first', role_name: '星缘',
    legacy_api: '/astrbot_plugin_private_companion_v2/' + route}]}];
  const plan = {plan_token: 'learning-social-plan', reaction_assets: {}, journals: {},
    worldbook: {general_count: 0, member_entry_count: 0, member_count: 2, member_profile_count: 2,
      available_count: 2, requires_id_confirmation: true, base_members_matches: false},
    persona_sources: [], group_networks: [], memory_database: {state: 'absent'},
    target_private_available: true, group_target_available: false};
  const page = harness({status: readyStatus(), targets, responses: {
    ['GET ' + route + '/data-plan']: plan,
    ['POST ' + route + '/data-apply']: {errors: [], worldbook: {members_imported: 2}}}});
  page.mountMigration();
  await settle();
  page.change('', 't-first', {setupLegacy: 'target'});
  page.change('', 'r-first', {setupLegacy: 'role'});
  page.click('legacy-data-plan');
  await settle();
  assert.match(page.html, /2 个学习关系网节点/);
  assert.match(page.html, /人物描述、身份备注、相处边界与重要印象一起迁移/);
  assert.doesNotMatch(page.html, /data-setup-legacy="import-worldbook"[^>]*disabled/);
  page.change('', '', {setupLegacy: 'import-worldbook'}, {checked: true});
  page.change('', '', {setupLegacy: 'confirm-member-ids'}, {checked: true});
  assert.doesNotMatch(page.html, /data-setup-legacy-action="legacy-data-apply"[^>]*disabled/);
  page.click('legacy-data-apply');
  await settle();
  const applied = page.calls.find(item => item.method === 'POST' && item.route === route + '/data-apply');
  assert.equal(applied.body.import_worldbook, true);
  assert.equal(applied.body.confirm_member_ids, true);
});

test('data migration previews the independent memory database and sends its explicit selection', async () => {
  const route = 'host/targets/t-first/roles/r-first/legacy';
  const targets = [{target_id: 't-first', roles: [{role_id: 'r-first', role_name: '星缘',
    legacy_api: '/astrbot_plugin_private_companion_v2/' + route}]}];
  const plan = {
    plan_token: 'memory-plan-token',
    reaction_assets: {total: 0, ready: 0, batch_count: 0, batch_bytes: 0},
    journals: {total: 0, ready: 0, batch_count: 0, already_present: 0, samples: [], conflicts: []},
    worldbook: {total: 0, available_count: 0, general_count: 0, member_count: 0,
      disabled_member_count: 0, group_count: 0, selected_group_entry_count: 0,
      requires_id_confirmation: false, groups: [], rejected: [], samples: []},
    profile_data: {}, work_delivery: {}, world_assets: {}, persona_sources: [
      {persona_id: '', label: '主角色（companions.json）', state: 'ready'},
      {persona_id: 'persona-b', label: 'V1 人格：persona-b', state: 'ready'},
    ], group_networks: [],
    group_target_available: false, target_private_available: true, warnings: [],
    archive: {state: 'incomplete', file_count: 1047, total_bytes: 1056942445, excluded_count: 1},
    memory_database: {state: 'incomplete', table_count: 2, record_count: 3, total_bytes: 1024,
      excluded_count: 1, assets: [{path: 'memory_companion.db'}],
      table_counts: {memories: 1, timeline: 2}},
  };
  const page = harness({status: readyStatus(), targets,
    responses: {['GET ' + route + '/data-plan']: plan}});
  page.mountMigration();
  await settle();
  page.change('', 't-first', {setupLegacy: 'target'});
  page.change('', 'r-first', {setupLegacy: 'role'});
  page.click('legacy-data-plan');
  await settle();

  assert.match(page.html, /逐个人格添加 V2 私聊目标与角色，或明确跳过/);
  assert.match(page.html, /V1 人格：persona-b/);
  assert.match(page.html, /群资料需另选 V2 群目标/);
  assert.match(page.html, /个人关系账户不在此处迁移/);
  assert.match(page.html, /独立记忆库表清单（2）/);
  assert.match(page.html, /data-setup-legacy="import-memory-database"[^>]*checked/);
  assert.doesNotMatch(page.html.match(/<input[^>]*data-setup-legacy="import-memory-database"[^>]*>/)?.[0] || '', /disabled/);
  assert.match(page.html, /其余可读文件可以归档，清单会标记不完整/);
  const archiveControl = page.html.match(/<input[^>]*data-setup-legacy="import-archive"[^>]*>/)?.[0] || '';
  assert.doesNotMatch(archiveControl, /disabled/);
  assert.match(archiveControl, /checked/);
  assert.match(page.html, /尽可能归档可读的原始资料/);
  assert.match(page.html, /data-setup-legacy-action="legacy-data-apply"/);
  page.click('legacy-data-apply');
  await settle();
  const applied = page.calls.find(item => item.method === 'POST' && item.route === route + '/data-apply');
  assert.ok(applied, JSON.stringify(page.calls));
  assert.deepEqual(JSON.parse(JSON.stringify(applied.options)), {timeoutMs: 300000});
  assert.equal(applied.body.import_memory_database, true);
  assert.equal(applied.body.import_archive, true);
});

test('a V1 persona can map to multiple explicitly selected V2 destinations and each imports serially', async () => {
  const {page, firstRoute, secondRoute} = await plannedMultiDestinationPage();
  const firstPlanRoute = firstRoute + '/data-plan';
  const secondPlanRoute = secondRoute + '/data-plan';
  assert.equal(page.calls.filter(item => item.route === firstPlanRoute).length, 1);

  page.click('legacy-data-batch-plan');
  await settle();
  assert.equal(page.calls.filter(item => item.route === firstPlanRoute).length, 1,
    'an unassigned V1 persona must not fan out to any V2 target');

  page.clickLegacyDestination('add', 'persona-a');
  page.clickLegacyDestination('add', 'persona-a');
  page.change('', 't-first', {setupLegacyBatchTarget: '', personaId: 'persona-a', destinationId: 'destination-1'});
  page.change('', 'r-first', {setupLegacyBatchRole: '', personaId: 'persona-a', destinationId: 'destination-1'});
  page.change('', 't-first', {setupLegacyBatchTarget: '', personaId: 'persona-a', destinationId: 'destination-2'});
  page.change('', 'r-first', {setupLegacyBatchRole: '', personaId: 'persona-a', destinationId: 'destination-2'});
  assert.match(page.html, /已阻止重复的 V2 目标角色映射/);
  assert.match(page.html, /该 V2 目标角色已映射到另一个目的地/);
  page.change('', 't-second', {setupLegacyBatchTarget: '', personaId: 'persona-a', destinationId: 'destination-2'});
  page.change('', 'r-second', {setupLegacyBatchRole: '', personaId: 'persona-a', destinationId: 'destination-2'});

  const planningStart = page.calls.length;
  page.click('legacy-data-batch-plan');
  await settle();
  assert.deepEqual(page.calls.slice(planningStart).filter(item => [firstPlanRoute, secondPlanRoute].includes(item.route)
    && item.body?.source_persona_id === 'persona-a')
    .map(item => [item.method, item.route]), [
    ['GET', firstPlanRoute], ['GET', secondPlanRoute],
  ]);
  assert.deepEqual(page.calls.slice(planningStart).filter(item => [firstPlanRoute, secondPlanRoute].includes(item.route)
    && item.body?.source_persona_id === 'persona-a').map(item => JSON.parse(JSON.stringify(item.body))), [
    {source_persona_id: 'persona-a'}, {source_persona_id: 'persona-a'},
  ]);
  assert.match(page.html, /已试算 2 \/ 2 个目的地/);

  const applyingStart = page.calls.length;
  page.click('legacy-data-batch-apply');
  await settle();
  assert.deepEqual(page.calls.slice(applyingStart).filter(item =>
    item.route.endsWith('/data-plan') || item.route.endsWith('/data-apply'))
    .map(item => [item.method, item.route]), [
    ['GET', firstPlanRoute], ['POST', firstRoute + '/data-apply'],
    ['GET', secondPlanRoute], ['POST', secondRoute + '/data-apply'],
  ]);
  for (const call of page.calls.filter(item => item.method === 'POST' && item.route.endsWith('/data-apply'))) {
    assert.equal(call.body.source_persona_id, 'persona-a');
    assert.equal(call.body.import_reactions, true);
  }
  assert.match(page.html, /各目标结果已分别保留/);
});

test('multi-destination migration sends wardrobe selection and keeps remaining materials resumable', async () => {
  const result = {source_persona_id: 'persona-a', errors: [], reaction_created: 1,
    reaction_remaining: 0, journal_created: 0, journal_remaining: 0,
    journal_derivatives_remaining: 0,
    reference_images: {reference_created: 0, reference_remaining: 0,
      wardrobe_created: 1, wardrobe_remaining: 1, wardrobe_images_skipped: 0}};
  const {page, firstRoute} = await plannedMultiDestinationPage(result);
  page.clickLegacyDestination('add', 'persona-a');
  page.change('', 't-first', {setupLegacyBatchTarget: '', personaId: 'persona-a', destinationId: 'destination-1'});
  page.change('', 'r-first', {setupLegacyBatchRole: '', personaId: 'persona-a', destinationId: 'destination-1'});
  page.click('legacy-data-batch-plan');
  await settle();
  page.change('', '', {setupLegacyBatchOption: 'wardrobe-items', personaId: 'persona-a',
    destinationId: 'destination-1'}, {checked: true});
  page.change('', '', {setupLegacyBatchOption: 'confirm-reference-persona', personaId: 'persona-a',
    destinationId: 'destination-1'}, {checked: true});
  page.click('legacy-data-batch-apply');
  await settle();

  const applied = page.calls.find(item => item.method === 'POST' && item.route === firstRoute + '/data-apply');
  assert.equal(applied.body.import_reference_images, false);
  assert.equal(applied.body.import_wardrobe_items, true);
  assert.equal(applied.body.confirm_reference_persona_mapping, true);
  assert.match(page.html, /仍有后续批次或未导入项/);
  assert.match(page.html, /衣物 1 条待继续/);
});

test('a failed or unknown destination apply stops before later destinations', async t => {
  for (const [label, response, statusText] of [
    ['known item failure', {source_persona_id: 'persona-a', errors: [{code: 'write_failed'}]}, '执行失败'],
    ['unknown response', new Error('network timeout'), '结果未确认'],
  ]) {
    await t.test(label, async () => {
      const {page, firstRoute, secondRoute} = await plannedMultiDestinationPage(response);
      page.clickLegacyDestination('add', 'persona-a');
      page.clickLegacyDestination('add', 'persona-a');
      page.change('', 't-first', {setupLegacyBatchTarget: '', personaId: 'persona-a', destinationId: 'destination-1'});
      page.change('', 'r-first', {setupLegacyBatchRole: '', personaId: 'persona-a', destinationId: 'destination-1'});
      page.change('', 't-second', {setupLegacyBatchTarget: '', personaId: 'persona-a', destinationId: 'destination-2'});
      page.change('', 'r-second', {setupLegacyBatchRole: '', personaId: 'persona-a', destinationId: 'destination-2'});
      page.click('legacy-data-batch-plan');
      await settle();

      const secondPlanCount = page.calls.filter(item => item.route === secondRoute + '/data-plan').length;
      page.click('legacy-data-batch-apply');
      await settle();
      assert.equal(page.calls.filter(item => item.method === 'POST' && item.route === firstRoute + '/data-apply').length, 1);
      assert.equal(page.calls.filter(item => item.method === 'POST' && item.route === secondRoute + '/data-apply').length, 0);
      assert.equal(page.calls.filter(item => item.route === secondRoute + '/data-plan').length, secondPlanCount,
        'a later destination must not be rechecked after an earlier apply failure or unknown result');
      assert.match(page.html, new RegExp(statusText));
      assert.match(page.html, /目的地执行已停止|后续目的地未执行/);
    });
  }
});
