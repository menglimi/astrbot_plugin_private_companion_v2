"use strict";
window.CompanionExpressionSamplesPage = (() => {
  const PREFIX = "/astrbot_plugin_private_companion_v2/";
  const FILTERS = [["all", "全部"], ["pending", "待审"], ["approved", "已允许"], ["rejected", "已排除"]];
  const STATES = {pending: "待审", approved: "已允许", rejected: "已排除"};
  const ERRORS = {
    bridge_unavailable: "页面连接暂不可用，请重新读取。",
    bridge_timeout: "读取超时，请重试。",
    expression_sample_unavailable: "当前窗口暂无可读取的消息素材。",
    expression_sample_changed: "素材已变化，请重新读取后再操作。",
    expression_view_stale: "素材状态已更新，请重新读取。",
    expression_binding_changed: "当前角色关联已变化，请重新选择范围。",
    expression_sample_review_invalid: "素材审核记录异常，请重新读取。",
    model_task_unregistered: "表达学习模型暂不可用，请检查模型连接。",
    staging_not_initialized: "角色数据尚未加载，请重新读取。",
    staging_host_terminated: "陪伴服务已停止。",
    dashboard_identity_required: "登录状态已失效，请重新打开陪伴小屋。",
  };
  const e = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
  const time = value => Number.isFinite(Date.parse(value))
    ? new Date(value).toLocaleString("zh-CN", {hour12:false, month:"numeric", day:"numeric", hour:"2-digit", minute:"2-digit"}) : "时间未知";
  let root, apiBase = "", scopeKey = "", ticket = 0, readTicket = 0, timer;
  let items = [], counts = {}, runtime = {}, filter = "all", cursor = null, reviewEnabled = false;
  let busy = false, writing = false, loaded = false, notice = "", error = false;
  const mounted = current => !!root?.isConnected && ticket === current;
  const message = code => ERRORS[code] || "操作未完成，请重新读取后核对。";
  async function api(method, route, body) {
    let timeout;
    try {
      return await Promise.race([(async () => {
        const product = window.CompanionProduct;
        const bridge = product?.bridgeNow?.() || await product?.bridgeFor?.();
        if (!bridge?.apiGet || method !== "GET" && !bridge.apiPost) throw {code:"bridge_unavailable"};
        let response = await (method === "GET" ? bridge.apiGet(route, body) : bridge.apiPost(route, body));
        for (let depth = 0; depth < 3; depth++) {
          if (response?.status === "error") throw {code:response.data?.code || response.code || response.message};
          if (response?.data !== undefined && (!response.status || response.status === "ok")) response = response.data;
          else break;
        }
        response = product?.unwrap ? product.unwrap(response) : response;
        if (!response || typeof response !== "object") throw {code:"invalid_response"};
        return response;
      })(), new Promise((_, reject) => {timeout = setTimeout(() => reject({code:"bridge_timeout"}), 15000);})]);
    } finally { clearTimeout(timeout); }
  }
  function statusText(value = runtime.last_result) {
    if (runtime.running || ["queued", "running", "created"].includes(value?.state)) return "学习中";
    const state = value?.state;
    if (state === "waiting_for_new_messages") return `新增消息 ${value.new_messages || 0} / ${value.required || runtime.required_new_messages}`;
    if (state === "waiting_for_sample_review" || state === "insufficient_samples") return `可用素材 ${value.available || 0} / ${value.required || runtime.minimum_samples}`;
    return {succeeded:"学习完成 · 候选已进入审阅中心", already_attempted:"本批素材已学习", learning_disabled:"当前窗口学习已关闭",
      capacity_reached:"规则容量已满", daily_budget_reached:"今日学习批次已用完", failed:"学习失败", blocked:"学习暂不可用",
      cancelled:"学习已取消", timed_out:"学习超时"}[state] || (runtime.learning_enabled === false ? "学习已关闭" : "尚未学习");
  }
  function canLearn() {
    return loaded && !busy && !writing && !runtime.running && runtime.learning_enabled
      && runtime.eligible_samples >= runtime.minimum_samples
      && (runtime.new_messages == null || runtime.new_messages >= runtime.required_new_messages
        && runtime.group_batches_today < runtime.group_daily_batch_limit);
  }
  function render() {
    if (!root) return;
    const disabled = busy || writing ? " disabled" : "";
    const application = loaded ? (runtime.application_enabled ? "表达应用开启" : "表达应用关闭") : "状态待读取";
    root.innerHTML = `<div class="lh-samples">
      <header class="lh-samples-head"><div><h3>观察素材</h3><span>${loaded ? reviewEnabled ? "先审核素材" : "自动取样" : "读取中"} · ${application}</span></div>
        <div class="lh-samples-tools"><button class="lh-command" data-sample-refresh${disabled}>重新读取</button>
          <button class="lh-command is-primary" data-sample-learn${canLearn() ? "" : " disabled"}>${runtime.running ? "学习中…" : "立即学习"}</button></div></header>
      <div class="lh-samples-progress" role="status"><span>${e(statusText())}</span><span>可用 ${Number(runtime.eligible_samples || 0)} / ${Number(runtime.minimum_samples || 0)}</span>
        ${runtime.new_messages == null ? "" : `<span>新增 ${Number(runtime.new_messages)} / ${Number(runtime.required_new_messages)}</span><span>今日 ${Number(runtime.group_batches_today)} / ${Number(runtime.group_daily_batch_limit)} 批</span>`}</div>
      <nav class="lh-review-filters" aria-label="素材审核状态">${FILTERS.map(([key, label]) => `<button data-sample-filter="${key}" aria-pressed="${filter === key}"${disabled}>${label}<span>${key === "all" ? Object.values(counts).reduce((a,b) => a + Number(b), 0) : Number(counts[key] || 0)}</span></button>`).join("")}</nav>
      ${notice ? `<p class="lh-inline-status${error ? " is-error" : ""}" role="status">${e(notice)}</p>` : ""}
      <div class="lh-samples-list" aria-busy="${busy || writing}">${items.length ? items.map(item => `<article class="lh-sample" data-state="${e(item.state)}">
        <details><summary><span class="lh-sample-sender">${e(item.sender_id || "当前对象")}</span><time>${e(time(item.received_at))}</time><span class="lh-sample-state">${STATES[item.state] || "不可用"}${item.eligible ? " · 可学习" : ""}</span><span class="lh-sample-preview">${e(item.text)}</span></summary><p>${e(item.text)}</p></details>
        <footer>${(item.actions || []).filter(action => ["approve", "reject"].includes(action)).map(action => `<button class="lh-command${action === "approve" ? " is-primary" : ""}" data-sample-action="${action}" data-handle="${e(item.handle)}"${disabled}>${action === "approve" ? item.state === "rejected" ? "重新允许" : "允许学习" : "排除素材"}</button>`).join("")}</footer></article>`).join("")
        : `<div class="lh-review-empty">${busy ? "正在读取素材…" : loaded ? "当前筛选下暂无素材" : "尚未读取素材"}</div>`}</div>
      ${cursor ? `<button class="lh-command" data-sample-more${disabled}>加载更多</button>` : ""}</div>`;
  }
  function updated(current) {
    if (mounted(current)) window.dispatchEvent?.(new CustomEvent("companion-expression-updated", {detail:{scopeKey}}));
  }
  function poll(current) {
    clearTimeout(timer);
    if (mounted(current) && runtime.running) timer = setTimeout(() => { if (mounted(current)) void read(current); }, 4000);
  }
  async function read(current = ticket, append = false, keepNotice = false) {
    if (!mounted(current) || !apiBase || writing || busy) return;
    clearTimeout(timer);
    const request = ++readTicket, wasRunning = runtime.running;
    const query = {state:filter, limit:24};
    if (append && cursor) query.after_id = cursor;
    busy = true; render();
    try {
      const data = await api("GET", apiBase + "/style/samples", query);
      if (!mounted(current) || request !== readTicket) return;
      if (!Array.isArray(data.items) || !data.runtime) throw {code:"invalid_response"};
      items = append ? [...items, ...data.items.filter(item => !items.some(old => old.handle === item.handle))] : data.items;
      counts = data.counts || {}; cursor = data.next_cursor || null; runtime = data.runtime;
      reviewEnabled = data.sample_review_enabled === true; loaded = true;
      if (error && !keepNotice) {notice = ""; error = false;}
      if (wasRunning && !runtime.running) updated(current);
    } catch (problem) {
      if (!mounted(current) || request !== readTicket) return;
      notice = message(problem?.code); error = true; loaded = false;
    }
    if (!mounted(current) || request !== readTicket) return;
    busy = false; render(); poll(current);
  }
  async function command(handle, action) {
    const item = items.find(item => item.handle === handle);
    if (!item?.view_token || !item.actions?.includes(action) || busy || writing) return;
    const current = ticket;
    writing = true; notice = ""; error = false; clearTimeout(timer); render();
    try {
      await api("POST", apiBase + "/style/samples/command", {handle, action, view_token:item.view_token,
        operation_key:`sample-${action}-${Date.now()}-${Math.random().toString(36).slice(2,10)}`});
      if (!mounted(current)) return;
      notice = action === "approve" ? "素材已允许学习。" : "素材已排除，相关规则已停止应用。";
      updated(current);
    } catch (problem) {
      if (!mounted(current)) return;
      notice = message(problem?.code); error = true;
    }
    if (!mounted(current)) return;
    writing = false; await read(current, false, true);
  }
  async function learn() {
    if (!canLearn()) return;
    const current = ticket;
    writing = true; notice = ""; error = false; render();
    try {
      const result = await api("POST", apiBase + "/style/learn", {});
      if (!mounted(current)) return;
      runtime.last_result = result; notice = statusText(result);
    } catch (problem) {
      if (!mounted(current)) return;
      notice = message(problem?.code); error = true;
    }
    if (!mounted(current)) return;
    writing = false; await read(current, false, true);
  }
  function click(event) {
    if (busy || writing) return;
    const action = event.target.closest("[data-sample-action]");
    if (action) {void command(action.dataset.handle, action.dataset.sampleAction); return;}
    const choice = event.target.closest("[data-sample-filter]");
    if (choice && FILTERS.some(([key]) => key === choice.dataset.sampleFilter)) {
      filter = choice.dataset.sampleFilter; items = []; cursor = null; void read(); return;
    }
    if (event.target.closest("[data-sample-refresh]")) {notice = ""; void read();}
    if (event.target.closest("[data-sample-more]")) void read(ticket, true);
    if (event.target.closest("[data-sample-learn]")) void learn();
  }
  function saved(event) {if (event.detail?.group === "expression.learning" && event.detail?.scopeKey === scopeKey) void read();}
  function mount(host, options = {}) {
    unmount(); root = host;
    apiBase = typeof options.replyApi === "string" && options.replyApi.startsWith(PREFIX) && options.replyApi.endsWith("/reply") ? options.replyApi.slice(PREFIX.length) : "";
    scopeKey = options.scopeKey || "";
    items = []; counts = {}; runtime = {}; filter = "all"; cursor = null; loaded = false; notice = ""; error = false;
    const current = ++ticket;
    root?.addEventListener("click", click); window.addEventListener?.("companion-workbench-saved", saved);
    if (apiBase) void read(current); else {notice = "当前角色没有表达学习入口。"; error = true; render();}
  }
  function unmount() {
    ticket++; readTicket++; clearTimeout(timer); root?.removeEventListener("click", click);
    window.removeEventListener?.("companion-workbench-saved", saved);
    root = null; apiBase = ""; scopeKey = ""; busy = false; writing = false;
  }
  return {mount, unmount, get state() {return {items, counts, runtime, busy, writing, scopeKey};}};
})();
