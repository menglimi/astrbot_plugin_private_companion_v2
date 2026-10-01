"use strict";

const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../pages/陪伴小屋/perception-overview.js"), "utf8");
const fixedNow = new Date("2026-10-01T10:00:00Z");
class FixedDate extends Date {
  constructor(...args) { super(...(args.length ? args : [fixedNow])); }
  static now() { return fixedNow.getTime(); }
}

function harness({runtimeWeatherState="available",mihomeEnabled=true,otherInjections=[{label:"参考资料",detail:"本轮加入 1 项"}],recallEnabled=true,recallEntries=[{local_time:"17:42",author:"user-1",text:"周末去公园走走"}]}={}) {
  let listener = null, intervalCallback = null, cleared = false, requested = [], fetchRequests = [];
  const parentNodes = {
    '[data-perception-tab="config-injection"]': {hidden:false},
    "#perception-detail-mihome": {hidden:true},
    "#mihomeStatusWorkspace": {innerHTML:""},
    "#perceptionRecallWorkspace": {innerHTML:""},
    "#perceptionInjectionWorkspace": {innerHTML:""},
  };
  const root = {isConnected:true, innerHTML:"", handlers:{},
    addEventListener(type, handler) { this.handlers[type] = handler; },
    removeEventListener(type) { delete this.handlers[type]; },
    querySelector(selector) {
      const match = /\[data-context-clock-(time|date|zone|weekday)\]/.exec(selector);
      if (!match) return null;
      const key = match[1];
      return this.clockNodes?.[key] || (this.clockNodes ||= {}, this.clockNodes[key] = {textContent:""});
    },
    parentElement:{querySelector(selector) { return parentNodes[selector] || null; }}};
  let snapshot = {ready:true,
    environment:{weatherReady:true, alertsReady:true, locationName:"用户配置区域", weatherEnabled:true, timezone:"Asia/Shanghai"},
    model:{calendarEnabled:true, timezone:"Asia/Shanghai", modalitiesEnabled:true},
    contact:{dateCheckinEnabled:true, lookaheadDays:3, timezone:"Asia/Shanghai",
      dates:JSON.stringify([{calendar:"gregorian",month:10,day:3,label:"相识纪念日"}])},
    news:{ready:true,label:"AstrBot 网页搜索",sourceKind:"search",explorationEnabled:true,
      explorationInterests:"科技,生活",explorationIntervalHours:8,explorationResultCount:6,
      externalSelfLinkEnabled:true,lastCheckedAt:"2026-10-01 17:50"}};
  const status = {tasks:[
    {kind:"conversation.reply",fields:{provider:{value:"provider-main"},fallback:{value:"provider-backup"}}},
    {kind:"image.generate",fields:{provider:{value:"provider-image"}}},
    {kind:"vision.review",fields:{provider:{value:"provider-vision"}}}],
    providers:[{id:"provider-main",model:"model-live"},{id:"provider-backup",model:"model-safe"},
      {id:"provider-image",model:"image-live"},{id:"provider-vision",model:"vision-live"}]};
  const runtime = {observed_at:"2026-10-01T10:00:00Z",
    weather:{state:runtimeWeatherState,location:"用户配置区域",provider:"open-meteo",condition:"晴",temperature_c:22,observed_at:"2026-10-01T09:58:00Z",
      alerts:[{title:"大风蓝色预警",severity:"蓝色",ends_at:"2026-10-01T20:00:00Z"}]},
    screen:{state:"available",purpose:"reply",interpretation:"用户正在查看代码编辑器。",surface:"编辑器",captured_at:"2026-10-01T09:55:00Z",created_at:"2026-10-01T09:56:00Z"},
    reality:{state:"available",captured_at:"2026-10-01T09:50:00Z",snapshot:{
      location:{available:true,label:"上海市·徐汇区",captured_at:1790848200},
      health:{available:true,measurements:[{label:"心率",value:72,unit:"次/分"}],captured_at:1790848200}}},
    calendar:{status:"available",holiday:{status:"available",kind:"workday",label:"工作日",source:"weekday_fallback"},
      lunar_status:"available",lunar_date:"农历八月二十",automatic_solar_terms:{status:"available",today:[],upcoming:[]},
      almanac:{status:"available",yi:"读书",ji:"熬夜"}},
    other_injections:otherInjections,
    camera:{state:"available",status:"success",answer_available:true,purpose:"看看我现在在做什么",
      captured_at:"2026-10-01T09:57:00Z",observation:{summary:"桌面上有打开的笔记本电脑。",confidence:0.9}}};
  const product = {scopeKey:() => "role-1", role:() => ({model_api:"/astrbot_plugin_private_companion_v2/model",
      perception_native_api:"/astrbot_plugin_private_companion_v2/perception-native"}),
    provider:id => id === "screen" ? {integration_state:"connected",runtime_ready:true,reason:"屏幕扩展运行正常"}
      : {integration_state:"missing",reason:"未安装"},
    statusLabel:value => value, data:{state:{state:{values:{},settings:{}}}},
    stateValues:() => null, relative:value => value, unwrap:value => value,
    request:async(_method,route) => {
      requested.push(route);
      if (route.endsWith("/runtime")) return runtime;
      if (route.endsWith("/voice")) return {languages:[{k:"zh-CN",n:"中文",bind:"tts-main"}],
        providers:[{id:"tts-main",label:"TTS 主路由"}],catalog_state:"ready",voice_enabled:true};
      if (route.endsWith("/image")) return {actions:[{action:"image.generate",enabled:true,
        owner:"Image 扩展",provider_id:"image-live",state:"ready"}]};
      return status;
    },
    bridgeNow:() => ({apiGet:async route => route === "semantic"
      ? {settings:{analysis_provider:"vision-analysis"}}
      : {enabled:recallEnabled,entries:recallEntries}})};
  const native = {subscribe(callback) { listener=callback; callback(snapshot); return () => {listener=null;}; },
    refresh() {}};
  const window = {CompanionProduct:product,CompanionNativePerceptionPage:native,
    fetch:async url => {
      fetchRequests.push(url);
      const value = url.endsWith("/status") ? {ok:true,tools:{enable_readonly_tool:mihomeEnabled}}
        : {ok:true,snapshot_at:"2026-10-01 17:55",devices:[
          {configured:true,name:"客厅灯",aliases:["living_light"],online:true},
          {configured:true,name:"书房插座",aliases:["study_plug"],online:false}]};
      return {ok:true,json:async()=>value};
    }};
  const intervals = new Map(); let intervalId=0;
  vm.runInNewContext(source, {window, Date:FixedDate, Intl, JSON, Number, String, Array, Object, RegExp,
    AbortController, setInterval(callback) { intervalCallback=callback; intervals.set(++intervalId,callback); return intervalId; },
    clearInterval(id) { intervals.delete(id); cleared=true; }, setTimeout, clearTimeout});
  return {page:window.CompanionPerceptionOverviewPage, root, snapshot, intervals,parentNodes,
    emit(next) { snapshot=next; listener?.(next); }, get requested(){return requested;}, get fetchRequests(){return fetchRequests;},
    get intervalCallback(){return intervalCallback;}, get cleared(){return cleared;}};
}

test("overview shows the requested context, live routes, authorized devices and only in-window dates", async () => {
  const page = harness();
  page.page.mount(page.root);
  await new Promise(resolve => setImmediate(resolve));

  assert.deepEqual(page.requested.sort(), [
    "/astrbot_plugin_private_companion_v2/model",
    "/astrbot_plugin_private_companion_v2/model/image",
    "/astrbot_plugin_private_companion_v2/model/voice",
    "/astrbot_plugin_private_companion_v2/perception-native/runtime",
  ]);
  assert.match(page.root.innerHTML, /用户配置区域/);
  assert.match(page.root.innerHTML, /晴 · 22°C/);
  assert.match(page.root.innerHTML, /大风蓝色预警/);
  assert.match(page.root.innerHTML, /所在地/);
  assert.match(page.root.innerHTML, /天气实况/);
  assert.match(page.root.innerHTML, /model-live/);
  assert.match(page.root.innerHTML, /Provider provider-main · 备用 model-safe/);
  assert.match(page.root.innerHTML, /TTS 主路由/);
  assert.match(page.root.innerHTML, /image-live/);
  assert.match(page.root.innerHTML, /vision-live/);
  assert.match(page.root.innerHTML, /外部资讯与检索/);
  assert.match(page.root.innerHTML, /AstrBot 网页搜索/);
  assert.match(page.root.innerHTML, /用户正在查看代码编辑器/);
  assert.match(page.root.innerHTML, /上海市·徐汇区/);
  assert.match(page.root.innerHTML, /摄像头状态/);
  assert.match(page.root.innerHTML, /农历八月二十/);
  assert.match(page.root.innerHTML, /宜 读书 · 忌 熬夜/);
  assert.match(page.root.innerHTML, /桌面上有打开的笔记本电脑/);
  assert.match(page.root.innerHTML, /看看我现在在做什么/);
  assert.match(page.root.innerHTML, /相识纪念日 · 2 天后/);
  assert.match(page.root.innerHTML, /data-perception-focus="config-environment:perception-detail-important-days"/);
  assert.match(page.root.innerHTML, /CONTEXT BOARD/);
  assert.match(page.root.innerHTML, /data-context-clock-time/);
  assert.match(page.root.innerHTML, /data-context-clock-date/);
  assert.match(page.root.innerHTML, /data-context-clock-weekday/);
  for (const item of ["所在地", "天气实况", "天气预警", "对话模型", "TTS 模型", "生图模型",
    "视觉模型", "外部资讯与检索", "用户定位", "识屏信息", "摄像头状态", "撤回记录",
    "米家设备", "其他注入"]) {
    assert.match(page.root.innerHTML, new RegExp(item));
  }
  assert.match(page.root.innerHTML, /撤回记录/);
  assert.match(page.root.innerHTML, /米家设备/);
  assert.match(page.parentNodes["#perceptionRecallWorkspace"].innerHTML, /周末去公园走走/);
  assert.match(page.parentNodes["#mihomeStatusWorkspace"].innerHTML, /客厅灯/);
  assert.match(page.parentNodes["#mihomeStatusWorkspace"].innerHTML, /离线/);
  assert.match(page.parentNodes["#perceptionInjectionWorkspace"].innerHTML, /参考资料/);
  assert.deepEqual(page.fetchRequests.sort(), [
    "/api/plugin/astrbot_plugin_mihome/devices",
    "/api/plugin/astrbot_plugin_mihome/status",
  ]);
  assert.match(page.root.clockNodes.time.textContent, /18:00:00/);
  assert.match(page.root.clockNodes.weekday.textContent, /星期四/);

  const outsideWindow = {...page.snapshot, contact:{...page.snapshot.contact, lookaheadDays:1}};
  assert.equal(page.page.upcomingDates(outsideWindow, new FixedDate()).length, 0);
  assert.equal(page.page.upcomingDates({...page.snapshot, contact:{...page.snapshot.contact, dateCheckinEnabled:false}}, new FixedDate()).length, 1);
  assert.equal(page.page.upcomingDates({...page.snapshot, model:{...page.snapshot.model, calendarEnabled:false}}, new FixedDate()).length, 1);

  page.page.unmount();
  assert.equal(page.intervals.size, 0);
  assert.equal(page.cleared, true);
});

test("readiness count reflects available signals, and optional rows stay absent", async () => {
  const page = harness({mihomeEnabled:false,otherInjections:[],recallEnabled:false,recallEntries:[]});
  page.page.mount(page.root);
  await new Promise(resolve => setImmediate(resolve));

  assert.match(page.root.innerHTML, /CONTEXT BOARD · 13 项有实况/);
  assert.doesNotMatch(page.root.innerHTML, /其他注入/);
  assert.doesNotMatch(page.root.innerHTML, /米家设备/);
  assert.equal(page.parentNodes["#perception-detail-mihome"].hidden, true);
  assert.deepEqual(page.fetchRequests, ["/api/plugin/astrbot_plugin_mihome/status"]);
  page.page.unmount();
});

test("the weather off state names its conversation and planning behavior", async () => {
  const page = harness({runtimeWeatherState:"disabled"});
  page.page.mount(page.root);
  page.emit({...page.snapshot, environment:{...page.snapshot.environment, weatherEnabled:false}});
  await new Promise(resolve => setImmediate(resolve));

  assert.match(page.root.innerHTML, /天气感知未启用/);
  assert.match(page.root.innerHTML, /私聊询问天气时按需读取/);
  assert.match(page.root.innerHTML, /日常计划也可参考/);
  page.page.unmount();
});

test("overview does not claim unavailable camera results or retain data after a failed refresh", async () => {
  const page = harness();
  page.page.mount(page.root);
  await new Promise(resolve => setImmediate(resolve));
  page.emit({ready:false,loading:false,error:"读取超时"});
  assert.match(page.root.innerHTML, /桌面上有打开的笔记本电脑/);
  assert.match(page.root.innerHTML, /读取未完成/);
  page.page.unmount();
});

test("context updates render through the subscription and preserve explicit unavailable states", async () => {
  const page = harness();
  page.page.mount(page.root);
  page.emit({ready:false,loading:false,error:"读取超时"});
  assert.match(page.root.innerHTML, /读取未完成/);
  assert.match(page.root.innerHTML, /正在读取天气实况/);
  assert.equal(typeof page.intervalCallback, "function");
  page.page.unmount();
});
