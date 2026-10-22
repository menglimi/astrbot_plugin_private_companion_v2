/* Real host-handler receipts cross the installed AstrBot SDK and product bridge. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {spawnSync} = require("node:child_process");
const {test, before, after} = require("node:test");
const {chromium} = require("playwright");
const root = path.resolve(__dirname, "..");
const pageRoot = path.join(root, "pages/陪伴小屋");
let browser, receipts, sdkSource;
before(async () => {
  const python = process.env.ASTRBOT_HOST_PYTHON;
  assert.ok(python, "ASTRBOT_HOST_PYTHON must name AstrBot's bundled Python");
  const app = path.resolve(path.dirname(python), "../app");
  sdkSource = fs.readFileSync(path.join(app, "astrbot/dashboard/plugin_page_bridge.js"), "utf8");
  const result = spawnSync(python, ["-X", "utf8", "-m", "tests.native_management_contract_process"], {
    cwd:root, encoding:"utf8", timeout:60000, maxBuffer:4 * 1024 * 1024,
    env:{...process.env, PYTHONPATH:[root, app].join(path.delimiter), PYTHONDONTWRITEBYTECODE:"1"},
  });
  assert.equal(result.status, 0, result.error?.message || result.stderr || result.stdout);
  const line = result.stdout.split(/\r?\n/).find(row => row.startsWith("NATIVE_MANAGEMENT_CONTRACT="));
  assert.ok(line, result.stdout);
  receipts = JSON.parse(line.slice("NATIVE_MANAGEMENT_CONTRACT=".length));
  browser = await chromium.launch({headless:true, ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH
    ? {executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH} : {})});
});
after(async () => { await browser?.close(); });

async function harness(initial = "initial") {
  const page = await browser.newPage({viewport:{width:1050, height:1100}});
  page.setDefaultTimeout(5000);
  await page.setContent('<!doctype html><html><body><div id="management"></div></body></html>');
  await page.evaluate(({receipts, initial}) => {
    window.receipts = receipts;
    window.currentStatus = structuredClone(receipts[initial]);
    window.requests = [];
    window.addEventListener("message", event => {
      const message = event.data;
      if (message?.channel !== "astrbot-plugin-page" || message.kind !== "request") return;
      window.requests.push(message);
      let response;
      if (window.endpointErrors?.[message.endpoint]) response = receipts[window.endpointErrors[message.endpoint]];
      else if (message.endpoint === "page/targets") response = {status:"ok", data:{
        installation_id:"synthetic", targets:[{target_id:"private", scope_kind:"private", participant_id:"200",
          roles:[{role_id:"role", role_name:"测试角色"}]}]}};
      else if (message.endpoint === "integration/manifest") response = {status:"ok", data:{extensions:[], providers:[]}};
      else if (message.endpoint === "extensions") response = window.currentStatus;
      else if (message.endpoint === "extensions/action") {
        const {action, payload} = message.body;
        const key = action === "consent_camera" ? payload.user_id === "999" ? "ineligible"
          : payload.confirmed ? "consent" : "revoke" : action === "update_camera_policy"
          ? window.currentStatus.data.extensions.reality.management.users.length ? "policy" : "missing_user"
          : ({save:"audio_saved", update_audio_policy:"audio_policy", select_audio:"audio_output"}[action] || "no_mihome_action");
        response = receipts[key];
        if (response.status === "ok") window.currentStatus.data.extensions.reality = structuredClone(response.data);
      } else throw new Error("unexpected bridge endpoint: " + message.endpoint);
      // AstrBot's parent bridge resolves inner data and rejects with message only.
      const reply = {channel:"astrbot-plugin-page", kind:"response", requestId:message.requestId,
        ok:response.status === "ok", data:response.data, error:response.message};
      if (message.endpoint === "extensions" && window.holdExtensionRead) {
        window.holdExtensionRead = false; window.heldExtensionReply = structuredClone(reply); return;
      }
      window.postMessage(reply, "*");
    });
  }, {receipts, initial});
  await page.addScriptTag({content:sdkSource});
  await page.evaluate(() => window.AstrBotPluginPage.__setInitialContext({pluginName:"astrbot_plugin_private_companion"}));
  for (const name of ["product-page.js", "native-extension-management.js"])
    await page.addScriptTag({content:fs.readFileSync(path.join(pageRoot, name), "utf8")});
  await page.evaluate(async () => {
    await window.CompanionProduct.connect();
    const result = await window.CompanionProduct.request("GET", "extensions");
    window.management = window.CompanionNativeExtensionManagement.mount(document.getElementById("management"),
      {extensionId:"reality", instance:"contract", record:result.extensions.reality});
  });
  return page;
}

test("camera-only authorization and policy survive real response serialization and refresh", async () => {
  const page = await harness();
  try {
    await page.locator("[data-native-camera-details] > summary").click();
    await page.locator("[data-native-camera-consent]").check();
    await page.getByRole("button", {name:"确认摄像头授权", exact:true}).click();
    await page.locator(".native-management-camera-state").filter({hasText:"已确认授权"}).waitFor();
    await page.locator("[data-native-camera-mode]").selectOption("auto");
    await page.getByRole("button", {name:"保存摄像头策略", exact:true}).click();
    await page.locator("[data-native-action-notice]").filter({hasText:"保存摄像头策略已完成"}).waitFor();
    await page.evaluate(() => { window.currentStatus = structuredClone(window.receipts.refreshed); });
    await page.getByRole("button", {name:"刷新管理状态", exact:true}).click();
    await page.locator("[data-native-action-notice]").filter({hasText:"管理状态已刷新"}).waitFor();
    assert.equal(await page.locator("[data-native-camera-mode]").inputValue(), "auto");
    assert.equal(await page.locator("[data-native-camera-enabled]").isChecked(), true);
    assert.equal(await page.locator("[data-native-camera-daily]").inputValue(), "-1");
    await page.getByRole("button", {name:"撤销摄像头授权", exact:true}).click();
    await page.locator(".native-management-camera-state").filter({hasText:"尚未确认"}).waitFor();
    assert.equal(await page.locator("[data-native-camera-enabled]").isChecked(), false);
  } finally { await page.close(); }
});

test("message-only errors explain policy prerequisites without granting camera authority", async () => {
  const page = await harness();
  try {
    await page.locator("[data-native-camera-details] > summary").click();
    await page.locator("[data-native-camera-enabled]").check();
    await page.getByRole("button", {name:"保存摄像头策略", exact:true}).click();
    const notice = page.locator("[data-native-action-notice]");
    await notice.filter({hasText:"请先确认该用户的摄像头授权"}).waitFor();
    assert.doesNotMatch(await notice.textContent(), /数据不完整/);
    assert.equal(await page.evaluate(() => window.management.record.management.users.length), 0);
    await page.locator("[data-native-camera-user]").fill("999");
    await page.locator("[data-native-camera-user]").dispatchEvent("change");
    await page.locator("[data-native-camera-consent]").check();
    await page.getByRole("button", {name:"确认摄像头授权", exact:true}).click();
    await notice.filter({hasText:"此用户没有主机摄像头使用权限"}).waitFor();
    assert.equal(await page.evaluate(() => window.management.record.management.users.length), 0);
  } finally { await page.close(); }
});

test("refresh shows persisted camera policy instead of default drafts when MiHome is unavailable", async () => {
  const page = await harness();
  try {
    await page.locator("[data-native-camera-details] > summary").click();
    await page.evaluate(() => {
      window.currentStatus = structuredClone(window.receipts.refreshed);
      window.currentStatus.data.extensions.reality.management.mihome = window.receipts.no_mihome.data.extensions.reality.management.mihome;
    });
    await page.getByRole("button", {name:"刷新管理状态", exact:true}).click();
    await page.locator(".native-management-camera-state").filter({hasText:"已确认授权"}).waitFor();
    assert.equal(await page.locator("[data-native-camera-mode]").inputValue(), "auto");
    assert.equal(await page.getByRole("button", {name:"扫码登录", exact:true}).isDisabled(), true);
    assert.match(await page.locator(".native-management").textContent(), /米家运行时不可用/);
    await page.locator("[data-native-camera-mode]").selectOption("ask");
    await page.getByRole("button", {name:"刷新管理状态", exact:true}).click();
    assert.equal(await page.locator("[data-native-camera-mode]").inputValue(), "ask", "real edits remain drafts");
    assert.equal(await page.evaluate(() => window.requests.filter(row => row.action === "api:post").length), 0);
  } finally { await page.close(); }
});

test("perception and furniture failures keep their codes through the installed Dashboard SDK", async () => {
  const page = await harness();
  try {
    const results = await page.evaluate(async () => {
      const cases = [["perception", "perception_denied"], ["integration/manifest", "manifest_denied"],
        ["perception", "perception_invalid"], ["integration/manifest", "manifest_invalid"]];
      const results = [];
      for (const [endpoint, receipt] of cases) {
        window.endpointErrors = {[endpoint]:receipt};
        try { await window.CompanionProduct.request("GET", endpoint); results.push({unexpected:true}); }
        catch (error) { results.push({code:error.code, message:error.message}); }
      }
      return results;
    });
    assert.deepEqual(results.map(row => row.code), ["dashboard_identity_required", "dashboard_identity_required",
      "perception_request_invalid", "integration_request_invalid"]);
    assert.match(results[2].message, /感知设置内容无效/);
    assert.match(results[3].message, /家具清单读取请求无效/);
  } finally { await page.close(); }
});

test("audio refresh adopts persisted values and preserves only edited fields before saving", async () => {
  const page = await harness("audio_before");
  try {
    await page.locator("[data-native-audio-details] > summary").click();
    await page.evaluate(() => { window.currentStatus = structuredClone(window.receipts.audio_refreshed); });
    await page.getByRole("button", {name:"刷新管理状态", exact:true}).click();
    await page.locator("[data-native-action-notice]").filter({hasText:"管理状态已刷新"}).waitFor();
    assert.equal(await page.locator('[data-native-audio-input="output_volume"]').inputValue(), "64");
    assert.equal(await page.locator('[data-native-audio-input="policy_volume"]').inputValue(), "47");
    assert.equal(await page.locator("[data-native-audio-proactive]").isChecked(), true);
    assert.equal(await page.locator("[data-native-alarm-time]").inputValue(), "08:45");
    assert.equal(await page.locator('[data-native-audio-input="repeat_count"]').inputValue(), "3");
    assert.equal(await page.evaluate(() => window.management.audioDraft), null);
    await page.locator("[data-native-alarm-message]").fill("未保存的话题");
    await page.locator("[data-native-alarm-message]").dispatchEvent("change");
    await page.evaluate(() => { window.currentStatus = structuredClone(window.receipts.audio_later); });
    await page.getByRole("button", {name:"刷新管理状态", exact:true}).click();
    await page.waitForFunction(() => window.management.record.management.users.find(row => row.user_id === "200").alarm.time === "09:20");
    assert.equal(await page.locator("[data-native-alarm-time]").inputValue(), "09:20");
    assert.equal(await page.locator('[data-native-audio-input="repeat_count"]').inputValue(), "4");
    assert.equal(await page.locator("[data-native-alarm-message]").inputValue(), "未保存的话题");
    assert.deepEqual(await page.evaluate(() => window.management.audioDraft), {alarm:{message:"未保存的话题"}});
    await page.getByRole("button", {name:"保存叫醒安排", exact:true}).click();
    await page.locator("[data-native-action-notice]").filter({hasText:"保存叫醒安排已完成"}).waitFor();
    const payload = await page.evaluate(() => window.requests.findLast(row => row.endpoint === "extensions/action").body.payload);
    assert.equal(payload.time, "09:20");
    assert.equal(payload.repeat_count, 4);
    assert.equal(payload.message, "未保存的话题");
    assert.equal(await page.locator("[data-native-alarm-message]").inputValue(), "未保存的话题");
    assert.equal(await page.evaluate(() => window.requests.filter(row => row.action === "api:post").length), 1);
  } finally { await page.close(); }
});

test("an older refresh cannot overwrite a completed audio save", async () => {
  const page = await harness("audio_before");
  try {
    await page.locator("[data-native-audio-details] > summary").click();
    await page.evaluate(() => {
      window.holdExtensionRead = true; window.pendingManagementRead = window.management.read();
    });
    await page.waitForFunction(() => !!window.heldExtensionReply);
    await page.locator('[data-native-audio-input="output_volume"]').fill("64");
    await page.getByRole("button", {name:"保存音频输出", exact:true}).click();
    await page.locator("[data-native-action-notice]").filter({hasText:"保存音频输出已完成"}).waitFor();
    await page.evaluate(async () => {
      window.postMessage(window.heldExtensionReply, "*"); await window.pendingManagementRead;
    });
    assert.equal(await page.locator('[data-native-audio-input="output_volume"]').inputValue(), "64");
    assert.equal(await page.evaluate(() => window.management.record.management.audio_output.playback_volume), 64);
    assert.match(await page.locator("[data-native-action-notice]").textContent(), /保存音频输出已完成/);
  } finally { await page.close(); }
});

test("legitimate business data survives both direct and wrapped bridge responses", async () => {
  const page = await harness();
  try {
    const result = await page.evaluate(() => {
      const unwrap = window.CompanionProduct.unwrap;
      const payload = {state:"ready", data:{nested:true}, revision:7};
      const nested = {kind:"diagnostic", data:{status:"ok", data:{value:2}}};
      return {direct:unwrap(payload), wrapped:unwrap({status:"ok", message:"", data:payload}),
        anonymous:unwrap({data:payload}), nested:unwrap(nested)};
    });
    const payload = {state:"ready", data:{nested:true}, revision:7};
    assert.deepEqual(result.direct, payload);
    assert.deepEqual(result.wrapped, payload);
    assert.deepEqual(result.anonymous, payload);
    assert.deepEqual(result.nested, {kind:"diagnostic", data:{status:"ok", data:{value:2}}});
  } finally { await page.close(); }
});
