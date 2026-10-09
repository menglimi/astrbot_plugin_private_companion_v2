"use strict";
/* Weather credentials and source settings against a synthetic host only. */
const assert=require("node:assert/strict");
const path=require("node:path");
const {run}=require("./check_state_page.cjs");

async function inspect({page,errors,outputDir}) {
  await page.evaluate(()=>window.navigate("manage","perception"));
  await page.evaluate(()=>window.CompanionPerceptionTabs.activate("config-environment:perception-detail-place",{focus:true,scroll:true}));
  const root=page.locator("#perceptionWeatherSourceWorkspace"), form=root.locator("[data-weather-source-form]");
  await form.waitFor();
  const source=name=>form.locator(`[name="${name}"]`);
  const submit=form.locator('button[type="submit"]');
  const save=async()=>{
    const before=await page.evaluate(()=>window.stateQA.posts.length);
    await submit.click();
    await page.waitForFunction(count=>window.stateQA.posts.length===count+1,before);
    await root.getByText("数据源已保存并立即生效。",{exact:true}).waitFor();
    return page.evaluate(()=>window.stateQA.posts.at(-1));
  };
  assert.equal(await source("credential").getAttribute("type"),"password");
  const secret="0123456789abcdef0123456789abcdef";
  await source("provider").selectOption("qweather");
  await source("api_host").fill("https://example.re.qweatherapi.com/");
  await source("credential").fill(secret);
  await source("refresh_minutes").fill("30");
  const first=await save();
  assert.equal(first.endpoint,"host-options/weather");
  assert.deepEqual(first.body.changes,{provider:"qweather",api_host:"https://example.re.qweatherapi.com/",refresh_minutes:30,credential:secret});
  assert.equal(await source("credential").inputValue(),"");
  assert.equal(await source("api_host").inputValue(),"example.re.qweatherapi.com");
  assert.match(await root.innerText(),/API Key 已配置/);
  assert.equal(await page.evaluate(key=>[localStorage,sessionStorage].some(storage=>Object.keys(storage).some(name=>storage.getItem(name).includes(key))),secret),false);
  const screenshot=async width=>{
    await page.setViewportSize({width,height:1100});
    await root.scrollIntoViewIfNeeded();
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1);
    assert.equal(overflow,false,`weather source overflows at ${width}px`);
    await page.screenshot({path:path.join(outputDir,`weather-source-${width}.png`)});
    const controls=await form.locator('input,select').evaluateAll(nodes=>nodes.map(node=>{
      const box=node.getBoundingClientRect();return {name:node.name,left:box.left,right:box.right,width:box.width,viewport:window.innerWidth};
    }));
    const ancestors=await root.evaluate(node=>{const result=[];while(node){const style=getComputedStyle(node);result.push({id:node.id,class:node.className,width:node.getBoundingClientRect().width,min:style.minWidth,display:style.display,grid:style.gridTemplateColumns});node=node.parentElement;}return result;});
    assert.equal(await form.locator('input,select').evaluateAll(nodes=>nodes.every(node=>{
      const box=node.getBoundingClientRect();return box.left>=-1&&box.right<=window.innerWidth+1;
    })),true,JSON.stringify({controls,ancestors}));
  };
  for(const width of [1366,390,320])await screenshot(width);
  await page.setViewportSize({width:1366,height:980});
  await source("refresh_minutes").fill("10");
  const update=await save();
  assert.deepEqual(update.body.changes,{refresh_minutes:10});
  assert.match(await source("credential").getAttribute("placeholder"),/留空保留/);
  await source("provider").selectOption("open-meteo");
  await page.evaluate(()=>window.stateQA.weatherSource.edit_token="d".repeat(64));
  await submit.click();
  await root.getByText("数据源已被其他页面修改。请重新读取后核对并保存。",{exact:true}).waitFor();
  assert.equal(await submit.isDisabled(),true);
  page.once("dialog",dialog=>dialog.accept());
  await root.locator('[data-weather-source-action="reload"]').click();
  await page.waitForFunction(()=>!document.querySelector('[data-weather-source-form] button[type="submit"]').disabled);
  await source("credential").fill("eyJhbGciOiJFZERTQSJ9.eyJleHAiOjQxMDI0NDQ4MDB9.fixture_signature");
  await source("refresh_minutes").fill("20");
  await page.evaluate(()=>window.stateQA.weatherDropNext=true);
  await submit.click();
  await root.getByText("保存结果尚未确认。请重新读取配置核对，再填写需要更新的凭据。",{exact:true}).waitFor();
  assert.equal(await source("credential").inputValue(),"");
  assert.equal(await submit.isDisabled(),true);
  const posts=await page.evaluate(()=>window.stateQA.posts.length);
  page.once("dialog",dialog=>dialog.accept());
  await root.locator('[data-weather-source-action="reload"]').click();
  await page.waitForFunction(()=>!document.querySelector('[data-weather-source-form] button[type="submit"]').disabled);
  assert.equal(await page.evaluate(()=>window.stateQA.posts.length),posts);
  assert.equal(await source("refresh_minutes").inputValue(),"20");
  assert.match(await root.innerText(),/JWT 已配置/);
  // Keyboard navigation and explicit clearing use the same real form controls.
  await source("provider").focus();
  await page.keyboard.press("Tab");
  assert.equal(await page.evaluate(()=>document.activeElement?.id),"weather-source-refresh");
  page.once("dialog",dialog=>dialog.accept());
  await root.locator('[data-weather-source-action="clear"]').click();
  await root.getByText("页面凭据已清除，当前来源已更新。",{exact:true}).waitFor();
  assert.equal(await source("api_host").inputValue(),"");
  assert.equal(await source("provider").inputValue(),"auto");
  assert.deepEqual(await page.evaluate(()=>window.stateQA.posts.at(-1).body.changes),{clear_credentials:true});
  assert.deepEqual(errors,[]);
  return {viewports:[1366,390,320],checks:["source, Host and API Key save","blank credential retention","secret not persisted in browser storage","credential input cleared after save","edit conflict","unknown save is checked without automatic replay","JWT support","keyboard controls","clear credentials"]};
}
if(require.main===module)(async()=>{
  const browser=await require("playwright").chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{})});
  try {console.log(JSON.stringify(await run({browser,pageRoot:process.env.COMPANION_PAGE_ROOT,outputDir:process.env.COMPANION_WEATHER_SOURCE_OUTPUT||path.join(require("node:os").tmpdir(),"companion-weather-source-"+Date.now()),inspect}),null,2));}
  finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
module.exports={inspect};
