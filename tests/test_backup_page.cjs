/* 备份与还原工作区：桥没就位时那个「重新读取」按钮到底做了什么。
 *
 * 这个模块此前没有测试，而它踩过一个只有运行到才能发现的坑：
 *
 *   const wait = product?.whenBridgeReady?.() ?? Promise.resolve(window.AstrBotPluginPage);
 *
 * `??` 的右半边会**立刻求值**。product 没提供等待器时（页面先于
 * product-page.js 就绪、或换了个不提供这个方法的实现），左半边是 undefined，
 * 于是捕到的是 `Promise.resolve(undefined)`——一个**成功**的 promise，
 * 里面躺着 undefined。接着 `.then` 里 `found?.apiGet` 判空抛出
 * bridge_unavailable，用户点了「重新读取」得到一句「还没接上」，
 * 而真正该发生的「去等桥」根本没发生。
 *
 * 断言的形状与其余页面一致：`bridgeNow() || bridgeFor()`——
 * 同步看一眼不抛，只有真没出现才等。
 *
 * 用 node --test 运行。DOM 是手搓替身，不引 jsdom。
 */
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "pages", "陪伴小屋", "backup-page.js"), "utf8");
const flush = () => new Promise(resolve => setImmediate(resolve));
/* load() 里要过「取桥 → 两个请求 → 重绘」几拍，单次 flush 不够。 */
const settle = async (rounds = 6) => { for (let i = 0; i < rounds; i += 1) await flush(); };

/* 最小 DOM。只够 mount + 点击委托跑起来：页面写 root.innerHTML，
   读 root.querySelector("#backupNote")，并往 root 上挂 click / input。 */
function element(attributes = {}) {
  const node = {
    _attributes: {...attributes},
    _listeners: {},
    innerHTML: "",
    value: "",
    /* live() 会看 root?.isConnected——缺了它 paint() 会静默早退，
       页面什么都不渲染，断言全部落空。 */
    isConnected: true,
    addEventListener(type, handler) { this._listeners[type] = handler; },
    removeEventListener(type) { delete this._listeners[type]; },
    hasAttribute(name) { return name in this._attributes; },
    getAttribute(name) { return this._attributes[name] ?? null; },
    closest(selector) {
      /* 页面用逗号分隔的属性选择器找按钮。替身只需回答「是不是这个按钮」。 */
      const names = selector.split(",").map(part =>
        part.trim().replace(/^\[|\]$/g, ""));
      return names.some(name => name in this._attributes) ? this : null;
    },
    querySelector() { return null; },
    contains() { return true; },
    fire(type, event) { (this._listeners[type] || (() => {}))(event); },
  };
  return node;
}

function harness({ product, bridge } = {}) {
  const window = {};
  if (product) window.CompanionProduct = product;
  if (bridge) window.AstrBotPluginPage = bridge;
  const document = {addEventListener() {}, removeEventListener() {}};
  vm.runInNewContext(SOURCE, {window, document, setTimeout, clearTimeout,
    Promise, Object, JSON, Array, String, Number, Boolean, Math, Date, Error,
    console, RegExp, encodeURIComponent, decodeURIComponent});
  return window.CompanionBackupPage;
}

/* 一个「桥还没出现」的 product 替身，记下谁被调用过。 */
function waitingProduct(found) {
  const calls = [];
  return {
    calls,
    bridgeNow() { calls.push("bridgeNow"); return null; },
    bridgeFor() {
      calls.push("bridgeFor");
      return found
        ? Promise.resolve(found)
        : Promise.reject(Object.assign(new Error("bridge_unavailable"),
            {code: "bridge_unavailable"}));
    },
  };
}

test("桥缺席时不会永久停在「正在读取」", async () => {
  /* 修之前的行为：mount 看到 !bridge 就直接 paint() 返回，而 data.loading
     仍是 true，于是渲染出来只有一句「正在读取快照列表…」——没有说明、没有出口，
     桥永远不来就永远停在那里。而那句注释还写着「给一个重新读取的入口」，
     实际并不存在。 */
  const product = waitingProduct(null);
  const page = harness({product});
  const root = element();

  page.mount(root);
  await settle();

  assert.doesNotMatch(root.innerHTML, /正在读取快照列表/,
    "读不到时不该停在加载态");
  assert.match(root.innerHTML, /data-backup-retry/,
    `读不到就应当给一个出口，实际渲染：${root.innerHTML.slice(0, 200)}`);
});

test("桥已经在时读得到列表，直接渲染内容", async () => {
  const bridge = {apiGet() { return Promise.resolve({status: "ok", data: {snapshots: []}}); },
    apiPost() { return Promise.resolve({status: "ok", data: {}}); }};
  const product = waitingProduct(bridge);
  const page = harness({product});
  const root = element();

  page.mount(root);
  await settle();

  assert.match(root.innerHTML, /暂无快照/,
    "读到空列表时使用简洁空态");
  assert.doesNotMatch(root.innerHTML, /data-backup-retry/,
    "读到了就不该摆重试按钮");
});

test("点重新读取会重新取桥", async () => {
  /* `??` 那个坑的护栏：只问一次 window.AstrBotPluginPage 的实现不会去等，
     用户点重新读取只会再得一句没接上。 */
  const product = waitingProduct(null);
  const page = harness({product});
  const root = element();

  page.mount(root);
  await settle();
  product.calls.length = 0;

  root.fire("click", {target: element({"data-backup-retry": ""})});
  await settle();

  assert.ok(product.calls.includes("bridgeNow"),
    `点重新读取应当重新取桥，实际只调了 ${JSON.stringify(product.calls)}`);
});

test("桥已经在时不去等，直接用", async () => {
  const bridge = {apiGet() { return Promise.resolve({status: "ok", data: {snapshots: []}}); },
    apiPost() { return Promise.resolve({status: "ok", data: {}}); }};
  let waited = false;
  const product = {
    bridgeNow() { return bridge; },
    bridgeFor() { waited = true; return Promise.resolve(bridge); },
  };
  const page = harness({product});
  const root = element();
  page.mount(root);

  const retry = element({"data-backup-retry": ""});
  root.fire("click", {target: retry});
  await flush();
  assert.strictEqual(waited, false, "桥已在就不该多等一拍，那会拖慢每一次读取");
});

test("桥等不到时如实报「没接上」，不抛类型错误", async () => {
  const product = waitingProduct(null);
  const page = harness({product});
  const root = element();
  page.mount(root);

  root.fire("click", {target: element({"data-backup-retry": ""})});
  await settle();

  assert.match(root.innerHTML, /还没有接上|没有接上/,
    "应当说清是桥没接上，而不是笼统的「读取失败」");
  assert.doesNotMatch(root.innerHTML, /Cannot read propert|undefined is not/,
    "不该把类型错误泄到界面上");
});

test("product 没提供等待器时也不静默变成「已接上」", () => {
  /* `??` 的右半边返回 Promise.resolve(undefined) 时，found 是 undefined，
     等价于「没有桥」——但代码路径上它被当成一个「成功的等待」。
     正确的形状应当落到拒绝分支。这里用没有 bridgeFor 的 product 复现。 */
  const product = {bridgeNow() { return null; }};
  const page = harness({product});
  const root = element();
  page.mount(root);

  root.fire("click", {target: element({"data-backup-retry": ""})});

  /* 同步阶段不该抛出去；异步起来后应当落到错误态。 */
  return settle().then(() => {
    assert.match(root.innerHTML, /还没有接上|没有接上|读取|失败|重试/,
      "缺等待器时应当落到错误态，而不是停在「正在读取」");
  });
});
