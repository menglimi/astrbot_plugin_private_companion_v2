/* Verify the cottage boot GIF while the voxel scene is still loading.
 * NODE_PATH and PLAYWRIGHT_EXECUTABLE_PATH may point to the local runtime.
 */
"use strict";
const assert = require("node:assert/strict");
const fsSync = require("node:fs");
const fs = require("node:fs/promises");
const http = require("node:http");
const path = require("node:path");
const {chromium} = require("playwright");

const ROOT = path.resolve(__dirname, "../pages/陪伴小屋");
const TYPES = {
  ".css": "text/css; charset=utf-8",
  ".gif": "image/gif",
  ".html": "text/html; charset=utf-8",
  ".jpg": "image/jpeg",
  ".js": "text/javascript; charset=utf-8",
  ".png": "image/png",
  ".woff2": "font/woff2",
};

function createServer() {
  return http.createServer((request, response) => {
    const pathname = decodeURIComponent(new URL(request.url, "http://127.0.0.1").pathname);
    const relative = pathname.replace(/^\/+/, "") || "index.html";
    const file = path.resolve(ROOT, relative);
    if (file !== ROOT && !file.startsWith(ROOT + path.sep)) {
      response.writeHead(403).end();
      return;
    }
    const send = () => {
      const stream = fsSync.createReadStream(file);
      stream.on("error", () => {
        if (!response.headersSent) response.writeHead(404);
        response.end();
      });
      response.setHeader("content-type", TYPES[path.extname(file)] || "application/octet-stream");
      stream.pipe(response);
    };
    if (relative === "assets/voxel-room.js") setTimeout(send, 2500);
    else send();
  });
}

async function inspectBoot(page, url) {
  await page.goto(url, {waitUntil: "commit"});
  await page.waitForFunction(() => {
    const image = document.querySelector("#roomBootGif");
    return image && !image.hidden && image.complete && image.naturalWidth === 300;
  });
  return page.evaluate(() => {
    const root = document.documentElement;
    const boot = document.querySelector(".room-boot");
    const image = document.querySelector("#roomBootGif");
    const style = getComputedStyle(boot);
    return {
      source: root.dataset.roomBootGif || "",
      ready: root.hasAttribute("data-room-ready"),
      visibility: style.visibility,
      opacity: Number(style.opacity),
      hidden: image.hidden,
      width: image.naturalWidth,
      height: image.naturalHeight,
      imageSrc: image.currentSrc || image.src || "",
      preload: document.querySelector('link[rel="preload"][as="image"]')?.href || "",
    };
  });
}

(async () => {
  const server = createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const url = `http://127.0.0.1:${server.address().port}/index.html`;
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined,
  });
  try {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    const bootGifRequests = [];
    const workspaceRequests = [];
    page.on("request", request => {
      if (/room-loading-(tea-coffee|mug)\.gif/.test(request.url())) bootGifRequests.push(request.url());
      if (/workspace-bundle\.js|workspace-bundles\//.test(request.url())) workspaceRequests.push(request.url());
    });
    const visible = await inspectBoot(page, url);
    assert.match(visible.source, /room-loading-(tea-coffee|mug)\.gif/);
    const expectedSource = new URL(visible.source, url).href;
    assert.match(visible.preload, /room-loading-tea-coffee\.gif/);
    assert.equal(visible.imageSrc, expectedSource);
    assert.equal(visible.ready, false);
    assert.equal(visible.visibility, "visible");
    assert.ok(visible.opacity > 0);
    assert.equal(visible.hidden, false);
    assert.equal(visible.width, 300);
    assert.equal(visible.height, 300);
    await page.waitForFunction(() => document.documentElement.dataset.roomBootGif.includes("room-loading-mug.gif"),
      undefined, {timeout: 6000});
    assert(bootGifRequests.some(source => source.includes("room-loading-tea-coffee.gif")));
    assert(bootGifRequests.some(source => source.includes("room-loading-mug.gif")));
    assert.deepEqual(workspaceRequests, [], "workspace scripts are not fetched during cottage startup");

    const output = process.argv[2];
    if (output) {
      await fs.mkdir(path.dirname(path.resolve(output)), {recursive: true});
      await page.screenshot({path: path.resolve(output)});
    }
    await page.close();

    const reduced = await browser.newPage({
      viewport: {width: 390, height: 844},
      reducedMotion: "reduce",
    });
    const gifRequests = [];
    reduced.on("request", request => {
      if (/room-loading-(tea-coffee|mug)\.gif/.test(request.url())) gifRequests.push(request.url());
    });
    await reduced.goto(url, {waitUntil: "commit"});
    await reduced.waitForSelector(".room-boot");
    await reduced.waitForTimeout(300);
    const reducedState = await reduced.evaluate(() => ({
      selected: document.documentElement.dataset.roomBootGif || "",
      hidden: document.querySelector("#roomBootGif").hidden,
      preload: !!document.querySelector('link[rel="preload"][as="image"]'),
    }));
    assert.deepEqual(reducedState, {selected: "", hidden: true, preload: false});
    assert.deepEqual(gifRequests, []);
    console.log(JSON.stringify({visible, bootGifRequests, workspaceRequests, reduced: reducedState, gifRequests}, null, 2));
    await reduced.close();
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
