const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const PAGE = '../pages/陪伴小屋/';
const workbench = fs.readFileSync(path.resolve(__dirname, PAGE + 'workbench-page.js'), 'utf8');
const adapter = fs.readFileSync(path.resolve(__dirname, PAGE + 'reply-page.js'), 'utf8');
const appPage = fs.readFileSync(path.resolve(__dirname, PAGE + 'app.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
const drains = async (times = 8) => { for (let index = 0; index < times; index += 1) await flush(); };
const TOKEN = 'a'.repeat(64);
const PREFIX = '/astrbot_plugin_private_companion_v2/';
const plain = value => JSON.parse(JSON.stringify(value));

/* The registered group is window-scoped; these are the fields the page edits. */
const DEFAULTS = {
  enabled: false, llm_controlled: true, rules_enabled: false, rule_mode: 'words',
  split_words: '["。","？","！","~","…","“","\\n"]', match_width_variants: true,
  rule_regex: '.*?[。？！~…\\n]+|.+$',
  threshold: 120, min_segment_chars: 12, max_segments: 4, prompt: '', streaming: false,
  part_gap_mode: 'fixed', part_gap_ms: 0, part_gap_min_ms: 1500, part_gap_max_ms: 3500,
  part_gap_log_base: 1.8, image_position: 'after_text', voice_enabled: false,
  group_wakeup_enabled: true, group_wakeup_direct_words: '[]',
  group_wakeup_context_words: '["机器人", "bot"]', group_wakeup_interest_keywords: '[]',
  group_wakeup_question_enabled: true, group_wakeup_bot_name: '',
  group_wakeup_primary_member_ids: '[]', group_wakeup_owner_direct_words: '[]',
  group_wakeup_interest_probability: 0.18, group_wakeup_question_threshold: 65,
  group_wakeup_cold_group_enabled: false, group_wakeup_cold_group_threshold: 65,
  group_wakeup_cold_group_idle_minutes: 25, group_wakeup_cooldown_seconds: 90,
  group_wakeup_fatigue_limit: 5, group_wakeup_fatigue_decay_minutes: 90,
  group_wakeup_bot_name_enabled: true, group_wakeup_generated_keyword_limit: 24,
  group_wakeup_topic_interest_max_boost: 45, group_wakeup_debounce_pending_penalty: 65,
  group_wakeup_image_enabled: false, group_wakeup_image_weight: 0.2,
  group_wakeup_short_text_wait_ms: 15000, group_wakeup_log_limit: 80,
  group_air_guard_enabled: true, group_air_guard_window_seconds: 180,
  group_air_guard_max_bot_replies: 3, group_air_guard_polite_loop_limit: 2,
  enable_group_injection_guard: true, enable_group_privacy_guard: true,
  enable_group_reality_promise_guard: true, enable_context_image_captioning: false,
  context_image_caption_max_items: 2,
  style_prompt: '', content_cleanup_enabled: false, content_cleanup_mode: 'words',
  content_cleanup_scope: 'all', content_cleanup_rule: '[\\n]', content_cleanup_words: '["\\n"]',
  content_replacement_enabled: false, content_replacements: '[]', framework_error_guard_enabled: true,
  enable_forbidden_word_recall: false, recall_forbidden_words: '[]', recall_forbidden_scope: 'bot_and_group',
  recall_forbidden_word_case_sensitive: false, component_order: '[]', reply_quote_enabled: false,
  reply_quote_group_enabled: true, reply_quote_first_part_only: true, reply_quote_skip_chars: 0,
  reply_mention_speaker_enabled: false,
  voice_trigger_mode: 'always', voice_generation_mode: 'plain', voice_segment_mode: 'each',
  voice_delivery_mode: 'voice_and_text', voice_position: 'after_media', voice_language: 'zh',
  voice_foreign_text_mode: 'original', voice_probability: 1, voice_cooldown_seconds: 0,
  voice_max_speech_chars: 1800, voice_timeout_seconds: 30, voice_trigger_keywords: '',
  voice_provider_id: '', voice_zh_provider_id: '', voice_ja_provider_id: '',
  voice_en_provider_id: '', voice_extra_prompt: '', style_prompt: '',
  enable_humanized_expression: false, humanized_expression_prompt: '',
};
const LIMITS = {
  threshold: [1, 65536], min_segment_chars: [1, 65536], max_segments: [1, 64],
  part_gap_ms: [0, 60000], part_gap_min_ms: [100, 60000], part_gap_max_ms: [100, 60000],
  part_gap_log_base: [1.1, 5], voice_cooldown_seconds: [0, 86400], voice_max_speech_chars: [1, 10000],
  voice_timeout_seconds: [1, 120], group_wakeup_question_threshold: [0, 100],
  group_wakeup_cold_group_threshold: [0, 100], group_wakeup_cold_group_idle_minutes: [3, 720],
  group_wakeup_cooldown_seconds: [0, 3600], group_wakeup_fatigue_limit: [1, 20],
  group_wakeup_fatigue_decay_minutes: [5, 720], group_wakeup_generated_keyword_limit: [4, 80],
  group_wakeup_topic_interest_max_boost: [0, 150], group_wakeup_debounce_pending_penalty: [0, 100],
  group_wakeup_short_text_wait_ms: [0, 30000], group_wakeup_log_limit: [10, 300],
  group_air_guard_window_seconds: [30, 1800], group_air_guard_max_bot_replies: [1, 20],
  group_air_guard_polite_loop_limit: [1, 10], context_image_caption_max_items: [0, 8],
};
const FIELDS = Object.fromEntries(Object.entries(DEFAULTS).map(([name, value]) => {
  const kind = name === 'part_gap_log_base' ? 'weight'
    : ['voice_probability', 'group_wakeup_interest_probability', 'group_wakeup_image_weight'].includes(name)
    ? 'probability'
    : typeof value === 'boolean' ? 'boolean' : typeof value === 'string' ? 'text' : 'integer';
  const entry = {kind, default: value, apply_mode: 'immediate',
    editable_layers: ['installation', 'role', 'window']};
  if (LIMITS[name]) [entry.minimum, entry.maximum] = LIMITS[name];
  if (kind === 'probability') Object.assign(entry, {minimum: 0, maximum: 1, decimal_places: 2});
  if (kind === 'weight') entry.decimal_places = 1;
  return [name, entry];
}));

/* This section answers flat (no `sections` wrapper) because it lives on the
   reply route family rather than the config route. */
function status(changes = {}, token = TOKEN) {
  const settings = {...DEFAULTS, ...changes};
  return {
    settings, edit_token: token, revision: 1, configuration_token: 'configuration',
    apply_mode: 'next_sealed_reply', group_id: 'conversation.presentation', scope: 'window',
    layers: ['installation', 'role', 'window'],
    provenance: Object.fromEntries(Object.keys(settings).map(name =>
      [name, {layer: 'window', explicit: true, revision: 1}])),
    fields: FIELDS, recent: [], participation_recent: [], participation_limit: 80,
    tts: {state: 'ready', providers: [{id: 'tts-a'}, {id: 'tts-b'}]},
  };
}

const PREVIEW = {mode: 'offline_preview', parts: ['example'], count: 1, characters: 7,
  minimum_spacing_ms: 0, planned_spacing_ms: 0, part_spacing_ms: [], image_position: 'after_text', instruction: '',
  components: [{speech: '', success_order: ['text'], fallback_order: ['text']}],
  voice: {enabled: false, instruction: ''}};

function harness() {
  const requests = [], store = new Map(), listeners = {}, inner = {}, slots = {};
  const sectionIds = ['segment', 'style', 'cleanup', 'wakeup', 'wakeup_timing', 'group_safety',
    'context_image', 'voice', 'components', 'checks', 'timing'];
  const sectionTabs = sectionIds.map(id => {
    const tab = {dataset: {wbSection: id}, focus() {}, click() {
      listeners['settings:click']?.({target: {closest: selector => selector === '[data-wb-section]' ? tab : null}});
    }};
    return tab;
  });
  const make = name => {
    const node = {
      dataset: {}, isConnected: true, textContent: '',
      classList: {add() {}, remove() {}, contains: () => false},
      querySelectorAll: selector => selector === '[data-wb-section]' ? sectionTabs : [], querySelector: () => null,
      scrollIntoView() {},
      addEventListener: (type, handler) => {listeners[name + ':' + type] = handler;},
      removeEventListener: (type, handler) => {
        if (listeners[name + ':' + type] === handler) delete listeners[name + ':' + type];
      },
    };
    Object.defineProperty(node, 'innerHTML', {
      get: () => inner[name] || '',
      set: value => { inner[name] = value; syncSlots(value); },
    });
    return node;
  };
  /* Holders are created by the adapter's innerHTML, and the preview/diagnostics
     sections resolve through root.querySelector('[data-reply-part="..."]'). */
  const syncSlots = () => {
    for (const part of ['settings', 'preview', 'diagnostics']) {
      if (!slots[part]) slots[part] = make(part);
    }
    slots.preview.querySelector = selector => {
      if (selector === '#reply-preview-result') return slots['preview-result'] || (slots['preview-result'] = make('preview-result'));
      return null;
    };
  };
  const root = make('root');
  root.querySelectorAll = selector => selector === '[data-wb-section]' ? sectionTabs : [];
  root.querySelector = selector => {
    const match = /^\[data-reply-part="(.+)"\]$/.exec(selector);
    if (match) return slots[match[1]] || null;
    if (selector === '#reply-preview-result') return slots['preview-result'] || null;
    return null;
  };
  const sessionStorage = {getItem: key => store.get(key) || null,
    setItem: (key, value) => store.set(key, value), removeItem: key => store.delete(key)};
  const window = {
    CompanionProduct: {
      hosted: () => true, role: () => ({reply_api: PREFIX + 'group/reply'}),
      identity: () => ({installation_id: 'inst', operator_id: 'admin'}),
      /* 页面取桥先问 bridgeNow()，没有再 await bridgeFor()。 */
      bridgeNow: () => window.AstrBotPluginPage,
      bridgeFor: () => ({then: resolve => resolve(window.AstrBotPluginPage)}),
    },
    AstrBotPluginPage: {
      apiGet: (route, body) => new Promise((resolve, reject) =>
        requests.push({method: 'GET', route, body, resolve, reject})),
      apiPost: (route, body) => new Promise((resolve, reject) =>
        requests.push({method: 'POST', route, body, resolve, reject})),
    },
  };
  const sandbox = {window, sessionStorage, crypto: {randomUUID: () => 'save-key'},
    setTimeout, clearTimeout, URLSearchParams, Math, Number, Object, JSON, Array, String};
  vm.runInNewContext(workbench, sandbox);
  vm.runInNewContext(adapter, sandbox);
  return {page: window.CompanionReplyPage, workbench: window.CompanionWorkbench,
    root, slots, requests, store, listeners, get previewHtml() { return inner.preview || ''; }};
}

async function loaded(harnessed, view = 'expression') {
  harnessed.page.mount(harnessed.root, {view});
  await drains();
  assert.equal(harnessed.requests.length, 1, 'mounting reads the settings exactly once');
  harnessed.requests[0].resolve(status());
  await drains();
  return harnessed;
}

const live = harnessed => harnessed.page.state.instance;

test('the settings section reads and saves through the reply route family', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  assert.equal(harnessed.requests[0].route, 'group/reply');
  const instance = live(harnessed);
  instance.state.draft.max_segments = 6;
  const saving = instance.save(false);
  await drains();
  assert.equal(harnessed.requests[1].route, 'group/reply/configure');
  assert.deepEqual(plain(harnessed.requests[1].body), {
    operation_key: 'save-key', edit_token: TOKEN, changes: {max_segments: 6},
  });
  harnessed.requests[1].resolve({result: {operation_id: 'op', replayed: false},
    status: status({max_segments: 6}, 'b'.repeat(64))});
  await saving;
  await drains();
  assert.equal(instance.state.base.max_segments, 6);
  assert.equal(harnessed.store.size, 0);
});

test('the card is split into labelled groups but keeps one save', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  const instance = live(harnessed);
  /* vm 上下文里的数组与宿主 realm 不同，比较前先过 plain()。 */
  const ids = plain(instance.state.container.groups.map(group => group.id));
  assert.deepEqual(ids, ['segment', 'style', 'cleanup', 'voice', 'components', 'checks', 'timing']);
  assert.ok(plain(instance.state.container.groups[3].fields).includes('voice_provider_id'));
  assert.ok(!ids.includes('wakeup') && !ids.includes('wakeup_timing') && !ids.includes('group_safety'));
  assert.deepEqual(Object.keys(plain(instance.state.container.fields.rule_mode.choices)),
    ['words', 'regex', 'sentences', 'paragraphs']);
  assert.equal(instance.state.draft.rule_mode, 'words');
  for (const name of ['style_prompt', 'content_cleanup_enabled', 'content_replacements',
    'component_order', 'reply_quote_enabled', 'reply_mention_speaker_enabled',
    'framework_error_guard_enabled', 'enable_forbidden_word_recall', 'part_gap_ms']) {
    assert.ok(instance.state.container.fields[name], `${name} is available in the editor`);
  }
  /* 段落只是阅读顺序：仍然只有一个 edit_token、一次保存。 */
  assert.equal(instance.state.container.fields.enabled.editable.includes('window'), true);
});

test('segmentation defaults to words and only shows controls for the active rule mode', async () => {
  const harnessed = await loaded(harness());
  const instance = live(harnessed);
  assert.equal(instance.state.draft.rule_mode, 'words');
  let html = harnessed.slots.settings.innerHTML;
  assert.match(html, /词列表（默认）/);
  assert.match(html, /data-wb-row="split_words" hidden/);
  assert.match(html, /data-wb-row="rule_regex" hidden/);
  assert.doesNotMatch(html, /<textarea data-wb-field="split_words"/);

  const enabled = {dataset: {wbField: 'rules_enabled'}, tagName: 'INPUT', checked: true,
    closest: () => null};
  harnessed.listeners['settings:input']({target: enabled});
  html = harnessed.slots.settings.innerHTML;
  assert.match(html, /data-wb-word-list="split_words"/);
  assert.match(html, /data-wb-row="rule_regex" hidden/);

  const regex = {dataset: {wbField: 'rule_mode'}, tagName: 'INPUT', value: 'regex',
    closest: () => null};
  harnessed.listeners['settings:input']({target: regex});
  html = harnessed.slots.settings.innerHTML;
  assert.match(html, /data-wb-row="split_words" hidden/);
  assert.doesNotMatch(html, /data-wb-row="rule_regex" hidden/);
});

test('word-list chips add and remove entries while saving the existing wire format', async () => {
  const harnessed = await loaded(harness());
  const instance = live(harnessed);
  for (const name of ['split_words', 'content_cleanup_words', 'recall_forbidden_words',
    ]) {
    assert.equal(instance.state.container.fields[name].input, 'word-list', name + ' uses the list editor');
    assert.doesNotMatch(instance.state.container.fields[name].help, /JSON/i);
  }
  const decision = await loaded(harness(), 'decision');
  for (const name of ['group_wakeup_direct_words', 'group_wakeup_context_words',
    'group_wakeup_interest_keywords', 'group_wakeup_primary_member_ids', 'group_wakeup_owner_direct_words']) {
    assert.equal(live(decision).state.container.fields[name].input, 'word-list', name + ' uses the list editor');
  }
  const enabled = {dataset: {wbField: 'rules_enabled'}, tagName: 'INPUT', checked: true,
    closest: () => null};
  harnessed.listeners['settings:input']({target: enabled});

  const original = JSON.parse(instance.state.draft.split_words);
  const input = {value: '♪', dataset: {wbWordInput: 'split_words'}, focus() {}};
  const addButton = {dataset: {wbWordAdd: 'split_words'},
    closest: selector => selector === '.wb-field' ? {querySelector: () => input} : null};
  const addTarget = {closest: selector => selector === '[data-wb-word-add]' ? addButton : null};
  harnessed.listeners['settings:click']({target: addTarget});
  assert.deepEqual(plain(JSON.parse(instance.state.draft.split_words)), [...original, '♪']);

  const saving = instance.save(false);
  await drains();
  assert.equal(harnessed.requests[1].body.changes.split_words, JSON.stringify([...original, '♪']));
  harnessed.requests[1].resolve({result: {operation_id: 'op', replayed: false},
    status: status({rules_enabled: true, split_words: JSON.stringify([...original, '♪'])}, 'd'.repeat(64))});
  await saving;
  await drains();

  const removeButton = {dataset: {wbWordRemove: 'split_words', wbWordIndex: String(original.length)}};
  const removeTarget = {closest: selector => selector === '[data-wb-word-remove]' ? removeButton : null};
  harnessed.listeners['settings:click']({target: removeTarget});
  assert.deepEqual(plain(JSON.parse(instance.state.draft.split_words)), original);
});

test('replacement pairs and component order are edited without JSON controls', async () => {
  const harnessed = await loaded(harness());
  const instance = live(harnessed);
  const settings = harnessed.slots.settings;
  const from = {value: '旧称', focus() {}};
  const to = {value: '新称', focus() {}};
  const form = {querySelector: selector => selector === '[data-wb-replacement-from]' ? from
    : selector === '[data-wb-replacement-to]' ? to : null};
  settings.querySelector = selector => selector === '[data-wb-replacement-form="content_replacements"]'
    ? form : null;

  assert.equal(instance.state.container.fields.content_replacements.input, 'replacement-list');
  assert.equal(instance.state.container.fields.component_order.input, 'order-list');
  assert.match(settings.innerHTML, /data-wb-replacement-form="content_replacements"/);
  assert.match(settings.innerHTML, /data-wb-order-start="component_order"/);
  assert.doesNotMatch(settings.innerHTML, /<textarea data-wb-field="content_replacements"/);
  assert.match(instance.state.container.fields.content_replacements.help, /逐项填写原词和替换文本/);

  const addPair = {dataset: {wbReplacementAdd: 'content_replacements'}};
  harnessed.listeners['settings:click']({target: {closest: selector =>
    selector === '[data-wb-replacement-add]' ? addPair : null}});
  assert.deepEqual(plain(JSON.parse(instance.state.draft.content_replacements)), [{from: '旧称', to: '新称'}]);
  assert.match(settings.innerHTML, /旧称/);
  assert.match(settings.innerHTML, /新称/);

  const startOrder = {dataset: {wbOrderStart: 'component_order'}};
  harnessed.listeners['settings:click']({target: {closest: selector =>
    selector === '[data-wb-order-start]' ? startOrder : null}});
  const originalOrder = ['voice', 'at', 'text', 'face', 'image'];
  assert.deepEqual(plain(JSON.parse(instance.state.draft.component_order)), originalOrder);
  const moveUp = {dataset: {wbOrderMove: 'up', wbOrderIndex: '2'}};
  harnessed.listeners['settings:click']({target: {closest: selector =>
    selector === '[data-wb-order-move]' ? moveUp : null}});
  assert.deepEqual(plain(JSON.parse(instance.state.draft.component_order)),
    ['voice', 'text', 'at', 'face', 'image']);
  const natural = {dataset: {wbOrderNatural: 'component_order'}};
  harnessed.listeners['settings:click']({target: {closest: selector =>
    selector === '[data-wb-order-natural]' ? natural : null}});
  assert.deepEqual(plain(JSON.parse(instance.state.draft.component_order)), []);
});

test('reply expression, perception, and decision settings partition every field exactly once', async () => {
  const harnessed = await loaded(harness());
  const expression = plain(live(harnessed).state.container.groups.flatMap(group => group.fields));
  harnessed.page.mount(harnessed.root, {view: 'decision'});
  await drains();
  harnessed.requests[1].resolve(status());
  await drains();
  const decision = plain(live(harnessed).state.container.groups.flatMap(group => group.fields));
  assert.deepEqual(plain(live(harnessed).state.container.groups.map(group => group.id)),
    ['wakeup', 'wakeup_timing', 'group_safety']);
  harnessed.page.mount(harnessed.root, {view: 'perception'});
  await drains();
  harnessed.requests[2].resolve(status());
  await drains();
  const perception = plain(live(harnessed).state.container.groups.flatMap(group => group.fields));
  const exposed = [...expression, ...perception, ...decision];
  assert.equal(Object.keys(DEFAULTS).length, 90);
  assert.equal(exposed.length, new Set(exposed).size, 'a setting must not be duplicated across modules');
  assert.deepEqual([...exposed].sort(), Object.keys(DEFAULTS).sort());
  assert.deepEqual(plain(live(harnessed).state.container.groups.map(group => group.id)),
    ['context_image']);
  assert.deepEqual(perception, ['enable_context_image_captioning', 'context_image_caption_max_items']);
  assert.equal(harnessed.page.selectSection('segment'), false);
  assert.equal(harnessed.page.selectSection('context_image'), true);
  harnessed.page.unmount();
});

test('decision view edits the same reply route and omits expression-only tools', async () => {
  const harnessed = await loaded(harness(), 'decision');
  assert.equal(harnessed.requests[0].route, 'group/reply');
  assert.match(harnessed.root.innerHTML, /data-reply-part="settings"/);
  assert.doesNotMatch(harnessed.root.innerHTML, /data-reply-part="preview"|data-reply-part="diagnostics"/);
  assert.equal(harnessed.page.selectSection('voice'), false);
  const instance = live(harnessed);
  instance.state.draft.group_wakeup_enabled = false;
  const saving = instance.save(false);
  await drains();
  assert.equal(harnessed.requests[1].route, 'group/reply/configure');
  assert.deepEqual(plain(harnessed.requests[1].body.changes), {group_wakeup_enabled: false});
  harnessed.requests[1].resolve({result: {operation_id: 'decision-save', replayed: false},
    status: status({group_wakeup_enabled: false}, 'e'.repeat(64))});
  await saving;
  await drains();
  harnessed.page.unmount();
});

test('the expression page can open its reply modules but leaves image understanding to perception', async () => {
  const harnessed = await loaded(harness());
  assert.equal(harnessed.page.selectSection('voice'), true);
  assert.equal(live(harnessed).state.activeGroupId, 'voice');
  assert.equal(harnessed.page.selectSection('context_image'), false);
  assert.equal(harnessed.page.selectSection('components'), true);
  assert.equal(live(harnessed).state.activeGroupId, 'components');
  assert.equal(harnessed.page.selectSection('unknown'), false);
});

test('the perception view edits image understanding without reply preview or diagnostics', async () => {
  const harnessed = await loaded(harness(), 'perception');
  assert.equal(harnessed.requests[0].route, 'group/reply');
  assert.match(harnessed.root.innerHTML, /data-reply-part="settings"/);
  assert.doesNotMatch(harnessed.root.innerHTML, /data-reply-part="preview"|data-reply-part="diagnostics"/);
  const instance = live(harnessed);
  assert.deepEqual(plain(instance.state.container.order),
    ['enable_context_image_captioning', 'context_image_caption_max_items']);
  assert.equal(harnessed.page.selectSection('context_image'), true);
  harnessed.page.unmount();
});

test('expression D1-D6 links reach current settings owners', () => {
  for (const id of ['expression-text', 'expression-voice', 'expression-reaction',
    'expression-platform', 'expression-timing', 'expression-group']) assert.ok(appPage.includes(id), `missing ${id}`);
  for (const id of ['voice', 'components', 'checks', 'timing']) {
    assert.ok(appPage.includes(`data-reply-section="${id}"`) || appPage.includes(`'${id}'`), `missing reply route ${id}`);
  }
  assert.ok(appPage.includes('data-expression-life-tab="${tab}"'));
  assert.ok(appPage.includes("navigate('life',el.dataset.expressionLifeTab)"));
  assert.ok(appPage.includes("settingsJump('主动语音与戳一戳','contact')"));
});

test('the TTS provider catalog comes from the read result, not a page-local list', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  const item = live(harnessed).state.container.fields.voice_provider_id;
  const entries = item.catalog();
  assert.equal(entries[''], '跟随 AstrBot');
  assert.deepEqual(Object.keys(entries).filter(Boolean).sort(), ['tts-a', 'tts-b']);
  const zh = live(harnessed).state.container.fields.voice_zh_provider_id.catalog();
  assert.equal(zh[''], '使用通用扩展');
});

test('offline preview submits the current draft and renders the result', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  const instance = live(harnessed);
  instance.state.draft.max_segments = 3;
  harnessed.listeners['root:click']({target: {closest: () => ({dataset: {replyAction: 'preview'}})}});
  await drains();
  const request = harnessed.requests[1];
  /* 预览按 app 相对路径发（桥接也接受），设置卡则用完整地址。 */
  assert.equal(request.route, 'group/reply/preview');
  assert.equal(request.body.settings.max_segments, 3, 'preview must use the draft, not the saved values');
  assert.equal(request.body.image_count, 0);
  request.resolve(PREVIEW);
  await drains();
  assert.match(harnessed.previewHtml, /离线预览/);
});

/* 页面桥只转发信封的 message，机器码到前端时没有 code 字段；这类只带码的
   失败必须翻成中文，不能把 staging_not_initialized 这种裸码摆到界面上。 */
test('a machine code delivered only in message is translated on load', async () => {
  const harnessed = harness();
  harnessed.page.mount(harnessed.root);
  await drains();
  harnessed.requests[0].reject(new Error('staging_not_initialized'));
  await drains();
  const html = harnessed.slots.settings.innerHTML;
  assert.match(html, /请先在账号与会话中加载 V2 运行实例/);
  assert.doesNotMatch(html, /staging_not_initialized/);
});

test('a machine code delivered only in message is translated on preview failure', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  harnessed.listeners['root:click']({target: {closest: () => ({dataset: {replyAction: 'preview'}})}});
  await drains();
  harnessed.requests[1].reject(new Error('reply_preview_invalid'));
  await drains();
  assert.equal(harnessed.page.state.notice, '请填写 1–65536 字的有效正文。');
  assert.equal(harnessed.page.state.bad, true);
  assert.doesNotMatch(String(harnessed.page.state.notice), /reply_preview_invalid/);
});

test('an unconfirmed save stays pending and the retry reuses the operation', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  const instance = live(harnessed);
  instance.state.draft.max_segments = 6;
  const saving = instance.save(false);
  await drains();
  const original = plain(harnessed.requests[1].body);
  harnessed.requests[1].reject(Object.assign(new Error('down'), {code: 'bridge_timeout'}));
  await saving;
  await drains();
  assert.equal(harnessed.store.size, 1);
  const retrying = instance.save(true);
  await drains();
  assert.deepEqual(plain(harnessed.requests[2].body), original);
  harnessed.requests[2].resolve({result: {operation_id: 'op', replayed: true},
    status: status({max_segments: 6}, 'c'.repeat(64))});
  await retrying;
  await drains();
  assert.equal(harnessed.store.size, 0);
  assert.match(instance.state.savedState, /is-replayed/);
});

test('an over-long prompt and an out-of-range value never dispatch', async () => {
  const harnessed = harness();
  await loaded(harnessed);
  const instance = live(harnessed);
  /* 提示词长度不在注册表范围里，由后端 validate 判；这里只验单字段越界。 */
  instance.state.draft.max_segments = 65;
  await instance.save(false);
  assert.equal(harnessed.requests.length, 1, 'the invalid draft must not reach the network');
  assert.equal(instance.state.bad, true);
  /* 概率字段在界面按百分比编辑，101% 要拦下。 */
  instance.state.draft.max_segments = 4;
  instance.state.draft.voice_probability = 1.5;
  await instance.save(false);
  assert.equal(harnessed.requests.length, 1);
  assert.equal(instance.state.bad, true);
});

test('the diagnostics block renders the recent batches the route returned', async () => {
  const harnessed = harness();
  harnessed.page.mount(harnessed.root);
  await drains();
  harnessed.requests[0].resolve({...status(),
    recent: [{batch_id: 'b1', created_at: '2026-09-27 10:00', state: 'complete', reason: '',
      captured: null, parts: [], calls: []}]});
  await drains();
  assert.match(harnessed.slots.diagnostics.innerHTML, /最近回复诊断/);
  assert.match(harnessed.slots.diagnostics.innerHTML, /b1/);
});

test('a route outside the plugin prefix is refused instead of half-mounting', async () => {
  const requests = [], listeners = {};
  const node = {dataset: {}, isConnected: true, textContent: '', innerHTML: '',
    classList: {add() {}, remove() {}, contains: () => false},
    querySelectorAll: () => [], querySelector: () => null,
    addEventListener: (type, handler) => {listeners[type] = handler;}, removeEventListener() {}};
  const window = {
    CompanionProduct: {hosted: () => true, role: () => ({reply_api: '/elsewhere/reply'}),
      identity: () => ({installation_id: 'inst', operator_id: 'admin'})},
    AstrBotPluginPage: {
      apiGet: route => new Promise(resolve => requests.push({method: 'GET', route, resolve})),
      apiPost: route => new Promise(resolve => requests.push({method: 'POST', route, resolve})),
    },
  };
  const sandbox = {window, sessionStorage: {getItem: () => null, setItem() {}, removeItem() {}},
    crypto: {randomUUID: () => 'k'}, setTimeout, clearTimeout, URLSearchParams,
    Math, Number, Object, JSON, Array, String};
  vm.runInNewContext(workbench, sandbox);
  vm.runInNewContext(adapter, sandbox);
  window.CompanionReplyPage.mount(node);
  await drains();
  assert.equal(requests.length, 0);
  assert.match(node.innerHTML, /没有可用的回复设置工作区/);
});
