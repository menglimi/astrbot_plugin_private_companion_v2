/* 学习与反思预览页冒烟检查。
 *
 * 生成页（tools/build_learning_preview.py）把真页面本体内联进 HTML，
 * 只把页面桥换成返回假数据的桩。这个脚本就是那份预览的验收：
 * 接线有没有断、五段轨道对不对、动作门守没守住、交互走不走得通。
 *
 * 用法：node tools/check_learning_preview.cjs [预览路径]
 *
 * 为什么值得单独一个脚本：预览坏掉的方式通常很安静
 * （桥的桩形状不对 → 页面停在空态，看着像"还在加载"），肉眼看是发现不了的。
 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const file = process.argv[2] || path.resolve(__dirname, '../docs/page-designs/learning-track-preview.html');
const source = fs.readFileSync(file, 'utf8');
const scripts = [...source.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (scripts.length !== 3) throw new Error('预期三个脚本块（桥桩 / 页面本体 / 挂载），实际 ' + scripts.length);

const listeners = {};
const element = id => ({
  id, innerHTML: '', isConnected: true,
  addEventListener: (type, handler) => { (listeners[id] ||= {})[type] = handler; },
  removeEventListener: () => {}, contains: () => true,
  querySelector: () => null, querySelectorAll: () => [],
  dataset: {}, style: {setProperty() {}}, onclick: null,
});
const nodes = {
  learningWorkspace: element('learningWorkspace'),
  theme: element('theme'), blind: element('blind'), log: element('log'),
};
const document = {
  documentElement: {dataset: {theme: 'courtyard'}},
  getElementById: id => nodes[id] || null,
  addEventListener: () => {}, querySelector: () => null, querySelectorAll: () => [],
  body: {classList: {add() {}, remove() {}, toggle() {}}}, title: '',
};
const window = {document};
const sandbox = {
  window, document, console, Intl, Date, JSON, Math, Number, Object, Array, String, Set, Map,
  Boolean, Error, Promise, setTimeout, clearTimeout, URL,
  localStorage: {getItem: () => null, setItem() {}, removeItem() {}},
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
for (const code of scripts) vm.runInContext(code, sandbox);

const flush = async () => { for (let i = 0; i < 25; i++) { await new Promise(r => setImmediate(r)); await new Promise(r => setTimeout(r, 12)); } };
/* 一次写操作会串起「POST → 回执 → 随后的 GET → 回执」。
   只 flush 一轮会在 POST 刚回来、GET 还没发出时继续往下点，
   而那时 writing 还为真，点击会被丢掉——表现是"点了没反应"，
   和真页面里那个读写互锁是同一种假象。所以等到完全空下来。 */
const idle = async () => {
  const page = () => sandbox.window.CompanionLearningPage.state.data;
  for (let i = 0; i < 40; i++) {
    await new Promise(r => setImmediate(r));
    await new Promise(r => setTimeout(r, 12));
    const state = page();
    if (state && !state.writing && !state.loading && !state.loadingReviews) return;
  }
};
const click = attrs => listeners.learningWorkspace.click({
  target: node(attrs), preventDefault() {}, stopPropagation() {},
});
const change = attrs => listeners.learningWorkspace.change({target: node(attrs), preventDefault() {}});
/* 桩元素：closest 按「自己命中哪些选择器」回答。 */
function node(attrs) {
  const self = {
    dataset: attrs, type: '', checked: false, value: '',
    closest(sel) {
      const probes = {view: '[data-view]', action: '[data-action]', act: '[data-act]',
                      id: '[data-id]', open: '[data-open]', review: '[data-review]',
                      confirm: '[data-confirm]', filterState: '[data-filter-state]',
                      filterKind: '[data-filter-kind]', access: '[data-access]'};
      for (const [key, pattern] of Object.entries(probes)) {
        if (attrs[key] !== undefined && sel === pattern) return self;
      }
      return null;
    },
  };
  return self;
}
let failures = 0;
function check(name, ok) {
  console.log((ok ? '  ✓ ' : '  ✗ ') + name);
  if (!ok) failures++;
}

(async () => {
  await flush();
  const state = sandbox.window.CompanionLearningPage.state.data;
  const html = () => nodes.learningWorkspace.innerHTML;

  console.log('== 首次读取 ==');
  check('页面挂载出内容', html().length > 2000);
  check('设置了 ready 标志', state && state.ready === true);
  check('读到了成长记录', state && state.items.length === 8);
  check('读到了待审阅', state && state.reviews.length === 3);
  check('权限随列表一起回来', !!(state && state.access));

  console.log('== 轨道几何 ==');
  const out = html();
  for (const key of ['proposed', 'active', 'paused', 'achieved', 'retired']) {
    check('轨道有 ' + key + ' 段', out.includes('data-lane="' + key + '"'));
  }
  check('五段各有卡片', ['proposed', 'active', 'paused', 'achieved', 'retired'].every(key => {
    const lane = out.split('data-lane="' + key + '"')[1] || '';
    return lane.split('data-id="').length > 1;
  }));
  check('来源失效的记录单独标出', out.includes('is-blind'));

  console.log('== 动作门 ==');
  /* proposed 的卡片上只能出现后端给的那几个动作。 */
  const proposedLane = out.split('data-lane="proposed"')[1].split('data-lane="')[0];
  const shown = [...proposedLane.matchAll(/data-act="([a-z]+)"/g)].map(m => m[1]);
  check('proposed 段有动作按钮', shown.length > 0);
  check('proposed 段没有越界动作',
    shown.every(a => ['confirm', 'revise', 'withdraw', 'retire'].includes(a)));
  check('proposed 段没有「暂停」', !shown.includes('pause'));

  console.log('== 交互 ==');
  for (const view of ['reviews', 'sources', 'gate', 'track']) {
    click({view});
    const marker = {track: 'lea-lanes', reviews: 'lea-reviews', sources: 'lea-sources', gate: 'lea-gate'}[view];
    check('切到 ' + view + ' 并渲染', html().includes(marker));
  }

  click({view: 'reviews'});
  check('审阅页有采纳按钮', /data-review="accept"/.test(html()));
  check('依据失效那条只有不采纳',
    (html().match(/data-review="accept"/g) || []).length === 2);

  /* 裁决一条：应当发出 POST 并且从列表里去掉。 */
  click({review: 'accept', id: 'r-1'});
  await idle();
  check('裁决后那条从队列里移除', !state.reviews.some(r => r.review_id === 'r-1'));
  check('裁决发了正确的路由',
    sandbox.window.__requests.some(r => r.indexOf('POST growth/progress/command') === 0));

  click({view: 'track'});
  click({act: 'pause', id: 'g-skill-2'});
  await idle();
  /* 读页面的 state，不是预览的 REPLY：页面把响应深拷进了自己那一份。 */
  const paused = state.items.find(r => r.growth_id === 'g-skill-2');
  check('暂停动作改了状态', paused && paused.state === 'paused');
  check('暂停动作后重新读了列表', html().includes('data-lane="paused"'));

  click({act: 'retire', id: 'g-skill-2'});
  check('不可逆动作先出确认条', html().includes('lea-confirm'));
  await idle();
  click({confirm: 'no'});
  await idle();
  check('取消后确认条收起', !html().includes('lea-confirm'));

  click({view: 'gate'});
  const reads = sandbox.window.__requests.filter(r => r === 'GET  growth').length;
  change({access: 'proposals_enabled', checked: false});
  await idle();
  check('开关保存改了设置', state.access.settings.proposals_enabled === false);
  check('保存后重新读了列表', sandbox.window.__requests.filter(r => r === 'GET  growth').length > reads);

  check('请求走的都是插件相对路径',
    !sandbox.window.__requests.some(r => r.indexOf('/astrbot_plugin') >= 0));

  console.log('== 请求记录 ==');
  console.log(sandbox.window.__requests.map(line => '  ' + line).join('\n'));
  if (failures) { console.log('失败 ' + failures + ' 项'); process.exit(1); }
  console.log('预览冒烟通过');
})().catch(error => { console.log('预览冒烟失败：' + error.message); process.exit(1); });
