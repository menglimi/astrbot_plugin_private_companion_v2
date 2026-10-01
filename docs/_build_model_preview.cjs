/* Builds a static preview of the redesigned model routing page from fixture data. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const PAGES = path.resolve(__dirname, '../pages/陪伴小屋');
const source = fs.readFileSync(path.join(PAGES, 'models-page.js'), 'utf8');
const TOKEN = 'p'.repeat(64);

function field(value, inherited, explicit = false, source = 'installation') {
  return {value, inherited_value: inherited, source: explicit ? 'window' : source, inherited_source: source, explicit};
}
const RULES = JSON.stringify([
  {id: 'code-help', keywords: ['写代码', '报错', 'debug'], match_mode: 'contains', keyword_logic: 'any', provider_id: 'secondary', model: '', priority: 10, enabled: true},
  {id: 'long-form', keywords: ['写一篇', '不少于'], match_mode: 'contains', keyword_logic: 'all', provider_id: 'primary', model: '', priority: 5, enabled: true},
  {id: 'peak-window', keywords: [], provider_id: 'secondary', model: '', priority: 0, enabled: true,
    time_window: {timezone: 'Asia/Shanghai', start: '09:00', end: '18:00', weekdays: [0, 1, 2, 3, 4, 5, 6]}},
]);

function task(kind, provider, lane, capabilities, explicit = false, prompt = '') {
  return {kind, lane, capabilities, edit_token: TOKEN, application_state: explicit ? 'next_task' : 'applied',
    fields: {provider: field(provider, 'primary', explicit), fallback: field('', ''),
      prompt: field(prompt, ''), max_output_tokens: field(4096, 4096),
      replacement_rules: field(explicit ? RULES : '[]', '[]'), fallback_on_refusal: field(explicit, false)}};
}
const payload = {
  tasks: [
    task('conversation.reply', 'primary', 'foreground', ['text'], true, '保持自然的语气，先回应当下的情绪。'),
    task('memory.reflect', 'primary', 'background', ['text']),
    task('calendar.plan', 'primary', 'background', ['text']),
    task('role.journal.diary', 'secondary', 'background', ['text'], true),
    task('role.reading.consume', 'primary', 'background', ['text', 'vision']),
  ],
  providers: [
    {id: 'primary', capabilities: ['text'], max_output_tokens: 8192},
    {id: 'secondary', capabilities: ['text', 'vision'], max_output_tokens: 16384},
    {id: 'draft-vision', capabilities: ['vision'], max_output_tokens: 4096},
  ],
  host_state: 'running',
};

const store = new Map();
const requests = [];
const sandbox = {
  crypto: {randomUUID: () => 'preview-key'},
  setTimeout, clearTimeout, AbortController,
  sessionStorage: {getItem: k => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, v), removeItem: k => store.delete(k)},
  window: {
    CompanionProduct: {hosted: () => true, role: () => ({model_api: '/astrbot_plugin_private_companion_v2/model'}), identity: () => ({installation_id: 'inst', operator_id: 'preview'})},
    AstrBotPluginPage: {
      apiGet: () => new Promise((resolve, reject) => requests.push({resolve, reject})),
      apiPost: () => new Promise((resolve, reject) => requests.push({resolve, reject})),
    },
  },
};
sandbox.globalThis = sandbox;
vm.runInNewContext(source, sandbox);

const handlers = {};
const node = {
  isConnected: true, innerHTML: '',
  addEventListener(type, handler) { handlers[type] = handler; },
  removeEventListener() {},
  querySelector: () => null, querySelectorAll: () => [],
};
sandbox.window.CompanionModelsPage.mount(node);
requests[0].resolve(payload);

setImmediate(() => {
  const fire = (type, selector, dataset) => handlers[type]({type, target: {dataset, value: dataset.value,
    matches: candidate => candidate === selector, closest: candidate => (candidate === selector ? {dataset} : null)}});
  fire('click', '[data-model-pick]', {modelPick: 'calendar.plan'});
  fire('click', '[data-model-pick]', {modelPick: 'memory.reflect'});
  fire('change', '[data-model-field]', {modelField: 'provider', modelKind: 'calendar.plan', value: 'secondary'});
  fire('change', '[data-model-field]', {modelField: 'max_output_tokens', modelKind: 'conversation.reply', value: '8192', valueAsNumber: 8192});
  fire('click', '[data-model-open]', {modelOpen: 'conversation.reply'});
  fire('click', '[data-model-sub]', {modelSub: 'pol'});
  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>模型与连接 · 排版预览</title>
<link rel="stylesheet" href="../pages/陪伴小屋/styles.css">
<link rel="stylesheet" href="../pages/陪伴小屋/models-page.css">
<style>body{margin:0;background:var(--bg);padding:24px}
.wrap{max-width:1120px;margin:0 auto;background:#fff;border:1px solid var(--line);border-radius:16px;padding:24px 26px;box-shadow:var(--shadow)}
.note{margin:0 0 18px;font-size:12px;color:#667085;line-height:1.7}</style></head>
<body><div class="wrap">
<p class="note">静态预览 · 数据为示例，用于确认新版「模型与连接」页的排版与交互。实际数据来自 V2 宿主的 <code>/model</code> 接口。缩小窗口可查看 ≤860px 的卡片式降级。</p>
${node.innerHTML}
</div></body></html>`;
  const out = path.resolve(__dirname, 'MODEL_PAGE_PREVIEW_20260926.html');
  fs.writeFileSync(out, html, 'utf8');
  console.log('written', out, html.length);
});
