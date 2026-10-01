/* 相识详情页的「能力授权」面板。
 *
 * 这一页的行动逻辑跑在模块私有状态上，只能靠 vm 跑真实文件 + 假桥来驱动。
 * 夹具的职责是让「点开一个人真的会去读他的授权、点按钮真的会把参数发出去」，
 * 因为这一页最怕的两种失败都是静默的：
 *
 *   1. 面板把**配置派生的**授权画成可以撤销的按钮——撤销会被下一次加载复原，
 *      页面于是显示「已撤销」而能力还活着；
 *   2. 按钮发出去了，但 expected_revision 取错（取成 0、或取成别处的 revision），
 *      后端会以冲突拒绝，用户看到的是"点了没反应"。
 *
 * 所以断言落在**渲染出来的 HTML**与**真实请求参数**上，不落在布尔标志上。
 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../pages/关系与权限/app.js"), "utf8");
const endpoint = "acquaintance";
const authorization = endpoint + "/authorization";

/* 目录里的一位私聊用户：字段就是后端 ``PersonAcquaintanceDirectory._person`` 的那几个。 */
function person(subjectId, name, extra = {}) {
  return {
    subject_id: subjectId, native_account_id: subjectId, display_name: name, name_basis: "platform",
    platform: "qq-main", account_id: "account-a", role_id: "role-a", bot_id: "bot-a", revision: 3,
    private_chat: true, group_member: false,
    private: { msg_count: 12, active_days: 3, last_seen: "2026-09-30T10:00:00+00:00" },
    groups: {},
    total: { msg_count: 12, active_days: 3,
             first_seen: "2026-09-01T10:00:00+00:00", last_seen: "2026-09-30T10:00:00+00:00" },
    updated_at: "2026-09-30T10:00:00+00:00",
    ...extra,
  };
}

function directory(persons, groups = []) {
  const privateCount = persons.filter((item) => item.private_chat).length;
  const groupCount = persons.filter((item) => item.group_member).length;
  const bothCount = persons.filter((item) => item.private_chat && item.group_member).length;
  return { installation_id: "inst", profile_id: "profile-1", operator_name: "admin",
    persons, groups, counts: { total: persons.length, private_chat: privateCount,
      group_member: groupCount, both: bothCount, private_only: privateCount - bothCount,
      group_only: groupCount - bothCount },
    page_managed_capabilities: ["conversation.reply", "message.delivery", "proactive.contact"] };
}

/* 一行授权。后端 ``PersonAuthorizationManagement._row`` 的形状。 */
function grantRow(capability, changes = {}) {
  return { capability, state: "active", managed_by: "page", revocable: true, tier: "standard",
    expires_at: null, valid_from: "2026-09-30T10:00:00+00:00",
    grant_id: "acquaintance-grant:" + capability, grant_revision: 1,
    scope: { kind: "private", native_scope_id: "subject-1", account_id: "login-a" },
    policy_revision: 7, ...changes };
}

function status(subjectId, items, companion = false) {
  const counts = {};
  for (const item of items) counts[item.state] = (counts[item.state] || 0) + 1;
  return { subject_id: subjectId, items, companion, counts };
}

/* ── 一个够用的 DOM 桩 ────────────────────────────────────────────────
   页面按 id 取固定节点、按标签造元素，并给卡片挂 click。真实 DOM 里这些
   都有语义，桩里只要让它们可断言即可：把元素按 id 记下来，事件处理器留着，
   测试从**真实注册的入口**驱动，而不是绕开接线直接调私有函数。 */
function element(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], textContent: "", className: "",
    hidden: false, disabled: false, type: "", dataset: {}, style: { setProperty() {} },
    isConnected: true,
    classList: {
      add(...tokens) { node.className = [...new Set([...node.className.split(/\s+/).filter(Boolean), ...tokens])].join(" "); },
      remove(...tokens) { node.className = node.className.split(/\s+/).filter((item) => item && !tokens.includes(item)).join(" "); },
      toggle(token, force) {
        const enabled = force === undefined ? !this.contains(token) : Boolean(force);
        if (enabled) this.add(token); else this.remove(token);
        return enabled;
      },
      contains(token) { return node.className.split(/\s+/).includes(token); },
    },
    setAttribute(name, value) { this[name] = String(value); },
    getAttribute(name) { return this[name]; },
    addEventListener(type, handler) { this.handlers = this.handlers || {}; this.handlers[type] = handler; },
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = items; },
    closest() { return this; },
    querySelector() { return null; },
  };
  return node;
}

function harness({ persons, groups = [], authorizations = {}, post } = {}) {
  const requests = [];
  const byId = new Map();
  const tabs = [element("button"), element("button"), element("button")];
  const chips = [element("button"), element("button"), element("button"), element("button")];
  const graphFilters = [element("button"), element("button"), element("button")];
  const panels = [element("section"), element("section"), element("section")];
  tabs.forEach((tab, index) => { tab.dataset.tab = ["network", "people", "groups"][index]; });
  chips.forEach((chip, index) => { chip.dataset.filter = ["all", "private", "group", "both"][index]; });
  graphFilters.forEach((filter, index) => { filter.dataset.graphScope = ["all", "private", "group"][index]; });
  panels.forEach((panel, index) => { panel.id = ["panel-network", "panel-people", "panel-groups"][index]; });
  tabs.forEach((tab, index) => { tab.id = ["tab-network", "tab-people", "tab-groups"][index]; });
  for (const id of ["notice", "sync-state", "profile", "operator", "count-total", "count-private",
                    "count-group", "count-both", "count-split", "graph-summary", "graph-empty",
                    "relationship-graph", "directory-search", "clear-search", "people-result-count",
                    "people-grid", "person-detail", "groups-result-count", "groups-list", "group-detail",
                    "refresh", "chip-all", "chip-private", "chip-group", "chip-both"]) {
    byId.set(id, element(id === "refresh" ? "button" : "div"));
  }
  byId.get("directory-search").value = "";
  const document = {
    getElementById: (id) => byId.get(id) || null,
    createElement: (tag) => element(tag),
    querySelectorAll: (selector) => selector === ".tab" ? tabs : selector === ".chip" ? chips
      : selector === ".graph-filter" ? graphFilters : selector === ".view-panel" ? panels : [],
    addEventListener() {},
  };
  const window = {
    AstrBotPluginPage: {
      ready: () => Promise.resolve({ pluginName: "astrbot_plugin_private_companion_v2" }),
      apiGet: (route, params) => new Promise((resolve, reject) => {
        requests.push({ method: "GET", route, params, resolve, reject });
      }),
      apiPost: (route, body) => new Promise((resolve, reject) => {
        requests.push({ method: "POST", route, body, resolve, reject });
      }),
    },
    document,
  };
  vm.runInNewContext(source, { window, document, console, Intl, Date, JSON, Math, Number, Object,
    Array, String, Set, Map, Boolean, Error, Promise, setTimeout, clearTimeout });
  const answers = {
    [endpoint]: directory(persons || [], groups),
    ...Object.fromEntries(Object.entries(authorizations).map(([subject, value]) =>
      [authorization + "|" + subject, value])),
  };
  const settle = async () => { for (let i = 0; i < 12; i++) await new Promise((r) => setImmediate(r)); };
  const harness = {
    requests, document, byId,
    element: (id) => byId.get(id),
    settle,
    /* 回答在飞的请求。目录与授权都按路由 + 参数分发，写请求交给用例的 post。
       顺序要紧：**先 settle 让请求发出来，再 answer**——answer 只处理已经在飞的
       请求，反过来写会让页面永远停在「正在读取」。 */
    answer(read) {
      for (const request of requests.slice()) {
        if (request.answered) continue;
        if (read && !read(request)) continue;
        request.answered = true;
        const value = request.method === "GET"
          ? answers[request.route + (request.params?.subject_id ? "|" + request.params.subject_id : "")]
          : post?.(request);
        if (value === undefined) continue;
        request.resolve(value);
      }
    },
    card: (name) => cardFor(byId.get("people-grid"), name),
  };
  harness.send = async (read) => { await settle(); harness.answer(read); await settle(); };
  return harness;
}

/* 卡片是 button 且它的子树里含这个名字：桩没有 parentElement，所以直接遍历。 */
function cardFor(grid, name) {
  const stack = [...grid.children];
  while (stack.length) {
    const item = stack.shift();
    if (item.tagName === "BUTTON" && item.handlers?.click && flat(item).includes(name)) return item;
    stack.push(...(item.children || []));
  }
  return null;
}

function text(node) {
  return [node.textContent, ...(node.children || []).map(text)];
}

/* 桩树的文本拍平：跨 realm 的数组原型与本 realm 不同，比较前先变成一段字符串。 */
function flat(node) {
  return text(node).flat(Infinity).filter(Boolean).join(" ");
}

/* 把整棵桩树打平成一段可断言的 HTML 形态：类名 + 数据属性 + 文本 + 禁用态。
   递归到底，因为面板是嵌在详情卡里的（只拍一层会漏掉授权行）。 */
function markup(node) {
  const attributes = [["class", node.className],
    ["data-capability", node.dataset?.capability], ["data-state", node.dataset?.state],
    ["data-managed-by", node.dataset?.managedBy]]
    .filter(([, value]) => value !== undefined && value !== "")
    .map(([name, value]) => ` ${name}="${value}"`).join("");
  const own = node.textContent ? node.textContent : "";
  const inner = (node.children || []).map(markup).join("");
  return `<${node.tagName.toLowerCase()}${attributes}${node.disabled ? " disabled" : ""}>${own}${inner}</${node.tagName.toLowerCase()}>`;
}

async function open(h, name) {
  await h.send((request) => request.route === endpoint);
  const grid = h.element("people-grid");
  const card = cardFor(grid, name);
  const seen = grid.children.map((item) => item.tagName + "/" + item.className).join(",");
  assert.ok(card?.handlers?.click,
    "目录里应当有 " + name + " 的卡片（grid=" + grid.children.length + " 个子节点：" + seen + "）");
  card.handlers.click();
  /* 点开一个人会去读他的授权：同一套「先发出来、再回答」。 */
  await h.send((request) => request.route === authorization);
  return h.element("person-detail");
}

function tree(node, depth = 0) {
  return [node.tagName + "." + node.className + (node.handlers?.click ? "[click]" : "")
    + (node.textContent ? "(" + node.textContent + ")" : ""),
    ...(node.children || []).map((child) => "  ".repeat(depth + 1) + tree(child, depth + 1))].join("\n");
}

test("面板为每一项能力画一行，状态取自服务端读回的那一份", async () => {
  const people = [person("subject-1", "阿澈")];
  const h = harness({ persons: people, authorizations: { "subject-1": status("subject-1", [
    grantRow("conversation.reply", { managed_by: "configuration", revocable: false,
      grant_id: "astrbot-staging-grant:conversation.reply" }),
    grantRow("proactive.contact", { state: "revoked" }),
  ]) } });
  const detail = await open(h, "阿澈");
  const html = markup(detail);
  /* 目录里那一行仍然是同一次请求，参数原样：只加读取，不改契约。 */
  const directoryRequest = h.requests.find((item) => item.route === endpoint);
  assert.deepEqual(Object.keys(directoryRequest.params), []);
  assert.match(html, /data-capability="conversation\.reply"[^>]*data-state="active"[^>]*data-managed-by="configuration"/);
  /* 撤销过就说撤销过，不是「关」也不是空白：那是记录里的事实。 */
  assert.match(html, /data-capability="proactive\.contact"[^>]*data-state="revoked"/);
  assert.match(JSON.stringify(text(detail)), /对话回复/);
  assert.match(JSON.stringify(text(detail)), /已撤销/);
  /* 一项配置派生的授权不当场改名成「没有授权」：它是生效的。 */
  assert.match(JSON.stringify(text(detail)), /已生效/);
});

test("配置派生的那一行没有撤销按钮，并说清去哪里改", async () => {
  const people = [person("subject-1", "阿澈")];
  const h = harness({ persons: people, authorizations: { "subject-1": status("subject-1", [
    grantRow("conversation.reply", { managed_by: "configuration", revocable: false,
      grant_id: "astrbot-staging-grant:conversation.reply" }),
  ]) } });
  const detail = await open(h, "阿澈");
  const html = markup(detail);
  assert.doesNotMatch(html, /撤销授权/, "配置派生的行不许出现撤销控件");
  const flat = JSON.stringify(text(detail));
  /* 不是笼统的「只读」：要说清它由运行实例配置签发、改哪里。 */
  assert.match(flat, /运行实例配置签发/);
  assert.match(flat, /每次加载都会按配置重新写入/);
  /* 本页拥有的那一行才有控件，并且按钮上写着它真的会做什么。 */
  const owned = harness({ persons: people, authorizations: { "subject-1": status("subject-1", [
    grantRow("proactive.contact"),
  ]) } });
  const ownedDetail = await open(owned, "阿澈");
  assert.match(markup(ownedDetail), /撤销授权/);
  assert.doesNotMatch(JSON.stringify(text(ownedDetail)), /运行实例配置签发/);
});

test("管理员称呼写入绑定目录路由与卡片 revision，空值清除并恢复平台名称", async () => {
  const people = [person("subject-1", "平台昵称")];
  let revision = 3;
  const h = harness({ persons: people, authorizations: { "subject-1": status("subject-1", []) },
    post: (request) => {
      revision += 1;
      return { status: "ok", data: { replayed: false, operation_id: "name-op",
        subject_id: request.body.subject_id, admin_nickname: request.body.admin_nickname || null,
        admin_nickname_updated_at: "2026-10-01T10:00:00+00:00",
        display_name: request.body.admin_nickname || "平台昵称",
        name_basis: request.body.admin_nickname ? "administrator" : "platform",
        revision, changed: true } };
    } });
  const detail = await open(h, "平台昵称");
  const input = findAll(detail, "admin-nickname-input")[0];
  assert.ok(input, "成员详情应显示称呼编辑框");
  input.value = "小月亮";
  findControl(detail, "保存称呼").handlers.click();
  await h.send((request) => request.method === "POST");
  const first = h.requests.find((request) => request.method === "POST");
  assert.equal(first.route, "acquaintance/admin-name");
  assert.deepEqual(JSON.parse(JSON.stringify(first.body)), { operation_key: first.body.operation_key,
    subject_id: "subject-1", platform: "qq-main", bot_id: "bot-a", account_id: "account-a",
    role_id: "role-a", native_account_id: "subject-1", admin_nickname: "小月亮", expected_revision: 3 });
  assert.match(flat(h.element("person-detail")), /小月亮/);
  assert.match(flat(h.element("person-detail")), /管理员称呼/);

  const clearInput = findAll(h.element("person-detail"), "admin-nickname-input")[0];
  clearInput.value = "";
  findControl(h.element("person-detail"), "保存称呼").handlers.click();
  await h.send((request) => request.method === "POST" && request.body.expected_revision === 4);
  const clear = h.requests.filter((request) => request.method === "POST")[1];
  assert.equal(clear.body.admin_nickname, "");
  assert.equal(clear.body.expected_revision, 4);
  assert.match(flat(h.element("person-detail")), /平台昵称/);
});

test("切换发出的就是这一项、这个人、这一次读到的 revision", async () => {
  const people = [person("subject-1", "阿澈")];
  const h = harness({ persons: people, authorizations: { "subject-1": status("subject-1", [
    grantRow("proactive.contact", { policy_revision: 11 }),
  ]) } });
  const detail = await open(h, "阿澈");
  const control = findControl(detail, "撤销授权");
  assert.ok(control?.handlers?.click, "应当有一个撤销控件");
  control.handlers.click();
  await h.settle();
  const written = h.requests.find((item) => item.method === "POST");
  assert.ok(written, "点击必须真的发出写请求");
  assert.equal(written.route, authorization);
  assert.equal(written.body.subject_id, "subject-1");
  assert.equal(written.body.capability, "proactive.contact");
  assert.equal(written.body.enabled, false);
  /* revision 必须来自**这一次读到的**那一行：取错就会被后端以冲突拒绝，
     用户看到的是"点了没反应"。 */
  assert.equal(written.body.expected_revision, 11);
  assert.equal(typeof written.body.operation_key, "string");
  assert.ok(written.body.operation_key.includes("subject-1"));
});

test("写回的是服务端返回的状态，页面不自己改本地副本", async () => {
  const people = [person("subject-1", "阿澈")];
  const h = harness({ persons: people, authorizations: { "subject-1": status("subject-1", [
    grantRow("proactive.contact"),
  ]) }, post: () => ({ status: "ok", data: { replayed: false, operation_id: "op-1",
    status: status("subject-1", [grantRow("proactive.contact", { state: "revoked",
      policy_revision: 12, grant_revision: 2 })]) } }) });
  const detail = await open(h, "阿澈");
  findControl(detail, "撤销授权").handlers.click();
  await h.send((request) => request.method === "POST");
  const html = markup(h.element("person-detail"));
  assert.match(html, /data-capability="proactive\.contact"[^>]*data-state="revoked"/);
  /* 新的 revision 已经就位：下一次点击用的是 12，不是上一次的 7。 */
  const control = findControl(h.element("person-detail"), "重新授权");
  assert.ok(control, "撤销之后这一行应当给出开启控件");
});

test("一项授权都没有的人得到一句说明，而不是一排空行", async () => {
  const people = [person("subject-1", "阿澈")];
  const h = harness({ persons: people, authorizations: { "subject-1": status("subject-1", []) } });
  const detail = await open(h, "阿澈");
  const flat = JSON.stringify(text(detail));
  assert.match(flat, /还没有单独签发或撤销过能力/);
  /* 空态不能说成"他什么都不能"：准入还有运行实例里的默认口径，页面读不到那一层。 */
  assert.match(flat, /实际准入还取决于运行实例默认值和角色配置/);
  assert.doesNotMatch(flat, /不能接收消息/);
  assert.doesNotMatch(markup(detail), /data-capability=/, "空态不许画成一排空行");
});

test("陪伴对象标记只在两项都生效时出现", async () => {
  const people = [person("subject-1", "阿澈"), person("subject-2", "小满"), person("subject-3", "阿岚")];
  const both = [grantRow("conversation.reply", { managed_by: "configuration", revocable: false }),
                grantRow("message.delivery", { managed_by: "configuration", revocable: false })];
  const half = [grantRow("conversation.reply", { managed_by: "configuration", revocable: false })];
  const h = harness({ persons: people, authorizations: {
    "subject-1": status("subject-1", both, true),
    "subject-2": status("subject-2", half, false),
    "subject-3": status("subject-3", [], false),
  } });
  const detail = await open(h, "阿澈");
  assert.match(flat(detail), /陪伴对象：对话回复与主动投递都生效/);
  /* 标记是**逐卡**的：断言落在每个节点上，而不是"整棵树里出现过这个词"。 */
  const badges = findAll(h.element("people-grid"), "badge companion");
  assert.equal(badges.length, 1, "列表上只该有一个人被标记为陪伴对象");
  assert.deepEqual(flat(badges[0]).split(" ").filter((item) => item === "陪伴对象"), ["陪伴对象"]);
  /* 另一个人只有对话权限：他自己的卡片上不能出现完整陪伴对象标记。 */
  const other = cardFor(h.element("people-grid"), "小满");
  other.handlers.click();
  await h.send((request) => request.route === authorization);
  const otherDetail = h.element("person-detail");
  assert.doesNotMatch(markup(otherDetail), /class="badge companion"/);
  assert.doesNotMatch(flat(otherDetail), /陪伴对象：对话回复/);
});

test("关系网和私聊、群聊视图按 V2 记录互相跳转", async () => {
  const member = person("subject-1", "阿澈", {
    group_member: true,
    groups: {
      "1001": { msg_count: 8, active_days: 3, last_seen: "2026-09-30T10:00:00+00:00" },
      "1002": { msg_count: 2, active_days: 1, last_seen: "2026-09-28T10:00:00+00:00" },
    },
    total: { msg_count: 22, active_days: 5,
      first_seen: "2026-09-01T10:00:00+00:00", last_seen: "2026-09-30T10:00:00+00:00" },
  });
  const h = harness({ persons: [member], groups: [
    { group_id: "1001", bot_id: "bot-a", account_id: "login-a", member_count: 1, msg_count: 8 },
  ], authorizations: { "subject-1": status("subject-1", []) } });
  await h.send((request) => request.route === endpoint);

  const graph = h.element("relationship-graph");
  assert.match(graph.innerHTML, /data-group-id="1001"[^]*已配置群目标/);
  assert.match(graph.innerHTML, /data-group-id="1002"[^]*历史群内记录/);
  assert.match(graph.innerHTML, /class="graph-edge group"/);
  assert.match(graph.innerHTML, /不推断成员彼此关系/);
  assert.equal(h.element("count-total").textContent, "1");
  assert.equal(h.element("count-both").textContent, "1");

  const groupTarget = { dataset: { groupId: "1001" }, closest(selector) {
    return selector === "[data-group-id]" ? this : null;
  } };
  graph.handlers.click({ target: groupTarget });
  assert.equal(h.document.querySelectorAll(".tab")[2].getAttribute("aria-selected"), "true");
  assert.match(flat(h.element("group-detail")), /群 1001/);
  const memberLink = findAll(h.element("group-detail"), "member-chip")[0];
  assert.ok(memberLink?.handlers?.click, "群成员应当可打开私聊与权限详情");
  memberLink.handlers.click();
  await h.send((request) => request.route === authorization);
  assert.equal(h.document.querySelectorAll(".tab")[1].getAttribute("aria-selected"), "true");
  assert.match(flat(h.element("person-detail")), /阿澈/);

  const contextGroup = findAll(h.element("person-detail"), "context-group").find((item) => flat(item).includes("1001"));
  assert.ok(contextGroup?.handlers?.click, "成员详情中的群记录应当可返回对应群详情");
  assert.doesNotThrow(() => contextGroup.handlers.click());
  assert.equal(h.document.querySelectorAll(".tab")[2].getAttribute("aria-selected"), "true");
  assert.match(flat(h.element("group-detail")), /群 1001/);

  const historicCard = findAll(h.element("groups-list"), "group-card").find((item) => flat(item).includes("1002"));
  assert.ok(historicCard?.handlers?.click, "历史群即使不在当前运行实例目标里也应可查看");
  historicCard.handlers.click();
  assert.match(flat(h.element("group-detail")), /历史群内往来记录/);
});

/* 按类名找节点：徽章是逐卡渲染的，断言要落在每个节点上，
   而不是落在"整棵树里出现过这个词"——后者读不出是哪一张卡。 */
function findAll(node, className) {
  const found = [];
  const stack = [node];
  while (stack.length) {
    const item = stack.shift();
    if (item.className === className) found.push(item);
    stack.push(...(item.children || []));
  }
  return found;
}

function findControl(node, label) {
  const stack = [node];
  while (stack.length) {
    const item = stack.shift();
    if (item.tagName === "BUTTON" && flat(item).includes(label)) return item;
    stack.push(...(item.children || []));
  }
  return null;
}
