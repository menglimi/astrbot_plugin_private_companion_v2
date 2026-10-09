/* Per-capability Reality consent for the selected private V2 scope. */
"use strict";
window.CompanionRealityAccess = (() => {
  const product = window.CompanionProduct;
  const esc = value => String(value ?? "").replace(/[&<>"']/g,
    char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const messages = {
    reality_provider_unavailable:"现实触及的 V2 接口尚未加载，请检查插件后重新读取。",
    reality_provider_changed:"现实触及接口已变化，请重新加载 V2 运行实例。",
    reality_package_changed:"现实触及版本已变化，请重新读取能力状态。",
    reality_access_changed:"授权状态已变化，请重新读取后再保存。",
    capability_not_installed:"当前会话尚未启用现实触及。",
    capability_not_active:"现实触及能力已暂停或移除，需要先恢复能力。",
    capability_role_disabled:"当前 Bot 的这个人格尚未启用现实触及。",
    capability_consent_missing:"当前私聊尚未允许此项能力。",
    camera_consent_missing:"当前私聊尚未允许摄像头识别。",
    reality_tool_unavailable:"此项工具尚未进入当前对话。",
    camera_tool_unavailable:"摄像头工具尚未进入当前对话。",
    reality_private_required:"现实触及的个人数据和设备能力只适用于已绑定的私聊窗口。",
    reality_camera_private_required:"摄像头观察只适用于已绑定的私聊窗口。",
    staging_not_initialized:"角色数据尚未就绪，请在「账号与会话」保存角色映射；已保存可重新读取状态。",
    staging_host_terminated:"V2 已停止，请重新加载插件。",
    core_access_required:"当前账号没有管理此授权的权限。",
    dashboard_identity_required:"请从已登录的 AstrBot 管理界面打开。",
    bridge_timeout:"连接超时。可用同一个操作编号核对原请求。",
  };
  const labels = {
    mobile:{path:"", capability:"reality.snapshot.read", icon:"map-pin", title:"手机摘要",
      description:"读取位置、终端状态、活动和健康摘要。", allowed:"允许读取手机摘要", revoke:"撤回手机摘要授权",
      saved:"已允许当前私聊读取手机摘要。", removed:"已撤回当前私聊的手机摘要授权。", ready:"手机摘要工具已进入当前对话。"},
    camera:{path:"/camera", capability:"reality.camera.observe", icon:"camera", title:"摄像头单帧",
      description:"仅按用户本轮明确请求读取单帧并返回识别摘要。", allowed:"允许摄像头单帧观察", revoke:"撤回摄像头授权",
      saved:"已允许当前私聊按明确请求读取单帧。", removed:"已撤回当前私聊的摄像头授权。",
      ready:"V2 授权已生效；Reality 侧设置和用户确认仍然有效。"},
    deviceList:{path:"/device-list", capability:"reality.device.list", icon:"list", title:"米家设备目录",
      description:"查看已映射别名、设备类别和缓存在线状态。", allowed:"允许读取设备目录", revoke:"撤回设备目录授权",
      saved:"已允许当前私聊读取设备目录。", removed:"已撤回当前私聊的设备目录授权。", ready:"设备目录工具已进入当前对话。"},
    deviceStatus:{path:"/device-status", capability:"reality.device.status", icon:"activity", title:"单设备状态",
      description:"按精确别名读取设备档案允许公开的属性。", allowed:"允许读取设备状态", revoke:"撤回设备状态授权",
      saved:"已允许当前私聊读取设备状态。", removed:"已撤回当前私聊的设备状态授权。", ready:"设备状态工具已进入当前对话。"},
    deviceControl:{path:"/device-control", capability:"reality.device.control", icon:"power", title:"设备电源控制",
      description:"对扩展白名单中的精确别名设备开关电源，会产生真实设备动作。", allowed:"允许控制设备电源", revoke:"撤回电源控制授权",
      saved:"已允许当前私聊控制白名单设备电源。", removed:"已撤回当前私聊的电源控制授权。", ready:"电源控制工具已进入当前对话。"},
    deviceAction:{path:"/device-action", capability:"reality.device.action", icon:"sliders-horizontal", title:"设备属性动作",
      description:"执行设备档案声明可写的模式、亮度或色温动作，会改变真实设备状态。", allowed:"允许设备属性动作", revoke:"撤回属性动作授权",
      saved:"已允许当前私聊执行设备属性动作。", removed:"已撤回当前私聊的设备属性动作授权。", ready:"设备属性动作工具已进入当前对话。"},
    operationLookup:{path:"/operation-lookup", capability:"reality.operation.lookup", icon:"search-check", title:"操作结果查询",
      description:"读取当前范围的原操作确认，不会重新派发设备动作。", allowed:"允许查询操作确认", revoke:"撤回操作查询授权",
      saved:"已允许当前私聊查询原操作确认。", removed:"已撤回当前私聊的操作查询授权。", ready:"操作查询工具已进入当前对话。"},
    operationCancel:{path:"/operation-cancel", capability:"reality.operation.cancel", icon:"ban", title:"未派发操作取消",
      description:"只可取消尚未跨过派发边界的操作；已派发操作请查询原确认。", allowed:"允许取消未派发操作", revoke:"撤回操作取消授权",
      saved:"已允许当前私聊取消未派发操作。", removed:"已撤回当前私聊的操作取消授权。", ready:"操作取消工具已进入当前对话。"},
  };
  const groups = [
    ["手机与镜头", ["mobile", "camera"]],
    ["米家设备", ["deviceList", "deviceStatus", "deviceControl", "deviceAction"]],
    ["设备操作确认", ["operationLookup", "operationCancel"]],
  ];
  let node = null, scope = "", paths = {}, statuses = {}, pending = {}, busy = new Set();
  let notices = {}, generation = 0;
  const pendingByScope = new Map();
  /* 授权读取结果按私聊角色范围暂存于本页内存。这样切换工作区后先能看到
     上次确认的状态，再由当前宿主请求刷新；不同能力、路由或范围不会串用。 */
  const statusByScope = new Map();
  const current = ticket => ticket === generation && node?.isConnected && scope === product.scopeKey();
  const scopeKey = kind => `${scope}:${kind}`;
  const statusKey = kind => `${scopeKey(kind)}:${paths[kind] || ""}`;
  const errorText = error => messages[error?.code] || messages[error?.message]
    || "暂时无法核对授权，请重新读取。";
  function identityLine() {
    return product.scopeLabel?.() || "当前私聊窗口";
  }
  function panel(kind) {
    const meta = labels[kind], status = statuses[kind], command = pending[kind];
    const canManage = status?.can_manage !== false;
    const stateLabel = !status ? "读取失败" : !canManage ? "只读" : status.invokable ? "可调用"
      : status.consented ? "未接通" : "未授权";
    const text = notices[kind] || (!canManage ? messages.core_access_required : status?.invokable ? meta.ready
      : status ? messages[status.reason] || "此项能力尚未进入当前对话。" : "正在读取此项授权…");
    const button = command
      ? canManage ? `<button class="button small" type="button" data-reality-access-action="${kind}-retry" ${busy.has(kind) ? "disabled" : ""}>${busy.has(kind) ? "正在核对…" : "核对原请求"}</button>` : ""
      : status && paths[kind] && canManage
        ? `<button class="button small ${status.consented ? "secondary" : "primary"}" type="button" data-reality-access-action="${kind}-${status.consented ? "disable" : "enable"}" ${busy.has(kind) ? "disabled" : ""}>${busy.has(kind) ? "正在保存…" : status.consented ? meta.revoke : meta.allowed}</button>`
        : "";
    return `<article class="reality-consent-panel ${status?.invokable ? "is-ready" : ""}">
      <header><span class="reality-consent-mark"><i data-lucide="${meta.icon}"></i></span><div><h4>${meta.title}</h4><small>${meta.description}</small></div>
        <span class="reality-consent-state ${status?.invokable ? "is-ready" : ""}">${stateLabel}</span></header>
      <p role="status" aria-live="polite">${esc(text)}</p><div class="dialog-actions">${button}</div>
    </article>`;
  }
  function render() {
    if (!node?.isConnected) return;
    const sections = groups.map(([title, kinds]) => `<section class="reality-consent-group" aria-label="${title}">
      <h4>${title}</h4><div class="reality-consent-grid">${kinds.map(panel).join("")}</div></section>`).join("");
    node.innerHTML = `<div class="reality-consent-head"><div><strong>当前会话能力授权</strong><small>${esc(identityLine())}</small></div>
      <button class="button small" type="button" data-reality-access-action="refresh" ${busy.size ? "disabled" : ""}>重新读取</button></div>${sections}`;
    window.lucide?.createIcons({attrs:{"aria-hidden":"true"}});
  }
  async function loadOne(kind, ticket) {
    if (!current(ticket)) return;
    busy.add(kind); notices[kind] = ""; render();
    try {
      if (!product.hosted() || !paths[kind]) throw {code:"reality_private_required"};
      const result = await product.request("GET", paths[kind]);
      if (!current(ticket)) return;
      if (result?.action !== labels[kind].capability || typeof result?.invokable !== "boolean"
          || typeof result?.consented !== "boolean" || typeof result?.edit_token !== "string")
        throw {code:"invalid_response"};
      statuses[kind] = result;
      statusByScope.set(statusKey(kind), result);
    } catch (error) {
      if (current(ticket)) {
        statuses[kind] = null;
        statusByScope.delete(statusKey(kind));
        notices[kind] = errorText(error);
      }
    } finally {
      if (current(ticket)) { busy.delete(kind); render(); }
    }
  }
  function nonce() {
    return crypto.randomUUID?.() || Array.from(crypto.getRandomValues(new Uint32Array(4)),
      value => value.toString(16).padStart(8, "0")).join("");
  }
  async function save(kind, enabled) {
    if (!current(generation) || busy.has(kind) || !paths[kind] || (!statuses[kind] && !pending[kind])) return;
    const ticket = generation;
    const key = scopeKey(kind);
    pending[kind] ||= {operation_key:`reality-${kind}-${nonce()}`, edit_token:statuses[kind].edit_token, enabled};
    const command = pending[kind];
    pendingByScope.set(key, command);
    busy.add(kind); notices[kind] = ""; render();
    try {
      const result = await product.request("POST", paths[kind] + "/configure", command);
      if (typeof result?.status?.invokable === "boolean" && pendingByScope.get(key) === command)
        pendingByScope.delete(key);
      if (!current(ticket)) return;
      if (result?.status?.action !== labels[kind].capability
          || typeof result?.status?.invokable !== "boolean" || typeof result?.status?.consented !== "boolean")
        throw {code:"invalid_response"};
      statuses[kind] = result.status; statusByScope.set(statusKey(kind), result.status); pending[kind] = null;
      notices[kind] = command.enabled ? labels[kind].saved : labels[kind].removed;
    } catch (error) {
      if (current(ticket)) {
        notices[kind] = errorText(error);
        if (["reality_access_changed","reality_package_changed","reality_request_invalid",
             "core_access_required","dashboard_identity_required"].includes(error.code || error.message)) {
          pendingByScope.delete(key); pending[kind] = null;
          statusByScope.delete(statusKey(kind)); statuses[kind] = null;
        }
      }
    } finally { if (current(ticket)) { busy.delete(kind); render(); } }
  }
  function click(event) {
    const action = event.target.closest("[data-reality-access-action]")?.dataset.realityAccessAction;
    if (!action) return;
    if (action === "refresh") {
      const ticket = generation;
      void Promise.all(Object.keys(labels).map(kind => loadOne(kind, ticket)));
      return;
    }
    const divider = action.lastIndexOf("-");
    const kind = action.slice(0, divider), intent = action.slice(divider + 1);
    if (!labels[kind]) return;
    if (intent === "retry") void save(kind, pending[kind]?.enabled);
    else void save(kind, intent === "enable");
  }
  function unmount() {
    ++generation;
    node?.removeEventListener("click", click);
    node = null; scope = ""; paths = {}; statuses = {}; pending = {}; busy = new Set(); notices = {};
  }
  function mount(host) {
    unmount(); node = host; if (!node) return;
    scope = product.scopeKey();
    for (const kind of Object.keys(labels)) pending[kind] = pendingByScope.get(scopeKey(kind)) || null;
    try {
      const base = product.role()?.reality_access_api;
      const relative = base ? product.relative(base) : "";
      paths = relative ? Object.fromEntries(Object.entries(labels).map(([kind, meta]) =>
        [kind, relative + meta.path])) : {};
    } catch (_) { paths = {}; }
    for (const kind of Object.keys(labels)) statuses[kind] = statusByScope.get(statusKey(kind)) || null;
    node.addEventListener("click", click);
    render();
    const ticket = generation;
    void Promise.all(Object.keys(labels).map(kind => loadOne(kind, ticket)));
  }
  return {mount, unmount};
})();
