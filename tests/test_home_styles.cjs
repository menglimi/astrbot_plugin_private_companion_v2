/* 小屋首页的结构契约：清单式外壳，以及那些「写死的示例状态」不许回来。
 *
 * 用户对首页的要求是「继续拓展页建设」时定的：与管理页同一套语汇。
 * 首页此前是另一套——右栏三张 overview-card、生活观察三张同款卡、
 * 家具目录一张四列等宽卡片网格。三处都带 radius + shadow + border，
 * 与管理页的分隔线清单并存，同一个插件两种读法。
 *
 * 这个文件守三件事：
 *   1. 首页样式表被引用，且新 class 都有定义（不许再出现「写了没引」）
 *   2. 首页不再渲染卡片壳（overview-card / furniture-card / home-summary-grid）
 *   3. directory 表里不再有写死的示例状态
 *
 * 第 3 条是这次真正抓到的缺陷：基础家具每件都挂着一条
 * `label: configSnapshot.base.dailyDiary ? '已开启' : '未启用'`，
 * 而 configSnapshot.base 恒为 {}（config-snapshot.js 里就是 `base:{}`，
 * 发行版快照没有这些字段）。于是七件基础家具永远显示「未启用」；
 * 另有两件挂着写死的示例词——'示例记录'、'示例照片'。用户看到的是假状态。
 *
 * 用 node --test 运行。
 */
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const DIR = path.join(__dirname, "..", "pages", "陪伴小屋");
const read = name => fs.readFileSync(path.join(DIR, name), "utf8");
const withoutComments = source => source.replace(/\/\*[\s\S]*?\*\//g, "");

const INDEX = read("index.html");
const APP = withoutComments(read("app.js"));
const PRODUCT = withoutComments(read("product-page.js"));

test("首页样式表被 index.html 引用", () => {
  /* 与管理页 console.css 那次同一个理由：漏引时首页整片没有结构样式，
     而预览构建器按同样的引用列表内联，所以本地看起来也「一致」，
     任何目视检查都发现不了。 */
  const linked = [...INDEX.matchAll(/<link\s+rel="stylesheet"\s+href="([^"?]+)[^"]*"/g)]
    .map(m => m[1]);
  assert.ok(linked.includes("home.css"),
    "index.html 没有引用 home.css：首页的 .home-band / .home-row / .home-item 全部失效");
});

test("首页用到的 class 都真的被定义了", () => {
  const linked = [...INDEX.matchAll(/<link\s+rel="stylesheet"\s+href="([^"?]+)[^"]*"/g)]
    .map(m => m[1]);
  const defined = new Set();
  for (const name of linked) {
    const source = withoutComments(read(name));
    for (const m of source.matchAll(/([^{}]+)\{/g)) {
      for (const part of m[1].split(",")) {
        const sel = part.trim();
        if (sel) defined.add(sel);
      }
    }
    // 形状 token 之类只出现在媒体查询里的选择器也一并收
    for (const m of source.matchAll(/\.([a-z][a-z0-9-]*)/g)) defined.add("." + m[1]);
  }
  /* 只查首页专有的前缀。通用 button / pill 散落在别处，不在这里重复断言。 */
  const used = new Set();
  for (const source of [APP, PRODUCT]) {
    for (const m of source.matchAll(/class="([^"]+)"/g)) {
      for (const name of m[1].split(/\s+/)) {
        if (/^(home-|room-doors|room-bar|room-foot|voxel-fallback)/.test(name)) used.add(name);
      }
    }
  }
  assert.ok(used.size >= 10, `没抓到首页的 class，选择器变了？抓到 ${used.size} 个`);
  const missing = [...used].filter(name => !defined.has("." + name));
  assert.deepStrictEqual(missing, [],
    `这些 class 被首页用到了但没有任何已加载的样式表定义：${missing.join("、")}`);
});

test("voxel-fallback-actions 有样式", () => {
  /* 体素小屋加载失败时的两个按钮容器。app.js 渲染它，但没有一张表定义过它——
     与管理页 console.css 漏引是同一个毛病，只是范围小到没人报过。 */
  const source = withoutComments(read("home.css"));
  assert.match(source, /\.voxel-fallback-actions\s*\{/,
    ".voxel-fallback-actions 又变成无样式的容器了");
});

test("首页不恢复旧的嵌套卡片壳", () => {
  /* 分区保留分隔线，避免恢复旧的等宽嵌套卡片。
     用户指定的右栏心情、位置与忙碌摘要允许使用紧凑卡片。 */
  for (const [name, source] of [["app.js", APP], ["product-page.js", PRODUCT]]) {
    for (const cls of ["overview-card", "furniture-card", "home-summary-grid",
                       "home-section-heading", "section-eyebrow", "furniture-grid"]) {
      assert.doesNotMatch(source, new RegExp('[\\s"]' + cls + '[\\s"]'),
        `${name} 里又出现了卡片壳 class「${cls}」——首页已经改成清单式`);
    }
  }
});

test("首页分区与家具清单维持分隔线", () => {
  /* 同 console.css 那条：分区之间用分隔线，不限制状态摘要的独立卡片。 */
  const source = withoutComments(read("home.css"));
  const band = source.match(/\.home-band\{([\s\S]*?)\n\}/);
  assert.ok(band, "home.css 里找不到 .home-band");
  assert.doesNotMatch(band[1], /border:\s*1px solid/,
    ".home-band 又画上整圈边框了：分区应当用 border-top 分隔线");
  assert.doesNotMatch(band[1], /box-shadow/,
    ".home-band 又加了阴影：那是卡片语汇");
  const item = source.match(/\.home-item\{([\s\S]*?)\n\}/);
  assert.ok(item, "home.css 里找不到 .home-item");
  assert.doesNotMatch(item[1], /border-radius/,
    ".home-item 又画成卡片了：家具目录是清单行，不是卡");
});

test("首页说明限宽，不会拉成通栏", () => {
  const source = withoutComments(read("home.css"));
  for (const name of ["home-band-note", "home-row-main small", "home-note"]) {
    const key = name.includes(" ") ? name.split(" ")[0] : name;
    const rule = source.match(new RegExp("\\." + key + "([^{}]*)\\{([\\s\\S]*?)\\}"));
    assert.ok(rule, `home.css 里找不到 .${key}`);
    const all = [...source.matchAll(new RegExp("\\." + key + "([^{}]*)\\{([^}]*)\\}", "g"))]
      .map(m => m[2]).join("\n");
    assert.match(all, /max-width:\s*\d+ch/,
      `.${key} 没有限宽：说明会拉成通栏，读起来一眼看不到头`);
  }
});

test("directory 表里没有写死的示例状态", () => {
  /* 这次真正抓到的缺陷。基础家具的状态标签此前读 configSnapshot.base.*，
     那份快照恒为 {}，于是七件永远显示「未启用」；另有两件写着
     '示例记录' 与 '示例照片'。三类都是假状态，用户拿不到真信息。 */
  const m = APP.match(/const directory\s*=\s*\[/);
  assert.ok(m, "找不到 directory 表");
  let depth = 0, end = m.index;
  for (let k = m.index + m[0].length - 1; k < APP.length; k += 1) {
    if (APP[k] === "[") depth += 1;
    else if (APP[k] === "]") { depth -= 1; if (depth === 0) { end = k + 1; break; } }
  }
  const block = APP.slice(m.index, end);
  assert.doesNotMatch(block, /示例/, "directory 表里又有「示例」字样了——那是假状态");
  assert.doesNotMatch(block, /configSnapshot/,
    "directory 表又去读 config-snapshot 了：那份快照的 base 恒为 {}，读它只会得到「未启用」");
});

test("家具状态只有一个判据来源", () => {
  /* 家具能不能用，只由扩展自报状态与本地「移出房间」决定。
     新增判据必须走 furnitureUnavailable()，不要在别处另写一份。 */
  assert.match(APP, /function furnitureUnavailable\(item\)/,
    "找不到 furnitureUnavailable()：家具可用性的唯一判据没了");
  assert.match(APP, /function furnitureStatus\(item\)/,
    "找不到 furnitureStatus()：家具状态标签的唯一出口没了");
});
