/* 主题注册表契约测试。
 *
 * 守住的约束：
 *   1. theme.js 与 index.html 内联引导脚本的主题表必须一致。
 *      引导必须内联（要在样式生效前跑完），所以注定有第二份副本；
 *      副本飘了会出现「刷新后主题自己变了」——极难查，所以用测试钉住。
 *   2. 每套主题都有光照映射，且光照值在小屋真实的场景名集合内。
 *   3. 旧主题名能迁移，未知值回落到默认（不让坏值把整站令牌变空）。
 *   4. 一个光照对应多套主题时（黄昏 → 暮色/深林）不擅自替用户换主题。
 *
 * 用 node --test 运行：node --test tests/test_theme_registry.cjs
 */
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const PAGE = path.join(__dirname, "..", "pages", "陪伴小屋");
const REGISTRY = fs.readFileSync(path.join(PAGE, "theme.js"), "utf8");
const INDEX = fs.readFileSync(path.join(PAGE, "index.html"), "utf8");
const TOKENS = fs.readFileSync(path.join(PAGE, "tokens.css"), "utf8");

function loadRegistry() {
  const context = vm.createContext({window: {}});
  vm.runInContext(REGISTRY, context);
  return context.window.CompanionTheme;
}

/* 小屋真实支持的场景名。取自 app.js 的 sceneTimes，以及 voxel controller 的
   setLight 接受的取值。注册表里的 light 必须落在这个集合里。 */
const SCENE_NAMES = new Set(["dawn", "day", "dusk", "night"]);

test("注册表导出六套主题，id 唯一", () => {
  const theme = loadRegistry();
  assert.strictEqual(theme.THEMES.length, 6);
  assert.strictEqual(new Set(theme.IDS).size, 6);
  /* 逐项比较而不是 deepStrictEqual：vm 里创建的数组跨 realm，
     原型与本 realm 的 Array.prototype 不同，deepStrictEqual 会判不等。 */
  assert.strictEqual(theme.IDS.length, theme.THEMES.length);
  theme.THEMES.forEach((item, index) => {
    assert.strictEqual(theme.IDS[index], item.id, `第 ${index} 项 id 不一致`);
  });
});

test("每套主题都有标签、说明与明暗归类", () => {
  const theme = loadRegistry();
  for (const item of theme.THEMES) {
    assert.ok(item.label && item.label.length, `${item.id} 缺 label`);
    assert.ok(item.note && item.note.length, `${item.id} 缺 note`);
    assert.ok(["light", "dark"].includes(item.mode), `${item.id} 的 mode 非法`);
    assert.ok(item.light, `${item.id} 缺 light 映射`);
  }
});

test("每套主题都声明完整的非配色皮肤", () => {
  const expected = new Set([
    "--skin-heading-font", "--skin-canvas-pattern", "--skin-canvas-size",
    "--skin-r-2xs", "--skin-r-xs", "--skin-r-sm", "--skin-r-md", "--skin-r-lg", "--skin-r-xl",
  ]);
  const blocks = [...TOKENS.matchAll(/([^{}]+)\{([^{}]+)\}/g)];
  for (const item of loadRegistry().THEMES) {
    const found = new Set();
    for (const [, selector, body] of blocks) {
      if (!selector.includes(`data-theme="${item.id}"`)) continue;
      for (const [, name] of body.matchAll(/(--skin-[a-z0-9-]+)\s*:/g)) found.add(name);
    }
    assert.deepEqual([...found].sort(), [...expected].sort(), `${item.id} 主题皮肤字段不完整`);
  }
});

test("光照映射落在小屋真实场景名里", () => {
  const theme = loadRegistry();
  for (const item of theme.THEMES) {
    assert.ok(SCENE_NAMES.has(item.light),
      `${item.id} 的光照 ${item.light} 不在小屋支持的场景名内`);
    assert.strictEqual(theme.LIGHT[item.id], item.light, `${item.id} 的 LIGHT 与 THEMES 不一致`);
  }
});

test("深色主题至少两套，浅色主题至少两套", () => {
  const theme = loadRegistry();
  const dark = theme.THEMES.filter(item => item.mode === "dark").length;
  assert.ok(dark >= 2, `深色主题只有 ${dark} 套`);
  assert.ok(theme.THEMES.length - dark >= 2, "浅色主题太少");
});

test("未知主题回落到默认，不回落到空", () => {
  const theme = loadRegistry();
  assert.strictEqual(theme.normalize("not-a-theme"), theme.FALLBACK);
  assert.strictEqual(theme.normalize(""), theme.FALLBACK);
  assert.strictEqual(theme.normalize(null), theme.FALLBACK);
  assert.ok(theme.IDS.includes(theme.FALLBACK), "默认值必须在列表内");
  assert.strictEqual(theme.normalize("night"), "night", "合法值不该被改掉");
});

test("旧主题名迁移到新主题，不是丢弃", () => {
  const theme = loadRegistry();
  /* 这三套已并入新色板。直接丢弃会让用户「主题突然变了」，
     所以必须映射到一个具体的新主题。 */
  for (const legacy of ["mist", "grove", "coral"]) {
    const migrated = theme.migrate(legacy);
    assert.ok(theme.IDS.includes(migrated), `${legacy} 迁移后不是合法主题：${migrated}`);
  }
  assert.strictEqual(theme.migrate("night"), "night", "新名字不该被迁移改动");
  assert.strictEqual(theme.migrate("garbage"), theme.FALLBACK, "未知值回落默认");
});

test("一个光照对应多套主题时不擅自替换用户选择", () => {
  const theme = loadRegistry();
  /* 黄昏同时对应暮色与深林。用户选了深林时，光照变成黄昏不该把他换成暮色。 */
  const duskThemes = theme.THEMES.filter(item => item.light === "dusk").map(item => item.id);
  assert.ok(duskThemes.length >= 2, "本测试前提是黄昏有多套主题");
  for (const current of duskThemes) {
    assert.strictEqual(theme.themeForLight("dusk", current), null,
      `当前已是 ${current}，黄昏不该再切主题`);
  }
  /* 唯一对应的光照才切。夜晚只有一套。 */
  const nightThemes = theme.THEMES.filter(item => item.light === "night").map(item => item.id);
  if (nightThemes.length === 1) {
    assert.strictEqual(theme.themeForLight("night", "courtyard"), nightThemes[0]);
  }
});

test("index.html 的引导脚本与注册表主题表一致", () => {
  const theme = loadRegistry();
  const block = INDEX.match(/var THEMES=\{([^}]+)\}/);
  assert.ok(block, "引导脚本里找不到 THEMES 表——本轮改名是否为引导同步改了？");
  const inline = new Map(
    [...block[1].matchAll(/([a-z]+):"([a-z]+)"/g)].map(match => [match[1], match[2]]));
  assert.strictEqual(inline.size, theme.THEMES.length,
    `引导脚本有 ${inline.size} 套主题，注册表有 ${theme.THEMES.length} 套`);
  for (const item of theme.THEMES) {
    assert.strictEqual(inline.get(item.id), item.light,
      `主题 ${item.id} 的引导光照是 ${inline.get(item.id)}，注册表是 ${item.light}`);
  }
});

test("index.html 的引导脚本与注册表的默认值一致", () => {
  const theme = loadRegistry();
  const fallback = INDEX.match(/var FALLBACK="([a-z]+)"/);
  assert.ok(fallback, "引导脚本里找不到 FALLBACK");
  assert.strictEqual(fallback[1], theme.FALLBACK);
});

test("index.html 的引导脚本与注册表的旧名映射一致", () => {
  const theme = loadRegistry();
  const block = INDEX.match(/var LEGACY=\{([^}]+)\}/);
  assert.ok(block, "引导脚本里找不到 LEGACY");
  const inline = new Map(
    [...block[1].matchAll(/([a-z]+):"([a-z]+)"/g)].map(match => [match[1], match[2]]));
  /* 引导只带旧名到新名的映射；注册表那份是同一张表的超集。 */
  for (const [from, to] of inline) {
    assert.strictEqual(theme.migrate(from), to,
      `旧名 ${from}：引导映射到 ${to}，注册表映射到 ${theme.migrate(from)}`);
  }
});

test("引导脚本会标记 themeReady，否则首屏永远是隐藏的", () => {
  /* tokens.css 用 :root:not([data-theme-ready]) body{visibility:hidden} 防主题闪烁。
     引导若不标记 ready，整页就永远不显示——这是个只会表现为「白屏」的缺陷。 */
  assert.match(INDEX, /dataset\.themeReady/,
    "引导脚本没有写 themeReady，tokens.css 的首屏防闪规则会让页面一直隐藏");
  const tokens = fs.readFileSync(path.join(PAGE, "tokens.css"), "utf8");
  assert.match(tokens, /not\(\[data-theme-ready\]\)/,
    "tokens.css 里的首屏防闪规则不见了——两处必须同时存在");
});

test("theme.js 在页面上被加载", () => {
  assert.match(INDEX, /<script defer src="theme\.js/,
    "index.html 没有加载 theme.js，app.js 里的 window.CompanionTheme 会是 undefined");
});

test("app.js 的界面色值不硬编码", () => {
  const app = fs.readFileSync(path.join(PAGE, "app.js"), "utf8");
  /* 色值只在 tokens.css 里。app.js 出现十六进制色值就说明又抄了一份色板——
     那是「加主题要改多处」「色卡与实际不符」的根源。
     例外：家具目录里的 accent 是传给 voxel-room 渲染体素模型的材质色
     （屏幕台、现实设备台各有一个），属于场景数据不是界面主题，逐条豁免。 */
  const SCENE_MATERIAL = new Set(["#7e91b5", "#84a091"]);
  const hardcoded = [...app.matchAll(/#[0-9a-fA-F]{6}\b/g)]
    .map(match => match[0])
    .filter(value => !SCENE_MATERIAL.has(value));
  assert.strictEqual(hardcoded.length, 0,
    `app.js 里还有硬编码的界面色值：${hardcoded.join(", ")}`);
});

test("色卡不传内联色值", () => {
  const app = fs.readFileSync(path.join(PAGE, "app.js"), "utf8");
  const panel = app.slice(app.indexOf("function appearancePanel"));
  const body = panel.slice(0, panel.indexOf("\nfunction applyAppearanceControl"));
  /* 旧写法给色卡传 style="--sw-bg:...;--sw-accent:...;--sw-quiet:..."，
     色值抄在 JS 里。现在色卡只带 data-theme，颜色由 CSS 从真实令牌取。 */
  assert.doesNotMatch(body, /--sw-(bg|accent|quiet)/,
    "色卡又在内联传色值了，应该只给 data-theme 让 CSS 取真实令牌");
  assert.match(body, /data-theme="\$\{item\.id\}"/,
    "色卡没有带 data-theme，预览不会显示该主题的真实颜色");
});

test("styles.css 不再声明主题色板", () => {
  const styles = fs.readFileSync(path.join(PAGE, "styles.css"), "utf8");
  /* styles.css 的 :root[data-theme=...] 会盖掉 tokens.css 的令牌，
     曾经的「换主题整页跳色」就是这么来的。 */
  assert.doesNotMatch(styles, /:root\[data-theme="(mist|grove|coral|dawn|dusk|night|courtyard|walnut|contrast)"\]/,
    "styles.css 里又出现了主题色板，会覆盖 tokens.css 的令牌");
});
