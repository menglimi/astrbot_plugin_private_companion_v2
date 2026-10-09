/* 事实与经历预览页冒烟检查。
 *
 * 生成页（tools/build_memory_preview.py）把真页面本体内联进 HTML，
 * 只把页面桥换成返回假数据的桩。这个脚本就是那份预览的验收：
 * 接线有没有断、事实流读没读进来、生命周期色画没画、交互走不走得通。
 *
 * 用法：node tools/check_memory_preview.cjs [预览路径]
 *
 * 为什么值得单独一个脚本：预览坏掉的方式通常很安静
 * （桥的桩形状不对 → 页面停在空态，看着像"还在加载"），肉眼看是发现不了的。
 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const file = process.argv[2] || path.resolve(__dirname, '../docs/page-designs/memory-archive-preview.html');
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
  memoryWorkspace: element('memoryWorkspace'),
  theme: element('theme'), log: element('log'),
};
const document = {
  documentElement: {dataset: {theme: 'courtyard'}},
  hidden: false, title: '',
  getElementById: id => nodes[id] || null,
  addEventListener: () => {}, querySelector: () => null, querySelectorAll: () => [],
  body: {classList: {add() {}, remove() {}, toggle() {}}},
};
const window = {document, matchMedia: () => ({matches: false})};
/* 页面用 localStorage 存待确认台账与幂等键，桩里要真的能存取。 */
const store = new Map();
const sandbox = {
  window, document, console, Intl, Date, JSON, Math, Number, Object, Array, String, Set, Map,
  Boolean, Error, Promise, setTimeout, clearTimeout, setInterval, clearInterval, URL, Blob,
  localStorage: {
    getItem: k => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: k => store.delete(k),
  },
  requestAnimationFrame: () => 0, performance: {now: () => 0},
  CSS: {escape: v => v},
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
for (const code of scripts) vm.runInContext(code, sandbox);

let failures = 0;
function check(name, ok) {
  console.log((ok ? '  ✓ ' : '  ✗ ') + name);
  if (!ok) failures++;
}
/* 让出事件循环，直到在飞的请求都答完。假桥的回执延迟是 110ms，
   而事实流是**串行预读**（发一页、等回执、再决定下一页），
   所以要真的等够：14 轮不够，第二页会还没回来就继续往下断言。 */
const flush = async () => {
  for (let i = 0; i < 26; i++) {
    await new Promise(r => setImmediate(r));
    await new Promise(r => setTimeout(r, 18));
  }
};
/* 点击桩。监听器缺失时**不能静默吞掉**——那会表现成"点了没反应"，
   和真页面里的交互失效是同一种假象，很难与本脚本要抓的问题区分。 */
const click = attrs => {
  const handler = listeners.memoryWorkspace?.click;
  if (!handler) throw new Error('memoryWorkspace 上没有 click 监听器：页面没挂上？');
  handler({target: node(attrs), preventDefault() {}, stopPropagation() {}});
};
/* 桩元素：closest 按「自己命中哪些选择器」回答。
   两个必须照抄的细节：
     1. 点击处理器第一行是 closest("button")，靠它找到承载动作的那个按钮；
        桩不认 "button" 就会在第一行返回，整条点击链静默失效。
     2. dataset 是**驼峰**（data-fact-id → dataset.factId），
        页面读的是 el.dataset.factId，不是连字符形式。
   传入的 attrs 直接用**真实属性名**（'data-fact-id'），不另起一套简称——
   简称与真实名之间多一层映射，写错一个键就变成"点了没反应"，极难查。 */
function node(attrs) {
  const camel = {};
  for (const [k, v] of Object.entries(attrs)) {
    camel[k.replace(/^data-/, '').replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = v;
  }
  const self = {
    /* id 也来自 attrs：视图轨道靠 memory-area-<id> 这个 id 识别，
       不是靠 data-area。 */
    dataset: camel, type: '', checked: false, value: '',
    id: attrs.id || '', disabled: false,
    classList: {add() {}, remove() {}, toggle() {}},
    closest(sel) {
      if (sel === 'button') return self;
      for (const key of Object.keys(attrs)) {
        if ('[' + key + ']' === sel) return self;
      }
      return null;
    },
  };
  return self;
}

(async () => {
  await flush();
  const page = sandbox.window.CompanionMemoryPage;
  const state = page.state.data;
  const html = () => nodes.memoryWorkspace.innerHTML;

  console.log('== 首次读取 ==');
  check('页面挂载出内容', html().length > 2000);
  check('设置了 ready 标志', state && state.ready === true);
  check('读到了目录', !!(state && state.catalog));
  check('读到了事实流', state && state.corpus.length === 12);
  check('读到了第二页并停止（不再有游标）', state && state.hasMore === false);
  check('请求走的都是插件相对路径',
    !sandbox.window.__requests.some(r => r.indexOf('/astrbot_plugin') >= 0));
  check('第一次请求是目录', sandbox.window.__requests[0] === 'GET  page/targets');

  console.log('== 生命周期呈现 ==');
  const out = html();
  /* 只有四种生命周期进列表：archived 是冷归档，不在工作集里，
     stateOf() 会把任何不认识的取值归到 superseded。断言四种，不是五种。 */
  check('四种生命周期各占一个状态类',
    ['active', 'superseded', 'retracted', 'forgotten']
      .every(s => out.includes('mem-state-' + s)));
  check('比例带按生命周期分段', (out.match(/mem-band/g) || []).length > 0);
  check('总览数字存在', /data-count="\d+"/.test(out));

  console.log('== 事实流与详情 ==');
  /* 先确认监听器真的挂上了：页面若在 mount 早期抛错，click 会静默失效。 */
  check('click 监听器已注册', typeof listeners.memoryWorkspace?.click === 'function');
  check('change 监听器已注册', typeof listeners.memoryWorkspace?.change === 'function');
  /* 类名会嵌套（mem-card-line / mem-card-q），所以要按精确类名匹配，
     不能拿 class="mem-card 前缀去数——那样会漏掉带状态类的卡片。 */
  check('事实列表渲染了卡片', (out.match(/class="mem-card (?:mem-state-\w+)"/g) || []).length === 12);
  check('每条都带来源标记位', (out.match(/class="mem-pin/g) || []).length === 12);
  click({'data-fact-id': 'a-02'});
  await flush();
  check('选中一条会读详情', state.selId === 'a-02');
  check('详情带出条目本体', !!state.factDetail?.item);
  check('读详情走的是 POST',
    sandbox.window.__requests.some(r => r.indexOf('POST memory/detail') === 0));
  /* 页面在读到详情后**自动**取版本历史——版本是这一页的核心信息，
     让人再点一次才看得到等于藏起来。历史走单独一路（GET .../revisions）。 */
  check('版本历史随详情自动读取', state.revisions.length === 3);
  check('历史请求走的是 GET memory/revisions',
    sandbox.window.__requests.some(r => r.indexOf('GET  memory/revisions') === 0));
  /* 详情里的来源引用：页面拿它做响应校验，缺了整条详情会被判为无效。 */
  check('详情带出来源引用', Array.isArray(state.factDetail?.sources)
    && state.factDetail.sources.length === 2);

  console.log('== 筛选与搜索（本地完成）==');
  const reads = sandbox.window.__requests.filter(r => r.startsWith('GET  memory')).length;
  click({'data-filter': 'forgotten'});
  await flush();
  check('筛选只影响渲染，不再发请求',
    sandbox.window.__requests.filter(r => r.startsWith('GET  memory')).length === reads);

  console.log('== 视图切换 ==');
  for (const area of ['reflections', 'query', 'archive', 'migrate', 'clear', 'facts']) {
    click({'id': 'memory-area-' + area});
    await flush();
    check('切到 ' + area + ' 并渲染', html().length > 800);
  }

  console.log('== 整理批次 ==');
  click({'id': 'memory-area-reflections'});
  await flush();
  check('整理视图读出批次', /mem-batch/.test(html()));

  console.log('== 请求记录 ==');
  console.log(sandbox.window.__requests.slice(0, 12).map(line => '  ' + line).join('\n'));
  if (failures) { console.log('失败 ' + failures + ' 项'); process.exit(1); }
  console.log('预览冒烟通过');
  /* 必须显式退出：页面挂载后会起一个 8 秒轮询（schedule()），
     它会一直把事件循环撑住，node 不会自己结束——表现就是"跑完了但不返回"。 */
  process.exit(0);
})().catch(error => { console.log('预览冒烟失败：' + error.message); process.exit(1); });
