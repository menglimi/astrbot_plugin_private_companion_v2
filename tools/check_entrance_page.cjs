/* 真实浏览器的入口回归：内容比例、交回布局时的矩形/机位连续性、UI 时序。
 * NODE_PATH 指向已安装 Playwright；PLAYWRIGHT_EXECUTABLE_PATH 可指定本机浏览器。
 * 用法：node tools/check_entrance_page.cjs [截图与报告目录]
 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const {pathToFileURL} = require("node:url");
const {chromium} = require("playwright");

function instrument() {
  let entrance;
  const qa = window.__entranceQA = {phase: "", states: [], frames: [], runCount: 0};
  Object.defineProperty(window, "CompanionEntrance", {
    configurable: true, get: () => entrance,
    set(value) {
      entrance = value;
      const original = value.run;
      value.run = (controller, host, options) => {
        qa.runCount++;
        const start = performance.now();
        const snapshot = label => {
          const rect = node => {
            const r = node.getBoundingClientRect();
            return [r.left, r.top, r.width, r.height];
          };
          const ui = [".rail", ".shell-side", ".shell-panel", ".stage-bar", ".stage-role", ".stage-furniture-strip", ".stage-overlay", ".voxel-hint"]
            .map(selector => Number(getComputedStyle(document.querySelector(selector)).opacity));
          const rest = options.measureRest?.() || options.geometry.rest;
          return {label, at: performance.now() - start, box: rect(host),
            room: rect(host.parentElement), target: [rest.left, rest.top, rest.width, rest.height],
            ui, camera: controller.getState().camera};
        };
        const phase = options.onPhase;
        qa.snapshot = snapshot;
        const handle = original(controller, host, {...options, onPhase(name) {
          qa.states.push(snapshot(name + " before"));
          phase(name);
          qa.phase = name;
          qa.states.push(snapshot(name + " after"));
        }});
        handle.ready.then(() => qa.states.push(snapshot("ready")));
        qa.skip = handle.skip;
        const frame = () => {
          if (qa.frames.length >= 500) return;
          qa.frames.push(snapshot("frame"));
          if (qa.phase !== "done") requestAnimationFrame(frame);
        };
        requestAnimationFrame(frame);
        return handle;
      };
    },
  });
}

const maxDifference = (a, b) => Math.max(...a.map((value, i) => Math.abs(value - b[i])));
async function check(browser, outputDir, item) {
  const page = await browser.newPage({viewport: item.viewport, reducedMotion: item.reduced ? "reduce" : "no-preference"});
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  if(process.argv.includes("--hosted"))await page.addInitScript(require("./check_home_sidebar.cjs").syntheticBridge,
    {catalogDelay:process.argv.includes("--late-layout")?900:0});
  await page.addInitScript(instrument);
  await page.goto(pathToFileURL(path.resolve(__dirname, "../pages/陪伴小屋/index.html")).href);
  await page.waitForFunction(() => window.__entranceQA?.states.some(s => s.label === "ready"));
  if (item.resize) {
    await page.waitForFunction(() => __entranceQA.phase === "pull");
    await page.setViewportSize(item.resize);
  } else if (item.skip) {
    await page.waitForFunction(() => __entranceQA.phase === "pull");
    await page.keyboard.press("Escape");
  } else if (item.shots) {
    await page.screenshot({path: path.join(outputDir, "1-central-closeup.png")});
    await page.waitForFunction(() => __entranceQA.phase === "pull");
    await page.waitForTimeout(500);
    await page.screenshot({path: path.join(outputDir, "2-pulling.png")});
    await page.waitForFunction(() => __entranceQA.phase === "settle");
    await page.screenshot({path: path.join(outputDir, "3-docked.png")});
    await page.waitForTimeout(240);
    await page.screenshot({path: path.join(outputDir, "4-ui-reveal.png")});
  }
  await page.waitForFunction(() => __entranceQA.phase === "done");
  await page.waitForTimeout(280);
  const result = await page.evaluate(() => ({states: __entranceQA.states, frames: __entranceQA.frames, final: __entranceQA.snapshot("stable"),
    overflow: document.documentElement.scrollWidth > innerWidth,
    residual: document.body.classList.contains("is-entrance") || document.body.classList.contains("is-entrance-pull"),
    sceneProperties: document.querySelector("[data-voxel-room]").style.cssText}));
  const get = label => result.states.find(s => s.label === label);
  await fs.writeFile(path.join(outputDir, item.name + "-frames.json"), JSON.stringify(result, null, 2) + "\n", "utf8");
  const ready = get("ready"), done = get("done after");
  let difference = 0;
  if (!item.reduced && !item.skip) {
    const before = get("settle before"), after = get("settle after");
    difference = maxDifference(before.box, after.box);
    assert.ok(maxDifference(before.box, before.target) < .05, `${item.name}: 拉远终点偏离真实内容框`);
    assert.ok(difference < .05, `${item.name}: 交回布局时跳了 ${difference}px`);
    assert.ok(maxDifference(after.box, done.box) < .05, `${item.name}: UI 入场改变了场景尺寸`);
    assert.ok(maxDifference(before.camera.position, after.camera.position) < .03, `${item.name}: 交回布局改变了相机`);
    assert.ok(ready.ui.every(value => value === 0) && before.ui.every(value => value === 0), `${item.name}: UI 在拉远前提前出现`);
    assert.ok(result.frames.filter(s => s.ui[0] > .05 && s.ui[0] < .95).length >= 3, `${item.name}: UI 没有渐入过程`);
    const distance = s => Math.hypot(...s.camera.position.map((v, i) => v - s.camera.target[i]));
    assert.ok(distance(ready) < distance(done) * .6, `${item.name}: 初始相机不是中央近景`);
    assert.ok(ready.box[2] > 0 && ready.box[3] > 0, `${item.name}: 初始场景框无有效尺寸`);
    assert.ok(ready.box[0] >= -.02 && ready.box[1] >= -.02
      && ready.box[0] + ready.box[2] <= item.viewport.width + .02
      && ready.box[1] + ready.box[3] <= item.viewport.height + .02, `${item.name}: 初始场景框没有位于视口内`);
    assert.ok(maxDifference(ready.box, ready.target) < .05, `${item.name}: 初始场景框偏离布局目标`);
  }
  assert.ok(result.final.ui.every(value => value === 1), `${item.name}: 最终 UI 不可见`);
  assert.equal(result.residual, false);
  assert.equal(result.overflow, false, `${item.name}: 出现横向溢出`);
  assert.equal(result.sceneProperties, "", `${item.name}: 遗留入口行内覆盖`);
  await page.locator('[data-life="state"]').first().dispatchEvent("click");
  await page.waitForFunction(() => window.CompanionShell?.view === "state");
  assert.equal(await page.evaluate(() => window.__entranceQA.runCount), 1,
    `${item.name}: 打开状态页重复调度了拓展页入口动画`);
  assert.deepEqual(errors, [], `${item.name}: 页面异常`);
  await page.screenshot({path: path.join(outputDir, item.name + "-settled.png")});
  await page.close();
  return {name: item.name, handoffDifferencePx: difference, states: result.states};
}

(async () => {
  const outputDir = path.resolve(process.argv[2] || "build/entrance-qa");
  await fs.mkdir(outputDir, {recursive: true});
  const browser = await chromium.launch({headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
    args: ["--enable-unsafe-swiftshader"]});
  try {
    const results = [];
    for (const item of [
      {name: "desktop", viewport: {width: 1440, height: 900}, shots: true},
      {name: "mobile", viewport: {width: 390, height: 844}},
      {name: "resize", viewport: {width: 1440, height: 900}, resize: {width: 960, height: 760}},
      {name: "reduced-motion", viewport: {width: 1440, height: 900}, reduced: true},
      {name: "skip", viewport: {width: 1440, height: 900}, skip: true},
    ].filter(item => !process.argv[3] || process.argv[3].startsWith("--") || item.name === process.argv[3])) results.push(await check(browser, outputDir, item));
    await fs.writeFile(path.join(outputDir, "report.json"), JSON.stringify(results, null, 2) + "\n", "utf8");
    console.log(JSON.stringify(results.map(({name, handoffDifferencePx}) => ({name, handoffDifferencePx})), null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
