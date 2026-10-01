/* 人物设定工坊：左边宿主原文（只读），右边草稿（可改），下面是只增不删的版本记录。
 *
 * 这一页只调用两条路由，`persona`（读）与 `persona/command`（追加一版）。
 * **没有任何写回宿主人格的调用，也没有这样的路由存在。** 需要「应用」的时候，
 * 用户自己把右侧文本复制进 AstrBot 的人格设置——这是产品边界，不是待办事项。
 * 用户上一版的抱怨是「问卷改完之后不好再改」，所以这里保留的是可反复修改的草稿，
 * 而不是替用户保存一个他再也认不出来的生成结果。
 */
"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const endpoint = "persona";
  const command = "persona/command";
  const errors = {
    dashboard_identity_required: "请从已登录的 AstrBot 管理界面打开陪伴小屋。",
    staging_not_initialized: "V2 运行实例尚未加载。请先在账号与会话中加载已初始化的配置，再刷新。",
    staging_host_terminated: "插件已经停止，请重新打开管理页面。",
    core_access_required: "当前账号没有管理本安装的权限，看不到人格原文。",
    host_persona_invalid: "AstrBot 返回的人格没有可用的文本（例如只配了示例对话）。本页不猜它的正文，请在 AstrBot 里补上人格提示词。",
    host_persona_unavailable: "这一版宿主装配读不到人格，请确认已初始化运行实例。",
    host_account_changed: "宿主账号已变化，请回到账号与会话重新确认对象。",
    host_conversation_missing: "原来绑定的会话已不存在，请重新绑定后再来。",
    host_conversation_changed: "读取过程中会话被改动，请刷新后重试。",
    persona_note_invalid: "请先写上这一版改了什么（备注必填，200 字以内）。",
    persona_draft_invalid: "草稿必须是文本。",
    persona_draft_too_large: "草稿超出单次保存的长度上限（65536 字）。",
    persona_draft_conflict: "草稿在你编辑期间已经有新版本。已重新读取，请核对后重试。",
    persona_version_unavailable: "这一版已不在当前角色的记录里，请刷新列表。",
    persona_workshop_scope_unsupported: "人格工坊只用于私聊对象的人格；群聊目标没有独立人格文本。",
    persona_workshop_request_invalid: "请求与当前接口不匹配，请刷新页面后重试。",
  };
  const KINDS = {draft: "草稿", restore: "撤回"};
  let bridge = null, state = null, selected = null, busy = false, sequence = 0;

  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const count = (value) => [...String(value ?? "")].length;
  const when = (value) => value && Number.isFinite(Date.parse(value))
    ? new Date(value).toLocaleString("zh-CN", {hour12: false}) : "时间未记录";
  const shortId = (value) => typeof value === "string" && value.length > 12 ? value.slice(-8) : String(value ?? "");

  function notice(message, error = false) {
    const box = $("notice");
    box.textContent = message;
    box.className = error ? "error" : "";
    box.hidden = !message;
  }
  function unwrap(response) {
    const wrapped = ["ok", "error"].includes(response?.status) ? response
      : ["ok", "error"].includes(response?.data?.status) ? response.data : null;
    if (wrapped?.status === "error") {
      /* 后端把机器码放在 message 上，可读原因放在 reason 里；两个都要留，
         否则页面只能显示一串下划线英文。 */
      throw Object.assign(new Error(wrapped.reason || "请求没有完成"), {code: wrapped.message, reason: wrapped.reason});
    }
    const content = wrapped ? wrapped.data : response;
    if (!content || typeof content !== "object") throw new Error("没有收到服务结果。");
    return content;
  }
  /* 后端把码放在 message 上、原因放在 reason 里，两者都可能是可直接展示的句子。 */
  function localized(error) {
    if (errors[error?.code]) return new Error(errors[error.code]);
    const message = [error?.reason, error?.message].find((item) => typeof item === "string" && item && !/^[a-z0-9_]+$/.test(item));
    return new Error(message || "这一操作没有完成，请刷新后重试。");
  }

  function persona() { return state?.persona || {persona_id: "", name: "", text: "", resolved: false}; }
  function current() { return state?.current || null; }
  function expected() { return current()?.version_id || ""; }

  function paintScope() {
    const item = persona();
    $("persona-name").textContent = item.name || item.persona_id || (item.resolved ? "未命名人格" : "未选中人格");
    $("persona-state").textContent = item.resolved ? "已解析到人格" : "没有人格文本";
    $("original-count").textContent = count(item.text) + " 字";
    $("version-count").textContent = state ? String(state.count ?? 0) : "—";
    /* 「没有人格」是一个状态，不是错误：会话可以跟随默认人格。这里解释它，
       而不是让页面看上去像坏了——用户需要知道下一步能做什么。 */
    $("absent").hidden = item.resolved;
  }
  function paintEditors({resetDraft = false} = {}) {
    const item = persona();
    $("original").value = item.text;
    if (resetDraft || $("draft").dataset.loaded !== "1") {
      $("draft").value = current() ? current().draft_text : item.text;
      $("draft").dataset.loaded = "1";
    }
    paintMeters();
  }
  function paintMeters() {
    $("original-meter").textContent = `${count($("original").value)} 字`;
    $("draft-meter").textContent = `${count($("draft").value)} 字`;
    const latest = current();
    $("draft-source").textContent = latest
      ? `第 ${latest.sequence} 版 · ${when(latest.created_at)} · ${KINDS[latest.kind] || latest.kind}`
      : "尚未保存草稿";
  }

  function versionRow(version, index) {
    const item = node("li", undefined, "version-row");
    item.style.setProperty("--i", String(index));
    const button = node("button", undefined, "version-open");
    button.type = "button";
    button.setAttribute("aria-pressed", String(selected?.version_id === version.version_id));
    button.append(
      node("span", `${KINDS[version.kind] || version.kind} · 第 ${version.sequence} 版`, "version-title"),
      node("span", version.note, "version-note"),
      node("span", `${when(version.created_at)} · ${count(version.draft_text)} 字`, "version-meta"));
    button.addEventListener("click", () => {
      selected = selected?.version_id === version.version_id ? null : version;
      paintVersions(); paintPreview();
    });
    item.append(button);
    return item;
  }
  function paintVersions() {
    const list = $("versions");
    list.replaceChildren();
    const versions = state?.versions || [];
    if (!versions.length) {
      const empty = node("li", undefined, "version-empty");
      empty.append(node("strong", "暂无保存版本"));
      list.append(empty);
      return;
    }
    versions.forEach((version, index) => list.append(versionRow(version, index)));
  }
  function previewBlock(title, text, className) {
    const block = node("div", undefined, "preview-block " + (className || ""));
    block.append(node("h3", title));
    /* <pre> 而不是 <p>：正文里的换行、缩进和结尾空白都是内容的一部分，
       HTML 折叠空白会把「原文长什么样」显示错，而这一页的全部意义就是对照。 */
    block.append(node("pre", text === "" ? "（空）" : text, "preview-text"));
    return block;
  }
  function paintPreview() {
    const host = $("preview");
    host.replaceChildren();
    if (!selected) {
      const placeholder = node("div", undefined, "placeholder");
      placeholder.append(node("span", "✦", "placeholder-mark"), node("h2", "选择一版查看"));
      host.append(placeholder);
      return;
    }
    const head = node("div", undefined, "preview-head");
    head.append(node("h2", `${KINDS[selected.kind] || selected.kind} · 第 ${selected.sequence} 版`),
      node("p", `${when(selected.created_at)} · ${selected.note} · ${shortId(selected.version_id)}`, "muted"));
    host.append(head);
    if (selected.restored_from) {
      host.append(node("p", `这一版是从 ${shortId(selected.restored_from)} 撤回得到的。`, "muted"));
    }
    host.append(previewBlock("这一版的正文", selected.draft_text, "draft"));
    /* 每版都带着它当时对着的原文：过一阵回头看，仍然知道改的是哪份底稿。
       用户最初的痛点正是「不知道在跟什么对照」。 */
    host.append(previewBlock("它当时对着的原文" + (selected.persona_name ? `（${selected.persona_name}）` : ""),
      selected.original_text, "original"));
    const actions = node("div", undefined, "preview-actions");
    const restore = node("button", undefined, "primary small");
    restore.type = "button";
    restore.textContent = "把这一版放回右侧";
    restore.disabled = busy || selected.version_id === current()?.version_id;
    restore.addEventListener("click", () => send({action: "restore", version_id: selected.version_id,
      note: restoreNote(selected), expected_current: expected()}));
    const copy = node("button", undefined, "secondary small");
    copy.type = "button";
    copy.textContent = "复制这一版";
    copy.addEventListener("click", () => copyText(selected.draft_text, "这一版"));
    actions.append(restore, copy);
    host.append(actions);
  }
  /* 撤回的备注由程序写清楚「撤回到哪一版」——那正是这条记录需要说明的事，
     而手打一遍反而容易写成没法对照的「回退」。 */
  function restoreNote(version) {
    const typed = $("note").value.trim();
    return typed || `撤回到第 ${version.sequence} 版（${when(version.created_at)}）`;
  }

  async function copyText(text, label) {
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
      else throw new Error("clipboard unavailable");
      notice(`${label}已复制到剪贴板，可以粘贴到 AstrBot 的人格设置里保存。`);
    } catch {
      notice(`当前环境不允许脚本写剪贴板。请在上方文本框里 Ctrl/⌘+A 全选后复制${label}。`, true);
    }
  }

  async function send(payload) {
    if (busy) return;
    if (!bridge) { notice(errors.dashboard_identity_required, true); return; }
    busy = true;
    paintPreview();
    try {
      const before = expected();
      const result = unwrap(await bridge.apiPost(command, payload));
      await load({quiet: true});
      notice(payload.action === "restore"
        ? `已把第 ${result.version.sequence} 版放回右侧（新增一版，历史没有被改写）。`
        : `已存为第 ${result.version.sequence} 版。记得把它复制到 AstrBot 里保存。`);
      if (payload.action === "save") $("note").value = "";
      selected = result.version;
      paintVersions(); paintPreview();
      if (before && before !== expected()) $("draft").dataset.loaded = "1";
    } catch (error) {
      const failure = localized(error);
      if (error?.code === "persona_draft_conflict") {
        await load({quiet: true});
        paintEditors();
      }
      notice(failure.message, true);
    } finally {
      busy = false;
      paintPreview();
    }
  }

  async function load({quiet = false} = {}) {
    const ticket = ++sequence;
    if (!quiet) notice("");
    try {
      const limit = Number($("limit").value) || 30;
      const result = unwrap(await bridge.apiGet(endpoint, {limit}));
      if (ticket !== sequence) return;
      state = result;
      if (!selected || !(result.versions || []).some((item) => item.version_id === selected.version_id)) {
        selected = null;
      }
      paintScope(); paintEditors(); paintVersions(); paintPreview();
    } catch (error) {
      if (ticket !== sequence) return;
      state = null;
      paintScope(); paintVersions(); paintPreview();
      $("original").value = ""; $("draft").value = ""; $("draft").dataset.loaded = "";
      paintMeters();
      notice(localized(error).message, true);
    }
  }

  $("refresh").addEventListener("click", () => load());
  $("limit").addEventListener("change", () => load());
  $("save").addEventListener("click", () => {
    const note = $("note").value.trim();
    if (!note) { notice(errors.persona_note_invalid, true); $("note").focus(); return; }
    send({action: "save", text: $("draft").value, note, expected_current: expected()});
  });
  $("note").addEventListener("keydown", (event) => { if (event.key === "Enter") $("save").click(); });
  $("copy-original").addEventListener("click", () => copyText($("original").value, "原文"));
  $("copy-draft").addEventListener("click", () => copyText($("draft").value, "草稿"));
  $("reset-draft").addEventListener("click", () => {
    paintEditors({resetDraft: true});
    notice("右侧已还原为" + (current() ? "最近一版草稿" : "原文") + "。");
  });
  $("draft").addEventListener("input", paintMeters);

  (async function start() {
    bridge = window.AstrBotPluginPage;
    if (!bridge) { notice(errors.dashboard_identity_required, true); return; }
    try { await bridge.ready(); await load(); }
    catch (error) { notice(localized(error).message, true); }
  })();
})();
