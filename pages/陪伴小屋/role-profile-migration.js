"use strict";
window.CompanionRoleProfileMigration = (() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
  const labels = window.CompanionConfigEditors?.spec?.role_profile?.labels || {};
  const state = {plan: null, personaId: "", busy: false, pending: null, pendingPersisted: false};

  function markup() {
    return '<dialog class="role-profile-draft-dialog role-profile-migration-dialog" id="roleProfileMigrationDialog" aria-labelledby="roleProfileMigrationTitle" aria-describedby="roleProfileMigrationDescription">' +
      '<div class="role-profile-draft-shell" aria-busy="false"><header class="role-profile-draft-head">' +
      '<div><span>旧版资料 → 角色档案</span><h2 id="roleProfileMigrationTitle">迁入已有设定</h2><p id="roleProfileMigrationDescription">把可识别的旧设定写入当前角色档案；只填空白字段，不覆盖已有内容。</p></div>' +
      '<button class="icon-button" type="button" data-role-profile-migration-close aria-label="关闭" title="关闭"><i data-lucide="x" aria-hidden="true"></i></button></header>' +
      '<section class="role-profile-migration-context" aria-label="迁移范围与策略">' +
      '<div class="role-profile-migration-context-item"><span>来源</span><strong data-role-profile-migration-source>待读取</strong><small data-role-profile-migration-source-kind>旧版 世界知识或当前 AstrBot 人格</small></div>' +
      '<div class="role-profile-migration-context-item"><span>目标</span><strong data-role-profile-migration-target>当前角色档案</strong><small>与当前私聊角色绑定</small></div>' +
      '<div class="role-profile-migration-context-item is-policy"><span>写入策略</span><strong>只填空白项</strong><small>已有内容保持不变</small></div></section>' +
      '<p class="role-profile-migration-notice" data-role-profile-migration-notice role="status" aria-live="polite">读取旧版世界知识中的角色设定；没有可用来源时读取当前 AstrBot 人格。</p>' +
      '<section class="role-profile-migration-output" data-role-profile-migration-output hidden aria-live="polite">' +
      '<div class="role-profile-migration-output-head"><div><span>迁入预览</span><h3>写入前核对</h3></div><strong data-role-profile-migration-summary>—</strong></div>' +
      '<div class="role-profile-migration-source" data-role-profile-migration-source-panel><span class="role-profile-migration-source-mark" aria-hidden="true"><i data-lucide="file-input"></i></span><div><strong data-role-profile-migration-source-detail>来源待读取</strong><small data-role-profile-migration-source-meta>只展示安全可识别的角色字段</small></div></div>' +
      '<div class="role-profile-migration-counts" data-role-profile-migration-counts></div>' +
      '<div class="role-profile-migration-fields-head"><div><span>待写入字段</span><small>确认后只会写入当前为空的字段</small></div></div>' +
      '<div class="role-profile-migration-fields" data-role-profile-migration-fields></div>' +
      '<p class="role-profile-migration-exclusions" data-role-profile-migration-exclusions hidden></p></section>' +
      '<footer class="role-profile-draft-actions"><span data-role-profile-migration-footer></span><div>' +
      '<button class="button small" type="button" data-role-profile-migration-close>取消</button>' +
      '<button class="button small primary" type="button" data-role-profile-migration-apply disabled>确认迁入空白项</button></div></footer></div></dialog>';
  }

  function notice(text, stateName = "ready") {
    const node = $("[data-role-profile-migration-notice]");
    if (!node) return;
    if (typeof stateName === "boolean") stateName = stateName ? "error" : "ready";
    node.textContent = text;
    node.dataset.state = stateName;
  }

  function setText(selector, text) {
    const node = $(selector);
    if (node) node.textContent = text;
    return node;
  }

  function refreshIcons() {
    window.lucide?.createIcons?.({attrs: {"aria-hidden": "true"}});
  }

  function setBusy(value) {
    state.busy = value;
    const shell = $(".role-profile-migration-dialog .role-profile-draft-shell");
    const apply = $("[data-role-profile-migration-apply]");
    if (shell?.setAttribute) shell.setAttribute("aria-busy", value ? "true" : "false");
    if (value && apply) {
      apply.disabled = true;
      apply.textContent = "正在处理…";
    }
    if (apply?.setAttribute) apply.setAttribute("aria-busy", value ? "true" : "false");
  }

  function formatCount(value) {
    const count = Number(value || 0);
    return Number.isFinite(count) && count >= 0 ? String(Math.floor(count)) : "0";
  }

  function formatChars(value) {
    const count = Number(value || 0);
    if (!Number.isFinite(count) || count <= 0) return "字符数未提供";
    return new Intl.NumberFormat("zh-CN").format(Math.floor(count)) + " 字符";
  }

  function sourceKindLabel(kind) {
    return kind === "v1_world_knowledge" ? "旧版世界知识" : kind === "astrbot_persona" ? "AstrBot 人格" : "角色设定来源";
  }

  function resetContext() {
    setText("[data-role-profile-migration-source]", "待读取");
    setText("[data-role-profile-migration-source-kind]", "旧版世界知识或当前 AstrBot 人格");
    setText("[data-role-profile-migration-target]", "当前角色档案");
    setText("[data-role-profile-migration-source-detail]", "来源待读取");
    setText("[data-role-profile-migration-source-meta]", "只展示安全可识别的角色字段");
    setText("[data-role-profile-migration-summary]", "—");
    setText("[data-role-profile-migration-footer]", "只填空白项 · 已有内容不会被覆盖");
    const exclusions = $("[data-role-profile-migration-exclusions]");
    if (exclusions) { exclusions.hidden = true; exclusions.textContent = ""; }
  }

  function renderSource(plan) {
    const source = plan?.source || {};
    const name = source.name || sourceKindLabel(source.kind);
    const kind = sourceKindLabel(source.kind);
    setText("[data-role-profile-migration-source]", name);
    setText("[data-role-profile-migration-source-kind]", kind + " · " + formatChars(source.source_chars));
    setText("[data-role-profile-migration-source-detail]", name);
    setText("[data-role-profile-migration-source-meta]", kind + " · 角色区块 " + formatChars(source.block_chars));
  }

  function renderExclusions(plan) {
    const node = $("[data-role-profile-migration-exclusions]");
    if (!node) return;
    const counts = plan?.counts || {};
    const notes = [];
    if (Number(counts.over_limit || 0)) notes.push(formatCount(counts.over_limit) + " 项超过字段长度，已排除");
    if (Number(counts.excluded_relationship_sections || 0)) notes.push(formatCount(counts.excluded_relationship_sections) + " 段用户关系内容未迁入");
    node.hidden = !notes.length;
    node.textContent = notes.length ? "已排除：" + notes.join("；") + "。" : "";
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
      : "迁入结果尚未确认；当前页面仍保留原请求，可以继续核对。若刷新页面后再打开，请重新试算；已迁入的字段会显示为已有内容。", "error");
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
    const stats = [
      ["待迁入", counts.to_import, "primary", "确认后写入"],
      ["已有内容", counts.preserved_existing, "muted", "保持不变"],
      ["内容相同", counts.already_matches, "ok", "无需重复写入"],
      ["超出长度", counts.over_limit, "warn", "已排除"],
      ["关系段排除", counts.excluded_relationship_sections, "warn", "不属于角色档案"],
    ];
    const countsNode = $("[data-role-profile-migration-counts]");
    if (countsNode) countsNode.innerHTML = stats.map(([label, value, tone, help]) =>
      '<div class="role-profile-migration-stat is-' + tone + '"><strong>' + formatCount(value) + '</strong><span>' + label + '</span><small>' + help + '</small></div>').join("");
    if (list) list.innerHTML = entries.length ? entries.map(([field, value]) =>
      '<article class="role-profile-migration-field"><div class="role-profile-migration-field-head"><span>角色字段</span><strong>' + escapeHTML(labels[field] || field) + '</strong><em>待写入</em></div><p>' +
      escapeHTML(value) + '</p><small>仅在该字段为空时写入</small></article>').join("") : '<p class="role-profile-migration-empty">没有需要迁入的空白字段；已有内容已保留。</p>';
    renderSource(plan);
    renderExclusions(plan);
    setText("[data-role-profile-migration-summary]", entries.length ? formatCount(entries.length) + " 项待写入" : "无需写入");
    setText("[data-role-profile-migration-footer]", entries.length
      ? "只填空白项 · 已有内容不会被覆盖"
      : "没有空白项可写入 · 已有内容不会被覆盖");
    if (output) output.hidden = false;
    if (apply) {
      apply.disabled = !entries.length || state.busy;
      apply.textContent = "确认迁入空白项";
    }
    refreshIcons();
  }

  async function callApply(pending) {
    if (state.busy || !pending) return;
    const product = window.CompanionProduct;
    setBusy(true);
    const apply = $("[data-role-profile-migration-apply]");
    try {
      notice("正在确认迁入请求；页面不会重复提交同一操作…", "loading");
      const response = await product.request("POST", pending.endpoint, pending.body);
      const result = response?.result ?? response;
      if (typeof result?.operation_id !== "string" || typeof result?.replayed !== "boolean") {
        unknownResultNotice();
        return;
      }
      clearPending();
      document.dispatchEvent(new Event("companion:role-profile-updated"));
      notice((result.replayed ? "已确认原迁入" : "已迁入") + " " + formatCount(result.imported_count) + " 项角色档案。", "success");
      state.plan = null;
      setText("[data-role-profile-migration-summary]", "迁入完成");
      setText("[data-role-profile-migration-footer]", "已写入 " + formatCount(result.imported_count) + " 项 · 现有内容未覆盖");
      if (apply) apply.textContent = "已完成";
    } catch (error) {
      if (error?.confirmed === true) {
        clearPending();
        state.plan = null;
        $("[data-role-profile-migration-output]").hidden = true;
        notice(error?.reason || error?.message || "迁入请求已被确认拒绝，请重新试算。", "error");
      } else {
        unknownResultNotice();
      }
    } finally {
      state.busy = false;
      if (apply) {
        apply.disabled = state.pending ? false : !state.plan || !Object.keys(state.plan.changes || {}).length;
        if (apply.setAttribute) apply.setAttribute("aria-busy", "false");
      }
      const shell = $(".role-profile-migration-dialog .role-profile-draft-shell");
      if (shell?.setAttribute) shell.setAttribute("aria-busy", "false");
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
    const output = $("[data-role-profile-migration-output]");
    const apply = $("[data-role-profile-migration-apply]");
    if (output) output.hidden = true;
    if (apply) { apply.disabled = true; apply.textContent = "确认迁入空白项"; }
    resetContext();
    if (!dialog.open) dialog.showModal();
    refreshIcons();
    if (state.pending) {
      setText("[data-role-profile-migration-source]", "上次未确认的请求");
      setText("[data-role-profile-migration-source-kind]", "沿用原请求 · 不会新建迁入");
      setText("[data-role-profile-migration-source-detail]", "原迁入请求仍在等待确认");
      setText("[data-role-profile-migration-source-meta]", "核对结果后才会清除待确认记录");
      setText("[data-role-profile-migration-summary]", "待核对");
      notice("上次迁入结果尚未确认，可以安全核对。", "error");
      setText("[data-role-profile-migration-footer]", "沿用原迁入请求");
      if (apply) { apply.textContent = "核对迁入结果"; apply.disabled = false; }
      return;
    }
    setBusy(true);
    try {
      const {product, bridge, base} = apiParts();
      notice("正在读取当前人格与角色档案…", "loading");
      const current = product.unwrap(await bridge.apiGet(base, {limit: 1}));
      state.personaId = current?.persona?.persona_id || "";
      if (!state.personaId) throw new Error("当前没有可读取的 AstrBot 人格。");
      const plan = product.unwrap(await bridge.apiPost(base + "/profile-migration-plan", {persona_id: state.personaId}));
      if (initialScope !== product.scopeKey?.()) throw new Error("角色已切换，请重新打开迁入窗口。");
      state.plan = plan;
      renderPlan(plan);
      const changeCount = Object.keys(plan.changes || {}).length;
      notice(changeCount
        ? "已生成迁入预览；用户资料和世界观不参与，现有角色档案不会被覆盖。"
        : "当前没有可迁入的空白字段；用户资料和世界观不参与，现有角色档案保持不变。", "ready");
    } catch (error) {
      state.plan = null;
      if (output) output.hidden = true;
      if (apply) apply.textContent = "确认迁入空白项";
      notice(error?.reason || error?.message || "无法读取当前角色设定。", "error");
    } finally {
      state.busy = false;
      if (apply) {
        apply.disabled = !state.plan || !Object.keys(state.plan.changes || {}).length;
        if (apply.setAttribute) apply.setAttribute("aria-busy", "false");
      }
      const shell = $(".role-profile-migration-dialog .role-profile-draft-shell");
      if (shell?.setAttribute) shell.setAttribute("aria-busy", "false");
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
