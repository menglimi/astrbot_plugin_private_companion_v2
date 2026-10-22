"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "pages", "陪伴小屋", "role-profile-migration.js"), "utf8");
const HOST = "astrbot_plugin_private_companion";
const flush = () => new Promise(resolve => setTimeout(resolve, 0));
async function settleUntil(predicate) {
  for (let index = 0; index < 50 && !predicate(); index++) await flush();
  assert.equal(predicate(), true, "page action did not settle");
}

function harness({storageThrows = false, replies = []} = {}) {
  const listeners = new Map();
  const requests = [];
  const events = [];
  const planRequests = [];
  const values = new Map();
  const notice = {textContent: "", dataset: {}};
  const apply = {disabled: true, textContent: ""};
  const dialog = {open: false, showModal() { this.open = true; }, close() { this.open = false; }};
  const nodes = {
    "#roleProfileMigrationDialog": dialog,
    "[data-role-profile-migration-notice]": notice,
    "[data-role-profile-migration-output]": {hidden: true},
    "[data-role-profile-migration-counts]": {innerHTML: ""},
    "[data-role-profile-migration-fields]": {innerHTML: ""},
    "[data-role-profile-migration-apply]": apply,
    "[data-role-profile-migration-footer]": {textContent: ""},
  };
  const plan = {plan_token: "a".repeat(64), edit_token: "b".repeat(64),
    changes: {name: "澄溪"}, counts: {to_import: 1}, source: {name: "测试来源"}};
  const bridge = {
    apiGet: async () => ({status: "ok", data: {persona: {persona_id: "persona-a"}}}),
    apiPost: async (endpoint, body) => {
      planRequests.push({endpoint, body});
      return {status: "ok", data: plan};
    },
  };
  const product = {
    identity: () => ({installation_id: "install-a", operator_id: "operator-a"}),
    scopeKey: () => "scope-a",
    role: () => ({persona_api: `/${HOST}/targets/target-a/roles/role-a/persona`}),
    bridgeNow: () => bridge,
    relative: value => value.replace(new RegExp(`^/${HOST}/`), ""),
    unwrap: value => value?.data ?? value,
    request: async (method, endpoint, body) => {
      requests.push({method, endpoint, body: JSON.parse(JSON.stringify(body))});
      const response = replies.shift();
      if (response instanceof Error) throw response;
      return typeof response === "function" ? response() : response;
    },
  };
  const document = {
    addEventListener: (name, callback) => listeners.set(name, callback),
    querySelector: selector => nodes[selector] || null,
    dispatchEvent: event => events.push(event.type),
  };
  const sessionStorage = {
    setItem(key, value) {
      if (storageThrows) throw new Error("storage disabled");
      values.set(key, value);
    },
    getItem: key => values.get(key) || null,
    removeItem: key => values.delete(key),
  };
  const window = {CompanionProduct: product,
    CompanionConfigEditors: {spec: {role_profile: {labels: {name: "姓名"}}}},
    lucide: {createIcons() {}}};
  const context = vm.createContext({window, document, sessionStorage, Event: class Event { constructor(type) { this.type = type; } },
    setTimeout, clearTimeout, console});
  vm.runInContext(source, context);

  async function click(selector) {
    listeners.get("click")({
      target: {
        closest: value => value === selector ? {} : null,
        matches: () => false,
      },
      preventDefault() {},
    });
  }
  return {click, apply, dialog, events, notice, planRequests, requests, values, settleUntil};
}

test("迁入成功会清除待确认记录并通知档案编辑器刷新", async () => {
  const h = harness({replies: [{operation_id: "operation-a", replayed: false, imported_count: 1}]});

  await h.click("[data-role-profile-migrate-open]");
  await h.settleUntil(() => h.planRequests.length === 1);
  assert.equal(h.planRequests.length, 1);
  await h.click("[data-role-profile-migration-apply]");
  await h.settleUntil(() => h.notice.textContent.includes("已迁入"));

  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].endpoint.endsWith("/profile-migration-apply"), true);
  assert.equal(h.values.size, 0);
  assert.deepEqual(h.events, ["companion:role-profile-updated"]);
  assert.match(h.notice.textContent, /已迁入 1 项角色档案/);
});

test("会话存储失败不阻断迁入，未知结果核对时复用同一请求", async () => {
  const unknown = new Error("request timed out");
  const h = harness({storageThrows: true, replies: [unknown,
    {operation_id: "operation-a", replayed: true, imported_count: 1}]});

  await h.click("[data-role-profile-migrate-open]");
  await h.settleUntil(() => h.planRequests.length === 1);
  await h.click("[data-role-profile-migration-apply]");
  await h.settleUntil(() => h.notice.textContent.includes("当前页面仍保留原请求"));

  assert.equal(h.requests.length, 1, "storage failure must not prevent the first POST");
  assert.match(h.notice.textContent, /当前页面仍保留原请求/);
  assert.equal(h.apply.textContent, "核对迁入结果");
  assert.equal(h.apply.disabled, false);
  const originalBody = h.requests[0].body;

  await h.click("[data-role-profile-migration-close]");
  await h.click("[data-role-profile-migrate-open]");
  assert.equal(h.planRequests.length, 1, "reopening the dialog must keep the in-memory request");
  assert.equal(h.apply.textContent, "核对迁入结果");
  await h.click("[data-role-profile-migration-apply]");
  await h.settleUntil(() => h.notice.textContent.includes("已确认原迁入"));

  assert.equal(h.requests.length, 2);
  assert.deepEqual(h.requests[1].body, originalBody);
  assert.equal(h.planRequests.length, 1, "verification must reuse the original plan");
  assert.deepEqual(h.events, ["companion:role-profile-updated"]);
});
