/* 外观与设置页的契约测试。
 *
 * 这一页与前几页不同：**没有后端端点**。它读写的全是字符串与特性开关，
 * 所以这里不 mock 桥，而是给一个假的 window 环境：
 *   · CompanionProduct.appearance() / setAppearance() / resetAppearance()
 *   · CompanionTheme（theme.js 的注册表）
 *   · matchMedia、localStorage
 * 断言的重点也不是"请求发对了没有"，而是：
 *   · 改动是否真的落到了 product 上（而不是只改了页面自己那份 state）
 *   · 预览窗的属性是否跟着变（这是这一页存在的理由）
 *   · 主题切换是否**不整页重渲染**（重渲染会打断叠化覆层）
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const PAGES = path.resolve(__dirname, '../pages/陪伴小屋');
const source = fs.readFileSync(path.join(PAGES, 'appearance-page.js'), 'utf8');

const THEMES = [
  {id: 'courtyard', label: '庭院', note: '窗格纹理与轻圆角，清爽通透', light: 'day', mode: 'light'},
  {id: 'dawn', label: '晨雾', note: '纸页细线与衬线标题，安静柔和', light: 'dawn', mode: 'light'},
  {id: 'dusk', label: '暮色', note: '陶土斜纹与收紧边角，温暖利落', light: 'dusk', mode: 'light'},
  {id: 'night', label: '夜读', note: '墨色书页与阅读排版，低照度舒适', light: 'night', mode: 'dark'},
  {id: 'walnut', label: '深林', note: '木作竖理与紧凑边界，沉稳耐看', light: 'dusk', mode: 'dark'},
  {id: 'contrast', label: '高对比', note: '纯色背景、实线边界与强焦点提示', light: 'day', mode: 'light'},
];

/* 极简元素桩。外观页的所有点击都用 `target.closest("[data-ap-*]")` 定位，
   所以这个桩必须按"自己命中哪些属性选择器"回答 closest——
   只有一个节点的场景下，"最近的祖先"就是它自己。
   返回 null 会让整条点击链在第一次 closest 处静默退出（页面不报错，
   只是什么都没发生），这正是最难查的一种测试失败。 */
function node(tag, attrs = {}) {
  const camel = {};
  for (const [k, v] of Object.entries(attrs)) {
    camel[k.replace(/^data-/, '').replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = v;
  }
  const self = {
    tagName: String(tag).toUpperCase(), dataset: camel, children: [], innerHTML: '',
    textContent: '', value: attrs.value || '', type: '', readOnly: false, tabIndex: 0,
    _classes: new Set(String(attrs.class || '').split(/\s+/).filter(Boolean)),
    _attrs: {...attrs},
    classList: {
      add: c => self._classes.add(c), remove: c => self._classes.delete(c),
      contains: c => self._classes.has(c),
      toggle: (c, on) => { if (on === undefined) { self._classes.has(c) ? self._classes.delete(c) : self._classes.add(c); }
                           else if (on) self._classes.add(c); else self._classes.delete(c); },
    },
    setAttribute(k, v) { self._attrs[k] = v; if (k === 'class') self._classes = new Set(String(v).split(/\s+/).filter(Boolean)); },
    getAttribute(k) { return self._attrs[k]; },
    addEventListener() {}, removeEventListener() {},
    /* 属性选择器形如 "[data-ap-theme]"；带上属性名即命中。 */
    closest(selector) {
      const m = String(selector).match(/^\[([a-z-]+)\]$/);
      if (m && Object.hasOwn(attrs, m[1])) return self;
      return null;
    },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    click() {},
  };
  return self;
}

function makeRoot() {
  const handlers = {};
  const store = {};
  const root = node('section', {class: 'appearance-workspace'});
  /* innerHTML 写入时把里面出现的 data-* 属性记下来，供断言查。
     （真实 DOM 会解析，这里只需要能回答"渲染出了什么"。） */
  let html = '';
  Object.defineProperty(root, 'innerHTML', {
    get: () => html,
    set: value => {
      html = String(value);
      store.apTheme = new Set([...html.matchAll(/data-ap-theme="([^"]+)"/g)].map(m => m[1]));
      store.apDim = new Set([...html.matchAll(/data-ap-dim="([^"]+)"/g)].map(m => m[1]));
      store.previewTheme = (html.match(/class="ap-preview" data-theme="([^"]+)"/) || [])[1] || '';
      store.previewDensity = (html.match(/data-density="([^"]+)"/) || [])[1] || '';
      store.previewTypeScale = (html.match(/data-type-scale="([^"]+)"/) || [])[1] || '';
      store.renders = (store.renders || 0) + 1;
    },
  });
  root.addEventListener = (type, handler) => { handlers[type] = handler; };
  root.removeEventListener = type => { delete handlers[type]; };
  root.querySelector = selector => {
    if (selector === '.ap-preview') return root.__preview || null;
    if (selector === '.ap-preview-note') return root.__note || null;
    return null;
  };
  root.querySelectorAll = selector => (store.queryAll && store.queryAll[selector]) || [];
  root.fire = (type, target) => { if (handlers[type]) handlers[type]({type, target, preventDefault() {}}); };
  root.store = store;
  return root;
}

function harness({ready = true, largeText = false} = {}) {
  const calls = [];
  const appearance = {theme: 'courtyard', density: 'standard', radius: 'standard', typeScale: 'm', motion: 'full'};
  const saved = {};
  const displayPreferences = {
    value: largeText,
    largeText() { return this.value; },
    setLargeText(value) { this.value = Boolean(value); return this.value; },
  };
  /* ready=false 模拟"宿主注入还没到"：这时 window.CompanionProduct 整个不存在，
     而不是存在但返回空。两种写法在页面里的走向不同——
     前者读不到就退回默认并拒绝写入，后者会被当成一次失败的读取。 */
  const window = {
    CompanionTheme: {
      THEMES,
      label: id => (THEMES.find(t => t.id === id) || {}).label || id,
    },
    CompanionDisplayPreferences: displayPreferences,
    matchMedia: () => ({matches: false}),
    localStorage: {getItem: k => saved[k] ?? null, setItem: (k, v) => { saved[k] = v; }},
    setTimeout, clearTimeout,
  };
  if (ready) window.CompanionProduct = {
    appearance: () => ({...appearance}),
    setAppearance: (name, value) => {
      calls.push({op: 'set', name, value});
      if (!(name in appearance)) return appearance[name];
      appearance[name] = value;
      return value;
    },
    resetAppearance: () => {
      calls.push({op: 'reset'});
      Object.assign(appearance, {theme: 'courtyard', density: 'standard',
                                 radius: 'standard', typeScale: 'm', motion: 'full'});
      return {...appearance};
    },
    followLight: () => false,
    setFollowLight: on => { calls.push({op: 'followLight', value: on}); return !!on; },
  };
  const context = vm.createContext({window, localStorage: window.localStorage,
    matchMedia: window.matchMedia, setTimeout, clearTimeout, console, CustomEvent: class { constructor(t, o) { this.type = t; this.detail = o?.detail; } }});
  vm.runInContext(source, context);
  return {page: context.window.CompanionAppearancePage, calls, appearance, displayPreferences, root: makeRoot()};
}

test('the page renders the live preview plus every theme and dimension', () => {
  const {page, root} = harness();
  page.mount(root);
  assert.match(root.innerHTML, /class="ap-preview"/);
  for (const part of ['apv-rail', 'apv-content', 'apv-card', 'apv-actions', 'apv-field']) {
    assert.match(root.innerHTML, new RegExp(`class="${part}"`), '预览缺少工作区组件 ' + part);
  }
  assert.match(root.innerHTML, /窗格纹理与轻圆角/, '主题卡应说明结构风格，不只展示名称');
  assert.match(root.innerHTML, /改变卡片内边距与区块之间的距离/, '显示维度应呈现对应说明');
  assert.match(root.innerHTML, /预览与主题/);
  assert.match(root.innerHTML, /这些偏好只作用于当前浏览器/);
  assert.match(root.innerHTML, /ap-top-grid/);
  assert.match(root.innerHTML, /显示维度与可读性/);
  assert.match(root.innerHTML, /ap-dimension-grid/);
  for (const id of THEMES.map(t => t.id)) {
    assert.ok(root.store.apTheme.has(id), '缺少主题 ' + id);
  }
  for (const dim of ['density', 'radius', 'typeScale', 'motion']) {
    assert.ok(root.store.apDim.has(dim), '缺少维度 ' + dim);
  }
  /* 明暗分组：深色两套不能混进日间那一组。 */
  const dayStart = root.innerHTML.indexOf('日间');
  const nightStart = root.innerHTML.indexOf('按陈设风格');
  assert.ok(dayStart >= 0 && nightStart > dayStart, '主题应按明暗分组');
  const nightBlock = root.innerHTML.slice(nightStart);
  assert.ok(nightBlock.includes('data-ap-theme="night"') && nightBlock.includes('data-ap-theme="walnut"'),
    '夜间组应包含 night 与 walnut');
  assert.ok(!nightBlock.includes('data-ap-theme="courtyard"'), '夜间组不应包含浅色主题');
  page.unmount();
});

test('choosing a theme goes through the product layer and repaints only the preview', () => {
  const {page, calls, root} = harness();
  page.mount(root);
  const renders = root.store.renders;
  root.fire('click', node('button', {'data-ap-theme': 'night'}));
  /* 落盘必须经过 product——页面自己那份 state 不是数据源。 */
  assert.deepEqual(calls.find(c => c.op === 'set'), {op: 'set', name: 'theme', value: 'night'});
  /* 关键：**没有整页重渲染**。主题切换走叠化覆层（是整页快照），
     重渲染会让覆层盖在已经变过的内容上，看着像闪了一下。 */
  assert.equal(root.store.renders, renders, '切换主题不应整页重渲染');
  page.unmount();
});

test('a non-theme dimension re-renders so the preview and pressed state stay in sync', () => {
  const {page, calls, root} = harness();
  page.mount(root);
  const renders = root.store.renders;
  root.fire('click', node('button', {'data-ap-dim': 'density', 'data-ap-value': 'roomy'}));
  assert.deepEqual(calls.find(c => c.op === 'set'), {op: 'set', name: 'density', value: 'roomy'});
  assert.ok(root.store.renders > renders, '非主题维度应重渲染');
  assert.equal(root.store.previewDensity, 'roomy');
  page.unmount();
});

test('the reset button restores every dimension through the product layer', () => {
  const {page, calls, root} = harness();
  page.mount(root);
  root.fire('click', node('button', {'data-ap-dim': 'radius', 'data-ap-value': 'round'}));
  root.fire('click', node('button', {'data-ap-reset': ''}));
  assert.ok(calls.some(c => c.op === 'reset'), '恢复默认应调用 product.resetAppearance');
  assert.equal(root.store.previewDensity, 'standard');
  assert.match(root.innerHTML, /data-theme="courtyard"/);
  page.unmount();
});

test('a page bridge that is not ready yet retains the appearance controls and explains retrying', () => {
  const {page, root} = harness({ready: false});
  page.mount(root);
  /* 读不到外观时不能整页空白：主题与维度仍要渲染出来（用默认值），
     只是改动会被拒绝并给出说明，等页面连接就绪后再重试。 */
  assert.match(root.innerHTML, /class="ap-preview"/);
  assert.equal(root.store.apTheme.size, THEMES.length);
  root.fire('click', node('button', {'data-ap-theme': 'night'}));
  assert.match(root.innerHTML, /页面连接尚未就绪/);
  page.unmount();
});

test('refresh() rereads without replacing the node', () => {
  const {page, root} = harness();
  page.mount(root);
  const renders = root.store.renders;
  const same = root;
  page.refresh();
  assert.ok(root.store.renders > renders, 'refresh 应重读并重渲染');
  assert.equal(root, same, 'refresh 不应替换节点');
  page.unmount();
});

test('the preview carries all four dimensions as data attributes', () => {
  const {page, root} = harness();
  page.mount(root);
  /* 预览窗靠这四个属性让令牌层按选定值解析——缺任何一个，
     那个维度在预览里就是假的（选了看不到效果）。 */
  assert.equal(root.store.previewTheme, 'courtyard');
  assert.equal(root.store.previewDensity, 'standard');
  assert.equal(root.store.previewTypeScale, 'm');
  assert.match(root.innerHTML, /data-motion="full"/);
  page.unmount();
});

test('the readability switch reflects and updates the shell-owned preference', () => {
  const {page, displayPreferences, root} = harness({largeText: true});
  page.mount(root);
  assert.match(root.innerHTML, /aria-checked="true" data-ap-large aria-label="放大辅助文字"/);
  const switcher = node('span', {'data-ap-large': '', 'aria-checked': 'true'});
  root.fire('click', switcher);
  assert.equal(displayPreferences.value, false);
  assert.equal(switcher.getAttribute('aria-checked'), 'false');
  page.unmount();
});

test('unmount detaches listeners and stops the late read', () => {
  const {page, root} = harness({ready: false});
  page.mount(root);
  page.unmount();
  const renders = root.store.renders;
  /* 卸载后那一次补读（setTimeout 400ms）必须被版本号挡住，
     否则它会往已经丢弃的节点上写。 */
  return new Promise(resolve => setTimeout(() => {
    assert.equal(root.store.renders, renders, '卸载后不应再渲染');
    resolve();
  }, 460));
});
