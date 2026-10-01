/* V2-owned perception settings for the selected private target and role. */
"use strict";
window.CompanionNativePerceptionPage = (() => {
  const product = window.CompanionProduct;
  const prefix = "/astrbot_plugin_private_companion_v2/";
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const errors = {
    configuration_revision_conflict:"配置已变化，草稿仍在。刷新后核对，再采用最新版本保存。",
    idempotency_key_conflict:"原请求与当前内容不一致，请刷新后核对。",
    core_access_required:"当前账号没有管理权限。",
    dashboard_identity_required:"请从已登录的管理界面打开陪伴小屋。",
    contact_private_required:"这项设置只适用于私聊对象。",
    staging_not_initialized:"请先在账号与会话加载 V2 运行实例。",
    staging_host_terminated:"宿主已停止，请重新打开插件页面。",
    bridge_timeout:"连接超时，原请求可能已保存；请核对后重试。",
    invalid_response:"配置数据不完整，请刷新核对。",
  };
  /* 后端把机器码放在信封的 message 上（页面桥只转发 message），取码要同时看
     data.code 与 message，不能只认前者。 */
  const CODE = /^[a-z][a-z0-9_]{2,60}$/;
  const codeOf = wrapped => wrapped?.data?.code
    || (CODE.test(wrapped?.message || "") ? wrapped.message : "") || "";
  const newsSourceOptions = [
    ["host", "宿主默认来源"],
    ["disabled", "停用资讯源"],
    ["bilibili", "B 站动态"],
    ["rss", "RSS / Atom"],
    ["json", "HTTPS JSON"],
  ];
  const fields = {
    environment:[
      ["planning_timezone","角色日历时区","text","用于角色计划和天气地点的日期判断。"],
      ["planning_annual_calendars","自定义年度日历","textarea","高级选项：仅在需要覆盖宿主日历时填写。"],
      ["planning_weather_enabled","启用角色天气感知","bool","打开后，私聊询问天气时按需读取配置地点实况；日常计划也可参考。关闭后两者都不读取。"],
      ["planning_weather_max_age_minutes","天气信息最长沿用（分钟）","number","5 至 120。超过这段时间的天气不再用于私聊回答或计划参考，避免沿用旧实况。"],
      ["location_name","所在城市或区域","text","填写后可自动补齐坐标；已配置和风天气时，实况与预警都使用和风。"],
      ["location_latitude","纬度（高级）","number","和风天气需要坐标；留空时由系统按地点解析。"],
      ["location_longitude","经度（高级）","number","和风天气需要坐标；留空时由系统按地点解析。"],
      ["location_alert_city","预警城市（可选）","text","需要精确匹配官方预警时填写。"],
      ["location_alert_area","预警区域（可选）","text","与预警城市同时填写。"],
    ],
    model:[
      ["calendar_enabled","提供本地日期上下文","bool","仅陈述明确可核实的日历信息。"],
      ["calendar_timezone","对话日期时区","text","使用 IANA 时区名称。"],
      ["holiday_enabled","提供节假日与工作日","bool","识别中国大陆节假日、调休；日历库不可用时按周末判断。"],
      ["holiday_country","节假日识别地区","select","当前提供中国大陆节假日表，或仅按周末区分。",[["CN","中国大陆"],["WEEKEND_ONLY","仅按周末识别"]]],
      ["lunar_enabled","提供农历日期","bool","农历日期由本地历法换算，不需要联网。"],
      ["automatic_solar_terms_enabled","提供节气日期","bool","启用后由宿主按年份查表；未装配节气表时不提供。"],
      ["almanac_enabled","提供黄历宜忌","bool","只陈述由历法数据得出的宜忌，不据此推断吉凶。"],
      ["platform_enabled","标明当前平台","bool","帮助模型区分消息来自哪个平台。"],
      ["model_route_enabled","标明模型路由","bool","让模型知道当前任务的路由标识。"],
      ["configured_modalities_enabled","标明已配置的输入模态","bool","仅说明能力配置；实际图像、语音和视频仍需真实输入与授权。"],
      ["guidance","感知表达偏好","textarea","补充角色如何表达观察；不改变实际权限与工具结果。"],
    ],
    news:[
      ["news_share_enabled","允许分享外部资讯","bool","只会考虑有来源、时间和链接的实际条目。"],
      ["news.enabled","允许资讯作为联系契机","bool","仍受主动联系总开关与免打扰约束。"],
      ["news_check_interval_minutes","资讯检查间隔（分钟）","number","15 至 1440 分钟。"],
      ["news_source_kind","资讯来源","select","B 站动态使用发布者动态；RSS / JSON 必须是 HTTPS 订阅地址。",newsSourceOptions],
      ["news_source_uid","B 站 UID","text","仅在来源选择 B 站动态时填写十进制 UID。"],
      ["news_source_url","RSS / JSON 地址","text","仅在来源选择 RSS / Atom 或 HTTPS JSON 时填写地址。"],
    ],
  };
  const locationFields = ["location_name","location_latitude","location_longitude","location_alert_city","location_alert_area"];
  let nodes = null, path = "", scope = "", status = null, drafts = {}, notices = {}, busy = false;
  let generation = 0, abort = null;
  const subscribers = new Set();
  const active = ticket => ticket === generation && nodes?.environment?.isConnected && scope === product.scopeKey();
  const error = (code, confirmed = false) => Object.assign(new Error(errors[code] || "操作未完成，请刷新核对。"), {code, confirmed});

  /* 同 memory-page.js / state-page.js：桥要插件相对路径，切掉插件目录名。 */
  function relative(value) {
    if (typeof value !== "string" || !value.startsWith(prefix)) throw error("invalid_response");
    const route = value.slice(prefix.length);
    if (!route || /[?#%\\:]/.test(route) || route.split("/").some(part => !part || part === "." || part === "..")) throw error("invalid_response");
    return route;
  }
  async function api(method, body) {
    let timer;
    try {
    /* 等桥就绪，而不是当场读 window.AstrBotPluginPage。
       主页面此前不引页面桥 SDK，桥是在 product.connect() 里动态补上的；
       这一页若在它补好之前就发请求，读到的是 undefined，用户看到的是
       「未连接」——一个只在几百毫秒窗口里出现的假故障。 */
      const bridge = window.CompanionProduct.bridgeNow() || await window.CompanionProduct.bridgeFor();
      const suffix = arguments.length > 2 ? arguments[2] : (method === "GET" ? "" : "/configure");
      const call = method === "GET" ? bridge.apiGet(path + suffix) : bridge.apiPost(path + suffix, body);
      const response = await Promise.race([call, new Promise((_, reject) => {
        timer = setTimeout(() => reject(error("bridge_timeout")), 15000);
      })]);
      const wrapped = ["ok","error"].includes(response?.status) ? response
        : ["ok","error"].includes(response?.data?.status) ? response.data : null;
      if (wrapped?.status === "error") throw error(codeOf(wrapped) || "invalid_response", true);
      const value = wrapped ? wrapped.data : response;
      if (!value || typeof value !== "object" || Array.isArray(value)) throw error("invalid_response");
      return value;
    } finally { clearTimeout(timer); }
  }
  function checked(value) {
    return ["environment","model","news"].every(section => value?.[section]?.settings
      && typeof value[section].edit_token === "string"
      && fields[section].filter(([name]) => !name.startsWith("location_")).every(([name, , type]) =>
        typeof value[section].settings[name] === (type === "bool" ? "boolean" : type === "number" ? "number" : "string")));
  }
  function publicSnapshot() {
    if (!status) return {ready:false, loading:!notices.load, error:notices.load || ""};
    const environment = status.environment.settings || {}, model = status.model.settings || {};
    const contact = status.contact?.settings || {};
    let locationName = "";
    try { locationName = JSON.parse(environment.planning_weather_location || "{}").name || ""; } catch (_) {}
    return {
      ready:true,
      environment:{weatherReady:!!status.environment.sources?.weather_ready,
        alertsReady:!!status.environment.sources?.alerts_ready, locationName,
        weatherEnabled:environment.planning_weather_enabled === true,
        timezone:environment.planning_timezone || ""},
      model:{calendarEnabled:model.calendar_enabled === true, timezone:model.calendar_timezone || "",
        lunarEnabled:model.lunar_enabled === true, solarTermsEnabled:model.automatic_solar_terms_enabled === true,
        almanacEnabled:model.almanac_enabled === true, platformEnabled:model.platform_enabled === true,
        routeEnabled:model.model_route_enabled === true, modalitiesEnabled:model.configured_modalities_enabled === true},
      contact:{dateCheckinEnabled:contact.date_checkin_enabled === true,
        dates:typeof contact.important_dates === "string" ? contact.important_dates : "[]",
        lookaheadDays:Number.isInteger(contact.important_date_lookahead_days)
          ? contact.important_date_lookahead_days : 0,
        timezone:contact.quiet_timezone || ""},
      news:{ready:!!status.news.source?.ready, label:status.news.source?.label || "",
        sourceKind:status.news.source?.kind || contact.news_source_kind || "",
        explorationEnabled:contact.web_exploration_enabled === true,
        explorationInterests:contact.web_exploration_interests || "",
        explorationIntervalHours:contact.web_exploration_min_interval_hours ?? null,
        explorationResultCount:contact.web_exploration_result_count ?? null,
        externalSelfLinkEnabled:contact.external_event_self_link_enabled === true,
        lastCheckedAt:status.news.diagnostic?.last_checked_at || "",
        failureCode:status.news.diagnostic?.failure?.code || ""},
    };
  }
  function publishStatus() {
    const snapshot = publicSnapshot();
    for (const listener of [...subscribers]) {
      try { listener(snapshot); } catch (_) {}
    }
  }
  function values(section, data) {
    const result = {...data.settings};
    if (section === "environment") {
      let location = {};
      try { location = JSON.parse(result.planning_weather_location || "{}"); } catch (_) {}
      if (!location || typeof location !== "object" || Array.isArray(location)) location = {};
      result.location_name = location.name || "";
      result.location_latitude = location.latitude ?? "";
      result.location_longitude = location.longitude ?? "";
      result.location_alert_city = location.alert_city || "";
      result.location_alert_area = location.alert_area || "";
    }
    return result;
  }
  function merge(next, force = "") {
    if (!checked(next)) throw error("invalid_response");
    status = next;
    for (const section of Object.keys(fields)) {
      const current = drafts[section], entry = next[section], latest = values(section, entry);
      if (!current || section === force || (!current.touched.size && !current.pending)) {
        drafts[section] = {values:{...latest}, original:latest, token:entry.edit_token,
          touched:new Set(), stale:false, pending:null};
      } else if (current.token !== entry.edit_token) {
        current.stale = true;
      }
    }
    publishStatus();
  }
  function field(section, spec, draft) {
    const [name, label, type, hint, options] = spec, value = draft.values[name];
    const id = "native-" + section + "-" + name.replaceAll(".", "-");
    const common = `id="${id}" data-native-field="${esc(name)}"`;
    if (type === "bool") return `<div class="perception-setting perception-setting-toggle"><span><strong>${label}</strong>${hint ? `<small>${hint}</small>` : ""}</span><label class="model-switch"><input ${common} type="checkbox" ${value ? "checked" : ""}><i></i></label></div>`;
    if (type === "select") return `<label class="perception-setting" for="${id}"><strong>${label}</strong><select ${common}>${(options || []).map(([option, text]) => `<option value="${esc(option)}" ${value === option ? "selected" : ""}>${esc(text)}</option>`).join("")}</select>${hint ? `<small>${hint}</small>` : ""}</label>`;
    const control = type === "textarea"
      ? `<textarea ${common} rows="${name === "planning_annual_calendars" ? 5 : 3}" spellcheck="false">${esc(value)}</textarea>`
      /* 只有纬度经度容忍小数；其余整数字段必须 step=1，
         否则浏览器会放过 12.5 这类值，到后端才被拒。 */
      : `<input ${common} type="${type === "number" ? "number" : "text"}" value="${esc(value)}" ${type === "number" ? `step="${name.startsWith("location_") ? "any" : "1"}"` : 'autocomplete="off"'}>`;
    return `<label class="perception-setting" for="${id}"><strong>${label}</strong>${control}${hint ? `<small>${hint}</small>` : ""}</label>`;
  }
  function context(section) {
    if (section === "environment") {
      const sources = status.environment.sources || {};
      return `<div class="native-perception-meta"><span>${sources.weather_ready ? "天气源已装配" : "天气源尚未就绪"}</span><span>${sources.alerts_ready ? "预警源已装配" : "预警源尚未就绪"}</span></div>`;
    }
    if (section === "model") return '<p class="perception-note">下一轮对话生效。</p>';
    const news = status.news, source = news.source || {};
    const diagnostic = news.diagnostic || {}, failure = diagnostic.failure || {};
    const sourceText = source.ready ? `资讯源已装配 · ${esc(source.label || "未命名")}` : "资讯源尚未就绪";
    const checkText = diagnostic.last_checked_at
      ? `最近检查 ${esc(diagnostic.last_checked_at)} · ${Number(diagnostic.item_count) || 0} 条`
      : "尚未完成检查";
    const failureText = failure.code
      ? `最近失败 ${esc(failure.code)}${failure.http_status ? ` · HTTP ${esc(failure.http_status)}` : ""}`
      : "最近检查未报告错误";
    return `<div class="native-perception-meta"><span>${sourceText}</span><span>${checkText}</span><span>${failureText}</span><span>${news.contact_enabled ? "主动联系总开关已开启" : "主动联系总开关已关闭"}</span><span>${news.automatic_enabled ? "后台联系已开启" : "后台联系已关闭"}</span></div><p class="perception-note">检查来源不会发送消息。</p><button class="button small" type="button" data-native-action="diagnose" data-native-section="news" ${busy ? "disabled" : ""}>检查来源</button>`;
  }
  function renderSection(section) {
    const node = nodes?.[section]; if (!node) return;
    if (!product.hosted()) { node.innerHTML = '<p class="memory-notice" role="status">未读取到宿主目录。</p><div class="native-perception-actions"><button class="button small" type="button" data-workspace-retry>重新读取</button></div>'; return; }
    if (!path) { node.innerHTML = '<p class="memory-notice">请选择有管理权限的私聊对象和角色。</p>'; return; }
    if (!status) {
      node.innerHTML = `<p class="memory-notice" role="status">${esc(notices.load || "正在读取当前配置…")}</p><button class="button small" type="button" data-native-action="refresh">重新读取</button>`;
      return;
    }
    const draft = drafts[section], pending = !!draft.pending;
    const message = draft.stale ? errors.configuration_revision_conflict : notices[section] || "";
    if (section === "news") {
      node.innerHTML = `${context(section)}<p class="perception-note">来源、资讯分享、网络探索和事件自关联设置在本面板下方统一编辑。</p><div class="native-perception-actions"><button class="button small" type="button" data-native-action="diagnose" data-native-section="news" ${busy ? "disabled" : ""}>${busy && notices.news ? "正在检查…" : "检查来源"}</button><button class="button small" type="button" data-native-action="refresh" ${busy ? "disabled" : ""}>刷新状态</button></div><p class="perception-save-status" role="status" aria-live="polite">${esc(message)}</p>`;
      return;
    }
    const title=({environment:"角色环境",model:"对话感知",news:"资讯联系"})[section];
    const formMarkup=`<form class="perception-settings-form native-perception-form" data-native-section="${section}">
      <div class="perception-settings-heading"><div><h4>${title}</h4></div>
      <button class="button small" type="submit" ${busy ? "disabled" : ""}>${pending ? "核对原保存" : "保存设置"}</button></div>
      <fieldset class="perception-settings-grid native-perception-fieldset" ${pending || busy ? "disabled" : ""}>${section === "environment" ? `<label class="perception-setting perception-setting-primary" for="native-environment-location_name"><strong>所在城市或区域</strong><input id="native-environment-location_name" data-native-field="location_name" type="text" value="${esc(draft.values.location_name)}" autocomplete="address-level2" placeholder="输入城市、区县或镇街"><small>用于定位天气。已配置和风天气时，实况与官方预警都来自和风；不会读取精确 GPS。</small></label><div class="perception-setting perception-setting-toggle"><span><strong>启用角色天气感知</strong><small>私聊询问天气时按需读取；日常计划也会参考。仅使用这里配置的地点。</small></span><label class="model-switch"><input data-native-field="planning_weather_enabled" type="checkbox" ${draft.values.planning_weather_enabled ? "checked" : ""}><i></i></label></div><details class="perception-advanced-settings"><summary>高级设置</summary><div class="perception-settings-grid">${fields[section].filter(spec => !["location_name","planning_weather_enabled"].includes(spec[0])).map(spec => field(section, spec, draft)).join("")}</div></details>` : fields[section].map(spec => field(section, spec, draft)).join("")}</fieldset>
      <p class="perception-save-status ${draft.stale ? "native-perception-warning" : ""}" role="status" aria-live="polite">${esc(message)}</p>
      <div class="native-perception-actions"><button class="button small" type="button" data-native-action="refresh" ${busy ? "disabled" : ""}>刷新</button>${draft.stale ? `<button class="button small" type="button" data-native-action="rebase" data-native-section="${section}" ${busy ? "disabled" : ""}>采用最新版本</button>` : ""}</div>
    </form>`;
    node.innerHTML = `${context(section)}${section === "environment" ? formMarkup : `<details class="perception-settings-disclosure" ${section === "model" ? "open" : ""}><summary><span>${title}</span><small>${fields[section].length} 项配置</small></summary>${formMarkup}</details>`}`;
  }
  function render() { for (const section of Object.keys(fields)) renderSection(section); }
  async function load() {
    if (!path || busy) return;
    const ticket = ++generation;
    notices.load = "";
    if (!status) render();
    try { const next = await api("GET"); if (active(ticket)) {
      merge(next);
      notices.load = "";
      for (const section of Object.keys(fields)) notices[section] = "";
      render();
    } }
    catch (failure) { if (active(ticket)) {
      notices.load = failure.message || "读取失败，请重试。";
      if (status) for (const section of Object.keys(fields)) notices[section] = notices.load;
      publishStatus();
      render();
    } }
  }
  function timezone(value) {
    try { new Intl.DateTimeFormat("zh-CN", {timeZone:value}).format(); return true; } catch (_) { return false; }
  }
  function patch(section, draft) {
    const changes = {};
    for (const [name, , type] of fields[section]) {
      if (name.startsWith("location_") || !draft.touched.has(name)) continue;
      let value = draft.values[name];
      if (type === "number") value = Number(value);
      if (value !== draft.original[name]) changes[name] = value;
    }
    if (section === "environment") {
      if (changes.planning_timezone && !timezone(changes.planning_timezone)) throw new Error("请填写有效的角色日历时区。");
      if (Object.hasOwn(changes, "planning_annual_calendars") && changes.planning_annual_calendars.trim()) {
        let annual; try { annual = JSON.parse(changes.planning_annual_calendars); } catch (_) { throw new Error("年度日历需要有效的 JSON 数组。"); }
        if (!Array.isArray(annual) || annual.length < 1 || annual.length > 3) throw new Error("年度日历请提供 1 至 3 个年份的数据。");
      }
      if (locationFields.some(name => draft.touched.has(name))) {
        const source = draft.values, name = String(source.location_name).trim();
        const latitude = String(source.location_latitude).trim(), longitude = String(source.location_longitude).trim();
        const city = String(source.location_alert_city).trim(), area = String(source.location_alert_area).trim();
        let location = "";
        if (name || latitude || longitude || city || area) {
          if (!name) throw new Error("请填写城市或区域名称。");
          if ((latitude && !Number.isFinite(Number(latitude))) || (longitude && !Number.isFinite(Number(longitude)))
              || (latitude && (Number(latitude) < -90 || Number(latitude) > 90))
              || (longitude && (Number(longitude) < -180 || Number(longitude) > 180)))
            throw new Error("纬度和经度需要成对填写，或全部留空由系统自动解析。");
          if (!!latitude !== !!longitude) throw new Error("纬度和经度需要成对填写，或全部留空由系统自动解析。");
          if (!!city !== !!area) throw new Error("预警城市和区域请同时填写，或同时留空。");
          location = JSON.stringify({name, ...(latitude ? {latitude:Number(latitude), longitude:Number(longitude)} : {}),
            ...(city ? {alert_city:city, alert_area:area} : {})});
        }
        if (location !== draft.original.planning_weather_location) changes.planning_weather_location = location;
      }
      if ((changes.planning_weather_enabled ?? draft.original.planning_weather_enabled)
          && !(changes.planning_weather_location ?? draft.original.planning_weather_location))
        throw new Error("启用天气前，请先设置角色地点。");
      /* 沿用时长后端限定 5–120 的整数；这里判一次，避免整份设置被后端退回。 */
      if (Object.hasOwn(changes, "planning_weather_max_age_minutes")) {
        const age = changes.planning_weather_max_age_minutes;
        if (!Number.isInteger(age) || age < 5 || age > 120) throw new Error("天气信息最长沿用时间应为 5 至 120 分钟的整数。");
      }
    }
    if (section === "model") {
      if (changes.calendar_timezone && !timezone(changes.calendar_timezone)) throw new Error("请填写有效的对话日期时区。");
      if (typeof changes.guidance === "string" && new TextEncoder().encode(changes.guidance).length > 2048)
        throw new Error("感知表达偏好不能超过 2 KiB。");
    }
    if (section === "news" && Object.hasOwn(changes, "news_check_interval_minutes")
        && (!Number.isInteger(changes.news_check_interval_minutes) || changes.news_check_interval_minutes < 15
            || changes.news_check_interval_minutes > 1440)) throw new Error("资讯检查间隔应为 15 至 1440 分钟的整数。");
    if (section === "news") {
      const kind = changes.news_source_kind ?? draft.original.news_source_kind;
      const uid = String(changes.news_source_uid ?? draft.values.news_source_uid ?? "").trim();
      const url = String(changes.news_source_url ?? draft.values.news_source_url ?? "").trim();
      if (kind === "bilibili" && !/^[1-9][0-9]{0,19}$/.test(uid)) throw new Error("B 站来源需要填写十进制 UID。");
      if ((kind === "rss" || kind === "json") && !/^https:\/\/[^\s#]+$/i.test(url)) throw new Error("RSS / JSON 来源需要填写 HTTPS 地址。");
    }
    return changes;
  }
  async function save(section) {
    if (!path || !status || busy) return;
    const draft = drafts[section];
    if (draft.stale) { notices[section] = errors.configuration_revision_conflict; renderSection(section); return; }
    if (!draft.pending) {
      let changes;
      try { changes = patch(section, draft); } catch (failure) { notices[section] = failure.message; renderSection(section); return; }
      if (!Object.keys(changes).length) { notices[section] = "没有待保存的修改。"; renderSection(section); return; }
      draft.pending = {operation_key:crypto.randomUUID(), edit_token:draft.token, changes};
    }
    const ticket = generation;
    busy = true; notices[section] = "正在保存…"; render();
    try {
      const response = await api("POST", {section, command:draft.pending});
      if (!active(ticket)) return;
      if (!response.status || !checked(response.status)) throw error("invalid_response");
      merge(response.status, section);
      notices[section] = "已保存。";
    } catch (failure) {
      if (!active(ticket)) return;
      if (failure.confirmed) {
        draft.pending = null;
        if (failure.code === "configuration_revision_conflict") draft.stale = true;
      }
      notices[section] = failure.message || "保存未完成，请核对原请求。";
    } finally { if (active(ticket)) { busy = false; render(); } }
  }
  async function diagnose() {
    if (!path || !status || busy) return;
    const ticket = generation;
    busy = true; notices.news = "正在检查资讯源…"; render();
    try {
      const response = await api("POST", {}, "/news-diagnostic");
      if (!active(ticket)) return;
      if (!response.status || !checked(response.status)) throw error("invalid_response");
      merge(response.status);
      notices.news = response.diagnostic?.failure ? "检查完成，来源返回错误。" : "检查完成。";
    } catch (failure) {
      if (active(ticket)) notices.news = failure.message || "来源检查失败，请重试。";
    } finally { if (active(ticket)) { busy = false; render(); } }
  }
  function rebase(section) {
    const draft = drafts[section], latest = values(section, status[section]);
    for (const [name] of fields[section]) if (!draft.touched.has(name)) draft.values[name] = latest[name];
    draft.original = latest;
    draft.token = status[section].edit_token;
    draft.stale = false;
    draft.pending = null;
    notices[section] = "草稿仍在；请核对后保存。";
    renderSection(section);
  }
  function mount(places) {
    unmount(); nodes = places; scope = product.scopeKey();
    abort = new AbortController();
    try { path = product.hosted() && product.role()?.perception_native_api
      ? relative(product.role().perception_native_api) : ""; }
    catch (failure) { path = ""; notices.load = failure.message; }
    for (const section of Object.keys(fields)) {
      const node = nodes?.[section]; if (!node) continue;
      node.addEventListener("input", event => {
        const input = event.target.closest("[data-native-field]");
        if (!input || !drafts[section]) return;
        const name = input.dataset.nativeField;
        drafts[section].values[name] = input.type === "checkbox" ? input.checked : input.value;
        drafts[section].touched.add(name);
        notices[section] = "";
      }, {signal:abort.signal});
      node.addEventListener("change", event => {
        const input = event.target.closest("[data-native-field]");
        if (!input || !drafts[section]) return;
        drafts[section].values[input.dataset.nativeField] = input.type === "checkbox" ? input.checked : input.value;
        drafts[section].touched.add(input.dataset.nativeField);
      }, {signal:abort.signal});
      node.addEventListener("submit", event => { event.preventDefault(); save(section); }, {signal:abort.signal});
      node.addEventListener("click", event => {
        const action = event.target.closest("[data-native-action]")?.dataset.nativeAction;
        if (action === "refresh") load();
        if (action === "rebase") rebase(section);
        if (action === "diagnose" && section === "news") diagnose();
      }, {signal:abort.signal});
    }
    render(); load();
  }
  function unmount() {
    generation++; abort?.abort(); abort = null;
    nodes = null; path = ""; scope = ""; status = null; drafts = {}; notices = {}; busy = false;
    publishStatus();
  }
  return {mount, unmount, refresh:load, subscribe(listener) {
    if (typeof listener !== "function") return () => {};
    subscribers.add(listener); listener(publicSnapshot());
    return () => subscribers.delete(listener);
  }};
})();
