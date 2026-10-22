/* Explicit management actions; background refreshes only read local snapshots. */
"use strict";
window.CompanionNativeExtensionManagement = (() => {
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const qrSource = value => /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(String(value || "")) ? value : "";
  const cameraPreviewSource = value => /^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(String(value || "")) ? value : "";
  const actionNames = {mihome_start_login:"扫码登录", mihome_login_status:"检查登录状态", mihome_sync_devices:"同步设备", mihome_logout:"退出米家账号",
    scan_camera:"扫描摄像头", consent_camera:"更新摄像头确认", update_camera_policy:"保存摄像头策略", connect:"连接 VTube Studio", request_auth:"请求 VTS 授权", list_hotkeys:"读取热键",
    scan_audio:"扫描音频设备", select_audio:"保存音频输出", test_audio:"播放设备测试音", request_audio_consent:"准备本人音频授权", revoke_audio_consent:"撤销音频授权",
    update_audio_policy:"保存语音策略", save:"保存叫醒安排", disable:"关闭叫醒", stop_session:"停止本次叫醒", test:"试听叫醒", cancel_reminder:"取消提醒"};
  actionNames.test_camera = "测试摄像头调用";
  const errors = {
    native_extension_inactive:"模块已暂停，请先启用模块再操作。",
    native_management_unavailable:"管理操作尚未就绪，请重新读取状态。",
    native_extension_action_failed:"操作未完成，请核对当前连接和配置。",
    vts_not_connected:"VTube Studio 尚未连接，请先连接。",
    vts_not_authenticated:"VTube Studio 尚未授权，请请求授权并在 VTS 弹窗中点允许。",
    vts_auth_timeout:"等待授权超时。请在 VTube Studio 弹窗中点允许，再重新连接核对授权结果。",
    camera_user_ineligible:"此用户没有主机摄像头使用权限，请选择管理员或主要用户。",
    camera_consent_required:"请先确认该用户的摄像头授权，再保存启用策略。",
    camera_user_not_configured:"请先确认该用户的摄像头授权，再保存使用策略。",
    native_mihome_unavailable:"米家运行时不可用，请在 AstrBot 运行环境安装米家依赖后重载插件。",
    native_service_not_running:"此模块尚未运行，请启用模块并等待启动完成。",
    native_service_changed:"模块已停止或重新配置，请刷新当前状态。",
    native_reality_action_failed:"操作未完成，请核对现实设备配置和当前用户授权。",
    native_reality_playback_failed:"音频未能播放，请核对输出设备、TTS 与当前用户授权。",
    native_reality_reminder_not_cancelled:"提醒未取消，请刷新提醒状态。",
    native_management_result_unknown:"操作结果暂不可确认，请刷新状态核对后再决定下一步。",
    native_vts_authorization_denied:"VTube Studio 未允许此次授权，请重新请求并在弹窗中点允许。",
    native_vts_authorization_required:"请在 VTube Studio 开启 API，并点击请求 VTS 授权。",
    native_vts_action_timeout:"操作超时，请核对 VTube Studio 连接，并在授权弹窗中点允许后重新连接。",
    native_vts_action_failed:"VTube Studio 操作未完成，请检查连接和设备状态。",
  };
  class Management {
    constructor(root, options) {
      this.root = root; this.options = options; this.name = options.extensionId;
      this.record = options.record; this.alive = true; this.busy = false; this.blocked = false; this.reads = 0;
      const saved = options.getState?.();
      this.cameraUser = saved?.user || ""; this.cameraDraft = saved?.draft || null;
      this.cameraOpen = saved?.open || false; this.cameraConsent = saved?.consent || false;
      this.audioOpen = saved?.audioOpen || false; this.audioDraft = saved?.audioDraft || null;
      this.cameraTestResult = saved?.cameraTestResult || null; this.cameraPreview = saved?.cameraPreview || null;
      this.click = event => this.onClick(event);
      this.change = event => this.onChange(event);
      root.addEventListener("click", this.click); root.addEventListener("change", this.change);
      this.render();
    }
    current() { return this.alive && this.root.isConnected !== false; }
    stop() {
      this.alive = false; clearTimeout(this.timer); this.timer = null;
      this.root.removeEventListener("click", this.click); this.root.removeEventListener("change", this.change);
    }
    update(record) { this.saveCameraDraft(); this.record = record; if (this.current()) this.render(); }
    setBlocked(value) { this.blocked = value; this.updateButtons(); }
    button(action, text = actionNames[action], extra = "") {
      if (action.startsWith("mihome_")) extra += " data-native-requires-mihome";
      return `<button class="button small" type="button" data-native-action="${action}" ${extra}>${escape(text)}</button>`;
    }
    notice(message, failed = false) {
      this.message = message; this.failed = failed;
      const node = this.root.querySelector("[data-native-action-notice]");
      if (node) { node.textContent = message; node.classList.toggle("is-error", failed); }
    }
    render() {
      if (!["reality", "live"].includes(this.name)) { this.root.innerHTML = ""; return; }
      if (!this.record.management) {
        this.root.innerHTML = `<section class="native-management"><h4>连接与设备管理</h4><p>管理状态尚未读取。</p><button class="button small" type="button" data-native-management-refresh>重新读取管理状态</button><p data-native-action-notice role="status" aria-live="polite"></p></section>`;
      } else this.root.innerHTML = this.name === "reality" ? this.reality() : this.live();
      if (this.name === "reality") {
        const cameraBody = this.root.querySelector("[data-native-camera-details] .native-management-body");
        if (cameraBody) cameraBody.insertAdjacentHTML("beforeend",
          `<div class="native-management-actions">${this.button("test_camera")}</div>${this.cameraTestMarkup()}`);
      }
      this.updateButtons(); this.notice(this.message || "", this.failed);
      this.scheduleRead();
    }
    reality() {
      const data = this.record.management, mi = data.mihome || {}, auth = mi.auth || {}, login = mi.login || {};
      const available = mi.available !== false && (mi.available === true || !!mi.auth || !!mi.login);
      const logged = auth.logged_in === true || login.credential_present === true;
      const loginLabels = {idle:"尚未登录", starting:"正在生成二维码", waiting:"等待扫码确认", pending:"等待扫码确认", success:"登录成功", already_logged_in:"已登录", expired:"二维码已过期", timeout:"登录已超时", error:"登录未完成"};
      const state = !available ? mi.available === false ? "米家运行时不可用" : "米家状态未读取"
        : logged ? "已登录" : loginLabels[login.status] || (login.running ? "等待扫码确认" : "尚未登录");
      const qr = qrSource(login.qr_image || this.lastQr);
      if (login.qr_available && login.qr_image) this.lastQr = qr;
      if (!login.qr_available || logged) this.lastQr = "";
      const qrMarkup = available && login.qr_available && !logged && qr ? `<div class="native-management-qr"><img src="${escape(qr)}" alt="米家登录二维码" width="180" height="180"><p>用米家 App 扫描，并在手机上确认登录。</p></div>` : "";
      const devices = Array.isArray(mi.devices) ? mi.devices : [];
      const devicesMarkup = devices.length ? `<div class="native-management-table"><table><thead><tr><th>设备</th><th>位置</th><th>状态</th></tr></thead><tbody>${devices.map(device => `<tr><td>${escape(device.name || device.alias || device.did || "设备")}<small>${escape(device.model || "")}</small></td><td>${escape([device.home_name, device.room_name].filter(Boolean).join(" · ") || device.room || "—")}</td><td>${device.online === true ? "在线" : device.online === false ? "离线" : "尚未读取"}</td></tr>`).join("")}</tbody></table></div>` : `<p class="native-management-muted">${!available ? "米家就绪后可登录并同步设备。" : logged ? "设备目录还是空的，点击同步设备读取。" : "登录后可以同步设备。"}</p>`;
      return `<div class="native-management"><details open><summary>米家账号与设备 <span>${escape(state)}</span></summary><div class="native-management-body"><div class="native-management-actions">${this.button("mihome_start_login", logged ? "重新扫码登录" : "扫码登录")}${this.button("mihome_login_status")}${this.button("mihome_sync_devices", undefined, logged ? "" : "data-native-requires-login")}${this.button("mihome_logout", undefined, logged ? "" : "data-native-requires-login")}</div>${qrMarkup}<p class="native-management-muted">${escape(!available ? mi.reason || "米家管理状态暂不可读取，请刷新核对。" : login.message || auth.last_login_error || "")}</p>${devicesMarkup}${mi.snapshot_at ? `<small class="native-management-muted">最近同步：${escape(mi.snapshot_at)}</small>` : ""}</div></details>${this.camera(data)}${this.audio(data)}<div class="native-management-bottom"><button class="button small" type="button" data-native-management-refresh>刷新管理状态</button><p data-native-action-notice role="status" aria-live="polite"></p></div></div>`;
    }
    camera(data) {
      const users = Array.isArray(data.users) ? data.users : [], camera = data.camera || {};
      const selected = window.CompanionProduct?.target?.();
      if (!this.cameraUser) this.cameraUser = selected?.scope_kind === "private" ? String(selected.participant_id || "") : String(users[0]?.user_id || "");
      const user = users.find(row => String(row.user_id) === this.cameraUser), policy = {...(user?.camera || {}), ...(this.cameraDraft || {})};
      const eligible = user?.camera?.eligible, consented = user?.camera?.consented === true;
      const state = !Array.isArray(data.users) ? "授权状态未读取" : !user?.camera ? "尚无摄像头授权记录"
        : eligible === false ? "当前用户不可用" : consented ? "已确认授权" : "尚未确认";
      const modes = [["off","仅明确请求"],["ask","主动前先询问"],["auto","按授权主动"]];
      const cameras = Array.isArray(camera.devices) ? camera.devices : [];
      const list = cameras.length ? `<ul class="native-management-camera-devices">${cameras.map(device => `<li>${escape(device.name || device.label || "摄像头")} <span>索引 ${escape(device.index ?? device.camera_index ?? "—")}</span></li>`).join("")}</ul>` : `<p class="native-management-muted">尚未发现摄像头，点击扫描摄像头读取设备目录。</p>`;
      return `<details data-native-camera-details ${this.cameraOpen ? "open" : ""}><summary>摄像头确认与策略 <span>${state}</span></summary><div class="native-management-body"><p class="native-management-muted">${escape(camera.boundary || "按明确任务读取摄像头单帧，画面可能发送给所选视觉模型；默认不保存原图。")}</p><label class="native-management-field">用户 QQ / ID<input type="text" data-native-camera-user list="native-camera-users-${this.options.instance}" value="${escape(this.cameraUser)}" placeholder="选择或填写要管理的用户"><datalist id="native-camera-users-${this.options.instance}">${users.map(row => `<option value="${escape(row.user_id)}">${escape(row.label || row.user_id)}</option>`).join("")}</datalist></label><p class="native-management-camera-state">${escape(user?.label || this.cameraUser || "尚未选择用户")} · ${state}</p><label class="native-management-consent"><input type="checkbox" data-native-camera-consent ${this.cameraConsent ? "checked" : ""}><span>我已了解单帧读取和视觉模型处理方式，确认给此用户授权。</span></label><div class="native-management-actions">${this.button("consent_camera", "确认摄像头授权", "data-native-consent=\"true\" data-native-requires-consent")}${this.button("consent_camera", "撤销摄像头授权", "data-native-consent=\"false\"")}</div><fieldset class="native-management-policy"><legend>此用户的使用策略</legend><label class="native-management-consent"><input type="checkbox" data-native-camera-enabled ${policy.enabled ? "checked" : ""}>允许使用摄像头</label><label class="native-management-field">主动读取方式<select data-native-camera-mode>${modes.map(([value, title]) => `<option value="${value}" ${value === (policy.proactive_mode || "off") ? "selected" : ""}>${title}</option>`).join("")}</select></label><label class="native-management-field">每天主动读取次数<input type="number" data-native-camera-daily min="-1" max="10" step="1" value="${escape(policy.proactive_max_daily ?? -1)}"><small>-1 跟随全局设置，0 关闭主动读取。</small></label>${this.button("update_camera_policy")}</fieldset><div class="native-management-actions">${this.button("scan_camera")}</div>${list}${camera.devices_error ? `<p class="native-management-muted">${escape(camera.devices_error)}</p>` : ""}</div></details>`;
    }
    cameraTestMarkup() {
      const test = this.cameraTestResult;
      if (!test) return "";
      const preview = cameraPreviewSource(this.cameraPreview?.data_url);
      const title = test.status === "error" ? "摄像头测试未完成"
        : test.status === "observation_uncertain" ? "已读取，识别结果不确定" : "摄像头测试完成";
      return `<div class="native-management-camera-test" data-native-camera-test role="status" aria-live="polite"><strong>${title}</strong><p>${escape(test.message || "")}</p>${test.summary ? `<p>视觉摘要：${escape(test.summary)}</p>` : ""}${preview ? `<img class="native-management-camera-preview" src="${escape(preview)}" alt="摄像头测试单帧预览" loading="lazy">` : ""}</div>`;
    }
    audio(data) {
      const users = Array.isArray(data.users) ? data.users : [], output = data.audio_output || {};
      const user = users.find(row => String(row.user_id) === this.cameraUser), draft = this.audioDraft || {};
      const alarm = {...(user?.alarm || {}), ...(draft.alarm || {})}, policy = {...(user?.policy || {}), ...(draft.policy || {})};
      const consented = user?.consent?.local_audio === true || user?.consent?.confirmed === true;
      const devices = Array.isArray(output.devices) ? output.devices : [], selected = draft.device_id || output.selected_device_id || "system_default";
      const number = (key, title, value, min, max) => `<label class="native-management-field">${title}<input type="number" data-native-audio-input="${key}" min="${min}" max="${max}" step="1" value="${escape(value)}"></label>`;
      const days = Array.isArray(alarm.days) ? alarm.days : [0,1,2,3,4,5,6];
      const modes = [["audio_only","仅本机语音"],["audio_and_chat","本机语音与私聊"],["chat_on_failure","语音失败时发私聊"]];
      const reminders = (Array.isArray(user?.custom_reminders) ? user.custom_reminders : []).filter(row => ["registering","scheduled","triggered","delivering"].includes(row.status));
      return `<details data-native-audio-details ${this.audioOpen ? "open" : ""}><summary>本机语音与叫醒 <span>${consented ? "本人已授权" : "等待本人授权"}</span></summary><div class="native-management-body">
        <label class="native-management-field">音频输出<select data-native-audio-device>${(!devices.some(row => row.id === selected) ? `<option value="${escape(selected)}">${escape(output.label || "跟随系统默认输出")}</option>` : "")}${devices.map(row => `<option value="${escape(row.id)}" ${row.id === selected ? "selected" : ""}>${escape(row.name || row.id)}</option>`).join("")}</select></label>
        ${number("output_volume","设备测试音量（0–100）",draft.output_volume ?? output.playback_volume ?? 35,0,100)}
        <div class="native-management-actions">${this.button("scan_audio")}${this.button("select_audio")}${this.button("test_audio")}</div>${output.error ? `<p class="native-management-muted">${escape(output.error)}</p>` : ""}
        <label class="native-management-field">语音与叫醒用户 QQ / ID<input type="text" data-native-audio-user list="native-camera-users-${this.options.instance}" value="${escape(this.cameraUser)}" placeholder="选择已有私聊的用户"></label>
        <p class="native-management-muted">${escape(user?.label || this.cameraUser || "尚未选择用户")} · ${consented ? "本人音频授权已生效" : "准备授权后，将提示文字发到本人的私聊，由本人确认。"}</p>
        <div class="native-management-actions">${this.button("request_audio_consent")}${this.button("revoke_audio_consent")}</div>
        <fieldset class="native-management-policy"><legend>主动语音</legend><label class="native-management-consent"><input type="checkbox" data-native-audio-proactive ${policy.proactive_voice_enabled ? "checked" : ""}>将主动联系同步播放到本机</label>${number("policy_volume","主动语音音量（0–100）",policy.playback_volume ?? 35,0,100)}${this.button("update_audio_policy")}</fieldset>
        <fieldset class="native-management-policy"><legend>叫醒安排</legend><label class="native-management-consent"><input type="checkbox" data-native-alarm-enabled ${alarm.enabled ? "checked" : ""}>启用此用户的叫醒安排</label><label class="native-management-field">叫醒时间<input type="time" data-native-alarm-time value="${escape(alarm.time || "07:30")}"></label>
        <div class="native-management-days" role="group" aria-label="重复日期">${["周一","周二","周三","周四","周五","周六","周日"].map((label,index) => `<label class="native-management-consent"><input type="checkbox" data-native-alarm-day="${index}" ${days.includes(index) ? "checked" : ""}>${label}</label>`).join("")}</div>
        <label class="native-management-field">叫醒话题<input type="text" data-native-alarm-message maxlength="240" value="${escape(alarm.message || "")}" placeholder="例如提醒吃早餐，文案由角色生成"></label>
        <label class="native-management-field">通知方式<select data-native-alarm-delivery>${modes.map(([value,title]) => `<option value="${value}" ${value === (alarm.delivery_mode || "chat_on_failure") ? "selected" : ""}>${title}</option>`).join("")}</select></label>
        <div class="native-management-grid">${[["playback_volume","叫醒音量（0–100）",alarm.playback_volume ?? 35,0,100],["repeat_count","每次播放次数",alarm.repeat_count ?? 1,1,6],["repeat_interval_seconds","播放间隔（秒）",alarm.repeat_interval_seconds ?? 20,5,300],["snooze_minutes","稍后再叫（分钟）",alarm.snooze_minutes ?? 10,1,120],["volume_step","每次递增音量",alarm.volume_step ?? 8,0,30],["max_volume","最大音量（0–100）",alarm.max_volume ?? 70,0,100],["fade_in_ms","音量渐入（毫秒）",alarm.fade_in_ms ?? 800,0,5000]].map(args => number(...args)).join("")}</div>
        <label class="native-management-consent"><input type="checkbox" data-native-alarm-ack ${alarm.require_acknowledgement !== false ? "checked" : ""}>在私聊中确认起床后停止</label>
        <div class="native-management-actions">${this.button("save")}${this.button("disable")}${this.button("stop_session")}${this.button("test")}</div><p class="native-management-muted">${alarm.next_trigger_text ? `下次叫醒：${escape(alarm.next_trigger_text)}` : "尚无下次叫醒时间"}${alarm.contact_session?.status ? ` · 本次状态：${escape(alarm.contact_session.status)}` : ""}</p></fieldset>
        ${reminders.length ? `<fieldset class="native-management-policy"><legend>待办提醒</legend><ul class="native-management-reminders">${reminders.map(row => `<li><span>${escape(row.scheduled_text || "时间待确认")} · ${escape(row.topic || "提醒")}</span>${this.button("cancel_reminder","取消这条提醒",`data-native-reminder-id="${escape(row.id)}"`)}</li>`).join("")}</ul></fieldset>` : ""}
      </div></details>`;
    }
    live() {
      const data = this.record.management, connected = data.connected === true, authenticated = data.authenticated === true;
      const hotkeys = Array.isArray(data.hotkeys) ? data.hotkeys : [];
      const label = authenticated ? "已连接并授权" : connected ? "已连接 · 等待授权" : "尚未连接";
      const table = hotkeys.length ? `<div class="native-management-table"><table><thead><tr><th>热键</th><th>ID</th><th>表情配置</th></tr></thead><tbody>${hotkeys.map((hotkey, index) => `<tr><td>${escape(hotkey.name || "未命名热键")}</td><td><code>${escape(hotkey.hotkeyID || hotkey.hotkey_id || hotkey.id || "")}</code></td><td><button class="button small" type="button" data-native-use-hotkey="${index}">添加到表情</button></td></tr>`).join("")}</tbody></table></div>` : `<p class="native-management-muted">连接并授权后，点击读取热键查看当前模型的可用表情。</p>`;
      return `<section class="native-management"><header><h4>VTube Studio</h4><span>${label}</span></header><p class="native-management-muted">先在 VTube Studio 开启 API。请求授权后，在 VTS 弹窗中点“允许”，再读取当前模型的热键。</p>${data.error_code ? `<p class="native-management-muted">${escape(errors[data.error_code] || "连接尚未就绪，请核对设备状态。")}</p>` : ""}<div class="native-management-actions">${this.button("connect", connected ? "重新连接" : "连接 VTube Studio")}${this.button("request_auth", "请求 VTS 授权")}${this.button("list_hotkeys", "读取热键", authenticated ? "" : "data-native-requires-auth")}</div>${table}<div class="native-management-bottom"><button class="button small" type="button" data-native-management-refresh>刷新管理状态</button><p data-native-action-notice role="status" aria-live="polite"></p></div></section>`;
    }
    updateButtons() {
      const mi = this.record.management?.mihome, logged = mi?.auth?.logged_in === true || mi?.login?.credential_present === true;
      const mihomeAvailable = mi?.available !== false && (mi?.available === true || !!mi?.auth || !!mi?.login);
      const consent = this.root.querySelector("[data-native-camera-consent]")?.checked === true;
      this.root.querySelectorAll("[data-native-action], [data-native-use-hotkey]").forEach(button => {
        button.disabled = this.busy || this.blocked || button.hasAttribute("data-native-requires-login") && !logged
          || button.hasAttribute("data-native-requires-mihome") && !mihomeAvailable
          || button.hasAttribute("data-native-requires-auth") && this.record.management?.authenticated !== true
          || button.hasAttribute("data-native-requires-consent") && !consent;
      });
      const refresh = this.root.querySelector("[data-native-management-refresh]");
      if (refresh) refresh.disabled = this.busy || this.blocked;
      this.root.querySelectorAll("input, select").forEach(node => { node.disabled = this.busy || this.blocked; });
      this.root.setAttribute("aria-busy", String(this.busy));
    }
    saveCameraDraft() {
      this.saveAudioDraft();
      const node = this.root.querySelector("[data-native-camera-enabled]");
      if (!node) return;
      this.cameraOpen = this.root.querySelector("[data-native-camera-details]").open;
      const draft = {enabled:node.checked, proactive_mode:this.root.querySelector("[data-native-camera-mode]").value,
        proactive_max_daily:Number(this.root.querySelector("[data-native-camera-daily]").value)};
      const stored = this.record.management?.users?.find(row => String(row.user_id) === this.cameraUser)?.camera;
      this.cameraDraft = this.differences(draft, {enabled:stored?.enabled === true,
        proactive_mode:stored?.proactive_mode || "off", proactive_max_daily:stored?.proactive_max_daily ?? -1});
      this.publishState();
    }
    differences(values, stored) {
      const result = {};
      for (const [key, value] of Object.entries(values)) {
        if (value && typeof value === "object" && !Array.isArray(value)) {
          const nested = this.differences(value, stored?.[key]);
          if (nested) result[key] = nested;
        } else if (JSON.stringify(value) !== JSON.stringify(stored?.[key])) result[key] = value;
      }
      return Object.keys(result).length ? result : null;
    }
    storedAudioValues() {
      const data = this.record.management || {}, output = data.audio_output || {};
      const user = data.users?.find(row => String(row.user_id) === this.cameraUser);
      const policy = user?.policy || {}, alarm = user?.alarm || {};
      return {device_id:output.selected_device_id || "system_default", output_volume:output.playback_volume ?? 35,
        policy:{proactive_voice_enabled:policy.proactive_voice_enabled === true, playback_volume:policy.playback_volume ?? 35},
        alarm:{enabled:alarm.enabled === true, time:alarm.time || "07:30", message:alarm.message || "",
          delivery_mode:alarm.delivery_mode || "chat_on_failure", require_acknowledgement:alarm.require_acknowledgement !== false,
          days:Array.isArray(alarm.days) ? alarm.days : [0,1,2,3,4,5,6],
          playback_volume:alarm.playback_volume ?? 35, repeat_count:alarm.repeat_count ?? 1,
          repeat_interval_seconds:alarm.repeat_interval_seconds ?? 20, snooze_minutes:alarm.snooze_minutes ?? 10,
          volume_step:alarm.volume_step ?? 8, max_volume:alarm.max_volume ?? 70, fade_in_ms:alarm.fade_in_ms ?? 800}};
    }
    audioFormValues() {
      const value = key => {
        const text = this.root.querySelector(`[data-native-audio-input="${key}"]`).value;
        return text.trim() ? Number(text) : "";
      };
      const alarm = {enabled:this.root.querySelector("[data-native-alarm-enabled]").checked,
        time:this.root.querySelector("[data-native-alarm-time]").value,
        message:this.root.querySelector("[data-native-alarm-message]").value,
        delivery_mode:this.root.querySelector("[data-native-alarm-delivery]").value,
        require_acknowledgement:this.root.querySelector("[data-native-alarm-ack]").checked,
        days:[...this.root.querySelectorAll("[data-native-alarm-day]:checked")].map(node => Number(node.dataset.nativeAlarmDay))};
      for (const key of ["playback_volume","repeat_count","repeat_interval_seconds","snooze_minutes","volume_step","max_volume","fade_in_ms"]) alarm[key] = value(key);
      return {device_id:this.root.querySelector("[data-native-audio-device]").value, output_volume:value("output_volume"),
        policy:{proactive_voice_enabled:this.root.querySelector("[data-native-audio-proactive]").checked, playback_volume:value("policy_volume")}, alarm};
    }
    saveAudioDraft() {
      if (!this.root.querySelector("[data-native-audio-device]")) return;
      this.audioOpen = this.root.querySelector("[data-native-audio-details]").open;
      const values = this.audioFormValues();
      this.audioDraft = this.differences(values, this.storedAudioValues());
      this.publishState();
      return values;
    }
    publishState() { this.options.onState?.({user:this.cameraUser, draft:this.cameraDraft, open:this.cameraOpen, consent:this.cameraConsent, audioOpen:this.audioOpen, audioDraft:this.audioDraft, cameraTestResult:this.cameraTestResult, cameraPreview:this.cameraPreview}); }
    async read({quiet = false} = {}) {
      if (!this.current() || this.reading || this.busy && !quiet) return;
      this.reading = true;
      const operation = this.operation;
      try {
        const result = await window.CompanionProduct.request("GET", "extensions");
        if (!this.current() || operation !== this.operation) return;
        const record = result?.extensions?.[this.name];
        if (!record?.management) throw {code:"native_management_unavailable"};
        this.saveCameraDraft(); this.record.management = record.management;
        this.options.onRead?.(record); this.render();
        if (!quiet) this.notice("管理状态已刷新。");
      } catch (error) { if (this.current() && operation === this.operation && !quiet) this.notice(errors[error?.code] || "管理状态暂时读取不到，请重新刷新。", true); }
      finally { this.reading = false; }
    }
    scheduleRead() {
      const login = this.record.management?.mihome?.login;
      if (this.name !== "reality" || !login?.running || this.timer || this.reads >= 75) return;
      this.timer = setTimeout(async () => { this.timer = null; this.reads++; if (this.current()) await this.read(); }, 2000);
    }
    async run(action, payload) {
      if (this.busy || this.blocked || !this.current()) return;
      this.operation = (this.operation || 0) + 1;
      this.saveCameraDraft(); this.busy = true; this.options.onBusy?.(true); this.updateButtons();
      const waiting = action === "request_auth" ? "请在 VTube Studio 弹窗中点“允许”，正在等待授权结果…" : `正在${actionNames[action] || "执行操作"}…`;
      this.notice(waiting);
      try {
        const record = await window.CompanionProduct.request("POST", "extensions/action", {extension_id:this.name, action, payload}, {timeoutMs:action === "test_camera" ? 130000 : 65000});
        if (!this.current()) return;
        if (!record?.management) throw {code:"invalid_response"};
        this.record = record;
        if (action === "test_camera") {
          const result = record.result || {}, observation = result.observation || {};
          this.cameraTestResult = {status:result.captured === true ? result.status || "success" : "error",
            message:result.message || (result.captured === true ? "已完成摄像头单帧测试。" : "摄像头测试没有取得有效画面。"),
            summary:observation.summary || observation.purpose_answer || observation.scene_description || ""};
          const preview = record.camera_preview;
          this.cameraPreview = result.captured === true && preview?.ephemeral === true
            && String(preview.user_id) === String(payload.user_id) && cameraPreviewSource(preview.data_url) ? preview : null;
          this.publishState();
        }
        if (action === "update_camera_policy") this.cameraDraft = null;
        if (action === "consent_camera" && this.cameraDraft) delete this.cameraDraft.enabled;
        if (action === "consent_camera" || action === "update_camera_policy") { this.cameraConsent = false; this.publishState(); }
        if (this.audioDraft) {
          if (action === "select_audio") { delete this.audioDraft.device_id; delete this.audioDraft.output_volume; }
          if (action === "update_audio_policy") delete this.audioDraft.policy;
          if (action === "save") delete this.audioDraft.alarm;
          if (["disable","revoke_audio_consent"].includes(action) && this.audioDraft.alarm) delete this.audioDraft.alarm.enabled;
          if (action === "revoke_audio_consent" && this.audioDraft.policy) delete this.audioDraft.policy.proactive_voice_enabled;
          this.publishState();
        }
        this.options.onRecord?.(record);
        if (!this.current()) return;
        this.render();
        if (record.result?.confirmation_required) this.notice(record.result.prompt || "请由本人在私聊中完成音频授权确认。");
        else if (action === "request_auth" && record.management.authenticated !== true) this.notice("授权还未完成。请到 VTube Studio 弹窗中点“允许”，再重新连接核对。", true);
        else if (action === "mihome_start_login") { this.reads = 0; this.notice("登录已发起，请用米家 App 扫码确认。"); this.scheduleRead(); }
        else if (action === "test_camera") this.notice(this.cameraTestResult.message, this.cameraTestResult.status === "error");
        else this.notice(`${actionNames[action] || "操作"}已完成。`);
      } catch (error) {
        if (this.current()) {
          const message = errors[error?.code] || window.CompanionProduct.errorLabel?.(error?.code) || "操作结果暂未确认，请刷新状态核对后再试。";
          if (action === "test_camera") { this.cameraTestResult = {status:"error", message, summary:""}; this.cameraPreview = null; this.publishState(); }
          this.notice(message, true);
          await this.read({quiet:true});
        }
      } finally {
        if (this.current()) { this.busy = false; this.options.onBusy?.(false); this.updateButtons(); }
      }
    }
    payload(action, button) {
      if (action === "mihome_login_status") return {qr_revision:this.record.management?.mihome?.login?.qr_revision || ""};
      if (["select_audio","test_audio","request_audio_consent","revoke_audio_consent","update_audio_policy","save","disable","stop_session","test","cancel_reminder"].includes(action)) {
        const draft = this.saveAudioDraft();
        if (action === "select_audio") return {device_id:draft.device_id, playback_volume:draft.output_volume};
        if (action === "test_audio") return {playback_volume:draft.output_volume};
        const user_id = this.root.querySelector("[data-native-audio-user]").value.trim();
        if (!user_id) throw new Error("先选择已有私聊的用户。");
        if (action === "update_audio_policy") return {user_id, ...draft.policy};
        if (action === "save") {
          if (!draft.alarm.time || !draft.alarm.days.length) throw new Error("请选择叫醒时间和至少一个重复日期。");
          const invalid = [...this.root.querySelectorAll("[data-native-audio-input]")].find(node => !node.value.trim() || !node.checkValidity());
          if (invalid) { invalid.focus(); throw new Error("请填写范围内的整数音量与叫醒参数。"); }
          return {user_id, ...draft.alarm};
        }
        if (action === "test") return {user_id, playback_volume:draft.alarm.playback_volume, message:draft.alarm.message};
        if (action === "cancel_reminder") return {user_id, reminder_id:button.dataset.nativeReminderId};
        return {user_id};
      }
      if (["consent_camera", "update_camera_policy"].includes(action)) {
        const user_id = this.root.querySelector("[data-native-camera-user]").value.trim();
        if (!user_id) throw new Error("先选择或填写要管理的用户。");
        if (action === "consent_camera") return {user_id, confirmed:button.dataset.nativeConsent === "true"};
        const daily = this.root.querySelector("[data-native-camera-daily]").value;
        const proactive_max_daily = Number(daily);
        if (!daily.trim() || !Number.isInteger(proactive_max_daily) || proactive_max_daily < -1 || proactive_max_daily > 10) throw new Error("主动读取次数应为 -1 到 10 的整数。");
        return {user_id, camera_enabled:this.root.querySelector("[data-native-camera-enabled]").checked,
          proactive_mode:this.root.querySelector("[data-native-camera-mode]").value, proactive_max_daily};
      }
      if (action === "test_camera") {
        const user_id = this.root.querySelector("[data-native-camera-user]").value.trim();
        if (!user_id) throw new Error("先选择已有 V2 私聊的用户。");
        return {user_id, purpose:"拓展页摄像头单帧测试"};
      }
      return {};
    }
    onClick(event) {
      const button = event.target.closest?.("button");
      if (!button || !this.root.contains(button) || button.disabled) return;
      if (button.hasAttribute("data-native-management-refresh")) { this.read(); return; }
      if (button.hasAttribute("data-native-use-hotkey")) {
        const hotkey = this.record.management.hotkeys[Number(button.dataset.nativeUseHotkey)];
        this.options.onUseHotkey?.(hotkey); return;
      }
      const action = button.dataset.nativeAction;
      if (action) { try { this.run(action, this.payload(action, button)); } catch (error) { this.notice(error.message, true); } }
    }
    onChange(event) {
      if (event.target.hasAttribute?.("data-native-camera-user") || event.target.hasAttribute?.("data-native-audio-user")) {
        this.cameraUser = event.target.value.trim(); this.cameraDraft = null; this.audioDraft = null; this.cameraConsent = false;
        this.cameraTestResult = null; this.cameraPreview = null;
        if (event.target.hasAttribute("data-native-audio-user")) this.audioOpen = true; else this.cameraOpen = true;
        this.publishState(); this.render();
      } else {
        if (event.target.hasAttribute?.("data-native-camera-consent")) this.cameraConsent = event.target.checked;
        this.saveCameraDraft(); this.updateButtons();
      }
    }
  }
  return {mount:(root, options) => new Management(root, options)};
})();
