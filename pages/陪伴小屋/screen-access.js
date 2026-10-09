/* Independent V2 consent for the native Screen capture tool. */
"use strict";
window.CompanionScreenAccess = (() => {
  const product = window.CompanionProduct;
  const messages = {
    screen_provider_unavailable:"未检测到可用的 Screen 原生扩展。请在 Screen 插件配置中启用 native_v2 并重载该插件后重试。",
    screen_provider_changed:"屏幕陪伴扩展已变化，请重新加载 V2 运行实例。",
    screen_package_changed:"屏幕陪伴版本已变化，请重新读取能力状态。",
    screen_access_changed:"授权状态已变化，请重新读取后再保存。",
    capability_not_installed:"当前尚未启用屏幕陪伴。",
    capability_not_active:"屏幕陪伴能力已暂停或移除，需要先恢复能力。",
    capability_role_disabled:"当前 Bot 的这个人格尚未启用屏幕陪伴。",
    screen_read_consent_missing:"当前私聊尚未允许读取屏幕原件。",
    screen_process_consent_missing:"当前私聊尚未允许处理屏幕画面。",
    screen_tool_unavailable:"屏幕采集工具尚未进入当前对话。",
    screen_private_required:"屏幕读取只适用于已绑定的私聊窗口。",
    screen_target_unavailable:"当前私聊没有可用的屏幕授权地址，请在账号与会话中刷新目标后重试。",
    staging_not_initialized:"角色数据尚未就绪，请在「账号与会话」保存角色映射；已保存可重新读取状态。",
    staging_host_terminated:"V2 已停止，请重新加载插件。",
    core_access_required:"当前账号没有管理此授权的权限。",
    dashboard_identity_required:"请从已登录的 AstrBot 管理界面打开。",
    bridge_timeout:"连接超时。可用同一个操作编号核对原请求。",
  };
  let node = null, path = "", status = null, pending = null, busy = false, notice = "", generation = 0;
  const pendingByScope = new Map();
  /* 路由切换会卸载工作区，但最近一次已确认的授权状态仍属于当前
     私聊范围。只放在本页进程内，按范围和实际路由隔离，不落盘。 */
  const statusByScope = new Map();
  const statusKey = (scope, route) => `${scope}:${route}`;
  const current = ticket => ticket === generation && node?.isConnected && path && path === currentPath();
  function currentPath() {
    try { return product.relative(product.role()?.screen_access_api || ""); } catch (_) { return ""; }
  }
  function errorText(error) { return messages[error?.code] || messages[error?.message] || "暂时无法核对屏幕授权，请重新读取。"; }
  function identityLine() {
    return product.scopeLabel?.() || "当前私聊窗口";
  }
  function scopeIssue() {
    const target = product.target();
    if (target?.scope_kind === "group") return "屏幕读取仅适用于已绑定的私聊窗口；请切换到私聊对象。";
    if (!product.hosted()) return "请从已登录的 AstrBot Dashboard 打开陪伴小屋。";
    if (!path) return messages.screen_target_unavailable;
    return "";
  }
  function escapeHTML(value) { return String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;", "'":"&#39;"}[char])); }
  function render() {
    if (!node?.isConnected) return;
    const ready = status?.invokable === true;
    const canManage = status?.can_manage !== false;
    const command = pending;
    const issue = scopeIssue();
    const text = notice || issue || (!canManage ? messages.core_access_required : ready ? "屏幕工具已进入当前私聊；只有本轮确实需要桌面画面时才会采集。"
      : status ? messages[status.reason] || "当前私聊尚未允许屏幕读取。" : "正在读取屏幕授权…");
    const action = issue || !canManage ? "" : command ? "retry" : status ? (status.consented ? "disable" : "enable") : "";
    const label = command ? (busy ? "正在核对…" : "核对原请求")
      : status?.consented ? "撤回当前私聊授权" : "允许当前私聊按需看屏";
    const stateLabel = !canManage ? "只读" : ready ? "已授权" : issue ? "仅限私聊" : status ? "未就绪" : busy ? "核对中" : "暂不可用";
    node.innerHTML = `<div class="reality-consent-head"><div><strong>屏幕读取权限</strong><small>${escapeHTML(identityLine())}</small></div>
      <button class="button small" type="button" data-screen-access-action="refresh" ${busy ? "disabled" : ""}>重新读取</button></div>
      <article class="reality-consent-panel ${ready ? "is-ready" : ""}">
        <header><span class="reality-consent-mark"><i data-lucide="monitor-dot"></i></span><div><h4>按需采集当前桌面</h4><small>只在明确需要时调用一次；屏幕原件只进入本轮理解，不会变成出站图片。</small></div>
          <span class="reality-consent-state ${ready ? "is-ready" : ""}">${stateLabel}</span></header>
        <p role="status" aria-live="polite">${escapeHTML(text)}</p>
        <div class="dialog-actions">${action ? `<button class="button small ${status?.consented ? "secondary" : "primary"}" type="button" data-screen-access-action="${action}" ${busy ? "disabled" : ""}>${busy ? "正在保存…" : label}</button>` : ""}</div>
      </article>`;
    window.lucide?.createIcons({attrs:{"aria-hidden":"true"}});
  }
  function nonce() { return crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`; }
  async function load(ticket = generation) {
    if (!node?.isConnected || busy) return;
    if (scopeIssue()) { render(); return; }
    if (!current(ticket)) return;
    busy = true; notice = ""; render();
    try {
      if (!product.hosted() || !path) throw {code:"screen_private_required"};
      const result = await product.request("GET", path);
      if (!current(ticket)) return;
      if (typeof result?.invokable !== "boolean" || typeof result?.consented !== "boolean" || typeof result?.edit_token !== "string") throw {code:"invalid_response"};
      status = result; pending = pendingByScope.get(product.scopeKey()) || null;
      statusByScope.set(statusKey(product.scopeKey(), path), result);
    } catch (error) {
      if (current(ticket)) {
        status = null;
        statusByScope.delete(statusKey(product.scopeKey(), path));
        notice = errorText(error);
      }
    } finally {
      if (current(ticket)) { busy = false; render(); }
    }
  }
  async function save(enabled) {
    if (!current(generation) || busy || !path || (!status && !pending)) return;
    const ticket = generation, scope = product.scopeKey();
    pending ||= {operation_key:`screen-${nonce()}`, edit_token:status.edit_token, enabled};
    pendingByScope.set(scope, pending); busy = true; notice = ""; render();
    try {
      const result = await product.request("POST", path + "/configure", pending);
      if (!current(ticket)) return;
      if (typeof result?.status?.invokable !== "boolean" || typeof result?.status?.consented !== "boolean") throw {code:"invalid_response"};
      status = result.status; statusByScope.set(statusKey(scope, path), result.status);
      pendingByScope.delete(scope); pending = null;
      notice = enabled ? "已保存：当前私聊可以在需要时按需看屏。" : "已撤回当前私聊的屏幕读取授权。";
    } catch (error) {
      if (current(ticket)) {
        notice = errorText(error);
        if (["screen_access_changed","screen_package_changed","screen_provider_changed","screen_provider_unavailable","screen_access_request_invalid","core_access_required","dashboard_identity_required"].includes(error.code || error.message)) {
          pendingByScope.delete(scope); pending = null;
          statusByScope.delete(statusKey(scope, path)); status = null;
        }
      }
    } finally { if (current(ticket)) { busy = false; render(); } }
  }
  function click(event) {
    const action = event.target.closest("[data-screen-access-action]")?.dataset.screenAccessAction;
    if (!action) return;
    if (action === "refresh") { void load(); return; }
    if (action === "retry") { void save(pending?.enabled); return; }
    if (action === "enable" || action === "disable") void save(action === "enable");
  }
  function unmount() { ++generation; node?.removeEventListener("click", click); node = null; path = ""; status = null; pending = null; busy = false; notice = ""; }
  function mount(host) {
    unmount(); node = host; if (!node) return; path = currentPath();
    const scope = product.scopeKey();
    status = statusByScope.get(statusKey(scope, path)) || null;
    pending = pendingByScope.get(scope) || null;
    node.addEventListener("click", click); render(); void load();
  }
  return {mount, unmount};
})();
