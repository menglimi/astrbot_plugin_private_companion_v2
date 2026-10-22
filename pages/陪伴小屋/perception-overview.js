"use strict";
window.CompanionPerceptionOverviewPage = (() => {
  const product = window.CompanionProduct;
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const icon = name => `<i data-lucide="${name}" aria-hidden="true"></i>`;
  const modelAvailabilityLabel = value => ({ready:"已就绪",disabled:"已关闭",missing:"尚未配置",unavailable:"暂不可用",
    unknown:"状态待核对",invalid:"配置待核对",failed:"读取失败",unsupported:"暂不支持"})[value] || "状态待核对";
  let root = null, scope = "", snapshot = null, runtimeSnapshot = null, runtimeState = "loading";
  let modelStatus = null, modelState = "loading", voiceStatus = null, voiceState = "loading";
  let imageStatus = null, imageState = "loading", semanticStatus = null, semanticState = "loading";
  let recallStatus = null, recallState = "loading", mihomeStatus = null, mihomeState = "loading";
  let balanceConfig = null, balanceDraft = null, balanceExpanded = false, balanceConfigLoading = false;
  let balanceWorkspace = null, balanceMarkup = "", selectedDestination = "", selectedModelTab = "";
  let balanceStatus = null, balanceStatusLoading = false, balanceStatusRefreshQueued = false, balanceStatusError = "";
  let balanceSaving = false, balanceTesting = false, balanceTestResult = null;
  let balanceResultScope = "", balanceResultConfigToken = "", balanceResultConfigKey = "", balanceResultIsDraft = false;
  let balanceMessage = "", balanceError = "", balanceTestError = "";
  let unsubscribe = null, clockTimer = null, abort = null, generation = 0, lastDay = "";
  /* 感知页每次换路由都会重新挂载。最近一次成功快照只在当前页面内存中
     按角色/会话和宿主路由保留，返回时先展示它，再异步核对最新状态。 */
  const overviewCache = new Map();
  /* 余额属于当前角色/会话，但不属于某个具体的感知路由。单独存一份，
     这样从仪表盘切到配置、再切回时不会因为下方配置工作区被卸载而丢掉
     最近成功读数。只挑选可安全展示的字段；API 令牌和 edit token 永不缓存。 */
  const balanceCache = new Map();
  let overviewRouteKey = "";
  function activeScopeKey() {
    try {
      const scoped = product.scopeKey?.();
      if (scoped != null && String(scoped).trim()) return String(scoped);
      const role = product.role?.() || {};
      const selection = product.selection?.() || {};
      const fallback = [selection.installation_id, selection.target_id, role.installation_id,
        role.target_id, role.role_id, role.model_api].filter(value => value != null && String(value).trim());
      return fallback.length ? fallback.join(":") : "default";
    } catch (_) { return "default"; }
  }
  function routeKey() {
    try {
      const role = product.role?.() || {};
      return [role.model_api, role.perception_native_api, role.screen_access_api, role.reality_access_api].join("|");
    } catch (_) { return ""; }
  }
  function overviewCacheEntry() {
    const key = `${scope}:${overviewRouteKey}`;
    let entry = overviewCache.get(key);
    if (!entry) { entry = {}; overviewCache.set(key, entry); }
    return entry;
  }
  function rememberOverview(name, value, stateName, stateValue) {
    const entry = overviewCacheEntry();
    if (value != null) entry[name] = value;
    if (stateName) entry[stateName] = stateValue;
  }
  function forgetOverview(name, stateName) {
    const entry = overviewCacheEntry();
    delete entry[name];
    if (stateName) delete entry[stateName];
  }

  function safeBalanceConfig(value) {
    if (!value || typeof value !== "object") return null;
    return {
      source: value.source || "none",
      source_state: value.source_state || "not_configured",
      provider: value.provider || "newapi",
      url: typeof value.url === "string" ? value.url : "",
      user_id: typeof value.user_id === "string" ? value.user_id : "",
      value_divisor: String(value.value_divisor || "500000"),
      has_api_key: value.has_api_key === true,
    };
  }

  function safeBalanceDraft(value) {
    if (!value || typeof value !== "object") return null;
    return {
      url: typeof value.url === "string" ? value.url : "",
      user_id: typeof value.user_id === "string" ? value.user_id : "",
      value_divisor: String(value.value_divisor || "500000"),
      /* A typed nap_ token is deliberately discarded on route changes. */
      api_key: "",
      clear_configuration: value.clear_configuration === true,
    };
  }

  function safeBalanceObservation(value) {
    if (!value || typeof value !== "object") return null;
    const amount = Number(value.amount);
    if (value.available !== true || !Number.isFinite(amount) || amount < 0) return null;
    return {
      tested: value.tested === true,
      available: true,
      provider: typeof value.provider === "string" ? value.provider : "newapi",
      provider_label: typeof value.provider_label === "string" ? value.provider_label : "NewAPI",
      currency_label: typeof value.currency_label === "string" ? value.currency_label : "额度",
      amount: formatBalanceAmount(amount),
      observed_at: typeof value.observed_at === "string" ? value.observed_at : "",
    };
  }

  function safeBalanceStatus(value) {
    if (!value || typeof value !== "object" || typeof value.configured !== "boolean"
        || typeof value.available !== "boolean") return null;
    const amount = Number(value.amount);
    if (value.available && (!Number.isFinite(amount) || amount < 0)) return null;
    return {
      configured:value.configured, available:value.available,
      provider:typeof value.provider === "string" ? value.provider : "newapi",
      provider_label:typeof value.provider_label === "string" ? value.provider_label : "NewAPI",
      currency_label:typeof value.currency_label === "string" ? value.currency_label : "额度",
      amount:value.available ? formatBalanceAmount(amount) : null,
      observed_at:typeof value.observed_at === "string" ? value.observed_at : "",
      state:typeof value.state === "string" ? value.state : value.available ? "available" : "unavailable",
    };
  }

  function balanceStatusMessage(value) {
    if (value?.available) return "";
    if (value?.state === "not_configured" || value?.configured === false) return "尚未配置服务余额数据源。";
    if (value?.state === "configuration_invalid") return "余额数据源配置无效，请检查配置。";
    return "余额读取失败，请检查 NewAPI 地址、令牌和网络。";
  }

  function balanceConfigKey(value) {
    const config = safeBalanceConfig(value);
    return config ? JSON.stringify(config) : "";
  }

  function rememberBalanceCache() {
    if (!scope) return;
    const entry = {};
    const config = safeBalanceConfig(balanceConfig);
    const draft = safeBalanceDraft(balanceDraft);
    const observation = safeBalanceObservation(balanceTestResult);
    const status = safeBalanceStatus(balanceStatus);
    if (config) entry.config = config;
    if (draft) entry.draft = draft;
    if (status) entry.status = status;
    if (observation) {
      entry.observation = observation;
      entry.observationIsDraft = balanceResultIsDraft === true;
      entry.observationConfigKey = balanceResultConfigKey || "";
    }
    if (Object.keys(entry).length) balanceCache.set(scope, entry);
    else balanceCache.delete(scope);
  }

  function restoreBalanceCache(nextScope) {
    const entry = balanceCache.get(nextScope) || {};
    balanceConfig = entry.config ? {...entry.config} : null;
    balanceDraft = entry.draft ? {...entry.draft, api_key: ""} : null;
    balanceStatus = safeBalanceStatus(entry.status);
    balanceStatusError = balanceStatus ? balanceStatusMessage(balanceStatus) : "";
    balanceTestResult = entry.observation ? {...entry.observation} : null;
    balanceResultScope = balanceTestResult ? nextScope : "";
    balanceResultConfigToken = "";
    balanceResultConfigKey = entry.observationConfigKey || "";
    balanceResultIsDraft = entry.observationIsDraft === true;
  }

  function formatBalanceAmount(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) && numeric >= 0 ? numeric.toFixed(2) : String(value ?? "");
  }
  function clearBalanceResult() {
    balanceTestResult = null;
    balanceResultConfigToken = "";
    balanceResultConfigKey = "";
    balanceResultIsDraft = false;
    rememberBalanceCache();
  }

  function validRoot(ticket) {
    return ticket === generation && !!root?.isConnected && scope === activeScopeKey();
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
      reality_private_required:"仅在当前私聊中读取", screen_repository_unavailable:"屏幕解读服务未就绪",
      screen_consent_missing:"等待此私聊屏幕授权", screen_consent_revoked:"此私聊已撤回屏幕授权",
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
    const provider = product.capability(id);
    if (!provider) return {state:"unknown", title:"尚未读取扩展", detail:"能力目录尚未提供状态"};
    const names = {connected:"已连接", installed:"已安装", missing:"未安装", disabled:"已停用",
      waiting:"等待就绪", degraded:"状态待检查", conflict:"重复安装", stopped:"插件已停止"};
    let state = provider.integration_state || "unknown";
    let title = names[state] || "状态未知";
    if (state === "connected" && provider.runtime_ready === false) { state = "waiting"; title = "运行未就绪"; }
    const detail = provider.reason || (provider.runtime_ready === true ? "扩展报告运行就绪" : "设备工作区负责确认采集授权");
    return {state:state === "connected" ? "ready" : state === "missing" || state === "disabled" ? "off" : "pending", title, detail};
  }
  /* === 服务端日历是日期语义的唯一基准 ===
     公历、星期、农历、节假日与节气都由服务端 project_local_date 按角色时区算出，
     随 /runtime 快照下发（页面从来没有自己算这些的权限）。
     只有"秒"必须本地走：用服务端给的时区推进，跨日则重新拉取服务端日历，
     因为农历与节假日跨日会变，本地推算会给出错误的一天。 */
  function calendarContext() {
    const value = runtimeSnapshot?.calendar;
    if (!value || typeof value !== "object") return null;
    if (value.status === "disabled" || typeof value.local_date !== "string") return null;
    return value;
  }
  function calendarTags(value) {
    const tags = [];
    const add = item => { if (typeof item === "string" && item && tags.indexOf(item) < 0) tags.push(item); };
    const configured = value.configured_annual_calendar?.listed_today;
    if (configured && typeof configured === "object") {
      add(configured.holiday);
      (Array.isArray(configured.solar_terms) ? configured.solar_terms : []).forEach(add);
    }
    if (value.holiday?.status === "available" && value.holiday?.kind === "holiday") add(value.holiday.label);
    add(value.fixed_gregorian_holiday);
    return tags.slice(0, 2);
  }
  function serverDateLabel() {
    const value = calendarContext();
    if (!value) return "";
    const bits = [];
    const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.local_date);
    if (parts) bits.push(`${Number(parts[2])} 月 ${Number(parts[3])} 日`);
    if (typeof value.weekday === "string" && value.weekday) bits.push(value.weekday);
    if (value.lunar_status === "available" && typeof value.lunar_date === "string" && value.lunar_date)
      bits.push(value.lunar_date.startsWith("农历") ? value.lunar_date : `农历${value.lunar_date}`);
    return bits.join(" · ");
  }
  function clockZone() {
    return calendarContext()?.timezone || snapshot?.model?.timezone || snapshot?.environment?.timezone
      || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  }
  function updateClock() {
    if (!root?.isConnected) return;
    const calendar = calendarContext();
    const timezone = clockZone(), now = new Date();
    const write = (selector, text) => {
      const node = root.querySelector(selector);
      if (node) node.textContent = text;
      return node;
    };
    try {
      const formatter = new Intl.DateTimeFormat("zh-CN", {timeZone:timezone, hour:"2-digit", minute:"2-digit", second:"2-digit", hourCycle:"h23"});
      const dateFormatter = new Intl.DateTimeFormat("zh-CN", {timeZone:timezone, year:"numeric", month:"long", day:"numeric"});
      const weekdayFormatter = new Intl.DateTimeFormat("zh-CN", {timeZone:timezone, weekday:"long"});
      write("[data-context-clock-time]", formatter.format(now));
      write("[data-context-clock-zone]", timezone);
      /* 服务端日历在手就用它的农历与节假日；读不到才退回本机推算，且不再假装有农历。 */
      const serverLabel = serverDateLabel();
      write("[data-context-clock-date]", serverLabel || dateFormatter.format(now));
      write("[data-context-clock-lunar]", serverLabel ? "" : weekdayFormatter.format(now));
      const today = calendar ? calendarTags(calendar)[0] || "" : "";
      const tag = write("[data-context-clock-tag]", today);
      if (tag) tag.hidden = !today;
      const parts = localParts(now, timezone), day = `${parts.year}-${parts.month}-${parts.day}`;
      /* 跨日不能本地推算：重新拉取 /runtime，让服务端按新的一天算农历与节假日。 */
      if (lastDay && day !== lastDay) { lastDay = day; refreshRuntime(); return; }
      lastDay = day;
    } catch (_) {
      write("[data-context-clock-time]", now.toLocaleTimeString("zh-CN", {hour12:false}));
      write("[data-context-clock-zone]", "本机时区");
    }
  }
  function emptyBalanceDraft(config) {
    return {url:config?.url || "", user_id:config?.user_id || "",
      value_divisor:config?.value_divisor || "500000", api_key:"", clear_configuration:false};
  }
  function rememberBalanceDraft(form) {
    const field = name => form.querySelector(`[name="${name}"]`);
    balanceDraft = {
      url:String(field("url")?.value || "").trim(),
      user_id:String(field("user_id")?.value || "").trim(),
      value_divisor:String(field("value_divisor")?.value || "").trim(),
      api_key:String(field("api_key")?.value || ""),
      clear_configuration:field("clear_configuration")?.checked === true,
    };
    return balanceDraft;
  }
  function balanceDraftIsCurrent() {
    return !!balanceConfig && !!balanceDraft && !balanceDraft.clear_configuration
      && balanceConfig.source_state === "configured"
      && balanceDraft.url === (balanceConfig.url || "")
      && balanceDraft.user_id === (balanceConfig.user_id || "")
      && balanceDraft.value_divisor === (balanceConfig.value_divisor || "500000")
      && !balanceDraft.api_key;
  }
  function balanceConfigMarkup() {
    if (!balanceExpanded) return "";
    if (balanceConfigLoading) return '<div id="perception-balance-source" class="perception-balance-config" role="status">正在读取余额数据源…</div>';
    if (!balanceConfig) return `<div id="perception-balance-source" class="perception-balance-config" role="status">
      <p>${esc(balanceError || "余额数据源配置暂不可读。")}</p><button type="button" data-balance-reload ${balanceSaving || balanceTesting ? "disabled" : ""}>重新读取</button></div>`;
    const draft = balanceDraft || emptyBalanceDraft(balanceConfig);
    const busy = balanceConfigLoading || balanceSaving || balanceTesting;
    const balanceActionLabel = balanceDraftIsCurrent() ? "重新读取余额" : "测试连接";
    const testable = !draft.clear_configuration && (balanceDraftIsCurrent()
      || (draft.url && (draft.api_key || balanceConfig.has_api_key)));
    const displayObservation = balanceResultIsDraft ? balanceTestResult
      : balanceStatus?.available ? balanceStatus : balanceTestResult;
    const displayMessage = displayObservation
      ? (balanceResultIsDraft ? "草稿测试成功" : "当前余额已读取") + "：" + formatBalanceAmount(displayObservation.amount)
        + " " + (displayObservation.currency_label || "额度") + " · " + (displayObservation.observed_at || "时间未知")
      : balanceStatusLoading ? "正在读取当前余额…" : balanceStatusError
        || (balanceStatus?.state === "not_configured" ? "尚未配置服务余额数据源。" : "");
    const sourceMessage = balanceConfig.source === "plugin" ? "本页保存的 NewAPI 数据源优先用于查询与主动联系。"
      : balanceConfig.source === "environment" ? "当前数据源来自插件环境配置；在这里保存后将优先使用本页配置。"
        : balanceConfig.source_state === "invalid" ? "检测到数据源配置，但读取失败；请检查地址、令牌和环境变量。"
          : "填写 NewAPI 地址和管理令牌后，插件即可查询服务额度。";
    const sourceState = balanceConfig.source_state === "invalid" ? "数据源配置无效"
      : balanceConfig.source === "plugin" ? balanceConfig.has_api_key ? "NewAPI 数据源已配置" : "NewAPI 令牌缺失"
      : balanceConfig.source === "environment" ? "正在使用插件环境配置"
        : "尚未配置数据源";
    return `<form id="perception-balance-source" class="perception-balance-config" data-balance-form novalidate aria-label="余额感知数据源配置">
      <div class="perception-balance-config-head"><span>${icon("wallet-cards")}</span><div><strong>余额数据源</strong><small>${esc(sourceState)} · ${esc(sourceMessage)}</small></div></div>
      <label class="perception-balance-field"><span>NewAPI 地址</span><input name="url" data-balance-field="url" type="url" inputmode="url" autocomplete="url" maxlength="2048"
        placeholder="https://newapi.example.com" value="${esc(draft.url)}" ${busy || draft.clear_configuration ? "disabled" : ""} required></label>
      <label class="perception-balance-field"><span>NewAPI 用户 ID（可选）</span><input name="user_id" data-balance-field="user_id" type="text" inputmode="numeric" autocomplete="off" maxlength="19"
        pattern="[1-9][0-9]{0,18}" placeholder="默认使用令牌所属账号" value="${esc(draft.user_id)}" ${busy || draft.clear_configuration ? "disabled" : ""}></label>
      <label class="perception-balance-field"><span>额度单位除数</span><input name="value_divisor" data-balance-field="value_divisor" type="text" inputmode="decimal" autocomplete="off" maxlength="64"
        value="${esc(draft.value_divisor)}" ${busy || draft.clear_configuration ? "disabled" : ""} required></label>
      <label class="perception-balance-field"><span>NewAPI 管理令牌（nap_）</span><input name="api_key" data-balance-field="api_key" type="password" autocomplete="new-password" maxlength="4096"
        value="${esc(draft.api_key)}" placeholder="${balanceConfig.has_api_key ? "已保存；留空保留当前令牌，输入新令牌可更换" : "输入带 profile:read 权限的个人访问令牌"}"
        ${busy || draft.clear_configuration ? "disabled" : ""}></label>
      <p class="perception-balance-note">查询使用个人访问令牌（需 profile:read），不是模型调用用的 sk- Key。额度按 NewAPI 的 QuotaPerUnit 换算；留空时使用 500000。</p>
      ${balanceConfig.source === "plugin" ? `<label class="perception-balance-clear"><input type="checkbox" name="clear_configuration" data-balance-field="clear_configuration" ${draft.clear_configuration ? "checked" : ""} ${busy ? "disabled" : ""}><span>移除本页保存的数据源</span><small>移除后会继续使用插件环境配置（如果已设置）。</small></label>` : ""}
      <p class="perception-balance-message" role="status" aria-live="polite" ${balanceMessage ? "" : "hidden"}>${esc(balanceMessage)}</p>
      <p class="perception-balance-message is-error" role="alert" ${balanceError ? "" : "hidden"}>${esc(balanceError)}</p>
      <p class="perception-balance-message" data-balance-test-result role="status" aria-live="polite" ${displayMessage ? "" : "hidden"}>${esc(displayMessage)}</p>
      <p class="perception-balance-message is-error" role="alert" ${balanceTestError ? "" : "hidden"}>${esc(balanceTestError)}</p>
      <footer class="perception-balance-actions">
        <button type="button" class="perception-balance-contact" data-go="manage" data-manage="contact" data-contact-view="sources">${icon("settings-2")}<span>前往主动联系 · 外部触发源</span></button>
        <span class="perception-balance-buttons">
          <button type="button" class="perception-balance-test" data-balance-test ${busy || !testable || (balanceStatusLoading && balanceDraftIsCurrent()) ? "disabled" : ""}>${balanceTesting ? balanceDraftIsCurrent() ? "正在读取…" : "正在测试…" : balanceActionLabel}</button>
          <button type="submit" class="perception-balance-save" ${busy ? "disabled" : ""}>${balanceSaving ? "正在保存…" : draft.clear_configuration ? "移除数据源" : "保存数据源"}</button>
        </span>
      </footer>
    </form>`;
  }
  function balanceFocus(form, active = window.document?.activeElement) {
    if (!active || !form?.contains?.(active)) return null;
    return {toggle:false, focus:active.getAttribute?.("name")
      || (active.matches?.('button[type="submit"]') ? "__submit" : active.matches?.("[data-balance-test]") ? "__test" : ""),
      selectionStart:active.selectionStart, selectionEnd:active.selectionEnd};
  }
  function restoreBalanceFocus(saved) {
    const form = balanceWorkspace?.querySelector("[data-balance-form]");
    const focus = saved?.focus === "__submit" ? form?.querySelector('button[type="submit"]')
      : saved?.focus === "__test" ? form?.querySelector("[data-balance-test]")
        : saved?.focus ? form?.querySelector(`[name="${saved.focus}"]`) : null;
    focus?.focus({preventScroll:true});
    if (focus && Number.isInteger(saved.selectionStart) && Number.isInteger(saved.selectionEnd))
      focus.setSelectionRange?.(saved.selectionStart, saved.selectionEnd);
  }
  function renderBalanceSource() {
    if (!balanceWorkspace || !balanceExpanded) return;
    const markup = balanceConfigMarkup();
    if (markup === balanceMarkup) return;
    const savedFocus = balanceFocus(balanceWorkspace.querySelector("[data-balance-form]"));
    balanceWorkspace.innerHTML = markup;
    balanceMarkup = markup;
    if (savedFocus) restoreBalanceFocus(savedFocus);
  }
  function syncSelection() {
    for (const card of root?.querySelectorAll?.(".perception-board-card") || []) card.classList.remove("is-selected");
    for (const button of root?.querySelectorAll?.("[data-board-goto]") || []) {
      const active = button.dataset.boardGoto === selectedDestination
        && (!button.dataset.boardModelTab || button.dataset.boardModelTab === selectedModelTab);
      button.setAttribute("aria-expanded", String(active));
      button.classList.toggle("is-selected", active);
      if (active) button.closest(".perception-board-card")?.classList.add("is-selected");
    }
  }
  function select(destination, {modelTab=""} = {}) {
    if (!root?.isConnected) return;
    selectedDestination = destination;
    selectedModelTab = modelTab;
    syncSelection();
    balanceExpanded = ["config-news","config-balance","config-recall"].includes(destination.split(":")[0]);
    renderBalanceSource();
    if (balanceExpanded && !balanceConfig && !balanceConfigLoading) void readBalanceConfig(generation);
  }
  function render({balanceSource=true} = {}) {
    if (!root?.isConnected) return;
    const active = window.document?.activeElement;
    const focusedId = active && root.contains?.(active) ? active.id : "";
    const ready = snapshot?.ready === true;
    const configurationFailed = !ready && (!!snapshot?.error || snapshot?.loading === false);
    const configurationState = configurationFailed ? "读取失败" : "正在读取…";
    const environment = snapshot?.environment || {}, model = snapshot?.model || {};
    const calendar = runtimeSnapshot?.calendar || {};
    const weather = runtimeSnapshot?.weather || {}, screenResult = runtimeSnapshot?.screen || {};
    const realityResult = runtimeSnapshot?.reality || {}, mobile = realityResult.snapshot || {};
    const cameraResult = runtimeSnapshot?.camera || {state:"unavailable", reason:"camera_runtime_unavailable"};
    const modelInfo = modelRoute();
    const modelStateLabel = modelInfo ? "路由已读取" : modelState === "loading" ? "正在读取模型路由" : "模型路由暂不可读";
    const news = snapshot?.news || {};
    const locationName = environment.locationName || "";
    const balanceEnabled = snapshot?.contact?.balanceAwarenessEnabled;
    const balanceAllowed = snapshot?.contact?.automaticAllowed;
    const balanceSourceConfigured = balanceConfig?.source_state === "configured";
    const balanceSourceInvalid = balanceConfig?.source_state === "invalid";
    const balanceDraftObservation = balanceResultIsDraft && balanceTestResult?.available === true ? balanceTestResult : null;
    const balanceObservation = balanceDraftObservation || (balanceStatus
      ? balanceStatus.available ? balanceStatus : null
      : balanceTestResult?.available === true ? balanceTestResult : null);
    const balanceObservationIsDraft = balanceObservation === balanceDraftObservation && !!balanceDraftObservation;
    const balanceValue = !ready ? `${balanceSourceConfigured ? "数据源已配置；" : ""}余额联系设置${configurationState === "读取失败" ? "读取失败" : "正在读取"}` : balanceEnabled === true
      ? balanceAllowed === true ? "服务余额联系已启用" : "余额契机已开，但后台自动联系未开启"
      : balanceSourceConfigured ? "数据源已配置，余额联系未开启"
        : balanceSourceInvalid ? "余额数据源配置无效，联系未开启"
          : "服务余额联系契机未启用";
    const balanceTag = !ready ? configurationFailed ? "读取失败" : "读取中" : balanceEnabled === true
      ? balanceAllowed === true ? "主动联系" : "总开关受限"
      : balanceSourceConfigured ? "数据源已配置" : balanceSourceInvalid ? "待修复" : ready ? "未启用" : "待读取";
    const balanceDetail = !ready ? "余额联系条件尚未核对；可展开配置数据源，或重新读取状态。"
      : balanceSourceConfigured && balanceEnabled !== true
      ? "数据源已配置；还需在主动联系的外部触发源中开启余额感知。"
      : "仅在服务余额达到阈值时作为主动联系素材，不会持续注入日常对话；不表示用户欠款。";
    const searchSource = news.sourceKind === "search";
    const dailySource = /AI\s*(早报|日报)|橘鸦/i.test(news.label || "");
    const explorationEnabled = news.explorationEnabled === true;
    const sourceAssembled = news.assembled ?? news.ready;
    const networkSucceeded = news.networkStatus === "succeeded";
    const networkLabel = news.networkStatus === "failed" ? "上次网络检查失败"
      : news.networkStatus === "succeeded" ? "网络检查通过"
        : sourceAssembled ? "网络尚未检查" : "来源未装配";
    const externalValue = !ready ? configurationFailed ? "外部来源设置读取失败" : "正在读取外部来源" : searchSource
      ? explorationEnabled ? networkSucceeded ? news.label || "网络搜索检查通过" : sourceAssembled ? `网络搜索已配置 · ${networkLabel}` : "网络探索已启用，搜索源未装配" : "网络探索未启用"
      : dailySource ? `AI 日报已装配 · ${networkSucceeded ? "后台持续维护" : networkLabel}`
        : sourceAssembled ? `${news.label || "资讯来源"} · ${networkSucceeded ? "后台持续维护" : networkLabel}`
          : ready ? "尚未配置外部来源" : "正在读取外部来源";
    const externalState = !ready ? "pending" : searchSource && explorationEnabled
      ? networkSucceeded ? "ready" : "pending"
      : networkSucceeded ? "ready" : sourceAssembled ? "pending" : "off";
    const externalDetail = [
      searchSource ? "AstrBot 网页搜索或自定义搜索源" : dailySource ? "内置 AI 日报来源" : `来源类型 ${news.sourceKind || "未选择"}`,
      news.explorationInterests ? `兴趣：${news.explorationInterests}` : "未指定搜索兴趣",
      Number.isInteger(news.explorationIntervalHours) ? `最短间隔 ${news.explorationIntervalHours} 小时` : "",
      Number.isInteger(news.explorationResultCount) ? `每次最多 ${news.explorationResultCount} 条` : "",
      networkLabel,
      news.lastAttemptAt ? `最近尝试 ${news.lastAttemptAt}` : "",
      news.lastCheckedAt ? `最近同步 ${news.lastCheckedAt}` : "",
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
          : voiceProvider?.model || voiceProvider?.label || voiceProvider?.name || voiceLanguage?.bind || "尚未绑定 TTS";
    const generated = imageStatus?.actions?.find(item => item.action === "image.generate");
    const imageRoute = modelRoute("image.generate");
    const imageValue = imageState === "loading" ? "正在读取生图状态"
      : imageState === "error" ? "生图状态暂不可读"
        : imageRoute?.model || generated?.provider_id || generated?.owner || "尚未分配生图模型";
    const visionRoute = modelRoute("vision.review") || modelRoute("screen.interpretation");
    const analysisProvider = semanticStatus?.settings?.analysis_provider;
    const events = upcomingDates(snapshot);
    const alertList = weather.state === "available" && Array.isArray(weather.alerts) ? weather.alerts.slice(0, 4) : [];
    const screenValue = screenResult.state === "available" ? screenResult.interpretation || "已有屏幕解读"
      : screenResult.state === "blocked" ? reasonLabel(screenResult.reason)
        : screenResult.state === "empty" ? "暂无已保存解读"
          : runtimeState === "loading" ? "正在核对屏幕权限" : "屏幕解读暂不可读";
    const mobileValue = mobile.location?.available
      ? mobile.location.label || "附近位置已读取"
      : runtimeState === "loading" ? "正在读取定位状态"
        : runtimeState === "error" ? "定位状态读取失败"
          : realityResult.reason ? reasonLabel(realityResult.reason)
        : realityResult.state === "ready" ? "授权已就绪，暂无位置快照"
          : "暂无已授权的位置快照";
    const device = mobile.device || {}, activity = mobile.activity || {};
    const phoneParts = [];
    if (device.available === true) {
      if (Number.isFinite(device.battery_percent)) phoneParts.push(`电量 ${device.battery_percent}%`);
      if (device.charging === true) phoneParts.push("充电中");
      const appState = ({foreground:"前台运行",background:"后台运行"})[device.app_state];
      if (appState) phoneParts.push(appState);
    }
    if (activity.available === true && activity.label) phoneParts.push(`${activity.stale ? "上次活动" : "活动"} · ${activity.label}`);
    const phoneAvailable = phoneParts.length > 0;
    const phoneValue = phoneAvailable ? phoneParts.join(" · ")
      : runtimeState === "loading" ? "正在读取手机状态"
        : runtimeState === "error" ? "手机状态读取失败"
          : realityResult.reason ? reasonLabel(realityResult.reason) : "暂无已授权的手机状态快照";
    const cameraObservation = cameraResult.observation || {};
    const cameraValue = cameraResult.state === "available"
      ? cameraResult.answer_available
        ? cameraObservation.summary || cameraObservation.scene_description || cameraObservation.purpose_answer || "最近单帧已识别"
        : cameraObservation.uncertainty || cameraResult.message || "最近单帧结果不确定"
      : runtimeState === "loading" ? "正在读取摄像头状态"
        : runtimeState === "error" ? "摄像头状态读取失败"
          : cameraResult.reason ? reasonLabel(cameraResult.reason)
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
    /* === 感知通道单一数据源 ===
       仪表盘只登记"当前真实存在的通道"，
       每条都带上它自己的读数与说明。不给通道编造数值、百分比或统一总数；
       读不到就说读不到（未启用 / 待授权），不拿旧数据冒充当前值。 */
    const percepts = [];
    const channel = (id, board, spec) => percepts.push({id, board, ...spec});
    const tabModel = "config-models:perception-detail-model-route";
    const tabPlace = "config-environment:perception-detail-place";
    const tabDevice = "config-screen:perception-detail-device-access";
    const tabCalendar = "config-models:perception-detail-context";

    channel("model-conversation", "models", {tab:tabModel, modelTab:"fn", icon:"cpu", title:"对话模型",
      value:routeLabel(modelInfo, modelState === "loading"), detail:detailForRoute(modelInfo),
      state:modelInfo ? "ready" : "pending", tag:modelInfo ? "当前路由" : modelStateLabel});
    channel("model-tts", "models", {tab:tabModel, modelTab:"voice", icon:"audio-lines", title:"TTS 模型",
      value:voiceValue,
      detail:voiceLanguage ? `${voiceLanguage.n || voiceLanguage.k} · ${modelAvailabilityLabel(voiceStatus?.catalog_state)}` : "按语种绑定，配置在模型与连接页。",
      state:voiceState === "error" || voiceState === "loading" ? "pending" : voiceStatus?.voice_enabled === false || !voiceLanguage?.bind ? "off" : "ready",
      tag:voiceState === "error" ? "读取失败" : voiceState === "loading" ? "读取中" : voiceStatus?.voice_enabled === false ? "未启用" : voiceLanguage?.bind ? "已绑定" : "未绑定"});
    channel("model-image", "models", {tab:tabModel, modelTab:"image", icon:"image", title:"生图模型",
      value:imageValue,
      detail:generated?.owner ? `${generated.owner}${imageRoute ? ` · ${imageRoute.model}` : ""} · ${modelAvailabilityLabel(generated.state)}`
        : "Native 生图动作与扩展由模型与连接页管理。",
      state:imageState !== "ready" ? "pending" : generated?.state === "ready" || imageRoute ? "ready" : generated?.state === "disabled" ? "off" : "pending",
      tag:imageState === "error" ? "读取失败" : imageState === "loading" ? "读取中" : generated?.state === "ready" ? "可调用" : generated?.state === "disabled" ? "已关闭" : imageRoute ? "已分配" : "待检查"});
    if (visionRoute || analysisProvider) channel("model-vision", "models", {tab:tabModel, modelTab:"fn", icon:"scan-eye", title:"视觉模型",
      value:visionRoute?.model || analysisProvider,
      detail:visionRoute ? detailForRoute(visionRoute) : "语义视觉分析 Provider",
      state:"ready", tag:"已配置"});

    /* 日期与历法：服务端 project_local_date 的产出必须有出口。
       每一项都只在服务端真的给出时才显示——历法项各有一个总开关，没开就是没开。 */
    const calendarView = (() => {
      const cal = calendarContext();
      if (!cal) return null;
      const labels = [];
      if (typeof cal.weekday === "string" && cal.weekday) labels.push(cal.weekday);
      if (typeof cal.period === "string" && cal.period) labels.push(cal.period);
      const detail = [];
      if (cal.lunar_status === "available" && typeof cal.lunar_date === "string" && cal.lunar_date)
        detail.push(cal.lunar_date.startsWith("农历") ? cal.lunar_date : `农历${cal.lunar_date}`);
      const terms = [];
      const today = cal.automatic_solar_terms?.today;
      if (Array.isArray(today)) for (const item of today) for (const name of item?.names || []) terms.push(name);
      const listed = cal.configured_annual_calendar?.listed_today?.solar_terms;
      if (Array.isArray(listed)) terms.push(...listed);
      if (terms.length) detail.push(`节气 ${terms.slice(0, 2).join("、")}`);
      if (cal.almanac?.status === "available" && cal.almanac.yi && cal.almanac.ji)
        detail.push(`宜 ${cal.almanac.yi} · 忌 ${cal.almanac.ji}`);
      return {
        labels: labels.length ? labels.join(" · ") : "历法已启用",
        detail: detail.length ? detail.join(" · ") : "服务端未产出更多历法明细；农历、节气与黄历各有独立开关。",
      };
    })();
    if (calendarView) channel("env-calendar", "environment", {tab:tabCalendar, icon:"calendar-days", title:"日期与历法",
      value:calendarView.labels, detail:calendarView.detail, state:"ready", tag:"服务端日历"});
    channel("env-location", "environment", {tab:tabPlace, icon:"map-pin", title:"所在地",
      value:locationName || (!ready ? `角色地点${configurationState}` : "尚未设置角色地点"),
      detail:locationName ? "使用角色配置的区域；不显示经纬度。" : "在日程与规划中填写角色所在地。",
      state:locationName ? "ready" : ready ? "off" : "pending", tag:locationName ? "已配置" : !ready ? configurationFailed ? "读取失败" : "读取中" : "待设置"});
    channel("env-weather", "environment", {tab:tabPlace, icon:"cloud-sun", title:"天气实况",
      value:weather.state === "available"
        ? `${weather.condition || "天气已读取"}${weather.temperature_c == null ? "" : ` · ${weather.temperature_c}°C`}`
        : weatherValue,
      detail:weatherDetail,
      state:weather.state === "available" ? "ready" : weather.state === "disabled" ? "off" : "pending",
      tag:weather.state === "available" ? "实况" : weather.state === "disabled" ? "未启用" : weather.state === "unconfigured" ? "待配置" : runtimeState === "loading" ? "读取中" : "读取失败"});
    if (alertList.length) channel("env-alert", "environment", {tab:tabPlace, icon:"triangle-alert", title:"天气预警",
      value:alertList[0].title || alertList[0].event_name || "有官方预警",
      detail:`${alertList[0].severity || "级别待核对"}${alertList[0].ends_at ? ` · 至 ${new Date(alertList[0].ends_at).toLocaleString("zh-CN")}` : ""}${alertList.length > 1 ? ` · 另有 ${alertList.length - 1} 条` : ""}`,
      state:"pending", tag:`${alertList.length} 条预警`});
    channel("ext-external", "external", {tab:"config-news:perception-detail-external", icon:"globe-2", title:"外部资讯与检索",
      value:externalValue, detail:externalDetail + (news.failureCode ? ` · ${news.failureCode}` : ""),
      state:externalState,
      tag:!ready ? configurationFailed ? "读取失败" : "读取中" : externalState === "ready" ? "检查通过" : externalState === "off" ? "未启用" : news.networkStatus === "failed" ? "检查失败" : "待检查"});
    channel("ext-balance", "external", {tab:"config-balance:perception-detail-balance-source", icon:"wallet-cards", title:"余额感知",
      value:balanceValue, detail:[balanceDetail, balanceObservation ? `${balanceResultIsDraft ? "草稿测试" : "最近查询"} ${formatBalanceAmount(balanceObservation.amount)} ${balanceObservation.currency_label || "额度"}` : "尚无余额查询结果"].join(" · "),
      state:balanceObservation ? "ready" : balanceSourceConfigured || balanceSourceInvalid || balanceEnabled === true || !ready || balanceError || balanceTestError || balanceStatusError ? "pending" : "off",
      tag:balanceTag});

    channel("device-location", "devices", {tab:tabDevice, icon:"smartphone", title:"用户定位",
      value:mobileValue,
      detail:mobile.location?.available ? `最近读取 ${ageLabel(mobile.location.captured_at)} · 仅展示授权区域，不显示坐标`
        : realityResult.state === "blocked" ? "位置读取需要当前私聊授权。" : "只回显对话已经读取的位置，不主动采集。",
      state:mobile.location?.available ? "ready" : realityResult.reason === "capability_role_disabled" ? "off" : "pending",
      tag:mobile.location?.available ? "已读取" : runtimeState === "error" ? "读取失败" : runtimeState === "loading" ? "读取中" : realityResult.state === "blocked" ? "需授权" : "暂无快照"});
    channel("device-screen", "devices", {tab:tabDevice, icon:"scan-eye", title:"识屏信息",
      value:screenValue,
      detail:screenResult.state === "available" ? `${screenResult.surface || "屏幕画面"} · 采集 ${ageLabel(screenResult.captured_at)} · 解读 ${ageLabel(screenResult.created_at)}`
        : "只显示最近完成的授权解读；刷新不会触发采集。",
      state:screenResult.state === "available" ? "ready" : "pending",
      tag:screenResult.state === "available" ? "有结果" : runtimeState === "error" ? "读取失败" : runtimeState === "loading" ? "读取中" : screenResult.state === "blocked" ? "需授权" : "暂无结果"});
    channel("device-phone", "devices", {tab:tabDevice, icon:"smartphone", title:"手机状态",
      value:phoneValue, detail:"展示最近已授权快照中的电量、运行状态与活动；刷新页面不会触发手机采集。",
      state:phoneAvailable ? "ready" : realityResult.reason === "capability_role_disabled" ? "off" : "pending",
      tag:phoneAvailable ? "有快照" : runtimeState === "error" ? "读取失败" : runtimeState === "loading" ? "读取中" : realityResult.state === "blocked" ? "需授权" : "暂无快照"});
    channel("device-camera", "devices", {tab:tabDevice, icon:"camera", title:"摄像头状态",
      value:cameraValue,
      detail:cameraResult.state === "available" ? `最近读取 ${ageLabel(cameraResult.captured_at)} · ${cameraResult.purpose || "按本轮明确请求"}`
        : "只显示已经完成的单帧识别；不会因刷新而拍摄。",
      state:cameraResult.state === "available" && cameraResult.answer_available === true ? "ready" : "pending",
      tag:cameraResult.state === "available" ? "已识别" : cameraResult.state === "blocked" ? "需授权" : cameraResult.state === "ready" ? "待请求" : "未就绪"});
    channel("device-recalls", "external", {tab:"config-recall:perception-detail-recalls", icon:"message-square-quote", title:"撤回记录",
      value:recallValue, detail:recallDetail,
      state:recallState === "error" || recallState === "loading" ? "pending" : recalls.length ? "ready" : "off",
      tag:recallState === "error" ? "读取失败" : recallState === "loading" ? "读取中" : recalls.length ? "只读记录" : "无记录"});
    if (mihomeEnabled) channel("device-mihome", "devices", {tab:"config-screen:perception-detail-mihome", icon:"plug-zap", title:"米家设备",
      value:mihomeSummary,
      detail:configuredDevices.slice(0, 3).map(item => `${item.name || item.aliases?.[0] || "设备"} ${item.online === true ? "在线" : item.online === false ? "离线" : "状态未知"}`).join(" · ")
        + (mihomeStatus?.snapshot_at ? ` · 同步 ${mihomeStatus.snapshot_at}` : ""),
      state:offlineCount ? "pending" : "ready", tag:offlineCount ? `${offlineCount} 台离线` : "设备正常"});
    if (injectionLabels.length) channel("ext-injection", "external", {tab:"config-injection:perception-detail-injection", icon:"layers-3", title:"其他注入",
      value:`${injectionLabels.length} 项进入本轮上下文`, detail:injectionLabels.join(" · "), state:"ready", tag:"本轮材料"});

    const activeCount = percepts.filter(item => item.state === "ready").length;
    /* === 顶部态势板 ===
       四张卡按能力簇分板，每块只用一个主视觉说话：环境卡给天气读数、模型卡给磁贴、
       设备与外部卡突出定位与余额，状态行显示实际读数、时间及缺失原因。
       卡头与通道直接选择仪表盘下方的真实配置页，不在卡内重复展开状态列表。 */
    const boardRows = id => percepts.filter(item => item.board === id);
    const boardSpecs = [
      {id:"environment", tone:"environment", icon:"cloud-sun", title:"时空 · 环境", tab:tabPlace},
      {id:"models", tone:"models", icon:"cpu", title:"模型能力", tab:tabModel, modelTab:"fn"},
      {id:"devices", tone:"devices", icon:"radar", title:"现实感知功能", tab:tabDevice},
      {id:"external", tone:"external", icon:"layers-2", title:"外部与记录", tab:"config-news:perception-detail-external"},
    ];
    const destinationAttrs = (destination, modelTab="") => `data-board-goto="${esc(destination)}" aria-controls="${esc(destination.split(":")[0])}" aria-expanded="false"${modelTab ? ` data-board-model-tab="${esc(modelTab)}"` : ""}`;
    const channelAttrs = item => `id="perception-channel-${item.id}" ${destinationAttrs(item.tab, item.modelTab)} title="${esc(`${item.tag} · ${item.value} · ${item.detail}`)}" aria-label="${esc(`${item.title}：${item.tag}。${item.value}。${item.detail}。打开对应配置`)}"`;
    const channelById = id => percepts.find(item => item.id === id);
    const timeMarkup = (value, fallback="") => {
      const date = typeof value === "number" ? new Date(value * 1000) : new Date(value || "");
      return Number.isNaN(date.getTime()) ? fallback ? `<small class="perception-reading-age">${esc(fallback)}</small>` : ""
        : `<time class="perception-reading-age" datetime="${esc(date.toISOString())}" title="${esc(date.toLocaleString("zh-CN", {timeZone:clockZone()}))}">${esc(ageLabel(value))}</time>`;
    };
    const badgeMarkup = (state, label) => `<span class="perception-reading-badge is-${state}"><i class="perception-dot" aria-hidden="true"></i>${esc(label)}</span>`;
    const readingRow = (item, label, value, observedAt, fallback="") => `<button type="button" class="perception-reading-row is-${item.state}" ${channelAttrs(item)}>
      <span class="perception-reading-icon">${icon(item.icon)}</span><strong>${esc(label)}</strong>
      <span class="perception-reading-value">${esc(value)}</span>${timeMarkup(observedAt, fallback)}<i class="perception-dot" aria-hidden="true"></i>
    </button>`;
    const deviceCard = (() => {
      const location = channelById("device-location"), screen = channelById("device-screen"), phone = channelById("device-phone");
      const camera = channelById("device-camera"), mihome = channelById("device-mihome");
      const cameraAuthorized = cameraResult.state === "available" || cameraResult.state === "ready";
      const cameraTag = cameraAuthorized ? "已授权" : runtimeState === "error" ? "读取失败" : runtimeState === "loading" ? "读取中" : /consent/.test(cameraResult.reason || "") ? "待授权" : "未就绪";
      const mihomeLabel = mihome ? mihomeSummary : mihomeState === "disabled" ? "未启用" : mihomeState === "loading" ? "读取中" : "暂不可读";
      return `<div class="perception-reading-card">
        <button type="button" class="perception-feature is-location is-${location.state}" ${channelAttrs(location)}>
          <span class="perception-feature-icon">${icon("map-pin")}</span>
          <span class="perception-feature-copy"><small>当前定位</small><strong>${esc(mobileValue)}</strong><span>${mobile.location?.available ? "最近授权快照" : "点击配置定位与手机授权"}</span></span>
          <span class="perception-feature-meta">${badgeMarkup(location.state, mobile.location?.available ? "最近一次定位" : location.tag)}${timeMarkup(mobile.location?.available ? mobile.location.captured_at : null)}</span>
        </button>
        ${readingRow(screen, "识屏", screenResult.state === "available" ? `上次识别 · ${screenResult.surface || "屏幕画面"}` : screenValue, screenResult.state === "available" ? screenResult.created_at || screenResult.captured_at : null)}
        ${readingRow(phone, "手机状态", phoneValue, phoneAvailable ? device.last_report_at || activity.last_report_at || realityResult.captured_at : null)}
        <div class="perception-board-footer"><span>设备授权</span><div class="perception-authorization-chips">
          <button type="button" class="perception-authorization-chip is-${cameraAuthorized ? "ready" : camera.state}" ${channelAttrs(camera)}><i class="perception-dot" aria-hidden="true"></i>摄像头 · ${esc(cameraTag)}</button>
          <button type="button" class="perception-authorization-chip is-${mihome?.state || (mihomeState === "disabled" ? "off" : "pending")}" ${mihome ? channelAttrs(mihome) : destinationAttrs(tabDevice)} title="${esc(mihome?.detail || mihomeLabel)}"><i class="perception-dot" aria-hidden="true"></i>米家 · ${esc(mihomeLabel)}</button>
        </div></div>
      </div>`;
    })();
    const externalCard = (() => {
      const balance = channelById("ext-balance"), external = channelById("ext-external"), recall = channelById("device-recalls"), injection = channelById("ext-injection");
      const balanceReadLabel = balanceObservation ? balanceObservationIsDraft ? "草稿测试结果" : "最近一次查询"
        : balanceTesting || balanceStatusLoading ? "查询中" : balanceTestError || balanceError || balanceStatusError ? "读取失败"
          : balanceStatus?.state === "not_configured" || balanceConfig ? "未配置" : balanceConfigLoading ? "读取中" : balanceSourceInvalid ? "配置无效" : "等待读取";
      const balanceReadDetail = balanceTestError || balanceError || balanceStatusError || (balanceObservation ? balanceObservation.provider_label || "NewAPI"
        : balanceSourceInvalid ? "请检查数据源配置" : balanceSourceConfigured ? "读取服务余额中" : "配置数据源后读取服务余额");
      const newsSummary = !ready ? externalValue : networkSucceeded
        ? `${Number.isInteger(news.itemCount) && news.itemCount >= 0 ? `最近检查 ${news.itemCount} 条` : "最近检查通过"} · ${news.label || "资讯来源"}`
        : news.networkStatus === "failed" ? "上次检查失败 · 请检查来源" : externalValue;
      return `<div class="perception-reading-card">
        <button type="button" class="perception-feature is-balance is-${balance.state}" ${channelAttrs(balance)}>
          <span class="perception-feature-icon">${icon("circle-dollar-sign")}</span>
          <span class="perception-feature-copy"><small>余额感知</small><strong>${balanceObservation ? `<span class="perception-balance-unit">${esc(balanceObservation.currency_label || "额度")}</span> ${esc(formatBalanceAmount(balanceObservation.amount))}` : "尚无余额读数"}</strong><span>${esc(balanceReadDetail)}</span></span>
          <span class="perception-feature-meta">${badgeMarkup(balance.state, balanceReadLabel)}${timeMarkup(balanceObservation?.observed_at)}</span>
        </button>
        ${readingRow(external, "外部资讯", newsSummary, news.lastAttemptAt || news.lastCheckedAt)}
        ${readingRow(recall, "撤回记录", recallState === "ready" && recallStatus?.enabled !== false ? `当前窗口 ${recalls.length} 条可读记录` : recallValue, recalls[0]?.withdrawn_at, recalls[0]?.local_time)}
        <div class="perception-board-footer">${injection ? `<button type="button" class="perception-injection-summary" ${channelAttrs(injection)}>${icon("layers-3")}<span>其他注入 · 本轮 ${injectionLabels.length} 项 · ${esc(injectionLabels.join("、"))}</span></button>` : '<span>本轮暂无其他注入</span>'}</div>
      </div>`;
    })();
    const weatherIconName = condition => {
      const text = String(condition || "");
      if (/雨|雪|雷|雾|霾/.test(text)) return "cloud-rain";
      if (/阴/.test(text)) return "cloud";
      return "cloud-sun";
    };
    /* 环境卡：地点、时间、更新时刻、预警状态、温度读数全靠排版层级说话，不写标签行。 */
    const weatherCard = (() => {
      const item = percepts.find(entry => entry.id === "env-weather");
      const available = weather.state === "available";
      const place = weather.location || locationName || (!ready ? `角色地点${configurationState}` : "尚未设置角色地点");
      const alertState = alertList.length ? "实时预警" : runtimeState === "error" ? "读取失败"
        : runtimeState === "loading" ? "待读取" : weather.state === "disabled" || weather.state === "unconfigured" ? "未启用"
          : !available || configurationFailed ? "暂不可读" : environment.alertsReady ? "当前无预警" : "未配置";
      const metaBits = [weather.humidity_pct == null ? "" : `湿度 ${weather.humidity_pct}%`,
        weather.wind_kph == null ? "" : `风 ${weather.wind_kph} km/h`].filter(Boolean);
      return `<div class="perception-wx">
        <div class="perception-wx-top">
          <button type="button" class="perception-wx-place" ${destinationAttrs(tabPlace)} aria-label="所在地：${esc(place)}。打开所在地与天气配置">${icon("map-pin")}<b>${esc(place)}</b></button>
          <button type="button" class="perception-wx-time" ${destinationAttrs(tabCalendar)} aria-label="打开日期与历法上下文配置" data-context-clock-time>--:--</button>
        </div>
        <div class="perception-wx-sub">
          <button type="button" class="perception-wx-date" ${destinationAttrs(tabCalendar)} aria-label="日期与历法：${esc(calendarView?.detail || "服务端日历暂不可用")}。打开日期与历法上下文配置"><i data-context-clock-date>${runtimeState === "loading" ? "正在读取服务端日历…" : ""}</i><i data-context-clock-lunar></i><em data-context-clock-tag hidden></em></button>
          <button type="button" class="perception-wx-chip is-${alertState === "实时预警" ? "alert" : alertState === "当前无预警" ? "ready" : "off"}" ${destinationAttrs(tabPlace)} title="${esc(alertList.map(item => item.title || item.event_name || "官方预警").join(" · "))}">${icon("triangle-alert")}<span>天气预警 · ${alertState}</span></button>
        </div>
        <button type="button" class="perception-wx-main" ${channelAttrs(item)}>
          <span class="perception-wx-icon">${icon(available ? weatherIconName(weather.condition) : "cloud")}</span>
          <span class="perception-wx-temp">${esc(available && weather.temperature_c != null ? String(weather.temperature_c) : "—")}<i>°C</i></span>
          <span class="perception-wx-meta">
            <strong>${esc(available ? weather.condition || "实况已读取" : item.value)}</strong>
            <small>${esc(metaBits.length ? metaBits.join(" · ") : item.detail)}</small>
          </span>
        </button>
        ${calendarView?.detail ? `<button type="button" class="perception-wx-calendar" ${destinationAttrs(tabCalendar)}>${esc(calendarView.detail)}</button>` : ""}
        <button type="button" class="perception-wx-events" ${destinationAttrs("config-environment:perception-detail-important-days")}>${icon("calendar-heart")}<span>${events.length ? events.map(event => `${esc(event.label)} · ${event.days === 0 ? "今天" : event.days === 1 ? "明天" : `${event.days} 天后`}`).join("；") : "配置重要日子与饭点"}</span></button>
      </div>`;
    })();
    const boardBodyMarkup = spec => {
      if (spec.id === "environment") return weatherCard;
      if (spec.id === "models") return `<div class="perception-mtiles">${boardRows("models").map(item =>
        `<button type="button" class="perception-mtile is-${item.state}" ${channelAttrs(item)}>${icon(item.icon)}<span class="perception-mtile-title">${esc(item.title)}</span><strong class="perception-mtile-model">${esc(item.value)}</strong></button>`).join("")}</div>`;
      return spec.id === "devices" ? deviceCard : externalCard;
    };
    const boardMarkup = `<section class="perception-board" aria-label="感知态势板">${boardSpecs.map(spec => {
      const rows = boardRows(spec.id);
      const live = rows.filter(item => item.state === "ready").length;
      const subtitle = spec.id === "environment" || spec.id === "models" ? ""
        : `<span class="perception-board-channels">${rows.length} 通道</span>`;
      return `<article class="perception-board-card is-${spec.tone}">
        <button type="button" id="perception-board-toggle-${spec.id}" class="perception-board-head" data-perception-board="${spec.id}" ${destinationAttrs(spec.tab, spec.modelTab)}
          aria-label="${esc(spec.title)}：${rows.length} 条通道，${live} 项实况在线。打开下方配置">
          <span class="perception-board-icon">${icon(spec.icon)}</span>
          <span class="perception-board-title"><strong>${esc(spec.title)}</strong></span>${subtitle}
          <span class="perception-board-chevron">${icon("arrow-down-right")}</span>
        </button>
        <div class="perception-board-body">${boardBodyMarkup(spec)}</div>
      </article>`;
    }).join("")}</section>`;

    /* 页头保留真实的整体读数：通道数与"实况在线"都由当前 percepts 现算，
       不写死总数——模型视觉、天气预警、米家这类通道本来就时有时无。 */
    /* 同步状态必须说出来：日期与天气都绑在服务端快照上，读失败时页面会停在旧值，
       不给提示就等于拿过期读数冒充当前实况。 */
    const readStates = [runtimeState, modelState, voiceState, imageState, semanticState, recallState];
    const syncState = readStates.includes("error") || configurationFailed ? {label:"读取未完成", tone:"warn", icon:"triangle-alert"}
      : readStates.includes("loading") || !ready ? {label:"正在读取实况", tone:"pending", icon:"loader-circle"}
        : ready ? {label:"真实状态已同步", tone:"ready", icon:"check"} : {label:"角色上下文待读取", tone:"pending", icon:"clock"};
    const barMarkup = `<header class="perception-board-bar">
      <div>
        <span class="perception-kicker">实时感知</span>
        <h1>感知仪表盘</h1>
      </div>
      <span class="perception-board-count">
        <span class="perception-board-sync is-${syncState.tone}" role="status" aria-live="polite">${icon(syncState.icon)}${syncState.label}</span>
        <b>${percepts.length} 个感知通道 · ${activeCount} 项实况在线</b>
        <button type="button" id="perception-status-refresh" class="button small" data-context-refresh>${icon("refresh-cw")}重新读取状态</button>
      </span>
    </header>`;
    root.innerHTML = `${barMarkup}${boardMarkup}`;
    syncSelection();
    if (balanceSource) renderBalanceSource();

    // 保留工作区处理逻辑
    const page = root.parentElement;
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
    if (focusedId) root.querySelector(`#${focusedId}`)?.focus?.({preventScroll:true});
    window.lucide?.createIcons({attrs:{"aria-hidden":"true"}});
    lastDay = ""; updateClock();
  }
  async function refreshModel(ticket = generation) {
    if (!validRoot(ticket)) return;
    modelState = "loading"; render();
    try {
      const endpoint = product.role()?.model_api;
      if (typeof endpoint !== "string" || !endpoint) throw new Error("missing model route");
      const response = await product.request("GET", product.relative(endpoint));
      const value = product.unwrap(response);
      if (!validRoot(ticket)) return;
      if (!Array.isArray(value.tasks) || !Array.isArray(value.providers)) throw new Error("invalid model route");
      modelStatus = value; modelState = "ready"; rememberOverview("modelStatus", value, "modelState", "ready");
    } catch (_) {
      if (!validRoot(ticket)) return;
      modelStatus = null; modelState = "error";
      forgetOverview("modelStatus", "modelState");
    }
    render();
  }
  async function refreshVoice(ticket = generation) {
    if (!validRoot(ticket)) return;
    voiceState = "loading"; render();
    try {
      const endpoint = product.role()?.model_api;
      if (typeof endpoint !== "string" || !endpoint) throw new Error("missing voice route");
      const value = product.unwrap(await product.request("GET", product.relative(endpoint.replace(/\/$/, "") + "/voice")));
      if (!validRoot(ticket)) return;
      if (!Array.isArray(value.languages) || !Array.isArray(value.providers)) throw new Error("invalid voice status");
      voiceStatus = value; voiceState = "ready"; rememberOverview("voiceStatus", value, "voiceState", "ready");
    } catch (_) {
      if (!validRoot(ticket)) return;
      voiceStatus = null; voiceState = "error";
      forgetOverview("voiceStatus", "voiceState");
    }
    render();
  }
  async function refreshImage(ticket = generation) {
    if (!validRoot(ticket)) return;
    imageState = "loading"; render();
    try {
      const endpoint = product.role()?.model_api;
      if (typeof endpoint !== "string" || !endpoint) throw new Error("missing image route");
      const value = product.unwrap(await product.request("GET", product.relative(endpoint.replace(/\/$/, "") + "/image")));
      if (!validRoot(ticket)) return;
      if (!Array.isArray(value.actions)) throw new Error("invalid image status");
      imageStatus = value; imageState = "ready"; rememberOverview("imageStatus", value, "imageState", "ready");
    } catch (_) {
      if (!validRoot(ticket)) return;
      imageStatus = null; imageState = "error";
      forgetOverview("imageStatus", "imageState");
    }
    render();
  }
  async function refreshSemanticStatus(ticket = generation) {
    if (!validRoot(ticket)) return;
    semanticState = "loading"; render();
    try {
      const bridge = product.bridgeNow?.() || await product.bridgeFor();
      const value = product.unwrap(await bridge.apiGet("semantic", {...product.selection(), kind:"reaction"}));
      if (!validRoot(ticket)) return;
      if (!value || typeof value !== "object") throw new Error("invalid semantic status");
      semanticStatus = value; semanticState = "ready"; rememberOverview("semanticStatus", value, "semanticState", "ready");
    } catch (_) {
      if (!validRoot(ticket)) return;
      semanticStatus = null; semanticState = "error";
      forgetOverview("semanticStatus", "semanticState");
    }
    render();
  }
  async function refreshRecalls(ticket = generation) {
    if (!validRoot(ticket)) return;
    recallState = "loading"; render();
    try {
      const bridge = product.bridgeNow?.() || await product.bridgeFor();
      const value = product.unwrap(await bridge.apiGet("reply/recalls", {limit:5}));
      if (!validRoot(ticket)) return;
      if (!Array.isArray(value.entries)) throw new Error("invalid recall status");
      recallStatus = value; recallState = "ready"; rememberOverview("recallStatus", value, "recallState", "ready");
    } catch (_) {
      if (!validRoot(ticket)) return;
      recallStatus = null; recallState = "error";
      forgetOverview("recallStatus", "recallState");
    }
    render();
  }
  async function refreshMihome(ticket = generation) {
    if (!validRoot(ticket)) return;
    mihomeState = "loading"; render();
    try {
      const bridge = product.bridgeNow?.() || await product.bridgeFor();
      const value = product.unwrap(await bridge.apiGet("extensions", {}));
      if (!validRoot(ticket)) return;
      const reality = value?.extensions?.reality;
      const settings = reality?.settings;
      const mihome = reality?.management?.mihome;
      if (!settings || !mihome || mihome.available === false || !Array.isArray(mihome.devices)
          || typeof mihome.tool_settings?.enable_readonly_tool !== "boolean")
        throw new Error("invalid native MiHome status");
      if (settings.enabled === false || settings.mihome?.enabled === false
          || !mihome.tool_settings.enable_readonly_tool) {
        mihomeStatus = null; mihomeState = "disabled"; forgetOverview("mihomeStatus", "mihomeState");
        render();
        return;
      }
      mihomeStatus = {
        enabled:true,
        snapshot_at:typeof mihome.snapshot_at === "string" ? mihome.snapshot_at : "",
        devices:mihome.devices.filter(item => item?.configured === true || item?.aliases?.length)
          .map(item => ({
            configured:true,
            name:typeof item.name === "string" ? item.name.slice(0, 160) : "",
            aliases:Array.isArray(item.aliases)
              ? item.aliases.filter(alias => typeof alias === "string").slice(0, 20).map(alias => alias.slice(0, 120)) : [],
            online:item.online === true ? true : item.online === false ? false : null,
          })),
      };
      mihomeState = "ready";
      rememberOverview("mihomeStatus", mihomeStatus, "mihomeState", "ready");
    } catch (_) {
      if (!validRoot(ticket)) return;
      mihomeStatus = null; mihomeState = "unavailable";
      forgetOverview("mihomeStatus", "mihomeState");
    }
    render();
  }
  async function refreshRuntime(ticket = generation) {
    if (!validRoot(ticket)) return;
    runtimeState = "loading"; render();
    try {
      const endpoint = product.role()?.perception_native_api;
      if (typeof endpoint !== "string" || !endpoint) throw new Error("missing perception runtime route");
      const route = endpoint.replace(/\/$/, "") + "/runtime";
      const value = product.unwrap(await product.request("GET", product.relative(route)));
      if (!validRoot(ticket)) return;
      if (!value || typeof value !== "object" || !value.weather || !value.screen || !value.reality || !value.calendar)
        throw new Error("invalid perception runtime snapshot");
      runtimeSnapshot = value; runtimeState = "ready"; rememberOverview("runtimeSnapshot", value, "runtimeState", "ready");
    } catch (_) {
      if (!validRoot(ticket)) return;
      runtimeSnapshot = null; runtimeState = "error";
      forgetOverview("runtimeSnapshot", "runtimeState");
    }
    render();
  }
  async function requestCurrentBalance(ticket) {
    const endpoint = product.role()?.model_api;
    if (typeof endpoint !== "string" || !endpoint) throw new Error("当前角色没有可用的模型余额接口。");
    const route = product.relative(endpoint.replace(/\/$/, "") + "/balance");
    const value = product.unwrap(await product.request("GET", route));
    if (!validRoot(ticket)) return null;
    const status = safeBalanceStatus(value);
    if (!status) throw new Error("余额接口返回的数据无效。");
    return status;
  }
  function unavailableBalanceStatus() {
    const configured = balanceConfig?.source_state === "configured" || balanceConfig?.source_state === "invalid";
    return {configured, available:false, provider:balanceConfig?.provider || "newapi",
      provider_label:"NewAPI", currency_label:"额度", amount:null, observed_at:"",
      state:configured ? "unavailable" : "not_configured"};
  }
  async function refreshCurrentBalance(ticket = generation) {
    if (!validRoot(ticket)) return;
    if (balanceStatusLoading) {balanceStatusRefreshQueued = true; return;}
    balanceStatusLoading = true; balanceStatusError = ""; render();
    try {
      const status = await requestCurrentBalance(ticket);
      if (!validRoot(ticket) || !status) return;
      balanceStatus = status;
      balanceStatusError = balanceStatusMessage(status);
    } catch (error) {
      if (!validRoot(ticket)) return;
      balanceStatus = unavailableBalanceStatus();
      balanceStatusError = error.message || "余额读取失败，请检查数据源配置。";
    } finally {
      if (validRoot(ticket)) {
        balanceStatusLoading = false;
        rememberBalanceCache();
        render();
        if (balanceStatusRefreshQueued) {
          balanceStatusRefreshQueued = false;
          void refreshCurrentBalance(ticket);
        }
      }
    }
  }
  async function readBalanceConfig(ticket = generation) {
    if (!validRoot(ticket) || balanceConfigLoading || balanceSaving || balanceTesting) return;
    balanceConfigLoading = true; balanceError = ""; balanceMessage = ""; render();
    try {
      const bridge = product.bridgeNow?.() || (product.bridgeFor ? await product.bridgeFor() : window.AstrBotPluginPage);
      if (!bridge?.apiGet) throw new Error("页面连接尚未就绪，请稍后重试。");
      const value = product.unwrap(await bridge.apiGet("host-options/balance"));
      if (!validRoot(ticket)) return;
      if (!value?.service_balance || !value?.edit_tokens?.balance) throw new Error("余额数据源配置暂不可读。");
      balanceConfig = value.service_balance;
      balanceConfig.edit_token = value.edit_tokens.balance;
      if ((balanceResultConfigToken && balanceResultConfigToken !== balanceConfig.edit_token)
          || (balanceResultConfigKey && balanceResultConfigKey !== balanceConfigKey(balanceConfig))) clearBalanceResult();
      if (!balanceDraft) balanceDraft = emptyBalanceDraft(balanceConfig);
      rememberBalanceCache();
    } catch (error) {
      if (!validRoot(ticket)) return;
      balanceConfig = null; balanceDraft = null;
      clearBalanceResult();
      balanceError = error.message || "余额数据源配置暂不可读。";
    } finally {
      if (validRoot(ticket)) {balanceConfigLoading = false; render();}
    }
  }
  async function saveBalanceConfig(event) {
    const form = event.target?.closest?.("[data-balance-form]");
    if (!form) return;
    event.preventDefault();
    if (!balanceConfig?.edit_token || balanceSaving || balanceTesting) return;
    const pendingFocus = balanceFocus(form);
    const draft = rememberBalanceDraft(form);
    const {url, api_key:apiKey, user_id:userId, value_divisor:divisor, clear_configuration:clear} = draft;
    if (!clear && (!url || !/^https:\/\//i.test(url))) {
      balanceError = "请填写有效的 HTTPS NewAPI 地址。"; render(); return;
    }
    if (!clear && !apiKey && !balanceConfig.has_api_key) {
      balanceError = "首次配置需要填写 NewAPI 管理令牌。"; render(); return;
    }
    if (!clear && userId && !/^[1-9][0-9]{0,18}$/.test(userId)) {
      balanceError = "NewAPI 用户 ID 必须为正整数。"; render(); return;
    }
    if (!clear && (!divisor || !Number.isFinite(Number(divisor)) || Number(divisor) <= 0)) {
      balanceError = "额度单位除数必须是大于 0 的数字。"; render(); return;
    }
    balanceSaving = true; balanceError = ""; balanceMessage = "";
    balanceTestError = ""; clearBalanceResult();
    const ticket = generation;
    render();
    try {
      const bridge = product.bridgeNow?.() || (product.bridgeFor ? await product.bridgeFor() : window.AstrBotPluginPage);
      if (!bridge?.apiPost) throw new Error("页面连接尚未就绪，请稍后重试。");
      const changes = clear ? {clear_configuration:true} : {url, api_key:apiKey, user_id:userId, value_divisor:divisor};
      const value = product.unwrap(await bridge.apiPost("host-options/balance", {
        edit_token:balanceConfig.edit_token, changes,
      }));
      if (!validRoot(ticket)) return;
      balanceConfig = value.service_balance;
      balanceConfig.edit_token = value.edit_tokens.balance;
      balanceMessage = clear ? "已移除本页数据源；环境变量数据源仍可继续使用。" : "已保存并立即生效。";
      balanceDraft = emptyBalanceDraft(balanceConfig);
      clearBalanceResult(); balanceTestError = "";
      void refreshCurrentBalance(ticket);
    } catch (error) {
      if (!validRoot(ticket)) return;
      balanceError = error.message || "余额数据源保存失败。";
    } finally {
      if (validRoot(ticket)) {
        balanceSaving = false;
        const focusLost = window.document?.activeElement === window.document?.body;
        render();
        if (focusLost && pendingFocus) restoreBalanceFocus(pendingFocus);
      }
    }
  }
  const balanceTestErrors = {
    balance_test_timeout:"NewAPI 查询超时，请核对地址和服务状态。",
    balance_test_failed:"连接失败，请检查令牌权限、用户 ID 和地址。",
    host_options_conflict:"设置已在别处更新，请重新读取后重试。",
    dashboard_identity_required:"请登录 AstrBot Dashboard 后再测试数据源。",
  };
  async function testBalanceConfig(form) {
    if (!balanceConfig?.edit_token || balanceSaving || balanceTesting
        || (balanceStatusLoading && balanceDraftIsCurrent())) return;
    const pendingFocus = balanceFocus(form);
    const draft = rememberBalanceDraft(form);
    let changes, usesCurrent = false;
    if (draft.clear_configuration) {
      balanceTestError = "先取消移除数据源，再测试当前连接。"; render(); return;
    }
    if (balanceDraftIsCurrent()) {
      usesCurrent = true;
    } else {
      if (!draft.url || !/^https:\/\//i.test(draft.url)) {
        balanceTestError = "请填写有效的 HTTPS NewAPI 地址。"; render(); return;
      }
      if (!draft.api_key && !balanceConfig.has_api_key) {
        balanceTestError = "请填写带 profile:read 权限的 NewAPI 管理令牌后再测试。"; render(); return;
      }
      if (draft.user_id && !/^[1-9][0-9]{0,18}$/.test(draft.user_id)) {
        balanceTestError = "NewAPI 用户 ID 必须为正整数。"; render(); return;
      }
      if (!draft.value_divisor || !Number.isFinite(Number(draft.value_divisor)) || Number(draft.value_divisor) <= 0) {
        balanceTestError = "额度单位除数必须是大于 0 的数字。"; render(); return;
      }
      changes = {url:draft.url, api_key:draft.api_key, user_id:draft.user_id,
        value_divisor:draft.value_divisor};
    }
    balanceTesting = true; balanceTestError = ""; clearBalanceResult();
    const ticket = generation;
    render();
    try {
      if (usesCurrent) {
        const status = await requestCurrentBalance(ticket);
        if (!validRoot(ticket) || !status) return;
        balanceStatus = status;
        balanceStatusError = balanceStatusMessage(status);
        balanceTestError = balanceStatusError;
        if (status.available) {
          balanceTestError = "";
          balanceMessage = "余额已重新读取。";
        }
      } else {
        const bridge = product.bridgeNow?.() || (product.bridgeFor ? await product.bridgeFor() : window.AstrBotPluginPage);
        if (!bridge?.apiPost) throw new Error("页面连接尚未就绪，请稍后重试。");
        const value = product.unwrap(await bridge.apiPost("host-options/balance/test", {
          edit_token:balanceConfig.edit_token, changes,
        }));
        if (!validRoot(ticket)) return;
        if (value?.tested !== true || value?.available !== true || !["number", "string"].includes(typeof value.amount)
            || String(value.amount).trim() === "" || !Number.isFinite(Number(value.amount)) || Number(value.amount) < 0)
          throw new Error("NewAPI 未返回可用余额，请检查配置后重试。");
        balanceTestResult = {...value, amount:formatBalanceAmount(value.amount)};
        balanceResultScope = scope;
        balanceResultConfigToken = "";
        balanceResultConfigKey = "";
        balanceResultIsDraft = true;
      }
      rememberBalanceCache();
    } catch (error) {
      if (!validRoot(ticket)) return;
      if (usesCurrent) {
        balanceStatus = unavailableBalanceStatus();
        balanceStatusError = error.message || "余额读取失败，请检查数据源配置。";
      }
      const code = error.code || "";
      balanceTestError = balanceTestErrors[code]
        || (error.message && error.message !== code ? error.message : "连接失败，请检查数据源配置后重试。");
    } finally {
      if (validRoot(ticket)) {
        balanceTesting = false;
        const focusLost = window.document?.activeElement === window.document?.body;
        render();
        if (focusLost && pendingFocus) restoreBalanceFocus(pendingFocus);
      }
    }
  }
  function input(event) {
    const field = event.target?.closest?.("[data-balance-field]");
    if (!field) return;
    const name = field.dataset?.balanceField || field.name;
    if (!["url", "user_id", "value_divisor", "api_key", "clear_configuration"].includes(name)) return;
    if (!balanceDraft) balanceDraft = emptyBalanceDraft(balanceConfig);
    balanceDraft[name] = name === "clear_configuration" ? field.checked === true : field.value;
    const hadDraftObservation = !!balanceTestResult && balanceResultIsDraft;
    balanceError = ""; balanceTestError = "";
    if (hadDraftObservation) clearBalanceResult();
    else rememberBalanceCache();
    const form = field.closest?.("[data-balance-form]");
    const result = form?.querySelector("[data-balance-test-result]");
    if (result && hadDraftObservation) result.hidden = true;
    const test = form?.querySelector("[data-balance-test]");
    if (test) test.disabled = balanceSaving || balanceTesting || (balanceStatusLoading && balanceDraftIsCurrent()) || balanceDraft.clear_configuration
      || !(balanceDraftIsCurrent() || (balanceDraft.url && (balanceDraft.api_key || balanceConfig?.has_api_key)));
    if (hadDraftObservation) render({balanceSource:false});
  }
  function click(event) {
    const testButton = event.target.closest("[data-balance-test]");
    if (testButton) {
      event.preventDefault();
      const form = testButton.closest("[data-balance-form]");
      if (form) void testBalanceConfig(form);
      return;
    }

    const gotoButton = event.target.closest("[data-board-goto]");
    if (gotoButton) {
      /* 配置本体由页面下方的分区面板维护，这里只负责切过去，
         避免在卡里再写一遍表单、两边各存一份状态。 */
      window.CompanionPerceptionTabs?.activate?.(gotoButton.dataset.boardGoto, {
        focus:true, scroll:true, modelTab:gotoButton.dataset.boardModelTab || "",
      });
      return;
    }
    if (event.target.closest("[data-balance-reload]")) {readBalanceConfig(generation); return;}
    if (event.target.closest("[data-balance-refresh]")) {void refreshCurrentBalance(generation); return;}
    if (!event.target.closest("[data-context-refresh]")) return;
    window.CompanionNativePerceptionPage?.refresh?.();
    const ticket = generation;
    refreshModel(ticket); refreshRuntime(ticket); refreshVoice(ticket); refreshImage(ticket);
    refreshSemanticStatus(ticket); refreshRecalls(ticket); refreshMihome(ticket);
    void refreshCurrentBalance(ticket);
    if (!balanceConfig || balanceDraftIsCurrent()) void readBalanceConfig(ticket);
  }
  function change(event) {
    input(event);
    const clear = event.target.closest('[name="clear_configuration"]');
    if (!clear) return;
    const form = clear.closest("[data-balance-form]");
    if (!form) return;
    for (const field of form.querySelectorAll('[name="url"], [name="user_id"], [name="value_divisor"], [name="api_key"]'))
      field.disabled = clear.checked;
    const button = form.querySelector('button[type="submit"]');
    if (button) button.textContent = clear.checked ? "移除数据源" : "保存数据源";
    const test = form.querySelector("[data-balance-test]");
    if (test) test.disabled = clear.checked || balanceTesting || balanceSaving
      || (balanceStatusLoading && balanceDraftIsCurrent());
  }
  function mount(node) {
    unmount();
    const nextScope = activeScopeKey();
    root = node; scope = nextScope; abort = new AbortController();
    overviewRouteKey = routeKey();
    restoreBalanceCache(nextScope);
    balanceWorkspace = root.parentElement?.querySelector("#perceptionBalanceSourceWorkspace") || null;
    const ticket = ++generation;
    const cached = overviewCache.get(`${scope}:${overviewRouteKey}`) || {};
    snapshot = cached.snapshot || null; runtimeSnapshot = cached.runtimeSnapshot || null;
    runtimeState = cached.runtimeState || "loading";
    modelStatus = cached.modelStatus || null; modelState = cached.modelState || "loading";
    voiceStatus = cached.voiceStatus || null; voiceState = cached.voiceState || "loading";
    imageStatus = cached.imageStatus || null; imageState = cached.imageState || "loading";
    semanticStatus = cached.semanticStatus || null; semanticState = cached.semanticState || "loading";
    recallStatus = cached.recallStatus || null; recallState = cached.recallState || "loading";
    mihomeStatus = cached.mihomeStatus || null; mihomeState = cached.mihomeState || "loading";
    root.addEventListener("click", click, {signal:abort.signal});
    if (balanceWorkspace) {
      balanceWorkspace.addEventListener("click", click, {signal:abort.signal});
      balanceWorkspace.addEventListener("submit", saveBalanceConfig, {signal:abort.signal});
      balanceWorkspace.addEventListener("input", input, {signal:abort.signal});
      balanceWorkspace.addEventListener("change", change, {signal:abort.signal});
    }
    unsubscribe = window.CompanionNativePerceptionPage?.subscribe?.(next => {
      if (!validRoot(ticket)) return;
      /* native 页刚挂载时会先发 loading。已有成功快照时保留它，避免切页
         回来出现一整块空白；明确失败仍清掉旧快照并展示失败状态。 */
      if (next?.ready === true || !snapshot || (next?.loading === false && next?.error)) snapshot = next;
      if (snapshot?.ready === true) rememberOverview("snapshot", snapshot);
      else if (next?.loading === false && next?.error) forgetOverview("snapshot");
      render();
    }) || null;
    render();
    refreshModel(ticket); refreshRuntime(ticket); refreshVoice(ticket); refreshImage(ticket);
    refreshSemanticStatus(ticket); refreshRecalls(ticket); refreshMihome(ticket); readBalanceConfig(ticket);
    void refreshCurrentBalance(ticket);
    clockTimer = setInterval(updateClock, 1000);
  }
  function unmount() {
    rememberBalanceCache();
    generation++; abort?.abort(); abort = null; unsubscribe?.(); unsubscribe = null;
    if (clockTimer) clearInterval(clockTimer);
    clockTimer = null; root = null; scope = ""; overviewRouteKey = ""; snapshot = null; runtimeSnapshot = null; runtimeState = "loading";
    modelStatus = null; modelState = "loading"; voiceStatus = null; voiceState = "loading";
    imageStatus = null; imageState = "loading"; semanticStatus = null; semanticState = "loading";
    recallStatus = null; recallState = "loading"; mihomeStatus = null; mihomeState = "loading";
    lastDay = ""; selectedDestination = ""; selectedModelTab = "";
    balanceWorkspace = null; balanceMarkup = "";
    balanceConfig = null; balanceDraft = null; balanceExpanded = false; balanceConfigLoading = false;
    balanceStatus = null; balanceStatusLoading = false; balanceStatusRefreshQueued = false; balanceStatusError = "";
    balanceSaving = false; balanceTesting = false;
    balanceTestResult = null; balanceResultScope = ""; balanceResultConfigToken = ""; balanceResultConfigKey = ""; balanceResultIsDraft = false;
    balanceMessage = ""; balanceError = ""; balanceTestError = "";
  }
  return {mount, unmount, select, refresh:refreshRuntime, upcomingDates};
})();
