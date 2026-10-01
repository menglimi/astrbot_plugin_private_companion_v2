"use strict";
window.CompanionStateEditor = (() => {
  const fields=["typing_enabled","typing_refresh_seconds","presence_enabled"];
  const maintenance=window.CompanionStateMaintenance;
  const contact=window.CompanionStateContact;
  const configKinds=new Set(["settings","home","intensity","maintenance","calendar","cycle","planning","mood","patrol"]);
  const configFields=kind=>kind==="settings"?fields:maintenance?.fields(kind)||[];
  const categoryFor=command=>command?.action==="contact.configure"?"contact":command?.action==="calendar.presence"?"planning"
    :command?.action==="configure"&&Object.keys(command.changes).some(key=>maintenance?.fields("planning").includes(key))?"planning"
      :command?.action==="cycle.align"||command?.action==="configure"&&Object.keys(command.changes).some(key=>!fields.includes(key))?"maintenance":"presentation";
  const cache=new Map();
  const e=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const messages={configuration_revision_conflict:"配置已被更新，填写内容已保留。请读取当前版本后核对。",
    record_revision_conflict:"日程已被更新，填写内容已保留。请读取当前版本后核对。",
    role_cycle_settings_conflict:"周期配置已变化，填写内容已保留。请读取当前参数后核对校准。",
    role_cycle_alignment:"请按当前周期长度填写校准方式和周期日。",cycle_configuration_invalid:"请核对周期模式、时区和表达偏好。",
    state_configuration_invalid:"请核对各项设置的类型与范围。",planning_timezone_invalid:"请填写有效的 IANA 规划时区，例如 Asia/Shanghai。",
    state_mood_settings:"请核对心情动力学：概率需在 0 到 1 之间，单轮幅度 1–4，半衰期 5–1440 分钟。",
    role_state_humanized:"请核对每日巡视：保留天数需在 3–180 之间，巡视时刻形如 04:00（24 小时制，不带秒与时区）。",
    planning_weather_max_age_invalid:"天气信息最长沿用时间需在 5–120 分钟之间。",
    state_target_changed:"当前对象或角色绑定已变化，请重新读取。",
    cycle_configuration_invalid:"请核对周期模式、时区、阶段时长与各阶段的精力偏移和表达引导。",
    planning_prompt_invalid:"规划偏好最多 4096 个字，请核对后保存。",
    invalid_contact_preference:"请核对免打扰时段、时区、暂停时间和联系偏好。",
    contact_configuration_invalid:"请核对当前对象的联系设置，刷新后再保存。",
    invalid_configuration_value:"请核对设置的类型与范围。",invalid_weight:"联系权重必须大于 0。",invalid_precision:"联系权重最多保留 6 位小数。",
    contact_relationship_budget_scope:"关系共享额度需在关系或角色层统一修改，当前会话只能查看。",
    state_view_stale:"角色或权限已变化，请读取当前版本后核对。",calendar_closed:"日程已取消或不存在。",
    calendar_presence_target_invalid:"只有角色计划可以设置公开短状态。",calendar_presence_invalid:"请只填写日程公开文案。",
    calendar_text_invalid:"公开文案最多 8 个字，可留空。",core_access_required:"当前账号没有修改权限。",
    authorization_denied:"当前授权不足，请刷新核对。",dashboard_identity_required:"请重新登录 AstrBot 管理界面。",
    binding_revoked:"当前身份授权已撤销，请重新进入。",binding_rebound:"身份绑定已变化，请重新进入。",
    role_binding_changed:"角色绑定已变化，请重新进入。",staging_host_terminated:"宿主已停止，请重新打开页面。"};
  const staleCodes=new Set(["configuration_revision_conflict","record_revision_conflict","state_view_stale","role_cycle_settings_conflict"]);
  const deniedCodes=new Set(["core_access_required","authorization_denied","dashboard_identity_required","binding_revoked","binding_rebound","role_binding_changed","staging_host_terminated"]);
  const sameKeys=(value,keys)=>value&&typeof value==="object"&&!Array.isArray(value)&&Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
  function valid(command) {
    if(!command||typeof command.operation_key!=="string"||!command.operation_key||command.operation_key.length>128)return false;
    if(command.action==="contact.configure")return sameKeys(command,["action","operation_key","edit_token","changes"])
      &&typeof command.edit_token==="string"&&command.changes&&Object.keys(command.changes).length>0
      &&Object.entries(command.changes).every(([key,value])=>contact?.validField(key,value));
    if(command.action==="configure")return sameKeys(command,["action","operation_key","edit_token","changes"])
      &&typeof command.edit_token==="string"&&command.changes&&Object.keys(command.changes).length>0
      &&Object.entries(command.changes).every(([key,value])=>fields.includes(key)?(key==="typing_refresh_seconds"
        ?Number.isInteger(value)&&value>=1&&value<=10:typeof value==="boolean"):maintenance?.validField(key,value));
    if(command.action==="cycle.align")return sameKeys(command,["action","operation_key","expected_revision","view_token","settings_token","data"])
      &&Number.isInteger(command.expected_revision)&&command.expected_revision>=0&&typeof command.view_token==="string"&&typeof command.settings_token==="string"
      &&sameKeys(command.data,["applicability","day"])&&["applicable","not_applicable","unknown","auto"].includes(command.data.applicability)
      &&(command.data.applicability==="applicable"?Number.isInteger(command.data.day)&&command.data.day>=1&&command.data.day<=180:command.data.day===null);
    return command.action==="calendar.presence"&&sameKeys(command,["action","operation_key","id","expected_revision","view_token","data"])
      &&typeof command.id==="string"&&!!command.id&&Number.isInteger(command.expected_revision)&&command.expected_revision>0
      &&typeof command.view_token==="string"&&sameKeys(command.data,["presence"])&&typeof command.data.presence==="string"
      &&[...command.data.presence].length<=8;
  }
  function stored(key) {
    if(cache.has(key))return cache.get(key);
    try {const value=JSON.parse(sessionStorage.getItem(key));if(valid(value)){cache.set(key,value);return value;}}catch{}
    return null;
  }
  function remember(key,value) {
    if(value)cache.set(key,value);else cache.delete(key);
    try {if(value)sessionStorage.setItem(key,JSON.stringify(value));else sessionStorage.removeItem(key);}catch{}
  }
  function forget(key,operation) {if(stored(key)?.operation_key===operation)remember(key,null);}
  function create({api,changed,refresh,failed,calendarEditor}) {
    let scope=null,status=null,draft=null,pending=null,busy=false,loading=false,alive=true,message="",error=false,category="presentation";
    const current=()=>status?.calendar?.items?.find(item=>item.id===draft?.base?.id);
    const usable=item=>item?.kind==="role_plan"&&item.state!=="cancelled"&&typeof item.view_token==="string";
    const say=(text,bad=false)=>{message=text;error=bad;};
    const emit=()=>{if(alive)changed();};
    function setScope(value) {
      const key=JSON.stringify([value.installation_id,value.operator_id,value.path]);
      if(scope?.key===key)return;
      scope={...value,key,storage:"companion-state-edit.v1:"+key};
      status=draft=null;pending=stored(scope.storage);busy=false;message="";error=false;
      category=categoryFor(pending);
      calendarEditor?.setScope(value);
    }
    function setStatus(value,isLoading=false) {status=value;loading=isLoading;calendarEditor?.setStatus(value,isLoading);}
    function invalidate() {scope=status=draft=pending=null;busy=false;message="";error=false;calendarEditor?.invalidate();}
  function open(kind,index) {
      if(busy||loading||pending||!status)return;
      if(kind==="cycle")maintenance?.resetPhase();
      if(kind==="contact") {
        if(!contact?.supported(status.contact))return;
        const base=Object.fromEntries(contact.fields(status.contact).map(key=>[key,status.contact.settings[key]]));
        draft={kind,base,token:status.contact.edit_token,values:{...base},purposes:structuredClone(contact.purposes(status.contact)),stale:false};
      } else if(configKinds.has(kind)) {
        if(typeof status.edit_token!=="string")return;
        if(kind!=="settings"&&!maintenance?.fields(kind).every(key=>maintenance.validField(key,status.settings?.[key])))return;
        const base=Object.fromEntries(configFields(kind).map(key=>[key,status.settings[key]]));
        draft={kind,base,token:status.edit_token,values:{...base},stale:false};
      } else if(kind==="align") {
        if(!maintenance?.canAlign(status))return;
        draft={kind,base:maintenance.snapshot(status),values:{applicability:"",day:status.state.cycle_timeline?.cycle_day??""},stale:false};
      } else {
        const item=status.calendar?.items?.[index];if(!usable(item))return;
        draft={kind:"wording",base:structuredClone(item),values:{presence:item.presence||""},stale:false};
      }
      category=kind==="contact"?"contact":kind==="planning"||kind==="wording"?"planning":kind==="settings"?"presentation":"maintenance";
      say("");emit();
      return true;
    }
    function input(event) {
      if(!draft||busy||!event.target.matches("[data-state-field]"))return;
      const field=event.target.dataset.stateField;
      if(Object.hasOwn(draft.values,field))draft.values[field]=field==="cycle_discomfort_types"
        ?maintenance.toggleChecklist(field,draft.values[field],event.target.value,event.target.checked)
        :event.target.type==="checkbox"?event.target.checked:event.target.value;
      if(field==="cycle_discomfort_enabled") {
        const group=document.querySelector("[data-cycle-discomfort-fields]");
        if(group)group.disabled=!event.target.checked;
      }
      if(event.target.type==="range") {
        const output=document.getElementById("state-config-"+field+"-output");
        if(output)output.value=event.target.value+"%";
      }
      if(draft.kind==="align"&&field==="applicability")emit();
    }
    function command() {
      if(draft.kind==="contact") {
        const values=contact.normalized(draft.values);
        const changes=Object.fromEntries(Object.keys(values).filter(key=>values[key]!==draft.base[key]).map(key=>[key,values[key]]));
        return Object.keys(changes).length?{action:"contact.configure",edit_token:draft.token,changes}:null;
      }
      if(configKinds.has(draft.kind)) {
        let values;
        if(draft.kind==="settings"){
          const seconds=Number(draft.values.typing_refresh_seconds);
          if(!Number.isInteger(seconds)||seconds<1||seconds>10)throw new Error("刷新间隔请填写 1–10 之间的整数秒。");
          values={...draft.values,typing_refresh_seconds:seconds};
        }else values=maintenance.normalized(draft.kind,draft.values);
        const changes=Object.fromEntries(configFields(draft.kind).filter(key=>values[key]!==draft.base[key]).map(key=>[key,values[key]]));
        return Object.keys(changes).length?{action:"configure",edit_token:draft.token,changes}:null;
      }
      if(draft.kind==="align")return maintenance.alignment(draft);
      const presence=draft.values.presence.trim();
      if([...presence].length>8)throw new Error("公开文案最多 8 个字，可留空。");
      return presence!==draft.base.presence?{action:"calendar.presence",id:draft.base.id,expected_revision:draft.base.revision,
        view_token:draft.base.view_token,data:{presence}}:null;
    }
    async function send(recover=false) {
      if(busy||loading||!scope||!status||(!recover&&(!draft||draft.stale||pending)))return;
      let body;
      try {body=recover?pending:command();}catch(problem){say(problem.message,true);emit();return;}
      if(!body){draft=null;say("没有需要保存的修改。");emit();return;}
      if(!recover)body={...body,operation_key:crypto.randomUUID()};
      const original={...scope},request=structuredClone(body);
      pending=request;remember(original.storage,request);busy=true;say("正在保存…");emit();
      try {
        const result=await api("POST",original.path+"/command",request);
        if(typeof result.operation_id!=="string")throw Object.assign(new Error("invalid_response"),{code:"invalid_response"});
        forget(original.storage,request.operation_key);
        if(!alive||scope?.key!==original.key||pending?.operation_key!==request.operation_key)return;
        pending=draft=null;busy=false;say(result.replayed?"已核对原请求：保存成功。":"已保存，请查看最新生效情况。");emit();
        await refresh();
      } catch(problem) {
        if(problem.confirmed)forget(original.storage,request.operation_key);
        if(!alive||scope?.key!==original.key||pending?.operation_key!==request.operation_key)return;
        busy=false;
        if(problem.confirmed) {
          pending=null;if(draft)draft.stale=staleCodes.has(problem.code);
          say(problem.code==="record_revision_conflict"&&request.action==="cycle.align"?"角色状态已变化，填写内容已保留。请读取当前版本后核对校准。":messages[problem.code]||"保存未完成，请刷新核对。",true);
          if(deniedCodes.has(problem.code)){draft=null;failed(problem);return;}
        } else say("保存结果尚未确认。可刷新查看当前值，或使用原请求核对确认。",true);
        emit();
      }
    }
    async function rebase() {
      if(!draft||busy||pending)return;
      const original=scope.key,previous=draft;busy=true;emit();
      const fresh=await refresh();
      if(!alive||scope?.key!==original)return;
      busy=false;
      if(!fresh){emit();return;}
      if(previous.kind==="contact") {
        if(!contact.supported(fresh.contact)){say("当前联系设置暂不可编辑，请关闭编辑并刷新核对。",true);emit();return;}
        const names=contact.fields(fresh.contact),touched=names.filter(key=>Object.hasOwn(previous.base,key)&&String(previous.values[key])!==String(previous.base[key]));
        const base=Object.fromEntries(names.map(key=>[key,fresh.contact.settings[key]]));
        draft={kind:"contact",base,token:fresh.contact.edit_token,purposes:structuredClone(contact.purposes(fresh.contact)),
          values:{...base,...Object.fromEntries(touched.map(key=>[key,previous.values[key]]))},stale:false};
      } else if(configKinds.has(previous.kind)) {
        const names=configFields(previous.kind),touched=names.filter(key=>String(previous.values[key])!==String(previous.base[key]));
        const base=Object.fromEntries(names.map(key=>[key,fresh.settings[key]]));
        draft={kind:previous.kind,base,token:fresh.edit_token,values:{...base,...Object.fromEntries(touched.map(key=>[key,previous.values[key]]))},stale:false};
      } else if(previous.kind==="align") {
        if(!maintenance.canAlign(fresh)){say("请先启用周期模拟并读取可用的角色状态，再重新选择校准。",true);emit();return;}
        draft={...previous,base:maintenance.snapshot(fresh),stale:false};
      } else {
        const row=fresh.calendar?.items?.find(item=>item.id===previous.base.id);
        if(!usable(row)){draft=previous;say("该日程已取消或不可读取，请关闭编辑并重新选择。",true);emit();return;}
        draft={...previous,base:structuredClone(row),stale:false};
      }
      say("已读取当前版本并保留你的修改，请核对后保存。");emit();
    }
    function click(event) {
      const button=event.target.closest("[data-state-edit]");if(!button)return false;
      const action=button.dataset.stateEdit;
      if(["home","settings","wording","maintenance","cycle","align","planning","contact","mood","patrol"].includes(action))open(action,Number(button.dataset.index));
      if(action==="cancel"&&!busy){draft=null;say("");emit();}
      if(action==="recover")send(true);
      if(action==="rebase")rebase();
      if(action==="dismiss"&&!busy){forget(scope.storage,pending?.operation_key);pending=draft=null;say("已结束核对；已保存的设置不会撤销。");emit();refresh();}
      return true;
    }
    function submit(event) {if(event.target.id!=="state-edit-form")return;event.preventDefault();send();}
    function form() {
      if(!draft)return "";
      const disabled=busy||!!pending,settings=draft.kind==="settings";
      const content=draft.kind==="contact"?contact.form(draft,e):maintenance?.titles[draft.kind]?maintenance.form(draft,e):settings?`<div class="state-edit-fields"><label class="state-checkbox"><input type="checkbox" id="state-typing-enabled" data-state-field="typing_enabled" ${draft.values.typing_enabled?"checked":""}>启用正在输入提示</label>
        <label for="state-typing-seconds">输入提示刷新间隔（秒）<input id="state-typing-seconds" type="number" min="1" max="10" step="1" required data-state-field="typing_refresh_seconds" value="${e(draft.values.typing_refresh_seconds)}"></label>
        <label class="state-checkbox"><input type="checkbox" id="state-presence-enabled" data-state-field="presence_enabled" ${draft.values.presence_enabled?"checked":""}>启用 QQ 自定义短状态</label></div>
        <p class="state-edit-help">启用后将更新所选 QQ 账号的展示。</p>`
        :`<p class="state-edit-title">${e(draft.base.title)}</p><label for="state-public-wording">公开短文案（最多 8 个字，可留空）<input id="state-public-wording" type="text" data-state-field="presence" value="${e(draft.values.presence)}" autocomplete="off"></label>
        <p class="state-edit-help">当前文案：${e(current()?.presence||"留空")}；清空后不提供日程文案。</p>`;
      const title=draft.kind==="contact"?"联系安排":maintenance?.titles[draft.kind];
      return `<form id="state-edit-form" data-state-form-kind="${draft.kind}"><fieldset ${disabled?"disabled":""}><legend>${title|| (settings?"编辑展示设置":"编辑日程公开文案")}</legend>${content}</fieldset>
        <div class="state-edit-actions"><button type="submit" class="memory-button" ${disabled||draft.stale?"disabled":""}>${busy?"正在保存…":draft.kind==="align"?"确认周期校准":title?"保存"+title:settings?"保存展示设置":"保存公开文案"}</button>
        ${draft.stale?`<button type="button" class="memory-button" data-state-edit="rebase" ${disabled?"disabled":""}>读取当前版本继续编辑</button>`:""}
        <button type="button" class="memory-button" data-state-edit="cancel" ${busy?"disabled":""}>取消编辑</button></div></form>`;
    }
    function focusedMarkup(feature) {
      const kinds={home:"home",energy:"intensity",health:"maintenance",hunger:"maintenance",cycle:"cycle",
        mood:"mood",patrol:"patrol",calendar:"calendar",planning:"planning",presentation:"settings"};
      const kind=kinds[feature];
      if(!kind)return "";
      const title=maintenance?.titles[kind]||"QQ 展示设置";
      const editing=draft&&(draft.kind===kind||feature==="cycle"&&draft.kind==="align");
      const unavailable=kind==="settings"?typeof status.edit_token!=="string"
        :kind==="align"?!maintenance.canAlign(status):!maintenance?.fields(kind)?.length
          ||!maintenance.fields(kind).every(key=>maintenance.validField(key,status.settings?.[key]));
      const action=feature==="home"?"home":feature==="energy"?"intensity":feature==="health"||feature==="hunger"?"maintenance":kind;
      const scopes=feature==="calendar"?"当前会话":feature==="presentation"?"当前 QQ 窗口":"当前人格";
      const summary=feature==="home"?maintenance.actionSummary("home",status,e)
        :feature==="energy"?maintenance.actionSummary("intensity",status,e)
          :feature==="health"||feature==="hunger"?maintenance.actionSummary("maintenance",status,e)
            :feature==="cycle"?maintenance.actionSummary("cycle",status,e)
              :feature==="mood"?maintenance.actionSummary("mood",status,e)
                :feature==="patrol"?maintenance.actionSummary("patrol",status,e):"查看并调整当前设置";
      const displayed=feature==="home"?`<p class="state-edit-help">首页当前展示：${Object.entries({energy:"能量",health:"健康",hunger:"饥饿",sleep:"睡眠",cycle:"生理期",busy:"忙碌",location:"位置"})
        .filter(([key])=>status.settings["home_show_"+key]!==false).map(([,label])=>label).join("、")||"无"}</p>`:"";
      const alignReady=maintenance?.canAlign(status);
      const alignAction=feature==="cycle"&&!editing
        ?`<button type="button" class="memory-button" data-state-edit="align" ${busy||loading||pending||!alignReady?"disabled":""} ${alignReady?"":"title=\"请先开启生理期模拟并读取角色状态\""}>校准当前周期</button>`:"";
      const sharedForm=editing?form():`<p class="state-feature-scope">${e(scopes)} · ${e(summary)}</p>
        ${displayed}<button type="button" class="memory-button" data-state-edit="${action}" ${busy||loading||pending||unavailable?"disabled":""}>${feature==="home"?"配置状态与首页展示":"调整"+title}</button>`;
      const feedbackVisible=feature==="home"
        ?draft?.kind==="home"
        :feature==="presentation"
          ?category==="presentation"
          :feature==="planning"
            ?category==="planning"
            :(["energy","health","hunger","cycle","mood","patrol"].includes(feature)&&category==="maintenance");
      const currentFeedback=feedbackVisible?feedbackMarkup():"";
      return `<section class="panel state-edit-panel state-feature-editor">${currentFeedback}${sharedForm}${alignAction?`<div class="state-edit-actions">${alignAction}</div>`:""}</section>`;
    }
    function feedbackMarkup() {
      return `${message?`<p class="memory-notice ${error?"error":""}" role="status" aria-live="polite">${e(message)}</p>`:""}
        ${pending?`<div class="state-pending" role="status"><strong>${busy?"请求处理中":"有一笔保存尚待核对"}</strong><p>${e(pending.action==="configure"?Object.entries(pending.changes).map(([key,value])=>`${maintenance?.label(key)||key}：${typeof value==="boolean"?(value?"开启":"关闭"):String(value).slice(0,100)}`).join("；"):maintenance?.pendingText(pending)||"状态设置" )}</p><div class="state-edit-actions">
          <button type="button" class="memory-button" data-state-edit="recover" ${busy||loading?"disabled":""}>用原请求核对</button>
          <button type="button" class="memory-button" data-state-edit="dismiss" ${busy?"disabled":""}>结束核对</button></div></div>`:""}`;
    }
    function markup({section="state",configPanel=null,feature=null}={}) {
      if(!status||!scope)return "";
      if(section==="state"&&feature)return focusedMarkup(feature);
      const locked=busy||loading||!!pending||!!draft||!!calendarEditor?.interacting;
      const showBody=configPanel===null||configPanel==="body";
      const showPresentation=configPanel===null||configPanel==="presentation";
      const showPlanning=configPanel===null||configPanel==="planning";
      const items=status.calendar?.items||[],plans=items.map((item,index)=>({item,index})).filter(({item})=>item.kind==="role_plan");
      const pendingText=pending?.action==="contact.configure"?Object.entries(pending.changes).map(([key,value])=>contact.label(key,status.contact)+"："+(typeof value==="boolean"?(value?"开启":"关闭"):String(value).slice(0,100))).join("；")
        :pending?.action==="configure"?Object.entries(pending.changes).map(([key,value])=>`${({typing_enabled:"输入提示",typing_refresh_seconds:"刷新秒数",presence_enabled:"自定义短状态"})[key]||maintenance?.label(key)}：${typeof value==="boolean"?(value?"开启":"关闭"):String(value).slice(0,100)}`).join("；")
        :pending?maintenance?.pendingText(pending)||`日程 ${pending.id} · 公开文案：${pending.data.presence||"留空"}`:"";
      const feedback=`${message?`<p class="memory-notice ${error?"error":""}" role="status" aria-live="polite">${e(message)}</p>`:""}
        ${pending?`<div class="state-pending" role="status"><strong>${busy?"请求处理中":"有一笔保存尚待核对"}</strong><p>${e(pendingText)}</p><div class="state-edit-actions">
          <button type="button" class="memory-button" data-state-edit="recover" ${busy||loading?"disabled":""}>用原请求核对</button>
          <button type="button" class="memory-button" data-state-edit="dismiss" ${busy?"disabled":""}>结束核对</button></div></div>`:""}`;
      if(section==="contact")return `<section class="panel state-edit-panel state-contact-panel">${contact?.summary(status.contact,e)||"<p>联系设置组件尚未加载，请刷新页面。</p>"}${category==="contact"?feedback:""}
        ${draft&&category==="contact"?form():`<button type="button" class="memory-button" data-state-edit="contact" ${locked||!contact?.supported(status.contact)?"disabled":""}>编辑联系安排</button>`}</section>
        ${pending&&category!=="contact"?`<section class="panel state-edit-panel"><h3>原设置请求待核对</h3>${feedback}</section>`:""}`;
      const body=showBody&&maintenance?`<section id="state-maintenance" class="panel state-edit-panel state-maintenance-panel">${maintenance.summary(status,e)}${category==="maintenance"?feedback:""}
        ${draft&&category==="maintenance"?form():`<div class="state-setting-list" aria-label="状态配置专题">${["maintenance","cycle","align","mood","patrol"].map((kind,index)=>{
          const scopes={maintenance:"当前会话",cycle:"共享模拟",align:"当前角色",mood:"当前会话",patrol:"当前会话"};
          const actions={maintenance:"调整频率",cycle:"配置周期",align:"校准位置",mood:"调整心情",patrol:"设置巡视"};
          const unavailable=kind==="align"?!maintenance.canAlign(status):typeof status.edit_token!=="string"||!maintenance.fields(kind).every(key=>maintenance.validField(key,status.settings[key]));
          const disabled=locked||unavailable;
          return `<article class="state-setting-row" data-setting-kind="${kind}"><span class="state-setting-index" aria-hidden="true">0${index+1}</span><div class="state-setting-copy"><div class="state-setting-meta"><span>${scopes[kind]}</span>${kind==="cycle"?`<span class="state-setting-scope">按 Bot 共享</span>`:""}</div><h4>${maintenance.titles[kind]}</h4><p>${maintenance.actionSummary(kind,status,e)}</p></div><button type="button" class="state-setting-action" data-state-edit="${kind}" aria-label="${actions[kind]} ${maintenance.titles[kind]}" ${disabled?`disabled title="${kind==="align"&&!maintenance.canAlign(status)?"请先启用周期模拟并读取角色状态":"当前配置暂不可编辑"}`:""}>${actions[kind]}</button></article>`;
        }).join("")}</div>`}
        ${!status.settings.cycle_enabled?"<p class=\"state-edit-help\">启用生理期模拟后可校准周期。</p>":""}</section>`:"";
      // Plan mutations and presentation settings have separate drafts and panels.
      const presentationMarkup=showPresentation?`<section id="state-presentation" class="panel state-edit-panel"><header><h3>QQ 展示设置</h3></header>
        ${category==="presentation"?feedback:""}
        ${draft&&category==="presentation"?form():`<button type="button" class="memory-button" data-state-edit="settings" ${locked||typeof status.edit_token!=="string"?"disabled":""}>编辑展示设置</button>`}
        </section>`:"";
      const calendarMarkup=showPlanning?calendarEditor?.markup({items:plans,locked,escape:e})||"":"";
      const planningMarkup=showPlanning&&maintenance?.planningSummary?`<section id="state-planning" class="panel state-edit-panel state-planning-panel">${maintenance.planningSummary(status,e)}${category==="planning"&&draft?.kind!=="wording"?feedback:""}
        ${draft&&category==="planning"&&draft.kind==="planning"?form():`<button type="button" class="memory-button" data-state-edit="planning" ${locked||typeof status.edit_token!=="string"||!maintenance.fields("planning").every(key=>maintenance.validField(key,status.settings?.[key]))?"disabled":""}>编辑自动规划设置</button>`}</section>`:"";
      const wordingMarkup=showPlanning&&draft?.kind==="wording"&&category==="planning"?`<section class="panel state-edit-panel state-wording-panel">${category==="planning"?feedback:""}${form()}</section>`:"";
      return body+presentationMarkup+planningMarkup+calendarMarkup+wordingMarkup+(pending&&category==="contact"?`<section class="panel state-edit-panel"><h3>联系安排请求待核对</h3>${feedback}</section>`:"");
    }
    return {setScope,setStatus,invalidate,open,markup,click,input,submit,
      get requiredFeature(){
        if(calendarEditor?.interacting)return "planning";
        const kind=draft?.kind|| (pending?.action==="cycle.align"?"align":pending?.action==="calendar.presence"?"wording":null);
        if(kind)return ({intensity:"energy",maintenance:"health",cycle:"cycle",align:"cycle",mood:"mood",patrol:"patrol",
          planning:"planning",wording:"planning",settings:"presentation"})[kind]||null;
        if(pending?.action==="configure"){
          const keys=Object.keys(pending.changes||{});
          if(keys.some(key=>key.startsWith("cycle_")))return "cycle";
          if(keys.some(key=>key.startsWith("planning_")))return "planning";
          if(keys.some(key=>key.startsWith("mood_")))return "mood";
          if(keys.some(key=>key.startsWith("daily_state_patrol_")))return "patrol";
          if(keys.some(key=>["typing_enabled","typing_refresh_seconds","presence_enabled","online_status_enabled"].includes(key)))return "presentation";
          if(keys.some(key=>["health_enabled","hunger_enabled"].includes(key)))return "health";
        }
        return null;
      },
      get interacting(){return busy||!!draft||!!pending||!!calendarEditor?.interacting;},
      get busy(){return busy||!!calendarEditor?.busy;},destroy(){alive=false;draft=status=null;calendarEditor?.destroy();}};
  }
  return {create};
})();
