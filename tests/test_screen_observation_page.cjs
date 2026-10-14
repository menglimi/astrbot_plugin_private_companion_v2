"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../pages/陪伴小屋/screen-observation.js"), "utf8");
const settle = async () => { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); };
function harness(request) {
  const calls = [], node = {innerHTML:"", isConnected:true, listeners:{},
    addEventListener(n, fn) { this.listeners[n] = fn; }, removeEventListener(n) { delete this.listeners[n]; },
    fire(action) { this.listeners.click({target:{closest:()=>({dataset:{screenReview:action}})}}); }};
  let scope = "a";
  const window = {CompanionProduct:{scopeKey:()=>scope, role:()=>({screen_access_api:"/screen-access"}),
    relative:value=>value.slice(1), target:()=>({scope_kind:"private"}),
    async request(method, endpoint, query) { calls.push({method, endpoint, query}); return request(endpoint, query); }}};
  vm.runInNewContext(source, {window, String, Date, Number});
  return {node, calls, page:window.CompanionScreenObservation, scope:value=>{scope=value;}};
}
const saved = {observation:{capture_id:"capture-a", media_kind:"image", captured_at:"2026-10-14T12:18:24Z",
  peek_task_id:"peek-a", mode:"automatic", analysis:{state:"succeeded", text:"观察 <img onerror=x>", provider:"deepseek4.1"}},
  latest_attempt:{task_id:"peek-a"}};
test("保存结果先显示文本；查看原件是有版本绑定的只读请求", async () => {
  const h = harness(async (endpoint) => endpoint.endsWith("last-original")
    ? {capture_id:"capture-a", data_url:"data:image/png;base64,AA=="} : saved);
  h.page.mount(h.node); await settle();
  assert.match(h.node.innerHTML, /识屏完成/);
  assert.match(h.node.innerHTML, /观察 &lt;img onerror=x&gt;/);
  assert.doesNotMatch(h.node.innerHTML, /<img /);
  h.node.fire("original"); await settle();
  assert.deepEqual(h.calls.map(c=>c.method), ["GET", "GET"]);
  assert.equal(h.calls[1].query.capture_id, "capture-a");
  assert.match(h.node.innerHTML, /src="data:image\/png;base64,AA=="/);
  h.page.unmount(); h.page.mount(h.node); await settle();
  assert.doesNotMatch(h.node.innerHTML, /src="data:/);
});
test("未知分析明确无确认结果，拒绝另一截图的预览回执", async () => {
  const h = harness(async endpoint => endpoint.endsWith("last-original")
    ? {capture_id:"different", data_url:"data:image/png;base64,AA=="}
    : {...saved, observation:{...saved.observation, analysis:{state:"uncertain", text:null}}});
  h.page.mount(h.node); await settle();
  assert.match(h.node.innerHTML, /识屏结果未确认/);
  assert.match(h.node.innerHTML, /尚无确认的识屏结果/);
  h.node.fire("original"); await settle();
  assert.doesNotMatch(h.node.innerHTML, /<img /);
});
test("切换私聊后，旧范围的异步结果不会出现", async () => {
  let finish;
  const h = harness(()=>new Promise(resolve=>{finish=resolve;}));
  h.page.mount(h.node); h.scope("b"); h.page.unmount();
  finish(saved); await settle();
  assert.doesNotMatch(h.node.innerHTML, /观察 &lt;img/);
});
