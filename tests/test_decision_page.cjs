const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const pageRoot = path.resolve(__dirname, "../pages/陪伴小屋");
const source = fs.readFileSync(path.join(pageRoot, "decision-page.js"), "utf8");

function harness() {
  const root = {innerHTML:"",dataset:{},querySelector(){return null;},querySelectorAll(){return [];},
    addEventListener(){},removeEventListener(){}};
  const window = {lucide:{createIcons(){}}};
  vm.runInNewContext(source, {window});
  return {page:window.CompanionDecisionPage,root};
}

test("decision page owns group participation and does not duplicate other domains", () => {
  const view = harness();
  view.page.mount(view.root, {groupSettingsMarkup:'<section id="decisionReplyWorkspace"></section><section id="groupParticipationConfigWorkspace"></section>'});

  assert.doesNotMatch(view.root.innerHTML, /perceptionOverviewWorkspace/);
  assert.match(view.root.innerHTML, /groupParticipationConfigWorkspace/);
  assert.match(view.root.innerHTML, /decisionReplyWorkspace/);
  for (const tab of ["overview", "response", "tempo", "safety", "group"])
    assert.match(view.root.innerHTML, new RegExp(`data-decision-tab="${tab}"`));
  assert.match(view.root.innerHTML, /<div class="decision-tab-list" role="tablist">/);
  assert.match(view.root.innerHTML, /<\/div>\s*<span class="decision-current"/);
  assert.doesNotMatch(view.root.innerHTML,
    /roleStateWorkspace|lifeConfigWorkspace|memorySettingsHost|personConfigWorkspace|privateAccessWorkspace/);
  view.page.unmount();
});

test("narrow decision navigation scrolls tabs without covering the status", () => {
  const css = fs.readFileSync(path.join(pageRoot, "decision-page.css"), "utf8");
  assert.match(css, /\.decision-tab-list\{[^}]*overflow-x:auto/s);
  assert.match(css, /\.decision-current\{position:static;justify-self:end/);
  assert.doesNotMatch(css, /\.decision-current\{position:sticky/);
});

test("the perception overview stays on perception while decision settings remain target-aware", () => {
  const app = fs.readFileSync(path.join(pageRoot, "app.js"), "utf8");
  assert.match(app, /CompanionDecisionPage\?\.mount\(decisionHost,\{groupSettingsMarkup:renderDecisionOriginal\(\)\}\)/);
  assert.match(app, /function renderDecisionOriginal\(\)\{\s*if\(typeof product\.role\(\)\?\.reply_api!=='string'\)return pageNeedsTarget\('群聊参与'\)/);
  assert.match(app, /function renderDecisionOriginal\(\)[\s\S]*?configEditors\('groupParticipationConfigWorkspace',\['group_participation'\],'群聊参与'\)/);
  assert.match(app, /if\(replyHost\)[\s\S]*?view:'expression',section:replyPane[\s\S]*?else if\(decisionReplyHost\)[\s\S]*?view:'decision',[\s\S]*?updateReplyStatus\?\.\(status\)[\s\S]*?else if\(contextImageHost\)[\s\S]*?view:'perception'/);
  assert.match(app, /id="contextImageWorkspace"/);
  assert.match(app, /sectionIds:\['atmosphere','joke_guard','interjection','repeat','history'\]/);
  assert.match(app, /sectionIds:\['denoise'\],title:'群聊表达去噪'/);
  assert.match(app, /decision:'群聊中判断何时回应、如何参与并守住边界。'/);
  assert.match(app, /function renderPerceptionOriginal\(\)[\s\S]*?id="perceptionOverviewWorkspace"/);
  assert.match(app, /if\(\$\('#perceptionOverviewWorkspace'\)\)guarded\('感知上下文',[\s\S]*?CompanionPerceptionOverviewPage\?\.mount/);
  assert.doesNotMatch(app, /决策页复用感知页的只读上下文流/);
  assert.match(app, /decisionView:entry\.section==='joke_guard'\?'safety':'group'/);
  assert.match(app, /const decisionView=\['wakeup_direct','wakeup_interest','wakeup_members'\]/);
  const searchOpen = app.slice(app.indexOf("function openSearchSetting("), app.indexOf("function openTokenTaskSettings("));
  const tokenOpen = app.slice(app.indexOf("function openTokenTaskSettings("), app.indexOf("function openSearch("));
  assert.match(searchOpen, /if\(location\.decisionView\)window\.CompanionDecisionPage\?\.setView/);
  assert.doesNotMatch(searchOpen, /target\.decisionView/);
  assert.match(tokenOpen, /if\(target\.decisionView\)window\.CompanionDecisionPage\?\.setView/);
});

test("settings are hosted by their matching domain pages", () => {
  const app = fs.readFileSync(path.join(pageRoot, "app.js"), "utf8");
  const memory = app.slice(app.indexOf("function renderMemoryPage(){"), app.indexOf("/* 学习与反思。", app.indexOf("function renderMemoryPage(){")));
  const diary = app.slice(app.indexOf("if(name==='diary')"), app.indexOf("return renderHomePanel();", app.indexOf("if(name==='diary')")));
  const identity = app.slice(app.indexOf("function renderIdentityPageOriginal(){"), app.indexOf("/* 主动与联系。", app.indexOf("function renderIdentityPageOriginal(){")));

  assert.match(memory, /data-memory-route="settings"/);
  assert.match(memory, /memorySettingsHost/);
  assert.match(diary, /lifeConfigWorkspace/);
  assert.match(identity, /personConfigWorkspace/);
  assert.match(identity, /privateAccessWorkspace/);
  assert.match(app, /if\(name==='state'\)[\s\S]*?renderRoleState\(\)/);
});

test("knowledge import and member attribution settings use separate input and self views", () => {
  const app = fs.readFileSync(path.join(pageRoot, "app.js"), "utf8");
  assert.match(app, /configEditors\('memberClueWorkspace',\['knowledge'\]/);
  assert.match(app, /knowledgeConfigWorkspace[\s\S]*?sectionIds:\['import','inject'\]/);
  assert.match(app, /memberClueWorkspace[\s\S]*?sectionIds:\['members'\]/);
});

test("memory view tabs support keyboard navigation", () => {
  const app = fs.readFileSync(path.join(pageRoot, "app.js"), "utf8");
  assert.match(app, /\[role="tab"\]\[data-memory-route\]/);
  assert.match(app, /data-memory-route="records"/);
  assert.match(app, /data-memory-route="settings"/);
  assert.match(app, /ArrowRight.*tabs\.length-1/s);
});

test("private access modules cover each field once", () => {
  const configSource = fs.readFileSync(path.join(pageRoot, "config-editor.js"), "utf8");
  const window = {};
  vm.runInNewContext(configSource, {window});
  const spec = window.CompanionConfigEditors.spec.private_access;
  const fields = Array.from(spec.sections).flatMap(section => Array.from(section.fields));

  assert.deepEqual(fields, Array.from(spec.order));
  assert.deepEqual(Array.from(spec.sections, section => section.title),
    ["新用户默认权限", "无权限回复", "陌生号处理"]);
});
