/* Account → role/personas → native windows, checked against the installed page SDK. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const http = require("node:http");
const path = require("node:path");

async function run({browser, outputDir, bridgePath}) {
  const root = path.resolve(__dirname, "../pages/宿主管理");
  await fs.mkdir(outputDir, {recursive: true});
  const sdk = await fs.readFile(bridgePath, "utf8");
  const qa = {shape: "", posts: [], calls: [], mappings: null, groups: null, running: false,
    statusReadFails: false, denied: false};
  const clone = value => JSON.parse(JSON.stringify(value));
  const ok = data => ({status: "ok", data});
  const error = code => ({status: "error", data: {code}});
  function accounts() {
    const first = {platform_id: "qq", account_id: "100", bot_id: "bot-a"};
    return ["partial", "shared"].includes(qa.shape) ? [first,
      {platform_id: "qq-alt", account_id: "101", bot_id: qa.shape === "shared" ? "bot-a" : "bot-b"}] : [first];
  }
  function bindings() {
    const nativeAccounts = accounts();
    const personas = [...new Map(nativeAccounts.flatMap(account =>
      (account.bot_id === "bot-a" ? ["original", "second", "[%None]"] : ["persona-b"])
        .map(persona_id => [account.bot_id + ":" + persona_id, {bot_id: account.bot_id, persona_id,
          label: qa.shape === "generated" && persona_id === "original" ? "星缘-私聊" : persona_id}]))).values()];
    const mappings = qa.mappings || [{bot_id: "bot-a", persona_id: "original",
      role_id: qa.shape === "generated" ? "role-3491542998-5a8f9db0db8f6bb4" : "星缘"},
      ...(qa.shape === "native" ? [{bot_id: "bot-a", persona_id: "second", role_id: "星缘"}] : [])];
    const nativeTargets = nativeAccounts.map((account, index) => ({...account,
      target_id: "native-private-" + index, session_key: "native-private-" + index,
      participant_id: String(200 + index), scope_kind: "private",
      unified_msg_origin: account.platform_id + ":FriendMessage:" + (200 + index),
      persona_id: account.bot_id === "bot-a" ? "original" : "persona-b", native: true}));
    if (["native", "generated"].includes(qa.shape)) {
      for (const session of ["300", "200_300"]) nativeTargets.push({...nativeAccounts[0],
        target_id: "native-" + session, session_key: "native-" + session, group_id: "300",
        scope_kind: "group", unified_msg_origin: "qq:GroupMessage:" + session,
        persona_id: "second", native: true});
    }
    const targets = nativeTargets.map(target => {
      const mapped = mappings.find(row => row.bot_id === target.bot_id && row.persona_id === target.persona_id);
      return {...target, managed: Boolean(mapped), persona_override: "", session_enabled: true, llm_enabled: true,
        roles: [{role_id: mapped?.role_id || "unmapped", persona_ids: [target.persona_id]}]};
    });
    targets.push({...nativeAccounts[0], target_id: "private-template", session_key: "configured-private-template",
      participant_id: "*", scope_kind: "private", native: false, managed: true, roles: []});
    return {enabled: true, accounts: nativeAccounts, personas: mappings, sessions: [], groups: qa.groups || [
      {target_id: "group-wildcard", platform_id: "qq", account_id: "100", bot_id: "bot-a", group_id: "*"}],
      discovered: {accounts: nativeAccounts, personas, targets}};
  }
  async function rpc(message) {
    qa.calls.push(clone(message));
    const {action, endpoint, body = {}} = message;
    assert(!endpoint.startsWith("/") && !/[?#%\\:]/.test(endpoint));
    if (qa.denied) return error("core_access_required");
    if (endpoint === "accounts" && action === "api:get") return ok(bindings());
    if (endpoint === "host/status" && action === "api:get") {
      if (qa.statusReadFails) return error("host_native_lookup_timeout");
      return ok({enabled: true, settings_valid: true, state: qa.running ? "running" : "uninitialized",
        accepting: qa.running, targets: [], last_failure: null});
    }
    if (endpoint === "acquaintance" && action === "api:get") return ok({group_networks: [{
      platform_id: "qq", account_id: "100", bot_id: "bot-a", group_id: "300", role_id: "星缘",
      role_name: "星缘", member_count: 2, interaction_count: 3,
      members: [{native_account_id: "200", display_name: "阿青",
        group_observation: {message_count: 5, active_days: 2, basis: "relationship_graph"},
        acquaintance: {message_count: 8, private_chat: true, group: {message_count: 5}}, clues: []},
        {native_account_id: "201", display_name: "小禾",
          group_observation: {message_count: 3, active_days: 1, basis: "acquaintance_card"},
          acquaintance: {message_count: 3, private_chat: false, group: {message_count: 3}}, clues: []}],
      edges: [{a: "200", b: "201", count: 3, tone: "banter", summary: "近期接话"}], unmatched_clues: [],
    }]});
    if (endpoint === "accounts" && action === "api:post") {
      assert.deepEqual(Object.keys(body).sort(), "sessions" in body
        ? ["accounts", "enabled", "groups", "personas", "sessions"]
        : ["accounts", "enabled", "groups", "personas"]);
      assert(body.personas.every(row => row.bot_id && row.persona_id && row.role_id));
      assert.equal(new Set(body.personas.map(row => row.bot_id + ":" + row.persona_id)).size, body.personas.length);
      assert(Array.isArray(body.groups));
      if ("sessions" in body) assert(Array.isArray(body.sessions));
      if (qa.shape === "native" && body.groups.some(row => row.group_id !== "*")) qa.groups = clone(body.groups);
      qa.posts.push(clone(body)); qa.mappings = clone(body.personas); qa.running = true;
      return ok({saved: true, started: true, configuration: bindings()});
    }
    throw new Error("Unexpected management request: " + action + " " + endpoint);
  }
  const wrapper = '<!doctype html><meta charset="utf-8"><style>body{margin:0}iframe{display:block;width:100%;height:1100px;border:0}</style>'
    + '<iframe src="/page/index.html" title="账号与会话"></iframe><script>'
    + "addEventListener('message',async event=>{const frame=document.querySelector('iframe'),m=event.data;"
    + "if(event.source!==frame.contentWindow||m.channel!=='astrbot-plugin-page')return;"
    + "const send=v=>frame.contentWindow.postMessage({channel:'astrbot-plugin-page',...v},location.origin);"
    + "if(m.kind==='ready'){send({kind:'context',context:{pluginName:'astrbot_plugin_private_companion',pageName:'账号与会话'}});return;}"
    + "if(m.kind!=='request')return;try{const r=await fetch('/qa',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(m)});"
    + "send({kind:'response',requestId:m.requestId,ok:true,data:await r.json()});}catch(e){send({kind:'response',requestId:m.requestId,ok:false,error:e.message});}});</script>";
  const serverErrors = [], browserErrors = [], checks = [];
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://127.0.0.1");
      if (["/", "/native", "/generated", "/partial", "/shared", "/denied"].includes(url.pathname)) {
        qa.shape = url.pathname.slice(1); qa.mappings = null; qa.groups = null; qa.running = false;
        qa.statusReadFails = false; qa.denied = qa.shape === "denied"; qa.calls = []; qa.posts = [];
        res.setHeader("Content-Type", "text/html; charset=utf-8"); res.end(wrapper); return;
      }
      if (url.pathname === "/api/plugin/page/bridge-sdk.js") {
        res.setHeader("Content-Type", "text/javascript; charset=utf-8"); res.end(sdk); return;
      }
      if (url.pathname === "/qa") {
        const parts = []; for await (const part of req) parts.push(part);
        res.setHeader("Content-Type", "application/json; charset=utf-8");
        res.end(JSON.stringify(await rpc(JSON.parse(Buffer.concat(parts).toString("utf8"))))); return;
      }
      const relative = decodeURIComponent(url.pathname.replace(/^\/page\//, ""));
      const file = path.resolve(root, relative === "index.html" ? "workspace.html" : relative);
      if (!file.startsWith(root + path.sep)) {res.writeHead(404).end(); return;}
      res.setHeader("Content-Type", ({".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8"})[path.extname(file)] || "application/octet-stream");
      res.end(await fs.readFile(file));
    } catch (error) {
      if (error.code !== "ENOENT") serverErrors.push(String(error.stack));
      res.writeHead(500).end();
    }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const page = await browser.newPage({viewport: {width: 1280, height: 900}, reducedMotion: "reduce"});
  await page.addInitScript(() => {
    const nativeInterval = window.setInterval;
    window.setInterval = (callback, duration, ...args) => {
      if (duration === 15000) window.__runDirectoryRefresh = callback;
      return nativeInterval(callback, duration, ...args);
    };
  });
  page.on("pageerror", error => browserErrors.push(String(error)));
  const loc = selector => page.frameLocator("iframe").locator(selector);
  const origin = "http://127.0.0.1:" + server.address().port;
  const ready = async () => {
    await loc("#status-heading").filter({hasText: "配置已加载"}).waitFor();
    await loc('.status-panel[aria-busy="false"]').waitFor();
  };
  const save = async () => {
    await loc("#save-bindings").click();
    await loc("#notice").filter({hasText: "角色映射已保存"}).waitFor();
    await loc('.status-panel[aria-busy="false"]').waitFor();
  };
  const screenshot = async name => {
    await page.locator("iframe").evaluate(el => {el.style.height = el.contentDocument.documentElement.scrollHeight + "px";});
    await page.screenshot({path: path.join(outputDir, name), fullPage: true});
  };
  try {
    await page.goto(origin); await ready();
    assert(qa.calls.every(call => call.action === "api:get"));
    assert.equal(await loc("#probe,#start,#stop,#save-session,#edit-sessions").count(), 0);
    assert.match(await loc("#topology-heading").innerText(), /账号 → 角色 \/ 人格 → 会话窗口/);
    assert.equal(await loc("#topology-accounts .topology-node").count(), 1);
    assert.equal(await loc('#topology-roles .topology-role-group[aria-label="角色 星缘"]').count(), 1);
    assert.equal(await loc("#topology-sessions .topology-node").count(), 1);
    assert.equal(await loc('#topology-roles [data-topology-kind="persona"]').filter({hasText: "original"}).count(), 1);
    await loc("#topology-links .topology-line").last().waitFor({state: "attached"});
    await loc('#topology-roles .topology-role-heading').filter({hasText: "星缘"}).hover();
    assert.equal(await loc("#topology-links .topology-line.is-active").count(), 2);
    await loc('#topology-roles .topology-role-heading').filter({hasText: "星缘"}).click();
    assert.match(await loc("#session-manager-meta").innerText(), /1 个 AstrBot 人格/);
    assert.equal(await loc('#session-manager-related button').filter({hasText: "original"}).count(), 1);
    checks.push("account_role_persona_window_hierarchy_and_read_only_native_windows");

    await page.goto(origin + "/generated"); await ready();
    const generatedRole = loc('#topology-roles .topology-role-group[aria-label="角色 星缘"]');
    assert.equal(await generatedRole.count(), 1);
    assert.equal(await generatedRole.locator('[data-topology-kind="persona"]').count(), 1);
    assert.equal(await loc('#edit-accounts .role-binding-identity strong').first().innerText(), "星缘");
    assert.equal(await loc('#edit-accounts [data-role-id]').first().inputValue(),
      "role-3491542998-5a8f9db0db8f6bb4");
    const groupWindowKey = await loc('#topology-sessions .topology-node').filter({hasText: "群 300"}).first()
      .getAttribute("data-topology-key");
    const generatedEdges = await loc("#topology-links .topology-line").evaluateAll(lines => lines.map(line =>
      ({source: line.dataset.topologySource, target: line.dataset.topologyTarget})));
    assert(generatedEdges.some(edge => edge.target === groupWindowKey && edge.source.includes("second")));
    assert(!generatedEdges.some(edge => edge.target === groupWindowKey && edge.source.includes("original")));
    await screenshot("generated-role-desktop.png");
    await page.setViewportSize({width: 320, height: 800});
    const generatedWidth = await loc("body").evaluate(() =>
      ({viewport: innerWidth, content: document.documentElement.scrollWidth}));
    assert(generatedWidth.content <= generatedWidth.viewport + 1, JSON.stringify(generatedWidth));
    await screenshot("generated-role-mobile.png");
    await page.setViewportSize({width: 1280, height: 900});
    checks.push("generated_role_label_preserves_id_and_unmapped_group_stays_separate");

    await page.goto(origin); await ready();

    const firstRole = loc("#edit-accounts .role-binding-card").first();
    await firstRole.locator("[data-role-id]").fill("未保存的角色");
    await loc("#edit-accounts .account-binding-heading button").first().click();
    const blankRole = loc("#edit-accounts .role-binding-card").last();
    await blankRole.locator("[data-role-id]").fill("草稿角色");
    /* 未关联窗口的人格默认就不显示；取消勾选才展开，再看勾选后的收敛与保留。 */
    assert.equal(await loc("#hide-unlinked-personas").isChecked(), true);
    await loc("#hide-unlinked-personas").uncheck();
    assert.equal(await firstRole.locator("[data-role-id]").inputValue(), "未保存的角色");
    assert.equal(await blankRole.locator("[data-role-id]").inputValue(), "草稿角色");
    await loc("#hide-unlinked-personas").check();
    assert.equal(await firstRole.locator("[data-role-id]").inputValue(), "未保存的角色");
    assert.equal(await blankRole.locator("[data-role-id]").inputValue(), "草稿角色");
    assert.equal(await firstRole.locator('[data-persona-id="original"]').isChecked(), true);
    assert.equal(await firstRole.locator('[data-persona-id="second"]').isVisible(), false);
    assert.equal(await loc('#topology-roles [data-topology-kind="persona"]').filter({hasText: "second"}).count(), 0);
    await loc("#hide-unlinked-personas").uncheck();
    assert.equal(await blankRole.locator("[data-role-id]").inputValue(), "草稿角色");
    await blankRole.locator(".binding-remove").click();
    await firstRole.locator('[data-persona-id="second"]').check();
    await loc("#hide-unlinked-personas").check();
    assert.equal(await firstRole.locator('[data-persona-id="second"]').isVisible(), true);
    await save();
    assert.equal(qa.posts[0].personas.length, 2);
    assert.equal("sessions" in qa.posts[0], false);
    assert.equal(await firstRole.locator("[data-role-id]").inputValue(), "未保存的角色");
    checks.push("hide_unlinked_personas_preserves_names_empty_drafts_and_mapped_choices");

    await page.goto(origin + "/partial"); await ready();
    assert.equal(await loc("#edit-accounts .account-binding-card").count(), 2);
    assert.equal(await loc("#save-bindings").isEnabled(), true);
    await save();
    assert.deepEqual(qa.posts[0].accounts.map(account => account.account_id), ["100"]);
    assert.equal(qa.posts[0].personas.length, 1);
    checks.push("unused_accounts_do_not_block_partial_mapping_save");

    await page.goto(origin + "/shared"); await ready();
    const roleCards = loc("#edit-accounts .role-binding-card");
    await roleCards.first().locator("[data-role-id]").fill("统一角色");
    assert.equal(await roleCards.last().locator("[data-role-id]").inputValue(), "统一角色");
    /* 这个形态里 second 没有原生窗口，默认被过滤掉；先展开再勾选。 */
    await loc("#hide-unlinked-personas").uncheck();
    await roleCards.first().locator('[data-persona-id="second"]').check();
    assert.equal(await roleCards.last().locator('[data-persona-id="second"]').isChecked(), true);
    await save();
    assert.equal(qa.posts[0].accounts.length, 2);
    assert.equal(qa.posts[0].personas.length, 2);
    checks.push("accounts_sharing_one_bot_use_one_unambiguous_persona_mapping");

    await page.goto(origin + "/native"); await ready();
    const roleGroup = loc('#topology-roles .topology-role-group[aria-label="角色 星缘"]');
    assert.equal(await roleGroup.locator('[data-topology-kind="persona"]').count(), 2);
    await loc("#topology-links .topology-line").last().waitFor({state: "attached"});
    const edges = await loc("#topology-links .topology-line").evaluateAll(lines => lines.map(line =>
      ({source: line.dataset.topologySource, target: line.dataset.topologyTarget})));
    assert(edges.every(edge => edge.source.startsWith("account:") && edge.target.startsWith("persona:")
      || edge.source.startsWith("persona:") && edge.target.startsWith("session:")));
    const privatePersona = roleGroup.locator('[data-topology-kind="persona"]').filter({hasText: "original"});
    const groupPersona = roleGroup.locator('[data-topology-kind="persona"]').filter({hasText: "second"});
    await privatePersona.hover();
    assert.equal(await loc("#topology-links .topology-line.is-active").count(), 2);
    await groupPersona.hover();
    assert.equal(await loc("#topology-links .topology-line.is-active").count(), 3);
    await groupPersona.click();
    assert.match(await loc("#session-manager-heading").innerText(), /人格 second/);
    assert.equal(await loc("#session-manager-related button").count(), 2);
    checks.push("role_frames_group_personas_and_native_links_keep_persona_endpoints");
    await loc('#topology-sessions .topology-node').filter({hasText: "群 300"}).first().click();
    await loc("#session-group-network-content").filter({hasText: "阿青"}).waitFor();
    assert.match(await loc("#session-group-network-counts").innerText(), /2 人.*1 条.*3 次/);
    assert.equal(await loc("#session-persona,#save-session,#session-binding").count(), 0);
    await loc("#topology-pin-session").click();
    assert.equal(await loc("#topology-sessions .topology-node-badge.pinned").count(), 1);
    assert.equal(await loc("#group-target-list [data-group-target-choice]").count(), 1);
    assert.equal(await loc("#group-target-list [data-group-target-choice]").first().isChecked(), false);
    await loc("#group-target-list [data-group-target-choice]").first().check();
    assert.match(await loc("#group-target-state").innerText(), /尚未保存/);
    await loc("#close-session-manager").click();
    const refreshReads = qa.calls.filter(call => call.endpoint === "accounts" && call.action === "api:get").length;
    await loc("body").evaluate(() => window.__runDirectoryRefresh());
    assert.equal(qa.calls.filter(call => call.endpoint === "accounts" && call.action === "api:get").length,
      refreshReads);
    assert.equal(await loc("#group-target-list [data-group-target-choice]").first().isChecked(), true);
    await loc("#refresh").click();
    await loc('.status-panel[aria-busy="false"]').waitFor();
    assert.equal(await loc("#group-target-list [data-group-target-choice]").first().isChecked(), true);
    assert.match(await loc("#group-target-state").innerText(), /尚未保存/);
    checks.push("unsaved_group_selection_survives_periodic_and_manual_directory_refresh");
    await loc("#save-group-targets").click();
    await loc("#notice").filter({hasText: "群目标已保存并启用 1 个群"}).waitFor();
    assert.deepEqual(qa.posts.at(-1).groups.map(row => row.group_id), ["300"]);
    assert.equal("sessions" in qa.posts.at(-1), false);
    assert.equal(await loc("#group-target-list [data-group-target-choice]").first().isChecked(), true);
    checks.push("explicit_group_targets_replace_wildcard_and_confirm_effective_state");
    await screenshot("account-role-windows-desktop.png");
    await page.setViewportSize({width: 320, height: 800});
    const mobile = await loc("body").evaluate(() => ({viewport: innerWidth, content: document.documentElement.scrollWidth}));
    assert(mobile.content <= mobile.viewport + 1, JSON.stringify(mobile));
    await screenshot("account-role-windows-mobile.png");
    checks.push("native_group_and_member_windows_keep_distinct_pins_and_read_only_relationship_data");

    await page.setViewportSize({width: 1280, height: 900});
    qa.statusReadFails = true;
    await save();
    assert.match(await loc("#notice").innerText(), /角色映射已保存；运行状态暂未读到/);
    assert.doesNotMatch(await loc("#notice").innerText(), /保存未完成/);
    checks.push("saved_configuration_receipt_survives_status_refresh_failure");

    await page.goto(origin + "/denied");
    await loc("#notice").filter({hasText: "当前管理账号无权编辑角色与会话"}).waitFor();
    assert.equal(await loc("#save-bindings").isDisabled(), true);
    checks.push("unauthorized_operator_cannot_save_mappings");

    assert.deepEqual(browserErrors, []); assert.deepEqual(serverErrors, []);
    const report = {checks, passed: checks.length, browserErrors, serverErrors};
    await fs.writeFile(path.join(outputDir, "host-management-browser-results.json"), JSON.stringify(report, null, 2) + "\n", "utf8");
    return report;
  } finally {
    await page.close();
    await new Promise(resolve => server.close(resolve));
  }
}
module.exports = {run};
if (require.main === module) {
  (async () => {
    const browser = await require("playwright").chromium.launch({headless: true,
      ...(process.env.HOST_PAGE_CHROMIUM ? {executablePath: process.env.HOST_PAGE_CHROMIUM} : {})});
    try {console.log(JSON.stringify(await run({browser, outputDir: process.argv[2], bridgePath: process.argv[3]}), null, 2));}
    finally {await browser.close();}
  })().catch(error => {console.error(error); process.exitCode = 1;});
}
