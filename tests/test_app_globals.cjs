/* 管理页签：每一个都要能真的渲染出来。
 *
 * 用户报「主动与联系页失效」。根因是那一行：
 *
 *   ...${configEditors(...)}${renderPreferences()}
 *
 * `renderPreferences` 在整个仓库里没有任何定义——它是「preferences 页签并入
 * 主动与联系页」那次合并留下的调用，函数本体没跟过来。后果不是「某一块不显示」，
 * 而是 renderContactPage() 执行到那一步抛 ReferenceError，**整页渲染中断**，
 * 本该正常的部分（联系节奏、繁忙顺延）也一起没了。
 *
 * 这类断点的特点是：`node --check` 能过（语法合法），静态看文件「没毛病」，
 * 只有真跑到那一行才炸。所以这里**真跑**：把 app.js 与它的依赖脚本装进一个
 * 最小 DOM，然后把每个管理页签渲染一遍，谁抛错就指名道姓。
 *
 * 用 node --test 运行。
 */
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const DIR = path.join(__dirname, "..", "pages", "陪伴小屋");
const APP = fs.readFileSync(path.join(DIR, "app.js"), "utf8");
const INDEX = fs.readFileSync(path.join(DIR, "index.html"), "utf8");

/* 一个够用的 DOM 替身：app.js 加载期只做少量 DOM 触碰，渲染函数基本只拼字符串。
   缺哪个接口补哪个，不引 jsdom。 */
function fakeElement() {
  return {
    classList: {add() {}, remove() {}, toggle() {}, contains: () => false},
    dataset: {}, style: {}, children: [], childNodes: [],
    innerHTML: "", textContent: "", value: "",
    addEventListener() {}, removeEventListener() {},
    appendChild() {}, removeChild() {}, insertBefore() {}, replaceChildren() {},
    setAttribute() {}, removeAttribute() {}, getAttribute: () => null,
    hasAttribute: () => false, closest: () => null, contains: () => false,
    querySelector: () => null, querySelectorAll: () => [],
    getBoundingClientRect: () => ({width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0}),
    focus() {}, blur() {}, click() {}, remove() {}, before() {}, after() {},
    isConnected: true, parentElement: null, firstElementChild: null,
  };
}

/* index.html 按顺序加载的经典脚本（无 type="module"），它们共享同一个全局生效范围。
   assets/ 里的第三方与编译产物不装：本文件不验它们。 */
function pageScripts() {
  return [...INDEX.matchAll(/<script(?![^>]*\btype=)[^>]*\ssrc="([^"?]+)[^"]*"[^>]*>/g)]
    .map(m => m[1])
    .filter(name => !name.startsWith("assets/"));
}

test("决策页模块由宿主页在 app.js 前加载", () => {
  const context = loadApp();
  const scripts = pageScripts();
  assert.ok(scripts.indexOf("decision-page.js") >= 0,
    "index.html 未加载 decision-page.js，决策页会停留在初始占位");
  assert.ok(scripts.indexOf("decision-page.js") < scripts.indexOf("app.js"),
    "decision-page.js 必须在 app.js 启动前加载");
  assert.strictEqual(typeof context.window.CompanionDecisionPage?.mount, "function",
    "宿主页脚本顺序未创建决策页挂载模块");
});

function loadApp() {
  const scripts = pageScripts();
  assert.ok(scripts.includes("app.js"), "index.html 里没加载 app.js？");

  const document = {
    readyState: "complete", hidden: false,
    documentElement: fakeElement(), head: fakeElement(), body: fakeElement(),
    title: "",
    addEventListener() {}, removeEventListener() {},
    querySelector: () => null, querySelectorAll: () => [], getElementById: () => null,
    createElement: () => fakeElement(), createTextNode: () => fakeElement(),
    createComment: () => fakeElement(), createDocumentFragment: () => fakeElement(),
  };
  const navigator = {language: "zh-CN", userAgent: "node"};
  const storage = {getItem: () => null, setItem() {}, removeItem() {}};
  const window = {
    document, console, navigator,
    localStorage: storage, sessionStorage: storage,
    addEventListener() {}, removeEventListener() {},
    matchMedia: () => ({matches: false, addEventListener() {}, removeEventListener() {}}),
    location: {hash: "", href: "http://localhost/", search: "", pathname: "/"},
    history: {replaceState() {}, pushState() {}},
    innerWidth: 1440, innerHeight: 900, devicePixelRatio: 1, scrollY: 0,
    getComputedStyle: () => ({getPropertyValue: () => ""}),
    requestAnimationFrame: cb => {cb(0); return 0;}, cancelAnimationFrame() {},
    setTimeout, clearTimeout, setInterval, clearInterval, queueMicrotask,
    structuredClone, getSelection: () => null, scrollTo() {},
  };
  const context = vm.createContext({
    window, document, console, navigator, localStorage: storage, sessionStorage: storage,
    location: window.location, history: window.history,
    setTimeout, clearTimeout, setInterval, clearInterval, queueMicrotask, structuredClone,
    requestAnimationFrame: window.requestAnimationFrame, cancelAnimationFrame() {},
    matchMedia: window.matchMedia, getComputedStyle: window.getComputedStyle,
    Intl, URL, URLSearchParams, TextEncoder, TextDecoder,
  });

  for (const name of scripts) {
    const source = fs.readFileSync(path.join(DIR, name), "utf8");
    try {
      vm.runInContext(source, context, {filename: name});
    } catch (error) {
      /* 加载期因缺少宿主 API 而失败不算本文件要抓的缺陷；
         但 ReferenceError（用了不存在的标识符）要抛出来——那正是本次的缺陷类型。 */
      if (error instanceof ReferenceError && /is not defined$/.test(error.message)) {
        throw new Error(`${name} 加载时引用了未定义的标识符：${error.message}`);
      }
    }
  }
  return context;
}

test("每个管理页签都能渲染出非空内容", () => {
  const context = loadApp();
  assert.strictEqual(typeof context.renderManage, "function",
    "app.js 里找不到 renderManage（管理页的分发入口）");

  /* 页签名取自 manageTabs 的定义本体。必须**限定在这个数组内**取：
     directory / stageBar 等数组的元素形状相同，全局扫会把家具名
     当成页签名传进分发表，报一堆假的 TypeError。 */
  const block = APP.match(/const manageTabs=\[([\s\S]*?)\n\];/);
  assert.ok(block, "找不到 manageTabs 的定义");
  const tabs = [...block[1].matchAll(/\['([a-z_]+)','[a-z-]+','([^']+)'\]/g)].map(m => [m[1], m[2]]);
  assert.ok(tabs.length >= 12, `只解析出 ${tabs.length} 个页签，manageTabs 形状变了？`);

  const failures = [];
  for (const [id, label] of tabs) {
    try {
      const markup = vm.runInContext(
        `(function(){manageTab=${JSON.stringify(id)};return renderManage();})()`, context);
      if (typeof markup !== "string" || !markup.trim()) {
        failures.push(`「${label}」(${id}) 渲染成空串`);
      }
    } catch (error) {
      failures.push(`「${label}」(${id}) 渲染抛错 → ${error.constructor.name}: ${error.message}`);
    }
  }
  assert.deepStrictEqual(failures, [],
    "这些管理页签渲染失败。报 ReferenceError 就说明调用了某个未定义的函数——\n"
    + "那会让**整页**渲染中断，不只是那一块：\n" + failures.join("\n"));
});

test("顶层函数没有重复定义", () => {
  /* 同生效范围重复 function 合法，只有最后一个生效，node --check 不报错。
     改前必须扫一遍，否则你改的那一个可能根本没生效。
     只看项目自有脚本——assets/ 是第三方与编译产物，压缩变量名会刷屏。 */
  const scripts = pageScripts().filter(name => fs.existsSync(path.join(DIR, name)));
  const duplicates = [];
  for (const name of scripts) {
    const source = fs.readFileSync(path.join(DIR, name), "utf8");
    const candidates = [];
    const probeSource = source.replace(
      /^([ \t]*(?:async[ \t]+)?function[ \t]+)([A-Za-z_$][\w$]*)([ \t]*\()/gm,
      (match, prefix, fn, parameters, offset) => {
        const probe = `__companionFunctionProbe${candidates.length}`;
        candidates.push({probe, fn, line: source.slice(0, offset).split("\n").length});
        return prefix + probe + parameters;
      });
    /* 全局函数在脚本执行前已被 V8 实例化。入口立即抛出，避免执行页面代码；
       只有真正位于顶层的探针会出现在全局对象上，嵌套的同名助手不会误报。 */
    const globals = vm.createContext({});
    const probe = new vm.Script("throw null;\n" + probeSource, {filename: name});
    try { probe.runInContext(globals); } catch (error) { if (error !== null) throw error; }
    const seen = new Map();
    for (const {probe, fn, line} of candidates) {
      if (typeof globals[probe] !== "function") continue;
      if (seen.has(fn)) duplicates.push(`${name}: ${fn}() 第 ${seen.get(fn)} 行与第 ${line} 行各定义一次`);
      else seen.set(fn, line);
    }
  }
  assert.deepStrictEqual(duplicates, [],
    `重复的顶层函数只有最后一个生效，不报错：\n${duplicates.join("\n")}`);
});
