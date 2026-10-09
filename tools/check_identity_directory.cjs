/* Synthetic browser checks for directory names, tab navigation and narrow layouts. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const http = require("node:http");
const path = require("node:path");
const {chromium} = require("playwright");

function syntheticBridge(directory, initialSections) {
  const copy = value => JSON.parse(JSON.stringify(value));
  const keyOf = value => JSON.stringify([value.subject_id, ...["platform", "bot_id", "account_id", "role_id"].map(name => (value.route || value)[name])]);
  const settings = new Map(), authorizations = new Map(), receipts = new Map(), tiers = new Map();
  window.memberTestRequests = [];
  const sectionsFor = person => {
    const key = keyOf(person);
    if (!settings.has(key)) settings.set(key, copy(initialSections));
    return settings.get(key);
  };
  const authFor = person => {
    const key = keyOf(person);
    if (!authorizations.has(key)) authorizations.set(key, {policy_revision: 1, identity_revision: 1, items: [
      {capability: "conversation.reply", state: "active", managed_by: "page", revocable: true, policy_revision: 1},
      {capability: "proactive.contact", state: "off", managed_by: "page", revocable: true, policy_revision: 1},
    ]});
    const result = copy(authorizations.get(key));
    result.identity_tier = tiers.get(person.subject_id) || "standard";
    for (const item of result.items) {
      item.identity_override = result.identity_tier !== "standard";
      item.effective_state = item.identity_override ? "active" : item.state;
    }
    return result;
  };
  window.AstrBotPluginPage = {
    ready: async () => ({}),
    apiGet: async (route, person) => route === "acquaintance" ? copy(directory)
      : route.endsWith("/settings") ? {sections: copy(sectionsFor(person))} : authFor(person),
    apiPost: async (route, command) => {
      window.memberTestRequests.push({route, command: copy(command)});
      const key = command.operation_key;
      if (receipts.has(key)) return copy(receipts.get(key));
      if (window.memberTestConflict && route.endsWith("/settings")) {
        window.memberTestConflict = false;
        for (const section of Object.values(sectionsFor(command))) section.edit_token = "b".repeat(64);
        return {status: "error", data: {code: "configuration_revision_conflict"}};
      }
      let result;
      if (route.endsWith("/settings")) {
        const sections = sectionsFor(command);
        for (const [name, edit] of Object.entries(command.sections)) assertToken(edit.edit_token, sections[name].edit_token);
        for (const [name, edit] of Object.entries(command.sections)) {
          Object.assign(sections[name].settings, edit.changes);
          sections[name].revision++;
          sections[name].edit_token = String(sections[name].revision).padStart(64, "0");
        }
        result = {sections: copy(sections)};
      } else if (route.endsWith("/authorization")) {
        const state = authorizations.get(keyOf(command));
        assertToken(command.expected_revision, state.policy_revision);
        state.policy_revision++;
        state.items.find(item => item.capability === command.capability).state = command.enabled ? "active" : "revoked";
        state.items.forEach(item => {item.policy_revision = state.policy_revision;});
        result = {status: authFor(command)};
      } else if (route.endsWith("/identity")) {
        const state = authorizations.get(keyOf(command));
        assertToken(command.expected_revision, state.identity_revision);
        state.identity_revision++;
        tiers.set(command.subject_id, command.tier);
        result = {status: authFor(command)};
      } else if (route.endsWith("/admin-name")) {
        const person = directory.persons.find(person => keyOf(person) === keyOf(command));
        person.admin_nickname = command.admin_nickname;
        person.display_name = command.admin_nickname || person.platform_nickname;
        person.revision++;
        result = copy(person);
      } else throw new Error("unexpected route");
      const response = {status: "ok", data: result};
      receipts.set(key, copy(response));
      if (window.memberTestLostResponse && route.endsWith("/settings")) {
        window.memberTestLostResponse = false;
        throw new Error("response unavailable");
      }
      return response;
    },
  };
  function assertToken(actual, expected) {if (actual !== expected) throw new Error("synthetic revision mismatch");}
}

function settingsFixture() {
  const values = {
    profile: {default_nickname: "", role_relation: "", user_gender: "", user_birthday: "", user_occupation: "", interaction: "", extra: ""},
    contact: {enabled: false, automatic_enabled: false, quiet_enabled: false, max_contacts_24h: 3,
      interval_seconds: 3600, idle_seconds: 600, quiet_start: "23:00", quiet_end: "07:00", quiet_timezone: "Asia/Shanghai", style_prompt: ""},
    person: {acquaintance_enabled: true, acquaintance_learning_enabled: true, acquaintance_card_chars: 1024},
  };
  return Object.fromEntries(Object.entries(values).map(([name, settings]) => [name, {settings, revision: 1, edit_token: "a".repeat(64),
    fields: Object.fromEntries(Object.entries(settings).map(([field, value]) => [field, {
      kind: typeof value === "boolean" ? "boolean" : typeof value === "number" ? "integer" : "text",
      maximum_chars: name === "profile" ? 800 : 3000,
    }])),
  }]));
}

async function run({browser, root, outputDir}) {
  await fs.mkdir(outputDir, {recursive: true});
  const groupName = "周末读书与生活分享讨论群的完整名称";
  const person = {subject_id: "onebot-user:200", native_account_id: "200", display_name: "朋友备注与昵称的完整显示名称",
    name_basis: "platform", platform_nickname: "朋友备注与昵称的完整显示名称", account_name: "小伴", role_name: "小屋原角色",
    platform: "qq-main", bot_id: "bot-a", account_id: "100", role_id: "role-a", revision: 1,
    private_chat: true, private_target: true, settings_available: true, group_member: true,
    private: {msg_count: 8, active_days: 2},
    groups: {"300": {msg_count: 4, active_days: 1}, "301": {msg_count: 2, active_days: 1}},
    total: {msg_count: 14, active_days: 4, first_seen: "2026-10-01T12:00:00Z", last_seen: "2026-10-02T12:00:00Z"}};
  const second = {...person, display_name: "同一成员的另一角色", role_id: "role-b", role_name: "另一角色"};
  const groupNetwork = {group_id: "300", platform_id: "qq-main", bot_id: "bot-a", account_id: "100",
    role_id: "role-a", configured: true, member_count: 2, interaction_count: 5,
    updated_at: "2026-10-02T12:00:00Z", members: [
      {native_account_id: "200", subject_id: person.subject_id, display_name: person.display_name,
        group_observation: {basis: "relationship_graph", message_count: 9, active_days: 3,
          last_seen: "2026-10-02T11:58:00Z", recent: [{text: "接上话题", at: "2026-10-02T11:58:00Z"}]},
        acquaintance: {message_count: 14, active_days: 4, private_chat: true}, clues: []},
      {native_account_id: "201", display_name: "木木", aliases: [],
        group_observation: {basis: "relationship_graph", message_count: 3, active_days: 1,
          last_seen: "2026-10-02T11:59:00Z", recent: []},
        acquaintance: {message_count: 0, private_chat: false}, clues: []},
    ], edges: [{a: "200", b: "201", count: 5, tone: "banter", summary: "近期有玩笑或接梗",
      last_seen: "2026-10-02T11:59:00Z"}], unmatched_clues: []};
  const directory = {profile_id: "synthetic-profile", operator_name: "本地验收", persons: [person, second],
    groups: [{group_id: "300", display_name: groupName, platform_id: "qq-main", bot_id: "bot-a",
      account_id: "100", account_name: "小伴", role_id: "role-a",
      configured: true, member_count: 1, msg_count: 4},
             {group_id: "301", display_name: "历史读书群", configured: false, member_count: 1, msg_count: 2},
             {group_id: "302", display_name: "", configured: true, member_count: 0, msg_count: 0}],
    group_networks: [groupNetwork],
    counts: {total: 2, private_chat: 2, group_member: 2, both: 2}};
  const bridge = `(${syntheticBridge.toString()})(${JSON.stringify(directory)},${JSON.stringify(settingsFixture())});`;
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://127.0.0.1");
      if (url.pathname === "/api/plugin/page/bridge-sdk.js") {
        res.setHeader("Content-Type", "text/javascript; charset=utf-8"); res.end(bridge); return;
      }
      const assets = {"/": "pages/关系与权限/workspace.html", "/app.js": "pages/关系与权限/app.js",
        "/member-editor.js": "pages/关系与权限/member-editor.js", "/style.css": "pages/关系与权限/style.css",
        "/pages/陪伴小屋/assets/lucide.min.js": "pages/陪伴小屋/assets/lucide.min.js"};
      const filename = assets[url.pathname] || (url.pathname.endsWith("/lucide.min.js") ? assets["/pages/陪伴小屋/assets/lucide.min.js"] : null);
      if (!filename) {res.writeHead(404); res.end(); return;}
      res.setHeader("Content-Type", (filename.endsWith("html") ? "text/html" : filename.endsWith("css") ? "text/css" : "text/javascript") + "; charset=utf-8");
      res.end(await fs.readFile(path.join(root, filename)));
    } catch (error) {res.writeHead(500); res.end(String(error));}
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const context = await browser.newContext({viewport: {width: 1280, height: 900}, reducedMotion: "reduce"});
  const page = await context.newPage();
  const errors = [], screenshots = [];
  page.on("pageerror", error => errors.push(error.message));
  const layout = async () => assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  const capture = async name => {
    const filename = path.join(outputDir, name + ".png");
    await page.screenshot({path: filename, fullPage: true}); screenshots.push(filename);
  };
  try {
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.getByText("V2 数据已同步", {exact: true}).waitFor();
    const tabLabels = await page.locator(".tab[data-tab]").allTextContents();
    assert.equal(tabLabels.length, 3);
    assert.match(tabLabels[0].trim(), /^关系网\s*\d+\s*层$/);
    assert.match(tabLabels[1].trim(), /^用户\s*\d+\s*位$/);
    assert.match(tabLabels[2].trim(), /^群聊\s*\d+\s*个$/);
    assert.equal(await page.getByRole("tab", {name: /^关系网/}).getAttribute("aria-selected"), "true");
    assert.equal(await page.locator("#panel-network").isVisible(), true);
    assert.match(await page.locator("#network-summary-label").innerText(), /2 位用户 · 2 \/ 0 \/ 0/);
    assert.equal(await page.locator(".network-person-card").count(), 2);
    assert.equal(await page.locator(".network-group-card").count(), 5);
    assert.equal(await page.locator(".page-nav-caption").count(), 0);
    await page.evaluate(() => document.documentElement.style.setProperty("--t-canvas", "rgb(1, 2, 3)"));
    await page.waitForFunction(() => getComputedStyle(document.body).backgroundColor === "rgb(1, 2, 3)");
    assert.equal(await page.locator("body").evaluate(element => getComputedStyle(element).backgroundColor), "rgb(1, 2, 3)");
    await page.evaluate(() => document.documentElement.style.removeProperty("--t-canvas"));
    await page.locator(".network-group-card").filter({hasText: groupName}).click();
    assert.equal(await page.getByRole("tab", {name: /^群聊/}).getAttribute("aria-selected"), "true");
    assert.equal(await page.locator("#group-detail h3").innerText(), groupName);
    await page.getByRole("tab", {name: /^关系网/}).click();
    await page.getByRole("tab", {name: /^用户/}).click();
    assert.equal(await page.locator("#panel-people").isVisible(), true);
    await page.locator(".person-card").first().click();
    assert.match(await page.locator("#person-detail").innerText(), /朋友备注与昵称的完整显示名称/);
    await page.getByRole("tab", {name: "人工关系资料", exact: true}).click();
    await page.getByLabel("对用户的称呼", {exact: true}).fill("小舟");
    await page.getByLabel("关系定位", {exact: true}).fill("搭档");
    await page.getByRole("tab", {name: "联系偏好", exact: true}).click();
    await page.getByLabel("24 小时联系上限", {exact: true}).fill("5");
    await page.getByRole("button", {name: "保存资料", exact: true}).click();
    await page.getByText("成员资料已保存。", {exact: true}).waitFor();
    const firstSave = await page.evaluate(() => window.memberTestRequests.find(request => request.route.endsWith("/settings")).command);
    assert.equal(firstSave.route.role_id, "role-a");
    assert.equal(firstSave.sections.profile.changes.default_nickname, "小舟");
    assert.equal(firstSave.sections.contact.changes.max_contacts_24h, 5);
    const acquaintanceButton = page.getByRole("button", {name: "熟人卡", exact: true});
    await acquaintanceButton.click();
    const acquaintanceDialog = page.locator(".member-dialog-host");
    await acquaintanceDialog.waitFor();
    assert.match(await acquaintanceDialog.innerText(), /互动记忆[\s\S]*自动积累[\s\S]*最近互动/);
    const acquaintanceLearning = page.getByRole("switch", {name: "持续更新熟人卡", exact: true});
    await acquaintanceLearning.waitFor({state: "attached"});
    await page.waitForFunction(() => !document.querySelector('[aria-label="持续更新熟人卡"]').disabled);
    await acquaintanceLearning.uncheck();
    await page.waitForFunction(() => !document.querySelector('.member-dialog-host .member-primary').disabled);
    await acquaintanceDialog.getByRole("button", {name: "保存资料", exact: true}).click();
    await page.getByText("成员资料已保存。", {exact: true}).waitFor();
    assert.equal(await page.evaluate(() => window.memberTestRequests.filter(request => request.route.endsWith("/settings")).at(-1).command.sections.person.changes.acquaintance_learning_enabled), false);
    await page.keyboard.press("Escape");
    await acquaintanceDialog.waitFor({state: "detached"});
    assert.equal(await acquaintanceButton.evaluate(element => document.activeElement === element), true);
    await page.getByRole("tab", {name: "人工关系资料", exact: true}).click();
    await page.getByLabel("对用户的称呼", {exact: true}).fill("保留的草稿");
    await page.locator(".person-card").filter({hasText: second.display_name}).click();
    await page.getByLabel("对用户的称呼", {exact: true}).waitFor();
    await page.waitForFunction(() => !document.querySelector('[aria-label="对用户的称呼"]').disabled);
    assert.equal(await page.getByLabel("对用户的称呼", {exact: true}).inputValue(), "");
    await page.locator(".person-card").filter({hasText: person.display_name}).click();
    assert.equal(await page.getByLabel("对用户的称呼", {exact: true}).inputValue(), "保留的草稿");
    await page.evaluate(() => {window.memberTestConflict = true;});
    await page.getByRole("button", {name: "保存资料", exact: true}).click();
    await page.getByText("设置已有更新，草稿已保留，请核对后重新保存。", {exact: true}).waitFor();
    await page.waitForFunction(() => !document.querySelector('[aria-label="对用户的称呼"]').disabled);
    assert.equal(await page.getByLabel("对用户的称呼", {exact: true}).inputValue(), "保留的草稿");
    await page.getByRole("button", {name: "保存资料", exact: true}).click();
    await page.getByText("成员资料已保存。", {exact: true}).waitFor();
    await page.getByLabel("对用户的称呼", {exact: true}).fill("回复丢失后的重试");
    await page.evaluate(() => {window.memberTestLostResponse = true;});
    await page.getByRole("button", {name: "保存资料", exact: true}).click();
    await page.getByText("操作未完成，草稿已保留，请重新读取后重试。", {exact: true}).waitFor();
    await page.getByRole("button", {name: "保存资料", exact: true}).click();
    await page.getByText("成员资料已保存。", {exact: true}).waitFor();
    const keys = await page.evaluate(() => window.memberTestRequests.filter(request => request.route.endsWith("/settings")).map(request => request.command.operation_key));
    assert.equal(keys.at(-1), keys.at(-2), "an uncertain save retries its original operation key");
    await layout(); await capture("member-profile-desktop");
    await page.getByRole("tab", {name: "身份与权限", exact: true}).click();
    await page.getByRole("button", {name: "保存身份", exact: true}).waitFor();
    await page.getByRole("switch", {name: "允许主动联系", exact: true}).check();
    await page.getByText("允许主动联系已开启。", {exact: true}).waitFor();
    await page.getByRole("radio", {name: /重要用户/}).click();
    await page.getByRole("button", {name: "保存身份", exact: true}).click();
    await page.getByText("已保存为重要用户。", {exact: true}).waitFor();
    assert.equal(await page.getByRole("switch", {name: "允许私聊对话", exact: true}).isDisabled(), true);
    assert.doesNotMatch(await page.locator("#person-detail").innerText(), /role-a|bot-a|onebot-user:200|synthetic-profile/);
    await layout(); await capture("directory-private-desktop");

    await page.getByRole("tab", {name: /^用户/}).focus();
    await page.keyboard.press("ArrowRight");
    assert.equal(await page.getByRole("tab", {name: /^群聊/}).getAttribute("aria-selected"), "true");
    assert.match(await page.locator("#groups-list").innerText(), /历史读书群.*群号 301/s);
    assert.match(await page.locator("#groups-list").innerText(), /群 302/);
    await page.locator(".group-card").filter({hasText: groupName}).click();
    assert.equal(await page.locator("#group-detail h3").innerText(), groupName);
    assert.match(await page.locator("#group-detail").innerText(), /群号 300/);
    await page.getByRole("button", {name: "本群回应设置", exact: true}).waitFor();
    await page.getByRole("button", {name: "群公共档案", exact: true}).waitFor();
    assert.match(await page.locator("#group-detail").innerText(), /V2 群聊接入[\s\S]*已接入/);
    assert.match(await page.locator("#group-detail").innerText(), /9 条[\s\S]*3 天/);
    assert.match(await page.locator("#group-detail").innerText(), /接上话题/);
    assert.match(await page.locator("#group-detail").innerText(), /朋友备注与昵称的完整显示名称 ↔ 木木[\s\S]*5 次/);
    await layout(); await capture("directory-group-detail-desktop");
    await page.getByLabel("搜索成员和群聊").fill("周末读书");
    assert.equal(await page.locator(".group-card").filter({hasText: groupName}).count(), 1);
    assert.equal(await page.locator(".group-card").filter({hasText: "群 302"}).count(), 0);
    await page.getByLabel("搜索成员和群聊").fill("301");
    assert.equal(await page.locator(".group-card").filter({hasText: "历史读书群"}).count(), 1);
    assert.equal(await page.locator(".group-card").filter({hasText: "群 302"}).count(), 0);
    await page.getByLabel("搜索成员和群聊").fill("");
    await layout(); await capture("directory-groups-desktop");

    await page.getByRole("tab", {name: /^关系网/}).click();
    assert.match(await page.locator(".graph-group-source[data-group-id='300'] title").textContent(), new RegExp(groupName));
    const within = await page.locator(".graph-node-title").evaluateAll(nodes => nodes.every(node => {
      const text = node.getBBox(), rect = node.parentNode.querySelector("rect").getBBox();
      return text.x >= rect.x && text.x + text.width <= rect.x + rect.width;
    }));
    assert.equal(within, true, "graph names stay inside their nodes");
    await layout(); await capture("directory-network-desktop");

    for (const width of [390, 320]) {
      await page.setViewportSize({width, height: 844});
      for (const [tab, name] of [["关系网", "network"], ["用户", "people"], ["群聊", "groups"]]) {
        await page.locator(`#tab-${tab === "关系网" ? "network" : tab === "用户" ? "people" : "groups"}`).click();
        if (tab === "用户") for (const [pane, key] of [["人工关系资料", "profile"], ["身份与权限", "access"], ["联系偏好", "contact"]]) {
          await page.getByRole("tab", {name: pane, exact: true}).click();
          await layout(); await capture(`member-${key}-${width}`);
        }
        await layout(); await capture(`directory-${name}-${width}`);
      }
    }
    assert.deepEqual(errors, []);
    const report = {passed: 16, errors, screenshots};
    await fs.writeFile(path.join(outputDir, "directory-results.json"), JSON.stringify(report, null, 2) + "\n", "utf8");
    return report;
  } finally {
    await context.close();
    await new Promise(resolve => server.close(resolve));
  }
}

if (require.main === module) (async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH});
  try {console.log(JSON.stringify(await run({browser, root: path.resolve(process.argv[2] || path.join(__dirname, "..")),
    outputDir: path.resolve(process.argv[3])}), null, 2));}
  finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
module.exports = {run};
