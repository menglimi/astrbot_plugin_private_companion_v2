"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const page = name => fs.readFileSync(path.join(__dirname, "../pages/陪伴小屋", name), "utf8");

function harness() {
  const location = {hash: ""}, writes = [], renders = [], scrolls = [], anchors = new Map(), targets = new Map();
  const history = Object.fromEntries(["pushState", "replaceState"].map(method => [method,
    (_state, _title, hash) => { writes.push({method, hash}); location.hash = hash; }]));
  const dialog = {open: false};
  const document = {
    documentElement: {dataset: {}},
    addEventListener() {},
    querySelectorAll: () => [],
    querySelector: selector => selector === "#detailDialog" ? dialog : targets.get(selector) || null,
    getElementById: id => anchors.get(id) || null,
  };
  const window = {location, history, addEventListener() {}, scrollTo(options) {scrolls.push(options);}, matchMedia: () => ({matches: true}),
    CompanionProduct: {scopeKey: () => "synthetic", workspace: (name, tab) => `${name}:${tab}`,
      provider: () => null, statusLabel: () => "状态已读取"},
  };
  const context = vm.createContext({window, document, location, history, console, renders,
    structuredClone, setTimeout, clearTimeout, requestAnimationFrame: callback => callback(), matchMedia: () => ({matches: true}),
    localStorage: {getItem: () => null}});
  vm.runInContext(page("shell.js"), context);
  // Run the navigation and render functions without starting the live page or SDK.
  const source = page("app.js");
  vm.runInContext(source.slice(0, source.indexOf("document.addEventListener('click'")), context);
  vm.runInContext(`render=()=>{
    if(route==='manage')window.CompanionShell.selectSection(manageTab);
    renders.push(currentNavigationHref());
  };renderShell=()=>renders.push(currentNavigationHref());`, context);
  const run = code => vm.runInContext(code, context);
  return {window, writes, renders, scrolls, run,
    target(selector, target) {targets.set(selector, target);},
    visit(hash) {location.hash = hash; run("syncFromHash()");},
    anchor(id) {
      const target = {hasAttribute: () => false, scrollIntoView() {this.scrolled = true;},
        focus() {this.focused = true;}};
      anchors.set(id, target);return target;
    }};
}

test("returning home clears configuration, diary and furniture selections", () => {
  const h = harness(), shell = h.window.CompanionShell;
  for (const destination of ["navigate('manage','models')", "navigate('life','diary','sleep')",
    "chooseFurniture('desk')", "goHomeSection('furniture')"]) {
    h.run(destination);h.run("backHome()");
    assert.equal(h.window.location.hash, "#life");
    assert.equal(shell.section, null);assert.equal(shell.view, null);assert.equal(shell.furniture, null);
  }
});

test("task prompts stay inside maintenance while direct links select the internal view", () => {
  const h = harness();
  const maintenanceButton = {attributes: {}, setAttribute(name, value) {this.attributes[name] = value;}};
  h.target('#shellNav [data-shell-section="maintenance"]', maintenanceButton);
  h.run("navigate('manage','maintenance','prompts')");
  assert.equal(h.window.location.hash, "#manage/maintenance/prompts");
  assert.equal(h.run("maintenancePane"), "prompts");
  let rail = h.run("window.CompanionShell.railHTML()");
  assert.doesNotMatch(rail, /提示词编排|data-shell-route="prompts"/);
  assert.match(rail, /data-shell-section="maintenance"[^>]*aria-pressed="true"/);

  h.visit("#manage/maintenance/cache");
  assert.equal(h.window.location.hash, "#manage/maintenance/cache");
  assert.equal(h.run("currentNavigationHref()"), "#manage/maintenance/cache");
  rail = h.run("window.CompanionShell.railHTML()");
  assert.doesNotMatch(rail, /提示词编排|data-shell-route="prompts"/);
  assert.match(rail, /data-shell-section="maintenance"[^>]*aria-pressed="true"/);
  h.run("onMaintenanceViewChange('overview')");
  assert.equal(h.window.location.hash, "#manage/maintenance");
  h.run("onMaintenanceViewChange('prompts')");
  assert.equal(maintenanceButton.attributes["aria-pressed"], "true");
  h.run("onMaintenanceViewChange('cache')");
  assert.equal(maintenanceButton.attributes["aria-pressed"], "true");

  h.visit("#manage/maintenance/unknown");
  assert.equal(h.window.location.hash, "#manage/maintenance");
});

test("maintenance subpage changes keep direct links and browser history", () => {
  const h = harness();
  h.run("navigate('manage','maintenance')");
  const entriesBeforeViewChange = h.writes.length;
  h.run("onMaintenanceViewChange('cache')");
  assert.equal(h.window.location.hash, "#manage/maintenance/cache");
  assert.equal(h.writes.length, entriesBeforeViewChange + 1);
  assert.equal(h.writes.at(-1).method, "pushState");

  h.visit("#manage/maintenance/diagnostics");
  assert.equal(h.run("maintenancePane"), "diagnostics");
  assert.equal(h.window.location.hash, "#manage/maintenance/diagnostics");
  h.run("onMaintenanceViewChange('overview')");
  assert.equal(h.window.location.hash, "#manage/maintenance");
  assert.equal(h.writes.at(-1).method, "pushState");
});

test("reply efficiency is a deep-linkable maintenance subpage", () => {
  const h = harness();
  assert.equal(h.run("manageTabs.find(([id]) => id === 'maintenance')[2]"), "治理与维护");
  assert.match(h.run("navGroups.flatMap(([, items]) => items).find(([, id]) => id === 'maintenance')[3]"), /治理与维护/);
  h.run("navigate('manage','maintenance','efficiency')");
  assert.equal(h.window.location.hash, "#manage/maintenance/efficiency");
  assert.equal(h.run("currentNavigationHref()"), "#manage/maintenance/efficiency");
  h.visit("#manage/maintenance/efficiency");
  assert.equal(h.run("maintenancePane"), "efficiency");
  h.run("onMaintenanceViewChange('overview')");
  assert.equal(h.window.location.hash, "#manage/maintenance");
});

test("data page exposes four deep-linkable subpages", () => {
  const h = harness();
  for (const [pane, title, workspace] of [
    ["storage", "存储位置与清理策略", "storageWorkspace"],
    ["backup", "备份与还原", "backupWorkspace"],
    ["records", "各处记录的入口", "data-record-grid"],
    ["migration", "V1 数据迁移", "legacyMigrationWorkspace"],
  ]) {
    h.run(`navigate('manage','data','${pane}')`);
    assert.equal(h.window.location.hash, `#manage/data/${pane}`);
    assert.equal(h.run("currentNavigationHref()"), `#manage/data/${pane}`);
    const markup = h.run("renderDataOriginal()");
    assert.match(markup, new RegExp(`href="#manage/data/${pane}" aria-current="page"`));
    assert.match(markup, new RegExp(title));
    assert.match(markup, new RegExp(workspace));
    assert.equal((markup.match(/href="#manage\/data\/(?:storage|backup|records|migration)"/g) || []).length, 4);
  }
  h.visit("#manage/data/unknown");
  assert.equal(h.window.location.hash, "#manage/data/storage");
});

test("settings jumps render the current single-page owner route", () => {
  const h = harness();
  const markup = h.run("settingsJump('语音与戳一戳','contact')");
  assert.match(markup, /data-go="manage"/);
  assert.match(markup, /data-manage="contact"/);
});

test("understanding configuration search opens the host-owned forward limits", () => {
  const h = harness();
  const location = h.run("configSearchLocation({group:'forward_intake'})");
  assert.equal(location.next, "manage");
  assert.equal(location.tab, "understanding");
  assert.equal(location.root, "#forwardIntakeWorkspace");
  const replyLocation = h.run("replySearchLocation({section:'forwards'})");
  assert.equal(replyLocation.tab, "understanding");
  assert.equal(replyLocation.root, "#contextImageWorkspace");
  for (const section of ["video_narration", "file_understanding"]) {
    const location = h.run(`replySearchLocation({section:'${section}'})`);
    assert.equal(location.tab, "understanding");
    assert.equal(location.root, "#contextImageWorkspace");
  }
});

test("quick setup reply links select the matching editable section", () => {
  const h = harness(), selected = [];
  h.window.CompanionReplyPage = {selectSection: (section, options) => selected.push({section, options})};
  h.run("navigateToReplySection('manage','understanding','','forwards')");
  assert.equal(h.window.location.hash, "#manage/understanding");
  assert.equal(selected.at(-1).section, "forwards");
  assert.equal(selected.at(-1).options.scroll, true);

  h.run("navigateToReplySection('manage','understanding','','image_narration')");
  assert.equal(h.window.location.hash, "#manage/understanding");
  assert.equal(selected.at(-1).section, "image_narration");
  assert.equal(selected.at(-1).options.scroll, true);
});

test("retired routes open their current workspace instead of account management", () => {
  const h = harness();
  const destinations = [
    ["#manage/growth", "#manage/learning/chain", "learning"],
    ["#manage/learning/skills", "#manage/learning/chain", "learning"],
    ["#manage/reply", "#manage/expression", "expression"],
    ["#manage/preferences", "#manage/contact", "contact"],
    ["#manage/semantic", "#manage/perception", "perception"],
    ["#people", "#manage/identity", "identity"],
    ["#memories", "#manage/memory", "memory"],
    ["#manage/base", "#life/diary", "diary"],
    ["#manage/state", "#life/state", "state"],
    ["#life/schedule", "#life/state", "state"],
    ["#library", "#life/directory", "directory"],
    ["#activities", "#life/directory", "directory"],
    ["#manage/capabilities", "#life/directory", "directory"],
  ];
  for (const [old, canonical, selection] of destinations) {
    h.visit(old);
    assert.equal(h.window.location.hash, canonical, old);
    assert.equal(h.window.CompanionShell.section || h.window.CompanionShell.view, selection, old);
    assert.equal(h.writes.at(-1).method, "replaceState", "aliases replace the current entry");
  }
});

test("self subpages survive copied links and a second address synchronization", () => {
  const h = harness();
  for (const pane of ["relationship", "questionnaire", "knowledge"]) {
    h.run(`navigate('manage','governance','${pane}')`);
    const hash = h.window.location.hash;
    assert.equal(hash, "#manage/governance/" + pane);
    h.visit(hash);
    assert.equal(h.run("selfPane"), pane);
  }
  h.visit("#manage/persona");assert.equal(h.run("selfPane"), "questionnaire");
  h.visit("#manage/knowledge");assert.equal(h.run("selfPane"), "knowledge");
});

test("reading and sleep entry points set the embedded tab before rendering", () => {
  const h = harness();
  for (const [detail, tab] of [["reading", "reading"], ["sleep", "sleep"], ["desk", "archive"]]) {
    h.run(`showDetail('${detail}')`);
    assert.equal(h.window.CompanionShell.view, "diary");
    assert.equal(h.run("renderLifeWorkspace()"), "life:" + tab);
    const hash = h.window.location.hash;
    h.run("navigate('manage','models')");h.visit(hash);
    assert.equal(h.run("renderLifeWorkspace()"), "life:" + tab);
  }
});

test("token usage links open the matching feature configuration", () => {
  const h = harness();
  assert.ok(h.run("manageTabs.some(([id]) => id === 'understanding')"));
  h.run("window.CompanionProduct.role = () => ({reply_api: '/reply'})");
  const understanding = h.run("renderUnderstanding()");
  assert.match(understanding, /id="contextImageWorkspace"/);
  assert.match(understanding, /图片、视频与文件理解/);
  assert.doesNotMatch(understanding, /节点显示的账号未经身份认证/);
  assert.match(understanding, /data-understanding-tab="forwards"/);
  assert.match(understanding, /id="forwardIntakeWorkspace"/);
  assert.match(understanding, /data-manage="decision"/);
  assert.match(understanding, /关系站位/);
  assert.match(understanding, /data-manage="identity"/);
  assert.equal(h.run("openTokenTaskSettings('proactive.compose')"), true);
  assert.equal(h.window.location.hash, "#manage/contact");
  assert.equal(h.run("tokenTaskSettingsFor('proactive.compose').contactView"), "purposes");
  assert.equal(h.run("tokenTaskSettingsFor('conversation.video_narration').tab"), "understanding");

  h.run("openTokenTaskSettings('memory.reflect')");
  assert.equal(h.window.location.hash, "#manage/memory");
  assert.equal(h.run("memoryWorkspaceRoute"), "settings");
  assert.equal(h.run("tokenTaskSettingsFor('memory.reflect').memorySection"), "reflection");

  h.run("openTokenTaskSettings('role.reading.consume')");
  assert.equal(h.window.location.hash, "#life/diary/reading");
  assert.equal(h.run("tokenTaskSettingsFor('role.reading.consume').workbench.field"), "reading_enabled");

  const decisionViews = [];
  h.window.CompanionDecisionPage = {setView: view => decisionViews.push(view)};
  h.run("openTokenTaskSettings('conversation.group.review')");
  assert.equal(h.window.location.hash, "#manage/decision");
  assert.equal(decisionViews.at(-1), "group");
  assert.equal(h.run("tokenTaskSettingsFor('conversation.group.review').workbench.root"), "#groupParticipationConfigWorkspace");
  assert.equal(h.run("tokenTaskSettingsFor('conversation.group.review').workbench.field"), "enable_group_interjection");

  h.run("openTokenTaskSettings('content.authoring.draft')");
  assert.equal(h.window.location.hash, "#manage/output");
  assert.equal(h.run("tokenTaskSettingsFor('content.authoring.draft').outputTab"), "creation");

  const knownKinds = ["conversation.reply", "conversation.group.review", "proactive.compose", "proactive.judge",
    "memory.reflect", "memory.reflection", "role.state.maintain", "role.state.maintenance", "calendar.plan",
    "role.calendar.plan", "role.reading.consume", "role.growth.progress", "role.journal.diary", "role.journal.dream",
    "role.journal.derive", "role.journal.select", "role.self_review", "role.expression.learn", "content.authoring.draft",
    "conversation.context_image_caption", "conversation.image_narration", "conversation.image_review", "image_review", "screen.interpretation", "screen.peek"];
  for (const kind of knownKinds) assert.ok(h.run(`tokenTaskSettings['${kind}']`), kind);
  assert.equal(h.run("tokenTaskSettingsFor('conversation.image_narration').tab"), 'understanding');
});

test("token usage opens the loaded workbench section and focuses its switch", () => {
  const h = harness();
  const selectors = [];
  const tab = {dataset: {wbSection: "reflection"}, getAttribute: () => "false", clicked: false,
    click() {this.clicked = true;}};
  const field = {dataset: {wbField: "reflection_enabled"}, scrolled: false, focused: false,
    matches: () => true, scrollIntoView() {this.scrolled = true;}, focus() {this.focused = true;}};
  h.target("#memorySettingsHost", {querySelectorAll: selector => {
    selectors.push(selector);
    return selector === "[data-wb-section]" ? [tab] : selector === "[data-wb-field]" ? [field] : [];
  }});
  h.run("openTokenTaskSettings('memory.reflect')");
  assert.deepEqual(selectors, ["[data-wb-section]", "[data-wb-group]", "[data-wb-field]"]);
  assert.equal(tab.clicked, true);
  assert.equal(field.scrolled, true);
  assert.equal(field.focused, true);
});

test("global search includes hidden content destinations and registered setting metadata", () => {
  const h = harness(), input = {value: "余额感知"}, results = {innerHTML: ""};
  h.target("#globalSearch", input);h.target("#searchResults", results);
  h.window.CompanionConfigEditors = {searchEntries: () => [{group: "proactive.contact",
    groupTitle: "主动联系偏好", field: "balance_awareness_enabled", label: "允许因余额变化联系",
    help: "余额感知开关", section: "balance", sectionTitle: "余额感知", sectionCount: 23, aliases: []}]};
  h.run("renderSearch()");
  assert.match(results.innerHTML, /允许因余额变化联系/);
  assert.match(results.innerHTML, /主动联系/);
  input.value = "便签";h.run("renderSearch()");
  assert.match(results.innerHTML, /便签/);
});

test("global search opens a setting section and focuses the matching field", () => {
  const h = harness();
  const field = {dataset: {wbField: "dialogue_default"}, matches: () => true,
    scrollIntoView() {this.scrolled = true;}, focus() {this.focused = true;}};
  h.target("#privateAccessWorkspace", {querySelectorAll: selector =>
    selector === "[data-wb-section]" ? [] : [field]});
  h.run(`openSearchSetting({entry:{group:"private_access",section:"defaults",field:"dialogue_default"},
    location:{next:"manage",tab:"identity",root:"#privateAccessWorkspace"}})`);
  assert.equal(h.window.location.hash, "#manage/identity");
  assert.equal(field.scrolled, true);
  assert.equal(field.focused, true);
});

test("global search expands relationship network settings before focusing member clues", () => {
  const h = harness();
  const disclosure = {open: false};
  const field = {dataset: {wbField: "member_match_aliases"}, matches: () => true,
    scrollIntoView() {this.scrolled = true;}, focus() {this.focused = true;}};
  h.target("#memberClueWorkspace", {closest: () => disclosure, querySelectorAll: selector =>
    selector === "[data-wb-section]" ? [] : [field]});
  const entry = {group: "knowledge", section: "members", field: "member_match_aliases"};
  h.run("openSearchSetting({entry:" + JSON.stringify(entry) + ",location:configSearchLocation(" + JSON.stringify(entry) + ")})");
  assert.equal(disclosure.open, true);
  assert.equal(field.scrolled, true);
  assert.equal(field.focused, true);
});

test("reply gate setting links select the gate view before focusing the editor", () => {
  const h = harness();
  const gateButton = {clicks: 0, click() {this.clicks += 1;}};
  h.target('#contactWorkspace [data-view="gates"]', gateButton);

  const busyGate = h.run("configSearchLocation({group:'busy_gate',section:'reply'})");
  assert.equal(busyGate.contactView, 'gates');
  h.run("openSearchSetting({entry:{group:'busy_gate',section:'reply',field:'busy_enabled'},location:configSearchLocation({group:'busy_gate',section:'reply'})})");
  assert.equal(gateButton.clicks, 1, '全局搜索应先打开开口闸门视图');

  assert.equal(h.run("configSearchLocation({group:'life',section:'rest'})").contactView, 'gates');
  assert.equal(h.run("configSearchLocation({group:'life',section:'backlog'})").contactView, 'gates');
});

test("global search opens the host voice and received-poke settings in their expression tabs", () => {
  const h = harness();
  const voiceField = {dataset: {wbField: "group_probability"}, matches: () => true,
    scrollIntoView() {this.scrolled = true;}, focus() {this.focused = true;}};
  const pokeField = {dataset: {wbField: "trigger_probability"}, matches: () => true,
    scrollIntoView() {this.scrolled = true;}, focus() {this.focused = true;}};
  h.window.CompanionHostOptionsPage = {searchEntries: () => [
    {group: "voice_reply", groupTitle: "宿主语音默认值", field: "group_probability", label: "群聊默认概率",
      section: "defaults", sectionTitle: "语音默认值", sectionCount: 1, aliases: ["TTS", "群聊"]},
    {group: "poke", groupTitle: "平台动作", field: "trigger_probability", label: "回复概率",
      section: "received", sectionTitle: "收到戳一戳", sectionCount: 1, aliases: ["戳一戳"]},
  ]};
  h.target("#voiceReplyPolicyWorkspace", {querySelectorAll: selector => selector === "[data-wb-section]" ? [] : [voiceField]});
  h.target("#pokePolicyWorkspace", {querySelectorAll: selector => selector === "[data-wb-section]" ? [] : [pokeField]});

  const voiceEntry = h.window.CompanionHostOptionsPage.searchEntries()[0];
  h.run(`openSearchSetting({entry:${JSON.stringify(voiceEntry)},location:configSearchLocation(${JSON.stringify(voiceEntry)})})`);
  assert.equal(h.window.location.hash, "#manage/expression/voice");
  assert.equal(h.run("expressionModule"), "expression-voice");
  assert.equal(voiceField.focused, true);

  const pokeEntry = h.window.CompanionHostOptionsPage.searchEntries()[1];
  h.run(`openSearchSetting({entry:${JSON.stringify(pokeEntry)},location:configSearchLocation(${JSON.stringify(pokeEntry)})})`);
  assert.equal(h.window.location.hash, "#manage/expression/platform");
  assert.equal(h.run("expressionModule"), "expression-platform");
  assert.equal(h.run("replyPane"), "");
  assert.equal(pokeField.focused, true);
});

test("profile and world details open the self editor and knowledge subpage", () => {
  const h = harness();
  h.run("showDetail('profile')");assert.equal(h.window.location.hash, "#manage/governance");
  h.run("showDetail('world')");assert.equal(h.window.location.hash, "#manage/governance/knowledge");
  h.run("showDetail('growth')");assert.equal(h.window.location.hash, "#manage/learning/chain");
  h.run("navigate('manage','expression','voice')");
  assert.equal(h.window.location.hash, "#manage/expression/voice");
  h.visit("#manage/reply/voice");assert.equal(h.run("replyPane"), "voice");
});

test("section anchors preserve the current page and focus their destination", () => {
  const h = harness(), target = h.anchor("expression-voice");
  h.run("navigate('manage','expression')");
  const renders = h.renders.length;
  h.visit("#expression-voice");
  assert.equal(h.window.location.hash, "#manage/expression");
  assert.equal(h.renders.length, renders);
  assert.equal(target.focused, true);assert.equal(target.scrolled, true);
});

test("page anchors expand collapsed disclosure sections before focusing them", () => {
  const h = harness();
  const details = {tagName: "DETAILS", open: false, parentElement: null};
  const target = h.anchor("nested-setting");
  target.parentElement = details;

  assert.equal(h.run("scrollToPageAnchor('nested-setting')"), true);
  assert.equal(details.open, true);
  assert.equal(target.focused, true);
});

test("user navigation records history and repeated synchronization preserves the editor", () => {
  const h = harness();
  h.run("navigate('manage','models')");
  const renders = h.renders.length;
  h.run("syncFromHash();syncFromHash()");
  assert.equal(h.renders.length, renders);
  assert.equal(h.writes[0].method, "pushState");
  h.visit("#life");assert.equal(h.window.CompanionShell.section, null);
});

test("reopening the active route does not reset the page scroll", () => {
  const h = harness();
  h.run("navigate('manage','models')");
  assert.equal(h.scrolls.length, 1, "entering a different route returns to its start");
  h.run("navigate('manage','models')");
  assert.equal(h.scrolls.length, 1, "the active route keeps its current scroll position");
});

test("wardrobe furniture exposes its room and reference-material actions", () => {
  const markup = harness().run("renderFurniturePanel('wardrobe')");
  assert.match(markup, /data-detail="arrange"/);
  assert.match(markup, /data-manage="output" data-output-target="materials"/);
});

test("home calendar action opens the calendar furniture with planning expanded", () => {
  const h = harness();
  h.window.CompanionProduct.scheduleCard = () => "schedule";
  assert.match(h.run("homeScheduleBand()"), /data-shell-furniture="calendar"/);
  assert.match(h.run("renderFurniturePanel('calendar')"), /data-state-feature="planning"/);
});

test("furniture directory filters, search and attention counts use the same records", () => {
  const h = harness();
  h.window.CompanionProduct.provider = id => ({label:id === "image" ? "图片伴侣" : "扩展",
    integration_state:id === "image" ? "connected" : "missing"});
  const ids = () => Array.from(h.run("filteredFurniture().map(item=>item.id)"));
  h.run("furnitureFilter='extensions'");
  assert.deepEqual(ids(), ["content", "image", "together", "game", "screen", "reality", "live"]);
  h.run("furnitureFilter='base'");
  assert.equal(ids().length, 7);
  h.run("furnitureFilter='all';furnitureQuery='图片伴侣'");
  assert.deepEqual(ids(), ["image"]);
  h.run("furnitureQuery='';furnitureFilter='attention';state.modules.image='removed'");
  assert.equal(ids().length, 7, "locally removed furniture needs attention even when its provider is connected");
  const html = h.run("renderDirectory()");
  assert.match(html, /data-furniture-filter="attention"[^>]*>待检查<span>7<\/span>/);
  assert.match(html, /显示 7 \/ 14 件/);
  h.run("furnitureQuery='不存在的家具'");
  assert.match(h.run("renderDirectory()"), /没有符合条件的家具/);
});
