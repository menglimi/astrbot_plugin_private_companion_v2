/* 页面桥的自愈路径。
 *
 * 用户报的现象：**整个拓展页依旧处于无法连接 AstrBot 的状态，所有页面的
 * 组件仍然未连接就不显示**。
 *
 * 根因：`AstrBotPluginPage` 不是宿主无条件塞进页面的全局变量，它由
 * /api/plugin/page/bridge-sdk.js 定义。四个工作区的 workspace.html 都显式引了，
 * 主页面此前没有——于是每个工作区都渲染「尚未读到宿主目录」。
 *
 * 但**不能**因此改成「主页面静态引一遍」：有的宿主会在重写 HTML 时自动补
 * 这条脚本（本地验收夹具 tools/check_product_page.cjs 就是这么做的），
 * 静态引会在那种宿主里加载两次。所以做成「先等，等不到再自己拉」，
 * 两种情况都成立。
 *
 * 这套测试守的就是那个「两种情况都成立」：
 *   1. 宿主已注入 → 不重复插标签
 *   2. 宿主不注入 → 自己插，并且等它
 *   3. 拉不到 → 抛可翻译的 bridge_unavailable，而不是 TypeError
 *
 * 第 3 条是真实写错过的形状：`await (P?.whenBridgeReady?.() ?? Promise.resolve(window.AstrBotPluginPage))`
 * 的 `??` 右半边会立刻求值，product 没提供等待器时拿到 undefined，
 * 接着 `bridge.apiGet` 抛 TypeError——用户看到一句无从翻译的类型错误。
 *
 * 用 node --test 运行。这里是 DOM 的最小替身，不引 jsdom。
 */
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "pages", "陪伴小屋", "product-page.js"), "utf8");
const INDEX = fs.readFileSync(
  path.join(__dirname, "..", "pages", "陪伴小屋", "index.html"), "utf8");
const flush = () => new Promise(resolve => setImmediate(resolve));

function harness({ bridge = null, readyState = "interactive", existingScript = false } = {}) {
  const appended = [];
  /* product-page.js 是整份模块，挂载时会用到这些浏览器接口。
     这里给最小的替身——本文件只关心桥的引导路径。 */
  const window = {
    addEventListener() {}, removeEventListener() {},
    matchMedia: () => ({matches: false, addEventListener() {}}),
    location: {hash: "", href: "http://localhost/#life"},
    history: {replaceState() {}},
    innerWidth: 1440, innerHeight: 900,
    requestAnimationFrame: callback => { callback(0); return 0; },
    cancelAnimationFrame() {},
  };
  if (bridge) window.AstrBotPluginPage = bridge;
  const document = {
    readyState,
    documentElement: {dataset: {}},
    head: {appendChild: node => { appended.push(node); }},
    body: {classList: {add() {}, remove() {}}},
    querySelector: selector => (existingScript && selector.includes("bridge-sdk") ? {} : null),
    /* sdkAlreadyPresent() 会遍历 script[src] 并读 src。existingScript 时
       返回一个带 bridge-sdk 路径的元素，模拟宿主已注入。 */
    querySelectorAll: selector => (existingScript && selector.includes("script[src]")
      ? [{getAttribute: () => "/api/plugin/page/bridge-sdk.js"}] : []),
    createElement: () => ({
      set src(value) { this._src = value; },
      get src() { return this._src; },
      addEventListener(type, handler) { (this._listeners ||= {})[type] = handler; },
      setAttribute() {},
    }),
    addEventListener() {},
  };
  const navigator = {language: "zh-CN"};
  vm.runInNewContext(SOURCE, {window, document, navigator, setTimeout, clearTimeout,
    Promise, Object, JSON, Array, String, Number, Boolean, Math, Date, Error, console,
    matchMedia: () => ({matches: false}), localStorage: {
      getItem: () => null, setItem() {}, removeItem() {}}});
  return {product: window.CompanionProduct, window, appended, document};
}

test("主页面不静态引页面桥，避免在自动注入的宿主里加载两次", () => {
  /* 静态引一遍看起来更省事，但宿主版本不定：有的自动补这条脚本，
     有的不补。页面里写死会在前者上重复加载。 */
  const tags = [...INDEX.matchAll(/<script[^>]*bridge-sdk[^>]*>/g)];
  assert.deepStrictEqual(tags.map(tag => tag[0]), [],
    "index.html 不该静态引 bridge-sdk.js：改由 product-page.js 动态处理");
});

test("宿主已经注入桥时不重复插标签", async () => {
  const injected = {apiGet() {}, apiPost() {}, ready: () => Promise.resolve({})};
  const {product, appended} = harness({bridge: injected});

  assert.strictEqual(product.bridgeNow(), injected, "桥已在，bridgeNow() 应当直接命中");
  await product.bridgeFor();
  assert.deepStrictEqual(appended, [], "桥已在，不该再插一次 SDK 标签");
});

test("宿主没注入时自己把 SDK 拉进来并等它", async () => {
  const {product, appended, window} = harness({readyState: "interactive"});
  /* 桥永远不来这条路径的拒绝由本用例之外的地方断言，这里先吞掉，
     免得变成 unhandledRejection 污染输出。 */
  const waiting = product.whenBridgeReady(2000);
  waiting.catch(() => {});

  /* defer 模块执行时 readyState 已经是 interactive——早前按
     `readyState === "loading"` 设限，这条路径永远不会插入脚本，
     整页就永远连不上。这条断言就是那个缺陷的护栏。 */
  assert.strictEqual(appended.length, 1, `readyState=interactive 时也应当插入 SDK：${appended.length}`);
  assert.match(appended[0]._src, /bridge-sdk\.js/);
  assert.strictEqual(appended[0]._src, "/api/plugin/page/bridge-sdk.js",
    "第一个候选应当是官方路径（三处验收脚本与演示宿主都用它）");

  /* 模拟 SDK 到位：等待器应当自己 resolve，不再超时。 */
  window.AstrBotPluginPage = {apiGet() {}, apiPost() {}, ready: () => Promise.resolve({})};
  const found = await waiting;
  assert.strictEqual(found, window.AstrBotPluginPage);
});

test("已经有人引过 SDK 就不重复插", async () => {
  const {product, appended} = harness({existingScript: true});
  product.whenBridgeReady(60).catch(() => {});
  await flush();

  assert.deepStrictEqual(appended, [], "页面上已有 bridge-sdk 标签，不该再插一个");
});

test("拉不到时抛可翻译的 bridge_unavailable，不是 TypeError", async () => {
  /* 真实写错过的形状：`await (P?.whenBridgeReady?.() ?? Promise.resolve(window.AstrBotPluginPage))`
     的 `??` 右半边立刻求值，拿到 undefined，接着 bridge.apiGet 抛 TypeError。
     用户看到的是一句无从翻译的类型错误，而不是「页面尚未连接到 AstrBot」。 */
  const {product} = harness();
  await assert.rejects(() => product.bridgeFor(), error => {
    assert.strictEqual(error.code, "bridge_unavailable");
    assert.doesNotMatch(String(error.message), /Cannot read propert|undefined/);
    return true;
  });
});

test("bridgeNow() 在桥缺失时返回假值而不是抛错", () => {
  /* 各页的写法是 `bridgeNow() || await bridgeFor()`，所以它必须是
     「同步看一眼」，不能抛——抛出去就没有等待的机会了。 */
  const {product} = harness();
  assert.ok(!product.bridgeNow());
});

/* === 没有宿主时不该是一块空框 ===
 *
 * 用户报的现象：「就算没有宿主也不该是现在这个鬼样子」。截图里「宿主管理」
 * 页是一整块 900px 高、带边框、里面什么都没有的方框。
 *
 * 根因：product.workspace() 无条件渲染 iframe，而填它内容的 mountWorkspace()
 * 只在桥可用时执行。桥不在 → iframe 留在那里永不加载。空框不表达任何东西：
 * 它不说明发生了什么，也不给下一步。
 *
 * 这跟「UI 全部加载好了小屋才出现」是同一个毛病的两个面：把「缺数据」
 * 当成「可以照常渲染」。
 */
function productWith(opts = {}) {
  const {bridge = null, catalog = null, loading = false, role = null} = opts;
  const window = {
    addEventListener() {}, removeEventListener() {},
    matchMedia: () => ({matches: false, addEventListener() {}}),
    location: {hash: "", href: "http://localhost/#life"},
    history: {replaceState() {}}, innerWidth: 1440, innerHeight: 900,
    requestAnimationFrame: callback => { callback(0); return 0; }, cancelAnimationFrame() {},
    /* 四个工作区都要在：只给 host 的话，其余三个会先命中断言
       「工作区资源未发布」，测不到本次要守的那条分支。 */
    CompanionWorkspaceBundle: {host: "<!doctype html><p>host</p>",
      life: "<!doctype html><p>life</p>",
      relationships: "<!doctype html><p>relationships</p>",
      identity: "<!doctype html><p>identity</p>"},
  };
  if (bridge) window.AstrBotPluginPage = bridge;
  const document = {
    readyState: "interactive", documentElement: {dataset: {}},
    head: {appendChild() {}}, body: {classList: {add() {}, remove() {}}},
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: () => ({addEventListener() {}, setAttribute() {}}),
    addEventListener() {},
  };
  vm.runInNewContext(SOURCE, {window, document, navigator: {language: "zh-CN"},
    setTimeout, clearTimeout, Promise, Object, JSON, Array, String, Number, Boolean,
    Math, Date, Error, console, matchMedia: () => ({matches: false}),
    localStorage: {getItem: () => null, setItem() {}, removeItem() {}}});
  return window.CompanionProduct;
}

test("没有宿主目录时不渲染空 iframe，而是给出说明与两个出口", () => {
  const markup = productWith().workspace("host");

  /* 关键断言：不能是 iframe。iframe 的内容由 mountWorkspace() 用 srcdoc 填，
     桥不在时它不会执行，于是留下一块永不加载的空白。 */
  assert.doesNotMatch(markup, /<iframe/, "宿主目录没读到却渲染了 iframe，会得到一块空框");
  assert.match(markup, /角色与会话目录暂未读到/, "应当说清发生了什么");
  assert.match(markup, /data-workspace-retry/, "应当给一个重试出口");
  assert.match(markup, /data-manage="host"/, "应当给一个去宿主管理的出口");
});

test("正在读取时也不先摆空框", () => {
  /* 「正在读取…」配一块 900px 空框，就是截图里那个观感的来源。 */
  const markup = productWith().workspace("host");
  assert.doesNotMatch(markup, /<iframe/);
  assert.match(markup, /正在读取角色与会话|角色与会话目录暂未读到/);
});

test("没有宿主目录时四个工作区都是说明块，没有空框", () => {
  const product = productWith();
  for (const name of ["host", "life", "relationships", "identity"]) {
    const markup = product.workspace(name);
    assert.doesNotMatch(markup, /<iframe/, `${name} 工作区不该渲染空 iframe`);
    assert.match(markup, /data-workspace-retry/, `${name} 工作区应当给重试出口`);
  }
});

test("一个候选拉不到就试下一个，而不是就此放弃", async () => {
  /* 写死一个路径的代价很不对称：猜对了只省一个 404，猜错了整页连不上宿主，
     而症状只是一句「连接失败」。所以按候选依次尝试。 */
  const {product, appended} = harness({readyState: "interactive"});
  product.whenBridgeReady(400).catch(() => {});
  await flush();
  assert.strictEqual(appended.length, 1);

  /* 第一个失败 → 应当自动试第二个。 */
  appended[0]._listeners.error();
  await flush();
  assert.strictEqual(appended.length, 2, "第一个候选失败后应当继续试下一个");
  assert.notStrictEqual(appended[1]._src, appended[0]._src);
});

test("所有候选都试完就停下，不无限重试刷控制台", async () => {
  const {product, appended} = harness({readyState: "interactive"});
  product.whenBridgeReady(3000).catch(() => {});
  await flush();

  /* 依次让每个候选失败，直到不再新增。 */
  for (let guard = 0; guard < 8 && appended.length; guard += 1) {
    const last = appended[appended.length - 1];
    const before = appended.length;
    last._listeners.error();
    await flush();
    if (appended.length === before) break;
  }
  const settled = appended.length;
  assert.ok(settled >= 2 && settled <= 4, `候选数量应当有限，实际试了 ${settled} 个`);

  /* 再触发等待器的下一拍，也不该继续插。 */
  await flush();
  await flush();
  assert.strictEqual(appended.length, settled, "候选用尽后不该继续插入");
});
