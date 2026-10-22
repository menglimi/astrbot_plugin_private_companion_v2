"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../pages/陪伴小屋/reality-access.js"), "utf8");
const prefix = "/astrbot_plugin_private_companion";
const capabilities = new Map([
  ["", "reality.snapshot.read"],
  ["/camera", "reality.camera.observe"],
  ["/device-list", "reality.device.list"],
  ["/device-status", "reality.device.status"],
  ["/device-control", "reality.device.control"],
  ["/device-action", "reality.device.action"],
  ["/operation-lookup", "reality.operation.lookup"],
  ["/operation-cancel", "reality.operation.cancel"],
]);
const flush = () => new Promise(resolve => setImmediate(resolve));
const settle = async () => { for (let i = 0; i < 12; i += 1) await flush(); };

test("只读账号能读取 Reality 状态，但看不到会被 CORE 权限拒绝的授权按钮", async () => {
  const calls = [];
  const node = {
    innerHTML: "", isConnected: true, listeners: {},
    addEventListener(name, fn) { this.listeners[name] = fn; },
    removeEventListener(name) { delete this.listeners[name]; },
  };
  const product = {
    hosted: () => true,
    role: () => ({reality_access_api: prefix + "/reality-access"}),
    relative(value) {
      if (typeof value !== "string" || !value.startsWith(prefix)) throw new Error("invalid route");
      return value.slice(prefix.length);
    },
    scopeKey: () => "install-a:target-a:role-a",
    scopeLabel: () => "当前私聊窗口",
    async request(method, route) {
      calls.push({method, route});
      const suffix = route.slice("/reality-access".length);
      return {action: capabilities.get(suffix), invokable: false, consented: false,
        can_manage: false, edit_token: "edit-a", reason: "capability_not_installed"};
    },
  };
  const window = {CompanionProduct: product};
  vm.runInNewContext(source, {window, Promise, Map, Set, String, Object, JSON});
  window.CompanionRealityAccess.mount(node);
  await settle();

  assert.equal(calls.length, capabilities.size);
  assert.ok(calls.every(call => call.method === "GET"));
  assert.equal((node.innerHTML.match(/只读/g) || []).length, capabilities.size);
  assert.match(node.innerHTML, /当前账号没有管理此授权的权限/);
  assert.doesNotMatch(node.innerHTML, /data-reality-access-action="(?:mobile|camera|deviceList|deviceStatus|deviceControl|deviceAction|operationLookup|operationCancel)-enable"/);
});
