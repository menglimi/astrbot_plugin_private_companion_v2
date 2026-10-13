/* Host-owned weather credentials stay in memory while editing and are never cached. */
"use strict";
window.CompanionWeatherSourcePage = (() => {
  const product = window.CompanionProduct;
  const endpoint = "host-options/weather";
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const providers = {auto:"自动选择（优先和风）",qweather:"和风天气", "open-meteo":"Open-Meteo"};
  const errors = {
    weather_source_invalid:"请核对数据源、专属 API Host 和 JWT／API Key；缓存间隔应为 1–120 分钟。",
    weather_source_credential_required:"替换环境变量中的 Host 时，请同时填写对应的和风凭据。",
    host_options_conflict:"数据源已被其他页面修改。请重新读取后核对并保存。",
    host_options_save_failed:"数据源未能保存，请重试。",
    host_options_save_unavailable:"当前宿主不支持保存插件配置。",
    core_access_required:"当前账号没有管理权限。",
    dashboard_identity_required:"请从已登录的 AstrBot 管理界面打开。",
    staging_not_initialized:"角色数据尚未就绪，请先保存角色映射。",
    staging_host_terminated:"插件已停止，请重新打开插件页面。",
    invalid_response:"数据源配置未能读取，请重新读取。",
  };
  let root = null, status = null, draft = null, busy = false, pending = false, stale = false;
  let generation = 0, abort = null, message = "", leavePrompt = null;
  const askConfirm = options => typeof window.CompanionConfirm === "function"
    ? window.CompanionConfirm(options) : Promise.resolve(false);
  /* 只缓存不含凭据原文的读取状态。编辑中的 credential 永远不会进入这个
     Map；切换角色或会话时使用不同 scope，避免把天气配置串给别的对象。 */
  const statusByScope = new Map();
  const currentScope = () => { try { return product.scopeKey?.() || "default"; } catch (_) { return "default"; } };
  const active = ticket => ticket === generation && root?.isConnected;
  const dirty = () => !!draft && (!status
    ? draft.credential !== "" || pending || stale
    : draft.credential !== "" || Object.keys(status.settings).some(key => String(draft[key]) !== String(status.settings[key])));
  async function request(method, body) {
    const bridge = product.bridgeNow() || await product.bridgeFor();
    let timer;
    try {
      const response = await Promise.race([
        method === "GET" ? bridge.apiGet(endpoint) : bridge.apiPost(endpoint, body),
        new Promise((_, reject) => {timer = setTimeout(() => reject(new Error("bridge_timeout")), 15000);}),
      ]);
      const wrapped = ["ok","error"].includes(response?.status) && response?.data !== undefined ? response
        : ["ok","error"].includes(response?.data?.status) && response?.data?.data !== undefined ? response.data : null;
      if (wrapped?.status === "error") throw Object.assign(new Error(wrapped.data?.code || wrapped.message || "invalid_response"), {confirmed:true});
      const value = wrapped ? wrapped.data : response;
      if (!value?.settings || !Object.hasOwn(providers, value.settings.provider)
          || typeof value.settings.api_host !== "string" || !Number.isInteger(value.settings.refresh_minutes)
          || typeof value.edit_token !== "string" || !/^[a-f0-9]{64}$/.test(value.edit_token)
          || typeof value.has_credential !== "boolean") throw new Error("invalid_response");
      return value;
    } finally {clearTimeout(timer);}
  }
  function render() {
    if (!root) return;
    if (!status) {
      root.innerHTML = `<p class="memory-notice" role="status">${esc(message || "正在读取天气数据源…")}</p>${message ? '<button type="button" class="button small" data-weather-source-action="reload">重新读取</button>' : ""}`;
      return;
    }
    const kind = {api_key:"API Key",jwt:"JWT",signed_jwt:"自动签名 JWT"}[status.credential_kind] || "凭据";
    const source = {plugin:"页面配置",environment:"环境变量",none:"尚未配置"}[status.credential_source] || "尚未配置";
    root.innerHTML = `<section class="weather-source-settings" aria-labelledby="weather-source-title">
      <header class="weather-source-heading"><div><h4 id="weather-source-title">数据源与和风凭据</h4></div><span class="weather-source-state">${status.source_state === "invalid" ? "配置待完善" : `当前 · ${esc(providers[status.actual_provider] || "未就绪")}`}</span></header>
      <form data-weather-source-form>
        <fieldset class="weather-source-grid" ${busy || pending ? "disabled" : ""}>
          <label class="perception-setting" for="weather-source-provider"><strong>天气数据源</strong><select id="weather-source-provider" name="provider">${Object.entries(providers).map(([value,label]) => `<option value="${value}" ${draft.provider === value ? "selected" : ""}>${label}</option>`).join("")}</select><small>自动模式有和风凭据时使用和风，否则使用 Open-Meteo。</small></label>
          <label class="perception-setting" for="weather-source-refresh"><strong>天气缓存刷新间隔（分钟）</strong><input id="weather-source-refresh" name="refresh_minutes" type="number" min="1" max="120" step="1" value="${esc(draft.refresh_minutes)}" required><small>1–120 分钟；控制实况数据源的读取频率。</small></label>
          <label class="perception-setting" for="weather-source-host"><strong>和风天气 API Host</strong><input id="weather-source-host" name="api_host" type="text" maxlength="253" value="${esc(draft.api_host)}" autocomplete="off" spellcheck="false" placeholder="例如 abc123.re.qweatherapi.com"><small>填写和风控制台分配的专属 Host，也可粘贴 HTTPS Host；不含接口路径。</small></label>
          <label class="perception-setting" for="weather-source-credential"><strong>和风凭据（JWT／API Key）</strong><input id="weather-source-credential" name="credential" type="password" maxlength="4096" value="${esc(draft.credential)}" autocomplete="new-password" spellcheck="false" placeholder="${status.has_credential ? "已配置，留空保留现有凭据" : "粘贴 JWT 或 API Key"}"><small>${esc(source)}${status.has_credential ? ` · ${kind} 已配置` : ""}。自动识别认证方式；JWT 不含 Bearer 前缀，过期后在此更新。</small></label>
        </fieldset>
        <div class="weather-source-footer"><p>官方预警共用这组和风凭据。凭据保存于宿主配置，读取时只返回配置状态。</p><div class="native-perception-actions"><button class="button small" type="button" data-weather-source-action="reload" ${busy ? "disabled" : ""}>重新读取</button>${status.credential_source === "plugin" ? `<button class="button small" type="button" data-weather-source-action="clear" ${busy || pending ? "disabled" : ""}>清除页面凭据</button>` : ""}<button class="button primary small" type="submit" ${busy || pending || stale ? "disabled" : ""}>${busy ? "正在保存…" : "保存数据源"}</button></div></div>
        <p class="perception-save-status" role="status" aria-live="polite">${esc(message)}</p>
      </form>
    </section>`;
  }
  async function load() {
    if (busy) return;
    const ticket = generation;
    const preserveDraft = dirty();
    try {
      const next = await request("GET");
      if (!active(ticket)) return;
      status = next; statusByScope.set(currentScope(), next);
      draft = {...next.settings, credential:""}; pending = stale = false;
      message = next.source_state === "invalid" ? errors.weather_source_invalid : "";
    } catch (failure) {if (active(ticket)) {
      /* 读取失败后不再画上一份数据源与凭据状态；凭据输入若尚未保存则留在
         内存里，等成功重读后再核对，绝不写入缓存。 */
      status = null;
      statusByScope.delete(currentScope());
      if (!preserveDraft) draft = null;
      stale = preserveDraft;
      message = errors[failure.code || failure.message] || errors.invalid_response;
    }}
    if (active(ticket)) render();
  }
  async function save(clear = false) {
    if (!status || busy || pending || stale) return;
    const ticket = generation, changes = {};
    if (clear) changes.clear_credentials = true;
    else {
      for (const name of ["provider","api_host","refresh_minutes"]) {
        const value = name === "refresh_minutes" ? Number(draft[name]) : draft[name].trim();
        if (value !== status.settings[name]) changes[name] = value;
      }
      if (draft.credential.trim()) changes.credential = draft.credential.trim();
      if (!Object.keys(changes).length) {message = "没有需要保存的修改。"; render(); return;}
    }
    busy = true; message = "正在保存数据源…"; render();
    try {
      const next = await request("POST", {edit_token:status.edit_token,changes});
      if (!active(ticket)) return;
      status = next; statusByScope.set(currentScope(), next); draft = {...next.settings,credential:""};
      message = clear ? "页面凭据已清除，当前来源已更新。" : "数据源已保存并立即生效。";
      window.CompanionNativePerceptionPage?.refresh();
      document.dispatchEvent(new CustomEvent("companion:weather-source-updated"));
    } catch (failure) {
      if (!active(ticket)) return;
      if (failure.confirmed) {
        message = errors[failure.code || failure.message] || "保存未完成，请核对配置后重试。";
        stale = (failure.code || failure.message) === "host_options_conflict";
      } else {
        pending = true; draft.credential = "";
        message = "保存结果尚未确认。请重新读取配置核对，再填写需要更新的凭据。";
      }
    } finally {if (active(ticket)) {busy = false; render();}}
  }
  function mount(node) {
    unmount(); root = node; abort = new AbortController();
    const cached = statusByScope.get(currentScope());
    if (cached) { status = cached; draft = {...cached.settings, credential:""}; }
    root.addEventListener("input", event => {
      if (draft && Object.hasOwn(draft,event.target.name)) draft[event.target.name] = event.target.value;
    }, {signal:abort.signal});
    root.addEventListener("change", event => {
      if (draft && Object.hasOwn(draft,event.target.name)) draft[event.target.name] = event.target.value;
    }, {signal:abort.signal});
    root.addEventListener("submit", event => {if (event.target.matches("[data-weather-source-form]")) {event.preventDefault(); save();}}, {signal:abort.signal});
    root.addEventListener("click", async event => {
      const action = event.target.closest("[data-weather-source-action]")?.dataset.weatherSourceAction;
      if (action === "reload") {
        if (dirty() && !await askConfirm({title:"放弃天气数据源修改",message:"重新读取会清空未保存的数据源修改。",confirmText:"重新读取"})) return;
        load();
      }
      if (action === "clear" && await askConfirm({title:"清除页面凭据",message:"清除页面保存的和风凭据？若存在环境变量凭据，将恢复使用它。",confirmText:"清除凭据",danger:true})) save(true);
    }, {signal:abort.signal});
    render(); load();
  }
  function canLeave() {
    if (busy) return false;
    if (!dirty()) return true;
    if (!leavePrompt) {
      leavePrompt = askConfirm({title:"天气数据源尚未保存",message:"离开此页会丢弃未保存的数据源修改。",confirmText:"离开并丢弃",danger:true})
        .finally(() => { leavePrompt = null; });
    }
    return leavePrompt;
  }
  function unmount() {
    generation++; abort?.abort(); abort = null; root = status = draft = null; leavePrompt = null;
    busy = pending = stale = false; message = "";
  }
  window.addEventListener("beforeunload", event => {if (dirty() || busy) {event.preventDefault(); event.returnValue = "";}});
  return {mount,unmount,canLeave};
})();
