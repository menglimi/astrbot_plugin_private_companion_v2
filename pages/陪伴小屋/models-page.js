/* Model configuration: functional task routing, voice (TTS) and image generation, in three tabs. */
"use strict";
window.CompanionModelsPage = (() => {
  const PREFIX = "/astrbot_plugin_private_companion_v2/";
  const routing = ["provider", "fallback", "max_output_tokens"];
  const fields = ["provider", "fallback", "prompt", "max_output_tokens", "timeout_seconds", "replacement_rules", "fallback_on_refusal", "replacement_scope"];
  const fieldLabel = { provider: "主 Provider", fallback: "备用 Provider", prompt: "附加提示词",
    max_output_tokens: "输出上限", timeout_seconds: "请求超时", replacement_rules: "替换规则",
    fallback_on_refusal: "拒答替代", replacement_scope: "替换作用范围" };
  const groups = [
    ["对话", [["conversation.reply", "对话回复", "当前私聊的正文生成"]]],
    ["主动与记忆", [["proactive.compose", "主动联系", "有真实契机时组织联系内容"], ["memory.reflect", "记忆整理", "从已授权素材整理认识"]]],
    ["生活与成长", [["calendar.plan", "日程规划", "基于已有目标规划下一步"], ["role.state.maintain", "角色状态", "维护角色的连续生活状态"], ["role.reading.consume", "阅读理解", "阅读实际提供的原文"], ["role.growth.progress", "成长进展", "根据已完成确认提出进展"]]],
    ["私人书写", [["role.journal.diary", "日记", "保存私人书写"], ["role.journal.dream", "梦境", "保存梦境记录"], ["role.journal.derive", "书写整理", "整理已有文字素材"], ["role.journal.select", "素材选择", "选择本次书写素材"]]],
  ];
  const names = new Map(groups.flatMap(([group, items]) => items.map(([kind, label, description]) => [kind, { group, label, description }])));
  const errors = {
    configuration_revision_conflict: "配置已变化，草稿保留；核对当前值后再保存。", idempotency_key_conflict: "原保存请求与当前内容不一致，请刷新后核对。",
    model_configuration_invalid: "请核对任务配置、Provider 和输出上限。", model_task_unavailable: "此任务已不再注册，请刷新列表。",
    model_provider_unavailable: "当前 Provider 尚无 V2 适配器。", model_capability_mismatch: "所选 Provider 不支持这项任务。", model_output_limit: "输出上限超过所选 Provider 能力。",
    model_fallback_duplicate: "备用 Provider 必须与主 Provider 不同。", core_access_required: "当前账号没有管理权限。", dashboard_identity_required: "请从已登录的 AstrBot 管理界面打开小屋。",
    staging_not_initialized: "请先在账号与会话加载 V2 运行实例。", staging_host_terminated: "宿主已停止，请重新打开插件。", bridge_timeout: "连接超时，请核对原保存结果。",
    model_route_invalid: "替换规则未通过校验：请检查规则默认 Provider、匹配方式与时段。",
    model_refused: "所选 Provider 拒绝了这次请求。",
    model_probe_timeout: "测试超时，结果未知。", model_probe_failed: "Provider 未返回可确认结果。",
    model_provider_changed: "测试期间 Provider 已变化，请重新测试。",
    model_voice_probe_timeout: "语音测试超时，结果未知。", model_voice_probe_failed: "语音合成未返回可确认结果。",
    model_voice_provider_unavailable: "TTS Provider 尚未加载。", model_voice_audio_invalid: "Provider 未返回有效音频。",
    model_voice_provider_changed: "测试期间 TTS Provider 已变化，请重新测试。",
    model_image_store_failed: "生图开关保存失败，请检查宿主数据目录权限。",
    model_request_invalid: "请求未通过校验，请刷新后重试。",
    staging_profile_conflict: "当前宿主状态与固定 profile 不一致，请在账号与会话重新对配。",
    tts_provider_invalid: "Provider 配置项未通过校验，请核对必填项。", tts_provider_missing: "TTS Provider 不存在，请刷新列表。",
    tts_provider_exists: "Provider ID 已存在，请换一个。", tts_provider_unsupported: "当前 AstrBot 不支持动态管理 Provider。",
    model_image_config_unavailable: "生图扩展未加载，路线与连接不可用。", model_image_config_conflict: "生图配置已在别处修改，请重新读取后再保存。",
    model_image_config_invalid: "生图扩展拒绝了这些值，请核对路线与连接。", model_image_config_busy: "生图扩展正在执行任务，稍后再调整并发。",
  };
  /* Real dashboard bridges reject failed requests with the error code carried in
     Error.message; the mocked bridge resolves error envelopes with Error.code. */
  const fail = (err, fallback) => errors[err.code] || errors[err.message] || fallback;
  /* 后端把机器码放在信封的 message 上（页面桥只转发 message），所以取码要同时
     看 data.code 与 message；reason 里若是人话则原样保留。 */
  const CODE = /^[a-z][a-z0-9_]{2,60}$/;
  const codeOf = wrapped => wrapped?.data?.code
    || (CODE.test(wrapped?.message || "") ? wrapped.message : "") || "";
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const failure = (code, confirmed = false) => Object.assign(new Error(code), { code, confirmed });
  const states = new Map();
  let root = null, path = null, key = null, state = null, version = 0;
  const current = (ticket, s) => ticket === version && state === s && root?.isConnected;
  const taskOf = (s, kind) => s.status?.tasks.find(task => task.kind === kind) || null;
  const configSource = source => ({ default: "插件默认", installation: "安装级", role: "角色级", window: "当前对象" }[source] || "上级配置");
  const adoption = state => ({ applied: "已采用", next_task: "下次任务", consumer_not_started: "宿主未运行", failed: "采用失败", pending: "等待采用", restart_required: "需重启" }[state] || state);
  const taskName = kind => names.get(kind) || { group: "其他任务", label: kind, description: "V2 注册任务" };
  const snapshot = s => s?.status?.tasks || [];
  const available = (s, task) => s.status.providers.filter(p => task.capabilities.every(cap => p.capabilities.includes(cap)));
  const effective = (task, draft, name) => draft.inherited[name] ? task.fields[name].inherited_value : draft.values[name];
  const providerFor = (task, draft) => effective(task, draft, "provider");
  const limitFor = (s, task, draft) => Math.min(32768, ...["provider", "fallback"]
    .map(name => effective(task, draft, name)).filter(Boolean)
    .map(id => s.status.providers.find(provider => provider.id === id)?.max_output_tokens || 32768));
  function fitLimit(s, task, draft) { const limit = limitFor(s, task, draft);
    if (effective(task, draft, "max_output_tokens") <= limit) return false;
    draft.values.max_output_tokens = limit; draft.inherited.max_output_tokens = false; return true; }
  const storageKey = kind => key + ":" + kind;
  const shown = (s, task) => { const info = taskName(task.kind), custom = fields.some(name => !s.drafts.get(task.kind).inherited[name]);
    return (!s.providerFilter || s.providerFilter === providerFor(task, s.drafts.get(task.kind)))
      && (!s.lane || s.lane === "all" || s.lane === task.lane)
      && (!s.custom || s.custom === "custom" && custom || s.custom === "inherited" && !custom)
      && (info.label + info.group + info.description + task.kind).toLocaleLowerCase().includes(s.query.toLocaleLowerCase()); };
  const visible = s => snapshot(s).filter(task => shown(s, task));
  const selected = s => s.selection.filter(kind => taskOf(s, kind));
  const pendingCount = s => snapshot(s).reduce((count, task) => { const draft = s.drafts.get(task.kind); return count + (draft && !draft.pending && dirty(task, draft) ? 1 : 0); }, 0);
  function readPending(kind) { try { const p = JSON.parse(sessionStorage.getItem(storageKey(kind))); return p && p.kind === kind && typeof p.operation_key === "string" && typeof p.edit_token === "string" && p.changes && Array.isArray(p.reset) ? p : null; } catch { return null; } }
  function storePending(kind, p) { try { if (p) sessionStorage.setItem(storageKey(kind), JSON.stringify(p)); else sessionStorage.removeItem(storageKey(kind)); } catch { } }
  const newDraft = task => ({ token: task.edit_token, values: Object.fromEntries(fields.map(name => [name, task.fields[name].value])),
    inherited: Object.fromEntries(fields.map(name => [name, !task.fields[name].explicit])), touched: false, stale: false, pending: readPending(task.kind) });
  /* The replacement fields are optional in the payload: newer hosts expose them,
     older ones only ship the routing fields. Missing ones degrade to inherited. */
  const plainField = value => ({ value, inherited_value: value, source: "default", inherited_source: "default", explicit: false });
  function normalize(data) { const tasks = Array.isArray(data?.tasks) ? data.tasks : [];
    for (const task of tasks) { if (!task || typeof task !== "object") continue;
      task.fields = task.fields && typeof task.fields === "object" ? task.fields : {};
      if (task.fields.replacement_rules === undefined) task.fields.replacement_rules = plainField("[]");
      if (task.fields.fallback_on_refusal === undefined) task.fields.fallback_on_refusal = plainField(false);
      if (task.fields.timeout_seconds === undefined) task.fields.timeout_seconds = plainField(60);
      if (task.fields.replacement_scope === undefined) task.fields.replacement_scope = plainField("all"); }
    return data; }
  function patchFor(task, draft) { const changes = {}, reset = [];
    for (const name of fields) { const field = task.fields[name]; if (draft.inherited[name]) { if (field.explicit) reset.push(name); }
      else if (!field.explicit || draft.values[name] !== field.value) changes[name] = draft.values[name]; }
    return { changes, reset }; }
  const dirty = (task, draft) => { const p = patchFor(task, draft); return Object.keys(p.changes).length > 0 || p.reset.length > 0; };
  async function api(method, endpoint, body, timeout = 15000) { let timer;
    try { const bridge = window.CompanionProduct.bridgeNow() || await window.CompanionProduct.bridgeFor();
      const response = await Promise.race([method === "GET" ? bridge.apiGet(endpoint) : bridge.apiPost(endpoint, body), new Promise((_, reject) => { timer = setTimeout(() => reject(failure("bridge_timeout")), timeout); })]);
      const wrapped = ["ok", "error"].includes(response?.status) ? response : ["ok", "error"].includes(response?.data?.status) ? response.data : null;
      if (wrapped?.status === "error") throw failure(codeOf(wrapped) || "invalid_response", true);
      const value = wrapped ? wrapped.data : response;
      if (!value || typeof value !== "object" || Array.isArray(value)) throw failure("invalid_response");
      return value;
    } finally { clearTimeout(timer); } }
  function validateStatus(data) { if (!Array.isArray(data.tasks) || !Array.isArray(data.providers) || data.tasks.some(task =>
    typeof task.kind !== "string" || typeof task.edit_token !== "string" || task.edit_token.length !== 64
    || !task.fields || routing.some(name => !task.fields[name]) || routing.some(name => !Object.hasOwn(task.fields[name], "value")))) throw failure("invalid_response"); return data; }
  function setStatus(s, data) { s.status = validateStatus(normalize(data));
    for (const task of data.tasks) { const draft = s.drafts.get(task.kind);
      if (!draft) { s.drafts.set(task.kind, newDraft(task)); continue; }
      if (draft.token !== task.edit_token) { if (!draft.touched && !draft.pending) s.drafts.set(task.kind, newDraft(task)); else draft.stale = true; } }
    const kinds = new Set(data.tasks.map(task => task.kind)); s.selection = s.selection.filter(kind => kinds.has(kind));
    if (s.expanded && !kinds.has(s.expanded)) s.expanded = null; }
  const projected = (task, patch, name) => Object.hasOwn(patch.changes, name) ? patch.changes[name]
    : (patch.reset.includes(name) ? task.fields[name].inherited_value : task.fields[name].value);
  function validatePatch(task, p) { if (!Object.keys(p.changes).length && !p.reset.length) return false;
    if (Object.hasOwn(p.changes, "prompt") && (typeof p.changes.prompt !== "string" || p.changes.prompt.length > 8000)) return false;
    if (Object.hasOwn(p.changes, "max_output_tokens") && (!Number.isInteger(p.changes.max_output_tokens) || p.changes.max_output_tokens < 1 || p.changes.max_output_tokens > 32768)) return false;
    if (Object.hasOwn(p.changes, "timeout_seconds") && (!Number.isInteger(p.changes.timeout_seconds) || p.changes.timeout_seconds < 1 || p.changes.timeout_seconds > 600)) return false;
    if (Object.hasOwn(p.changes, "replacement_scope") && !["plugin", "conversation", "all"].includes(p.changes.replacement_scope)) return false;
    if (Object.hasOwn(p.changes, "fallback_on_refusal") && typeof p.changes.fallback_on_refusal !== "boolean") return false;
    if (Object.hasOwn(p.changes, "replacement_rules") && (typeof p.changes.replacement_rules !== "string" || p.changes.replacement_rules.length > 24000)) return false;
    const primary = projected(task, p, "provider"), fallback = projected(task, p, "fallback"), limit = projected(task, p, "max_output_tokens");
    const picked = [primary, ...(fallback ? [fallback] : [])], providers = picked.map(id => state.status.providers.find(provider => provider.id === id));
    return new Set(picked).size === picked.length && providers.every(provider => provider && task.capabilities.every(cap => provider.capabilities.includes(cap)) && limit <= provider.max_output_tokens); }
  /* ---------- functional markup (design alignment: MODEL_CONFIG_UI_UX_DESIGN_20260926) ---------- */
  /* Stable per-provider hue for the colored routing pills and map dots. */
  const hue = id => { let h = 0; for (const ch of String(id || "")) h = (h * 31 + ch.charCodeAt(0)) % 360; return h; };
  const pillColor = id => id ? `hsl(${hue(id)} 52% 46%)` : "var(--m-line2)";
  const icon = (paths, extra = "") => `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>${extra}`;
  const ICONS = {
    fn: '<path d="M4 6h16M4 12h10M4 18h7"/><circle cx="18" cy="17" r="3"/>',
    voice: '<path d="M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3Z"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="m4 18 5-5 3 3 3-3 5 5"/>',
    reply: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"/>',
    memory: '<circle cx="12" cy="12" r="9"/><path d="M12 8v4l2.5 2.5"/>',
    life: '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M8 2v4M16 2v4M3 10h18"/>',
    write: '<path d="M4 20l4-1 10-10-3-3L5 16l-1 4Z"/>',
    lane: '<path d="M4 6h16M4 12h16M4 18h16"/>' };
  const groupIcon = name => ({ "对话": ICONS.reply, "主动与记忆": ICONS.memory, "生活与成长": ICONS.life, "私人书写": ICONS.write }[name] || ICONS.lane);
  function topbar(s) {
    return `<div class="model-topbar"><span class="model-topbar-t">当前对象与角色 · 任务 → Provider 路由</span>
      <span class="model-pill ${s.status?.host_state === "running" ? "ok" : "warn"}">${esc(s.status?.host_state === "running" ? "宿主运行中" : s.status?.host_state || "未连接")}</span>
      <button type="button" class="button small" data-model-action="refresh" ${s.loading || s.busy ? "disabled" : ""}>刷新配置</button></div>`; }
  function overview(s) { const tasks = snapshot(s), custom = tasks.filter(task => fields.some(name => task.fields[name].explicit)).length;
    const withFb = tasks.filter(task => task.fields.fallback?.value).length;
    return `<div class="model-overview"><div><strong>${tasks.length}</strong><span>已注册任务</span></div>
      <div><strong>${s.status?.providers.length || 0}</strong><span>可用 Provider</span></div>
      <div><strong>${withFb}</strong><span>已设回退</span></div>
      <div><strong>${custom}</strong><span>单独设置的任务</span></div></div>`; }
  function notice(s) { const text = s.notice || (s.loading ? "正在读取任务配置…" : "改动进入待保存队列，按下“保存”后在下一次启动的任务生效。");
    return `<div class="model-notice ${s.bad ? "error" : ""}" role="status" aria-live="polite">${esc(text)}</div>`; }
  function rail(s) { const providers = s.status?.providers || []; if (!providers.length) return "";
    const used = id => snapshot(s).filter(task => providerFor(task, s.drafts.get(task.kind)) === id).length;
    const active = id => s.providerFilter === id ? " active" : "";
    return `<div class="model-mlgd" aria-label="可用的 Provider">${providers.map(provider => `<button type="button" class="model-lgd${active(provider.id)}" data-model-provider="${esc(provider.id)}" aria-pressed="${s.providerFilter === provider.id}">
        <i style="background:${pillColor(provider.id)}"></i><em>${esc(provider.id)}</em><span>${used(provider.id)} 项 · 上限 ${provider.max_output_tokens}</span></button>`).join("")}
      ${s.providerFilter ? `<button type="button" class="model-rail-clear" data-model-action="clear-provider">清除 Provider 筛选</button>` : ""}</div>`; }
  function toolbar(s) { const count = selected(s).length;
    return `<div class="model-toolbar"><label class="model-search"><span>搜索任务</span>
        <input type="search" data-model-search value="${esc(s.query)}" placeholder="名称、用途或任务键"></label>
      <div class="model-switches" role="group" aria-label="视图">${[["tasks", "按任务"], ["providers", "按 Provider"]].map(([id, label]) => `<button type="button" data-model-view="${id}" aria-pressed="${s.view === id}" class="${s.view === id ? "active" : ""}">${label}</button>`).join("")}</div>
      <div class="model-filters" role="group" aria-label="来源筛选">${[["all", "全部"], ["custom", "单独设置"], ["inherited", "跟随上级"]]
        .map(([id, label]) => { const on = (id === "all" && !s.custom) || s.custom === id; return `<button type="button" data-model-custom="${id}" aria-pressed="${on}" class="${on ? "active" : ""}">${label}</button>`; }).join("")}</div>
      <div class="model-filters" role="group" aria-label="通道筛选">${[["all", "全部通道"], ["foreground", "前台"], ["background", "后台"]]
        .map(([id, label]) => `<button type="button" data-model-lane="${id}" aria-pressed="${s.lane === id}" class="${s.lane === id ? "active" : ""}">${label}</button>`).join("")}</div></div>
    ${count ? `<div class="model-selection" role="status">已选 <strong>${count}</strong> 项任务
      <select data-model-assign aria-label="批量指派 Provider" ${s.busy || s.loading || s.denied ? "disabled" : ""}><option value="">批量指派 Provider…</option>${(s.status?.providers || []).map(provider => `<option value="${esc(provider.id)}">${esc(provider.id)}</option>`).join("")}</select>
      <button type="button" class="button small" data-model-action="inherit" ${s.busy || s.loading || s.denied ? "disabled" : ""}>恢复跟随上级</button>
      <button type="button" class="button small" data-model-action="clear-selection">取消选择</button></div>` : ""}`; }
  function queue(s) { const count = pendingCount(s); if (!count) return "";
    return `<div class="model-queue ${s.busy ? "busy" : ""}" role="status">
      <span><b>${count}</b> 项改动待保存 · 保存前不影响正在进行的任务</span>
      <button type="button" class="button primary small" data-model-action="save-all" ${s.busy || s.loading ? "disabled" : ""}>全部保存</button>
      <button type="button" class="button small" data-model-action="discard-all" ${s.busy || s.loading ? "disabled" : ""}>全部放弃</button></div>`; }
  /* Provider 的显示名：`id · 模型名`。
     只写 id 时，同一个 AstrBot 上挂两个同类型 Provider（很常见：一个便宜一个强）
     在下拉里是两行一模一样的字，选错只能靠试。模型名才是区分它们的信息。
     模型名允许为空（本地测试适配器没有这个概念），所以后缀是可选的而不是拼死的。 */
  const providerLabel = provider => provider && provider.model
    ? `${provider.id} · ${provider.model}` : provider ? provider.id : "";
  function providerOptions(s, task, draft, name) { const providers = available(s, task);
    const selected = draft.inherited[name] ? task.fields[name].inherited_value : draft.values[name];
    return `${name === "fallback" ? '<option value="">不使用备用 Provider</option>' : ''}${providers.map(provider => `<option value="${esc(provider.id)}" ${selected === provider.id ? "selected" : ""}>${esc(providerLabel(provider))}</option>`).join("")}
      ${selected && !providers.some(p => p.id === selected) ? `<option value="${esc(selected)}" selected>${esc(selected)} · 未注册</option>` : ""}`; }
  function sourceCell(s, task, draft) { const field = task.fields.provider;
    if (draft.inherited.provider) return `<span class="model-source inherit">跟随 ${esc(configSource(field.inherited_source || "default"))}</span>`;
    if (field.explicit) return `<span class="model-source own">当前对象单独设置</span>`;
    return `<span class="model-source pending">待保存</span>`; }
  /* Design: precise config uses one card per task (sc.fn), not a table. */
  function fnCard(s, task) { const info = taskName(task.kind), draft = s.drafts.get(task.kind), locked = s.loading || s.busy || s.denied;
    const picked = s.selection.includes(task.kind), open = s.expanded === task.kind, waiting = dirty(task, draft) && !draft?.pending;
    const limit = limitFor(s, task, draft);
    const main = providerFor(task, draft), fallback = effective(task, draft, "fallback");
    const own = fields.some(name => !draft.inherited[name]);
    const caps = available(s, task);
    const testing = main && s.testing.has(main), result = main ? s.providerTests[main] : null;
    return `<article class="model-fncard${open ? " open" : ""}${waiting ? " dirty" : ""}${picked ? " picked" : ""}" data-fncard="${esc(task.kind)}">
      <div class="model-sc-tp">
        <div class="model-eb">精准配置 · ${esc(info.group)}<span class="st">${own ? '<span class="model-tag a">单独设置</span>' : '<span class="model-tag n">跟随上级</span>'}</span></div>
        <div class="model-ti">${icon(groupIcon(info.group))}<b>${esc(info.label)}</b>
          <label class="model-pick"><input type="checkbox" data-model-pick="${esc(task.kind)}" ${picked ? "checked" : ""} aria-label="选择 ${esc(info.label)}"></label>
          <span class="model-tag ${task.lane === "foreground" ? "g" : "n"}">${task.lane === "foreground" ? "前台" : "后台"}</span></div>
        
        <div class="model-rl">${task.capabilities.map(cap => `<span>${esc(cap)}</span>`).join("") || "<span>无能力声明</span>"}</div>
      </div>
      <div class="model-sc-bd">
        ${draft.stale ? '<div class="model-alert">当前配置已更新。核对字段后，可保留草稿以新版本为基准继续编辑。</div>' : ""}
        ${draft.pending ? '<div class="model-alert">上次保存结果未确认。请核对原操作，避免重复提交。</div>' : ""}
        <label class="model-fd"><span class="model-cap">主 Provider <em>上级默认 ${esc(task.fields.provider.inherited_value || "未设置")}</em></span>
          <span class="model-msel"><i style="background:${pillColor(main)}"></i><select data-model-field="provider" data-model-kind="${esc(task.kind)}" aria-label="${esc(info.label)} 主 Provider" ${locked || draft.pending ? "disabled" : ""}>${providerOptions(s, task, draft, "provider")}</select></span></label>
        <label class="model-fd"><span class="model-cap">备用 Provider <em>主 Provider 失败、超时或拒答时尝试一次</em></span>
          <span class="model-msel"><i style="background:${pillColor(fallback)}"></i><select data-model-field="fallback" data-model-kind="${esc(task.kind)}" aria-label="${esc(info.label)} 备用 Provider" ${locked || draft.pending ? "disabled" : ""}>${providerOptions(s, task, draft, "fallback")}</select></span></label>
        <div class="model-duo">
          <label class="model-fd"><span class="model-cap">请求超时</span>
            <span class="model-unit"><input type="number" min="1" max="600" step="1" data-model-field="timeout_seconds" data-model-kind="${esc(task.kind)}" value="${esc(effective(task, draft, "timeout_seconds"))}" ${locked || draft.pending ? "disabled" : ""}><i>秒</i></span></label>
          <label class="model-fd"><span class="model-cap">单次输出上限</span>
            <span class="model-unit"><input type="number" min="1" max="${limit}" step="1" data-model-field="max_output_tokens" data-model-kind="${esc(task.kind)}" value="${esc(effective(task, draft, "max_output_tokens"))}" ${locked || draft.pending ? "disabled" : ""}><i>Token</i></span></label>
        </div>
        <label class="model-fd dash"><span class="model-cap">任务附加提示词 <em>最多 8000 字</em></span>
          <textarea rows="3" maxlength="8000" data-model-field="prompt" data-model-kind="${esc(task.kind)}" ${locked || draft.pending ? "disabled" : ""}>${esc(draft.inherited.prompt ? task.fields.prompt.inherited_value : draft.values.prompt)}</textarea></label>
        <div class="model-inh"><span class="lab">未单独设置时跟随上级</span>
          ${fields.map(name => `<label><input type="checkbox" data-model-inherit="${name}" data-model-kind="${esc(task.kind)}" ${draft.inherited[name] ? "checked" : ""} ${locked || draft.pending ? "disabled" : ""}>${esc(fieldLabel[name])}</label>`).join("")}</div>
      </div>
      <div class="model-sc-rf">
        <div class="r"><b>来源</b><span>${sourceCell(s, task, draft)}</span></div>
        <div class="r"><b>当前使用</b><span class="model-mono">${esc(main || "未设置")}${fallback ? " → " + esc(fallback) : ""}</span></div>
        <div class="r"><b>采用</b><span class="model-state ${draft?.pending ? "warn" : ""}">${esc(draft?.pending ? "待核对原保存" : adoption(task.application_state))}</span></div>
      </div>
      <div class="model-sc-ft"><code>${esc(task.kind)}</code>
        <span class="model-res">${result ? `<span class="model-resk ${result.status === "ok" ? "ok" : "bad"}">${result.status === "ok" ? "✓" : "！"}</span>${esc(probeLabel(result))}` : testing ? '<span class="model-sp"></span>测试中' : ""}</span>
        <button type="button" class="button small" data-provider-test="${esc(main)}" ${!main || testing ? "disabled" : ""}>测试</button>
        <span class="model-grow"></span>
        ${draft.stale && !draft.pending ? `<button type="button" class="button small" data-model-action="rebase" data-model-kind="${esc(task.kind)}">已核对，保留草稿</button>` : ""}
        ${draft.pending ? `<button type="button" class="button small" data-model-action="retry" data-model-kind="${esc(task.kind)}" ${s.busy ? "disabled" : ""}>核对原保存结果</button>` : ""}
        <button type="button" class="button small" data-model-action="discard" data-model-kind="${esc(task.kind)}" ${locked ? "disabled" : ""}>放弃</button>
        <button type="button" class="button small primary" data-model-action="save-one" data-model-kind="${esc(task.kind)}" ${locked || draft.stale || !dirty(task, draft) ? "disabled" : ""}>保存</button>
      </div>
      ${caps.length < 2 ? '<p class="model-hint">当前宿主仅注册支持该任务能力的 Provider ' + caps.length + ' 个，无法在此切换通道。</p>' : ""}
    </article>`; }
  function taskCards(s) { const rows = visible(s); if (!rows.length) return '<p class="model-empty">没有匹配的任务。</p>';
    return `<div class="model-qgrid">${rows.map(task => fnCard(s, task)).join("")}</div>`; }
  function providerView(s) { const providers = s.status?.providers || []; if (!providers.length) return '<p class="model-empty">尚未读取到 Provider。</p>';
    const tasks = visible(s), filtered = !!(s.query || s.custom || s.lane !== "all" || s.providerFilter);
    const panels = providers.filter(provider => !s.providerFilter || s.providerFilter === provider.id).map(provider => {
      const capable = tasks.filter(task => task.capabilities.every(cap => provider.capabilities.includes(cap)));
      const routed = tasks.filter(task => providerFor(task, s.drafts.get(task.kind)) === provider.id);
      if (filtered && !routed.length && s.providerFilter !== provider.id) return "";
      return `<article class="model-provider-panel"><header><span><strong>${esc(provider.id)}</strong><em>${routed.length} / ${capable.length} 项任务走这里</em></span>
          <span class="model-state">上限 ${provider.max_output_tokens}</span></header>
        ${provider.model ? `<p class="model-provider-model">${esc(provider.model)}</p>` : ""}
        <p class="model-provider-caps">${provider.capabilities.map(cap => `<small>${esc(cap)}</small>`).join("") || "<small>无能力声明</small>"}</p>
         <ul class="model-provider-tasks">${routed.map(task => { const info = taskName(task.kind);
           return `<li><button type="button" data-model-open="${esc(task.kind)}" aria-label="编辑 ${esc(info.label)} 的模型配置">${esc(info.label)}</button></li>`; }).join("") || '<li class="model-empty">还没有任务走这个 Provider。</li>'}</ul>
         ${capable.length > routed.length ? `<p class="model-provider-note">还有 ${capable.length - routed.length} 项能力相符的任务由其他 Provider 承担。</p>` : ""}</article>`; }).filter(Boolean);
    return panels.length ? `<div class="model-providers">${panels.join("")}</div>` : '<p class="model-empty">没有匹配的任务。</p>'; }
  function body(s) { if (!s.status) return '<p class="model-empty">连接 V2 宿主后显示已注册任务。</p>';
    if (!snapshot(s).length) return '<p class="model-empty">当前宿主还没有注册任何模型任务。</p>';
    return s.view === "providers" ? providerView(s) : taskCards(s); }
  function syncInput(kind) { const s = state; if (!root || !s) return;
    const slot = root.querySelector(".model-queue-slot"); if (slot) slot.innerHTML = queue(s);
    const task = taskOf(s, kind), draft = s.drafts.get(kind);
    const save = [...root.querySelectorAll('[data-model-action="save-one"]')].find(button => button.dataset.modelKind === kind);
    if (save && task && draft) save.disabled = draft.stale || draft.pending || !dirty(task, draft); }
  /* ---------- functional actions ---------- */
  async function refresh() { const s = state, ticket = version; if (!s || s.loading || s.busy) return; s.loading = true; s.notice = "正在读取任务配置…"; render();
    try { const data = await api("GET", path); if (!current(ticket, s)) return; setStatus(s, data); s.bad = false; s.denied = false; s.notice = "已读取当前任务配置。"; }
    catch (err) { if (!current(ticket, s)) return; s.bad = true; s.denied = true; s.notice = fail(err, "无法读取任务配置，请检查宿主连接。"); }
    finally { s.loading = false; if (current(ticket, s)) render(); } }
  async function saveTasks(s, kinds) { if (s.busy || s.loading || s.denied) return; const unsaved = kinds.filter(kind => { const task = taskOf(s, kind), draft = s.drafts.get(kind);
    return task && draft && !draft.stale && !draft.pending && dirty(task, draft); });
    if (!unsaved.length) { s.bad = true; s.notice = "这些任务没有待保存的改动。"; render(); return; }
    const ticket = version; s.busy = true; s.bad = false; s.notice = `正在保存 ${unsaved.length} 项任务路由…`; render();
    const failed = []; let saved = 0;
    for (const kind of unsaved) { if (ticket !== version) return;
      const task = taskOf(s, kind), draft = s.drafts.get(kind); if (!task || !draft) continue;
      const patch = patchFor(task, draft);
      if (!validatePatch(task, patch)) { failed.push(`${taskName(kind).label}：字段校验未通过`); continue; }
      draft.pending = { kind, operation_key: crypto.randomUUID(), edit_token: draft.token, ...patch }; storePending(kind, draft.pending); render();
      try { const result = await api("POST", path + "/configure", draft.pending);
        if (ticket !== version) return;
        if (result?.task?.kind !== kind || typeof result.replayed !== "boolean") throw failure("invalid_response");
        storePending(kind, null); const index = s.status.tasks.findIndex(t => t.kind === kind); if (index >= 0) s.status.tasks[index] = result.task;
        s.drafts.set(kind, newDraft(result.task)); saved++; }
      catch (err) { if (ticket !== version) return;
        if (err.confirmed) { storePending(kind, null); draft.pending = null; draft.stale = true; }
        failed.push(`${taskName(kind).label}：${fail(err, "保存未通过")}`); }
      render(); }
    if (ticket !== version) return;
    s.busy = false; s.bad = failed.length > 0;
    s.notice = failed.length ? `已保存 ${saved} 项；${failed.length} 项未通过：${failed.join("；")}。改动仍保留，核对后可继续保存。`
      : `已保存 ${saved} 项。下一次启动的任务会采用当前配置。`;
    render(); }
  async function retry(s, kind) { const task = taskOf(s, kind), draft = s.drafts.get(kind); if (!draft?.pending || s.busy) return;
    const ticket = version; s.busy = true; s.notice = "正在核对原保存结果…"; render();
    try { const result = await api("POST", path + "/configure", draft.pending); if (!current(ticket, s)) return;
      if (result?.task?.kind !== kind || typeof result.replayed !== "boolean") throw failure("invalid_response");
      storePending(kind, null); const index = s.status.tasks.findIndex(t => t.kind === kind); if (index >= 0) s.status.tasks[index] = result.task;
      s.drafts.set(kind, newDraft(result.task)); s.bad = false; s.notice = result.replayed ? "原保存已确认。下一次任务会采用当前配置。" : "已保存。下一次任务会采用当前配置。"; }
    catch (err) { if (!current(ticket, s)) return; s.bad = true;
      if (err.confirmed) { storePending(kind, null); draft.pending = null; draft.stale = true; s.notice = fail(err, "保存未通过。请刷新并核对。"); }
      else s.notice = "保存结果尚未确认。请核对原保存结果后继续编辑。"; }
    finally { s.busy = false; if (current(ticket, s)) render(); } }
  function assign(s, providerId) { const kinds = selected(s); if (!providerId || !kinds.length) return;
    const skipped = []; let changed = 0;
    for (const kind of kinds) { const task = taskOf(s, kind), draft = s.drafts.get(kind); if (!task || !draft || draft.pending || draft.stale) continue;
      if (!task.capabilities.every(cap => s.status.providers.find(p => p.id === providerId)?.capabilities.includes(cap))) { skipped.push(taskName(kind).label); continue; }
      if (draft.values.provider === providerId && !draft.inherited.provider) continue;
      draft.inherited.provider = false; draft.values.provider = providerId; draft.touched = true; fitLimit(s, task, draft); changed++; }
    s.bad = skipped.length > 0;
    s.notice = changed ? `已把 ${changed} 项任务指派给 ${providerId}${skipped.length ? `；${skipped.length} 项能力不符已跳过：${skipped.join("、")}` : ""}。记得保存。`
      : (skipped.length ? `没有任务被改动；能力不符：${skipped.join("、")}。` : "没有任务被改动。");
    render(); }
  function discard(s, kinds) { let count = 0;
    for (const kind of kinds) { const task = taskOf(s, kind), draft = s.drafts.get(kind); if (!task || !draft || draft.pending) continue;
      s.drafts.set(kind, newDraft(task)); count++; }
    s.bad = false; s.notice = count ? `已放弃 ${count} 项任务的草稿。` : '没有可放弃的草稿。'; render(); }
  function restoreInherit(s, kinds) { let count = 0;
    for (const kind of kinds) { const task = taskOf(s, kind), draft = s.drafts.get(kind); if (!task || !draft || draft.pending) continue;
      for (const name of fields) draft.inherited[name] = true;
      draft.touched = true; count++; }
    s.bad = false; s.notice = count ? `已把 ${count} 项任务改为跟随上级配置，保存后生效。` : '没有可调整的任务。'; render(); }
  /* ---------- functional events ---------- */
  function fnInput(event) { const s = state; if (!s || s.busy || s.loading || s.denied) return; const target = event.target;
    /* The policy pane owns toggles and selects, so it gets every input event. */
    if (s.sub === "pol") { event.type === "change" ? ruleChange(s, event) : ruleInput(s, event); return; }
    if (target.matches("[data-model-search]")) { s.query = target.value; render(); const next = root.querySelector("[data-model-search]");
      if (next) { next.focus(); next.setSelectionRange(next.value.length, next.value.length); } return; }
    if (target.matches("[data-model-slot]")) { s.slotDraft[target.dataset.modelSlot] = target.value; render(); return; }
    const kind = target.dataset.modelKind;
    if (target.matches("[data-model-assign]")) { assign(s, target.value); target.value = ""; return; }
    if (!kind) return;
    const inheritName = target.dataset.modelInherit;
    if (inheritName) { const draft = s.drafts.get(kind); if (draft && !draft.pending) { draft.inherited[inheritName] = target.checked; draft.touched = true; render(); } return; }
    const name = target.dataset.modelField; if (!name || !fields.includes(name)) return;
    const draft = s.drafts.get(kind), task = taskOf(s, kind); if (!draft || !task || draft.pending) return;
    draft.values[name] = ["max_output_tokens", "timeout_seconds"].includes(name)
      ? (Number.isFinite(target.valueAsNumber) ? target.valueAsNumber : draft.values[name]) : target.value;
    draft.inherited[name] = false;
    const adjusted = (name === "provider" || name === "fallback") && fitLimit(s, task, draft);
    if (adjusted) { s.notice = `${taskName(kind).label} 的输出上限已调整为 ${draft.values.max_output_tokens}，请核对后保存。`; s.bad = false; }
    draft.touched = true;
    if (event.type === "change") render(); else syncInput(kind); }
  function fnClick(event) { const s = state; if (!s) return;
    if (event.target.closest("[data-drawer-close]")) { s.drawer = null; render(); return; }
    const pill = event.target.closest("[data-provider-pill]");
    if (pill) { s.drawer = s.drawer === pill.dataset.providerPill ? null : pill.dataset.providerPill; render(); return; }
    const goto = event.target.closest("[data-drawer-goto]");
    if (goto) { s.drawer = null; s.sub = "cfg"; s.cm = "precise"; s.view = "tasks"; s.providerFilter = goto.dataset.drawerGoto; render(); return; }
    const exp = event.target.closest("[data-model-exp]");
    if (exp) { const key = exp.dataset.modelExp; s.expOpen[key] = !s.expOpen[key]; render(); return; }
    const gpick = event.target.closest("[data-model-gpick]");
    if (gpick) { const key = gpick.dataset.modelGpick;
      const kinds = key.startsWith("lane:") ? snapshot(s).filter(t => t.lane === key.slice(5)).map(t => t.kind)
        : (groups.find(([name]) => name === key) || [null, []])[1].map(([kind]) => kind);
      if (kinds.length) { const all = kinds.every(kind => s.rule.picked.includes(kind));
        s.rule.picked = all ? s.rule.picked.filter(kind => !kinds.includes(kind)) : Array.from(new Set(s.rule.picked.concat(kinds)));
        s.rule.report = null; render(); } return; }
    const sub = event.target.closest("[data-model-sub]"); if (sub) { s.sub = sub.dataset.modelSub; render(); return; }
    /* The select-all checkbox lives inside the row button, so the pick has to win. */
    const mapPick = event.target.closest("[data-map-pick]");
    if (mapPick) { const kind = mapPick.dataset.mapPick;
      s.rule.picked = s.rule.picked.includes(kind) ? s.rule.picked.filter(item => item !== kind) : s.rule.picked.concat(kind);
      s.rule.report = null; render(); return; }
    /* Opening a task jumps to its precise editor, from any subtab or provider view. */
    const openTask = event.target.closest("[data-model-open]");
    if (openTask) { const kind = openTask.dataset.modelOpen, wasOpen = s.sub === "cfg" && s.cm === "precise" && s.view === "tasks";
      s.sub = "cfg"; s.view = "tasks"; s.cm = "precise"; s.expanded = wasOpen && s.expanded === kind ? null : kind; render();
      if (s.expanded) { try { const card = root.querySelector('[data-fncard="' + kind + '"]');
        if (card && card.scrollIntoView) card.scrollIntoView({ block: "nearest", behavior:
          (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches) ? "auto" : "smooth" }); } catch { } }
      return; }
    const policyMode = event.target.closest("[data-model-pm]");
    if (policyMode) { s.pm = policyMode.dataset.modelPm; render(); return; }
    if (s.sub === "pol") { ruleClick(s, event); return; }
    const mapClear = event.target.closest("[data-map-clear]"); if (mapClear) { s.rule.picked = []; s.rule.report = null; render(); return; }
    const mapTest = event.target.closest("[data-map-test]"); if (mapTest) { runMapTest(s); return; }
    const providerTest = event.target.closest("[data-provider-test]");
    if (providerTest) { probeProvider(s, providerTest.dataset.providerTest); return; }
    const cm = event.target.closest("[data-model-cm]"); if (cm) { s.cm = cm.dataset.modelCm; render(); return; }
    const av = event.target.closest("[data-model-av]"); if (av) { s.av = av.dataset.modelAv; render(); return; }
    const af = event.target.closest("[data-model-af]"); if (af) { s.af = af.dataset.modelAf; render(); return; }
    const slotApply = event.target.closest("[data-model-slot-apply]"); if (slotApply) { applySlot(s, slotApply.dataset.modelSlotApply); return; }
    const pick = event.target.closest("[data-model-pick]");
    if (pick) { const kind = pick.dataset.modelPick; s.selection = s.selection.includes(kind) ? s.selection.filter(item => item !== kind) : s.selection.concat(kind); render(); return; }
    const provider = event.target.closest("[data-model-provider]");
    if (provider) { const id = provider.dataset.modelProvider; s.providerFilter = s.providerFilter === id ? null : id; render(); return; }
    const custom = event.target.closest("[data-model-custom]");
    if (custom) { const id = custom.dataset.modelCustom; s.custom = id === "all" ? null : id; render(); return; }
    const lane = event.target.closest("[data-model-lane]");
    if (lane) { s.lane = lane.dataset.modelLane; render(); return; }
    const view = event.target.closest("[data-model-view]");
    if (view) { s.view = view.dataset.modelView; render(); return; }
    const action = event.target.closest("[data-model-action]")?.dataset.modelAction; if (!action || s.busy && action !== "refresh") return;
    if (action === "refresh") { refresh(); return; }
    if (action === "clear-provider") { s.providerFilter = null; render(); return; }
    if (action === "clear-selection") { s.selection = []; render(); return; }
    if (action === "inherit") { restoreInherit(s, selected(s)); return; }
    if (action === "discard-all") { discard(s, selected(s).length ? selected(s) : snapshot(s).map(task => task.kind)); return; }
    if (action === "save-all") { const kinds = snapshot(s).map(task => task.kind); saveTasks(s, kinds); return; }
    const kind = event.target.closest("[data-model-action]")?.dataset.modelKind; if (!kind || s.busy || s.loading) return;
    const draft = s.drafts.get(kind); if (!draft) return;
    if (action === "save-one") { saveTasks(s, [kind]); return; }
    if (action === "discard") { s.drafts.set(kind, newDraft(taskOf(s, kind))); s.notice = "草稿已放弃。"; s.bad = false; render(); }
    if (action === "rebase") { draft.token = taskOf(s, kind).edit_token; draft.stale = false; s.notice = "已采用当前版本作为保存基准，草稿仍待保存。"; s.bad = false; render(); }
    if (action === "retry") retry(s, kind); }
  /* ---------- voice model ---------- */
  const voiceCurrent = v => v.data.languages.find(l => l.k === v.ui.lang) || v.data.languages[0];
  const voiceBinding = (v, lang) => v.draft.bindings[lang.k] ?? "";
  const voiceChanges = v => { const changes = {};
    for (const lang of v.data.languages) { const name = `voice_${lang.k}_provider_id`;
      if (voiceBinding(v, lang) !== lang.bind) changes[name] = voiceBinding(v, lang); }
    if (v.draft.timeout_seconds !== v.data.timeout_seconds) changes.voice_timeout_seconds = v.draft.timeout_seconds;
    return changes; };
  const voiceDirty = v => !!v.draft && Object.keys(voiceChanges(v)).length > 0;
  const voiceDraft = data => ({bindings: Object.fromEntries(data.languages.map(lang => [lang.k, lang.bind])), timeout_seconds: data.timeout_seconds});
  async function voiceRefresh(s) { const v = s.voice, ticket = version; if (v.loading) return; v.loading = true; v.notice = "正在读取语音配置…"; render();
    try { const data = await api("GET", path + "/voice"); if (!current(ticket, s)) return;
      if (!Array.isArray(data.languages) || !Array.isArray(data.providers) || typeof data.edit_token !== "string") throw failure("invalid_response");
      if (v.draft && voiceDirty(v)) v.stale = v.data.edit_token !== data.edit_token;
      else v.draft = voiceDraft(data);
      v.data = data; v.loaded = true; v.bad = false; v.notice = "已读取当前 TTS 绑定。"; }
    catch (err) { if (!current(ticket, s)) return; v.bad = true; v.notice = fail(err, "无法读取语音配置。"); }
    finally { v.loading = false; if (current(ticket, s)) render(); } }
  async function voiceSave(s, retry = false) { const v = s.voice;
    if (v.busy || v.loading || !v.data || v.stale || (!retry && !voiceDirty(v))) return;
    if (!Number.isInteger(v.draft.timeout_seconds) || v.draft.timeout_seconds < 1 || v.draft.timeout_seconds > 120) {
      v.bad = true; v.notice = "语音超时需要设置为 1–120 秒。"; render(); return; }
    const ticket = version, command = retry ? v.pending : {operation_key: crypto.randomUUID(), edit_token: v.data.edit_token, changes: voiceChanges(v)};
    if (!command) return; v.pending = command; v.busy = true; v.bad = false; v.notice = "正在保存语音配置…"; render();
    try { const data = await api("POST", path + "/voice/save", command); if (!current(ticket, s)) return;
      if (!Array.isArray(data.languages) || typeof data.edit_token !== "string") throw failure("invalid_response");
      v.data = data; v.draft = voiceDraft(data); v.pending = null; v.stale = false; v.notice = data.replayed ? "原保存已确认。" : "语音配置已保存，下一次语音回复生效。"; }
    catch (err) { if (!current(ticket, s)) return; v.bad = true;
      if (err.confirmed) { v.pending = null; v.stale = true; }
      v.notice = err.confirmed ? (fail(err, "保存未通过，请刷新核对配置。")) : "保存结果未确认，可重试同一请求核对结果。"; }
    finally { v.busy = false; if (current(ticket, s)) render(); } }
  async function voiceTest(s) { const v = s.voice, lang = voiceCurrent(v), providerId = voiceBinding(v, lang);
    if (!providerId || v.testing || !v.data.providers.some(p => p.id === providerId)) return;
    const ticket = version; v.testing = true; v.lastTest = null; v.notice = ""; render();
    try { const result = await api("POST", path + "/voice/test", {provider_id: providerId, language: lang.k}, 125000);
      if (!current(ticket, s)) return;
      v.lastTest = {status: result.status, latency_ms: result.latency_ms, code: result.code || ""}; }
    catch (err) { if (!current(ticket, s)) return;
      v.lastTest = {status: "unknown", code: err.code || err.message || ""}; }
    finally { v.testing = false; if (current(ticket, s)) render(); } }
  /* V1-parity diagnostics: the outcome names the failure stage instead of a bare error. */
  const VOICE_SAMPLES = {"zh": "你好。", "ja": "こんにちは。", "en": "Hello."};
  const voiceTestLabel = r => r.status === "ok" ? `语音合成成功 · ${r.latency_ms} ms`
    : r.code ? (errors[r.code] || "语音合成结果未知。") : "语音合成结果未知。";
  /* ---------- TTS provider management (V1 parity; AstrBot owns provider configs) ---------- */
  async function ttsCatalogLoad(s) { const v = s.voice; if (v.catalogLoading) return;
    const ticket = version; v.catalogLoading = true; render();
    try { const data = await api("GET", path + "/tts/providers"); if (!current(ticket, s)) return;
      v.catalog = data; }
    catch (err) { if (!current(ticket, s)) return; v.catalog = { items: [], templates: [], error: fail(err, "无法读取 Provider 配置列表。") }; }
    finally { v.catalogLoading = false; if (current(ticket, s)) render(); } }

  const ttsSelected = v => (v.catalog && v.catalog.items || []).find(item => item.id === v.editorId) || null;
  function ttsValues(v, item) { if (!v.editorValues[item.id]) { const values = {};
      for (const field of item.fields) values[field.key] = field.secret ? "" : (field.value === null || field.value === undefined ? "" : field.value);
      values.enable = item.enable; v.editorValues[item.id] = values; }
    return v.editorValues[item.id]; }

  const ttsField = (field, values) => {
    const attr = `data-tts-field="${esc(field.key)}"`;
    if (field.type === "bool") return `<label class="model-fd"><span class="model-cap">${esc(field.label)}</span>
      <label class="model-switch"><input type="checkbox" ${attr} ${values[field.key] ? "checked" : ""}><i></i></label></label>`;
    if (field.options.length) return `<label class="model-fd"><span class="model-cap">${esc(field.label)}</span>
      <select ${attr}>${field.options.map(option => `<option value="${esc(option.value)}" ${String(values[field.key]) === option.value ? "selected" : ""}>${esc(option.label)}</option>`).join("")}</select></label>`;
    if (field.secret) return `<label class="model-fd"><span class="model-cap">${esc(field.label)} <em>${field.set ? "已配置 · 留空表示保留" : "未配置"}</em></span>
      <input type="password" ${attr} value="" placeholder="${field.set ? "已配置，留空表示保留" : "请输入"}" autocomplete="new-password"></label>`;
    const type = field.type === "int" || field.type === "float" ? "number" : "text";
    return `<label class="model-fd"><span class="model-cap">${esc(field.label)}${field.hint ? ` <em>${esc(field.hint)}</em>` : ""}</span>
      <input type="${type}" ${attr} value="${esc(values[field.key] === undefined ? "" : values[field.key])}"></label>`; };

  function ttsEditor(s) { const v = s.voice;
    if (!v.editorOpen) return "";
    if (v.catalogLoading) return '<div class="model-card"><p class="model-empty">正在读取 Provider 配置…</p></div>';
    if (!v.catalog) return "";
    if (v.catalog.error) return `<div class="model-card"><p class="model-notice error">${esc(v.catalog.error)}</p></div>`;
    const items = v.catalog.items || [];
    const item = ttsSelected(v) || items[0] || null;
    if (item) v.editorId = item.id;
    const creating = v.creating;
    const templates = v.catalog.templates || [];
    const createType = v.createDraft.type || (templates[0] && templates[0].type) || "";
    const fields = item && item.fields ? item.fields : [];
    const values = item ? ttsValues(v, item) : null;
    return `<div class="model-card tts-editor"><div class="model-phead"><div class="model-grow"><span class="model-eb">连接管理</span><h3>TTS Provider 配置</h3></div>
        <button type="button" class="button small" data-tts-create-toggle ${v.ttsBusy ? "disabled" : ""}>${creating ? "收起新建" : "+ 新建 Provider"}</button></div>
      ${creating ? `<div class="model-vcreate">
          <label class="model-fd"><span class="model-cap">提供商类型</span>
            <select data-tts-type>${templates.map(template => `<option value="${esc(template.type)}" ${template.type === createType ? "selected" : ""}>${esc(template.label)}</option>`).join("")}</select></label>
          <label class="model-fd"><span class="model-cap">Provider ID <em>字母、数字、点、下划线、冒号、短横线</em></span>
            <input data-tts-id value="${esc(v.createDraft.id)}" placeholder="例如 fishaudio-ja"></label>
          <div class="model-editor-actions"><button type="button" class="button small primary" data-tts-create ${v.ttsBusy || !createType ? "disabled" : ""}>创建（默认停用）</button></div>
        </div>` : ""}
      ${items.length ? `<label class="model-fd"><span class="model-cap">编辑对象</span>
          <select data-tts-pick>${items.map(option => `<option value="${esc(option.id)}" ${option.id === (item && item.id) ? "selected" : ""}>${esc(option.id)} · ${esc(option.label)}${option.enable ? " · 已启用" : " · 停用"}${option.loaded ? "" : " · 未加载"}</option>`).join("")}</select></label>` : '<p class="model-empty">还没有可管理的 TTS Provider。</p>'}
      ${item && values ? `<div class="model-tts-fields">
          <label class="model-fd"><span class="model-cap">启用 <em>停用的 Provider 不能被语种绑定使用</em></span>
            <label class="model-switch"><input type="checkbox" data-tts-enable ${values.enable ? "checked" : ""}><i></i></label></label>
          ${fields.map(field => ttsField(field, values)).join("")}
        </div>
        <div class="model-editor-actions">
          <button type="button" class="button primary" data-tts-save ${v.ttsBusy ? "disabled" : ""}>保存 Provider 配置</button>
          <button type="button" class="button" data-tts-clone ${v.ttsBusy ? "disabled" : ""}>克隆为${esc(voiceCurrent(v).n)}专用</button></div>
        <p class="model-note">新建或克隆后需启用。保存对所有会话生效。</p>` : ""}
    </div>`; }

  async function ttsCreate(s) { const v = s.voice; if (v.ttsBusy) return;
    const providerType = v.createDraft.type || (v.catalog && v.catalog.templates && v.catalog.templates[0] && v.catalog.templates[0].type) || "";
    const providerId = String(v.createDraft.id || "").trim();
    if (!providerType || !providerId) { v.bad = true; v.notice = "先选择类型并填写 Provider ID。"; render(); return; }
    const ticket = version; v.ttsBusy = true; v.notice = "正在创建 Provider…"; render();
    try { const data = await api("POST", path + "/tts/providers/create", {type: providerType, id: providerId}, 30000);
      if (!current(ticket, s)) return;
      v.catalog = data; v.editorValues = {}; v.editorId = providerId; v.creating = false;
      v.createDraft = { type: "", id: "" }; v.bad = false; v.notice = "Provider 已创建（默认停用），填写连接并启用。"; }
    catch (err) { if (!current(ticket, s)) return; v.bad = true; v.notice = fail(err, "Provider 创建未完成。"); }
    finally { v.ttsBusy = false; if (current(ticket, s)) render(); } }

  async function ttsSave(s) { const v = s.voice, item = ttsSelected(v); if (!item || v.ttsBusy) return;
    const values = ttsValues(v, item); const ticket = version; v.ttsBusy = true; v.notice = "正在保存 Provider 配置…"; render();
    try { const data = await api("POST", path + "/tts/providers/update", {provider_id: item.id, values}, 30000);
      if (!current(ticket, s)) return;
      v.catalog = data; delete v.editorValues[item.id]; v.bad = false; v.notice = "Provider 配置已保存，写入 AstrBot Provider 配置。"; }
    catch (err) { if (!current(ticket, s)) return; v.bad = true; v.notice = fail(err, "Provider 配置保存未完成。"); }
    finally { v.ttsBusy = false; if (current(ticket, s)) render(); } }

  async function ttsClone(s) { const v = s.voice, item = ttsSelected(v); if (!item || v.ttsBusy) return;
    const lang = voiceCurrent(v), ticket = version; v.ttsBusy = true; v.notice = "正在克隆 Provider…"; render();
    try { const data = await api("POST", path + "/tts/providers/clone", {provider_id: item.id, language: lang.k}, 30000);
      if (!current(ticket, s)) return;
      v.catalog = data; v.editorValues = {}; v.editorId = data.created_id || v.editorId;
      if (v.draft) v.draft.bindings[lang.k] = data.created_id || "";
      v.bad = false; v.notice = `已克隆为 ${v.editorId}（默认停用），当前语种草稿已指向它；启用并保存语种绑定后生效。`; }
    catch (err) { if (!current(ticket, s)) return; v.bad = true; v.notice = fail(err, "Provider 克隆未完成。"); }
    finally { v.ttsBusy = false; if (current(ticket, s)) render(); } }

  function voicePane(s) { const v = s.voice; if (!v.data || !v.draft) return `<p class="model-empty">${esc(v.notice || "正在读取语音配置…")}</p>`;
    const lang = voiceCurrent(v), binding = voiceBinding(v, lang), loaded = v.data.providers.some(p => p.id === binding);
    const bound = v.data.languages.filter(item => voiceBinding(v, item)).length;
    const missing = binding && !loaded;
    const shared = binding ? v.data.languages.filter(item => item.k !== lang.k && voiceBinding(v, item) === binding) : [];
    const dot = item => { const b = voiceBinding(v, item); return !b ? "var(--m-line2)" : v.data.providers.some(p => p.id === b) ? "var(--m-green)" : "var(--m-red)"; };
    const sub = item => { const b = voiceBinding(v, item); return b ? esc(b) + (v.data.providers.some(p => p.id === b) ? " · 已加载" : " · 未加载") : "跟随会话 Provider"; };
    const test = v.lastTest;
    return `<div class="model-voice">
      <div class="model-card"><div class="model-phead"><div class="model-grow"><span class="model-eb">合成后端</span><h3>语音模型</h3></div>
          <button type="button" class="button small" data-go="manage" data-manage="reply">TTS 增强设置 ↗</button>
          <button type="button" class="button small" data-voice-refresh ${v.loading || v.busy ? "disabled" : ""}>刷新</button></div>
        <div class="model-kpis">${kpi(v.data.voice_enabled ? "已开启" : "未开启", "语音回复")}${kpi(bound + "/3", "专用语种绑定")}${kpi(v.data.providers.length, "已加载 TTS Provider")}${kpi(v.data.timeout_seconds + "s", "当前合成超时")}</div></div>
      <div class="model-card"><div class="model-phead"><div class="model-grow"><span class="model-eb">按语种配置 TTS</span><h3>${esc(lang.n)}</h3></div>
          <span class="model-tag ${missing ? "r" : binding ? "g" : "n"}">${missing ? "绑定未加载" : binding ? "已加载" : "跟随会话"}</span>
          <button type="button" class="button small" data-voice-editor ${v.loading || v.busy ? "disabled" : ""}>${v.editorOpen ? "收起连接管理" : "新建 / 编辑连接"}</button></div>
        <div class="model-vtabs">${v.data.languages.map(item => `<button type="button" data-voice-lang="${esc(item.k)}" class="${item.k === lang.k ? "on" : ""}"><b><i class="d" style="background:${dot(item)}"></i>${esc(item.n)}</b><small>${sub(item)}</small></button>`).join("")}</div>
        ${shared.length ? `<div class="model-sharewarn"><span style="flex:1">该 Provider 同时绑定到${shared.map(item => item.n).join("、")}。V2 按语种独立保存，修改当前语种不会影响其他语种。</span>
          <button type="button" class="button small" data-voice-unbind ${v.busy || v.loading || v.pending ? "disabled" : ""}>解除${shared.map(item => item.n).join("、")}绑定</button></div>` : ""}
        <div class="model-vbar"><label class="model-fd"><span class="model-cap">${esc(lang.n)} 语音合成 Provider <em>连接、凭据和声音由 AstrBot TTS 配置管理</em></span>
          <select data-voice-provider ${v.busy || v.loading || v.pending ? "disabled" : ""}><option value="">跟随 AstrBot 当前会话 Provider</option>
            ${v.data.providers.map(p => `<option value="${esc(p.id)}" ${p.id === binding ? "selected" : ""}>${esc(p.id)}</option>`).join("")}
            ${missing ? `<option value="${esc(binding)}" selected>${esc(binding)} · 未加载</option>` : ""}</select></label></div>
        <div class="model-vfoot"><span class="model-play">▶</span><span class="model-sample">试听样句：${esc(VOICE_SAMPLES[lang.k] || "")}</span>
          <span class="model-res">${v.testing ? '<span class="model-sp"></span>测试中'
            : test ? `<span class="model-resk ${test.status === "ok" ? "ok" : "bad"}">${test.status === "ok" ? "✓" : "！"}</span>${esc(voiceTestLabel(test))}` : ""}</span>
          <span class="model-grow"></span>
          <span class="model-note">${binding ? "测试只在服务端合成样句，不在聊天中发送音频。" : "未指定时由 AstrBot 当前会话选择 TTS。"}</span>
          <button type="button" class="button small primary" data-ve-test ${!loaded || v.testing ? "disabled" : ""}>${v.testing ? "测试中…" : "测试合成"}</button></div>
      </div>
      ${v.editorOpen ? ttsEditor(s) : ""}
      <div class="model-card"><div class="model-phead"><div class="model-grow"><span class="model-eb">语音请求</span><h3>合成超时与保存</h3></div></div>
        <div class="model-fd"><span class="model-cap">合成超时（秒）</span>
          <span class="model-unit"><input type="number" min="1" max="120" data-voice-timeout value="${esc(v.draft.timeout_seconds)}" ${v.busy || v.loading || v.pending ? "disabled" : ""}><i>秒</i></span></div>
        <p class="model-note">${!v.data.voice_enabled ? "语音回复未开启，请到「表达」启用。" : "发送策略见「表达」。"}</p>
        <div class="model-editor-actions"><button type="button" class="button primary" data-voice-save ${v.busy || v.loading || v.pending || v.stale || !voiceDirty(v) ? "disabled" : ""}>保存语音配置</button>
          ${v.pending ? '<button type="button" class="button" data-voice-retry>核对原保存结果</button>' : ""}
          ${v.stale ? '<button type="button" class="button" data-voice-rebase>核对后用当前版本保存</button>' : ""}</div></div>
      ${v.notice ? `<div class="model-notice ${v.bad ? "error" : ""}" role="status">${esc(v.notice)}</div>` : ""}</div>`; }
  function voiceInput(s, event) { const v = s.voice; if (v.loading || v.busy) return; const t = event.target;
    if (t.matches("[data-voice-provider]")) { if (!v.draft || v.pending) return; v.draft.bindings[voiceCurrent(v).k] = t.value; v.lastTest = null; render(); }
    if (t.matches("[data-voice-timeout]")) { if (!v.draft || v.pending) return; v.draft.timeout_seconds = t.valueAsNumber; if (event.type === "change") render(); }
    if (t.matches("[data-tts-field]")) { const item = ttsSelected(v); if (!item || v.ttsBusy) return;
      const values = ttsValues(v, item), key = t.dataset.ttsField;
      values[key] = t.type === "checkbox" ? t.checked : (t.type === "number" && Number.isFinite(t.valueAsNumber) ? t.valueAsNumber : t.value);
      if (event.type === "change") render(); return; }
    if (t.matches("[data-tts-enable]")) { const item = ttsSelected(v); if (!item || v.ttsBusy) return;
      ttsValues(v, item).enable = t.checked; if (event.type === "change") render(); return; }
    if (t.matches("[data-tts-type]")) { v.createDraft.type = t.value; render(); return; }
    if (t.matches("[data-tts-id]")) { v.createDraft.id = t.value; return; }
    if (t.matches("[data-tts-pick]")) { v.editorId = t.value; if (event.type === "change") render(); return; } }
  function voiceClick(s, event) { const v = s.voice, t = event.target;
    const lang = t.closest("[data-voice-lang]"); if (lang) { v.ui.lang = lang.dataset.voiceLang; render(); return; }
    if (t.closest("[data-voice-editor]")) { v.editorOpen = !v.editorOpen; if (v.editorOpen && !v.catalog) ttsCatalogLoad(s); render(); return; }
    if (t.closest("[data-tts-create-toggle]")) { v.creating = !v.creating; render(); return; }
    if (t.closest("[data-tts-create]")) { ttsCreate(s); return; }
    if (t.closest("[data-tts-save]")) { ttsSave(s); return; }
    if (t.closest("[data-tts-clone]")) { ttsClone(s); return; }
    const unbind = t.closest("[data-voice-unbind]");
    if (unbind) { const current = voiceBinding(v, voiceCurrent(v));
      if (current) v.data.languages.forEach(item => { if (item.k !== v.ui.lang && voiceBinding(v, item) === current) v.draft.bindings[item.k] = ""; });
      v.lastTest = null; v.bad = false; v.notice = "已解除其他语种的同 Provider 绑定，保存语音配置后生效。"; render(); return; }
    if (t.closest("[data-voice-refresh]")) { voiceRefresh(s); return; }
    if (t.closest("[data-voice-save]")) { voiceSave(s); return; }
    if (t.closest("[data-voice-retry]")) { voiceSave(s, true); return; }
    if (t.closest("[data-voice-rebase]")) { v.stale = false; render(); return; }
    if (t.closest("[data-ve-test]")) voiceTest(s); }
  /* ---------- image model ---------- */
  const IMAGE_LABELS = {"image.generate": "文生图", "image.edit": "改图", "image.mask_edit": "局部改图"};
  const imageDirty = i => i.data && i.draft && Object.keys(i.draft).some(action => i.draft[action] !== i.data.enabled[action]);
  async function imageRefresh(s) { const i = s.image, ticket = version; if (i.loading) return; i.loading = true; i.notice = "正在读取 Native 生图能力…"; render();
    try { const data = await api("GET", path + "/image"); if (!current(ticket, s)) return;
      if (!Array.isArray(data.actions) || !data.enabled || Object.keys(IMAGE_LABELS).some(action => typeof data.enabled[action] !== "boolean")) throw failure("invalid_response");
      if (!imageDirty(i)) i.draft = {...data.enabled}; i.data = data; i.loaded = true; i.bad = false; i.notice = "已读取当前 Native 动作状态。"; }
    catch (err) { if (!current(ticket, s)) return; i.bad = true; i.notice = fail(err, "无法读取生图能力。"); }
    finally { i.loading = false; if (current(ticket, s)) render(); } }
  async function imageSave(s) { const i = s.image; if (i.busy || i.loading || !imageDirty(i)) return;
    const ticket = version; i.busy = true; i.bad = false; i.notice = "正在保存 Native 生图开关…"; render();
    try { const data = await api("POST", path + "/image/save", {enabled: {...i.draft}}); if (!current(ticket, s)) return;
      if (!Array.isArray(data.actions) || !data.enabled) throw failure("invalid_response");
      i.data = data; i.draft = {...data.enabled}; i.notice = "生图开关已保存，后续调用会采用当前设置。"; }
    catch (err) { if (!current(ticket, s)) return; i.bad = true; i.notice = fail(err, "生图开关保存结果未确认，请刷新核对。"); }
    finally { i.busy = false; if (current(ticket, s)) render(); } }
  async function imageTest(s, action) { const i = s.image, ticket = version; if (i.testing || !IMAGE_LABELS[action]) return;
    i.testing = action; i.notice = `正在检查${IMAGE_LABELS[action]}注册状态…`; render();
    try { const result = await api("POST", path + "/image/test", {action}); if (!current(ticket, s)) return;
      i.bad = result.state !== "ready"; i.notice = result.state === "ready" ? `${IMAGE_LABELS[action]}已注册，可由后续真实任务调用。`
        : result.state === "disabled" ? `${IMAGE_LABELS[action]}当前已关闭。` : `${IMAGE_LABELS[action]}扩展未加载或声明已变化。`; }
    catch (err) { if (!current(ticket, s)) return; i.bad = true; i.notice = fail(err, "注册检查未完成。"); }
    finally { i.testing = null; if (current(ticket, s)) render(); } }
  /* ---------- image route configuration (owned by the image extension) ---------- */
  /* 扩展下发的数值边界表。页面的 min/max 与提交前挡下都用它，
     自己不再抄一份数字——抄一份就会漂移，而漂移的表现是
     「页面放行、扩展拒绝」，用户提交一次才知道被拒。
     扩展没给（旧版本）时退回空表，此时只是不写 min/max，不影响其它功能。 */
  const imageLimits = i => i.config?.limits || null;
  /* 路线配置的请求体上限。路线说明是可长文本（扩展的单键上限 4000 字），
     而保存提交的是整份路线数组，写满时能到几百 KB。这里先挡一次，
     为的是给一句「哪条路线的说明太长」，而不是让用户收到宿主那句
     「model request is too large」。数字必须与宿主一致：
     astrbot_host/model_api.py 的 image_config_save 用的是同一个值。 */
  const IMAGE_SAVE_LIMIT = 262144;
  const limitSpan = (i, section, key) => {
    const limits = imageLimits(i);
    const span = limits && limits[section] && limits[section][key];
    return span && Number.isFinite(span.min) && Number.isFinite(span.max) ? span : null; };
  /* 生成 number 输入框的 min/max。没有边界时不留空属性——
     写 min="" 会让浏览器报 "The specified value is not a valid number"。 */
  const numAttrs = (i, section, key) => { const span = limitSpan(i, section, key);
    return span ? ` min="${span.min}" max="${span.max}"` : ""; };

  /* ---------- 路线的四个预置字段 ----------
   * 扩展把每条路线读成一份 spec，除页面已编辑的五个标量外还有四个字段：
   *   parameters          数值/文本参数，有真实运行时效果 → 给控件，边界用扩展下发的 limits
   *   guidance            选路线的说明（六键，含一个受约束的枚举）→ 给控件
   *   reference_bindings  必须与工作流的图槽位一致，槽位表扩展未下发 → 只读
   *   masked_edit         派生值（等于绑定里是否存在 edit_mask），不是开关 → 只读
   * 页面挡一次只为当场说清是哪一条路线哪一格越界；扩展那边必须留着同样的判断。 */
  const PARAM_LABELS = {width: "宽", height: "高", seed: "随机种子", steps: "步数", batch_size: "每批张数",
                        cfg_scale: "提示词强度", denoising_strength: "重绘幅度", sampler_name: "采样器"};
  const PARAM_ORDER = ["width", "height", "seed", "steps", "batch_size", "cfg_scale", "denoising_strength", "sampler_name"];
  const GUIDE_LABELS = {summary: "一句话说明", edit_method: "改图方式", suitable_for: "适用场景",
                        limitations: "局限", prompt_advice: "提示建议", test_notes: "实测记录"};
  const GUIDE_LIST_KEYS = ["suitable_for", "limitations"];
  const GUIDE_TEXT_KEYS = ["summary", "prompt_advice", "test_notes"];
  const EDIT_METHODS = {auto: "自动（未声明）", whole_image: "整图重绘", instruction: "指令编辑",
                        masked: "蒙版局部", controlled: "受控工作流"};
  const EDIT_ROLES = {identity: "身份", outfit: "服装", pose: "姿态", style: "风格",
                      background: "背景", continuity: "延续", edit_source: "底图", edit_mask: "蒙版"};
  /* 展开状态挂在路线对象上（WeakSet），不进草稿——草稿会被整段提交给扩展，
     多一个页面自己的键就会被它的严格校验拒掉。 */
  const expandedRoutes = new WeakSet();

  /* 某个后端允许写的参数字段及其边界，全部来自扩展的 limits.parameters。 */
  function paramSpecs(i, backend) {
    const all = (imageLimits(i) || {}).parameters || {};
    const specs = [];
    const push = (key, spec) => { if (key) specs.push({key, ...spec}); };
    for (const [key, span] of Object.entries(all.common || {})) push(key, {kind: "int", min: span.min, max: span.max});
    if (backend === "sd_webui") {
      for (const [key, span] of Object.entries(all.sd_webui || {})) push(key, {kind: "int", min: span.min, max: span.max});
      for (const [key, span] of Object.entries(all.float || {})) push(key, {kind: "float", min: span.min, max: span.max});
      for (const [key, span] of Object.entries(all.text || {})) push(key, {kind: "text", maxLength: span.max_length});
    }
    /* 顺序固定，避免后端下发的键序变化让控件跳来跳去。 */
    return specs.sort((a, b) => {
      const left = PARAM_ORDER.indexOf(a.key), right = PARAM_ORDER.indexOf(b.key);
      return (left < 0 ? PARAM_ORDER.length : left) - (right < 0 ? PARAM_ORDER.length : right);
    });
  }

  /* 改图方式的可选项。约束在扩展那边：非改图路线只能是 auto；
     SD WebUI 的允许集取决于 masked_edit（蒙版路线才有 masked）。 */
  function guidanceMethods(route) {
    if (route.operation !== "edit") return ["auto"];
    if (route.backend === "sd_webui") return route.masked_edit === true ? ["auto", "masked"] : ["auto", "whole_image"];
    return ["auto", "whole_image", "instruction", "masked", "controlled"];
  }

  function paramCell(i, route, index, spec) {
    const value = (route.parameters || {})[spec.key];
    const shown = value === undefined || value === null ? "" : String(value);
    const label = PARAM_LABELS[spec.key] || spec.key;
    const title = `${spec.key}${spec.kind === "int" ? ` · ${spec.min}–${spec.max}` : spec.kind === "float" ? ` · ${spec.min}–${spec.max}` : ` · 最多 ${spec.maxLength} 字`}`;
    const attrs = spec.kind === "text"
      ? `maxlength="${spec.maxLength}"`
      : `type="number" step="${spec.kind === "float" ? "0.01" : "1"}" min="${spec.min}" max="${spec.max}"`;
    return `<label class="model-imgr-p" title="${esc(title)}"><span class="model-cap">${esc(label)}</span>
      <input ${attrs} data-imgr-param="${index}:${esc(spec.key)}" value="${esc(shown)}" placeholder="未声明" aria-label="参数 ${esc(spec.key)}">
      <em class="model-mono">${esc(spec.key)}</em></label>`;
  }

  function guidanceCell(route, index) {
    const guidance = route.guidance || {};
    const methods = guidanceMethods(route);
    const current = typeof guidance.edit_method === "string" ? guidance.edit_method : "";
    /* 已声明但当前后端/操作不接受时补一条标注，不静默改写用户配置。 */
    const extra = current && !methods.includes(current)
      ? `<option value="${esc(current)}" selected>${esc(EDIT_METHODS[current] || current)}（当前不接受，保存会被拒）</option>` : "";
    const select = `<label class="model-imgr-g"><span class="model-cap">${esc(GUIDE_LABELS.edit_method)}</span>
      <select data-imgr-guide="${index}:edit_method">
        <option value="" ${!current ? "selected" : ""}>未声明</option>
        ${methods.map(m => `<option value="${m}" ${current === m ? "selected" : ""}>${esc(EDIT_METHODS[m])}</option>`).join("")}
        ${extra}</select></label>`;
    const text = key => `<label class="model-imgr-g"><span class="model-cap">${esc(GUIDE_LABELS[key])}</span>
      <textarea rows="2" data-imgr-guide="${index}:${key}" placeholder="未声明">${esc(guidance[key] || "")}</textarea></label>`;
    const list = key => `<label class="model-imgr-g"><span class="model-cap">${esc(GUIDE_LABELS[key])} <em>每行一条</em></span>
      <textarea rows="2" data-imgr-guide="${index}:${key}" placeholder="每行一条">${esc((guidance[key] || []).join("\n"))}</textarea></label>`;
    return select + text("summary") + list("suitable_for") + list("limitations") + text("prompt_advice") + text("test_notes");
  }

  /* 只读的两项：写清它是什么、由谁核验、为什么本页不给控件。 */
  function presetReadOnly(route) {
    const bindings = Array.isArray(route.reference_bindings) ? route.reference_bindings : [];
    const bindingText = bindings.length
      ? bindings.map(b => `${EDIT_ROLES[b && b.role] || (b && b.role) || "未知用途"} ← ${(b && b.slot) || "?"}`).join("；")
      : "未声明（由工作流里的图输入自动绑定）";
    return `<div class="model-imgr-ro">
      <p><b>参考图绑定</b> ${esc(bindingText)}</p>
      
      <p><b>蒙版改图</b> ${route.masked_edit === true ? "已声明" : "未声明"}（不是开关）</p>
      
    </div>`;
  }

  function routeExtras(i, route, index) {
    const specs = paramSpecs(i, route.backend || "comfyui");
    const params = specs.length
      ? `<div class="model-imgr-ps">${specs.map(spec => paramCell(i, route, index, spec)).join("")}</div>`
      : `<p class="model-note">${route.backend === "sd_webui" ? "SD WebUI" : "ComfyUI"} 的参数字段边界尚未从扩展读到，保存前无法在本页挡下越界值。</p>`;
    return `<details class="model-imgr-ext" data-imgr-ext="${index}" ${expandedRoutes.has(route) ? "open" : ""}>
      <summary>参数与路线说明（4 项预置字段）</summary>
      <div class="model-imgr-body">
        <div class="model-fd"><span class="model-cap">数值参数 <em>留空表示未声明，交给扩展默认值</em></span>${params}</div>
        <div class="model-imgr-gs">${guidanceCell(route, index)}</div>
        ${presetReadOnly(route)}
      </div></details>`;
  }

  /* 超过宿主请求体上限时的提示：只说「太大了」用户没法下手，
     所以要报出最占地方的那条路线。 */
  function oversizedNotice(changes, size) {
    const routes = Array.isArray((changes.preparation || {}).routes) ? changes.preparation.routes : [];
    let worst = "", worstSize = 0;
    routes.forEach((route, index) => {
      const bytes = JSON.stringify(route || {}).length;
      if (bytes > worstSize) { worstSize = bytes; worst = (route && route.route_id) || `第 ${index + 1} 条`; } });
    const kb = Math.round(size / 1024), limitKb = Math.round(IMAGE_SAVE_LIMIT / 1024);
    return `路线配置共约 ${kb} KB，超过一次能保存的 ${limitKb} KB。`
      + (worst ? `最占地方的是「${worst}」（约 ${Math.round(worstSize / 1024)} KB）：先缩短它的路线说明，或删掉不再用的路线。` : "");
  }

  async function imageConfigLoad(s) { const i = s.image; if (i.configLoading) return;
    const ticket = version; i.configLoading = true; render();
    try { const data = await api("GET", path + "/image/config"); if (!current(ticket, s)) return;
      i.config = data; const draft = JSON.parse(JSON.stringify(data.sections || {}));
      if (draft.preparation) draft.preparation.routes = (draft.preparation.routes || []).map(route =>
        typeof route === "string" ? JSON.parse(route) : route);
      i.configDraft = draft; }
    catch (err) { if (!current(ticket, s)) return; i.config = { error: fail(err, "无法读取生图路线配置。") }; }
    finally { i.configLoading = false; if (current(ticket, s)) render(); } }

  /* ComfyUI 原生适配：工作流按名称引用；行编辑把配置里的字符串路径 / 内联对象规范化呈现 */
  const workflowNames = comfyRows => comfyRows.map(row => row.__name || "").filter(Boolean);
  function comfyRowsFrom(draftComfy) {
    if (Array.isArray(draftComfy.__rows)) return draftComfy.__rows;
    const raw = draftComfy.workflows || [];
    draftComfy.__rows = raw.map(entry => {
      if (typeof entry === "string") return { __kind: "path", __name: entry.split(/[\\/]/).pop().replace(/\.[^.]+$/, ""), path: entry };
      const inline = entry && typeof entry.workflow === "string" && entry.workflow;
      const name = String(entry.name || "");
      return { __kind: inline ? "inline" : "path", __name: name, name, path: String(entry.path || ""), raw: entry };
    });
    return draftComfy.__rows;
  }
  const comfyEntriesForSave = rows => rows.map(row => row.__kind === "inline"
    ? { ...(row.raw || {}), name: row.__name || row.name || "" }
    : (row.raw ? { ...(row.raw || {}), name: row.name || row.__name || "", path: row.path || "" }
               : (row.path || "").trim()));

  function imageConfigChanges(i) {
    if (!i.config || !i.configDraft) return {};
    const before = i.config.sections || {}, draft = i.configDraft, changes = {};
    for (const name of Object.keys(draft)) {
      const diff = {}, originalSection = before[name] || {};
      for (const [key, value] of Object.entries(draft[name] || {})) {
        if (key === "api_key") {
          if (draft[name].__clear_key === true) diff[key] = "";
          else if (String(value || "").trim()) diff[key] = String(value);
          continue; }
        if (key === "__rows" || key === "__clear_key" || (name === "comfyui" && key === "workflows" && Array.isArray(draft[name].__rows))) continue;
        let original = originalSection[key];
        if (name === "preparation" && key === "routes" && Array.isArray(value)) {
          original = Array.isArray(original) ? original.map(route => {
            if (typeof route !== "string") return route;
            try { return JSON.parse(route); } catch { return route; }
          }) : [];
        }
        if (JSON.stringify(value) !== JSON.stringify(original)) diff[key] = value;
      }
      if (name === "comfyui" && Array.isArray(draft[name]?.__rows)) {
        const workflows = comfyEntriesForSave(draft[name].__rows);
        if (JSON.stringify(workflows) !== JSON.stringify(originalSection.workflows || [])) diff.workflows = workflows; }
      if (Object.keys(diff).length) changes[name] = diff;
    }
    return changes;
  }
  const imageConfigDirty = i => Object.keys(imageConfigChanges(i)).length > 0;

  function imageConfigEditor(s) { const i = s.image;
    if (!i.configOpen) return "";
    if (i.configLoading) return '<div class="model-imgconfig"><p class="model-empty">正在读取生图路线配置…</p></div>';
    if (!i.config) return "";
    if (i.config.error) return `<div class="model-imgconfig"><p class="model-notice error" role="status">${esc(i.config.error)}</p></div>`;
    const draft = i.configDraft || (i.configDraft = {});
    const prep = draft.preparation || (draft.preparation = {});
    const routes = prep.routes || (prep.routes = []);
    const sd = draft.sd_webui || (draft.sd_webui = {});
    const comfy = draft.comfyui || (draft.comfyui = {});
    const comfyRows = comfyRowsFrom(comfy);
    const srcSections = i.config.sections || {};
    const keyFlag = present => present ? "已配置 · 留空保留" : "尚未配置";
    const maxRoutes = Number.isInteger(i.config.limits?.max_routes) ? i.config.limits.max_routes : null;
    const workflowCell = (route, index) => {
      if (route.backend !== "comfyui") return `<input data-imgr-edit="${index}:workflow_id" value="" disabled placeholder="仅 ComfyUI 使用" aria-label="工作流">`;
      if (comfyRows.length) return `<select data-imgr-edit="${index}:workflow_id" aria-label="工作流">
        <option value="">未指定</option>${comfyRows.map(row => `<option value="${esc(row.__name)}" ${route.workflow_id === row.__name ? "selected" : ""}>${esc(row.__name)}</option>`).join("")}</select>`;
      return `<input data-imgr-edit="${index}:workflow_id" value="${esc(route.workflow_id || "")}" placeholder="工作流名称" aria-label="工作流">`; };
    const comfyRow = (row, index) => `<li class="model-cfgr">
      <span class="model-tag ${row.__kind === "inline" ? "a" : "n"}">${row.__kind === "inline" ? "内联" : "文件"}</span>
      <input data-cfgr="${index}:name" value="${esc(row.__name || row.name || "")}" placeholder="名称（路线按此引用）" aria-label="工作流名称">
      ${row.__kind === "inline" ? '<span class="model-mono">内联 workflow JSON · 请在扩展配置维护</span>'
        : `<input data-cfgr="${index}:path" value="${esc(row.path || "")}" placeholder="API JSON 文件路径" aria-label="工作流文件路径">`}
      <button type="button" class="button small danger" data-cfgr-del="${index}" aria-label="删除工作流">删除</button></li>`;
    const routeRow = (route, index) => `<li class="model-imgr-item">
      <div class="model-imgr">
      <input data-imgr-edit="${index}:route_id" value="${esc(route.route_id || "")}" placeholder="route-id" aria-label="路线 ID">
      <select data-imgr-edit="${index}:operation" aria-label="操作">
        <option value="generate" ${route.operation === "generate" ? "selected" : ""}>文生图</option>
        <option value="edit" ${route.operation === "edit" ? "selected" : ""}>改图</option></select>
      <select data-imgr-edit="${index}:backend" aria-label="后端">
        <option value="comfyui" ${(route.backend || "comfyui") === "comfyui" ? "selected" : ""}>ComfyUI</option>
        <option value="sd_webui" ${route.backend === "sd_webui" ? "selected" : ""}>SD WebUI</option></select>
      ${workflowCell(route, index)}
      <input data-imgr-edit="${index}:profile" value="${esc(route.profile || "")}" placeholder="profile" aria-label="提示词分层">
      <button type="button" class="button small danger" data-imgr-del="${index}" aria-label="删除路线">删除</button></div>
      ${routeExtras(i, route, index)}</li>`;
    const connectionFields = (name, section, label, placeholder) => `<div class="model-img-connection">
      <header><b>${label}</b><span>${esc(section.timeout_seconds === undefined ? "使用扩展默认超时" : `超时 ${section.timeout_seconds} 秒`)}</span></header>
      <label class="model-fd"><span class="model-cap">服务地址</span><input data-imgr-sec="${name}:base_url" value="${esc(section.base_url || "")}" placeholder="${placeholder}" autocomplete="url"></label>
      <label class="model-fd"><span class="model-cap">API 密钥 <em>${keyFlag(!!(srcSections[name] && srcSections[name].api_key_set))}</em></span><input type="password" data-imgr-sec="${name}:api_key" value="" autocomplete="new-password">${srcSections[name] && srcSections[name].api_key_set ? `<span class="model-key-clear"><input type="checkbox" data-imgr-clear="${name}"> 清除已保存的密钥</span>` : ""}</label>
      <label class="model-fd"><span class="model-cap">请求超时（秒）</span><input type="number"${numAttrs(i, "connection", "timeout_seconds")} data-imgr-sec="${name}:timeout_seconds" value="${esc(section.timeout_seconds === undefined ? "" : section.timeout_seconds)}"></label>
    </div>`;
    const tabs = [["routes", "执行路线", `${routes.length} 条`], ["limits", "资源限额", "用量与保留"],
      ["comfyui", "ComfyUI", `${comfyRows.length} 个工作流`], ["sd_webui", "SD WebUI", "连接"]];
    if (!tabs.some(([id]) => id === i.configTab)) i.configTab = "routes";
    const dirty = imageConfigDirty(i);
    let content = "";
    if (i.configTab === "routes") content = `<div class="model-img-view" role="tabpanel" id="model-imgcfg-panel">
      <header class="model-img-sectionhead"><div><b>执行路线</b><span>为文生图和改图指定后端与工作流</span></div><button type="button" class="button small" data-imgr-add ${maxRoutes !== null && routes.length >= maxRoutes ? "disabled" : ""}>+ 新增路线</button></header>
      <div class="model-duo">
        <label class="model-fd"><span class="model-cap">默认文生图路线</span>
          <select data-imgr-def="default_generate_route"><option value="">未指定</option>${routes.filter(route => route.operation === "generate").map(route => `<option value="${esc(route.route_id)}" ${prep.default_generate_route === route.route_id ? "selected" : ""}>${esc(route.route_id)}</option>`).join("")}</select></label>
        <label class="model-fd"><span class="model-cap">默认改图路线</span>
          <select data-imgr-def="default_edit_route"><option value="">未指定</option>${routes.filter(route => route.operation === "edit").map(route => `<option value="${esc(route.route_id)}" ${prep.default_edit_route === route.route_id ? "selected" : ""}>${esc(route.route_id)}</option>`).join("")}</select></label></div>
      <div class="model-fd"><span class="model-cap">路线队列 <em>route_id 必须唯一；profile 对应提示词分层</em></span>
        <ul class="model-imgrs">${routes.map(routeRow).join("") || '<li class="model-empty">还没有路线。新增一条路线后，才能为动作指定默认执行方式。</li>'}</ul></div>
    </div>`;
    if (i.configTab === "limits") content = `<div class="model-img-view" role="tabpanel" id="model-imgcfg-panel">
      <header class="model-img-sectionhead"><div><b>资源限额</b><span>控制生成频率、历史保留与并发</span></div></header>
      <div class="model-img-limits">
        <label class="model-fd"><span class="model-cap">每日生成上限</span><input type="number"${numAttrs(i, "preparation", "daily_limit")} data-imgr-num="daily_limit" value="${esc(prep.daily_limit === undefined ? "" : prep.daily_limit)}"></label>
        <label class="model-fd"><span class="model-cap">最大并发</span><input type="number"${numAttrs(i, "preparation", "max_concurrency")} data-imgr-num="max_concurrency" value="${esc(prep.max_concurrency === undefined ? "" : prep.max_concurrency)}"></label>
        <label class="model-fd"><span class="model-cap">记录保留天数</span><input type="number"${numAttrs(i, "preparation", "retention_days")} data-imgr-num="retention_days" value="${esc(prep.retention_days === undefined ? "" : prep.retention_days)}"></label>
        <label class="model-fd"><span class="model-cap">存储上限（MB）</span><input type="number"${numAttrs(i, "preparation", "max_storage_mb")} data-imgr-num="max_storage_mb" value="${esc(prep.max_storage_mb === undefined ? "" : prep.max_storage_mb)}"></label>
      </div>
    </div>`;
    if (i.configTab === "comfyui") content = `<div class="model-img-view" role="tabpanel" id="model-imgcfg-panel">
      <header class="model-img-sectionhead"><div><b>ComfyUI 连接</b><span>工作流名称要与路线中的 workflow_id 对应</span></div><span class="model-tag">${comfyRows.length} 个工作流</span></header>
      <div class="model-fd"><span class="model-cap">工作流清单 <em>文件路径按 ComfyUI API JSON 读取；内联 JSON 请在扩展配置维护</em></span>
        <ul class="model-cfgrs">${comfyRows.map(comfyRow).join("") || '<li class="model-empty">尚未登记工作流。添加文件工作流后，可在执行路线中按名称引用。</li>'}</ul>
        <div class="model-editor-actions"><button type="button" class="button small" data-cfgr-add>+ 新增文件工作流</button></div></div>
      ${connectionFields("comfyui", comfy, "连接参数", "http://127.0.0.1:8188")}
    </div>`;
    if (i.configTab === "sd_webui") content = `<div class="model-img-view" role="tabpanel" id="model-imgcfg-panel">
      <header class="model-img-sectionhead"><div><b>SD WebUI 连接</b><span>连接信息由生图扩展安全保存</span></div></header>
      ${connectionFields("sd_webui", sd, "连接参数", "http://127.0.0.1:7860")}
    </div>`;
    return `<section class="model-imgconfig" aria-label="生图路线与连接配置">
      <header class="model-imgconfig-head"><div><span class="model-eb">IMAGE PIPELINE</span><h3>路线与连接</h3><p>当前配置由生图扩展校验；切换面板不会丢失未保存内容。</p></div>
        <span class="model-tag ${dirty ? "a" : "g"}">${dirty ? "有未保存更改" : "配置已同步"}</span></header>
      <div class="model-img-workbench"><nav class="model-img-nav" role="tablist" aria-label="生图配置分区">
        ${tabs.map(([id, label, meta], index) => `<button type="button" role="tab" data-imgcfg-tab="${id}" aria-selected="${i.configTab === id}" class="${i.configTab === id ? "on" : ""}"><span class="model-img-nav-no">0${index + 1}</span><span><b>${label}</b><small>${esc(meta)}</small></span><i aria-hidden="true">›</i></button>`).join("")}
      </nav><div class="model-img-main">${content}</div></div>
      <footer class="model-img-savebar"><span>${dirty ? "更改尚未写入扩展" : "所有面板共用同一份草稿"}</span>
        <div><button type="button" class="button small" data-imgcfg-reload ${i.configSaving ? "disabled" : ""}>${dirty ? "放弃更改并重读" : "重新读取"}</button>
          <button type="button" class="button primary" data-imgcfg-save ${i.configSaving || !dirty ? "disabled" : ""}>${i.configSaving ? "保存中…" : "保存路线与连接"}</button></div></footer>
      <p class="model-note">密钥留空则保留；勾选清除则删除已保存的密钥。保存后由扩展校验生效。</p>
    </section>`; }
  /* 越界提示里的字段名。键与扩展的 limits.preparation 一一对应，
     漏掉一个只是退回显示英文键，不会漏检。 */
  const IMAGE_LIMITS_LABEL = {daily_limit: "每日生成上限", retention_days: "记录保留天数",
    max_storage_mb: "存储上限", max_concurrency: "最大并发"};

  /* 边界表是对照扩展下发的 limits 逐格检查草稿。
     返回一句人话（越界的那一格和允许范围），全部在范围内则返回空串。
     刻意只查**扩展声明过边界的字段**：没有边界的就是没有边界，
     页面不能凭感觉加一条比扩展更严的规则，那会让本来能存的值存不下去。 */
  function checkImageBounds(i) {
    const limits = imageLimits(i); if (!limits) return "";
    const draft = i.configDraft || {};
    const prep = draft.preparation || {};
    for (const [key, span] of Object.entries(limits.preparation || {})) {
      const value = prep[key]; if (value === undefined || value === null || value === "") continue;
      /* input[type=number] 的值可能是字符串（用户正在输入时），先转成数再比。
         非数字在这里不拦——扩展那边会给出更准确的 invalid_configuration。 */
      const number = Number(value);
      if (!Number.isFinite(number) || !Number.isInteger(number)) continue;
      if (number < span.min || number > span.max)
        return `${IMAGE_LIMITS_LABEL[key] || key} 需要在 ${span.min}–${span.max} 之间，当前是 ${number}。`;
    }
    const conn = limits.connection && limits.connection.timeout_seconds;
    if (conn) for (const name of ["comfyui", "sd_webui"]) {
      const value = (draft[name] || {}).timeout_seconds;
      if (value === undefined || value === null || value === "") continue;
      const number = Number(value);
      if (!Number.isFinite(number) || !Number.isInteger(number)) continue;
      if (number < conn.min || number > conn.max)
        return `${name === "comfyui" ? "ComfyUI" : "SD WebUI"} 超时需要在 ${conn.min}–${conn.max} 秒之间，当前是 ${number}。`;
    }
    /* 路线的预置字段：参数的数值/文本边界、说明的条数与字数、改图方式是否适用于当前操作与后端。
       这三样都属于"提交后才知道被拒"，所以在页面一次说清是哪一条路线的哪一格。 */
    const guide = limits.guidance || null;
    for (const [index, route] of (Array.isArray(prep.routes) ? prep.routes : []).entries()) {
      if (!route || typeof route !== "object") continue;
      const where = `路线 ${route.route_id || index + 1}`;
      for (const spec of paramSpecs(i, route.backend || "comfyui")) {
        const value = (route.parameters || {})[spec.key];
        if (value === undefined || value === null || value === "") continue;
        const label = PARAM_LABELS[spec.key] || spec.key;
        if (spec.kind === "text") {
          if (typeof value === "string" && value.length > spec.maxLength)
            return `${where} 的${label}最多 ${spec.maxLength} 个字符，当前 ${value.length} 个。`;
          continue; }
        const number = Number(value);
        if (!Number.isFinite(number)) continue;
        if (number < spec.min || number > spec.max)
          return `${where} 的${label}需要在 ${spec.min}–${spec.max} 之间，当前是 ${number}。`;
      }
      const guidance = route.guidance || {};
      if (guide) {
        for (const key of GUIDE_LIST_KEYS) {
          const items = guidance[key];
          if (!Array.isArray(items)) continue;
          if (guide.max_items && items.length > guide.max_items)
            return `${where} 的「${GUIDE_LABELS[key]}」最多 ${guide.max_items} 条，当前 ${items.length} 条。`;
          if (guide.max_chars && items.some(item => String(item).length > guide.max_chars))
            return `${where} 的「${GUIDE_LABELS[key]}」单条最多 ${guide.max_chars} 字。`;
        }
        for (const key of GUIDE_TEXT_KEYS) {
          const text = guidance[key];
          if (typeof text === "string" && guide.max_chars && text.length > guide.max_chars)
            return `${where} 的「${GUIDE_LABELS[key]}」最多 ${guide.max_chars} 字，当前 ${text.length} 字。`;
        }
      }
      const method = typeof guidance.edit_method === "string" ? guidance.edit_method : "";
      const allowed = guidanceMethods(route);
      if (method && !allowed.includes(method))
        return `${where} 的改图方式「${EDIT_METHODS[method] || method}」不适用于当前操作或后端，请改为 ${allowed.map(item => EDIT_METHODS[item]).join(" / ")}。`;
    }
    return ""; }

  async function imageConfigSave(s) { const i = s.image;
    if (!i.config || !i.configDraft || i.configSaving) return;
    /* 提交前按扩展下发的边界挡一次。
       这不是重复校验——扩展那边必须留着同样的判断（页面是提示层，不是安全边界）。
       在页面挡的价值是：用户当场看到是哪一格越界，而不是提交后收到一句
       「生图扩展拒绝了这些值」，然后自己去猜是四格里的哪一格。
       只在扩展给了边界时生效；旧版扩展不下发 limits 时静默跳过。 */
    const outOfRange = checkImageBounds(i);
    if (outOfRange) { i.bad = true; i.notice = outOfRange; render(); return; }
    const changes = imageConfigChanges(i);
    if (!Object.keys(changes).length) { i.notice = "路线与连接没有改动。"; render(); return; }
    /* 路线说明是可长文本，保存提交的是整份路线数组；超过宿主的请求体上限时
       先在页面说清是哪条路线占地方，别让用户去读宿主那句 "model request is too large"。 */
    const size = JSON.stringify(changes).length;
    if (size > IMAGE_SAVE_LIMIT) { i.bad = true; i.notice = oversizedNotice(changes, size); render(); return; }
    const ticket = version; i.configSaving = true; i.notice = "正在保存生图路线与连接…"; render();
    try { const result = await api("POST", path + "/image/config/save", {revision: i.config.revision, changes}, 45000);
      if (!current(ticket, s)) return;
      i.bad = false; i.notice = "生图路线与连接已保存，由生图扩展校验生效。"; i.config = null; i.configDraft = null;
      imageConfigLoad(s); return; }
    catch (err) { if (!current(ticket, s)) return; i.bad = true; i.notice = fail(err, "生图路线保存未完成。"); }
    finally { i.configSaving = false; if (current(ticket, s)) render(); } }

  function imagePane(s) { const i = s.image; if (!i.data) return '<p class="model-empty">正在读取生图模型配置…</p>';
    const actions = i.data.actions, loaded = actions.filter(item => item.loaded).length;
    const ready = actions.filter(item => item.state === "ready").length;
    return `<div class="model-image">
      <div class="model-card model-img-status"><div class="model-phead"><div class="model-grow"><span class="model-eb">IMAGE STATUS</span><h3>生图能力与连接</h3></div>
          <button type="button" class="button small" data-go="manage" data-manage="output">生图相关功能 ↗</button>
          <button type="button" class="button small" data-img-refresh ${i.loading || i.busy ? "disabled" : ""}>刷新状态</button></div>
        <div class="model-kpis">${kpi(actions.length, "Native 动作")}${kpi(loaded + "/" + actions.length, "已加载")}${kpi(ready + "/" + actions.length, "当前可调用", ready ? "g" : "a")}${kpi(i.data.authorization === "checked_for_each_invocation" ? "逐次校验" : "未确认", "调用授权")}</div></div>
      <div class="model-card"><div class="model-phead"><div class="model-grow"><span class="model-eb">执行类型 · 按动作分别控制</span><h3>Native 生图动作</h3></div>
          <button type="button" class="button small" data-img-config ${i.loading || i.busy ? "disabled" : ""}>${i.configOpen ? "收起路线与连接" : "路线队列与连接"}</button></div>
        <ul class="model-pvl">${actions.map((item, index) => {
          const enabled = !!i.draft[item.action], changed = enabled !== i.data.enabled[item.action];
          const stateLabel = !enabled ? "已关闭" : item.state === "ready" ? "已注册" : item.loaded ? "注册未就绪" : "扩展未加载";
          const diag = [["已加载", item.loaded], ["声明一致", item.current], ["已注册", item.registered]]
            .map(([label, ok]) => `<span class="model-diag ${ok ? "ok" : "no"}"><i>${ok ? "✓" : "—"}</i>${label}</span>`).join("");
          const route = !enabled ? "已关闭 · V2 不会调用此动作"
            : item.state === "ready" ? "可调用 · V2 每次调用前逐次校验授权"
            : item.loaded ? "声明与注册不一致 · 暂不可调用" : "扩展未加载 · 暂不可调用";
          return `<li class="model-pv${enabled && item.state === "ready" ? " main" : ""}${enabled ? "" : " off"}">
            <span class="ix">${index + 1}</span>
            <span class="nm"><strong>${esc(IMAGE_LABELS[item.action] || item.action)}</strong>
              <small>${esc(item.action)} · ${esc(item.owner || "尚无扩展提供")}${item.provider_id ? " · " + esc(item.provider_id) : ""}</small>
              <span class="caps"><span class="model-tag ${enabled && item.state === "ready" ? "g" : enabled ? "a" : "n"}">${esc(stateLabel)}${changed ? " · 待保存" : ""}</span>${diag}</span>
              <small class="rt">${esc(route)}</small></span>
            <span class="mt"><label class="model-switch"><input type="checkbox" data-img-toggle="${esc(item.action)}" ${enabled ? "checked" : ""} ${i.loading || i.busy ? "disabled" : ""} aria-label="启用${esc(IMAGE_LABELS[item.action] || item.action)}"><i></i></label>
              <button type="button" class="button small" data-img-test="${esc(item.action)}" ${i.testing ? "disabled" : ""}>${i.testing === item.action ? "检查中…" : "检查注册"}</button></span></li>`; }).join("")}</ul>
        <div class="model-editor-actions"><button type="button" class="button primary" data-img-save ${i.busy || i.loading || !imageDirty(i) ? "disabled" : ""}>保存生图开关</button></div>
        <p class="model-note">注册检查不提交生图任务。</p>
      </div>
      ${i.configOpen ? imageConfigEditor(s) : ""}
      ${i.bad ? `<div class="model-notice error" role="status">${esc(i.notice)}</div>` : i.notice ? `<div class="model-notice" role="status">${esc(i.notice)}</div>` : ""}
    </div>`; }
  function imageInput(s, event) { const i = s.image; if (i.loading || i.busy) return; const t = event.target;
    if (t.matches("[data-img-toggle]") && IMAGE_LABELS[t.dataset.imgToggle]) { i.draft[t.dataset.imgToggle] = t.checked; render(); return; }
    if (!i.configDraft) return;
    const clear = t.dataset.imgrClear;
    if (clear) {
      // Stored as a draft flag, never as the key value: the diff only turns it
      // into an explicit empty string at save time.
      const section = i.configDraft[clear] || (i.configDraft[clear] = {});
      section.__clear_key = t.checked === true;
      if (event.type === "change") render();
      return; }
    const edit = t.dataset.imgrEdit;
    if (edit) { const [index, key] = String(edit).split(":"); const route = ((i.configDraft.preparation || {}).routes || [])[Number(index)];
      if (!route) return;
      route[key] = key === "operation" || key === "backend" ? t.value : t.value;
      if (event.type === "change") render(); return; }
    /* 路线的参数：空值表示「未声明」，直接把键删掉，让扩展用它自己的默认值——
       写一个空字符串过去会被它的参数类型校验拒掉。 */
    const param = t.dataset.imgrParam;
    if (param) { const [index, key] = String(param).split(":"); const route = ((i.configDraft.preparation || {}).routes || [])[Number(index)];
      if (!route) return;
      const params = route.parameters || (route.parameters = {});
      const raw = String(t.value === undefined || t.value === null ? "" : t.value).trim();
      /* 该键是数字还是文本按扩展下发的参数表判，不看 input 的 type——
         表里说它是文本就当文本存，表里没有时按字面量能不能当数字读。 */
      const spec = paramSpecs(i, route.backend || "comfyui").find(item => item.key === key);
      if (!raw) delete params[key];
      else if (spec ? spec.kind === "text" : !/^-?\d+(\.\d+)?$/.test(raw)) params[key] = raw;
      else { const parsed = Number.isFinite(t.valueAsNumber) ? t.valueAsNumber : Number(raw);
        if (!Number.isFinite(parsed)) return;
        params[key] = parsed; }
      if (!Object.keys(params).length) delete route.parameters;
      if (event.type === "change") render(); return; }
    /* 路线说明：两个列表字段按行拆成数组，其余按文本存；空值同样删键。 */
    const guide = t.dataset.imgrGuide;
    if (guide) { const [index, key] = String(guide).split(":"); const route = ((i.configDraft.preparation || {}).routes || [])[Number(index)];
      if (!route) return;
      const guidance = route.guidance || (route.guidance = {});
      const raw = String(t.value === undefined || t.value === null ? "" : t.value);
      if (GUIDE_LIST_KEYS.includes(key)) {
        const items = raw.split("\n").map(item => item.trim()).filter(Boolean);
        if (items.length) guidance[key] = items; else delete guidance[key];
      } else if (raw.trim()) guidance[key] = raw;
      else delete guidance[key];
      if (!Object.keys(guidance).length) delete route.guidance;
      if (event.type === "change") render(); return; }
    if (t.matches("[data-imgr-num]")) { const key = t.dataset.imgrNum; const prep = i.configDraft.preparation || (i.configDraft.preparation = {});
      const parsed = Number.isFinite(t.valueAsNumber) ? t.valueAsNumber : null;
      if (event.type === "change") { if (parsed !== null) prep[key] = parsed; render(); } return; }
    const sec = t.dataset.imgrSec;
    if (sec) { const [name, key] = String(sec).split(":"); const section = i.configDraft[name] || (i.configDraft[name] = {});
      if (key === "timeout_seconds") { const parsed = Number.isFinite(t.valueAsNumber) ? t.valueAsNumber : null;
        if (event.type === "change") { if (parsed !== null) section[key] = parsed; render(); } return; }
      section[key] = t.value; return; }
    const def = t.dataset.imgrDef;
    if (def) { const prep = i.configDraft.preparation || (i.configDraft.preparation = {}); prep[def] = t.value; if (event.type === "change") render(); return; }
    if (t.matches("[data-imgr-chat]")) { const prep = i.configDraft.preparation || (i.configDraft.preparation = {});
      prep.chat_enabled = t.checked; if (event.type === "change") render(); return; }
    const cfgr = t.dataset.cfgr;
    if (cfgr && i.configDraft.comfyui) { const rows = comfyRowsFrom(i.configDraft.comfyui);
      const [index, key] = String(cfgr).split(":"); const row = rows[Number(index)];
      if (row) { row[key] = t.value; row.__name = key === "name" ? t.value : (row.__name || t.value);
        if (event.type === "change") render(); } return; } }
  function imageClick(s, event) { const i = s.image; const t = event.target;
    if (t.closest("[data-img-refresh]")) { imageRefresh(s); return; }
    if (t.closest("[data-img-save]")) { imageSave(s); return; }
    if (t.closest("[data-img-config]")) { i.configOpen = !i.configOpen; if (i.configOpen && !i.config) imageConfigLoad(s); render(); return; }
    const configTab = t.closest("[data-imgcfg-tab]");
    if (configTab) { i.configTab = configTab.dataset.imgcfgTab; render(); return; }
    if (t.closest("[data-imgcfg-reload]")) { i.config = null; i.configDraft = null; imageConfigLoad(s); return; }
    if (t.closest("[data-imgcfg-save]")) { imageConfigSave(s); return; }
    const addRoute = t.closest("[data-imgr-add]");
    if (addRoute) { const prep = i.configDraft && (i.configDraft.preparation || (i.configDraft.preparation = {}));
      const routes = prep.routes || (prep.routes = []);
      const maxRoutes = i.config?.limits?.max_routes;
      if (Number.isInteger(maxRoutes) && routes.length >= maxRoutes) { i.bad = true; i.notice = `当前版本最多支持 ${maxRoutes} 条执行路线。`; render(); return; }
      const seed = routes[0] || {};
      let id = "route-" + (routes.length + 1), guard = 0;
      while (routes.some(route => route.route_id === id) && guard < 64) { guard += 1; id = "route-" + (routes.length + 1) + "-" + guard; }
      routes.push({route_id: id, profile: seed.profile || "default", operation: "generate", backend: "comfyui", workflow_id: ""});
      i.configTab = "routes";
      render(); return; }
    const cfgrAdd = t.closest("[data-cfgr-add]");
    if (cfgrAdd) { const comfy = i.configDraft && (i.configDraft.comfyui || (i.configDraft.comfyui = {}));
      const rows = comfyRowsFrom(comfy); rows.push({ __kind: "path", __name: "workflow-" + (rows.length + 1), path: "" });
      render(); return; }
    const cfgrDel = t.closest("[data-cfgr-del]");
    if (cfgrDel) { const comfy = i.configDraft && i.configDraft.comfyui; const rows = comfy && comfyRowsFrom(comfy);
      const index = Number(cfgrDel.dataset.cfgrDel);
      if (rows[index]) rows.splice(index, 1);
      render(); return; }
    const delRoute = t.closest("[data-imgr-del]");
    if (delRoute) { const prep = i.configDraft && i.configDraft.preparation; const routes = prep && prep.routes || [];
      const index = Number(delRoute.dataset.imgrDel);
      if (routes[index]) routes.splice(index, 1);
      render(); return; }
    /* 预置字段那一块默认收起（一条路线最多三十几张，全展开会淹掉路线队列）。
       <details> 的展开状态在重绘后会丢，所以记在路线对象上；重绘由 render() 重建 DOM，
       这里按点击后的状态提前写入——点击 summary 的默认动作在事件之后才发生。 */
    const ext = t.closest("details[data-imgr-ext]");
    if (ext) { const routes = ((i.configDraft || {}).preparation || {}).routes || [];
      const route = routes[Number(ext.dataset.imgrExt)];
      if (route) { if (ext.open) expandedRoutes.delete(route); else expandedRoutes.add(route); }
      return; }
    const testBtn = t.closest("[data-img-test]"); if (testBtn) imageTest(s, testBtn.dataset.imgTest); }
  /* ---------- top-level render & routing ---------- */
  function tabBar(s) { const tabs = [["fn", "功能模型", ICONS.fn, snapshot(s).length],
      ["voice", "语音模型", ICONS.voice, s.voice.data ? s.voice.data.providers.length : ""],
      ["image", "生图模型", ICONS.image, s.image.data ? s.image.data.actions.length : ""]];
    return `<div class="model-tabs" role="tablist" aria-label="模型配置分类">${tabs.map(([id, label, ic, count]) =>
      `<button type="button" role="tab" data-model-tab="${id}" aria-selected="${s.tab === id}" class="${s.tab === id ? "on" : ""}">${icon(ic)}${label}${count !== "" ? `<span class="c">${count}</span>` : ""}</button>`).join("")}</div>`; }
  /* ---------- functional subtabs (design migration) ---------- */
  function subtabBar(s) { const tabs = [["map", "态势图"], ["cfg", "模型配置"], ["pol", "替换策略"]];
    return `<div class="model-subtabs" role="tablist" aria-label="功能模型视图">${tabs.map(([id, label]) => `<button type="button" role="tab" data-model-sub="${id}" aria-selected="${s.sub === id}" class="${s.sub === id ? "on" : ""}">${label}</button>`).join("")}</div>`; }
  function kpi(n, label, tone = "") { return `<div class="model-kpi ${tone}"><b>${n}</b><span>${esc(label)}</span></div>`; }
  function fnKpis(s) { const tasks = snapshot(s); const total = tasks.length; const providers = s.status?.providers.length || 0;
    const withFb = tasks.filter(t => t.fields.fallback?.value).length; const own = tasks.filter(t => fields.some(nm => t.fields[nm]?.explicit)).length;
    return kpi(total, "需要模型的功能") + kpi(providers, "可用模型") + kpi(withFb, "已设回退", "g")
      + kpi(total - withFb, "暂无回退", "a") + kpi(own, "单独设置"); }
  function sitFilters(s) { const avSeg = [["slot", "按能力槽"], ["lane", "按前台 / 后台"]]; const afSeg = [["all", "全部"], ["nofb", "仅无备用"], ["own", "仅单独设置"]];
    const seg = (cls, attr, arr, cur) => `<div class="${cls}" role="group">${arr.map(([id, label]) => `<button type="button" data-model-${attr}="${id}" aria-pressed="${cur === id}" class="${cur === id ? "active" : ""}">${label}</button>`).join("")}</div>`;
    return `<div class="model-map-filters"><label class="model-search"><span class="sr-only">搜索任务</span><input type="search" data-model-search value="${esc(s.query)}" placeholder="按名称或用途搜索"></label>${seg("model-filters", "av", avSeg, s.av)}${seg("model-filters", "af", afSeg, s.af)}</div>`; }
  const providerPill = (id, missing) => id
    ? `<button type="button" class="model-pill m" data-provider-pill="${esc(id)}" style="--mc:${pillColor(id)}" title="查看 ${esc(id)} 的路由分工">${esc(id)}</button>`
    : `<span class="model-pill m none">${missing || "无回退"}</span>`;
  function situationMap(s) { const tasks = snapshot(s); const q = s.query.toLocaleLowerCase();
    const match = t => { if (s.af === "nofb" && t.fields.fallback?.value) return false; if (s.af === "own" && !fields.some(nm => t.fields[nm]?.explicit)) return false;
      if (!q) return true; const info = taskName(t.kind); return (info.label + info.group + info.description + t.kind).toLocaleLowerCase().includes(q); };
    let groups2;
    if (s.av === "lane") groups2 = [["前台 · 用户可见", tasks.filter(t => t.lane === "foreground")], ["后台 · 静默运行", tasks.filter(t => t.lane === "background")]];
    else groups2 = groups.map(([g, items]) => [g, items.map(([kind]) => tasks.find(t => t.kind === kind)).filter(Boolean)]);
    const list = groups2.filter(([, ts]) => ts.length).map(([g, ts]) => {
      const shownTasks = ts.filter(match);
      const items = shownTasks.map(t => { const info = taskName(t.kind); const main = t.fields.provider?.value || ""; const fb = t.fields.fallback?.value;
        const rules = parseRules(t.fields.replacement_rules.value).length, refusal = t.fields.fallback_on_refusal.value === true;
        const picked = s.rule.picked.includes(t.kind);
        return `<li class="model-item${picked ? " seled" : ""}"><label class="model-item-sel"><input type="checkbox" data-map-pick="${esc(t.kind)}" ${picked ? "checked" : ""} aria-label="选择 ${esc(info.label)} 参与批量测试"></label>
          <span class="model-item-nm"><button type="button" class="model-map-open" data-model-open="${esc(t.kind)}" aria-label="编辑 ${esc(info.label)}"><b>${esc(info.label)}</b></button></span>
          <span class="model-item-ch">
            <span class="model-ln"><i>默认模型</i><span class="model-ps">${providerPill(main, "未设置")}</span></span>
            <span class="model-ln"><i>备用模型</i><span class="model-ps">${providerPill(fb)}${rules ? `<span class="model-tag">${rules} 规则</span>` : ""}${refusal ? '<span class="model-tag a">拒答替代</span>' : ""}</span></span>
          </span></li>`; }).join("");
      const sel = ts.filter(t => s.rule.picked.includes(t.kind)).length;
      const all = shownTasks.length && shownTasks.every(t => s.rule.picked.includes(t.kind));
      const gkey = s.av === "lane" ? "lane:" + (g.startsWith("前台") ? "foreground" : "background") : g;
      return `<section class="model-grp"><header><input type="checkbox" class="model-gck" data-model-gpick="${esc(gkey)}" ${all ? "checked" : ""} aria-label="全选 ${esc(g)}">${icon(groupIcon(g))}<b>${esc(g)}</b><span class="cnt">${ts.length} 项${sel ? " · 已选 " + sel : ""}</span></header>
        ${items || '<p class="model-empty">没有匹配的任务。</p>'}</section>`; }).join("");
    const legend = (s.status?.providers || []).map(p => `<span><i style="background:${pillColor(p.id)}"></i><em>${esc(p.id)}</em></span>`).join("");
    return `<div class="model-subpane"><div class="model-kpis">${fnKpis(s)}</div>${sitFilters(s)}
      <div class="model-mlgd legend">${legend}</div>
      <div class="model-rgrid">${list}</div>${testBar(s)}</div>`; }
  const probeLabel = result => result.status === "ok" ? `连接成功 · ${result.latency_ms} ms`
    : result.status === "testing" ? "测试中…" : errors[result.code] || "结果未知";
  async function probeProvider(s, provider) {
    if (!provider || s.testing.has(provider) || !s.status?.providers.some(item => item.id === provider)) return;
    const ticket = version, endpoint = path + "/test";
    s.testing.add(provider); s.providerTests[provider] = {status: "testing"}; render();
    try { const result = await api("POST", endpoint, {provider_id: provider}, 35000);
      if (!current(ticket, s)) return;
      if (result.provider_id !== provider || !["ok", "unknown", "unavailable"].includes(result.status)) throw failure("invalid_response");
      s.providerTests[provider] = result;
    } catch (err) { if (!current(ticket, s)) return; s.providerTests[provider] = {status: "unknown", code: err.code || err.message}; }
    finally { s.testing.delete(provider); if (current(ticket, s)) render(); }
  }
  function testBar(s) { const picked = s.rule.picked.filter(kind => taskOf(s, kind)); if (!picked.length) return "";
    const providers = new Set();
    picked.forEach(kind => { const task = taskOf(s, kind), draft = s.drafts.get(kind);
      const primary = providerFor(task, draft); if (primary) providers.add(primary);
      const fallback = effective(task, draft, "fallback"); if (fallback) providers.add(fallback); });
    const rows = (s.rule.report || []).map(line => { const st = line.provider ? s.providerTests[line.provider] : null;
      const running = s.rule.testing && (!st || st.status === "testing");
      const cls = running ? "run" : st && st.status === "ok" ? "ok" : running ? "run" : "bad";
      const tail = !line.provider ? "无 Provider"
        : running ? '<span class="model-sp"></span>测试中'
        : st ? esc(probeLabel(st)) : "结果未知";
      return `<div class="model-trow ${cls}"><span class="dotm" style="background:${pillColor(line.provider)}"></span><span class="mno">${esc(line.provider || "—")}</span>
        <span class="u">${esc(line.role)} · ${esc(line.label)}</span><span class="tr">${tail}</span></div>`; }).join("");
    const total = (s.rule.report || []).length;
    const done = (s.rule.report || []).filter(line => { const st = line.provider && s.providerTests[line.provider]; return st && st.status !== "testing"; }).length;
    const okCount = (s.rule.report || []).filter(line => s.providerTests[line.provider]?.status === "ok").length;
    return `<div class="model-dock"><div class="model-selbar"><span>已选 <b>${picked.length}</b> 项任务 · 涉及 <b>${providers.size}</b> 个 Provider</span>
      <span class="model-bar${total && done === total && okCount === total ? " full" : ""}"><i style="width:${total ? Math.round(done / total * 100) : 0}%"></i></span>
      <span class="model-grow"></span>
      <button type="button" class="button small" data-map-clear ${s.rule.testing ? "disabled" : ""}>清空</button>
      <button type="button" class="button small primary" data-map-test ${s.rule.testing ? "disabled" : ""}>${s.rule.testing ? "测试中…" : "批量测试"}</button></div>
      ${s.rule.report ? `<div class="model-tres"><div class="th"><b>测试</b><span class="s">${s.rule.testing ? `正在测试 ${picked.length} 项` : `${total} 项完成 · ${okCount} 通过${okCount < total ? " · " + (total - okCount) + " 失败" : ""}`}</span></div>
        <div class="tbody">${rows}</div></div>` : ""}</div>`; }
  async function runMapTest(s) { if (s.rule.testing) return; const ticket = version, picked = s.rule.picked.filter(kind => taskOf(s, kind));
    const report = [];
    picked.forEach(kind => { const task = taskOf(s, kind), draft = s.drafts.get(kind), info = taskName(kind);
      const primary = providerFor(task, draft), fallback = effective(task, draft, "fallback");
      report.push({ provider: primary, role: "主 Provider", label: info.label });
      if (fallback) report.push({ provider: fallback, role: "备用 Provider", label: info.label }); });
    s.rule.report = report; s.rule.testing = true; s.bad = false; render();
    for (const provider of new Set(report.map(line => line.provider).filter(Boolean))) {
      await probeProvider(s, provider); if (!current(ticket, s)) return;
    }
    s.rule.testing = false;
    s.bad = report.some(line => !line.provider || s.providerTests[line.provider]?.status !== "ok");
    s.notice = s.bad ? "部分 Provider 未通过测试，请核对结果。" : "所选任务涉及的 Provider 均已通过测试。"; render(); }
  function quickConfig(s) { const providers = s.status?.providers || [];
    const opts = id => `<option value="">跟随分组默认</option>${providers.map(p => `<option value="${esc(p.id)}" ${s.slotDraft[id] === p.id ? "selected" : ""}>${esc(p.id)}</option>`).join("")}`;
    const cards = groups.map(([g, items]) => { const kinds = items.map(([kind]) => kind);
      const cur = kinds.map(k => { const t = taskOf(s, k), d = s.drafts.get(k); return t && d ? providerFor(t, d) : null; }).filter(Boolean);
      const same = cur.length && cur.every(v => v === cur[0]) ? cur[0] : "";
      const own = kinds.filter(k => { const d = s.drafts.get(k); return d && fields.some(name => !d.inherited[name]); }).length;
      const routed = kinds.map(k => { const t = taskOf(s, k); return t ? parseRules(t.fields.replacement_rules.value).length : 0; }).reduce((a, b) => a + b, 0);
      const refusal = kinds.filter(k => { const t = taskOf(s, k); return t && t.fields.fallback_on_refusal.value === true; }).length;
      const open = !!s.expOpen[g];
      return `<article class="model-sc">
        <div class="model-sc-tp">
          <div class="model-eb">快速配置<span class="st">${own ? `<span class="model-tag a">${own} 项单独设置</span>` : '<span class="model-tag n">默认统一</span>'}</span></div>
          <div class="model-ti">${icon(groupIcon(g))}<b>${esc(g)}</b></div>
          <div class="model-ds">${esc(items.map(([, label]) => label).join("、"))}</div>
          <div class="model-rl"><span>${items.length} 项任务</span><span>替换规则 ${routed} 条</span>${refusal ? `<span>拒答替代 ${refusal} 项</span>` : ""}</div>
        </div>
        <div class="model-sc-bd">
          <label class="model-fd"><span class="model-cap">统一指派 Provider <em>写入每项任务的主 Provider</em></span>
            <select data-model-slot="${esc(g)}" aria-label="${esc(g)} 统一指派">${opts(g)}</select></label>
          <div class="model-fd"><span class="model-cap">当前统一路由</span>
            <div class="model-cur${same ? "" : " miss"}">${esc(same || "混合 / 跟随上级")}</div></div>
        </div>
        <div class="model-sc-rf">
          <div class="r"><b>用途</b><span>${esc(items.map(([, label, desc]) => `${label}：${desc}`).join("；"))}</span></div>
          <div class="r"><b>覆盖</b><span>只写入各任务的主 Provider，保留各自的备用、提示词与替换规则；可随时在精准配置改回跟随上级。</span></div>
        </div>
        <div class="model-sc-ft"><code>${esc(g)}</code><span class="model-grow"></span>
          <button type="button" class="model-lk" data-model-exp="${esc(g)}">${open ? "收起" : "覆盖"} ${items.length} 项${own ? ` · ${own} 项单独设置` : ""} ▾</button>
          <button type="button" class="button small primary" data-model-slot-apply="${esc(g)}" ${s.busy || s.loading || s.denied || !s.slotDraft[g] ? "disabled" : ""}>应用到本组</button></div>
        ${open ? `<div class="model-exp"><ul>${kinds.map(k => { const t = taskOf(s, k), d = s.drafts.get(k);
          const isOwn = d && fields.some(name => !d.inherited[name]);
          return `<li>${esc(taskName(k)?.label || k)}<span>${t ? providerFor(t, d) || "未设置" : "未注册"}${isOwn ? " · 单独设置" : " · 跟随本组"}</span></li>`; }).join("")}</ul></div>` : ""}
      </article>`; }).join("");
    return `<div class="model-subpane"><div class="model-qgrid">${cards}</div></div>`; }
  async function applySlot(s, slotId) { const gp = groups.find(([g]) => g === slotId); if (!gp) return; const providerId = s.slotDraft[slotId]; if (!providerId) return;
    const kinds = [];
    for (const [kind] of gp[1]) { const task = taskOf(s, kind), draft = s.drafts.get(kind); if (!task || !draft || draft.pending || draft.stale) continue;
      if (!task.capabilities.every(cap => s.status.providers.find(p => p.id === providerId)?.capabilities.includes(cap))) continue;
      draft.inherited.provider = false; draft.values.provider = providerId; draft.touched = true; fitLimit(s, task, draft); kinds.push(kind); }
    if (!kinds.length) { s.bad = true; s.notice = "这些任务没有可改动的草稿或能力不符。"; render(); return; }
    s.notice = `正在把「${slotId}」组中 ${kinds.length} 项任务指派给 ${providerId}…`; render();
    await saveTasks(s, kinds); }
  /* ---------- replacement policy (keyword / time-window rules, refusal retry) ---------- */
  /* Rules live in one JSON string per task; the gateway's replacement_rules.build_rules
     reads the same keys, so the editor round-trips them verbatim. */
  const RULE_SEED = { id: "rule-1", provider_id: "", model: "", priority: 0, keywords: [], match_mode: "contains", keyword_logic: "any", case_sensitive: false, enabled: true };
  const MATCH_MODES = [["contains", "包含"], ["exact", "精确"], ["regex", "正则"]];
  const LOGICS = [["any", "任一"], ["all", "全部"]];
  const WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
  const DEFAULT_WINDOW = "09:00-12:00\n14:00-18:00";
  /* V1 exposed these as the refusal trigger surface. V2 detects a refusal from the
     provider's own finish_reason, so this list is reference text, not routing input. */
  const REFUSAL_HINTS = ["很抱歉，我无法", "我有我自己的底线", "我们可以聊聊别的", "我无法满足", "The prompt could not be submitted"];
  const ruleMode = rule => MATCH_MODES.some(([id]) => id === rule.match_mode) ? rule.match_mode : "contains";
  const ruleKeywordText = rule => Array.isArray(rule.keywords) ? rule.keywords.join("，") : "";
  function parseRules(text) { if (typeof text !== "string" || !text.trim()) return [];
    try { const parsed = JSON.parse(text); const list = Array.isArray(parsed) ? parsed : parsed && typeof parsed === "object" ? [parsed] : [];
      return list.filter(item => item && typeof item === "object" && !Array.isArray(item)); }
    catch { return []; } }
  const serializeRules = rules => JSON.stringify(rules, null, 2);
  const keywordChips = text => String(text || "").split(/[,，;；\n]+/).map(word => word.trim()).filter(Boolean);
  function parseWindows(text) { const cells = new Set();
    String(text || "").split(/[\n,;，；]+/).map(part => part.trim()).filter(Boolean).forEach(part => {
      const match = part.match(/^(\d{1,2}):(\d{2})\s*[-–~至]\s*(\d{1,2}):(\d{2})$/); if (!match) return;
      let start = Number(match[1]), end = Number(match[3]);
      if (!Number.isInteger(start) || !Number.isInteger(end) || start > 23 || end > 24) return;
      if (end <= start) end += 24;
      for (let hour = start; hour < end; hour++) cells.add(hour % 24); });
    return cells; }
  function formatWindows(cells) { if (!cells.size) return "";
    const hours = [...cells].sort((a, b) => a - b), spans = [];
    let start = hours[0], previous = hours[0];
    for (let index = 1; index <= hours.length; index++) { const current = hours[index];
      if (current === previous + 1) { previous = current; continue; }
      spans.push(String(start).padStart(2, "0") + ":00-" + String((previous + 1) % 24).padStart(2, "0") + ":00");
      start = previous = current; }
    if (spans.length === 1 && spans[0] === "00:00-00:00") return "00:00-12:00\n12:00-00:00";
    return spans.join("\n"); }
  const peakWindows = peak => parseWindows(peak.windows);
  const timeValid = value => /^\d{2}:\d{2}$/.test(value) && Number(value.slice(0, 2)) < 24 && Number(value.slice(3)) < 60;
  const peakSegments = text => String(text || "").split(/\n+/).map(span => span.trim()).filter(Boolean)
    .map(span => span.split("-")).filter(parts => parts.length === 2 && parts.every(timeValid) && parts[0] !== parts[1]);
  const ruleOf = (s, kind) => { const task = taskOf(s, kind); if (!task || !s.drafts.has(kind)) return [];
    const draft = s.drafts.get(kind);
    return parseRules(draft.inherited.replacement_rules ? task.fields.replacement_rules.inherited_value : draft.values.replacement_rules); };
  const dayLabel = days => Array.isArray(days) && days.length === 7 ? "每天"
    : Array.isArray(days) && days.length ? days.map(day => WEEKDAYS[day] || day).join(" ") : "每天";
  function timeText(rule) { const window = rule.time_window; if (!window || typeof window !== "object") return "";
    return `${window.start || ""}-${window.end || ""}`; }
  /* ---------- replacement policy: markup ---------- */
  /* The policy pane always has an active task: the explicit pick, else the first. */
  const policyTask = s => taskOf(s, s.pol) || snapshot(s)[0] || null;
  function ruleCard(s, task, rule, index) {
    const info = taskName(task.kind), draft = s.drafts.get(task.kind), locked = s.loading || s.busy || s.denied || draft?.pending;
    const providers = available(s, task), picked = typeof rule.provider_id === "string" ? rule.provider_id : "";
    const extra = providers.some(provider => provider.id === picked) ? "" : picked ? `<option value="${esc(picked)}" selected>${esc(picked)} · 未注册</option>` : "";
    const window = rule.time_window && typeof rule.time_window === "object" ? rule.time_window : null;
    const ref = `${esc(task.kind)}:${index}`;
    return `<li class="model-kw${rule.enabled === false ? " off" : ""}" data-rule-card="${ref}">
      <div class="model-kwh">
        <span class="model-ix">#${index + 1}</span>
        <input class="model-kn" value="${esc(rule.id || "")}" data-rule-id="${ref}" aria-label="规则名" ${locked ? "disabled" : ""}>
        <label class="model-switch sm"><input type="checkbox" data-rule-enabled="${ref}" ${rule.enabled === false ? "" : "checked"} ${locked ? "disabled" : ""}><i></i></label>
        <button type="button" class="button small danger" data-rule-del="${ref}" ${locked ? "disabled" : ""}>删除</button>
      </div>
      <div class="model-kwc">
        <span class="model-cap">关键词</span>
        <textarea class="model-kk" rows="1" data-rule-keywords="${ref}" placeholder="写代码，代码报错（逗号或换行分隔）" ${locked ? "disabled" : ""}>${esc(ruleKeywordText(rule))}</textarea>
        <span class="model-arw">→</span>
        <select data-rule-provider="${ref}" aria-label="规则目标 Provider" ${locked ? "disabled" : ""}><option value="">未选择 · 规则不生效</option>${providers.map(provider => `<option value="${esc(provider.id)}" ${provider.id === picked ? "selected" : ""}>${esc(provider.id)}</option>`).join("")}${extra}</select>
      </div>
      <div class="model-kwc">
        <span class="model-cap">匹配</span>
        <select data-rule-match="${ref}" aria-label="匹配方式" ${locked ? "disabled" : ""}>${MATCH_MODES.map(([id, label]) => `<option value="${id}" ${ruleMode(rule) === id ? "selected" : ""}>${label}</option>`).join("")}</select>
        <span class="model-cap">条件</span>
        <select data-rule-logic="${ref}" aria-label="条件" ${locked ? "disabled" : ""}>${LOGICS.map(([id, label]) => `<option value="${id}" ${(rule.keyword_logic === "all" ? "all" : "any") === id ? "selected" : ""}>${label}</option>`).join("")}</select>
        <span class="model-cap">优先级</span>
        <input class="model-num" type="number" step="1" data-rule-priority="${ref}" value="${esc(Number.isInteger(rule.priority) ? rule.priority : 0)}" ${locked ? "disabled" : ""}>
        <span class="model-cap">模型覆盖</span>
        <input class="model-mo" data-rule-model="${ref}" value="${esc(rule.model || "")}" placeholder="${esc(picked && providers.find(provider => provider.id === picked)?.supports_model_override ? "该 Provider 支持覆盖" : "留空沿用默认")}" ${locked ? "disabled" : ""}>
      </div>
      <div class="model-rule-time">
        <label class="model-cap"><input type="checkbox" data-rule-window="${ref}" ${window ? "checked" : ""} ${locked ? "disabled" : ""}> 限定生效时段</label>
        ${window ? `<div class="model-band" role="img" aria-label="${esc(timeText(window))}">${Array.from({ length: 24 }, (_, hour) =>
          `<span class="model-band-cell${parseWindows(timeText(window)).has(hour) ? " on" : ""}${hour % 3 === 0 ? " tick" : ""}" title="${hour}:00">${hour % 3 === 0 ? hour : ""}</span>`).join("")}</div>
        <div class="model-kwc">
          <span class="model-cap">开始</span><input class="model-num" data-rule-start="${ref}" value="${esc(window.start || "")}" maxlength="5" placeholder="09:00" ${locked ? "disabled" : ""}>
          <span class="model-cap">结束</span><input class="model-num" data-rule-end="${ref}" value="${esc(window.end || "")}" maxlength="5" placeholder="18:00" ${locked ? "disabled" : ""}>
          <span class="model-cap">时区</span><input class="model-mo" data-rule-zone="${ref}" value="${esc(window.timezone || "Asia/Shanghai")}" ${locked ? "disabled" : ""}>
        </div>
        <p class="model-note">生效日：${esc(dayLabel(window.weekdays))} · 未选关键词时整段生效</p>` : ``}
      </div>
      ${Array.isArray(rule.keywords) && rule.keywords.length ? `<div class="model-chips">${rule.keywords.map(word => `<span class="model-kchip">${esc(word)}</span>`).join("")}</div>` : ""}
      <p class="model-rule-src">${esc(info.label)} · ${esc(task.kind)}</p></li>`; }
  function policyTaskPicker(s) { const tasks = snapshot(s), picked = policyTask(s);
    const needle = s.rule.query.trim().toLocaleLowerCase();
    const shown = needle ? tasks.filter(task => { const info = taskName(task.kind);
      return (info.label + info.group + info.description + task.kind).toLocaleLowerCase().includes(needle); }) : tasks;
    const selected = picked && s.drafts.get(picked.kind) ? effective(picked, s.drafts.get(picked.kind), "replacement_scope") : "all";
    const locked = !picked || s.loading || s.busy || s.denied || s.drafts.get(picked.kind)?.pending;
    const scopeSeg = [["plugin", "仅插件调用"], ["conversation", "仅普通对话模型"], ["all", "全部生效"]];
    return `<div class="model-policy-controls">
      <label class="model-field"><span class="model-cap">当前编辑任务 <em>${picked ? esc(taskName(picked.kind).group) : "暂无可用任务"}</em></span>
        <select data-model-pol-task aria-label="选择要配置替换规则的任务">${shown.map(task => {
          const info = taskName(task.kind), count = ruleOf(s, task.kind).length;
          return `<option value="${esc(task.kind)}" ${task.kind === picked?.kind ? "selected" : ""}>${esc(info.label)} · ${esc(task.kind)}${count ? " · " + count + " 条规则" : ""}</option>`; }).join("")}</select></label>
      <label class="model-field"><span class="model-cap">筛选任务 <em>${shown.length}/${tasks.length}</em></span>
        <input data-model-pol-search value="${esc(s.rule.query)}" placeholder="按名称或任务键过滤"></label>
      <section class="model-policy-scope"><header><b>作用范围</b><span>控制哪些请求采用这项策略</span></header>
        <div class="model-seg" role="group" aria-label="替换策略作用范围">${scopeSeg.map(([id, label]) =>
          `<button type="button" data-model-scope="${id}" aria-pressed="${selected === id}" class="${selected === id ? "on" : ""}" ${locked ? "disabled" : ""}>${label}</button>`).join("")}</div>
      </section>
      <p class="model-policy-hint">按任务保存；设置会与「${esc(fieldLabel.replacement_rules)}」一起生效。</p>
    </div>`; }
  function keywordPolicy(s) { const task = policyTask(s); if (!task) return '<p class="model-empty">当前宿主还没有注册任何模型任务。</p>';
    const draft = s.drafts.get(task.kind), locked = s.loading || s.busy || s.denied || draft?.pending;
    const rules = ruleOf(s, task.kind), custom = !draft.inherited.replacement_rules;
    const inherited = task.fields.replacement_rules.inherited_value || "[]";
    return `<article class="model-pol-card"><header class="model-rule-title"><div><h3>关键词替换规则</h3>
        <p class="model-note">命中时使用目标 Provider。</p></div>
        <div class="model-rule-actions"><button type="button" class="button small" data-rule-add ${locked ? "disabled" : ""}>+ 新增规则</button></div></header>
      <ul class="model-rules">${rules.length ? rules.map((rule, index) => ruleCard(s, task, rule, index)).join("") : '<li class="model-empty">这项任务还没有替换规则。</li>'}</ul>
      <p class="model-note">上级默认规则 ${parseRules(inherited).length} 条 · 当前任务 ${rules.length} 条；${custom ? "已单独设置" : "跟随上级"}。</p>
      <details class="model-rule-json"><summary>JSON 源码</summary>
        <textarea rows="7" spellcheck="false" data-model-pol-json ${locked ? "disabled" : ""}>${esc(serializeRules(rules))}</textarea>
        <p class="model-note">失焦后提交；格式错误时保留原值。</p></details></article>`; }
  function peakPolicy(s) { const task = policyTask(s); if (!task) return '<p class="model-empty">当前宿主还没有注册任何模型任务。</p>';
    const draft = s.drafts.get(task.kind), locked = s.loading || s.busy || s.denied || draft?.pending;
    const rules = ruleOf(s, task.kind), windows = rules.filter(rule => !ruleKeywordText(rule) && rule.time_window);
    const providers = available(s, task), alternative = s.peak.provider;
    const extra = providers.some(provider => provider.id === alternative) ? "" : alternative ? `<option value="${esc(alternative)}" selected>${esc(alternative)} · 未注册</option>` : "";
    return `<article class="model-pol-card">
      <div class="model-phead"><div class="model-grow"><span class="model-eb">成本路由 · 可选</span><h3>高价时段替代</h3></div>
        <div class="model-st2"><span class="model-tag ${s.peak.on ? (s.peak.provider ? "a" : "a") : "n"}">${s.peak.on ? (s.peak.provider ? "已启用" : "等待选择替代 Provider") : "未启用"}</span>
          <label class="model-switch"><input type="checkbox" data-peak-switch ${s.peak.on ? "checked" : ""} ${locked ? "disabled" : ""} aria-label="启用高价时段替代"><i></i></label></div></div>
      ${s.peak.on ? `<div class="model-pol-body">
        <label class="model-fd"><span class="model-cap">高价时段替代 Provider <em>时段内整体改走这里</em></span>
          <select data-peak-provider ${locked ? "disabled" : ""}><option value="">请选择替代 Provider</option>${providers.map(provider => `<option value="${esc(provider.id)}" ${provider.id === alternative ? "selected" : ""}>${esc(provider.id)}</option>`).join("")}${extra}</select></label>
        <div class="model-fd"><span class="model-cap">高价时段 <em>点击格子切换 · 每行一个区间 · 支持跨午夜</em></span>
          <div class="model-band" data-peak-band>${Array.from({ length: 24 }, (_, hour) => {
            const on = peakWindows(s.peak).has(hour);
            return `<button type="button" class="model-band-cell${on ? " on" : ""}${hour % 3 === 0 ? " tick" : ""}" data-peak-hour="${hour}" title="${hour}:00" aria-label="${hour}:00–${(hour + 1) % 24}:00" aria-pressed="${on}" ${locked ? "disabled" : ""}>${hour % 3 === 0 ? hour : ""}</button>`; }).join("")}</div>
          <div class="model-hrs">${Array.from({ length: 24 }, (_, hour) => `<span>${hour % 3 === 0 ? hour : ""}</span>`).join("")}</div>
          <div class="model-hrl">
            <span class="lg"><i class="hi"></i>高价时段</span><span class="lg"><i class="lo"></i>默认路由</span>
            <span class="model-grow"></span>
            <button type="button" class="button small" data-peak-preset ${locked ? "disabled" : ""}>默认 09–12 / 14–18</button>
            <button type="button" class="button small" data-peak-clear ${locked ? "disabled" : ""}>清空时段</button></div>
        </div>
        <div class="model-kwc">
          <span class="model-cap">开始</span><input class="model-num" data-peak-start value="${esc(s.peak.start)}" maxlength="5" placeholder="09:00" ${locked ? "disabled" : ""}>
          <span class="model-cap">结束</span><input class="model-num" data-peak-end value="${esc(s.peak.end)}" maxlength="5" placeholder="18:00" ${locked ? "disabled" : ""}>
          <span class="model-grow"></span>
          <button type="button" class="button small primary" data-peak-apply ${locked ? "disabled" : ""}>写入这项任务的时段规则</button></div>
        <div class="model-runstat">
          <div class="rs"><span>当前选择</span><b>${esc(s.peak.windows.replaceAll(String.fromCharCode(10), " · ") || "无")}</b></div>
          <div class="rs"><span>已配置时段规则</span><b>${windows.length} 条</b></div>
          <div class="rs"><span>写入行为</span><b>替换本任务原有的纯时段规则</b></div>
        </div></div>` : ""}
      </article>`; }
  function refusalPolicy(s) { const task = policyTask(s); if (!task) return '<p class="model-empty">当前宿主还没有注册任何模型任务。</p>';
    const draft = s.drafts.get(task.kind), locked = s.loading || s.busy || s.denied || draft?.pending;
    const on = draft.inherited.fallback_on_refusal ? !!task.fields.fallback_on_refusal.inherited_value : !!draft.values.fallback_on_refusal;
    const fallback = effective(task, draft, "fallback");
    return `<article class="model-pol-card">
      <div class="model-phead"><div class="model-grow"><span class="model-eb">安全兜底</span><h3>拒答替代</h3></div>
        <div class="model-st2"><span class="model-tag ${on ? (fallback ? "g" : "a") : "n"}">${on ? (fallback ? "已启用 · 可重试一次" : "已开启 · 没有备用链路") : "未启用"}</span>
          <label class="model-switch"><input type="checkbox" data-refusal-switch ${on ? "checked" : ""} ${locked ? "disabled" : ""}><i></i></label></div></div>
      ${on ? `<div class="model-pol-body"><div class="model-rf2">
        <div class="model-fd"><span class="model-cap">拒答时换到哪里 <em>备用 Provider 在「模型配置 · 精准配置」设置</em></span>
          <div class="model-cur${fallback ? "" : " miss"}">${fallback ? esc(fallback) : "未设置备用 Provider · 开启后仍无路可退"}</div></div>
        <div class="model-fd"><span class="model-cap">判定方式 <em>V2 依据 Provider 返回的拒答标记，不再按文本匹配</em></span>
          <div class="model-rfchips">${REFUSAL_HINTS.map(hint => `<span class="model-kchip muted">${esc(hint)}</span>`).join("")}</div></div>
      </div></div>` : ""}
      <p class="model-note">命中拒答时使用备用模型重试一次。</p></article>`; }
  function replacementPolicy(s) { const task = policyTask(s), draft = task && s.drafts.get(task.kind);
    const rules = task ? ruleOf(s, task.kind) : [];
    const peakCount = rules.filter(rule => !ruleKeywordText(rule) && rule.time_window).length;
    const refusalOn = task && draft ? (draft.inherited.fallback_on_refusal
      ? !!task.fields.fallback_on_refusal.inherited_value : !!draft.values.fallback_on_refusal) : false;
    const modes = [["kw", "关键词换模", "按内容命中，切换到指定 Provider", `${rules.length} 条规则`],
      ["peak", "高价时段替代", "在指定时段改走成本模型", `${peakCount} 条时段规则`],
      ["refuse", "拒答替代", "主模型拒答后使用备用模型重试", refusalOn ? "已启用" : "未启用"]];
    const picked = taskOf(s, s.pol) || snapshot(s)[0];
    const panel = s.pm === "peak" ? peakPolicy(s) : s.pm === "refuse" ? refusalPolicy(s) : keywordPolicy(s);
    const locked = !picked || s.busy || s.loading || s.denied || s.drafts.get(picked.kind)?.pending;
    return `<div class="model-subpane model-policy">
      <header class="model-policy-heading"><div><span class="model-eb">MODEL ROUTING / ${esc(task ? taskName(task.kind).label : "TASK")}</span>
        <h3>替换策略工作台</h3><p>为不同任务组合内容路由、时段切换和拒答兜底。</p></div>
        ${draft && dirty(task, draft) ? '<span class="model-tag a">本任务有待保存改动</span>' : '<span class="model-tag">按任务独立生效</span>'}</header>
      ${notice(s)}
      <div class="model-policy-modes" role="group" aria-label="选择替换策略模式">${modes.map(([id, label, description, meta], index) =>
        `<button type="button" data-model-pm="${id}" aria-pressed="${s.pm === id}" class="model-policy-mode${s.pm === id ? " on" : ""}">
          <span class="model-policy-index">0${index + 1}</span><b>${label}</b><small>${description}</small><em>${esc(meta)}</em></button>`).join("")}</div>
      <div class="model-policy-layout"><aside class="model-policy-rail">${policyTaskPicker(s)}
        ${picked ? `<div class="model-pol-actions"><button type="button" class="button primary" data-policy-save="${esc(picked.kind)}" ${s.busy || s.loading || s.denied || s.drafts.get(picked.kind)?.stale || !dirty(picked, s.drafts.get(picked.kind)) ? "disabled" : ""}>保存本任务策略</button>
          <button type="button" class="button" data-policy-discard="${esc(picked.kind)}" ${s.busy || s.loading || s.drafts.get(picked.kind)?.pending ? "disabled" : ""}>放弃草稿</button></div>` : ""}
      </aside><div class="model-policy-editor">${picked ? panel : '<div class="model-empty">当前宿主还没有注册任何模型任务。</div>'}</div></div>
    </div>`; }
  function cfgPane(s) { const tasks = snapshot(s);
    const own = tasks.filter(t => fields.some(nm => t.fields[nm]?.explicit)).length;
    const note = s.status ? `生效中 · ${own} / ${tasks.length} 项任务单独设置了模型` : "";
    const cmSeg = [["quick", "快速配置"], ["precise", "精准配置"]];
    const seg = `<div class="model-seg" role="group" aria-label="配置模式">${cmSeg.map(([id, label]) => `<button type="button" data-model-cm="${id}" aria-pressed="${s.cm === id}" class="${s.cm === id ? "on" : ""}">${label}</button>`).join("")}</div>`;
    const body2 = s.cm === "quick" ? quickConfig(s) : `${rail(s)}${toolbar(s)}<div class="model-queue-slot">${queue(s)}</div>${body(s)}`;
    return `<div class="model-subpane"><div class="model-note cfg">${seg}</div>${notice(s)}${s.cm === "quick" ? "" : overview(s)}${body2}</div>`; }
  /* ---------- replacement policy: mutations ---------- */
  const ruleTarget = ref => { const [kind, index] = String(ref || "").split(":"); return { kind, index: Number(index) }; };
  /* Every rule edit funnels through here so the JSON the gateway reads stays canonical. */
  function editRules(s, kind, mutate) { const task = taskOf(s, kind), draft = s.drafts.get(kind);
    if (!task || !draft || draft.pending || s.busy || s.loading) return;
    const rules = ruleOf(s, kind).slice(); if (mutate(rules) === false) return;
    draft.values.replacement_rules = serializeRules(rules); draft.inherited.replacement_rules = false; draft.touched = true;
    s.bad = false; s.notice = `${taskName(kind).label} 的替换规则已改动，保存本任务后生效。`; render(); }
  function rulePatch(rule, patch) { Object.assign(rule, patch); }
  function ruleInput(s, event) { const t = event.target;
    if (t.matches("[data-model-pol-search]")) { s.rule.query = t.value; render();
      const next = root.querySelector("[data-model-pol-search]");
      if (next) { next.focus(); next.setSelectionRange(next.value.length, next.value.length); } return; }
    if (t.matches("[data-model-pol-json]")) { if (event.type !== "change") return; const task = policyTask(s); if (!task) return;
      const parsed = parseRules(t.value);
      try { JSON.parse(t.value || "[]"); } catch { s.bad = true; s.notice = "JSON 解析失败，已保留原有规则。"; render(); return; }
      editRules(s, task.kind, rules => { rules.length = 0; parsed.forEach(rule => rules.push(rule)); }); return; }
    if (t.matches("[data-peak-provider]")) { s.peak.provider = t.value; render(); return; }
    if (t.matches("[data-peak-start]") || t.matches("[data-peak-end]")) { s.peak[t.matches("[data-peak-start]") ? "start" : "end"] = t.value;
      if (event.type === "change") { if (timeValid(s.peak.start) && timeValid(s.peak.end) && s.peak.start !== s.peak.end)
        s.peak.windows = `${s.peak.start}-${s.peak.end}`; render(); } return; }
    const idRef = t.dataset.ruleId, kwRef = t.dataset.ruleKeywords, matchRef = t.dataset.ruleMatch, logicRef = t.dataset.ruleLogic,
      prioRef = t.dataset.rulePriority, provRef = t.dataset.ruleProvider, modelRef = t.dataset.ruleModel,
      startRef = t.dataset.ruleStart, endRef = t.dataset.ruleEnd, zoneRef = t.dataset.ruleZone;
    const ref = idRef || kwRef || matchRef || logicRef || prioRef || provRef || modelRef || startRef || endRef || zoneRef;
    if (!ref) return;
    const { kind, index } = ruleTarget(ref);
    const name = t.matches("[data-rule-id]") ? "id" : t.matches("[data-rule-keywords]") ? "keywords" : t.matches("[data-rule-match]") ? "match_mode"
      : t.matches("[data-rule-logic]") ? "keyword_logic" : t.matches("[data-rule-priority]") ? "priority" : t.matches("[data-rule-provider]") ? "provider_id"
      : t.matches("[data-rule-model]") ? "model" : "window";
    const value = name === "keywords" ? keywordChips(t.value) : name === "priority" ? (Number.isFinite(t.valueAsNumber) ? t.valueAsNumber : 0) : t.value;
    /* Free-text fields must not re-render on every keystroke or the caret is lost. */
    const typing = (name === "id" || name === "keywords" || name === "model") && event.type === "input";
    if (typing) { const task = taskOf(s, kind), draft = s.drafts.get(kind);
      if (!task || !draft || draft.pending) return;
      const rules = ruleOf(s, kind).slice(); if (!rules[index]) return;
      rules[index][name] = value;
      draft.values.replacement_rules = serializeRules(rules); draft.inherited.replacement_rules = false; draft.touched = true;
      return; }
    editRules(s, kind, rules => { const rule = rules[index]; if (!rule) return false;
      if (name !== "window") { rulePatch(rule, { [name]: value }); return; }
      if (!rule.time_window || typeof rule.time_window !== "object") rule.time_window = { timezone: "Asia/Shanghai", start: "09:00", end: "18:00", weekdays: [0, 1, 2, 3, 4, 5, 6] };
      if (t.matches("[data-rule-start]")) rule.time_window.start = value;
      else if (t.matches("[data-rule-end]")) rule.time_window.end = value;
      else rule.time_window.timezone = value || "Asia/Shanghai"; }); }
  function ruleClick(s, event) { const t = event.target;
    const save = t.closest("[data-policy-save]"); if (save) { saveTasks(s, [save.dataset.policySave]); return; }
    const discardButton = t.closest("[data-policy-discard]"); if (discardButton) { discard(s, [discardButton.dataset.policyDiscard]); return; }
    const add = t.closest("[data-rule-add]"); if (add) { const task = policyTask(s); if (!task) return;
      const providers = available(s, task), rules = ruleOf(s, task.kind);
      const used = new Set(rules.map(rule => rule.id));
      let seed = 1; while (used.has("rule-" + seed)) seed++;
      editRules(s, task.kind, list => list.push({ ...RULE_SEED, id: "rule-" + seed, provider_id: providers[0]?.id || "" })); return; }
    const del = t.closest("[data-rule-del]"); if (del) { const { kind, index } = ruleTarget(del.dataset.ruleDel);
      editRules(s, kind, rules => { if (!rules[index]) return false; rules.splice(index, 1); }); return; }
    const hour = t.closest("[data-peak-hour]"); if (hour) { const cells = peakWindows(s.peak);
      const value = Number(hour.dataset.peakHour); cells.has(value) ? cells.delete(value) : cells.add(value);
      s.peak.windows = formatWindows(cells); const first = peakSegments(s.peak.windows)[0];
      s.peak.start = first?.[0] || ""; s.peak.end = first?.[1] || "";
      render(); return; }
    const preset = t.closest("[data-peak-preset]"); if (preset) { s.peak.windows = "09:00-12:00\n14:00-18:00"; s.peak.start = "09:00"; s.peak.end = "12:00"; render(); return; }
    const clear = t.closest("[data-peak-clear]"); if (clear) { s.peak.windows = ""; s.peak.start = ""; s.peak.end = ""; render(); return; }
    const apply = t.closest("[data-peak-apply]"); if (apply) { const task = policyTask(s); if (!task) return;
      if (s.peak.on && !s.peak.provider) { s.bad = true; s.notice = "先选择时段替代的 Provider。"; render(); return; }
      const segments = peakSegments(s.peak.windows);
      if (s.peak.on && !segments.length) { s.bad = true; s.notice = "先设置至少一个有效时段。"; render(); return; }
      editRules(s, task.kind, rules => { for (let index = rules.length - 1; index >= 0; index--)
        if (!ruleKeywordText(rules[index]) && rules[index].time_window) rules.splice(index, 1);
        if (s.peak.on) segments.forEach(([start, end]) => rules.push({ ...RULE_SEED,
          id: "peak-" + start.replace(":", "") + "-" + end.replace(":", ""), provider_id: s.peak.provider,
          time_window: { timezone: "Asia/Shanghai", start, end, weekdays: [0, 1, 2, 3, 4, 5, 6] } })); }); return; }
    const scope = t.closest("[data-model-scope]"); if (scope) { const task = policyTask(s), draft = task && s.drafts.get(task.kind);
      if (!draft || draft.pending || s.busy || s.loading || s.denied) return;
      draft.values.replacement_scope = scope.dataset.modelScope; draft.inherited.replacement_scope = false; draft.touched = true;
      s.notice = `${taskName(task.kind).label} 的替换范围已改动，保存本任务后生效。`; s.bad = false; render(); return; } }
  function ruleChange(s, event) { const t = event.target;
    if (t.matches("[data-model-pol-task]")) { s.pol = t.value; render(); return; }
    if (t.matches("[data-peak-switch]")) { s.peak.on = t.checked; render(); return; }
    if (t.matches("[data-refusal-switch]")) { const task = policyTask(s); const draft = task && s.drafts.get(task.kind);
      if (!task || !draft || draft.pending || s.busy || s.loading) return;
      draft.values.fallback_on_refusal = t.checked; draft.inherited.fallback_on_refusal = false; draft.touched = true;
      s.bad = false; s.notice = t.checked ? `${taskName(task.kind).label} 已开启拒答替代，保存本任务后生效。` : `${taskName(task.kind).label} 已关闭拒答替代，保存本任务后生效。`;
      render(); return; }
    const enabled = t.dataset.ruleEnabled, window = t.dataset.ruleWindow;
    if (enabled) { const { kind, index } = ruleTarget(enabled);
      editRules(s, kind, rules => { const rule = rules[index]; if (!rule) return false; rule.enabled = t.checked; }); return; }
    if (window) { const { kind, index } = ruleTarget(window);
      editRules(s, kind, rules => { const rule = rules[index]; if (!rule) return false;
        if (t.checked) rule.time_window = { timezone: "Asia/Shanghai", start: "09:00", end: "18:00", weekdays: [0, 1, 2, 3, 4, 5, 6] };
        else delete rule.time_window; }); return; }
    ruleInput(s, event); }
  function fnPane(s) { const sub = s.sub === "map" ? situationMap(s) : s.sub === "pol" ? replacementPolicy(s) : cfgPane(s);
    return `${topbar(s)}${subtabBar(s)}${sub}`; }
  function pane(s) { if (s.tab === "voice") return voicePane(s); if (s.tab === "image") return imagePane(s); return fnPane(s); }
  function drawer(s) { const id = s.drawer; if (!id) return "";
    const provider = s.status?.providers.find(p => p.id === id); if (!provider) return "";
    const tasks = snapshot(s), asMain = tasks.filter(t => providerFor(t, s.drafts.get(t.kind)) === id);
    const asFb = tasks.filter(t => effective(t, s.drafts.get(t.kind), "fallback") === id);
    return `<div class="model-mask on" data-drawer-close></div><aside class="model-drawer on" role="dialog" aria-label="Provider ${esc(id)}">
      <div class="dh"><div><h3>${esc(id)}</h3><p>${esc(provider.capabilities.join(" · ") || "无能力声明")}</p></div>
        <button type="button" class="x" data-drawer-close aria-label="关闭">×</button></div>
      <dl class="model-kv"><dt>单次输出上限</dt><dd>${provider.max_output_tokens}</dd>
        <dt>承担任务</dt><dd>${asMain.length} 项主路由 · ${asFb.length} 项备用</dd></dl>
      <div class="model-sec"><h4>作为主模型 · ${asMain.length} 项</h4>${asMain.map(t => `<div class="li">${esc(taskName(t.kind).label)}<span>${esc(taskName(t.kind).description)}</span></div>`).join("") || '<span class="model-mono">无</span>'}</div>
      <div class="model-sec"><h4>作为备用 · ${asFb.length} 项</h4>${asFb.map(t => `<div class="li">${esc(taskName(t.kind).label)}<span>${esc(taskName(t.kind).description)}</span></div>`).join("") || '<span class="model-mono">无</span>'}</div>
      <div class="model-sec"><button type="button" class="button primary" style="width:100%" data-drawer-goto="${esc(id)}">在精准配置中调整</button></div></aside>`; }
  function render() { if (!root || !state) return; const s = state;
    root.innerHTML = `<div class="model-workspace">${s.catalog ? `<div class="model-catalog" role="status"><strong>AstrBot 模型列表</strong><span>${s.catalog.providers.length} 个已加载 Provider</span>${s.catalog.providers.map(p => `<span class="model-pill ${p.configured ? "ok" : "warn"}">${esc(p.name || p.id)} · ${esc(p.id)}</span>`).join("")}</div>` : ""}${tabBar(s)}${pane(s)}${drawer(s)}</div>`; }
  function input(event) { const s = state; if (!s || !root?.isConnected) return;
    if (s.tab === "voice") { voiceInput(s, event); return; }
    if (s.tab === "image") { imageInput(s, event); return; }
    fnInput(event); }
  function click(event) { const s = state; if (!s || !root?.isConnected) return;
    const tab = event.target.closest("[data-model-tab]");
    if (tab) { const id = tab.dataset.modelTab; if (s.tab !== id) { s.tab = id;
        if (id === "voice" && !state.voice.loaded) voiceRefresh(s); else if (id === "image" && !state.image.loaded) imageRefresh(s);
        render(); } return; }
    if (s.tab === "voice") { voiceClick(s, event); return; }
    if (s.tab === "image") { imageClick(s, event); return; }
    fnClick(event); }
  /* ---------- lifecycle ---------- */
  function unmount() { version++; if (root) { root.removeEventListener("input", input); root.removeEventListener("change", input); root.removeEventListener("click", click); }
    if (state) { state.loading = false; state.busy = false; }
    root = null; state = null; path = key = null; }
  function mount(element) { unmount(); root = element; if (!root) return; const product = window.CompanionProduct;
    /* 这里原先先判断 hosted()，桥还没注入时直接写「从 AstrBot 管理界面打开陪伴小屋后…」。
       桥的注入晚于脚本执行是正常时序，所以那句话在正经的拓展页里也出现过。
       现在改成读不到就说读不到，并给一个重新读取的入口——刷新之后桥通常就在了。 */
    const identity = product.identity();
    const endpoint = product.role()?.model_api;
    if (!product.hosted() || typeof endpoint !== "string" || !endpoint.startsWith(PREFIX) || /[?#%\\:]/.test(endpoint) || endpoint.split("/").slice(1).some(p => !p || p === "." || p === "..") || !identity.operator_id) { root.innerHTML = `<div class="model-empty">${product.hosted()?'当前对象没有模型配置工作区。请选择已初始化的私聊对象和角色。':'还没有读到宿主目录。宿主注入连接通常比页面脚本晚几秒，重新读取一次即可。'}<div class="dialog-actions"><button class="button small" type="button" data-workspace-retry>重新读取</button><button class="button small" type="button" data-go="manage" data-manage="host">账号与会话</button></div></div>`; return; }
    /* path 是每一次请求的基址（model_api + /configure、/voice、/tts/providers…），
       也是 localStorage 键的一部分。桥要插件相对路径，所以切掉插件目录名。 */
    path = endpoint.slice(PREFIX.length); key = "companion-model-edit.v2:" + JSON.stringify([identity.installation_id, identity.operator_id, path]);
    state = states.get(key) || { status: null, catalog: null, drafts: new Map(), selection: [], expanded: null, view: "tasks", custom: null, lane: "all", providerFilter: null, query: "", sub: "cfg", cm: "precise", av: "slot", af: "all", pm: "kw", slotDraft: {}, providerTests: {}, testing: new Set(),
      drawer: null, expOpen: {}, pol: null, rule: { query: "", picked: [], report: null, testing: false }, peak: { on: true, provider: "", start: "09:00", end: "12:00", windows: "09:00-12:00\n14:00-18:00" },
      tab: "fn",
      voice: { data: null, draft: null, loaded: false, loading: false, busy: false, testing: false, bad: false, notice: "", ui: { lang: "ja" },
        editorOpen: false, catalog: null, catalogLoading: false, editorId: null, editorValues: {}, creating: false, ttsBusy: false, createDraft: { type: "", id: "" } },
      image: { data: null, draft: null, loaded: false, loading: false, busy: false, testing: null, bad: false, notice: "",
        configOpen: false, config: null, configLoading: false, configSaving: false, configDraft: null, configTab: "routes" },
      loading: false, busy: false, bad: false, denied: false, notice: "" };
    state.providerTests ||= {}; state.testing ||= new Set(); state.expOpen ||= {}; state.drawer ||= null; state.voice.lastTest ||= null; state.voice.editorValues ||= {}; state.voice.createDraft ||= { type: "", id: "" }; state.configDraft ||= null; state.peak ||= { on: true, provider: "", start: "09:00", end: "12:00" }; state.testing ||= new Set(); state.peak.windows ||= "09:00-12:00\n14:00-18:00"; state.image.configTab ||= "routes";
    states.set(key, state);
    root.addEventListener("input", input); root.addEventListener("change", input); root.addEventListener("click", click); render();
    if (state.tab && state.tab !== "fn") { if (state.tab === "voice" && !state.voice.loaded) voiceRefresh(state); else if (state.tab === "image" && !state.image.loaded) imageRefresh(state); }
    else { refresh().catch(error => { if (error?.code !== "staging_not_initialized") return; const ticket = version; api("GET", path + "/catalog").then(data => { if (current(ticket, state)) { state.catalog = data; render(); } }).catch(() => {}); }); } }
  return { mount, unmount };
})();
