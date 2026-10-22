"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "pages", "陪伴小屋", "learning-review-page.js"), "utf8");
const flush = () => new Promise(resolve => setTimeout(resolve, 0));

test("表达规则因明确负反馈退回复审时显示原因和计数", async () => {
  const feedbackRule = {signal_id:"signal-1",run_id:"run-1",dimension:"diction",source_kind:"conversation_input",
    observation:"晚间问候时使用轻松短句",proposal:"用轻松短句问候",state:"pending",created_at:"2026-10-08T10:00:00+00:00",
    actions:["adopt","reject"],positive_feedback:1,negative_feedback:2,
    review_reason:"收到两次以上明确负向反馈，已退回复审",evidence:[],view_token:"token",confidence:0.82};
  const bridge = {apiGet:async route => ({status:"ok",data:{items:route.endsWith("/style")?[feedbackRule]:[]}}),
    apiPost:async () => ({status:"ok",data:{}})};
  const root = {isConnected:true,innerHTML:"",listeners:new Map(),
    addEventListener(name,callback){this.listeners.set(name,callback);},
    removeEventListener(name){this.listeners.delete(name);}};
  const window = {CompanionProduct:{bridgeNow:()=>bridge,unwrap:value=>value},lucide:{createIcons(){}}};
  const context = vm.createContext({window,setTimeout,clearTimeout,Date,Math,Number,Object,Array,String});
  vm.runInContext(source,context);
  context.window.CompanionLearningReviewPage.mount(root,{sources:[{
    key:"role-a",label:"星缘 · 私聊",
    replyApi:"/astrbot_plugin_private_companion/targets/profile-a/roles/role-a/reply",
    growthApi:"/astrbot_plugin_private_companion/targets/profile-a/roles/role-a/growth",
  }]});
  for(let index=0;index<40&&!root.innerHTML.includes("退回复审");index++)await flush();
  assert.ok(root.innerHTML.includes("明确反馈 · 认可 1 / 不喜欢 2"));
  assert.ok(root.innerHTML.includes("收到两次以上明确负向反馈，已退回复审"));
  context.window.CompanionLearningReviewPage.unmount();
});
