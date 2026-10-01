"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "../pages/陪伴小屋");
const SOURCE = fs.readFileSync(path.join(ROOT, "image-materials-page.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "output-page.css"), "utf8");
const tick = () => new Promise(resolve => setImmediate(resolve));
const ok = data => ({status: "ok", data});
const image = id => ({
  image_id: id, created_at: `2026-10-01T0${id.slice(-1)}:00:00Z`,
  action: "generate", width: 768, height: 1024,
  thumbnail: "data:image/jpeg;base64,ZmFrZQ==",
});

function inventory({enabled = true, label = "已登记参考图", wardrobe = []} = {}) {
  return {
    settings: {
      references: {enabled, daily_outfit_enabled: enabled},
      wardrobe: {enabled},
    },
    references: label ? [{asset_id: "asset-1", label, roles: ["outfit"], state: "active", mime_type: "image/jpeg"}] : [],
    wardrobe,
    daily_outfit: null,
  };
}

function makeNode() {
  const handlers = new Map();
  const submit = {disabled: false};
  const matches = (target, selector) => target?.matches?.(selector) === true;
  const targetFor = (selector, dataset = {}, extra = {}) => ({
    ...extra,
    dataset,
    matches: candidate => candidate === selector,
    closest: candidate => candidate.split(",").map(value => value.trim()).includes(selector) ? target : null,
  });
  let target;
  const node = {
    isConnected: true,
    innerHTML: "",
    addEventListener(type, handler) { handlers.set(type, handler); },
    removeEventListener(type) { handlers.delete(type); },
    contains() { return true; },
    querySelector(selector) { return selector === "[data-im-wardrobe-submit]" ? submit : null; },
    fire(type, next) { target = next; handlers.get(type)?.({type, target}); },
    click(selector, dataset = {}) { node.fire("click", targetFor(selector, dataset)); },
    input(selector, value) { node.fire("input", targetFor(selector, {}, {value})); },
    change(selector, dataset = {}, extra = {}) { node.fire("change", targetFor(selector, dataset, extra)); },
    submit,
  };
  return node;
}

function harness({role = () => ({image_material_api: "image-materials"}), scope = () => "scope-a", response} = {}) {
  const requests = [];
  const deferred = [];
  const product = {
    scopeKey: scope,
    role,
    relative: path => path,
    bridgeNow: () => bridge,
  };
  const bridge = {
    apiGet(pathname, query) {
      const request = {method: "GET", pathname, query};
      requests.push(request);
      return response ? response(request) : Promise.resolve(ok(pathname.endsWith("/album") ? {items: [], next_cursor: null} : inventory({label: "默认"})));
    },
    apiPost(pathname, body) {
      const request = {method: "POST", pathname, body};
      requests.push(request);
      return response ? response(request) : Promise.resolve(ok({}));
    },
  };
  const context = {
    window: {CompanionProduct: product, crypto: {randomUUID: () => `uuid-${requests.length}`}},
    console, AbortController, setTimeout, clearTimeout, Promise, Math, Date, Error,
    Object, String, Array, Set, JSON,
  };
  vm.runInNewContext(SOURCE, context, {filename: "image-materials-page.js"});
  return {page: context.window.CompanionImageMaterialsPage, node: makeNode(), requests, deferred, product};
}

test("未绑定角色只显示等待绑定，不发素材请求", () => {
  const fixture = harness({role: () => null, scope: () => ""});
  fixture.page.mount(fixture.node);
  assert.match(fixture.node.innerHTML, /等待私聊角色绑定/);
  assert.equal(fixture.requests.length, 0);
});

test("关闭配置时参考图和衣柜控件保持禁用，路由使用插件内相对地址", async () => {
  const fixture = harness({response: request => Promise.resolve(ok(
    request.pathname.endsWith("/album") ? {items: [image("img-1")], next_cursor: null} : inventory({enabled: false}),
  ))});
  fixture.page.mount(fixture.node);
  await tick();
  fixture.node.click("[data-im-select]", {imSelect: "img-1"});
  assert.match(fixture.node.innerHTML, /data-im-register[^>]*disabled/);
  assert.match(fixture.node.innerHTML, /data-im-wardrobe-submit[^>]*disabled/);
  assert.ok(fixture.requests.every(request => !request.pathname.startsWith("/astrbot_plugin_")));
});

test("角色切换后旧请求不能覆盖新角色", async () => {
  let selected = "a";
  const pending = [];
  const fixture = harness({
    role: () => ({image_material_api: "image-materials"}),
    scope: () => selected,
    response: request => new Promise((resolve, reject) => pending.push({request, resolve, reject})),
  });
  fixture.page.mount(fixture.node);
  selected = "b";
  fixture.page.refresh();
  assert.equal(pending.length, 4);
  pending[2].resolve(ok(inventory({label: "新角色"})));
  pending[3].resolve(ok({items: [image("img-new")], next_cursor: null}));
  await tick();
  pending[0].resolve(ok(inventory({label: "旧角色"})));
  pending[1].resolve(ok({items: [image("img-old")], next_cursor: null}));
  await tick();
  assert.match(fixture.node.innerHTML, /新角色/);
  assert.doesNotMatch(fixture.node.innerHTML, /旧角色/);
  assert.doesNotMatch(fixture.node.innerHTML, /img-old/);
});

test("相册分页、参考登记、撤回、衣柜和每日穿搭均沿用当前角色路由", async () => {
  const posted = [];
  let albumPage = 0;
  let current = inventory({label: "穿搭参考"});
  current.wardrobe = [{item_id: "item-1", name: "米白针织衫", tags: ["日常"], state: "active", asset_id: "asset-1"}];
  const fixture = harness({response: request => {
    if (request.method === "GET" && request.pathname.endsWith("/album")) {
      albumPage += 1;
      return Promise.resolve(ok(albumPage === 1 ? {items: [image("img-1")], next_cursor: "cursor-1"} : {items: [image("img-2")], next_cursor: null}));
    }
    if (request.method === "GET") return Promise.resolve(ok(current));
    posted.push(request);
    if (request.pathname.endsWith("/references")) current.references = [{asset_id: "asset-1", label: "新参考", roles: ["outfit"], state: "active", mime_type: "image/jpeg"}];
    if (request.pathname.endsWith("/daily-outfit")) current.daily_outfit = {item_id: "item-1", name: "米白针织衫"};
    return Promise.resolve(ok({}));
  }});
  fixture.page.mount(fixture.node);
  await tick();
  assert.match(fixture.node.innerHTML, /读取更早的产出/);
  fixture.node.click("[data-im-load-more]");
  await tick();
  assert.match(fixture.node.innerHTML, /img-2/);
  fixture.node.click("[data-im-select]", {imSelect: "img-1"});
  fixture.node.input("[data-im-reference-label]", "新参考");
  fixture.node.click("[data-im-register]");
  await tick();
  assert.equal(posted[0].pathname, "image-materials/references");
  assert.deepEqual([...posted[0].body.roles], ["identity"]);
  fixture.node.click("[data-im-withdraw-ref]", {imWithdrawRef: "asset-1"});
  await tick();
  fixture.node.input("[data-im-wardrobe-name]", "米白针织衫");
  assert.equal(fixture.node.submit.disabled, false);
  fixture.node.click("[data-im-wardrobe-submit]");
  await tick();
  fixture.node.click("[data-im-daily]", {imDaily: "item-1"});
  await tick();
  assert.deepEqual(posted.map(item => item.pathname), [
    "image-materials/references", "image-materials/references/withdraw",
    "image-materials/wardrobe", "image-materials/daily-outfit",
  ]);
  assert.ok(posted.every(item => item.body == null || item.body.operation_key || item.pathname.endsWith("/withdraw") || item.pathname.endsWith("/daily-outfit")));
});

test("后端错误码翻译成页面提示，窄屏样式收拢为单列", async () => {
  const fixture = harness({response: request => {
    if (request.method === "GET" && request.pathname.endsWith("/album")) return Promise.resolve(ok({items: [image("img-1")], next_cursor: null}));
    if (request.method === "GET") return Promise.resolve(ok(inventory()));
    return Promise.reject(Object.assign(new Error("photo_reference_disabled"), {code: "photo_reference_disabled"}));
  }});
  fixture.page.mount(fixture.node);
  await tick();
  fixture.node.click("[data-im-select]", {imSelect: "img-1"});
  fixture.node.click("[data-im-register]");
  await tick();
  assert.match(fixture.node.innerHTML, /参考图功能当前关闭/);
  assert.match(CSS, /@media\(max-width:900px\)\s*\{\s*\.image-materials-columns\{grid-template-columns:minmax\(0,1fr\)\}/);
  assert.match(CSS, /@media\(max-width:620px\)/);
});
