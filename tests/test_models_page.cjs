const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.resolve(__dirname, '../pages/陪伴小屋/models-page.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
const TOKEN = 'a'.repeat(64);

/* An inherited task: every field follows the upstream layer. */
function task(kind, provider, capabilities = ['text'], lane = 'foreground') {
  return {
    kind, lane, capabilities, edit_token: TOKEN, application_state: 'applied',
    fields: {
      provider: {value: provider, inherited_value: provider, source: 'window', inherited_source: 'installation', explicit: false},
      fallback: {value: '', inherited_value: '', source: 'default', inherited_source: 'default', explicit: false},
      prompt: {value: '', inherited_value: '', source: 'default', inherited_source: 'default', explicit: false},
      max_output_tokens: {value: 4096, inherited_value: 4096, source: 'window', inherited_source: 'installation', explicit: false},
      timeout_seconds: {value: 60, inherited_value: 60, source: 'default', inherited_source: 'default', explicit: false},
      replacement_rules: {value: '[]', inherited_value: '[]', source: 'default', inherited_source: 'default', explicit: false},
      fallback_on_refusal: {value: false, inherited_value: false, source: 'default', inherited_source: 'default', explicit: false},
      replacement_scope: {value: 'all', inherited_value: 'all', source: 'default', inherited_source: 'default', explicit: false},
    },
  };
}

/* Base routing fields with explicit values, so a saved task still shows changes. */
function baseFields(provider) {
  return {
    provider: {value: provider, inherited_value: 'primary', source: 'window', inherited_source: 'installation', explicit: true},
    fallback: {value: '', inherited_value: '', source: 'default', inherited_source: 'default', explicit: false},
    prompt: {value: '', inherited_value: '', source: 'default', inherited_source: 'default', explicit: false},
    max_output_tokens: {value: 4096, inherited_value: 4096, source: 'window', inherited_source: 'installation', explicit: true},
    timeout_seconds: {value: 60, inherited_value: 60, source: 'default', inherited_source: 'default', explicit: false},
    replacement_rules: {value: '[]', inherited_value: '[]', source: 'window', inherited_source: 'default', explicit: false},
    fallback_on_refusal: {value: false, inherited_value: false, source: 'default', inherited_source: 'default', explicit: false},
    replacement_scope: {value: 'all', inherited_value: 'all', source: 'default', inherited_source: 'default', explicit: false},
  };
}

/* A task payload carrying the replacement fields a current V2 host returns. */
function editable(kind, provider, capabilities = ['text'], lane = 'foreground') {
  return {kind, lane, capabilities, edit_token: TOKEN, application_state: 'applied', fields: baseFields(provider)};
}

function status() {
  return {
    tasks: [
      {kind: 'conversation.reply', lane: 'foreground', capabilities: ['text'], edit_token: TOKEN, application_state: 'applied', fields: baseFields('primary')},
      {kind: 'memory.reflect', lane: 'background', capabilities: ['text'], edit_token: TOKEN, application_state: 'applied', fields: baseFields('primary')},
    ],
    providers: [
      {id: 'primary', capabilities: ['text'], max_output_tokens: 8192},
      {id: 'secondary', capabilities: ['text'], max_output_tokens: 8192},
    ],
    host_state: 'running',
  };
}

function harness() {
  const requests = [];
  const store = new Map();
  const window = {
    CompanionProduct: {
      hosted: () => true,
      role: () => ({model_api: '/astrbot_plugin_private_companion_v2/model'}),
      identity: () => ({installation_id: 'inst', operator_id: 'operator'}),
      /* 页面取桥先问 bridgeNow()，没有再 await bridgeFor()。
         这里两者都给，保持同步路径不被打断。 */
      bridgeNow: () => window.AstrBotPluginPage,
      bridgeFor: () => ({then: resolve => resolve(window.AstrBotPluginPage)}),
    },
    AstrBotPluginPage: {
      apiGet: route => new Promise((resolve, reject) => requests.push({method: 'GET', route, resolve, reject})),
      apiPost: (route, values) => new Promise((resolve, reject) => requests.push({method: 'POST', route, values, resolve, reject})),
    },
    sessionStorage: {
      getItem: key => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => store.set(key, value),
      removeItem: key => store.delete(key),
    },
    crypto: {randomUUID: () => 'key-' + requests.length},
  };
  vm.runInNewContext(source, {window, crypto: window.crypto, AbortController, setTimeout, clearTimeout});
  function root() {
    const handlers = {};
    return {
      isConnected: true, innerHTML: '',
      addEventListener(type, handler) { handlers[type] = handler; },
      removeEventListener(type) { delete handlers[type]; },
      querySelectorAll() { return []; },
      querySelector() { return null; },
      fire(type, selector, dataset) {
        handlers[type]({type, target: {dataset: dataset || {}, value: dataset?.value, checked: dataset?.checked, valueAsNumber: dataset?.valueAsNumber,
          matches: candidate => candidate === selector, closest: candidate => (candidate === selector ? {dataset} : null)}});
      },
      click(selector, dataset) { this.fire('click', selector, dataset); },
      input(selector, dataset) { this.fire('input', selector, dataset); },
      change(selector, dataset) { this.fire('change', selector, dataset); },
    };
  }
  return {page: window.CompanionModelsPage, requests, root, store};
}

test('the routing matrix lists every registered task with its provider', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  assert.match(node.innerHTML, /任务/);
  assert.match(node.innerHTML, /对话回复/);
  assert.match(node.innerHTML, /记忆整理/);
  assert.match(node.innerHTML, /2<\/strong><span>可用 Provider/);
  assert.match(node.innerHTML, /前台/);
  assert.doesNotMatch(node.innerHTML, /保存本任务/);
});

test('a slow reply from a previous mount cannot overwrite the current matrix', async () => {
  const {page, requests, root} = harness();
  const first = root(), second = root();
  page.mount(first);
  page.unmount();
  page.mount(second);
  requests[1].resolve({tasks: [task('conversation.reply', 'primary')], providers: [{id: 'primary', capabilities: ['text'], max_output_tokens: 8192}], host_state: 'running'});
  await flush();
  requests[0].resolve(status());
  await flush();
  assert.match(second.innerHTML, /对话回复/);
  assert.doesNotMatch(second.innerHTML, /记忆整理/);
});

test('switching a provider inline raises one queued change and posting saves that task only', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.change('[data-model-field]', {modelField: 'provider', modelKind: 'memory.reflect', value: 'secondary'});
  assert.match(node.innerHTML, /1<\/b> 项改动待保存/);
  node.click('[data-model-action]', {modelAction: 'save-one', modelKind: 'memory.reflect'});
  const post = requests.find(request => request.method === 'POST');
  assert.equal(post.route, 'model/configure');
  assert.deepEqual(JSON.parse(JSON.stringify(post.values)),
    {kind: 'memory.reflect', operation_key: post.values.operation_key, edit_token: TOKEN, changes: {provider: 'secondary'}, reset: []});
  post.resolve({replayed: false, task: task('memory.reflect', 'secondary', ['text'], 'background')});
  await flush();
  assert.match(node.innerHTML, /已保存 1 项/);
  assert.doesNotMatch(node.innerHTML, /项改动待保存/);
});

test('multi-select assigns one provider to several tasks and keeps capability mismatches out', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.click('[data-model-pick]', {modelPick: 'conversation.reply'});
  node.click('[data-model-pick]', {modelPick: 'memory.reflect'});
  assert.match(node.innerHTML, /已选 <strong>2<\/strong> 项任务/);
  node.change('[data-model-assign]', {value: 'secondary', matches: () => true});
  assert.match(node.innerHTML, /已把 2 项任务指派给 secondary/);
  assert.match(node.innerHTML, /2<\/b> 项改动待保存/);
});

test('restoring inheritance resets explicit fields through the reset list', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  const explicit = status();
  explicit.tasks[0].fields.provider = {value: 'secondary', inherited_value: 'primary', source: 'window', inherited_source: 'installation', explicit: true};
  requests[0].resolve(explicit);
  await flush();
  node.click('[data-model-pick]', {modelPick: 'conversation.reply'});
  node.click('[data-model-action]', {modelAction: 'inherit'});
  assert.match(node.innerHTML, /已把 1 项任务改为跟随上级配置/);
  node.click('[data-model-action]', {modelAction: 'save-one', modelKind: 'conversation.reply'});
  const post = requests.find(request => request.method === 'POST');
  assert.deepEqual([...post.values.reset], ['provider', 'max_output_tokens']);
  assert.deepEqual({...post.values.changes}, {});
  post.resolve({replayed: false, task: task('conversation.reply', 'primary')});
  await flush();
});

test('clicking a provider card filters the matrix and switching view regroups by provider', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.click('[data-model-provider]', {modelProvider: 'secondary'});
  assert.match(node.innerHTML, /清除 Provider 筛选/);
  node.click('[data-model-provider]', {modelProvider: 'secondary'});
  assert.doesNotMatch(node.innerHTML, /清除 Provider 筛选/);
  node.click('[data-model-view]', {modelView: 'providers'});
  assert.match(node.innerHTML, /2 \/ 2 项任务走这里/);
  assert.match(node.innerHTML, /0 \/ 2 项任务走这里/);
  assert.match(node.innerHTML, /还有 2 项能力相符的任务由其他 Provider 承担/);
});

test('an unreadable host offers a retry that loads the matrix', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].reject(Object.assign(new Error('read failed'), {code: 'staging_not_initialized'}));
  await flush();
  assert.match(node.innerHTML, /请先加载|请先在账号与会话加载 V2 运行实例/);
  node.click('[data-model-action]', {modelAction: 'refresh'});
  requests[1].resolve(status());
  await flush();
  assert.match(node.innerHTML, /对话回复/);
  assert.doesNotMatch(node.innerHTML, /请先在账号与会话加载 V2 运行实例/);
});

test('a real dashboard bridge rejects with the code inside Error.message', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].reject(new Error('staging_not_initialized'));
  await flush();
  assert.match(node.innerHTML, /请先在账号与会话加载 V2 运行实例/);
  assert.doesNotMatch(node.innerHTML, /无法读取任务配置，请检查宿主连接/);
});

test('provider search narrows tasks and a routed task opens its editor', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.click('[data-model-view]', {modelView: 'providers'});
  node.input('[data-model-search]', {value: '记忆'});
  assert.match(node.innerHTML, /记忆整理/);
  assert.doesNotMatch(node.innerHTML, /对话回复/);
  node.click('[data-model-open]', {modelOpen: 'memory.reflect'});
  assert.match(node.innerHTML, /data-model-view="tasks" aria-pressed="true"/);
  assert.match(node.innerHTML, /model-fncard open/);
  assert.match(node.innerHTML, /任务附加提示词/);
});

test('a lower-capacity provider adjusts the draft output limit before saving', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  const constrained = status();
  constrained.providers[1].max_output_tokens = 2048;
  requests[0].resolve(constrained);
  await flush();
  node.change('[data-model-field]', {modelField: 'provider', modelKind: 'memory.reflect', value: 'secondary'});
  assert.match(node.innerHTML, /输出上限已调整为 2048/);
  node.click('[data-model-action]', {modelAction: 'save-one', modelKind: 'memory.reflect'});
  const post = requests.find(request => request.method === 'POST');
  assert.deepEqual({...post.values.changes}, {provider: 'secondary', max_output_tokens: 2048});
  const saved = task('memory.reflect', 'secondary', ['text'], 'background');
  saved.fields.max_output_tokens = {...saved.fields.max_output_tokens, value: 2048, explicit: true};
  post.resolve({replayed: false, task: saved});
  await flush();
  assert.match(node.innerHTML, /已保存 1 项/);
});

test('typing a prompt keeps the editor mounted until the field changes', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.click('[data-model-open]', {modelOpen: 'memory.reflect'});
  const before = node.innerHTML;
  node.input('[data-model-field]', {modelField: 'prompt', modelKind: 'memory.reflect', value: '保留当次语境'});
  assert.equal(node.innerHTML, before);
  node.change('[data-model-field]', {modelField: 'prompt', modelKind: 'memory.reflect', value: '保留当次语境'});
  assert.match(node.innerHTML, /1<\/b> 项改动待保存/);
  node.click('[data-model-action]', {modelAction: 'save-one', modelKind: 'memory.reflect'});
  const post = requests.find(request => request.method === 'POST');
  assert.equal(post.values.changes.prompt, '保留当次语境');
  post.resolve({replayed: false, task: task('memory.reflect', 'primary', ['text'], 'background')});
  await flush();
});

test('an uncertain save keeps its original operation and blocks further edits until retry', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.change('[data-model-field]', {modelField: 'provider', modelKind: 'memory.reflect', value: 'secondary'});
  node.click('[data-model-action]', {modelAction: 'save-one', modelKind: 'memory.reflect'});
  const first = requests.find(request => request.method === 'POST');
  node.click('[data-model-action]', {modelAction: 'inherit'});
  assert.equal(requests.filter(request => request.method === 'POST').length, 1);
  first.reject(new Error('network interrupted'));
  await flush();
  node.change('[data-model-field]', {modelField: 'provider', modelKind: 'memory.reflect', value: 'primary'});
  node.click('[data-model-open]', {modelOpen: 'memory.reflect'});
  assert.match(node.innerHTML, /上次保存结果未确认/);
  node.click('[data-model-action]', {modelAction: 'retry', modelKind: 'memory.reflect'});
  const second = requests.filter(request => request.method === 'POST')[1];
  assert.deepEqual(JSON.parse(JSON.stringify(second.values)), JSON.parse(JSON.stringify(first.values)));
  second.resolve({replayed: true, task: task('memory.reflect', 'secondary', ['text'], 'background')});
  await flush();
  assert.match(node.innerHTML, /原保存已确认/);
  assert.doesNotMatch(node.innerHTML, /上次保存结果未确认/);
});

test('switching to the voice tab lazily loads the voice config and saves via the voice route', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.click('[data-model-tab]', {modelTab: 'voice'});
  const get = requests.find(r => r.method === 'GET' && r.route === 'model/voice');
  assert.ok(get, 'voice tab should trigger a GET to model/voice');
  const voice = {languages: [{k: 'zh', n: '中文', bind: ''}, {k: 'ja', n: '日语', bind: ''}, {k: 'en', n: '英语', bind: ''}],
    providers: [{id: 'tts-live'}], timeout_seconds: 30, voice_enabled: true, edit_token: TOKEN};
  get.resolve(voice);
  await flush();
  assert.match(node.innerHTML, /语音模型/);
  assert.match(node.innerHTML, /按语种配置 TTS/);
  node.change('[data-voice-provider]', {value: 'tts-live'});
  node.click('[data-voice-save]');
  const post = requests.find(r => r.method === 'POST' && r.route === 'model/voice/save');
  assert.ok(post, 'voice save should POST to model/voice/save');
  assert.equal(post.values.changes.voice_ja_provider_id, 'tts-live');
  post.resolve({...voice, languages: voice.languages.map(item => item.k === 'ja' ? {...item, bind: 'tts-live'} : item)});
  await flush();
  assert.match(node.innerHTML, /语音配置已保存/);
  node.click('[data-ve-test]');
  const testRequest = requests.find(r => r.route === 'model/voice/test');
  assert.deepEqual({...testRequest.values}, {provider_id: 'tts-live', language: 'ja'});
  testRequest.resolve({status: 'ok', data: {provider_id: 'tts-live', status: 'ok', latency_ms: 25, code: ''}});
  await flush();
  assert.match(node.innerHTML, /语音合成成功/);
});

test('a provider shared across languages warns and can unbind the others before saving', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.click('[data-model-tab]', {modelTab: 'voice'});
  const get = requests.find(r => r.method === 'GET' && r.route === 'model/voice');
  const voice = {languages: [{k: 'zh', n: '中文', bind: 'tts-live'}, {k: 'ja', n: '日语', bind: 'tts-live'}, {k: 'en', n: '英语', bind: ''}],
    providers: [{id: 'tts-live'}], timeout_seconds: 30, voice_enabled: true, edit_token: TOKEN};
  get.resolve(voice);
  await flush();
  assert.match(node.innerHTML, /同时绑定到中文/);
  node.click('[data-voice-unbind]');
  assert.match(node.innerHTML, /已解除其他语种的同 Provider 绑定/);
  node.click('[data-voice-save]');
  const post = requests.find(r => r.method === 'POST' && r.route === 'model/voice/save');
  assert.equal(post.values.changes.voice_zh_provider_id, '');
  assert.ok(!Object.hasOwn(post.values.changes, 'voice_ja_provider_id'), 'untouched language must not be re-sent');
});

test('switching to the image tab loads image config and saves via the image route', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.click('[data-model-tab]', {modelTab: 'image'});
  const get = requests.find(r => r.method === 'GET' && r.route === 'model/image');
  assert.ok(get, 'image tab should trigger a GET to model/image');
  const image = {actions: [
    {action: 'image.generate', enabled: true, owner: 'image-plugin', provider_id: 'native-image', loaded: true, current: true, registered: true, state: 'ready'},
    {action: 'image.edit', enabled: true, owner: '', provider_id: '', loaded: false, current: false, registered: false, state: 'unavailable'},
    {action: 'image.mask_edit', enabled: true, owner: 'image-plugin', provider_id: 'native-image', loaded: true, current: true, registered: true, state: 'ready'},
  ], enabled: {'image.generate': true, 'image.edit': true, 'image.mask_edit': true}, authorization: 'checked_for_each_invocation'};
  get.resolve(image);
  await flush();
  assert.match(node.innerHTML, /生图模型/);
  assert.match(node.innerHTML, /Native/);
  assert.match(node.innerHTML, /扩展未加载/);
  node.click('[data-img-test]', {imgTest: 'image.mask_edit'});
  const maskCheck = requests.find(r => r.route === 'model/image/test');
  assert.equal(maskCheck.values.action, 'image.mask_edit');
  maskCheck.resolve({...image.actions[2], check: 'registration_only'});
  await flush();
  assert.match(node.innerHTML, /局部改图已注册，可由后续真实任务调用/);
  node.change('[data-img-toggle]', {imgToggle: 'image.edit', checked: false});
  node.change('[data-img-toggle]', {imgToggle: 'image.mask_edit', checked: false});
  node.click('[data-img-save]');
  const post = requests.find(r => r.method === 'POST' && r.route === 'model/image/save');
  assert.ok(post, 'image save should POST to model/image/save');
  assert.deepEqual({...post.values.enabled}, {'image.generate': true, 'image.edit': false, 'image.mask_edit': false});
  post.resolve({...image, enabled: post.values.enabled, actions: image.actions.map(item =>
    ['image.edit', 'image.mask_edit'].includes(item.action) ? {...item, enabled: false, state: 'disabled'} : item)});
  await flush();
  assert.match(node.innerHTML, /生图开关已保存/);
  node.click('[data-img-test]', {imgTest: 'image.generate'});
  const check = requests.find(r => r.route === 'model/image/test' && r.values.action === 'image.generate');
  assert.equal(check.values.action, 'image.generate');
  check.resolve({...image.actions[0], check: 'registration_only'});
  await flush();
  assert.match(node.innerHTML, /已注册，可由后续真实任务调用/);
});

test('switching tabs round-trip keeps the functional matrix without reloading', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.click('[data-model-tab]', {modelTab: 'voice'});
  requests.find(r => r.route === 'model/voice').resolve({languages: [{k: 'zh', n: '中文', bind: ''}, {k: 'ja', n: '日语', bind: ''}, {k: 'en', n: '英语', bind: ''}], providers: [], timeout_seconds: 30, voice_enabled: false, edit_token: TOKEN});
  await flush();
  node.click('[data-model-tab]', {modelTab: 'fn'});
  await flush();
  assert.match(node.innerHTML, /对话回复/);
  assert.match(node.innerHTML, /记忆整理/);
  // exactly one functional GET happened on mount; switching back reused in-memory state
  const fnGets = requests.filter(r => r.method === 'GET' && r.route === 'model');
  assert.equal(fnGets.length, 1, 'functional matrix must not be re-fetched on tab return');
});

test('the functional page exposes the design subtabs and the situation map derives routing', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  assert.match(node.innerHTML, /态势图/);
  assert.match(node.innerHTML, /模型配置/);
  assert.match(node.innerHTML, /替换策略/);
  node.click('[data-model-sub]', {modelSub: 'map'});
  assert.match(node.innerHTML, /需要模型的功能/);
  assert.match(node.innerHTML, /可用模型/);
  assert.match(node.innerHTML, /对话回复/);
  assert.match(node.innerHTML, /按能力槽/);
  node.click('[data-model-av]', {modelAv: 'lane'});
  assert.match(node.innerHTML, /前台/);
  assert.match(node.innerHTML, /后台/);
});

test('quick config fans a slot provider out to every task via model/configure', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.click('[data-model-cm]', {modelCm: 'quick'});
  assert.match(node.innerHTML, /覆盖/);
  node.change('[data-model-slot]', {modelSlot: '对话', value: 'secondary'});
  node.click('[data-model-slot-apply]', {modelSlotApply: '对话'});
  const posts = requests.filter(r => r.method === 'POST' && r.route === 'model/configure');
  assert.ok(posts.length >= 1, 'slot override should POST at least one model/configure');
  posts.forEach(p => p.resolve({replayed: false, task: task('conversation.reply', 'secondary')}));
  await flush();
  assert.match(node.innerHTML, /已保存/);
});

test('replacement policy edits keyword rules into the task replacement_rules field', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.click('[data-model-sub]', {modelSub: 'pol'});
  assert.match(node.innerHTML, /关键词换模/);
  assert.match(node.innerHTML, /高价时段替代/);
  assert.match(node.innerHTML, /拒答替代/);
  assert.match(node.innerHTML, /作用范围/);
  node.click('[data-rule-add]');
  assert.match(node.innerHTML, /data-rule-card="conversation.reply:0"/);
  node.change('[data-rule-keywords]', {ruleKeywords: 'conversation.reply:0', value: '写代码, 报错'});
  node.change('[data-rule-provider]', {ruleProvider: 'conversation.reply:0', value: 'secondary'});
  node.change('[data-rule-match]', {ruleMatch: 'conversation.reply:0', value: 'exact'});
  node.click('[data-policy-save]', {policySave: 'conversation.reply'});
  const post = requests.find(request => request.method === 'POST');
  const rules = JSON.parse(post.values.changes.replacement_rules);
  assert.equal(rules.length, 1);
  assert.deepEqual(rules[0].keywords, ['写代码', '报错']);
  assert.equal(rules[0].provider_id, 'secondary');
  assert.equal(rules[0].match_mode, 'exact');
  assert.equal(rules[0].priority, 0);
  post.resolve({replayed: false, task: editable('conversation.reply', 'primary')});
  await flush();
  assert.match(node.innerHTML, /已保存 1 项/);
});

test('the refusal switch saves fallback_on_refusal for the task', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.click('[data-model-sub]', {modelSub: 'pol'});
  node.click('[data-model-pm]', {modelPm: 'refuse'});
  assert.match(node.innerHTML, /拒答替代/);
  node.change('[data-refusal-switch]', {checked: true});
  node.click('[data-policy-save]', {policySave: 'conversation.reply'});
  const post = requests.find(request => request.method === 'POST');
  assert.deepEqual({...post.values.changes}, {fallback_on_refusal: true});
  post.resolve({replayed: false, task: editable('conversation.reply', 'primary')});
  await flush();
  assert.match(node.innerHTML, /已保存 1 项/);
});

test('the high-price preset writes two keyword-free time rules with a timezone', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.click('[data-model-sub]', {modelSub: 'pol'});
  node.click('[data-model-pm]', {modelPm: 'peak'});
  assert.match(node.innerHTML, /高价时段替代/);
  node.change('[data-peak-provider]', {peakProvider: '', value: 'secondary'});
  node.click('[data-peak-preset]');
  node.click('[data-peak-apply]');
  node.click('[data-policy-save]', {policySave: 'conversation.reply'});
  const post = requests.find(request => request.method === 'POST');
  const rules = JSON.parse(post.values.changes.replacement_rules);
  assert.equal(rules.length, 2);
  assert.deepEqual(rules[0].keywords, []);
  assert.equal(rules[0].provider_id, 'secondary');
  assert.deepEqual(rules.map(rule => [rule.time_window.start, rule.time_window.end]), [['09:00', '12:00'], ['14:00', '18:00']]);
  assert.equal(rules[0].time_window.timezone, 'Asia/Shanghai');
  post.resolve({replayed: false, task: editable('conversation.reply', 'primary')});
  await flush();
});

test('a task whose routes are inherited shows the upstream rule count instead of editing them', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  const shared = status();
  shared.tasks[0].fields.replacement_rules = {value: '[]', inherited_value: JSON.stringify([
    {name: '共享规则', keywords: ['代码'], provider_id: 'secondary'},
  ]), source: 'default', inherited_source: 'installation', explicit: false};
  requests[0].resolve(shared);
  await flush();
  node.click('[data-model-sub]', {modelSub: 'pol'});
  assert.match(node.innerHTML, /共享规则/);
  assert.match(node.innerHTML, /上级默认规则 1 条/);
  node.click('[data-policy-discard]', {policyDiscard: 'conversation.reply'});
  assert.match(node.innerHTML, /已放弃/);
});

test('the situation map lists rule counts and routes a selected task into the editor', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  const mapped = status();
  mapped.tasks[0].fields.replacement_rules = {value: JSON.stringify([{name: '代码问题', keywords: ['代码'], provider_id: 'secondary'}]), inherited_value: '[]', source: 'window', inherited_source: 'default', explicit: true};
  requests[0].resolve(mapped);
  await flush();
  node.click('[data-model-sub]', {modelSub: 'map'});
  assert.match(node.innerHTML, /1 规则/);
  node.click('[data-map-pick]', {mapPick: 'conversation.reply'});
  assert.match(node.innerHTML, /已选 <b>1<\/b> 项任务/);
  node.click('[data-map-test]');
  const probe = requests.find(r => r.route === 'model/test');
  assert.deepEqual({...probe.values}, {provider_id: 'primary'});
  probe.resolve({status: 'ok', data: {provider_id: 'primary', status: 'ok', latency_ms: 15, code: ''}});
  await flush();
  assert.match(node.innerHTML, /连接成功/);
  node.click('[data-map-clear]');
  assert.doesNotMatch(node.innerHTML, /data-map-test/);
  node.click('[data-model-open]', {modelOpen: 'memory.reflect'});
  assert.match(node.innerHTML, /model-fncard open/);
  assert.match(node.innerHTML, /任务附加提示词/);
});

test('the scope selector saves replacement_scope for the current task', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  node.click('[data-model-sub]', {modelSub: 'pol'});
  assert.match(node.innerHTML, /仅插件调用/);
  assert.match(node.innerHTML, /仅普通对话模型/);
  assert.match(node.innerHTML, /全部生效/);
  node.click('[data-model-scope]', {modelScope: 'plugin'});
  assert.match(node.innerHTML, /替换范围已改动/);
  node.click('[data-policy-save]', {policySave: 'conversation.reply'});
  const post = requests.find(r => r.route === 'model/configure');
  assert.equal(post.values.changes.replacement_scope, 'plugin');
  post.resolve({replayed: false, task: editable('conversation.reply', 'primary')});
  await flush();
  assert.match(node.innerHTML, /已保存 1 项/);
});

test('two same-type providers show their model names so they are tellable apart', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  /* 宿主新增的 model 字段：同一个 AstrBot 上挂两个同类型 Provider 时，
     只显示 id 的话下拉里是两行一样的字，选错只能靠试。 */
  requests[0].resolve({
    tasks: [{kind: 'conversation.reply', lane: 'foreground', capabilities: ['text'], edit_token: TOKEN,
             application_state: 'applied', fields: baseFields('primary')}],
    providers: [
      {id: 'primary', capabilities: ['text'], max_output_tokens: 8192, model: 'deepseek-v4-flash'},
      {id: 'secondary', capabilities: ['text'], max_output_tokens: 8192, model: 'deepseek-v4-pro'},
    ],
    host_state: 'running',
  });
  await flush();
  node.click('[data-model-open]', {modelOpen: 'conversation.reply'});
  /* 主 Provider 的下拉里两项必须带模型名。 */
  assert.match(node.innerHTML, /primary · deepseek-v4-flash/);
  assert.match(node.innerHTML, /secondary · deepseek-v4-pro/);
  /* Provider 视图里模型名单独占一行。 */
  node.click('[data-model-view]', {modelView: 'providers'});
  assert.match(node.innerHTML, /class="model-provider-model">deepseek-v4-flash</);
});

test('a provider without a model name degrades to its bare id', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  /* 本地测试适配器没有"模型"这个概念，字段允许为空。
     空值不能拼出 "primary · " 这种尾巴，也不能渲染出一个空的模型名行。 */
  requests[0].resolve({
    tasks: [{kind: 'conversation.reply', lane: 'foreground', capabilities: ['text'], edit_token: TOKEN,
             application_state: 'applied', fields: baseFields('primary')}],
    providers: [{id: 'primary', capabilities: ['text'], max_output_tokens: 8192, model: ''}],
    host_state: 'running',
  });
  await flush();
  assert.doesNotMatch(node.innerHTML, /primary ·/);
  node.click('[data-model-view]', {modelView: 'providers'});
  assert.doesNotMatch(node.innerHTML, /model-provider-model/);
});

/* 生图配置的边界表由扩展随配置一起下发（GET model/image/config 的 limits）。
   页面据此做两件事：给数字框写 min/max、提交前挡下越界值。
   这里守住"挡下"这一半——它是用户能看见的那一半。 */
function imageConfig(limits) {
  return {
    revision: 'r'.repeat(64),
    sections: {
      preparation: {routes: [], default_generate_route: '', default_edit_route: '',
                    daily_limit: 100, retention_days: 30, max_storage_mb: 512, max_concurrency: 2},
      sd_webui: {base_url: '', timeout_seconds: 300},
      comfyui: {base_url: '', timeout_seconds: 300, workflows: []},
    },
    limits,
  };
}
const LIMITS = {
  preparation: {daily_limit: {min: 1, max: 10000}, retention_days: {min: 1, max: 365},
                max_storage_mb: {min: 16, max: 102400}, max_concurrency: {min: 1, max: 4}},
  connection: {timeout_seconds: {min: 5, max: 1800}},
  parameters: {common: {}, sd_webui: {}, float: {}, text: {}},
  max_routes: 32, max_canvas_pixels: 16777216,
  guidance: {max_items: 16, max_chars: 4000},
};

async function openImageConfig(node, requests, limits, routes, customize) {
  node.click('[data-model-tab]', {modelTab: 'image'});
  const image = {actions: [{action: 'image.generate', enabled: true, owner: 'image-plugin',
    provider_id: 'native-image', loaded: true, current: true, registered: true, state: 'ready'}],
    enabled: {'image.generate': true, 'image.edit': true, 'image.mask_edit': true}, authorization: 'checked_for_each_invocation'};
  requests.find(r => r.method === 'GET' && r.route === 'model/image').resolve(image);
  await flush();
  node.click('[data-img-config]');
  const config = requests.find(r => r.method === 'GET' && r.route === 'model/image/config');
  assert.ok(config, 'opening the route editor should GET model/image/config');
  const payload = imageConfig(limits);
  if (routes) payload.sections.preparation.routes = routes;
  if (customize) customize(payload);
  config.resolve(payload);
  await flush();
}

test('the route editor writes the extension limits onto its number inputs', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, LIMITS);
  /* 上限来自扩展，不是页面自己抄的数字。 */
  assert.match(node.innerHTML, /data-imgcfg-tab="routes"[^>]*aria-selected="true"/);
  node.click('[data-imgcfg-tab]', {imgcfgTab: 'limits'});
  assert.match(node.innerHTML, /min="1" max="10000" data-imgr-num="daily_limit"/);
  assert.match(node.innerHTML, /min="1" max="4" data-imgr-num="max_concurrency"/);
  assert.match(node.innerHTML, /min="16" max="102400" data-imgr-num="max_storage_mb"/);
  node.click('[data-imgcfg-tab]', {imgcfgTab: 'comfyui'});
  assert.match(node.innerHTML, /min="5" max="1800" data-imgr-sec="comfyui:timeout_seconds"/);
});

test('an out-of-range value is refused before the save is posted', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, LIMITS);
  node.click('[data-imgcfg-tab]', {imgcfgTab: 'limits'});
  node.change('[data-imgr-num]', {imgrNum: 'max_concurrency', valueAsNumber: 8});
  await flush();
  node.click('[data-imgcfg-save]');
  await flush();
  /* 关键：**没有发出** POST。提交一次才知道越界正是这次要修掉的东西。 */
  assert.equal(requests.filter(r => r.route === 'model/image/config/save').length, 0,
    'an out-of-range value must not be submitted');
  /* 提示要说清是哪一格、允许多少、当前多少。 */
  assert.match(node.innerHTML, /最大并发 需要在 1–4 之间，当前是 8。/);
});

test('an in-range value still reaches the extension for its own validation', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, LIMITS);
  node.click('[data-imgcfg-tab]', {imgcfgTab: 'limits'});
  assert.match(node.innerHTML, /所有面板共用同一份草稿/);
  node.change('[data-imgr-num]', {imgrNum: 'max_concurrency', valueAsNumber: 3});
  await flush();
  node.click('[data-imgcfg-tab]', {imgcfgTab: 'routes'});
  node.click('[data-imgcfg-tab]', {imgcfgTab: 'limits'});
  assert.match(node.innerHTML, /有未保存更改/);
  assert.match(node.innerHTML, /data-imgr-num="max_concurrency" value="3"/);
  node.click('[data-imgcfg-save]');
  const post = requests.find(r => r.route === 'model/image/config/save');
  assert.ok(post, 'an in-range change must be submitted');
  assert.equal(post.values.changes.preparation.max_concurrency, 3);
});

test('a host that does not publish limits leaves the editor usable', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  /* 旧版扩展不下发 limits。此时不能写空 min/max（浏览器会报非法数值），
     也不能因此把保存路径整个堵死。 */
  await openImageConfig(node, requests, undefined);
  node.click('[data-imgcfg-tab]', {imgcfgTab: 'limits'});
  assert.doesNotMatch(node.innerHTML, /min=""|max=""/);
  node.change('[data-imgr-num]', {imgrNum: 'max_concurrency', valueAsNumber: 999});
  await flush();
  node.click('[data-imgcfg-save]');
  const post = requests.find(r => r.route === 'model/image/config/save');
  assert.ok(post, 'without limits the extension remains the only judge');
  assert.equal(post.values.changes.preparation.max_concurrency, 999);
});

test('image configuration tabs preserve drafts and save only changed sections', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, LIMITS);
  assert.match(node.innerHTML, /data-imgcfg-save disabled/);
  node.click('[data-imgcfg-tab]', {imgcfgTab: 'comfyui'});
  assert.match(node.innerHTML, /data-imgr-sec="comfyui:base_url"/);
  node.change('[data-imgr-sec]', {imgrSec: 'comfyui:base_url', value: 'http://localhost:8188'});
  node.click('[data-imgcfg-tab]', {imgcfgTab: 'sd_webui'});
  node.change('[data-imgr-sec]', {imgrSec: 'sd_webui:base_url', value: 'http://localhost:7860'});
  node.click('[data-imgcfg-tab]', {imgcfgTab: 'comfyui'});
  assert.match(node.innerHTML, /data-imgr-sec="comfyui:base_url" value="http:\/\/localhost:8188"/);
  node.click('[data-imgcfg-save]');
  const post = requests.find(r => r.route === 'model/image/config/save');
  assert.ok(post, 'edited connections must be submitted');
  assert.deepEqual(JSON.parse(JSON.stringify(post.values.changes)), {
    comfyui: {base_url: 'http://localhost:8188'},
    sd_webui: {base_url: 'http://localhost:7860'},
  });
});

test('ComfyUI workflow names appear in route selectors and save with the route', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, LIMITS, [{...COMFY_ROUTE, workflow_id: 'portrait'}], payload => {
    payload.sections.comfyui.workflows = [
      {name: 'portrait', path: 'portrait-api.json'},
      {name: 'edit', path: 'edit-api.json'},
    ];
  });
  assert.match(node.innerHTML, /<option value="portrait" selected>portrait<\/option>/);
  node.change('[data-imgr-edit]', {imgrEdit: '0:workflow_id', value: 'edit'});
  node.click('[data-imgcfg-save]');
  const post = requests.find(r => r.route === 'model/image/config/save');
  assert.equal(post.values.changes.preparation.routes[0].workflow_id, 'edit');
});

/* ---------- 路线的四个预置字段 ----------
   parameters / guidance 给控件（边界来自扩展下发的 limits），
   reference_bindings / masked_edit 只读（槽位表在扩展手里，蒙版是派生值）。
   这一组守住"页面能改的只有前两个、且越界与不适用的组合当场挡下"。 */
const ROUTE_LIMITS = {
  preparation: {daily_limit: {min: 1, max: 10000}, retention_days: {min: 1, max: 365},
                max_storage_mb: {min: 16, max: 102400}, max_concurrency: {min: 1, max: 4}},
  connection: {timeout_seconds: {min: 5, max: 1800}},
  parameters: {
    common: {width: {min: 64, max: 4096}, height: {min: 64, max: 4096}, seed: {min: -1, max: 9007199254740991}},
    sd_webui: {steps: {min: 1, max: 150}, batch_size: {min: 1, max: 4}},
    float: {cfg_scale: {min: 0, max: 30}, denoising_strength: {min: 0, max: 1}},
    text: {sampler_name: {max_length: 120}},
  },
  max_routes: 32, max_canvas_pixels: 16777216,
  guidance: {max_items: 16, max_chars: 4000},
};
const COMFY_ROUTE = {route_id: 'r-comfy', operation: 'generate', backend: 'comfyui', workflow_id: 'wf', profile: 'default'};
const SD_ROUTE = {route_id: 'r-sd', operation: 'generate', backend: 'sd_webui', profile: 'default'};

/* 取某条路线的 edit_method 下拉框 HTML——按索引切片，避免相邻路线的选项混进来。 */
function methodSelect(html, index) {
  const at = html.indexOf(`data-imgr-guide="${index}:edit_method"`);
  assert.ok(at >= 0, `route ${index} should render an edit_method select`);
  return html.slice(at, html.indexOf('</select>', at));
}

test('parameter inputs follow the backend the route declares', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, ROUTE_LIMITS, [COMFY_ROUTE, SD_ROUTE]);
  /* ComfyUI 只有公共参数：宽、高、种子。 */
  assert.match(node.innerHTML, /min="64" max="4096" data-imgr-param="0:width"/);
  assert.match(node.innerHTML, /data-imgr-param="0:seed"/);
  assert.doesNotMatch(node.innerHTML, /data-imgr-param="0:steps"/);
  /* SD WebUI 多出步数、每批张数、两个浮点与采样器，边界一样来自扩展。 */
  assert.match(node.innerHTML, /min="1" max="150" data-imgr-param="1:steps"/);
  assert.match(node.innerHTML, /min="0" max="30" data-imgr-param="1:cfg_scale"/);
  assert.match(node.innerHTML, /step="0.01"/);
  assert.match(node.innerHTML, /maxlength="120" data-imgr-param="1:sampler_name"/);
});

test('an out-of-range parameter is refused before the save is posted', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, ROUTE_LIMITS, [COMFY_ROUTE]);
  node.change('[data-imgr-param]', {imgrParam: '0:width', value: '9999', valueAsNumber: 9999});
  await flush();
  node.click('[data-imgcfg-save]');
  await flush();
  assert.equal(requests.filter(r => r.route === 'model/image/config/save').length, 0,
    'an out-of-range route parameter must not be submitted');
  assert.match(node.innerHTML, /路线 r-comfy 的宽需要在 64–4096 之间，当前是 9999。/);
});

test('a declared parameter reaches the extension as a number', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, ROUTE_LIMITS, [COMFY_ROUTE]);
  node.change('[data-imgr-param]', {imgrParam: '0:width', value: '1024', valueAsNumber: 1024});
  await flush();
  node.click('[data-imgcfg-save]');
  const post = requests.find(r => r.route === 'model/image/config/save');
  assert.ok(post, 'an in-range parameter must be submitted');
  assert.equal(post.values.changes.preparation.routes[0].parameters.width, 1024);
  assert.equal(typeof post.values.changes.preparation.routes[0].parameters.width, 'number');
});

test('clearing a parameter drops the key instead of writing an empty value', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, ROUTE_LIMITS,
    [{...COMFY_ROUTE, parameters: {width: 1024, seed: 7}}]);
  node.change('[data-imgr-param]', {imgrParam: '0:width', value: '', valueAsNumber: NaN});
  node.change('[data-imgr-param]', {imgrParam: '0:seed', value: '', valueAsNumber: NaN});
  await flush();
  node.click('[data-imgcfg-save]');
  const post = requests.find(r => r.route === 'model/image/config/save');
  assert.ok(post, 'clearing the last parameter is still a change worth saving');
  const params = post.values.changes.preparation.routes[0].parameters;
  /* 空字符串会被扩展的参数类型校验拒掉，所以整段参数键一起删掉，回到它的默认值。 */
  assert.equal(params, undefined);
});

test('the edit method options follow the operation, backend and mask declaration', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, ROUTE_LIMITS, [
    {...COMFY_ROUTE, route_id: 'gen'},
    {route_id: 'edit-comfy', operation: 'edit', backend: 'comfyui', profile: 'default'},
    {route_id: 'edit-sd', operation: 'edit', backend: 'sd_webui', profile: 'default'},
    {route_id: 'edit-sd-mask', operation: 'edit', backend: 'sd_webui', profile: 'default', masked_edit: true},
  ]);
  const generate = methodSelect(node.innerHTML, 0);
  assert.match(generate, /自动（未声明）/);
  assert.doesNotMatch(generate, /指令编辑/);
  const comfyEdit = methodSelect(node.innerHTML, 1);
  for (const label of ['整图重绘', '指令编辑', '蒙版局部', '受控工作流']) assert.match(comfyEdit, new RegExp(label));
  const sdEdit = methodSelect(node.innerHTML, 2);
  assert.match(sdEdit, /整图重绘/);
  assert.doesNotMatch(sdEdit, /蒙版局部/);
  const sdMask = methodSelect(node.innerHTML, 3);
  assert.match(sdMask, /蒙版局部/);
  assert.doesNotMatch(sdMask, /整图重绘/);
});

test('a declared edit method that the backend cannot accept is refused with the allowed set', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, ROUTE_LIMITS, [
    {route_id: 'edit-sd', operation: 'edit', backend: 'sd_webui', profile: 'default',
     guidance: {edit_method: 'instruction'}},
  ]);
  /* 页面补一条标注而不是静默改写配置。 */
  assert.match(node.innerHTML, /当前不接受，保存会被拒/);
  node.click('[data-imgcfg-save]');
  await flush();
  assert.equal(requests.filter(r => r.route === 'model/image/config/save').length, 0);
  assert.match(node.innerHTML, /路线 edit-sd 的改图方式「指令编辑」不适用于当前操作或后端/);
});

test('guidance text and lists reach the extension in its declared shape', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, ROUTE_LIMITS,
    [{route_id: 'edit-comfy', operation: 'edit', backend: 'comfyui', profile: 'default'}]);
  node.change('[data-imgr-guide]', {imgrGuide: '0:summary', value: '适合写实全身'});
  node.change('[data-imgr-guide]', {imgrGuide: '0:suitable_for', value: '全身构图\n多主体同框\n'});
  node.change('[data-imgr-guide]', {imgrGuide: '0:edit_method', value: 'instruction'});
  await flush();
  node.click('[data-imgcfg-save]');
  const post = requests.find(r => r.route === 'model/image/config/save');
  assert.ok(post, 'guidance edits must be submitted');
  const guidance = post.values.changes.preparation.routes[0].guidance;
  assert.equal(guidance.summary, '适合写实全身');
  assert.equal(guidance.edit_method, 'instruction');
  /* 数组是在 vm 上下文里建的，拷回本域再比，否则 deepEqual 只在原型上失败。 */
  assert.deepEqual(Array.from(guidance.suitable_for), ['全身构图', '多主体同框']);
});

test('guidance beyond the published limits is refused before the save', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, ROUTE_LIMITS,
    [{route_id: 'edit-comfy', operation: 'edit', backend: 'comfyui', profile: 'default'}]);
  const many = Array.from({length: 17}, (unused, index) => `场景 ${index + 1}`).join('\n');
  node.change('[data-imgr-guide]', {imgrGuide: '0:suitable_for', value: many});
  await flush();
  node.click('[data-imgcfg-save]');
  await flush();
  assert.equal(requests.filter(r => r.route === 'model/image/config/save').length, 0);
  assert.match(node.innerHTML, /「适用场景」最多 16 条，当前 17 条。/);
});

test('the two preset fields stay read-only but report what was declared', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, ROUTE_LIMITS, [
    {route_id: 'edit-mask', operation: 'edit', backend: 'comfyui', profile: 'default', masked_edit: true,
     reference_bindings: [{slot: 'image1', role: 'edit_source', subject_ids: []},
                          {slot: 'mask1', role: 'edit_mask', subject_ids: []}]},
  ]);
  /* 已声明的绑定按「用途 ← 槽位」列出来，并写清为什么本页不给控件。 */
  assert.match(node.innerHTML, /底图 ← image1/);
  assert.match(node.innerHTML, /蒙版 ← mask1/);
  assert.match(node.innerHTML, /不是开关/);
  /* 两个字段都不该出现任何控件。 */
  assert.doesNotMatch(node.innerHTML, /data-imgr-param="0:masked_edit"/);
  assert.doesNotMatch(node.innerHTML, /data-imgr-guide="0:reference_bindings"/);
  assert.doesNotMatch(node.innerHTML, /data-imgr-masked/);
});

test('an expanded preset block survives a re-render', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  await openImageConfig(node, requests, ROUTE_LIMITS, [COMFY_ROUTE]);
  assert.match(node.innerHTML, /data-imgr-ext="0"(?! open)/);
  node.click('details[data-imgr-ext]', {imgrExt: '0'});
  /* 任何一次重绘（这里用准备段的数字框触发）都不该把展开状态丢掉。 */
  node.change('[data-imgr-num]', {imgrNum: 'max_concurrency', valueAsNumber: 3});
  await flush();
  assert.match(node.innerHTML, /data-imgr-ext="0" open/);
});

test('a route list too large for one save is refused with the route that fills it', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(status());
  await flush();
  /* 每格说明都在扩展允许的 4000 字以内，但 30 条路线加起来超过了宿主的请求体上限。
     这正是路线说明可编辑之后才出现的失败方式。 */
  const long = '很长的路线说明'.repeat(500);
  const routes = Array.from({length: 30}, (unused, index) => ({
    route_id: 'route-' + (index + 1), operation: 'edit', backend: 'comfyui', profile: 'default',
    guidance: {summary: long, prompt_advice: long, test_notes: long},
  }));
  await openImageConfig(node, requests, ROUTE_LIMITS, routes);
  node.change('[data-imgr-param]', {imgrParam: '0:width', value: '1024', valueAsNumber: 1024});
  await flush();
  node.click('[data-imgcfg-save]');
  await flush();
  assert.equal(requests.filter(r => r.route === 'model/image/config/save').length, 0,
    'an oversized route document must not be posted');
  assert.match(node.innerHTML, /超过一次能保存的 256 KB/);
  assert.match(node.innerHTML, /最占地方的是「route-1」/);
});
