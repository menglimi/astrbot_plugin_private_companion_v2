"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const endpoint = "acquaintance";
  const authorizationEndpoint = endpoint + "/authorization";
  const adminNameEndpoint = endpoint + "/admin-name";
  const CAPABILITY_LABELS = {
    text: "接收消息",
    "conversation.reply": "对话回复",
    "message.delivery": "主动投递",
    "proactive.contact": "主动联系",
    "configuration.read": "读取配置",
    "extension.tool.invoke": "调用拓展工具",
    "screen.read": "读取屏幕",
    "screen.process": "处理屏幕",
  };
  const STATE_LABELS = { active: "已生效", off: "未授权", revoked: "已撤销", expired: "已过期", pending: "尚未生效" };
  const errors = {
    dashboard_identity_required: "请从已登录的 AstrBot 管理界面打开本页面。",
    staging_not_initialized: "页面已连接 AstrBot，但 V2 运行实例尚未加载。请先在宿主管理中加载运行实例，再重新读取。",
    staging_host_terminated: "插件已经停止，请重新打开管理页面。",
    core_access_required: "当前管理账号没有相识目录查看权限。",
    acquaintance_request_invalid: "目录请求不合法，请刷新页面重试。",
    acquaintance_subject_required: "请先选择一位成员。",
    acquaintance_subject_unknown: "这个人不在当前运行实例的相识目录里，请刷新后重试。",
    authorization_command_invalid: "这次授权变更缺少必要信息，请刷新页面重试。",
    authorization_capability_configured: "这项能力由运行实例配置签发，请到宿主管理的能力配置中调整。",
    authorization_capability_not_managed: "这项能力当前没有本页可以撤销的授权，请刷新后重试。",
    authorization_revision_conflict: "授权刚刚被改过，页面已读回最新状态，请再确认一次。",
    authorization_operation_unresolved: "上一次授权变更没有走完，请刷新核对后再试。",
    authorization_change_not_applied: "这次授权变更没有落到记录上，请刷新核对。",
    person_nickname_command_invalid: "称呼请求不完整，请刷新成员资料后重试。",
    person_nickname_invalid: "管理员称呼最多 64 个字符。",
    acquaintance_person_unknown: "这位成员已不在当前 Bot 与角色目录中，请刷新后重试。",
    person_nickname_revision_conflict: "成员资料刚刚被更新，正在读回最新版本。",
    person_nickname_operation_conflict: "这次称呼操作键已用于另一项修改，请重新保存。",
    person_nickname_operation_unresolved: "上一次称呼修改尚未完成，请刷新核对后重试。",
  };
  let bridge, data = null, filter = "all", selected = null, selectedGroupId = "", activeView = "network";
  let graphScope = "all", searchTerm = "", requestSequence = 0, authSequence = 0;
  let authorization = {}, authServer = "", authBusy = false, nicknameBusy = false;
  let pendingNicknameOperation = null;

  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const hue = (seed) => {
    let value = 0;
    for (const char of String(seed)) value = (value * 31 + char.codePointAt(0)) % 360;
    return value;
  };
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
  const number = (value) => Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
  const shortTime = (value) => {
    if (!value) return "—";
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "—";
    return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(date);
  };
  const nameOf = (person) => person.display_name || `未命名成员 ${person.native_account_id ?? ""}`.trim();
  const groupsOf = (person) => person.groups && typeof person.groups === "object" ? person.groups : {};
  const groupIdsOf = (person) => Object.keys(groupsOf(person));
  const groupKey = (group) => String(group.group_id ?? "");

  function notice(message, error = false) {
    const target = $("notice");
    target.textContent = message;
    target.className = "notice" + (error ? " error" : "");
    target.hidden = !message;
  }
  function setSyncState(state, message) {
    const target = $("sync-state");
    target.className = "sync-state" + (state ? " is-" + state : "");
    target.textContent = message;
  }
  function unwrap(response) {
    const wrapped = ["ok", "error"].includes(response?.status) ? response
      : ["ok", "error"].includes(response?.data?.status) ? response.data : null;
    if (wrapped?.status === "error") throw Object.assign(
      new Error(wrapped.reason || wrapped.error?.reason || wrapped.message || "读取失败"),
      { code: wrapped.data?.code || wrapped.error?.code || wrapped.message });
    const content = wrapped ? wrapped.data : response;
    if (!content || typeof content !== "object") throw new Error("未收到服务结果。");
    return content;
  }
  function localized(error) {
    if (errors[error?.code]) return new Error(errors[error.code]);
    const message = [error?.message, error?.reason].find((item) => typeof item === "string" && item) || "";
    if (/initialized v2 profile|staging profile|staging profile first/i.test(message)) return new Error(errors.staging_not_initialized);
    if (/dashboard|sign in/i.test(message)) return new Error(errors.dashboard_identity_required);
    return new Error(message || "暂时无法读取相识目录，请刷新重试。");
  }
  function searchText(person) {
    return [nameOf(person), person.native_account_id, person.subject_id, ...groupIdsOf(person)].join(" ").toLocaleLowerCase();
  }
  function matchesSearch(person) { return !searchTerm || searchText(person).includes(searchTerm); }
  function visiblePeople() {
    if (!data) return [];
    return data.persons.filter((person) => {
      if (!matchesSearch(person)) return false;
      if (filter === "private") return person.private_chat;
      if (filter === "group") return person.group_member;
      if (filter === "both") return person.private_chat && person.group_member;
      return true;
    });
  }
  function graphPeople() {
    if (!data) return [];
    return data.persons.filter((person) => {
      if (!matchesSearch(person)) return false;
      if (graphScope === "private") return person.private_chat;
      if (graphScope === "group") return person.group_member;
      return true;
    });
  }
  function allGroups() {
    if (!data) return [];
    const groups = new Map();
    for (const group of data.groups || []) {
      const id = groupKey(group);
      if (!id) continue;
      groups.set(id, { ...group, group_id: id, configured: true,
        member_count: number(group.member_count), msg_count: number(group.msg_count) });
    }
    for (const person of data.persons || []) {
      for (const [id, item] of Object.entries(groupsOf(person))) {
        if (!id) continue;
        if (!groups.has(id)) groups.set(id, { group_id: id, configured: false, member_count: 0, msg_count: 0,
          account_id: "", bot_id: "" });
        const group = groups.get(id);
        if (!group.configured) {
          group.member_count += 1;
          group.msg_count += number(item?.msg_count);
        }
      }
    }
    return [...groups.values()].sort((a, b) => Number(b.configured) - Number(a.configured)
      || number(b.msg_count) - number(a.msg_count) || groupKey(a).localeCompare(groupKey(b), "zh-CN"));
  }
  function searchedGroups() {
    const people = graphPeople();
    return allGroups().filter((group) => {
      if (graphScope === "private") return false;
      if (!searchTerm) return true;
      const idMatch = groupKey(group).toLocaleLowerCase().includes(searchTerm);
      return idMatch || people.some((person) => groupsOf(person)[groupKey(group)]);
    });
  }
  function peopleInGroup(group, { honorSearch = true } = {}) {
    if (!data) return [];
    const id = groupKey(group);
    return data.persons.filter((person) => groupsOf(person)[id]
      && (!honorSearch || !searchTerm || id.toLocaleLowerCase().includes(searchTerm) || matchesSearch(person)));
  }
  function avatar(person, className = "avatar") {
    const wrapper = node("span", undefined, className);
    wrapper.style.setProperty("--hue", String(hue(person.subject_id)));
    wrapper.append(node("span", (nameOf(person)[0] ?? "？").toUpperCase()));
    if (person.private_chat) wrapper.append(node("i", undefined, "private-dot"));
    return wrapper;
  }
  function badge(text, className = "") { return node("small", text, "badge" + (className ? " " + className : "")); }
  function contextBadge(text, className = "") { return node("span", text, "ctx" + (className ? " " + className : "")); }

  function personCard(person, index) {
    const card = node("button", undefined, "person-card");
    card.type = "button";
    card.style.setProperty("--i", String(index));
    card.setAttribute("aria-pressed", String(selected?.subject_id === person.subject_id));
    const head = node("span", undefined, "card-head");
    head.append(avatar(person));
    const title = node("span", undefined, "card-title");
    title.append(node("strong", nameOf(person)));
    const badges = node("span", undefined, "card-badges");
    if (person.private_chat) badges.append(badge("私聊", "private"));
    if (person.group_member) badges.append(badge(`群聊 ${groupIdsOf(person).length}`, "group"));
    if (!person.private_chat && !person.group_member) badges.append(badge("暂无往来"));
    if (authorization[person.subject_id]?.companion === true) badges.append(badge("陪伴对象", "companion"));
    title.append(badges);
    head.append(title);
    const meta = node("span", undefined, "card-meta");
    meta.append(node("span", `${number(person.total?.msg_count)} 条消息`),
      node("span", `${number(person.total?.active_days)} 活跃天`),
      node("span", `最近 ${shortTime(person.total?.last_seen)}`));
    const contexts = node("span", undefined, "card-contexts");
    if (person.private_chat) contexts.append(contextBadge(`私聊 ${number(person.private?.msg_count)} 条`, "private"));
    groupIdsOf(person).slice(0, 3).forEach((id) => contexts.append(contextBadge(`群 ${id}`)));
    if (groupIdsOf(person).length > 3) contexts.append(contextBadge(`另有 ${groupIdsOf(person).length - 3} 个群`));
    card.append(head, meta, contexts);
    card.addEventListener("click", () => select(person));
    return card;
  }
  function renderPeople() {
    const grid = $("people-grid");
    grid.replaceChildren();
    const people = visiblePeople();
    $("people-result-count").textContent = `${people.length} 人`;
    if (!people.length) {
      const empty = node("div", undefined, "empty-state");
      empty.append(node("strong", data ? searchTerm ? "沒有符合的往来成员" : "这里还没有符合的相识" : "正在读取相识目录…"));
      grid.append(empty);
      return;
    }
    people.forEach((person, index) => grid.append(personCard(person, index)));
  }

  function svgPerson(person, y) {
    const id = esc(person.subject_id);
    const name = esc(nameOf(person));
    const privateCount = number(person.private?.msg_count);
    const groupCount = groupIdsOf(person).length;
    const meta = [person.private_chat ? `私聊 ${privateCount} 条` : "",
      groupCount ? `群聊 ${groupCount} 个` : ""].filter(Boolean).join(" · ") || "往来已记录";
    const selectedClass = selected?.subject_id === person.subject_id ? " selected" : "";
    return `<g class="graph-person${selectedClass}" data-person-id="${id}" tabindex="0" role="button" aria-label="打开 ${name} 的私聊详情">
      <title>${name} · ${esc(meta)}</title><rect x="790" y="${y - 23}" width="224" height="46" rx="7"></rect>
      <circle class="graph-avatar" cx="812" cy="${y}" r="13" fill="hsl(${hue(person.subject_id)} 42% 43%)"></circle>
      <text class="graph-avatar-letter" x="812" y="${y + 4}">${esc((nameOf(person)[0] ?? "？").toUpperCase())}</text>
      <text class="graph-node-title" x="834" y="${y - 2}">${name}</text>
      <text class="graph-node-meta" x="834" y="${y + 14}">${esc(meta)}</text></g>`;
  }
  function svgGroup(group, y) {
    const id = groupKey(group), configured = group.configured;
    return `<g class="graph-group${selectedGroupId === id ? " selected" : ""}" data-group-id="${esc(id)}" tabindex="0" role="button" aria-label="打开群 ${esc(id)} 的详情">
      <title>群 ${esc(id)} · ${configured ? "已配置群目标" : "历史群内记录"}</title>
      <rect x="408" y="${y - 25}" width="190" height="50" rx="7"></rect>
      <rect class="group-icon" x="421" y="${y - 11}" width="22" height="22" rx="5"></rect>
      <text class="graph-node-title" x="452" y="${y - 2}">群 ${esc(id)}</text>
      <text class="graph-node-meta" x="452" y="${y + 14}">${configured ? "已配置群目标" : "历史群内记录"} · ${number(group.member_count)} 人</text></g>`;
  }
  function graphMarkup() {
    if (!data) return "";
    const people = graphPeople();
    const groups = searchedGroups();
    const personStep = 58, groupStep = 72;
    const height = Math.max(390, 96 + people.length * personStep, 96 + groups.length * groupStep);
    const hubY = height / 2, personStart = Math.max(52, (height - (people.length - 1) * personStep) / 2);
    const groupStart = Math.max(52, (height - (groups.length - 1) * groupStep) / 2);
    const personY = new Map(people.map((person, index) => [person.subject_id, personStart + index * personStep]));
    const groupY = new Map(groups.map((group, index) => [groupKey(group), groupStart + index * groupStep]));
    const edges = [];
    for (const group of groups) {
      const y = groupY.get(groupKey(group));
      const kind = group.configured ? "target" : "group";
      edges.push(`<path class="graph-edge ${kind}" d="M 226 ${hubY} C 292 ${hubY}, 342 ${y}, 408 ${y}"></path>`);
    }
    for (const person of people) {
      const y = personY.get(person.subject_id);
      if (person.private_chat) edges.push(`<path class="graph-edge private" d="M 226 ${hubY} C 418 ${hubY}, 602 ${y}, 790 ${y}"></path>`);
      for (const id of groupIdsOf(person)) {
        const targetY = groupY.get(id);
        if (targetY === undefined) continue;
        edges.push(`<path class="graph-edge group" d="M 598 ${targetY} C 666 ${targetY}, 718 ${y}, 790 ${y}"></path>`);
      }
    }
    const groupNodes = groups.map((group) => svgGroup(group, groupY.get(groupKey(group)))).join("");
    const personNodes = people.map((person) => svgPerson(person, personY.get(person.subject_id))).join("");
    const profile = esc(data.profile_id || "当前运行实例");
    const summary = `${people.length} 位成员 · ${groups.length} 个群聊节点 · 按 V2 往来记录绘制`;
    $("graph-summary").textContent = summary;
    $("graph-empty").hidden = people.length > 0 || groups.length > 0;
    $("graph-empty").replaceChildren(node("strong", searchTerm ? "图谱中没有符合的往来" : "还没有可展示的关系记录"),
      node("p", searchTerm ? "试试成员名称、平台账号或群号。" : "当 V2 记录到私聊或群内互动后，成员节点会出现在这里。"));
    if (!people.length && !groups.length) return "";
    return `<svg class="relationship-graph-svg" viewBox="0 0 1040 ${height}" role="group" aria-label="${esc(summary)}">
      <desc>连线仅表示运行实例私聊往来、已配置群目标或群成员记录，不推断成员彼此关系。</desc>
      <text class="graph-column-label" x="44" y="27">运行实例</text><text class="graph-column-label" x="408" y="27">群聊空间</text><text class="graph-column-label" x="790" y="27">相识成员</text>
      ${edges.join("")}
      <g class="graph-hub"><rect x="44" y="${hubY - 31}" width="182" height="62" rx="7"></rect>
        <text class="hub-label" x="61" y="${hubY - 3}">V2 运行实例</text><text class="hub-sub" x="61" y="${hubY + 16}">${profile}</text></g>
      ${groupNodes}${personNodes}
    </svg>`;
  }
  function renderGraph() {
    $("relationship-graph").innerHTML = graphMarkup();
  }
  function updateGraphFilters() {
    document.querySelectorAll(".graph-filter").forEach((button) => {
      const active = button.dataset.graphScope === graphScope;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function renderGroups() {
    const list = $("groups-list");
    list.replaceChildren();
    const groups = allGroups().filter((group) => {
      if (!searchTerm) return true;
      return groupKey(group).toLocaleLowerCase().includes(searchTerm)
        || peopleInGroup(group, { honorSearch: false }).some(matchesSearch);
    });
    $("groups-result-count").textContent = `${groups.length} 个群`;
    if (!groups.length) {
      const empty = node("div", undefined, "empty-state");
      empty.append(node("strong", data ? searchTerm ? "没有符合的群聊记录" : "当前没有群聊目标或历史往来" : "正在读取群聊目录…"),
        node("p", data ? "群聊目标由运行实例配置；历史群内往来来自 V2 已记录的相识资料。" : ""));
      list.append(empty);
      renderGroupDetail(null);
      return;
    }
    groups.forEach((group) => {
      const id = groupKey(group);
      const card = node("button", undefined, "group-card");
      card.type = "button";
      card.setAttribute("aria-pressed", String(selectedGroupId === id));
      const info = node("span", undefined, "group-info");
      info.append(node("strong", `群 ${id}`),
        node("small", `${group.configured ? "当前目标" : "历史往来"}${group.account_id ? ` · 账号 ${group.account_id}` : ""}${group.bot_id ? ` · Bot ${group.bot_id}` : ""}`));
      const stats = node("span", undefined, "group-stats");
      stats.append(node("span", `${number(group.member_count)} 位相识成员`), node("span", `${number(group.msg_count)} 条消息`));
      card.append(info, stats);
      card.addEventListener("click", () => selectGroup(group));
      list.append(card);
    });
    const selectedGroup = groups.find((group) => groupKey(group) === selectedGroupId) || null;
    if (!selectedGroup) selectedGroupId = "";
    renderGroupDetail(selectedGroup);
  }
  function renderGroupDetail(group) {
    const panel = $("group-detail");
    panel.replaceChildren();
    if (!group) {
      const empty = node("div", undefined, "placeholder");
      empty.append(node("span", "02", "placeholder-mark"), node("h3", data ? "选择一个群聊" : "群聊信息暂不可用"),
        node("p", "查看群内已记录的相识成员及往来数量。"));
      panel.append(empty);
      return;
    }
    const id = groupKey(group);
    const members = peopleInGroup(group);
    const detail = node("div", undefined, "group-detail-inner");
    const head = node("header", undefined, "group-detail-head");
    const title = node("div");
    title.append(node("span", "GROUP SPACE", "eyebrow"), node("h3", `群 ${id}`),
      node("small", group.configured ? "群目标已在当前运行实例配置" : "历史群内往来记录；此群不是当前配置目标", "detail-subtitle"));
    head.append(title, badge(group.configured ? "当前目标" : "历史记录", group.configured ? "group" : ""));
    const metrics = node("div", undefined, "group-detail-metrics");
    const metric = (label, value) => { const cell = node("div"); cell.append(node("span", label), node("strong", value)); metrics.append(cell); };
    metric("相识成员", `${number(group.member_count)} 人`);
    metric("已记录消息", `${number(group.msg_count)} 条`);
    metric("账号 / Bot", group.account_id || group.bot_id ? `${group.account_id || "—"} / ${group.bot_id || "—"}` : "—");
    const memberSection = node("section", undefined, "detail-section");
    const memberHead = node("div", undefined, "group-members-head");
    memberHead.append(node("h4", "群内相识"), node("span", `${members.length} 人 · 点击成员看私聊权限`));
    const roster = node("div", undefined, "group-members");
    if (!members.length) {
      const empty = node("p", group.configured ? "当前没有可关联到目录的群成员记录。" : "当前目录中没有该群的成员明细。", "auth-empty");
      roster.append(empty);
    }
    members.forEach((person) => {
      const record = groupsOf(person)[id] || {};
      const button = node("button", undefined, "member-chip");
      button.type = "button";
      button.append(avatar(person), node("span", nameOf(person)),
        node("small", `${number(record.msg_count)} 条 · ${number(record.active_days)} 天`));
      button.addEventListener("click", () => {
        filter = "all";
        searchTerm = "";
        $("directory-search").value = "";
        $("clear-search").hidden = true;
        updateFilterButtons();
        switchTab("people");
        select(person);
      });
      roster.append(button);
    });
    memberSection.append(memberHead, roster);
    detail.append(head, metrics, memberSection);
    panel.append(detail);
  }

  function renderCounts() {
    const counts = data?.counts;
    $("count-total").textContent = counts ? String(number(counts.total)) : "—";
    $("count-private").textContent = counts ? String(number(counts.private_chat)) : "—";
    $("count-group").textContent = counts ? String(number(counts.group_member)) : "—";
    $("count-both").textContent = counts ? String(number(counts.both)) : "—";
    $("count-split").textContent = counts ? `${number(counts.private_chat)} · ${number(counts.group_member)} · ${number(counts.both)}` : "—";
    $("profile").textContent = data?.profile_id ?? "—";
    $("operator").textContent = data?.operator_name ?? "—";
    $("chip-all").textContent = String(number(counts?.total));
    $("chip-private").textContent = String(number(counts?.private_chat));
    $("chip-group").textContent = String(number(counts?.group_member));
    $("chip-both").textContent = String(number(counts?.both));
  }
  function updateFilterButtons() {
    document.querySelectorAll(".chip").forEach((button) => {
      const active = button.dataset.filter === filter;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }
  function renderAll() {
    renderCounts();
    renderGraph();
    renderPeople();
    renderGroups();
    renderDetail();
    updateGraphFilters();
    updateFilterButtons();
  }
  function renderDetail() {
    const panel = $("person-detail");
    panel.replaceChildren();
    if (!selected) {
      const empty = node("div", undefined, "placeholder");
      empty.append(node("span", "01", "placeholder-mark"), node("h3", "选择一位成员"),
        node("p", "查看往来详情、当前能力授权和可在本页调整的授权。"));
      panel.append(empty);
      return;
    }
    const person = selected;
    const card = node("div", undefined, "detail-card");
    const head = node("header", undefined, "detail-head");
    head.append(avatar(person));
    const title = node("div", undefined, "detail-title");
    const nameSource = person.name_basis === "administrator" ? "管理员称呼"
      : person.name_basis === "platform" ? "平台称呼" : "未设置称呼";
    title.append(node("h3", nameOf(person)), node("small", `账号 ${person.native_account_id ?? "未知"} · ${nameSource}`));
    head.append(title);
    const facts = node("dl", undefined, "detail-facts");
    const row = (label, value) => { const pair = node("div"); pair.append(node("dt", label), node("dd", value)); facts.append(pair); };
    row("往来类型", person.private_chat && person.group_member ? `私聊 · 群聊 ${groupIdsOf(person).length}`
      : person.private_chat ? "私聊" : person.group_member ? `群聊 ${groupIdsOf(person).length}` : "暂无记录");
    row("累计消息", `${number(person.total?.msg_count)} 条`);
    row("活跃天数", `${number(person.total?.active_days)} 天`);
    row("首次出现", shortTime(person.total?.first_seen));
    row("最近出现", shortTime(person.total?.last_seen));
    if (person.private_chat) row("私聊互动", `${number(person.private?.msg_count)} 条 / ${number(person.private?.active_days)} 天`);
    const contexts = node("section", undefined, "detail-section detail-contexts");
    const contextHead = node("div", undefined, "detail-section-head");
    contextHead.append(node("h4", "出现过的窗口"), node("small", "V2 相识目录记录"));
    const contextRows = node("div", undefined, "context-rows");
    if (person.private_chat) contextRows.append(contextBadge(`私聊 · ${number(person.private?.msg_count)} 条`, "private"));
    groupIdsOf(person).forEach((id) => {
      const button = node("button", `群 ${id}`, "context-group");
      button.type = "button";
      button.addEventListener("click", () => {
        const group = allGroups().find((item) => groupKey(item) === id);
        if (group) { switchTab("groups"); selectGroup(group); }
      });
      contextRows.append(button);
    });
    if (!contextRows.children.length) contextRows.append(contextBadge("还没有窗口记录"));
    contexts.append(contextHead, contextRows);
    card.append(head, facts, adminNameEditor(person), contexts, authorizationPanel(person));
    panel.append(card);
  }
  function personRouteKey(person) {
    return JSON.stringify([person.subject_id, person.platform, person.bot_id, person.account_id, person.role_id]);
  }
  function adminNameEditor(person) {
    const section = node("section", undefined, "detail-name-editor detail-section");
    const heading = node("div", undefined, "detail-section-head");
    heading.append(node("h4", "管理员称呼"));
    if (person.admin_nickname_updated_at) {
      heading.append(node("small", `更新于 ${shortTime(person.admin_nickname_updated_at)}`));
    }
    const label = node("label", undefined, "admin-name-field");
    const input = node("input", undefined, "admin-nickname-input");
    input.type = "text";
    input.maxLength = 64;
    input.value = person.admin_nickname || "";
    input.disabled = nicknameBusy;
    input.placeholder = "留空则使用平台称呼";
    input.setAttribute("aria-label", "管理员称呼");
    label.append(input);
    const save = node("button", nicknameBusy ? "保存中" : "保存称呼", "secondary admin-name-save");
    save.type = "button";
    save.disabled = nicknameBusy;
    save.addEventListener("click", () => setAdminName(person, input.value));
    section.append(heading, label, node("small", "留空后保存会清除管理员称呼，并恢复平台资料显示。", "admin-name-help"), save);
    return section;
  }
  async function setAdminName(person, nickname) {
    if (nicknameBusy) return;
    const routeKey = personRouteKey(person);
    const value = String(nickname);
    if (!pendingNicknameOperation || pendingNicknameOperation.routeKey !== routeKey
        || pendingNicknameOperation.value !== value) {
      pendingNicknameOperation = { routeKey, value,
        key: [person.subject_id, "name", Date.now().toString(36), Math.random().toString(36).slice(2, 8)].join(":") };
    }
    nicknameBusy = true;
    renderDetail();
    try {
      const result = unwrap(await bridge.apiPost(adminNameEndpoint, {
        operation_key: pendingNicknameOperation.key,
        subject_id: person.subject_id, platform: person.platform,
        bot_id: person.bot_id, account_id: person.account_id, role_id: person.role_id,
        native_account_id: person.native_account_id, admin_nickname: value,
        expected_revision: person.revision,
      }));
      const updated = { ...person, ...result };
      data.persons = data.persons.map((item) => personRouteKey(item) === routeKey ? updated : item);
      selected = updated;
      pendingNicknameOperation = null;
      notice(result.changed ? "管理员称呼已更新。" : "管理员称呼没有变化。");
      renderAll();
    } catch (error) {
      notice(localized(error).message, true);
      if (error?.code === "person_nickname_revision_conflict" && selected
          && personRouteKey(selected) === routeKey) {
        pendingNicknameOperation = null;
        await load();
      }
    }
    nicknameBusy = false;
    renderDetail();
  }
  function capabilityLabel(capability) { return CAPABILITY_LABELS[capability] || capability; }
  function scopeText(item) {
    if (!item.scope) return "—";
    const parts = [item.scope.native_scope_id ?? item.scope.kind];
    if (item.scope.account_id) parts.push(`账号 ${item.scope.account_id}`);
    return parts.join(" · ");
  }
  function authorizationRow(person, item) {
    const row = node("div", undefined, "auth-row");
    row.dataset.capability = item.capability;
    row.dataset.state = item.state;
    row.dataset.managedBy = item.managed_by;
    const head = node("div", undefined, "auth-head");
    head.append(node("strong", capabilityLabel(item.capability), "auth-name"),
      node("small", item.capability, "auth-code"),
      node("span", STATE_LABELS[item.state] || item.state, "auth-state state-" + item.state));
    const facts = [];
    if (item.tier) facts.push(`档位 ${item.tier}`);
    if (item.expires_at) facts.push(`到期 ${shortTime(item.expires_at)}`);
    else if (item.state === "active") facts.push("无期限");
    facts.push(`生效范围 ${scopeText(item)}`);
    row.append(head, node("small", facts.join(" · "), "auth-meta"));
    if (item.managed_by === "configuration") {
      row.append(node("p", "由运行实例配置签发：每次加载都会按配置重新写入；需在「宿主管理」的能力配置中调整。", "auth-origin configuration"));
    } else {
      const enabled = item.state !== "active";
      const control = node("button", enabled ? "重新授权" : "撤销授权", "secondary auth-toggle" + (enabled ? "" : " is-revoke"));
      control.type = "button";
      control.disabled = authBusy || !item.revocable;
      control.setAttribute("aria-label", `${enabled ? "重新授权" : "撤销授权"}：${capabilityLabel(item.capability)}，${nameOf(person)}`);
      control.addEventListener("click", () => configure(person, item, enabled));
      row.append(control);
    }
    return row;
  }
  function authorizationPanel(person) {
    const wrap = node("section", undefined, "detail-authorization");
    const heading = node("header");
    heading.append(node("h4", "能力授权"));
    const loaded = authorization[person.subject_id];
    if (authServer === "error") heading.append(node("span", "读取失败", "auth-load-state error"));
    else if (authServer === "loading" && !loaded) heading.append(node("span", "读取中", "auth-load-state"));
    wrap.append(heading);
    if (!loaded) {
      wrap.append(node("p", authServer === "error" ? "暂时读不到授权状态；目录往来资料仍可查看。" : "正在读取这个人的当前授权…", "muted auth-pending"));
      return wrap;
    }
    if (!loaded.items.length) {
      wrap.append(node("p", "这个人还没有单独签发或撤销过能力。实际准入还取决于运行实例默认值和角色配置。", "muted auth-empty"));
      return wrap;
    }
    wrap.append(node("p", loaded.companion ? "陪伴对象：对话回复与主动投递都生效。"
      : "授权按能力分别生效；对话回复与主动投递的状态互不替代。", "auth-summary"));
    const list = node("div", undefined, "auth-rows");
    loaded.items.forEach((item) => list.append(authorizationRow(person, item)));
    wrap.append(list);
    return wrap;
  }
  async function loadAuthorization(person) {
    const sequence = ++authSequence;
    authServer = "loading";
    renderDetail();
    try {
      const result = unwrap(await bridge.apiGet(authorizationEndpoint, { subject_id: person.subject_id }));
      if (sequence !== authSequence || selected?.subject_id !== person.subject_id) return;
      authorization = { ...authorization, [person.subject_id]: result };
      authServer = "ok";
    } catch (error) {
      if (sequence !== authSequence) return;
      authServer = "error";
      notice(localized(error).message, true);
    }
    renderPeople();
    renderDetail();
  }
  async function configure(person, item, enabled) {
    if (authBusy) return;
    authBusy = true;
    renderDetail();
    const operationKey = [person.subject_id, item.capability, enabled ? "on" : "off",
      Date.now().toString(36), Math.random().toString(36).slice(2, 8)].join(":");
    try {
      const result = unwrap(await bridge.apiPost(authorizationEndpoint, {
        operation_key: operationKey, subject_id: person.subject_id, capability: item.capability,
        enabled, expected_revision: item.policy_revision,
      }));
      authorization = { ...authorization, [person.subject_id]: result.status };
      authServer = "ok";
      notice(enabled ? "已重新读取并开启这项能力。" : "已撤销这项能力。");
    } catch (error) {
      notice(localized(error).message, true);
      if (error?.code === "authorization_revision_conflict" && selected?.subject_id === person.subject_id) {
        authBusy = false;
        await loadAuthorization(person);
      }
    }
    authBusy = false;
    renderPeople();
    renderDetail();
  }
  function select(person) {
    selected = person;
    authServer = "";
    renderPeople();
    renderDetail();
    if (person) loadAuthorization(person);
    else authSequence++;
  }
  function selectGroup(group) {
    selectedGroupId = groupKey(group);
    renderGroups();
  }
  function switchTab(next) {
    if (!["network", "people", "groups"].includes(next)) return;
    activeView = next;
    document.querySelectorAll(".tab").forEach((item) => {
      const active = item.dataset.tab === next;
      item.classList.toggle("active", active);
      item.setAttribute("aria-selected", String(active));
      item.tabIndex = active ? 0 : -1;
    });
    document.querySelectorAll(".view-panel").forEach((panel) => {
      const active = panel.id === "panel-" + next;
      panel.hidden = !active;
      panel.classList.toggle("active", active);
      if (active) { panel.classList.remove("is-entering"); void panel.offsetWidth; panel.classList.add("is-entering"); }
    });
  }
  function navigateToPerson(id) {
    const person = data?.persons.find((item) => item.subject_id === id);
    if (!person) return;
    filter = "all";
    updateFilterButtons();
    switchTab("people");
    select(person);
  }
  function navigateToGroup(id) {
    const group = allGroups().find((item) => groupKey(item) === id);
    if (!group) return;
    switchTab("groups");
    selectGroup(group);
  }
  function activateGraphNode(target) {
    const person = target?.closest?.("[data-person-id]");
    if (person) { navigateToPerson(person.dataset.personId); return; }
    const group = target?.closest?.("[data-group-id]");
    if (group) navigateToGroup(group.dataset.groupId);
  }
  async function load() {
    const sequence = ++requestSequence;
    const refresh = $("refresh");
    refresh.disabled = true;
    refresh.classList.add("is-loading");
    setSyncState("", "正在读取");
    try {
      const result = unwrap(await bridge.apiGet(endpoint, {}));
      if (sequence !== requestSequence) return;
      data = { ...result, persons: Array.isArray(result.persons) ? result.persons : [], groups: Array.isArray(result.groups) ? result.groups : [] };
      setSyncState("ready", "V2 数据已同步");
      notice("");
      selected = selected ? data.persons.find((person) => person.subject_id === selected.subject_id) || null : null;
      if (selected) {
        authorization = {};
        authServer = "loading";
      }
      const foundGroup = selectedGroupId && allGroups().some((group) => groupKey(group) === selectedGroupId);
      if (!foundGroup) selectedGroupId = "";
      renderAll();
      if (selected) loadAuthorization(selected);
    } catch (error) {
      if (sequence !== requestSequence) return;
      const failure = localized(error);
      data = null;
      selected = null;
      selectedGroupId = "";
      authorization = {};
      setSyncState("error", "读取未完成");
      renderAll();
      notice(failure.message, true);
    } finally {
      if (sequence === requestSequence) {
        refresh.disabled = false;
        refresh.classList.remove("is-loading");
      }
    }
  }

  document.querySelectorAll(".tab").forEach((item) => item.addEventListener("click", () => switchTab(item.dataset.tab)));
  document.querySelectorAll(".chip").forEach((item) => item.addEventListener("click", () => {
    filter = item.dataset.filter;
    updateFilterButtons();
    if (selected && !visiblePeople().some((person) => person.subject_id === selected.subject_id)) select(null);
    renderPeople();
  }));
  document.querySelectorAll(".graph-filter").forEach((item) => item.addEventListener("click", () => {
    graphScope = item.dataset.graphScope;
    updateGraphFilters();
    renderGraph();
  }));
  $("directory-search").addEventListener("input", (event) => {
    searchTerm = String(event.target.value || "").trim().toLocaleLowerCase();
    $("clear-search").hidden = !searchTerm;
    renderGraph(); renderPeople(); renderGroups();
    if (selected && !visiblePeople().some((person) => person.subject_id === selected.subject_id)) select(null);
  });
  $("clear-search").addEventListener("click", () => {
    $("directory-search").value = "";
    searchTerm = "";
    $("clear-search").hidden = true;
    renderGraph(); renderPeople(); renderGroups();
  });
  $("relationship-graph").addEventListener("click", (event) => activateGraphNode(event.target));
  $("relationship-graph").addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const target = event.target?.closest?.("[data-person-id], [data-group-id]");
    if (!target) return;
    event.preventDefault();
    activateGraphNode(target);
  });
  $("refresh").addEventListener("click", () => { notice(""); load(); });
  (async function start() {
    bridge = window.AstrBotPluginPage;
    if (!bridge) { setSyncState("error", "页面桥未连接"); notice(errors.dashboard_identity_required, true); return; }
    try { await bridge.ready(); await load(); }
    catch (error) { setSyncState("error", "读取未完成"); notice(localized(error).message, true); }
  })();
})();
