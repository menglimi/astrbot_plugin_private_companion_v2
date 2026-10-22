"use strict";

const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../pages/陪伴小屋/perception-overview.js"), "utf8");
const styles = fs.readFileSync(path.resolve(__dirname, "../pages/陪伴小屋/semantic-page.css"), "utf8");
const fixedNow = new Date("2026-10-01T10:00:00Z");
class FixedDate extends Date {
  constructor(...args) { super(...(args.length ? args : [fixedNow])); }
  static now() { return fixedNow.getTime(); }
}

function harness({runtimeWeatherState="available",mihomeEnabled=true,balanceEnabled=true,automaticAllowed=true,balanceConfigured=false,balanceResponse=null,otherInjections=[{label:"参考资料",detail:"本轮加入 1 项"}],recallEnabled=true,recallEntries=[{local_time:"17:42",withdrawn_at:"2026-10-01T09:42:00Z",author:"user-1",text:"周末去公园走走"}]}={}) {
  let listener = null, intervalCallback = null, cleared = false, requested = [], bridgeRequests = [];
  const failedRequests = new Set(), tabActivations = [], focused = [];
  const currentBalance = balanceResponse || (balanceConfigured
    ? {configured:true,available:true,provider:"newapi",provider_label:"NewAPI",currency_label:"额度",
      amount:"123.45",observed_at:"2026-10-01T09:59:00Z",state:"available"}
    : {configured:false,available:false,provider:"newapi",provider_label:"NewAPI",currency_label:"额度",
      amount:null,observed_at:null,state:"not_configured"});
  const parentNodes = {
    '[data-perception-tab="config-injection"]': {hidden:false},
    "#perception-detail-mihome": {hidden:true},
    "#mihomeStatusWorkspace": {innerHTML:""},
    "#perceptionRecallWorkspace": {innerHTML:""},
    "#perceptionInjectionWorkspace": {innerHTML:""},
    "#perceptionBalanceSourceWorkspace": {innerHTML:"",handlers:{},
      addEventListener(type,handler){this.handlers[type]=handler;},querySelector(){return null;}},
  };
  const root = {isConnected:true, innerHTML:"", handlers:{},
    addEventListener(type, handler) { this.handlers[type] = handler; },
    removeEventListener(type) { delete this.handlers[type]; },
    querySelector(selector) {
      const match = /\[data-context-clock-(time|date|zone|lunar|tag)\]/.exec(selector);
      if (!match) return {focus(options) {focused.push({selector,options});}};
      const key = match[1];
      return this.clockNodes?.[key] || (this.clockNodes ||= {}, this.clockNodes[key] = {textContent:"", hidden:false});
    },
    parentElement:{querySelector(selector) { return parentNodes[selector] || null; }}};
  let snapshot = {ready:true,
    environment:{weatherReady:true, alertsReady:true, locationName:"用户配置区域", weatherEnabled:true, timezone:"Asia/Shanghai"},
    model:{calendarEnabled:true, timezone:"Asia/Shanghai", modalitiesEnabled:true},
    contact:{dateCheckinEnabled:true, lookaheadDays:3, timezone:"Asia/Shanghai",
      balanceAwarenessEnabled:balanceEnabled, automaticAllowed,
      dates:JSON.stringify([{calendar:"gregorian",month:10,day:3,label:"相识纪念日"}])},
    news:{ready:true,assembled:true,networkStatus:"succeeded",itemCount:2,label:"AstrBot 网页搜索",sourceKind:"search",explorationEnabled:true,
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
      device:{available:true,battery_percent:68,charging:true,app_state:"foreground",last_report_at:1790848200},
      health:{available:true,measurements:[{label:"心率",value:72,unit:"次/分"}],captured_at:1790848200}}},
    /* 服务端日历要齐全才有意义：缺 local_date 会被判定为"没有可用日历"而整体降级。 */
    calendar:{status:"available",timezone:"Asia/Shanghai",local_date:"2026-10-01",weekday:"星期四",local_time:"18:00",
      holiday:{status:"available",kind:"workday",label:"工作日",source:"weekday_fallback"},
      lunar_status:"available",lunar_date:"农历八月二十",automatic_solar_terms:{status:"available",today:[],upcoming:[]},
      almanac:{status:"available",yi:"读书",ji:"熬夜"}},
    other_injections:otherInjections,
    camera:{state:"available",status:"success",answer_available:true,purpose:"看看我现在在做什么",
      captured_at:"2026-10-01T09:57:00Z",observation:{summary:"桌面上有打开的笔记本电脑。",confidence:0.9}}};
  const product = {scopeKey:() => "role-1", role:() => ({model_api:"/astrbot_plugin_private_companion/model",
      perception_native_api:"/astrbot_plugin_private_companion/perception-native"}),
    provider:id => id === "screen" ? {integration_state:"connected",runtime_ready:true,reason:"屏幕扩展运行正常"}
      : {integration_state:"missing",reason:"未安装"},
    statusLabel:value => value, data:{state:{state:{values:{},settings:{}}}},
    stateValues:() => null, selection:() => ({role_id:"role-1"}), relative:value => value, unwrap:value => value,
    request:async(_method,route) => {
      requested.push(route);
      if (failedRequests.has(route)) throw new Error("读取超时");
      if (route.endsWith("/runtime")) return runtime;
      if (route.endsWith("/balance")) return currentBalance;
      if (route.endsWith("/voice")) return {languages:[{k:"zh-CN",n:"中文",bind:"tts-main"}],
        providers:[{id:"tts-main",label:"TTS 主路由",model:"tts-live"}],catalog_state:"ready",voice_enabled:true};
      if (route.endsWith("/image")) return {actions:[{action:"image.generate",enabled:true,
        owner:"Image 扩展",provider_id:"image-live",state:"ready"}]};
      return status;
    },
    bridgeNow:() => ({apiGet:async route => {
      bridgeRequests.push(["GET", route]);
      if (failedRequests.has(route)) throw new Error("读取超时");
      if (route === "semantic") return {settings:{analysis_provider:"vision-analysis"}};
      if (route === "extensions") return {extensions:{reality:{settings:{enabled:true,mihome:{enabled:true}},management:{mihome:{
        tool_settings:{enable_readonly_tool:mihomeEnabled},snapshot_at:"2026-10-01 17:55",devices:[
          {did:"sensitive-device-id-1",configured:true,name:"客厅灯",aliases:["living_light"],online:true},
          {did:"sensitive-device-id-2",configured:true,name:"书房插座",aliases:["study_plug"],online:false}]}}}}};
      if (route === "host-options/balance") return {service_balance:{source:balanceConfigured?"plugin":"none",source_state:balanceConfigured?"configured":"not_configured",
        provider:"newapi",url:balanceConfigured?"https://newapi.example.com":"",user_id:"",value_divisor:"500000",has_api_key:balanceConfigured},
        edit_tokens:{balance:"b".repeat(64)}};
      return {enabled:recallEnabled,entries:recallEntries};
    },apiPost:async(route,body) => {
      bridgeRequests.push(["POST", route, body]);
      if (failedRequests.has(route)) throw Object.assign(new Error("连接失败"),{code:"balance_test_failed"});
      if (route === "host-options/balance/test") return {tested:true,available:true,provider:"newapi",
        provider_label:"NewAPI",currency_label:"额度",amount:"123.45",observed_at:"2026-10-01T09:59:00Z"};
      return {saved:true,apply_mode:"immediate",service_balance:{source:"plugin",source_state:"configured",
        provider:"newapi",url:body.changes.url,user_id:body.changes.user_id,
        value_divisor:body.changes.value_divisor,has_api_key:true},edit_tokens:{balance:"c".repeat(64)}};
    }})};
  const native = {subscribe(callback) { listener=callback; callback(snapshot); return () => {listener=null;}; },
    refresh() {}};
  const window = {CompanionProduct:product,CompanionNativePerceptionPage:native,
    CompanionPerceptionTabs:{activate(...args) {tabActivations.push(args);window.CompanionPerceptionOverviewPage.select(...args);}},
    };
  const intervals = new Map(); let intervalId=0;
  vm.runInNewContext(source, {window, Date:FixedDate, Intl, JSON, Number, String, Array, Object, RegExp,
    AbortController, setInterval(callback) { intervalCallback=callback; intervals.set(++intervalId,callback); return intervalId; },
    clearInterval(id) { intervals.delete(id); cleared=true; }, setTimeout, clearTimeout});
  return {page:window.CompanionPerceptionOverviewPage, root, runtime, snapshot, intervals,parentNodes,tabActivations,focused,
    balanceWorkspace:parentNodes["#perceptionBalanceSourceWorkspace"],
    failRequest(route) {failedRequests.add(route);}, recoverRequests() {failedRequests.clear();},
    emit(next) { snapshot=next; listener?.(next); }, get requested(){return requested;},
    get bridgeRequests(){return bridgeRequests;},
    get intervalCallback(){return intervalCallback;}, get cleared(){return cleared;}};
}

test("overview shows the requested context, live routes, authorized devices and only in-window dates", async () => {
  const page = harness();
  page.page.mount(page.root);
  await new Promise(resolve => setImmediate(resolve));

  assert.deepEqual(page.requested.sort(), [
    "/astrbot_plugin_private_companion/model",
    "/astrbot_plugin_private_companion/model/balance",
    "/astrbot_plugin_private_companion/model/image",
    "/astrbot_plugin_private_companion/model/voice",
    "/astrbot_plugin_private_companion/perception-native/runtime",
  ]);
  assert.match(page.root.innerHTML, /用户配置区域/);
  assert.match(page.root.innerHTML, /晴 · 22°C/);
  assert.match(page.root.innerHTML, /大风蓝色预警/);
  assert.match(page.root.innerHTML, /服务余额联系已启用/);
  assert.match(page.root.innerHTML, /data-board-goto="config-balance:perception-detail-balance-source"/);
  assert.doesNotMatch(page.root.innerHTML, /data-go="manage" data-manage="contact"/);
  assert.match(page.root.innerHTML, /不会持续注入日常对话/);
  assert.doesNotMatch(page.root.innerHTML, /余额(?:\s|&nbsp;)*\d+(?:\.\d+)?/);
  assert.match(page.root.innerHTML, /所在地/);
  assert.match(page.root.innerHTML, /天气实况/);
  assert.match(page.root.innerHTML, /model-live/);
  assert.match(page.root.innerHTML, /Provider provider-main · 备用 model-safe/);
  assert.deepEqual([...page.root.innerHTML.matchAll(/class="perception-mtile-model">([^<]*)<\/strong>/g)].map(match => match[1]),
    ["model-live", "tts-live", "image-live", "vision-live"]);
  assert.match(page.root.innerHTML, /image-live/);
  assert.match(page.root.innerHTML, /中文 · 已就绪/);
  assert.match(page.root.innerHTML, /Image 扩展 · image-live · 已就绪/);
  assert.doesNotMatch(page.root.innerHTML.replace(/<[^>]*>/g, ''), /\bready\b/);
  assert.match(page.root.innerHTML, /vision-live/);
  assert.match(page.root.innerHTML, /外部资讯与检索/);
  assert.match(page.root.innerHTML, /AstrBot 网页搜索/);
  assert.match(page.root.innerHTML, /用户正在查看代码编辑器/);
  assert.match(page.root.innerHTML, /上海市·徐汇区/);
  assert.match(page.root.innerHTML, /摄像头状态/);
  /* 农历与星期属于服务端日历语义，由运行时写入日期行，不在服务端渲染的 HTML 里。 */
  assert.match(page.root.clockNodes.date.textContent, /农历八月二十/);
  assert.match(page.root.clockNodes.date.textContent, /星期四/);
  assert.match(page.root.clockNodes.date.textContent, /10 月 1 日/);
  assert.match(page.root.innerHTML, /宜 读书 · 忌 熬夜/);
  assert.match(page.root.innerHTML, /桌面上有打开的笔记本电脑/);
  assert.match(page.root.innerHTML, /看看我现在在做什么/);
  assert.match(page.root.innerHTML, /相识纪念日 · 2 天后/);
  /* 明细行现在是就地展开（data-perception-toggle），旧的“跳去重日期 tab”属性已废弃。 */
  assert.match(page.root.innerHTML, /data-board-goto="config-models:perception-detail-context"/);
  assert.match(page.root.innerHTML, /日期与历法/);
  assert.match(page.root.innerHTML, /感知仪表盘/);
  assert.match(page.root.innerHTML, /项实况在线/);
  assert.match(page.root.innerHTML, /data-context-clock-time/);
  assert.match(page.root.innerHTML, /data-context-clock-date/);
  assert.match(page.root.innerHTML, /data-context-clock-lunar/);
  assert.doesNotMatch(page.root.innerHTML, /perception-group|perception-stream-container|perception-stream-details|perception-board-config/);
  assert.equal((page.root.innerHTML.match(/class="perception-board-card/g) || []).length, 4);
  for (const item of ["所在地", "天气实况", "天气预警", "余额感知", "对话模型", "TTS 模型", "生图模型",
    "视觉模型", "外部资讯与检索", "用户定位", "识屏信息", "摄像头状态", "撤回记录",
    "米家设备", "其他注入"]) {
    assert.match(page.root.innerHTML, new RegExp(item));
  }
  assert.match(page.root.innerHTML, /撤回记录/);
  assert.match(page.root.innerHTML, /米家设备/);
  assert.match(page.parentNodes["#perceptionRecallWorkspace"].innerHTML, /周末去公园走走/);
  assert.match(page.parentNodes["#mihomeStatusWorkspace"].innerHTML, /客厅灯/);
  assert.match(page.parentNodes["#mihomeStatusWorkspace"].innerHTML, /离线/);
  assert.doesNotMatch(page.parentNodes["#mihomeStatusWorkspace"].innerHTML, /sensitive-device-id/);
  assert.match(page.parentNodes["#perceptionInjectionWorkspace"].innerHTML, /参考资料/);
  assert.deepEqual(page.bridgeRequests.filter(([method, route]) => method === "GET" && route === "extensions"),
    [["GET", "extensions"]]);
  assert.match(page.root.clockNodes.time.textContent, /18:00:00/);
  /* 今天是工作日就不该挂节假日标签：不是节日就空着，不替它找一个标签。 */
  assert.equal(page.root.clockNodes.tag.textContent, "");
  assert.equal(page.root.clockNodes.tag.hidden, true);

  const outsideWindow = {...page.snapshot, contact:{...page.snapshot.contact, lookaheadDays:1}};
  assert.equal(page.page.upcomingDates(outsideWindow, new FixedDate()).length, 0);
  assert.equal(page.page.upcomingDates({...page.snapshot, contact:{...page.snapshot.contact, dateCheckinEnabled:false}}, new FixedDate()).length, 1);
  assert.equal(page.page.upcomingDates({...page.snapshot, model:{...page.snapshot.model, calendarEnabled:false}}, new FixedDate()).length, 1);

  page.page.unmount();
  assert.equal(page.intervals.size, 0);
  assert.equal(page.cleared, true);
});

test("dashboard provides narrow-screen rows, focus states and reduced motion", () => {
  assert.match(styles, /@media\(max-width:900px\)\{\.perception-board\{grid-template-columns:minmax\(0,1fr\)\}/);
  assert.match(styles, /\.perception-reading-row>\.perception-reading-value\{grid-column:2\/-1/);
  assert.match(styles, /\[data-board-goto\]:focus-visible/);
  assert.match(styles, /prefers-reduced-motion:reduce\).*?\.perception-board/);
  assert.match(styles, /\.perception-balance-actions button:focus-visible/);
});

test("the two lower cards show source-backed readings and explain absent snapshots", async () => {
  const page=harness({mihomeEnabled:false});
  page.page.mount(page.root);
  await new Promise(resolve=>setImmediate(resolve));
  const html=page.root.innerHTML;
  assert.match(html,/当前定位/);
  assert.match(html,/最近一次定位/);
  assert.match(html,/电量 68% · 充电中 · 前台运行/);
  assert.match(html,/上次识别 · 编辑器/);
  assert.match(html,/最近检查 2 条 · AstrBot 网页搜索/);
  assert.match(html,/当前窗口 1 条可读记录/);
  assert.match(html,/datetime="2026-10-01T09:56:00\.000Z"/);
  assert.match(html,/4 分钟前/);
  assert.doesNotMatch(html,/已静音|累计 12 条|已读取摘要|￥|¥/);
  page.page.unmount();

  page.runtime.reality={state:"ready",reason:"no_recent_snapshot"};
  page.runtime.camera={state:"ready",reason:"no_recent_observation"};
  page.runtime.screen={state:"empty"};
  page.page.mount(page.root);
  await new Promise(resolve=>setImmediate(resolve));
  assert.match(page.root.innerHTML,/授权已就绪，尚无最近快照/);
  assert.match(page.root.innerHTML,/摄像头 · 已授权/);
  assert.doesNotMatch(page.root.innerHTML,/最近一次定位|电量 68%|编辑器|perception-feature is-location is-ready/);
  assert.match(page.root.innerHTML,/perception-feature is-location is-pending/);
  page.page.unmount();
});

test("configured balance is read through the model balance route and failed reads clear the amount", async () => {
  const page=harness({balanceConfigured:true});
  page.page.mount(page.root);
  await new Promise(resolve=>setImmediate(resolve));
  assert.match(page.root.innerHTML,/perception-feature is-balance is-ready/);
  assert.match(page.root.innerHTML,/perception-balance-unit">额度<\/span> 123\.45/);
  assert.ok(page.requested.includes("/astrbot_plugin_private_companion/model/balance"));
  assert.equal(page.bridgeRequests.some(([method,route])=>method==="POST"&&route==="host-options/balance/test"),false,
    "打开仪表盘复用 Token 页的模型余额接口");
  page.page.select("config-balance:perception-detail-balance-source");
  const controls={url:{value:"https://newapi.example.com"},api_key:{value:""},user_id:{value:""},value_divisor:{value:"500000"},clear_configuration:{checked:false}};
  const resultStatus={hidden:false};
  const form={querySelector(selector){return selector==="[data-balance-test-result]"?resultStatus:controls[selector.match(/^\[name="(.+)"\]$/)?.[1]]||null;}};
  const testButton={closest(selector){return selector==="[data-balance-form]"?form:null;}};
  const query=async()=>{
    page.balanceWorkspace.handlers.click({target:{closest(selector){return selector==="[data-balance-test]"?testButton:null;}},preventDefault(){}});
    await new Promise(resolve=>setImmediate(resolve));
  };
  await query();
  assert.match(page.root.innerHTML,/最近一次查询/);
  assert.match(page.root.innerHTML,/perception-balance-unit">额度<\/span> 123\.45/);
  page.failRequest("/astrbot_plugin_private_companion/model/balance");
  await query();
  assert.match(page.root.innerHTML,/读取超时/);
  assert.doesNotMatch(page.root.innerHTML,/123\.45/);
  page.recoverRequests();
  await query();
  const field={dataset:{balanceField:"url"},value:"https://other.example.com",closest(){return form;}};
  page.balanceWorkspace.handlers.input({target:{closest(selector){return selector==="[data-balance-field]"?field:null;}}});
  assert.match(page.root.innerHTML,/123\.45/,"编辑草稿配置不影响已保存数据源的当前余额");
  assert.equal(resultStatus.hidden,false,"当前数据源读数与草稿测试结果分开维护");
  page.page.unmount();
});

test("the latest balance reading survives switching away from the dashboard", async () => {
  const page = harness({balanceConfigured:true});
  page.page.mount(page.root);
  await new Promise(resolve=>setImmediate(resolve));
  page.page.select("config-balance:perception-detail-balance-source");
  const form={querySelector(selector){
    const name=selector.match(/^\[name="(.+)"\]$/)?.[1];
    return name === "url" ? {value:"https://newapi.example.com"}
      : name === "user_id" ? {value:""}
      : name === "value_divisor" ? {value:"500000"}
      : name === "api_key" ? {value:""}
      : name === "clear_configuration" ? {checked:false} : null;
  }};
  const testButton={closest(selector){return selector==="[data-balance-form]"?form:null;}};
  page.balanceWorkspace.handlers.click({target:{closest(selector){
    return selector==="[data-balance-test]"?testButton:null;
  }},preventDefault(){}});
  await new Promise(resolve=>setImmediate(resolve));
  assert.match(page.root.innerHTML,/额度<\/span> 123\.45/);

  page.page.unmount();
  page.page.mount(page.root);
  await new Promise(resolve=>setImmediate(resolve));
  assert.match(page.root.innerHTML,/额度<\/span> 123\.45/);

  /* Route changes keep the successful observation and safe draft fields, but
     never carry a typed nap_ token into the next mount. */
  page.page.select("config-balance:perception-detail-balance-source");
  const tokenField={dataset:{balanceField:"api_key"},value:"draft-nap-secret",closest(){return form;}};
  page.balanceWorkspace.handlers.input({target:{closest(selector){
    return selector==="[data-balance-field]"?tokenField:null;
  }}});
  page.page.unmount();
  page.page.mount(page.root);
  page.page.select("config-balance:perception-detail-balance-source");
  assert.doesNotMatch(page.balanceWorkspace.innerHTML,/draft-nap-secret/);
  page.page.unmount();
});

test("successful perception readings are visible immediately after a route remount", async () => {
  const page = harness();
  page.page.mount(page.root);
  await new Promise(resolve => setImmediate(resolve));
  assert.match(page.root.innerHTML, /晴 · 22°C/);
  assert.match(page.root.innerHTML, /model-live/);

  page.page.unmount();
  page.page.mount(page.root);
  /* mount() starts the refresh requests asynchronously. The cached snapshot is
     rendered first, so routing away and back does not turn known readings into
     an empty loading board. */
  assert.match(page.root.innerHTML, /晴 · 22°C/);
  assert.match(page.root.innerHTML, /model-live/);
  await new Promise(resolve => setImmediate(resolve));
  assert.match(page.root.innerHTML, /真实状态已同步|正在读取实况/);
  page.page.unmount();
});

test("dashboard regions directly select the configuration and model subtab below", async () => {
  const page = harness();
  page.page.mount(page.root);
  await new Promise(resolve => setImmediate(resolve));
  const click = (selector, dataset) => page.root.handlers.click({target:{closest(value) {
    return value === selector ? {dataset} : null;
  }}});

  for (const destination of [
    "config-screen:perception-detail-device-access", "config-recall:perception-detail-recalls",
    "config-screen:perception-detail-mihome", "config-injection:perception-detail-injection",
    "config-models:perception-detail-context", "config-environment:perception-detail-important-days",
  ]) {
    assert.match(page.root.innerHTML, new RegExp(`data-board-goto="${destination}"`));
    click("[data-board-goto]", {boardGoto:destination});
    assert.equal(page.tabActivations.at(-1)[0], destination);
    assert.deepEqual({...page.tabActivations.at(-1)[1]}, {focus:true,scroll:true,modelTab:""});
    assert.doesNotMatch(page.root.innerHTML, /perception-stream-details|perception-board-config/);
  }

  for (const [id, tab] of [["model-tts", "voice"], ["model-image", "image"]]) {
    assert.match(page.root.innerHTML, new RegExp(`id="perception-channel-${id}"[^>]*data-board-model-tab="${tab}"`));
    click("[data-board-goto]", {boardGoto:"config-models:perception-detail-model-route",boardModelTab:tab});
    assert.equal(page.tabActivations.at(-1)[1].modelTab, tab);
  }
  page.page.unmount();
});

test("balance awareness distinguishes the active opportunity from a disabled setting", async () => {
  const disabled = harness({balanceEnabled:false});
  disabled.page.mount(disabled.root);
  await new Promise(resolve => setImmediate(resolve));
  assert.match(disabled.root.innerHTML, /服务余额联系契机未启用/);
  disabled.page.unmount();

  const gated = harness({balanceEnabled:true,automaticAllowed:false});
  gated.page.mount(gated.root);
  await new Promise(resolve => setImmediate(resolve));
  assert.match(gated.root.innerHTML, /余额契机已开，但后台自动联系未开启/);
  assert.match(gated.root.innerHTML, /总开关受限/);
  gated.page.unmount();
});

test("balance settings stay in one lower workspace and save without token echo", async () => {
  const page = harness({balanceEnabled:false});
  page.page.mount(page.root);
  await new Promise(resolve => setImmediate(resolve));
  const clickEvent = {target:{closest(selector) { return selector === "[data-board-goto]" ? {dataset:{boardGoto:"config-balance:perception-detail-balance-source"}} : null; }}};
  page.root.handlers.click(clickEvent);
  await new Promise(resolve => setImmediate(resolve));

  const workspace = page.balanceWorkspace;
  assert.match(workspace.innerHTML, /data-balance-form/);
  assert.match(workspace.innerHTML, /name="api_key"[^>]*type="password"/);
  assert.match(workspace.innerHTML, /name="user_id"/);
  assert.match(workspace.innerHTML, /name="value_divisor"/);
  assert.match(workspace.innerHTML, /data-balance-test/);
  assert.match(workspace.innerHTML, /data-go="manage" data-manage="contact" data-contact-view="sources"/);
  assert.match(workspace.innerHTML, /前往主动联系 · 外部触发源/);
  const externalCard = page.root.innerHTML.split('data-perception-board="external"')[1].split("</article>")[0];
  assert.doesNotMatch(externalCard, /data-balance-form|perception-board-config/);
  assert.doesNotMatch(page.root.innerHTML, /data-balance-form/);
  assert.equal((workspace.innerHTML.match(/data-balance-form/g) || []).length, 1);
  assert.equal(page.tabActivations.at(-1)[0], "config-balance:perception-detail-balance-source");
  assert.ok(page.bridgeRequests.some(([method, route]) => method === "GET" && route === "host-options/balance"));

  const form = {querySelector(selector) {
    if (selector === '[name="url"]') return {value:"https://newapi.example.com"};
    if (selector === '[name="user_id"]') return {value:"1234"};
    if (selector === '[name="value_divisor"]') return {value:"1000000"};
    if (selector === '[name="api_key"]') return {value:"visible-only-while-typing"};
    if (selector === '[name="clear_configuration"]') return {checked:false};
    if (selector === 'button[type="submit"]') return {disabled:false,textContent:"保存数据源"};
    return null;
  }};
  await workspace.handlers.submit({target:{closest(selector) { return selector === "[data-balance-form]" ? form : null; }},
    preventDefault() {}});
  assert.deepEqual(JSON.parse(JSON.stringify(page.bridgeRequests[page.bridgeRequests.length - 1])), ["POST", "host-options/balance", {
    edit_token:"b".repeat(64), changes:{url:"https://newapi.example.com",api_key:"visible-only-while-typing",
      user_id:"1234",value_divisor:"1000000"},
  }]);
  assert.match(workspace.innerHTML, /已保存并立即生效/);
  assert.match(page.root.innerHTML, /数据源已配置，余额联系未开启/);
  assert.doesNotMatch(workspace.innerHTML + page.root.innerHTML, /visible-only-while-typing/);
  page.page.unmount();
});

test("opening the external and records page loads its single balance source form", async () => {
  const page = harness();
  page.page.mount(page.root);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(page.bridgeRequests.filter(([method, route]) => method === "GET" && route === "host-options/balance").length, 1);

  page.page.select("config-news:perception-detail-external");
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(page.bridgeRequests.filter(([method, route]) => method === "GET" && route === "host-options/balance").length, 1);
  assert.match(page.balanceWorkspace.innerHTML, /data-balance-form/);
  assert.equal((page.balanceWorkspace.innerHTML.match(/data-balance-form/g) || []).length, 1);
  page.page.unmount();
});

test("balance form keeps an unsaved token through redraw and tests the draft without saving", async () => {
  const page = harness();
  page.page.mount(page.root);
  await new Promise(resolve => setImmediate(resolve));
  page.page.select("config-balance:perception-detail-balance-source");
  await new Promise(resolve => setImmediate(resolve));

  const draft = {url:"https://newapi.example.com", user_id:"1234", value_divisor:"1000000",
    api_key:"draft-token-kept", clear_configuration:false};
  for (const [name, value] of Object.entries(draft)) {
    const field = {dataset:{balanceField:name}, value, checked:value};
    page.balanceWorkspace.handlers.input({target:{closest(selector) {
      return selector === "[data-balance-field]" ? field : null;
    }}});
  }
  page.emit({...page.snapshot, contact:{...page.snapshot.contact, balanceAwarenessEnabled:false}});
  assert.match(page.balanceWorkspace.innerHTML, /value="draft-token-kept"/);

  const click = (selector, dataset) => page.root.handlers.click({target:{closest(value) {
    return value === selector ? {dataset} : null;
  }}});
  click("[data-board-goto]", {boardGoto:"config-models:perception-detail-model-route"});
  click("[data-board-goto]", {boardGoto:"config-balance:perception-detail-balance-source"});
  assert.doesNotMatch(page.root.innerHTML, /data-balance-form|draft-token-kept/);
  assert.match(page.balanceWorkspace.innerHTML, /value="draft-token-kept"/);
  assert.equal((page.balanceWorkspace.innerHTML.match(/data-balance-form/g) || []).length, 1);
  assert.equal(page.bridgeRequests.filter(([method,route]) => method === "GET" && route === "host-options/balance").length, 1);

  const controls = Object.fromEntries(Object.entries(draft).map(([name, value]) => [name,
    name === "clear_configuration" ? {checked:value} : {value}]));
  const form = {querySelector(selector) {
    const name = selector.match(/^\[name="(.+)"\]$/)?.[1];
    return name ? controls[name] : null;
  }};
  const testButton = {closest(selector) { return selector === "[data-balance-form]" ? form : null; }};
  page.balanceWorkspace.handlers.click({target:{closest(selector) {
    return selector === "[data-balance-test]" ? testButton : null;
  }}, preventDefault() {}});
  await new Promise(resolve => setImmediate(resolve));

  const testCall = page.bridgeRequests.find(([method, route]) => method === "POST" && route === "host-options/balance/test");
  assert.deepEqual(JSON.parse(JSON.stringify(testCall)), ["POST", "host-options/balance/test", {
    edit_token:"b".repeat(64), changes:{url:"https://newapi.example.com",api_key:"draft-token-kept",
      user_id:"1234",value_divisor:"1000000"},
  }]);
  assert.equal(page.bridgeRequests.some(([method, route]) => method === "POST" && route === "host-options/balance"), false);
  assert.match(page.balanceWorkspace.innerHTML, /草稿测试成功：123\.45 额度/);
  assert.match(page.balanceWorkspace.innerHTML, /value="draft-token-kept"/);
  assert.match(page.root.innerHTML, /草稿测试结果/);
  assert.match(page.root.innerHTML, /perception-balance-unit">额度<\/span> 123\.45/);
  assert.doesNotMatch(page.root.innerHTML, /￥|¥|draft-token-kept/);
  page.page.unmount();
});

test("readiness count reflects available signals, and optional rows stay absent", async () => {
  const page = harness({mihomeEnabled:false,otherInjections:[],recallEnabled:false,recallEntries:[]});
  page.page.mount(page.root);
  await new Promise(resolve => setImmediate(resolve));

  /* 通道数与实况在线数全程由当前 percepts 现算，不为"看起来完整"写死总数。 */
  assert.match(page.root.innerHTML, /个感知通道 · \d+ 项实况在线/);
  assert.match(page.root.innerHTML, /\d+ 通道/);
  assert.match(page.root.innerHTML, /本轮暂无其他注入/);
  assert.doesNotMatch(page.root.innerHTML, /id="perception-channel-ext-injection"/);
  /* 未启用的通道不作为"感知通道"列出（与没有路由的视觉模型同处理），
     也不展示任何设备明细；对应详情分区保持隐藏，且只发一次能力查询。 */
  assert.match(page.root.innerHTML, /米家 · 未启用/);
  assert.doesNotMatch(page.root.innerHTML, /id="perception-channel-device-mihome"/);
  assert.equal(page.parentNodes["#perception-detail-mihome"].hidden, true);
  assert.deepEqual(page.bridgeRequests.filter(([method, route]) => method === "GET" && route === "extensions"),
    [["GET", "extensions"]]);
  page.page.unmount();
});

test("the MiHome dashboard uses the authenticated V2 page bridge", () => {
  assert.doesNotMatch(source, /window\.fetch\s*\(/);
  assert.doesNotMatch(source, /\/api\/plugin\/astrbot_plugin_mihome\//);
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

test("failed reads clear stale results, name the failed settings and recover on retry", async () => {
  const page = harness();
  page.page.mount(page.root);
  await new Promise(resolve => setImmediate(resolve));
  page.failRequest("/astrbot_plugin_private_companion/perception-native/runtime");
  page.failRequest("/astrbot_plugin_private_companion/model/voice");
  page.failRequest("/astrbot_plugin_private_companion/model/image");
  page.emit({...page.snapshot, ready:false, loading:false, error:"读取超时", environment:{}, news:{}});
  page.root.handlers.click({target:{closest(selector) {return selector === "[data-context-refresh]" ? {} : null;}}});
  await new Promise(resolve => setImmediate(resolve));

  assert.match(page.root.innerHTML, /读取未完成/);
  assert.match(page.root.innerHTML, /余额联系设置读取失败/);
  assert.match(page.root.innerHTML, /外部来源设置读取失败/);
  assert.match(page.root.innerHTML, /角色地点读取失败/);
  assert.match(page.root.innerHTML, /天气预警 · 读取失败/);
  assert.doesNotMatch(page.root.innerHTML, /正在读取|桌面上有打开的笔记本电脑|大风蓝色预警|晴 · 22°C/);
  const balanceRow = page.root.innerHTML.match(/<button[^>]*id="perception-channel-ext-balance"[\s\S]*?<\/button>/)[0];
  assert.match(balanceRow, /is-pending/);
  const imageRow = page.root.innerHTML.match(/<button[^>]*id="perception-channel-model-image"[\s\S]*?<\/button>/)[0];
  assert.match(imageRow, /is-pending/);
  assert.match(imageRow, /读取失败/);
  assert.doesNotMatch(imageRow, /已分配|可调用/);

  page.recoverRequests();
  page.emit(page.snapshot);
  page.root.handlers.click({target:{closest(selector) {return selector === "[data-context-refresh]" ? {} : null;}}});
  await new Promise(resolve => setImmediate(resolve));
  assert.match(page.root.innerHTML, /真实状态已同步/);
  assert.match(page.root.innerHTML, /晴 · 22°C/);
  assert.match(page.root.innerHTML, /tts-live/);
  assert.match(page.root.innerHTML, /服务余额联系已启用/);
  page.page.unmount();
});

test("perception board enumerates real perception items and keeps every count consistent", async () => {
  // 态势板把"真实能感知到的内容"逐条铺成一行；state=ready 即实况在线。
  // 校验口径一致：每条通道只有一个出口、卡片读数之和＝页头读数，
  // 且态势板与下方明细列表沿用同一份 percepts（不存在两边各喊一个数）。
  const page = harness({mihomeEnabled:false,otherInjections:[],recallEnabled:false,recallEntries:[]});
  page.page.mount(page.root);
  await new Promise(resolve => setImmediate(resolve));

  const html = page.root.innerHTML;
  for (const id of ["environment", "models", "devices", "external"])
    assert.match(html, new RegExp(`data-perception-board="${id}"`));

  for (const id of ["environment", "models"]) {
    const heading = html.split(`id="perception-board-toggle-${id}"`)[1].split("</button>")[0];
    assert.doesNotMatch(heading, /<small>/, "截图中的两处标题应移除统计说明行");
  }

  const headline = /(\d+) 个感知通道 · (\d+) 项实况在线/.exec(html);
  assert.ok(headline, "页头应给出通道数与实况在线数");
  const total = Number(headline[1]), live = Number(headline[2]);
  assert.ok(total >= 1 && live <= total, "实况在线数不应多于通道总数");

  const heads = [...html.matchAll(/aria-label="([^"]*)：(\d+) 条通道，(\d+) 项实况在线/g)];
  assert.equal(heads.length, 4, "四张卡都要各自给出读数");
  assert.equal(heads.reduce((acc, m) => acc + Number(m[2]), 0), total, "各卡通道数之和应等于页头总数");
  assert.equal(heads.reduce((acc, m) => acc + Number(m[3]), 0), live, "各卡实况在线之和应等于页头读数");

  assert.doesNotMatch(html, /data-perception-toggle|data-balance-toggle|perception-stream-container|perception-group/);
  assert.equal((html.match(/class="perception-board-card/g) || []).length, 4);
  page.page.unmount();
});
