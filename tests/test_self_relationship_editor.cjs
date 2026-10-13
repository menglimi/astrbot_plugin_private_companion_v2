"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../pages/陪伴小屋/self-relationship.js"), "utf8");
const profile = {edit_token: "profile-v1", settings: {default_nickname: "主人", role_relation: "朋友",
  user_gender: "", user_birthday: "", user_occupation: "", interaction: "", extra: ""}};
const contact = {edit_token: "contact-v1", scope: "window", settings: {enabled: true,
  automatic_enabled: false, quiet_enabled: false, note: "", style_prompt: ""}, provenance: {
  enabled: {explicit: false}, automatic_enabled: {explicit: false}, quiet_enabled: {explicit: false},
  note: {explicit: false}, style_prompt: {explicit: false},
}};

function person(subject, changes = {}) {
  return {subject_id: subject, native_account_id: subject, display_name: subject, platform: "qq-main",
    bot_id: "bot-a", account_id: "account-a", role_id: "role-a", private_target: true,
    settings_available: true, identity_tier: "core", ...changes};
}

function harness(persons) {
  const calls = [];
  const listeners = {};
  const saveButton = {disabled: true};
  const status = {textContent: ""};
  const contactStatus = {textContent: ""};
  const root = {innerHTML: "", handlers: {}, addEventListener(type, callback) { this.handlers[type] = callback; },
    querySelector(selector) { return selector.includes("data-self-relationship-action") ? saveButton
      : selector === ".self-contact-settings .self-relationship-actions>span" ? contactStatus
      : selector === ".self-relationship-actions>span" ? status : null; }};
  const product = {
    role: () => ({role_id: "role-a"}), roleTarget: () => ({bot_id: "bot-a"}),
    roleLabel: () => "澄汐", platformLabel: () => "QQ · OneBot",
    acquaintanceDirectory: async () => ({persons}), errorLabel: () => "读取失败。",
    request: async (method, route, body) => {
      calls.push({method, route, body});
      if (method === "GET") return {sections: {profile, contact}};
      const sections = {};
      if (body.sections.profile) sections.profile = {...profile, edit_token: "profile-v2",
        settings: {...profile.settings, ...body.sections.profile.changes}};
      if (body.sections.contact) sections.contact = {...contact, edit_token: "contact-v2",
        settings: {...contact.settings, ...body.sections.contact.changes}, provenance: {
          ...contact.provenance,
          ...Object.fromEntries(Object.keys(body.sections.contact.changes).map(name => [name, {explicit: true}])),
        }};
      return {sections};
    },
  };
  const document = {addEventListener(type, callback) {listeners[type] = callback;}};
  const window = {CompanionProduct: product, crypto: {randomUUID: () => "operation-1"}};
  vm.runInNewContext(source, {window, document, Promise, Date, Math, JSON, Object, String, Map, Set, Array, Error});
  return {root, calls, saveButton, status, contactStatus, mount: window.CompanionSelfRelationship.mount};
}

const settle = async () => { for (let index = 0; index < 8; index++) await new Promise(resolve => setImmediate(resolve)); };

test("核心关系资料按当前角色读取，多位核心用户时明确选择并保存 profile 分区", async () => {
  const h = harness([
    person("core-1"), person("core-2", {account_id: "account-b"}),
    person("other-role", {role_id: "role-b"}), person("regular", {identity_tier: "standard"}),
  ]);
  h.mount(h.root);
  await settle();
  assert.match(h.root.innerHTML, /选择要编辑的核心用户/);
  assert.match(h.root.innerHTML, /core-1/);
  assert.match(h.root.innerHTML, /core-2/);
  assert.doesNotMatch(h.root.innerHTML, /other-role|regular/);
  assert.equal(h.calls.length, 0, "未选择用户时不能读取或编辑任意私聊对象的资料");

  const selectedKey = JSON.stringify(["core-2", "qq-main", "bot-a", "account-b", "role-a"]);
  const picker = {value: selectedKey, closest(selector) { return selector === "[data-self-core-picker]" ? this : null; }};
  h.root.handlers.change({target: picker});
  await settle();
  assert.match(h.root.innerHTML, /核心用户/);
  assert.match(h.root.innerHTML, /core-2/);
  assert.match(h.root.innerHTML, /QQ · OneBot/);
  assert.match(h.root.innerHTML, /当前角色/);
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls[0])), {method: "GET", route: "acquaintance/settings", body: {
    subject_id: "core-2", platform: "qq-main", bot_id: "bot-a", account_id: "account-b", role_id: "role-a",
  }});

  const input = {value: "小屋主人", dataset: {selfRelationshipField: "default_nickname"},
    closest(selector) { return selector === "[data-self-relationship-field]" ? this : null; }};
  input.value = "阿澈";
  h.root.handlers.input({target: input});
  assert.equal(h.saveButton.disabled, false);
  const action = {dataset: {selfRelationshipAction: "save"},
    closest(selector) { return selector === "[data-self-relationship-action]" ? this : null; }};
  h.root.handlers.click({target: action});
  await settle();
  const saved = h.calls[1];
  assert.equal(saved.method, "POST");
  assert.equal(saved.route, "acquaintance/settings");
  assert.equal(saved.body.operation_key, "operation-1");
  assert.equal(saved.body.subject_id, "core-2");
  assert.deepEqual(JSON.parse(JSON.stringify(saved.body.route)), {platform: "qq-main", bot_id: "bot-a", account_id: "account-b", role_id: "role-a"});
  assert.deepEqual(JSON.parse(JSON.stringify(saved.body.sections.profile)), {edit_token: "profile-v1", changes: {default_nickname: "阿澈"}});
  assert.match(h.root.innerHTML, /关系资料已保存/);
});

test("私聊用户页编辑主动联系覆盖，只提交该用户实际修改的 contact 字段", async () => {
  const h = harness([person("core-1")]);
  h.mount(h.root);
  await settle();
  assert.match(h.root.innerHTML, /主动联系/);
  assert.match(h.root.innerHTML, /跟随全局默认/);

  const enabled = {type: "checkbox", checked: false, dataset: {selfContactField: "enabled"},
    closest(selector) { return selector === "[data-self-contact-field]" ? this : null; }};
  h.root.handlers.change({target: enabled});
  const note = {type: "textarea", value: "只對這位用戶放慢聯絡節奏", dataset: {selfContactField: "note"},
    closest(selector) { return selector === "[data-self-contact-field]" ? this : null; }};
  h.root.handlers.input({target: note});
  assert.equal(h.contactStatus.textContent, "2 项未保存");

  const action = {dataset: {selfRelationshipAction: "save-contact"},
    closest(selector) { return selector === "[data-self-relationship-action]" ? this : null; }};
  h.root.handlers.click({target: action});
  await settle();
  const saved = h.calls.at(-1);
  assert.equal(saved.method, "POST");
  assert.equal(saved.route, "acquaintance/settings");
  assert.deepEqual(JSON.parse(JSON.stringify(saved.body.sections)), {contact: {
    edit_token: "contact-v1", changes: {enabled: false, note: "只對這位用戶放慢聯絡節奏"},
  }});
  assert.match(h.root.innerHTML, /该私聊窗口的主动联系设置已保存/);
  assert.match(h.root.innerHTML, /此窗口单独设置/);
});
