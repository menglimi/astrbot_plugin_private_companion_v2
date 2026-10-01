/* 入场：普通首页从中央近景拉远；状态页随拉远从底部搭建；最后浮现 UI。
 *
 * 栅格与小屋操作面始终保留最终布局，只有 voxel-room 渲染层暂时固定到视口。
 * 渲染层使用与最终内容框同宽高比的 cover 尺寸，全程只写等比 transform。
 * 相机和容器共用同一条进度，终点同步写入 1，再撤掉固定定位并同步 resize。
 * UI 从实际落位事件起步，避免页面加载、rAF 与 CSS 时钟不同步时提前出现。
 * 跳过、减少动效或失败都交回正常页面；跳过时先同步写终态再允许场景销毁。
 */
"use strict";
window.CompanionEntrance = (() => {
  const REDUCED = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    || ["low", "off"].includes(document.documentElement?.dataset?.motion);

  /* UI 由实际落位事件启动；留一小段呼吸，再按视觉层级依次浮现。 */
  const UI_REVEAL = {pause: 90, duration: 620, stagger: 240};
  /* 中央近景同步写入。prime 留出启动幕消退的时间，首帧近景可见后再拉远。 */
  const TIMING = {
    prime: 220,
    pullBack: 1600,
    settle: UI_REVEAL.pause + UI_REVEAL.duration + UI_REVEAL.stagger + 60,
  };
  const BUILD_DURATION = 2600;
  const TOTAL = Object.values(TIMING).reduce((sum, value) => sum + value, 0);
  /* 保留体素包默认 focus 的时长，供诊断和兼容调用参考。 */
  const FLIGHT = 1450;
  /* 预计 UI 起点供调试读取；呈现由 settle 事件启动，不依赖绝对时间。 */
  const UI_AT = TIMING.prime + TIMING.pullBack + UI_REVEAL.pause;

  /* 单段曲线，起手与收尾速度均为零；不拼接、不回弹。 */
  const PULL = {
    curve: [0.45, 0, 0.2, 1],
  };

  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  /* 可中断的等待：跳过时立即 resolve，不用等完整段时长。 */
  function waitOrSkip(ms, signal) {
    if (signal.skipped) return Promise.resolve();
    return new Promise(resolve => {
      const timer = setTimeout(finish, ms);
      function finish() {
        clearTimeout(timer);
        signal.removeEventListener("skip", finish);
        resolve();
      }
      signal.addEventListener("skip", finish);
    });
  }

  /* 把首屏闸门交给浏览器先画一帧，再开始拉远。
     若在 resolve ready 的同一个任务里调用 overview，首个可见帧仍可能已经
     进入拉远段；等待一个 rAF 能确保用户先看到稳定的中央近景。 */
  function frameOrSkip(signal) {
    if (signal.skipped) return Promise.resolve();
    return new Promise(resolve => {
      let frame = requestAnimationFrame(finish);
      function finish() {
        cancelAnimationFrame(frame);
        signal.removeEventListener("skip", finish);
        resolve();
      }
      signal.addEventListener("skip", finish);
    });
  }

  /* 三次贝塞尔求值：给定四个控制点参数与 x，回一个 y。
     牛顿迭代五次足够收敛到亚像素精度（误差 < 1e-6），
     再不行就退化成线性近似——入场动画掉几帧没人看得出来，
     但求值卡住是整段黑屏。 */
  function bezierAt(control, t) {
    const [x1, y1, x2, y2] = control;
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const sample = u => ((ax * u + bx) * u + cx) * u;
    const slope = u => (3 * ax * u + 2 * bx) * u + cx;
    let u = t;
    for (let step = 0; step < 5; step += 1) {
      const dx = sample(u) - t;
      if (Math.abs(dx) < 1e-6) break;
      const d = slope(u);
      if (Math.abs(d) < 1e-6) break;
      u -= dx / d;
    }
    if (u < 0 || u > 1) u = t;
    return ((ay * u + by) * u + cy) * u;
  }

  /* 段内取缓动值。t 是 0..1 的整段进度。用于容器 transform 与镜头飞行。 */
  function pullCurve(t) {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    return bezierAt(PULL.curve, t);
  }

  /* === 遥测 ===
     入场是「看不见的过程」——出问题时只能看到最终画面不对，看不出是哪一拍、
     哪个调用出了问题。所以把每次触碰控制器的动作与每帧相机状态记下来，
     出问题时可以直接读这段记录，而不是靠猜。

     默认关闭，通过 options.debug=true 或 window.CompanionEntrance.debug=true 打开。
     记录上限 600 条，避免长序列把内存吃满。 */
  const LOG_LIMIT = 600;
  function createLog(enabled) {
    const entries = [];
    return {
      enabled,
      push(kind, detail) {
        if (!this.enabled || entries.length >= LOG_LIMIT) return;
        entries.push({at: Math.round(performance.now()), kind, ...detail});
      },
      all() { return entries.slice(); },
      clear() { entries.length = 0; },
      /* 摘要：只抽相机位姿，便于回答「镜头到底有没有停下」。 */
      cameraTrack() {
        return entries.filter(item => item.kind === "frame")
          .map(item => ({at: item.at, pos: item.pos, fov: item.fov, target: item.target}));
      },
    };
  }
  /* 是否记录遥测。options.debug 优先，其次全局开关。 */
  function debugEnabled(options) {
    return options.debug === true || window.CompanionEntrance?.debug === true;
  }

  /* === 家具显隐 ===
     见坑一：隐藏必须写 stored:true，而且要在原条目上改，
     把模型、样式、surface 这些字段一并带上——Ir 会对每个条目跑 _i()，
     缺字段会被回落成默认外观。 */
  function storedItem(item) {
    return {...item, stored: true};
  }
  /* 只让 subset 里的家具显形，其余全部收进收藏。 */
  function revealLayout(base, subset) {
    const keep = new Set(subset.map(entry => entry.id));
    const items = {};
    for (const [id, item] of Object.entries(base.items || {})) {
      items[id] = keep.has(id) ? {...item} : storedItem(item);
    }
    return {...base, items};
  }

  /* 按世界坐标高度把家具分三批：低处先落地，高处最后。
     高度取条目的 y（布局里是格子坐标），缺值按 0 处理——
     没有坐标的多半是地毯一类的贴地件，先出现不突兀。 */
  function tiersFor(controller) {
    const layout = controller.getLayout?.();
    if (!layout?.items) return null;
    const withHeight = Object.entries(layout.items).filter(([, item]) => item?.stored !== true).map(([id, item]) => {
      const y = Number(item?.y);
      return {id, y: Number.isFinite(y) ? y : 0};
    });
    if (!Object.keys(layout.items).length) return null;
    withHeight.sort((a, b) => a.y - b.y);
    const third = Math.ceil(withHeight.length / 3) || 1;
    return {
      full: layout,
      low: withHeight.slice(0, third),
      mid: withHeight.slice(third, third * 2),
      high: withHeight.slice(third * 2),
    };
  }

  /* 把一批家具加入「已显形」集合。 */
  function addAll(set, entries) {
    for (const entry of entries || []) set.add(entry.id);
  }

  /* 飞入近景的目标机位。两个条件必须同时满足，否则 focus 会静默回落到全景
     （见坑四），那一段飞行会变成全景跳变：

       1. 这件家具有固定机位。包里的机位表只有七个：
          calendar / desk / shelf / wardrobe / bed / radio / garden。
          地毯、凳、挂画没有机位——按布局高度排出来的「低处那批」里
          恰恰有 rug 和 stool，所以不能直接取低处第一个。
       2. 这件家具此刻已经显形。清单顺序即偏好顺序，靠前的观感更稳。 */
  const STATIONS = ["wardrobe", "desk", "calendar", "radio", "shelf", "bed", "garden"];
  /* 只接受一个「已显形家具 id」集合。刻意不用 instanceof Set 判断——
     跨 realm（例如测试里的 vm 上下文）拿到的 Set 原型不同，instanceof 会
     静默为 false，集合被当成空，这里就永远返回 null 了。 */
  function flyInTarget(visibleIds) {
    const seen = (visibleIds && typeof visibleIds.has === "function")
      ? visibleIds : new Set(Array.isArray(visibleIds) ? visibleIds : []);
    return STATIONS.find(id => seen.has(id)) || null;
  }

  /* 波纹：一圈从中心摊开的光晕。纯 DOM + CSS，不动 3D 渲染。
     挂在 host 上，它的中心由 --entrance-ripple-x/y 决定——
     全屏阶段小屋是 position:fixed 铺满视口，所以波纹也得按视口居中。 */
  function rippleLayer(host) {
    const layer = document.createElement("div");
    layer.className = "entrance-ripple";
    layer.setAttribute("aria-hidden", "true");
    for (let index = 0; index < 3; index += 1) {
      const ring = document.createElement("span");
      ring.style.setProperty("--delay", `${index * 160}ms`);
      layer.appendChild(ring);
    }
    host.appendChild(layer);
    return layer;
  }

  /* 与静息内容框同宽高比、盖住视口的 cover 框。
     原点是底边中点 (W/2,H)。s=静息宽/cover宽；
     Tx=静息中心X-W/2，Ty=静息底边-H，终点便与内容框精确重合。
     测量对象不包含标题、工具按钮或家具条，避免将周边 UI 算进缩放比例。 */
  function stageGeometry(stage, viewport) {
    const rect = stage.getBoundingClientRect();
    const width = viewport.width;
    const height = viewport.height;
    if (!(rect.width > 0) || !(rect.height > 0) || !(width > 0) || !(height > 0)) return null;
    /* 与静息同比例、盖住视口的框。 */
    const ratio = rect.width / rect.height;
    const coverWidth = Math.max(width, height * ratio);
    const coverHeight = coverWidth / ratio;
    return {
      scale: rect.width / coverWidth,
      cover: {width: coverWidth, height: coverHeight},
      rest: {width: rect.width, height: rect.height, left: rect.left, top: rect.top},
      viewport: {width, height},
      translateX: rect.left + rect.width / 2 - width / 2,
      translateY: rect.top + rect.height - height,
    };
  }

  /* 把几何写进 CSS 变量。progress=0 → cover 满屏；progress=1 → 静息。
     调用方给什么曲线，动画就是什么曲线（见 pullCurve）。
     只写变换，不写尺寸——尺寸整段不变，见 coverVars。 */
  function applyGeometry(stage, geometry, progress) {
    const scale = 1 + (geometry.scale - 1) * progress;
    stage.style.setProperty("--entrance-scale", scale.toFixed(8));
    stage.style.setProperty("--entrance-tx", `${(geometry.translateX * progress).toFixed(5)}px`);
    stage.style.setProperty("--entrance-ty", `${(geometry.translateY * progress).toFixed(5)}px`);
    stage.style.setProperty("--entrance-radius", `${((geometry.radius || 0) * progress / scale).toFixed(5)}px`);
  }

  /* cover 框的尺寸。整段入场里它是个定值（只跟视口与静息比例有关），
     所以只在开始与窗口尺寸变化时写一次——每帧重写会让浏览器白白
     失效一次样式，而尺寸本身没变。 */
  function coverVars(stage, geometry) {
    if (!stage || !geometry) return;
    stage.style.setProperty("--entrance-w", `${geometry.cover.width.toFixed(6)}px`);
    stage.style.setProperty("--entrance-h", `${geometry.cover.height.toFixed(6)}px`);
  }

  /* 清除入场期间写在容器上的行内覆盖，交回栅格。
     这里漏一个变量，小屋就会被永久钉在全屏尺寸、
     或者留一条裁切线——所以是「逐个 removeProperty」而不是整串清空。
     position/width/height 也在内：geometry 不可用时写过它们（见 run 里
     的分支），漏了会让容器留在 static 而 CSS 期望它回到栅格。 */
  function releaseStage(stage) {
    if (!stage) return;
    for (const name of [
      "--entrance-scale", "--entrance-tx", "--entrance-ty",
      "--entrance-w", "--entrance-h", "--entrance-wipe", "--entrance-radius",
      "clip-path", "-webkit-clip-path",
      "position", "width", "height",
    ]) stage.style.removeProperty(name);
  }

  /* 返回值刻意不是 promise，而是立即给出的句柄：
       {skip, done}
     skip() 必须在序列还在跑的时候就能调用——那正是它存在的理由。
     早先的写法把整个序列包在一个 async 里返回 promise，调用方要 await 完
     才拿得到 skip，等于永远只能「跳过一个已经结束的序列」。 */
  function run(controller, host, options = {}) {
    const {onPhase = () => {}, stage: suppliedStage = null, viewport = null, geometry: suppliedGeometry = null} = options;
    const buildFromBottom = options.buildFromBottom === true;
    const stage = buildFromBottom ? null : suppliedStage;
    const log = createLog(debugEnabled(options));
    const signal = new EventTarget();
    signal.skipped = false;
    let finished = false;
    /* 跳过时同步写入终态。调用方随后可能立即销毁控制器，不能在 await 后归位。 */
    const skip = () => {
      if (signal.skipped || finished) return;
      try {
        if (buildFromBottom) controller?.setConstructionProgress?.(1);
      } catch (error) {
        log.push("error", {message: "跳过时小屋无法完成搭建：" + String(error?.message || error)});
      }
      try {
        controller?.setEntranceProgress?.(1);
      } catch (error) {
        log.push("error", {message: "跳过时场景已不可用：" + String(error?.message || error)});
      }
      signal.skipped = true;
      signal.dispatchEvent(new Event("skip"));
    };
    let readyResolved = false;
    let resolveReady;
    const ready = new Promise(resolve => { resolveReady = resolve; });
    const markReady = () => {
      if (readyResolved) return;
      readyResolved = true;
      resolveReady(!signal.skipped);
    };
    const finishStage = () => {
      try { onPhase("done"); }
      catch (error) {
        log.push("error", {message: "页面收尾回调失败：" + String(error?.message || error)});
        console.warn("入场页面回调失败，已清理动画覆盖：", error);
      } finally { releaseStage(stage); }
    };

    /* 座舱降级：减少动效偏好、控制器缺失时直接呈现终态。
       返回的 done 仍会 resolve，页面照常显示。
       全屏那一拍也一并跳过——否则减弱动效的用户会看到一次满屏闪现。 */
    if (!controller || options.reducedMotion || REDUCED()) {
      log.push("degrade", {reason: !controller ? "no-controller" : "reduced-motion"});
      finishStage();
      markReady();
      return {skipped: true, skip: () => {}, ready: Promise.resolve(false), done: Promise.resolve(true), log};
    }

    const tiers = tiersFor(controller);
    log.push("start", {
      furniture: tiers ? Object.keys(tiers.full.items || {}).length : 0,
      thresholds: tiers ? [tiers.low.length, tiers.mid.length, tiers.high.length] : null,
      fullscreen: !!stage,
    });

    /* 视口矩形。全屏阶段要用它算缩放与波纹中心；
       窗口尺寸变化时（拖窗口、转屏）重算一次，
       否则缩放比例会按旧视口算，容器落不到正确大小。 */
    const bounds = () => ({
      width: viewport?.width || window.innerWidth || 0,
      height: viewport?.height || window.innerHeight || 0,
    });
    /* 使用固定定位之前测出的内容框，不能把 full-screen 层再次当作静息框。 */
    let geometry = stage ? (suppliedGeometry || stageGeometry(stage, bounds())) : null;
    let geometryTarget = geometry, geometryTransition = null, geometryRaw = 0;
    /* 宿主目录、对象选择条或字体加载也会移动落点，不能只监听窗口 resize。
       在现有拉远时间轴内平滑重定向；当前位置保持连续，终点仍是实际内容框。 */
    function refreshGeometry(raw) {
      if (!stage || !geometry) return;
      const rest = options.measureRest?.() || geometryTarget.rest;
      const next = stageGeometry({getBoundingClientRect: () => rest}, bounds());
      if (!next) return;
      next.radius = suppliedGeometry?.radius || 0;
      const blend = transition => {
        const amount = raw >= 1 ? 1 : pullCurve((raw-transition.raw)/(1-transition.raw));
        const mix = (a,b) => a+(b-a)*amount;
        return {...transition.to, scale:mix(transition.from.scale,transition.to.scale),
          translateX:mix(transition.from.translateX,transition.to.translateX),
          translateY:mix(transition.from.translateY,transition.to.translateY),
          cover:{width:mix(transition.from.cover.width,transition.to.cover.width),
            height:mix(transition.from.cover.height,transition.to.cover.height)}};
      };
      let current = geometryTransition ? blend(geometryTransition) : geometry;
      const moved = ["left","top","width","height"].some(key=>Math.abs(next.rest[key]-geometryTarget.rest[key])>.01)
        || next.viewport.width !== geometryTarget.viewport.width || next.viewport.height !== geometryTarget.viewport.height;
      if (moved) {
        geometryTarget = next;
        if (raw <= 0 || raw >= 1) {current=next;geometryTransition=null;}
        else {geometryTransition={from:current,to:next,raw};}
        log.push("stage", {reason:"layout", rest:[next.rest.left,next.rest.top,next.rest.width,next.rest.height]});
      }
      if (Math.abs(current.cover.width-geometry.cover.width)>.0001 || Math.abs(current.cover.height-geometry.cover.height)>.0001) coverVars(stage,current);
      geometry=current;
      geometryRaw=raw;
    }
    log.push("stage", geometry
      ? {scale: Math.round(geometry.scale * 1000) / 1000,
         rest: [Math.round(geometry.rest.width), Math.round(geometry.rest.height)]}
      : {scale: null});
    /* 量不出静息矩形时不要用「全屏」那一套：容器现在是 fixed，
       却没有任何 --entrance-* 变量，会以 100vw/100vh 且 scale(1) 呈现——
       落不回栅格。这里直接把 fixed 那一层脱掉，序列照常跑（只有 3D 动画），
       页面不会卡在全屏状态。 */
    if (stage && !geometry) {
      stage.style.position = "static";
      stage.style.width = "auto";
      stage.style.height = "auto";
      log.push("stage", {reason: "geometry-unavailable"});
    }
    /* 尺寸只写一次。 */
    coverVars(stage, geometry);

    const dom = {layer: null};

    /* 每帧采样相机。这是判断「镜头到底有没有停下」的唯一可靠依据——
       读代码只能看出「应该会停」，采样才能看出「实际停在哪个数」。 */
    let sampler = 0;
    const sample = () => {
      if (!log.enabled || finished) return;
      const state = controller.getState?.();
      if (state?.camera) {
        log.push("frame", {
          pos: state.camera.position.map(value => Math.round(value * 100) / 100),
          target: state.camera.target.map(value => Math.round(value * 100) / 100),
          fov: Math.round(state.camera.fov * 10) / 10,
          shot: state.shotIndex,
          moving: !!state.moving,
          tour: !!state.tourRunning,
        });
      }
      sampler = requestAnimationFrame(sample);
    };
    sampler = requestAnimationFrame(sample);

    /* 显形的家具集合。用 Set 累加而不是按批次取切片：
       跳过或异常时都能一眼看出「此刻该看见几件」，重建布局也用同一份真值。 */
    const visible = new Set();
    const applyVisibility = () => {
      if (!tiers || signal.skipped || !controller) return;
      const subset = [...visible].map(id => ({id}));
      controller.setLayout(revealLayout(tiers.full, subset));
      log.push("layout", {count: subset.length});
    };

    /* 普通入场同步拉远容器与镜头；状态页则在固定画布内同步拉远与建造。 */
    function pullStage(duration) {
      const start = performance.now();
      let frame = 0;
      let last = -1;
      const tick = () => {
        if (signal.skipped || finished) return;
        const raw = Math.min(1, (performance.now() - start) / duration);
        /* 0 是中央近景和建造起点，1 是默认全景和完整小屋。 */
        refreshGeometry(raw);
        const progress = pullCurve(raw);
        if (buildFromBottom) controller.setConstructionProgress?.(progress);
        controller.setEntranceProgress?.(progress);
        if (stage && geometry) applyGeometry(stage, geometry, progress);
        /* 落点记一次就够，不然 90 帧会淹掉遥测。 */
        const bucket = Math.round(raw * 10);
        if (bucket !== last) { last = bucket; log.push("stage-frame", {progress: bucket / 10}); }
        if (raw < 1) frame = requestAnimationFrame(tick);
        else log.push("stage-frame", {progress: 1});
      };
      frame = requestAnimationFrame(tick);
      const stop = () => cancelAnimationFrame(frame);
      signal.addEventListener("skip", stop);
      return () => { stop(); signal.removeEventListener("skip", stop); };
    }

    /* 跳过入口：按键或点击。
       点击刻意挂在 document 而不是 host：全屏阶段小屋是 pointer-events:none
       （否则用户会在开场时拖动旋转场景），事件根本到不了 host，
       挂在 host 上等于跳过用不了。挂在 document 上还有一个好处——
       用户点左栏任何一处、或者点空白，都能跳过。 */
    const onKey = event => {
      if (["Escape", " ", "Enter"].includes(event.key)) skip();
    };
    document.addEventListener("keydown", onKey);
    const onPointer = () => skip();
    document.addEventListener("pointerdown", onPointer, {passive: true});

    /* 兜底：无论中途出了什么，都不许把页面卡在「小屋不可见」的状态。
       宁可直接定格，也不要一屏空白。 */
    const guard = setTimeout(() => { if (!finished) skip(); }, TOTAL + 1500);

    /* 窗口尺寸变化时重算几何。此刻正在跑的那一段会按新几何继续，
       因为 pullStage 每帧调用 applyGeometry 都会读一遍 geometry。
       尺寸变量也要跟着重写——cover 框的宽高依赖视口。 */
    const onResize = () => {
      if (!stage || finished) return;
      refreshGeometry(geometryRaw);
      log.push("stage", {reason: "resize", scale: geometry ? Math.round(geometry.scale * 1000) / 1000 : null});
    };
    window.addEventListener("resize", onResize);

    /* UI 的缓冲与时长交给 CSS；实际启动由页面的 settle 回调控制。 */
    const root = document?.documentElement;
    if (root?.style?.setProperty) {
      root.style.setProperty("--entrance-ui-at", `${UI_AT}ms`);
      root.style.setProperty("--entrance-ui-pause", `${UI_REVEAL.pause}ms`);
      root.style.setProperty("--entrance-ui-duration", `${UI_REVEAL.duration}ms`);
    }

    const done = (async () => {
      /* 每次触碰控制器前都要问一次「还能碰吗」。
         一个 await 之后状态就可能变了：app.js 在切页时先 skip() 再 dispose()，
         若只在循环开头检查，跳出后仍会走「定格」并调用 focus/setLight，
         那些调用就落在已销毁的场景上。
         家具归位是个例外——它必须在 finally 里无条件做，见下方说明。 */
      const live = () => !signal.skipped && controller;
      let stopPull = () => {};
      try {
        /* 拍 1：中央近景已在首屏闸门关闭期间同步完成。
           先让浏览器提交一帧中央近景，再开始拉远；否则 ready 与 focus
           在同一个任务里连续执行，用户可能直接看到中间状态。 */
        onPhase("prime");
        log.push("phase", {name: "prime"});
        if (live()) {
          if (buildFromBottom) controller.setConstructionProgress?.(0);
          if (tiers && !buildFromBottom) {
            visible.clear();
            addAll(visible, Object.keys(tiers.full.items || {}).map(id => ({id}))
              .filter(({id}) => tiers.full.items[id]?.stored !== true));
            applyVisibility();
          }
          if (stage && geometry) {
            coverVars(stage, geometry);
            applyGeometry(stage, geometry, 0);
          }
          controller.setLight?.(options.light || "day");
          controller.resize?.();
          if (controller.setEntranceProgress) controller.setEntranceProgress(0);
          else controller.focus?.("overview");
        }
        markReady();
        await frameOrSkip(signal);
        await waitOrSkip(TIMING.prime, signal);
        if (signal.skipped) return;

        /* 拍 2：普通入口同步缩回容器；状态页让建造面随镜头一起推进。 */
        onPhase("pull");
        log.push("phase", {name: "pull"});
        if (live()) {
          log.push("focus", {id: "overview", phase: "pull-back"});
          refreshGeometry(0);
          const duration = buildFromBottom ? BUILD_DURATION : TIMING.pullBack;
          stopPull = pullStage(duration);
          await waitOrSkip(duration, signal);
          /* 定时器与最后一个 rAF 不保证同一时刻完成，显式写入终点。 */
          if (live()) {
            stopPull();
            stopPull = () => {};
            if (buildFromBottom) controller.setConstructionProgress?.(1);
            controller.setEntranceProgress?.(1);
            refreshGeometry(1);
            if (stage && geometry) applyGeometry(stage, geometry, 1);
          }
        }
        if (signal.skipped) return;

        /* 拍 3：先撤掉固定定位，再清变量。页面在此处同步 resize 并启动 UI，
           避免固定层吃到变量缺省值，也避免下一帧还保留 cover 分辨率的画面。 */
        try { onPhase("settle"); } finally { releaseStage(stage); }
        log.push("phase", {name: "settle"});
        if (live()) {
          if (tiers && !buildFromBottom) controller.setLayout(tiers.full);
          if (options.light) controller.setLight?.(options.light);
          await waitOrSkip(TIMING.settle, signal);
        }
      } catch (error) {
        /* 任何一步失败都直接定格：小屋可见、可交互，只是没有动画。
           记录到控制台便于排查，但不弹给用户——它不影响使用。 */
        console.warn("入场序列中断，已直接定格：", error);
        log.push("error", {message: String(error?.message || error)});
        /* 场景还活着就把家具补齐——留一屋子残缺是用户直接看得见的。
           但归位本身也可能抛（控制器已销毁），所以单独包一层，
           不能让它把异常带出 finally、导致 done 不 resolve。 */
        try {
          if (buildFromBottom) controller.setConstructionProgress?.(1);
          if (tiers && !buildFromBottom) controller.setLayout(tiers.full);
          controller.focus?.("overview");
        } catch (nested) {
          log.push("error", {message: "定格时场景已不可用：" + String(nested?.message || nested)});
          console.warn("定格时场景已不可用，跳过家具归位：", nested);
        }
      } finally {
        markReady();
        finished = true;
        stopPull();
        cancelAnimationFrame(sampler);
        clearTimeout(guard);
        document.removeEventListener("keydown", onKey);
        window.removeEventListener("resize", onResize);
        document.removeEventListener("pointerdown", onPointer);
        dom.layer?.remove();
        /* 收尾时补最后一次采样，把最终位姿记下来。 */
        const final = controller.getState?.();
        if (final?.camera) {
          log.push("final", {
            pos: final.camera.position.map(value => Math.round(value * 100) / 100),
            fov: Math.round(final.camera.fov * 10) / 10,
            moving: !!final.moving,
            tour: !!final.tourRunning,
            skipped: signal.skipped,
          });
        }
        finishStage();
      }
      return signal.skipped;
    })();

    return {skip, ready, done, log, get skipped() { return signal.skipped; }};
  }

  /* 供测试与调试读取的常量表。 */
  return {run, TIMING, BUILD_DURATION, TOTAL, UI_AT, UI_REVEAL, FLIGHT, PULL, pullCurve, stageGeometry};
})();
