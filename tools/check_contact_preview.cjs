/* 主动与联系预览页冒烟检查。
 *
 * 生成页（tools/build_contact_preview.py）把真页面本体内联进 HTML，
 * 只把页面桥换成返回假数据的桩。这个脚本就是那份预览的验收：
 * 接线有没有断、几何对不对、交互走不走得通。
 *
 * 用法：node tools/check_contact_preview.cjs [预览路径]
 *
 * 为什么值得单独一个脚本：预览是给人看的，它坏掉的方式通常很安静
 * （桥的桩形状不对 → 页面停在空态，看着像"还在加载"）。
 * 靠肉眼看是发现不了的。
 */
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const html = fs.readFileSync(process.argv[2] || "docs/page-designs/contact-rhythm-preview.html", 'utf8');
const materialPreview = (process.argv[2] || "").includes("material-pool-preview.html");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
console.log('脚本块数：', scripts.length);
if (scripts.length !== 3) throw new Error('预期三个脚本块（桥桩 / 页面本体 / 挂载）');

/* 预览壳曾只内联主题色块，:root 的尺寸/字号令牌全缺，
   页面所有 var(--sp-*) / var(--fs-*) 静默归零——真页面是好的，
   预览却整体挤成一团，靠肉眼看只会以为「样式没调好」。
   这里守住：内联区必须带 :root 令牌本体，而不是只有换肤用的色值。 */
const styleBlock = html.slice(html.indexOf('<style>') + 7, html.indexOf('</style>'));
const tokenChecks = {
  '内联了 :root 尺寸令牌（--sp-*）': styleBlock.includes('--sp-2:8px') && styleBlock.includes('--sp-6:30px'),
  '内联了 :root 字号令牌（--fs-*）': /--fs-body:calc\(\d+(?:\.\d+)?px \* var\(--font-scale\)\)/.test(styleBlock),
  '内联了 :root 圆角令牌（--r-*）': /--r-md:[^;]+;/.test(styleBlock),
  '内联区在令牌之后才是页面样式': styleBlock.indexOf('--sp-2:8px') < styleBlock.indexOf('contact-page.css'),
  /* tokens.css 的首屏引导闸门有两道（theme-ready / room-ready）：
     html 没带齐时 body 整页 visibility:hidden。预览没有引导脚本，
     标记必须直接写在 <html> 上。 */
  'html 带齐了 ready 标记（body 才可见）':
    /<html\b[^>]*data-theme-ready/.test(html) && /<html\b[^>]*data-room-ready/.test(html),
};
for (const [name, ok] of Object.entries(tokenChecks)) {
  console.log((ok ? '  ✓ ' : '  ✗ ') + name);
  if (!ok) process.exit(1);
}

const listeners = {};
const el = (id) => ({id, innerHTML: '', isConnected: true,
  addEventListener: (t, h) => { (listeners[id] ||= {})[t] = h; },
  removeEventListener: () => {}, contains: () => true,
  querySelector: () => null, querySelectorAll: () => [], dataset: {},
  style: {setProperty(){}}, onclick: null});
const nodes = {contactWorkspace: el('contactWorkspace'), theme: el('theme'), scene: el('scene')};
const document = {
  documentElement: {dataset: {theme: 'courtyard'}},
  getElementById: (id) => nodes[id] || null,
  addEventListener: () => {},
  querySelector: selector => materialPreview && selector === '#contactWorkspace [data-view="materials"]'
    ? {click: () => listeners.contactWorkspace?.click({target: {closest: sel => sel === '[data-view]'
      ? {dataset: {view: 'materials'}} : null}})} : null,
  querySelectorAll: () => [],
  body: {classList: {add(){},remove(){},toggle(){}}}, title: '',
};
const window = {document};
const sandbox = {window, document, console, Intl, Date, JSON, Math, Number, Object, Array,
  String, Set, Map, Boolean, Error, Promise, setTimeout, clearTimeout, URL,
  localStorage: {getItem: () => null, setItem(){}, removeItem(){}}};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
for (const code of scripts) vm.runInContext(code, sandbox);

const initial = (async () => {
  for (let i = 0; i < 40; i++) { await new Promise(r => setImmediate(r)); await new Promise(r => setTimeout(r, 20)); }
  const state = sandbox.window.CompanionContactPage.state.data;
  const out = nodes.contactWorkspace.innerHTML;
  const surfaceChecks = materialPreview ? {
    '主动检视页同时显示外部素材和主动记录': out.includes('素材与主动检视')
      && out.includes('外部素材') && out.includes('主动记录'),
    '待发送问候显示发送前状态': out.includes('早上想和你打个招呼')
      && out.includes('发送前检视 · 等待投递'),
    '已送达消息与未发送念头可检视': out.includes('发送前检视 · 已送达')
      && out.includes('发送前检视 · 未发送'),
    '主动消息显示接收目标和角色': out.includes('用户 001') && out.includes('澄溪'),
  } : {
    '环上有 24 根柱子': (out.match(/class="ct-bar[" ]/g) || []).length === 24,
    '环上有三条问候弧': (out.match(/class="ct-anchor"/g) || []).length === 3,
    '免打扰弧跨午夜拆两段': (out.match(/class="ct-quiet is-on"/g) || []).length === 1,
  };
  const checks = {
    '页面挂载出内容': out.length > 3000,
    '设置了 ready 标志': state && state.ready === true,
    '拉到了 160 项设置': !!(state && state.settings) && Object.keys(state.settings).length === 160,
    ...surfaceChecks,
    '契机矩阵可切换': !!listeners.contactWorkspace.click,
    '曲线可拖涂': !!listeners.contactWorkspace.pointerdown,
    '请求走的是插件相对路径': sandbox.window.__requests.every(r => r.indexOf('/astrbot_plugin') < 0),
  };
  let bad = 0;
  for (const [name, ok] of Object.entries(checks)) {
    console.log((ok ? '  ✓ ' : '  ✗ ') + name);
    if (!ok) bad++;
  }
  console.log('请求记录：', sandbox.window.__requests.join(' | '));
  if (bad) { console.log('失败 ' + bad + ' 项'); process.exit(1); }
  console.log('预览冒烟通过');
})();

/* ---- 交互冒烟：预览里点得动，真页面就点得动 ----
   必须等上面那一段跑完：两段都是 async，并行的话交互断言会在
   首次读取还没回来时就开始，看到的是一块空 DOM。 */
initial.then(async () => {
  const click = (target) => listeners.contactWorkspace.click({target, preventDefault(){}, stopPropagation(){}});
  const change = (target) => listeners.contactWorkspace.change({target, preventDefault(){}, stopPropagation(){}});
  /* 桩元素：closest 按「这个元素自己命中哪些选择器」回答，而不是只认一个。
     页面用 closest('[data-view]') / closest('[data-action]') / closest('[data-tier]')
     分别取不同的属性，一个元素同时可能命中多个。 */
  const wrap = (attrs) => {
    const self = {
      dataset: attrs, type: '', step: '', checked: false, value: '',
      closest(sel) {
        const probes = {view: '[data-view]', action: '[data-action]', tier: '[data-tier]',
                        anchor: '[data-anchor]', field: '[data-field]'};
        for (const [key, pattern] of Object.entries(probes)) {
          if (attrs[key] !== undefined && sel === pattern) return self;
        }
        return null;
      },
      parentElement: {querySelector: () => null},
    };
    return self;
  };

  for (const view of ['purposes', 'gates', 'budgets', 'sources', 'dial']) {
    click(wrap({view}));
    const marker = {purposes:'ct-purposes', gates:'ct-gates', budgets:'ct-budgets',
                    sources:'ct-sources', dial:'ct-dial'}[view];
    if (!nodes.contactWorkspace.innerHTML.includes(marker)) throw new Error(view + ' 视图没渲染');
  }
  console.log('  ✓ 五个视图都能切并渲染');

  click(wrap({tier: 'live'}));
  const data = sandbox.window.CompanionContactPage.state.data;
  if (data.draft.proactive_intensity_preset !== 'live') throw new Error('档位没进草稿');
  if (data.touched.size !== 1) throw new Error('草稿条数不对：' + data.touched.size);
  console.log('  ✓ 换档位进草稿且只记一项');

  click(wrap({action: 'curve-flat'}));
  if (data.draft.proactive_hour_activity_curve.split(',').length !== 24) throw new Error('拉平没写 24 个值');
  console.log('  ✓ 拉平曲线写满 24 格');

  const before = sandbox.window.__requests.length;
  click(wrap({action: 'save'}));
  for (let i = 0; i < 20; i++) { await new Promise(r => setImmediate(r)); await new Promise(r => setTimeout(r, 20)); }
  const post = sandbox.window.__requests.slice(before).find(r => r.startsWith('POST'));
  if (!post) throw new Error('保存没有发出 POST');
  if (!post.includes('proactive_intensity_preset')) throw new Error('载荷里没有档位：' + post);
  console.log('  ✓ 保存发出 POST：' + post.slice(0, 110));

  if (sandbox.window.CompanionContactPage.state.data.touched.size !== 0) {
    throw new Error('保存成功后草稿没清空');
  }
  console.log('  ✓ 保存成功后草稿清空');
  console.log('交互冒烟通过');
}).catch(e => { console.log("交互冒烟失败：" + e.message); process.exit(1); });
