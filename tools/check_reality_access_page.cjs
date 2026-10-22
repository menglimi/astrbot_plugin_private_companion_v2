"use strict";

const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const {chromium} = require("playwright");

const capabilities = [
  {key:"mobile", path:"", action:"reality.snapshot.read", title:"手机摘要",
    allowed:"允许读取手机摘要", revoke:"撤回手机摘要授权",
    saved:"已允许当前私聊读取手机摘要。", removed:"已撤回当前私聊的手机摘要授权。"},
  {key:"camera", path:"/camera", action:"reality.camera.observe", title:"摄像头单帧",
    allowed:"允许摄像头单帧观察", revoke:"撤回摄像头授权",
    saved:"已允许当前私聊按明确请求读取单帧。", removed:"已撤回当前私聊的摄像头授权。"},
  {key:"deviceList", path:"/device-list", action:"reality.device.list", title:"米家设备目录",
    allowed:"允许读取设备目录", revoke:"撤回设备目录授权",
    saved:"已允许当前私聊读取设备目录。", removed:"已撤回当前私聊的设备目录授权。"},
  {key:"deviceStatus", path:"/device-status", action:"reality.device.status", title:"单设备状态",
    allowed:"允许读取设备状态", revoke:"撤回设备状态授权",
    saved:"已允许当前私聊读取设备状态。", removed:"已撤回当前私聊的设备状态授权。"},
  {key:"deviceControl", path:"/device-control", action:"reality.device.control", title:"设备电源控制",
    allowed:"允许控制设备电源", revoke:"撤回电源控制授权",
    saved:"已允许当前私聊控制白名单设备电源。", removed:"已撤回当前私聊的电源控制授权。"},
  {key:"deviceAction", path:"/device-action", action:"reality.device.action", title:"设备属性动作",
    allowed:"允许设备属性动作", revoke:"撤回属性动作授权",
    saved:"已允许当前私聊执行设备属性动作。", removed:"已撤回当前私聊的设备属性动作授权。"},
  {key:"operationLookup", path:"/operation-lookup", action:"reality.operation.lookup", title:"操作结果查询",
    allowed:"允许查询操作回执", revoke:"撤回操作查询授权",
    saved:"已允许当前私聊查询原操作确认。", removed:"已撤回当前私聊的操作查询授权。"},
  {key:"operationCancel", path:"/operation-cancel", action:"reality.operation.cancel", title:"未派发操作取消",
    allowed:"允许取消未派发操作", revoke:"撤回操作取消授权",
    saved:"已允许当前私聊取消未派发操作。", removed:"已撤回当前私聊的操作取消授权。"},
];

async function main() {
  const root = path.resolve(__dirname, "..");
  const pageRoot = path.join(root, "pages", "陪伴小屋");
  const output = path.resolve(process.argv[2]);
  fs.mkdirSync(output, {recursive:true});
  const browser = await chromium.launch({headless:true,
    executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH,
    args:["--disable-gpu", "--disable-features=PaintHolding", "--run-all-compositor-stages-before-draw"]});
  const report = [];
  try {
    for (const [name, width, height] of [["desktop", 1440, 1000], ["mobile", 390, 844], ["narrow", 320, 740]]) {
      const page = await browser.newPage({viewport:{width,height}, reducedMotion:"reduce"});
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.setContent(`<!doctype html><html lang="zh-CN" data-theme="courtyard" data-theme-ready="true" data-room-ready="true"><head><meta charset="utf-8"></head>
        <body><main><h2>现实触及授权</h2><section id="access"></section></main></body></html>`);
      for (const stylesheet of ["tokens.css", "styles.css", "semantic-page.css", "product-page.css"])
        await page.addStyleTag({content:fs.readFileSync(path.join(pageRoot, stylesheet), "utf8")});
      await page.addStyleTag({content:`body{margin:0;padding:20px!important;background:var(--t-canvas);font:15px/1.6 system-ui}
        main{max-width:620px;margin:auto;border:1px solid var(--t-line);padding:20px;border-radius:8px}
        p{overflow-wrap:anywhere}.dialog-actions{display:flex;flex-wrap:wrap;gap:8px}button{min-height:40px}`});
      await page.evaluate(specs => {
        window.qa = {scope:"first", calls:[], defer:false, pending:[], timeout:false,
          capabilities:specs, records:Object.fromEntries(specs.map(spec => [spec.key, {revision:1, enabled:false}]))};
        window.CompanionProduct = {
          hosted:() => true, scopeKey:() => qa.scope,
          selection:() => ({target_id:qa.scope, role_id:"合成测试人格"}),
          target:() => ({bot_id:"测试 Bot"}),
          role:() => ({reality_access_api:"/astrbot_plugin_private_companion/" + qa.scope + "/reality-access"}),
          relative:path => path.slice("/astrbot_plugin_private_companion/".length),
          request:async (method, endpoint, body) => {
            qa.calls.push({method,endpoint,body});
            const prefix = qa.scope + "/reality-access";
            if (!endpoint.startsWith(prefix)) throw {code:"unexpected_endpoint"};
            const suffix = endpoint.slice(prefix.length).replace(/\/configure$/, "");
            const spec = qa.capabilities.find(item => item.path === suffix);
            if (!spec) throw {code:"unexpected_capability_path"};
            const record = qa.records[spec.key];
            if (method === "POST") {
              if (qa.timeout) { qa.timeout = false; throw {code:"bridge_timeout"}; }
              record.enabled = body.enabled; ++record.revision;
            }
            const status = {action:spec.action, invokable:record.enabled, consented:record.enabled,
              edit_token:"revision-" + record.revision,
              reason:record.enabled ? "" : "capability_consent_missing"};
            if (qa.defer && method === "GET")
              return new Promise(resolve => qa.pending.push({scope:qa.scope, finish:() => resolve(status)}));
            return method === "POST" ? {status} : status;
          },
        };
      }, capabilities);
      await page.addScriptTag({path:path.join(pageRoot, "assets", "lucide.min.js")});
      await page.addScriptTag({path:path.join(pageRoot, "reality-access.js")});
      await page.evaluate(() => CompanionRealityAccess.mount(document.querySelector("#access")));
      await page.locator(".reality-consent-panel").nth(7).waitFor({timeout:5000});
      await page.getByText("当前会话能力授权", {exact:true}).waitFor();
      assert.equal(await page.locator(".reality-consent-panel").count(), capabilities.length);
      for (const spec of capabilities) await page.getByRole("heading", {name:spec.title, exact:true}).waitFor();

      const layout = await page.evaluate(() => ({bodyPadding:getComputedStyle(document.body).paddingLeft,
        mainWidth:document.querySelector("main").getBoundingClientRect().width,
        gridColumns:getComputedStyle(document.querySelector(".reality-consent-grid")).gridTemplateColumns,
        panelBorder:getComputedStyle(document.querySelector(".reality-consent-panel")).borderTopWidth,
        refreshWhiteSpace:getComputedStyle(document.querySelector("[data-reality-access-action=refresh]")).whiteSpace}));
      assert.equal(layout.bodyPadding, "20px");
      assert.ok(layout.mainWidth <= 662);
      assert.equal(layout.gridColumns.split(" ").length, width > 650 ? 2 : 1, JSON.stringify(layout));
      assert.equal(layout.panelBorder, "1px", JSON.stringify(layout));
      assert.equal(layout.refreshWhiteSpace, "nowrap", JSON.stringify(layout));
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      await page.screenshot({path:path.join(output, name + ".png"), fullPage:true});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);

      await page.evaluate(() => {qa.timeout = true;});
      await page.locator('[data-reality-access-action="mobile-enable"]').click();
      await page.getByRole("button", {name:"核对原请求"}).waitFor();
      await page.getByRole("button", {name:"核对原请求"}).click();
      try {
        await page.getByText(capabilities[0].saved, {exact:true}).waitFor({timeout:5000});
      } catch (error) {
        const state = await page.evaluate(() => ({calls:qa.calls, panels:[...document.querySelectorAll(".reality-consent-panel")]
          .map(panel => panel.innerText)}));
        throw new Error(error.message + "\n" + JSON.stringify(state));
      }
      let calls = await page.evaluate(() => qa.calls);
      let mobilePosts = calls.filter(call => call.method === "POST"
        && call.endpoint.endsWith("/reality-access/configure"));
      assert.deepEqual(mobilePosts.at(-2).body, mobilePosts.at(-1).body,
        "an uncertain response must retry the original operation key and payload");
      assert.deepEqual(Object.keys(mobilePosts[0].body).sort(), ["edit_token","enabled","operation_key"]);

      for (const spec of capabilities) {
        if (spec.key !== "mobile") {
          await page.locator(`[data-reality-access-action="${spec.key}-enable"]`).click();
          try {
            await page.getByText(spec.saved, {exact:true}).waitFor({timeout:5000});
          } catch (error) {
            const state = await page.evaluate(key => ({calls:qa.calls.slice(-4), record:qa.records[key],
              panel:[...document.querySelectorAll(".reality-consent-panel")]
                .find(item => item.querySelector("h4")?.textContent === qa.capabilities.find(spec => spec.key === key).title)?.innerText}), spec.key);
            throw new Error(error.message + "\n" + JSON.stringify(state));
          }
        }
        await page.locator(`[data-reality-access-action="${spec.key}-disable"]`).click();
        await page.getByText(spec.removed, {exact:true}).waitFor();
      }
      calls = await page.evaluate(() => qa.calls);
      const postPaths = new Set(calls.filter(call => call.method === "POST").map(call => call.endpoint));
      assert.deepEqual(postPaths, new Set(capabilities.map(spec => "first/reality-access" + spec.path + "/configure")));

      await page.evaluate(() => {qa.defer = true;});
      await page.getByRole("button", {name:"重新读取"}).click();
      await page.waitForFunction(() => qa.pending.length === 8);
      await page.evaluate(() => {
        const oldRequests = qa.pending.slice(0, 8);
        qa.scope = "second";
        qa.records = Object.fromEntries(qa.capabilities.map(spec => [spec.key, {revision:1, enabled:false}]));
        CompanionRealityAccess.mount(document.querySelector("#access"));
        oldRequests.forEach(request => request.finish());
      });
      await page.waitForFunction(() => qa.pending.length === 16);
      assert.equal(await page.locator('[data-reality-access-action$="-disable"]').count(), 0,
        "late responses for the previous scope cannot populate the current page");
      await page.evaluate(() => qa.pending.slice(8).forEach(request => request.finish()));
      await page.locator('[data-reality-access-action="mobile-enable"]').waitFor();
      calls = await page.evaluate(() => qa.calls);
      const currentPaths = calls.slice(-8).map(call => call.endpoint);
      assert.deepEqual(new Set(currentPaths), new Set(capabilities.map(spec => "second/reality-access" + spec.path)));
      assert.deepEqual(errors, []);
      report.push({viewport:name, width, height, capability_count:capabilities.length,
        independent_enable_revoke:true, original_retry:true, late_scope_response_ignored:true,
        javascript_errors:errors, horizontal_overflow:false});
      await page.close();
    }
  } finally {await browser.close();}
  fs.writeFileSync(path.join(output, "browser-results.json"), JSON.stringify(report, null, 2) + "\n", "utf8");
  console.log(JSON.stringify(report));
}

main().catch(error => {console.error(error);process.exitCode = 1;});
