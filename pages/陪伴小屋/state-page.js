"use strict";
window.CompanionStatePage = (() => {
  const HOST = "astrbot_plugin_private_companion_v2";
  const PREFIX = "/" + HOST + "/";
  const phaseNames = {menstrual:"经期", follicular:"卵泡期", pre_ovulation:"排卵前", ovulation:"排卵期",
    luteal:"黄体期", pms:"经前期", recovery:"恢复期"};
  const errors = {
    dashboard_identity_required:"请从已登录的 AstrBot 管理界面打开陪伴小屋。",
    staging_not_initialized:"V2 数据尚未加载。请先在账号与会话中加载已初始化的配置，再刷新。",
    staging_host_terminated:"V2 宿主已停止，请重新打开拓展页。",
    core_access_required:"当前账号没有角色状态管理权限。",
    binding_revoked:"管理账号的授权已撤销。", binding_rebound:"管理账号的绑定已变化，请重新进入。",
    page_request_invalid:"目标目录请求无效，请重新打开页面。", bridge_unavailable:"页面还没有接上 AstrBot。若这是从管理界面打开的插件页，刷新一次通常就好；若反复出现，请确认插件已启用。",
    bridge_timeout:"未收到状态确认，请刷新核对。", invalid_response:"服务返回的数据不完整，请刷新核对。",
  };
  const presentationReasons = {
    presentation_disabled:"开关已关闭", presence_port_missing:"未安装 QQ 展示端口", host_not_running:"宿主尚未运行或已停止",
    authorization_denied:"当前窗口缺少展示授权", binding_revoked:"当前身份授权已撤销", binding_rebound:"当前身份绑定已变化",
    role_binding_changed:"当前角色绑定已变化，请重新打开页面",
    multiple_presence_owners:"同一 QQ 账号有多个展示窗口，请保留一个窗口启用自定义短状态",
    presence_plan_conflict:"当前有多个带公开文案的日程重叠，请核对日程",
    presence_calendar_partial:"当前日程未完整读取，暂不选择公开文案", presence_no_public_wording:"当前没有显式公开文案",
    presence_context_unbound:"等待宿主绑定当前会话", typing_batch_suppressed:"本轮确认失败或未知，已停止自动刷新",
    typing_turn_closed:"当前会话的回复已结束", presence_changed:"发送前公开文案已变化",
    presence_scope_mismatch:"原账号或收件人与请求不一致", presence_transport_unavailable:"原账号的 QQ 连接不可用",
    presence_authorization_changed:"发送前授权或平台环境未通过复核", presence_wording_invalid:"公开文案需为 1–8 个字",
    presence_action_rejected:"平台拒绝了展示请求", presence_ack_unknown:"平台未返回可确认的结果",
    presence_interrupted:"请求被中断，结果需要人工核对", typing_failed:"输入提示未获得可确认的结果",
  };
  const e = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const when = value => value && Number.isFinite(Date.parse(value))
    ? new Date(value).toLocaleString("zh-CN", {hour12:false}) : "未安排";
  const reason = code => errors[code] || (code ? "需要核对：" + code : "暂时无法读取角色状态。请刷新核对。");
  let root = null, bridge = null, version = 0, timer = null, data = null, editor = null, calendarEditor = null;
  let section = "state", activeFeature = null, extraConfig = null, extraConfigRoot = null, extraConfigFeature = null;

  function blank() { return {catalog:null,target:0,role:0,status:null,cursor:"",loading:false,error:false,notice:"",ready:false}; }
  function target() { return data?.catalog?.targets[data.target]; }
  function role() { return target()?.roles[data.role]; }
  function personaLabel() { return role()?.persona_ids?.join("、")||role()?.role_id||"当前人格"; }
  /* 同 memory-page.js：桥要插件相对路径，所以切掉插件目录名。 */
  function endpoint() {
    const path = role()?.state_api;
    if (typeof path !== "string" || !path.startsWith(PREFIX)) throw Object.assign(new Error("invalid_response"),{code:"invalid_response"});
    const relative = path.slice(PREFIX.length);
    if (!relative || relative.split("/").some(part => !part || part === "." || part === "..") || /[?#%\\:]/.test(relative)) {
      throw Object.assign(new Error("invalid_response"),{code:"invalid_response"});
    }
    return relative;
  }
  async function bounded(promise) {
    let timeout;
    try { return await Promise.race([promise,new Promise((_,reject)=>{timeout=setTimeout(()=>reject(Object.assign(new Error("bridge_timeout"),{code:"bridge_timeout"})),15000);})]); }
    finally { clearTimeout(timeout); }
  }
  /* 后端把机器码放在信封的 message 上（页面桥只转发 message），取码要同时看
     data.code 与 message，不能只认前者。 */
  const CODE = /^[a-z][a-z0-9_]{2,60}$/;
  const codeOf = wrapped => wrapped?.data?.code
    || (CODE.test(wrapped?.message || "") ? wrapped.message : "") || "";
  async function api(method,path,body) {
    const response = await bounded(method === "GET" ? bridge.apiGet(path,body) : bridge.apiPost(path,body));
    const wrapped = ["ok","error"].includes(response?.status) ? response : ["ok","error"].includes(response?.data?.status) ? response.data : null;
    if (wrapped?.status === "error") {const code=codeOf(wrapped)||"invalid_response";throw Object.assign(new Error(code),{code,confirmed:true});}
    const value = wrapped ? wrapped.data : response;
    if (!value || typeof value !== "object" || Array.isArray(value)) throw Object.assign(new Error("invalid_response"),{code:"invalid_response"});
    return value;
  }
  function live(ticket) { return ticket === version && root?.isConnected; }
  function stopTimer() { clearTimeout(timer); timer = null; }
  function notice(message,error=false) { data.notice=message; data.error=error; }
  function statusLabel(status) {
    return ({active:"运行中",disabled:"状态维护未启用",unknown:"尚无状态记录",unavailable:"当前状态不可用"})[status] || "角色状态";
  }
  function valueLabel(value,enabled=true) { return !enabled ? "未启用" : value == null || value === "" ? "尚未记录" : String(value); }
  function phaseLabel(status) {
    const settings=status.settings||{}, state=status.state||{}, timeline=state.cycle_timeline;
    if (!settings.cycle_enabled) return "未启用";
    if (!timeline) return state.state === "unavailable" ? "暂不可读取" : "尚无阶段记录";
    if (timeline.applicability === "not_applicable") return "不适用";
    if (timeline.applicability !== "applicable") return "尚未定位";
    const phase=phaseNames[timeline.phase]||"周期阶段";
    return Number.isInteger(timeline.phase_day)&&Number.isInteger(timeline.phase_days)
      ? `${phase} · 第 ${timeline.phase_day} / ${timeline.phase_days} 天` : phase;
  }
  function metric(name,value,detail="") {
    return `<article class="state-metric"><span>${name}</span><strong>${e(value)}</strong>${detail?`<small>${e(detail)}</small>`:""}</article>`;
  }
  function stateGauge(name,value,detail="",tone="accent") {
    const known=!(value==null||value===""),numeric=typeof value==="number"&&Number.isFinite(value);
    const label=!known?"尚未记录":numeric?`${value} / 100`:String(value);
    const meter=numeric?`<div class="state-gauge-track" aria-hidden="true"><i style="width:${Math.max(0,Math.min(100,value))}%"></i></div>`
      :known?"":'<div class="state-gauge-track is-unmeasured" aria-hidden="true"></div>';
    return `<article class="state-gauge ${tone}${!known?" is-unknown":known&&!numeric?" is-qualitative":""}"><div class="state-gauge-head"><span>${name}</span><strong>${e(label)}</strong></div>${meter}<small>${e(detail||"暂无可用记录")}</small></article>`;
  }
  const moodAxes = {joy:"喜", anger:"怒", sorrow:"哀", fear:"惧"};
  const moodOrder = ["joy", "anger", "sorrow", "fear"];
  function moodText(mood) {
    return typeof mood === "string" ? mood : mood?.description || "";
  }
  function moodNumbers(mood) {
    return moodOrder.map(key=>`${moodAxes[key]} ${mood[key]}`).join(" · ");
  }
  function moodDetail(status) {
    const mood=status.state?.values?.mood, dynamics=status.state?.mood_dynamics;
    if (!moodEnabled(status) || !mood || typeof mood !== "object") return "";
    const reference=dynamics?.reference;
    const fallback=reference?`无新互动时的回落参考：${moodOrder.map(key=>`${moodAxes[key]} ${reference[key]}`).join(" · ")}`:"";
    const marks=[moodNumbers(mood),`基线 ${mood.baseline}`,mood.intensity||null,dynamics?.neutral?"处于中性带":null,
      dynamics?.cross_window?"跨窗口共享本体":null].filter(Boolean).join(" · ");
    return [marks,fallback].filter(Boolean).join("；");
  }
  function moodEnabled(status) { return !!status?.settings?.mood_enabled; }
  function sleepMarkup(status) {
    const plan=status.sleep_schedule||{}, execution=status.body_sleep;
    const planned=plan.enabled ? `${e(plan.time||"未设定")} · ${e(plan.timezone||"")} · ${e(plan.duration_minutes)} 分钟` : "自动睡眠日程未启用";
    const executor=!plan.enabled ? "未安排" : plan.executor_state === "available"
      ? `${e(plan.executor_window?.label||"已选定执行窗口")}${plan.executor_is_current?"（当前窗口）":""}`
      : "暂无有效授权窗口";
    const actual=execution?.state === "sleeping" ? `睡眠中 · 计划醒来 ${when(execution.planned_wake_at)}`
      : execution?.state === "awake" ? `最近一次睡眠已结束 · ${when(execution.ended_at)}`
        : execution?.state === "interrupted" ? "最近一次睡眠已中断" : "当前没有进行中的睡眠";
    return `<section id="state-sleep-schedule" class="state-sleep-summary"><header><h4>睡眠作息</h4></header>
      <dl><div><dt>日程</dt><dd>${planned}</dd></div><div><dt>执行窗口</dt><dd>${executor}</dd></div>
      <div><dt>下次入睡 / 计划醒来</dt><dd>${plan.next_sleep_at?`${when(plan.next_sleep_at)} / ${when(plan.next_wake_at)}`:"未安排"}</dd></div>
      <div><dt>当前执行</dt><dd>${actual}</dd></div></dl></section>`;
  }
  function presentationMarkup(status) {
    const receipts=status.presentation||{};
    const diagnostics=status.presentation_diagnostics, settings=status.settings||{}, effective=status.effective||{};
    const explain=code=>presentationReasons[code]||reason(code);
    const configured=option=>!settings[option]?"开关已关闭":effective[option]?.allowed
      ?"已开启 · 授权通过":effective[option]?.reason?`已开启 · ${explain(effective[option].reason)}`:"已开启 · 授权待核对";
    const activity=(value,typing=false)=>{
      if(!value)return "尚无运行诊断";
      const labels=typing?{idle:"当前会话没有进行中的回复",waiting:"等待刷新任务",refreshing:"刷新任务运行中",suppressed:"本轮已停止刷新"}
        :{idle:"暂无待展示文案",waiting:"等待宿主处理当前文案",recorded:"相同文案已有请求记录，不自动重发",deduplicated:"账号已有相同文案记录，不重复请求"};
      return [labels[value.state]||({disabled:"未启用",unavailable:"展示端口不可用",blocked:"当前条件未满足",paused:"展示已暂停"})[value.state]||"状态待核对",
        value.reason?explain(value.reason):null].filter(Boolean).join(" · ");
    };
    const typing=diagnostics?.typing, custom=diagnostics?.custom_status;
    const basis=value=>({calendar_plan:"当前日程的公开文案",role_simulation:"角色模拟的公开文案"})[value]||"公开文案";
    const configuration=`<dl class="state-presentation-settings"><div><dt>正在输入 · ${e(configured("typing_enabled"))}</dt>
      <dd>${e(activity(typing,true))}</dd><dd class="state-presentation-note">配置刷新间隔：${e(typing?.refresh_seconds??settings.typing_refresh_seconds??"未提供")} 秒</dd></div>
      <div><dt>自定义短状态 · ${e(configured("presence_enabled"))}</dt><dd>${e(activity(custom))}</dd>
      ${custom?.desired?`<dd class="state-presentation-note">待展示：${e(custom.desired.wording)} · ${e(basis(custom.desired.basis))}</dd>`:""}</div></dl>`;
    const items=Object.entries(receipts).filter(([,result])=>result&&typeof result==="object");
    const label=(key,result)=>result.state==="unknown"?(key.startsWith("typing:")?"确认未知，本轮不再重试":"确认未知，相同文案不自动重发")
      :({accepted:"平台已受理",failed:"平台拒绝",not_started:"未发送（授权或环境未满足）",blocked:"展示被阻止，未发送"})[result.state]||"状态未识别";
    return `<section class="state-presentation"><header><h4>QQ 平台展示确认</h4>
      <p>受理确认不代表客户端当前展示状态。${diagnostics?.observed_at?`诊断时间：${when(diagnostics.observed_at)}`:""}</p></header>
      ${configuration}${receipts.state==="preview"?"<p>当前为预览宿主，未安装 QQ 展示端口。</p>":items.length?`<ul class="state-receipts">${items.map(([key,result],index)=>`<li>
        <strong>${key.startsWith("typing:")?"正在输入":"自定义短状态"}</strong><div><span>${e(label(key,result))}</span>
        <small class="state-receipt-detail">${result.recorded_at?`记录于 ${when(result.recorded_at)}`:"旧确认未记录时间"}${key.startsWith("typing:")?" · 仅保留本次宿主运行记录":""}</small>
        ${result.code?`<small class="state-receipt-detail">${e(explain(result.code))}</small>`:""}
        ${result.desired?`<small class="state-receipt-detail">请求文案：${e(result.desired.wording)} · ${e(basis(result.desired.basis))}</small>`:""}
        ${result.operation_state==="started"?"<small class=\"state-receipt-detail\">仅记录了请求开始，尚无完成确认；时间为开始记录时间。</small>":""}
        ${result.operation_id||result.batch_id?`<details class="state-receipt-reference" data-receipt="${e(result.operation_id||result.batch_id)}"><summary id="state-receipt-summary-${index}">查看请求标识</summary>${result.operation_id?`<p>请求：${e(result.operation_id)}</p>`:""}${result.batch_id?`<p>回复批次：${e(result.batch_id)}</p>`:""}</details>`:""}</div></li>`).join("")}</ul>`:"<p>尚无 QQ 展示确认。</p>"}</section>`;
  }
  const featureInfo={energy:["能量","battery-medium"],health:["健康","heart-pulse"],hunger:["饥饿","utensils"],
    sleep:["睡眠","moon-star"],cycle:["生理期","calendar-heart"],busy:["忙碌","briefcase-business"],
    location:["位置","map-pin"],mood:["心情","smile"],planning:["日程与规划","calendar-days"],
    patrol:["每日巡视","scan-heart"],presentation:["QQ 展示","radio-tower"]};
  function dashboardItem(feature,label,value,icon,detail="",tone="") {
    const energy=feature==="energy"&&typeof value==="number";
    return `<button type="button" id="state-status-${feature}" class="state-board-point ${tone}" data-state-feature="${feature}"
      aria-expanded="${activeFeature===feature}" aria-controls="state-feature-detail" title="${e([label,value,detail].filter(Boolean).join(" · "))}">
      <i data-lucide="${icon}" aria-hidden="true"></i><span>${label}</span><strong>${e(energy?`${value} / 100`:value)}</strong>
      ${energy?`<meter min="0" max="100" value="${Math.max(0,Math.min(100,value))}" aria-label="能量 ${value} / 100"></meter>`:""}</button>`;
  }
  function dashboardMarkup(status) {
    const values=status.state?.values||{},settings=status.settings||{};
    const energy=typeof values.energy==="number"&&Number.isFinite(values.energy)?values.energy:valueLabel(values.energy);
    const sleep=status.body_sleep?.state==="sleeping"?"睡眠中":valueLabel(values.sleep);
    const health=!settings.enabled?"维护已关闭":settings.health_enabled===false?"已关闭":valueLabel(values.health);
    const hunger=!settings.enabled?"维护已关闭":settings.hunger_enabled===false?"已关闭":valueLabel(values.hunger);
    return `<section class="state-dashboard" aria-labelledby="state-dashboard-title">
      <header><div><span class="state-eyebrow">${e(personaLabel())}</span><h2 id="state-dashboard-title">状态看板</h2></div>
        <span class="state-dashboard-updated">${e(status.state?.updated_at?`更新于 ${when(status.state.updated_at)}`:statusLabel(status.state?.state))}</span></header>
      <div class="state-dashboard-grid">
        ${dashboardItem("energy","能量",energy,"battery-medium",`表达强度 ${settings.humanized_state_intensity??50} / 100`,"tone-energy")}
        ${dashboardItem("health","健康",health,"heart-pulse","人格共享模拟","tone-health")}
        ${dashboardItem("hunger","饥饿",hunger,"utensils","人格共享模拟","tone-hunger")}
        ${dashboardItem("sleep","睡眠",sleep,"moon-star",status.sleep_schedule?.enabled?`${status.sleep_schedule.time||""} · ${status.sleep_schedule.duration_minutes||""} 分钟`:"睡眠感受与作息计划","tone-sleep")}
        ${dashboardItem("cycle","生理期",phaseLabel(status),"calendar-heart",settings.cycle_enabled?"人格共享模拟":"周期模拟未开启","tone-cycle")}
        ${dashboardItem("busy","忙碌",valueLabel(values.busy),"briefcase-business","日程状态与忙碌处理","tone-busy")}
        ${dashboardItem("location","位置",valueLabel(values.location),"map-pin","对话中记录的人格位置","tone-location")}
      </div>
      <footer><span class="state-dashboard-status"><i aria-hidden="true"></i>${e(statusLabel(status.state?.state))}</span>
        <span>${status.maintenance?.next_at?`下次更新 ${e(when(status.maintenance.next_at))}`:""}</span></footer>
    </section>`;
  }
  function extraButtons() {
    return `<nav class="state-extra-nav" aria-label="其他状态设置"><span>更多设置</span>${["mood","planning","patrol","presentation"].map(feature=>
      `<button type="button" id="state-extra-${feature}" data-state-feature="${feature}" aria-expanded="${activeFeature===feature}" aria-controls="state-feature-detail"><i data-lucide="${featureInfo[feature][1]}" aria-hidden="true"></i><span>${featureInfo[feature][0]}</span></button>`).join("")}</nav>`;
  }
  function featurePanelMarkup(status) {
    if(!activeFeature||!featureInfo[activeFeature])return "";
    const [title,icon]=featureInfo[activeFeature],values=status.state?.values||{};
    let body="";
    if(activeFeature==="sleep")body=`${sleepMarkup(status)}<div id="state-extra-config" class="state-extra-config" data-state-external="sleep"></div>`;
    else if(activeFeature==="busy")body=`<div class="state-feature-current"><span>当前状态</span><strong>${e(valueLabel(values.busy))}</strong><small>状态由日程形成；下方可调整回复顺延。</small></div><div id="state-extra-config" class="state-extra-config" data-state-external="busy"></div>`;
    else if(activeFeature==="location")body=`<div class="state-feature-current"><span>人格位置 · ${e(personaLabel())}</span><strong>${e(valueLabel(values.location))}</strong><small>这是角色自身的位置模拟，随人格在窗口间共享；不记录聊天对象的私人位置。</small></div>`;
    else if(activeFeature==="planning")body=editor?.markup({configPanel:"planning"})||"";
    else if(activeFeature==="presentation")body=`${presentationMarkup(status)}${editor?.markup({feature:"presentation"})||""}`;
    else body=editor?.markup({feature:activeFeature})||"";
    return `<section id="state-feature-detail" class="state-feature-detail" aria-labelledby="state-feature-title">
      <header><div><span class="state-eyebrow">STATE SETTINGS</span><h3 id="state-feature-title"><i data-lucide="${icon}" aria-hidden="true"></i>${title}</h3></div>
        <button type="button" class="state-feature-close" data-state-feature-close aria-label="收起${title}" title="收起"><i data-lucide="x" aria-hidden="true"></i></button></header>
      <div class="state-feature-content">${body}</div>
    </section>`;
  }
  function mountExtraConfig() {
    const feature=activeFeature==="sleep"?"sleep":activeFeature==="busy"?"busy":null;
    const host=feature?root?.querySelector("#state-extra-config"):null;
    if(!host){extraConfig?.stop?.();extraConfig=null;extraConfigRoot=null;extraConfigFeature=null;return;}
    if(extraConfig&&extraConfigRoot===host&&extraConfigFeature===feature)return;
    extraConfig?.stop?.();extraConfig=null;extraConfigRoot=null;extraConfigFeature=null;
    const views=feature==="sleep"?{life:{sectionIds:["sleep","rest","backlog"],title:"睡眠与休息"}}:{};
    const kinds=feature==="sleep"?["life"]:["busy_gate"];
    extraConfig=window.CompanionConfigEditors?.create(kinds,()=>host,views)||null;
    if(extraConfig){extraConfig.restore();extraConfig.paint();extraConfig.read();extraConfigRoot=host;extraConfigFeature=feature;}
    else host.innerHTML=`<p class="state-edit-help">当前工作台尚未就绪，请刷新状态页后重试。</p>`;
  }
  function render() {
    if (!root?.isConnected || !data) return;
    const status=data.status,roleTarget=target(),contactView=section==="contact";
    if(role()?.state_api&&data.catalog)editor?.setScope({installation_id:data.catalog.installation_id,operator_id:data.catalog.operator_id,path:endpoint()});
    else editor?.invalidate();
    editor?.setStatus(status,data.loading);
    if(!contactView&&editor?.requiredFeature)activeFeature=editor.requiredFeature;
    const focused=root.contains(document.activeElement)?document.activeElement.id:null;
    const expanded=new Set([...root.querySelectorAll(".state-receipt-reference[open]")].map(item=>item.dataset.receipt));
    const available=!!role()?.state_api;
    let content;
    if (!data.ready) content=`<div class="panel state-empty">${data.loading?"正在读取授权目标…":"刷新目标后即可查看角色状态。"}</div>`;
    else if (!available) content=contactView?`<div class="panel state-empty"><h3>请选择已授权的私聊对象</h3></div>`
      :`<div class="panel state-empty"><h3>请选择已授权的私聊对象</h3></div>`;
    else if (!status) content=`<div class="panel state-empty">${data.loading?"正在读取状态…":"尚未读取状态。"}</div>`;
    else if(contactView)content=editor?.markup({section:"contact"})||"";
    else {
      const settings=status.settings||{};
      const locked=!!editor?.interacting;
      const values=status.state?.values||{};
      const temporary=Array.isArray(values.conditions)&&values.conditions.length
        ?`<section class="state-conditions-inline"><h3>当前临时状态</h3><ul>${values.conditions.map(item=>`<li><strong>${e(item.kind)}</strong><span>${e(item.text)}</span><small>${item.expires_at?`记录至 ${when(item.expires_at)}`:"未设结束时间"}</small></li>`).join("")}</ul></section>`:"";
      const homeControls=editor?.markup({feature:"home"})||"";
      content=`${dashboardMarkup(status)}
        <section class="state-settings-zone" aria-label="状态功能与首页展示">
          <header><div><span class="state-eyebrow">人格共享</span><h3>状态功能与首页展示</h3></div>
            <span class="state-settings-scope ${settings.enabled?"is-enabled":""}">${e(settings.enabled?"运行中":"已关闭")}</span></header>
          ${homeControls}
        </section>
        ${activeFeature?featurePanelMarkup(status):""}
        ${extraButtons()}${temporary}`;
    }
    const selectedScope=window.CompanionProduct?.selection?.();
    const accessScope=roleTarget?`${roleTarget.scope_kind==="group"?"群聊":"私聊"} ${roleTarget.participant_id||roleTarget.group_id||roleTarget.target_id}`:"尚未选择真实会话";
    const scopeMarkup=contactView?`<div class="panel memory-scope state-scope"><div class="state-scope-current"><span>当前会话</span><strong>${e(accessScope)}</strong><small>联系安排适用于当前会话。</small></div>${!selectedScope?`<button type="button" class="button small" data-go="manage" data-manage="host">去账号与会话选择</button>`:""}</div>`
      :`<div class="panel memory-scope state-scope"><div class="state-scope-current"><span>人格状态归属</span><strong>${e(personaLabel())}</strong><small>角色模拟状态整体归属人格；${e(accessScope)}仅用于权限核验。日历安排与 QQ 平台展示按当前窗口处理。</small></div></div>`;
    root.innerHTML=`<div class="state-page-heading"><div><span class="state-badge">${contactView?"联系安排":"角色状态"}</span></div><button type="button" class="memory-button" id="state-refresh" ${data.loading||editor?.busy||isExternalFeatureOpen()?"disabled":""} ${isExternalFeatureOpen()?`title="先收起睡眠或忙碌配置，再刷新状态"`:""}>${contactView?"刷新联系设置":"刷新状态"}</button></div>
      ${scopeMarkup}<div class="memory-notice ${data.error?"error":""}" id="state-notice" role="status" aria-live="polite" ${data.notice?"":"hidden"}>${e(data.notice)}</div>${content}`;
    root.querySelectorAll(".state-receipt-reference").forEach(item=>{item.open=expanded.has(item.dataset.receipt);});
    if(focused)root.querySelector("#"+focused)?.focus({preventScroll:true});
    mountExtraConfig();
    window.lucide?.createIcons({attrs:{"aria-hidden":"true"}});
  }
  function schedule() {
    stopTimer();
    if(data?.ready&&role()?.state_api&&!document.hidden&&!editor?.interacting&&!isExternalFeatureOpen())timer=setTimeout(()=>{if(!data.loading)load();else schedule();},15000);
  }
  function isExternalFeatureOpen() { return activeFeature==="sleep"||activeFeature==="busy"; }
  function failure(error) {
    data.status=null; data.error=true; data.notice=reason(error?.code);
    if(["dashboard_identity_required","core_access_required","authorization_denied","role_binding_changed","binding_revoked","binding_rebound","staging_host_terminated"].includes(error?.code)) {
      data.catalog=null; data.ready=false; editor?.invalidate(); stopTimer();
    }
  }
  async function directory() {
    const ticket=++version; stopTimer(); data=blank(); data.loading=true; render();
    try {
      const catalog=await api("GET","page/targets");
      if(!live(ticket))return;
      if(!Array.isArray(catalog.targets)||!catalog.installation_id||catalog.targets.some(item=>!Array.isArray(item.roles))) throw Object.assign(new Error("invalid_response"),{code:"invalid_response"});
      data.catalog=catalog;data.ready=true;data.loading=false;
      const selected=window.CompanionProduct?.selection();
      const targetIndex=catalog.targets.findIndex(item=>item.target_id===selected?.target_id);
      const roleIndex=targetIndex>=0?catalog.targets[targetIndex].roles.findIndex(item=>item.role_id===selected?.role_id):-1;
      if(targetIndex>=0&&roleIndex>=0){data.target=targetIndex;data.role=roleIndex;}
      if(targetIndex>=0&&roleIndex>=0&&role()?.state_api){endpoint();await load();}else {data.notice="请先在账号与会话选择一个真实对象和角色。";render();}
    } catch(error) { if(live(ticket)){failure(error);data.loading=false;render();} }
  }
  async function load(cursor=data?.cursor||"") {
    if(!root||!data.ready||!role()?.state_api||data.loading)return;
    const ticket=++version;stopTimer();data.cursor=cursor;data.loading=true;render();
    try {
      const result=await api("GET",endpoint(),{after_id:data.cursor});
      if(!live(ticket))return;
      if(!result.state||!result.settings||!result.sleep_schedule)throw Object.assign(new Error("invalid_response"),{code:"invalid_response"});
      data.status=result;notice("");
      return result;
    } catch(error) { if(live(ticket))failure(error);return null; }
    finally { if(live(ticket)){data.loading=false;render();schedule();} }
  }
  function changeScope(targetIndex,roleIndex) {
    if(!data.catalog?.targets[targetIndex]?.roles[roleIndex])return;
    ++version;stopTimer();const catalog=data.catalog;
    data={...blank(),catalog,target:targetIndex,role:roleIndex,ready:true};
    window.CompanionProduct?.choose(catalog.targets[targetIndex].target_id,catalog.targets[targetIndex].roles[roleIndex].role_id,true);
    if(role()?.state_api){try{endpoint();load();}catch(error){failure(error);render();}}else render();
  }
  function click(event) {
    const close=event.target.closest("[data-state-feature-close]");
    if(close) {
      const feature=activeFeature;activeFeature=null;render();schedule();
      root?.querySelector(`#state-status-${feature}, #state-extra-${feature}`)?.focus({preventScroll:true});
      return;
    }
    const featureButton=event.target.closest("[data-state-feature]");
    if(featureButton) {
      if(editor?.interacting)return;
      const feature=featureButton.dataset.stateFeature;
      activeFeature=activeFeature===feature?null:feature;
      render();schedule();
      if(activeFeature)root?.querySelector("#state-feature-detail")?.scrollIntoView({
        behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth",block:"nearest"});
      return;
    }
    const cycleViewTab=event.target.closest("[data-cycle-view]");
    if(cycleViewTab) {
      const id=cycleViewTab.id;
      window.CompanionStateMaintenance?.selectCycleView(cycleViewTab.dataset.cycleView);
      render();root?.querySelector("#"+id)?.focus({preventScroll:true});
      return;
    }
    const phaseTab=event.target.closest("[data-state-phase]");
    if(phaseTab) {
      const id=phaseTab.id;
      window.CompanionStateMaintenance?.selectPhase(phaseTab.dataset.statePhase);
      render();root?.querySelector("#"+id)?.focus({preventScroll:true});
      return;
    }
    if(calendarEditor?.click(event))return;
    if(editor?.click(event))return;
    if(event.target.closest("#state-refresh")&&!editor?.busy&&!isExternalFeatureOpen()){if(data.ready)load();else directory();}
    const page=event.target.closest("[data-state-page]");
    if(page&&!page.disabled&&!editor?.interacting)load(page.dataset.statePage);
  }
  function keydown(event) {
    const cycleViewTab=event.target.closest("[data-cycle-view]");
    if(cycleViewTab) {
      const views=["plan","expression"],index=views.indexOf(cycleViewTab.dataset.cycleView);
      const next=event.key==="ArrowRight"?(index+1)%views.length:event.key==="ArrowLeft"?(index+views.length-1)%views.length
        :event.key==="Home"?0:event.key==="End"?views.length-1:-1;
      if(next<0)return;
      event.preventDefault();window.CompanionStateMaintenance.selectCycleView(views[next]);render();
      root?.querySelector(`#state-cycle-view-${views[next]}`)?.focus({preventScroll:true});
      return;
    }
    const phaseTab=event.target.closest("[data-state-phase]");
    if(phaseTab) {
      const phases=Object.keys(window.CompanionStateMaintenance?.phases||{}),index=phases.indexOf(phaseTab.dataset.statePhase);
      const next=event.key==="ArrowRight"?(index+1)%phases.length:event.key==="ArrowLeft"?(index+phases.length-1)%phases.length
        :event.key==="Home"?0:event.key==="End"?phases.length-1:-1;
      if(next<0||!phases.length)return;
      event.preventDefault();window.CompanionStateMaintenance.selectPhase(phases[next]);render();
      root?.querySelector(`#state-cycle-phase-${phases[next]}`)?.focus({preventScroll:true});
      return;
    }
  }
  function input(event) {calendarEditor?.input(event);editor?.input(event);
    if(event.target.matches('[data-state-field^="cycle_"][data-state-field$="_days"]'))window.CompanionStateMaintenance?.syncDurationPreview(root);}
  function submit(event) {if(calendarEditor?.submit(event))return;editor?.submit(event);}
  function change(event) {
    calendarEditor?.change(event);editor?.input(event);
    if(event.target.matches('[data-state-field^="cycle_"][data-state-field$="_days"]'))window.CompanionStateMaintenance?.syncDurationPreview(root);
  }
  function setChrome(active) {
    document.body.classList.toggle("state-connected",active);
    /* 外壳徽标在场时由 product.updateHostChrome() 统一渲染，这里不抢。
       只有在单独嵌入（没有外壳徽标）时才自己补一条状态——而且不能写
       「设计预览」，那正是「连不上」的观感来源。 */
    if(window.CompanionProduct?.hosted()&&document.querySelector("[data-host-badge]"))return;
    const badge=document.querySelector(".preview-badge");
    if(badge)badge.innerHTML=active?"<span></span>角色状态读取正常 <b>V2</b>":"<span></span>角色状态读取待检查 <b>V2</b>";
    if(active)document.title="角色状态维护 · 陪伴 V2";
  }
  async function mount(element,options={}) {
    unmount();section=options.section==="contact"?"contact":"state";activeFeature=null;root=element;data=blank();root.addEventListener("click",click);root.addEventListener("keydown",keydown);root.addEventListener("change",change);
    root.addEventListener("input",input);root.addEventListener("submit",submit);
    calendarEditor=section==="contact"?null:window.CompanionCalendarEditor?.create({api,changed:()=>{render();schedule();},refresh:()=>load(),
      failed:error=>{failure(error);render();}});
    editor=window.CompanionStateEditor?.create({api,calendarEditor,changed:()=>{render();schedule();},refresh:()=>load(),
      failed:error=>{failure(error);render();}});
    const ticket=version;
    try {
      /* 等宿主把桥注进来，而不是「现在没有就当作没有」。
         桥的注入晚于页面脚本执行是正常时序：早前这里一看 bridge 为空就直接
         渲染「设计预览」，于是真实宿主里也会看到「请从管理界面打开」——
         用户以为是自己打开方式不对，其实是时序问题。
         等不到（超时）才算真的没接上，那时报 bridge_unavailable 并给重试。 */
      bridge=window.CompanionProduct?.bridgeNow?.()||await window.CompanionProduct?.bridgeFor?.();
      if(!live(ticket))return;
      if(!bridge?.ready)throw Object.assign(new Error("bridge_unavailable"),{code:"bridge_unavailable"});
      const context=await bounded(bridge.ready());if(!live(ticket))return;
      /* 桥在、但不是这一支插件的桥：这确实是环境问题，如实报错。 */
      if(context?.pluginName!==HOST)throw Object.assign(new Error("bridge_unavailable"),{code:"bridge_unavailable"});
      setChrome(true);await directory();
    } catch(error) { if(live(ticket)){failure(error);data.loading=false;render();} }
  }
  function unmount() { ++version;stopTimer();extraConfig?.stop?.();extraConfig=null;extraConfigRoot=null;extraConfigFeature=null;editor?.destroy();editor=null;calendarEditor=null;root?.removeEventListener("click",click);root?.removeEventListener("keydown",keydown);root?.removeEventListener("change",change);root?.removeEventListener("input",input);root?.removeEventListener("submit",submit);root=null;data=null;bridge=null;activeFeature=null;setChrome(false); }
  document.addEventListener("visibilitychange",()=>{if(!data?.ready)return;if(document.hidden)stopTimer();else if(!data.loading&&!editor?.interacting&&!isExternalFeatureOpen())load();});
  return {mount,unmount};
})();
