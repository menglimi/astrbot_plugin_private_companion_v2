"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../pages/陪伴小屋/output-page.js"), "utf8");
const selectors = [
  '[data-output-content-stat="works"]',
  '[data-output-content-stat="candidates"]',
  '[data-output-content-stat="updated"]',
  "[data-output-content-preview]",
  "[data-output-content-preview-count]",
  "[data-output-content-preview-updated]",
];

function fixture() {
  const nodes = new Map(selectors.map(selector => [selector, [{textContent: "初始值"}]]));
  const requests = [];
  let observabilityFailure = false;
  const role = {model_api: "model", image_material_api: "image-materials"};
  const window = {
    CompanionProduct: {
      scopeKey: () => "role-a",
      role: () => role,
      relative: value => value,
      async request(method, endpoint) {
        requests.push({method, endpoint});
        if (endpoint === "model/image/observability") {
          if (observabilityFailure) throw Object.assign(new Error("network failed"), {code: "network_error"});
          return {images: {total: 1, items: []}, content: {available: true, works_count: 2,
            candidate_count: 1, updated_at: "2026-10-12T04:05:00Z"}};
        }
        if (endpoint === "model/image/output") return {settings: {backend: "auto", enabled: false,
          endpoints: [], comfyui: {}, sd_webui: {}}, revision: "r1", host_registered: false};
        if (endpoint === "model/image/review/providers") return {providers: []};
        if (endpoint === "image-materials/album") return {items: []};
        throw new Error(`unexpected request: ${method} ${endpoint}`);
      },
    },
    dispatchEvent() {},
  };
  const root = {
    isConnected: true,
    addEventListener() {},
    removeEventListener() {},
    querySelector() {return null;},
    querySelectorAll(selector) {return nodes.get(selector) || [];},
  };
  const context = {window, console, AbortController, Event, setTimeout, clearTimeout, Promise, Math, Date, JSON,
    Object, String, Array, Map, Set, Error};
  vm.runInNewContext(source, context, {filename: "output-page.js"});
  return {page: window.CompanionOutputPage, nodes, requests, root,
    failObservability(value) {observabilityFailure = value;}};
}

test("Content summary renders real counts and clears stale values after a failed reread", async () => {
  const state = fixture();
  state.page.mount(state.root);
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(state.nodes.get('[data-output-content-stat="works"]')[0].textContent, "2");
  assert.equal(state.nodes.get('[data-output-content-stat="candidates"]')[0].textContent, "1");
  assert.match(state.nodes.get("[data-output-content-preview]")[0].textContent, /2 部已关联作品 · 1 份续写候选稿/);
  assert.ok(state.requests.some(request => request.endpoint === "model/image/observability"));

  state.failObservability(true);
  await state.page.refreshObservability();
  assert.equal(state.nodes.get('[data-output-content-stat="works"]')[0].textContent, "—");
  assert.equal(state.nodes.get('[data-output-content-stat="candidates"]')[0].textContent, "—");
  assert.equal(state.nodes.get("[data-output-content-preview]")[0].textContent, "Content 作品数据暂不可用");

  state.page.unmount();
});
