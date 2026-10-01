const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.resolve(__dirname, '../pages/陪伴小屋/maintenance-page.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
const localDay = value => {
  const date = value || new Date();
  return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('-');
};
const localStamp = value => {
  const date = value || new Date();
  return `${localDay(date)}T${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`;
};
const daily = (day, values = {}) => ({
  day, calls: 0, tokens: 0, cost_microusd: 0, unconfirmed_calls: 0, failures: 0,
  unknown_calls: 0, active_calls: 0, cache_reported_calls: 0, cache_telemetry_calls: 0,
  cache_input_tokens: 0, cached_input_tokens: 0, cache_creation_tokens: 0,
  cache_other_input_tokens: 0, input_tokens: 0, output_tokens: 0,
  avg_latency_ms: null, providers: [], tasks: [], ...values,
});

function harness(responses) {
  const listeners = {};
  const requests = [];
  const csvExports = [];
  const downloads = [];
  const confirmations = [];
  let modelReads = 0;
  const bridge = {
    apiGet: async route => {
      requests.push(['GET', route]);
      if (route.endsWith('/maintenance')) return responses.maintenance;
      if (route.endsWith('/voice')) return responses.voice || {providers: []};
      if (route.endsWith('/image')) return responses.image || {actions: []};
      if (route === '/model') {
        const value = Array.isArray(responses.model)
          ? responses.model[Math.min(modelReads++, responses.model.length - 1)]
          : responses.model;
        return typeof value === 'function' ? value(modelReads++) : value || {tasks: [], providers: []};
      }
      throw new Error('unexpected GET ' + route);
    },
    apiPost: async (route, body) => {
      requests.push(['POST', route, body]);
      const value = responses.posts?.[route];
      const result = typeof value === 'function' ? value(body, requests) : value;
      return result || {};
    },
  };
  const window = {
    CompanionProduct: {
      role: () => ({model_api: '/astrbot_plugin_private_companion_v2/model', role_id: 'role-a'}),
      bridgeNow: () => bridge,
    },
    lucide: {createIcons() {}},
    confirm: message => {
      confirmations.push(message);
      return responses.confirmations?.length ? responses.confirmations.shift() : true;
    },
  };
  const root = {
    innerHTML: '',
    addEventListener(type, handler) { listeners[type] = handler; },
    removeEventListener(type) { delete listeners[type]; },
    querySelector() { return null; },
    click(selector, dataset = {}) {
      listeners.click({target: {closest: value => value === selector ? {dataset} : null}});
    },
    change(selector, value) {
      listeners.change({target: {
        value,
        matches: candidate => candidate === selector,
      }});
    },
    input(value, selector = '[data-call-search]') {
      listeners.input({target: {
        value, selectionStart: value.length, selectionEnd: value.length,
        matches: candidate => candidate === selector,
      }});
    },
  };
  window.setTimeout = callback => callback();
  window.clearTimeout = () => {};
  const document = {createElement: () => ({click() { downloads.push(this.download); }})};
  const url = {createObjectURL: blob => { csvExports.push(blob.parts.join('')); return 'blob:maintenance'; }, revokeObjectURL() {}};
  class BlobMock { constructor(parts) { this.parts = parts; } }
  vm.runInNewContext(source, {window, document, URL: url, Blob: BlobMock, Intl, Date, Number, Object, String, Math,
    Array, Set, Promise});
  return {page: window.CompanionMaintenancePage, requests, root, exports: csvExports, downloads, confirmations};
}

test('maintenance offers today, total, date drilldown, ranked detail, cache and diagnostic filters', async () => {
  const today = localDay(new Date());
  const previous = localDay(new Date(Date.now() - 86400000));
  const provider = {key: '<main>', calls: 1, tokens: 120, cost_microusd: 15, failures: 0,
    input_tokens: 100, output_tokens: 20, cache_reported_calls: 1, cache_telemetry_calls: 1,
    cache_input_tokens: 100, cached_input_tokens: 40, cache_creation_tokens: 10,
    cache_other_input_tokens: 50, avg_latency_ms: 120};
  const task = {...provider, key: 'conversation.reply'};
  const current = daily(today, {...provider, calls: 1, tokens: 120, providers: [provider], tasks: [task]});
  const prior = daily(previous, {calls: 2, tokens: 80, input_tokens: 60, output_tokens: 20, providers: [], tasks: []});
  const hour = String(new Date().getHours()).padStart(2, '0');
  const recent = Array.from({length: 12}, (_, index) => ({kind: 'conversation.reply', provider: '<main>',
    state: 'generated', tokens: 120 + index, cost_microusd: 15, input_tokens: 100, cached_input_tokens: 40,
    cache_creation_tokens: 10, output_tokens: 20, cache_hit_rate: 40, latency_ms: 120,
    at: localStamp(new Date(Date.now() - index * 60000)), failure: index === 11 ? 'provider_request_failed' : null}));
  const responses = {
    maintenance: {
      generated_at: localStamp(),
      summary: {calls: 3, tokens: 200, unconfirmed_calls: 0},
      totals: {calls: 3, tokens: 200, cost_microusd: 25, input_tokens: 160, output_tokens: 40,
        failures: 0, cache_reported_calls: 1, cache_telemetry_calls: 1, cache_input_tokens: 100,
        cached_input_tokens: 40, cache_creation_tokens: 10, cache_other_input_tokens: 50,
        providers: [provider], tasks: [task]},
      daily: [prior, current], history: [prior, current],
      windows: {
        '7d': {start_day: previous, end_day: today, totals: {calls: 3, tokens: 200, cost_microusd: 25,
          input_tokens: 160, output_tokens: 40, failures: 0, providers: [provider], tasks: [task]}, providers: [provider], tasks: [task]},
        '30d': {start_day: previous, end_day: today, totals: {calls: 3, tokens: 200, cost_microusd: 25,
          input_tokens: 160, output_tokens: 40, failures: 0, providers: [provider], tasks: [task]}, providers: [provider], tasks: [task]},
      },
      hourly: [{day: today, hour, calls: 1, tokens: 120, cost_microusd: 15}],
      by_provider: [provider], by_task: [task],
      recent,
      budget: {limit_tokens: 1000, spent_tokens: 100, held_tokens: 20, soft_limit_enabled: true, soft_limit_tokens: 500},
      providers: [{id: '<main>', model: 'model-a'}],
      runtime: {
        storage: {journal_mode: 'wal', synchronous: 2, busy_timeout_ms: 5000, foreign_keys: true, page_count: 88, freelist_count: 2, schema_version: 46},
        conversation: [{created_at: localStamp(), batch_state: 'closed', flow_state: 'blocked', flow_reason: 'provider_failure',
          input_count: 2, part_count: 2, delivered_parts: 1, failed_parts: 1, unknown_parts: 0, pending_parts: 0}],
        identity_scope: {dashboard_operator: 'verified', role_access: 'verified', token_ledger: 'current_role'},
        debounce_trace: [{at: localStamp(), batch_state: 'ready', flow_state: 'complete', reason: 'debounce',
          input_count: 2, part_count: 1, due_at: localStamp(), deadline_at: localStamp(), quiet_window_ms: 600, merge_window_ms: 2000}],
        prompt_materials: [{owner: 'memory.recall', purpose: 'conversation', state: 'included', uses: 2}],
        proactive: {calls: 3, latest_at: localStamp()},
      },
    },
    voice: {providers: [{id: 'voice-a'}]},
    image: {actions: [{action: 'image.generate', registered: true, current: true}]},
    posts: {
      '/model/test': {provider_id: '<main>', status: 'ok', latency_ms: 41},
      '/model/voice/test': {provider_id: 'voice-a', status: 'ok', latency_ms: 55},
      '/model/image/test': {action: 'image.generate', registered: true, current: true},
      '/model/test/storage': {status: 'ok', integrity: ['ok'], foreign_key_issues: 0, elapsed_ms: 9},
    },
    model: {tasks: [{kind: 'conversation.reply', capabilities: [], fields: {provider: {value: '<main>'}, fallback: {value: ''}, max_output_tokens: {value: 1024}}, application_state: 'applied'}],
      providers: [{id: '<main>', capabilities: [], max_output_tokens: 4096}]},
  };
  const {page, requests, root, exports, downloads} = harness(responses);
  page.mount(root);
  await flush();

  assert.deepEqual(requests.slice(0, 4).map(item => item[0]), ['GET', 'GET', 'GET', 'GET']);
  assert.match(root.innerHTML, /运行态势/);
  assert.match(root.innerHTML, /Token 统计管理/);
  assert.match(root.innerHTML, /120/);
  assert.match(root.innerHTML, /周期对比/);
  assert.match(root.innerHTML, /40\.0% 命中/);
  assert.match(root.innerHTML, /Provider 消耗排行/);
  assert.match(root.innerHTML, /任务消耗排行/);
  assert.match(root.innerHTML, /每日明细/);
  assert.match(root.innerHTML, /后台软限额/);
  assert.match(root.innerHTML, /统计口径/);
  assert.match(root.innerHTML, /当前角色的 V2 模型任务/);
  assert.match(root.innerHTML, /模型任务路由/);
  assert.match(root.innerHTML, /路由正常/);
  assert.match(root.innerHTML, /data-call-search/);
  assert.match(root.innerHTML, /12 \/ 12 条/);
  assert.match(root.innerHTML, /事件时间线/);
  assert.match(root.innerHTML, /诊断说明与常见问题/);
  assert.match(root.innerHTML, /TTS 合成/);
  assert.match(root.innerHTML, /原生图片工具/);
  assert.match(root.innerHTML, /服务商可能计费/);
  assert.match(root.innerHTML, /data-token-source="memory"/);
  assert.match(root.innerHTML, /Provider 余额 · 未接入/);
  assert.match(root.innerHTML, /role="img" aria-label="缓存命中、缓存写入、普通输入与输出 Token 构成"/);
  assert.match(root.innerHTML, /缓存前缀诊断/);
  assert.match(root.innerHTML, /来源同周期对照/);
  assert.match(root.innerHTML, /各账本独立统计/);
  assert.match(root.innerHTML, /回执覆盖/);
  assert.match(root.innerHTML, /上下文重置/);
  assert.match(root.innerHTML, /system prompt/);
  assert.match(root.innerHTML, /工具定义/);
  assert.match(root.innerHTML, /顺序漂移/);
  assert.match(root.innerHTML, /签名状态 · 未采集/);
  assert.match(root.innerHTML, /运行证据台/);
  assert.match(root.innerHTML, /V2 SQLite 存储/);
  assert.match(root.innerHTML, /REQ-041/);
  assert.match(root.innerHTML, /统一身份与隔离/);
  assert.match(root.innerHTML, /消息聚合与防抖追踪/);
  assert.match(root.innerHTML, /安静窗 600 ms/);
  assert.match(root.innerHTML, /memory\.recall/);
  assert.match(root.innerHTML, /<strong>3<\/strong><span>条已记录主动触达<\/span>/);
  assert.match(root.innerHTML, /1 已送达 \/ 1 失败/);
  assert.match(root.innerHTML, /&lt;main&gt;/);
  assert.doesNotMatch(root.innerHTML, /<main>/);

  root.click('[data-token-source]', {tokenSource: 'memory'});
  assert.match(root.innerHTML, /SOURCE \/ NOT CONNECTED/);
  assert.match(root.innerHTML, /记忆插件 Token/);
  assert.doesNotMatch(root.innerHTML, /class="maint-token-hero"/);
  assert.match(root.innerHTML, /当前角色数据不会替代它/);
  root.click('[data-token-source]', {tokenSource: 'companion'});
  assert.match(root.innerHTML, /class="maint-token-hero"/);

  root.click('[data-period]', {period: 'total'});
  assert.match(root.innerHTML, /aria-pressed=\"true\" class=\"is-active\">总计/);
  assert.match(root.innerHTML, /200/);
  root.click('[data-period]', {period: '7d'});
  assert.match(root.innerHTML, /aria-pressed="true" class="is-active">7 日/);
  assert.match(root.innerHTML, /近 7 日 · Token 总量/);
  root.click('[data-period]', {period: '30d'});
  assert.match(root.innerHTML, /aria-pressed="true" class="is-active">30 日/);
  root.click('[data-period]', {period: 'today'});
  root.input('provider_request_failed');
  assert.match(root.innerHTML, /1 \/ 12 条/);
  assert.match(root.innerHTML, /Provider 请求失败/);
  root.input('');
  assert.match(root.innerHTML, /12 \/ 12 条/);
  assert.equal((root.innerHTML.match(/class="maint-call-row/g) || []).length, 10);
  root.click('[data-export-tokens]');
  assert.equal((exports[0].match(/^"调用"/gm) || []).length, 12);
  assert.equal(downloads.length, 1);
  root.click('[data-select-day]', {selectDay: previous});
  assert.match(root.innerHTML, /aria-pressed=\"true\" class=\"is-active\">按日期/);
  assert.match(root.innerHTML, new RegExp('value=\"' + previous + '\"'));
  assert.match(root.innerHTML, /80/);

  root.click('[data-period]', {period: 'today'});
  root.click('[data-select-hour]', {selectHour: today + 'T' + hour, selectDay: today});
  assert.match(root.innerHTML, new RegExp('已聚焦时段：' + today + ' ' + hour + ':00'));

  root.click('[data-diagnostic-severity]', {diagnosticSeverity: 'error'});
  assert.match(root.innerHTML, /data-diagnostic-severity=\"error\" aria-pressed=\"true\"/);
  root.click('[data-diagnostic-category]', {diagnosticCategory: 'model'});
  assert.match(root.innerHTML, /模型链路工作区/);
  assert.match(root.innerHTML, /data-category="model"/);
  assert.doesNotMatch(root.innerHTML, /<article data-severity="[^"]+" data-category="delivery"/);
  assert.match(root.innerHTML, /探测通过就代表真实回复正常吗/);
  root.click('[data-diagnostic-category]', {diagnosticCategory: 'delivery'});
  assert.match(root.innerHTML, /消息收口工作区/);
  assert.match(root.innerHTML, /部分片段失败后会自动补发吗/);
  assert.match(root.innerHTML, /data-category="delivery"/);
  assert.match(root.innerHTML, /data-evidence-kind="debounce"/);
  root.click('[data-diagnostic-category]', {diagnosticCategory: 'identity'});
  assert.match(root.innerHTML, /aria-selected="true" class="is-active" title="管理身份与角色账本边界/);
  assert.match(root.innerHTML, /data-evidence-kind="identity"/);
  assert.match(root.innerHTML, /REQ-041 结果为什么只显示状态/);
  root.click('[data-diagnostic-category]', {diagnosticCategory: 'all'});
  root.click('[data-diagnostic-severity]', {diagnosticSeverity: 'all'});
  root.click('[data-rank-kind]', {rankKind: 'providers', rankKey: '<main>'});
  assert.match(root.innerHTML, /已按排行筛选：&lt;main&gt;/);

  root.click('[data-period]', {period: 'today'});
  root.click('[data-storage-test]');
  await flush();
  assert.ok(requests.some(item => item[0] === 'POST' && item[1] === '/model/test/storage'));
  assert.match(root.innerHTML, /SQLite 完整性检查通过/);
  assert.match(root.innerHTML, /完整性 ok/);
  assert.match(root.innerHTML, /外键问题 0/);
  root.click('[data-provider-probe]');
  await flush();
  assert.match(root.innerHTML, /41 ms/);
  assert.match(root.innerHTML, /Provider 可响应/);
  root.click('[data-voice-test]');
  await flush();
  assert.match(root.innerHTML, /55 ms/);
  root.click('[data-image-test]');
  await flush();
  assert.deepEqual(requests.filter(item => item[0] === 'POST').map(item => item[1]),
    ['/model/test/storage', '/model/test', '/model/voice/test', '/model/image/test']);
  assert.match(root.innerHTML, /注册检查通过/);
  page.unmount();
});

test('maintenance shows connected external token ledgers without mixing their budgets', async () => {
  const today = localDay(new Date());
  const previous = localDay(new Date(Date.now() - 86400000));
  const dimension = (key, tokens) => ({key, calls: 1, tokens, input_tokens: tokens - 10,
    output_tokens: 10, failures: 0, reported_tokens: tokens - 15, estimated_tokens: 15, avg_latency_ms: 80});
  const day = (key, tokens, reported, estimated) => ({...dimension('day', tokens), key, day: key, reported_tokens: reported, estimated_tokens: estimated,
    providers: [dimension('memory-model', tokens)], tasks: [dimension('memory.recall', tokens)]});
  const responses = {
    maintenance: {
      generated_at: new Date().toISOString(), summary: {calls: 0, tokens: 0}, totals: {calls: 0, tokens: 0},
      daily: [daily(today)], history: [], recent: [], budget: {}, providers: [],
      external_token_sources: {memory: {
        available: true, installed: true, display_name: '记忆伴侣', updated_at: new Date().toISOString(),
        totals: {calls: 2, tokens: 115, reported_tokens: 70, estimated_tokens: 45, input_tokens: 85,
          output_tokens: 30, failures: 0, cached_input_tokens: 20, cache_creation_tokens: 5, avg_latency_ms: 80},
        by_provider: [dimension('memory-model', 115)], by_task: [dimension('memory.recall', 115)],
        history: [day(previous, 40, 20, 20), day(today, 75, 50, 25)],
        daily: [day(previous, 40, 20, 20), day(today, 75, 50, 25)],
        hourly: [{key: today + 'T09', calls: 2, tokens: 115}],
        recent: [{at: today + 'T09:00:00', kind: 'memory.recall', provider: 'memory-model', state: 'generated',
          tokens: 75, input_tokens: 65, output_tokens: 10, reported_tokens: 60, estimated_tokens: 15, latency_ms: 80}],
      }},
    },
  };
  const {page, root} = harness(responses);
  page.mount(root);
  await flush();
  root.click('[data-token-source]', {tokenSource: 'memory'});
  assert.match(root.innerHTML, /记忆伴侣 独立账本/);
  assert.match(root.innerHTML, /75/);
  assert.match(root.innerHTML, /50/);
  assert.match(root.innerHTML, /25/);
  assert.match(root.innerHTML, /V2 角色预算保持独立|不计入 V2 角色预算/);
  root.click('[data-period]', {period: '7d'});
  assert.match(root.innerHTML, /115/);
  assert.match(root.innerHTML, /70/);
  assert.match(root.innerHTML, /45/);
  assert.match(root.innerHTML, /记忆伴侣 独立账本/);
  page.unmount();
});

test('maintenance distinguishes empty usage from cache receipts without computable hit rate', async () => {
  const today = localDay(new Date());
  const response = {
    generated_at: new Date().toISOString(), summary: {calls: 0, unconfirmed_calls: 0},
    totals: {calls: 0, tokens: 0, providers: [], tasks: []}, daily: [daily(today)], history: [],
    recent: [], budget: {}, providers: [],
  };
  const empty = harness({maintenance: response, voice: {providers: []}, image: {actions: []}});
  empty.page.mount(empty.root);
  await flush();
  assert.match(empty.root.innerHTML, /这个范围没有模型调用/);
  assert.match(empty.root.innerHTML, /没有已加载的 V2 文本 Provider/);
  empty.page.unmount();

  response.summary.calls = 1;
  response.daily[0] = daily(today, {calls: 1, tokens: 20, cache_telemetry_calls: 1, cache_creation_tokens: 8});
  response.history = [response.daily[0]];
  const partial = harness({maintenance: response, voice: {providers: []}, image: {actions: []}});
  partial.page.mount(partial.root);
  await flush();
  assert.match(partial.root.innerHTML, /暂无命中率|等待确认/);
  assert.match(partial.root.innerHTML, /写入量仍按 Provider 实报展示/);
  assert.match(partial.root.innerHTML, /缓存写入/);
  partial.page.unmount();
});

test('maintenance completes the V1 task prompt workspace on the V2 model contract', async () => {
  const today = localDay(new Date());
  const baseMaintenance = {
    generated_at: new Date().toISOString(),
    summary: {calls: 0, tokens: 0, unconfirmed_calls: 0},
    totals: {calls: 0, tokens: 0, providers: [], tasks: []},
    daily: [daily(today)], history: [], recent: [], budget: {}, providers: [],
  };
  const task = (kind, prompt, token, explicit = false) => ({
    kind, lane: 'foreground', capabilities: ['text'], default_prompt: prompt, prompt_version: '7', edit_token: token,
    application_state: 'applied', fields: {
      prompt: {value: explicit ? '已有自定义提示词' : prompt, inherited_value: prompt,
        source: explicit ? 'window' : 'default', inherited_source: 'default', explicit},
    },
  });
  const initial = {
    tasks: [
      task('conversation.reply', '回复规则：{{task_input}}\n{{role_instruction}}', 'a'.repeat(64)),
      task('proactive.compose', '主动联系规则：{{recent_history}}', 'b'.repeat(64), true),
      task('role.journal.diary', '日记整理规则：{{persona_context}}', 'c'.repeat(64)),
    ],
    providers: [{id: '<main>', capabilities: ['text'], max_output_tokens: 4096}],
  };
  let latest = {
    ...initial,
    tasks: initial.tasks.map(item => item.kind === 'conversation.reply'
      ? {...item, edit_token: 'd'.repeat(64), fields: {...item.fields,
        prompt: {...item.fields.prompt, value: '服务器最新完整提示词', source: 'window', explicit: true}}}
      : item),
  };
  const saved = [];
  const responses = {
    maintenance: baseMaintenance,
    model: [initial, latest],
    confirmations: [false, true],
    posts: {
      '/model/configure': body => {
        saved.push(body);
        if (saved.length === 1) {
          return {status: 'error', data: {code: 'configuration_revision_conflict'}};
        }
        const updated = latest.tasks.find(item => item.kind === body.kind);
        return {task: {...updated, edit_token: 'e'.repeat(64), fields: {...updated.fields,
          prompt: {...updated.fields.prompt, value: body.reset.length ? updated.default_prompt : body.changes.prompt,
            source: body.reset.length ? 'default' : 'window', explicit: !body.reset.length}}}};
      },
    },
  };
  const {page, requests, root, confirmations} = harness(responses);
  page.mount(root);
  await flush();

  assert.match(root.innerHTML, /完整内置任务提示词/);
  assert.match(root.innerHTML, /回复规则：\{\{task_input\}\}/);
  assert.match(root.innerHTML, /内置版本/);
  assert.match(root.innerHTML, /v7/);
  assert.match(root.innerHTML, /动态字段/);
  assert.match(root.innerHTML, /本次任务的结构化输入/);
  assert.match(root.innerHTML, /当前角色的角色指令/);

  root.input('日记', '[data-prompt-search]');
  assert.match(root.innerHTML, /data-prompt-task="role\.journal\.diary"/);
  assert.doesNotMatch(root.innerHTML, /data-prompt-task="conversation\.reply"/);
  root.input('', '[data-prompt-search]');
  root.click('[data-prompt-mode]', {promptMode: 'customized'});
  assert.match(root.innerHTML, /data-prompt-task="proactive\.compose"/);
  assert.doesNotMatch(root.innerHTML, /data-prompt-task="conversation\.reply"/);
  root.click('[data-prompt-mode]', {promptMode: 'all'});
  root.click('[data-prompt-group]', {promptGroup: '对话'});
  assert.match(root.innerHTML, /data-prompt-task="conversation\.reply"/);
  assert.doesNotMatch(root.innerHTML, /data-prompt-task="role\.journal\.diary"/);

  root.input('编辑后的完整提示词', '[data-prompt-draft]');
  assert.match(root.innerHTML, /有未保存更改/);
  root.click('[data-prompt-save]');
  await flush();
  assert.equal(saved[0].kind, 'conversation.reply');
  assert.equal(saved[0].changes.prompt, '编辑后的完整提示词');
  assert.equal(saved[0].reset.length, 0);
  assert.match(root.innerHTML, /保存时发现版本冲突/);
  assert.match(root.innerHTML, /编辑后的完整提示词/);

  root.click('[data-prompt-discard]');
  await flush();
  assert.equal(confirmations.length, 1);
  assert.match(root.innerHTML, /已保留当前草稿/);
  assert.match(root.innerHTML, /编辑后的完整提示词/);
  assert.equal(requests.filter(item => item[0] === 'GET' && item[1] === '/model').length, 2);

  root.click('[data-prompt-discard]');
  await flush();
  assert.equal(confirmations.length, 2);
  assert.match(root.innerHTML, /服务器最新完整提示词/);
  assert.doesNotMatch(root.innerHTML, /编辑后的完整提示词/);
  assert.match(root.innerHTML, /d{12}/);

  root.click('[data-prompt-reset]');
  await flush();
  assert.equal(saved[1].kind, 'conversation.reply');
  assert.equal(Object.keys(saved[1].changes).length, 0);
  assert.deepEqual(Array.from(saved[1].reset), ['prompt']);

  root.input('临时覆盖', '[data-prompt-draft]');
  root.input('   ', '[data-prompt-draft]');
  root.click('[data-prompt-save]');
  await flush();
  assert.equal(saved[2].kind, 'conversation.reply');
  assert.equal(Object.keys(saved[2].changes).length, 0);
  assert.deepEqual(Array.from(saved[2].reset), ['prompt']);
  page.unmount();
});
