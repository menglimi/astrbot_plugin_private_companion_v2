"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../pages/陪伴小屋/weather-source-page.js"), "utf8");
const flush = () => new Promise(resolve => setImmediate(resolve));

function harness() {
  const listeners = {}, confirmations = [];
  const status = {
    settings: {provider: "auto", api_host: "", refresh_minutes: 30},
    actual_provider: "open-meteo", edit_token: "a".repeat(64), has_credential: false,
    credential_kind: "", credential_source: "none", source_state: "ready",
  };
  const bridge = {apiGet: async () => status, apiPost: async () => status};
  const window = {
    CompanionProduct: {bridgeNow: () => bridge, bridgeFor: async () => bridge, scopeKey: () => "role-scope"},
    CompanionConfirm: request => new Promise(resolve => confirmations.push({request, resolve})),
    addEventListener() {},
  };
  const root = {
    isConnected: true, innerHTML: "",
    addEventListener(type, callback) { listeners[type] = callback; },
    removeEventListener(type) { delete listeners[type]; },
    dispatch(type, event) { return listeners[type]?.(event); },
  };
  vm.runInNewContext(source, {window, Promise, Object, String, Number, Error, AbortController, setTimeout, clearTimeout});
  return {window, root, confirmations, page: window.CompanionWeatherSourcePage};
}

test("weather draft confirmation is asynchronous and cancellation preserves the draft", async () => {
  const {page, root, confirmations} = harness();
  page.mount(root);
  await flush();
  root.dispatch("input", {target: {name: "credential", value: "draft-secret"}});

  const canceled = page.canLeave();
  assert.equal(typeof canceled.then, "function");
  assert.equal(confirmations[0].request.title, "天气数据源尚未保存");
  assert.equal(confirmations[0].request.danger, true);
  confirmations[0].resolve(false);
  assert.equal(await canceled, false);
  const accepted = page.canLeave();
  assert.equal(confirmations.length, 2);

  confirmations[1].resolve(true);
  assert.equal(await accepted, true);
  page.unmount();
});
