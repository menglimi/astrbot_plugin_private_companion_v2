/* Headless host-lifecycle UI checks against the installed AstrBot page bridge. */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const http = require("node:http");
const path = require("node:path");

async function run({browser, outputDir, bridgePath}) {
  const root = path.resolve(__dirname, "../pages/宿主管理");
  await fs.mkdir(outputDir, {recursive: true});
  const sdk = await fs.readFile(bridgePath, "utf8");
  const qa = {mode: "single", calls: [], posts: [], allPosts: [], denied: false, probed: false,
    state: {enabled: true, settings_valid: true, settings_error: null,
      profile_id: "demo-preview-20260924", delivery_mode: "preview", configured: false,
      runtime_open: false, session_state: "unloaded", accepting: false, last_failure: null,
      model_request_sent_by_status: false, platform_message_sent_by_status: false}};
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const ok = (data) => ({status: "ok", data});
  const error = (code) => ({status: "error", message: "request rejected", data: {code}});
  function routeStatus() {
    if (qa.mode === "multi") return {mode: "multi", enabled: true, installation_id: "synthetic-v2-installation",
      state: qa.state.state || "uninitialized", accepting: Boolean(qa.state.accepting), delivery_mode: "preview",
      group_delivery_mode: "preview", targets: [
        {target_id: "private-a", scope_kind: "private", platform_id: "qq", account_id: "100", bot_id: "bot-a",
          participant_id: "200", delivery_mode: "preview", roles: [{role_id: "晨星", persona_ids: ["persona-a"]}]},
        {target_id: "group-a", scope_kind: "group", platform_id: "qq", account_id: "100", bot_id: "bot-a",
          group_id: "300", delivery_mode: "preview", roles: [{role_id: "晨星", persona_ids: ["persona-a"]}]},
        {target_id: "private-b", scope_kind: "private", platform_id: "qq", account_id: "101", bot_id: "bot-b",
          participant_id: "201", delivery_mode: "preview", roles: [{role_id: "晚星", persona_ids: ["persona-b"]}]},
        ...Array.from({length: 7}, (_, index) => ({
          target_id: `private-extra-${index + 1}`, scope_kind: "private", platform_id: "qq",
          account_id: index % 2 ? "101" : "100", bot_id: index % 2 ? "bot-b" : "bot-a",
          participant_id: String(210 + index), delivery_mode: "preview",
          roles: [{role_id: index % 2 ? "晚星" : "晨星", persona_ids: [index % 2 ? "persona-b" : "persona-a"]}],
        })),
      ], last_failure: null, settings_error: null};
    return qa.state;
  }
  async function rpc(message) {
    const {action, endpoint, params = {}, body = {}} = message;
    qa.calls.push(clone(message));
    assert.equal(endpoint.startsWith("/"), false, "bridge endpoints remain plugin-relative");
    assert.equal(/[?#%\\:]/.test(endpoint), false, "bridge endpoint contains no identity override or URL syntax");
    if (qa.denied) return error("core_access_required");
    const prefix = qa.mode === "multi" ? "host" : "staging";
    if (qa.mode === "multi" && endpoint.startsWith("staging/")) {
      return {status: "error", message: "未找到该路由", data: {}};
    }
    if (qa.mode === "single" && endpoint.startsWith("host/")) {
      return {status: "error", message: "未找到该路由", data: {}};
    }
    if (endpoint === `${prefix}/status` && action === "api:get") return ok(clone(routeStatus()));
    if (action !== "api:post") throw new Error(`Unexpected bridge method ${action} ${endpoint}`);
    assert.deepEqual(body, {}, "lifecycle requests carry no caller-supplied identity or target");
    const operation = endpoint.slice(prefix.length + 1);
    qa.posts.push({mode: qa.mode, operation});
    qa.allPosts.push({mode: qa.mode, operation});
    if (operation === "probe") {
      qa.probed = true;
      return ok(qa.mode === "multi"
        ? {installation_id: "synthetic-v2-installation", targets: 2, group_targets: 0,
          model_request_sent: false, platform_message_sent: false}
        : {profile_id: qa.state.profile_id, target_ready: true,
          model_request_sent: false, platform_message_sent: false});
    }
    if (operation === "initialize") {
      assert.equal(qa.probed, true, "the page requires a successful probe before enabling initialization");
      if (qa.mode === "multi") qa.state.state = "new";
      else Object.assign(qa.state, {configured: true, runtime_open: true, session_state: "new"});
      return ok({initialized: true, started: false});
    }
    if (operation === "start") {
      assert.equal(qa.mode === "multi" ? qa.state.state === "new" : qa.state.runtime_open, true,
        "the page does not start an uninitialized host");
      if (qa.mode === "multi") qa.state.state = "running";
      else qa.state.session_state = "running";
      qa.state.accepting = true;
      return ok({state: "running"});
    }
    if (operation === "stop") {
      if (qa.mode === "multi") qa.state.state = "stopped";
      else qa.state.session_state = "stopped";
      qa.state.accepting = false;
      return ok({state: "stopped"});
    }
    throw new Error(`Unexpected lifecycle route ${endpoint}`);
  }
  const wrapper = `<!doctype html><meta charset="utf-8"><style>body{margin:0}iframe{display:block;width:100%;height:1100px;border:0}</style>
    <iframe src="/page/index.html" title="Companion V2 账号与会话"></iframe><script>
    addEventListener('message',async event=>{const frame=document.querySelector('iframe'),m=event.data;
      if(event.source!==frame.contentWindow||m.channel!=='astrbot-plugin-page')return;
      const send=v=>frame.contentWindow.postMessage({channel:'astrbot-plugin-page',...v},location.origin);
      if(m.kind==='ready'){send({kind:'context',context:{pluginName:'astrbot_plugin_private_companion_v2',pageName:'宿主管理'}});return;}
      if(m.kind!=='request')return;
      try{const response=await fetch('/qa',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(m)});
        send({kind:'response',requestId:m.requestId,ok:true,data:await response.json()});}
      catch(error){send({kind:'response',requestId:m.requestId,ok:false,error:'模拟连接中断'});}
    });<\/script>`;
  const serverErrors = [];
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://127.0.0.1");
      if (url.pathname === "/" || url.pathname === "/multi" || url.pathname === "/denied") {
        qa.mode = url.pathname === "/multi" ? "multi" : "single";
        qa.denied = url.pathname === "/denied";
        if (qa.mode === "single") qa.state = {enabled: true, settings_valid: true, settings_error: null,
          profile_id: "demo-preview-20260924", delivery_mode: "preview", configured: false,
          runtime_open: false, session_state: "unloaded", accepting: false, last_failure: null,
          model_request_sent_by_status: false, platform_message_sent_by_status: false};
        if (qa.mode === "multi") qa.state = {state: "uninitialized", accepting: false};
        qa.probed = false;
        qa.posts.length = 0;
        res.setHeader("Content-Type", "text/html; charset=utf-8"); res.end(wrapper); return;
      }
      if (url.pathname === "/bridge.js") {
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
      let payload = await fs.readFile(file);
      if (relative === "index.html") payload = Buffer.from(payload.toString("utf8")
        .replace("</body>", '<script src="/bridge.js"></script></body>'), "utf8");
      res.setHeader("Content-Type", ({".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8"})[path.extname(file)] || "application/octet-stream");
      res.end(payload);
    } catch (error) {
      if (error.code !== "ENOENT") serverErrors.push(String(error.stack));
      res.writeHead(500).end();
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const page = await browser.newPage({viewport: {width: 1280, height: 900},
    reducedMotion: process.env.HOST_PAGE_REDUCED_MOTION || "reduce"});
  const browserErrors = [];
  page.on("pageerror", (error) => browserErrors.push(String(error)));
  const frame = () => page.frameLocator("iframe");
  const loc = (selector) => frame().locator(selector);
  const checks = [];
  async function ready() { await loc("#status-heading").filter({hasText: /配置已加载/}).waitFor(); }
  async function clickConfirm(id) {
    await loc(`#${id}`).click();
    await loc("#confirm").evaluate((element) => { if (!element.open) throw new Error("confirmation dialog did not open"); });
    await loc("#confirm-action").click();
  }
  async function waitNotice(text) {
    try { await loc("#notice").filter({hasText: text}).waitFor({timeout: 5000}); }
    catch {
      throw new Error(`notice ${JSON.stringify(text)} missing; current=${JSON.stringify(await loc("#notice").innerText().catch(() => ""))}; calls=${JSON.stringify(qa.calls)}; posts=${JSON.stringify(qa.posts)}`);
    }
  }
  try {
    const origin = `http://127.0.0.1:${server.address().port}`;
    await page.goto(origin); await ready();
    assert.equal(qa.calls.length, 1, "initial render reads status only");
    assert.equal(qa.posts.length, 0, "initial render never mutates the host");
    assert.equal(await loc("#initialize").isDisabled(), true);
    assert.equal(await loc("#start").isDisabled(), true);
    assert.match(await loc("#safety-note").innerText(), /平台不会收到回复/);
    checks.push("single_status_load_is_read_only_and_preview_mode_is_clear");

    await loc("#probe").click(); await waitNotice("探测通过");
    assert.deepEqual(qa.posts, [{mode: "single", operation: "probe"}]);
    assert.equal(await loc("#initialize").isDisabled(), false);
    checks.push("probe_is_explicit_and_enables_initialization");

    await clickConfirm("initialize"); await waitNotice("运行档已初始化");
    assert.deepEqual(qa.posts.map((item) => item.operation), ["probe", "initialize"]);
    assert.equal(await loc("#start").isDisabled(), false);
    checks.push("initialize_requires_confirmation_and_keeps_host_stopped");

    await clickConfirm("start"); await waitNotice("宿主已启动");
    assert.equal(await loc("#accepting").innerText(), "正在接管消息");
    assert.equal(await loc("#stop").isDisabled(), false);
    await clickConfirm("stop"); await waitNotice("宿主已停止");
    assert.deepEqual(qa.posts.map((item) => item.operation), ["probe", "initialize", "start", "stop"]);
    checks.push("start_and_stop_require_confirmation_and_follow_status");

    await page.goto(origin + "/multi"); await ready();
    assert.equal(qa.calls.some((item) => item.endpoint === "host/status"), true);
    assert.equal(qa.calls.some((item) => item.endpoint === "staging/status"), true);
    assert.match(await loc("#profile").innerText(), /synthetic-v2-installation/);
    assert.equal(await loc("#topology-canvas").isVisible(), true);
    assert.match(await loc("#topology-accounts").innerText(), /100/);
    assert.match(await loc("#topology-personas").innerText(), /晨星/);
    assert.match(await loc("#topology-sessions").innerText(), /私聊 200|群 300/);
    assert.equal(await loc("#topology-session-pagination").isVisible(), true);
    assert.match(await loc("#topology-session-page").innerText(), /第 1 \/ 2 页/);
    const sessionListStyle = await loc("#topology-sessions").evaluate((element) => {
      const style = getComputedStyle(element);
      return {maxHeight: style.maxHeight, overflowY: style.overflowY};
    });
    assert.notEqual(sessionListStyle.maxHeight, "none");
    assert.equal(sessionListStyle.overflowY, "auto");
    await loc('.topology-node[data-topology-kind="persona"]').first().click();
    assert.equal(await loc('.topology-node[data-topology-kind="persona"]').first().getAttribute("aria-pressed"), "true");
    assert.equal(await loc("#topology-links .topology-line.is-active").count() > 0, true);
    await loc('.topology-node[data-topology-kind="persona"]').first().press("Escape");
    assert.equal(await loc('.topology-node[data-topology-kind="persona"]').first().getAttribute("aria-pressed"), "false");
    assert.match(await loc("#topology-note").innerText(), /点击任意节点/);
    await loc("#topology-session-next").click();
    assert.match(await loc("#topology-session-page").innerText(), /第 2 \/ 2 页/);
    assert.equal(await loc("#topology-session-next").isDisabled(), true);
    assert.match(await loc("#topology-sessions").innerText(), /私聊 216/);
    await loc("#topology-session-prev").click();
    assert.match(await loc("#topology-session-page").innerText(), /第 1 \/ 2 页/);
    await page.screenshot({path: path.join(outputDir, "host-management-multi-topology.png"), fullPage: true});
    await page.setViewportSize({width: 320, height: 800});
    const topologyMobile = await frame().locator("body").evaluate(() => ({viewport: innerWidth, content: document.documentElement.scrollWidth}));
    assert(topologyMobile.content <= topologyMobile.viewport + 1, JSON.stringify(topologyMobile));
    await page.screenshot({path: path.join(outputDir, "host-management-multi-topology-mobile-320.png"), fullPage: true});
    await page.setViewportSize({width: 1280, height: 900});
    checks.push("multi_target_topology_renders_accounts_personas_windows_and_highlights_paths");
    await loc("#probe").click(); await waitNotice("探测通过");
    await clickConfirm("initialize"); await waitNotice("运行档已初始化");
    await clickConfirm("start"); await waitNotice("宿主已启动");
    assert.deepEqual(qa.posts.map((item) => item.operation), ["probe", "initialize", "start"]);
    checks.push("multi_host_uses_shared_lifecycle_routes");

    await page.goto(origin + "/denied");
    await loc("#notice").filter({hasText: "没有账号与会话管理权限"}).waitFor();
    assert.equal(await loc("#probe").isDisabled(), true);
    assert.equal(qa.posts.length, 0);
    checks.push("unauthorized_dashboard_user_cannot_run_lifecycle_actions");

    await page.goto(origin); await ready();
    await page.screenshot({path: path.join(outputDir, "host-management-desktop.png"), fullPage: true});
    await page.setViewportSize({width: 320, height: 800});
    const size = await frame().locator("body").evaluate(() => ({viewport: innerWidth, content: document.documentElement.scrollWidth}));
    assert(size.content <= size.viewport + 1, JSON.stringify(size));
    await loc("#refresh").focus(); await page.keyboard.press("Tab");
    assert.equal(await loc("#probe").evaluate((element) => element === document.activeElement), true);
    await page.screenshot({path: path.join(outputDir, "host-management-mobile-320.png"), fullPage: true});
    checks.push("mobile_320_layout_and_keyboard_focus");

    assert.deepEqual(browserErrors, []); assert.deepEqual(serverErrors, []);
    const report = {checks, passed: checks.length, synthetic_posts: qa.allPosts.length, browserErrors, serverErrors};
    await fs.writeFile(path.join(outputDir, "host-management-browser-results.json"), JSON.stringify(report, null, 2) + "\n", "utf8");
    return report;
  } finally {
    await page.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

module.exports = {run};
if (require.main === module) {
  (async () => {
    const browser = await require("playwright").chromium.launch({headless: true,
      ...(process.env.HOST_PAGE_CHROMIUM ? {executablePath: process.env.HOST_PAGE_CHROMIUM} : {})});
    try { console.log(JSON.stringify(await run({browser, outputDir: process.argv[2], bridgePath: process.argv[3]}), null, 2)); }
    finally { await browser.close(); }
  })().catch((error) => { console.error(error); process.exitCode = 1; });
}
