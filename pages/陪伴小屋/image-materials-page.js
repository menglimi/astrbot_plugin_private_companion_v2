/* Native image materials: explicit album registration, references and wardrobe. */
"use strict";

window.CompanionImageMaterialsPage = (() => {
  const ROLES = [
    ["identity", "身份"], ["outfit", "穿搭"], ["pose", "姿态"],
    ["scene", "场景"], ["style", "风格"], ["background", "背景"],
    ["continuity", "连续性"], ["edit_source", "编辑源"], ["edit_mask", "编辑遮罩"],
  ];
  const ROLE_LABEL = Object.fromEntries(ROLES);
  const ERRORS = {
    dashboard_identity_required: "请从已登录的 AstrBot 管理界面打开陪伴小屋。",
    core_access_required: "当前账号没有管理参考素材的权限。",
    bridge_unavailable: "页面还没有接上 AstrBot，请刷新后重试。",
    bridge_timeout: "连接超时，请刷新后重试。",
    staging_not_initialized: "V2 运行实例尚未加载，请先完成账号与会话设置。",
    staging_host_terminated: "插件已经停止，请重新打开管理页面。",
    image_material_request_invalid: "请求信息不完整，请刷新后重新选择素材。",
    generated_album_cursor_invalid: "相册分页已经失效，请刷新相册。",
    generated_image_missing: "请先从当前角色的产出相册选择一张图片。",
    generated_album_thumbnail_invalid: "这张产出图暂时无法预览，请刷新相册。",
    photo_reference_disabled: "参考图功能当前关闭，请先在上方配置中开启。",
    daily_outfit_disabled: "每日穿搭当前关闭，请先在参考素材配置中开启。",
    wardrobe_disabled: "衣柜当前关闭，请先在上方配置中开启。",
    reference_operation_invalid: "这次登记没有生成有效的操作编号，请重新提交。",
    reference_operation_conflict: "这张图的登记编号已经对应了另一组资料，请重新选择后提交。",
    reference_roles_invalid: "请至少选择一个参考用途。",
    reference_label_invalid: "参考图名称不能超过 120 个字符。",
    reference_asset_missing: "请先选择一条已登记的参考图。",
    reference_scope_invalid: "参考素材只支持已绑定的私聊角色。",
    reference_context_invalid: "当前角色上下文已变化，请刷新后重试。",
    binding_rebound: "绑定对象已经变化，请重新打开当前角色。",
    reference_target_changed: "当前角色或私聊对象已经变化，请刷新后重试。",
    wardrobe_operation_conflict: "这个衣柜编号已经对应另一件衣物，请重新提交。",
    wardrobe_tags_invalid: "标签请用逗号分隔，并保持为文字。",
    wardrobe_reference_invalid: "衣柜图片必须是已登记的穿搭参考图。",
    wardrobe_item_missing: "请先选择一件有效的衣物。",
    invalid_response: "返回的数据不完整，请刷新后重试。",
  };
  const state = {
    root: null, scope: "", ticket: 0, abort: null,
    inventory: null, inventoryLoading: false, inventoryError: "",
    album: [], albumCursor: null, albumLoaded: false, albumLoading: false, albumError: "",
    selectedImage: "", selectedRoles: new Set(["identity"]), referenceLabel: "", referenceKey: "",
    wardrobeName: "", wardrobeDescription: "", wardrobeTags: "", wardrobeAssetId: "", wardrobeKey: "",
    action: "", notice: "", noticeError: false,
  };

  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
  const makeError = code => Object.assign(new Error(ERRORS[code] || "请求没有完成，请刷新后重试。"), {code});
  const product = () => window.CompanionProduct;
  const live = ticket => state.root?.isConnected && ticket === state.ticket
    && state.scope === (product()?.scopeKey?.() || "");
  const role = () => product()?.role?.() || null;

  function operationKey(prefix) {
    let value = "";
    try { value = window.crypto?.randomUUID?.() || ""; } catch (_) {}
    if (!value) value = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    return `${prefix}-${value}`;
  }

  function apiPath(suffix = "") {
    const current = product();
    const endpoint = role()?.image_material_api;
    if (!current || !state.scope) throw makeError("reference_scope_invalid");
    if (typeof endpoint !== "string" || !endpoint) throw makeError("image_material_unavailable");
    try { return current.relative(endpoint) + suffix; }
    catch (_) { throw makeError("invalid_response"); }
  }

  function unwrap(response) {
    const current = product();
    if (current?.unwrap) return current.unwrap(response);
    const wrapped = ["ok", "error"].includes(response?.status) ? response
      : ["ok", "error"].includes(response?.data?.status) ? response.data : null;
    if (wrapped?.status === "error") throw makeError(wrapped.message);
    const value = wrapped ? wrapped.data : response;
    if (!value || typeof value !== "object" || Array.isArray(value)) throw makeError("invalid_response");
    return value;
  }

  async function request(method, path, body) {
    const current = product();
    const bridge = current?.bridgeNow?.() || await current?.bridgeFor?.();
    if (!bridge) throw makeError("bridge_unavailable");
    try {
      const response = method === "GET" ? await bridge.apiGet(path, body) : await bridge.apiPost(path, body);
      return unwrap(response);
    } catch (error) {
      if (error?.code && ERRORS[error.code]) throw makeError(error.code);
      throw error;
    }
  }

  function errorText(error, fallback) {
    if (ERRORS[error?.code]) return ERRORS[error.code];
    if (typeof error?.message === "string" && error.message && !/^[a-z][a-z0-9_]{2,60}$/.test(error.message)) {
      return error.message;
    }
    return fallback;
  }

  function settings() {
    return state.inventory?.settings || {};
  }
  function referenceSettings() { return settings().references || null; }
  function wardrobeSettings() { return settings().wardrobe || null; }
  function referencesEnabled() { return referenceSettings()?.enabled === true; }
  function wardrobeEnabled() { return wardrobeSettings()?.enabled === true; }
  function dailyEnabled() {
    return referencesEnabled() && referenceSettings()?.daily_outfit_enabled === true && wardrobeEnabled();
  }
  function activeReferences() {
    return (state.inventory?.references || []).filter(item => item?.state === "active");
  }
  function activeWardrobe() {
    return (state.inventory?.wardrobe || []).filter(item => item?.state === "active");
  }

  function setNotice(message, isError = false) {
    state.notice = message || "";
    state.noticeError = !!isError;
  }

  function statusCard(title, body, kind = "empty") {
    return `<div class="image-materials-status image-materials-status--${kind}" role="status"><strong>${esc(title)}</strong><p>${esc(body)}</p></div>`;
  }

  function renderSettings() {
    if (state.inventoryLoading && !state.inventory) return statusCard("正在读取当前角色", "正在核对参考图、衣柜和每日穿搭的配置。", "loading");
    if (!state.inventory) return "";
    const refs = referenceSettings();
    const wardrobe = wardrobeSettings();
    const refLabel = refs ? (refs.enabled ? "已开启" : "已关闭") : "未读取";
    const wardrobeLabel = wardrobe ? (wardrobe.enabled ? "已开启" : "已关闭") : "未读取";
    const dailyLabel = refs?.daily_outfit_enabled ? "已开启" : "已关闭";
    return `<div class="image-materials-switches" aria-label="素材功能状态">
      <span class="image-materials-switch ${refs?.enabled ? "is-on" : ""}"><b>参考图</b><em>${esc(refLabel)}</em></span>
      <span class="image-materials-switch ${wardrobe?.enabled ? "is-on" : ""}"><b>衣柜</b><em>${esc(wardrobeLabel)}</em></span>
      <span class="image-materials-switch ${refs?.daily_outfit_enabled ? "is-on" : ""}"><b>每日穿搭</b><em>${esc(dailyLabel)}</em></span>
    </div>`;
  }

  function renderAlbum() {
    const items = state.album;
    let body = "";
    if (state.albumLoading && !items.length) body = statusCard("正在读取产出相册", "只展示已经治理过的生成图；登记前不会自动成为参考素材。", "loading");
    else if (state.albumError && !items.length) body = statusCard("产出相册暂不可读", state.albumError, "error");
    else if (!state.albumLoaded && !items.length) body = statusCard("等待读取相册", "点击刷新后读取当前角色的已生成图片。", "empty");
    else if (!items.length) body = statusCard("相册里还没有生成图", "先完成一次图像生成，生成图才会出现在这里。", "empty");
    else {
      body = `<div class="image-materials-album-grid">${items.map(item => {
        const selected = item.image_id === state.selectedImage;
        const action = item.action ? ` · ${item.action}` : "";
        return `<button type="button" class="image-materials-album-item${selected ? " is-selected" : ""}" data-im-select="${esc(item.image_id)}" aria-pressed="${selected}" aria-label="选择${esc(item.created_at || "生成图片")}">
          <img src="${esc(item.thumbnail)}" alt="${esc(item.created_at || "生成图片")}" loading="lazy">
          <span class="image-materials-album-meta"><b>${esc(item.width || "—")} × ${esc(item.height || "—")}</b><small>${esc((item.created_at || "时间未记录") + action)}</small></span>
        </button>`;
      }).join("")}</div>`;
      if (state.albumCursor) body += `<button type="button" class="button small image-materials-load-more" data-im-load-more ${state.albumLoading ? "disabled" : ""}>${state.albumLoading ? "正在读取…" : "读取更早的产出"}</button>`;
      else body += `<p class="image-materials-footnote">这是当前角色相册的全部结果。</p>`;
    }
    return `<section class="image-materials-section image-materials-album-section"><header class="image-materials-section-head"><div><h4>产出相册</h4><p>选一张图片，再明确声明它可以用于哪些参考位置。</p></div><button type="button" class="button small" data-im-refresh ${state.albumLoading || state.inventoryLoading ? "disabled" : ""}>刷新</button></header>${body}</section>`;
  }

  function renderRoles() {
    return ROLES.map(([value, label]) => `<label class="image-materials-role"><input type="checkbox" data-im-role="${value}" ${state.selectedRoles.has(value) ? "checked" : ""}><span>${label}</span></label>`).join("");
  }

  function renderReferenceEditor() {
    const selected = state.album.find(item => item.image_id === state.selectedImage);
    if (!selected) return statusCard("先选择一张产出图", "选中后可以为它登记参考用途；未登记的相册图片不会参与后续生图。", "empty");
    const disabled = !referencesEnabled() || !!state.action;
    return `<div class="image-materials-editor image-materials-reference-editor">
      <div class="image-materials-selected"><img src="${esc(selected.thumbnail)}" alt="已选择的产出图"><div><strong>已选择一张产出图</strong><span>${esc(selected.created_at || "时间未记录")}</span></div></div>
      <label class="image-materials-field"><span>名称（可选）</span><input type="text" maxlength="120" data-im-reference-label value="${esc(state.referenceLabel)}" placeholder="例如：春日头像"></label>
      <fieldset class="image-materials-roles"><legend>允许的参考用途</legend><div class="image-materials-role-grid">${renderRoles()}</div></fieldset>
      <p class="image-materials-help">用途只授予你勾选的范围，之后可以单独撤回这条登记。</p>
      <button type="button" class="button primary" data-im-register ${disabled || !state.selectedRoles.size ? "disabled" : ""}>${state.action === "register-reference" ? "正在登记…" : "登记为参考素材"}</button>
    </div>`;
  }

  function renderReferenceList() {
    const records = state.inventory?.references || [];
    if (!records.length) return statusCard("还没有已登记的参考素材", "从上面的产出相册选择图片并登记后，它才会出现在这里。", "empty");
    return `<ul class="image-materials-record-list">${records.map(item => {
      const active = item.state === "active";
      const roles = (item.roles || []).map(value => ROLE_LABEL[value] || value).join("、") || "未声明用途";
      return `<li class="image-materials-record ${active ? "" : "is-withdrawn"}"><div><strong>${esc(item.label || "未命名参考图")}</strong><span>${esc(roles)} · ${esc(item.mime_type || "图片")}</span></div><div class="image-materials-record-action"><em>${active ? "生效中" : "已撤回"}</em>${active ? `<button type="button" class="button small danger" data-im-withdraw-ref="${esc(item.asset_id)}" ${state.action ? "disabled" : ""}>撤回</button>` : ""}</div></li>`;
    }).join("")}</ul>`;
  }

  function renderWardrobeForm() {
    const refs = activeReferences().filter(item => (item.roles || []).includes("outfit"));
    const disabled = !wardrobeEnabled() || !!state.action;
    return `<div class="image-materials-editor image-materials-wardrobe-editor">
      <div class="image-materials-form-heading"><div><h5>新增衣柜条目</h5><p>衣柜是角色级资料，可以选择一张已登记的穿搭参考图作为图片。</p></div></div>
      <div class="image-materials-form-grid">
        <label class="image-materials-field"><span>名称</span><input type="text" maxlength="120" data-im-wardrobe-name value="${esc(state.wardrobeName)}" placeholder="例如：米白针织衫"></label>
        <label class="image-materials-field"><span>标签</span><input type="text" maxlength="640" data-im-wardrobe-tags value="${esc(state.wardrobeTags)}" placeholder="针织，浅色，日常"></label>
      </div>
      <label class="image-materials-field"><span>描述（可选）</span><textarea maxlength="2000" rows="3" data-im-wardrobe-description placeholder="记录材质、版型或适合的场合">${esc(state.wardrobeDescription)}</textarea></label>
      <label class="image-materials-field"><span>关联穿搭参考图（可选）</span><select data-im-wardrobe-asset><option value="">不关联图片</option>${refs.map(item => `<option value="${esc(item.asset_id)}" ${state.wardrobeAssetId === item.asset_id ? "selected" : ""}>${esc(item.label || item.asset_id)}</option>`).join("")}</select></label>
      <button type="button" class="button primary" data-im-wardrobe-submit ${disabled || !state.wardrobeName.trim() ? "disabled" : ""}>${state.action === "register-wardrobe" ? "正在保存…" : "加入衣柜"}</button>
      ${!refs.length ? `<p class="image-materials-help">如果需要关联图片，请先登记一张带「穿搭」用途的参考图。</p>` : ""}
    </div>`;
  }

  function renderWardrobeList() {
    const records = state.inventory?.wardrobe || [];
    const daily = state.inventory?.daily_outfit;
    const dailyText = daily ? `今天选择：${daily.name || daily.item_id}` : "今天还没有选择穿搭";
    const dailyNote = dailyEnabled() ? dailyText : "每日穿搭未开启";
    if (!records.length) return `<div class="image-materials-daily"><strong>${esc(dailyNote)}</strong></div>${statusCard("衣柜还是空的", "新增一件衣物后，可以在这里选择每日穿搭。", "empty")}`;
    return `<div class="image-materials-daily"><strong>${esc(dailyNote)}</strong>${dailyEnabled() ? `<span>选择后只影响当前角色的每日穿搭记录。</span>` : ""}</div><ul class="image-materials-record-list image-materials-wardrobe-list">${records.map(item => {
      const active = item.state === "active";
      const selected = daily?.item_id === item.item_id;
      return `<li class="image-materials-record ${active ? "" : "is-withdrawn"}${selected ? " is-daily" : ""}"><div><strong>${esc(item.name || "未命名衣物")}</strong><span>${esc((item.tags || []).join("、") || item.description || "未填写描述")}${item.asset_id ? " · 已关联图片" : ""}</span></div><div class="image-materials-record-action">${active && dailyEnabled() ? `<button type="button" class="button small ${selected ? "" : "primary"}" data-im-daily="${esc(item.item_id)}" ${state.action ? "disabled" : ""}>${state.action === "daily-" + item.item_id ? "正在选择…" : selected ? "今日穿搭" : "设为今日"}</button>` : ""}${active ? `<button type="button" class="button small danger" data-im-withdraw-wardrobe="${esc(item.item_id)}" ${state.action ? "disabled" : ""}>撤回</button>` : ""}${!active ? "<em>已撤回</em>" : ""}</div></li>`;
    }).join("")}</ul>`;
  }

  function render() {
    const root = state.root;
    if (!root?.isConnected) return;
    if (!state.scope || !role()?.image_material_api) {
      root.innerHTML = `<section class="image-materials-card"><header class="image-materials-head"><div><span class="image-materials-kicker">角色级素材</span><h3>参考素材与衣柜</h3><p>这里管理产出图如何被角色再次引用。</p></div></header>${statusCard("等待私聊角色绑定", "参考图和衣柜需要一个已绑定的私聊角色。先到「账号与会话」完成绑定，再返回这里。", "empty")}</section>`;
      return;
    }
    const error = state.inventoryError || (!state.album.length && state.albumError);
    root.innerHTML = `<section class="image-materials-card">
      <header class="image-materials-head"><div><span class="image-materials-kicker">角色级素材 · 明确登记</span><h3>参考素材与衣柜</h3><p>产出相册只提供候选图片。只有经过明确登记的图片，才会进入参考用途或衣柜。</p></div><button type="button" class="button small" data-im-refresh ${state.inventoryLoading || state.albumLoading ? "disabled" : ""}>重新读取</button></header>
      ${state.notice ? `<div class="image-materials-notice ${state.noticeError ? "is-error" : ""}" role="status">${esc(state.notice)}</div>` : ""}
      ${error ? statusCard("素材状态暂不可读", errorText({message:error}, "请刷新后重试。"), "error") : ""}
      ${renderSettings()}
      <div class="image-materials-columns">${renderAlbum()}<section class="image-materials-section image-materials-reference-section"><header class="image-materials-section-head"><div><h4>登记为参考图</h4><p>一张图可以声明多个用途，后续仍能撤回。</p></div></header>${renderReferenceEditor()}</section></div>
      <section class="image-materials-section"><header class="image-materials-section-head"><div><h4>已登记参考图</h4><p>当前角色可以使用的图片登记。</p></div><span class="image-materials-count">${activeReferences().length} 条生效</span></header>${renderReferenceList()}</section>
      <section class="image-materials-section image-materials-wardrobe-section"><header class="image-materials-section-head"><div><h4>衣柜与每日穿搭</h4><p>衣物记录和每日选择都属于当前角色。</p></div><span class="image-materials-count">${activeWardrobe().length} 件生效</span></header>${renderWardrobeForm()}${renderWardrobeList()}</section>
    </section>`;
    window.lucide?.createIcons?.({attrs: {"aria-hidden": "true"}});
  }

  async function loadInventory(ticket) {
    if (!live(ticket)) return;
    state.inventoryLoading = true; state.inventoryError = ""; render();
    try {
      const value = await request("GET", apiPath());
      if (!live(ticket)) return;
      if (!Array.isArray(value.references) || !Array.isArray(value.wardrobe) || typeof value.settings !== "object") throw makeError("invalid_response");
      state.inventory = value;
      if (state.selectedImage && !state.album.some(item => item.image_id === state.selectedImage)) state.selectedImage = "";
    } catch (error) {
      if (live(ticket)) { state.inventory = null; state.inventoryError = errorText(error, "参考素材暂不可读，请刷新后重试。"); }
    } finally {
      if (live(ticket)) { state.inventoryLoading = false; render(); }
    }
  }

  async function loadAlbum(ticket, append = false) {
    if (!live(ticket) || state.albumLoading || (append && !state.albumCursor)) return;
    state.albumLoading = true; if (!append) state.albumError = ""; render();
    try {
      const value = await request("GET", apiPath("/album"), append ? {cursor: state.albumCursor} : undefined);
      if (!live(ticket)) return;
      if (!Array.isArray(value.items)) throw makeError("invalid_response");
      const incoming = value.items.filter(item => item && typeof item.image_id === "string");
      if (append) {
        const known = new Set(state.album.map(item => item.image_id));
        state.album.push(...incoming.filter(item => !known.has(item.image_id)));
      } else state.album = incoming;
      state.albumCursor = typeof value.next_cursor === "string" && value.next_cursor ? value.next_cursor : null;
      state.albumLoaded = true;
    } catch (error) {
      if (live(ticket)) state.albumError = errorText(error, "产出相册暂不可读，请刷新后重试。");
    } finally {
      if (live(ticket)) { state.albumLoading = false; render(); }
    }
  }

  async function refresh() {
    const current = product();
    const nextScope = current?.scopeKey?.() || "";
    state.scope = nextScope;
    const ticket = ++state.ticket;
    /* A refresh supersedes an in-flight request.  Reset the local busy flags as
       well: the old promise deliberately cannot clear them after its ticket is
       stale, and otherwise the album's append guard would leave the new read
       permanently blocked. */
    state.inventoryLoading = false; state.albumLoading = false;
    state.inventory = null; state.inventoryError = ""; state.album = []; state.albumCursor = null;
    state.albumLoaded = false; state.albumError = ""; setNotice("");
    render();
    if (!nextScope || !role()?.image_material_api) return;
    await Promise.allSettled([loadInventory(ticket), loadAlbum(ticket)]);
  }

  async function registerReference() {
    if (!state.selectedImage || !state.selectedRoles.size || !referencesEnabled() || state.action) return;
    const ticket = state.ticket; state.action = "register-reference"; render();
    try {
      await request("POST", apiPath("/references"), {
        image_id: state.selectedImage, label: state.referenceLabel.trim(), roles: [...state.selectedRoles],
        operation_key: state.referenceKey || (state.referenceKey = operationKey("reference")),
      });
      if (!live(ticket)) return;
      setNotice("已登记为参考素材。相册图片仍保留在原位置，登记用途可以单独撤回。");
      await loadInventory(ticket);
    } catch (error) { if (live(ticket)) setNotice(errorText(error, "参考图登记没有完成，请重试。"), true); }
    finally { if (live(ticket)) { state.action = ""; render(); } }
  }

  async function withdrawReference(assetId) {
    if (!assetId || state.action) return;
    const ticket = state.ticket; state.action = `withdraw-reference-${assetId}`; render();
    try {
      await request("POST", apiPath("/references/withdraw"), {asset_id: assetId});
      if (live(ticket)) { setNotice("已撤回这条参考素材登记。用途授权已经停止，原产出图仍保留在相册。"); await loadInventory(ticket); }
    } catch (error) { if (live(ticket)) setNotice(errorText(error, "参考素材撤回没有完成，请重试。"), true); }
    finally { if (live(ticket)) { state.action = ""; render(); } }
  }

  function parseTags(value) {
    return [...new Set(String(value || "").split(/[，,]/).map(item => item.trim()).filter(Boolean))];
  }

  async function registerWardrobe() {
    if (!wardrobeEnabled() || state.action || !state.wardrobeName.trim()) return;
    const ticket = state.ticket; state.action = "register-wardrobe"; render();
    try {
      await request("POST", apiPath("/wardrobe"), {
        operation_key: state.wardrobeKey || (state.wardrobeKey = operationKey("wardrobe")),
        name: state.wardrobeName.trim(), description: state.wardrobeDescription.trim(), tags: parseTags(state.wardrobeTags),
        asset_id: state.wardrobeAssetId || null,
      });
      if (!live(ticket)) return;
      state.wardrobeName = ""; state.wardrobeDescription = ""; state.wardrobeTags = ""; state.wardrobeAssetId = ""; state.wardrobeKey = operationKey("wardrobe");
      setNotice("衣柜条目已加入当前角色。你可以继续添加，或设为今日穿搭。");
      await loadInventory(ticket);
    } catch (error) { if (live(ticket)) setNotice(errorText(error, "衣柜条目没有保存，请重试。"), true); }
    finally { if (live(ticket)) { state.action = ""; render(); } }
  }

  async function withdrawWardrobe(itemId) {
    if (!itemId || state.action) return;
    const ticket = state.ticket; state.action = `withdraw-wardrobe-${itemId}`; render();
    try {
      await request("POST", apiPath("/wardrobe/withdraw"), {item_id: itemId});
      if (live(ticket)) { setNotice("已撤回这件衣物。已有的历史记录不会被改写。"); await loadInventory(ticket); }
    } catch (error) { if (live(ticket)) setNotice(errorText(error, "衣柜条目撤回没有完成，请重试。"), true); }
    finally { if (live(ticket)) { state.action = ""; render(); } }
  }

  async function selectDailyOutfit(itemId) {
    if (!itemId || !dailyEnabled() || state.action) return;
    const ticket = state.ticket; state.action = `daily-${itemId}`; render();
    try {
      await request("POST", apiPath("/daily-outfit"), {item_id: itemId});
      if (live(ticket)) { setNotice("已更新今天的穿搭选择。"); await loadInventory(ticket); }
    } catch (error) { if (live(ticket)) setNotice(errorText(error, "每日穿搭没有更新，请重试。"), true); }
    finally { if (live(ticket)) { state.action = ""; render(); } }
  }

  function input(event) {
    const target = event.target;
    if (target.matches("[data-im-reference-label]")) state.referenceLabel = target.value;
    if (target.matches("[data-im-wardrobe-name]")) {
      state.wardrobeName = target.value;
      const submit = state.root?.querySelector?.("[data-im-wardrobe-submit]");
      if (submit) submit.disabled = !wardrobeEnabled() || !!state.action || !state.wardrobeName.trim();
    }
    if (target.matches("[data-im-wardrobe-description]")) state.wardrobeDescription = target.value;
    if (target.matches("[data-im-wardrobe-tags]")) state.wardrobeTags = target.value;
  }
  function change(event) {
    const target = event.target;
    if (target.matches("[data-im-role]")) {
      if (target.checked) state.selectedRoles.add(target.dataset.imRole);
      else state.selectedRoles.delete(target.dataset.imRole);
      render();
    }
    if (target.matches("[data-im-wardrobe-asset]")) { state.wardrobeAssetId = target.value; render(); }
  }
  function click(event) {
    const target = event.target.closest("[data-im-refresh],[data-im-load-more],[data-im-select],[data-im-register],[data-im-withdraw-ref],[data-im-wardrobe-submit],[data-im-withdraw-wardrobe],[data-im-daily]");
    if (!target || !state.root?.contains(target)) return;
    if (target.matches("[data-im-refresh]")) { refresh(); return; }
    if (target.matches("[data-im-load-more]")) { loadAlbum(state.ticket, true); return; }
    if (target.matches("[data-im-select]")) {
      const id = target.dataset.imSelect;
      state.selectedImage = id; state.referenceLabel = ""; state.referenceKey = operationKey("reference"); state.selectedRoles = new Set(["identity"]); render(); return;
    }
    if (target.matches("[data-im-register]")) { registerReference(); return; }
    if (target.matches("[data-im-withdraw-ref]")) { withdrawReference(target.dataset.imWithdrawRef); return; }
    if (target.matches("[data-im-wardrobe-submit]")) { registerWardrobe(); return; }
    if (target.matches("[data-im-withdraw-wardrobe]")) { withdrawWardrobe(target.dataset.imWithdrawWardrobe); return; }
    if (target.matches("[data-im-daily]")) { selectDailyOutfit(target.dataset.imDaily); }
  }

  function mount(node) {
    unmount();
    state.root = node || null; state.scope = product()?.scopeKey?.() || ""; state.ticket++;
    state.inventory = null; state.inventoryError = ""; state.album = []; state.albumCursor = null; state.albumLoaded = false; state.albumError = "";
    state.selectedImage = ""; state.selectedRoles = new Set(["identity"]); state.referenceLabel = ""; state.referenceKey = operationKey("reference");
    state.wardrobeName = ""; state.wardrobeDescription = ""; state.wardrobeTags = ""; state.wardrobeAssetId = ""; state.wardrobeKey = operationKey("wardrobe");
    state.action = ""; setNotice("");
    if (!state.root) return;
    state.abort = new AbortController();
    state.root.addEventListener("click", click, {signal: state.abort.signal});
    state.root.addEventListener("input", input, {signal: state.abort.signal});
    state.root.addEventListener("change", change, {signal: state.abort.signal});
    render();
    if (state.scope && role()?.image_material_api) { const ticket = state.ticket; Promise.allSettled([loadInventory(ticket), loadAlbum(ticket)]); }
  }

  function unmount() {
    state.ticket++; state.abort?.abort(); state.abort = null; state.root = null; state.scope = "";
    state.inventory = null; state.album = []; state.albumCursor = null; state.albumLoaded = false; state.albumError = ""; state.inventoryError = ""; state.action = "";
  }

  return {mount, unmount, refresh};
})();
