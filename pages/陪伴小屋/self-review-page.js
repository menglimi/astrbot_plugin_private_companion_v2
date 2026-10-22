/* Daily review queue for evidence-bound role guidance. */
"use strict";
window.CompanionSelfReviewPage = (() => {
  const HOST = "astrbot_plugin_private_companion";
  const PREFIX = "/" + HOST + "/";
  const errors = {
    dashboard_identity_required:"当前登录状态不可用，请重新打开陪伴小屋。",
    staging_not_initialized:"角色数据尚未加载，请重新读取。",
    staging_host_terminated:"陪伴服务已停止，请重新读取。",
    relationship_required:"当前角色还没有可用的复盘权限。",
    self_review_query_invalid:"复盘列表条件无效，请刷新后重试。",
    self_review_command_invalid:"复盘操作未被接受，请刷新后重试。",
    self_review_item_unavailable:"这条复盘记录的来源已不可用。",
    self_review_view_stale:"复盘内容已有变化，请刷新后重新核对。",
    self_review_evidence_changed:"原始依据已变化或撤回，不能继续采纳。",
    self_review_expired:"这条短期建议已过期。",
    self_review_decided:"这条建议已经处理。",
    core_access_required:"当前账号没有复盘管理权限。",
    binding_revoked:"管理账号的授权已撤销。",
    binding_rebound:"管理账号的绑定已变化，请重新进入。",
    bridge_unavailable:"页面连接暂不可用，请重新读取。",
    bridge_timeout:"未收到服务确认，请刷新核对。",
    invalid_response:"服务返回的数据不完整，请刷新核对。",
  };
  const CODE = /^[a-z][a-z0-9_]{2,60}$/;
  const KIND = {try_next_time:"下次尝试", keep:"值得保持", ask_user:"需要先询问", no_change:"无需调整"};
  const e = value => String(value ?? "").replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;", "'":"&#39;"}[c]));
  const problem = code => Object.assign(new Error(errors[code] || "当前状态未能确认，请刷新核对。"), {code});
  const when = value => typeof value === "string" && Number.isFinite(Date.parse(value))
    ? new Date(value).toLocaleString("zh-CN", {hour12:false, month:"numeric", day:"numeric", hour:"2-digit", minute:"2-digit"})
    : "时间未知";
  let root = null, bridge = null, generation = 0, operation = 0, data = null;

  function fresh() {
    return {sources:[], state:"active", items:[], stopped:[], policy:null, loading:false, writing:false,
      confirming:"", notice:"", error:false, sourceErrors:[], expired:0};
  }
  function live(ticket) { return ticket === generation && root?.isConnected; }
  function note(message, error = false) { data.notice = message; data.error = error; }
  function rel(absolute) {
    if (typeof absolute !== "string" || !absolute.startsWith(PREFIX)) throw problem("invalid_response");
    const path = absolute.slice(PREFIX.length);
    if (!path || /[?#%\\:]/.test(path) || path.split("/").some(part => !part || part === "." || part === "..")) {
      throw problem("invalid_response");
    }
    return path;
  }
  async function bounded(promise) {
    let timeout;
    try {
      return await Promise.race([promise, new Promise((_, reject) => {
        timeout = setTimeout(() => reject(problem("bridge_timeout")), 15000);
      })]);
    } finally { clearTimeout(timeout); }
  }
  async function ready(ticket) {
    if (window.AstrBotPluginPage?.apiGet) return window.AstrBotPluginPage;
    const product = window.CompanionProduct;
    try {
      const found = product?.bridgeNow?.() || await product?.bridgeFor?.();
      if (found?.apiGet) return found;
    } catch { /* wait for the host bridge below */ }
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const tick = () => {
        if (!live(ticket)) return reject(problem("bridge_unavailable"));
        if (window.AstrBotPluginPage?.apiGet) return resolve(window.AstrBotPluginPage);
        if (Date.now() - started >= 10000) return reject(problem("bridge_unavailable"));
        setTimeout(tick, 80);
      };
      tick();
    });
  }
  async function api(source, method, suffix, body) {
    const response = await bounded(method === "GET"
      ? bridge.apiGet(source.path + suffix, body)
      : bridge.apiPost(source.path + suffix, body));
    const wrapped = ["ok", "error"].includes(response?.status) && response?.data !== undefined ? response
      : ["ok", "error"].includes(response?.data?.status) && response?.data?.data !== undefined ? response.data : null;
    if (wrapped?.status === "error") {
      const code = wrapped.data?.code || wrapped.message || "invalid_response";
      throw problem(CODE.test(code) ? code : "invalid_response");
    }
    const value = wrapped ? wrapped.data : response;
    if (!value || typeof value !== "object") throw problem("invalid_response");
    return value;
  }
  function reason(code) { return errors[code] || "当前状态未能确认，请刷新核对。"; }
  function actions(item, sourceKey) {
    const actionKey = sourceKey + "\u0000" + item.item_id;
    if (item.unavailable_reason) return `<span class="sr-state is-stopped">证据失效 · 暂停注入</span>`;
    if (item.state !== "pending") return `<span class="sr-state${item.expires_at&&Date.parse(item.expires_at)<=Date.now()?" is-stopped":""}">${item.kind === "no_change" && item.state === "rejected" ? "已收起" : item.state === "accepted" ? item.expires_at&&Date.parse(item.expires_at)<=Date.now()?"已过期":"生效中" : "已驳回"}</span>`;
    if (data.confirming === actionKey) return `<div class="sr-actions">
      <span>采纳后会在短期内作为该角色的工作指导。</span>
      <button class="button small primary" type="button" data-review-action="confirm" data-review-id="${e(item.item_id)}" data-review-source="${e(sourceKey)}">确认采纳</button>
      <button class="button small" type="button" data-review-action="cancel" data-review-id="${e(item.item_id)}" data-review-source="${e(sourceKey)}">取消</button></div>`;
    const choices = item.actions || [];
    return `<div class="sr-actions">${choices.includes("accept")
      ? `<button class="button small primary" type="button" data-review-action="accept" data-review-id="${e(item.item_id)}" data-review-source="${e(sourceKey)}">采纳为短期指导</button>` : ""}${choices.includes("reject")
      ? `<button class="button small" type="button" data-review-action="reject" data-review-id="${e(item.item_id)}" data-review-source="${e(sourceKey)}">${item.kind === "no_change" ? "收起结论" : "驳回"}</button>` : ""}</div>`;
  }
  function card(item) {
    const unavailable = item.unavailable_reason;
    const basis = Array.isArray(item.evidence) ? item.evidence : [];
    const confidence = Number.isFinite(Number(item.confidence)) ? Math.round(Number(item.confidence) * 100) : null;
    const expired = item.expires_at && Date.parse(item.expires_at) <= Date.now();
    return `<article class="sr-item">
      <header class="sr-item-head"><span class="sr-kind">${e(KIND[item.kind] || "复盘建议")}</span>
        <span class="sr-source">记录归属 · ${e(item._sourceLabel || "数据来源")}</span>
        <time datetime="${e(item.created_at || "")}">${e(when(item.created_at))}</time>
        ${confidence === null ? "" : `<span class="sr-confidence">置信度 ${confidence}%</span>`}
        ${expired ? `<span class="sr-expired">已过期</span>` : ""}</header>
      ${item.summary ? `<div class="sr-summary"><strong>本次复盘</strong><p>${e(item.summary)}</p></div>` : ""}
      ${unavailable ? `<p class="sr-unavailable">${e(reason(unavailable))}详情已隐藏。</p>` : `<div class="sr-review-body">
        <div><h3>观察</h3><p>${e(item.observation || "暂无观察内容")}</p></div>
        <div><h3>建议</h3><p>${e(item.next_action || "暂无后续建议")}</p></div>
      </div>${basis.length ? `<details class="sr-evidence"><summary>引用依据 · ${basis.length} 条</summary><ol>${basis.map(text => `<li>${e(text)}</li>`).join("")}</ol></details>` : ""}`}
      ${actions(item, item._sourceKey)}
    </article>`;
  }
  function render() {
    if (!root || !data) return;
    const valid=data.items.filter(item=>!item.unavailable_reason&&item.expires_at&&Date.parse(item.expires_at)>Date.now());
    const policy=data.policy||{};
    const duration=seconds=>Number.isFinite(seconds)?seconds%3600===0?`${seconds/3600} 小时`:seconds%60===0?`${seconds/60} 分钟`:`${seconds} 秒`:"—";
    const metrics=[["自动应用",data.items.filter(item=>item.automatic&&!item.unavailable_reason).length,"条"],
      ["生效中",valid.length,"条"],["复盘周期",Number.isFinite(policy.window_hours)?`${policy.window_hours} 小时`:"—",""],
      ["空结果重查",duration(policy.empty_retry_seconds),"后重查"]];
    const mechanisms=[
      ["复盘周期",Number.isFinite(policy.window_hours)?`${policy.window_hours} 小时`:"—"],
      ["证据门槛",Number.isInteger(policy.minimum_evidence)?`至少 ${policy.minimum_evidence} 条`:"—"],
      ["空结果重查",duration(policy.empty_retry_seconds)+" 后重查"],
      ["指导类型","下次尝试 · 保持 · 询问 · 无需调整"],
      ["生效方式","低风险建议自动应用；询问项进入审阅中心"],
    ];
    const active=valid.length?`<div class="sr-list">${valid.map(card).join("")}</div>`:`<div class="sr-empty">${data.loading?"正在读取…":"暂无生效中的指导"}</div>`;
    const stopped=data.stopped.length?`<section class="sr-stopped"><h3>已停止注入</h3><div class="sr-list">${data.stopped.map(card).join("")}</div></section>`:"";
    root.innerHTML=`<div class="sr-toolbar"><span>${data.sources.length} 个记录归属${data.loading?" · 正在读取":""}</span>
      <button class="lh-refresh" type="button" data-review-refresh aria-label="重新读取" title="重新读取" ${data.loading||data.writing?"disabled":""}><i data-lucide="refresh-cw"></i></button></div>
      ${data.notice?`<p class="sr-status${data.error?" is-error":""}" role="status" aria-live="polite">${e(data.notice)}</p>`:""}
      ${data.sources.length?`<section class="sr-kpis" aria-label="复盘状态">${metrics.map(([label,value,unit])=>`<article><span>${label}</span><strong>${e(value)}${unit&&typeof value==="number"?` ${unit}`:""}</strong></article>`).join("")}</section>
        <section class="sr-mechanism"><header><h2>复盘运行机制</h2><span>${data.loading?"":"已连接"}</span></header><div>${mechanisms.map(([label,value])=>`<article><strong>${label}</strong><span>${e(value)}</span></article>`).join("")}</div></section>
        <section class="sr-effective"><header><h2>生效中的自我指导</h2><span>${valid.length} 条</span></header>${active}</section>${stopped}`
        :`<div class="sr-empty">暂无复盘记录</div>`}
      ${data.error&&!data.sources.length?`<div class="sr-empty">${e(data.notice)}</div>`:""}
      ${data.sources.some(source=>source.next)?`<div class="sr-more"><button class="button small" type="button" data-review-more ${data.loading?"disabled":""}>加载更多</button></div>`:""}`;
    window.lucide?.createIcons({nodes:root.querySelectorAll("[data-lucide]")});
  }
  let loadGeneration = 0;
  async function load({append = false, force = false} = {}) {
    if (data.loading && !force) return;
    if (!data.sources.length) { note("暂无可读取的复盘记录。", true); render(); return; }
    const ticket = generation;
    const query = ++loadGeneration;
    data.loading = true;
    if (!append) {
      data.items = []; data.stopped=[];data.expired = 0; data.sourceErrors = [];data.policy=null;note("");
      data.sources.forEach(source => { source.next = ""; });
    }
    render();
    const targets = append ? data.sources.filter(source => source.next) : data.sources;
    const fetched = [], failures = [], stoppedKeys = new Set(
      data.stopped.map(item => `${item._sourceKey}\u0000${item.item_id}`));
    let expired = 0, succeeded = 0;
    for (let offset = 0; offset < targets.length; offset += 8) {
      const batch = targets.slice(offset, offset + 8);
      const results = await Promise.allSettled(batch.map(async source => {
        const after = append ? source.next : "";
        const active = await api(source, "GET", "/self-review", {
          state:"active", limit:50, ...(after ? {after_id:after} : {}),
        });
        const decided = append?{items:[]}:await api(source,"GET","/self-review",{state:"decided",limit:50});
        return {source, active, decided};
      }));
      if (!live(ticket) || query !== loadGeneration) return;
      results.forEach((settled, index) => {
        const source = batch[index];
        if (settled.status === "rejected") {
          failures.push(`${source.label}：${reason(settled.reason?.code)}`);
          return;
        }
        succeeded++;
        const {active,decided}=settled.value;
        source.next = typeof active.next_cursor === "string" ? active.next_cursor : "";
        if(!data.policy&&active.policy)data.policy=active.policy;
        if (Number.isInteger(decided.expired_in_page)) expired += decided.expired_in_page;
        for (const item of Array.isArray(active.items) ? active.items : []) {
          const enriched = {...item, _sourceKey:source.key, _sourceLabel:source.label};
          const expired = item.expires_at && Date.parse(item.expires_at) <= Date.now();
          if (item.unavailable_reason || expired) {
            const key = `${source.key}\u0000${item.item_id}`;
            if (!stoppedKeys.has(key)) { data.stopped.push(enriched); stoppedKeys.add(key); }
          } else fetched.push(enriched);
        }
        for(const item of Array.isArray(decided.items)?decided.items:[]){
          if(item.state==="accepted"&&(item.unavailable_reason||item.expires_at&&Date.parse(item.expires_at)<=Date.now())){
            const enriched={...item,_sourceKey:source.key,_sourceLabel:source.label};
            const key=`${source.key}\u0000${item.item_id}`;
            if(!stoppedKeys.has(key)){data.stopped.push(enriched);stoppedKeys.add(key);}
          }
        }
      });
    }
    if (!live(ticket) || query !== loadGeneration) return;
    data.items = append ? [...data.items, ...fetched] : fetched;
    data.items.sort((left, right) => Date.parse(right.created_at || "") - Date.parse(left.created_at || ""));
    data.expired = append ? data.expired + expired : expired;
    data.sourceErrors = failures;
    if (failures.length) note(succeeded
      ? `部分记录归属暂不可读（${failures.length}/${targets.length}）；已显示其余记录。`
      : `复盘记录暂时无法读取：${failures[0]}`, true);
    data.loading = false;
    render();
  }
  function operationKey(action, itemId) {
    return `self-review:${action}:${itemId}:${operation++}`;
  }
  async function decide(sourceKey, itemId, action) {
    const item = data.items.find(row => row.item_id === itemId && row._sourceKey === sourceKey);
    const source = data.sources.find(row => row.key === sourceKey);
    if (!item || data.writing || !item.actions?.includes(action)) return;
    if (!source) return;
    const ticket = generation;
    data.writing = true;
    data.confirming = "";
    note("");
    render();
    try {
      await api(source, "POST", "/self-review/command", {
        item_id:item.item_id, action, view_token:item.view_token,
        operation_key:operationKey(action, item.item_id),
      });
      if (!live(ticket)) return;
      await load({force:true});
      if (live(ticket)) note(action === "accept" ? "已采纳，短期指导已生效。" : item.kind === "no_change" ? "结论已收起。" : "已驳回。");
    } catch (failure) {
      if (live(ticket)) note(reason(failure.code), true);
    } finally {
      if (live(ticket)) { data.writing = false; render(); }
    }
  }
  function onClick(event) {
    const stateButton = event.target.closest("[data-review-state]");
    if (stateButton) {
      const next = stateButton.dataset.reviewState;
      if (["pending", "decided"].includes(next) && next !== data.state) {
        data.state = next; data.confirming = ""; load({force:true});
      }
      return;
    }
    if (event.target.closest("[data-review-refresh]")) { load({force:true}); return; }
    if (event.target.closest("[data-review-more]")) { load({append:true}); return; }
    const action = event.target.closest("[data-review-action]");
    if (!action) return;
    const itemId = action.dataset.reviewId;
    const sourceKey = action.dataset.reviewSource;
    const actionKey = sourceKey + "\u0000" + itemId;
    if (action.dataset.reviewAction === "accept") { data.confirming = actionKey; render(); }
    else if (action.dataset.reviewAction === "cancel") { data.confirming = ""; render(); }
    else if (action.dataset.reviewAction === "confirm") decide(sourceKey, itemId, "accept");
    else if (action.dataset.reviewAction === "reject") decide(sourceKey, itemId, "reject");
  }
  async function mount(host, options = {}) {
    unmount();
    root = host; data = fresh();
    if(["active","pending","decided"].includes(options.state))data.state=options.state;
    const seen = new Set();
    for (const [index, item] of (Array.isArray(options.sources) ? options.sources : []).entries()) {
      try {
        const path = rel(item?.api);
        const key = typeof item.key === "string" && item.key ? item.key : path;
        if (seen.has(key)) continue;
        seen.add(key);
        data.sources.push({path, key, label:typeof item.label === "string" && item.label ? item.label : `角色 ${index + 1}`, next:""});
      } catch { /* an invalid manifest entry cannot become a request route */ }
    }
    const ticket = ++generation;
    root.addEventListener("click", onClick);
    render();
    try {
      bridge = await ready(ticket);
      if (!live(ticket)) return;
      const context = await bounded(bridge.ready());
      if (!live(ticket)) return;
      if (context?.pluginName !== HOST) throw problem("bridge_unavailable");
      await load();
    } catch (failure) {
      if (live(ticket)) { note(reason(failure.code), true); data.loading = false; render(); }
    }
  }
  function unmount() {
    generation++;
    loadGeneration++;
    if (root) root.removeEventListener("click", onClick);
    root = null; bridge = null; data = null;
  }
  return {mount, unmount};
})();
