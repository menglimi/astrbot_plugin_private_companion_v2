/* Synthetic contact settings in the existing state editor; no model, host reload, or external message. */
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const {randomUUID}=require("node:crypto");
const {test}=require("node:test");
const pageRoot=path.resolve(__dirname,"../pages/陪伴小屋");
const clone=value=>JSON.parse(JSON.stringify(value));
const settle=()=>new Promise(resolve=>setImmediate(resolve));
const scope={installation_id:"synthetic",operator_id:"dashboard:qa",path:"host/targets/first/roles/role-a/state"};
function fixture(){
  const labels={affection:"想念与亲近",care:"情绪关怀",play:"轻松互动",repair:"关系修复",chat:"日常话题",greeting:"问候与纪念",
    life:"分享自己的生活",creation:"作品与阅读",news:"外部资讯",followup:"接回旧话题",invitation:"共同活动邀请",reminder:"约定与提醒",environment:"环境与状态变化"};
  return {settings:{},state:{},calendar:{items:[]},contact:{settings:{enabled:false,automatic_enabled:false,pause_until:"",note:"",
    quiet_enabled:false,quiet_start:"23:00",quiet_end:"07:00",quiet_timezone:"Asia/Shanghai",idle_seconds:900,interval_seconds:3600,
    event_max_age_seconds:3600,max_contacts_24h:3,
    silence_min_confidence:0.66,silence_feedback_penalty:0.2,
    weather_checkin_enabled:false,weather_checkin_time:"08:30",weather_sample_minutes:60,weather_change_enabled:false,
    dedup_weather_window_minutes:1080,official_weather_alert_enabled:false,official_alert_poll_minutes:5,official_alert_min_severity:"",
    ...Object.fromEntries(Object.keys(labels).flatMap(key=>[[key+".enabled",true],[key+".weight",1],[key+".pause_until",""]]))},
    edit_token:"contact-original",purposes:Object.fromEntries(Object.entries(labels).map(([key,label])=>[key,{label,allowed:false,reason:"proactive_disabled"}])),
    host_state:"running",effective:{allowed:false,reason:"proactive_disabled",automatic_allowed:false,automatic_reason:"contact_automatic_disabled",
      model_registered:true,readonly_fields:[]}}};
}
function harness({storage=new Map(),status=fixture(),api,refresh}={}){
  const context=vm.createContext({window:{},structuredClone,Intl,Date,crypto:{randomUUID},
    sessionStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)}});
  for(const name of ["state-maintenance.js","state-contact.js","state-editor.js"]){
    vm.runInContext(fs.readFileSync(path.join(pageRoot,name),"utf8"),context,{filename:name});
  }
  const h={posts:[],refreshes:0,failures:[],status,storage,contact:context.window.CompanionStateContact};
  h.editor=context.window.CompanionStateEditor.create({changed(){},
    api:async(method,url,body)=>{h.posts.push({method,url,body:clone(body)});return api?api(method,url,body):{operation_id:"op-synthetic"};},
    refresh:async()=>{h.refreshes++;const value=refresh?await refresh():h.status;h.editor.setStatus(value);return value;},
    failed:problem=>{h.failures.push(problem);h.editor.invalidate();}});
  h.editor.setScope(scope);h.editor.setStatus(status);
  h.click=action=>h.editor.click({target:{closest:()=>({dataset:{stateEdit:action}})}});
  h.input=(name,value)=>h.editor.input({target:{matches:()=>true,dataset:{stateField:name},
    type:typeof value==="boolean"?"checkbox":"text",checked:value,value}});
  h.submit=async()=>{h.editor.submit({target:{id:"state-edit-form"},preventDefault(){}});await settle();};
  h.markup=()=>h.editor.markup({section:"contact"});
  return h;
}

test("contact form uses backend purpose directory and writes one minimal guarded command",async()=>{
  const h=harness();assert.doesNotMatch(h.markup(),/关系共享上限/);assert.match(h.markup(),/每日额度/);h.click("contact");
  const markup=h.markup();assert.equal((markup.match(/class="state-contact-purpose"/g)||[]).length,13);
  assert.doesNotMatch(markup,/data-state-field="max_relationship_/);
  h.input("enabled",true);h.input("automatic_enabled",true);h.input("interval_seconds","7200");
  h.input("chat.enabled",false);h.input("life.weight","2.5");h.input("note","忙时少打扰，休息时可以分享见闻。");
  await h.submit();
  assert.equal(h.posts.length,1);assert.equal(h.posts[0].url,scope.path+"/command");
  assert.equal(h.posts[0].body.action,"contact.configure");assert.equal(h.posts[0].body.edit_token,"contact-original");
  assert.deepEqual(h.posts[0].body.changes,{enabled:true,automatic_enabled:true,interval_seconds:7200,note:"忙时少打扰，休息时可以分享见闻。",
    "chat.enabled":false,"life.weight":2.5});assert.equal(h.refreshes,1);
});

test("contact settings separate freshness from cadence in the editor form",()=>{
  const h=harness();
  const markup=h.contact.form({values:h.status.contact.settings,
    purposes:Object.entries(h.status.contact.purposes)},value=>String(value));
  const rhythmStart=markup.indexOf('<h4 class="state-form-section">联系节奏</h4>');
  const freshnessStart=markup.indexOf('<h4 class="state-form-section">近况素材时效</h4>');
  const eventField=markup.indexOf('data-state-field="event_max_age_seconds"');
  assert.ok(rhythmStart>=0&&freshnessStart>rhythmStart&&eventField>freshnessStart);
  assert.doesNotMatch(markup.slice(rhythmStart,freshnessStart),/event_max_age_seconds/);
  assert.match(markup,/不限制主动跟进或未完话头/);
});

test("private contact status explains the most recent automatic scheduler gate",()=>{
  const status=fixture();status.contact.schedule_diagnostic={
    scheduler:{state:"running",reason_code:"contact_schedule_running",last_seen_at:"2026-10-12T10:00:00+00:00"},
    evaluation:{outcome:"skipped",stage:"settings",reason_code:"automatic_contact_disabled",purpose:null,
      observed_at:"2026-10-12T09:59:00+00:00",next_at:null}};
  const h=harness({status});const markup=h.markup();
  assert.match(markup,/最近自动调度/);assert.match(markup,/正常运行/);
  assert.match(markup,/后台自动联系已关闭/);assert.match(markup,/打开此窗口的后台自动联系开关/);
});

test("silence planning fields render as bounded numbers and save like any other preference",async()=>{
  const h=harness();h.click("contact");
  const markup=h.markup();assert.match(markup,/行为规划与沉默/);
  assert.match(markup,/data-state-field="silence_min_confidence"[^>]*min="0" max="1" step="0.01"/);
  assert.match(markup,/data-state-field="silence_feedback_penalty"[^>]*min="0" max="1" step="0.01"/);
  assert.match(h.markup(),/开口门槛 0.66 · 沉默降权 0.2/);
  assert.equal(h.contact.validField("silence_min_confidence",0),true);
  assert.equal(h.contact.validField("silence_min_confidence",1),true);
  assert.equal(h.contact.validField("silence_min_confidence",1.5),false);
  assert.equal(h.contact.validField("silence_feedback_penalty",-0.1),false);
  assert.equal(h.contact.validField("silence_feedback_penalty","0.5"),false);
  for(const value of ["1.5","-1",""]){h.input("silence_min_confidence",value);await h.submit();assert.equal(h.posts.length,0,value);}
  h.input("silence_min_confidence","0");h.input("silence_feedback_penalty","0.35");await h.submit();
  assert.deepEqual(h.posts[0].body.changes,{silence_min_confidence:0,silence_feedback_penalty:0.35});
});

test("invalid frequency, weight, timezone, quiet time, and prompt never dispatch",async()=>{
  const h=harness();h.click("contact");
  const invalid=[["idle_seconds","-1","900"],["interval_seconds","59","3600"],["max_contacts_24h","101","3"],
    ["event_max_age_seconds","86401","3600"],
    ["life.weight","0","1"],["life.weight","0.0000001","1"],["life.weight","","1"],
    ["quiet_timezone","Not/AZone","Asia/Shanghai"],["quiet_start","24:00","23:00"],["quiet_end","7:00","07:00"],
    ["pause_until","not-a-date",""],["note","文".repeat(8193),""]];
  for(const [name,value,restore] of invalid){h.input(name,value);await h.submit();assert.equal(h.posts.length,0,name);h.input(name,restore);}
  h.input("max_contacts_24h","0");h.input("note","🌙".repeat(8192));await h.submit();
  assert.equal(h.posts[0].body.changes.max_contacts_24h,0);assert.equal([...h.posts[0].body.changes.note].length,8192);
  assert.equal(h.contact.validField("constructor","bad"),false);
  assert.equal(h.contact.validField("max_relationship_contacts_24h",100),false);
});

test("pause input is explicitly normalized and unchanged parent pauses are not rewritten",async()=>{
  const status=fixture();status.contact.settings.pause_until="2026-10-20T11:12:13+08:00";
  const h=harness({status});h.click("contact");h.input("enabled",true);await h.submit();
  assert.deepEqual(h.posts[0].body.changes,{enabled:true});
  h.click("contact");h.input("pause_until","");h.input("care.pause_until","2026-10-21T10:20:30");await h.submit();
  assert.deepEqual(h.posts[1].body.changes,{pause_until:"","care.pause_until":new Date("2026-10-21T10:20:30").toISOString()});
});

test("backend field absence disables editing and leaves state controls independent",async()=>{
  const status=fixture();delete status.contact.settings.interval_seconds;
  const h=harness({status});assert.match(h.markup(),/当前宿主尚未提供完整的联系设置/);
  assert.match(h.markup(),/data-state-edit="contact" disabled/);h.click("contact");await h.submit();assert.equal(h.posts.length,0);
  h.editor.setStatus({...status,contact:undefined});assert.match(h.markup(),/当前宿主尚未提供完整的联系设置/);
});

test("contact labels, notes, and backend diagnostic codes are escaped",()=>{
  const status=fixture(),unsafe='<img src=x onerror="window.injected=true">';
  status.contact.purposes.life.label=unsafe;status.contact.purposes.life.reason=unsafe;
  status.contact.settings.note='</textarea>'+unsafe;
  const h=harness({status});assert.doesNotMatch(h.markup(),/<img/);h.click("contact");
  assert.match(h.markup(),/&lt;img/);assert.match(h.markup(),/&lt;\/textarea&gt;/);assert.doesNotMatch(h.markup(),/<img/);
});

test("contact conflicts rebase the contact token and preserve unrelated setting changes",async()=>{
  let conflict=true;const h=harness({api:async()=>{if(conflict)throw {confirmed:true,code:"configuration_revision_conflict"};return {operation_id:"op-current"};}});
  h.click("contact");h.input("max_contacts_24h","5");await h.submit();assert.match(h.markup(),/配置已被更新/);
  h.status.contact.edit_token="contact-current";h.status.contact.settings["care.weight"]=3;
  h.click("rebase");await settle();assert.match(h.markup(),/value="5"/);
  conflict=false;await h.submit();assert.deepEqual(h.posts[1].body.changes,{max_contacts_24h:5});
  assert.equal(h.posts[1].body.edit_token,"contact-current");
});

test("lost contact receipt persists across reload and stays visible from the state view",async()=>{
  const h=harness({api:async()=>{throw new Error("synthetic timeout");}});h.click("contact");h.input("enabled",true);await h.submit();
  assert.match(h.markup(),/有一笔保存尚待核对/);assert.match(h.editor.markup(),/联系安排请求待核对/);
  const original=clone(h.posts[0]);h.editor.destroy();const fresh=harness({storage:h.storage});
  assert.equal(fresh.posts.length,0);fresh.click("recover");await settle();
  assert.deepEqual(fresh.posts[0],original);assert.equal(fresh.storage.size,0);assert.equal(fresh.refreshes,1);
});

test("a pending state command remains reviewable from contact settings",async()=>{
  const status=fixture();Object.assign(status.settings,{typing_enabled:true,typing_refresh_seconds:4,presence_enabled:false});
  status.edit_token="state-token";const h=harness({status,api:async()=>{throw new Error("synthetic timeout");}});
  h.click("settings");h.input("typing_enabled",false);await h.submit();
  assert.match(h.markup(),/原设置请求待核对/);assert.match(h.markup(),/用原请求核对/);
});

test("switching role during save ignores the old result and permission loss clears contact data",async()=>{
  let release;const h=harness({api:()=>new Promise(resolve=>{release=resolve;})});
  h.click("contact");h.input("enabled",true);await h.submit();
  h.editor.setScope({...scope,path:"host/targets/second/roles/role-b/state"});h.editor.setStatus(fixture());
  release({operation_id:"old-role"});await settle();assert.equal(h.refreshes,0);assert.doesNotMatch(h.markup(),/已保存|有一笔保存尚待核对/);
  const revoked=harness({api:async()=>{throw {confirmed:true,code:"authorization_denied"};}});
  revoked.click("contact");revoked.input("enabled",true);await revoked.submit();
  assert.equal(revoked.failures[0].code,"authorization_denied");assert.equal(revoked.markup(),"");assert.equal(revoked.storage.size,0);
});

test("the only public page loads contact before its editor and routes preferences through the shared scope",()=>{
  const html=fs.readFileSync(path.join(pageRoot,"index.html"),"utf8");
  assert.ok(html.indexOf('src="state-contact.js')<html.indexOf('src="state-editor.js'));
  /* 这一段原先断言 `function renderPreferences(){...data-state-section="contact"}`。
     那个函数早就不存在了（app.js 里只剩一句注释说明它当年从未定义过、
     整页因此崩过），断言于是长期空转。改验当前真实的载入与挂载：
       · contact 页有自己的整页模块，且**先于**用它的 app.js 载入；
       · 它的样式与脚本都带缓存串，改完必须两处一起动；
       · app.js 里确实按 manageTab==='contact' 挂到 #contactWorkspace。 */
  assert.ok(html.indexOf('src="contact-page.js')>0,"contact 页要有自己的模块");
  assert.ok(html.indexOf('src="contact-page.js')<html.indexOf('src="app.js'),
    "页面模块必须先于 app.js 载入，否则第一帧挂载时 window.CompanionContactPage 还是空的");
  assert.match(html,/contact-page\.css\?v=[\w.-]+/,"样式要带缓存串");
  assert.match(html,/contact-page\.js\?v=[\w.-]+/,"脚本要带缓存串");
  const shell=fs.readFileSync(path.join(pageRoot,"app.js"),"utf8");
  assert.match(shell,/function renderContactPage\(\)\{return `<section id="contactWorkspace"/);
  /* 挂载已经改成「容器探测」式：外壳重排后左栏走 section 面板，
     不再经过 manageTab==='contact' 那个分支。断言要验当前的写法——
     容器在就挂、不在就卸，两条路都要有。 */
  assert.match(shell,/\$\('#contactWorkspace'\)[\s\S]{0,120}CompanionContactPage\?\.mount/,
    "容器在就挂上联系页");
  assert.match(shell,/contactHost\s*\?\s*window\.CompanionContactPage\?\.mount\(contactHost\)\s*:\s*window\.CompanionContactPage\?\.unmount\(\)/,
    "容器不在就要卸载，否则 80ms 涟漪链会继续往已丢弃的节点上写");
  /* 只否掉**调用**，不否掉注释：app.js 里有一段注释专门说明这个函数当年
     从未定义、整页因此崩过，那段历史要留着。 */
  assert.doesNotMatch(shell,/[^\/\s]renderPreferences\(\)/,"已删除的函数不该再被调用");
  assert.doesNotMatch(shell,/在 AstrBot 插件配置中调整主动联系与调度设置/);
  const state=fs.readFileSync(path.join(pageRoot,"state-page.js"),"utf8");
  assert.match(state,/window\.CompanionProduct\?\.selection\(\)/);assert.match(state,/editor\?\.markup\(\{section:"contact"\}\)/);
});

test("weather controls render in three groups and save like any other preference",async()=>{
  const h=harness();h.click("contact");
  const markup=h.markup();
  for(const name of ["weather_checkin_enabled","weather_checkin_time","weather_sample_minutes","weather_change_enabled",
    "dedup_weather_window_minutes","official_weather_alert_enabled","official_alert_poll_minutes","official_alert_min_severity"]){
    assert.match(markup,new RegExp(`data-state-field="${name}"`),name);
  }
  /* 数值字段带着自己的界，浏览器与校验用同一套范围。 */
  assert.match(markup,/data-state-field="weather_sample_minutes"[^>]*min="10" max="1440"/);
  assert.match(markup,/data-state-field="official_alert_poll_minutes"[^>]*min="1" max="1440"/);
  assert.match(markup,/data-state-field="dedup_weather_window_minutes"[^>]*min="0" max="2880"/);
  assert.match(markup,/data-state-field="weather_checkin_time"[^>]*step="60"/);
  h.input("weather_checkin_enabled",true);h.input("weather_checkin_time","07:15");
  h.input("weather_sample_minutes","30");h.input("weather_change_enabled",true);
  h.input("dedup_weather_window_minutes","360");h.input("official_weather_alert_enabled",true);
  h.input("official_alert_poll_minutes","15");h.input("official_alert_min_severity","severe");
  await h.submit();
  assert.equal(h.posts.length,1);
  assert.deepEqual(h.posts[0].body.changes,{weather_checkin_enabled:true,weather_checkin_time:"07:15",
    weather_sample_minutes:30,weather_change_enabled:true,dedup_weather_window_minutes:360,
    official_weather_alert_enabled:true,official_alert_poll_minutes:15,official_alert_min_severity:"severe"});
});

test("the severity control offers no filter as a real choice and refuses anything else",async()=>{
  const h=harness();h.click("contact");
  /* 空值就是「全部转发」，是正当选择而不是未填——它必须在选项里，
     并且不能被 required 挡住。markup 只是字符串，浏览器不会替我们拦，
     所以这里直接断言该 select 上没有 required。 */
  const select=h.markup().match(/<select[^>]*data-state-field="official_alert_min_severity"[^>]*>/);
  assert.ok(select,"severity 控件应当渲染为 select");
  assert.doesNotMatch(select[0],/required/,"「不限制」是合法取值，select 不能标 required");
  assert.match(h.markup(),/<option value="" selected>不限制（全部转发）<\/option>/);
  for(const value of ["","minor","moderate","severe","extreme"])assert.equal(h.contact.validField("official_alert_min_severity",value),true,value);
  /* unknown 是响应里可能出现的值，不是可以选的门槛。 */
  for(const value of ["unknown","blue","高","severe "])assert.equal(h.contact.validField("official_alert_min_severity",value),false,value);
  h.input("official_alert_min_severity","unknown");await h.submit();
  assert.equal(h.posts.length,0);
});

test("weather numbers are validated before dispatch instead of being sent and rejected",async()=>{
  const h=harness();h.click("contact");
  const invalid=[["weather_sample_minutes","9","60"],["weather_sample_minutes","1441","60"],
    ["official_alert_poll_minutes","0","5"],["official_alert_poll_minutes","1441","5"],
    ["dedup_weather_window_minutes","-1","1080"],["dedup_weather_window_minutes","2881","1080"],
    ["weather_checkin_time","24:00","08:30"],["weather_checkin_time","8:30","08:30"]];
  for(const [name,value,restore] of invalid){
    h.input(name,value);await h.submit();assert.equal(h.posts.length,0,`${name}=${value}`);h.input(name,restore);
  }
  assert.equal(h.contact.validField("weather_sample_minutes",10),true);
  assert.equal(h.contact.validField("weather_sample_minutes",9.5),false);
  assert.equal(h.contact.validField("dedup_weather_window_minutes",0),true);
});

test("weather switches are off until the operator turns them on",()=>{
  const h=harness();
  assert.equal(h.contact.validField("weather_checkin_enabled",false),true);
  assert.equal(h.contact.validField("official_weather_alert_enabled",false),true);
  /* 布尔字段不接受字符串，避免 "false" 被当成真值传到后端。 */
  assert.equal(h.contact.validField("weather_change_enabled","false"),false);
});
