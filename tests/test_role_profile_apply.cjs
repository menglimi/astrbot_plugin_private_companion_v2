const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../pages/陪伴小屋/role-profile-draft.js"), "utf8");
const testSource = source.replace("return {markup, open: openDialog, isDirty};",
  "return {markup, open: openDialog, isDirty, recoverPendingApply, restorePendingApply, storePendingApply, get state() { return state; }};");
assert.notEqual(testSource, source, "test seam must match the private module return");

function harness(sessionStore, outcomes) {
  const calls = [], notices = [], events = [];
  const dialog = {open: true, querySelector: () => null, querySelectorAll: () => []};
  const noticeNode = {textContent: "", dataset: {}};
  const document = {
    querySelector(selector) {
      if (selector === "#roleProfileDraftDialog") return dialog;
      if (selector === "[data-role-profile-draft-notice]") return noticeNode;
      return null;
    },
    querySelectorAll: () => [],
    addEventListener() {},
    dispatchEvent(event) { events.push(event.type); },
  };
  const window = {
    CompanionProduct: {
      identity: () => ({installation_id: "installation-a", operator_id: "operator-a"}),
      scopeKey: () => "target-a:role-a",
      role: () => ({config_api: "config"}),
      relative: value => value,
      request: async (method, endpoint, body) => {
        calls.push({method, endpoint, body: body && JSON.parse(JSON.stringify(body))});
        if (method === "GET") throw new Error("status read unavailable");
        return outcomes.shift()();
      },
    },
  };
  vm.runInNewContext(testSource, {
    window, document, sessionStorage: {
      getItem: key => sessionStore.has(key) ? sessionStore.get(key) : null,
      setItem: (key, value) => sessionStore.set(key, String(value)),
      removeItem: key => sessionStore.delete(key),
    },
    Event: class { constructor(type) { this.type = type; } },
    setTimeout, clearTimeout, Math, JSON, Object, Array, String, Number, Set, Map, Error, Promise,
  });
  return {module: window.CompanionRoleProfileDraft, calls, notices, events, noticeNode};
}

test("an unknown role-profile save survives reload and confirms by replaying the same request", async () => {
  const sessionStore = new Map();
  const pending = {target: "role_profile", scopeKey: "target-a:role-a", endpoint: "config/configure",
    skipped_count: 0, body: {section: "role_profile", operation_key: "stable-operation",
      edit_token: "e".repeat(64), changes: {name: "小伴"}}};
  const first = harness(sessionStore, [() => Promise.reject(Object.assign(new Error("timeout"), {code: "bridge_timeout"}))]);
  first.module.state.target = pending.target;
  first.module.state.scopeKey = pending.scopeKey;
  first.module.state.pendingApply = pending;
  assert.equal(first.module.storePendingApply(pending), true);

  await first.module.recoverPendingApply();
  assert.deepEqual(first.calls[0], {method: "POST", endpoint: pending.endpoint, body: pending.body});
  assert.equal(first.module.state.pendingApply.body.operation_key, "stable-operation");
  assert.match(first.noticeNode.textContent, /保存结果尚未确认/);

  const second = harness(sessionStore, [() => Promise.resolve({result: {
    operation_id: "stored-operation", replayed: true,
  }})]);
  second.module.state.target = pending.target;
  second.module.state.pendingApply = second.module.restorePendingApply(
    pending.target, pending.scopeKey, pending.endpoint);
  assert.equal(second.module.state.pendingApply.body.operation_key, "stable-operation");
  await second.module.recoverPendingApply();

  const posts = second.calls.filter(call => call.method === "POST");
  assert.equal(posts.length, 1);
  assert.deepEqual(posts[0].body, pending.body);
  assert.equal(second.module.state.pendingApply, null);
  assert.equal(sessionStore.size, 0);
  assert.match(second.noticeNode.textContent, /原保存已确认/);
  assert.match(second.noticeNode.textContent, /未能刷新/);
  assert.doesNotMatch(second.noticeNode.textContent, /保存结果尚未确认/);
  assert.deepEqual(second.events, ["companion:role-profile-updated"]);
});

test("a confirmed role-profile rejection clears the recoverable request", async () => {
  const sessionStore = new Map();
  const pending = {target: "role_profile", scopeKey: "target-a:role-a", endpoint: "config/configure",
    body: {section: "role_profile", operation_key: "rejected-operation",
      edit_token: "f".repeat(64), changes: {name: "小伴"}}};
  const app = harness(sessionStore, [() => Promise.reject(Object.assign(new Error("revision changed"), {
    code: "configuration_revision_conflict", confirmed: true,
  }))]);
  app.module.state.target = pending.target;
  app.module.state.scopeKey = pending.scopeKey;
  app.module.state.pendingApply = pending;
  app.module.storePendingApply(pending);

  await app.module.recoverPendingApply();
  assert.equal(app.module.state.pendingApply, null);
  assert.equal(sessionStore.size, 0);
  assert.match(app.noticeNode.textContent, /刚刚更新过/);
});
