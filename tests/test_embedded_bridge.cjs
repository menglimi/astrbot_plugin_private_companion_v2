"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const SOURCE = fs.readFileSync(path.join(__dirname, "../pages/陪伴小屋/embedded-bridge.js"), "utf8");

function harness() {
  const messages = [], timers = [];
  let onMessage;
  const parent = {postMessage(message) { messages.push(message); }};
  const window = {
    parent,
    addEventListener(type, handler) { if (type === "message") onMessage = handler; },
  };
  const document = {addEventListener() {}};
  const setTimeout = (callback, ms) => {
    const timer = {callback, ms, cleared: false};
    timers.push(timer);
    return timer;
  };
  const clearTimeout = timer => { if (timer) timer.cleared = true; };
  vm.runInNewContext(SOURCE, {window, document, parent, setTimeout, clearTimeout,
    Promise, Map, Number, Math, Object, String, CustomEvent: class {}});
  messages.length = 0;
  return {window, parent, messages, timers, respond: data => onMessage({source: parent, data})};
}

test("embedded workspace carries a migration timeout through the host bridge", async () => {
  const h = harness();
  const pending = h.window.AstrBotPluginPage.apiGet("setup/data-plan", {}, {timeoutMs: 300000});
  assert.equal(h.messages[0].timeoutMs, 300000);
  assert.equal(h.timers[0].ms, 301000, "the child leaves room for the host's five-minute response");
  h.respond({channel: "companion-workspace", kind: "response", requestId: "workspace-1",
    ok: true, data: {state: "ready"}});
  assert.deepEqual(await pending, {state: "ready"});
  assert.equal(h.timers[0].cleared, true);
});

test("ordinary embedded requests keep their short default and timeout input is capped", () => {
  const h = harness();
  void h.window.AstrBotPluginPage.apiGet("setup/status");
  assert.equal(h.messages[0].timeoutMs, 18000);
  assert.equal(h.timers[0].ms, 19000);

  const capped = harness();
  void capped.window.AstrBotPluginPage.apiGet("setup/plan", {}, {timeoutMs: 900000});
  assert.equal(capped.messages[0].timeoutMs, 300000);
  assert.equal(capped.timers[0].ms, 301000);
});

test("an embedded timeout carries an explicit ambiguous transport code", async () => {
  const h = harness();
  const pending = h.window.AstrBotPluginPage.apiPost("acquaintance/settings", {}, {timeoutMs: 60000});
  h.timers[0].callback();
  await assert.rejects(pending, error => error.code === "bridge_timeout" && error.confirmed === false);
});
