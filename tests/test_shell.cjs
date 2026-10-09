/* 外壳状态机的行为测试。
 *
 * 外壳负责三件容易悄然出错的事：
 *
 *   1. 三个维度（家具 / 配置分区 / 整页视图）互斥。同时选中两个会让
 *      下方面板同时想渲染两样东西——paintPanel 里的三目链会静默只显示第一个，
 *      用户看到的是「点了没反应」。
 *
 *   2. 非法值必须收敛成 null，而不是原样存下来。存下来会一路走到渲染函数，
 *      在 directory / manageTabs 里找不到对应项，然后回落成首页——
 *      又是一次「点了没反应」。
 *
 *   3. 重复选中同一项不触发订阅者。config-editor 的面板重绘会重建输入框，
 *      把用户正在填的内容和光标一起丢掉。这条是真实缺陷：selectSection
 *      最初没有判重，重复点同一个分区会把表单重绘一遍。
 *
 * 用 node --test 运行。shell.js 只依赖 window / document / console，
 * 所以给一个最小替身即可，不用 jsdom。
 */
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "pages", "陪伴小屋", "shell.js"), "utf8");

function load() {
  const context = vm.createContext({window: {}, document: {}, console});
  vm.runInContext(SOURCE, context);
  return context.window.CompanionShell;
}

/* 体素包机位表的子集。这里对表断言，因为清单漂移的后果是
   focus 静默回落全景——不报错，只是镜头不动。 */
const BUNDLE_STATIONS = ["calendar", "desk", "shelf", "wardrobe", "bed", "radio", "garden"];

test("三个维度初始都为空", () => {
  const shell = load();
  const now = shell.snapshot();
  assert.strictEqual(now.furniture, null);
  assert.strictEqual(now.section, null);
  assert.strictEqual(now.view, null);
});

test("选家具会清掉分区与视图", () => {
  const shell = load();
  shell.selectSection("memory");
  assert.strictEqual(shell.section, "memory");
  shell.selectFurniture("desk");
  assert.strictEqual(shell.furniture, "desk");
  assert.strictEqual(shell.section, null, "选家具后分区仍占着，面板会同时想渲染两样");
  assert.strictEqual(shell.view, null);
});

test("选分区会清掉家具与视图", () => {
  const shell = load();
  shell.selectFurniture("desk");
  shell.selectSection("memory");
  assert.strictEqual(shell.section, "memory");
  assert.strictEqual(shell.furniture, null, "选分区后家具仍占着");
  assert.strictEqual(shell.view, null);
});

test("选视图会清掉家具与分区", () => {
  const shell = load();
  shell.selectFurniture("desk");
  shell.selectView("directory");
  assert.strictEqual(shell.view, "directory");
  assert.strictEqual(shell.furniture, null);
  assert.strictEqual(shell.section, null);
});

test("传 null 取消选中，不误清别的维度", () => {
  const shell = load();
  shell.selectFurniture("desk");
  shell.selectFurniture(null);
  assert.strictEqual(shell.furniture, null);
  /* 取消选中不该顺手把别的东西也清掉——那会让「回到全景」把面板重置两次。 */
  shell.selectSection("memory");
  shell.selectFurniture(null);
  assert.strictEqual(shell.section, "memory", "取消家具时把配置分区一起清了");
});

test("非法家具 id 收敛成 null", () => {
  const shell = load();
  /* 目录里有 lounge / album / image 等，但体素包没有它们的机位。
     存下来会一路走到 focus，然后静默回落全景。 */
  for (const bad of ["lounge", "image", "together", "game", "art", "nonsense", ""]) {
    const result = shell.selectFurniture(bad);
    assert.strictEqual(result.id, null, `「${bad}」不是合法机位，却存了下来`);
    assert.strictEqual(shell.furniture, null);
  }
});

test("非法视图名收敛成 null", () => {
  const shell = load();
  for (const bad of ["home", "settings", "nonsense", ""]) {
    shell.selectView(bad);
    assert.strictEqual(shell.view, null, `「${bad}」不是合法视图，却存了下来`);
  }
});

test("重复选中同一项不触发订阅者", async () => {
  /* 这条挡的是真实缺陷：selectSection 最初没有判重，
     重复点同一个分区会把配置面板重绘一遍，用户正在填的输入框被重建。 */
  const shell = load();
  let hits = 0;
  const off = shell.onChange(() => { hits += 1; });
  shell.selectSection("models");
  shell.selectSection("models");
  shell.selectSection("models");
  assert.strictEqual(hits, 1, `重复选中触发了 ${hits} 次，配置表单会被无谓重绘`);
  shell.selectFurniture("desk");
  shell.selectFurniture("desk");
  assert.strictEqual(hits, 2, "重复选家具也在重复触发");
  shell.selectView("directory");
  shell.selectView("directory");
  assert.strictEqual(hits, 3, "重复选视图也在重复触发");
  off();
  shell.selectSection("appearance");
  assert.strictEqual(hits, 3, "退订之后仍在触发");
});

test("订阅者抛错不影响其它订阅者", () => {
  /* 一个订阅者坏了不该让整个外壳停止响应。 */
  const shell = load();
  let reached = false;
  shell.onChange(() => { throw new Error("故意抛错"); });
  shell.onChange(() => { reached = true; });
  shell.selectSection("models");
  assert.strictEqual(reached, true, "前一个订阅者抛错把后面的挡掉了");
});

test("机位清单与体素包一致", () => {
  /* 清单里多一个包里不存在的机位，飞入就会永远回落全景；
     少一个只是少一个候选，不会报错。所以直接对表。 */
  const bundle = fs.readFileSync(
    path.join(__dirname, "..", "pages", "陪伴小屋", "assets", "voxel-room.js"), "utf8");
  const from = bundle.indexOf("window.PrivateCompanionHomeRoom3D");
  const head = bundle.slice(from, from + 6000);
  const declared = new Set([...head.matchAll(
    /(\w+):\{label:"[^"]*",target:\[[^\]]*\],position:\[[^\]]*\],fov:\d+\}/g
  )].map(match => match[1]));
  assert.ok(declared.size >= 5, `体素包机位表只解析出 ${declared.size} 个`);
  const shell = load();
  /* 注意 [...shell.STAGE_STATIONS]：它是 vm 上下文里创建的数组，
     原型与宿主不同，跨 realm 的数组拿 filter() 出来的结果
     deepStrictEqual 比不过宿主里的 []。先摊成本地数组再比。 */
  const wrong = [...shell.STAGE_STATIONS].filter(id => !declared.has(id));
  assert.deepStrictEqual(wrong, [],
    `shell.js 里列了包里不存在的机位：${wrong.join(", ")}——focus 会静默回落全景`);
});

test("机位清单与包完全同集", () => {
  /* 反向：包里有而我漏掉，意味着那件家具在小屋里点不到。 */
  const bundle = fs.readFileSync(
    path.join(__dirname, "..", "pages", "陪伴小屋", "assets", "voxel-room.js"), "utf8");
  const from = bundle.indexOf("window.PrivateCompanionHomeRoom3D");
  const head = bundle.slice(from, from + 6000);
  const declared = new Set([...head.matchAll(
    /(\w+):\{label:"[^"]*",target:\[[^\]]*\],position:\[[^\]]*\],fov:\d+\}/g
  )].map(match => match[1]));
  const shell = load();
  const mine = [...shell.STAGE_STATIONS];
  const missed = [...declared].filter(id => !mine.includes(id));
  assert.deepStrictEqual(missed, [],
    `包里这些机位没进清单，对应家具在小屋里点不到：${missed.join(", ")}`);
});

/* === paint()：外壳上的状态属性 ===
   视觉全部由 CSS 依据这些属性决定，所以属性写错不会报错，只是样式不生效。
   data-away 尤其关键：它是「小屋退到背景」的开关，
   错了的表现是小屋既没收起也没缩略，或者反过来在首页就被压成窄条。 */
function stubDom() {
  const attrs = new Map();
  const make = (hidden = false) => ({
    hidden,
    dataset: new Proxy({}, {
      get: (_, key) => attrs.get(key),
      set: (_, key, value) => { attrs.set(key, value); return true; },
      has: (_, key) => attrs.has(key),
    }),
    set innerHTML(value) { this._html = value; },
    get innerHTML() { return this._html || ""; },
  });
  const shell = make();
  const nodes = {"#homeShell": shell};
  const context = vm.createContext({
    window: {},
    document: {querySelector: selector => nodes[selector] || null},
    console,
  });
  vm.runInContext(SOURCE, context);
  return {shell, api: context.window.CompanionShell};
}

test("paint 在首页时 data-away 为假", () => {
  const {shell, api} = stubDom();
  api.paint();
  assert.strictEqual(shell.dataset.away, "false", "首页不该是小屋退场状态");
});

test("paint 在配置分区时 data-away 为真", () => {
  /* 这是「小屋退到背景」的唯一开关。若它一直为假，
     小屋会留在原位不缩略，配置面板被推到屏幕外。 */
  const {shell, api} = stubDom();
  api.selectSection("memory");
  api.paint();
  assert.strictEqual(shell.dataset.away, "true", "选了配置分区，小屋应当退到背景");
  api.selectSection(null);
  api.paint();
  assert.strictEqual(shell.dataset.away, "false", "回到小屋后应当退出背景态");
});

test("选中家具不让小屋退场", () => {
  /* 家具说明属于首页，不是离开首页。退场只由 section 触发。 */
  const {shell, api} = stubDom();
  api.selectFurniture("desk");
  api.paint();
  assert.strictEqual(shell.dataset.away, "false", "选了家具不该把小屋收起来");
  assert.strictEqual(shell.dataset.selected, "desk");
});

test("整页视图不让小屋退场", () => {
  const {shell, api} = stubDom();
  api.selectView("directory");
  api.paint();
  assert.strictEqual(shell.dataset.away, "false", "看家具目录不该把小屋收起来");
});
