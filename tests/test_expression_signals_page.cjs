"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "pages", "陪伴小屋", "expression-signals-page.js"), "utf8");
const HOST = "astrbot_plugin_private_companion";
const flush = () => new Promise(resolve => setTimeout(resolve, 0));

test("规则库导出与 V1 分享包预览/导入使用已选择角色路由", async () => {
  const gets = [], posts = [], listeners = new Map();
  const bridge = {
    apiGet: async (route, query) => {
      gets.push({route, query});
      const items = query?.state === "adopted" ? [{signal_id:"signal-1",run_id:"run-1",dimension:"diction",
        source_kind:"conversation_input",observation:"晚间问候时使用轻松短句",proposal:"用轻松短句问候",
        state:"adopted",created_at:"2026-10-08T10:00:00+00:00",actions:["retire"],injections:3,
        positive_feedback:1,negative_feedback:2,evidence:[],view_token:"token"}] : [];
      return {status:"ok", data:{items, capacity:{active:1,limit:60}}};
    },
    apiPost: async (route, body) => {
      posts.push({route, body});
      if (route.endsWith("/style/export")) return {status:"ok", data:{package:{schema:"private-companion-expression-pack",version:1,rule_groups:[]},rule_count:0,excluded_count:0}};
      if (route.endsWith("/style/import/preview")) return {status:"ok", data:{title:"测试分享",group_count:1,rule_count:1,
        importable_rule_count:1,duplicate_rule_count:0,capacity_blocked_count:0,rejected_count:0,
        preview_token:"a".repeat(64),candidates:[{dimension:"diction",observation:"短称呼",proposal:"使用简短称呼"}]}};
      return {status:"ok", data:{imported_count:1,state:"pending_review",replayed:false}};
    },
  };
  const root = {isConnected:true,innerHTML:"",addEventListener:(name, callback)=>listeners.set(name, callback),
    removeEventListener:name=>listeners.delete(name),querySelector:()=>null};
  const window = {CompanionProduct:{bridgeNow:()=>bridge,unwrap:value=>value},lucide:{createIcons(){}}};
  const context = vm.createContext({window,setTimeout,clearTimeout,TextEncoder,JSON,Date,Math,Number,Object,Array,String,URLSearchParams});
  vm.runInContext(source, context);
  await context.window.CompanionExpressionSignalsPage.mount(root, {
    replyApi:`/${HOST}/targets/profile-a/roles/role-a/reply`,
    target:{scope_kind:"group",group_id:"group-a"},scopeKey:"scope-a",
  });
  for(let index=0;index<20&&!gets.length;index++)await flush();
  for(let index=0;index<30&&context.window.CompanionExpressionSignalsPage.state.busy;index++)await flush();
  assert.ok(gets.length);
  assert.ok(gets.every(call=>call.route===`targets/profile-a/roles/role-a/reply/style`));
  assert.ok(root.innerHTML.includes("明确反馈 · 认可 1 / 不喜欢 2"));

  const click = async selector => listeners.get("click")?.({target:{closest:value=>value===selector?{}:null}});
  const change = target => listeners.get("change")?.({target});
  const input = target => listeners.get("input")?.({target});
  await click("[data-share-toggle]");
  await click("[data-share-export]");
  for(let index=0;index<30&&!root.innerHTML.includes("分享包已生成");index++)await flush();
  assert.ok(posts.some(call=>call.route===`targets/profile-a/roles/role-a/reply/style/export`));
  const json = JSON.stringify({schema:"private-companion-expression-pack",version:1,rule_groups:[{rules:[{kind:"style",label:"短称呼",pattern:"使用简短称呼"}]}]});
  input({value:json,closest:selector=>selector==="[data-share-import-json]"?{value:json}:null});
  await click("[data-share-preview]");
  for(let index=0;index<30&&!root.innerHTML.includes("预览已更新");index++)await flush();
  const preview = posts.find(call=>call.route.endsWith("/style/import/preview"));
  assert.equal(preview.body.package_json,json);
  await click("[data-share-apply]");
  for(let index=0;index<30&&!root.innerHTML.includes("已加入审阅中心");index++)await flush();
  assert.equal(posts.find(call=>call.route.endsWith("/style/import/apply")).body.preview_token,"a".repeat(64));
  assert.equal(root.innerHTML.includes("已加入审阅中心"),true);
  context.window.CompanionExpressionSignalsPage.unmount();
  assert.equal(listeners.size,0);
});
