"use strict";
window.CompanionRoleProfileMigration = (() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
  const labels = window.CompanionConfigEditors?.spec?.role_profile?.labels || {};
  const state = {plan: null, personaId: "", busy: false, pending: null, pendingPersisted: false};

  function markup() {
    return '<dialog class="role-profile-draft-dialog role-profile-migration-dialog" id="roleProfileMigrationDialog" aria-labelledby="roleProfileMigrationTitle">' +
      '<div class="role-profile-draft-shell"><header class="role-profile-draft-head">' +
      '<div><span>PERSONA → ROLE CANON</span><h2 id="roleProfileMigrationTitle">迁入已有设定</h2></div>' +
      '<button class="icon-button" type="button" data-role-profile-migration-close aria-label="关闭" title="关闭"><i data-lucide="x" aria-hidden="true"></i></button></header>' +
      '<p class="role-profile-migration-notice" data-role-profile-migration-notice role="status" aria-live="polite">读取 V1 世界知识中的角色设定；没有可用来源时读取当前 AstrBot 人格。</p>' +
      '<section class="role-profile-migration-output" data-role-profile-migration-output hidden>' +
      '<div class="role-profile-migration-counts" data-role-profile-migration-counts></div>' +
      '<div class="role-profile-migration-fields" data-role-profile-migration-fields></div></section>' +
      '<footer class="role-profile-draft-actions"><span data-role-profile-migration-footer></span><div>' +
      '<button class="button small" type="button" data-role-profile-migration-close>取消</button>' +
      '<button class="button small primary" type="button" data-role-profile-migration-apply disabled>确认迁入空白项</button></div></footer></div></dialog>';
  }

  function notice(text, bad = false) {
    const node = $("[data-role-profile-migration-notice]");
    if (!node) return;
    node.textContent = text;
    node.dataset.state = bad ? "error" : "ready";
  }

  function storageKey() {
    const product = window.CompanionProduct;
    const identity = product?.identity?.() || {};
    return "companion-role-profile-migration.v1:" + JSON.stringify([
      identity.installation_id || "", identity.operator_id || "", product?.scopeKey?.() || "",
    ]);
  }

  function persistPending(value) {
    try { sessionStorage.setItem(storageKey(), JSON.stringify(value)); return true; } catch { return false; }
  }

  function readPending() {
    try {
      const value = JSON.parse(sessionStorage.getItem(storageKey()) || "null");
      return value?.body?.plan_token && value?.body?.changes && value?.endpoint ? value : null;
    } catch { return null; }
  }

  function clearPending() {
    try { sessionStorage.removeItem(storageKey()); } catch {}
    state.pending = null;
    state.pendingPersisted = false;
  }

  function unknownResultNotice() {
    const apply = $("[data-role-profile-migration-apply]");
    if (apply) apply.textContent = "核对迁入结果";
    notice(state.pendingPersisted
      ? "迁入结果尚未确认，点击“核对迁入结果”会沿用同一请求。"
      : "迁入结果尚未确认；当前页面仍保留原请求，可以继续核对。若刷新页面后再打开，请重新试算；已迁入的字段会显示为已有内容。", true);
  }

  function apiParts() {
    const product = window.CompanionProduct;
    const role = product?.role?.();
    const bridge = product?.bridgeNow?.() || window.AstrBotPluginPage;
    if (!role?.persona_api || !bridge?.apiGet || !bridge?.apiPost) throw new Error("当前角色没有人格迁入入口。");
    return {product, role, bridge, base: product.relative(role.persona_api)};
  }

  function renderPlan(plan) {
    const output = $("[data-role-profile-migration-output]");
    const counts = plan?.counts || {};
    const list = $("[data-role-profile-migration-fields]");
    const apply = $("[data-role-profile-migration-apply]");
    const entries = Object.entries(plan?.changes || {});
    $("[data-role-profile-migration-counts]").innerHTML =
      '<strong>' + Number(counts.to_import || 0) + '</strong><span>项待迁入</span>' +
      '<strong>' + Number(counts.preserved_existing || 0) + '</strong><span>项已有内容保留</span>' +
      '<strong>' + Number(counts.already_matches || 0) + '</strong><span>项内容相同</span>' +
      (Number(counts.over_limit) ? '<strong>' + Number(counts.over_limit) + '</strong><span>项超出字段长度</span>' : '') +
      (Number(counts.excluded_relationship_sections) ? '<strong>' + Number(counts.excluded_relationship_sections) + '</strong><span>段用户关系已排除</span>' : '');
    list.innerHTML = entries.length ? entries.map(([field, value]) =>
      '<article class="role-profile-migration-field"><strong>' + escapeHTML(labels[field] || field) + '</strong><p>' +
      escapeHTML(value) + '</p></article>').join("") : '<p class="role-profile-migration-empty">没有需要迁入的空白字段。</p>';
    output.hidden = false;
    apply.disabled = !entries.length || state.busy;
    $("[data-role-profile-migration-footer]").textContent = plan?.source?.name
      ? '来源：' + plan.source.name : '';
  }

  async function callApply(pending) {
    if (state.busy || !pending) return;
    const product = window.CompanionProduct;
    state.busy = true;
    const apply = $("[data-role-profile-migration-apply]");
    if (apply) apply.disabled = true;
    try {
      const response = await product.request("POST", pending.endpoint, pending.body);
      const result = response?.result ?? response;
      if (typeof result?.operation_id !== "string" || typeof result?.replayed !== "boolean") {
        unknownResultNotice();
        return;
      }
      clearPending();
      document.dispatchEvent(new Event("companion:role-profile-updated"));
      notice((result.replayed ? "已确认原迁入" : "已迁入") + " " + Number(result.imported_count || 0) + " 项角色档案。");
      state.plan = null;
      $("[data-role-profile-migration-output]").hidden = true;
    } catch (error) {
      if (error?.confirmed === true) {
        clearPending();
        state.plan = null;
        $("[data-role-profile-migration-output]").hidden = true;
        notice(error?.reason || error?.message || "迁入请求已被确认拒绝，请重新试算。", true);
      } else {
        unknownResultNotice();
      }
    } finally {
      state.busy = false;
      if (apply) apply.disabled = state.pending ? false : !state.plan || !Object.keys(state.plan.changes || {}).length;
    }
  }

  async function open() {
    const dialog = $("#roleProfileMigrationDialog");
    if (!dialog || state.busy) return;
    state.plan = null;
    const scopeKey = window.CompanionProduct?.scopeKey?.() || "";
    const memoryPending = state.pending?.scope_key === scopeKey ? state.pending : null;
    state.pending = memoryPending || readPending();
    state.pendingPersisted = memoryPending ? state.pendingPersisted : !!state.pending;
    const initialScope = window.CompanionProduct?.scopeKey?.() || "";
    $("[data-role-profile-migration-output]").hidden = true;
    $("[data-role-profile-migration-apply]").disabled = true;
    if (!dialog.open) dialog.showModal();
    window.lucide?.createIcons({attrs: {"aria-hidden": "true"}});
    if (state.pending) {
      notice("上次迁入结果尚未确认，可以安全核对。", true);
      $("[data-role-profile-migration-footer]").textContent = "沿用原迁入请求";
      const button = $("[data-role-profile-migration-apply]");
      button.textContent = "核对迁入结果";
      button.disabled = false;
      return;
    }
    try {
      const {product, bridge, base} = apiParts();
      notice("正在读取当前人格与角色档案…");
      const current = product.unwrap(await bridge.apiGet(base, {limit: 1}));
      state.personaId = current?.persona?.persona_id || "";
      if (!state.personaId) throw new Error("当前没有可读取的 AstrBot 人格。");
      const plan = product.unwrap(await bridge.apiPost(base + "/profile-migration-plan", {persona_id: state.personaId}));
      if (initialScope !== product.scopeKey?.()) throw new Error("角色已切换，请重新打开迁入窗口。");
      state.plan = plan;
      renderPlan(plan);
      notice("已按明确字段生成迁入计划；用户资料和世界观不参与，现有角色档案不会被覆盖。");
      const button = $("[data-role-profile-migration-apply]");
      button.textContent = "确认迁入空白项";
      button.disabled = !Object.keys(plan.changes || {}).length;
    } catch (error) {
      notice(error?.reason || error?.message || "无法读取当前角色设定。", true);
    }
  }

  async function apply() {
    if (state.pending) { await callApply(state.pending); return; }
    const plan = state.plan;
    if (!plan || !Object.keys(plan.changes || {}).length || state.busy) return;
    const {product, role} = apiParts();
    const endpoint = product.relative(role.persona_api) + "/profile-migration-apply";
    const pending = {scope_key: product.scopeKey?.() || "", endpoint,
      body: {persona_id: state.personaId, plan_token: plan.plan_token,
      edit_token: plan.edit_token, changes: plan.changes}};
    state.pending = pending;
    state.pendingPersisted = persistPending(pending);
    await callApply(pending);
  }

  document.addEventListener("click", event => {
    if (event.target.closest?.("[data-role-profile-migrate-open]")) {
      event.preventDefault(); void open(); return;
    }
    if (event.target.closest?.("[data-role-profile-migration-close]")) {
      event.preventDefault(); $("#roleProfileMigrationDialog")?.close(); return;
    }
    if (event.target.closest?.("[data-role-profile-migration-apply]")) {
      event.preventDefault(); void apply(); return;
    }
    if (event.target.matches?.("#roleProfileMigrationDialog")) $("#roleProfileMigrationDialog")?.close();
  });

  return {markup};
})();
