"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const candidates = [
    { mode: "single", prefix: "staging" },
    { mode: "multi", prefix: "host" },
  ];
  const labels = {
    dashboard_identity_required: "请从已登录的 AstrBot 管理页面打开本页。",
    core_access_required: "当前管理账号没有账号与会话管理权限。",
    staging_disabled: "请先在插件配置中启用试运行宿主。",
    staging_settings_incomplete: "插件配置尚未填写完整，请补齐目标账号、会话与模型。",
    staging_settings_invalid: "插件配置无效，请检查运行实例和宿主设置。",
    /* 已固定运行实例读不出来。真实原因藏在 reason 里（缺字段/未知字段/版本不符），
       后端把它编进码尾（staging_intent_invalid__missing_fields），见 labels 兜底。 */
    staging_intent_invalid: "已固定的运行实例配置读不出来，请重新初始化运行实例。",
    staging_intent_write_failed: "运行实例配置写入失败，请检查插件数据目录是否可写。",
    staging_profile_conflict: "固定运行实例的账号、私聊对象或 AstrBot 人格发生变化。请先核对绑定身份；模型参数变化不会阻止连接。",
    staging_not_initialized: "运行实例尚未初始化，请先执行连接探测再初始化。",
    staging_session_unavailable: "当前没有可用的 V2 会话，请先加载或初始化运行实例。",
    staging_host_terminated: "宿主正在停止或已停止，请刷新状态后重试。",
    staging_batch_invalid: "指定的对话批次不存在或已不可读取。",
    staging_delivery_session_active: "当前运行实例正在接收消息，请先停止后修改目标。",
    authorization_denied: "当前关系设置不允许在这个会话中回复。",
    authorization_expired: "当前会话权限已失效，请检查关系与权限设置。",
    authorization_not_active: "当前会话权限尚未生效，请检查关系与权限设置。",
    authorization_revoked: "当前关系设置已收回回复权限。",
    scope_not_granted: "当前会话没有相应的回复权限。",
    staging_delivery_grant_changed: "当前会话权限发生变化，请重新读取状态。",
    staging_review_only: "当前会话没有进入正式接管状态，请检查运行实例和启动状态。",
    staging_session_mode_conflict: "当前会话状态不支持本次操作，请先停止后重试。",
    staging_session_still_stopping: "上一会话仍在收尾，请稍后重新完成连接。",
    staging_account_unavailable: "配置的 OneBot 账号当前未连接。",
    staging_platform_unavailable: "找不到配置的平台实例。",
    staging_conversation_missing: "目标会话在 AstrBot 中不可用，请先建立目标私聊会话。",
    staging_persona_mismatch: "目标会话当前选择的人格与固定运行实例不一致。",
    staging_provider_unsupported: "当前模型没有通过宿主适配检查。",
    host_account_unavailable: "至少一个配置账号当前未连接。",
    host_persona_unavailable: "至少一个配置人格当前无法解析。",
    account_config_mode_required: "账号与会话编辑仅适用于共享宿主模式。",
    account_config_persistence_unavailable: "当前宿主没有提供安全的插件配置保存接口。",
    host_provider_unavailable: "配置的共享模型没有通过宿主适配检查。",
  };
  /* 后端把「运行实例读不出来」的真实原因编进码尾（staging_intent_invalid__schema）。
     具体原因比泛码更能指导修复，所以先查这张表；查不到再退回泛码文案。 */
  const intentReasons = {
    __bom: "文件带 UTF-8 BOM，请以无 BOM 的 UTF-8 重新保存。",
    __not_utf8: "文件不是合法的 UTF-8 文本。",
    __unreadable: "文件无法读取，请检查插件数据目录的权限。",
    __too_large: "文件超过 128 KB 上限，可能被别的程序改写。",
    __not_json: "文件不是合法 JSON，可能被手工编辑或写坏。",
    __duplicate: "JSON 里存在重复键。",
    __not_finite: "文件中存在非法数值（NaN / Infinity）。",
    __version: "schema_version 不是 companion-v2.astrbot-staging.v1。",
    __schema: "字段与当前版本不符：缺少必需字段或存在未知字段。",
    __scope: "目标会话、账号或人格信息不完整或互不匹配。",
    __fingerprint: "人格或模型指纹格式不是 SHA-256。",
    __invalid: "文件内容不合法。",
  };
  /* 码可能带 `__后缀`；先按整码查，再按后缀查，最后回退。 */
  function labelFor(code) {
    if (!code) return "";
    if (labels[code]) return labels[code];
    const cut = code.indexOf("__");
    if (cut > 0) {
      const base = labels[code.slice(0, cut)];
      const detail = intentReasons[code.slice(cut)];
      if (base || detail) return [base, detail].filter(Boolean).join(" ");
    }
    return "";
  }
  let bridge = null;
  let host = null;
  let status = null;
  let probePassed = false;
  let busy = false;
  let pendingAction = null;
  let confirmTrigger = null;
  let topologySelection = null;
  let topologySnapshot = null;
  let topologyFrame = 0;
  let topologySessionPage = 0;
  let bindingConfig = null;
  const accountApi = "accounts";
  const TOPOLOGY_SESSION_PAGE_SIZE = 5;

  const displayValue = (value, fallback = "未标记") => {
    const text = String(value ?? "").trim();
    return text || fallback;
  };
  const topologyScope = (target) => target?.scope_kind === "group" || target?.group_id
    ? `群 ${displayValue(target.group_id || target.target_id)}`
    : `私聊 ${displayValue(target.participant_id || target.target_id)}`;
  function makeTopologySnapshot() {
    const targets = Array.isArray(status?.targets) ? status.targets : [];
    const accounts = new Map();
    const personas = new Map();
    const sessions = [];
    targets.forEach((target, targetIndex) => {
      const platform = displayValue(target.platform_id, "未知平台");
      const account = displayValue(target.account_id, "未知账号");
      const bot = displayValue(target.bot_id, account);
      const accountKey = ["account", platform, account, bot].join(":");
      if (!accounts.has(accountKey)) {
        accounts.set(accountKey, {key: accountKey, platform, account, bot,
          personaKeys: new Set(), sessionKeys: new Set()});
      }
      const rawRoles = Array.isArray(target.roles) && target.roles.length
        ? target.roles
        : target.role_id ? [{role_id: target.role_id, persona_ids: target.persona_ids || []}] : [];
      const personaKeys = [];
      rawRoles.forEach((role, roleIndex) => {
        const roleId = displayValue(role?.role_id, `角色 ${roleIndex + 1}`);
        const personaKey = ["persona", accountKey, roleId].join(":");
        if (!personas.has(personaKey)) {
          personas.set(personaKey, {key: personaKey, roleId, personaIds: new Set(),
            accountKey, sessionKeys: new Set()});
        }
        const persona = personas.get(personaKey);
        (Array.isArray(role?.persona_ids) ? role.persona_ids : []).forEach((id) => persona.personaIds.add(displayValue(id)));
        personaKeys.push(personaKey);
        accounts.get(accountKey).personaKeys.add(personaKey);
      });
      const sessionKey = ["session", displayValue(target.target_id, `${target.scope_kind || "target"}-${targetIndex}`)].join(":");
      const session = {key: sessionKey, targetId: displayValue(target.target_id, `窗口 ${targetIndex + 1}`),
        label: topologyScope(target), scopeKind: target.scope_kind === "group" || target.group_id ? "group" : "private",
        accountKey, personaKeys,
        platform, raw: target};
      sessions.push(session);
      const accountItem = accounts.get(accountKey);
      accountItem.sessionKeys.add(sessionKey);
      personaKeys.forEach((key) => personas.get(key).sessionKeys.add(sessionKey));
    });
    return {accounts: [...accounts.values()], personas: [...personas.values()], sessions,
      mode: host?.mode || (targets.length ? "multi" : "single")};
  }

  function topologyItems(data) {
    return [...data.accounts.map((item) => ({...item, kind: "account"})),
      ...data.personas.map((item) => ({...item, kind: "persona"})),
      ...data.sessions.map((item) => ({...item, kind: "session"}))];
  }

  function connectedTopologyKeys(data, selected) {
    if (!selected) return null;
    const all = topologyItems(data);
    const item = all.find((entry) => entry.key === selected);
    if (!item) return null;
    const keys = new Set([item.key]);
    if (item.kind === "account") {
      item.personaKeys.forEach((key) => keys.add(key));
      item.sessionKeys.forEach((key) => keys.add(key));
    } else if (item.kind === "persona") {
      keys.add(item.accountKey);
      item.sessionKeys.forEach((key) => keys.add(key));
    } else {
      keys.add(item.accountKey);
      item.personaKeys.forEach((key) => keys.add(key));
    }
    return keys;
  }

  function topologyItemLabel(item) {
    if (!item) return "当前关系";
    if (item.kind === "account") return `账号 ${item.account}`;
    if (item.kind === "persona") return `人格 ${item.roleId}`;
    return `会话窗口 ${item.label}`;
  }

  function updateTopologyNote(connected) {
    const note = $("topology-note");
    if (!note || !topologySnapshot?.sessions.length) return;
    if (!topologySelection) {
      note.textContent = "";
      note.hidden = true;
      return;
    }
    const selected = topologyItems(topologySnapshot).find((item) => item.key === topologySelection);
    const relatedCount = Math.max(0, (connected?.size || 1) - 1);
    note.hidden = false;
    note.textContent = `${topologyItemLabel(selected)} · ${relatedCount} 个关联节点`;
  }

  function paintTopologySelection() {
    if (!topologySnapshot) return;
    const connected = connectedTopologyKeys(topologySnapshot, topologySelection);
    document.querySelectorAll(".topology-node").forEach((node) => {
      const active = node.dataset.topologyKey === topologySelection;
      node.classList.toggle("is-active", active);
      node.classList.toggle("is-muted", Boolean(connected && !connected.has(node.dataset.topologyKey)));
      node.setAttribute("aria-pressed", String(active));
    });
    document.querySelectorAll(".topology-line").forEach((line) => {
      const active = Boolean(connected && connected.has(line.dataset.topologySource)
        && connected.has(line.dataset.topologyTarget));
      line.classList.toggle("is-active", active);
      line.classList.toggle("is-muted", Boolean(connected && !active));
    });
    const canvas = $("topology-canvas");
    if (canvas) canvas.dataset.selection = topologySelection ? "active" : "none";
    updateTopologyNote(connected);
  }

  function topologyNode(item, kind, index) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "topology-node";
    button.dataset.topologyKey = item.key;
    button.dataset.topologyKind = kind;
    const head = document.createElement("span");
    head.className = "topology-node-head";
    const title = document.createElement("span");
    title.className = "topology-node-title";
    title.textContent = kind === "account" ? item.account
      : kind === "persona" ? item.roleId : item.label;
    const badge = document.createElement("span");
    badge.className = `topology-node-badge${item.scopeKind === "group" ? " group" : ""}`;
    badge.textContent = kind === "account" ? item.platform
      : kind === "persona" ? "角色" : item.scopeKind === "group" ? "群聊" : "私聊";
    head.append(title, badge);
    const meta = document.createElement("span");
    meta.className = "topology-node-meta";
    if (kind === "account") meta.textContent = `账号 ${item.account} · Bot ${item.bot}`;
    else if (kind === "persona") meta.textContent = item.personaIds.size
      ? `人格 ${[...item.personaIds].join("、")}` : "跟随当前人格设置";
    else meta.textContent = `${item.platform} · ${item.targetId}`;
    const detail = document.createElement("span");
    detail.className = "topology-node-detail";
    if (kind === "account") detail.textContent = `${item.sessionKeys.size} 个窗口 · ${item.personaKeys.size} 个人格`;
    else if (kind === "persona") detail.textContent = `${item.sessionKeys.size} 个窗口 · 来自 ${item.accountKey.split(":")[2] || "账号"}`;
    else detail.textContent = item.delivery;
    button.append(head, meta, detail);
    button.style.setProperty("--node-index", String(index));
    button.title = `${topologyItemLabel({...item, kind})} · 点击高亮关联关系`;
    button.setAttribute("aria-label", `${topologyItemLabel({...item, kind})}，${meta.textContent}，${detail.textContent}`);
    button.setAttribute("aria-pressed", String(item.key === topologySelection));
    button.addEventListener("click", () => {
      topologySelection = topologySelection === item.key ? null : item.key;
      paintTopologySelection();
    });
    return button;
  }

  function renderTopologySessions(data) {
    const list = $("topology-sessions");
    const pagination = $("topology-session-pagination");
    const previous = $("topology-session-prev");
    const next = $("topology-session-next");
    const pageLabel = $("topology-session-page");
    if (!list || !pagination || !previous || !next || !pageLabel) return;
    const pageCount = Math.max(1, Math.ceil(data.sessions.length / TOPOLOGY_SESSION_PAGE_SIZE));
    topologySessionPage = Math.min(Math.max(0, topologySessionPage), pageCount - 1);
    const start = topologySessionPage * TOPOLOGY_SESSION_PAGE_SIZE;
    const visible = data.sessions.slice(start, start + TOPOLOGY_SESSION_PAGE_SIZE);
    list.replaceChildren(...visible.map((item, index) => topologyNode(item, "session", index)));
    const paged = pageCount > 1;
    pagination.hidden = !paged;
    pageLabel.textContent = paged
      ? `第 ${topologySessionPage + 1} / ${pageCount} 页 · ${start + 1}–${start + visible.length} / ${data.sessions.length}`
      : "";
    previous.dataset.disabled = String(topologySessionPage === 0);
    next.dataset.disabled = String(topologySessionPage >= pageCount - 1);
    previous.disabled = previous.dataset.disabled === "true";
    next.disabled = next.dataset.disabled === "true";
  }

  function changeTopologySessionPage(delta) {
    if (!topologySnapshot || topologySnapshot.sessions.length <= TOPOLOGY_SESSION_PAGE_SIZE) return;
    const pageCount = Math.ceil(topologySnapshot.sessions.length / TOPOLOGY_SESSION_PAGE_SIZE);
    const nextPage = Math.min(Math.max(0, topologySessionPage + delta), pageCount - 1);
    if (nextPage === topologySessionPage) return;
    topologySessionPage = nextPage;
    if (topologySelection?.startsWith("session:")) topologySelection = null;
    renderTopologySessions(topologySnapshot);
    scheduleTopologyLinks();
  }

  function drawTopologyLinks() {
    const data = topologySnapshot;
    const canvas = $("topology-canvas");
    const svg = $("topology-links");
    if (!data || !canvas || !svg || canvas.hidden) return;
    const canvasRect = canvas.getBoundingClientRect();
    const width = Math.max(1, canvasRect.width);
    const height = Math.max(1, canvasRect.height);
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.replaceChildren();
    const nodes = [...canvas.querySelectorAll(".topology-node")];
    const find = (key) => nodes.find((node) => node.dataset.topologyKey === key);
    const connections = [];
    data.personas.forEach((persona) => {
      if (persona.accountKey) connections.push([persona.accountKey, persona.key]);
    });
    data.sessions.forEach((session) => {
      const personaKeys = session.personaKeys.length ? session.personaKeys : [session.accountKey];
      personaKeys.forEach((key) => connections.push([key, session.key]));
    });
    const port = (from, to) => {
      const horizontalRight = to.left >= from.right - 4;
      const horizontalLeft = to.right <= from.left + 4;
      if (horizontalRight) return [[from.right - canvasRect.left, from.top - canvasRect.top + from.height / 2],
        [to.left - canvasRect.left, to.top - canvasRect.top + to.height / 2], false];
      if (horizontalLeft) return [[from.left - canvasRect.left, from.top - canvasRect.top + from.height / 2],
        [to.right - canvasRect.left, to.top - canvasRect.top + to.height / 2], false];
      if (to.top >= from.bottom - 4) return [[from.left - canvasRect.left + from.width / 2, from.bottom - canvasRect.top],
        [to.left - canvasRect.left + to.width / 2, to.top - canvasRect.top], true];
      return [[from.left - canvasRect.left + from.width / 2, from.top - canvasRect.top],
        [to.left - canvasRect.left + to.width / 2, to.bottom - canvasRect.top], true];
    };
    connections.forEach(([sourceKey, targetKey], lineIndex) => {
      const source = find(sourceKey);
      const target = find(targetKey);
      if (!source || !target) return;
      const [start, end, vertical] = port(source.getBoundingClientRect(), target.getBoundingClientRect());
      const distance = vertical ? Math.max(18, Math.abs(end[1] - start[1]) * .42)
        : Math.max(22, Math.abs(end[0] - start[0]) * .42);
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.classList.add("topology-line");
      path.dataset.topologySource = sourceKey;
      path.dataset.topologyTarget = targetKey;
      path.setAttribute("pathLength", "1");
      path.style.setProperty("--line-delay", `${Math.min(lineIndex * 48, 240)}ms`);
      path.setAttribute("d", vertical
        ? `M ${start[0]} ${start[1]} C ${start[0]} ${start[1] + distance}, ${end[0]} ${end[1] - distance}, ${end[0]} ${end[1]}`
        : `M ${start[0]} ${start[1]} C ${start[0] + distance} ${start[1]}, ${end[0] - distance} ${end[1]}, ${end[0]} ${end[1]}`);
      svg.append(path);
    });
    paintTopologySelection();
  }

  function scheduleTopologyLinks() {
    if (topologyFrame) cancelAnimationFrame(topologyFrame);
    topologyFrame = requestAnimationFrame(() => {
      topologyFrame = 0;
      drawTopologyLinks();
    });
  }

  function renderTopology() {
    const canvas = $("topology-canvas");
    const empty = $("topology-empty");
    const mode = $("topology-mode");
    const counts = $("topology-counts");
    const note = $("topology-note");
    if (!canvas || !empty || !mode || !counts || !note) return;
    const data = makeTopologySnapshot();
    topologySnapshot = data;
    const hasTargets = data.sessions.length > 0;
    mode.textContent = host?.mode === "multi" ? "多目标映射" : "单目标运行实例";
    mode.dataset.state = hasTargets ? "ready" : "empty";
    counts.textContent = hasTargets
      ? `${data.accounts.length} 个账号 · ${data.personas.length} 个人格 · ${data.sessions.length} 个窗口`
      : "尚未返回映射";
    note.textContent = hasTargets
      ? "" : "暂无绑定目录。";
    note.hidden = hasTargets;
    if (!hasTargets) {
      topologySelection = null;
      topologySessionPage = 0;
      canvas.hidden = true;
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    canvas.hidden = false;
    const lists = {accounts: $("topology-accounts"), personas: $("topology-personas"), sessions: $("topology-sessions")};
    lists.accounts.replaceChildren(...data.accounts.map((item, index) => topologyNode(item, "account", index)));
    lists.personas.replaceChildren(...data.personas.map((item, index) => topologyNode(item, "persona", index)));
    renderTopologySessions(data);
    if (topologySelection && !topologyItems(data).some((item) => item.key === topologySelection)) topologySelection = null;
    scheduleTopologyLinks();
  }

  function codeOf(value) {
    return value?.code || value?.data?.code || value?.response?.data?.code || "";
  }
  function messageOf(value) {
    return [value?.message, value?.reason, value?.response?.message, value?.detail]
      .find((item) => typeof item === "string" && item) || "";
  }
  function unwrap(value) {
    let current = value;
    for (let depth = 0; depth < 3; depth += 1) {
      if (current?.status === "error") {
        const error = new Error(labelFor(current?.data?.code) || messageOf(current) || "请求未完成。请刷新状态后重试。");
        error.code = current?.data?.code || "";
        throw error;
      }
      if (current?.status === "ok" && Object.hasOwn(current, "data")) {
        current = current.data;
        continue;
      }
      return current;
    }
    return current;
  }
  function isMissingRoute(error) {
    if (["dashboard_identity_required", "core_access_required"].includes(error?.code)) return false;
    const message = messageOf(error) || error?.message || "";
    return /未找到该路由|route (?:was )?not found|no matching route/i.test(message);
  }
  async function api(method, endpoint, body = {}) {
    if (!bridge) throw new Error("AstrBot 页面桥尚未就绪，请从已启用插件的管理页面打开本页。");
    const response = method === "GET"
      ? await bridge.apiGet(endpoint, {})
      : await bridge.apiPost(endpoint, body);
    return unwrap(response);
  }
  function setBusy(value) {
    busy = value;
    document.querySelectorAll("button").forEach((button) => {
      button.disabled = value || button.dataset.disabled === "true";
    });
    document.querySelector(".status-panel").setAttribute("aria-busy", String(value));
    updateControls();
  }

  function setLoading(button, value) {
    if (!button) return;
    button.classList.toggle("is-loading", value);
    button.setAttribute("aria-busy", String(value));
  }

  function paintStatusValue(id, value) {
    const element = $(id);
    if (!element) return;
    const next = String(value ?? "");
    if (element.textContent === next) return;
    element.textContent = next;
    element.classList.remove("is-updated");
    void element.offsetWidth;
    element.classList.add("is-updated");
  }
  function notice(text, kind = "info") {
    const element = $("notice");
    element.textContent = text;
    element.dataset.kind = kind;
    element.hidden = !text;
  }
  function stateLabel(value) {
    return ({ running: "运行中", new: "已初始化，未启动", stopped: "已停止", uninitialized: "未初始化", unloaded: "尚未加载" })[value] || value || "未知";
  }
  function isInitialized() {
    if (!status || !host) return false;
    if (host.mode === "single") return Boolean(status.configured || status.runtime_open);
    return status.state !== "uninitialized";
  }
  function isAccepting() { return Boolean(status?.accepting); }
  function isEnabled() {
    if (!status || !host) return false;
    return host.mode === "single" ? Boolean(status.enabled && status.settings_valid) : Boolean(status.enabled && !status.settings_error);
  }
  function editorRow(fields, values, remove) {
    const row = document.createElement("div"); row.className = "binding-row";
    fields.forEach(([key, label, placeholder]) => { const input = document.createElement("input"); input.dataset.field = key; input.placeholder = placeholder || label; input.value = values?.[key] || ""; input.setAttribute("aria-label", label); row.append(input); });
    const button = document.createElement("button"); button.type = "button"; button.className = "button button-quiet binding-remove"; button.textContent = "移除"; button.addEventListener("click", () => { row.remove(); updateBindingCheck(); }); row.append(button); return row;
  }
  function choiceRow(fields, values, choices, remove) {
    const row = document.createElement("div"); row.className = "binding-row";
    fields.forEach(([key, label]) => { const select = document.createElement("select"); select.dataset.field = key; select.setAttribute("aria-label", label); const list = choices[key] || []; select.append(new Option(`选择${label}`, "")); list.forEach(item => select.append(new Option(item.label || item.value, item.value))); select.value = values?.[key] || ""; row.append(select); });
    const button = document.createElement("button"); button.type = "button"; button.className = "button button-quiet binding-remove"; button.textContent = "移除"; button.addEventListener("click", () => { row.remove(); updateBindingCheck(); }); row.append(button); return row;
  }
  function collectRows(id) { return [...document.querySelectorAll(`#${id} .binding-row`)].map(row => Object.fromEntries([...row.querySelectorAll("[data-field]")].map(input => [input.dataset.field, input.value.trim()]))); }
  function renderBindingEditor(data) {
    if (!data) return;
    bindingConfig = data;
    $("bindings-enabled").checked = Boolean(data.enabled);
    const discovered = data.discovered || {}, accounts = discovered.accounts || data.accounts || [], personas = discovered.personas || [];
    const accountChoices = accounts.map(x => ({value: `${x.platform_id}|${x.account_id}|${x.bot_id}`, label: `${x.bot_id || x.account_id} · ${x.account_id}`}));
    const accountByKey = new Map(accounts.map(x => [`${x.platform_id}|${x.account_id}|${x.bot_id}`, x]));
    const personaChoices = personas.map(x => ({value: `${x.bot_id || ""}|${x.persona_id || ""}|${x.role_id || "role-1"}`, label: `${x.bot_id || "Bot"} · ${x.label || x.persona_id || "当前人格"}`}));
    $("edit-accounts").replaceChildren(...(data.accounts || []).map(x => choiceRow([["account_key","Bot 账号"]], {account_key: `${x.platform_id}|${x.account_id}|${x.bot_id}`}, {account_key: accountChoices}, true)));
    $("edit-personas").replaceChildren(...(data.personas || []).map(x => choiceRow([["persona_key","人格"]], {persona_key: `${x.persona_id}|${x.role_id}`}, {persona_key: personaChoices}, true)));
    const targets = discovered.targets || [];
    const sessionChoices = new Map();
    targets.forEach(x => { const key = `${x.platform_id}|${x.account_id}|${x.bot_id}`; const list = sessionChoices.get(key) || []; const id = x.participant_id || x.group_id || x.target_id; if (id) list.push({value: id, label: `${x.scope_kind === "group" ? "群" : "私聊"} ${id}`}); sessionChoices.set(key, list); });
    $("edit-sessions").replaceChildren(...(data.sessions || []).map(x => { const key = `${x.platform_id}|${x.account_id}|${x.bot_id}`; return choiceRow([["account_key","Bot 账号"]], {account_key: key}, {account_key: accountChoices}, true); }));
    if ((data.sessions || []).length) (data.sessions || []).forEach((x, index) => { const row=$("edit-sessions").children[index]; const key=`${x.platform_id}|${x.account_id}|${x.bot_id}`; const values=sessionChoices.get(key)||[]; const input=document.createElement("input"); input.dataset.field="participant_id"; input.placeholder="私聊对象 QQ 号"; input.value=x.participant_id||""; input.setAttribute("aria-label","私聊对象"); row.insertBefore(input,row.lastElementChild); });
    bindingConfig._accountByKey = accountByKey;
    updateBindingCheck();
  }
  function updateBindingCheck() {
    const accounts = collectRows("edit-accounts"), personas = collectRows("edit-personas"), sessions = collectRows("edit-sessions");
    const accountKeys = new Set(accounts.map(x => x.account_key));
    const valid = accounts.length && personas.length && sessions.length && sessions.every(x => accountKeys.has(x.account_key) && x.participant_id) && personas.every(x => x.persona_key);
    $("binding-check").textContent = valid ? `${accounts.length} 个账号 · ${personas.length} 个人格 · ${sessions.length} 个窗口，配置完整` : "请补齐账号、人格和窗口，并确保窗口选择已存在的账号";
    $("save-bindings").disabled = !valid || busy || host?.mode !== "multi";
  }
  async function readBindingConfig() { try { renderBindingEditor(await api("GET", accountApi)); } catch (error) { $("binding-check").textContent = publicError(error); } }
  async function saveBindingConfig() { const rawAccounts = collectRows("edit-accounts"), rawPersonas = collectRows("edit-personas"), rawSessions = collectRows("edit-sessions"); const accountMap = bindingConfig?._accountByKey || new Map(); const accounts = rawAccounts.map(x => accountMap.get(x.account_key)).filter(Boolean); const personas = rawPersonas.map((x, i) => { const [bot_id, persona_id, role_id] = String(x.persona_key || "||").split("|"); return {bot_id, persona_id, role_id: role_id || `role-${i+1}`}; }); const sessions = rawSessions.map(x => { const a = accountMap.get(x.account_key); return a ? {...a, participant_id: x.participant_id} : null; }).filter(Boolean); const body = {enabled: $("bindings-enabled").checked, accounts, personas, sessions}; try { setBusy(true); const result = await api("POST", accountApi, body); renderBindingEditor(result.configuration); notice("账号与会话已保存。请重载插件后继续首次设置。", "success"); } catch (error) { notice(`保存未完成：${publicError(error)}`, "error"); } finally { setBusy(false); updateBindingCheck(); } }
  function renderStatus() {
    if (!status || !host) return;
    $("connection").textContent = host.mode === "multi" ? "共享宿主管理接口可用" : "单目标宿主管理接口可用";
    $("connection").dataset.state = "ready";
    $("status-heading").textContent = isEnabled() ? "配置已加载" : "宿主尚未启用或配置无效";
    paintStatusValue("profile", host.mode === "single" ? status.profile_id || "未配置" : status.installation_id || "未配置");
    paintStatusValue("runtime-state", host.mode === "single"
      ? stateLabel(status.session_state || (status.configured ? "new" : "uninitialized"))
      : stateLabel(status.state));
    paintStatusValue("accepting", isAccepting() ? "正在接管消息" : "未接管消息");
    $("safety-note").textContent = isAccepting()
      ? "当前会话按关系权限处理；主动消息使用已确认的核心管理员窗口。"
      : "启动后开始接收匹配的入站消息。";
    $("safety-note").hidden = !$("safety-note").textContent;
    if (status.last_failure?.code || status.settings_error) {
      const code = status.last_failure?.code || status.settings_error;
      notice(labelFor(code) || `宿主最近一次操作未完成（${code}）。修复配置后可重新探测。`, "error");
    } else {
      notice("");
    }
    renderTopology();
    updateControls();
  }
  function updateControls() {
    $("refresh").disabled = busy;
    $("probe").disabled = busy || !host;
    $("initialize").disabled = busy || !status || !probePassed || isInitialized() || !isEnabled();
    $("start").disabled = busy || !status || !isInitialized() || isAccepting() || !isEnabled();
    $("stop").disabled = busy || !status || !isAccepting();
    $("probe-state").textContent = probePassed ? "本次探测通过" : "请先执行连接探测";
  }
  async function readStatus() {
    let lastError = null;
    for (const candidate of candidates) {
      try {
        const value = await api("GET", `${candidate.prefix}/status`);
        host = candidate;
        status = value;
        probePassed = false;
        renderStatus();
        await readBindingConfig();
        return;
      } catch (error) {
        lastError = error;
        if (!isMissingRoute(error)) throw error;
      }
    }
    throw lastError || new Error("没有发现可用的 Companion V2 宿主 API。");
  }
  function publicError(error) {
    if (labelFor(error?.code)) return labelFor(error.code);
    const message = messageOf(error) || error?.message || "";
    if (labelFor(message)) return labelFor(message);
    if (/dashboard|sign in|unauthorized|401/i.test(message)) return "请先登录 AstrBot Dashboard，再从插件页面打开本页。";
    if (isMissingRoute(error)) return "当前插件版本没有提供账号与会话 API，请重新加载 Companion V2 插件。";
    return message || "宿主操作未完成，请刷新状态后重试。";
  }
  async function runAction(action) {
    const text = { probe: "连接探测", initialize: "初始化", start: "启动", stop: "停止" }[action];
    const trigger = $(action);
    setLoading(trigger, true);
    setBusy(true);
    try {
      if (action === "probe") {
        const result = await api("POST", `${host.prefix}/probe`);
        probePassed = host.mode === "multi" || result.target_ready !== false;
        if (!probePassed) throw new Error("目标尚未就绪。请补齐目标账号、会话和模型设置。" );
        await readStatus();
        probePassed = true;
        renderStatus();
        notice("探测通过。此次探测没有调用模型或发送平台消息，可以继续初始化运行实例。", "success");
      } else {
        await api("POST", `${host.prefix}/${action}`);
        await readStatus();
        probePassed = false;
        const message = action === "initialize" ? "V2 运行实例已初始化，宿主保持停止状态。"
          : action === "start" ? "宿主已启动，当前匹配的入站消息将按已绑定目标处理。"
            : "宿主已停止接管新消息。";
        notice(message, "success");
      }
    } catch (error) {
      probePassed = false;
      const message = `${text}未完成：${publicError(error)}`;
      try { await readStatus(); } catch { /* Keep the operation error visible. */ }
      notice(message, "error");
    } finally {
      setBusy(false);
      setLoading(trigger, false);
    }
  }
  const actionCopy = {
    initialize: () => `将按当前插件配置初始化 ${status?.profile_id || status?.installation_id || "当前 V2 运行实例"}。此操作会创建或恢复插件独立数据，不会删除旧运行实例。`,
    start: () => "启动后开始处理账号配置中匹配的入站消息，并通过对应 OneBot 账号回复。",
    stop: () => "停止接管新消息，并等待当前任务安全收尾。",
  };
  function confirm(action) {
    confirmTrigger = document.activeElement;
    pendingAction = action;
    $("confirm-heading").textContent = ({ initialize: "初始化运行实例", start: "启动宿主", stop: "停止宿主" })[action];
    $("confirm-copy").textContent = actionCopy[action]();
    $("confirm-action").textContent = action === "initialize" ? "初始化" : action === "start" ? "启动" : "停止";
    $("confirm-action").classList.toggle("button-danger", action === "stop");
    $("confirm-action").classList.toggle("button-primary", action !== "stop");
    $("confirm").showModal();
    requestAnimationFrame(() => $("cancel")?.focus());
  }
  async function boot() {
    try {
      bridge = window.AstrBotPluginPage;
      if (!bridge) throw new Error("AstrBot 页面桥未加载，请从已登录的插件管理页面打开本页。");
      await bridge.ready();
      setBusy(true);
      await readStatus();
    } catch (error) {
      $("connection").textContent = "未连接";
      $("connection").dataset.state = "error";
      $("status-heading").textContent = "无法读取宿主状态";
      status = null;
      host = null;
      topologySnapshot = null;
      renderTopology();
      notice(publicError(error), "error");
      updateControls();
    } finally {
      setBusy(false);
      document.querySelector(".status-panel").setAttribute("aria-busy", "false");
    }
  }
  $("refresh").addEventListener("click", async () => {
    setLoading($("refresh"), true);
    setBusy(true);
    try { await readStatus(); }
    catch (error) { notice(publicError(error), "error"); }
    finally { setBusy(false); setLoading($("refresh"), false); }
  });
  $("probe").addEventListener("click", () => runAction("probe"));
  $("initialize").addEventListener("click", () => confirm("initialize"));
  $("start").addEventListener("click", () => confirm("start"));
  $("stop").addEventListener("click", () => confirm("stop"));
  $("topology-session-prev").addEventListener("click", () => changeTopologySessionPage(-1));
  $("topology-session-next").addEventListener("click", () => changeTopologySessionPage(1));
  $("add-account").addEventListener("click", () => { const choices = (bindingConfig?.discovered?.accounts || []).map(x => ({value:`${x.platform_id}|${x.account_id}|${x.bot_id}`, label:`${x.bot_id} · ${x.account_id}`})); $("edit-accounts").append(choiceRow([["account_key","Bot 账号"]], {}, {account_key:choices}, true)); updateBindingCheck(); });
  $("add-persona").addEventListener("click", () => { const choices = (bindingConfig?.discovered?.personas || []).map(x => ({value:`${x.bot_id}|${x.persona_id}|${x.role_id || "role-1"}`, label:`${x.bot_id} · ${x.label || x.persona_id}`})); $("edit-personas").append(choiceRow([["persona_key","人格"]], {}, {persona_key:choices}, true)); updateBindingCheck(); });
  $("add-session").addEventListener("click", () => { const accounts = bindingConfig?.discovered?.accounts || []; const accountChoices = accounts.map(x => ({value:`${x.platform_id}|${x.account_id}|${x.bot_id}`, label:`${x.bot_id} · ${x.account_id}`})); const row = choiceRow([["account_key","Bot 账号"]], {}, {account_key:accountChoices}, true); const input=document.createElement("input"); input.dataset.field="participant_id"; input.placeholder="私聊对象 QQ 号"; input.setAttribute("aria-label","私聊对象"); row.insertBefore(input,row.lastElementChild); $("edit-sessions").append(row); updateBindingCheck(); });
  $("save-bindings").addEventListener("click", saveBindingConfig);
  document.addEventListener("input", (event) => { if (event.target.closest(".binding-editor")) updateBindingCheck(); });
  $("confirm").addEventListener("close", () => {
    const action = pendingAction;
    const confirmed = $("confirm").returnValue === "confirm";
    pendingAction = null;
    if (confirmTrigger?.isConnected) confirmTrigger.focus();
    confirmTrigger = null;
    if (action && confirmed) void runAction(action);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || $("confirm")?.open || !topologySelection) return;
    topologySelection = null;
    paintTopologySelection();
  });
  window.addEventListener("resize", scheduleTopologyLinks, {passive: true});
  boot();
})();
