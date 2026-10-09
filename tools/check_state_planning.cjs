/* Automatic planning settings use the existing state command contract, without a live host. */
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
function fixture(){return {
  settings:{enabled:true,maintenance_minutes:30,calendar_enabled:true,hunger_enabled:true,health_enabled:true,
    schedule_simulation_mode:"orchestrated",
    cycle_enabled:false,cycle_mode:"basic",cycle_timezone:"Asia/Shanghai",cycle_initialization:"natural",
    cycle_variation_enabled:false,cycle_discomfort_enabled:false,cycle_menstrual_days:5,cycle_follicular_days:7,
    cycle_pre_ovulation_days:2,cycle_ovulation_days:2,cycle_luteal_days:9,cycle_pms_days:3,cycle_expression_prompt:"",
    typing_enabled:true,typing_refresh_seconds:4,presence_enabled:true,
    planning_enabled:false,planning_timezone:"Asia/Shanghai",planning_horizon_days:90,
    planning_refine_minutes:15,planning_max_items:12,planning_prompt:"",planning_annual_calendars:"",
    planning_weather_enabled:false,planning_weather_max_age_minutes:120,
    planning_weather_location:'{"name":"杭州"}'},
  edit_token:"edit-original",state:{state:"active",revision:1,view_token:"view-original"},calendar:{items:[]},
  planning:{enabled:false,calendar_enabled:true,running:false,last_result:null,next_check:null}
};}
function harness({storage=new Map(),status=fixture(),api,refresh}={}){
  const context=vm.createContext({window:{},structuredClone,Intl,Date,TextEncoder,crypto:{randomUUID},
    sessionStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)}});
  for(const name of ["state-maintenance.js","state-editor.js"]){
    vm.runInContext(fs.readFileSync(path.join(pageRoot,name),"utf8"),context,{filename:name});
  }
  const h={posts:[],refreshes:0,failures:[],changes:0,status,storage,maintenance:context.window.CompanionStateMaintenance};
  h.editor=context.window.CompanionStateEditor.create({changed(){h.changes++;},
    api:async(method,url,body)=>{h.posts.push({method,url,body:clone(body)});return api?api(method,url,body):{operation_id:"op-synthetic"};},
    refresh:async()=>{h.refreshes++;const value=refresh?await refresh():h.status;h.editor.setStatus(value);return value;},
    failed:problem=>h.failures.push(problem)});
  h.editor.setScope(scope);h.editor.setStatus(status);
  h.click=action=>h.editor.click({target:{closest:()=>({dataset:{stateEdit:action}})}});
  h.input=(name,value)=>h.editor.input({target:{matches:()=>true,dataset:{stateField:name},
    type:typeof value==="boolean"?"checkbox":"text",checked:value,value}});
  h.submit=async()=>{h.editor.submit({target:{id:"state-edit-form"},preventDefault(){}});await settle();};
  return h;
}

test("planning edits save only changed fields through the existing guarded command",async()=>{
  const h=harness();h.click("planning");
  assert.match(h.editor.markup(),/data-state-form-kind="planning"/);
  const beforeModeChange=h.changes;
  h.input("schedule_simulation_mode","continuous");
  assert.equal(h.changes,beforeModeChange+1);
  assert.match(h.editor.markup(),/state-planning-mode-option is-selected" for="state-config-schedule-mode-continuous"/);
  assert.doesNotMatch(h.editor.markup(),/state-planning-mode-option is-selected" for="state-config-schedule-mode-orchestrated"/);
  h.input("planning_enabled",true);h.input("planning_timezone"," Europe/London ");
  h.input("planning_horizon_days","120");h.input("planning_refine_minutes","30");
  h.input("planning_max_items","8");h.input("planning_weather_enabled",true);
  h.input("planning_weather_max_age_minutes","45");
  h.input("planning_annual_calendars",JSON.stringify([{schema:"companion.annual-calendar.v1",year:2026,
    holidays:[],makeup_workdays:[],solar_terms:[]}]))
  h.input("planning_prompt","周末留出空闲时间。");
  await h.submit();
  assert.equal(h.posts.length,1);assert.equal(h.posts[0].url,scope.path+"/command");
  assert.deepEqual(h.posts[0].body.changes,{schedule_simulation_mode:"continuous",planning_enabled:true,planning_timezone:"Europe/London",planning_horizon_days:120,
    planning_refine_minutes:30,planning_max_items:8,planning_weather_enabled:true,planning_weather_max_age_minutes:45,
    planning_annual_calendars:JSON.stringify([{schema:"companion.annual-calendar.v1",year:2026,
      holidays:[],makeup_workdays:[],solar_terms:[]}]),planning_prompt:"周末留出空闲时间。"});
  assert.equal(h.posts[0].body.action,"configure");assert.equal(h.posts[0].body.edit_token,"edit-original");
  assert.equal(typeof h.posts[0].body.operation_key,"string");assert.equal(h.refreshes,1);
  assert.doesNotMatch(h.editor.markup(),/state-edit-form/);
});

test("invalid settings never issue a command; Unicode prompt and markup remain intact",async()=>{
  const h=harness();h.click("planning");
  const invalid=[
    ["planning_timezone","Invalid/Zone","Asia/Shanghai"],
    ["planning_horizon_days","367","90"],["planning_horizon_days","1.5","90"],
    ["planning_refine_minutes","0","15"],["planning_refine_minutes","1441","15"],
    ["planning_max_items","33","12"],["planning_weather_max_age_minutes","4","120"],
    ["planning_annual_calendars","not-json",""],["planning_prompt","长".repeat(4097),""]
  ];
  for(const [name,value,restore] of invalid){h.input(name,value);await h.submit();assert.equal(h.posts.length,0);h.input(name,restore);}
  h.input("planning_prompt","🌙".repeat(4096));await h.submit();
  assert.equal(h.posts[0].body.changes.planning_prompt,[..."🌙".repeat(4096)].join(""));
  const unsafe='保留原文 </textarea><img src=x onerror="window.injected=true">';
  h.status.settings.planning_prompt=unsafe;h.editor.setStatus(h.status);h.click("planning");
  assert.match(h.editor.markup(),/&lt;\/textarea&gt;&lt;img/);assert.doesNotMatch(h.editor.markup(),/<img/);
});

test("role-wide calendar switch and automatic planning save together",async()=>{
  const status=fixture();status.settings.calendar_enabled=false;status.planning.calendar_enabled=false;
  const h=harness({status});h.click("planning");
  assert.match(h.editor.markup(),/data-state-form-kind="planning"/);
  assert.match(h.editor.markup(),/对同一角色的所有私聊生效/);
  h.input("calendar_enabled",true);h.input("planning_enabled",true);await h.submit();
  assert.deepEqual(h.posts[0].body.changes,{calendar_enabled:true,planning_enabled:true});
  status.settings.planning_enabled=true;status.planning.enabled=true;h.editor.setStatus(status);
  assert.match(h.maintenance.planningSummary(status,value=>String(value)),/角色日程已关闭/);
  assert.doesNotMatch(h.editor.markup(),/data-state-edit="(?:run|generate|plan-now)"/);
  assert.equal(h.posts.length,1);
});

test("calendar does not have a separate window-scoped settings form",()=>{
  const status=fixture();status.settings.calendar_enabled=false;status.planning.calendar_enabled=false;
  status.settings.planning_enabled=true;status.planning.enabled=true;
  const h=harness({status});
  const summary=h.maintenance.planningSummary(status,value=>String(value));
  assert.doesNotMatch(summary,/data-state-edit="calendar"/);
  h.click("planning");
  assert.match(h.editor.markup(),/data-state-form-kind="planning"/);
  assert.match(h.editor.markup(),/启用角色日程/);
  assert.doesNotMatch(h.editor.markup(),/当前窗口权限|按窗口单独授权/);
});

test("weather cannot be enabled before the shared role location is configured",async()=>{
  const h=harness();h.status.settings.planning_weather_location="";h.editor.setStatus(h.status);
  h.click("planning");h.input("planning_weather_enabled",true);await h.submit();
  assert.equal(h.posts.length,0);
  assert.match(h.editor.markup(),/请先在本页填写角色天气地点，再启用天气感知/);
});

test("legacy or incomplete fields disable planning without filling defaults",async()=>{
  const status=fixture();delete status.planning;delete status.settings.planning_max_items;
  const h=harness({status});
  assert.match(h.editor.markup(),/当前宿主尚未提供完整的自动规划设置/);
  assert.match(h.editor.markup(),/data-state-edit="planning" disabled/);
  h.click("planning");await h.submit();
  assert.doesNotMatch(h.editor.markup(),/data-state-form-kind="planning"/);assert.equal(h.posts.length,0);
  h.click("maintenance");assert.match(h.editor.markup(),/data-state-form-kind="maintenance"/);
});

test("missing runtime diagnostics show uncertainty and future statuses remain readable",()=>{
  const status=fixture();status.settings.planning_enabled=true;delete status.planning;
  const h=harness({status});assert.match(h.editor.markup(),/运行状态尚未提供/);
  status.planning={enabled:true,calendar_enabled:true,running:true,last_result:null,next_check:null};
  h.editor.setStatus(status);assert.match(h.editor.markup(),/正在规划/);
  status.planning={enabled:true,calendar_enabled:true,running:false,next_check:"2026-09-25T10:30:00Z",
    last_result:{state:"succeeded",mode:"horizon",saved:3,rejected:1}};
  h.editor.setStatus(status);assert.match(h.editor.markup(),/长期节点 · 已完成 · 保存 3 项 · 未采用 1 项/);
  status.planning.last_result={state:"interrupted",mode:"refine"};
  h.editor.setStatus(status);assert.match(h.editor.markup(),/临近细化 · 已中断/);
  status.planning={enabled:true,calendar_enabled:true,running:false,next_check:"not-an-iso-date",
    last_result:{state:"future-state",mode:"future-mode",code:'<script>alert(1)</script>',task_id:'task-"<img>'}};
  h.editor.setStatus(status);const markup=h.editor.markup();
  assert.match(markup,/已有处理记录/);assert.match(markup,/检查时间暂不可用/);
  assert.match(markup,/data-receipt="planning:task-&quot;&lt;img&gt;"/);
  assert.match(markup,/本次规划未完成/);assert.doesNotMatch(markup,/<script>|<img>/);
});

test("configuration conflicts preserve edits and rebase untouched planning preferences",async()=>{
  let denied=true;
  const h=harness({api:async()=>{if(denied)throw {confirmed:true,code:"configuration_revision_conflict"};return {operation_id:"op-synthetic"};}});
  h.click("planning");h.input("planning_refine_minutes","45");await h.submit();
  assert.match(h.editor.markup(),/配置已被更新/);assert.match(h.editor.markup(),/value="45"/);
  h.status.settings.planning_max_items=7;h.status.edit_token="edit-current";
  h.click("rebase");await settle();
  assert.match(h.editor.markup(),/value="7"/);assert.match(h.editor.markup(),/value="45"/);
  denied=false;await h.submit();
  assert.deepEqual(h.posts[1].body.changes,{planning_refine_minutes:45});assert.equal(h.posts[1].body.edit_token,"edit-current");
});

test("uncertain planning writes survive reload and recover with the exact original request",async()=>{
  const h=harness({api:async()=>{throw new Error("synthetic lost receipt");}});
  h.click("planning");h.input("planning_prompt","留出散步时间。");await h.submit();
  const sent=clone(h.posts[0]);assert.match(h.editor.markup(),/有一笔保存尚待核对/);
  h.editor.destroy();
  const restored=harness({storage:h.storage});
  assert.equal(restored.posts.length,0);assert.match(restored.editor.markup(),/state-planning-panel[\s\S]*有一笔保存尚待核对/);
  restored.click("recover");await settle();
  assert.deepEqual(restored.posts[0],sent);assert.equal(restored.refreshes,1);
  assert.equal(restored.storage.size,0);
});

test("switching roles while a planning save is in flight never reuses its result in the new role",async()=>{
  let release;
  const h=harness({api:()=>new Promise(resolve=>{release=resolve;})});
  h.click("planning");h.input("planning_enabled",true);await h.submit();
  h.editor.setScope({...scope,path:"host/targets/first/roles/role-b/state"});h.editor.setStatus(fixture());
  release({operation_id:"op-original-role"});await settle();
  assert.equal(h.posts[0].url,scope.path+"/command");assert.equal(h.refreshes,0);
  assert.doesNotMatch(h.editor.markup(),/已保存|有一笔保存尚待核对/);
});

test("confirmed permission loss closes the planning editor and clears its pending request",async()=>{
  const h=harness({api:async()=>{throw {confirmed:true,code:"authorization_denied"};}});
  h.click("planning");h.input("planning_enabled",true);await h.submit();
  assert.equal(h.failures[0].code,"authorization_denied");assert.equal(h.storage.size,0);
  assert.doesNotMatch(h.editor.markup(),/data-state-form-kind="planning"/);
  h.editor.invalidate();assert.equal(h.editor.markup(),"");
});
