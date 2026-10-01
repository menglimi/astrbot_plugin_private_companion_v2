/* Role-state page acceptance with synthetic host data and command receipts. */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const http = require("node:http");
const path = require("node:path");

async function run({browser, outputDir, bridgeMode="direct", pageRoot=path.resolve(__dirname,"../pages/陪伴小屋")}) {
  const root=path.resolve(pageRoot);
  await fs.mkdir(outputDir,{recursive:true});
  const host="astrbot_plugin_private_companion_v2";
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
    settings:{enabled:true,maintenance_minutes:30,humanized_state_intensity:50,calendar_enabled:true,hunger_enabled:true,health_enabled:true,cycle_enabled:true,
      ...Object.fromEntries(["energy","health","hunger","sleep","cycle","busy","location"].map(key=>["home_show_"+key,true])),
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
    sleep_schedule:{shared:true,enabled:true,time:"00:30",timezone:"Asia/Shanghai",duration_minutes:480,
      executor_state:"available",executor_is_current:true,
      executor_window:{label:"qq · 账号 10001 · 会话 20002"},next_sleep_at:"2026-09-24T16:30:00Z",
      next_wake_at:"2026-09-25T00:30:00Z"},
    body_sleep:{state:"sleeping",planned_wake_at:"2026-09-24T11:00:00Z"},
    maintenance:{enabled:true,next_at:"2026-09-24T02:00:00Z"},presentation,host_state:"running"});
  const values={[first]:fixture('有点饿 <script>window.injected=true</script>',"menstrual"),
    [secondRole]:fixture("不太饿","luteal"),[secondTarget]:fixture("饿了","ovulation",{state:"preview"})};
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
      roles:[{role_id:"澄汐",state_api:full(first)},{role_id:"望舒",state_api:full(secondRole)}]},
    {target_id:"second",scope_kind:"private",participant_id:"200",platform_id:"qq-second",account_id:"101",bot_id:"bot-b",
      roles:[{role_id:"澄汐",state_api:full(secondTarget)}]},
    {target_id:"group",scope_kind:"group",group_id:"300",platform_id:"qq-main",account_id:"100",bot_id:"bot-a",
      roles:[{role_id:"澄汐",state_api:null}]}]};
  const bridge=`window.AstrBotPluginPage={ready:async()=>({pluginName:${JSON.stringify(host)}}),apiGet:async (endpoint,query)=>{
    window.stateQA.calls.push(endpoint);
    if(window.stateQA.deny)return {status:"error",data:{code:"core_access_required"}};
    if(endpoint==="page/targets")return {status:"ok",data:window.stateQA.catalog};
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
    if(qa.holdNext){qa.holdNext=false;await new Promise(resolve=>{qa.release=resolve;});}
    if(qa.denyWrites)return {status:"error",data:{code:"core_access_required"}};
    const receiptKey=endpoint+"|"+request.operation_key;
    if(qa.receipts[receiptKey]){
      const original=qa.receipts[receiptKey];
      if(JSON.stringify(original.request)!==JSON.stringify(request))return {status:"error",data:{code:"operation_conflict"}};
      return {status:"ok",data:{...original.result,replayed:true}};
    }
    if(!value)return {status:"error",data:{code:"invalid_response"}};
    if(request.action==="configure"){
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
  const page=await context.newPage(),errors=[];page.on("pageerror",error=>errors.push(String(error.stack||error)));
  page.on("requestfailed",request=>errors.push(`REQUEST ${request.url()}: ${request.failure()?.errorText||"failed"}`));
  page.on("console",message=>{if(message.type()==="error")errors.push(`CONSOLE ${message.text()} @ ${message.location().url}:${message.location().lineNumber}`);});
  await page.addInitScript(({catalog,values,pages})=>{
    let saved=null;try{saved=JSON.parse(sessionStorage.getItem("state-QA-backend"));}catch{}
    window.stateQA={calls:[],deny:false,loadCount:0,catalog,values,pages,posts:[],receipts:{},applied:0,cancelledReminders:[],...saved};
  },{catalog,values,pages});
  const rootPage=()=>page.locator("#roleStateWorkspace");
  const loadDone=async()=>page.waitForFunction(()=>{const button=document.querySelector("#state-refresh");return !!button&&!button.disabled;},null,{timeout:8000});
  const checkWidth=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  try {
    await page.goto(`http://127.0.0.1:${server.address().port}/#life/state`);
    await rootPage().waitFor();await page.waitForFunction(()=>!!document.querySelector("#roleStateWorkspace .state-dashboard")&&!document.querySelector("#state-refresh")?.disabled);
    const initialReads=await page.evaluate(()=>window.stateQA.loadCount);
    const initialState=await page.evaluate(()=>({text:document.querySelector("#roleStateWorkspace")?.innerText||"",
      points:[...document.querySelectorAll("#roleStateWorkspace .state-board-point")].map(item=>item.dataset.stateFeature)}));
    assert.match(initialState.text,/有点饿/);
    assert.match(initialState.text,/健康/);
    assert.match(initialState.text,/72 \/ 100/);
    assert.match(await rootPage().innerText(),/经期 · 第 2 \/ 5 天/);
    assert.deepEqual(initialState.points,["energy","health","hunger","sleep","cycle","busy","location"]);
    assert.equal(await rootPage().locator(".state-config-tabs,[data-state-tab]").count(),0);
    assert.equal(await rootPage().locator('[data-state-edit="home"]').isEnabled(),true);
    assert.equal(await rootPage().locator(".state-dashboard .state-eyebrow").innerText(),"澄汐");
    assert.doesNotMatch(await rootPage().innerText(),/function personaLabel|return role\(\)/);
    assert.doesNotMatch(await rootPage().innerText(),/QQ 平台展示确认|睡眠作息/);
    await checkWidth();await page.screenshot({path:path.join(outputDir,"state-desktop.png"),fullPage:true});
    await page.setViewportSize({width:390,height:844});await checkWidth();
    await page.screenshot({path:path.join(outputDir,"state-mobile.png"),fullPage:true});
    await page.setViewportSize({width:1366,height:980});await checkWidth();
    await page.emulateMedia({reducedMotion:"no-preference"});
    await rootPage().locator('[data-state-feature="energy"]').focus();await page.keyboard.press("Enter");
    assert.equal(await rootPage().locator("#state-feature-detail").evaluate(item=>getComputedStyle(item).animationName),"state-feature-enter");
    assert.equal(await rootPage().locator('[data-state-edit="intensity"]').count(),1);
    await rootPage().locator("[data-state-feature-close]").click();
    for(const [name,editorAction] of [["health","maintenance"],["hunger","maintenance"],["cycle","cycle"]]){
      await rootPage().locator(`[data-state-feature="${name}"]`).click();
      assert.equal(await rootPage().locator(`[data-state-edit="${editorAction}"]`).count(),1,name);
      await rootPage().locator("[data-state-feature-close]").click();
    }
    await rootPage().locator('[data-state-feature="location"]').click();
    assert.match(await rootPage().innerText(),/这是角色自身的位置模拟，随人格在窗口间共享/);
    assert.equal(await rootPage().locator('[data-state-edit="location"]').count(),0);
    await rootPage().locator("[data-state-feature-close]").click();
    await page.evaluate(()=>{
      window.stateQA.externalKinds=[];
      window.CompanionConfigEditors.create=(kinds,rootProvider)=>{
        window.stateQA.externalKinds.push(kinds);
        return {restore(){},paint(){const host=rootProvider();if(host)host.innerHTML='<div class="config-editors"><div data-config-host="sleep"></div></div>';},read(){},stop(){},start(){}};
      };
    });
    await rootPage().locator('[data-state-feature="sleep"]').click();
    assert.match(await rootPage().innerText(),/睡眠作息/);
    assert.match(await rootPage().innerText(),/睡眠中 · 计划醒来/);
    assert.deepEqual(await page.evaluate(()=>window.stateQA.externalKinds.at(-1)),["life"]);
    assert.equal(await rootPage().locator("#state-refresh").isDisabled(),true);
    await rootPage().locator("[data-state-feature-close]").click();
    await rootPage().locator('[data-state-feature="busy"]').click();
    assert.match(await rootPage().innerText(),/状态由日程形成；下方可调整回复顺延/);
    assert.deepEqual(await page.evaluate(()=>window.stateQA.externalKinds.at(-1)),["busy_gate"]);
    await rootPage().locator("[data-state-feature-close]").click();
    await rootPage().locator('[data-state-feature="planning"]').click();
    assert.match(await rootPage().innerText(),/角色计划与日程/);
    assert.doesNotMatch(await rootPage().innerText(),/身体与周期设置/);
    await page.evaluate(()=>document.activeElement?.blur());await page.waitForTimeout(300);
    await page.screenshot({path:path.join(outputDir,"state-workspace-schedule.png"),fullPage:true});
    await rootPage().locator("[data-state-feature-close]").click();
    await rootPage().locator('[data-state-feature="presentation"]').click();
    assert.match(await rootPage().innerText(),/QQ 平台展示确认/);
    assert.match(await rootPage().innerText(),/自定义短状态/);
    assert.match(await rootPage().innerText(),/正在输入/);
    assert.match(await rootPage().innerText(),/平台已受理/);
    assert.match(await rootPage().innerText(),/确认未知，本轮不再重试/);
    assert.match(await rootPage().innerText(),/受理确认不代表客户端当前展示状态/);
    assert.match(await rootPage().innerText(),/已开启 · 授权通过/);
    assert.match(await rootPage().innerText(),/配置刷新间隔：4 秒/);
    assert.match(await rootPage().innerText(),/本轮已停止刷新/);
    assert.match(await rootPage().innerText(),/待展示：阅读中 · 当前日程的公开文案/);
    assert.match(await rootPage().innerText(),/请求文案：阅读中/);
    assert.match(await rootPage().innerText(),/记录于/);
    await page.evaluate(()=>document.activeElement?.blur());await page.waitForTimeout(300);
    await page.screenshot({path:path.join(outputDir,"state-workspace-presentation.png"),fullPage:true});
    const historyBefore=await rootPage().locator(".state-receipts").innerText();
    await rootPage().locator(".state-receipt-reference summary").first().focus();
    await page.keyboard.press("Enter");
    assert.match(await rootPage().innerText(),new RegExp(requestId));
    assert.equal(await rootPage().locator("script").count(),0);
    assert.equal(await page.evaluate(()=>window.injected),undefined);
    assert.equal(await page.evaluate(()=>window.stateQA.loadCount),initialReads);
    await page.evaluate(()=>document.dispatchEvent(new Event("visibilitychange")));await loadDone();
    assert.equal(await page.evaluate(()=>document.activeElement?.id),"state-receipt-summary-0");
    assert.match(await rootPage().innerText(),new RegExp(requestId));
    await checkWidth();
    await page.locator("#product-role").selectOption("望舒");await loadDone();
    assert.match(await rootPage().innerText(),/黄体期 · 第 2 \/ 5 天/);
    await rootPage().locator('[data-state-feature="presentation"]').click();
    assert.match(await rootPage().innerText(),/同一 QQ 账号有多个展示窗口/);
    assert.match(await rootPage().innerText(),/旧确认未记录时间/);
    assert.doesNotMatch(await rootPage().innerText(),new RegExp(requestId));
    await rootPage().locator(".state-receipt-reference summary").click();
    assert.equal(await rootPage().locator("script,.state-presentation img,.state-presentation b").count(),0);
    assert.equal(await page.evaluate(()=>window.injected),undefined);
    await page.locator("#product-target").selectOption("second");await loadDone();
    assert.match(await rootPage().innerText(),/排卵期 · 第 2 \/ 5 天/);
    await rootPage().locator('[data-state-feature="presentation"]').click();
    assert.match(await rootPage().innerText(),/当前为预览宿主，未安装 QQ 展示端口/);
    assert.equal((await page.evaluate(()=>window.stateQA.calls)).includes(secondTarget),true);
    await page.locator("#product-target").selectOption("group");
    await rootPage().getByText("请选择已授权的私聊对象").waitFor();
    assert.doesNotMatch(await rootPage().innerText(),/有点饿|状态稳定/);
    await page.locator("#product-target").selectOption("first");await loadDone();
    await page.evaluate(first=>{
      const status=window.stateQA.values[first];
      status.settings.presence_enabled=false;
      status.effective.presence_enabled={allowed:false,reason:"authorization_denied"};
      status.presentation_diagnostics.typing={state:"idle",refresh_seconds:4};
      status.presentation_diagnostics.custom_status={state:"disabled",reason:"presentation_disabled"};
      status.presentation_diagnostics.observed_at="2026-09-25T02:00:00Z";
    },first);
    await rootPage().locator("#state-refresh").click();await loadDone();
    if(await rootPage().locator("#state-feature-detail").count()===0)
      await rootPage().locator('[data-state-feature="presentation"]').click();
    assert.match(await rootPage().innerText(),/当前会话没有进行中的回复/);
    assert.match(await rootPage().innerText(),/自定义短状态 · 开关已关闭/);
    assert.equal(await rootPage().locator(".state-receipts").innerText(),historyBefore);
    await page.setViewportSize({width:390,height:844});await checkWidth();
    await page.setViewportSize({width:320,height:720});await checkWidth();
    const editing=await require("./check_state_editor.cjs").run({page,rootPage,loadDone,checkWidth,first,secondRole,outputDir});
    await page.evaluate(()=>{window.stateQA.deny=true;});
    await rootPage().locator("#state-refresh").click();
    await page.getByText("当前账号没有角色状态管理权限。",{exact:true}).waitFor();
    assert.doesNotMatch(await rootPage().innerText(),/状态稳定/);
    assert.doesNotMatch(await rootPage().innerText(),/QQ 平台展示确认/);
    assert.deepEqual(errors,[]);
    return {pageRoot:root,bridgeMode,checks:"persona state board, homepage controls, contextual energy/body/cycle/sleep/busy/location configuration, presentation conditions and receipts, receipt focus survives refresh, role/target separation, group exclusion, XSS escaping, permission revocation, responsive 390/320px",editing,screenshots:[path.join(outputDir,"state-desktop.png"),path.join(outputDir,"state-mobile.png"),path.join(outputDir,"state-workspace-schedule.png"),path.join(outputDir,"state-workspace-presentation.png")]};
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
