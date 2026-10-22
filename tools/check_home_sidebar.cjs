/* 小屋右栏的浏览器验收。仅使用合成对象与只读桥，不连接真实账号。 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const {pathToFileURL} = require("node:url");
const {chromium} = require("playwright");

function syntheticBridge(options={}) {
  const HOST="astrbot_plugin_private_companion", base="/"+HOST+"/host/targets/";
  const iso = offset => new Date(Date.now()+offset*60000).toISOString();
  const qa=window.__sidebarQA={empty:false,denyState:false,deferSecond:false,hiddenKinds:[],
    calendarCoverage:null,stateEnabled:true,posts:0};
  const catalog={mode:"multi",installation_id:"sidebar-qa",operator_id:"dashboard:qa",targets:["a","b"].map(id=>({
    target_id:id,scope_kind:"private",participant_id:"合成对象 "+id,platform_id:"qq",account_id:"qa-bot",bot_id:"qa-bot",
    roles:[{role_id:id==="a"?"晨星":"晚星",state_api:base+id+"/roles/role-"+id+"/state",life_api:base+id+"/roles/role-"+id+"/life"}],
  }))};
  const state = id => ({settings:{enabled:qa.stateEnabled,mood_enabled:true,health_enabled:true,hunger_enabled:true,planning_timezone:"Asia/Shanghai",
    ...Object.fromEntries(["energy","health","hunger","sleep","cycle","busy","location"].map(key=>["home_show_"+key,!qa.hiddenKinds.includes(key)]))},
    state:{state:qa.empty?"unknown":"ready",revision:qa.empty?0:1,updated_at:qa.empty?undefined:iso(-10),values:qa.empty?{}:{
      energy:id==="a"?71:83,mood:{description:id==="a"?"平静而专注":"心情轻快",joy:7,anger:2,sorrow:2,fear:2,baseline:6},
      location:id==="a"?"小屋窗边":"庭院",sleep:"清醒",busy:"稍忙",health:"稳定",hunger:"不饿"}},
    calendar:{items:[],next_cursor:null,skipped:0},occurrences:{partial:Boolean(qa.calendarCoverage),
      ...(qa.calendarCoverage||{}),items:qa.empty?[]:[
      {id:"later",sequence:0,kind:"role_plan",state:"accepted",title:"给花草浇水 "+id,start:iso(120),end:iso(150)},
      {id:"now",sequence:0,kind:"role_plan",state:"accepted",title:"阅读时间 "+id,start:iso(-20),end:iso(30)},
      {id:"old",sequence:0,kind:"role_plan",state:"accepted",title:"过去的安排",start:iso(-180),end:iso(-120)},
    ]},sleep_schedule:{enabled:!qa.empty,time:"00:30",timezone:"Asia/Shanghai",duration_minutes:480,
      next_sleep_at:iso(480),next_wake_at:iso(960),executor_state:"available"},presentation:{state:"preview"}});
  const life = id => ({role_id:id==="a"?"晨星":"晚星",config:{enabled:true,diary_enabled:false},
    activities:qa.empty?[]:[{activity_id:"reading-"+id,kind:"reading",state:"active",title:id==="a"?"窗边读书":"整理散步见闻",
      started_at:iso(-12),due_at:iso(30)},{activity_id:"done",state:"completed",title:"已完成的历史活动"}],journals:[]});
  window.AstrBotPluginPage={
    ready:async()=>({pluginName:HOST}),onContext:()=>()=>{},
    apiGet:async endpoint=>{
      if(endpoint==="page/targets"){
        if(options.catalogDelay)await new Promise(resolve=>setTimeout(resolve,options.catalogDelay));
        return catalog;
      }
      if(endpoint==="integration/manifest")return {product:{version:"2.0.0"},host:{enabled:true},core:[],extensions:[],providers:[],summary:{connected_count:0,extension_ready_count:0,unassembled_extension_count:0,provider_count:0}};
      const match=/host\/targets\/([ab])\/roles\/role-[ab]\/(state|life)$/.exec(endpoint);
      if(!match)throw new Error("unexpected read: "+endpoint);
      if(match[2]==="life")return life(match[1]);
      if(qa.denyState)throw Object.assign(new Error("authorization_denied"),{code:"authorization_denied"});
      if(match[1]==="b"&&qa.deferSecond)await new Promise(resolve=>{qa.resolveSecond=resolve;});
      return state(match[1]);
    },
    apiPost:async()=>{qa.posts++;throw new Error("sidebar must remain read-only");},
  };
}

module.exports={syntheticBridge};
if(require.main===module)(async()=>{
  const output=path.resolve(process.argv[2]||"build/home-sidebar-qa");
  await fs.mkdir(output,{recursive:true});
  const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH,args:["--enable-unsafe-swiftshader"]});
  const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
  const errors=[],checks=[];page.on("pageerror",error=>errors.push(error.message));
  await page.addInitScript(syntheticBridge);
  const side=page.locator("#shellSide");
  const capture=async name=>page.screenshot({path:path.join(output,name+".png"),fullPage:true});
  async function layout() {
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    assert.deepEqual(await side.locator("strong,dd,time,button").evaluateAll(elements=>{
      const parent=document.getElementById("shellSide").getBoundingClientRect();
      return elements.filter(el=>{const r=el.getBoundingClientRect();return getComputedStyle(el).visibility!=="hidden"&&r.width&&(r.right>parent.right+1||r.left<parent.left-1);}).map(el=>el.textContent);
    }),[],"sidebar text must stay within the available width");
  }
  try {
    await page.goto(pathToFileURL(path.resolve(__dirname,"../pages/陪伴小屋/index.html")).href);
    await side.getByText("窗边读书",{exact:true}).waitFor();
    const initial=await side.innerText();
    assert.match(await side.locator(".home-state-board").getAttribute("aria-label"),/71/);assert.doesNotMatch(initial,/平静而专注/);
    assert.equal(await side.locator(".home-state-point").count(),7);
    assert.equal(await side.locator(".home-state-point .home-state-glyph svg").count(),7);
    assert.match(initial,/当前计划时段/);assert.match(initial,/自动睡眠计划/);
    assert.doesNotMatch(initial,/过去的安排|已完成的历史活动|\[object Object\]/);
    await layout();await capture("desktop");
    await side.screenshot({path:path.join(output,"sidebar-detail.png")});
    const energy=side.locator(".home-state-point").first(),detail=energy.locator('[role="tooltip"]');
    await energy.hover();await detail.waitFor({state:"visible"});assert.match(await detail.innerText(),/71 \/ 100/);
    await layout();await capture("energy-hover");
    await page.mouse.move(100,100);await side.locator(".home-state-board").focus();
    assert.match(await side.locator(".home-state-board").getAttribute("aria-label"),/能量 71 \/ 100/);
    checks.push("首页状态看板悬停可读细节，键盘聚焦可访问完整摘要");
    for(const [width,height] of [[960,900],[390,844],[320,740]]){
      await page.setViewportSize({width,height});await layout();await capture("width-"+width);
    }
    checks.push("状态摘要和时间线在 1440、960、390、320 像素下无溢出");
    await page.setViewportSize({width:1440,height:1000});
    await page.evaluate(()=>{__sidebarQA.deferSecond=true;});
    await page.locator("#product-target").selectOption("b");
    await side.locator(".home-state-board").getByText("读取中",{exact:true}).first().waitFor();
    assert.doesNotMatch(await side.innerText(),/窗边读书|平静而专注|71/);
    await page.waitForFunction(()=>typeof __sidebarQA.resolveSecond==="function");
    await page.evaluate(()=>{__sidebarQA.deferSecond=false;__sidebarQA.resolveSecond();});
    await side.getByText("整理散步见闻",{exact:true}).waitFor();
    assert.match(await side.locator(".home-state-board").getAttribute("aria-label"),/83/);assert.doesNotMatch(await side.innerText(),/窗边读书|平静而专注/);
    checks.push("对象切换先清空旧角色，再显示当前角色的状态与计划");
    await page.evaluate(async()=>{__sidebarQA.denyState=true;await CompanionProduct.connect();});
    assert.match(await side.innerText(),/当前角色没有可用的授权/);
    assert.match(await side.innerText(),/整理散步见闻/);await capture("partial-read");
    checks.push("日历读取失败不掩盖已读取的活动，并给出权限原因");
    await page.evaluate(async()=>{__sidebarQA.denyState=false;__sidebarQA.empty=true;await CompanionProduct.connect();});
    assert.match(await side.innerText(),/暂无近期安排/);assert.match(await side.innerText(),/尚未记录/);
    assert.doesNotMatch(await side.innerText(),/整理散步见闻|平静而专注/);await capture("empty");
    checks.push("空记录保留状态位置与日程入口，不补写生活内容");
    await page.evaluate(async()=>{__sidebarQA.empty=false;__sidebarQA.calendarCoverage={skipped:2,
      skipped_reasons:{role_mismatch:2},scan_truncated:true,occurrences_truncated:3};await CompanionProduct.connect();});
    const coverage=await side.innerText();
    assert.match(coverage,/2 条日历记录已跳过（2 条来源角色不匹配）/);
    assert.match(coverage,/日历记录达到读取上限/);assert.match(coverage,/3 个日历期次超过读取上限/);
    checks.push("首页分别说明来源跳过数量、扫描截断和期次截断");
    await page.evaluate(async()=>{__sidebarQA.hiddenKinds=["energy","location"];await CompanionProduct.connect();});
    assert.equal(await side.locator(".home-state-point").count(),5);
    assert.doesNotMatch(await side.locator(".home-state-board").innerText(),/能量|位置/);
    await page.evaluate(async()=>{__sidebarQA.hiddenKinds=[];await CompanionProduct.connect();});
    await side.locator(".home-state-board").click();
    await page.locator("#roleStateWorkspace .state-page-heading").waitFor();
    assert.equal(new URL(page.url()).hash,"#life/state");
    assert.match(await page.locator("#roleStateWorkspace").innerText(),/状态看板/);
    checks.push("首页右侧状态看板整块点击进入当前人格的状态配置页");
    assert.equal(await page.evaluate(()=>__sidebarQA.posts),0);assert.deepEqual(errors,[]);
    await fs.writeFile(path.join(output,"report.json"),JSON.stringify({checks,errors},null,2)+"\n","utf8");
    console.log(JSON.stringify({checks,errors},null,2));
  } catch(error){await capture("failure");throw error;}
  finally{await page.close();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
