/* 页面桥的 endpoint 口径：**插件相对路径**。
 *
 * 用户截图：决策页的「统一记忆策略」一打开就是两个红框——「未找到该路由」和
 * 「Plugin bridge endpoint is invalid.」。桥是通的（请求发出去了、拿到确认），
 * 错在路径。
 *
 * 根因：`product-page.js` 的 `relative()` 当初写成「只去掉前导斜杠、保留插件
 * 目录名」，于是送出 `astrbot_plugin_private_companion/page/targets`。
 * 宿主拿插件名与 endpoint 拼真实路由，带上目录名就是拼两次：
 *
 *   /astrbot_plugin_private_companion/astrbot_plugin_private_companion/page/targets
 *
 * → 未找到该路由。那段注释还断言「两种宿主都成立」，是没验证过的猜测；
 * 而五个工作区页（memory / state / perception-native / reply / models）用的
 * 一直是切掉目录名的写法，两边矛盾。
 *
 * 反证有三处，这套测试把它们变成常驻断言：
 *   - tools/check_host_management_page.cjs:29 跑**真实 SDK**（宿主的
 *     plugin_page_bridge.js），断言 endpoint 不以 "/" 开头，并按裸名分发；
 *   - tools/check_product_page.cjs 的合成 SDK 按 `'/'+HOST+'/'+relative`
 *     还原绝对地址，RPC 只认裸名；
 *   - docs/CORE_HOST_MANAGEMENT_PAGE_20260924.md：「所有请求使用插件相对路径」。
 *
 * 用 node --test 运行。
 */
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const PAGE = name => fs.readFileSync(
  path.join(__dirname, "..", "pages", "陪伴小屋", name), "utf8");
const TOOL = name => fs.readFileSync(
  path.join(__dirname, "..", "tools", name), "utf8");

const HOST = "astrbot_plugin_private_companion";

/* 只跑引导路径，拿到 CompanionProduct，用它来问 endpoint 口径。 */
function product() {
  const window = {
    addEventListener() {}, removeEventListener() {},
    matchMedia: () => ({matches: false, addEventListener() {}}),
    location: {hash: "", href: "http://localhost/#life"},
    history: {replaceState() {}}, innerWidth: 1440, innerHeight: 900,
    requestAnimationFrame: cb => { cb(0); return 0; }, cancelAnimationFrame() {},
  };
  const document = {
    readyState: "interactive", documentElement: {dataset: {}},
    head: {appendChild() {}}, body: {classList: {add() {}, remove() {}}},
    querySelector: () => null, querySelectorAll: () => [],
    createElement: () => ({addEventListener() {}, setAttribute() {}}),
    addEventListener() {},
  };
  vm.runInNewContext(PAGE("product-page.js"),
    {window, document, navigator: {language: "zh-CN"}, setTimeout, clearTimeout,
     Promise, Object, JSON, Array, String, Number, Boolean, Math, Date, Error, console,
     matchMedia: () => ({matches: false}),
     localStorage: {getItem: () => null, setItem() {}, removeItem() {}}});
  return window.CompanionProduct;
}

test("endpoint 不带插件目录名", () => {
  /* 唯一正确的形状。带上目录名就是拼两次，宿主 404。 */
  const relative = product().relative;
  assert.strictEqual(relative("/" + HOST + "/page/targets"), "page/targets");
  assert.strictEqual(relative("/" + HOST + "/host/targets/a/roles/role-a/state"),
    "host/targets/a/roles/role-a/state");
  assert.strictEqual(relative("/" + HOST + "/config"), "config");
});

test("endpoint 不带前导斜杠", () => {
  /* 夹具里的真实 SDK 断言就是这一条：
     assertion "bridge endpoints remain plugin-relative"。 */
  const relative = product().relative;
  const value = relative("/" + HOST + "/semantic");
  assert.doesNotMatch(value, /^\//, `endpoint 不该带前导斜杠，实际 ${value}`);
  assert.strictEqual(value.split("/").length, 1,
    `单段路由切完就只剩一段，实际 ${value}`);
});

test("endpoint 拒绝越界、查询串与外来前缀", () => {
  const relative = product().relative;
  for (const bad of ["/" + HOST + "/../secrets",
                     "/" + HOST + "/a/../../b",
                     "/" + HOST + "/x?y=1",
                     "/" + HOST + "/x#frag",
                     "/other_plugin/state",
                     "/" + HOST + "/"]) {
    assert.throws(() => relative(bad), undefined,
      `${bad} 应当被拒绝，而不是原样发给桥`);
  }
});

test("各工作区页与主页面用同一种口径", () => {
  /* 插件桥只接受插件相对路径；所有页面都必须去掉插件目录前缀。 */
  const pages = ["product-page.js", "memory-page.js", "state-page.js",
    "perception-native-page.js", "reply-page.js", "models-page.js"];
  for (const name of pages) {
    const code = PAGE(name).split("\n")
      .filter(line => !/^\s*(\/\*|\*|\/\/)/.test(line)).join("\n");
    assert.match(code, /slice\(\s*(prefix|PREFIX)\s*\.\s*length\s*\)/,
      `${name} 没有把插件目录名切掉：endpoint 会带上目录名，宿主拼两次后 404`);
    assert.doesNotMatch(code, /replace\(\s*\/\^\\\/\+\/[^)]*\)\s*;/,
      `${name} 用的是「只去前导斜杠」，会保留插件目录名`);
  }
});

test("真实 SDK 夹具断言 endpoint 是插件相对路径", () => {
  /* 这条守的是**证据**本身：check_host_management_page.cjs 跑的是宿主的
     plugin_page_bridge.js，它的断言就是口径的定义。哪天有人把这个断言删了，
     说明依据没了，得重新找证据，而不是继续照抄注释。 */
  const tool = TOOL("check_host_management_page.cjs");
  assert.ok(tool.includes('assert(!endpoint.startsWith("/")'),
    "宿主 SDK 夹具不再拒绝绝对 endpoint——插件相对路径的口径证据丢了");
  assert.ok(tool.includes('endpoint.startsWith("/")'),
    "宿主 SDK 夹具没有检查 endpoint 是否以斜杠开头");
});
