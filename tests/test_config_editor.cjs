const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const PAGE = '../pages/陪伴小屋/';
const workbench = fs.readFileSync(path.resolve(__dirname, PAGE + 'workbench-page.js'), 'utf8');
const adapter = fs.readFileSync(path.resolve(__dirname, PAGE + 'config-editor.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
/* 每次 await 只推进一层微任务；refresh 里有多层 await，用 drains 让它走完。 */
const drains = async (times = 6) => { for (let index = 0; index < times; index += 1) await flush(); };
const TOKEN = a => a.repeat(64);
const plain = value => JSON.parse(JSON.stringify(value));
const PREFIX = '/astrbot_plugin_private_companion_v2/';

const quota = {
  private_owner_max_daily: -1, private_friend_max_daily: -1, group_max_daily: -1, proactive_max_daily: -1,
};
const review = {
  enable_group_nsfw_private_fallback: false, group_nsfw_image_review_mode: 'single',
  group_nsfw_image_review_sensitivity: 'balanced', group_nsfw_image_review_min_confidence: 0.7,
  group_nsfw_image_review_timeout_seconds: 8, group_nsfw_image_review_max_dimension: 1280,
  group_nsfw_image_review_max_images: 1, group_nsfw_image_review_failure_action: 'private',
  group_nsfw_image_review_custom_prompt: '', review_provider: '', review_dual_provider: '',
};

/* The backend also publishes the inheritance chain, per-field provenance and the
   registered field contract, so the workbench renders controls from the server's
   bounds instead of a duplicated copy that can drift from the validator. */
const QUOTA_FIELDS = Object.fromEntries(Object.keys(quota).map(name =>
  [name, {kind: 'integer', default: -1, minimum: -1, maximum: 100,
    apply_mode: 'immediate', editable_layers: ['installation', 'role']}]));
/* Enum-valued fields are TEXT in the registry, so the fixture's contract says
   `text` and the options come from the page; the two tests below check that the
   adapter actually hands those options to the kernel.
   Kinds must mirror the registry rather than the fixture value's JS type: a
   confidence is registered as PROBABILITY (a 0–1 float), not as an integer. */
const REVIEW_KINDS = {
  enable_group_nsfw_private_fallback: 'boolean', group_nsfw_image_review_mode: 'text',
  group_nsfw_image_review_sensitivity: 'text', group_nsfw_image_review_min_confidence: 'probability',
  group_nsfw_image_review_timeout_seconds: 'integer', group_nsfw_image_review_max_dimension: 'integer',
  group_nsfw_image_review_max_images: 'integer', group_nsfw_image_review_failure_action: 'text',
  group_nsfw_image_review_custom_prompt: 'text', review_provider: 'text', review_dual_provider: 'text',
};
const REVIEW_FIELDS = Object.fromEntries(Object.keys(review).map(name => {
  const kind = REVIEW_KINDS[name];
  const entry = {kind, default: review[name], apply_mode: 'immediate',
    editable_layers: ['installation', 'role', 'window']};
  if (kind === 'probability') Object.assign(entry, {minimum: 0, maximum: 1, decimal_places: 2});
  return [name, entry];
}));

function section(kind, changes = {}, token = TOKEN('a')) {
  const settings = kind === 'quota' ? {...quota, ...changes} : {...review, ...changes};
  return {
    settings, edit_token: token, revision: 1, configuration_token: 'configuration',
    group_id: kind === 'quota' ? 'conversation.media_quota' : 'conversation.image_review',
    scope: kind === 'quota' ? 'role' : 'window',
    apply_mode: kind === 'quota' ? 'next_task' : 'immediate',
    layers: kind === 'quota' ? ['installation', 'role'] : ['installation', 'role', 'window'],
    provenance: Object.fromEntries(Object.keys(settings).map(name =>
      [name, {layer: kind === 'quota' ? 'role' : 'window', explicit: true, revision: 1}])),
    fields: kind === 'quota' ? QUOTA_FIELDS : REVIEW_FIELDS,
    section: kind,
  };
}
/* 2026-09-28 新接入的四个分区。默认值、类型与边界都照真实注册表抄，
   否则夹具给出与后端不一致的合同，就测不出「页面按后端下发的范围校验」这件事。 */
const NEW_KINDS = {
  recall: {
    group: 'conversation.recall',
    settings: {transcribe_enabled: false, transcribe_max_items: 5, transcribe_text_chars: 500,
      transcribe_window_minutes: 10},
    fields: {transcribe_enabled: ['boolean'], transcribe_max_items: ['integer', 1, 20],
      transcribe_text_chars: ['integer', 80, 2000], transcribe_window_minutes: ['integer', 1, 1440]},
  },
  screen: {
    group: 'screen',
    settings: {interpretation_enabled: false, journal_material_enabled: false,
      journal_material_max_chars: 700},
    fields: {interpretation_enabled: ['boolean'], journal_material_enabled: ['boolean'],
      journal_material_max_chars: ['integer', 200, 1600]},
  },
  person: {
    group: 'person',
    settings: {acquaintance_enabled: true, acquaintance_card_chars: 1024},
    fields: {acquaintance_enabled: ['boolean'], acquaintance_card_chars: ['integer', 256, 4096]},
  },
  role_growth: {
    group: 'role.growth',
    settings: {read_enabled: false, proposals_enabled: false},
    fields: {read_enabled: ['boolean'], proposals_enabled: ['boolean']},
  },
  'role.growth.skills': {
    group: 'role.growth.skills',
    settings: {custom_skills: '[]', schedule_influence_strength: 0},
    fields: {custom_skills: ['text'], schedule_influence_strength: ['integer', 0, 3]},
    /* 双层组：窗口为默认落点，角色级可写，最后一段仍是 window。 */
    layers: ['installation', 'role', 'window'],
    scope: 'window',
  },
  knowledge: {
    group: 'knowledge',
    settings: {import_enabled: false, import_paths: '', source_ids: '', entry_limit: 500,
      entry_char_limit: 1200, source_limit: 16, candidate_char_budget: 60000, inject_enabled: true,
      inject_max_entries: 8, inject_max_chars: 6000, member_recognition_enabled: false,
      member_match_aliases: true, member_inject_limit: 6, member_clue_chars: 1200},
    fields: {import_enabled: ['boolean'], import_paths: ['text'], source_ids: ['text'],
      entry_limit: ['integer', 1, 5000], entry_char_limit: ['integer', 64, 4000],
      source_limit: ['integer', 1, 64], candidate_char_budget: ['integer', 2000, 200000],
      inject_enabled: ['boolean'], inject_max_entries: ['integer', 1, 24],
      inject_max_chars: ['integer', 500, 24000], member_recognition_enabled: ['boolean'],
      member_match_aliases: ['boolean'], member_inject_limit: ['integer', 1, 12],
      member_clue_chars: ['integer', 200, 4000]},
  },
  life: {
    group: 'role.life',
    settings: {enabled: false, diary_enabled: true, diary_time: '23:50', timezone: 'Asia/Shanghai',
      sleep_enabled: false, sleep_time: '00:30', sleep_timezone: 'Asia/Shanghai', sleep_minutes: 480,
      reading_enabled: false, derive_enabled: true,
      diary_style_prompt: '', dream_theme_candidates: '', dream_mixed_themes_enabled: false,
      dream_intimate_theme_enabled: false, dream_afterglow_mode: 'auto',
      enable_rest_reply_simulation: false, rest_reply_mode: 'probability', rest_reply_probability: 18,
      rest_reply_llm_threshold: 65, rest_reply_active_windows: '23:00-08:30,12:20-13:40',
      rest_reply_awake_grace_minutes: 30, enable_rest_backlog_reply: true,
      rest_backlog_max_messages: 4},
    fields: {enabled: ['boolean'], diary_enabled: ['boolean'], diary_time: ['text'],
      timezone: ['text'], sleep_enabled: ['boolean'], sleep_time: ['text'],
      sleep_timezone: ['text'], sleep_minutes: ['integer', 1, 1440], reading_enabled: ['boolean'],
      derive_enabled: ['boolean'],
      diary_style_prompt: ['text'], dream_theme_candidates: ['text'],
      dream_mixed_themes_enabled: ['boolean'], dream_intimate_theme_enabled: ['boolean'],
      dream_afterglow_mode: ['text'], enable_rest_reply_simulation: ['boolean'],
      rest_reply_mode: ['text'], rest_reply_probability: ['integer', 0, 100],
      rest_reply_llm_threshold: ['integer', 0, 100], rest_reply_active_windows: ['text'],
      rest_reply_awake_grace_minutes: ['integer', 0, 240],
      enable_rest_backlog_reply: ['boolean'], rest_backlog_max_messages: ['integer', 1, 32]},
  },
  library: {
    group: 'library',
    scope: 'role',
    layers: ['installation', 'role'],
    settings: {enabled: false, reviews_enabled: true, reading_excerpt_chars: 1200,
      manual_entries_enabled: true, max_entries_per_page: 64, rating_enabled: false,
      preference_influence_enabled: false, preference_min_ratings: 5, preference_max_terms: 8,
      min_interval_hours: 18, share_probability: 0.18, ask_probability: 0.16},
    fields: {enabled: ['boolean'], reviews_enabled: ['boolean'],
      reading_excerpt_chars: ['integer', 200, 8000], manual_entries_enabled: ['boolean'],
      max_entries_per_page: ['integer', 1, 200], rating_enabled: ['boolean'],
      preference_influence_enabled: ['boolean'], preference_min_ratings: ['integer', 1, 64],
      preference_max_terms: ['integer', 1, 32], min_interval_hours: ['integer', 1, 720],
      share_probability: ['fraction'], ask_probability: ['fraction']},
  },
  wardrobe: {
    group: 'wardrobe',
    scope: 'role',
    layers: ['installation', 'role'],
    settings: {enabled: false, tendency: '', prompt_enabled: false, prompt_max_items: 12,
      image_max_count: 3, image_prompt: ''},
    fields: {enabled: ['boolean'], tendency: ['text'], prompt_enabled: ['boolean'],
      prompt_max_items: ['integer', 1, 24], image_max_count: ['integer', 1, 8],
      image_prompt: ['text']},
  },
  'photo.reference': {
    group: 'photo.reference',
    scope: 'role',
    layers: ['installation', 'role'],
    settings: {enabled: false, daily_outfit_enabled: false, daily_outfit_rotation_days: 14},
    fields: {enabled: ['boolean'], daily_outfit_enabled: ['boolean'],
      daily_outfit_rotation_days: ['integer', 1, 365]},
  },
  group_participation: {
    group: 'conversation.group_participation',
    settings: {enable_group_social_context: false, enable_group_mood_detection: false,
      enable_group_roleplay_strength: false, enable_group_moments: false,
      enable_group_moment_portrait: false, enable_group_joke_guard: false,
      enable_group_persona_denoise: true, enable_group_interjection: false,
      group_interject_min_interval_minutes: 180, group_interject_max_daily: 2,
      enable_group_interjection_feedback: true, group_interject_feedback_window_seconds: 600,
      enable_group_repeat_follow: true, group_repeat_count_distinct_users_only: false,
      group_repeat_trigger_threshold: 4, group_repeat_follow_probability: 0.18,
      group_repeat_interrupt_probability: 0.1, group_repeat_interrupt_probability_step: 0.12,
      group_repeat_interrupt_text: '禁止复读', group_repeat_window_seconds: 120},
    /* 概率字段注册成 probability（0–1 的小数），与 role.growth 的整数档位不同。 */
    fields: {enable_group_social_context: ['boolean'], enable_group_mood_detection: ['boolean'],
      enable_group_roleplay_strength: ['boolean'], enable_group_moments: ['boolean'],
      enable_group_moment_portrait: ['boolean'], enable_group_joke_guard: ['boolean'],
      enable_group_persona_denoise: ['boolean'], enable_group_interjection: ['boolean'],
      group_interject_min_interval_minutes: ['integer', 0, 1440],
      group_interject_max_daily: ['integer', 0, 20],
      enable_group_interjection_feedback: ['boolean'],
      group_interject_feedback_window_seconds: ['integer', 60, 86400],
      enable_group_repeat_follow: ['boolean'], group_repeat_count_distinct_users_only: ['boolean'],
      group_repeat_trigger_threshold: ['integer', 3, 20],
      group_repeat_follow_probability: ['probability', 0, 1],
      group_repeat_interrupt_probability: ['probability', 0, 1],
      group_repeat_interrupt_probability_step: ['probability', 0, 1],
      group_repeat_interrupt_text: ['text'], group_repeat_window_seconds: ['integer', 10, 600]},
  },
};

function newSection(kind, changes = {}, token = TOKEN('a')) {
  const spec = NEW_KINDS[kind];
  const settings = {...spec.settings, ...changes};
  /* 层不是所有分区都一样：书架按角色(installation+role)保存，其余新分区按会话。
     夹具写死 window 会让页面把书架标成「当前会话」。 */
  const layers = spec.layers || ['installation', 'role', 'window'];
  const scope = spec.scope || 'window';
  const fields = Object.fromEntries(Object.entries(spec.fields).map(([name, [type, low, high]]) => {
    /* editable 覆盖某几个字段的可写层：主动联系偏好的两个关系级额度在窗口层写不进去，
       后端下发的契约里就没有窗口节点，夹具必须照抄，否则测不出层轨的锁定态。 */
    const editable = (spec.editable || {})[name] || layers;
    const entry = {kind: type, default: spec.settings[name], apply_mode: 'immediate',
      editable_layers: editable};
    if (low !== undefined) Object.assign(entry, {minimum: low, maximum: high});
    return [name, entry];
  }));
  return {
    settings, edit_token: token, revision: 1, configuration_token: 'configuration',
    group_id: spec.group, scope, apply_mode: 'immediate',
    layers,
    provenance: Object.fromEntries(Object.keys(settings).map(name =>
      [name, {layer: layers[0], explicit: true, revision: 1}])),
    fields, section: kind,
  };
}

/* The route answers with every requested section wrapped in `sections`. */
const payload = (kind, changes, token) =>
  ({sections: {[kind]: Object.hasOwn(NEW_KINDS, kind)
    ? newSection(kind, changes, token) : section(kind, changes, token)}});

function harness(kinds = ['quota', 'image_review'], views = {}) {
  const requests = [], store = new Map(), holders = {}, painted = {};
  const root = {
    isConnected: true, dataset: {}, textContent: '', classList: {add() {}},
    appendChild(node) {
      holders[node.dataset.configHost] = node;
      Object.defineProperty(node, 'innerHTML', {
        get: () => node._html || '',
        set: value => { node._html = value; painted[node.dataset.configHost] = value; },
      });
    },
    querySelector: selector => {
      const match = /^\[data-config-host="(.+)"\]$/.exec(selector);
      return match ? holders[match[1]] || null : null;
    },
  };
  const sessionStorage = {
    getItem: key => store.get(key) || null,
    setItem: (key, value) => store.set(key, value), removeItem: key => store.delete(key),
  };
  const window = {
    CompanionProduct: {
      hosted: () => true, role: () => ({reply_api: PREFIX + 'reply'}),
      identity: () => ({installation_id: 'inst', operator_id: 'admin'}),
    },
    AstrBotPluginPage: {
      apiGet: (route, body) => new Promise((resolve, reject) =>
        requests.push({method: 'GET', route, body, resolve, reject})),
      apiPost: (route, body) => new Promise((resolve, reject) =>
        requests.push({method: 'POST', route, body, resolve, reject})),
    },
  };
  /* 适配层用 document.createElement 造分区挂载点；这里只要一个带 dataset 的壳。 */
  const document = {
    createElement: () => ({
      dataset: {}, classList: {add() {}}, textContent: '',
      innerHTML: '', appendChild() {}, querySelector: () => null, querySelectorAll: () => [],
      addEventListener() {}, removeEventListener() {},
    }),
    hidden: false,
  };
  const sandbox = {window, sessionStorage, document, crypto: {randomUUID: () => 'config-key'},
    setTimeout, clearTimeout, URLSearchParams, Math, Number, Object, JSON, Array, String};
  vm.runInNewContext(workbench, sandbox);
  vm.runInNewContext(adapter, sandbox);
  const editors = window.CompanionConfigEditors.create(kinds, () => root, views);
  return {editors, root, holders, requests, store, window, painted, workbench: window.CompanionWorkbench};
}

/* Mounts the sections and answers each one's own read, in the same order app.js
   drives it: restore → paint → read. The workbench ignores a read that arrives
   while one is already in flight, so a section still issues exactly one request. */
async function loaded(harnessed, kinds = ['quota', 'image_review']) {
  harnessed.editors.restore();
  harnessed.editors.paint();
  for (const kind of Object.keys(harnessed.painted)) harnessed.painted[kind] = '';
  harnessed.editors.read();
  await drains();
  kinds.forEach((kind, index) => {
    const request = harnessed.requests[index];
    assert.equal(request.method, 'GET');
    assert.equal(request.route, 'config');
    assert.deepEqual(plain(request.body), {sections: kind});
    request.resolve(payload(kind));
  });
  await drains();
  return harnessed.editors.state.instances;
}

test('the role dossier exposes the V1 character and world detail fields in one grouped contract', () => {
  const {window} = harness(['role_profile']);
  const profile = window.CompanionConfigEditors.spec.role_profile;
  const grouped = plain(profile.sections.flatMap(section => section.fields));
  assert.equal(profile.sections.length, 8);
  assert.equal(new Set(grouped).size, grouped.length, 'each field belongs to one dossier group');
  assert.deepEqual(grouped.slice().sort(), plain(profile.order).slice().sort());
  assert.deepEqual(grouped.slice().sort(), Object.keys(profile.labels).sort());
  for (const field of ['name', 'species', 'birthday', 'age', 'gender', 'appearance_points', 'hair', 'eyes',
    'clothing', 'occupation', 'personality', 'first_person', 'reaction_patterns', 'voice_examples',
    'emotional_style', 'social_distance', 'signature_phrases', 'desire', 'hobbies', 'taboos', 'key_lore',
    'world_name', 'era', 'tone', 'rules', 'scenes', 'network', 'platform_group_chat']) {
    assert.ok(grouped.includes(field), `${field} is part of the editable role dossier`);
  }
  for (const legacy of ['identity', 'appearance', 'personality', 'motivations', 'boundaries', 'world', 'platform_names']) {
    assert.ok(grouped.includes(legacy), `${legacy} retains its earlier saved content`);
  }
  assert.deepEqual(plain(profile.choices.world_adaptation_mode),
    {auto: '自动', modern: '现代日常', fantasy: '幻想世界', sci_fi: '科幻世界', custom: '自定义', off: '关闭'});
  assert.ok(profile.sections.flatMap(section => section.fields).includes('world_adaptation'));
});

test('each section reads its own route and keeps its own edit token', async () => {
  const harnessed = harness();
  const [quotaInstance, reviewInstance] = await loaded(harnessed);
  assert.equal(quotaInstance.state.status.scope, 'role');
  assert.equal(reviewInstance.state.status.scope, 'window');
  assert.equal(quotaInstance.state.status.group_id, 'conversation.media_quota');
  assert.equal(reviewInstance.state.status.group_id, 'conversation.image_review');
  assert.deepEqual(plain(quotaInstance.state.draft), quota);
  assert.deepEqual(plain(reviewInstance.state.draft), review);
});

test('the server publishes the inheritance chain and per-field provenance', async () => {
  const harnessed = harness(['quota']);
  const [instance] = await loaded(harnessed, ['quota']);
  assert.deepEqual(plain(instance.state.container.layers), ['installation', 'role']);
  assert.equal(instance.state.container.writeLayer, 'role');
  assert.equal(instance.state.status.provenance.group_max_daily.layer, 'role');
  assert.equal(instance.state.status.provenance.group_max_daily.explicit, true);
  /* Bounds come from the contract, not from a page-local copy. */
  assert.equal(instance.state.container.fields.group_max_daily.maximum, 100);
});

test('a section the route never answered is refused instead of half-applied', async () => {
  const harnessed = harness(['quota']);
  harnessed.editors.paint();
  await drains();
  /* The group id does not match the requested section: the token was never accepted. */
  harnessed.requests[0].resolve({sections: {image_review: section('image_review')}});
  await drains();
  const [instance] = harnessed.editors.state.instances;
  assert.equal(instance.state.denied, true);
  assert.equal(instance.state.draft, null);
});

/* 页面桥只转发信封的 message，机器码到前端时没有 code 字段——工作台内核必须
   从 message 里认出码并翻成中文，同时保留本来就是人话的原因句。 */
test('a machine code delivered only in message is translated on read failure', async () => {
  const harnessed = harness(['quota']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].reject(new Error('staging_not_initialized'));
  await drains();
  const [instance] = harnessed.editors.state.instances;
  assert.equal(instance.state.denied, true);
  assert.match(instance.state.notice, /请先在账号与会话中加载 V2 运行实例/);
  assert.doesNotMatch(String(instance.state.notice), /staging_not_initialized/);
  assert.doesNotMatch(harnessed.painted.quota || '', /staging_not_initialized/);
});

test('a reason sentence that is not a machine code is kept verbatim', async () => {
  const harnessed = harness(['quota']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  /* 后端有时直接给人话（例如某项能力未装配），这种原因句要原样展示。 */
  harnessed.requests[0].reject(new Error('unsupported reaction delivery settings'));
  await drains();
  const [instance] = harnessed.editors.state.instances;
  assert.match(instance.state.notice, /unsupported reaction delivery settings/);
});

test('an out-of-range draft is refused before any write is dispatched', async () => {
  const harnessed = harness(['quota']);
  const [instance] = await loaded(harnessed, ['quota']);
  instance.state.draft.proactive_max_daily = 101;
  await instance.save(false);
  assert.equal(harnessed.requests.length, 1, 'the invalid draft must not reach the network');
  assert.equal(instance.state.bad, true);
});

test('saving sends only the changed fields with the section edit token', async () => {
  const harnessed = harness(['quota']);
  const [instance] = await loaded(harnessed, ['quota']);
  instance.state.draft.group_max_daily = 5;
  const saving = instance.save(false);
  await drains();
  assert.equal(harnessed.requests.length, 2,
    JSON.stringify(harnessed.requests.map(item => [item.method, item.route])));
  assert.equal(harnessed.requests[1].route, 'config/configure');
  assert.deepEqual(plain(harnessed.requests[1].body), {
    operation_key: 'config-key', edit_token: TOKEN('a'), changes: {group_max_daily: 5},
  });
  harnessed.requests[1].resolve({result: {operation_id: 'op-1', replayed: false},
    status: payload('quota', {group_max_daily: 5}, TOKEN('b'))});
  await saving;
  await drains();
  assert.equal(instance.state.status.settings.group_max_daily, 5);
  assert.equal(instance.state.pending, null);
});

test('an enum-valued text field is edited as a select, not a free-text box', async () => {
  const harnessed = harness(['image_review']);
  const [instance] = await loaded(harnessed, ['image_review']);
  const item = instance.state.container.fields.group_nsfw_image_review_mode;
  assert.equal(item.kind, 'text');
  assert.deepEqual(plain(item.choices), {single: '单模型', dual: '双模型复核'});
  const markup = harnessed.painted.image_review;
  assert.match(markup, /<select data-wb-field="group_nsfw_image_review_mode">/);
  assert.doesNotMatch(markup, /<textarea data-wb-field="group_nsfw_image_review_mode"/);
  /* 未声明选项的文本字段仍是自由输入。 */
  assert.equal(instance.state.container.fields.group_nsfw_image_review_custom_prompt.choices, null);
});

test('a value outside the declared options is refused before any write', async () => {
  const harnessed = harness(['image_review']);
  const [instance] = await loaded(harnessed, ['image_review']);
  instance.state.draft.group_nsfw_image_review_mode = 'triple';
  await instance.save(false);
  assert.equal(harnessed.requests.length, 1, 'the invalid draft must not reach the network');
  assert.equal(instance.state.bad, true);
  /* 合法选项仍然放行。 */
  instance.state.draft.group_nsfw_image_review_mode = 'dual';
  const saving = instance.save(false);
  await drains();
  assert.equal(harnessed.requests.length, 2);
  harnessed.requests[1].resolve({result: {operation_id: 'op-3', replayed: false},
    status: payload('image_review', {group_nsfw_image_review_mode: 'dual'}, TOKEN('b'))});
  await saving;
  await drains();
});

test('a save the server answered but refused stops being pending', async () => {
  const harnessed = harness(['image_review']);
  const [instance] = await loaded(harnessed, ['image_review']);
  instance.state.draft.group_nsfw_image_review_mode = 'dual';
  const saving = instance.save(false);
  await drains();
  /* 服务端明确回绝：这不是「未确认」，继续挂着 pending 反而会让人重复提交。 */
  harnessed.requests[1].resolve({status: 'error', data: {code: 'configuration_revision_conflict'}});
  await saving;
  await drains();
  assert.equal(instance.state.pending, null);
  assert.equal(instance.state.bad, true);
  assert.match(instance.state.notice, /配置已经更新/);
  assert.equal(harnessed.store.size, 0, 'the draft receipt must not survive a refusal');
});

test('an unconfirmed save stays pending and a replay reuses the same request', async () => {
  const harnessed = harness(['image_review']);
  const [instance] = await loaded(harnessed, ['image_review']);
  instance.state.draft.group_nsfw_image_review_mode = 'dual';
  const saving = instance.save(false);
  await drains();
  const original = plain(harnessed.requests[1].body);
  /* 结果没有回来（连接层失败）：写入可能已落库，所以保留 pending 待核对。 */
  harnessed.requests[1].reject(Object.assign(new Error('bridge down'), {code: 'bridge_timeout'}));
  await saving;
  await drains();
  assert.equal(instance.state.pending.operation_key, 'config-key');
  const retrying = instance.save(true);
  await drains();
  assert.deepEqual(plain(harnessed.requests[2].body), original,
    'review must reuse the original request instead of minting a second operation');
  harnessed.requests[2].resolve({result: {operation_id: 'op-2', replayed: true},
    status: payload('image_review', {group_nsfw_image_review_mode: 'dual'}, TOKEN('b'))});
  await drains();
  await Promise.all([saving, retrying]);
  assert.equal(instance.state.pending, null);
  assert.match(instance.state.savedState, /is-replayed/);
  assert.match(instance.state.notice, /没有重复写入/);
});

test('the endpoint falls back to the reply route family when the manifest has no config_api', () => {
  const {window} = harness();
  assert.equal(window.CompanionConfigEditors.endpointFor(window.CompanionProduct), PREFIX + 'config');
  window.CompanionProduct.role = () => ({reply_api: '/other', config_api: PREFIX + 'x/config'});
  assert.equal(window.CompanionConfigEditors.endpointFor(window.CompanionProduct), PREFIX + 'x/config');
});

/* ==== 2026-09-28 新接入的四个分区 ==== */

test('the four new sections each read their own group under the shared route family', async () => {
  const kinds = Object.keys(NEW_KINDS);
  const harnessed = harness(kinds);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  assert.equal(harnessed.requests.length, kinds.length);
  kinds.forEach((kind, index) => {
    assert.equal(harnessed.requests[index].method, 'GET');
    assert.equal(harnessed.requests[index].route, 'config');
    assert.deepEqual(plain(harnessed.requests[index].body), {sections: kind});
    harnessed.requests[index].resolve(payload(kind));
  });
  await drains();
  const instances = harnessed.editors.state.instances;
  /* 每个分区各自持 edit token；container.group 是页面侧的 kind，
     后端真正的组名在 status.group_id 上。 */
  assert.deepEqual(plain(instances.map(item => item.state.status.group_id)),
    kinds.map(kind => NEW_KINDS[kind].group));
  assert.deepEqual(plain(instances.map(item => item.state.container.group)), kinds);
  /* 层由各分区自己的契约决定，不是一律 window。 */
  assert.deepEqual(plain(instances.map(item => item.state.status.scope)),
    kinds.map(kind => NEW_KINDS[kind].scope || 'window'));
});

test('a new section saves only the changed fields with its own token', async () => {
  const harnessed = harness(['recall']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('recall'));
  await drains();
  const [instance] = harnessed.editors.state.instances;
  instance.state.draft.transcribe_enabled = true;
  const saving = instance.save(false);
  await drains();
  assert.deepEqual(plain(harnessed.requests[1].body), {
    operation_key: 'config-key', edit_token: TOKEN('a'), changes: {transcribe_enabled: true},
  });
  harnessed.requests[1].resolve({result: {operation_id: 'op', replayed: false},
    status: newSection('recall', {transcribe_enabled: true}, TOKEN('b'))});
  await saving;
  await drains();
  assert.equal(instance.state.base.transcribe_enabled, true);
});

test('a value outside the published bounds never reaches the network', async () => {
  const harnessed = harness(['screen']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('screen'));
  await drains();
  const [instance] = harnessed.editors.state.instances;
  /* 注册表写的是 200–1600；越界必须就地拦下。 */
  instance.state.draft.journal_material_max_chars = 5000;
  await instance.save(false);
  assert.equal(harnessed.requests.length, 1, 'the out-of-range draft must not be dispatched');
  assert.equal(instance.state.bad, true);
});

test('the growth skill list is edited as text because the parser is lenient', async () => {
  const harnessed = harness(['role_growth']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('role_growth'));
  await drains();
  const [instance] = harnessed.editors.state.instances;
  /* 后端 custom_skills() 同时接受 JSON 数组与逗号分隔，超限只是截断，
     所以页面不做 JSON 校验，原样提交。 */
  instance.state.draft.custom_skills = '写作, 植物学';
  const saving = instance.save(false);
  await drains();
  assert.equal(harnessed.requests[1].body.changes.custom_skills, '写作, 植物学');
  harnessed.requests[1].resolve({result: {operation_id: 'op', replayed: false},
    status: newSection('role_growth', {custom_skills: '写作, 植物学'}, TOKEN('b'))});
  await saving;
  await drains();
  assert.equal(instance.state.bad, false);
});

test('a scope refusal on a new section is translated instead of shown raw', async () => {
  const harnessed = harness(['person']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].reject(new Error('person_scope_invalid'));
  await drains();
  const [instance] = harnessed.editors.state.instances;
  assert.equal(instance.state.denied, true);
  assert.match(instance.state.notice, /熟人卡按对象生效/);
  assert.doesNotMatch(String(instance.state.notice), /person_scope_invalid/);
});

/* ==== 2026-09-28 第二批：knowledge 与 role.life ==== */

test('knowledge reads its own group and saves only the changed field', async () => {
  const harnessed = harness(['knowledge']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  assert.equal(harnessed.requests[0].route, 'config');
  assert.deepEqual(plain(harnessed.requests[0].body), {sections: 'knowledge'});
  harnessed.requests[0].resolve(payload('knowledge'));
  await drains();
  const [instance] = harnessed.editors.state.instances;
  assert.equal(instance.state.status.group_id, 'knowledge');
  assert.equal(instance.state.status.scope, 'window');
  instance.state.draft.import_enabled = true;
  const saving = instance.save(false);
  await drains();
  assert.deepEqual(plain(harnessed.requests[1].body), {
    operation_key: 'config-key', edit_token: TOKEN('a'), changes: {import_enabled: true},
  });
  harnessed.requests[1].resolve({result: {operation_id: 'op', replayed: false},
    status: newSection('knowledge', {import_enabled: true}, TOKEN('b'))});
  await saving;
  await drains();
  assert.equal(instance.state.base.import_enabled, true);
});

test('the knowledge path and source lists are edited as free text with their hint', async () => {
  const harnessed = harness(['knowledge']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('knowledge'));
  await drains();
  const [instance] = harnessed.editors.state.instances;
  const painted = harnessed.painted.knowledge;
  /* 这两项填错不会报错、只是静默不生效，所以帮助文案必须留在界面上，
     且它们不能被渲染成下拉或数字框。 */
  assert.match(painted, /相对 AstrBot 数据根解析/);
  assert.match(painted, /只接受本机确实存在的标识/);
  assert.equal(instance.state.container.fields.source_ids.kind, 'text');
  assert.equal(instance.state.container.fields.import_paths.kind, 'text');
});

test('the rest gate mode and dream afterglow are edited as selects, not free text', async () => {
  const harnessed = harness(['life']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('life'));
  await drains();
  const [instance] = harnessed.editors.state.instances;
  const painted = harnessed.painted.life;
  /* 注册表里这两项是 TEXT，取值合法性只有内核的 valid() 知道；
     漏传 choices 就会被当成任意文本放过，填错后静默回默认值。 */
  assert.match(painted, /<select[^>]*data-wb-field="rest_reply_mode"/);
  assert.match(painted, /<select[^>]*data-wb-field="dream_afterglow_mode"/);
  assert.match(painted, /value="probability"[^>]*>概率判定/);
  assert.match(painted, /value="llm"[^>]*>模型判定/);
  assert.match(painted, /value="auto"[^>]*>自动/);
  assert.match(painted, /rest_reply_active_windows[\s\S]{0,400}23:00-08:30/);
});

test('a life field outside its registered bounds never reaches the network', async () => {
  const harnessed = harness(['life']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('life'));
  await drains();
  const [instance] = harnessed.editors.state.instances;
  instance.state.draft.rest_reply_probability = 180;
  await instance.save(false);
  assert.equal(harnessed.requests.length, 1, 'the out-of-range draft must not be dispatched');
  assert.equal(instance.state.bad, true);
});

test('the knowledge cross-field rule is reported in words, not as a bare code', async () => {
  const harnessed = harness(['knowledge']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('knowledge'));
  await drains();
  const [instance] = harnessed.editors.state.instances;
  instance.state.draft.entry_char_limit = 4000;
  const saving = instance.save(false);
  await drains();
  /* 后端 KnowledgeConfigurationOwner 拒绝「单轮引用上限 < 单条字数」这个组合，
     它跨字段、各自的范围都表达不了，所以只能在保存时被后端回绝。 */
  harnessed.requests[1].resolve({status: 'error', data: {code: 'knowledge_settings_invalid'}});
  await saving;
  await drains();
  assert.match(instance.state.notice, /不能小于单条素材的字数上限/);
  assert.doesNotMatch(String(instance.state.notice), /knowledge_settings_invalid/);
});

/* 回归：整数档位字段此前拿不到枚举，渲染成数字框、且下拉读回的字符串
   判不过 valid()，导致这类字段根本存不进去（schedule_influence_strength
   就是实例）。contract() 现在对非布尔字段都保留 choices，并按下拉值归一。 */
test('an integer field with named steps keeps its choices and accepts them', () => {
  const {workbench} = harness([]);
  const definition = {kind: 'integer', default: 0, minimum: 0, maximum: 3};
  const choices = {0: '不影响', 1: '轻微参考', 2: '留出练习时间', 3: '优先安排相关活动'};
  const item = workbench.contract('schedule_influence_strength', definition, choices);
  assert.equal(item.kind, 'int');
  assert.deepEqual(plain(item.choices), choices);
  assert.equal(workbench.valid(item, 0), true);
  assert.equal(workbench.valid(item, 3), true);
  /* 越界与非整数仍然被拒。 */
  assert.equal(workbench.valid(item, 4), false);
  assert.equal(workbench.valid(item, 1.5), false);
  /* 布尔字段不接受枚举：它的控件就是开关。 */
  assert.equal(workbench.contract('x', {kind: 'boolean', default: false}, choices).choices, null);
});

/* 有依赖关系的字段靠段落分组说明条件；漏传 sections 时内核会退回单段渲染，
   分组与依赖说明被静默丢掉——看起来正常，只是少了几段。 */
test('the knowledge section groups import, injection and member clues', async () => {
  const harnessed = harness(['knowledge']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('knowledge'));
  await drains();
  const painted = harnessed.painted.knowledge;
  assert.match(painted, /data-wb-group="import"/);
  assert.match(painted, /data-wb-group="inject"/);
  assert.match(painted, /data-wb-group="members"/);
  /* 依赖说明要留在界面上，否则总闸关着时调下面几项看不出为什么没反应。 */
  assert.match(painted, /关闭导入总闸时，下面几项不起作用/);
  assert.match(painted, /关闭时下面几项不起作用/);
});

test('the life section separates routines, writing, the rest gate and the backlog', async () => {
  const harnessed = harness(['life']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('life'));
  await drains();
  const painted = harnessed.painted.life;
  assert.match(painted, /data-wb-group="routine"/);
  assert.match(painted, /data-wb-group="writing"/);
  assert.match(painted, /data-wb-group="rest"/);
  assert.match(painted, /data-wb-group="backlog"/);
  /* 例程总闸关着时，日记/睡眠/阅读的日程都不登记——这是新接入的依赖说明。 */
  assert.match(painted, /关闭总闸时，日记、睡眠与阅读的日程都不再登记/);
  assert.match(painted, /关闭总闸时，下面各项都不起作用/);
  /* 两个时刻字段用时间控件；注册表里它们是 TEXT，值仍是字符串。 */
  assert.match(painted, /<input type="time" data-wb-field="diary_time"/);
  assert.match(painted, /<input type="time" data-wb-field="sleep_time"/);
  /* 时区是单行文本，不是多行框——TEXT 且没声明 rows 时内核会画成 textarea。 */
  assert.match(painted, /<input type="text" data-wb-field="timezone"/);
  assert.match(painted, /<input type="text" data-wb-field="sleep_timezone"/);
  /* 分组不能把没提到的字段弄丢：全部 23 项都要在界面上。 */
  const container = harnessed.editors.state.instances[0].state.container;
  const rendered = plain(container.groups.flatMap(group => group.fields));
  assert.deepEqual(rendered.sort(), plain(Object.keys(NEW_KINDS.life.settings)).sort());
});

test('the life audit blocks a malformed clock or timezone before any request', async () => {
  /* 内核的 valid() 对 TEXT 只判「是不是字符串」，HH:MM 与 IANA 时区
     得靠分区的 audit 钩子兜住，否则值会走到后端才被拒。 */
  const harnessed = harness(['life']);
  const [instance] = await loaded(harnessed, ['life']);
  const posts = () => harnessed.requests.filter(request => request.method === 'POST').length;
  const before = posts();
  instance.state.draft.diary_time = '25:00';
  await instance.save(false);
  assert.equal(posts(), before, '25:00 不该发请求');
  assert.equal(instance.state.bad, true);
  assert.match(instance.state.notice, /二十四小时制/);
  instance.state.draft.diary_time = '23:50';
  instance.state.draft.timezone = 'Not/A-Zone';
  await instance.save(false);
  assert.equal(posts(), before, '无效时区不该发请求');
  assert.match(instance.state.notice, /IANA 时区/);
  /* 合法的组合应当放行。 */
  instance.state.draft.timezone = 'Asia/Tokyo';
  await instance.save(false);
  assert.equal(posts(), before + 1);
});

test('the library section separates the switches from the bounds they govern', async () => {
  const harnessed = harness(['library']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('library'));
  await drains();
  const painted = harnessed.painted.library;
  assert.match(painted, /data-wb-group="switches"/);
  assert.match(painted, /data-wb-group="limits"/);
  assert.match(painted, /data-wb-group="preference"/);
  assert.match(painted, /data-wb-group="triggers"/);
  assert.match(painted, /关闭书架后，下面各项都不起作用/);
  /* 书架按角色保存，所以标签是「安装与角色」而不是「当前会话」。 */
  assert.match(painted, /安装与角色/);
  assert.doesNotMatch(painted, /当前会话/);
  /* 间隔先于概率这条顺序必须在页面上说清，否则用户会把概率设成 1 却等不到开口。 */
  assert.match(painted, /先看最短间隔，再看概率/);
  assert.match(painted, /重启不重置/);
  /* 偏好只是参考，不是本轮要求——这句不能丢。 */
  assert.match(painted, /偏好只是参考，不是本轮要求/);
  /* 分组不能把没提到的字段弄丢：全部 12 项都要在界面上。 */
  const container = harnessed.editors.state.instances[0].state.container;
  const rendered = plain(container.groups.flatMap(group => group.fields));
  assert.deepEqual(rendered.sort(), plain(Object.keys(NEW_KINDS.library.settings)).sort());
});

test('the wardrobe section separates its switches, ceilings and the operator words', async () => {
  const harnessed = harness(['wardrobe']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('wardrobe'));
  await drains();
  const painted = harnessed.painted.wardrobe;
  assert.match(painted, /data-wb-group="switches"/);
  assert.match(painted, /data-wb-group="material"/);
  assert.match(painted, /data-wb-group="words"/);
  assert.match(painted, /关闭后既不进提示词，也不接受新的识图入库/);
  assert.match(painted, /安装与角色/);
  assert.doesNotMatch(painted, /当前会话/);
  /* 条目本体在数据表里，页面只出现开关与上限：一个字段都不能丢。 */
  const container = harnessed.editors.state.instances[0].state.container;
  const rendered = plain(container.groups.flatMap(group => group.fields));
  assert.deepEqual(rendered.sort(), plain(Object.keys(NEW_KINDS.wardrobe.settings)).sort());
});

test('the reference section keeps the daily outfit switch independent', async () => {
  const harnessed = harness(['photo.reference']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('photo.reference'));
  await drains();
  const painted = harnessed.painted['photo.reference'];
  assert.match(painted, /data-wb-group="switches"/);
  assert.match(painted, /data-wb-group="rotation"/);
  /* 同意参考图不等于同意每天出穿搭图，文案必须说清这一点。 */
  assert.match(painted, /不等于同意每天都出一张穿搭图/);
  assert.match(painted, /配置里不存文件路径/);
  assert.match(painted, /安装与角色/);
  const container = harnessed.editors.state.instances[0].state.container;
  const rendered = plain(container.groups.flatMap(group => group.fields));
  assert.deepEqual(rendered.sort(), plain(Object.keys(NEW_KINDS['photo.reference'].settings)).sort());
});

test('the skill group is its own section and says it is shared across the role', async () => {
  const harnessed = harness(['role.growth.skills']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('role.growth.skills'));
  await drains();
  const painted = harnessed.painted['role.growth.skills'];
  assert.ok(painted, 'the skills section must paint into its own host, keys: '
    + JSON.stringify(Object.keys(harnessed.painted)));
  /* 角色共享的组不能只标「当前会话」——那会让人以为设置只属于这一次对话。 */
  assert.match(painted, /角色共享/, 'scope label was: '
    + (/<span class="wb-scope">([^<]*)</.exec(painted) || [])[1]);
  /* 技能按角色共享，页面必须说清这一点，否则用户会以为它是某个会话的私有设置。
     单分段的分组标题按内核约定不渲染（单段不强加小标题），所以生效范围要靠卡片标题与说明。 */
  assert.match(painted, /<h3>技能领域<\/h3>/);
  assert.match(painted, /技能属于角色本身/);
  assert.match(painted, /会话之间共享|不随会话改变/);
  assert.match(painted, /第一次设置会把这份清单记为角色级/);
  /* 双层组会公布 role 层；标签不该退化成「当前会话」独占的说法。 */
  assert.doesNotMatch(painted, /scope_key|binding_revision|operation_id/);
  /* 两个字段都不能在分组里弄丢。 */
  const container = harnessed.editors.state.instances[0].state.container;
  const rendered = plain(container.groups.flatMap(group => group.fields));
  assert.deepEqual(rendered.sort(), plain(Object.keys(NEW_KINDS['role.growth.skills'].settings)).sort());
});

test('the permissions group no longer claims the skill fields', async () => {
  const harnessed = harness(['role_growth']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('role_growth'));
  await drains();
  const container = harnessed.editors.state.instances[0].state.container;
  const rendered = plain(container.groups.flatMap(group => group.fields));
  /* 拆组后权限组只剩两个开关；技能字段若仍在这里就是漏迁。 */
  assert.deepEqual(rendered.sort(), ['proposals_enabled', 'read_enabled']);
});

test('the wardrobe note states its bound because the registry cannot enforce one', async () => {
  const harnessed = harness(['wardrobe']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('wardrobe'));
  await drains();
  /* 文字长度由扩展在写入时拒绝；注册表只公布上限，不做长度校验，
     所以页面的职责是说清 800 字这条线，而不是假装能拦住。 */
  const painted = harnessed.painted.wardrobe;
  assert.match(painted, /最多 800 字/);
  assert.match(painted, /超长会被拒绝而不是截断/);
});

test('the group participation section splits the three independent chains', async () => {
  const harnessed = harness(['group_participation']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('group_participation'));
  await drains();
  const painted = harnessed.painted.group_participation;
  for (const id of ['atmosphere', 'denoise', 'interjection', 'repeat'])
    assert.match(painted, new RegExp(`data-wb-group="${id}"`), id);
  /* 三条链各有一层总闸，关掉后下面的数字不起作用——必须在界面上说清楚。 */
  assert.match(painted, /关闭这一项时，下面五项都不起作用/);
  assert.match(painted, /关闭总闸时下面四项不起作用/);
  assert.match(painted, /关闭总闸时下面七项都不起作用/);
  /* 分组不能把没提到的字段弄丢：全部 20 项都要在界面上。 */
  const container = harnessed.editors.state.instances[0].state.container;
  const rendered = plain(container.groups.flatMap(group => group.fields));
  assert.deepEqual(rendered.sort(), plain(Object.keys(NEW_KINDS.group_participation.settings)).sort());
});

test('group participation fields can be filtered by page without duplicating the shared contract', async () => {
  const decisionView = harness(['group_participation'], {group_participation:{
    sectionIds:['atmosphere', 'interjection', 'repeat'],
  }});
  const [decision] = await loaded(decisionView, ['group_participation']);
  const decisionFields = plain(decision.state.container.groups.flatMap(group => group.fields));
  assert.deepEqual(plain(decision.state.container.groups.map(group => group.id)),
    ['atmosphere', 'interjection', 'repeat']);
  assert.equal(decisionFields.includes('enable_group_persona_denoise'), false);

  const expressionView = harness(['group_participation'], {group_participation:{
    sectionIds:['denoise'], title:'群聊表达去噪', note:'只影响群聊回复的表达腔调。',
  }});
  const [expression] = await loaded(expressionView, ['group_participation']);
  const expressionFields = plain(expression.state.container.groups.flatMap(group => group.fields));
  assert.deepEqual(plain(expression.state.container.groups.map(group => group.id)), ['denoise']);
  assert.deepEqual(expressionFields, ['enable_group_persona_denoise']);
  assert.equal(expression.state.container.title, '群聊表达去噪');

  const exposed = [...decisionFields, ...expressionFields];
  assert.equal(exposed.length, new Set(exposed).size);
  assert.deepEqual([...exposed].sort(),
    plain(Object.keys(NEW_KINDS.group_participation.settings)).sort());
});

test('world knowledge and member clues can live on separate page views of one contract', async () => {
  const worldView = harness(['knowledge'], {knowledge:{sectionIds:['import', 'inject']}});
  const [world] = await loaded(worldView, ['knowledge']);
  const worldFields = plain(world.state.container.groups.flatMap(group => group.fields));
  assert.deepEqual(plain(world.state.container.groups.map(group => group.id)), ['import', 'inject']);
  assert.equal(worldFields.includes('member_recognition_enabled'), false);

  const clueView = harness(['knowledge'], {knowledge:{sectionIds:['members'],
    title:'群聊成员线索', note:'只在群聊输入中提供已登记的成员线索。'}});
  const [clues] = await loaded(clueView, ['knowledge']);
  const clueFields = plain(clues.state.container.groups.flatMap(group => group.fields));
  assert.deepEqual(plain(clues.state.container.groups.map(group => group.id)), ['members']);
  assert.deepEqual(clueFields, ['member_recognition_enabled', 'member_match_aliases',
    'member_inject_limit', 'member_clue_chars']);

  const exposed = [...worldFields, ...clueFields];
  assert.equal(exposed.length, new Set(exposed).size);
  assert.deepEqual([...exposed].sort(), plain(Object.keys(NEW_KINDS.knowledge.settings)).sort());
});

test('probability fields keep decimals because the registry declares a fraction', async () => {
  /* 这一组有四个 0–1 的概率字段。它们不是整数档位，也不是 TEXT，
     若被当成整数处理，0.18 会被 valid() 拒掉，跟读概率就永远存不进去。 */
  const harnessed = harness(['group_participation']);
  const [instance] = await loaded(harnessed, ['group_participation']);
  /* container.fields 是按短名索引的契约表；container.groups[].fields 存的是名字。 */
  const byName = instance.state.container.fields;
  for (const name of ['group_repeat_follow_probability', 'group_repeat_interrupt_probability',
                      'group_repeat_interrupt_probability_step']) {
    assert.equal(byName[name].kind, 'float', name);
    assert.equal(byName[name].minimum, 0, name);
    assert.equal(byName[name].maximum, 1, name);
  }
  /* 整数上限字段不受影响。 */
  assert.equal(byName.group_interject_max_daily.kind, 'int');
  assert.equal(byName.group_interject_max_daily.maximum, 20);
});

test('a group participation refusal is translated instead of shown raw', async () => {
  const harnessed = harness(['group_participation']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  /* 桥只转发信封的 message，所以机器码就是在这里出现的。 */
  harnessed.requests[0].reject({message: 'group_participation_configuration_invalid'});
  await drains();
  const markup = harnessed.painted.group_participation;
  assert.doesNotMatch(markup, /group_participation_configuration_invalid/);
  assert.match(markup, /打断语只能是一行/);
});

/* ==== 主动联系偏好（proactive.contact）：158 项、四层、22 段 ====
 *
 * 这一组此前四个触点全缺（编辑器 / SECTIONS / spec / 挂载点），158 项里 92 项
 * 在任何页面上都点不到。字段名与类型按注册表抄成独立的一份：页面与它逐项对齐
 * 才算「没有字段被丢掉」，而页面与**注册表**的对齐由
 * tools/audit_page_config_coverage.py 的 MODULES 表保证。
 *
 * 数量本身就是断言：42 boolean / 54 integer / 42 text / 17 weight / 3 probability。
 */
const CONTACT_KINDS = {
  boolean: [
    "affection.enabled", "allow_insomnia_night_message", "automatic_enabled",
    "balance_awareness_enabled", "balance_include_amount_in_message", "care.enabled", "chat.enabled",
    "creation.enabled", "date_checkin_enabled", "dedup_enabled", "dedup_last_message_enabled",
    "enable_daily_greetings", "enable_llm_proactive_persona_judge", "enable_proactive_burst", "enabled",
    "environment.enabled", "external_event_self_link_enabled", "followup.enabled", "greeting.enabled",
    "insomnia_require_sleep_state", "invitation.enabled", "life.enabled", "meal.enabled",
    "meal_checkin_enabled", "news.enabled", "news_daily_hot_read_enabled", "news_share_enabled",
    "official_weather_alert_enabled", "play.enabled", "poke_action_enabled",
    "proactive_hour_activity_enabled", "quiet_enabled", "reminder.enabled", "repair.enabled",
    "screen.enabled", "screen_glance_enabled", "screen_glance_followup_enabled",
    "screen_glance_goodnight_enabled", "voice_action_enabled", "weather_change_enabled",
    "weather_checkin_enabled", "web_exploration_enabled",
  ],
  integer: [
    "appointment_lag_minutes", "appointment_lead_minutes", "appointment_pre_silence_minutes",
    "balance_check_interval_minutes", "balance_critical_percent_threshold", "balance_critical_threshold",
    "balance_low_percent_threshold", "balance_low_threshold", "balance_message_cooldown_hours",
    "dedup_last_message_window_minutes", "dedup_min_shared_tokens", "dedup_sent_window_minutes",
    "dedup_weather_window_minutes", "event_max_age_seconds", "external_event_self_link_cooldown_hours",
    "generation_history_limit", "greeting_idle_minutes", "history_max_chars", "idle_seconds",
    "important_date_lookahead_days", "insomnia_night_daily_limit", "interval_seconds",
    "max_attempts_24h", "max_contacts_24h", "max_relationship_attempts_24h",
    "max_relationship_contacts_24h", "meal_care_followup_minutes", "news_check_interval_minutes",
    "news_hot_result_count", "official_alert_poll_minutes", "poke_action_cooldown_minutes",
    "poke_action_daily_limit", "proactive_burst_gap_max_seconds", "proactive_burst_gap_min_seconds",
    "proactive_burst_max_messages", "proactive_closing_contacts_threshold",
    "proactive_closing_grace_minutes", "proactive_intensity_body_chars",
    "proactive_persona_judge_cache_minutes", "proactive_persona_judge_daily_limit",
    "proactive_persona_judge_threshold", "proactive_share_probability", "screen_glance_cooldown_minutes",
    "screen_glance_daily_limit", "screen_glance_followup_after_minutes",
    "screen_glance_followup_cooldown_minutes", "screen_glance_goodnight_delay_minutes",
    "unanswered_pause_after", "unanswered_slowdown_start", "voice_action_cooldown_minutes",
    "voice_action_max_chars", "weather_sample_minutes", "web_exploration_min_interval_hours",
    "web_exploration_result_count",
  ],
  text: [
    "affection.pause_until", "balance_currency_label", "care.pause_until", "chat.pause_until",
    "creation.pause_until", "date_checkin_time", "dedup_policies", "environment.pause_until",
    "followup.pause_until", "greeting.pause_until", "greeting_evening_window", "greeting_morning_window",
    "greeting_noon_window", "important_dates", "insomnia_night_end", "insomnia_night_start",
    "invitation.pause_until", "life.pause_until", "meal.pause_until", "meal_dinner_time",
    "meal_lunch_time", "news.pause_until", "news_hot_sources", "news_source_kind", "news_source_uid",
    "news_source_url", "note", "official_alert_min_severity", "pause_until", "play.pause_until",
    "proactive_hour_activity_curve", "proactive_intensity_preset",
    "proactive_persona_judge_exempt_purposes", "quiet_end", "quiet_start", "quiet_timezone",
    "reminder.pause_until", "repair.pause_until", "screen.pause_until", "style_prompt",
    "weather_checkin_time", "web_exploration_interests",
  ],
  weight: [
    "affection.weight", "care.weight", "chat.weight", "creation.weight", "environment.weight",
    "external_event_self_link_weight", "followup.weight", "greeting.weight", "invitation.weight",
    "life.weight", "meal.weight", "news.weight", "play.weight", "reminder.weight", "repair.weight",
    "screen.weight", "unanswered_max_interval_multiplier",
  ],
  probability: ["dedup_min_overlap_ratio", "silence_feedback_penalty", "silence_min_confidence"],
};
/* 文本字段的默认值照注册表抄：页面审计按这些值判断时刻、窗口、曲线与清单的形状。 */
const CONTACT_DEFAULTS = {
  quiet_start: '23:00', quiet_end: '07:00', quiet_timezone: 'Asia/Shanghai',
  meal_lunch_time: '12:00', meal_dinner_time: '18:00', weather_checkin_time: '08:30',
  date_checkin_time: '09:00', insomnia_night_start: '23:00', insomnia_night_end: '06:00',
  greeting_morning_window: '07:45-10:20', greeting_noon_window: '12:05-13:35',
  greeting_evening_window: '20:10-21:20',
  important_dates: '[]', dedup_policies: 'semantic,content_fingerprint,life_event,event_revision',
  news_source_kind: 'host', news_hot_sources: 'weibo,hackernews', official_alert_min_severity: '',
  proactive_intensity_preset: 'off', balance_currency_label: '元',
  proactive_hour_activity_curve: '0.22,0.16,0.12,0.10,0.10,0.14,0.28,0.50,0.66,0.72,0.78,0.92,'
    + '1.0,0.94,0.82,0.74,0.78,0.92,1.0,0.98,0.88,0.70,0.48,0.32',
};
const CONTACT_SETTINGS = {};
const CONTACT_FIELDS = {};
for (const [kind, names] of Object.entries(CONTACT_KINDS)) {
  for (const name of names) {
    if (Object.hasOwn(CONTACT_DEFAULTS, name)) CONTACT_SETTINGS[name] = CONTACT_DEFAULTS[name];
    else if (kind === 'boolean') CONTACT_SETTINGS[name] = false;
    else if (kind === 'text') CONTACT_SETTINGS[name] = '';
    else if (kind === 'integer') CONTACT_SETTINGS[name] = 0;
    else if (kind === 'weight') CONTACT_SETTINGS[name] = 1;
    else CONTACT_SETTINGS[name] = 0.5;
    CONTACT_FIELDS[name] = [kind];
  }
}
const CONTACT_LAYERS = ['installation', 'role', 'relationship', 'window'];
const CONTACT_RELATIONSHIP_BUDGET = ['max_relationship_contacts_24h', 'max_relationship_attempts_24h'];
NEW_KINDS['proactive.contact'] = {
  group: 'proactive.contact', layers: CONTACT_LAYERS, scope: 'window',
  settings: CONTACT_SETTINGS, fields: CONTACT_FIELDS,
  /* 后端下发的契约里这两个字段没有窗口节点：按窗口写入会被所有者拒绝。 */
  editable: Object.fromEntries(CONTACT_RELATIONSHIP_BUDGET.map(name =>
    [name, CONTACT_LAYERS.filter(layer => layer !== 'window')])),
};
const CONTACT_SECTIONS = ['master', 'rhythm', 'intensity', 'relationship_budget', 'quiet', 'dedup',
  'judgement', 'bond', 'daily', 'share', 'greeting', 'meal', 'date', 'weather', 'news', 'web',
  'selflink', 'balance', 'screen', 'action', 'appointment', 'context'];

async function contactLoaded(changes = {}, token = TOKEN('a')) {
  const harnessed = harness(['proactive.contact']);
  harnessed.editors.restore();
  harnessed.editors.paint();
  harnessed.editors.read();
  await drains();
  harnessed.requests[0].resolve(payload('proactive.contact', changes, token));
  await drains();
  return harnessed;
}

/* 画出来的某一行控件：从它的行标记切到下一条行标记。 */
function fieldRow(markup, name) {
  const start = markup.indexOf(`data-wb-row="${name}"`);
  assert.notEqual(start, -1, `字段 ${name} 没有渲染出来`);
  const end = markup.indexOf('data-wb-row="', start + 10);
  return markup.slice(start, end === -1 ? markup.length : end);
}

test('the contact section renders all 158 fields exactly once', async () => {
  const harnessed = await contactLoaded();
  const painted = harnessed.painted['proactive.contact'];
  assert.ok(painted, '主动联系偏好必须画进自己的挂载点');
  const container = harnessed.editors.state.instances[0].state.container;
  const rendered = plain(container.groups.flatMap(group => group.fields));
  const expected = plain(Object.keys(CONTACT_FIELDS));
  assert.equal(rendered.length, 158, '158 项一个都不能少');
  assert.equal(new Set(rendered).size, 158, '同一个字段不能出现在两段里');
  assert.deepEqual(rendered.slice().sort(), expected.slice().sort());
  assert.deepEqual(plain(container.order).slice().sort(), expected.slice().sort());
  /* 22 段全部画出来，段落 id 是测试能定位依赖说明的锚点。 */
  for (const id of CONTACT_SECTIONS) {
    assert.match(painted, new RegExp(`data-wb-group="${id}"`), id);
  }
  /* 四层链要画全：安装 · 角色 · 关系 · 窗口；关系层是这个组独有的。 */
  assert.deepEqual(plain(container.layers), CONTACT_LAYERS);
  assert.match(painted, /<b>关系<\/b>/);
  assert.match(painted, /<b>窗口<\/b>/);
});

test('the contact card says the relationship budgets are not per-conversation', async () => {
  const harnessed = await contactLoaded();
  const painted = harnessed.painted['proactive.contact'];
  /* 四层组不能只标「角色共享」：真正管着这一段关系的是关系层。 */
  assert.match(painted, /安装 \/ 角色 \/ 关系共享 · 本会话可覆盖/);
  assert.doesNotMatch(painted, /<span class="wb-scope">当前会话/);
  assert.match(painted, /不是这一次会话/);
  assert.match(painted, /在窗口层保存会被拒绝/);
  /* 层轨上这两个字段的窗口节点是锁定态，鼠标悬停说「不适用于这一字段」；
     其余字段仍然可以在窗口层覆盖。 */
  for (const name of CONTACT_RELATIONSHIP_BUDGET) {
    assert.match(fieldRow(painted, name), /窗口层不适用于这一字段/, name);
    assert.match(fieldRow(painted, name), /is-locked/, name);
  }
  /* 其余字段在窗口层照旧可写：层轨上该节点不是锁定态。
     别去断言「窗口层可写」这句话——页面从来没输出过它（只输出
     「当前生效值来自这里」或「X 层不适用于这一字段」），那样的断言恒假。 */
  const ordinary = fieldRow(painted, 'interval_seconds');
  assert.match(ordinary, /data-layer="window"/, '普通字段应有窗口层节点');
  assert.doesNotMatch(ordinary, /is-locked/, '普通字段的窗口节点不该锁');
  assert.match(fieldRow(painted, CONTACT_RELATIONSHIP_BUDGET[0]), /is-locked/,
    '关系级额度字段的窗口节点必须锁');
  assert.match(fieldRow(painted, CONTACT_RELATIONSHIP_BUDGET[0]), /窗口层不适用于这一字段/);
  assert.match(fieldRow(painted, 'interval_seconds'), /is-editable/);
  /* 暂停的继承语义要写清楚：祖先层更晚的到期时间在本层清空后仍然生效。 */
  assert.match(painted, /祖先层更晚的到期时间仍然生效/);
  /* 内部名词不能漏到界面上。 */
  assert.doesNotMatch(painted, /scope_key|binding_revision|operation_id|provider_id/);
});

test('the contact audit blocks malformed shapes before any request', async () => {
  const harnessed = await contactLoaded();
  const [instance] = harnessed.editors.state.instances;
  const posts = () => harnessed.requests.filter(request => request.method === 'POST').length;
  const before = posts();
  const cases = [
    ['quiet_start', '25:00', /二十四小时制/],
    ['greeting_morning_window', '20:10-07:45', /必须当天内结束/],
    ['quiet_timezone', 'Not/A-Zone', /IANA 时区/],
    ['pause_until', '2026-09-28T12:00:00', /要带时区/],
    ['proactive_hour_activity_curve', '1,1,1', /写满 24 个/],
    ['dedup_policies', 'semantic,nope', /只能填允许的名字/],
    ['news_hot_sources', 'weibo,weibo', /不能重复/],
    ['proactive_persona_judge_exempt_purposes', 'nope', /只能填允许的名字/],
    ['important_dates', '{', /JSON 数组/],
    ['news_source_kind', 'bilibili', /十进制 UID/],
  ];
  for (const [name, value, expected] of cases) {
    instance.state.draft[name] = value;
    await instance.save(false);
    assert.equal(posts(), before, `${name}=${value} 不该发请求`);
    assert.equal(instance.state.bad, true, name);
    assert.match(instance.state.notice, expected, name);
    instance.state.draft[name] = instance.state.base[name];
  }
  /* 合法的组合应当放行：注册表默认值本身就必须通过审计。 */
  instance.state.draft.quiet_start = '22:30';
  await instance.save(false);
  assert.equal(posts(), before + 1);
});

test('a relationship-budget refusal is translated instead of shown raw', async () => {
  const harnessed = await contactLoaded();
  const [instance] = harnessed.editors.state.instances;
  instance.state.draft.max_relationship_contacts_24h = 12;
  const saving = instance.save(false);
  await drains();
  /* 桥只转发信封的 message，所以机器码就是在这里出现的。 */
  harnessed.requests[1].resolve({status: 'error', data: {code: 'contact_relationship_budget_scope'}});
  await saving;
  await drains();
  assert.equal(instance.state.bad, true);
  assert.match(instance.state.notice, /不能按会话保存/);
  assert.doesNotMatch(instance.state.notice, /contact_relationship_budget_scope/);
});
