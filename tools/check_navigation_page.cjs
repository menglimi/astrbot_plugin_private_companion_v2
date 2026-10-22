/* Navigation acceptance with the installed SDK, sandboxed frames and read-only synthetic data. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const http = require("node:http");
const {chromium} = require("playwright");

async function run({pageRoot, output, bridgePath}) {
  const HOST = "astrbot_plugin_private_companion", calls = [], errors = [], checks = [];
  await fs.mkdir(output, {recursive: true});
  const sdk = await fs.readFile(bridgePath, "utf8");
  const api = name => `/${HOST}/host/targets/qa/roles/qa/${name}`;
  const extensions = ["content", "image", "together", "game", "screen", "reality", "live"].map(id => ({
    capability_id: id, extension_id: id, owner: "companion_v2", assembled: true,
    label: id, enabled: true, runtime_ready: true, integration_state: "connected", pages: [],
    version: "qa-native", installed_package_version: "qa-native", desired_state: "active",
  }));
  const extensionSettings = Object.fromEntries(["together", "game", "reality", "live"].map(id => [id, {
    revision: "qa-native", settings: {enabled:true},
    schema: {enabled:{type:"bool", description:"启用能力", default:true}},
    runtime: {state:"running"},
  }]));
  const replySettings = {enabled: false, llm_controlled: true, prompt: "", max_segments: 4,
    voice_enabled: false, voice_extra_prompt: "", part_gap_ms: 0, image_position: "after_text", voice_language: "zh",
    style_prompt: "", content_cleanup_enabled: false, content_cleanup_words: "[]"};
  const isOfflinePreview = call => call.action === "api:post"
    && call.endpoint === "host/targets/qa/roles/qa/reply/preview";
  const fixture = endpoint => {
    if (endpoint === "page/targets") return {mode: "multi", installation_id: "navigation-qa",
      operator_id: "dashboard:qa", acquaintance_api: `/${HOST}/acquaintance`, targets: [{
        target_id: "qa", scope_kind: "private", participant_id: "合成对象", bot_id: "qa-bot", platform_id: "qq", account_id: "qa-bot",
        roles: [{role_id: "合成角色", ...Object.fromEntries(["life", "state", "growth", "memory", "relationships", "reply", "persona"].map(name => [name + "_api", api(name)]))}],
      }]};
    if (endpoint === "page/ownership") return {owner: "self", reason: "owner_module_absent"};
    if (endpoint === "integration/manifest") return {extensions, providers: [], core: [], summary: {connected_count: 7, extension_ready_count: 7, provider_count: 0}};
    if (endpoint === "extensions") return {extensions:extensionSettings};
    if (endpoint === "acquaintance") return {persons: [], groups: [], counts: {total: 0}};
    if (endpoint === "semantic") return {state:"ready",selection_ready:true,settings:{revision:1},
      providers:{embedding:[],rerank:[],analysis:[]},catalog:{reaction:{enabled:0},slang:{enabled:0}},sessions:[],items:[],errors:{}};
    if (endpoint.endsWith("/life")) return {role_id: "合成角色", participant: "合成对象", host_state: "new",
      config: {enabled: false, diary_enabled: false, diary_time: "23:50", timezone: "Asia/Shanghai",
        sleep_enabled: false, sleep_time: "00:30", sleep_timezone: "Asia/Shanghai", sleep_minutes: 480},
      sleep_schedule: {enabled: false, executor_state: "unavailable"}, journals: [], activities: [], receipts: [], running: []};
    if (endpoint.endsWith("/state")) return {state: {state: "ready", revision: 1, values: {energy: 75, health: "稳定", sleep: "清醒"}},
      settings: {}, sleep_schedule: {enabled: false}, calendar: {items: []}, occurrences: {items: []}, presentation: {state: "preview"}};
    if (endpoint.endsWith("/growth")) return {items: [], next_cursor: null,
      access: {settings: {read_enabled: true, proposals_enabled: false}, effective: {
        read_enabled: {allowed: true}, proposals_enabled: {allowed: false}}, edit_token: "a".repeat(64)}};
    if (endpoint.endsWith("/relationships")) return {role_id: "合成角色", scope_label: "合成对象", items: [], next_cursor: null};
    if (endpoint.endsWith("/persona")) return {persona: {resolved: true, name: "合成人格", text: "合成原文"}, versions: [], count: 0};
    if (endpoint.endsWith("/reply")) return {settings: replySettings, edit_token: "b".repeat(64), recent: [],
      fields: Object.fromEntries(Object.entries(replySettings).map(([name, value]) => [name,
        {kind: typeof value === "boolean" ? "boolean" : typeof value === "number" ? "integer" : "text", default: value,
         apply_mode: "immediate", editable_layers: ["window"]}])),
      tts: {state: "ready", providers: []}};
    if (endpoint.endsWith("/status")) return {enabled: false, state: "new", delivery_mode: "preview", targets: []};
    return {items: [], next_cursor: null};
  };
  const wrapper = `<!doctype html><meta charset="utf-8"><style>body{margin:0}iframe{width:100%;height:100vh;border:0;display:block}</style>
    <iframe id="cottage" sandbox="allow-scripts allow-forms" src="/page/index.html#life"></iframe><script>
    addEventListener('message',async event=>{const frame=document.getElementById('cottage'),m=event.data;
      if(event.source!==frame.contentWindow||m.channel!=='astrbot-plugin-page')return;
      const send=data=>frame.contentWindow.postMessage({channel:'astrbot-plugin-page',...data},'*');
      if(m.kind==='ready'){send({kind:'context',context:{pluginName:'${HOST}',pageName:'陪伴小屋'}});return;}
      if(m.kind!=='request')return;
      const response=await fetch('/rpc',{method:'POST',body:JSON.stringify(m)});
      send({kind:'response',requestId:m.requestId,ok:true,data:await response.json()});
    });</script>`;
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://127.0.0.1");
      if (url.pathname === "/") {res.setHeader("Content-Type", "text/html;charset=utf-8");res.end(wrapper);return;}
      if (url.pathname === "/api/plugin/page/bridge-sdk.js") {res.setHeader("Content-Type", "text/javascript;charset=utf-8");res.end(sdk);return;}
      if (url.pathname === "/rpc") {
        const chunks = [];for await (const chunk of req) chunks.push(chunk);
        const message = JSON.parse(Buffer.concat(chunks).toString("utf8"));calls.push(message);
        const data = message.action === "api:get" ? fixture(message.endpoint)
          : isOfflinePreview(message) ? {mode: "offline_preview", parts: [message.body.text], count: 1,
              characters: Array.from(message.body.text).length, planned_spacing_ms: 0,
              image_position: "after_text", image_count: 0, instruction: "",
              components: [{speech: "", success_order: ["text"], fallback_order: ["text"], text_hidden: false}],
              voice: {enabled: false, instruction: ""}}
          : {status: "error", message: "Read-only navigation check"};
        res.setHeader("Content-Type", "application/json;charset=utf-8");res.end(JSON.stringify(data));return;
      }
      if (!url.pathname.startsWith("/page/")) {res.writeHead(404).end();return;}
      const file = path.resolve(pageRoot, decodeURIComponent(url.pathname.slice(6)));
      if (!file.startsWith(pageRoot + path.sep)) {res.writeHead(403).end();return;}
      const mime = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".jpg": "image/jpeg", ".gif": "image/gif", ".woff2": "font/woff2"};
      res.setHeader("Content-Type", (mime[path.extname(file)] || "application/octet-stream") + ";charset=utf-8");
      res.end(await fs.readFile(file));
    } catch (error) {errors.push(error.message);res.writeHead(500).end();}
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const browser = await chromium.launch({headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
    args: ["--enable-unsafe-swiftshader"]});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}, reducedMotion: "reduce"});
  page.on("pageerror", error => errors.push(error.message));
  const shell = page.frameLocator("#cottage"), body = shell.locator("body");
  const evaluate = fn => body.evaluate(fn);
  const locationHash = () => evaluate(() => location.hash);
  const visit = async hash => {
    await body.evaluate((_body,value) => {location.hash = value;}, hash);
    await body.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  };
  try {
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await shell.locator(".stage-role-title").filter({hasText:"合成角色"}).waitFor();
    for (const section of ["identity", "contact", "memory", "learning", "models", "maintenance", "perception", "understanding", "decision", "action", "output", "expression", "governance", "setup", "appearance", "host", "data"]) {
      await shell.locator(`[data-shell-section="${section}"]`).click();
      const expectedHash = section === "host" ? "#manage"
        : section === "learning" ? "#manage/learning/overview"
        : section === "data" ? "#manage/data/storage" : "#manage/" + section;
      assert.equal(await locationHash(), expectedHash);
      assert.equal(await shell.locator("#homeShell").getAttribute("data-section"), section);
      const text=(await shell.locator(".shell-panel-body").innerText()).trim();
      const frames=shell.locator(".product-workspace-frame");
      assert.ok(text.length||await frames.count(), section + " must have content");
      for(const frame of await frames.all())assert.ok((await frame.getAttribute("srcdoc")).length, section + " must mount its embedded content");
    }
    checks.push("all_17_navigation_sections_render");
    await shell.locator("#railBrand").click();
    assert.equal(await shell.locator("#homeShell").getAttribute("data-away"), "false");
    assert.equal(await shell.locator("#shellPanel").isVisible(), false);
    await shell.locator("[data-shell-furniture=wardrobe]").click();
    await shell.locator("#shellPanel [data-output-target=materials]").click();
    assert.equal(await shell.locator("#output-panel-materials").isVisible(), true);
    checks.push("brand_returns_home_and_wardrobe_opens_materials");
    await body.evaluate(() => showDetail("profile"));
    assert.equal(await shell.locator("#self-panel-profile").isVisible(), true);
    await body.evaluate(() => showDetail("album"));
    assert.equal(await shell.locator("#output-panel-materials").isVisible(), true);
    checks.push("profile_opens_self_and_album_opens_materials");
    for (const [extension, tab] of [["content", "creation"], ["image", "materials"]]) {
      await body.evaluate((_body,id) => showDetail("cap-" + id), extension);
      await shell.locator(`#detailDialog [data-output-target=${tab}]`).first().click();
      assert.equal(await shell.locator("#output-panel-" + tab).isVisible(), true);
    }
    checks.push("native_content_and_image_open_cottage_workspaces");
    for (const extension of extensions.map(item => item.capability_id)) {
      await body.evaluate((_body,id) => showDetail("cap-" + id), extension);
      if (["together", "game", "reality", "live"].includes(extension)) {
        await shell.locator(`[data-native-extension-host="${extension}"] .native-extension-panel`).waitFor();
      }
      assert.match(await shell.locator("#detailDialog").innerText(), /V2 内置能力/);
      assert.equal(await shell.locator('#detailDialog input[id^="provider-page-"]').count(), 0);
      assert.equal(await shell.locator('#detailDialog [data-copy-address]').count(), 0);
      assert.equal(await shell.locator('#detailDialog a[href*="plugin-page"]').count(), 0);
      assert.equal(await body.evaluate((_body,id) => window.CompanionProduct.providerAddress(id), extension), "");
      await shell.locator("[data-close-detail]").click();
    }
    checks.push("seven_native_extensions_stay_inside_the_cottage");
    await visit("#manage/expression");
    const editor = await shell.locator("#replyWorkspace").elementHandle();
    await shell.locator('[role="tab"][data-expression-module="expression-voice"]').click();
    assert.equal(await shell.locator('#expression-panel-expression-voice').isVisible(), true);
    assert.equal(await shell.locator('#expression-panel-expression-text').isVisible(), false);
    await shell.locator('[role="tab"][data-expression-module="expression-voice"]').press('ArrowRight');
    assert.equal(await shell.locator('#expression-panel-expression-reaction').isVisible(), true);
    await shell.locator('[role="tab"][data-expression-module="expression-text"]').click();
    assert.equal(await locationHash(), "#manage/expression");
    assert.equal(await editor.evaluate(el => el.isConnected), true);
    await shell.locator("#reply-preview-result .reply-preview-part").waitFor();
    await shell.locator("#toast.show").waitFor({state: "hidden"});
    await page.screenshot({path: path.join(output, "expression-desktop.png")});
    for (const [width, height] of [[700, 900], [390, 844], [320, 720]]) {
      await page.setViewportSize({width, height});
      await shell.locator(".expression-page .wb-section-sidebar").scrollIntoViewIfNeeded();
      assert.equal(await evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      const initialBounds = await shell.locator(".expression-module-nav").evaluate(el => {
        const nav = el.getBoundingClientRect();
        const sidebar = document.querySelector(".expression-page .wb-section-sidebar");
        const subnav = sidebar.getBoundingClientRect();
        const choices = sidebar.querySelector(".wb-section-nav");
        const choicesRect = choices.getBoundingClientRect();
        const choiceBounds = [...choices.querySelectorAll(".wb-section-tab")].map(item => {
          const rect = item.getBoundingClientRect();return {left: rect.left, right: rect.right};
        });
        return {top: nav.top, bottom: nav.bottom, subnavTop: subnav.top,
          choicesFit: choices.scrollWidth <= choices.clientWidth + 1
            && choiceBounds.every(item => item.left >= choicesRect.left - 1 && item.right <= choicesRect.right + 1),
          choiceWidth: choices.clientWidth, choiceScrollWidth: choices.scrollWidth, choiceBounds};
      });
      assert.ok(initialBounds.subnavTop >= initialBounds.bottom, "the configuration navigation stays below the expression tabs");
      assert.equal(initialBounds.choicesFit, true,
        `all expression configuration choices remain visible at ${width}px: ${JSON.stringify(initialBounds)}`);
      await page.screenshot({path: path.join(output, "expression-" + width + ".png")});
      await evaluate(() => window.scrollBy({top: 180, behavior: "instant"}));
      assert.equal(await shell.locator('.expression-module-nav [role="tab"][aria-selected="true"]').count(), 1);
      assert.equal(await shell.locator('[role="tab"][data-expression-module="expression-text"]').getAttribute("aria-selected"), "true");
      assert.equal(await editor.evaluate(el => el.isConnected), true);
      assert.equal(await locationHash(), "#manage/expression");
    }
    await page.setViewportSize({width: 1440, height: 1000});
    checks.push("anchors_keep_the_editor_and_current_route");
    await visit("#life");
    await shell.locator('[data-detail="arrange"]').click();
    await shell.locator("#roomEditor").waitFor();
    for (const [width, height] of [[1440, 1000], [390, 844], [320, 720]]) {
      await page.setViewportSize({width, height});
      await page.waitForTimeout(250);
      assert.equal(await evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false,
        `the room editor fits the ${width}px viewport`);
      assert.equal(await shell.locator('#roomEditor [data-room-house][aria-pressed="true"]').count(), 1);
      assert.ok(await shell.locator('#roomEditor [data-room-furniture] option').count());
      for (const group of ["ambience", "furniture", "placement-group"]) {
        assert.equal(await shell.locator("#roomEditor .room-editor-" + group).isVisible(), true);
      }
      await page.screenshot({path: path.join(output, "room-editor-" + width + ".png"), fullPage: true});
      const canvas = await shell.locator("#stageScene canvas").boundingBox();
      assert.ok(canvas && canvas.width > 100 && canvas.height > 100,
        `the 3D room canvas has a stable size at ${width}px`);
      await shell.locator("#stageScene").screenshot({path: path.join(output, "room-stage-" + width + ".png")});
      await shell.locator('#roomEditor [data-room-coordinate="x"]').scrollIntoViewIfNeeded();
      assert.equal(await shell.locator('#roomEditor [data-room-coordinate="x"]').isVisible(), true);
      assert.equal(await evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    }
    await page.setViewportSize({width: 1440, height: 1000});
    await page.screenshot({path: path.join(output, "room-editor-placement-1440.png"), fullPage: true});
    await shell.locator('[data-room-cancel]').click();
    await shell.locator("#roomEditor").waitFor({state: "detached"});
    checks.push("room_editor_controls_fit_desktop_and_mobile_with_a_rendered_scene");
    await visit("#manage/reply/voice");
    await shell.locator('[role="tab"][data-expression-module="expression-voice"][aria-selected="true"]').waitFor();
    await shell.locator('#replyWorkspace [data-wb-field="voice_extra_prompt"]').waitFor();
    checks.push("tts_deep_link_selects_voice_after_async_load");
    for (const [detail, tab] of [["reading", "reading"], ["sleep", "sleep"], ["desk", "archive"]]) {
      await body.evaluate((_body,id) => showDetail(id), detail);
      const inner = shell.frameLocator('[data-workspace="life"] iframe');
      await inner.locator(`[data-tab="${tab}"][aria-current="page"]`).waitFor();
      assert.equal(await shell.locator('[data-workspace="life"]').getAttribute("data-workspace-tab"), tab);
    }
    checks.push("reading_sleep_and_archive_open_their_real_embedded_tabs");
    for (const pane of ["relationship", "questionnaire", "knowledge"]) {
      await visit("#manage/governance/" + pane);
      assert.equal(await shell.locator("#self-panel-" + pane).isVisible(), true);
      assert.equal(await locationHash(), "#manage/governance/" + pane);
      if(pane==="questionnaire")await shell.frameLocator('[data-workspace="persona"] iframe').locator("#persona-name").filter({hasText:"合成人格"}).waitFor();
    }
    checks.push("self_subpages_follow_deep_links");
    await visit("#manage/models");
    await shell.locator("[data-shell-section=expression]").click();
    await evaluate(() => history.back());
    await shell.locator('#homeShell[data-section="models"]').waitFor();
    checks.push("browser_back_restores_the_previous_section");
    await visit("#life");
    await shell.locator("[data-shell-furniture=wardrobe]").click();
    await shell.locator("#toast.show").waitFor({state: "hidden"});
    for (const [width, height] of [[1440, 1000], [390, 844], [320, 720]]) {
      await page.setViewportSize({width, height});
      assert.equal(await evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      await shell.locator("#shellPanel").scrollIntoViewIfNeeded();
      await page.screenshot({path: path.join(output, "wardrobe-" + width + ".png")});
      await shell.locator("#stageScene").screenshot({path:path.join(output,"room-"+width+".png")});
    }
    await shell.locator("#shellPanel [data-shell-home]").click();
    assert.equal(await shell.locator("#shellPanel").isVisible(), false);
    checks.push("desktop_and_mobile_navigation_fit_and_return_home");
    assert.equal(calls.filter(call => call.action !== "api:get" && !isOfflinePreview(call)).length, 0);
    assert.deepEqual(errors, []);
    const report = {checks, reads: calls.filter(call => call.action === "api:get").length,
      previews: calls.filter(isOfflinePreview).length, writes: 0, errors};
    await fs.writeFile(path.join(output, "navigation-results.json"), JSON.stringify(report, null, 2) + "\n", "utf8");
    console.log(JSON.stringify(report, null, 2));
  } catch(error) {
    await page.screenshot({path:path.join(output,"failure.png")}).catch(()=>{});
    await fs.writeFile(path.join(output,"failure.json"),JSON.stringify({error:error.message,checks,errors,calls},null,2)+"\n","utf8");
    throw error;
  } finally {await browser.close();await new Promise(resolve => server.close(resolve));}
}

run({pageRoot: path.resolve(process.argv[4] || path.join(__dirname, "../pages/陪伴小屋")),
  output: path.resolve(process.argv[2] || "build/navigation-qa"),
  bridgePath: process.argv[3] || path.resolve(__dirname, "../../../../backend/app/astrbot/dashboard/plugin_page_bridge.js"),
}).catch(error => {console.error(error);process.exitCode = 1;});
