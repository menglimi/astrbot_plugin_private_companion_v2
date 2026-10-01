/* Local browser checks with synthetic bridge responses; never connects to AstrBot. */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");

async function run({ browser, outputDir }) {
  const root = path.resolve(__dirname, "../pages/关系与记忆");
  await fs.mkdir(outputDir, { recursive: true });
  const bridge = `(() => {
    const records = [
      { memory_id: 'a', kind: 'context', state: 'proposed', interpretation: '最近的聊天让我觉得，我们逐渐能够自在地分享生活中的小事。\\n这是一段逐渐熟悉的过程，还不能代表所有时候的感受。', source_count: 3 },
      { memory_id: 'b', kind: 'emotion_episode', state: 'adopted', interpretation: '那天一起整理计划时，我感到安心。<img src=x onerror="window.injected=true">', emotion_subject: 'role', source_count: 2 },
      { memory_id: 'c', kind: 'context', state: 'adopted', interpretation: null, unavailable_reason: 'source_revoked', source_count: 1 }
    ].map(item => ({revision: 1, view_token: 'v1', observed_at: '2026-09-23T04:00:00Z', updated_at: '2026-09-23T04:00:00Z', attribution: {}, ...item}));
    function actions(item) {
      item.actions = item.state === 'retracted' ? [] : item.unavailable_reason ? ['retract'] :
        [...(item.state === 'proposed' ? ['review'] : item.state === 'reviewed' ? ['adopt'] : []), 'revise', 'retract'];
      return item;
    }
    const receipts = new Map();
    window.pageQA = { records, calls: [], effects: 0, failRead: false, loseNextResponse: false };
    window.AstrBotPluginPage = {
      ready: async () => ({}),
      apiGet: async (endpoint, params) => {
        if (endpoint !== 'relationships') throw new Error('Use a plugin-relative bridge endpoint');
        if (window.pageQA.failRead) return {status: 'error', data: {code: 'core_access_required'}};
        const filtered = records.filter(item => !params.state || item.state === params.state).map(actions);
        return {status: 'ok', data: {context_key: 'synthetic', role_id: '小伴', subject_id: '测试用户', scope_label: '测试私聊',
          operator_id: 'dashboard:qa', operator_name: '本地测试管理员', items: structuredClone(filtered), next_cursor: null}};
      },
      apiPost: async (endpoint, body) => {
        if (endpoint !== 'relationships/command') throw new Error('Unexpected write endpoint');
        window.pageQA.calls.push(structuredClone(body));
        if (receipts.has(body.operation_key)) return structuredClone(receipts.get(body.operation_key));
        const item = records.find(item => item.memory_id === body.memory_id);
        if (item.revision !== body.expected_revision) return {status: 'error', data: {code: 'relationship_memory_conflict'}};
        item.state = {review: 'reviewed', adopt: 'adopted', revise: 'proposed', retract: 'retracted'}[body.action];
        if (body.action === 'revise') { item.interpretation = body.interpretation; item.attribution = {}; }
        item.attribution[{review:'reviewed_by', adopt:'adopted_by', revise:'revised_by', retract:'retracted_by'}[body.action]] = 'dashboard:qa';
        item.revision++; item.view_token = 'v' + item.revision; actions(item); window.pageQA.effects++;
        const result = {status: 'ok', data: {item: structuredClone(item), applied_revision: item.revision}};
        receipts.set(body.operation_key, result);
        if (window.pageQA.loseNextResponse) { window.pageQA.loseNextResponse = false; throw new Error('未收到操作结果，请重试本次操作。'); }
        return result;
      }
    };
  })();`;
  const files = new Map([["/", "workspace.html"], ["/app.js", "app.js"], ["/style.css", "style.css"]]);
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://127.0.0.1");
    if (url.pathname === "/api/plugin/page/bridge-sdk.js") {
      res.setHeader("Content-Type", "text/javascript; charset=utf-8"); res.end(bridge); return;
    }
    const file = files.get(url.pathname);
    if (!file) { res.writeHead(404); res.end(); return; }
    res.setHeader("Content-Type", (file.endsWith("html") ? "text/html" : file.endsWith("css") ? "text/css" : "text/javascript") + "; charset=utf-8");
    res.end(await fs.readFile(path.join(root, file)));
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: "reduce" });
  const page = await context.newPage();
  const failures = [];
  page.on("pageerror", error => failures.push(error.message));
  const checkLayout = async () => assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  const waitIdle = () => page.waitForFunction(() => document.getElementById("list").getAttribute("aria-busy") === "false");
  const screenshots = [];
  const capture = async name => { const filename = path.join(outputDir, name + ".png"); await page.screenshot({path: filename, fullPage: true}); screenshots.push(filename); };
  try {
    await page.goto(`http://127.0.0.1:${server.address().port}/`); await waitIdle();
    assert.equal(await page.locator(".record").count(), 3);
    await page.locator(".record").first().click(); await checkLayout(); await capture("relationship-desktop");
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement.textContent), "审阅通过");
    await page.keyboard.press("Enter"); await waitIdle();
    assert.equal(await page.locator("#detail .badge").textContent(), "已审阅");
    await page.getByRole("button", {name: "采用到对话", exact: true}).click(); await waitIdle();
    assert.equal(await page.locator("#detail .badge").textContent(), "已采用");

    await page.getByRole("button", {name: "更正理解", exact: true}).click();
    await page.getByLabel("完整的关系理解").fill("更正：这是那一天的感受，需要保留当时的语境。");
    await page.evaluate(() => { window.pageQA.loseNextResponse = true; });
    await page.getByRole("button", {name: "保存更正", exact: true}).click();
    await page.locator("#dialog-error").waitFor({state: "visible"});
    assert.equal(await page.getByLabel("完整的关系理解").inputValue(), "更正：这是那一天的感受，需要保留当时的语境。");
    await page.getByRole("button", {name: "保存更正", exact: true}).click(); await waitIdle();
    const replay = await page.evaluate(() => window.pageQA.calls.slice(-2));
    assert.equal(replay[0].operation_key, replay[1].operation_key);
    assert.equal(await page.evaluate(() => window.pageQA.effects), 3);
    assert.equal(await page.locator("#detail .badge").textContent(), "待审阅");

    await page.locator(".record").nth(1).click();
    assert.equal(await page.locator("#detail img").count(), 0);
    assert.equal(await page.evaluate(() => window.injected), undefined);
    await page.locator(".record").nth(2).click();
    assert.equal(await page.locator("#detail .actions button").count(), 1);
    await page.getByRole("button", {name: "撤回记录", exact: true}).click();
    await page.getByRole("button", {name: "确认撤回", exact: true}).click(); await waitIdle();
    assert.equal(await page.locator("#detail .badge").textContent(), "已撤回");
    await page.getByLabel("筛选状态").selectOption("reviewed"); await waitIdle();
    assert.equal(await page.locator(".record").count(), 0);
    assert.equal(await page.getByRole("button", {name: "下一页", exact: true}).isDisabled(), true);
    await page.getByLabel("筛选状态").selectOption(""); await waitIdle();
    await page.setViewportSize({width: 390, height: 844});
    await page.locator(".record").first().click(); await checkLayout(); await capture("relationship-mobile");
    await page.getByRole("button", {name: "更正理解", exact: true}).click();
    await checkLayout(); await capture("relationship-mobile-editor");
    await page.keyboard.press("Escape");
    assert.equal(await page.locator("#editor").evaluate(element => element.open), false);
    await page.setViewportSize({width: 320, height: 700}); await checkLayout();
    assert.equal(await page.locator("#refresh").evaluate(element => getComputedStyle(element).transitionDuration), "0s");
    await page.evaluate(() => { window.pageQA.failRead = true; });
    await page.getByRole("button", {name: "刷新记录", exact: true}).click(); await waitIdle();
    assert.equal(await page.locator("#notice").textContent(), "当前账号没有本体管理权限。");
    assert.equal(await page.locator(".record").count(), 0);
    assert.deepEqual(failures, []);
    return {checks: "review, adopt, correction, lost response retry, retract, empty filter, denied read, XSS text, keyboard, mobile, reduced motion", screenshots};
  } finally {
    await context.close(); await new Promise(resolve => server.close(resolve));
  }
}
module.exports = {run};
if (require.main === module) {
  (async () => {
    const browser = await require("playwright").chromium.launch({headless: true});
    try { console.log(JSON.stringify(await run({browser, outputDir: await fs.mkdtemp(path.join(os.tmpdir(), "relationship-page-"))}), null, 2)); }
    finally { await browser.close(); }
  })().catch(error => { console.error(error); process.exitCode = 1; });
}
