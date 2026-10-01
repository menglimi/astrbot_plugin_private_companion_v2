/* 主题注册表 —— 唯一来源。
 *
 * 背景：主题定义原先散在十处——product-page.js 的注册表、index.html 的引导脚本、
 * embedded-bridge.js、app.js 的色卡数组、tokens.css、styles.css，以及四个子工作区
 * 各自的 style.css。加一套主题要同步改十处，漏改一处不会报错，只会让那个主题在某
 * 个界面上静默失效（子工作区就已经飘了：host 声明四套，其余三个只声明三套）。
 *
 * 本文件只放「有哪些主题、叫什么、对应什么光照」。
 * 色值不放这里——色值属于 tokens.css，那是唯一色源。
 *
 * 两种用法：
 *   页面（ESM 之外）：<script defer src="theme.js"></script> 后用 window.CompanionTheme
 *   引导脚本（内联、必须最早执行）：用下面的 bootstrap 片段，不要引入本文件，
 *     因为引导必须在样式生效前跑完，多一个网络往返就会闪一下默认主题。
 */
"use strict";
window.CompanionTheme = (() => {
  /* 六套，按明暗分两组。每套对应小屋的一个时段或陈设风格。 */
  const THEMES = [
    {id:"courtyard", label:"庭院", note:"窗格纹理与轻圆角，清爽通透",       light:"day",   mode:"light"},
    {id:"dawn",      label:"晨雾", note:"纸页细线与衬线标题，安静柔和",     light:"dawn",  mode:"light"},
    {id:"dusk",      label:"暮色", note:"陶土斜纹与收紧边角，温暖利落",     light:"dusk",  mode:"light"},
    {id:"night",     label:"夜读", note:"墨色书页与阅读排版，低照度舒适",   light:"night", mode:"dark"},
    {id:"walnut",    label:"深林", note:"木作竖理与紧凑边界，沉稳耐看",     light:"dusk",  mode:"dark"},
    {id:"contrast",  label:"高对比", note:"纯色背景、实线边界与强焦点提示", light:"day", mode:"light"},
  ];
  const IDS = THEMES.map(item => item.id);
  const FALLBACK = "courtyard";
  const LIGHT = Object.fromEntries(THEMES.map(item => [item.id, item.light]));

  /* 一个光照可能对应多套主题（黄昏同时是暮色与深林）。
     此时「跟随时段」保留用户当前选择，不擅自换掉。 */
  function themeForLight(light, current) {
    const candidates = THEMES.filter(item => item.light === light).map(item => item.id);
    if (candidates.includes(current)) return null;
    return candidates.length === 1 ? candidates[0] : null;
  }

  /* 未知值一律回落到默认，不让一个坏值把整站令牌变成空。 */
  function normalize(value) {
    return IDS.includes(value) ? value : FALLBACK;
  }

  /* 兼容旧主题名：薄雾 mist / 林间 grove / 珊瑚 coral 三套已并入新色板。
     旧名字若留在 localStorage 里，直接丢弃会让人「主题突然变了」，
     所以映射到最接近的新主题。映射一次即可，不回写旧值。 */
  const LEGACY = {mist:"dawn", grove:"courtyard", coral:"dusk", light:"dawn", dark:"night"};
  function migrate(value) {
    return LEGACY[value] || normalize(value);
  }

  return {THEMES, IDS, FALLBACK, LIGHT, themeForLight, normalize, migrate,
    isDark:id => THEMES.find(item => item.id === id)?.mode === "dark",
    label:id => THEMES.find(item => item.id === id)?.label || id};
})();
