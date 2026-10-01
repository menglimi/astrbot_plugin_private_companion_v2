const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.resolve(__dirname, '../pages/陪伴小屋/semantic-page.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));

function catalog(kind, name) {
  return {
    state: 'ready', selection_ready: true, settings: {revision: 0}, providers: {},
    catalog: {reaction: {enabled: 1}, slang: {enabled: 1}},
    sessions: ['group-1', 'group-2'], session_id: 'group-1', next_after: null,
    items: [{id: kind + '-1', kind, revision: 1, enabled: true,
      payload: kind === 'reaction' ? {name} : {term: name, meaning: name}}],
  };
}

function harness(group = false) {
  const requests = [];
  const window = {
    CompanionProduct: {
      hosted: () => true, scopeKey: () => 'same-role',
      selection: () => ({target_id: 'target', role_id: 'role'}),
      target: () => group ? {scope_kind: 'group', group_id: 'group-1'} : {scope_kind: 'private'},
      unwrap: value => value,
      /* 页面统一走 bridgeFor() 取桥，夹具必须提供。刻意返回同步 thenable：
         用 Promise.resolve 会多引入一个微任务，而下面几个用例断言的是
         「mount 之后 requests[0] 立刻可用」——多一拍就取到 undefined。 */
      bridgeFor: () => ({then: resolve => resolve(window.AstrBotPluginPage)}),
      /* 同步取桥。页面先问它，没有再走 bridgeFor()——这样常规路径不发散时序。 */
      bridgeNow: () => window.AstrBotPluginPage,
    },
    AstrBotPluginPage: {
      apiGet: (route, values) => new Promise((resolve, reject) => requests.push({method: 'GET', route, values, resolve, reject})),
      apiPost: (route, values) => new Promise((resolve, reject) => requests.push({method: 'POST', route, values, resolve, reject})),
    },
    lucide: {createIcons() {}},
  };
  /* FormData 的替身：page 用 new FormData(form) 读表单，而这里的 form 是
     提交时构造的桩，所以直接用它的 values 映射。 */
  class FormDataStub {
    constructor(form) { this.map = (form && form.values) || {}; }
    has(name) { return Boolean(this.map[name]); }
    get(name) { return name in this.map ? this.map[name] : null; }
  }
  vm.runInNewContext(source, {window, AbortController, FormData: FormDataStub});
  function root() {
    const handlers = {};
    return {
      isConnected: true, innerHTML: '',
      addEventListener(type, handler) { handlers[type] = handler; },
      querySelectorAll() { return []; },
      querySelector() { return null; },
      click(selector, dataset) {
        handlers.click({target: {closest: candidate => candidate === selector ? {dataset} : null}});
      },
      /* 设置表单的提交：values 是 FormData 的替身内容。
         数值保持原类型，否则 Number() 读到字符串会得到 NaN。 */
      submit(id, values) {
        const map = values || {};
        handlers.submit({preventDefault() {}, target: {id, values: map}});
      },
    };
  }
  return {page: window.CompanionSemanticPage, requests, root};
}

test('late response from a previous mount cannot overwrite the current catalog', async () => {
  const {page, requests, root} = harness();
  const first = root(), second = root();
  page.mount(first);
  page.unmount();
  page.mount(second);
  requests[1].resolve(catalog('reaction', 'current reaction'));
  await flush();
  requests[0].resolve(catalog('reaction', 'stale reaction'));
  await flush();
  assert.match(second.innerHTML, /current reaction/);
  assert.doesNotMatch(second.innerHTML, /stale reaction/);
});

test('switching catalogs discards an outstanding item detail', async () => {
  const {page, requests, root} = harness(true);
  const node = root();
  page.mount(node);
  requests[0].resolve(catalog('reaction', 'reaction entry'));
  await flush();
  node.click('[data-semantic-open]', {semanticOpen: 'reaction-1'});
  assert.equal(requests[1].values.kind, 'reaction');
  node.click('[data-semantic-kind]', {semanticKind: 'slang'});
  assert.equal(requests[2].values.kind, 'slang');
  requests[2].resolve(catalog('slang', 'current slang'));
  await flush();
  requests[1].resolve({item: {id: 'reaction-1', revision: 1, enabled: true,
    payload: {name: 'stale detail'}}});
  await flush();
  assert.match(node.innerHTML, /current slang/);
  assert.doesNotMatch(node.innerHTML, /stale detail|id="semanticEditor"/);
});

test('late command receipt cannot reload a newly selected catalog', async () => {
  const {page, requests, root} = harness(true);
  const node = root();
  page.mount(node);
  requests[0].resolve(catalog('reaction', 'reaction entry'));
  await flush();
  node.click('[data-semantic]', {semantic: 'reindex'});
  assert.equal(requests[1].method, 'POST');
  node.click('[data-semantic-kind]', {semanticKind: 'slang'});
  requests[2].resolve(catalog('slang', 'current slang'));
  await flush();
  requests[1].resolve({state: 'scheduled'});
  await flush();
  assert.equal(requests.length, 3);
  assert.match(node.innerHTML, /current slang/);
  assert.doesNotMatch(node.innerHTML, /索引重建已安排/);
});

test('initial read failure offers a retry that loads the catalog', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].reject(new Error('read failed'));
  await flush();
  assert.match(node.innerHTML, /read failed/);
  assert.match(node.innerHTML, /data-semantic="retry"/);
  node.click('[data-semantic]', {semantic: 'retry'});
  requests[1].resolve(catalog('reaction', 'recovered reaction'));
  await flush();
  assert.match(node.innerHTML, /recovered reaction/);
  assert.doesNotMatch(node.innerHTML, /data-semantic="retry"/);
});

/* 设置表单的桩：settings 版本号 + 可编辑的 15 项。 */
function settingsCatalog(revision = 3, overrides = {}) {
  return {
    state: 'ready', selection_ready: true, providers: {embedding: [], rerank: [], analysis: []},
    settings: {revision, enabled: true, memory_enabled: true, reactions_enabled: true,
      slang_enabled: true, slang_learning: true, slang_web_search_enabled: false,
      vision_review: true,
      embedding_provider: '', rerank_provider: '', analysis_provider: '',
      timeout_seconds: 8, batch_size: 24, learning_interval_seconds: 900,
      slang_web_search_candidates: 4, slang_web_search_results: 2, ...overrides},
    catalog: {reaction: {enabled: 1}, slang: {enabled: 1}},
    sessions: [], session_id: null, items: [], next_after: null,
  };
}

const FORM = {enabled: true, memory_enabled: true, reactions_enabled: true,
  slang_enabled: true, slang_learning: true, slang_web_search_enabled: false,
  vision_review: true,
  embedding_provider: '', rerank_provider: '', analysis_provider: '',
  timeout_seconds: 12, batch_size: 24, learning_interval_seconds: 900,
  slang_web_search_candidates: 6, slang_web_search_results: 3};

test('a revision conflict re-reads and keeps the values the user just entered', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(settingsCatalog(3));
  await flush();
  node.submit('semanticSettings', FORM);
  assert.equal(node.innerHTML.includes('草稿待核对'), false, 'no draft before submitting');
  assert.equal(requests[1].values.action, 'configure');
  assert.equal(requests[1].values.revision, 3);
  assert.equal(requests[1].values.changes.timeout_seconds, 12, 'the submitted numbers must be numbers');
  /* 联网参考的三项：开关必须是布尔，两个计数必须是数字。夹具缺字段时
     values.get() 返回 null，Number(null) 会得到 0，而后端拒绝 0。 */
  assert.equal(requests[1].values.changes.slang_web_search_enabled, false,
    'the search switch must be a boolean, never a missing key');
  assert.equal(requests[1].values.changes.slang_web_search_candidates, 6);
  assert.equal(requests[1].values.changes.slang_web_search_results, 3);
  /* 别处先改过：服务端拒绝这次 CAS。 */
  requests[1].reject(new Error('settings changed; refresh before saving'));
  await flush();
  /* 重读一次拿新版本号。 */
  assert.equal(requests[2].method, 'GET');
  /* 重读返回的是服务端旧值（timeout 8），用户填的是 12。 */
  requests[2].resolve(settingsCatalog(4));
  await flush();
  assert.match(node.innerHTML, /已被别处修改/);
  assert.match(node.innerHTML, /value="12"/, 'the user input must survive the reload');
  assert.match(node.innerHTML, /草稿待核对/);
  /* 再次提交按新版本号写入，且带的仍是用户的草稿。 */
  node.submit('semanticSettings', FORM);
  assert.equal(requests[3].values.revision, 4);
  assert.equal(requests[3].values.changes.timeout_seconds, 12);
});

test('a successful save clears the draft instead of leaving it labelled', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(settingsCatalog(3));
  await flush();
  node.submit('semanticSettings', {...FORM, timeout_seconds: 15});
  requests[1].resolve({});
  await flush();
  /* 保存成功 → reload 显示服务端值（这里仍是 8），且不再标草稿。 */
  assert.equal(requests[2].method, 'GET');
  requests[2].resolve(settingsCatalog(4, {timeout_seconds: 15}));
  await flush();
  assert.doesNotMatch(node.innerHTML, /草稿待核对/);
  assert.match(node.innerHTML, /value="15"/);
});

test('discarding a draft restores the saved values', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(settingsCatalog(3));
  await flush();
  node.submit('semanticSettings', {...FORM, timeout_seconds: 12});
  requests[1].reject(new Error('settings changed; refresh before saving'));
  await flush();
  requests[2].resolve(settingsCatalog(4));
  await flush();
  assert.match(node.innerHTML, /data-semantic="discard"/);
  node.click('[data-semantic]', {semantic: 'discard'});
  assert.doesNotMatch(node.innerHTML, /草稿待核对/);
  assert.match(node.innerHTML, /value="8"/, 'discard shows the saved value again');
});

test('a non-conflict failure does not fabricate a draft or a reload', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].resolve(settingsCatalog(3));
  await flush();
  node.submit('semanticSettings', FORM);
  requests[1].reject(new Error('unsupported reaction delivery setting'));
  await flush();
  assert.equal(requests.length, 2, 'a plain failure must not trigger a re-read');
  assert.match(node.innerHTML, /unsupported reaction delivery setting/);
  assert.doesNotMatch(node.innerHTML, /草稿待核对/);
});

test('a machine code is translated instead of shown raw', async () => {
  /* 后端把机器码放在信封的 message 上（页面桥只转发 message），共享的
     CompanionProduct.labels 表不含这里用到的多数码。裸码不该出现在页面上。 */
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].reject(new Error('staging_not_initialized'));
  await flush();
  assert.doesNotMatch(node.innerHTML, /staging_not_initialized/);
  assert.match(node.innerHTML, /账号与会话/);
});

test('an uninitialized host points at host management instead of offering a pointless retry', async () => {
  /* 运行实例没加载时重试仍是同样结果，所以只给去宿主管家的入口。 */
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].reject(new Error('staging_not_initialized'));
  await flush();
  assert.match(node.innerHTML, /data-go="manage" data-manage="host"/);
  assert.doesNotMatch(node.innerHTML, /data-semantic="retry"/);

  requests[1] = null;
  const other = root();
  page.mount(other);
  requests[2].reject(new Error('read failed'));
  await flush();
  assert.match(other.innerHTML, /data-semantic="retry"/);
  assert.doesNotMatch(other.innerHTML, /data-manage="host"/);
});

test('a loaded but unstarted host explains the state and links to host management', async () => {
  const {page, requests, root} = harness();
  const node = root();
  page.mount(node);
  requests[0].reject(Object.assign(new Error('unavailable'), {code: 'supervisor_fenced'}));
  await flush();
  assert.match(node.innerHTML, /后台尚未运行或已被替换/);
  assert.match(node.innerHTML, /data-go="manage" data-manage="host"/);
  assert.doesNotMatch(node.innerHTML, /读取失败|data-semantic="retry"/);
});
