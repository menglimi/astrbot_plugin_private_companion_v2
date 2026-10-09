"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../pages/陪伴小屋/calendar-editor.js"), "utf8");
const scope = {installation_id:"test-install", operator_id:"dashboard:test", path:"state"};
const schedule = {anchor:"2026-10-03T00:00:00Z", timezone_name:"Asia/Shanghai", frequency:"daily",
  interval:1, count:null, fold:0, gap_policy:"reject"};
const data = {kind:"role_plan", title:"晨间散步", detail:"", schedule, duration_minutes:30, presence:""};

test("pristine calendar drafts can be discarded when switching away", () => {
  const window = {};
  vm.runInNewContext(source, {window, structuredClone, Intl, Date, JSON,
    sessionStorage:{getItem:()=>null, setItem(){}, removeItem(){}}});
  const editor = window.CompanionCalendarEditor.create({changed() {}, failed() {}, refresh:async()=>null, api:async()=>({})});
  editor.setScope(scope);
  editor.setStatus({create_token:"create", calendar:{items:[]}});
  editor.open("create");
  assert.equal(editor.interacting, true);
  assert.equal(editor.dirty, false);
  assert.equal(editor.discardIfPristine(), true);
  assert.equal(editor.interacting, false);

  editor.open("create");
  editor.input({target:{dataset:{calendarField:"title"}, value:"新的计划", matches:()=>true}});
  assert.equal(editor.dirty, true);
  assert.equal(editor.discardIfPristine(), false);
  editor.destroy();
});

test("calendar empty state is grouped and only shows first-page navigation after paging forward", () => {
  const window = {};
  vm.runInNewContext(source, {window, structuredClone, Intl, Date, JSON,
    sessionStorage:{getItem:()=>null, setItem(){}, removeItem(){}}});
  const editor = window.CompanionCalendarEditor.create({changed() {}, failed() {}, refresh:async()=>null, api:async()=>({})});
  editor.setScope(scope);
  editor.setStatus({create_token:"create", calendar:{items:[]}});
  const firstPage = editor.markup();
  assert.match(firstPage, /class="state-calendar-empty"/);
  assert.match(firstPage, /创建一项安排，让角色在连续日程中接续它/);
  assert.doesNotMatch(firstPage, /返回首批/);
  assert.doesNotMatch(firstPage, /state-calendar-pagination/);
  editor.setStatus({create_token:"create", request_cursor:"cursor-a", calendar:{items:[], next_cursor:"cursor-b"}});
  const laterPage = editor.markup();
  assert.match(laterPage, /返回首批/);
  assert.match(laterPage, /下一批/);
  editor.destroy();
});

for (const [action, label, extra] of [
  ["create", "创建计划", {data}],
  ["revise", "修改日程", {data, sources:[]}],
  ["cancel", "取消日程", {}],
  ["remind", "安排提醒", {sequence:0}],
  ["exception", "调整本次安排", {data:{sequence:0, start:null}}],
]) {
  test("pending calendar " + action + " uses readable text and retries the exact request", async () => {
    const command = {action:"calendar." + action, id:"internal-plan-opaque", expected_revision:action === "create" ? 0 : 1,
      operation_key:"internal-operation-opaque", view_token:"internal-view-token", ...extra};
    const storageKey = "companion-state-calendar.v1:" + JSON.stringify([scope.installation_id, scope.operator_id, scope.path]);
    const cached = new Map([[storageKey, JSON.stringify(command)]]), window = {}, calls = [];let refreshes=0;
    vm.runInNewContext(source, {window, structuredClone, Intl, Date, JSON,
      sessionStorage:{getItem:key=>cached.get(key)||null, setItem:(key,value)=>cached.set(key,value), removeItem:key=>cached.delete(key)}});
    const editor = window.CompanionCalendarEditor.create({changed() {}, failed() {}, refresh:async()=>{refreshes+=1;return {calendar:{items:[]}};},
      api:async(method, route, body)=>{calls.push({method, route, body});return {operation_id:"receipt"};}});
    editor.setScope(scope);
    editor.setStatus({create_token:"create", calendar:{items:[{id:command.id, title:"晨间散步"}]}});
    const html = editor.markup();
    assert.match(html, new RegExp("待核对：" + label + " · 晨间散步"));
    assert.doesNotMatch(html, /internal-plan-opaque|internal-operation-opaque|internal-view-token|calendar\.(create|revise|cancel|remind|exception)/);
    editor.setStatus({create_token:"create", calendar:{items:[]}});
    if (!["create", "revise"].includes(action)) assert.match(editor.markup(), /当前日程/);
    editor.click({target:{closest:()=>({dataset:{calendarEdit:"recover"}})}});
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(calls.length, 1);
    assert.equal(calls[0].route, "state/command");
    assert.deepEqual(JSON.parse(JSON.stringify(calls[0].body)), command);
    assert.equal(cached.has(storageKey), false);
    assert.equal(refreshes, 1, "日程保存后应重新读取日程");
    assert.match(editor.markup(), /日程已保存/);
  });
}
