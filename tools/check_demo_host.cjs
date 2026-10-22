/* Exercise the shipped page against real SDK routes, controllers and SQLite. */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");

async function run(origin, output) {
  const {chromium} = require("playwright");
  const browser = await chromium.launch({headless: true,
    ...(process.env.HOST_PAGE_CHROMIUM ? {executablePath: process.env.HOST_PAGE_CHROMIUM} : {})});
  const context = await browser.newContext({viewport: {width: 1280, height: 900}, reducedMotion: "reduce"});
  const external = [], errors = [], checks = [];
  await context.route("**/*", (route) => {
    if (new URL(route.request().url()).origin === origin) return route.continue();
    external.push(route.request().url());
    return route.abort();
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => errors.push(String(error)));
  const loc = (selector) => page.frameLocator("iframe").locator(selector);
  const snapshot = async () => (await context.request.get(origin + "/__fixture__/snapshot")).json();
  const fixture = async (endpoint) => {
    const response = await context.request.post(origin + "/__fixture__/" + endpoint);
    assert.equal(response.status(), 200, await response.text());
    return response.json();
  };
  const notice = async (text) => {
    try { await loc("#notice").filter({hasText: text}).waitFor({timeout: 10000}); }
    catch (error) {
      console.error("DEMO NOTICE", await loc("#notice").innerText().catch(() => ""));
      console.error("DEMO UI SNAPSHOT", await snapshot().catch(() => ""));
      throw error;
    }
  };
  const ready = () => loc("#status-heading").filter({hasText: "配置已加载"}).waitFor();
  const confirm = async (id, message) => {
    await loc("#" + id).click();
    await loc("#confirm-action").click();
    await notice(message);
  };
  const preview = async (batch, mode) => {
    const endpoint = mode === "single" ? "staging" : "host";
    const params = new URLSearchParams({batch_id: batch.batch_id});
    if (mode === "multi") params.set("target_id", batch.target_id);
    const response = await context.request.get(`${origin}/api/plug/astrbot_plugin_private_companion/${endpoint}/preview?${params}`);
    const result = await response.json();
    assert.equal(result.status, "ok", JSON.stringify(result));
    assert.equal(result.data.sent, false);
    assert.equal(result.data.parts.map((part) => part.text).join(""), "我在这里。");
  };
  try {
    await page.goto(origin); await ready();
    const initial = await snapshot();
    const {mode, phase} = initial;
    const expectedInputs = mode === "single" ? 1 : 2;
    assert.equal(initial.status.accepting, false);
    assert.equal(initial.model_calls, 0);
    assert.equal(initial.platform_calls, 0);
    assert(initial.api_calls.every((call) => call.method === "GET"));
    checks.push("page_load_is_read_only_with_real_sdk_dispatch");

    if (phase === "fresh") {
      assert.equal(initial.batches.length, 0);
      assert.equal(await loc("#initialize").isDisabled(), true);
      assert.equal(await loc("#start").isDisabled(), true);
      await loc("#probe").click(); await notice("探测通过");
      assert.equal(await loc("#initialize").isDisabled(), false);
      assert.equal((await snapshot()).model_calls, 0);
      checks.push("native_probe_enables_explicit_initialization");

      await loc("#initialize").click();
      await loc("#cancel").click();
      assert.equal((await snapshot()).api_calls.filter((c) => c.path.endsWith("/initialize")).length, 0);
      await confirm("initialize", "运行档已初始化");
      assert.equal((await snapshot()).status.accepting, false);
      checks.push("confirmation_creates_real_profile_without_starting");

      // A dialog's previous returnValue must not turn Escape into confirmation.
      const before = (await snapshot()).api_calls.length;
      await loc("#start").click();
      await page.keyboard.press("Escape");
      await loc("#confirm").waitFor({state: "hidden"});
      await loc("#refresh").click();
      assert.equal((await snapshot()).status.accepting, false);
      assert.equal((await snapshot()).api_calls.slice(before).filter((c) => c.method === "POST").length, 0);
      checks.push("escape_after_previous_confirmation_never_starts_host");

      await fixture("connection/disconnect");
      await confirm("start", "启动未完成");
      assert.equal((await snapshot()).status.accepting, false);
      assert.equal((await snapshot()).model_calls, 0);
      await fixture("connection/restore");
      checks.push("disconnected_native_account_keeps_intake_closed");
    } else {
      assert.equal(initial.batches.length, expectedInputs);
      assert.equal(await loc("#initialize").isDisabled(), true);
      assert.equal(await loc("#start").isDisabled(), false);
      for (const batch of initial.batches) await preview(batch, mode);
      checks.push("new_process_loads_existing_drafts_without_model_replay");
    }

    await confirm("start", "宿主已启动");
    assert.equal((await snapshot()).status.accepting, true);
    checks.push("page_start_arms_real_plugin_entry");

    if (phase === "fresh") {
      const result = await fixture("input");
      assert(result.events_claimed.every(Boolean));
      assert.equal(result.batches.length, expectedInputs);
      assert.equal(result.model_calls, expectedInputs);
      for (const batch of result.batches) await preview(batch, mode);
      if (mode === "multi") {
        assert.equal(new Set(result.batches.map((b) => b.bot_id)).size, 2);
        const params = new URLSearchParams({target_id: "second", batch_id: result.batches[0].batch_id});
        const mismatch = await (await context.request.get(`${origin}/api/plug/astrbot_plugin_private_companion/host/preview?${params}`)).json();
        assert.equal(mismatch.data.code, "host_target_mismatch");
      }
      checks.push("sdk_messages_generate_preview_with_bot_isolation");
    } else {
      assert.equal((await snapshot()).model_calls, 0);
      checks.push("restart_preserves_batches_and_does_not_replay_generation");
    }
    await page.screenshot({path: path.join(output, "running-desktop.png"), fullPage: true});
    await confirm("stop", "宿主已停止");
    const stopped = await fixture("input");
    assert(stopped.events_claimed.every((claimed) => !claimed));
    assert.equal(stopped.batches.length, expectedInputs);
    assert.equal(stopped.model_calls, phase === "fresh" ? expectedInputs : 0);
    assert.equal(stopped.platform_calls, 0);
    checks.push("stop_releases_intake_without_new_calls_or_rows");

    await page.setViewportSize({width: 320, height: 800});
    const widths = await loc("body").evaluate(() => ({viewport: innerWidth, content: document.documentElement.scrollWidth}));
    assert(widths.content <= widths.viewport + 1);
    await page.screenshot({path: path.join(output, "stopped-mobile-320.png"), fullPage: true});
    checks.push("real_host_state_fits_mobile_page");
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    const report = {checks, browser_errors: errors, unexpected_network: external};
    await fs.writeFile(path.join(output, "browser-results.json"), JSON.stringify(report, null, 2) + "\n", "utf8");
    console.log(JSON.stringify(report));
  } finally {
    await browser.close();
  }
}

run(process.argv[2], process.argv[3]).catch(async (error) => {
  try {
    const snapshot = await (await fetch(process.argv[2] + "/__fixture__/snapshot")).text();
    console.error("DEMO SNAPSHOT", snapshot);
  } catch (_) { /* The server may already have shut down. */ }
  console.error(error);
  process.exitCode = 1;
});
