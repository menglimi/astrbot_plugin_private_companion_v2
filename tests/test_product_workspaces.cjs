/* Embedded workspaces share a page, but never a response channel or scope. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const HOST = "astrbot_plugin_private_companion_v2";
const source = fs.readFileSync(path.join(__dirname, "../pages/陪伴小屋/product-page.js"), "utf8");
const relationshipApi = "host/targets/first/roles/role-first/relationships";

async function harness(savedTheme = null) {
  const events = {}, calls = [], frames = [];
  const contextHandlers = new Set();
  let pending = null;
  const catalog = {
    mode: "multi", installation_id: "synthetic", acquaintance_api: "/" + HOST + "/acquaintance",
    targets: [{target_id: "first", scope_kind: "private", participant_id: "synthetic-person",
      roles: [{role_id: "synthetic-role", relationships_api: "/" + HOST + "/" + relationshipApi}]}],
  };
  const window = {
    addEventListener(type, handler) { events[type] = handler; },
    matchMedia: () => ({matches: false}),
    CompanionWorkspaceBundle: {identity: "<p>directory</p>", relationships: "<p>relationship</p>"},
    AstrBotPluginPage: {
      ready: async () => ({pluginName: HOST}),
      onContext(handler) { contextHandlers.add(handler); return () => contextHandlers.delete(handler); },
      apiGet: async (endpoint, params) => {
        calls.push({method: "GET", endpoint, params});
        if (pending && endpoint === relationshipApi) return pending.promise;
        if (endpoint === "page/targets") return catalog;
        if (endpoint === "integration/manifest") return {providers: [], summary: {connected_count: 0}};
        return {items: []};
      },
      apiPost: async (endpoint, body) => { calls.push({method: "POST", endpoint, body}); return {}; },
    },
  };
  const document = {
    readyState: "interactive", documentElement: {dataset: {}},
    head: {appendChild() {}}, body: {classList: {add() {}, remove() {}}},
    querySelector: () => null,
    querySelectorAll: selector => selector === ".product-workspace-frame" ? frames : [],
    createElement: () => ({addEventListener() {}, setAttribute() {}}), addEventListener() {},
  };
  vm.runInNewContext(source, {window, document, navigator: {language: "zh-CN"},
    setTimeout, clearTimeout, matchMedia: () => ({matches: false}),
    localStorage: {getItem: key => key === "companion-v2-theme" ? savedTheme : null, setItem() {}, removeItem() {}}});
  const product = window.CompanionProduct;
  await product.connect();
  calls.length = 0;
  function addFrame(kind) {
    const messages = [];
    const owner = {isConnected: true, style: {}, srcdoc: "",
      parentElement: {dataset: {workspace: kind, workspaceTab: ""}},
      contentWindow: {postMessage: message => messages.push(message)}, messages};
    frames.push(owner);
    return owner;
  }
  const identity = addFrame("identity"), relationships = addFrame("relationships");
  function request(owner, method, endpoint, requestId = "request-1") {
    return events.message({source: owner.contentWindow, data: {channel: "companion-workspace",
      kind: "request", requestId, method, path: endpoint, body: {}}});
  }
  return {product, calls, identity, relationships, events, request, document,
    hostTheme(isDark) {
      document.documentElement.dataset.theme = isDark ? "dark" : "light";
      for (const handler of contextHandlers) handler({pluginName: HOST, isDark});
    },
    contextHandlers,
    defer() {
      let resolve;
      pending = {promise: new Promise(done => { resolve = done; })};
      return resolve;
    }};
}

test("directory and relationship workspaces both mount and receive appearance updates", async () => {
  const h = await harness();
  assert.match(h.product.workspace("identity"), /product-workspace-frame/,
    "the installation directory does not require an identity_api on a role");
  h.product.mountWorkspace();
  assert.equal(h.identity.srcdoc, "<p>directory</p>");
  assert.equal(h.relationships.srcdoc, "<p>relationship</p>");
  h.product.setAppearance("motion", "off");
  assert.equal(h.identity.messages.at(-1).name, "motion");
  assert.equal(h.relationships.messages.at(-1).name, "motion");
});

test("host context updates preserve the browser theme and synchronize every workspace", async () => {
  const h = await harness("walnut");
  h.product.mountWorkspace();
  h.hostTheme(false);
  assert.equal(h.document.documentElement.dataset.theme, "walnut");
  assert.equal(h.product.appearance().theme, "walnut");
  assert.equal(h.identity.messages.at(-1).appearance.theme, "walnut");
  assert.equal(h.relationships.messages.at(-1).appearance.theme, "walnut");
  h.hostTheme(true);
  assert.equal(h.document.documentElement.dataset.theme, "walnut");
  await h.product.connect();
  assert.equal(h.contextHandlers.size, 1, "reconnecting replaces the context subscription");
});

test("each workspace sends requests only to its own API and response channel", async () => {
  const h = await harness();
  h.product.mountWorkspace();
  await h.request(h.identity, "GET", "acquaintance", "directory-request");
  await h.request(h.relationships, "GET", "relationships", "relationship-request");
  assert.deepEqual(h.calls.map(call => call.endpoint), ["acquaintance", relationshipApi]);
  assert.equal(h.identity.messages.at(-1).requestId, "directory-request");
  assert.equal(h.relationships.messages.at(-1).requestId, "relationship-request");
  await h.request(h.identity, "POST", "acquaintance");
  await h.request(h.identity, "GET", "relationships");
  assert.equal(h.calls.length, 2, "a read-only directory cannot relay mutation or relationship requests");
  assert.equal(h.identity.messages.at(-1).ok, false);
  await h.events.message({source: {}, data: {channel: "companion-workspace", kind: "request",
    requestId: "unrelated", method: "GET", path: "acquaintance", body: {}}});
  assert.equal(h.calls.length, 2, "messages from unrelated frames are ignored");
});

test("a response from a previous mount cannot enter the replacement workspace", async () => {
  const h = await harness();
  h.product.mountWorkspace();
  const resolve = h.defer();
  const request = h.request(h.relationships, "GET", "relationships");
  h.product.unmountWorkspace();
  h.product.mountWorkspace();
  resolve({items: [{title: "old scope"}]});
  await request;
  assert.equal(h.relationships.messages.length, 0);
  assert.equal(h.identity.messages.length, 0);
});

/* 相识详情页的授权面板要写，而这一页的主要通道是只读的。放行的必须是**它自己的
   那一个地址**，而不是"identity 工作区从此可以写"：地址放错会让面板上的按钮
   静默变成 invalid_response（用户看到的是"点了没反应"）。
   endpoint 与目录一样是**插件内相对路径**（前导斜杠与目录名都剥掉），
   这是桥自己的口径，别处（reply-page 等）也照这一条。 */
test("the identity workspace may relay its own authorization write and nothing else", async () => {
  const h = await harness();
  h.product.mountWorkspace();
  await h.request(h.identity, "POST", "acquaintance/authorization", "authorization-write");
  assert.deepEqual(h.calls.map(call => call.method + " " + call.endpoint),
    ["POST acquaintance/authorization"],
    "授权写入要落到目录端点族下的第二段，而不是目录本身");
  assert.equal(h.identity.messages.at(-1).ok, true);
  assert.equal(h.identity.messages.at(-1).requestId, "authorization-write");
  // 读也要能走那个地址（面板先读再写），但别的地址一律不放行。
  await h.request(h.identity, "GET", "acquaintance/authorization", "authorization-read");
  assert.deepEqual(h.calls.map(call => call.method + " " + call.endpoint),
    ["POST acquaintance/authorization", "GET acquaintance/authorization"]);
  for (const [method, path] of [["POST", "acquaintance"], ["GET", "acquaintance/command"],
                                ["POST", "acquaintance/authorization/extra"]]) {
    await h.request(h.identity, method, path, "rejected-" + method + path);
    assert.equal(h.identity.messages.at(-1).ok, false, method + " " + path + " 不该被放行");
  }
  assert.equal(h.calls.length, 2, "被拒的请求不许真的发出去");
});
