"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../pages/陪伴小屋/confirmation-dialog.js"), "utf8");
const confirmationClients = [
  "../pages/陪伴小屋/memory-page.js",
  "../pages/陪伴小屋/maintenance-page.js",
  "../pages/陪伴小屋/semantic-page.js",
  "../pages/陪伴小屋/weather-source-page.js",
  "../pages/关系与记忆/group-memory.js",
];

function control() {
  const listeners = new Map();
  return {
    textContent: "", dataset: {}, open: false, returnValue: "",
    addEventListener(type, callback) {
      const group = listeners.get(type) || [];
      group.push(callback); listeners.set(type, group);
    },
    dispatch(type, event = {}) { for (const callback of listeners.get(type) || []) callback(event); },
    showModal() { this.open = true; },
    close(value) { this.open = false; this.returnValue = value; this.dispatch("close"); },
    focus() {},
    getBoundingClientRect() { return {left: 0, top: 0, right: 100, bottom: 100}; },
  };
}

function harness() {
  const elements = Object.fromEntries(["confirmationDialog", "confirmationTitle", "confirmationMessage",
    "confirmationCancel", "confirmationAccept"].map(id => [id, control()]));
  const document = {querySelector: selector => elements[selector.slice(1)] || null};
  const window = {};
  vm.runInNewContext(source, {window, document});
  return {window, elements};
}

test("confirmation dialogs use text content, serialize requests, and resolve cancel safely", async () => {
  const {window, elements} = harness();
  const first = window.CompanionConfirm({title: "删除素材", message: "<img src=x>", confirmText: "删除", danger: true});
  const second = window.CompanionConfirm({title: "离开页面", message: "丢弃未保存修改？"});

  assert.equal(elements.confirmationDialog.open, true);
  assert.equal(elements.confirmationTitle.textContent, "删除素材");
  assert.equal(elements.confirmationMessage.textContent, "<img src=x>");
  assert.equal(elements.confirmationDialog.dataset.intent, "danger");
  assert.equal(elements.confirmationAccept.textContent, "删除");

  elements.confirmationAccept.dispatch("click");
  assert.equal(await first, true);
  await Promise.resolve();
  assert.equal(elements.confirmationTitle.textContent, "离开页面");
  assert.equal(elements.confirmationDialog.dataset.intent, "normal");
  elements.confirmationCancel.dispatch("click");
  assert.equal(await second, false);
  assert.equal(elements.confirmationDialog.open, false);
});

test("Escape and backdrop interactions cancel the active request", async () => {
  const {window, elements} = harness();
  const escaped = window.CompanionConfirm("确认第一步");
  let prevented = false;
  elements.confirmationDialog.dispatch("cancel", {preventDefault() { prevented = true; }});
  assert.equal(prevented, true);
  assert.equal(await escaped, false);

  const backdrop = window.CompanionConfirm("确认第二步");
  elements.confirmationDialog.dispatch("click", {target: elements.confirmationDialog, clientX: 150, clientY: 50});
  assert.equal(await backdrop, false);
});

test("destructive pages use in-page confirmation instead of the browser confirm API", () => {
  for (const file of confirmationClients) {
    const text = fs.readFileSync(path.resolve(__dirname, file), "utf8");
    assert.doesNotMatch(text, /window\.confirm\s*\(/, file);
  }
});
