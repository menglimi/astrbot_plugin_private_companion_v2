/* Browser acceptance for the action matrix. Uses a synthetic read-only AstrBot bridge. */
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs/promises");
const path=require("node:path");
const {pathToFileURL}=require("node:url");
const {chromium}=require("playwright");

function syntheticBridge(){
  const host="astrbot_plugin_private_companion_v2";
  window.AstrBotPluginPage={
    ready:async()=>({pluginName:host}),
    onContext:()=>()=>{},
    apiGet:async endpoint=>{
      if(endpoint==="integration/manifest")return {providers:[
        {capability_id:"together",label:"共处",integration_state:"connected",enabled:true,runtime_ready:true,installed:true,version:"2.0",description:"一起活动",reason:"状态正常"},
        {capability_id:"game",label:"游戏",integration_state:"missing",enabled:false,runtime_ready:false,installed:false,version:"未安装",description:"棋类和游戏",reason:"提供方未安装"},
        {capability_id:"reality",label:"现实触及",integration_state:"degraded",enabled:true,runtime_ready:false,installed:true,version:"2.0",description:"设备",reason:"等待设备授权"},
      ],summary:{connected_count:1,installed_count:2,missing_count:1}};
      if(endpoint==="page/targets")return {installation_id:"action-qa",operator_id:"dashboard:qa",targets:[{
        target_id:"qa",scope_kind:"private",participant_id:"验收对象",platform_id:"qq",account_id:"qa-bot",
        roles:[{role_id:"测试人格"}],
      }]};
      throw new Error("unexpected read: "+endpoint);
    },
    apiPost:async()=>{throw new Error("action overview must remain read-only");},
  };
}

async function run(){
  const root=path.resolve(__dirname,"..");
  const pagePath=path.join(root,"pages","陪伴小屋","index.html");
  const output=path.resolve(process.argv[2]||path.join(require("node:os").tmpdir(),"action-page-qa"));
  await fs.mkdir(output,{recursive:true});
  const launchOptions={headless:true};
  if(process.env.PLAYWRIGHT_EXECUTABLE_PATH)launchOptions.executablePath=process.env.PLAYWRIGHT_EXECUTABLE_PATH;
  const browser=await chromium.launch(launchOptions);
  const page=await browser.newPage({viewport:{width:1366,height:1000},reducedMotion:"reduce"});
  const errors=[],checks=[];
  page.on("pageerror",error=>errors.push(error.message));
  await page.addInitScript(syntheticBridge);
  const capture=name=>page.screenshot({path:path.join(output,name+".png"),fullPage:true});
  const checkWidth=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  const checkPanelClearance=async()=>page.evaluate(()=>{
    const rail=document.querySelector("#homeShell .rail").getBoundingClientRect();
    const panel=document.querySelector("#shellPanel").getBoundingClientRect();
    return innerWidth<=760||panel.left>=rail.right-1;
  }).then(clear=>assert.equal(clear,true,"configuration panel must clear the navigation rail"));
  try{
    await page.goto(pathToFileURL(pagePath).href+"#manage/action");
    const matrix=page.locator(".action-page");
    await matrix.waitFor();
    await page.locator('.action-route-node[data-state="degraded"]').waitFor();
    const firstCard=page.locator(".action-config-card").first();
    await page.emulateMedia({reducedMotion:"no-preference"});
    assert.equal(await firstCard.evaluate(element=>getComputedStyle(element).animationName),"action-arrive");
    await page.emulateMedia({reducedMotion:"reduce"});
    assert.equal(await firstCard.evaluate(element=>getComputedStyle(element).animationName),"none");
    await page.evaluate(()=>{document.documentElement.dataset.motion="off";});
    assert.equal(await firstCard.evaluate(element=>getComputedStyle(element).animationName),"none");
    await page.evaluate(()=>{document.documentElement.dataset.motion="full";});
    checks.push("入场动画按正常偏好播放，系统减少动态和页面关闭动效时停止");
    assert.equal(await page.locator(".action-route-node").count(),3);
    assert.match(await matrix.innerText(),/01\s*\/\s*03/);
    assert.match(await matrix.innerText(),/状态全部正常|项需要留意/);
    assert.equal(await page.locator(".action-config-card").count(),3);
    await checkWidth();
    await capture("desktop");
    checks.push("提供方清单映射三项状态，显示连接计数与三张配置归属卡片");

    const reality=page.locator('.action-route-node[data-action-focus="reality"]');
    await reality.click();
    const realityCard=page.locator("#action-config-reality");
    await realityCard.waitFor({state:"visible"});
    assert.equal(await realityCard.evaluate(el=>el.classList.contains("is-focused")),true);
    assert.equal(await page.locator("#action-config-reality .action-settings-button").evaluate(el=>el===document.activeElement),true);
    checks.push("状态节点滚动到对应配置卡片，并将键盘焦点交给设置入口");

    await page.locator("#action-config-reality .action-provider-button").click();
    await page.locator("#detailDialog[open]").waitFor();
    assert.match(await page.locator("#dialogContent").innerText(),/等待设备授权/);
    await page.keyboard.press("Escape");
    checks.push("拓展详情从真实能力清单呈现状态与原因");

    for(const [width,height] of [[960,900],[390,844],[320,740]]){
      await page.setViewportSize({width,height});
      await checkWidth();
      await checkPanelClearance();
      const wrappedTitles=await matrix.locator(".action-config-card h3").evaluateAll(elements=>elements
        .filter(element=>element.getBoundingClientRect().height>parseFloat(getComputedStyle(element).lineHeight)+2)
        .map(element=>element.textContent.trim()));
      assert.deepEqual(wrappedTitles,[],"short action titles should stay on one line");
      await capture("width-"+width);
    }
    checks.push("960、390、320 像素下无横向溢出，平板面板不被导航栏遮挡");

    await page.setViewportSize({width:1366,height:1000});
    await page.locator("#action-config-game .action-settings-button").click();
    await page.waitForFunction(()=>location.hash==="#manage/contact");
    assert.match(await page.locator("#shellPanel").innerText(),/主动与联系/);
    checks.push("配置入口跳转到既有的主动与联系归属页");
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({checks,errors,output},null,2));
  }catch(error){await capture("failure");throw error;}
  finally{await page.close();await browser.close();}
}

if(require.main===module)run().catch(error=>{console.error(error);process.exitCode=1;});
module.exports={run};
