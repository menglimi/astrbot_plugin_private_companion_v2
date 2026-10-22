/* Headless UI contract checks. Uses the installed bridge SDK, only synthetic data. */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const http = require("node:http");
const path = require("node:path");

async function run({browser, outputDir, bridgePath}) {
  const root = path.resolve(__dirname, "../pages/陪伴小屋");
  // A standalone preview uses the same canonical assets without host metadata.
  // The acceptance remains runnable from a freshly extracted core package.
  const preview = root;
  await fs.mkdir(outputDir, {recursive:true});
  const sdk = await fs.readFile(bridgePath,"utf8");
  const HOST = "astrbot_plugin_private_companion";
  const A = "host/targets/first/roles/role-a/memory";
  const B = "host/targets/second/roles/role-b/memory";
  const C = "host/targets/first/roles/role-c/memory";
  const full = value => "/"+HOST+"/"+value;
  const item = (id,state="prepared",extra={}) => ({batch_id:id,state,summary:"合成测试：一起记录的生活小事。",
    receipts:{},remaining_sources:null,deferred_sources:0,unavailable_sources:0,selection:{phase:"sources",examined:12},
    issues:[],unresolved_items:[],resumable:["prepared","received","modelled","selecting"].includes(state),
    retryable:["failed","partial"].includes(state),continuation:null,captured:false,...extra});
  const qa = {calls:[],posts:[],effects:0,deny:false,lose:false,holdRead:null,holdWrite:null,invalidPath:false,
    settingsWrites:0,clearWrites:0,sourceSessions:new Map(),
    settings:{"memory.enabled":true,"memory.automatic_context":true,"memory.context_items":4,
      "memory.context_chars":2400,"memory.query_items":12,"memory.query_chars":8000,
      "memory.source_chars":4000,"memory.turn_chars":16000,"memory.turn_calls":8,
      "memory.core_items":4,"memory.core_chars":4000,"memory.inclusion_chars":12000,
      "memory.reflection_enabled":false,"memory.reflection_timezone":"Asia/Shanghai",
      "memory.reflection_time":"23:50","memory.reflection_response_format":"text",
      "memory.reflection_auto_repair":true},
    records:{[A]:[item("batch-a","partial",{summary:'原摘要 <img src=x onerror="window.injected=true">',captured:true,
      receipts:{p1:{operation_id:"saved-one"}},issues:[{code:"invalid_json"}]}),item("uncertain","running"),item("later","received")],
      [B]:[item("batch-b","prepared",{summary:"另一个账号的独立记录。"})], [C]:[item("batch-c","received",{summary:"另一个角色的记录。"})]},receipts:new Map()};
  const ok = data => ({status:"ok",data});
  const fail = code => ({status:"error",data:{code}});
  const clone = value => JSON.parse(JSON.stringify(value));
  function catalog() {
    return {installation_id:"synthetic-installation",operator_id:"dashboard:qa",mode:"multi",targets:[
      {target_id:"first",scope_kind:"private",participant_id:"200",platform_id:"qq-main",account_id:"100",bot_id:"bot-a",
        roles:[{role_id:"澄汐",memory_api:qa.invalidPath?"/foreign/memory":full(A)},{role_id:"望舒",memory_api:full(C)}]},
      {target_id:"second",scope_kind:"private",participant_id:"200",platform_id:"qq-second",account_id:"101",bot_id:"bot-b",
        roles:[{role_id:"澄汐",memory_api:full(B)}]},
      {target_id:"group",scope_kind:"group",group_id:"300",platform_id:"qq-main",account_id:"100",bot_id:"bot-a",
        roles:[{role_id:"澄汐",memory_api:null}]}]};
  }
  async function rpc(message) {
    const {action,endpoint,params={},body={}} = message;
    qa.calls.push(clone(message));
    // Matches the host: endpoints are plugin-relative, never URLs or an identity override.
    assert(!endpoint.startsWith("/") && !endpoint.includes("..") && !/[?#%\\:]/.test(endpoint),endpoint);
    if (qa.deny) return fail("core_access_required");
    if (endpoint === "page/targets") return ok(catalog());
    if (endpoint === "integration/manifest") {
      assert.equal(action,"api:get");
      assert.deepEqual(params,{});
      return ok({product:{id:"private_companion.v2",version:"2.0.0"},discovery:"available",
        extensions:[{capability_id:"image",extension_id:"image",owner:"companion_v2",integration_state:"connected",assembled:true,enabled:true,runtime_ready:true}],
        providers:[],
        summary:{core_count:1,extension_count:1,extension_ready_count:1,provider_count:0,connected_count:1}});
    }
    const base = [A,B,C].find(p=>endpoint===p || endpoint.startsWith(p+"/"));
    assert(base,"unexpected bridge endpoint "+endpoint);
    if (action === "api:post" && endpoint.endsWith("/reflections/queue")) {
      assert.equal(endpoint,base+"/reflections/queue");
      assert.deepEqual(Object.keys(body).sort(),["batch_id","operation_key"]);
      qa.posts.push(clone(message));
      if (qa.holdWrite) { const release = qa.holdWrite; qa.holdWrite = null; await release.promise; }
      const key = base+":"+body.operation_key;
      if (qa.receipts.has(key)) return clone(qa.receipts.get(key));
      const original = qa.records[base].find(r=>r.batch_id===body.batch_id);
      if (!original) return fail("memory_reflection_unavailable");
      if (original.state === "running") return fail("memory_reflection_uncertain");
      let batch = original;
      if (original.retryable) {
        original.repair_batch = "repair-"+(qa.effects+1); original.retryable = false;
        batch = item(original.repair_batch,"received",{retry_of:original.batch_id});
        qa.records[base].push(batch);
      }
      const receipt = {job_id:"job-"+(++qa.effects),batch_id:batch.batch_id,state:"queued",result_code:null,
        next_at:"2026-09-24T08:05:00Z",updated_at:"2026-09-24T08:00:00Z"};
      batch.continuation = receipt;
      const response = ok(receipt); qa.receipts.set(key,clone(response));
      if (qa.lose) { qa.lose=false; return {lost:true}; }
      return response;
    }
    let response;
    const fact={atom_id:"fact-one",state:"active",revision:1,context_mode:"relevant",view_token:"fact-view-v1",
      predicate:"阅读偏好",object:"散文",representation:'喜欢散文 <script>window.injected=true</script>',subject:"当前用户",retention:"durable"};
    if(endpoint===base) response=ok({items:[fact],next_cursor:null});
    else if(endpoint===base+"/detail" && action==="api:post") {
      assert.deepEqual(Object.keys(body).sort(),["atom_id","revision"]);
      const session="memory-page-query-detail-"+base.split("/").at(-1);
      const handle="source-handle-"+base.split("/").at(-1); qa.sourceSessions.set(session,handle);
      response=body.atom_id==="fact-one"&&body.revision===1
        ?ok({item:fact,sources:[{handle,source_kind:"human_message",speaker_id:"user-200",start:0,end:12}],session_id:session})
        :fail("memory_fact_unavailable");
    } else if(endpoint===base+"/source" && action==="api:post") {
      assert(qa.sourceSessions.get(body.session_id)===body.handle,"source handle must stay in its query session");
      response=ok({handle:body.handle,text:"合成来源：一起散步。",start:0,end:10,next_offset:null,total_chars:10});
    } else if(endpoint===base+"/query" && action==="api:post") {
      const session=body.session_id||"memory-page-query-search-"+base.split("/").at(-1);
      if(!body.cursor){const handle="query-source-"+base.split("/").at(-1);qa.sourceSessions.set(session,handle);}
      const handle=qa.sourceSessions.get(session)||"query-source-"+base.split("/").at(-1);
      qa.sourceSessions.set(session,handle);
      response=ok({session_id:session,items:body.cursor?[]:[{kind:"experience",title:"一起散步",text:"那天在雨后散步。",statements:[{text:"沿河走了一段",sources:[handle]}]}],
        next_cursor:body.cursor?null:"memory-page-next-test",index_state:"ready",candidates_examined:3,
        unavailable_sources:false,complete:!body.cursor,scope_coverage:"captured_authorized_sources_only"});
    } else if(endpoint===base+"/settings" && action==="api:get") {
      response=ok({values:{...qa.settings},edit_token:"settings-edit-v1",revision:1,
        inheritance:Object.fromEntries(Object.keys(qa.settings).map(key=>[key,{layer:"角色"}]))});
    } else if(endpoint===base+"/settings/command" && action==="api:post") {
      qa.settingsWrites++; Object.assign(qa.settings,body.changes||{});
      response=ok({changed_fields:Object.keys(body.changes||{}),revision:qa.settingsWrites+1});
    } else if(endpoint===base+"/clear/preview" && action==="api:get") {
      response=ok({scope:"private_relationship_facts_and_revisions",counts:{active:1,forgotten:0,revisions:1},revision_token:"clear-revision-v1"});
    } else if(endpoint===base+"/clear" && action==="api:post") {
      qa.clearWrites++;response=ok({forgotten_count:1,revision_token:"clear-revision-v2"});
    } else if(endpoint===base+"/revisions" && action==="api:get") {
      response=ok({items:[{revision:1,state:"active",object:"散文",representation:"喜欢散文"}],next_cursor:null});
    } else if(endpoint===base+"/command" && action==="api:post") {
      response=ok({operation_id:"memory-operation-synthetic",revision:2});
    } else if (params.batch_id) {
      const record = qa.records[base].find(r=>r.batch_id===params.batch_id);
      response = record ? ok(record) : fail("memory_reflection_unavailable");
    } else {
      const available = qa.records[base].filter(r=>!["complete","empty"].includes(r.state) && !r.repair_batch);
      const offset = params.after_id ? available.findIndex(r=>r.batch_id===params.after_id)+1 : 0;
      const records = available.slice(offset,offset+2);
      response = ok({items:records,next_cursor:offset+2<available.length?records.at(-1).batch_id:null,scope:"private_memory_reflections"});
    }
    response = clone(response);
    if (qa.holdRead?.base === base) { const release = qa.holdRead; qa.holdRead = null; await release.promise; }
    return response;
  }
  const wrapper = plugin => `<!doctype html><meta charset="utf-8"><style>body{margin:0}iframe{border:0;width:100%;height:100vh;display:block}</style><iframe src="/page/index.html#memories" title="陪伴小屋"></iframe><script>
    addEventListener('message',async event=>{
      const frame=document.querySelector('iframe'),m=event.data;
      if(event.source!==frame.contentWindow || m.channel!=='astrbot-plugin-page')return;
      const send=v=>frame.contentWindow.postMessage({channel:'astrbot-plugin-page',...v},location.origin);
      if(m.kind==='ready'){send({kind:'context',context:{pluginName:${JSON.stringify(plugin)},pageName:'陪伴小屋'}});return;}
      if(m.kind!=='request')return;
      try{const response=await fetch('/qa',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(m)});
        const value=await response.json();
        if(value.lost){send({kind:'response',requestId:m.requestId,ok:false,error:'连接已中断'});return;}
        send({kind:'response',requestId:m.requestId,ok:true,data:value});
      }catch(error){send({kind:'response',requestId:m.requestId,ok:false,error:'模拟连接中断'});}
    });<\/script>`;
  const serverErrors = [];
  const server = http.createServer(async(req,res)=>{
    try {
      const url = new URL(req.url,"http://127.0.0.1");
      if (url.pathname === "/") {res.setHeader("Content-Type","text/html;charset=utf-8");res.end(wrapper(HOST));return;}
      if (url.pathname === "/wrong-host") {res.setHeader("Content-Type","text/html;charset=utf-8");res.end(wrapper("astrbot_plugin_content_companion"));return;}
      if (url.pathname === "/bridge.js") {res.setHeader("Content-Type","text/javascript;charset=utf-8");res.end(sdk);return;}
      if (url.pathname === "/qa") {
        const parts=[]; for await (const part of req) parts.push(part);
        const result=await rpc(JSON.parse(Buffer.concat(parts).toString("utf8")));
        res.setHeader("Content-Type","application/json");res.end(JSON.stringify(result));return;
      }
      const isPreview = url.pathname.startsWith("/preview/");
      const source = isPreview?preview:root;
      const relative = decodeURIComponent(url.pathname.replace(/^\/(page|preview)\//,""));
      const file = path.resolve(source,relative);
      if (!file.startsWith(source+path.sep)) {res.writeHead(404).end();return;}
      let payload=await fs.readFile(file);
      if (relative==="index.html" && !isPreview) payload=Buffer.from(payload.toString("utf8").replace("</body>",'<script src="/bridge.js"></script></body>'));
      if (relative==="index.html" && isPreview) payload=Buffer.from(payload.toString("utf8").replace(/\s*<meta name="companion-api-host"[^>]*>/,""));
      res.setHeader("Content-Type",({".html":"text/html;charset=utf-8",".js":"text/javascript;charset=utf-8",".css":"text/css;charset=utf-8",
        ".woff2":"font/woff2",".jpg":"image/jpeg"}[path.extname(file)] || "application/octet-stream"));
      res.end(payload);
    } catch(error) {if(error.code!=="ENOENT")serverErrors.push(String(error.stack));res.writeHead(500).end();}
  });
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  const url = "http://127.0.0.1:"+server.address().port;
  const page = await browser.newPage({viewport:{width:1366,height:1000},reducedMotion:"reduce"});
  page.setDefaultTimeout(8000);
  const browserErrors=[]; page.on("pageerror",error=>browserErrors.push(String(error)));
  const frame=()=>page.frameLocator("iframe");
  const locator=s=>frame().locator(s);
  const waitText=async(s,text)=>{await locator(s).filter({hasText:text}).waitFor();};
  const loaded=()=>locator('.memory-content[aria-busy="false"]').waitFor();
  const click=async s=>{await locator(s).click();await loaded();};
  const gate = ()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
  const checks=[];
  async function screenshot(name) {
    await page.evaluate(()=>{const el=document.querySelector("iframe");el.style.height=el.contentDocument.documentElement.scrollHeight+"px";});
    try {await page.screenshot({path:path.join(outputDir,name),fullPage:true});}
    finally {await page.evaluate(()=>{document.querySelector("iframe").style.height="";});}
  }
  try {
    await page.goto(url); await loaded();
    await waitText("#hostStatus","项拓展状态已读取");
    assert.match(await locator("#hostStatus").innerText(),/1 项拓展状态已读取/);
    checks.push("integrated_capability_manifest_preserved");
    assert.match(await locator("#memory-detail").innerText(),/尚未统计/);
    assert.equal(await locator("#memoryWorkspace img").count(),0);
    assert.equal(qa.posts.length,0); checks.push("mount_reads_only_null_counts_and_escaped_summary");
    await locator("#memory-queue").click(); await loaded();
    assert.equal(qa.effects,1); assert.equal(qa.posts[0].body.batch_id,"batch-a");
    assert.match(await locator(".memory-identifiers").textContent(),/repair-1/);
    assert.equal(await locator("#memory-queue").isDisabled(),true);
    await screenshot("memory-desktop.png");
    // Completing the child removes it from the queue but not the explicitly followed detail.
    const child=qa.records[A].find(r=>r.batch_id==="repair-1");
    Object.assign(child,{state:"complete",resumable:false,summary:"已完成，关闭页面后仍可核对。",continuation:{...child.continuation,state:"complete"}});
    await page.reload();await loaded();
    assert.match(await locator("#memory-detail").innerText(),/已完成，关闭页面后仍可核对/);
    assert.equal(qa.effects,1);checks.push("repair_tracks_child_and_completed_detail_survives_reload");
    // An unknown model attempt exposes no replay action.
    await locator(".memory-batch").filter({hasText:"调用结果待核对"}).click();await loaded();
    assert.equal(await locator("#memory-queue").count(),0);
    assert.match(await locator("#memory-detail").innerText(),/不能重复发起/);checks.push("unknown_model_attempt_has_no_replay");
    // Switch account with the same participant ID; no identity goes into request arguments.
    await locator("#memory-target").selectOption("1");await loaded();
    assert.match(await locator("#memory-detail").innerText(),/另一个账号/);
    qa.lose=true;
    await locator("#memory-queue").click();
    await waitText("#memory-notice","未收到提交回执");
    assert.equal(qa.effects,2);
    const lostKey=qa.posts.at(-1).body.operation_key;
    await page.reload();await loaded();
    await locator("#memory-target").selectOption("1");await loaded();
    await waitText(".memory-recovery","回执未确认");
    assert.equal(qa.effects,2);
    await click("#memory-recover");
    assert.equal(qa.effects,2);assert.equal(qa.posts.at(-1).body.operation_key,lostKey);
    assert.equal(qa.posts.at(-1).endpoint,B+"/reflections/queue");checks.push("lost_receipt_reuses_operation_across_reload_and_account_switch");
    // Page scope changes are allowed while a read is in flight; old response cannot overwrite it.
    const held=gate();qa.holdRead={base:B,...held};
    await locator("#memory-refresh").click();
    await locator("#memory-target").selectOption("0");await loaded();
    held.resolve(); await page.waitForTimeout(150);
    assert.equal(await locator("#memory-target").inputValue(),"0");
    assert.doesNotMatch(await locator("#memoryWorkspace").innerText(),/另一个账号的独立记录/);
    await locator("#memory-role").selectOption("1");await loaded();
    assert.match(await locator("#memory-detail").innerText(),/另一个角色/);checks.push("stale_account_response_ignored_and_role_selection_is_independent");
    // A POST already sent belongs to its captured role even if the user changes selection.
    const writeGate=gate();qa.holdWrite=writeGate;
    await locator("#memory-queue").click();
    await locator("#memory-target").selectOption("1");await loaded();
    writeGate.resolve();await page.waitForTimeout(150);
    assert.equal(await locator("#memory-target").inputValue(),"1");
    assert.doesNotMatch(await locator("#memory-detail").innerText(),/另一个角色的记录/);
    const heldKey=qa.posts.at(-1).body.operation_key;
    await locator("#memory-target").selectOption("0");await loaded();
    await locator("#memory-role").selectOption("1");await loaded();await click("#memory-recover");
    assert.equal(qa.posts.at(-1).body.operation_key,heldKey);assert.equal(qa.effects,3);
    checks.push("inflight_submit_keeps_original_role_and_recovers_original_operation");
    const blocked=qa.records[C][0];
    Object.assign(blocked,{state:"failed",resumable:false,retryable:true,
      continuation:{...blocked.continuation,state:"blocked",result_code:"invalid_json"}});
    const postCount=qa.posts.length;
    await click("#memory-refresh"); // Re-read current status without queuing another model call.
    assert.match(await locator("#memory-detail").innerText(),/本次处理受阻/);
    assert.equal(qa.posts.length,postCount);
    assert.match(await locator("#memory-detail").innerText(),/格式不合规/);
    await click("#memory-queue");assert.notEqual(qa.posts.at(-1).body.operation_key,heldKey);assert.equal(qa.effects,4);
    checks.push("blocked_job_poll_does_not_replay_and_explicit_repair_has_new_operation");
    await locator("#memory-target").selectOption("2");
    await waitText("#memoryWorkspace","群聊记忆独立管理");
    assert.equal(await locator("#memory-queue").count(),0);checks.push("group_never_reads_private_member_memory");
    await locator("#memory-target").selectOption("0");await loaded();
    await click("#memory-area-facts");
    assert.match(await locator(".memory-facts").innerText(),/喜欢散文 <script>/);
    assert.equal(await locator(".memory-facts script").count(),0);checks.push("saved_facts_use_same_scope_and_escape_text");
    qa.deny=true;await locator("#memory-refresh").click();await waitText("#memory-notice","没有记忆管理权限");
    assert.equal(await locator(".memory-facts").count(),0);
    assert.equal(await locator("#memory-target option").count(),1);checks.push("permission_revocation_clears_records_and_directory");
    qa.deny=false;await locator("#memory-directory-refresh").click();await loaded();
    qa.records[A].push(item("paging-last","selecting"));await click("#memory-refresh");
    await click("#memory-next");assert.match(await locator(".memory-pagination").innerText(),/第 2 页/);
    assert(qa.calls.some(c=>c.params?.after_id));await click("#memory-previous");checks.push("cursor_pagination");
    // Verify the route from the existing voxel home, not an isolated memory page.
    await locator('a.rail-link[href="#life"]').click();
    await locator("[data-voxel-room]").waitFor();
    await locator('[data-go="memories"]').first().click();await loaded();checks.push("voxel_home_memory_entry_uses_connected_workspace");

    await locator("#memory-area-facts").click();await loaded();
    assert.match(await locator(".memory-facts").innerText(),/喜欢散文/);
    await locator('[data-fact-id="fact-one"]').click();await loaded();
    assert.match(await locator(".memory-detail").innerText(),/事实 · fact-one/);
    await locator(".memory-source-link").first().click();await loaded();
    assert.match(await locator(".memory-source-text").innerText(),/合成来源/);
    await click("#memory-revisions");assert.match(await locator(".memory-revisions-list").innerText(),/第 1 版/);
    checks.push("fact_detail_revisions_and_session_bound_source_read");

    await locator("#memory-area-query").click();await loaded();
    await locator("#memory-query-text").fill("雨后散步");
    await locator("#memory-query-kind").selectOption("all");
    await locator('#memory-query-form button[type="submit"]').click();await loaded();
    assert.match(await locator(".memory-query-results").innerText(),/一起散步/);
    await locator(".memory-query-results .memory-source-link").first().click();await loaded();
    assert.match(await locator(".memory-query .memory-source-text").innerText(),/合成来源/);
    checks.push("source_experience_mixed_query_and_original_evidence");

    await locator("#memory-area-settings").click();await loaded();
    assert.match(await locator(".memory-settings").innerText(),/统一记忆策略/);
    await locator('[data-setting="memory.enabled"]').uncheck();
    await click("#memory-settings-save");
    assert.equal(qa.settingsWrites,1);assert.equal(qa.settings["memory.enabled"],false);
    checks.push("unified_memory_settings_patch");

    await locator("#memory-area-clear").click();await loaded();
    assert.match(await locator(".memory-clear").innerText(),/1/);
    page.on("dialog",dialog=>dialog.accept());
    await click("#memory-clear-confirm");
    assert.equal(qa.clearWrites,1);checks.push("previewed_scoped_clear_requires_explicit_confirmation");
    await locator("#memory-target").focus();await page.keyboard.press("Tab");
    assert.equal(await locator("#memory-role").evaluate(el=>el===document.activeElement),true);checks.push("keyboard_scope_navigation");
    for (const width of [390,320]) {
      await page.setViewportSize({width,height:844});
      await screenshot(`memory-mobile-${width}.png`);
      const overflow = await frame().locator("body").evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,
        elements:[...document.querySelectorAll("body *")].filter(el=>el.getBoundingClientRect().right>innerWidth+1).slice(0,12)
          .map(el=>({tag:el.tagName,class:el.className,right:el.getBoundingClientRect().right,width:el.getBoundingClientRect().width}))}));
      assert(overflow.scroll<=overflow.width+1,JSON.stringify(overflow));
    }
    checks.push("390_and_320_layout_no_horizontal_overflow");
    qa.invalidPath=true;await locator("#memory-directory-refresh").click();await waitText("#memory-notice","数据不完整");
    assert(!qa.calls.some(c=>c.endpoint.includes("foreign")));checks.push("foreign_api_path_rejected");
    qa.invalidPath=false;
    await page.goto(url+"/wrong-host");await waitText("#memory-notice","尚未连接");
    assert.equal(await locator("[data-detail^=memory-]").count(),0);checks.push("wrong_host_does_not_fall_back_to_example_records");
    await page.goto(url+"/preview/index.html#memories");
    await page.locator("#memoryWorkspace").filter({hasText:"当前为布局预览"}).waitFor();
    assert(await page.locator("[data-detail^=memory-]").count()>0);checks.push("standalone_preview_stays_explicitly_synthetic");
    assert.deepEqual(browserErrors,[]);assert.deepEqual(serverErrors,[]);
    const report={checks,passed:checks.length,synthetic_queue_effects:qa.effects,post_count:qa.posts.length,browserErrors,serverErrors};
    await fs.writeFile(path.join(outputDir,"browser-results.json"),JSON.stringify(report,null,2)+"\n","utf8");
    return report;
  } finally {await page.close();await new Promise(resolve=>server.close(resolve));}
}
module.exports={run};
if(require.main===module){
  (async()=>{
    const browser=await require("playwright").chromium.launch({headless:true,
      ...(process.env.MEMORY_PAGE_CHROMIUM?{executablePath:process.env.MEMORY_PAGE_CHROMIUM}:{})});
    try{console.log(JSON.stringify(await run({browser,outputDir:process.argv[2],bridgePath:process.argv[3]}),null,2));}
    finally{await browser.close();}
  })().catch(error=>{console.error(error);process.exitCode=1;});
}
