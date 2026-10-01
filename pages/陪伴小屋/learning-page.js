/* 陪伴小屋 · 学习与反思（培育轨道）
 *
 * 这一页管的是「角色自己长出来的技能与长期目标」：从哪条来源提出、谁确认过、
 * 现在在什么阶段、下一步能做什么、有哪些进展等着你过目。
 *
 * 为什么又是新一套版式：
 *   记忆页的轴是生命周期（一条事实的四种归宿），联系页的轴是一天（24 格的节律），
 *   而这一域的轴是**有向推进**——proposed → active ⇄ paused → achieved，
 *   任何状态都能 retired。所以主体是一条轨道：左起"提出"，右到"达成"或"归档"，
 *   每张卡停在自己的位置上。状态不是标签，是坐标。
 *
 * 三条查出来的契约，直接决定了这一页不能自己拼按钮：
 *
 * ① **动作由后端给。** `RoleGrowthManagement._project()` 按当前状态算出 `actions`
 *    列表（`management.py:85-117`），且"来源还能不能读"会进一步收窄它：
 *    来源不可用时 `confirm`/`revise`/`pause`/`resume`/`complete` 全部消失，
 *    只剩 `withdraw`/`retire`。所以页面上每一个动作按钮必须是后端给的，
 *    自己按状态推断会给出一个后端一定拒绝的按钮。
 *
 * ② **来源过期时连标题都读不出来。** `_project()` 在 `unavailable is None` 之外
 *    把 `title`/`description`/`progress_note` 一律置 `null`。
 *    这不是"字段缺失"，是设计：读不到来源就不该把内容摊出来。
 *    页面必须把这个 null 说成「来源已不可读取」，而不是显示成空白卡片。
 *
 * ③ **权限开关管的是「能不能读写」，不是「发不发」。**
 *    `role.growth.read` / `role.growth.propose` 两个 window 层布尔，
 *    而 `proposals_enabled` 在 `read_enabled` 关闭时会被后端强制跟成同一份判定
 *    （`access_management.py:29-31`）——页面上要照实反映这个从属关系。
 *
 * 读写出口：
 *   读  GET  {role.growth_api}                     列表（state/kind/limit/after_id）
 *   读  GET  {role.growth_api}/progress            待审阅的进展
 *   写  POST {role.growth_api}/command             propose / confirm / pause / resume /
 *                                                  complete / retire / withdraw / revise / configure
 *   写  POST {role.growth_api}/progress/command    accept / reject
 *   权限在列表响应的 access 里一并回来（read 已 merge 进 list，见 growth_api.py:78-80）
 *
 * 动效分两层：
 *   克制的功能动效——轨道推进、卡片移出、保存确认；
 *   场景化重头戏——一条记录的阶段位移（状态变化时卡片沿轨道滑到新位置）、
 *   审阅队列的逐个落位、来源凭证的失效褪色。
 *   prefers-reduced-motion 下压时长到瞬时终态，信息不丢。
 */
"use strict";
window.CompanionLearningPage = (() => {
  const HOST = "astrbot_plugin_private_companion_v2";
  const PREFIX = "/" + HOST + "/";
  const STORE = "companion-learning-page-v1:";
  /* 五个阶段按推进方向排，轨道就按这个顺序画。
     `retired` 不在主线末端——它是从任何位置都能去的旁支，所以单独一条支路。 */
  const STAGES = [
    {key:"proposed", label:"提出", tone:"lea-proposed",
     hint:"由来源提出，等你确认"},
    {key:"active",   label:"进行中", tone:"lea-active",
     hint:"已确认，正在推进"},
    {key:"paused",   label:"暂停",  tone:"lea-paused",
     hint:"暂时停下，可随时继续"},
    {key:"achieved", label:"达成",  tone:"lea-achieved",
     hint:"目标已完成"},
  ];
  const RETIRED = {key:"retired", label:"归档", tone:"lea-retired"};
  const STATE_BY_KEY = Object.fromEntries([...STAGES, RETIRED].map(s => [s.key, s]));
  const KIND_LABEL = {skill:"技能", goal:"目标"};
  /* 动作文案。**准入状态不写在这里**——那由后端的 actions 决定，
     这里只负责把码翻译成人话，以及说明这个动作会带来什么后果。 */
  const ACTIONS = {
    confirm:  {label:"确认",   kind:"primary", note:"确认后进入进行中。"},
    resume:   {label:"继续",   kind:"primary", note:"从暂停恢复到进行中。"},
    pause:    {label:"暂停",   kind:"",        note:"暂停后不再计入日程参考，可随时继续。"},
    complete: {label:"已完成", kind:"primary", note:"只对目标开放；完成后进入达成。"},
    revise:   {label:"修订",   kind:"",        note:"改动标题、描述与进展，会生成新版本。"},
    withdraw: {label:"撤回",   kind:"quiet",   note:"只对未确认的记录开放；撤回后归档。"},
    retire:   {label:"归档",   kind:"quiet",   note:"归档后不再出现在活跃列表，记录保留。"},
  };
  const REVIEW_ACTIONS = {
    accept: {label:"采纳",   kind:"primary", note:"采纳后这条进展写进目标。"},
    reject: {label:"不采纳", kind:"quiet",   note:"不采纳也会记下这次审阅。"},
  };
  /* 来源失效的码。后端把它们放在 unavailable_reason 上；
     这一页只需把它翻译成"为什么读不出来"，不参与判定。 */
  const errors = {
    dashboard_identity_required:"请从已登录的 AstrBot 管理界面打开陪伴小屋。",
    staging_not_initialized:"V2 数据尚未加载。请先在账号与会话中加载已初始化的配置，再刷新。",
    staging_host_terminated:"V2 宿主已停止，请重新打开拓展页。",
    core_access_required:"当前账号没有成长记录权限。",
    binding_revoked:"管理账号的授权已撤销。", binding_rebound:"管理账号的绑定已变化，请重新进入。",
    relationship_required:"这个对象还没有建立可读写的关系，请先在关系与权限页建立。",
    growth_query_invalid:"列表筛选条件不被接受，请更新页面后重试。",
    growth_command_invalid:"这条成长指令与接口不匹配，未做任何写入。",
    growth_progress_query_invalid:"审阅列表的查询条件不被接受，请刷新后重试。",
    growth_progress_command_invalid:"这条审阅指令与接口不匹配，未做任何写入。",
    growth_request_invalid:"请求与当前接口不匹配，请更新页面后重试。",
    growth_configuration_invalid:"权限开关只接受布尔值。",
    growth_record_unavailable:"这条记录已不在当前授权范围。",
    growth_revision_conflict:"记录已有新版本，已读取最新值。",
    growth_operation_conflict:"这个操作标识已经用于另一份内容，未重复写入。",
    growth_scope_changed:"当前对象、角色或绑定已变化，请重新读取。",
    growth_transition_invalid:"当前状态不接受这个动作，已刷新可用动作。",
    growth_source_unavailable:"这条记录的原来源已不可读取，内容暂不展示。",
    growth_source_expired:"原来源已过期。",
    growth_source_revoked:"原来源已撤回。",
    source_unavailable:"原来源不可读取。", source_expired:"原来源已过期。", source_revoked:"原来源已撤回。",
    source_dependency_expired:"原来源的依赖已过期。",
    growth_review_unavailable:"这条审阅依据已不可读取，只能不采纳。",
    growth_review_conflict:"这条审阅已有结论，已刷新。",
    growth_review_missing:"这条审阅已不在待处理列表。",
    unauthorized:"当前对象尚未获得这项权限。",
    permission_denied:"当前对象尚未获得这项权限。",
    bridge_unavailable:"页面还没有接上 AstrBot。若这是从管理界面打开的插件页，刷新一次通常就好；若反复出现，请确认插件已启用。",
    bridge_timeout:"未收到服务确认，请刷新核对。",
    invalid_response:"服务返回的数据不完整，请刷新核对。",
  };
  const CODE = /^[a-z][a-z0-9_]{2,60}$/;
  const denied = new Set(["dashboard_identity_required","core_access_required","binding_revoked",
    "binding_rebound","staging_host_terminated","relationship_required"]);
  const e = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const problem = code => Object.assign(new Error(errors[code] || (code ? "需要核对：" + code : "暂无具体原因")), {code});
  const reason = code => errors[code] || (code ? "需要核对：" + code : "暂无具体原因");
  const when = value => {
    if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) return "时间未知";
    return new Date(value).toLocaleString("zh-CN", {hour12:false, month:"numeric", day:"numeric",
      hour:"2-digit", minute:"2-digit"});
  };
  const ICON = {
    track:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 17V7M12 17V4M19 17v-6"/><path d="M3 20h18"/></svg>',
    review:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="13" rx="2"/><path d="M8 9h8M8 13h5"/><path d="m9 20 3-3 3 3"/></svg>',
    source:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h16M4 18h9"/><circle cx="18" cy="18" r="2.4"/></svg>',
    gate:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>',
    refresh:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12a7 7 0 1 1-2.1-5"/><path d="M19 4v4h-4"/></svg>',
    check:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7"/></svg>',
    alert:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5M12 16h.01"/></svg>',
    close:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="m6 6 12 12M18 6 6 18"/></svg>',
    sourceKey:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="12" r="3.4"/><path d="M11.5 12H20M17 12v3.4"/></svg>',
  };
  let root = null, bridge = null, version = 0, data = null;

  function blank() {
    return {view:"track",
      path:"", profileId:"", operatorName:"",
      items:[], cursor:"", next:null, stateFilter:"", kindFilter:"",
      reviews:[], reviewCursor:"", reviewNext:null,
      detailId:null, detail:null,
      access:null, accessToken:"",
      form:null, busy:false, loading:false, loadingReviews:false, writing:false, ready:false,
      notice:"", error:false, entered:new Set(), confirm:null};
  }
  /* 插件相对路径。目录给的是绝对地址，交给桥之前切掉插件目录名——
     带上它宿主会拼两次，整族 404。 */
  function rel(absolute) {
    if (typeof absolute !== "string" || !absolute.startsWith(PREFIX)) throw problem("invalid_response");
    const route = absolute.slice(PREFIX.length);
    if (!route || /[?#%\\:]/.test(route) || route.split("/").some(p => !p || p === "." || p === "..")) {
      throw problem("invalid_response");
    }
    return route;
  }
  async function bounded(promise) {
    let timeout;
    try {
      return await Promise.race([promise, new Promise((_, reject) => {
        timeout = setTimeout(() => reject(problem("bridge_timeout")), 15000);
      })]);
    } finally { clearTimeout(timeout); }
  }
  async function api(method, path, body) {
    const response = await bounded(method === "GET" ? bridge.apiGet(path, body) : bridge.apiPost(path, body));
    const wrapped = ["ok","error"].includes(response?.status) ? response
      : ["ok","error"].includes(response?.data?.status) ? response.data : null;
    if (wrapped?.status === "error") throw problem(CODE.test(wrapped.data?.code || wrapped.message || "")
      ? (wrapped.data?.code || wrapped.message) : "invalid_response");
    const value = wrapped ? wrapped.data : response;
    if (!value || typeof value !== "object") throw problem("invalid_response");
    return value;
  }
  function live(ticket) { return ticket === version && root?.isConnected; }
  function notice(message, error = false) { data.notice = message; data.error = error; }
  let opCounter = 0;
  function operationKey(kind, id) {
    return STORE + (data.path || "") + ":" + kind + ":" + (id || "") + ":" + opCounter++;
  }
  function item(id) { return data.items.find(row => row.growth_id === id) || null; }

  /* ---- 读 ------------------------------------------------------------- */
  function listQuery(afterId = "") {
    return {
      ...(afterId ? {after_id: afterId} : {}),
      ...(data.stateFilter ? {state: data.stateFilter} : {}),
      ...(data.kindFilter ? {kind: data.kindFilter} : {}),
    };
  }
  /* 读与写各有各的标志，而且**读的护栏不能看写的标志**。
     这是一个踩过两次的坑：写操作在开始时置上忙标志，结束时调用 load() 刷新，
     而 load() 的护栏正是那个忙标志——于是它立即早退，忙标志再也没人清，
     整页从此卡住：动作发出去了、结果也回来了，界面却停在原地。
     两个标志职责不同：loading 管"正在读"，writing 管"正在写"。 */
  async function load() {
    if (!data.path || data.loading) return;
    const ticket = version;
    data.loading = true; render();
    try {
      const page = await api("GET", data.path, listQuery());
      if (!live(ticket)) return;
      if (!Array.isArray(page.items)) throw problem("invalid_response");
      data.items = page.items;
      data.cursor = data.stateFilter || data.kindFilter ? "" : data.path;
      data.next = typeof page.next_cursor === "string" ? page.next_cursor : null;
      data.profileId = page.profile_id || "";
      data.operatorName = page.operator_name || "";
      /* 列表响应里带 access（growth_api.py 在 list 成功时 merge 进来），
         所以权限不用另发一次请求。缺失就退化成"未读到"。 */
      if (page.access) {
        data.access = page.access;
        data.accessToken = typeof page.access.edit_token === "string" ? page.access.edit_token : "";
      }
      data.ready = true;
      /* 详情跟着列表刷新：列表里的那条已经变了，详情不能停在旧版本。 */
      if (data.detailId) data.detail = item(data.detailId);
    } catch (error) {
      if (!live(ticket)) return;
      data.items = []; data.detail = null; data.next = null;
      notice(error.code ? reason(error.code) : "连接中断，已清空旧内容。请刷新核对。", true);
      if (denied.has(error.code)) { data.ready = false; data.path = ""; }
    } finally {
      if (live(ticket)) { data.loading = false; render(); }
    }
  }
  async function loadMore() {
    if (!data.next || data.loading || !data.path) return;
    const ticket = version;
    data.loading = true; render();
    try {
      const page = await api("GET", data.path, listQuery(data.next));
      if (!live(ticket)) return;
      if (Array.isArray(page.items)) data.items = data.items.concat(page.items);
      data.next = typeof page.next_cursor === "string" ? page.next_cursor : null;
    } catch (error) {
      if (live(ticket)) notice(error.code ? reason(error.code) : "下一页没有读到。", true);
    } finally {
      if (live(ticket)) { data.loading = false; render(); }
    }
  }
  /* 列表与审阅是两条独立的读取，所以**各有各的忙标志**。
     共用一个的话，挂载时 `await load()` 期间它一直是 true，
     随后调用的 loadReviews() 会直接早退——审阅队列永远是空的，
     而用户看到的只是"没有待审阅"，不会报错。 */
  async function loadReviews() {
    if (!data.path || data.loadingReviews) return;
    const ticket = version;
    data.loadingReviews = true; render();
    try {
      const page = await api("GET", data.path + "/progress");
      if (!live(ticket)) return;
      data.reviews = Array.isArray(page.items) ? page.items : [];
      data.reviewNext = typeof page.next_cursor === "string" ? page.next_cursor : null;
      data.ready = true;
    } catch (error) {
      if (!live(ticket)) return;
      data.reviews = [];
      notice(error.code ? reason(error.code) : "审阅列表没有读到。", true);
    } finally {
      if (live(ticket)) { data.loadingReviews = false; render(); }
    }
  }
  async function loadMoreReviews() {
    if (!data.reviewNext || data.loadingReviews) return;
    const ticket = version;
    data.loadingReviews = true; render();
    try {
      const page = await api("GET", data.path + "/progress", {after_id: data.reviewNext});
      if (!live(ticket)) return;
      if (Array.isArray(page.items)) data.reviews = data.reviews.concat(page.items);
      data.reviewNext = typeof page.next_cursor === "string" ? page.next_cursor : null;
    } catch (error) {
      if (live(ticket)) notice(error.code ? reason(error.code) : "下一页审阅没有读到。", true);
    } finally {
      if (live(ticket)) { data.loadingReviews = false; render(); }
    }
  }

  /* ---- 写 ------------------------------------------------------------- */
  /* 状态动作。载荷照 growth_api.command 的合同：
     {action, operation_key, view_token, growth_id, expected_revision}，
     只有 revise 额外带 title/description/progress_note。 */
  async function act(id, action, extra) {
    const row = item(id);
    if (!row || data.writing) return;
    if (!row.actions || !row.actions.includes(action)) {
      /* 后端没给这个动作就绝不发。发出去一定被拒，而且会把可用动作刷一遍，
         用户看到按钮跳走却不知道为什么。 */
      notice("当前状态不接受「" + (ACTIONS[action]?.label || action) + "」，已刷新可用动作。", true);
      await load(); return;
    }
    const ticket = version;
    data.writing = true; render();
    try {
      const body = {action, operation_key:operationKey(action, id), view_token:row.view_token,
        growth_id:id, expected_revision:row.revision};
      if (extra) Object.assign(body, extra);
      const payload = await api("POST", data.path + "/command", body);
      if (!live(ticket)) return;
      data.detailId = null; data.detail = null; data.form = null;
      data.entered.add(id);
      data.writing = false;
      notice((ACTIONS[action]?.label || action) + "已完成，版本 " + (payload?.revision ?? row.revision + 1) + "。");
      await load();
    } catch (error) {
      if (!live(ticket)) return;
      data.writing = false;
      const code = error.code || "";
      notice(reason(code), true);
      if (code === "growth_revision_conflict" || code === "growth_transition_invalid") await load();
      else render();
    }
  }
  /* 提出新记录。sources 是一到八条完整来源引用——这里不做"选来源"的界面，
     因为它需要 ScopeRef 与 VersionRef 的完整结构，页面上拼不出来：
     来源凭证由对话侧或迁移侧签发，页面只负责把它们带上。
     所以提出入口只在你确实拿到了凭证时才可用，并用一行说明这件事。 */
  async function propose(form) {
    if (data.writing) return;
    const ticket = version;
    data.writing = true; render();
    try {
      const body = {action:"propose", operation_key:operationKey("propose", form.kind),
        view_token:form.view_token, kind:form.kind, title:form.title, description:form.description,
        progress_note:form.progress_note, sources:form.sources};
      const payload = await api("POST", data.path + "/command", body);
      if (!live(ticket)) return;
      data.form = null;
      data.writing = false;
      notice("已提出，等待确认。");
      await load();
    } catch (error) {
      if (!live(ticket)) return;
      data.writing = false; notice(reason(error.code), true); render();
    }
  }
  /* 权限开关。两个布尔，且 proposals 在 read 关闭时由后端强制跟从——
     页面上要照实画出这个从属，而不是并排放两个独立开关。 */
  async function saveAccess(changes) {
    if (data.writing || !data.accessToken || !Object.keys(changes).length) return;
    const ticket = version;
    data.writing = true; render();
    try {
      const payload = await api("POST", data.path + "/command", {
        action:"configure", operation_key:operationKey("access", "permissions"),
        edit_token:data.accessToken, changes});
      if (!live(ticket)) return;
      if (payload?.access) {
        data.access = payload.access;
        data.accessToken = typeof payload.access.edit_token === "string" ? payload.access.edit_token : data.accessToken;
      }
      notice("权限已保存。");
      await load();
    } catch (error) {
      if (!live(ticket)) return;
      data.writing = false; notice(reason(error.code), true); render();
    }
  }
  /* 审阅裁决。载荷只有五个字段，一个不多（growth_api.py 对 progress_command
     做的是 `set(data) != fields` 的严格相等校验）。 */
  /* 裁决是**写**，所以它不能挂在读取的标志上。
     `loadingReviews` 会由点开审阅页签触发的那次读取置上，
     用它当护栏等于"读的时候把自己要操作的按钮禁掉了"：
     点开页签、立刻点采纳，什么都不会发生，也没有任何提示。
     读与写各有各的标志，互不阻塞——写完照例重新读一遍。 */
  async function review(row, action) {
    if (data.writing) return;
    if (!row.actions || !row.actions.includes(action)) {
      notice("这条审阅当前只能「不采纳」。", true); render(); return;
    }
    const ticket = version;
    data.writing = true; render();
    try {
      await api("POST", data.path + "/progress/command", {
        review_id:row.review_id, action, expected_revision:row.base_revision,
        view_token:row.view_token, operation_key:operationKey("review", row.review_id)});
      if (!live(ticket)) return;
      data.reviews = data.reviews.filter(entry => entry.review_id !== row.review_id);
      data.writing = false;
      notice(action === "accept" ? "已采纳，进展写进目标。" : "已记下这次审阅。");
      await load();
    } catch (error) {
      if (!live(ticket)) return;
      data.writing = false; notice(reason(error.code), true);
      if (error.code === "growth_review_conflict") await loadReviews(); else render();
    }
  }

  /* ---- 渲染 ------------------------------------------------------------ */
  const VIEWS = [["track","培育轨道",ICON.track],["reviews","待审阅",ICON.review],
                 ["sources","来源与凭证",ICON.source],["gate","权限开关",ICON.gate]];
  /* 列表分页。后端 limit 上限是 20（页面传 20），游标是 after_id。
     这一页不做本地全量预读（记忆页那样）——因为成长记录条数天然远小于事实，
     而且每一条都可能带动作，预读多页会把动作列表读旧。 */
  function headMarkup() {
    const label = VIEWS.find(([id]) => id === data.view)?.[1] || "培育轨道";
    const pending = data.reviews.length;
    return `<header class="lea-head">
      <div class="lea-head-main">
        <h2>${e(label)}</h2>
        ${pending ? `<span class="lea-pill">${pending} 条待审阅</span>` : ""}
        ${data.profileId ? `<span class="lea-id" title="记录归属">${e((data.operatorName || "") + " · " + data.profileId)}</span>` : ""}
      </div>
      <div class="lea-head-actions">
        <button type="button" class="lea-btn" data-action="refresh"${data.loading || data.writing ? " disabled" : ""}>${ICON.refresh}<span>重新读取</span></button>
      </div>
    </header>`;
  }
  function railMarkup() {
    return `<nav class="lea-rail" aria-label="学习与反思工作台">${VIEWS.map(([id, text, icon]) =>
      `<button type="button" data-view="${id}" aria-pressed="${data.view === id}">
        <span class="lea-rail-icon">${icon}</span><span class="lea-rail-label">${e(text)}</span>
        ${id === "reviews" && data.reviews.length ? `<em class="lea-count">${data.reviews.length}</em>` : ""}</button>`).join("")}</nav>`;
  }
  function noticeMarkup() {
    if (!data.notice) return "";
    return `<p class="lea-notice${data.error ? " is-error" : ""}" role="status">${data.error ? ICON.alert : ICON.check}`
      + `<span>${e(data.notice)}</span><button type="button" data-action="dismiss" aria-label="关闭">×</button></p>`;
  }
  function emptyMarkup() {
    if (data.loading) return `<div class="lea-empty"><span class="lea-spinner"></span>正在读取成长记录…</div>`;
    if (!data.path) return `<div class="lea-empty">${ICON.alert}<strong>还没有可管理的私聊对象</strong>
      <p>请先选择已初始化的私聊对象与角色。</p></div>`;
    return `<div class="lea-empty">${ICON.alert}<strong>还没有读到记录</strong>
      <p>${e(data.notice || "请重新读取；若反复失败，先在账号与会话中确认 V2 已启动。")}</p>
      <button type="button" class="lea-btn" data-action="refresh">${ICON.refresh}<span>重新读取</span></button></div>`;
  }
  /* 轨道。四段主线一列，归档是旁支挂在末段右侧。
     每段上方写该段的条数——空段也留着，因为"这一段现在没有"本身是信息，
     而按有内容的段动态缩短轨道会让人以为流程变了。 */
  function trackView() {
    const groups = STAGES.map(stage => ({stage, rows:data.items.filter(row => row.state === stage.key)}));
    const retired = data.items.filter(row => row.state === RETIRED.key);
    const unknown = data.items.filter(row => !STATE_BY_KEY[row.state]);
    return `<div class="lea-track">
      ${filterBar()}
      <div class="lea-lanes">
        ${groups.map(({stage, rows}) => lane(stage, rows)).join("")}
        ${retired.length || data.stateFilter === "retired" ? lane(RETIRED, retired) : ""}
        ${unknown.length ? `<section class="lea-lane is-unknown"><header>
          <h3>状态未识别</h3><em>${unknown.length}</em></header>
          <p class="lea-lane-warn">状态未识别：${e(unknown.map(r => String(r.state)).join("、"))}</p>
          ${unknown.map(row => card(row)).join("")}</section>` : ""}
      </div>
      ${confirmMarkup()}
      ${data.next ? `<button type="button" class="lea-btn is-wide" data-action="more"${data.loading ? " disabled" : ""}>${ICON.refresh}<span>读取下一页</span></button>` : ""}
    </div>`;
  }
  function filterBar() {
    const states = [...STAGES, RETIRED];
    return `<div class="lea-filters" role="group" aria-label="筛选">
      <span class="lea-filters-label">阶段</span>
      <button type="button" data-filter-state="" aria-pressed="${!data.stateFilter}">全部</button>
      ${states.map(s => `<button type="button" data-filter-state="${s.key}" aria-pressed="${data.stateFilter === s.key}">${e(s.label)}</button>`).join("")}
      <span class="lea-filters-label">类型</span>
      <button type="button" data-filter-kind="" aria-pressed="${!data.kindFilter}">全部</button>
      ${Object.entries(KIND_LABEL).map(([key, text]) =>
        `<button type="button" data-filter-kind="${key}" aria-pressed="${data.kindFilter === key}">${e(text)}</button>`).join("")}
    </div>`;
  }
  function lane(stage, rows) {
    return `<section class="lea-lane ${stage.tone}" data-lane="${stage.key}">
      <header><span class="lea-lane-dot"></span>
        <h3>${e(stage.label)}</h3><em>${rows.length}</em>
        <span class="lea-lane-hint">${e(stage.hint)}</span></header>
      ${rows.length ? rows.map(row => card(row)).join("")
        : `<p class="lea-lane-empty">这一段暂时是空的。</p>`}
    </section>`;
  }
  function card(row) {
    const stage = STATE_BY_KEY[row.state] || {};
    /* 来源不可用时后端把 title/description 都置 null。这不是缺字段，
       所以文案必须说清"读不到"而不是显示成一张空卡。 */
    const blind = !!row.unavailable_reason;
    const entering = data.entered.has(row.growth_id);
    return `<article class="lea-card${blind ? " is-blind" : ""}${entering ? " is-entered" : ""}"
      data-id="${e(row.growth_id)}" tabindex="0" role="button"
      aria-label="${e(blind ? "来源不可读取的记录" : row.title || "未命名记录")}">
      <div class="lea-card-top">
        <span class="lea-kind">${e(KIND_LABEL[row.kind] || row.kind || "记录")}</span>
        <span class="lea-rev">v${e(row.revision)}</span>
      </div>
      <h4 class="lea-card-title">${blind ? `<span class="lea-blind-label">来源已不可读取</span>` : e(row.title || "未命名记录")}</h4>
      ${blind ? `<p class="lea-card-why">${e(reason(row.unavailable_reason))}</p>`
        : row.progress_note ? `<p class="lea-card-note">${e(row.progress_note)}</p>` : ""}
      <div class="lea-card-foot">
        <span class="lea-card-meta">${e(row.source_count ?? 0)} 条来源 · ${e(when(row.updated_at))}</span>
        ${(row.actions || []).length ? `<span class="lea-card-actions">${(row.actions || []).slice(0, 2).map(a =>
          `<button type="button" class="lea-mini${ACTIONS[a]?.kind === "primary" ? " is-primary" : ""}"
            data-act="${e(a)}" data-id="${e(row.growth_id)}">${e(ACTIONS[a]?.label || a)}</button>`).join("")}</span>` : ""}
      </div>
    </article>`;
  }

  /* 详情。整页唯一的"深度"视图：一张卡的全部字段、完整的动作列表、
     以及修订与来源。动作列表在这里完整给出（卡片上只给前两个）。 */
  function detailView() {
    const row = data.detail || (data.detailId ? item(data.detailId) : null);
    if (!row) return `<div class="lea-detail"><p class="lea-lane-empty">这条记录已不在当前列表中。</p>
      <button type="button" class="lea-btn" data-action="close-detail">${ICON.close}<span>返回轨道</span></button></div>`;
    const stage = STATE_BY_KEY[row.state] || {};
    const blind = !!row.unavailable_reason;
    return `<div class="lea-detail">
      <button type="button" class="lea-btn is-quiet" data-action="close-detail">${ICON.close}<span>返回轨道</span></button>
      <header class="lea-detail-head ${stage.tone || ""}">
        <span class="lea-pill">${e(stage.label || row.state)}</span>
        <span class="lea-kind">${e(KIND_LABEL[row.kind] || row.kind)}</span>
        <span class="lea-rev">v${e(row.revision)}</span>
      </header>
      ${blind ? `<div class="lea-blind">
          ${ICON.sourceKey}
          <div><strong>原来源已不可读取</strong>
            <p>${e(reason(row.unavailable_reason))}</p>
            <p class="lea-blind-note">来源不可读；仅可归档。</p></div></div>`
        : `<h3 class="lea-detail-title">${e(row.title || "未命名记录")}</h3>
           ${row.description ? `<p class="lea-detail-desc">${e(row.description)}</p>` : ""}
           ${row.progress_note ? `<div class="lea-detail-note"><span>进展</span><p>${e(row.progress_note)}</p></div>` : ""}`}
      ${row.proposed_by || row.confirmed_by || row.changed_by ? `<dl class="lea-chain">
        ${row.proposed_by ? `<div><dt>提出</dt><dd>${e(row.proposed_by)}</dd></div>` : ""}
        ${row.confirmed_by ? `<div><dt>确认</dt><dd>${e(row.confirmed_by)}</dd></div>` : ""}
        ${row.changed_by ? `<div><dt>最近变更</dt><dd>${e(row.changed_by)}</dd></div>` : ""}
        </dl>` : ""}
      <dl class="lea-times">
        <div><dt>创建</dt><dd>${e(when(row.created_at))}</dd></div>
        <div><dt>更新</dt><dd>${e(when(row.updated_at))}</dd></div>
        <div><dt>来源</dt><dd>${e(row.source_count ?? 0)} 条</dd></div>
      </dl>
      <section class="lea-detail-actions">
        <h4>可用动作</h4>
        
        ${(row.actions || []).length ? `<div class="lea-action-row">${(row.actions || []).map(a => {
          const spec = ACTIONS[a] || {label:a, kind:"", note:""};
          return `<button type="button" class="lea-btn${spec.kind === "primary" ? " is-primary" : spec.kind === "quiet" ? " is-quiet" : ""}"
            data-act="${e(a)}" data-id="${e(row.growth_id)}"${data.writing ? " disabled" : ""}>
            <span>${e(spec.label)}</span></button>`;
        }).join("")}</div>
        <ul class="lea-action-notes">${(row.actions || []).map(a =>
          `<li><strong>${e(ACTIONS[a]?.label || a)}</strong><span>${e(ACTIONS[a]?.note || "")}</span></li>`).join("")}</ul>`
        : `<p class="lea-lane-empty">当前状态没有可用动作。</p>`}
      </section>
      ${(row.actions || []).includes("revise") ? reviseForm(row) : ""}
    </div>`;
  }
  function reviseForm(row) {
    const draft = data.form?.id === row.growth_id ? data.form : null;
    return `<form class="lea-revise" data-form="revise">
      <h4>修订</h4>
      <label class="lea-field"><span>标题</span>
        <input type="text" name="title" maxlength="200" required value="${e(draft?.title ?? row.title ?? "")}"></label>
      <label class="lea-field"><span>描述</span>
        <textarea name="description" rows="3" maxlength="2000">${e(draft?.description ?? row.description ?? "")}</textarea></label>
      <label class="lea-field"><span>进展</span>
        <textarea name="progress_note" rows="3" maxlength="2000">${e(draft?.progress_note ?? row.progress_note ?? "")}</textarea></label>
      <div class="lea-form-actions">
        <button type="submit" class="lea-btn is-primary"${data.writing ? " disabled" : ""}>保存修订</button>
      </div></form>`;
  }

  /* 审阅队列。每一条是一条**待裁决的进展**，不是一条记录：
     它挂在某个目标上，带自己的依据来源。依据读不出来时只剩「不采纳」——
     后端就是这么给的（`progress_management.py:94`），页面照实显示。 */
  function reviewsView() {
    if (!data.reviews.length) {
      return `<div class="lea-reviews-empty">${ICON.check}
        <strong>没有待审阅的进展</strong>
        </div>`;
    }
    return `<div class="lea-reviews">
      <p class="lea-reviews-sum"><strong>${data.reviews.length}</strong> 条待审阅</p>
      ${data.reviews.map((row, index) => {
        const blind = !!row.unavailable_reason;
        return `<article class="lea-review${blind ? " is-blind" : ""}" style="--i:${index}">
          <header>
            <span class="lea-review-target">${e(row.growth_title || "目标已不可读取")}</span>
            <span class="lea-rev">依据 v${e(row.base_revision)}</span>
            <span class="lea-review-time">${e(when(row.created_at))}</span>
          </header>
          ${blind ? `<p class="lea-card-why">${ICON.sourceKey}<span>${e(reason(row.unavailable_reason))}——只能不采纳。</span></p>`
            : row.progress_note ? `<p class="lea-review-note">${e(row.progress_note)}</p>`
            : ``}
          <footer>
            ${(row.actions || []).map(a => `<button type="button"
              class="lea-btn${REVIEW_ACTIONS[a]?.kind === "primary" ? " is-primary" : REVIEW_ACTIONS[a]?.kind === "quiet" ? " is-quiet" : ""}"
              data-review="${e(a)}" data-id="${e(row.review_id)}"${data.writing ? " disabled" : ""}>
              <span>${e(REVIEW_ACTIONS[a]?.label || a)}</span></button>`).join("")}
          </footer>
          ${(row.actions || []).length === 1 && row.actions[0] === "reject"
            ? `<p class="lea-review-warn">依据不可读取，无法采纳。</p>` : ""}
        </article>`;
      }).join("")}
      ${data.reviewNext ? `<button type="button" class="lea-btn is-wide" data-action="more-reviews"${data.loadingReviews ? " disabled" : ""}>读取下一页审阅</button>` : ""}
    </div>`;
  }

  /* 来源与凭证。这一屏是**解释性**的：它说明为什么有的记录读不出内容，
     以及来源凭证从哪里来。不摆假控件——页面确实拼不出 ScopeRef/VersionRef。 */
  function sourcesView() {
    const blind = data.items.filter(row => row.unavailable_reason);
    return `<div class="lea-sources">
      <section class="lea-block">
        <h3>当前读不到内容的记录</h3>
        ${blind.length ? `
          <ul class="lea-blind-list">${blind.map(row => `<li>
            <code>${e(row.growth_id)}</code>
            <span>${e(reason(row.unavailable_reason))}</span>
            <em>${e(row.source_count ?? 0)} 条来源 · v${e(row.revision)}</em>
            <button type="button" class="lea-mini" data-open="${e(row.growth_id)}">查看</button></li>`).join("")}</ul>`
        : `<p class="lea-note is-ok">${ICON.check}<span>当前所有记录的来源都可读取。</span></p>`}
      </section>
    </div>`;
  }

  /* 权限开关。两个布尔，但**不是两个独立开关**：
     `proposals_enabled` 在 `read_enabled` 关闭时会被后端强制跟成同一份判定。
     所以关闭 read 时，propose 那一行要显示成"跟随 read"，而不是留一个开了也没用的开关。 */
  function gateView() {
    if (!data.access) {
      return `<div class="lea-empty">${ICON.alert}<strong>还没有读到权限设置</strong>
        <p>${e(data.notice || "权限尚未读取。")}</p>
        <button type="button" class="lea-btn" data-action="refresh">${ICON.refresh}<span>重新读取</span></button></div>`;
    }
    const settings = data.access.settings || {};
    const effective = data.access.effective || {};
    const readOn = settings.read_enabled === true;
    const following = !readOn;
    const rows = [
      {name:"read_enabled", label:"读取成长记录", note:"关闭后这一页读不到任何记录，相关页面的入口也会空着。"},
      {name:"proposals_enabled", label:"接受角色提出的成长", note:"关闭后角色不会提出新的技能与目标；已有的不受影响。"},
    ];
    return `<div class="lea-gate">
      <p class="lea-note">权限按当前窗口保存。</p>
      <div class="lea-gate-list">
        ${rows.map(row => {
          const on = settings[row.name] === true;
          const blocked = row.name === "proposals_enabled" && following;
          const verdict = effective[row.name];
          return `<div class="lea-switch${blocked ? " is-following" : ""}">
            <label>
              <input type="checkbox" data-access="${row.name}"${on ? " checked" : ""}${blocked || data.writing ? " disabled" : ""}>
              <span class="lea-switch-track"><i></i></span>
              <span class="lea-switch-text"><strong>${e(row.label)}</strong><small>${e(row.note)}</small></span>
            </label>
            ${blocked ? `<p class="lea-switch-note">${ICON.alert}<span>需先启用读取权限。</span></p>`
              : verdict && verdict.allowed === false ? `<p class="lea-switch-note is-warn">${ICON.alert}
                <span>已开启，但当前对象尚未获得这项权限：${e(reason(verdict.reason))}</span></p>` : ""}
          </div>`;
        }).join("")}
      </div>
    </div>`;
  }

  function body() {
    if (!data.ready) return emptyMarkup();
    if (data.detailId) return detailView();
    return {"track":trackView, "reviews":reviewsView, "sources":sourcesView, "gate":gateView}[data.view]();
  }
  function render() {
    if (!root || !data) return;
    root.innerHTML = `<div class="lea-app">${railMarkup()}<div class="lea-main">${headMarkup()}${noticeMarkup()}${body()}</div></div>`;
  }

  /* ---- 交互 ------------------------------------------------------------ */
  /* 只注册一个 click：确认条的按键与其余点击**必须**在同一个处理器里按顺序判，
     分成两个监听就会依赖注册顺序，而且卸载时要记得摘两次。
     确认条排在最前面——它浮在别的东西上面，优先级最高。 */
  function onClick(event) {
    if (event.target.closest("[data-confirm]")) { confirmClick(event); return; }
    clicked(event);
  }
  function clicked(event) {
    const view = event.target.closest("[data-view]");
    if (view) {
      data.view = view.dataset.view; data.detailId = null; data.form = null; data.notice = ""; render();
      if (data.view === "reviews") loadReviews();
      return;
    }
    const action = event.target.closest("[data-action]")?.dataset.action;
    if (action === "refresh") {
      data.notice = "";
      if (data.view === "reviews" || data.view === "track") loadReviews();
      load(); return;
    }
    if (action === "dismiss") { data.notice = ""; render(); return; }
    if (action === "more") { loadMore(); return; }
    if (action === "more-reviews") { loadMoreReviews(); return; }
    if (action === "close-detail") { data.detailId = null; data.form = null; render(); return; }
    const filterState = event.target.closest("[data-filter-state]")?.dataset.filterState;
    if (filterState !== undefined) { data.stateFilter = filterState; load(); return; }
    const filterKind = event.target.closest("[data-filter-kind]")?.dataset.filterKind;
    if (filterKind !== undefined) { data.kindFilter = filterKind; load(); return; }
    const open = event.target.closest("[data-open]")?.dataset.open;
    if (open) { data.detailId = open; data.detail = item(open); data.form = null; render(); return; }
    /* 状态动作。卡片上的与详情里的是同一条路径。
       变量名不能叫 `act`：那是本模块的状态动作函数，
       同名会把它遮蔽掉，`act(id, name)` 就变成「调用一个 dataset」。 */
    const actionButton = event.target.closest("[data-act]");
    if (actionButton) {
      event.stopPropagation();
      const id = actionButton.dataset.id, name = actionButton.dataset.act;
      if (name === "revise") {
        data.detailId = id; data.detail = item(id); data.form = null; render();
        root.querySelector(".lea-revise input")?.focus();
        return;
      }
      if (name === "withdraw" || name === "retire") {
        /* 两个不可逆动作走一次确认：它们把记录移出活跃列表。 */
        data.notice = ""; data.confirm = {id, name}; render(); return;
      }
      act(id, name); return;
    }
    const reviewAction = event.target.closest("[data-review]");
    if (reviewAction) {
      const row = data.reviews.find(r => r.review_id === reviewAction.dataset.id);
      if (row) review(row, reviewAction.dataset.review);
      return;
    }
    /* 点卡片本体开详情；点按钮不算（上面已经 stopPropagation）。 */
    const card = event.target.closest("[data-id]");
    if (card && !event.target.closest("[data-act]")) {
      data.detailId = card.dataset.id; data.detail = item(card.dataset.id); data.form = null; render();
    }
  }
  /* 确认条渲染在轨道里、被点卡片所属的那一段下方——不居中弹窗。
     弹窗会把轨道整个盖住，用户看不到自己正要移走的那张卡。
     用 state 里的一条标记驱动，而不是 document.createElement：
     这一页其余部分全是字符串模板，混进一个 DOM 构造会让测试夹具
     必须多实现一套 API，而多出来的那套没有别的东西在验证。 */
  function confirmMarkup() {
    const pending = data.confirm;
    if (!pending) return "";
    const spec = ACTIONS[pending.name] || {label:pending.name, note:""};
    const row = item(pending.id);
    const stage = row ? (STATE_BY_KEY[row.state] || {}) : {};
    return `<div class="lea-confirm" role="alertdialog" aria-label="确认${e(spec.label)}">
      <span class="lea-confirm-text">${e(spec.note)}</span>
      <span class="lea-confirm-target">${e(stage.label || "")} · ${e(row?.title || pending.id)}</span>
      <button type="button" class="lea-mini is-primary" data-confirm="yes">确认${e(spec.label)}</button>
      <button type="button" class="lea-mini" data-confirm="no">取消</button></div>`;
  }
  function change(event) {
    const access = event.target.closest("[data-access]");
    if (access) { saveAccess({[access.dataset.access]: access.checked}); return; }
  }
  function submit(event) {
    const form = event.target.closest('[data-form="revise"]');
    if (!form) return;
    event.preventDefault();
    const row = data.detail || item(data.detailId);
    if (!row) return;
    const values = new FormData(form);
    const title = String(values.get("title") || "").trim();
    if (!title) { notice("标题不能为空。", true); render(); return; }
    act(row.growth_id, "revise", {title, description:String(values.get("description") || ""),
      progress_note:String(values.get("progress_note") || "")});
  }
  function confirmClick(event) {
    const button = event.target.closest("[data-confirm]");
    if (!button || !data.confirm) return;
    const {id, name} = data.confirm;
    data.confirm = null;
    if (button.dataset.confirm === "yes") act(id, name);
    else render();
  }
  function keydown(event) {
    if (event.key === "Escape") {
      if (data.notice) { data.notice = ""; render(); return; }
      if (data.confirm) { data.confirm = null; render(); return; }
      if (data.detailId) { data.detailId = null; data.form = null; render(); return; }
    }
    const card = event.target.closest(".lea-card");
    if (card && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      data.detailId = card.dataset.id; data.detail = item(card.dataset.id); data.form = null; render();
    }
    const rail = event.target.closest("[data-view]");
    if (rail && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      const index = VIEWS.findIndex(([id]) => id === data.view);
      const next = (index + (event.key === "ArrowDown" ? 1 : VIEWS.length - 1)) % VIEWS.length;
      data.view = VIEWS[next][0]; data.detailId = null; render();
      root.querySelector('[data-view="' + data.view + '"]')?.focus();
    }
  }

  /* ---- 挂载 ------------------------------------------------------------ */
  async function whenBridgeReady(ticket, timeout = 10000) {
    if (window.AstrBotPluginPage?.apiGet) return window.AstrBotPluginPage;
    const product = window.CompanionProduct;
    if (product?.bridgeNow || product?.bridgeFor) {
      try {
        const found = product.bridgeNow?.() || await product.bridgeFor();
        if (found?.apiGet) return found;
      } catch { /* 交给下面的轮询 */ }
      if (window.AstrBotPluginPage?.apiGet) return window.AstrBotPluginPage;
    }
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const tick = () => {
        if (!live(ticket)) return;
        const found = window.AstrBotPluginPage;
        if (found?.apiGet) return resolve(found);
        if (Date.now() - started >= timeout) return reject(problem("bridge_unavailable"));
        setTimeout(tick, 80);
      };
      tick();
    });
  }
  async function mount(host) {
    /* 顺序有讲究：unmount() 会 ++version 并清掉 data，所以
       ① 先 unmount，② 再建新 data，③ 才取票号。
       在 unmount() 之前取票会让下面第一处 live(ticket) 立即为假。 */
    unmount();
    root = host; data = blank();
    const ticket = ++version;
    root.addEventListener("click", onClick);
    root.addEventListener("change", change);
    root.addEventListener("submit", submit);
    root.addEventListener("keydown", keydown);
    render();
    try {
      bridge = await whenBridgeReady(ticket);
      if (!live(ticket)) return;
      const context = await bounded(bridge.ready());
      if (!live(ticket)) return;
      if (context?.pluginName !== HOST) throw problem("bridge_unavailable");
      const absolute = window.CompanionProduct.role?.()?.growth_api;
      if (typeof absolute !== "string" || !absolute) throw problem("relationship_required");
      data.path = rel(absolute);
      await load(); await loadReviews();
      if (live(ticket)) render();
    } catch (error) {
      if (!live(ticket)) return;
      notice(error.code ? reason(error.code) : String(error?.message || "未完成"), true);
      render();
    }
  }
  function unmount() {
    ++version;
    if (!root) { data = null; bridge = null; return; }
    root.removeEventListener("click", onClick);
    root.removeEventListener("change", change);
    root.removeEventListener("submit", submit);
    root.removeEventListener("keydown", keydown);
    root = null; bridge = null; data = null;
  }
  return {mount, unmount,
    get state() { return {data}; },
    _internals:{STAGES, RETIRED, ACTIONS, REVIEW_ACTIONS, KIND_LABEL, when}};
})();
