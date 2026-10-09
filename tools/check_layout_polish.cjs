"use strict";
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs/promises");
const {pathToFileURL} = require("node:url");
const {chromium} = require("playwright");

(async () => {
  const output = path.resolve("build/ui-layout-qa");
  await fs.mkdir(output, {recursive: true});
  const browser = await chromium.launch({headless: true,
    executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH});
  try {
    const page = await browser.newPage({reducedMotion: "reduce"});
    await page.goto(pathToFileURL(path.resolve("pages/陪伴小屋/index.html")).href + "#manage/decision");
    await page.locator("#shellPanel").waitFor();
    await page.evaluate(() => {
      document.querySelector("#shellPanel").insertAdjacentHTML("beforeend",
        '<section class="console-section"><header class="console-section-head"><div class="console-section-copy"><h2>配置分区</h2></div><p class="console-section-note">用于检查窄屏分区说明的间距与自然换行。</p></header><div class="console-section-body"></div></section>');
    });
    for (const width of [1366, 960, 390, 320]) {
      await page.setViewportSize({width, height: 900});
      await page.evaluate(() => {
        document.documentElement.dataset.typeScale = "xl";
        document.documentElement.dataset.motion = "off";
      });
      await page.waitForTimeout(150);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      if (width <= 650) {
        assert.equal(await page.locator(".console-section-note").first()
          .evaluate(el => getComputedStyle(el).flexBasis), "auto");
      }
      await page.screenshot({path: path.join(output, `decision-${width}.png`), fullPage: true});
    }
    await page.evaluate(() => {
      document.documentElement.dataset.theme = "night";
      document.querySelector(".console-section-body").insertAdjacentHTML("beforeend",
        '<div class="config-editor-fields"><label>配置项<input value="测试内容"><small>辅助说明</small></label></div>');
    });
    assert.equal(await page.locator(".config-editor-fields input").first().evaluate(el => {
      const style = getComputedStyle(el);
      const probe = document.createElement("div");
      probe.style.background = "var(--t-surface)";
      document.body.append(probe);
      const same = style.backgroundColor === getComputedStyle(probe).backgroundColor;
      probe.remove();
      return same;
    }), true);
    await page.screenshot({path: path.join(output, "night-controls.png"), fullPage: true});
    console.log("PASS: desktop/mobile XL layout, section spacing and dark controls");
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
