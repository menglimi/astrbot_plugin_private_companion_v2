"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../pages/陪伴小屋/screen-access.js"), "utf8");
const prefix = "/astrbot_plugin_private_companion_v2";
const flush = () => new Promise(resolve => setImmediate(resolve));
const settle = async () => { for (let i = 0; i < 10; i += 1) await flush(); };

function harness({kind = "private", route = true, request} = {}) {
  const calls = [];
  const target = {scope_kind: kind, target_id: "window-a", bot_id: "bot-a"};
  const node = {
    innerHTML: "", isConnected: true, listeners: {},
    addEventListener(name, fn) { this.listeners[name] = fn; },
    removeEventListener(name) { delete this.listeners[name]; },
    fire(action) {
      this.listeners.click({target: {closest: () => ({dataset: {screenAccessAction: action}})}});
    },
  };
  const product = {
    hosted: () => true,
    target: () => target,
    selection: () => ({role_id: "role-a", target_id: target.target_id}),
    role: () => ({screen_access_api: route ? prefix + "/screen-access" : null}),
    relative(value) {
      if (typeof value !== "string" || !value.startsWith(prefix)) throw new Error("invalid route");
      return value.slice(prefix.length);
    },
    scopeKey: () => JSON.stringify(["install-a", target.target_id, "role-a"]),
    async request(method, path, body) {
      calls.push({method, path, body});
      if (request) return request(method, path, body);
      return method === "GET"
        ? {invokable: false, consented: false, edit_token: "edit-a", reason: "capability_not_installed"}
        : {status: {invokable: body.enabled, consented: body.enabled, edit_token: "edit-b"}};
    },
  };
  const window = {CompanionProduct: product};
  const document = {};
  vm.runInNewContext(source, {window, document, Promise, Map, String, Math, Date, JSON, Object,
    crypto: {randomUUID: () => "operation-a"}});
  window.CompanionScreenAccess.mount(node);
  return {node, calls};
}

test("群聊显示私聊边界，不发送屏幕授权请求", async () => {
  const {node, calls} = harness({kind: "group", route: false});
  await settle();
  assert.match(node.innerHTML, /切换到私聊对象/);
  assert.doesNotMatch(node.innerHTML, /核对中/);
  assert.equal(calls.length, 0);
});

test("私聊目标缺少目录路由时说明下一步", async () => {
  const {node, calls} = harness({route: false});
  await settle();
  assert.match(node.innerHTML, /账号与会话中刷新目标/);
  assert.doesNotMatch(node.innerHTML, /核对中/);
  assert.equal(calls.length, 0);
});

test("缺少原生扩展时指导启用 native_v2 并重载", async () => {
  const {node} = harness({request: async () => {
    throw Object.assign(new Error("screen_provider_unavailable"), {code: "screen_provider_unavailable"});
  }});
  await settle();
  assert.match(node.innerHTML, /启用 native_v2 并重载/);
  assert.match(node.innerHTML, /暂不可用/);
});

test("授权和撤回沿用当前私聊的版本令牌", async () => {
  const {node, calls} = harness();
  await settle();
  assert.match(node.innerHTML, /允许当前私聊按需看屏/);
  node.fire("enable");
  await settle();
  assert.equal(calls[1].method, "POST");
  assert.equal(calls[1].body.enabled, true);
  assert.equal(calls[1].body.edit_token, "edit-a");
  assert.match(node.innerHTML, /撤回当前私聊授权/);
  node.fire("disable");
  await settle();
  assert.equal(calls[2].body.enabled, false);
  assert.equal(calls[2].body.edit_token, "edit-b");
});
