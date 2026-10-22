/* Browser acceptance for the action workspace; Qzone write controls are not exercised. */
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs/promises");
const path=require("node:path");
const {pathToFileURL}=require("node:url");
const {chromium}=require("playwright");

function syntheticBridge(){
  const host="astrbot_plugin_private_companion";
  window.AstrBotPluginPage={
    ready:async()=>({pluginName:host}),
    onContext:()=>()=>{},
    apiGet:async endpoint=>{
      if(endpoint==="integration/manifest")return {extensions:[
        {capability_id:"together",extension_id:"together",owner:"companion_v2",label:"共处",integration_state:"connected",enabled:true,runtime_ready:true,assembled:true,version:"2.0",description:"一起活动",reason:"状态正常"},
        {capability_id:"game",extension_id:"game",owner:"companion_v2",label:"游戏",integration_state:"unassembled",enabled:false,runtime_ready:false,assembled:false,version:"2.0",description:"棋类和游戏",reason:"V2 拓展尚未装配"},
        {capability_id:"reality",extension_id:"reality",owner:"companion_v2",label:"现实触及",integration_state:"degraded",enabled:true,runtime_ready:false,assembled:true,version:"2.0",description:"设备",reason:"等待设备授权"},
      ],providers:[],summary:{connected_count:1,extension_ready_count:1,unassembled_extension_count:1,provider_count:0}};
      if(endpoint==="extensions")return {extensions:{reality:{revision:"qa-native",settings:{enabled:true},
        schema:{enabled:{type:"bool",description:"启用能力",default:true}},runtime:{state:"running"}}}};
      if(endpoint==="page/targets")return {installation_id:"action-qa",operator_id:"dashboard:qa",targets:[{
        target_id:"qa",scope_kind:"private",participant_id:"验收对象",platform_id:"qq",account_id:"qa-bot",
        roles:[{role_id:"测试人格"}],
      }]};
      throw new Error("unexpected read: "+endpoint);
    },
    apiPost:async()=>{throw new Error("unexpected API write in browser acceptance");},
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
    const actionPage=page.locator(".action-page");
    await actionPage.waitFor();
    await page.locator("#actionQzoneBody").waitFor();
    await page.locator('.action-capability-row[data-state="degraded"]').waitFor();
    const capabilities=page.locator(".action-capability-row");
    assert.equal(await capabilities.count(),3);
    assert.equal(await page.locator('.action-capability-row[data-state="connected"]').count(),1);
    assert.equal(await page.locator('.action-capability-row[data-state="unassembled"]').count(),1);
    assert.equal(await page.locator('.action-capability-row[data-state="degraded"]').count(),1);
    assert.equal(await page.locator(".action-overview, .action-config-card").count(),0);
    assert.match(await page.locator(".action-capabilities-count").innerText(),/1\s*\/\s*3 已接入/);
    assert.equal(await actionPage.evaluate(root=>Boolean(root.querySelector("#action-qzone").compareDocumentPosition(root.querySelector(".action-capabilities"))&Node.DOCUMENT_POSITION_FOLLOWING)),true);
    await checkWidth();
    await capture("desktop");
    checks.push("QQ 空间工作区位于首位，三个 V2 内置能力按真实状态呈现");

    await page.locator("#action-config-reality .action-provider-button").click();
    await page.locator("#detailDialog[open]").waitFor();
    await page.locator('[data-native-extension-host="reality"] .native-extension-panel').waitFor();
    assert.match(await page.locator("#dialogContent").innerText(),/V2 内置能力/);
    assert.equal(await page.locator('#dialogContent [data-copy-address], #dialogContent a[href*="plugin-page"]').count(),0);
    await page.keyboard.press("Escape");
    checks.push("能力详情在小屋内打开 V2 原生设置");

    for(const [width,height] of [[960,900],[390,844],[320,740]]){
      await page.setViewportSize({width,height});
      await checkWidth();
      await checkPanelClearance();
      const wrappedTitles=await capabilities.locator("h3").evaluateAll(elements=>elements
        .filter(element=>element.getBoundingClientRect().height>parseFloat(getComputedStyle(element).lineHeight)+2)
        .map(element=>element.textContent.trim()));
      assert.deepEqual(wrappedTitles,[],"capability titles should stay on one line");
      await capture("width-"+width);
    }
    checks.push("960、390、320 像素下无横向溢出，能力名称完整显示");

    await page.setViewportSize({width:1366,height:1000});
    await page.locator("#action-config-game .action-settings-button").click();
    await page.waitForFunction(()=>location.hash==="#manage/contact");
    assert.match(await page.locator("#shellPanel").innerText(),/主动联系/);
    checks.push("配置入口跳转到既有的主动联系归属页");
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({checks,errors,output},null,2));
  }catch(error){await capture("failure");throw error;}
  finally{await page.close();await browser.close();}
}

if(require.main===module)run().catch(error=>{console.error(error);process.exitCode=1;});
module.exports={run};
