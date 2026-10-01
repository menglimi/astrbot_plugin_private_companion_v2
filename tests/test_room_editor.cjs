/* 布置房间（room-editor.js）的挂载点合同。
 *
 * 布置时工作台临时替换小屋右栏的状态与日程；小屋场景留在左侧原位。
 * 这里锁住挂载、恢复和保存语义，不依赖浏览器或 jsdom。
 */
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const PAGE = path.join(__dirname, "..", "pages", "陪伴小屋");
const SOURCE = fs.readFileSync(path.join(PAGE, "room-editor.js"), "utf8");

function makeNode(name) {
  const node = {
    name, children: [], parent: null, attributes: {}, dataset: {}, removed: false,
    classList: {
      set: new Set(),
      add(...names) { names.forEach(item => this.set.add(item)); },
      remove(...names) { names.forEach(item => this.set.delete(item)); },
      contains(name) { return this.set.has(name); },
    },
    setAttribute(key, value) { this.attributes[key] = value; },
    removeAttribute(key) { delete this.attributes[key]; },
    append(...children) {
      children.forEach(child => { child.parent = this; this.children.push(child); });
      return children[0];
    },
    remove() {
      this.removed = true;
      const at = this.parent?.children.indexOf(this) ?? -1;
      if (at >= 0) this.parent.children.splice(at, 1);
      this.parent = null;
    },
    querySelector(selector) { return selector === "canvas" ? this.canvas || null : null; },
    focus() { this.focused = true; },
    isConnected: true,
  };
  Object.defineProperty(node, "innerHTML", {
    get() { return this._html || ""; },
    set(value) {
      this._html = value;
      this.children.forEach(child => { child.parent = null; });
      this.children = [];
      this.onHTML?.(value);
    },
  });
  return node;
}

function harness() {
  const body = makeNode("body");
  const main = makeNode("main");
  main.hidden = true;
  const shell = makeNode("homeShell");
  const stageRegion = makeNode("stage-region");
  const stage = makeNode("room-stage");
  const canvas = makeNode("canvas");
  stage.canvas = canvas;
  stageRegion.append(stage);
  shell.append(stageRegion);
  const side = makeNode("shell-side");
  shell.append(side);
  body.append(shell);
  body.append(main);

  let editor = null;
  side.onHTML = html => {
    if (html.includes('id="roomEditor"')) {
      editor = makeNode("roomEditor");
      side.append(editor);
    } else {
      editor = null;
      side.append(makeNode("state-band"), makeNode("schedule-band"));
    }
  };
  side.innerHTML = "<state-band></state-band><schedule-band></schedule-band>";

  const selectors = {
    ".room-stage": stage,
    ".room-stage canvas": canvas,
    "#shellSide": side,
    "#main": main,
    "#roomEditor": () => (editor && !editor.removed ? editor : null),
  };
  const document = {
    body,
    activeElement: null,
    querySelector: selector => (selector === "#main" ? main : null),
  };
  const arrangement = {draft: null};
  const sandbox = {
    document,
    window: {scrollY: 120},
    escapeHTML: value => String(value ?? ""),
    I: () => "<i></i>",
    icons() {},
    $: selector => {
      const found = selectors[selector];
      return typeof found === "function" ? found() : (found || null);
    },
    get arrangementDraft() { return arrangement.draft; },
    set arrangementDraft(value) { arrangement.draft = value; },
    voxelController: {
      editing: false,
      layout: {items: {desk: {x: 1}}},
      getLayout() { return this.layout; },
      setLayout(layout) { this.layout = layout; },
      getCatalog() { return {houseStyles: {classic: "简约"}, styles: {oak: "橡木"}}; },
      setEditing(value) { this.editing = value; },
      resize() { this.resized = (this.resized || 0) + 1; },
    },
    state: {scene: "day", modules: {}, roomLayouts: {}},
    directory: [],
    sceneTimes: [["day", "白天"], ["night", "夜晚"]],
    roleName: () => "角色",
    layoutKey: () => "role-a",
    closeDetail() {},
    toast() {},
    saved() {},
    syncEnvironment() {},
    renderShellSide() {
      side.setAttribute("aria-label", arrangement.draft ? "布置房间工作台" : "当前状态与日程");
      if (arrangement.draft) return;
      side.innerHTML = "<state-band></state-band><schedule-band></schedule-band>";
    },
    updateFurnitureDirectory() {},
    console,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SOURCE, sandbox);
  return {sandbox, body, main, shell, stage, stageRegion, side, editor: () => editor};
}

test("进入布置后工作台替换右栏，场景仍留在原位", () => {
  const {sandbox, body, main, shell, stage, stageRegion, side, editor} = harness();

  sandbox.openRoomEditor();

  const view = editor();
  assert.ok(view, "应当插入一个 #roomEditor");
  assert.equal(side.children.includes(view), true, "工作台应挂在状态与日程所在的右栏");
  assert.equal(body.children.includes(view), false, "工作台不能追加到页面底部");
  assert.equal(stage.parent, stageRegion, "3D 场景应当留在小屋原位");
  assert.equal(shell.children.includes(stageRegion), true);
  assert.equal(body.classList.contains("room-editing"), true);
  assert.equal(side.attributes["aria-label"], "布置房间工作台");
  assert.equal(main.hidden, true, "布置不应改变路由主内容区");

  sandbox.renderShellSide();
  assert.equal(editor(), view, "布置期间右栏状态刷新不能覆盖工作台");
});

test("取消布置后恢复状态与日程，场景和主内容区不变", () => {
  const {sandbox, body, main, shell, stage, stageRegion, side, editor} = harness();

  sandbox.openRoomEditor();
  const view = editor();
  sandbox.finishRoomEditor(false);

  assert.equal(view.removed, true, "退出时应移除工作台");
  assert.equal(body.classList.contains("room-editing"), false);
  assert.equal(side.children.map(item => item.name).join(","), "state-band,schedule-band");
  assert.equal(side.attributes["aria-label"], "当前状态与日程");
  assert.equal(stage.parent, stageRegion, "场景不需要在退出时搬回");
  assert.equal(shell.children.includes(stageRegion), true);
  assert.equal(main.hidden, true);
});

test("保存布置时保留当前布局", () => {
  const {sandbox, side} = harness();

  sandbox.openRoomEditor();
  sandbox.voxelController.layout = {items: {desk: {x: 9}}};
  sandbox.finishRoomEditor(true);

  assert.equal(sandbox.state.roomLayouts["role-a"].items.desk.x, 9);
  assert.equal(sandbox.voxelController.layout.items.desk.x, 9);
  assert.equal(side.children.map(item => item.name).join(","), "state-band,schedule-band");
});

test("布局样式与右栏重绘共同守住工作台位置", () => {
  const css = fs.readFileSync(path.join(PAGE, "styles.css"), "utf8");
  assert.match(css, /\.room-editing \.shell-side\s*\{/);
  assert.doesNotMatch(css, /\.room-editing[^{}]*#homeShell[^{}]*\{\s*display:\s*none/);
  assert.doesNotMatch(css, /\.room-editing[^{}]*#main[^{}]*\{\s*display:\s*none/);

  const app = fs.readFileSync(path.join(PAGE, "app.js"), "utf8");
  assert.match(app, /function renderShellSide\(\)\s*\{[^}]*if\(arrangementDraft\)return;/s);

  const html = fs.readFileSync(path.join(PAGE, "index.html"), "utf8");
  assert.match(html, /data-detail="arrange"/);
  assert.match(html, /room-editor\.js\?v=/);
});
