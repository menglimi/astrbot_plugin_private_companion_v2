"use strict";

const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../pages/陪伴小屋/perception-native-page.js"), "utf8");
const flush = () => new Promise(resolve => setImmediate(resolve));

function status(token = "revision-1", timezone = "Asia/Shanghai") {
  return {
    environment: {edit_token:token, sources:{weather_ready:false, alerts_ready:false}, settings:{
      planning_timezone:timezone, planning_annual_calendars:"", planning_weather_enabled:false,
      planning_weather_location:"", planning_weather_max_age_minutes:120,
    }},
    model: {edit_token:token, settings:{calendar_enabled:true, calendar_timezone:timezone,
      holiday_enabled:true, holiday_country:"CN",
      lunar_enabled:true, automatic_solar_terms_enabled:false, almanac_enabled:false,
      platform_enabled:true, model_route_enabled:true, configured_modalities_enabled:true, guidance:""}},
     contact: {settings:{date_checkin_enabled:true, important_dates:"[]",
       important_date_lookahead_days:0, quiet_timezone:timezone}},
     news: {edit_token:token, source:{ready:false, kind:"", label:""},
       diagnostic:{source:{ready:false, kind:"", label:""}, last_attempt_at:null,
         last_checked_at:null, failure:null, item_count:0, candidate:false}, contact_enabled:false,
       automatic_enabled:false, settings:{news_share_enabled:false, "news.enabled":false,
         news_check_interval_minutes:60, news_source_kind:"host", news_source_uid:"",
         news_source_url:""}},
  };
}

function harness() {
  const requests = [];
  const window = {
    CompanionProduct: {hosted:() => true, scopeKey:() => "role-1",
      role:() => ({perception_native_api:"/astrbot_plugin_private_companion_v2/perception-native"}),
      /* 页面取桥先问 bridgeNow()，没有再 await bridgeFor()。 */
      bridgeNow:() => window.AstrBotPluginPage,
      bridgeFor:() => ({then:resolve => resolve(window.AstrBotPluginPage)})},
    AstrBotPluginPage: {
      apiGet:route => new Promise(resolve => requests.push({method:"GET", route, resolve})),
      apiPost:(route, body) => new Promise(resolve => requests.push({method:"POST", route, body, resolve})),
    },
  };
  vm.runInNewContext(source, {window, AbortController, crypto, TextEncoder, setTimeout, clearTimeout, Intl});
  function root() {
    const handlers = {};
    return {isConnected:true, innerHTML:"",
      addEventListener(type, handler) { handlers[type] = handler; },
      input(name, value, kind = "text") { handlers.input({target:{closest:() => ({dataset:{nativeField:name}, type:kind, value})}}); },
      toggle(name, checked) { handlers.input({target:{closest:() => ({dataset:{nativeField:name}, type:"checkbox", checked})}}); },
      submit() { handlers.submit({preventDefault() {}}); },
      click(action) { handlers.click({target:{closest:() => ({dataset:{nativeAction:action}})}}); },
    };
  }
  const environment = root();
  const model = root();
  const news = root();
  window.CompanionNativePerceptionPage.mount({environment, model, news});
  return {requests, environment, model, news, page:window.CompanionNativePerceptionPage};
}

test("edited perception settings save, and a stale draft can adopt the latest token", async () => {
  const {requests, environment} = harness();
  requests[0].resolve({status:"ok", data:status()});
  await flush();

  environment.input("planning_timezone", "Asia/Tokyo");
  environment.submit();
  assert.equal(requests[1].method, "POST");
  assert.equal(requests[1].body.command.changes.planning_timezone, "Asia/Tokyo");
  requests[1].resolve({status:"ok", data:{status:status("revision-2", "Asia/Tokyo")}});
  await flush();
  assert.match(environment.innerHTML, /已保存。/);

  environment.input("planning_timezone", "Asia/Seoul");
  environment.click("refresh");
  requests[2].resolve({status:"ok", data:status("revision-3", "Asia/Tokyo")});
  await flush();
  assert.match(environment.innerHTML, /配置已变化，草稿仍在/);
  environment.click("rebase");
  environment.submit();
  assert.equal(requests[3].body.command.edit_token, "revision-3");
  assert.equal(requests[3].body.command.changes.planning_timezone, "Asia/Seoul");
  requests[3].resolve({status:"ok", data:{status:status("revision-4", "Asia/Seoul")}});
  await flush();
});

test("a city name saves without requiring JSON or manual coordinates", async () => {
  const {requests, environment} = harness();
  requests[0].resolve({status:"ok", data:status()});
  await flush();

  assert.match(environment.innerHTML, /placeholder="输入城市、区县或镇街"/);
  environment.input("location_name", "自定义测试区域");
  environment.submit();
  assert.equal(requests[1].body.section, "environment");
  const savedLocation = JSON.parse(requests[1].body.command.changes.planning_weather_location);
  assert.equal(savedLocation.name, "自定义测试区域");
  assert.equal("latitude" in savedLocation, false);
  assert.equal("longitude" in savedLocation, false);
  const next = status("revision-2");
  next.environment.settings.planning_weather_location = JSON.stringify(savedLocation);
  requests[1].resolve({status:"ok", data:{status:next}});
  await flush();
  assert.match(environment.innerHTML, /已保存。/);
});

test("weather settings explain private on-demand reads and planning context", async () => {
  const {requests, environment} = harness();
  requests[0].resolve({status:"ok", data:status()});
  await flush();

  assert.match(environment.innerHTML, /启用角色天气感知/);
  assert.match(environment.innerHTML, /私聊询问天气时按需读取/);
  assert.match(environment.innerHTML, /日常计划也会参考/);
});

test("news status is diagnostic only and leaves one configuration editor below", async () => {
  const {requests, news, page} = harness();
  requests[0].resolve({status:"ok", data:status()});
  await flush();

  assert.match(news.innerHTML, /资讯源尚未就绪/);
  assert.match(news.innerHTML, /检查来源不会发送消息/);
  assert.match(news.innerHTML, /检查来源/);
  assert.doesNotMatch(news.innerHTML, /data-native-field/);
  assert.doesNotMatch(news.innerHTML, /<form/);
  page.unmount();
});

/* 历法三项（农历 / 节气 / 黄历）此前只有后端字段、没有控件，用户无法开启。
   它们和其余感知开关同属 model 分区，保存走同一次 configure。 */
test("the calendar switches are editable and ride the model section save", async () => {
  const {requests, model} = harness();
  requests[0].resolve({status:"ok", data:status()});
  await flush();

  assert.match(model.innerHTML, /提供农历日期/);
  assert.match(model.innerHTML, /提供节气日期/);
  assert.match(model.innerHTML, /提供黄历宜忌/);
  assert.match(model.innerHTML, /节假日识别地区/);

  model.toggle("lunar_enabled", false);
  model.toggle("automatic_solar_terms_enabled", true);
  model.input("holiday_country", "WEEKEND_ONLY", "select");
  model.submit();
  assert.equal(requests[1].method, "POST");
  assert.equal(requests[1].body.section, "model");
  assert.equal(requests[1].body.command.changes.lunar_enabled, false);
  assert.equal(requests[1].body.command.changes.automatic_solar_terms_enabled, true);
  assert.equal(requests[1].body.command.changes.holiday_country, "WEEKEND_ONLY");
  /* 未改动的项不得混进变更集，否则每次保存都会覆盖别人刚改的值。 */
  assert.equal("almanac_enabled" in requests[1].body.command.changes, false);
  assert.equal("calendar_enabled" in requests[1].body.command.changes, false);
});

test("the overview subscription publishes display fields without exposing configured coordinates", async () => {
  const {requests, page} = harness();
  let snapshot = null;
  const unsubscribe = page.subscribe(value => { snapshot = value; });
  const next = status();
  next.environment.settings.planning_weather_location = JSON.stringify({name:"用户配置区域", latitude:12.34, longitude:56.78});
  next.contact.settings.important_dates = JSON.stringify([{calendar:"gregorian",month:10,day:3,label:"相识纪念日"}]);
  next.contact.settings.important_date_lookahead_days = 4;
  requests[0].resolve({status:"ok", data:next});
  await flush();

  assert.equal(snapshot.ready, true);
  assert.equal(snapshot.environment.locationName, "用户配置区域");
  assert.equal(snapshot.contact.lookaheadDays, 4);
  assert.match(snapshot.contact.dates, /相识纪念日/);
  assert.doesNotMatch(JSON.stringify(snapshot), /latitude|longitude|113\.75|23\.04/);
  unsubscribe();
});
