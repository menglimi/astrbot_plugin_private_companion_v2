/* 页面动效浏览器验收：合成只读数据，不发送平台消息或修改宿主配置。 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const {pathToFileURL} = require("node:url");
const {chromium} = require("playwright");
const {syntheticBridge} = require("./check_home_sidebar.cjs");

function editorBridge() {
  const original = window.AstrBotPluginPage.apiGet;
  const values = {enabled: false, llm_controlled: true, prompt: "合成分段提示", max_segments: 4,
    style_prompt: "合成表达提示", content_cleanup_enabled: false, content_cleanup_words: "[]",
    voice_enabled: false, part_gap_ms: 0};
  window.AstrBotPluginPage.apiGet = async endpoint => {
    if (endpoint === "page/targets") {
      const catalog = await original(endpoint);
      for (const target of catalog.targets) for (const role of target.roles) {
        const prefix = role.state_api.slice(0, -5);
        for (const name of ["reply", "model"]) role[name + "_api"] = prefix + name;
      }
      return catalog;
    }
    if (endpoint.endsWith("/reply")) return {settings: values, recent: [], edit_token: "b".repeat(64),
      fields: Object.fromEntries(Object.entries(values).map(([name, value]) => [name,
        {kind: typeof value === "boolean" ? "boolean" : typeof value === "number" ? "integer" : "text",
          default: value, apply_mode: "immediate", editable_layers: ["role", "window"]}])),
      tts: {state: "ready", providers: []}};
    return original(endpoint);
  };
}

async function run({pageRoot, output}) {
  await fs.mkdir(output, {recursive: true});
  const browser = await chromium.launch({headless: true,
    executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH, args: ["--enable-unsafe-swiftshader"]});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}, reducedMotion: "no-preference"});
  const report = {checks: [], frames: [], errors: []};
  page.on("pageerror", error => report.errors.push(error.message));
  await page.addInitScript(syntheticBridge);
  await page.addInitScript(editorBridge);
  await page.addInitScript(() => {
    /* 首次入场另有验收，本脚本从已就绪的页面验证后续过渡。 */
    localStorage.setItem("companion-v2-motion", "off");
  });
  const settle = () => page.waitForFunction(() => !document.getAnimations().some(animation =>
    animation.playState === "running" && animation.effect?.getTiming().iterations !== Infinity));
  const capture = name => page.screenshot({path: path.join(output, name + ".png")});
  async function visit(section) {
    await page.locator(`#shellNav [data-shell-section="${section}"]`).click();
    await page.locator(`#homeShell[data-section="${section}"]`).waitFor();
  }
  async function fullMotion() {
    await page.evaluate(() => {
      window.CompanionProduct.setAppearance("motion", "full");
      updateAppearance();
    });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
  }
  async function layout() {
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    assert.equal(await page.locator("#shellPanel:not([hidden])").count() <= 1, true);
  }
  try {
    await page.goto(pathToFileURL(path.join(pageRoot, "index.html")).href);
    await page.locator(".home-state-board").waitFor();
    await page.locator("#stageScene canvas").waitFor();
    await page.waitForFunction(() => document.documentElement.hasAttribute("data-room-ready"));
    await page.waitForFunction(() => !document.body.classList.contains("is-entrance"));
    await settle();
    const canvas = await page.locator("#stageScene canvas").elementHandle();
    await fullMotion();
    const furnitureButton = page.locator("#homeShell .stage-furniture-strip button").first();
    await furnitureButton.hover();
    const hoverTransform = await furnitureButton.evaluate(element => getComputedStyle(element).transform);
    await page.mouse.down();
    const pressTransform = await furnitureButton.evaluate(element => getComputedStyle(element).transform);
    assert.notEqual(hoverTransform, "none");
    assert.notEqual(pressTransform, hoverTransform, "press feedback replaces the hover lift");
    await page.mouse.move(0, 0);await page.mouse.up();
    report.checks.push("家具入口的悬停与按压使用不同反馈");
    await visit("appearance");await settle();
    await fullMotion();
    const navigationButton = await page.locator('[data-shell-section="perception"]').elementHandle();
    await page.locator('[data-shell-section="perception"]').focus();
    await page.keyboard.press("Enter");
    assert.equal(await navigationButton.evaluate(element => element === document.activeElement && element.isConnected), true);
    assert.equal(await page.locator('#shellNav [aria-current="page"]').count(), 1);
    await settle();await layout();
    report.checks.push("键盘切页保留同一导航按钮与焦点，活动页语义同步");
    const frames = await page.evaluate(() => new Promise(resolve => {
      const start = performance.now(), samples = [];
      document.querySelector('[data-shell-section="output"]').click();
      function sample() {
        const body = document.querySelector(".shell-panel-body"), style = getComputedStyle(body);
        const marker = document.querySelector(".shell-nav-indicator").getBoundingClientRect();
        samples.push({at: performance.now() - start, opacity: Number(style.opacity), transform: style.transform, markerTop: marker.top});
        if (performance.now() - start < 400) requestAnimationFrame(sample); else resolve(samples);
      }
      requestAnimationFrame(sample);
    }));
    report.frames = frames;
    assert(frames.some(frame => frame.opacity < .95), "page content fades in");
    assert(frames.some(frame => frame.transform !== "none"), "page content moves briefly");
    assert(Math.abs(frames.at(-1).opacity - 1) < .001);
    assert(new Set(frames.map(frame => Math.round(frame.markerTop))).size >= 3, "navigation selection slides continuously");
    await settle();await capture("desktop-output");
    report.checks.push("页面内容有连续淡入与轻位移，导航选中块平滑滑动");
    await page.evaluate(() => {render();render();});await settle();
    assert.equal(await page.locator(".shell-panel-body").evaluate(element => element.getAnimations().length), 0);
    report.checks.push("同一页面的数据重绘不重播切页动效");
    await page.evaluate(() => {
      for (const section of ["appearance", "output", "perception", "expression"]) {
        document.querySelector(`[data-shell-section="${section}"]`).click();
      }
    });
    await page.locator("#replyWorkspace textarea").first().waitFor();await settle();
    assert.equal(await page.locator("#homeShell").getAttribute("data-section"), "expression");
    await page.evaluate(() => navigate("manage", "expression", "segment"));await settle();
    const input = page.locator('#replyWorkspace [data-wb-field="prompt"]');
    await input.waitFor();await input.fill("动效验收的未保存草稿");
    const editor = await page.locator("#replyWorkspace").elementHandle();
    await page.locator('[data-expression-module="expression-platform"]').click();await settle();
    await page.locator('[data-expression-module="expression-text"]').click();await settle();
    await page.evaluate(() => CompanionReplyPage.selectSection("segment", {scroll: false}));await settle();
    assert.equal(await input.inputValue(), "动效验收的未保存草稿");
    assert.equal(await editor.evaluate(element => element.isConnected), true);
    assert.equal(await canvas.evaluate(element => element.isConnected), true);
    report.checks.push("快速切页最终状态正确，模块切换保留回复草稿和小屋 canvas");
    await visit("output");await settle();
    const preview = await page.evaluate(() => {
      activateOutputTab("materials");
      return document.getElementById("output-panel-materials").getAnimations().length;
    });
    assert(preview > 0, "local tab switch animates");await settle();
    report.checks.push("页内标签切换有独立过渡，并在结束后释放动画");
    await page.evaluate(() => {
      const details = document.createElement("details");details.id = "motion-qa-details";
      details.innerHTML = '<summary>验收展开区域</summary><div style="padding:16px">内容第一行<br>内容第二行<br>内容第三行</div>';
      document.querySelector(".shell-panel-body").prepend(details);
    });
    const collapsed = await page.locator("#motion-qa-details").evaluate(element => element.getBoundingClientRect().height);
    await page.locator("#motion-qa-details summary").click();
    assert.equal(await page.locator("#motion-qa-details").getAttribute("open"), "");
    await settle();
    const expanded = await page.locator("#motion-qa-details").evaluate(element => element.getBoundingClientRect().height);
    assert(expanded > collapsed + 40);
    await page.locator("#motion-qa-details summary").focus();await page.keyboard.press("Enter");await settle();
    assert.equal(await page.locator("#motion-qa-details").getAttribute("open"), null);
    await page.waitForFunction(expected => {
      const details = document.getElementById("motion-qa-details");
      return details && Math.abs(details.getBoundingClientRect().height - expected) < 1;
    }, collapsed);
    report.checks.push("折叠内容可用鼠标和键盘开合，关闭后恢复正常高度");
    await page.locator("#searchButton").click();
    await page.locator("#searchDialog[open]").waitFor();await settle();await capture("desktop-search");
    assert.equal(await page.locator("#globalSearch").evaluate(element => element === document.activeElement), true);
    await page.keyboard.press("Escape");await settle();
    assert.equal(await page.locator("#searchDialog").getAttribute("open"), null);
    assert.equal(await page.locator("#searchButton").evaluate(element => element === document.activeElement), true);
    report.checks.push("搜索弹窗开合和遮罩过渡正常，Escape 关闭并归还焦点");
    await page.evaluate(() => {document.documentElement.dataset.motion = "off";});
    await visit("appearance");
    assert.equal(await page.locator(".shell-panel-body").evaluate(element => element.getAnimations().length), 0);
    await page.evaluate(() => {document.documentElement.dataset.motion = "low";});
    await visit("output");
    const lowFrames = await page.locator(".shell-panel-body").evaluate(element => element.getAnimations().flatMap(animation => animation.effect.getKeyframes()));
    assert(lowFrames.length > 0);
    assert(lowFrames.every(frame => !frame.transform));await settle();
    await fullMotion();
    await page.evaluate(() => {
      document.querySelector('[data-shell-section="appearance"]').click();
      document.documentElement.dataset.motion = "off";
    });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
    assert.equal(await page.locator(".shell-panel-body").evaluate(element => element.getAnimations().length), 0);
    await fullMotion();await page.emulateMedia({reducedMotion: "reduce"});await visit("output");
    assert.equal(await page.locator(".shell-panel-body").evaluate(element => element.getAnimations().length), 0);
    report.checks.push("减弱只淡入，关闭和系统减少动效均停止位移及正在运行的动画");
    await page.emulateMedia({reducedMotion: "no-preference"});
    for (const [width, height] of [[960, 900], [390, 844], [320, 740]]) {
      await page.setViewportSize({width, height});await fullMotion();await visit("appearance");await settle();await layout();
      await page.locator("#shellPanel").scrollIntoViewIfNeeded();await capture("appearance-" + width);
      await page.locator("#searchButton").click();await settle();await layout();await capture("search-" + width);
      await page.keyboard.press("Escape");await settle();
    }
    report.checks.push("960、390、320 像素下页面与弹窗无横向溢出，控件仍可操作");
    await page.evaluate(() => navigate("life", "home"));await settle();await layout();
    assert.equal(await canvas.evaluate(element => element.isConnected), true);
    assert.deepEqual(report.errors, []);
    await fs.writeFile(path.join(output, "page-motion-results.json"), JSON.stringify(report, null, 2) + "\n", "utf8");
    console.log(JSON.stringify({checks: report.checks, writes: 0, errors: report.errors}, null, 2));
  } catch (error) {
    await capture("failure").catch(() => {});
    await fs.writeFile(path.join(output, "failure.json"), JSON.stringify({error: error.message, ...report}, null, 2) + "\n", "utf8");
    throw error;
  } finally {await browser.close();}
}

if (require.main === module) run({
  pageRoot: path.resolve(process.argv[3] || path.join(__dirname, "../pages/陪伴小屋")),
  output: path.resolve(process.argv[2] || "build/page-motion-qa"),
}).catch(error => {console.error(error);process.exitCode = 1;});
module.exports = {run};
