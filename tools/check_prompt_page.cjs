/* Real cottage assets and the installed page SDK, using synthetic configuration only. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const http = require("node:http");
const {spawnSync} = require("node:child_process");
const {chromium} = require("playwright");

async function run({output, bridgePath, python, sourceRoot}) {
  const root = sourceRoot || path.resolve(__dirname, ".."), pageRoot = path.join(root, "pages/陪伴小屋");
  await fs.mkdir(output, {recursive: true});
  const templates = spawnSync(python, ["-X", "utf8", "-c",
    "from dataclasses import asdict; import json; from companion_v2.proactive.service import contact_profile; from companion_v2.model_gateway.management import PROMPT_LAYERS; print(json.dumps({'profile':asdict(contact_profile('synthetic')), 'layers':PROMPT_LAYERS},ensure_ascii=False))"],
    {cwd: root, encoding: "utf8"});
  assert.equal(templates.status, 0, templates.stderr);
  const {profile, layers} = JSON.parse(templates.stdout);
  const sdk = await fs.readFile(bridgePath, "utf8"), HOST = "astrbot_plugin_private_companion";
  const model = "host/targets/qa/roles/qa/model", calls = [], writes = [], errors = [], checks = [];
  const edits = new Map(), inheritedNews = "保留原人格，分享一个亮点与具体感想。", token = () => String(revision).padStart(64, "0");
  let revision = 1, conflict = false;
  const field = (value, inherited, explicit) => ({value, inherited_value: inherited,
    source: explicit ? "window" : "default", inherited_source: "default", explicit});
  function task() {
    return {kind: profile.kind, default_prompt: profile.default_prompt, prompt_version: profile.version,
      prompt_layers: layers.map(item => item.key === "request_instruction" ? {...item, editable: true} : item),
      edit_token: "a".repeat(64), fields: {prompt: field(profile.default_prompt, profile.default_prompt, false)},
      prompt_sections: profile.prompt_sections.map(section => {
        const editable = Boolean(section.field), inherited = section.key === "news_sharing" ? inheritedNews : section.default_prompt;
        const value = edits.get(section.key) ?? inherited;
        return {...section, editable, prompt: editable ? value : section.default_prompt,
          ...(editable ? {edit_token: token(), field: {...field(value, inherited, edits.has(section.key)),
            inherited_source: section.key === "news_sharing" ? "relationship" : "default",
            source: edits.has(section.key) ? "window" : section.key === "news_sharing" ? "relationship" : "default"}} : {})};
      })};
  }
  function fixture(message) {
    const action = message.method === "GET" ? "api:get" : "api:post";
    const body = message.body || {}, endpoint = String(message.path || "").replace(/^\//, "");
    calls.push({action, endpoint, body});
    if (endpoint === model + "/configure") {
      assert.equal(action, "api:post");assert.equal(body.kind, "proactive.compose");
      writes.push(body);
      if (conflict || body.edit_token !== token()) return {status: "error", data: {code: "configuration_revision_conflict"}};
      const section = profile.prompt_sections.find(item => item.key === body.section);
      assert(section?.field, "unregistered template write");
      if (body.reset.length) edits.delete(section.key);else edits.set(section.key, body.changes.prompt);
      revision++;
      return {task: task(), replayed: false};
    }
    assert.equal(action, "api:get", "unexpected mutation: " + endpoint);
    if (endpoint === model) return {tasks: [task()], providers: []};
    if (endpoint === model + "/maintenance") return {generated_at: "2026-10-08T06:00:00Z",
      summary: {}, totals: {}, recent: [], daily: [], providers: [], budget: {}};
    if (endpoint === model + "/voice") return {providers: []};
    if (endpoint === model + "/image") return {actions: []};
    if (endpoint === model + "/balance") return {configured: false, available: false};
    if (endpoint === "page/targets") return {mode: "multi", installation_id: "synthetic-prompts",
      operator_id: "dashboard:synthetic", targets: [{target_id: "qa", scope_kind: "private", participant_id: "合成对象",
        platform_id: "qq", account_id: "qa-bot", bot_id: "qa-bot", roles: [{role_id: "合成角色",
          model_api: "/" + HOST + "/" + model, ...Object.fromEntries(["state", "life", "memory", "reply", "growth", "relationships"].map(name =>
            [name + "_api", "/" + HOST + "/host/targets/qa/roles/qa/" + name]))}]}]};
    if (endpoint === "integration/manifest") return {extensions: [], providers: [], core: [], summary: {}};
    if (endpoint === "page/ownership") return {owner: "self", reason: "owner_module_absent"};
    if (endpoint.endsWith("/state")) return {state: {state: "ready", revision: 1, values: {energy: 75, sleep: "清醒"}},
      settings: {}, sleep_schedule: {enabled: false}, calendar: {items: []}, occurrences: {items: []}, presentation: {state: "preview"}};
    if (endpoint.endsWith("/life")) return {role_id: "合成角色", config: {enabled: false, diary_enabled: false},
      journals: [], activities: [], receipts: [], running: []};
    return {items: [], next_cursor: null};
  }
  const wrapper = `<!doctype html><meta charset="utf-8"><style>body{margin:0}iframe{width:100%;height:100vh;border:0;display:block}</style>
    <iframe id="cottage" title="陪伴小屋" sandbox="allow-scripts allow-forms allow-modals" src="/page/index.html#manage/maintenance/prompts"></iframe><script>
    addEventListener('message',async event=>{const frame=document.getElementById('cottage'),m=event.data;
      if(event.source!==frame.contentWindow||m.channel!=='companion-workspace')return;
      const send=data=>frame.contentWindow.postMessage({channel:'companion-workspace',...data},'*');
      if(m.kind==='ready'){send({kind:'context',context:{pluginName:'${HOST}',pageName:'陪伴小屋'}});return;}
      if(m.kind!=='request')return;
      const response=await fetch('/rpc',{method:'POST',body:JSON.stringify(m)});
      send({kind:'response',requestId:m.requestId,ok:true,data:await response.json()});
    });</script>`;
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://127.0.0.1");
      if (url.pathname === "/") {res.setHeader("Content-Type", "text/html;charset=utf-8");res.end(wrapper);return;}
      if (url.pathname === "/bridge.js") {res.setHeader("Content-Type", "text/javascript;charset=utf-8");res.end(sdk);return;}
      if (url.pathname === "/rpc") {
        const chunks = [];for await (const chunk of req) chunks.push(chunk);
        res.setHeader("Content-Type", "application/json;charset=utf-8");
        res.end(JSON.stringify(fixture(JSON.parse(Buffer.concat(chunks).toString("utf8")))));return;
      }
      if (!url.pathname.startsWith("/page/")) {res.writeHead(404).end();return;}
      const file = path.resolve(pageRoot, decodeURIComponent(url.pathname.slice(6)));
      if (!file.startsWith(pageRoot + path.sep)) {res.writeHead(404).end();return;}
      let content = await fs.readFile(file);
      if (file.endsWith(".html")) content = Buffer.from(content.toString("utf8").replace("</body>", '<script src="/bridge.js"></script></body>'));
      res.setHeader("Content-Type", ({".html": "text/html;charset=utf-8", ".js": "text/javascript;charset=utf-8",
        ".css": "text/css;charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg"})[path.extname(file)] || "application/octet-stream");
      res.end(content);
    } catch (error) {
      if (error.code === "ENOENT") {res.writeHead(404).end();return;}
      errors.push(error.stack);res.writeHead(500).end();
    }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  let browser, page;
  try {
    browser = await chromium.launch({headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH});
    page = await browser.newPage({viewport: {width: 1440, height: 1050}, reducedMotion: "reduce"});
    page.setDefaultTimeout(15000);page.on("pageerror", error => errors.push(error.message));
    const shell = page.frameLocator("#cottage"), workspace = shell.locator(".maint-prompt-section");
    const select = shell.locator("[data-prompt-section]"), draft = shell.locator("[data-prompt-draft]");
    const status = shell.locator(".maint-prompt-status"), save = shell.locator("[data-prompt-save]");
    const view = key => shell.locator(`[data-prompt-view="${key}"]`);
    const readDraft = () => draft.inputValue();
    const capture = async (name, {scrollToEditor = true} = {}) => {
      if (scrollToEditor) await shell.locator(".maint-prompt-editor").evaluate(element => element.scrollIntoView({block: "start"}));
      await page.screenshot({path: path.join(output, name + ".png")});
    };
    const layout = async () => {
      const result = await workspace.evaluate(element => {
        const overflow = [...element.querySelectorAll("input,select,textarea,button,pre,p")]
          .filter(item => item.getClientRects().length && item.getBoundingClientRect().right > innerWidth + 1)
          .map(item => item.tagName + "." + item.className);
        return {horizontal: document.documentElement.scrollWidth > innerWidth + 1, overflow};
      });
      assert.deepEqual(result, {horizontal: false, overflow: []});
    };
    await page.goto("http://127.0.0.1:" + server.address().port);
    await select.waitFor();
    assert.equal(await select.inputValue(), "expression");
    assert.match((await workspace.locator(".maint-prompt-summary").innerText()).replace(/\s+/g, " "), /1 个任务.*1 个已自定义/);
    assert.match(await workspace.locator(".maint-prompt-task-copy small").innerText(), /真实契机/);
    assert.equal(await readDraft(), profile.prompt_sections.find(item => item.key === "expression").default_prompt);
    assert.doesNotMatch(await readDraft(), /一句话能说完就只说一句/);
    checks.push("deep_link_opens_actual_expression_template");
    await capture("prompt-workspace-desktop", {scrollToEditor: false});
    await shell.locator("[data-prompt-search]").fill("来源、日期和原文链接");
    assert.equal(await shell.locator('[data-prompt-task="proactive.compose"]').count(), 1);
    await shell.locator("[data-prompt-search]").fill("");
    await select.selectOption("news_sharing");assert.equal(await readDraft(), inheritedNews);
    await draft.fill("看见新鲜事就兴冲冲分享一个亮点。\n\n自然说出自己的具体感想。");
    await select.selectOption("length");assert.equal(await select.inputValue(), "news_sharing");
    assert.match(await status.innerText(), /未保存更改/);
    await view("rules").click();assert.equal(await view("rules").getAttribute("aria-pressed"), "true");
    const rules = shell.locator("[data-prompt-rule]"), fulltext = shell.locator(".maint-prompt-fulltext");
    assert.equal(await rules.locator("option").count(), profile.prompt_sections.filter(item => !item.field).length);
    for (const section of profile.prompt_sections.filter(item => !item.field)) {
      await rules.selectOption(section.key);assert.equal((await fulltext.textContent()).trim(), section.default_prompt.trim());
    }
    await capture("prompt-rules-desktop");
    await view("composition").click();assert.equal(await view("composition").getAttribute("aria-pressed"), "true");assert.match(await workspace.innerText(), /本轮动态内容/);
    await capture("prompt-composition-desktop");
    await view("edit").click();assert.equal(await view("edit").getAttribute("aria-pressed"), "true");assert.match(await readDraft(), /自己的具体感想/);
    checks.push("fixed_templates_are_complete_and_views_preserve_draft");
    await save.click();await status.filter({hasText: "提示词已保存"}).waitFor();
    assert.equal(writes[0].section, "news_sharing");assert.equal(writes[0].edit_token, "1".padStart(64, "0"));
    await shell.locator("[data-prompt-reset]").click();await status.filter({hasText: "已恢复上级继承值"}).waitFor();
    assert.equal(await readDraft(), inheritedNews);
    checks.push("save_uses_template_token_and_reset_restores_relationship_value");
    await select.selectOption("news_length");await draft.fill("所有正文合计 {chars} 字，按亮点与感想分段。");
    conflict = true;await save.click();await status.filter({hasText: "版本冲突"}).waitFor();
    assert.match(await readDraft(), /按亮点与感想分段/);assert.equal(await save.isDisabled(), true);
    assert.equal(await shell.locator("[data-prompt-reset]").isDisabled(), true);
    await capture("prompt-conflict-desktop");
    conflict = false;edits.set("news_length", "服务器更新后的新闻正文 {chars} 字模板。");revision++;
    page.once("dialog", dialog => dialog.accept());await shell.locator("[data-prompt-discard]").click();
    await status.filter({hasText: "已载入最新服务器配置"}).waitFor();
    assert.match(await readDraft(), /服务器更新后/);
    checks.push("conflicts_keep_draft_and_confirmed_reload_reads_same_template");
    await select.selectOption("news_sharing");
    await shell.locator(".maint-prompt-default summary").filter({hasText: "查看内置默认模板"}).click();
    assert.equal(await shell.locator(".maint-prompt-preview pre").textContent(), profile.prompt_sections.find(item => item.key === "news_sharing").default_prompt);
    for (const [width, height] of [[1440, 1050], [390, 844], [320, 720]]) {
      await page.setViewportSize({width, height});await layout();await capture("prompt-editor-" + width);
      for (const key of ["rules", "composition"]) {
        await view(key).click();await layout();await capture("prompt-" + key + "-" + width);
      }
      await view("edit").click();
      await select.focus();await select.press("Tab");
      assert.equal(await draft.evaluate(element => element === document.activeElement), true);
    }
    checks.push("editor_rules_and_composition_fit_1440_390_320_and_keyboard_path");
    assert.deepEqual(errors, []);
    const report = {checks, passed: checks.length, reads: calls.filter(item => item.action === "api:get").length,
      templateWrites: writes.length, templates: profile.prompt_sections.length, errors};
    await fs.writeFile(path.join(output, "prompt-page-results.json"), JSON.stringify(report, null, 2) + "\n", "utf8");
    return report;
  } catch (error) {
    await page?.screenshot({path: path.join(output, "prompt-page-failure.png")}).catch(() => {});
    await fs.writeFile(path.join(output, "prompt-page-failure.json"), JSON.stringify({error: error.message, checks, errors, calls}, null, 2) + "\n", "utf8");
    throw error;
  } finally {
    await browser?.close();await new Promise(resolve => server.close(resolve));
  }
}

if (require.main === module) run({output: path.resolve(process.argv[2]), bridgePath: process.argv[3],
  python: process.argv[4] || "python", sourceRoot: process.argv[5] && path.resolve(process.argv[5])})
  .then(report => console.log(JSON.stringify(report, null, 2)))
  .catch(error => {console.error(error);process.exitCode = 1;});
module.exports = {run};
