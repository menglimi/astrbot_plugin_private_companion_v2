"use strict";
window.CompanionCalendarEditor = (() => {
  const frequencies={once:"一次",daily:"每天",weekly:"每周",monthly:"每月",yearly:"每年"};
  const gaps={reject:"要求改选有效时间",shift_forward:"顺延至有效时间"};
  const modes={move:"改到新的时间",skip:"跳过这一次"};
  const e=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const cache=new Map();
  const message={calendar_exists:"这个日程标识已经存在，请重新打开创建表单。",calendar_closed:"日程已取消或不存在。",
    calendar_kind_changed:"不能把角色计划改成其他类型，请创建新的日程。",calendar_occurrence_missing:"这次重复发生不存在，请重新读取日程。",
    calendar_exception_invalid:"请提供有效的重复序号和改期时间。",calendar_reminder_past:"提醒时间已经过去，请选择未来的发生。",
    calendar_text_invalid:"请核对标题、详情或公开文案的长度。",calendar_duration_invalid:"时长需为 1–1440 分钟。",
    calendar_event_invalid:"日程字段不完整，请重新填写。",calendar_kind_invalid:"这里只能创建角色计划。",
    schedule_needs_resolution:"这个时区的本地时间不存在，请改用其他时间或选择顺延。",timezone_unavailable:"请填写有效的 IANA 时区。",
    record_revision_conflict:"日程已被更新，填写内容已保留。请读取当前版本后核对。",state_view_stale:"角色或权限已变化，请读取当前版本后核对。",
    core_access_required:"当前账号没有日程管理权限。",authorization_denied:"当前授权不足，请刷新核对。",
    dashboard_identity_required:"请重新登录 AstrBot 管理界面。",binding_revoked:"当前身份授权已撤销，请重新进入。",
    binding_rebound:"当前身份绑定已变化，请重新进入。",role_binding_changed:"角色绑定已变化，请重新进入。",
    staging_host_terminated:"插件已停止，请重新打开页面。"};
  const staleCodes=new Set(["record_revision_conflict","state_view_stale","calendar_occurrence_missing","calendar_closed"]);
  const deniedCodes=new Set(["core_access_required","authorization_denied","dashboard_identity_required","binding_revoked","binding_rebound","role_binding_changed","staging_host_terminated"]);
  const exact=(value,keys)=>value&&typeof value==="object"&&!Array.isArray(value)&&Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
  const dataShape=data=>exact(data,["kind","title","detail","schedule","duration_minutes","presence"])
    &&data.kind==="role_plan"&&typeof data.title==="string"&&!!data.title.trim()&&[...data.title].length<=256&&typeof data.detail==="string"&&[...data.detail].length<=4096
    &&typeof data.presence==="string"&&[...data.presence].length<=8&&Number.isInteger(data.duration_minutes)&&data.duration_minutes>=1&&data.duration_minutes<=1440
    &&scheduleShape(data.schedule);
  const scheduleShape=schedule=>exact(schedule,["anchor","timezone_name","frequency","interval","count","fold","gap_policy"])
    &&typeof schedule.anchor==="string"&&Number.isFinite(Date.parse(schedule.anchor))&&typeof schedule.timezone_name==="string"&&!!schedule.timezone_name
    &&Object.hasOwn(frequencies,schedule.frequency)&&Number.isSafeInteger(schedule.interval)&&schedule.interval>=1
    &&(schedule.count===null||Number.isSafeInteger(schedule.count)&&schedule.count>=1)&&[0,1].includes(schedule.fold)
    &&Object.hasOwn(gaps,schedule.gap_policy);
  function valid(command) {
    if(!command||typeof command.operation_key!=="string"||!command.operation_key||command.operation_key.length>128)return false;
    if(typeof command.id!=="string"||!command.id||!Number.isSafeInteger(command.expected_revision))return false;
    const common=["action","operation_key","id","expected_revision","view_token"];
    if(command.action==="calendar.create")return exact(command,[...common,"data"])&&command.expected_revision===0&&typeof command.id==="string"&&!!command.id
      &&typeof command.view_token==="string"&&dataShape(command.data);
    if(command.action==="calendar.revise")return exact(command,[...common,"data","sources"])&&command.expected_revision>0&&typeof command.id==="string"
      &&typeof command.view_token==="string"&&Array.isArray(command.sources)&&command.sources.length<=8&&dataShape(command.data);
    if(command.action==="calendar.cancel")return exact(command,common)&&command.expected_revision>0&&typeof command.id==="string"&&typeof command.view_token==="string";
    if(command.action==="calendar.remind")return exact(command,[...common,"sequence"])&&command.expected_revision>0&&typeof command.id==="string"
      &&typeof command.view_token==="string"&&Number.isInteger(command.sequence)&&command.sequence>=0;
    if(command.action==="calendar.exception")return exact(command,[...common,"data"])&&command.expected_revision>0&&typeof command.id==="string"
      &&typeof command.view_token==="string"&&exact(command.data,["sequence","start"])&&Number.isInteger(command.data.sequence)&&command.data.sequence>=0
      &&(command.data.start===null||typeof command.data.start==="string");
    return false;
  }
  function storage(scope){return "companion-state-calendar.v1:"+scope.key;}
  function stored(key){if(cache.has(key))return cache.get(key);try{const value=JSON.parse(sessionStorage.getItem(key));if(valid(value)){cache.set(key,value);return value;}}catch{}return null;}
  function remember(key,value){if(value)cache.set(key,value);else cache.delete(key);try{if(value)sessionStorage.setItem(key,JSON.stringify(value));else sessionStorage.removeItem(key);}catch{}}
  function forget(key,operation){if(stored(key)?.operation_key===operation)remember(key,null);}
  function offsetMinutes(date,zone){
    const parts=new Intl.DateTimeFormat("en-US",{timeZone:zone,timeZoneName:"longOffset",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(date);
    const raw=parts.find(item=>item.type==="timeZoneName")?.value||"GMT";
    if(raw==="GMT"||raw==="UTC")return 0;const match=raw.match(/GMT([+-])(\d{2}):?(\d{2})?/);if(!match)throw new Error("请填写有效的 IANA 时区。");
    return (match[1]==="-"?-1:1)*(Number(match[2])*60+Number(match[3]||0));
  }
  function wallToIso(value,zone,fold=0,gap="reject"){
    if(typeof value!=="string"||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$/.test(value))throw new Error("请选择日程开始时间。");
    if(typeof zone!=="string"||!zone.trim())throw new Error("请填写有效的 IANA 时区。");
    const wall=Date.parse(value+":00Z");
    if(!Number.isFinite(wall)||new Date(wall).toISOString().slice(0,16)!==value)throw new Error("请选择有效的日程开始时间。");
    // Check offsets on both sides of a transition, then round-trip the chosen
    // instant. Treating wall time as UTC chooses the wrong offset near DST.
    let offsets;
    try{offsets=new Set([-36,0,36].map(hours=>offsetMinutes(new Date(wall+hours*3600000),zone)));}
    catch{throw new Error("请填写有效的 IANA 时区。");}
    const choices=[...offsets].map(offset=>new Date(wall-offset*60000).toISOString()).sort();
    const exact=choices.filter(iso=>isoToWall(iso,zone)===value);
    if(exact.length)return exact[Math.min(fold,exact.length-1)];
    if(gap==="shift_forward"){
      const after=choices.filter(iso=>isoToWall(iso,zone)>value);
      if(after.length)return after[0];
    }
    throw new Error("这个时区的本地时间不存在，请改用其他时间或选择顺延。");
  }
  function isoToWall(value,zone){
    if(!value)return "";try{const parts=new Intl.DateTimeFormat("en-CA",{timeZone:zone,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(new Date(value));
      const get=name=>parts.find(item=>item.type===name)?.value;return `${get("year")}-${get("month")}-${get("day")}T${get("hour")==="24"?"00":get("hour")}:${get("minute")}`;
    }catch{return "";}
  }
  function scheduleValues(schedule){
    const zone=schedule?.timezone_name||"Asia/Shanghai";return {start:isoToWall(schedule?.anchor,zone),timezone:zone,frequency:schedule?.frequency||"once",
      interval:schedule?.interval??1,count:schedule?.count??"",fold:schedule?.fold??0,gap_policy:schedule?.gap_policy||"reject"};
  }
  function blankValues(item){
    const schedule=scheduleValues(item?.schedule);return {title:item?.title||"",detail:item?.detail||"",presence:item?.presence||"",duration:item?.duration_minutes??30,...schedule};
  }
  function create({api,changed,refresh,failed}){
    let scope=null,status=null,draft=null,pending=null,busy=false,loading=false,alive=true,messageText="",error=false;
    const emit=()=>{if(alive)changed();};
    const say=(value,bad=false)=>{messageText=value;error=bad;};
    const sameValue=(left,right)=>Array.isArray(left)||Array.isArray(right)
      ?JSON.stringify(left)===JSON.stringify(right)
      :left===right||typeof left==="number"&&typeof right==="string"&&right.trim()!==""&&left===Number(right)
        ||typeof right==="number"&&typeof left==="string"&&left.trim()!==""&&right===Number(left);
    function draftDirty(){return !!draft&&Object.keys(draft.values).some(key=>!sameValue(draft.values[key],draft.initial?.[key]));}
    // A successful state read carries the core operator's view token. Automatic
    // role access is separate from the authenticated manager's calendar access.
    const canManage=()=>typeof status?.create_token==="string"&&!!status.create_token;
    const usable=item=>item?.kind==="role_plan"&&item.state!=="cancelled"&&typeof item.view_token==="string";
    function setScope(value){const key=JSON.stringify([value.installation_id,value.operator_id,value.path]);if(scope?.key===key)return;scope={...value,key};status=draft=null;pending=stored(storage(scope));busy=false;messageText="";error=false;}
    function setStatus(value,isLoading=false){status=value;loading=isLoading;}
    function invalidate(){scope=status=draft=pending=null;busy=false;messageText="";error=false;}
    function open(kind,index){
      if(busy||loading||pending||!status||!canManage())return;
      if(kind==="create"){
        if(typeof status.create_token!=="string")return;const values=blankValues();draft={kind,base:null,token:status.create_token,values,initial:{...values},stale:false};
      }else{
        const item=status.calendar?.items?.[index];if(!usable(item))return;const base=structuredClone(item);
        if(kind==="revise"){const values=blankValues(base);draft={kind,base,values,initial:{...values},stale:false};}
        else if(kind==="exception"){
          if(base.schedule?.frequency==="once")return;const schedule=scheduleValues(base.schedule),values={sequence:1,mode:"move",start:schedule.start,timezone:schedule.timezone};draft={kind,base,values,initial:{...values},stale:false};
        }else if(kind==="cancel")draft={kind,base,values:{},initial:{},stale:false};
        else if(kind==="remind")draft={kind,base,values:{sequence:1},initial:{sequence:1},stale:false};
      }
      say("");emit();
    }
    function input(event){if(!draft||busy||!event.target.matches("[data-calendar-field]"))return;const key=event.target.dataset.calendarField;
      if(Object.hasOwn(draft.values,key))draft.values[key]=event.target.type==="checkbox"?event.target.checked:event.target.value;
      if((draft.kind==="exception"&&key==="mode")||key==="frequency")emit();
    }
    function buildData(values,base=null){
      const title=String(values.title||"").trim(),detail=String(values.detail||""),presence=String(values.presence||"").trim();
      if(!title||[...title].length>256)throw new Error("标题需填写且不超过 256 个字。");if([...detail].length>4096)throw new Error("详情最多 4096 个字。");
      if([...presence].length>8)throw new Error("公开文案最多 8 个字，可留空。");
      const interval=Number(values.interval),count=values.count===""||values.count==null?null:Number(values.count),duration=Number(values.duration);
      if(!Number.isInteger(duration)||duration<1||duration>1440)throw new Error("时长需为 1–1440 分钟。");
      if(!Object.hasOwn(frequencies,values.frequency)||!Number.isSafeInteger(interval)||interval<1)throw new Error("请核对重复频率和间隔。");
      if(count!==null&&(!Number.isSafeInteger(count)||count<1))throw new Error("重复次数需为空或为正整数。");
      const timezone=String(values.timezone||"").trim(),fold=Number(values.fold);
      if(![0,1].includes(fold))throw new Error("请选择夏令时重复时间的处理方式。");
      const before=base&&scheduleValues(base.schedule);
      const unchanged=before&&values.start===before.start&&timezone===before.timezone&&fold===before.fold;
      const schedule={anchor:unchanged?base.schedule.anchor:wallToIso(values.start,timezone,fold,values.gap_policy),timezone_name:timezone,frequency:values.frequency,
        interval,count,fold,gap_policy:values.gap_policy};
      if(!Object.hasOwn(gaps,schedule.gap_policy))throw new Error("请选择夏令时缺口处理方式。");
      return {kind:"role_plan",title,detail,schedule,duration_minutes:duration,presence};
    }
    function command(){
      if(draft.kind==="create")return {action:"calendar.create",id:"plan-"+crypto.randomUUID(),expected_revision:0,view_token:draft.token,data:buildData(draft.values)};
      if(draft.kind==="revise")return {action:"calendar.revise",id:draft.base.id,expected_revision:draft.base.revision,view_token:draft.base.view_token,
        data:buildData(draft.values,draft.base),sources:Array.isArray(draft.base.sources)?structuredClone(draft.base.sources):[]};
      if(draft.kind==="exception"){
        const sequence=Number(draft.values.sequence)-1;if(!Number.isSafeInteger(sequence)||sequence<0)throw new Error("发生次数请从 1 开始填写。");
        const start=draft.values.mode==="skip"?null:wallToIso(draft.values.start,draft.values.timezone,draft.base.schedule.fold,draft.base.schedule.gap_policy);
        return {action:"calendar.exception",id:draft.base.id,expected_revision:draft.base.revision,view_token:draft.base.view_token,data:{sequence,start}};
      }
      if(draft.kind==="remind"){
        const sequence=Number(draft.values.sequence)-1;if(!Number.isSafeInteger(sequence)||sequence<0)throw new Error("发生次数请从 1 开始填写。");
        return {action:"calendar.remind",id:draft.base.id,expected_revision:draft.base.revision,view_token:draft.base.view_token,sequence};
      }
      return {action:"calendar.cancel",id:draft.base.id,expected_revision:draft.base.revision,view_token:draft.base.view_token};
    }
    async function send(recover=false){
      if(busy||loading||!scope||!status||(!recover&&(!draft||draft.stale||pending)))return;let body;
      try{body=recover?pending:command();}catch(problem){say(problem.message,true);emit();return;}
      if(!body){draft=null;say("没有需要保存的修改。");emit();return;}if(!recover)body={...body,operation_key:crypto.randomUUID()};
      const original={...scope},request=structuredClone(body);pending=request;remember(storage(original),request);busy=true;say("正在保存…");emit();
      try{const result=await api("POST",original.path+"/command",request);if(typeof result.operation_id!=="string")throw Object.assign(new Error("invalid_response"),{code:"invalid_response"});
        forget(storage(original),request.operation_key);if(!alive||scope?.key!==original.key||pending?.operation_key!==request.operation_key)return;
        pending=draft=null;busy=false;say(result.replayed?"已核对原请求：日程保存成功。":"日程已保存，请查看最新安排。");emit();await refresh();
      }catch(problem){if(problem.confirmed)forget(storage(original),request.operation_key);if(!alive||scope?.key!==original.key||pending?.operation_key!==request.operation_key)return;busy=false;
        if(problem.confirmed){pending=null;if(draft)draft.stale=staleCodes.has(problem.code);say(message[problem.code]||"日程保存未完成，请刷新核对。",true);if(deniedCodes.has(problem.code)){draft=null;failed(problem);return;}}
        else say("日程保存结果尚未确认。可刷新查看，或使用原请求核对确认。",true);emit();}
    }
    async function rebase(){if(!draft||busy||pending)return;const original=scope.key,previous=draft;busy=true;emit();const fresh=await refresh();if(!alive||scope?.key!==original)return;busy=false;
      if(!fresh){emit();return;}if(previous.kind==="create"){draft={...previous,token:fresh.create_token,stale:false};}
      else{const current=fresh.calendar?.items?.find(item=>item.id===previous.base.id);if(!usable(current)){draft=previous;say("该日程已取消或不可读取，请关闭编辑并重新选择。",true);emit();return;}
        if(previous.kind==="revise"){
          const before=blankValues(previous.base),names=Object.keys(previous.values),touched=names.filter(key=>String(previous.values[key])!==String(before[key]));
          const base=structuredClone(current),freshValues=blankValues(base);draft={...previous,base,values:{...freshValues,...Object.fromEntries(touched.map(key=>[key,previous.values[key]]))},stale:false};
        }else if(previous.kind==="exception"){
          if(current.schedule.frequency==="once"){say("当前安排已改为一次事件，请关闭后选择修改整个日程。",true);emit();return;}
          draft={...previous,base:structuredClone(current),values:{...previous.values,timezone:current.schedule.timezone_name},stale:false};
        }else draft={...previous,base:structuredClone(current),stale:false};}
      say("已读取当前日程并保留你的修改，请核对后保存。");emit();}
    function discardIfPristine(){if(busy||pending||draftDirty())return false;if(draft){draft=null;say("");emit();}return true;}
    function click(event){const button=event.target.closest("[data-calendar-edit]");if(!button)return false;const action=button.dataset.calendarEdit;
      if(["create","revise","exception","cancel","remind"].includes(action))open(action,Number(button.dataset.index));
      if(action==="close"&&!busy){draft=null;say("");emit();}
      if(action==="recover")send(true);if(action==="rebase")rebase();
      if(action==="dismiss"&&!busy){forget(storage(scope),pending?.operation_key);pending=draft=null;say("已结束日程核对；已保存的日程不会撤销。");emit();refresh();}return true;}
    function submit(event){if(event.target.id!=="state-calendar-form")return false;event.preventDefault();send();return true;}
    function form(){if(!draft)return "";const v=draft.values;
      if(["create","revise"].includes(draft.kind))return `<div class="state-calendar-fields"><label for="calendar-title">计划标题<input id="calendar-title" data-calendar-field="title" maxlength="256" required value="${e(v.title)}"></label>
        <label for="calendar-detail">计划详情<textarea id="calendar-detail" data-calendar-field="detail" maxlength="4096" rows="3">${e(v.detail)}</textarea></label>
        <label for="calendar-presence">QQ 公开短文案（最多 8 个字，可留空）<input id="calendar-presence" data-calendar-field="presence" maxlength="8" value="${e(v.presence)}"></label>
        <label for="calendar-start">开始时间（按所选时区）<input id="calendar-start" type="datetime-local" data-calendar-field="start" required value="${e(v.start)}"></label>
        <label for="calendar-timezone">时区<input id="calendar-timezone" data-calendar-field="timezone" required value="${e(v.timezone)}" autocomplete="off"></label>
        <label for="calendar-frequency">重复方式<select id="calendar-frequency" data-calendar-field="frequency">${Object.entries(frequencies).map(([key,text])=>`<option value="${key}" ${v.frequency===key?"selected":""}>${text}</option>`).join("")}</select></label>
        <label for="calendar-interval">重复间隔<input id="calendar-interval" type="number" min="1" step="1" data-calendar-field="interval" required value="${e(v.interval)}"></label>
        <label for="calendar-count">重复次数（留空表示持续）<input id="calendar-count" type="number" min="1" step="1" data-calendar-field="count" value="${e(v.count)}"></label>
        <label for="calendar-duration">每次时长（分钟）<input id="calendar-duration" type="number" min="1" max="1440" step="1" data-calendar-field="duration" required value="${e(v.duration)}"></label>
        <label for="calendar-gap">夏令时缺口<select id="calendar-gap" data-calendar-field="gap_policy">${Object.entries(gaps).map(([key,text])=>`<option value="${key}" ${v.gap_policy===key?"selected":""}>${text}</option>`).join("")}</select></label>
        <label for="calendar-fold">夏令时重复时间<select id="calendar-fold" data-calendar-field="fold"><option value="0" ${Number(v.fold)===0?"selected":""}>采用较早一次</option><option value="1" ${Number(v.fold)===1?"selected":""}>采用较晚一次</option></select></label></div>
        <p class="state-edit-help">${draft.kind==="create"?"":"修改整组会重置例外并取消提醒；单次调整请选“仅改这次”。"}</p>`;
      if(draft.kind==="exception")return `<p class="state-edit-help">仅调整本次；原提醒将取消，需重新安排。</p>
        <div class="state-calendar-fields"><label for="calendar-sequence">第几次发生（从 1 开始）<input id="calendar-sequence" type="number" min="1" step="1" data-calendar-field="sequence" required value="${e(v.sequence)}"></label>
        <label for="calendar-exception-mode">处理方式<select id="calendar-exception-mode" data-calendar-field="mode">${Object.entries(modes).map(([key,text])=>`<option value="${key}" ${v.mode===key?"selected":""}>${text}</option>`).join("")}</select></label>
        <label for="calendar-exception-start">新时间（${e(v.timezone)}）<input id="calendar-exception-start" type="datetime-local" data-calendar-field="start" value="${e(v.start)}" ${v.mode==="skip"?"disabled":""}></label></div>`;
      if(draft.kind==="remind")return `<p class="state-edit-help">需提醒授权；再次安排会替换原提醒，改期或取消时会撤销提醒。</p>
        <label for="calendar-reminder-sequence">提醒第几次（从 1 开始）<input id="calendar-reminder-sequence" type="number" min="1" step="1" data-calendar-field="sequence" required value="${e(v.sequence)}"></label>`;
      return `<p class="state-edit-help">取消整组及全部未来发生、已有提醒。仅取消一次请选择“仅改这次”。</p>`;
    }
    function itemSummary(item){const s=item.schedule||{},unit={daily:"天",weekly:"周",monthly:"个月",yearly:"年"}[s.frequency],
      repeat=s.frequency==="once"?"一次":`每 ${s.interval||1} ${unit||"次"}${s.count?` · 共 ${s.count} 次`:""}`;
      const start=isoToWall(s.anchor,s.timezone_name),exceptions=Object.keys(item.exceptions||{}).length;
      return `${start?start.replace("T"," ")+" · "+s.timezone_name+" · ":""}${repeat}${exceptions?` · 已有 ${exceptions} 次例外`:""}${item.reminder_id?" · 已安排提醒":""}`;}
    function markup({items=[],locked=false,escape=e}={}){if(!status||!scope)return "";const can=canManage(),messageMarkup=messageText?`<p class="memory-notice ${error?"error":""}" role="status" aria-live="polite">${escape(messageText)}</p>`:"";
      const pendingAction={"calendar.create":"创建计划","calendar.revise":"修改日程","calendar.cancel":"取消日程","calendar.remind":"安排提醒","calendar.exception":"调整本次安排"}[pending?.action]||"保存日程";
      const pendingTitle=pending?.data?.title||status.calendar?.items?.find(item=>item.id===pending?.id)?.title||"当前日程";
      const pendingMarkup=pending?`<div class="state-pending" role="status"><strong>${busy?"请求处理中":"有一笔日程保存尚待核对"}</strong><p>待核对：${escape(pendingAction)} · ${escape(pendingTitle)}</p><div class="state-edit-actions"><button type="button" class="memory-button" data-calendar-edit="recover" ${busy||loading?"disabled":""}>用原请求核对</button><button type="button" class="memory-button" data-calendar-edit="dismiss" ${busy?"disabled":""}>结束核对</button></div></div>`:"";
      const body=draft?`<form id="state-calendar-form"><fieldset ${busy||pending?"disabled":""}><legend>${draft.kind==="create"?"创建角色计划":draft.kind==="revise"?"修改整个日程":draft.kind==="exception"?"修改这一次发生":draft.kind==="remind"?"安排日程提醒":"取消整组日程"}</legend>${form()}</fieldset><div class="state-edit-actions"><button type="submit" class="memory-button" ${busy||pending||draft.stale?"disabled":""}>${busy?"正在保存…":draft.kind==="create"?"创建角色计划":draft.kind==="revise"?"保存整个日程":draft.kind==="exception"?"保存这次修改":draft.kind==="remind"?"安排提醒":"确认取消"}</button>${draft.stale?`<button type="button" class="memory-button" data-calendar-edit="rebase" ${busy||pending?"disabled":""}>读取当前版本继续编辑</button>`:""}<button type="button" class="memory-button" data-calendar-edit="close" ${busy?"disabled":""}>取消编辑</button></div></form>`:
        `<div class="state-edit-actions"><button type="button" class="memory-button" data-calendar-edit="create" ${locked||!can?"disabled":""}>创建角色计划</button>${!can?"<span class=\"state-edit-help\">当前日程管理权限尚未确认，请刷新核对。</span>":""}</div>`;
      const itemMarkup=({item,index})=>{
        const wording=item.state==="cancelled"?"已取消":"公开文案："+escape(item.presence||"留空"),
          recurring=item.schedule?.frequency!=="once",disabled=locked||!can||!usable(item),wordingDisabled=locked||!usable(item);
        return `<li><div><strong>${escape(item.title)}</strong><p>${wording}</p><small class="state-calendar-meta">${escape(itemSummary(item))}</small></div><div class="state-calendar-actions"><button type="button" class="memory-button" data-state-edit="wording" data-index="${index}" ${wordingDisabled?"disabled":""}>编辑文案</button><button type="button" class="memory-button" data-calendar-edit="revise" data-index="${index}" ${disabled?"disabled":""}>修改整个日程</button>${recurring?`<button type="button" class="memory-button" data-calendar-edit="exception" data-index="${index}" ${disabled?"disabled":""}>仅改这次</button>`:""}<button type="button" class="memory-button" data-calendar-edit="remind" data-index="${index}" ${disabled?"disabled":""}>安排提醒</button><button type="button" class="memory-button" data-calendar-edit="cancel" data-index="${index}" ${disabled?"disabled":""}>取消整组</button></div></li>`;
      };
      const list=items.length?`<ul class="state-plan-list">${items.map(itemMarkup).join("")}</ul>`:`<div class="state-calendar-empty"><i data-lucide="calendar-plus" aria-hidden="true"></i><div><strong>本批暂无角色计划</strong><p>创建一项安排，让角色在连续日程中接续它。</p></div></div>`;
      const pagination=`${status.request_cursor?`<button type="button" class="memory-button" data-state-page="" ${locked?"disabled":""}>返回首批</button>`:""}${status.calendar?.next_cursor?`<button type="button" class="memory-button" data-state-page="${escape(status.calendar.next_cursor)}" ${locked?"disabled":""}>下一批</button>`:""}`;
      return `<section class="panel state-edit-panel state-calendar-section"><div class="state-plan-heading"><div><h4>角色计划与日程</h4><p>已接受的安排会作为角色回复时的日程依据。</p></div>${items.length?`<span class="state-calendar-count">${items.length} 项</span>`:""}</div>${messageMarkup}${pendingMarkup}<div class="state-calendar-create">${body}</div>${list}${status.calendar?.skipped?"<p class=\"state-calendar-warning\">部分日程的来源当前不可读取。</p>":""}${pagination?`<nav class="state-calendar-pagination" aria-label="日程分页">${pagination}</nav>`:""}</section>`;
    }
    return {setScope,setStatus,invalidate,open,markup,click,input,change:input,submit,discardIfPristine,
      get dirty(){return busy||!!pending||draftDirty();},get interacting(){return busy||!!draft||!!pending;},get busy(){return busy;},destroy(){alive=false;draft=status=null;}};
  }
  return {create};
})();
