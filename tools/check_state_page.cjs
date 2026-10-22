/* Role-state page acceptance with synthetic host data and command receipts. */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const http = require("node:http");
const path = require("node:path");

async function run({browser, outputDir, bridgeMode="direct", pageRoot=path.resolve(__dirname,"../pages/陪伴小屋"), inspect=null}) {
  const root=path.resolve(pageRoot);
  await fs.mkdir(outputDir,{recursive:true});
  const host="astrbot_plugin_private_companion";
  const first=`host/targets/first/roles/role-a/state`;
  const secondRole=`host/targets/first/roles/role-b/state`;
  const secondTarget=`host/targets/second/roles/role-a/state`;
  const full=value=>`/${host}/${value}`;
  const recordedAt="2026-09-25T01:00:00Z", requestId="presence-"+"a".repeat(64);
  const phasePreferences=Object.fromEntries([["menstrual",-12,"疲惫"],["follicular",0,"轻快"],["pre_ovulation",8,"期待"],
    ["ovulation",9,"明朗"],["luteal",5,"平稳"],["pms",-8,"敏感"]].flatMap(([phase,energy,mood])=>[
      [`cycle_${phase}_energy`,energy],[`cycle_${phase}_mood`,mood],[`cycle_${phase}_prompt`,""]]));
  const fixture=(hunger,phase,presentation={"synthetic-account":{state:"accepted",recorded_at:recordedAt,
      operation_id:requestId,desired:{wording:"阅读中",basis:"calendar_plan"}},
      "typing:synthetic-route":{state:"unknown",recorded_at:recordedAt,code:"presence_ack_unknown",batch_id:"batch-synthetic"}})=>({
    settings:{enabled:true,maintenance_minutes:30,energy_enabled:true,sleep_enabled:true,busy_enabled:true,location_enabled:true,
      ...Object.fromEntries(["health","hunger","sleep","cycle","busy"].map(key=>["home_only_special_"+key,false])),
      humanized_state_intensity:50,energy_expression_prompt:"",calendar_enabled:true,hunger_enabled:true,
      hunger_expression_prompt:"",health_enabled:true,health_expression_prompt:"",cycle_enabled:true,
      schedule_simulation_mode:"orchestrated",planning_enabled:true,planning_timezone:"Asia/Shanghai",planning_horizon_days:30,planning_refine_minutes:120,planning_max_items:5,planning_prompt:"",
      planning_annual_calendars:"",planning_weather_enabled:false,planning_weather_location:"",planning_weather_max_age_minutes:120,
      mood_enabled:true,mood_update_probability:0.5,mood_update_max_delta:2,mood_decay_half_life_minutes:60,
      daily_state_patrol_enabled:true,daily_state_patrol_time:"04:00",daily_state_patrol_retention_days:30,
      ...Object.fromEntries(["energy","health","hunger","sleep","cycle","mood","busy","location"].map(key=>["home_show_"+key,true])),
      cycle_mode:"basic",cycle_timezone:"Asia/Shanghai",cycle_initialization:"natural",cycle_variation_enabled:false,cycle_discomfort_enabled:false,
      cycle_menstrual_days:5,cycle_follicular_days:7,cycle_pre_ovulation_days:2,cycle_ovulation_days:2,cycle_luteal_days:9,cycle_pms_days:3,
      cycle_expression_prompt:"",cycle_link_intensity:false,cycle_discomfort_chance:55,cycle_discomfort_types:"痛经,头痛,腰酸,乏力",
      ...phasePreferences,typing_enabled:true,presence_enabled:true,typing_refresh_seconds:4},
    effective:{typing_enabled:{allowed:true,reason:null},presence_enabled:{allowed:true,reason:null},calendar_enabled:{allowed:true,reason:null}},
    presentation_diagnostics:{observed_at:"2026-09-25T01:05:00Z",port:presentation.state==="preview"?"preview":"installed",
      typing:presentation.state==="preview"?{state:"unavailable",reason:"presence_port_missing",refresh_seconds:4}
        :{state:"suppressed",reason:"typing_batch_suppressed",refresh_seconds:4},
      custom_status:presentation.state==="preview"?{state:"unavailable",reason:"presence_port_missing"}
        :{state:"recorded",reason:null,desired:{wording:"阅读中",basis:"calendar_plan"}}},
    state:{state:"active",revision:7,view_token:"state-view-original",values:{energy:72,hunger,health:"状态稳定",sleep:"有一点困",mood:"平静",busy:null,
      cycle:"小腹有些不适",conditions:[{kind:"cycle",text:"轻微腹痛",expires_at:"2026-09-24T14:00:00+08:00"}]},
      cycle_timeline:{applicability:"applicable",phase,phase_day:2,phase_days:5,cycle_day:2,cycle_days:28}},
    sleep_schedule:{shared:true,enabled:true,time:"00:30",timezone:"Asia/Shanghai",variation_minutes:20,duration_minutes:480,
      executor_state:"available",executor_is_current:true,
      executor_window:{label:"qq · 账号 10001 · 会话 20002"},next_sleep_at:"2026-09-24T16:30:00Z",
      next_wake_at:"2026-09-25T00:30:00Z"},
    body_sleep:{state:"sleeping",planned_wake_at:"2026-09-24T11:00:00Z"},
    maintenance:{enabled:true,next_at:"2026-09-24T02:00:00Z"},presentation,host_state:"running"});
  const values={[first]:fixture('有点饿 <script>window.injected=true</script>',"menstrual"),
    [secondRole]:fixture("不太饿","luteal"),[secondTarget]:fixture("饿了","ovulation",{state:"preview"})};
  values[first].maintenance.result={state:"failed",code:"model_budget_exhausted"};
  values[secondRole].presentation_diagnostics.custom_status={state:"blocked",reason:"multiple_presence_owners"};
  values[secondRole].presentation={"synthetic-account":{state:"not_started",code:'<img src=x onerror="window.injected=true">',
    operation_id:'<script>window.injected=true</script>',desired:{wording:"<b>散步</b>",basis:"calendar_plan"}}};
  const plan=(id,title)=>({id,title,kind:"role_plan",state:"accepted",revision:1,view_token:"view-"+id,
    presence:"阅读中",detail:"私人日程内容",schedule:{anchor:"2026-09-25T02:00:00.000Z",timezone_name:"Asia/Shanghai",frequency:"weekly",interval:1,count:4,fold:0,gap_policy:"reject"},duration_minutes:30,
    exceptions:{"1":null},sources:[{source_id:"original"}],reminder_id:"reminder-original"});
  for(const [key,value] of Object.entries(values)){
    value.edit_token="edit-"+key;value.create_token="create-"+key;value.cycle_settings_token="cycle-settings-"+key;value.calendar={items:[plan("plan-a","周末阅读 <script>window.injected=true</script>")],next_cursor:"plan-a",skipped:0};
  }
  const pages={[first]:{"plan-a":{items:[plan("plan-b","晚间散步")],next_cursor:null,skipped:0}}};
  const catalog={installation_id:"synthetic-installation",operator_id:"dashboard:qa",mode:"multi",targets:[
    {target_id:"first",scope_kind:"private",participant_id:"200",platform_id:"qq-main",account_id:"100",bot_id:"bot-a",
      roles:[{role_id:"澄汐",state_api:full(first),reply_api:full(first.replace(/\/state$/,"/reply"))},{role_id:"望舒",state_api:full(secondRole),reply_api:full(secondRole.replace(/\/state$/,"/reply"))}]},
    {target_id:"second",scope_kind:"private",participant_id:"200",platform_id:"qq-second",account_id:"101",bot_id:"bot-b",
      roles:[{role_id:"澄汐",state_api:full(secondTarget),reply_api:full(secondTarget.replace(/\/state$/,"/reply"))}]},
    {target_id:"group",scope_kind:"group",group_id:"300",platform_id:"qq-main",account_id:"100",bot_id:"bot-a",
      roles:[{role_id:"澄汐",state_api:null}]}]};
  for(const target of catalog.targets)for(const role of target.roles)if(role.state_api)role.perception_native_api=role.state_api.slice(0,-6)+"/perception-native";
  const bridge=`window.AstrBotPluginPage={ready:async()=>({pluginName:${JSON.stringify(host)}}),apiGet:async (endpoint,query)=>{
    window.stateQA.calls.push(endpoint);
    if(window.stateQA.deny)return {status:"error",data:{code:"core_access_required"}};
    if(endpoint==="page/targets")return {status:"ok",data:window.stateQA.catalog};
    if(endpoint==="host-options/weather")return {status:"ok",data:structuredClone(window.stateQA.weatherSource)};
    if(endpoint.endsWith("/perception-native")){
      const role=window.stateQA.values[endpoint.slice(0,-"/perception-native".length)+"/state"],source=window.stateQA.weatherSource;
      const newsSettings={news_share_enabled:false,"news.enabled":false,news_check_interval_minutes:60,news_source_kind:"disabled",news_source_uid:"",news_source_url:""};
      if(role)return {status:"ok",data:{environment:{settings:Object.fromEntries(["planning_timezone","planning_annual_calendars","planning_weather_enabled","planning_weather_location","planning_weather_max_age_minutes"].map(key=>[key,role.settings[key]])),sources:{weather_ready:true,weather_provider:source.actual_provider,alerts_ready:source.alerts_ready}},model:{settings:{calendar_enabled:true,calendar_timezone:"Asia/Shanghai",holiday_enabled:true,holiday_country:"CN",lunar_enabled:true,automatic_solar_terms_enabled:true,almanac_enabled:false,platform_enabled:true,model_route_enabled:true,configured_modalities_enabled:true,guidance:""},edit_token:"synthetic-model"},news:{settings:newsSettings,edit_token:"synthetic-news",source:{ready:false,assembled:false,kind:"disabled",label:""},contact_enabled:false,automatic_enabled:false},contact:{settings:newsSettings,effective:{automatic_allowed:false}}}};
    }
    const key=endpoint;
    if(window.stateQA.values[key])window.stateQA.loadCount++;
    if(window.stateQA.failReadNext&&window.stateQA.values[key]){window.stateQA.failReadNext=false;throw Object.assign(new Error("synthetic read timeout"),{code:"bridge_timeout"});}
    if(!window.stateQA.values[key])return {status:"error",data:{code:"invalid_response"}};
    const value=structuredClone(window.stateQA.values[key]);
    if(query?.after_id&&window.stateQA.pages[key]?.[query.after_id])value.calendar=structuredClone(window.stateQA.pages[key][query.after_id]);
    return {status:"ok",data:value};
  },apiPost:async(endpoint,body)=>{
    const qa=window.stateQA,request=structuredClone(body),key=endpoint.replace(/\\/command$/,""),value=qa.values[key];
    qa.posts.push({endpoint,body:request});
    if(endpoint==="host-options/weather"){
      if(request.edit_token!==qa.weatherSource.edit_token)return {status:"error",data:{code:"host_options_conflict"}};
      const next=qa.weatherSource,changes={...request.changes};
      if(changes.credential){next.has_credential=true;next.credential_source="plugin";next.credential_kind=changes.credential.includes(".")?"jwt":"api_key";delete changes.credential;}
      if(changes.clear_credentials){next.has_credential=false;next.credential_source="none";next.credential_kind="none";next.settings.api_host="";delete changes.clear_credentials;if(next.settings.provider==="qweather")next.settings.provider="auto";}
      if(typeof changes.api_host==="string"){if(changes.api_host.startsWith("https://"))changes.api_host=changes.api_host.slice(8);if(changes.api_host.endsWith("/"))changes.api_host=changes.api_host.slice(0,-1);}
      Object.assign(next.settings,changes);next.actual_provider=next.settings.provider==="open-meteo"||!next.has_credential?"open-meteo":"qweather";
      next.alerts_ready=next.has_credential;next.edit_token=(qa.posts.length%16).toString(16).repeat(64);
      if(qa.weatherDropNext){qa.weatherDropNext=false;throw new Error("synthetic weather response lost after save");}
      return {status:"ok",data:{saved:true,...structuredClone(next)}};
    }
    if(qa.holdNext){qa.holdNext=false;await new Promise(resolve=>{qa.release=resolve;});}
    if(qa.denyWrites)return {status:"error",data:{code:"core_access_required"}};
    const receiptKey=endpoint+"|"+request.operation_key;
    if(qa.receipts[receiptKey]){
      const original=qa.receipts[receiptKey];
      if(JSON.stringify(original.request)!==JSON.stringify(request))return {status:"error",data:{code:"operation_conflict"}};
      return {status:"ok",data:{...original.result,replayed:true}};
    }
    if(!value)return {status:"error",data:{code:"invalid_response"}};
    if(request.action==="maintain"){
      if(request.expected_revision!==value.state.revision||request.view_token!==value.state.view_token)
        return {status:"error",data:{code:"record_revision_conflict"}};
      if(!value.settings.enabled)return {status:"error",data:{code:"state_not_enabled"}};
      value.state.revision++;value.state.view_token="maintained-"+request.operation_key;
      value.state.values.energy=Math.min(100,(value.state.values.energy||50)+1);
      value.maintenance.result={state:"succeeded",task_id:"state-task-"+request.operation_key};
    }else if(request.action==="configure"){
      if(request.edit_token!==value.edit_token)return {status:"error",data:{code:"configuration_revision_conflict"}};
      Object.assign(value.settings,request.changes);value.edit_token="saved-"+request.operation_key;
      value.cycle_settings_token="cycle-settings-"+request.operation_key;
      for(const option of ["typing_enabled","presence_enabled"]){value.effective[option]={allowed:value.settings[option],reason:null};}
      value.presentation_diagnostics.typing={state:value.settings.typing_enabled?"idle":"disabled",refresh_seconds:value.settings.typing_refresh_seconds};
      value.presentation_diagnostics.custom_status={state:value.settings.presence_enabled?"waiting":"disabled"};
    }else if(request.action==="cycle.align"){
      if(request.expected_revision!==value.state.revision||request.view_token!==value.state.view_token)return {status:"error",data:{code:"record_revision_conflict"}};
      if(request.settings_token!==value.cycle_settings_token)return {status:"error",data:{code:"role_cycle_settings_conflict"}};
      value.state.revision++;value.state.view_token="cycle-view-"+request.operation_key;
      value.state.cycle_timeline={applicability:request.data.applicability==="auto"?"unknown":request.data.applicability,
        ...(request.data.applicability==="applicable"?{cycle_day:request.data.day,cycle_days:28,phase:"menstrual",phase_day:request.data.day,phase_days:5}:{})};
    }else if(request.action.startsWith("calendar.")){
      const records=[...value.calendar.items,...Object.values(qa.pages[key]||{}).flatMap(page=>page.items)];
      const item=request.action==="calendar.create"?null:records.find(item=>item.id===request.id);
      if(request.action==="calendar.create"){
        if(records.some(existing=>existing.id===request.id))return {status:"error",data:{code:"calendar_exists"}};
        if(request.view_token!==value.create_token||request.expected_revision!==0)return {status:"error",data:{code:"state_view_stale"}};
        const created={...structuredClone(request.data),id:request.id,state:"accepted",revision:1,view_token:"saved-"+request.operation_key,
          exceptions:{},sources:structuredClone(request.sources||[]),accepted_by:[],changed_by:{subject_id:"dashboard:qa"},reminder_id:null};
        value.calendar.items.push(created);
      }else{
        if(!item||item.revision!==request.expected_revision||item.view_token!==request.view_token)return {status:"error",data:{code:"record_revision_conflict"}};
        if(item.state==="cancelled")return {status:"error",data:{code:"calendar_closed"}};
        const previousReminder=item.reminder_id;
        const sequence=request.action==="calendar.remind"?request.sequence:request.data?.sequence;
        if(["calendar.remind","calendar.exception"].includes(request.action)&&(!Number.isInteger(sequence)||sequence<0||
          item.schedule.frequency==="once"&&sequence>0||item.schedule.count!==null&&sequence>=item.schedule.count))
          return {status:"error",data:{code:request.action==="calendar.remind"?"calendar_reminder_past":"calendar_occurrence_missing"}};
        if(request.action==="calendar.presence")item.presence=request.data.presence;
        else if(request.action==="calendar.revise"){
          Object.assign(item,structuredClone(request.data),{sources:structuredClone(request.sources||[]),exceptions:{},reminder_id:null,state:"accepted"});
        }else if(request.action==="calendar.exception"){
          item.exceptions={...(item.exceptions||{}),[String(request.data.sequence)]:request.data.start};item.reminder_id=null;
        }else if(request.action==="calendar.remind"){
          if(Object.hasOwn(item.exceptions,String(sequence))&&item.exceptions[String(sequence)]===null)return {status:"error",data:{code:"calendar_reminder_past"}};
          item.reminder_id="reminder-"+request.operation_key;
        }else if(request.action==="calendar.cancel"){
          item.state="cancelled";item.reminder_id=null;
        }else return {status:"error",data:{code:"state_command_invalid"}};
        if(previousReminder&&request.action!=="calendar.presence")qa.cancelledReminders.push({key,id:previousReminder});
        item.revision++;item.view_token="saved-"+request.operation_key;
      }
    }else return {status:"error",data:{code:"state_command_invalid"}};
    qa.applied++;const result={operation_id:"synthetic-command-"+qa.applied,replayed:false};
    qa.receipts[receiptKey]={request,result};
    sessionStorage.setItem("state-QA-backend",JSON.stringify({values:qa.values,pages:qa.pages,posts:qa.posts,receipts:qa.receipts,applied:qa.applied,cancelledReminders:qa.cancelledReminders}));
    if(qa.dropNext){qa.dropNext=false;throw new Error("synthetic response lost after commit");}
    return {status:"ok",data:result};
  }};
  for(const method of ["apiGet","apiPost"]){const original=window.AstrBotPluginPage[method];
    window.AstrBotPluginPage[method]=async(...args)=>{const result=await original(...args);
      return ${JSON.stringify(bridgeMode)}==="direct"&&result?.status==="ok"?result.data
        :${JSON.stringify(bridgeMode)}==="nested"?{data:result}:result;};}
  `;
  const server=http.createServer(async(req,res)=>{
    const url=new URL(req.url,"http://127.0.0.1");
    if(url.pathname==="/favicon.ico") {res.writeHead(204).end();return;}
    if(url.pathname==="/bridge.js") {res.setHeader("Content-Type","text/javascript;charset=utf-8");res.end(bridge);return;}
    const relative=decodeURIComponent(url.pathname==="/"?"index.html":url.pathname.slice(1));
    const file=path.resolve(root,relative);
    if(!file.startsWith(root+path.sep)){res.writeHead(404).end();return;}
    try {
      let payload=await fs.readFile(file);
      if(relative==="index.html")payload=Buffer.from(payload.toString("utf8").replace("</body>",'<script src="/bridge.js"></script></body>'));
      res.setHeader("Content-Type",({".html":"text/html;charset=utf-8",".js":"text/javascript;charset=utf-8",".css":"text/css;charset=utf-8",
        ".woff2":"font/woff2",".jpg":"image/jpeg"}[path.extname(file)]||"application/octet-stream"));res.end(payload);
    } catch {res.writeHead(404).end();}
  });
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  const context=await browser.newContext({viewport:{width:1366,height:980},reducedMotion:"reduce"});
  await context.route("**/api/plugin/astrbot_plugin_mihome/**",route=>route.fulfill({
    status:200,contentType:"application/json",body:JSON.stringify({status:"ok",data:{enabled:false,devices:[]}})}));
  const page=await context.newPage(),errors=[];page.on("pageerror",error=>errors.push(String(error.stack||error)));
  page.on("requestfailed",request=>errors.push(`REQUEST ${request.url()}: ${request.failure()?.errorText||"failed"}`));
  page.on("console",message=>{if(message.type()==="error")errors.push(`CONSOLE ${message.text()} @ ${message.location().url}:${message.location().lineNumber}`);});
  await page.addInitScript(({catalog,values,pages})=>{
    let saved=null;try{saved=JSON.parse(sessionStorage.getItem("state-QA-backend"));}catch{}
    window.stateQA={calls:[],deny:false,loadCount:0,catalog,values,pages,posts:[],receipts:{},applied:0,cancelledReminders:[],
      weatherSource:{settings:{provider:"auto",api_host:"",refresh_minutes:5},credential_source:"none",credential_kind:"none",has_credential:false,source_state:"configured",actual_provider:"open-meteo",alerts_ready:false,edit_token:"a".repeat(64),apply_mode:"immediate"},...saved};
  },{catalog,values,pages});
  const rootPage=()=>page.locator("#roleStateWorkspace");
  const closeFeature=async()=>{
    if(await rootPage().locator("#state-edit-form").count())await rootPage().locator('[data-state-edit="cancel"]').click();
    if(await rootPage().locator("[data-state-feature-close]").count())await rootPage().locator("[data-state-feature-close]").first().click();
  };
  const loadDone=async()=>page.waitForFunction(()=>{const button=document.querySelector("#state-refresh");return !!button&&!button.disabled;},null,{timeout:8000});
  const checkWidth=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  try {
    await page.goto(`http://127.0.0.1:${server.address().port}/#life/state`);
    await rootPage().waitFor();await page.waitForFunction(()=>!!document.querySelector("#roleStateWorkspace .state-dashboard")&&!document.querySelector("#state-refresh")?.disabled);
    assert.match(await rootPage().innerText(),/模型预算不足，请查看模型与连接中的今日用量/);
    const inspectPage=inspect||require("./check_state_config.cjs").inspect;
    const result=await inspectPage({page,rootPage,closeFeature,loadDone,checkWidth,errors,root,outputDir,
      first,secondRole,secondTarget,requestId,bridgeMode});
    return {pageRoot:root,bridgeMode,...result};
  } catch(error) {
    error.message+=`\nPage errors: ${errors.join("; ")||"none"}\nPage root: ${root}`;
    throw error;
  } finally {await context.close();await new Promise(resolve=>server.close(resolve));}
}
module.exports={run};
if(require.main===module){
  (async()=>{const launchOptions={headless:true};if(process.env.PLAYWRIGHT_EXECUTABLE_PATH)launchOptions.executablePath=process.env.PLAYWRIGHT_EXECUTABLE_PATH;
    const browser=await require("playwright").chromium.launch(launchOptions);
    try{console.log(JSON.stringify(await run({browser,pageRoot:process.env.COMPANION_PAGE_ROOT,bridgeMode:process.env.COMPANION_STATE_BRIDGE_MODE||"direct",
      outputDir:await fs.mkdtemp(require("node:os").tmpdir()+"/state-page-")}),null,2));}
    finally{await browser.close();}
  })().catch(error=>{console.error(error);process.exitCode=1;});
}
