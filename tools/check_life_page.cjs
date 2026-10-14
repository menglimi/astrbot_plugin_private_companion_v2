/* Isolated browser acceptance: synthetic bridge, no AstrBot/model/platform I/O. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const http = require('node:http');
const path = require('node:path');

async function run({browser, outputDir}) {
  await fs.mkdir(outputDir, {recursive:true});
  const root = path.resolve(__dirname, '../pages/日记与生活');
  const bridge = `(() => {
    const state = {role_id:'小伴', participant:'测试私聊', host_state:'running', view_token:'v1', edit_token:'c1',
      config:{enabled:true,diary_enabled:true,diary_time:'23:50',timezone:'Asia/Shanghai',sleep_enabled:false,sleep_time:'00:30',sleep_timezone:'Asia/Shanghai',sleep_variation_minutes:20,sleep_window_minutes:120,sleep_minutes:480,reading_enabled:false,derive_enabled:true},
      sleep_schedule:{shared:true,owner:{installation_id:'test',bot_id:'bot-test',role_id:'小伴'},enabled:true,time:'22:30',timezone:'Asia/Shanghai',variation_minutes:20,window_minutes:120,duration_minutes:480,recommended_duration_minutes:510,physiology:{sleep_pressure:68,sleep_debt_minutes:95,workload_score:54,awake_minutes:390,has_sleep_history:true},executor_is_current:true,executor_state:'available',executor_window:{platform:'qq',account_id:'10001',native_scope_id:'20002',session_id:'20002',label:'qq · 账号 10001 · 会话 20002'},next_sleep_at:'2026-09-23T14:30:00Z',next_wake_at:'2026-09-23T22:30:00Z',active_wake_at:'2026-09-23T12:00:00Z'},
      journals:[{kind:'diary',local_date:'2026-09-23',revision:1,state:'active',body:'读到一段谈论城市和树木的文章。\\n我又想起窗边那点慢慢移动的光。<img src=x onerror="window.injected=true">',afterglow:'',summary:'读到城市与树木，想到窗边的光。',dream_fragments:[],view_token:'j1'},
        {kind:'dream',local_date:'2026-09-22',revision:1,state:'active',body:'我只记得树叶的影子。',afterglow:'有一点安静。',summary:null,dream_fragments:[],view_token:'j2'}],
      activities:[{activity_id:'book1',revision:1,kind:'reading',state:'planned',title:'城市与树木 · 1–120 字符',started_at:'2026-09-23T04:00:00Z',view_token:'a1',task:null},
        {activity_id:'sleep1',revision:1,kind:'sleep',state:'active',title:'角色开始一段睡眠',started_at:'2026-09-23T04:00:00Z',due_at:'2026-09-23T12:00:00Z',view_token:'s1'}],
      next_date:null,next_activity:null,receipts:[],running:[]};
    window.pageQA={state,calls:[],lose:false,deny:false,effects:0,envelope:false}; const receipts=new Map();
    const response=result=>window.pageQA.envelope?result:result.data;
    window.AstrBotPluginPage={ready:async()=>{},apiGet:async endpoint=>{
      if(endpoint==='staging/status')return {status:'ok',data:{runtime_open:true}};
      if(endpoint!=='life')throw Error('wrong endpoint');
      return window.pageQA.deny?{status:'error',data:{code:'core_access_required'}}:response({status:'ok',data:structuredClone(state)});
    },apiPost:async(endpoint,body)=>{
      if(endpoint==='staging/start'||endpoint==='staging/stop'){state.host_state=endpoint.endsWith('start')?'running':'stopped';return {status:'ok',data:{}};}
      if(endpoint!=='life/command')throw Error('wrong endpoint');
      window.pageQA.calls.push(structuredClone(body));
      if(receipts.has(body.operation_key))return response(receipts.get(body.operation_key));
      window.pageQA.effects++;
      const j=state.journals.find(j=>j.kind===body.kind&&j.local_date===body.local_date);
      const a=state.activities.find(a=>a.activity_id===body.activity_id);
      if(body.action==='edit'){j.body=body.body;j.revision++;j.view_token='j'+j.revision;}
      if(body.action==='delete'){j.body=null;j.state='deleted';j.revision++;j.view_token='j'+j.revision;}
      if(body.action==='restore'){j.body=body.body;j.state='active';j.revision++;j.view_token='j'+j.revision;}
      if(body.action==='read'){a.state='completed';a.reflection='这段阅读让我想起一条街。';a.task={state:'succeeded'};a.revision++;a.view_token='a'+a.revision;}
      if(body.action==='wake'){a.state='completed';a.revision++;a.view_token='s'+a.revision;}
      if(body.action==='configure'){Object.assign(state.config,body.changes);state.edit_token='c2';}
      const result={status:'ok',data:{state:'completed'}};receipts.set(body.operation_key,result);
      if(window.pageQA.lose){window.pageQA.lose=false;throw Error('未收到执行结果，请重试本次操作。');}return response(result);
    }};
  })();`;
  const server = http.createServer(async(req,res)=>{
    const url=new URL(req.url,'http://127.0.0.1');
    if(url.pathname==='/api/plugin/page/bridge-sdk.js'){res.setHeader('Content-Type','text/javascript; charset=utf-8');res.end(bridge);return;}
    const file={'/':'workspace.html','/app.js':'app.js','/style.css':'style.css'}[url.pathname];
    if(!file){res.writeHead(404);res.end();return;}
    res.setHeader('Content-Type',(file.endsWith('html')?'text/html':file.endsWith('css')?'text/css':'text/javascript')+'; charset=utf-8');
    res.end(await fs.readFile(path.join(root,file)));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const context=await browser.newContext({viewport:{width:1360,height:980},reducedMotion:'reduce'});
  const page=await context.newPage();const failures=[],screenshots=[];
  page.on('pageerror',error=>failures.push(error.message));
  const idle=()=>page.waitForFunction(()=>!document.getElementById('refresh').disabled);
  const layout=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  const capture=async name=>{const target=path.join(outputDir,name+'.png');await page.screenshot({path:target,fullPage:true});screenshots.push(target);};
  try{
    await page.goto('http://127.0.0.1:'+server.address().port);
    await page.waitForFunction(()=>document.getElementById('role').textContent==='小伴');
    assert.match(await page.locator('#sleep-scope').textContent(),/当前角色 · 各会话共享/);
    assert.match(await page.locator('#sleep-executor').textContent(),/当前私聊窗口（本页）/);
    assert.doesNotMatch(await page.locator('body').innerText(),/bot-test|10001|20002/);
    assert.match(await page.locator('#sleep-active-wake').textContent(),/2026/);
    assert.equal(await page.locator('#sleep-pressure').textContent(),'68 / 100');
    assert.equal(await page.locator('#sleep-debt').textContent(),'95 分钟');
    assert.equal(await page.locator('#sleep-workload').textContent(),'54 / 100');
    assert.equal(await page.locator('#sleep-recommended').textContent(),'8.5 小时');
    assert.equal(await page.locator('#sleep_window_minutes').inputValue(),'120');
    await layout();assert.equal(await page.evaluate(()=>window.injected),undefined);
    await capture('life-desktop');
    await page.getByRole('button',{name:'更正正文',exact:true}).click();
    await page.locator('#text-body').fill('更正后的私人日记。');
    await page.evaluate(()=>{window.pageQA.lose=true;});
    await page.locator('#dialog-submit').click();await idle();
    assert.equal(await page.locator('#editor').evaluate(d=>d.open),true);
    await page.locator('#dialog-submit').click();await idle();
    assert.equal(await page.locator('#journal-detail .prose').textContent(),'更正后的私人日记。');
    const calls=await page.evaluate(()=>window.pageQA.calls);assert.equal(calls[0].operation_key,calls[1].operation_key);
    assert.equal(await page.evaluate(()=>window.pageQA.effects),1);
    await page.evaluate(()=>{window.pageQA.envelope=true;});
    await page.getByRole('button',{name:'删除',exact:true}).click();await page.locator('#dialog-submit').click();await idle();
    await page.getByRole('button',{name:'填写正文并恢复',exact:true}).click();await page.locator('#text-body').fill('主动恢复的正文。');
    await page.locator('#dialog-submit').click();await idle();
    await page.getByRole('button',{name:'阅读书架',exact:true}).click();
    await page.getByRole('button',{name:'开始阅读',exact:true}).click();await idle();
    assert.equal(await page.locator('#reading-list .prose').textContent(),'这段阅读让我想起一条街。');
    await page.getByRole('button',{name:'添加原文',exact:true}).click();
    await page.keyboard.press('Escape');assert.equal(await page.locator('#editor').evaluate(d=>d.open),false);
    await page.getByRole('button',{name:'睡眠记录',exact:true}).click();await page.getByRole('button',{name:'现在醒来',exact:true}).click();
    await page.locator('#dialog-submit').click();await idle();assert.equal(await page.locator('#sleep-list .badge').textContent(),'已完成');
    await page.locator('#settings summary').click();await page.locator('#diary_time').fill('22:40');
    await page.locator('#sleep_window_minutes').fill('75');
    await page.getByRole('button',{name:'保存设置',exact:true}).click();await idle();
    assert.equal(await page.evaluate(()=>window.pageQA.state.config.diary_time),'22:40');
    assert.equal(await page.evaluate(()=>window.pageQA.calls.at(-1).changes.sleep_window_minutes),75);
    assert.equal(await page.evaluate(()=>window.pageQA.calls.at(-1).changes.sleep_timezone),'Asia/Shanghai');
    await page.locator('#settings summary').click();
    await page.getByRole('button',{name:'停止运行',exact:true}).click();await idle();assert.equal(await page.locator('#host-state').textContent(),'已停止');
    await page.getByRole('button',{name:'启动当前配置',exact:true}).click();await idle();assert.equal(await page.locator('#host-state').textContent(),'运行中');
    await page.getByRole('button',{name:'日记与梦境',exact:true}).click();
    await page.setViewportSize({width:390,height:844});await layout();await capture('life-mobile');
    await page.getByRole('button',{name:'更正正文',exact:true}).click();await layout();await capture('life-mobile-editor');
    await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.querySelector('#editor').contains(document.activeElement)),true);
    await page.keyboard.press('Escape');await page.setViewportSize({width:320,height:700});await layout();
    await page.evaluate(()=>{window.pageQA.deny=true;});await page.getByRole('button',{name:'刷新记录',exact:true}).click();
    await page.waitForFunction(()=>document.getElementById('notice').textContent==='当前账号没有本体管理权限。');
    assert.equal(await page.locator('.journal-link').count(),0);assert.equal(await page.locator('#journal-detail').textContent(),'');
    assert.deepEqual(failures,[]);
    return {checks:'desktop/mobile 390/320px, role sleep physiology, sleep window persistence, edit/lost-response idempotency, delete/restore, reading, wake, settings, keyboard/Escape, XSS, revoked read clears content',screenshots};
  }finally{await context.close();await new Promise(resolve=>server.close(resolve));}
}
module.exports={run};
if(require.main===module){
  (async()=>{
    const launchOptions={headless:true};
    if(process.env.PLAYWRIGHT_EXECUTABLE_PATH) launchOptions.executablePath=process.env.PLAYWRIGHT_EXECUTABLE_PATH;
    const browser=await require('playwright').chromium.launch(launchOptions);
    try{console.log(JSON.stringify(await run({browser,outputDir:await fs.mkdtemp(require('os').tmpdir()+'/life-page-')}),null,2));}
    finally{await browser.close();}
  })().catch(error=>{console.error(error);process.exitCode=1;});
}
