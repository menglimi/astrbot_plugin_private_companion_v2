"use strict";
window.CompanionPerceptionOverviewPage = (() => {
  const product = window.CompanionProduct;
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const icon = name => `<i data-lucide="${name}" aria-hidden="true"></i>`;
  let root = null, scope = "", snapshot = null, runtimeSnapshot = null, runtimeState = "loading";
  let modelStatus = null, modelState = "loading", voiceStatus = null, voiceState = "loading";
  let imageStatus = null, imageState = "loading", semanticStatus = null, semanticState = "loading";
  let recallStatus = null, recallState = "loading", mihomeStatus = null, mihomeState = "loading";
  let unsubscribe = null, clockTimer = null, abort = null, generation = 0, lastDay = "";

  function validRoot(ticket) {
    return ticket === generation && !!root?.isConnected && scope === product.scopeKey();
  }
  function localParts(date, timezone) {
    const parts = new Intl.DateTimeFormat("en-CA-u-nu-latn", {timeZone:timezone, year:"numeric", month:"2-digit", day:"2-digit"})
      .formatToParts(date);
    return Object.fromEntries(parts.filter(part => part.type !== "literal").map(part => [part.type, Number(part.value)]));
  }
  function dayNumber(parts) { return Math.floor(Date.UTC(parts.year, parts.month - 1, parts.day) / 86400000); }
  function chineseParts(date, timezone) {
    const parts = new Intl.DateTimeFormat("en-u-ca-chinese-nu-latn", {timeZone:timezone, month:"numeric", day:"numeric"})
      .formatToParts(date);
    const month = parts.find(part => part.type === "month")?.value || "";
    const day = Number(parts.find(part => part.type === "day")?.value);
    const numericMonth = Number(month.replace(/bis/i, ""));
    return {month:numericMonth, day, leap:/bis/i.test(month)};
  }
  function upcomingDates(data, now = new Date()) {
    const contact = data?.contact;
    if (!contact) return [];
    const lookahead = Number(contact.lookaheadDays);
    if (!Number.isInteger(lookahead) || lookahead < 0 || lookahead > 30) return [];
    let rows;
    try { rows = JSON.parse(contact.dates || "[]"); } catch (_) { return []; }
    if (!Array.isArray(rows) || !rows.length) return [];
    const timezone = contact.timezone || data.environment?.timezone || data.model?.timezone || "UTC";
    let today;
    try { today = localParts(now, timezone); } catch (_) { return []; }
    const todayNumber = dayNumber(today), found = [];
    for (const row of rows) {
      if (!row || typeof row.label !== "string" || !Number.isInteger(row.month) || !Number.isInteger(row.day)) continue;
      if (row.calendar === "lunar") {
        let formatterReady = true;
        try { chineseParts(now, timezone); } catch (_) { formatterReady = false; }
        if (!formatterReady) continue;
        for (let days = 0; days <= lookahead; days++) {
          const candidate = new Date(Date.UTC(today.year, today.month - 1, today.day + days, 12));
          let lunar;
          try { lunar = chineseParts(candidate, timezone); } catch (_) { break; }
          if (lunar.month === row.month && lunar.day === row.day && lunar.leap === (row.leap_month === true)) {
            found.push({label:row.label, days, calendar:"lunar"});
            break;
          }
        }
        continue;
      }
      if (row.calendar && row.calendar !== "gregorian") continue;
      for (let year = today.year; year <= today.year + 1; year++) {
        const candidate = new Date(Date.UTC(year, row.month - 1, row.day, 12));
        if (candidate.getUTCMonth() !== row.month - 1 || candidate.getUTCDate() !== row.day) continue;
        const days = dayNumber({year, month:row.month, day:row.day}) - todayNumber;
        if (days >= 0 && days <= lookahead) {
          found.push({label:row.label, days, calendar:"gregorian"});
          break;
        }
      }
    }
    return found.sort((a,b) => a.days - b.days || a.label.localeCompare(b.label, "zh-CN")).slice(0, 4);
  }
  function calendarDetailsMarkup(calendar) {
    if (!calendar || calendar.status === "disabled") return "";
    const rows = [];
    if (calendar.holiday?.status === "available") rows.push(["日历", calendar.holiday.label]);
    if (calendar.lunar_status === "available" && calendar.lunar_date) rows.push(["农历", calendar.lunar_date]);
    const terms = calendar.automatic_solar_terms || {};
    if (terms.status === "available") {
      if (terms.today?.length) rows.push(["节气", terms.today.join("、")]);
      else if (terms.upcoming?.length) {
        const next = terms.upcoming[0];
        rows.push(["节气", `${next.days_ahead} 天后 ${next.names.join("、")}`]);
      }
    }
    if (calendar.almanac?.status === "available") rows.push(["轻量黄历", `宜 ${calendar.almanac.yi} · 忌 ${calendar.almanac.ji}`]);
    return rows.length ? `<dl class="perception-calendar-details">${rows.map(([label,value]) =>
      `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join("")}</dl>` : "";
  }
  function stateValue(value) {
    if (typeof value === "string" || typeof value === "number") return String(value);
    if (value && typeof value === "object") {
      const candidate = value.label ?? value.name ?? value.value ?? value.description;
      if (typeof candidate === "string" || typeof candidate === "number") return String(candidate);
    }
    return "";
  }
  function ageLabel(value) {
    const date = typeof value === "number" ? new Date(value * 1000) : new Date(value || "");
    if (Number.isNaN(date.getTime())) return "时间未知";
    const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
    if (seconds < 60) return "刚刚";
    if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
    return new Intl.DateTimeFormat("zh-CN", {month:"numeric", day:"numeric", hour:"2-digit", minute:"2-digit"}).format(date);
  }
  function reasonLabel(code) {
    return ({capability_consent_missing:"等待此私聊授权", capability_consent_revoked:"此私聊已撤回授权",
      camera_consent_missing:"等待此私聊授权", camera_tool_unavailable:"摄像头工具暂不可用",
      capability_role_disabled:"此角色未启用手机读取", reality_provider_unavailable:"Reality 扩展未就绪",
      reality_tool_unavailable:"手机读取工具暂不可用", no_recent_snapshot:"授权已就绪，尚无最近快照",
      no_recent_observation:"摄像头授权已就绪，尚无最近单帧结果",
      capability_not_installed:"Reality 能力尚未登记", capability_not_active:"Reality 能力已停用"})[code]
      || "当前没有可显示的数据";
  }
  function modelRoute(kind = "conversation.reply") {
    const tasks = modelStatus?.tasks;
    const task = Array.isArray(tasks) ? tasks.find(item => item?.kind === kind) : null;
    const fields = task?.fields || {};
    const providerId = fields.provider?.value;
    const provider = modelStatus?.providers?.find(item => item?.id === providerId);
    const fallbackId = fields.fallback?.value;
    const fallback = modelStatus?.providers?.find(item => item?.id === fallbackId);
    if (!task || !providerId) return null;
    return {model:provider?.model || providerId, provider:providerId,
      fallback:fallback ? fallback.model || fallback.id : ""};
  }
  function providerSignal(id) {
    const provider = product.provider(id);
    if (!provider) return {state:"unknown", title:"尚未读取扩展", detail:"能力目录尚未提供状态"};
    const names = {connected:"已连接", installed:"已安装", missing:"未安装", disabled:"已停用",
      waiting:"等待就绪", degraded:"状态待检查", conflict:"重复安装", stopped:"宿主已停止"};
    let state = provider.integration_state || "unknown";
    let title = names[state] || "状态未知";
    if (state === "connected" && provider.runtime_ready === false) { state = "waiting"; title = "运行未就绪"; }
    const detail = provider.reason || (provider.runtime_ready === true ? "扩展报告运行就绪" : "设备工作区负责确认采集授权");
    return {state:state === "connected" ? "ready" : state === "missing" || state === "disabled" ? "off" : "pending", title, detail};
  }
  function clockZone() {
    return snapshot?.model?.timezone || snapshot?.environment?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  }
  function updateClock() {
    if (!root?.isConnected) return;
    const timezone = clockZone(), now = new Date();
    try {
      const time = root.querySelector("[data-context-clock-time]");
      const date = root.querySelector("[data-context-clock-date]");
      const zone = root.querySelector("[data-context-clock-zone]");
      const formatter = new Intl.DateTimeFormat("zh-CN", {timeZone:timezone, hour:"2-digit", minute:"2-digit", second:"2-digit", hourCycle:"h23"});
      const dateFormatter = new Intl.DateTimeFormat("zh-CN", {timeZone:timezone, year:"numeric", month:"long", day:"numeric"});
      const weekdayFormatter = new Intl.DateTimeFormat("zh-CN", {timeZone:timezone, weekday:"long"});
      if (time) time.textContent = formatter.format(now);
      if (date) date.textContent = dateFormatter.format(now);
      const weekday = root.querySelector("[data-context-clock-weekday]");
      if (weekday) weekday.textContent = weekdayFormatter.format(now);
      if (zone) zone.textContent = timezone;
      const parts = localParts(now, timezone), day = `${parts.year}-${parts.month}-${parts.day}`;
      if (lastDay && day !== lastDay) render();
      lastDay = day;
    } catch (_) {
      const time = root.querySelector("[data-context-clock-time]");
      const zone = root.querySelector("[data-context-clock-zone]");
      if (time) time.textContent = now.toLocaleTimeString("zh-CN", {hour12:false});
      if (zone) zone.textContent = "本机时区";
    }
  }
  function streamRow({tab, iconName, title, value, detail, state="pending", tag="待读取"}) {
    return `<button type="button" class="perception-stream-row state-${state}" data-perception-focus="${tab}" aria-label="${esc(title)}：${esc(value)}。打开对应配置">
      <span class="perception-stream-node">${icon(iconName)}</span>
      <span class="perception-stream-copy"><strong>${title}</strong><span class="perception-stream-value">${esc(value)}</span><small>${esc(detail)}</small></span>
      <span class="perception-stream-tag">${esc(tag)}</span><span class="perception-stream-arrow">${icon("arrow-up-right")}</span>
    </button>`;
  }
  function render() {
    if (!root?.isConnected) return;
    const ready = snapshot?.ready === true;
    const environment = snapshot?.environment || {}, model = snapshot?.model || {};
    const calendar = runtimeSnapshot?.calendar || {};
    const weather = runtimeSnapshot?.weather || {}, screenResult = runtimeSnapshot?.screen || {};
    const realityResult = runtimeSnapshot?.reality || {}, mobile = realityResult.snapshot || {};
    const cameraResult = runtimeSnapshot?.camera || {state:"unavailable", reason:"camera_runtime_unavailable"};
    const modelInfo = modelRoute();
    const modelStateLabel = modelInfo ? "路由已读取" : modelState === "loading" ? "正在读取模型路由" : "模型路由暂不可读";
    const news = snapshot?.news || {};
    const locationName = environment.locationName || "";
    const searchSource = news.sourceKind === "search";
    const explorationEnabled = news.explorationEnabled === true;
    const externalValue = searchSource
      ? explorationEnabled ? news.ready ? news.label || "网络搜索来源已就绪" : "网络探索已启用，搜索源未就绪" : "网络探索未启用"
      : explorationEnabled ? "探索已开启，当前来源不是搜索" : news.label || (ready ? "尚未配置外部来源" : "正在读取外部来源");
    const externalState = searchSource && explorationEnabled
      ? news.ready ? "ready" : "pending"
      : explorationEnabled ? "pending" : news.ready ? "ready" : "off";
    const externalDetail = [
      searchSource ? "AstrBot 网页搜索或自定义搜索源" : `来源类型 ${news.sourceKind || "未选择"}`,
      news.explorationInterests ? `兴趣：${news.explorationInterests}` : "未指定搜索兴趣",
      Number.isInteger(news.explorationIntervalHours) ? `最短间隔 ${news.explorationIntervalHours} 小时` : "",
      Number.isInteger(news.explorationResultCount) ? `每次最多 ${news.explorationResultCount} 条` : "",
      news.lastCheckedAt ? `最近检查 ${news.lastCheckedAt}` : "",
    ].filter(Boolean).join(" · ");
    const weatherValue = weather.state === "available"
      ? `${weather.location || environment.locationName || "当前位置"} · ${weather.condition || "天气已读取"}${weather.temperature_c == null ? "" : ` · ${weather.temperature_c}°C`}`
      : weather.state === "disabled" ? "天气感知未启用"
        : weather.state === "unconfigured" ? "尚未设置天气地点"
          : runtimeState === "loading" ? "正在读取天气实况" : "天气实况暂不可用";
    const weatherDetail = weather.state === "available"
      ? `${weather.provider || "天气来源"} · 观测 ${ageLabel(weather.observed_at)}${weather.humidity_pct == null ? "" : ` · 湿度 ${weather.humidity_pct}%`}${weather.wind_kph == null ? "" : ` · 风速 ${weather.wind_kph} km/h`}`
      : weather.state === "disabled" ? "启用后总览显示当前实况；私聊询问天气时按需读取，日常计划也可参考。"
        : weather.state === "unconfigured" ? "在下方环境配置设置角色地点。"
          : "实况读取失败时不会沿用旧数据冒充当前天气。";
    const routeLabel = (route, pending) => route?.model || (pending ? "正在读取模型路线" : "尚未分配");
    const detailForRoute = route => route
      ? `Provider ${route.provider}${route.fallback ? ` · 备用 ${route.fallback}` : ""}`
      : modelState === "error" ? "任务路由暂不可读" : "此任务当前没有可用路由";
    const voiceLanguage = voiceStatus?.languages?.find(item => /^(zh|zh[-_])|中文/i.test(item.k || item.n || ""))
      || voiceStatus?.languages?.[0];
    const voiceProvider = voiceStatus?.providers?.find(item => item.id === voiceLanguage?.bind);
    const voiceValue = voiceState === "loading" ? "正在读取语音绑定"
      : voiceState === "error" ? "TTS 绑定暂不可读"
        : voiceStatus?.voice_enabled === false ? "语音回复未启用"
          : voiceProvider?.label || voiceProvider?.name || voiceLanguage?.bind || "尚未绑定 TTS";
    const generated = imageStatus?.actions?.find(item => item.action === "image.generate");
    const imageRoute = modelRoute("image.generate");
    const imageValue = imageState === "loading" ? "正在读取生图状态"
      : imageState === "error" ? "生图状态暂不可读"
        : imageRoute?.model || generated?.provider_id || generated?.owner || "尚未分配生图模型";
    const visionRoute = modelRoute("vision.review") || modelRoute("screen.interpretation");
    const analysisProvider = semanticStatus?.settings?.analysis_provider;
    const events = upcomingDates(snapshot);
    const alertList = Array.isArray(weather.alerts) ? weather.alerts.slice(0, 4) : [];
    const screenValue = screenResult.state === "available" ? screenResult.interpretation || "已有屏幕解读"
      : screenResult.state === "blocked" ? reasonLabel(screenResult.reason)
        : screenResult.state === "empty" ? "暂无已保存解读"
          : runtimeState === "loading" ? "正在核对屏幕权限" : "屏幕解读暂不可读";
    const mobileValue = mobile.location?.available
      ? mobile.location.label || "附近位置已读取"
      : realityResult.state === "blocked" ? reasonLabel(realityResult.reason)
        : realityResult.state === "ready" ? "授权已就绪，暂无位置快照"
          : "暂无已授权的位置快照";
    const cameraObservation = cameraResult.observation || {};
    const cameraValue = cameraResult.state === "available"
      ? cameraResult.answer_available
        ? cameraObservation.summary || cameraObservation.scene_description || cameraObservation.purpose_answer || "最近单帧已识别"
        : cameraObservation.uncertainty || cameraResult.message || "最近单帧结果不确定"
      : cameraResult.state === "blocked" ? reasonLabel(cameraResult.reason)
        : cameraResult.state === "ready" ? "授权已就绪，暂无识别结果" : "暂无可用的摄像头结果";
    const recalls = Array.isArray(recallStatus?.entries) ? recallStatus.entries : [];
    const recallValue = recallState === "loading" ? "正在读取撤回记录"
      : recallState === "error" ? "撤回记录暂不可读"
        : recallStatus?.enabled === false ? "撤回转录未启用"
        : recalls.length ? `${recalls.length} 条近期记录` : "近期没有可读记录";
    const recallDetail = recalls[0]
      ? `${recalls[0].local_time || ageLabel(recalls[0].withdrawn_at)} · ${String(recalls[0].text || "").slice(0, 72)}`
      : recallState === "error" ? "检查当前会话授权与撤回转录开关。"
        : recallStatus?.enabled === false ? "打开下方撤回转录设置后，才会显示授权范围内的记录。"
          : "仅显示当前会话授权范围内的记录，不会重新进入对话。";
    const configuredDevices = (mihomeStatus?.devices || []).filter(item => item?.configured === true || item?.aliases?.length);
    const onlineCount = configuredDevices.filter(item => item.online === true).length;
    const offlineCount = configuredDevices.filter(item => item.online === false).length;
    const unknownCount = configuredDevices.length - onlineCount - offlineCount;
    const mihomeEnabled = mihomeState === "ready" && mihomeStatus?.enabled === true;
    const mihomeSummary = mihomeEnabled
      ? configuredDevices.length
        ? `${onlineCount} 在线 · ${offlineCount} 离线 · ${unknownCount} 未核实 · ${configuredDevices.length} 台已配置`
        : "只读设备状态已开启，尚无已映射设备"
      : "";
    const injections = Array.isArray(runtimeSnapshot?.other_injections)
      ? runtimeSnapshot.other_injections.filter(item => typeof item === "string" || item?.label || item?.name).slice(0, 6) : [];
    const injectionLabels = injections.map(item => typeof item === "string" ? item : item.label || item.name);
    const signals = [
      streamRow({tab:"config-environment:perception-detail-place", iconName:"map-pin", title:"所在地",
        value:locationName || "尚未设置角色地点",
        detail:locationName ? "使用角色配置的区域；不显示经纬度。" : "在地点与天气设置中填写城市或区域。",
        state:locationName ? "ready" : ready ? "off" : "pending", tag:locationName ? "已配置" : "待设置"}),
      streamRow({tab:"config-environment:perception-detail-place", iconName:"cloud-sun", title:"天气实况",
        value:weather.state === "available"
          ? `${weather.condition || "天气已读取"}${weather.temperature_c == null ? "" : ` · ${weather.temperature_c}°C`}`
          : weatherValue,
        detail:weatherDetail,
        state:weather.state === "available" ? "ready" : weather.state === "disabled" ? "off" : "pending",
        tag:weather.state === "available" ? "实况" : weather.state === "disabled" ? "未启用" : "待配置"}),
      ...(alertList.length ? [streamRow({tab:"config-environment:perception-detail-place", iconName:"triangle-alert", title:"天气预警",
        value:alertList[0].title || alertList[0].event_name || "有官方预警",
        detail:`${alertList[0].severity || "级别待核对"}${alertList[0].ends_at ? ` · 至 ${new Date(alertList[0].ends_at).toLocaleString("zh-CN")}` : ""}${alertList.length > 1 ? ` · 另有 ${alertList.length - 1} 条` : ""}`,
        state:"pending", tag:`${alertList.length} 条预警`})] : []),
      streamRow({tab:"config-models:perception-detail-model-route", iconName:"cpu", title:"对话模型",
        value:routeLabel(modelInfo, modelState === "loading"), detail:detailForRoute(modelInfo),
        state:modelInfo ? "ready" : "pending", tag:modelInfo ? "当前路由" : modelStateLabel}),
      streamRow({tab:"config-models:perception-detail-model-route", iconName:"audio-lines", title:"TTS 模型",
        value:voiceValue, detail:voiceLanguage ? `${voiceLanguage.n || voiceLanguage.k} · ${voiceStatus?.catalog_state || "AstrBot TTS Provider"}` : "按语种绑定，配置在模型与连接页。",
        state:voiceState === "error" || voiceState === "loading" ? "pending" : voiceStatus?.voice_enabled === false || !voiceLanguage?.bind ? "off" : "ready",
        tag:voiceStatus?.voice_enabled === false ? "未启用" : voiceLanguage?.bind ? "已绑定" : "未绑定"}),
      streamRow({tab:"config-models:perception-detail-model-route", iconName:"image", title:"生图模型",
        value:imageValue, detail:generated?.owner ? `${generated.owner}${imageRoute ? ` · ${imageRoute.model}` : ""} · ${generated.state || "状态已读取"}`
          : "Native 生图动作与扩展由模型与连接页管理。",
        state:generated?.state === "ready" || imageRoute ? "ready" : generated?.state === "disabled" ? "off" : "pending",
        tag:generated?.state === "ready" ? "可调用" : generated?.state === "disabled" ? "已关闭" : imageRoute ? "已分配" : "待检查"}),
      ...(visionRoute || analysisProvider ? [streamRow({tab:"config-models:perception-detail-model-route", iconName:"scan-eye", title:"视觉模型",
        value:visionRoute?.model || analysisProvider,
        detail:visionRoute ? detailForRoute(visionRoute) : "语义视觉分析 Provider",
        state:"ready", tag:"已配置"})] : []),
      streamRow({tab:"config-news:perception-detail-external", iconName:"globe-2", title:"外部资讯与检索",
        value:externalValue,
        detail:externalDetail + (news.failureCode ? ` · ${news.failureCode}` : ""),
        state:externalState, tag:externalState === "ready" ? "来源可用" : externalState === "off" ? "未启用" : "待检查"}),
      streamRow({tab:"config-screen:perception-detail-device-access", iconName:"smartphone", title:"用户定位",
        value:mobileValue,
        detail:mobile.location?.available ? `最近读取 ${ageLabel(mobile.location.captured_at)} · 仅展示授权区域，不显示坐标`
          : realityResult.state === "blocked" ? "位置读取需要当前私聊授权。" : "只回显对话已经读取的位置，不主动采集。",
        state:mobile.location?.available ? "ready" : realityResult.state === "blocked" ? "pending" : "off",
        tag:mobile.location?.available ? "已读取" : realityResult.state === "blocked" ? "需授权" : "暂无快照"}),
      streamRow({tab:"config-screen:perception-detail-device-access", iconName:"scan-eye", title:"识屏信息",
        value:screenValue,
        detail:screenResult.state === "available" ? `${screenResult.surface || "屏幕画面"} · 采集 ${ageLabel(screenResult.captured_at)} · 解读 ${ageLabel(screenResult.created_at)}`
          : "只显示最近完成的授权解读；刷新不会触发采集。",
        state:screenResult.state === "available" ? "ready" : screenResult.state === "blocked" ? "pending" : "off",
        tag:screenResult.state === "available" ? "有结果" : screenResult.state === "blocked" ? "需授权" : "暂无结果"}),
      streamRow({tab:"config-screen:perception-detail-device-access", iconName:"camera", title:"摄像头状态",
        value:cameraValue,
        detail:cameraResult.state === "available" ? `最近读取 ${ageLabel(cameraResult.captured_at)} · ${cameraResult.purpose || "按本轮明确请求"}`
          : "只显示已经完成的单帧识别；不会因刷新而拍摄。",
        state:cameraResult.state === "available" || cameraResult.state === "ready" ? "ready" : cameraResult.state === "blocked" ? "pending" : "off",
        tag:cameraResult.state === "available" ? "已识别" : cameraResult.state === "blocked" ? "需授权" : cameraResult.state === "ready" ? "待请求" : "未就绪"}),
      streamRow({tab:"config-recall:perception-detail-recalls", iconName:"message-square-quote", title:"撤回记录",
        value:recallValue, detail:recallDetail,
        state:recallState === "error" || recallState === "loading" ? "pending" : recalls.length ? "ready" : "off",
        tag:recalls.length ? "只读记录" : recallState === "error" ? "不可读" : "无记录"}),
      ...(mihomeSummary ? [streamRow({tab:"config-screen:perception-detail-mihome", iconName:"plug-zap", title:"米家设备",
        value:mihomeSummary,
        detail:configuredDevices.slice(0, 3).map(item => `${item.name || item.aliases?.[0] || "设备"} ${item.online === true ? "在线" : item.online === false ? "离线" : "状态未知"}`).join(" · ")
          + (mihomeStatus?.snapshot_at ? ` · 同步 ${mihomeStatus.snapshot_at}` : ""),
        state:offlineCount ? "pending" : "ready", tag:offlineCount ? `${offlineCount} 台离线` : "设备正常"})] : []),
      ...(injectionLabels.length ? [streamRow({tab:"config-injection:perception-detail-injection", iconName:"layers-3", title:"其他注入",
        value:`${injectionLabels.length} 项进入本轮上下文`, detail:injectionLabels.join(" · "),
        state:"ready", tag:"本轮材料"})] : []),
    ];
    const activeCount = [model.calendarEnabled, events.length > 0, locationName, weather.state === "available", alertList.length > 0,
      modelInfo, voiceLanguage?.bind, generated?.state === "ready", visionRoute || analysisProvider,
      searchSource && explorationEnabled && news.ready, screenResult.state === "available",
      mobile.location?.available, cameraResult.state === "available", recallStatus?.enabled && recalls.length > 0,
      mihomeEnabled && configuredDevices.length > 0, injectionLabels.length > 0].filter(Boolean).length;
    root.innerHTML = `<section class="perception-overview" aria-labelledby="perceptionOverviewTitle">
      <header class="perception-overview-head"><div><span class="perception-kicker">CONTEXT BOARD · ${activeCount} 项有实况</span>
        <h1 id="perceptionOverviewTitle">此刻，对话能读到什么</h1><p>按当前对象与角色配置汇总；设备内容只在真实输入和授权后出现。</p></div>
        <span class="perception-pulse ${ready && runtimeState === "ready" ? "is-ready" : "is-pending"}" data-perception-overview-state role="status" aria-live="polite"><i></i>${runtimeState === "error" || snapshot?.error ? "读取未完成" : runtimeState === "loading" ? "正在读取实况" : ready ? "真实状态已同步" : "角色上下文待读取"}</span></header>
      <div class="perception-context-board">
        <div class="perception-clock-panel">
          <button type="button" class="perception-clock-main" data-perception-focus="config-environment:perception-detail-calendar" aria-label="打开本地日期与历法配置">
            <span class="perception-clock-label">ROLE LOCAL TIME</span>
            <span class="perception-clock-values"><time class="perception-clock-time" data-context-clock-time>--:--:--</time>
            <span class="perception-clock-date-stack"><span class="perception-clock-date" data-context-clock-date>正在读取日期…</span><strong class="perception-clock-weekday" data-context-clock-weekday>—</strong></span>
            <span class="perception-clock-zone"><span>时区</span><b data-context-clock-zone>—</b></span>
            </span>
          </button>
          <button type="button" class="perception-calendar-context" data-perception-focus="config-environment:perception-detail-calendar" aria-label="打开历法与日期上下文配置">${calendarDetailsMarkup(calendar)}
            <span class="perception-calendar-state ${model.calendarEnabled ? "enabled" : ""}">${icon(model.calendarEnabled ? "calendar-check-2" : "calendar-days")}<span>${model.calendarEnabled ? "日期上下文进入对话" : ready ? "日期上下文未启用" : "日历状态待读取"}</span></span>
          </button>
          ${events.length ? `<button type="button" class="perception-clock-events" data-perception-focus="config-environment:perception-detail-important-days" aria-label="${esc(`打开重要日子配置：${events.map(event => `${event.label}，${event.days === 0 ? "今天" : `${event.days} 天后`}`).join("；")}`)}">${icon("calendar-heart")}<span>${events.map(event => `${esc(event.label)} · ${event.days === 0 ? "今天" : `${event.days} 天后`}`).join("　/　")}</span>${icon("arrow-up-right")}</button>` : ""}
        </div>
        <div class="perception-stream" aria-label="对话上下文来源">${signals.join("")}</div>
      </div>
      <footer class="perception-overview-foot"><span>${icon("shield-check")}只回显当前范围已授权数据 · 不主动采集手机、屏幕或摄像头 · 点击条目查看对应配置</span>
        <button type="button" class="perception-refresh" data-context-refresh title="刷新感知状态" aria-label="刷新感知状态" ${runtimeState === "loading" ? "disabled" : ""}>${icon("refresh-cw")}</button></footer>
    </section>`;
    const page = root.parentElement;
    const injectionTab = page?.querySelector('[data-perception-tab="config-injection"]');
    if (injectionTab) injectionTab.hidden = injectionLabels.length === 0;
    const mihomePanel = page?.querySelector("#perception-detail-mihome");
    if (mihomePanel) mihomePanel.hidden = !mihomeEnabled;
    const mihomeWorkspace = page?.querySelector("#mihomeStatusWorkspace");
    if (mihomeWorkspace) mihomeWorkspace.innerHTML = mihomeEnabled
      ? `<p class="perception-mihome-note">${mihomeStatus.snapshot_at ? `设备目录最近同步 ${esc(mihomeStatus.snapshot_at)}。` : "当前展示米家扩展缓存的设备目录状态。"} 状态未知时不会调用设备接口补采。</p>${configuredDevices.length
        ? `<ul>${configuredDevices.map(item => `<li class="perception-mihome-device"><span><strong>${esc(item.name || item.aliases?.[0] || "未命名设备")}</strong><small>${esc((item.aliases || []).join("、") || "未设置别名")}</small></span><b class="state-${item.online === true ? "online" : item.online === false ? "offline" : "unknown"}">${item.online === true ? "在线" : item.online === false ? "离线" : "未核实"}</b></li>`).join("")}</ul>`
        : `<p class="memory-notice" role="status">只读状态已启用，暂时没有已映射设备。</p>`}` : "";
    const recallWorkspace = page?.querySelector("#perceptionRecallWorkspace");
    if (recallWorkspace) recallWorkspace.innerHTML = recallState === "loading"
      ? `<p class="memory-notice" role="status">正在读取当前窗口的撤回记录…</p>`
      : recallState === "error" ? `<p class="memory-notice" role="status">撤回记录暂不可读；检查当前窗口授权和转录配置。</p>`
        : recallStatus?.enabled === false ? `<p class="memory-notice" role="status">撤回转录未启用。配置开启后，只读记录会在设定时限内显示。</p>`
          : recalls.length ? `<ul>${recalls.map(item => `<li class="perception-recall-item"><span><strong>${esc(item.local_time || ageLabel(item.withdrawn_at))}</strong><small>${item.author ? `发送账号 ${esc(item.author)}` : "当前会话记录"}</small></span><p>${esc(item.text || "（无可展示文本）")}</p></li>`).join("")}</ul>`
            : `<p class="memory-notice" role="status">当前保留时限内没有可读的撤回记录。</p>`;
    const injectionWorkspace = page?.querySelector("#perceptionInjectionWorkspace");
    if (injectionWorkspace) injectionWorkspace.innerHTML = injectionLabels.length
      ? `<ul>${injections.map(item => {
        const label = typeof item === "string" ? item : item.label || item.name;
        const detail = typeof item === "string" ? "本轮上下文材料" : item.detail || item.source || "本轮上下文材料";
        return `<li><strong>${esc(label)}</strong><span>${esc(detail)}</span></li>`;
      }).join("")}</ul>` : "";
    window.lucide?.createIcons({attrs:{"aria-hidden":"true"}});
    lastDay = ""; updateClock();
  }
  async function refreshModel(ticket = generation) {
    if (!root) return;
    modelState = "loading"; render();
    try {
      const endpoint = product.role()?.model_api;
      if (typeof endpoint !== "string" || !endpoint) throw new Error("missing model route");
      const response = await product.request("GET", product.relative(endpoint));
      const value = product.unwrap(response);
      if (!validRoot(ticket)) return;
      if (!Array.isArray(value.tasks) || !Array.isArray(value.providers)) throw new Error("invalid model route");
      modelStatus = value; modelState = "ready";
    } catch (_) {
      if (!validRoot(ticket)) return;
      modelStatus = null; modelState = "error";
    }
    render();
  }
  async function refreshVoice(ticket = generation) {
    try {
      const endpoint = product.role()?.model_api;
      if (typeof endpoint !== "string" || !endpoint) throw new Error("missing voice route");
      const value = product.unwrap(await product.request("GET", product.relative(endpoint.replace(/\/$/, "") + "/voice")));
      if (!validRoot(ticket)) return;
      if (!Array.isArray(value.languages) || !Array.isArray(value.providers)) throw new Error("invalid voice status");
      voiceStatus = value; voiceState = "ready";
    } catch (_) {
      if (!validRoot(ticket)) return;
      voiceStatus = null; voiceState = "error";
    }
    render();
  }
  async function refreshImage(ticket = generation) {
    try {
      const endpoint = product.role()?.model_api;
      if (typeof endpoint !== "string" || !endpoint) throw new Error("missing image route");
      const value = product.unwrap(await product.request("GET", product.relative(endpoint.replace(/\/$/, "") + "/image")));
      if (!validRoot(ticket)) return;
      if (!Array.isArray(value.actions)) throw new Error("invalid image status");
      imageStatus = value; imageState = "ready";
    } catch (_) {
      if (!validRoot(ticket)) return;
      imageStatus = null; imageState = "error";
    }
    render();
  }
  async function refreshSemanticStatus(ticket = generation) {
    try {
      const bridge = product.bridgeNow?.() || await product.bridgeFor();
      const value = product.unwrap(await bridge.apiGet("semantic", {...product.selection(), kind:"reaction"}));
      if (!validRoot(ticket)) return;
      if (!value || typeof value !== "object") throw new Error("invalid semantic status");
      semanticStatus = value; semanticState = "ready";
    } catch (_) {
      if (!validRoot(ticket)) return;
      semanticStatus = null; semanticState = "error";
    }
    render();
  }
  async function refreshRecalls(ticket = generation) {
    try {
      const bridge = product.bridgeNow?.() || await product.bridgeFor();
      const value = product.unwrap(await bridge.apiGet("reply/recalls", {limit:5}));
      if (!validRoot(ticket)) return;
      if (!Array.isArray(value.entries)) throw new Error("invalid recall status");
      recallStatus = value; recallState = "ready";
    } catch (_) {
      if (!validRoot(ticket)) return;
      recallStatus = null; recallState = "error";
    }
    render();
  }
  async function refreshMihome(ticket = generation) {
    try {
      if (typeof window.fetch !== "function") throw new Error("fetch unavailable");
      const statusResponse = await window.fetch("/api/plugin/astrbot_plugin_mihome/status", {
        credentials:"same-origin", cache:"no-store",
      });
      if (!statusResponse?.ok) throw new Error("device status unavailable");
      const status = await statusResponse.json();
      if (!validRoot(ticket)) return;
      if (status?.ok !== true || typeof status.tools?.enable_readonly_tool !== "boolean")
        throw new Error("invalid device capability status");
      if (!status.tools.enable_readonly_tool) {
        mihomeStatus = null; mihomeState = "disabled";
        render();
        return;
      }
      const devicesResponse = await window.fetch("/api/plugin/astrbot_plugin_mihome/devices", {
        credentials:"same-origin", cache:"no-store",
      });
      if (!devicesResponse?.ok) throw new Error("device status unavailable");
      const devices = await devicesResponse.json();
      if (!validRoot(ticket)) return;
      if (devices?.ok !== true || !Array.isArray(devices.devices)) throw new Error("invalid device status");
      mihomeStatus = {...devices, enabled:true, tools:status.tools}; mihomeState = "ready";
    } catch (_) {
      if (!validRoot(ticket)) return;
      mihomeStatus = null; mihomeState = "unavailable";
    }
    render();
  }
  async function refreshRuntime(ticket = generation) {
    if (!root) return;
    runtimeState = "loading"; render();
    try {
      const endpoint = product.role()?.perception_native_api;
      if (typeof endpoint !== "string" || !endpoint) throw new Error("missing perception runtime route");
      const route = endpoint.replace(/\/$/, "") + "/runtime";
      const value = product.unwrap(await product.request("GET", product.relative(route)));
      if (!validRoot(ticket)) return;
      if (!value || typeof value !== "object" || !value.weather || !value.screen || !value.reality || !value.calendar)
        throw new Error("invalid perception runtime snapshot");
      runtimeSnapshot = value; runtimeState = "ready";
    } catch (_) {
      if (!validRoot(ticket)) return;
      runtimeSnapshot = null; runtimeState = "error";
    }
    render();
  }
  function click(event) {
    if (!event.target.closest("[data-context-refresh]")) return;
    window.CompanionNativePerceptionPage?.refresh?.();
    const ticket = generation;
    refreshModel(ticket); refreshRuntime(ticket); refreshVoice(ticket); refreshImage(ticket);
    refreshSemanticStatus(ticket); refreshRecalls(ticket); refreshMihome(ticket);
  }
  function mount(node) {
    unmount();
    root = node; scope = product.scopeKey(); abort = new AbortController();
    const ticket = ++generation;
    snapshot = null; runtimeSnapshot = null; runtimeState = "loading";
    modelStatus = null; modelState = "loading"; voiceStatus = null; voiceState = "loading";
    imageStatus = null; imageState = "loading"; semanticStatus = null; semanticState = "loading";
    recallStatus = null; recallState = "loading"; mihomeStatus = null; mihomeState = "loading";
    root.addEventListener("click", click, {signal:abort.signal});
    unsubscribe = window.CompanionNativePerceptionPage?.subscribe?.(next => {
      if (!validRoot(ticket)) return;
      snapshot = next; render();
    }) || null;
    render();
    refreshModel(ticket); refreshRuntime(ticket); refreshVoice(ticket); refreshImage(ticket);
    refreshSemanticStatus(ticket); refreshRecalls(ticket); refreshMihome(ticket);
    clockTimer = setInterval(updateClock, 1000);
  }
  function unmount() {
    generation++; abort?.abort(); abort = null; unsubscribe?.(); unsubscribe = null;
    if (clockTimer) clearInterval(clockTimer);
    clockTimer = null; root = null; scope = ""; snapshot = null; runtimeSnapshot = null; runtimeState = "loading";
    modelStatus = null; modelState = "loading"; voiceStatus = null; voiceState = "loading";
    imageStatus = null; imageState = "loading"; semanticStatus = null; semanticState = "loading";
    recallStatus = null; recallState = "loading"; mihomeStatus = null; mihomeState = "loading";
  }
  return {mount, unmount, refresh:refreshRuntime, upcomingDates};
})();
