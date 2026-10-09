"use strict";

/* 日期语义的数据链路回归：
   服务端 /runtime 下发的 calendar（project_local_date 的产出）才是日期的唯一权威。
   前端只允许让"秒"本地走字，绝不可以自己重算星期 / 农历 / 节假日——
   这些语义服务端算了，页面重算一次就等于多一个可能答错的地方。
   跨日同样必须回服务端取，因为农历与节假日跨日会变。 */

const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../pages/陪伴小屋/perception-overview.js"), "utf8");
const fixedNow = new Date("2026-10-06T10:00:00Z");
class FixedDate extends Date {
  constructor(...args) { super(...(args.length ? args : [fixedNow])); }
  static now() { return fixedNow.getTime(); }
}

const RUNTIME_BASE = {
  observed_at: "2026-10-06T10:00:00+00:00",
  weather: {state:"available", location:"广东省东莞市", provider:"open-meteo",
    observed_at:"2026-10-06T09:40:00+00:00", condition:"局部晴朗",
    temperature_c:25, humidity_pct:58, wind_kph:12, alerts:[]},
  screen: {state:"empty"},
  reality: {state:"ready", reason:"no_recent_snapshot"},
  camera: {state:"ready", reason:"no_recent_observation"},
  other_injections: [],
};
const CALENDAR_AVAILABLE = {
  status: "available", basis: "request_time_calendar_projection", timezone: "Asia/Shanghai",
  local_date: "2026-10-06", weekday: "星期二", local_time: "18:00", period: "傍晚",
  fixed_gregorian_holiday: null,
  holiday: {status:"available", kind:"holiday", label:"国庆节", source:"configured_annual_calendar"},
  lunar_date: "八月十六", lunar_status: "available",
  almanac: {status:"available", yi:"读书", ji:"熬夜"},
};

/* 最小挂载环境：只实现渲染与时钟写入真正用到的那部分 DOM。 */
function harness(payload) {
  const written = new Map();
  const root = {
    isConnected: true,
    addEventListener() {}, removeEventListener() {},
    set innerHTML(v) { this._html = v; }, get innerHTML() { return this._html || ""; },
    querySelector(selector) {
      if (!this._nodes) this._nodes = new Map();
      if (!this._nodes.has(selector)) this._nodes.set(selector, {textContent:"", hidden:false});
      return this._nodes.get(selector);
    },
    querySelectorAll() { return []; },
    contains() { return false; }, parentElement: null,
  };
  for (const key of ["time", "date", "zone", "lunar", "tag"]) {
    root.querySelector(`[data-context-clock-${key}]`);
    written.set(key, root._nodes.get(`[data-context-clock-${key}]`));
  }
  const product = {
    scopeKey: () => "role-1", hosted: () => true, relative: value => value, unwrap: value => value,
    provider: () => null, selection: () => ({}),
    role: () => ({model_api:"/api/role/models", perception_native_api:"/api/role/perception-native"}),
    bridgeNow: () => null, bridgeFor: () => Promise.reject(new Error("no bridge")),
    request: (method, route) => String(route).endsWith("/runtime")
      ? Promise.resolve(payload) : Promise.resolve({tasks:[], providers:[]}),
  };
  const window = {Date:FixedDate,document:{activeElement:null}, lucide:{createIcons() {}}, CompanionProduct:product,
    fetch: () => Promise.reject(new Error("offline")),
    /* vm 沙箱自带标准全局，但宿主专有对象要显式放进去；
       setInterval 返回一个空 handle 即可——测试用例不依赖秒针推进。 */
    AbortController, setInterval: () => 0, clearInterval: () => {}};
  window.window = window;
  vm.createContext(window);
  vm.runInContext(source, window);
  return {root, written, page:window.CompanionPerceptionOverviewPage};
}

async function settle() { await new Promise(resolve => setImmediate(resolve)); }
async function readClocks(runtime) {
  const hive = harness(runtime);
  hive.page.mount(hive.root);
  await settle();
  await settle();
  const values = {};
  for (const [key, node] of hive.written) values[key] = node.textContent;
  values.tagHidden = hive.written.get("tag").hidden;
  values.html = hive.root.innerHTML;
  hive.page.unmount();
  return values;
}

test("日期行采用服务端日历，不本地重算星期与农历", async () => {
  const clocks = await readClocks({...RUNTIME_BASE, calendar:CALENDAR_AVAILABLE});
  assert.match(clocks.date, /10 月 6 日/, "公历日期来自服务端 local_date");
  assert.match(clocks.date, /星期二/, "星期来自服务端 weekday");
  assert.match(clocks.date, /农历八月十六/, "农历来自服务端 lunar_date");
  assert.equal(clocks.zone, "Asia/Shanghai", "时区取服务端 calendar.timezone，而非浏览器");
  assert.equal(clocks.lunar, "", "服务端在档时不再补一个本地星期，避免同一语义说两次");
  assert.equal(clocks.tag, "国庆节", "节假日标签来自服务端 holiday.label");
  assert.equal(clocks.tagHidden, false);
});

test("服务端日历不可用时降级到本机，但不假装懂农历", async () => {
  const clocks = await readClocks({...RUNTIME_BASE, calendar:{status:"disabled"}});
  assert.ok(clocks.date.length > 0, "降级后仍要给出一个可读日期");
  assert.doesNotMatch(clocks.date, /农历/, "读不到农历就不能显示农历");
  assert.equal(clocks.tag, "", "读不到节假日就不能挂标签");
  assert.equal(clocks.tagHidden, true);
  assert.equal(clocks.lunar, "星期二", "降级档下沿用本机星期作为唯一可读的日期语义");
});

test("黄历与节气只在服务端真的产出时出现", async () => {
  const full = await readClocks({...RUNTIME_BASE, calendar:CALENDAR_AVAILABLE});
  assert.match(full.html, /宜 读书 · 忌 熬夜/, "almanac 开启时应显示宜忌");
  const noAlmanac = await readClocks({...RUNTIME_BASE,
    calendar:{...CALENDAR_AVAILABLE, almanac:{status:"disabled"}}});
  assert.doesNotMatch(noAlmanac.html, /宜 读书/, "黄历未开启就不该出现宜忌");
  // 工作日不算节假日，不为了填充而挂标签。
  const workday = await readClocks({...RUNTIME_BASE,
    calendar:{...CALENDAR_AVAILABLE, holiday:{status:"available", kind:"workday", label:"工作日"}}});
  assert.equal(workday.tag, "", "今天是工作日就不挂节假日标签");
  assert.equal(workday.tagHidden, true);
});

test("日历链路缺失整包降级，不会让某一 cross 项凭空出现", async () => {
  // /runtime 失败时不保留任何日历读数。
  const broken = harness(undefined);
  broken.page.mount(broken.root);
  await settle();
  await settle();
  assert.doesNotMatch(broken.root.innerHTML, /农历|宜 读书|perception-channel-env-calendar|perception-wx-calendar/,
    "拿不到服务端日历时不凭空加一条历法通道");
  broken.page.unmount();
});
