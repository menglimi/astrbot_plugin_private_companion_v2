"use strict";
/* 备份与还原工作区。
 *
 * 为什么值得单独做一个模块：后端 `backup_api.py` 有六条真实路由和一台完整的
 * 两阶段状态机，而**此前没有任何页面调用过其中任何一条**——资料与维护页当时
 * 只放了一张 boundaryCard 解释「为什么没有入口」。那是「能接却没接」，
 * 属于要接上的那一类，不是要删的那一类。
 *
 * 后端状态机（`companion_v2/storage/backup.py`）：
 *
 *   listing            列出已完成快照，按 created_at 倒序
 *   create(note)       写一份快照；sidecar 最后写，它的存在标记快照完成
 *   inspect(snapshot_id)      只读打开并在内存里校验，不还原
 *   restore/preview(snapshot_id)  校验 + 报告当前三条表的行数
 *   restore(snapshot_id, confirmed_hash)  暂存还原请求
 *   pending            报告是否有还原在等重启
 *
 * 三处语义必须照实呈现，否则页面会误导用户：
 *
 *   1. 还原是两阶段的，**必须重启宿主才生效**。页面不能说「已还原」——
 *      只能说到「已暂存，等待重启」。后端也把 effect 写成 requires_restart /
 *      restart_required 两个值，页面对它们各自给话术。
 *
 *   2. 确认的是**字节**：restore 要求传 confirmed_hash，且必须与
 *      manifest.content_hash 逐字相等，否则 backup_confirmation_mismatch。
 *      所以页面必须先把 inspect/preview 拿到的哈希存下来，再原样回传，
 *      不能自己现算也不能省。
 *
 *   3. 暂存时会**自动先做一份安全副本**（pre-restore safety copy）并回传
 *      safety_snapshot_id。这条要显示出来——用户会想知道「还原失败还能退回哪」。
 *
 * 信封与其它页一致：{status, message, data}，机器码在 message 与 data.code 上，
 * 两者都要看（见 [[project_companion_v2_page_error_codes]]）。
 */
window.CompanionBackupPage = (() => {
  const HOST = "astrbot_plugin_private_companion";
  const PREFIX = "/" + HOST + "/";
  const ROUTE = "backup";

  /* 后端 BackupError 对应的可读提示。 */
  const errors = {
    backup_snapshot_missing: "这份快照已经不在了，可能在别处被清理。刷新列表看看。",
    backup_snapshot_unreadable: "这份快照读不出来，文件可能已损坏。",
    backup_snapshot_corrupt: "这份快照完整性校验没通过，不能用来还原。",
    backup_snapshot_foreign: "这份快照属于另一个安装，不能还原到当前数据根。",
    backup_snapshot_schema_mismatch: "这份快照的结构版本与当前不一致，无法直接还原。",
    backup_snapshot_incomplete: "这份快照没有写完（缺少配套清单），已被跳过。",
    backup_snapshot_id_invalid: "快照标识不合法，请从列表中重新选择。",
    backup_snapshot_size_invalid: "快照体积超出允许范围，无法读取。",
    backup_snapshot_changed: "快照在预览之后发生了变化，出于安全没有继续。请重新预览。",
    backup_snapshot_broken_references: "快照里的引用关系不完整，可能缺少关联数据。",
    backup_confirmation_mismatch: "确认的摘要与快照当前内容不一致，已拒绝执行。请重新预览后再试。",
    backup_restore_pending: "已有一个还原在等待重启，请先重启插件再发起新的还原。",
    backup_restore_unverified: "这份快照尚未通过校验，不能还原。",
    backup_note_invalid: "备注最多 200 个字。",
    backup_write_failed: "写快照失败，可能是磁盘空间或权限问题。",
    backup_clock_invalid: "系统时间不可用，无法为快照打时间戳。",
    backup_metadata_missing: "备份所需的元数据缺失，请确认 V2 数据根完整。",
    backup_pending_unreadable: "等待重启的还原记录读不出来，请检查数据根。",
    backup_preview_failed: "读取当前数据行数失败，请刷新核对。",
    /* 宿主与身份层的提示也在此处翻译。 */
    dashboard_identity_required: "请从已登录的 AstrBot 管理界面打开。",
    staging_not_initialized: "V2 数据尚未加载，请先在账号与会话中加载已配置的运行实例。",
    staging_host_terminated: "插件已停止，请重新打开拓展页。",
    backup_request_invalid: "请求参数不合法，请重新操作。",
    bridge_unavailable: "页面还没有接上 AstrBot。若这是从管理界面打开的插件页，刷新一次通常就好；若反复出现，请确认插件已启用。",
    bridge_timeout: "未收到确认，请刷新核对。",
    invalid_response: "服务返回的数据不完整，请刷新核对。",
  };
  const e = value => String(value ?? "").replace(/[&<>"']/g,
    c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const CODE = /^[a-z][a-z0-9_]{2,60}$/;
  const codeOf = wrapped => wrapped?.data?.code
    || (CODE.test(wrapped?.message || "") ? wrapped.message : "") || "";
  const reason = code => errors[code] || "备份操作未完成，请重新读取快照与还原状态后核对。";

  /* 三张被统计的表。中文名只为让用户看懂「还原会替换掉什么」，
     键名必须与 COUNTED_TABLES 一致。 */
  const TABLES = [
    ["memory_atoms", "记忆条目"],
    ["operations", "操作记录"],
    ["configuration_values", "配置项"],
  ];

  let root = null, bridge = null, version = 0;
  let data = {snapshots: [], pending: null, loading: true, busy: "", error: false,
    notice: "", preview: null, confirming: null};

  function bytes(value) {
    const size = Number(value);
    if (!Number.isFinite(size) || size <= 0) return "—";
    if (size < 1024) return size + " B";
    if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KB";
    return (size / 1024 / 1024).toFixed(1) + " MB";
  }
  function when(value) {
    return value && Number.isFinite(Date.parse(value))
      ? new Date(value).toLocaleString("zh-CN", {hour12: false}) : "时间未知";
  }
  /* 32 位十六进制摘要按 8 位一组显示更容易比对，整串仍保留在 title 里。 */
  function shortHash(hash) {
    const text = String(hash || "");
    return text.length > 12 ? text.slice(0, 12) + "…" : text;
  }

  function token() { return version; }
  function live(ticket) { return ticket === version && root?.isConnected; }
  function stop() { root = null; bridge = null; }
  function paint() { if (live(version)) render(); }

  function setNotice(message, isError = false) {
    data.notice = message; data.error = isError; paint();
  }

  async function bounded(promise) {
    let timeout;
    try {
      return await Promise.race([promise, new Promise((_, reject) => {
        timeout = setTimeout(() => reject(Object.assign(new Error("bridge_timeout"), {code: "bridge_timeout"})), 20000);
      })]);
    } finally { clearTimeout(timeout); }
  }

  /* 六个动作走同一台桥。GET 的那三个后面不带查询参数，POST 的体是严格字段集
     （后端 _body 要求 set(arguments) 完全相等，多一个字段就 invalid）。 */
  async function call(method, path, body) {
    const response = await bounded(method === "GET"
      ? bridge.apiGet(path, body) : bridge.apiPost(path, body));
    const wrapped = ["ok", "error"].includes(response?.status) && response?.data !== undefined ? response
      : ["ok", "error"].includes(response?.data?.status) && response?.data?.data !== undefined ? response.data : null;
    if (wrapped?.status === "error") {
      const code = codeOf(wrapped) || "invalid_response";
      throw Object.assign(new Error(code), {code, confirmed: true});
    }
    const value = wrapped ? wrapped.data : response;
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw Object.assign(new Error("invalid_response"), {code: "invalid_response"});
    }
    return value;
  }

  async function load(ticket = version) {
    data.loading = true; data.error = false; paint();
    try {
      /* 桥可能比页面脚本晚到（正常时序），也可能真的没接上。
         两种情况都先等一等，等不到就抛出可翻译的码。 */
      bridge = bridge || await bridgeReady();
      const [listed, waiting] = await Promise.all([
        call("GET", ROUTE),
        /* pending 在早期版本可能不存在；单独失败不该让整页读不出列表。 */
        call("GET", ROUTE + "/pending").catch(() => ({pending: null})),
      ]);
      if (!live(ticket)) return;
      data.snapshots = Array.isArray(listed.snapshots) ? listed.snapshots : [];
      data.pending = waiting.pending || null;
      data.loading = false;
    } catch (error) {
      if (!live(ticket)) return;
      data.loading = false; data.error = true;
      data.notice = reason(error.code); paint();
      return;
    }
    paint();
  }

  /* 创建快照。备注是可选字段，但后端严格要求 body 的键集等于 {note}，
     所以没填也要传空串，不能省略键。 */
  async function create(note) {
    if (data.busy) return;
    const ticket = token();
    data.busy = "create"; data.notice = ""; paint();
    try {
      const created = await call("POST", ROUTE + "/create", {note: String(note || "").slice(0, 200)});
      if (!live(ticket)) return;
      data.busy = "";
      setNotice(created.retention?.failed
        ? "快照已生成，自动清理未完成。"
        : "快照已生成。");
      await load(ticket);
    } catch (error) {
      if (!live(ticket)) return;
      data.busy = ""; setNotice(reason(error.code), true);
    }
  }

  /* 预览还原：校验快照 + 报告当前行数，并把哈希留在 data.preview 里等确认。
     哈希必须来自后端（inspect/preview 的 manifest.content_hash），
     页面不自己算——后端比对的就是它。 */
  async function preview(snapshotId) {
    if (data.busy) return;
    const ticket = token();
    data.busy = "preview:" + snapshotId; data.notice = ""; data.preview = null; paint();
    try {
      const result = await call("GET", ROUTE + "/restore/preview", {snapshot_id: snapshotId});
      if (!live(ticket)) return;
      const manifest = result.verified?.manifest || {};
      data.busy = "";
      data.preview = {
        snapshot_id: result.snapshot_id,
        current: result.current || {},
        effect: result.effect,
        /* 这次还原影响哪些目标与角色。后端随预览一并下发：还原是整根替换，
           多目标下会同时替换该安装下所有目标的资料，而用户最容易误以为
           「只还原我当前看的这个角色」。旧版后端没有这一段，读不到就不显示。 */
        scope: result.scope || null,
        content_hash: manifest.content_hash || "",
        created_at: manifest.created_at,
        note: manifest.note || "",
        byte_size: manifest.byte_size,
      };
      paint();
    } catch (error) {
      if (!live(ticket)) return;
      data.busy = ""; setNotice(reason(error.code), true);
    }
  }

  /* 暂存还原。confirmed_hash 原样回传预览时拿到的那个。
     成功后**不是**「已还原」，而是「已暂存、等重启」——话术上必须区分开。 */
  async function stageRestore() {
    const previewState = data.preview;
    if (!previewState || data.busy) return;
    const ticket = token();
    data.busy = "restore"; data.notice = ""; paint();
    try {
      const result = await call("POST", ROUTE + "/restore", {
        snapshot_id: previewState.snapshot_id,
        confirmed_hash: previewState.content_hash,
      });
      if (!live(ticket)) return;
      const safety = result.safety_snapshot_id ? shortHash(result.safety_snapshot_id) : "";
      data.busy = ""; data.preview = null; data.confirming = null;
      setNotice("还原请求已暂存，将在下次启动插件时生效。"
        + (safety ? `还原前的数据已另存为安全副本 ${safety}。` : "")
        + "现在重启插件即可完成。");
      await load(ticket);
    } catch (error) {
      if (!live(ticket)) return;
      data.busy = ""; setNotice(reason(error.code), true);
    }
  }

  function snapshotRow(item) {
    const id = String(item.snapshot_id || "");
    const busy = data.busy === "preview:" + id;
    const pendingSame = data.pending?.snapshot_id === id;
    return `<li class="backup-snapshot-row">
      <div class="backup-snapshot-main">
        <div class="backup-snapshot-title">
          <strong>${e(when(item.created_at))}</strong>
          ${pendingSame ? `<span class="backup-tag is-pending">等待重启</span>` : ""}
        </div>
        ${item.note ? `<p class="backup-snapshot-note">${e(item.note)}</p>` : ""}
        <small class="backup-snapshot-meta">${e(bytes(item.byte_size))} · 结构版本 ${e(item.schema_version || "未知")} · 摘要 <code title="${e(item.content_hash)}">${e(shortHash(item.content_hash))}</code></small>
      </div>
      <div class="backup-snapshot-actions">
        <button class="button small" data-backup-preview="${e(id)}"${busy || pendingSame ? " disabled" : ""}>
          ${busy ? "正在校验…" : "预览还原"}
        </button>
      </div>
    </li>`;
  }

  /* 预览区。这里是全局唯一需要用户「看清楚再点」的地方，
     所以把会被替换掉的三个行数与哈希都摊开，并要求二次确认。 */
  function previewBlock() {
    const state = data.preview;
    if (!state) return "";
    const rows = TABLES.map(([key, label]) => {
      const count = state.current?.[key];
      return `<div class="backup-count"><dt>${label}</dt><dd>${Number.isFinite(count) ? count : "—"}<small>行</small></dd></div>`;
    }).join("");
    const confirming = data.confirming === state.snapshot_id;
    /* 影响面：后端说这次还原覆盖几个目标、几个角色。多目标下这句话是必要的——
       数据根是整个安装的，不是某一个角色。 */
    const scope = state.scope;
    const scopeLine = scope
      ? `<p class="backup-preview-scope">还原将替换整个安装的数据：${Number(scope.targets) || 1} 个目标、${Number(scope.roles) || 1} 个角色${scope.restart_required === false ? "" : "；重启后生效"}。</p>`
      : "";
    return `<section class="backup-preview" aria-label="还原预览">
      <header class="backup-preview-head">
        <strong>还原这份快照会替换掉当前数据</strong>
        <small>${e(when(state.created_at))}${state.note ? " · " + e(state.note) : ""} · ${e(bytes(state.byte_size))}</small>
      </header>
      <p class="backup-preview-lead">当前数据行数</p>
      <dl class="backup-counts">${rows}</dl>
      ${scopeLine}
      <p class="backup-preview-hash">确认摘要 <code>${e(shortHash(state.content_hash))}</code></p>
      <p class="backup-preview-warn">暂存还原时会生成当前数据的安全副本。</p>
      <div class="backup-preview-actions">
        ${confirming
          ? `<button class="button small danger" data-backup-confirm ${data.busy === "restore" ? "disabled" : ""}>
               ${data.busy === "restore" ? "正在暂存…" : "确认暂存还原"}</button>
             <button class="button small" data-backup-cancel>再想想</button>`
          : `<button class="button small danger" data-backup-stage>暂存还原请求</button>
             <button class="button small" data-backup-cancel>取消</button>`}
      </div>
    </section>`;
  }

  function pendingBlock() {
    const pending = data.pending;
    if (!pending) return "";
    return `<section class="backup-pending" role="status">
      <strong>有一个还原在等待重启</strong>
      <p>它请求把数据还原到 ${e(shortHash(pending.snapshot_id))}，于 ${e(when(pending.requested_at))} 暂存。
        重启插件后生效；在此之前不会改动任何数据。</p>
      ${pending.safety_snapshot_id
        ? `<small>还原前的安全副本：<code>${e(shortHash(pending.safety_snapshot_id))}</code></small>` : ""}
    </section>`;
  }

  function body() {
    if (data.loading) {
      return `<div class="backup-loading" aria-live="polite">正在读取快照列表…</div>`;
    }
    /* 读不到就不要再摆出那张「还没有任何快照」的空表单——那是一句假消息，
       用户会以为备份真的空着，还可能对着一个读不出来的列表点生成。 */
    if (data.error) {
      return `<section class="backup-unavailable">
        <p>${e(data.notice || "备份列表暂时读不出来。")}</p>
        <div class="backup-unavailable-actions">
          <button class="button small" data-backup-retry>重新读取</button>
        </div>
      </section>`;
    }
    const list = data.snapshots.length
      ? `<ul class="backup-snapshot-list">${data.snapshots.map(snapshotRow).join("")}</ul>`
      /* 空态要给「怎么让它不空」，不是「为什么没有」——所以直接指向下面的创建按钮。 */
      : `<p class="backup-empty">暂无快照</p>`;
    return `${pendingBlock()}
    <div class="backup-create">
      <strong class="backup-create-title">生成快照</strong>
      <label for="backupNote">备注（可选，最多 200 字）</label>
      <div class="backup-create-row">
        <input id="backupNote" type="text" maxlength="200" placeholder="例如：升级插件之前">
        <button class="button small" data-backup-create ${data.busy === "create" ? "disabled" : ""}>
          ${data.busy === "create" ? "正在生成…" : "生成快照"}
        </button>
      </div>
    </div>
    ${previewBlock()}
    <section class="backup-list-block" aria-label="已有快照">
      <header><strong>已有快照</strong><small>整个安装</small></header>
      ${list}
    </section>`;
  }

  function render() {
    if (!root) return;
    /* 错误态由 body() 自己说清并给出口；这里不再重复一遍同样的句子。 */
    const notice = data.notice && !data.error
      ? `<p class="backup-notice" role="status">${e(data.notice)}</p>` : "";
    root.innerHTML = `<div class="backup-workspace">
      ${notice}
      ${body()}
    </div>`;
    /* 输入框在重绘时会被重建，把用户正在打的备注放回去——
       否则一有通知刷新，备注就没了。 */
    const input = root.querySelector("#backupNote");
    if (input && data.draft != null) input.value = data.draft;
  }

  /* 取桥：先同步看一眼（不抛），真没出现才等。
   *
   * 不能写成 `product?.whenBridgeReady?.() ?? Promise.resolve(window.AstrBotPluginPage)`：
   * `??` 的右半边会**立刻求值**，product 没提供等待器时捕到的是
   * Promise.resolve(undefined)——一个「成功」的 promise 里躺着 undefined，
   * 于是「去等桥」这件事根本没发生，用户点重新读取只会再得一句没接上。
   */
  async function bridgeReady() {
    const product = window.CompanionProduct;
    const found = product?.bridgeNow?.() || (product?.bridgeFor
      ? await product.bridgeFor()
      : window.AstrBotPluginPage);
    if (!found?.apiGet) {
      throw Object.assign(new Error("bridge_unavailable"), {code: "bridge_unavailable"});
    }
    return found;
  }

  root = null;
  function mount(node, options = {}) {
    stop();
    root = node;
    bridge = options.bridge || window.AstrBotPluginPage;
    version += 1;
    data = {snapshots: [], pending: null, loading: true, busy: "", error: false,
      notice: "", preview: null, confirming: null, draft: ""};
    /* 事件委托：面板每次重绘都会换掉按钮，逐个绑定会随重绘失效。
       它要在「桥还没到」那条早退之前绑上——早退分支里的重试按钮靠它生效。 */
    root.addEventListener("click", onClick);
    /* 缺桥不早退。早退的写法有两处不对：那条分支里没有任何出口
       （data.loading 仍是 true，渲染出来只有一句「正在读取快照列表…」，
       桥永远不来就永远停在那里），而且真实宿主里 mountWorkspace() 只在
       桥可用时才执行——这条分支平时走不到，也就没人发现它坏了。
       改成照常去读，读不到由 load() 落到带重试出口的错误态。 */
    root.addEventListener("input", event => {
      if (event.target?.id === "backupNote") data.draft = event.target.value;
    });
    load(version);
  }

  function unmount() {
    if (root) {
      root.removeEventListener("click", onClick);
      root.innerHTML = "";
    }
    version += 1;
    stop();
  }

  function onClick(event) {
    const button = event.target?.closest?.("[data-backup-create],[data-backup-preview],[data-backup-stage],[data-backup-confirm],[data-backup-cancel],[data-backup-retry]");
    if (!button || !root?.contains(button)) return;
    if (button.hasAttribute("data-backup-retry")) {
      /* 就地等桥，不交给外层重渲染：外层会重建整页，用户刚在备注框里
         打的字会一起没掉，而他只是为了重试一次读取。 */
      data.loading = true; data.error = false; paint();
      bridge = null;
      load(version);
      return;
    }
    if (button.hasAttribute("data-backup-create")) {
      create(root.querySelector("#backupNote")?.value || "");
      return;
    }
    if (button.hasAttribute("data-backup-preview")) {
      preview(button.getAttribute("data-backup-preview"));
      return;
    }
    /* 暂存分两步：先切到「确认」态，再真的发请求。
       这是整个页面唯一不可逆的入口，多一次点击是应该的。 */
    if (button.hasAttribute("data-backup-stage")) {
      data.confirming = data.preview?.snapshot_id || null; paint(); return;
    }
    if (button.hasAttribute("data-backup-confirm")) { stageRestore(); return; }
    if (button.hasAttribute("data-backup-cancel")) {
      data.confirming = null; data.preview = null; paint();
    }
  }

  return {
    mount, unmount,
    /* 供测试读取内部状态与走查渲染分支。 */
    get state() { return data; },
    _reason: reason, _bytes: bytes, _shortHash: shortHash,
  };
})();
