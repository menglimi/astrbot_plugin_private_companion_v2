/* One-time V2 setup. Progress is owned by the host and survives page and plugin reloads. */
"use strict";
window.CompanionSetup = (() => {
  const PREFIX = "setup";
  const ORDER = ["mode", "binding", "model", "knowledge", "relationships", "proactive_test"];
  const LABELS = {
    mode: "运行模式", binding: "核心管理员窗口",
    model: "插件模型", knowledge: "世界知识", relationships: "关系教学", proactive_test: "主动消息测试",
  };
  const $ = (selector, root = document) => root.querySelector(selector);
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c =>
    ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
  const product = () => window.CompanionProduct;
  const api = (method, path, body) => product().request(method, PREFIX + path, body);
  let root = null;
  let state = null;
  let busy = false;
  let notice = "";
  let modeDraft = {accounts: "single", personas: "single"};
  let modelDraft = "";
  let legacyTargetId = "";
  let legacyRoleId = "";
  let legacyApi = "";
  let legacyFinding = null;
  let legacyPlan = null;
  let legacyResult = null;
  let legacyError = "";
  let generation = 0;

  function modeLabel(mode) {
    if (!mode) return "尚未选择";
    return `${mode.accounts === "multiple" ? "多账号" : "单账号"} · ${mode.personas === "multiple" ? "多人格" : "单人格"}`;
  }

  function progress() {
    const done = new Set(state?.completed || []);
    const skipped = new Set(state?.skipped || []);
    const bindingDone = Boolean(state?.binding_confirmed);
    const prepared = Boolean(state?.prepared);
    return ORDER.map(id => {
      const complete = id === "mode" ? Boolean(state?.mode && !state?.mode_requires_reload)
        : id === "binding" ? bindingDone
        : id === "proactive_test" ? Boolean(state?.ready)
        : done.has(id) || skipped.has(id);
      return {id, label: LABELS[id], complete};
    });
  }

  function stepIndex(step) {
    const index = ORDER.indexOf(step);
    return index < 0 ? 0 : index;
  }

  function renderRail(step) {
    return `<ol class="setup-progress" aria-label="首次连接进度">${progress().map((item, index) => `
      <li class="${item.complete ? "complete" : ""} ${item.id === step ? "current" : ""}">
        <span class="setup-progress-marker">${item.complete ? "✓" : String(index + 1).padStart(2, "0")}</span>
        <span>${escape(item.label)}</span>
      </li>`).join("")}</ol>`;
  }

  function noticeMarkup() {
    if (!notice) return "";
    return `<p class="setup-notice" role="status">${escape(notice)}</p>`;
  }

  function connectionDiagnostic() {
    const failure = state?.host?.last_failure;
    if (!failure || typeof failure.reason !== "string") return "";
    const supported = new Set(["staging_profile_conflict", "host_binding_changed"]);
    if (!supported.has(failure.code)) return "";
    const detail = Array.isArray(failure.details) && failure.details.length
      ? `（${failure.details.map(item => String(item)).join("、")}）` : "";
    return `<p class="setup-inline-error" role="alert">${escape(failure.reason)}${escape(detail)}</p>`;
  }

  function button(action, label, {primary = false, disabled = false} = {}) {
    return `<button type="button" class="button${primary ? " primary" : ""}" data-setup-action="${escape(action)}" ${disabled || busy ? "disabled" : ""}>${escape(label)}</button>`;
  }

  function workspaceButton(label, tab, subtab = "") {
    const path = subtab ? ` data-manage-subtab="${escape(subtab)}"` : "";
    return `<button type="button" class="button" data-go="manage" data-manage="${escape(tab)}"${path}>${escape(label)}</button>`;
  }

  function homeButton(label, primary = false) {
    return `<button type="button" class="button${primary ? " primary" : ""}" data-go="life">${escape(label)}</button>`;
  }

  const isMulti = () => product()?.targetsMode?.() === "multi";

  function legacyChoices() {
    const multi = isMulti();
    const targets = multi ? (product()?.targets?.() || []).filter(target =>
      (target.roles || []).some(role => role.legacy_api)) : [];
    const target = targets.find(item => item.target_id === legacyTargetId) || null;
    const roles = target?.roles?.filter(role => role.legacy_api) || [];
    const role = roles.find(item => item.role_id === legacyRoleId) || null;
    return {multi, targets, target, roles, role};
  }

  function legacyAddress() {
    if (!isMulti()) return "legacy";
    const role = legacyChoices().role;
    return role?.legacy_api ? product().relative(role.legacy_api) : "";
  }

  function legacySelection() {
    const choices = legacyChoices();
    return {...choices, api: legacyAddress()};
  }

  function legacyScopeStatus(plan = legacyPlan) {
    return Array.isArray(plan?.scope_status) ? plan.scope_status : [];
  }

  function legacyScopePanel() {
    const choices = legacyChoices();
    return `<section class="setup-stage setup-legacy setup-legacy-scope-only">
      <p class="setup-kicker">V1 DATA</p><h3>选择迁移目标</h3>
      <p>多目标模式下，先选择要写入的 V2 目标与人格。侦察只读 V1；执行只写入选中的 V2 作用域。</p>
      <div class="setup-legacy-scope">
        <label><span>V2 目标</span><select data-setup-legacy="target"><option value="">选择目标</option>${choices.targets.map(item => `<option value="${escape(item.target_id)}" ${legacyTargetId === item.target_id ? "selected" : ""}>${escape(item.target_id)} · ${escape(item.bot_id || "Bot")}</option>`).join("")}</select></label>
        <label><span>V2 人格</span><select data-setup-legacy="role" ${legacyTargetId ? "" : "disabled"}><option value="">选择人格</option>${choices.roles.map(item => `<option value="${escape(item.role_id)}" ${legacyRoleId === item.role_id ? "selected" : ""}>${escape(item.persona_ids?.join(" / ") || item.role_id)}</option>`).join("")}</select></label>
      </div>
    </section>`;
  }

  function legacyButton(action, label, {primary = false, disabled = false} = {}) {
    return `<button type="button" class="button${primary ? " primary" : ""}" data-setup-legacy-action="${escape(action)}" ${disabled || busy ? "disabled" : ""}>${escape(label)}</button>`;
  }

  function legacyPanel() {
    const selection = legacySelection();
    const legacyScope = selection.role;
    if (isMulti() && !legacyScope) return legacyScopePanel();
    const multi = selection.multi;
    const targets = selection.targets;
    const roles = selection.roles;
    const statuses = {ready: "可转换", absent: "未发现", no_handler: "暂缺转换器", read_only: "只读保留",
      external: "由其他插件负责", held: "归属待确认", unreadable: "存在但不可读取"};
    const findings = legacyFinding?.findings || legacyPlan?.findings || [];
    const planScopes = legacyScopeStatus();
    const blocked = planScopes.some(item => !item.available);
    const canApply = Boolean(legacyPlan?.plan_token && legacyPlan.change_count > 0 && !blocked);
    return `<section class="setup-stage setup-legacy">
      <p class="setup-kicker">V1 DATA</p><h3>V1 配置迁移</h3>
      <p>连接完成后可以单独检查 V1 来源。侦察只读 V1；执行只写入当前 V2 目标，不会删除或改写 V1。</p>
      ${multi ? `<div class="setup-legacy-scope">
        <label><span>V2 目标</span><select data-setup-legacy="target"><option value="">选择目标</option>${targets.map(item => `<option value="${escape(item.target_id)}" ${legacyTargetId === item.target_id ? "selected" : ""}>${escape(item.target_id)} · ${escape(item.bot_id || "Bot")}</option>`).join("")}</select></label>
        <label><span>V2 人格</span><select data-setup-legacy="role" ${legacyTargetId ? "" : "disabled"}><option value="">选择人格</option>${roles.map(item => `<option value="${escape(item.role_id)}" ${legacyRoleId === item.role_id ? "selected" : ""}>${escape(item.persona_ids?.join(" / ") || item.role_id)}</option>`).join("")}</select></label>
      </div><p class="setup-legacy-scope-note">迁移结果会写入选中的目标与人格。</p>` : ""}
      ${legacyError ? `<p class="setup-inline-error">${escape(legacyError)}</p>` : ""}
      ${legacyResult ? `<p class="setup-recorded">已写入 ${Number(legacyResult.written_count) || 0} 项 V2 设置。V1 文件保持不变。</p>` : ""}
      ${legacyFinding || legacyPlan ? `<p class="setup-legacy-root">V1 位置：${escape(legacyFinding?.v1_root || legacyPlan?.v1_root || "")}</p>
        <ul class="setup-legacy-findings">${findings.map(item => `<li><strong>${escape(item.source_id)}</strong><span>${escape(statuses[item.state] || item.state)}</span><small>${escape(item.detail || item.owner || "")}</small></li>`).join("")}</ul>` : ""}
      ${legacyPlan ? `<div class="setup-legacy-plan"><p>试算将写入 ${Number(legacyPlan.change_count) || 0} 项设置。</p>
        ${(legacyPlan.warnings || []).map(item => `<p>${escape(item)}</p>`).join("")}
        ${(legacyPlan.differences || []).map(item => `<p>${escape(item.field)}：${escape(item.before)} → ${escape(item.after)}。${escape(item.explain || "")}</p>`).join("")}
        ${blocked ? `<p class="setup-inline-error">有作用域暂不可写：${escape(planScopes.filter(item => !item.available).map(item => item.scope).join("、"))}</p>` : ""}
      </div>` : ""}
      ${noticeMarkup()}
      <div class="setup-actions">
        ${multi ? legacyButton("legacy-choose", "检查所选目标", {primary: true, disabled: !selection.api})
          : legacyButton("legacy-scan", legacyFinding ? "重新检查 V1" : "检查 V1 配置", {primary: true})}
        ${legacyFinding && !legacyPlan ? legacyButton("legacy-plan", "试算迁移") : ""}
        ${legacyPlan && !legacyResult && legacyPlan.change_count > 0 ? legacyButton("legacy-apply", "写入 V2", {primary: true, disabled: !canApply}) : ""}
      </div>
    </section>`;
  }

  function modeOption(group, value, title, description) {
    const selected = modeDraft[group] === value;
    return `<label class="setup-mode-option ${selected ? "selected" : ""}">
      <input type="radio" name="setup-${group}" value="${value}" ${selected ? "checked" : ""} ${busy ? "disabled" : ""}>
      <span class="setup-mode-option-copy"><strong>${title}</strong><small>${description}</small></span>
    </label>`;
  }

  function renderMode() {
    if (state?.mode && state.mode_requires_reload) {
      return `<section class="setup-stage">
        <p class="setup-kicker">STEP 1</p><h3>运行规模已保存</h3>
        <p>已保存为 <strong>${escape(modeLabel(state.mode))}</strong>。请在 AstrBot 插件管理中重载 V2，应用后会直接进入核心管理员窗口绑定。</p>
        ${noticeMarkup()}
        <div class="setup-actions">${button("refresh", "我已重载，继续", {primary: true})}</div>
      </section>`;
    }
    return `<section class="setup-stage">
      <p class="setup-kicker">STEP 1</p><h3>选择运行规模</h3>
      <p>先决定 V2 管理几个 OneBot 账号，以及这些账号使用几种 AstrBot 人格。多账号或多人格模式共用一个 V2 安装数据根。</p>
      <fieldset class="setup-mode-group"><legend>账号</legend><div class="setup-mode-options">
        ${modeOption("accounts", "single", "单账号", "一个 Bot 登录账号")}
        ${modeOption("accounts", "multiple", "多账号", "多个 Bot 登录账号")}
      </div></fieldset>
      <fieldset class="setup-mode-group"><legend>人格</legend><div class="setup-mode-options">
        ${modeOption("personas", "single", "单人格", "一个主要 AstrBot 人格")}
        ${modeOption("personas", "multiple", "多人格", "为不同角色配置独立人格")}
      </div></fieldset>
      <p class="setup-current-mode">当前选择：<strong>${escape(modeLabel(state?.mode))}</strong></p>
      ${connectionDiagnostic()}
      ${noticeMarkup()}
      <div class="setup-actions">${button("save-mode", "保存运行模式", {primary: true})}</div>
    </section>`;
  }

  function bindingFacts(binding) {
    if (!binding || !binding.participant_id) return "";
    return `<dl class="setup-facts">
      <div><dt>平台</dt><dd>${escape(binding.platform_id || "未知")}</dd></div>
      <div><dt>Bot 账号</dt><dd>${escape(binding.account_id || "未知")}</dd></div>
      <div><dt>私聊对象</dt><dd>${escape(binding.participant_id || "未知")}</dd></div>
      <div><dt>AstrBot 人格</dt><dd>${escape(binding.persona_id || "跟随当前会话")}</dd></div>
    </dl>`;
  }

  function renderBinding() {
    const binding = state?.binding || {};
    const command = state?.mode?.personas === "multiple" ? "companion_bind <AstrBot 人格名>" : "companion_bind";
    if (binding.pending) {
      return `<section class="setup-stage">
        <p class="setup-kicker">STEP 2</p><h3>核对核心管理员窗口</h3>
        <p>已收到这条私聊里的绑定指令。核对它是你希望 V2 接收管理员指令、也作为主动消息主要投递窗口的私聊。</p>
        <p class="setup-command"><code>${escape(command)}</code></p>
        ${connectionDiagnostic()}
        ${bindingFacts(binding)}
        <p class="setup-confirm-copy">候选绑定仅保存在 V2 数据根，不会触发聊天回复。平台、Bot 账号、私聊对象和人格均正确后，点击确认。</p>
        ${noticeMarkup()}
        <div class="setup-actions">${button("confirm-binding", "确认此窗口", {primary: true})}${button("refresh", "重新读取")}</div>
      </section>`;
    }
    if (state?.binding_confirmed) {
      return `<section class="setup-stage">
        <p class="setup-kicker">STEP 2</p><h3>核心管理员窗口已绑定</h3>
        ${bindingFacts(binding)}
        <p>这个私聊窗口用于管理员控制，也是主动消息测试的目标。下一步配置模型后，V2 才会建立运行实例。</p>
        ${noticeMarkup()}
        <div class="setup-actions">${button("refresh", "继续配置模型", {primary: true})}</div>
      </section>`;
    }
    return `<section class="setup-stage">
      <p class="setup-kicker">STEP 2</p><h3>绑定核心管理员窗口</h3>
      <p>在希望 V2 接收管理员指令、也作为主动消息主要投递窗口的私聊中，发送固定指令：</p>
      <p class="setup-command"><code>${escape(command)}</code></p>
      <p>回到这里核对平台、Bot 账号、私聊对象和人格，再由 Dashboard 管理员确认。首次确认会登记这个核心管理员窗口；若选择多人格，请填写 AstrBot 中的准确人格名。</p>
      ${connectionDiagnostic()}
      ${state?.settings_error ? `<p class="setup-inline-error">${escape(state.settings_error)}</p>` : ""}
      ${noticeMarkup()}
      <div class="setup-actions">${button("refresh", "我已发送，检查绑定", {primary: true})}</div>
    </section>`;
  }

  function renderSection(step) {
    const definitions = {
      knowledge: {number: "STEP 4", title: "填写世界知识", copy: "进入知识库与世界书，补充角色世界观，或选择现有知识来源。", tab: "knowledge", open: "打开世界知识", canSkip: true},
      relationships: {number: "STEP 5", title: "教学关系网", copy: "进入关系与权限，补充核心管理员与其他重要对象的称呼、身份和关系。", tab: "identity", open: "打开关系设置", canSkip: true},
    }[step];
    const complete = state?.completed?.includes(step);
    const skipped = state?.skipped?.includes(step);
    return `<section class="setup-stage">
      <p class="setup-kicker">${definitions.number}</p><h3>${definitions.title}</h3>
      <p>${definitions.copy}</p>
      ${complete || skipped ? `<p class="setup-recorded">${skipped ? "已选择暂时跳过" : "已标记完成"}</p>` : ""}
      ${noticeMarkup()}
      <div class="setup-actions">
        ${workspaceButton(definitions.open, definitions.tab)}
        ${button("complete-step", complete ? "重新确认完成" : skipped ? "改为已完成" : "已完成这部分", {primary: true})}
        ${definitions.canSkip ? button("skip-step", "暂时跳过") : ""}
      </div>
    </section>`;
  }

  function renderModel() {
    const model = state?.model || {};
    const providers = Array.isArray(model.providers) ? model.providers : [];
    const providerId = modelDraft || model.provider_id || "";
    return `<section class="setup-stage">
      <p class="setup-kicker">STEP 3</p><h3>配置插件模型</h3>
      <p>选择 AstrBot 已加载且 V2 可适配的文本 Provider。保存后会初始化 V2 运行实例；之后可在模型与连接中细调各任务路由。</p>
      ${connectionDiagnostic()}
      ${providers.length ? `<label class="setup-model-field"><span>主文本 Provider</span>
        <select name="setup-provider" ${busy ? "disabled" : ""}>
          <option value="">选择 Provider</option>
          ${providers.map(item => `<option value="${escape(item.id)}" ${providerId === item.id ? "selected" : ""}>${escape(item.name)} · ${escape(item.id)}</option>`).join("")}
        </select></label>` : `<p class="setup-inline-error">AstrBot 当前没有已加载的文本 Provider。请先在 AstrBot 的提供方管理中加载模型，再回来刷新。</p>`}
      ${state?.settings_error ? `<p class="setup-inline-error">${escape(state.settings_error)}</p>` : ""}
      ${noticeMarkup()}
      <div class="setup-actions">${button("save-model", "保存模型并继续", {primary: true, disabled: !providers.length || !providerId})}${providers.length ? button("refresh", "刷新 Provider") : ""}</div>
    </section>`;
  }

  function renderProactiveTest() {
    const test = state?.proactive_test;
    if (state?.ready) {
      const accepting = Boolean(state?.host?.accepting);
      return `<section class="setup-stage setup-finished">
        <p class="setup-kicker">首次连接</p><h3>首次设置已完成</h3>
        <p>运行模式、核心管理员窗口、模型与初始资料已记录。之后直接使用陪伴小屋和聊天窗口，不需要重新走向导。</p>
        <p class="setup-test-receipt setup-connection-state ${accepting ? "" : "is-stopped"}">${accepting ? "V2 正在接收消息" : "首次设置已保留，当前运行实例尚未接收消息"}</p>
        <p class="setup-test-receipt">${escape(test?.finished_at || "测试已送达")}</p>
        <div class="setup-actions">${accepting ? "" : button("reconnect-host", "重新连接", {primary: true})}${homeButton("进入陪伴小屋", !accepting)}${workspaceButton("模型与连接", "models")}${workspaceButton("账号与会话", "host")}</div>
      </section>
      <details class="setup-legacy-disclosure"><summary>V1 配置迁移（可选）</summary>${legacyPanel()}</details>`;
    }
    if (test?.state === "started" || test?.state === "unknown") {
      return `<section class="setup-stage">
        <p class="setup-kicker">STEP 6</p><h3>主动测试结果未知</h3>
        <p>平台没有返回可确认的送达确认。为避免重复发送，这次测试不会自动重放，也不能再次触发。请到目标私聊检查是否收到测试消息。</p>
        <p class="setup-test-receipt">${test?.state === "started" ? "等待平台确认" : "结果未知"}</p>
        ${noticeMarkup()}
        <div class="setup-actions">${button("refresh", "重新读取确认", {primary: true})}</div>
      </section>`;
    }
    return `<section class="setup-stage">
      <p class="setup-kicker">STEP 6</p><h3>测试主动消息</h3>
      <p>只有点击下方按钮后，V2 才会向已确认的核心管理员私聊发送一条固定测试消息。这一步不调用模型；测试结果未知时不会重发。</p>
      ${noticeMarkup()}
      <div class="setup-actions">${button("proactive-test", "发送一次测试消息", {primary: true})}</div>
    </section>`;
  }

  function renderUnavailable() {
    return `<section class="setup-stage">
      <p class="setup-kicker">连接状态</p><h3>暂时读不到设置进度</h3>
      <p>${escape(notice || "Dashboard 与 V2 管理接口暂时没有连通。")}</p>
      <div class="setup-actions">${button("refresh", "重新读取", {primary: true})}</div>
    </section>`;
  }

  function render() {
    if (!root) return;
    if (!state) {
      root.innerHTML = `<div class="setup-shell"><p class="setup-loading">正在读取 V2 设置进度…</p>${renderUnavailable()}</div>`;
      return;
    }
    if (state.ready) {
      root.innerHTML = `<div class="setup-shell setup-complete-shell"><header class="setup-header"><div><span class="setup-kicker">我会永远陪着你 V2.0</span><h2>首次连接</h2></div><span class="setup-mode-badge">${escape(modeLabel(state.mode))}</span></header>${renderProactiveTest()}</div>`;
      return;
    }
    const step = state.step || "mode";
    modeDraft = state.mode ? {...state.mode} : modeDraft;
    const content = step === "mode" ? renderMode()
      : step === "binding" ? renderBinding()
      : step === "model" ? renderModel()
      : step === "proactive_test" ? renderProactiveTest()
      : renderSection(step);
    const current = stepIndex(step);
    root.innerHTML = `<div class="setup-shell">
      <header class="setup-header"><div><span class="setup-kicker">我会永远陪着你 V2.0</span><h2>首次连接</h2></div>
        <span class="setup-step-count">${String(current + 1).padStart(2, "0")} / ${String(ORDER.length).padStart(2, "0")}</span></header>
      ${renderRail(step)}<div class="setup-content">${content}</div>
    </div>`;
  }

  async function refresh() {
    const ticket = ++generation;
    try {
      const result = await api("GET", "/status");
      if (ticket !== generation) return;
      state = result;
      modelDraft = result?.model?.provider_id || "";
      notice = "";
      render();
    } catch (error) {
      if (ticket !== generation) return;
      state = null;
      notice = error?.message || "V2 管理接口暂时没有连通。";
      render();
    }
  }

  async function runLegacy(action) {
    legacyError = "";
    if (action === "legacy-scan") {
      if (!legacyAddress()) throw new Error("先选择有迁移接口的 V2 目标与人格。");
      legacyApi = legacyAddress();
      legacyFinding = await product().request("GET", legacyApi);
      legacyPlan = null;
      legacyResult = null;
    } else if (action === "legacy-plan") {
      if (!legacyAddress()) throw new Error("先选择有迁移接口的 V2 目标与人格。");
      legacyApi = legacyAddress();
      if (!legacyApi || !legacyFinding) throw new Error("先检查 V1 来源，再试算迁移。");
      legacyPlan = await product().request("GET", legacyApi + "/plan");
      legacyResult = null;
    } else if (action === "legacy-apply") {
      if (!legacyAddress()) throw new Error("先选择有迁移接口的 V2 目标与人格。");
      legacyApi = legacyAddress();
      if (!legacyApi || !legacyPlan?.plan_token) throw new Error("先完成迁移试算，再执行写入。");
      legacyResult = await product().request("POST", legacyApi + "/apply", {plan_token: legacyPlan.plan_token});
      legacyFinding = null;
      legacyPlan = null;
    } else if (action === "legacy-choose") {
      if (!legacyAddress()) throw new Error("先选择有迁移接口的 V2 目标与人格。");
      legacyApi = legacyAddress();
      legacyFinding = await product().request("GET", legacyApi);
      legacyPlan = null;
      legacyResult = null;
    }
  }

  async function act(action) {
    if (busy) return;
    busy = true;
    notice = "";
    render();
    try {
      if (action === "save-mode") {
        const result = await api("POST", "/mode", modeDraft);
        notice = result.mode_requires_reload ? "运行模式已保存，需要重载插件后才能继续。" : "运行模式已保存。";
      } else if (action === "confirm-binding") {
        await api("POST", "/binding/confirm", {});
      } else if (action === "prepare") {
        await api("POST", "/prepare", {});
      } else if (action === "save-model") {
        await api("POST", "/model", {provider_id: modelDraft});
        notice = "模型已保存，V2 运行实例已准备。";
      } else if (action === "complete-step" || action === "skip-step") {
        await api("POST", "/complete", {step: state.step, skipped: action === "skip-step"});
      } else if (action === "proactive-test") {
        const result = await api("POST", "/proactive-test", {});
        notice = result.state === "delivered" ? "测试消息已收到平台送达确认。"
          : "平台没有返回可确认的送达确认，本次不会重发。请检查核心管理员私聊。";
      } else if (action === "reconnect-host") {
        await api("POST", "/host/start", {});
        notice = "V2 已重新连接并开始接收消息。";
      } else if (["legacy-scan", "legacy-choose", "legacy-plan", "legacy-apply"].includes(action)) {
        await runLegacy(action);
      }
      if (action === "refresh") {
        await refresh();
      } else {
        const result = await api("GET", "/status");
        state = result;
        modelDraft = result?.model?.provider_id || "";
        if (result.ready) notice = "";
        render();
      }
    } catch (error) {
      if (action.startsWith("legacy-")) {
        legacyError = error?.message || "V1 配置处理未完成，请核对当前 V2 目标后重试。";
        if (action === "legacy-apply") legacyPlan = null;
      }
      notice = error?.message || "操作未完成，请重新读取状态。";
      try { state = await api("GET", "/status"); } catch { state = null; }
      render();
    } finally {
      busy = false;
      if (root) render();
    }
  }

  function onClick(event) {
    const legacyAction = event.target.closest?.("[data-setup-legacy-action]")?.dataset.setupLegacyAction;
    if (legacyAction) { act(legacyAction); return; }
    const action = event.target.closest?.("[data-setup-action]")?.dataset.setupAction;
    if (action) act(action);
  }

  function onChange(event) {
    const input = event.target;
    if (input?.dataset?.setupLegacy === "target") {
      legacyTargetId = input.value;
      legacyRoleId = "";
      legacyApi = "";
      legacyFinding = legacyPlan = legacyResult = null;
      legacyError = "";
      render();
    }
    if (input?.dataset?.setupLegacy === "role") {
      legacyRoleId = input.value;
      legacyApi = "";
      legacyFinding = legacyPlan = legacyResult = null;
      legacyError = "";
      render();
    }
    if (input?.name === "setup-accounts" && ["single", "multiple"].includes(input.value)) {
      modeDraft.accounts = input.value;
      render();
    }
    if (input?.name === "setup-personas" && ["single", "multiple"].includes(input.value)) {
      modeDraft.personas = input.value;
      render();
    }
    if (input?.name === "setup-provider") {
      modelDraft = input.value;
      render();
    }
  }

  function mount(node) {
    unmount();
    root = node;
    root.addEventListener("click", onClick);
    root.addEventListener("change", onChange);
    state = null;
    notice = "";
    modeDraft = {accounts: "single", personas: "single"};
    modelDraft = "";
    legacyTargetId = legacyRoleId = legacyApi = "";
    legacyFinding = legacyPlan = legacyResult = null;
    legacyError = "";
    render();
    refresh();
  }

  function unmount() {
    generation++;
    if (root) {
      root.removeEventListener("click", onClick);
      root.removeEventListener("change", onChange);
    }
    root = null;
  }

  return {mount, unmount, refresh};
})();
