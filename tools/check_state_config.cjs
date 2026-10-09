"use strict";
/* Validate the state subpages against a synthetic host. No real writes or sends. */
const assert=require("node:assert/strict");
const fs=require("node:fs/promises");
const path=require("node:path");
const {run}=require("./check_state_page.cjs");

async function inspect({page,rootPage,checkWidth,loadDone,errors,outputDir,first,secondRole,secondTarget,requestId}) {
  const root=rootPage(),detail=()=>root.locator("#state-feature-detail");
  assert.deepEqual(await root.locator(".state-board-point").evaluateAll(nodes=>nodes.map(node=>node.dataset.stateFeature)),
    ["energy","health","hunger","sleep","cycle","mood","busy","location"]);
  assert.match(await root.innerText(),/72 \/ 100/);
  assert.equal(await root.locator("script").count(),0);
  assert.equal(await page.evaluate(()=>window.injected),undefined);
  const open=async feature=>{
    await root.locator(`[data-state-feature="${feature}"]`).click();
    await detail().waitFor();
    assert.equal(await detail().getAttribute("data-state-config-feature"),feature);
  };
  const save=async(surface=detail())=>{
    const before=await page.evaluate(()=>window.stateQA.posts.length);
    await surface.locator('#state-edit-form button[type="submit"]').click();
    await page.waitForFunction(count=>window.stateQA.posts.length===count+1,before);
    await page.waitForFunction(()=>document.querySelector("#roleStateWorkspace")?.textContent.includes("已保存，请查看最新生效情况。"));
    return page.evaluate(()=>window.stateQA.posts.at(-1).body);
  };
  const close=async()=>{
    if(await detail().locator('[data-state-edit="cancel"]').count())await detail().locator('[data-state-edit="cancel"]').click();
    await detail().locator(".state-feature-back").click();
    assert.equal(await detail().count(),0);
  };
  const screenshot=async(name,width)=>{
    await page.setViewportSize({width,height:980});
    try{await checkWidth();}catch(problem){
      await page.screenshot({path:path.join(outputDir,`${name}-${width}-overflow.png`),fullPage:true});
      const overflow=await page.evaluate(()=>[...document.querySelectorAll("*")].filter(item=>{
        const box=item.getBoundingClientRect();return box.width>3&&(box.left<0||box.right>innerWidth+1);
      }).slice(0,12).map(item=>({tag:item.tagName,id:item.id,class:item.className,text:item.textContent.slice(0,60)})));
      console.error(`${name} at ${width}px: ${JSON.stringify(overflow)}`);
      throw problem;
    }
    const fits=await detail().evaluate(node=>[...node.querySelectorAll("input,select,textarea,button")].filter(item=>{
      const box=item.getBoundingClientRect();return box.width>3&&box.height>3&&(box.left<0||box.right>innerWidth+1);
    }).map(item=>item.id||item.textContent));
    assert.deepEqual(fits,[],`${name} controls at ${width}px`);
    await detail().screenshot({path:path.join(outputDir,`${name}-${width}.png`)});
  };
  const previews=[];
  const gear=page.locator("#state-settings-button"),settings=()=>root.locator("#state-home-settings");
  assert.equal(await gear.evaluate(node=>node.previousElementSibling?.tagName==="H2"&&node.previousElementSibling.textContent==="状态"),true);
  assert.equal(await root.locator(".state-settings-zone").count(),0);
  assert.equal(await root.locator(".state-extra-card").count(),4);
  assert.equal(await root.locator('#state-extra-patrol,#state-extra-time,#state-extra-date').count(),0);
  for(const name of ["presentation","planning","weather","datetime"])
    assert.equal(await root.locator("#state-extra-"+name).isVisible(),true,name+" entry");
  for(const width of [1366,390,320]) {
    await page.setViewportSize({width,height:980});await checkWidth();
    await page.screenshot({path:path.join(outputDir,`status-overview-${width}.png`)});
  }
  await page.setViewportSize({width:1366,height:980});
  await open("health");await gear.click();
  assert.equal(await settings().evaluate(node=>node.open),true);
  assert.equal(await settings().locator("[data-state-home-feature]").count(),8);
  assert.equal(await settings().locator('[data-state-field$="_enabled"]').count(),8);
  assert.equal(await settings().locator('[data-state-field="enabled"]').count(),1);
  assert.equal(await settings().locator('[data-state-field^="home_show_"]').count(),8);
  assert.equal(await settings().locator("[data-state-display-policy]").count(),5);
  for(const width of [1366,390,320]) {
    await page.setViewportSize({width,height:980});await checkWidth();
    assert.equal(await settings().evaluate(node=>node.scrollWidth>node.clientWidth),false);
    await page.screenshot({path:path.join(outputDir,`status-settings-${width}.png`)});
  }
  await page.setViewportSize({width:1366,height:980});
  previews.push({feature:"home",title:"状态功能与首页展示",html:await settings().evaluate(node=>node.outerHTML.replace("<dialog","<section").replace("</dialog>","</section>"))});
  await page.keyboard.press("Escape");
  assert.equal(await settings().count(),0);
  assert.equal(await detail().getAttribute("data-state-config-feature"),"health");
  assert.equal(await gear.evaluate(node=>node===document.activeElement),true);
  await close();
  await gear.click();
  for(const name of ["health","hunger","sleep","cycle","busy"])
    await settings().locator(`[data-state-field="home_only_special_${name}"]`).selectOption("special");
  await settings().locator('[data-state-field="energy_enabled"]').uncheck();
  await settings().locator('[data-state-field="home_show_mood"]').uncheck();
  assert.equal(await settings().locator("[data-state-home-count]").innerText(),"6 项允许展示");
  await settings().locator('[data-state-field="home_show_sleep"]').uncheck();
  assert.equal(await settings().locator('[data-state-field="home_only_special_sleep"]').isDisabled(),true);
  await settings().locator('[data-state-field="home_show_sleep"]').check();
  assert.equal(await settings().locator('[data-state-field="home_only_special_sleep"]').inputValue(),"special");
  await page.keyboard.press("Escape");
  assert.equal(await settings().evaluate(node=>node.open),true,"Escape keeps an unsaved draft");
  await page.evaluate(()=>window.navigate("manage","perception"));
  assert.equal(await page.evaluate(()=>location.hash),"#life/state");
  assert.equal(await settings().evaluate(node=>node.open),true);
  const homeSaved=await save(settings());
  assert.deepEqual(homeSaved.changes,{energy_enabled:false,home_show_mood:false,
    home_only_special_health:true,home_only_special_hunger:true,home_only_special_sleep:true,home_only_special_cycle:true,home_only_special_busy:true});
  assert.equal(await settings().locator('[data-state-field="energy_enabled"]').isChecked(),false);
  await settings().locator('[data-state-field="energy_enabled"]').check();
  await settings().locator('[data-state-edit="reset"]').click();
  assert.equal(await settings().locator('[data-state-field="energy_enabled"]').isChecked(),false);
  await settings().locator('[data-state-field="energy_enabled"]').check();
  await settings().locator('[data-state-edit="cancel"]').click();
  assert.equal(await settings().count(),0);
  await gear.click();assert.equal(await settings().locator('[data-state-field="energy_enabled"]').isChecked(),false);
  await settings().locator('[data-state-field="energy_enabled"]').check();
  await settings().locator('[data-state-field="home_show_mood"]').check();
  await save(settings());
  await page.mouse.click(4,4);assert.equal(await settings().count(),0,"backdrop closes a clean draft");

  // A shared field must restore the panel that originally authored the request.
  await gear.click();await settings().locator('[data-state-field="health_enabled"]').uncheck();
  await page.evaluate(()=>{window.stateQA.dropNext=true;});
  await settings().locator('button[type="submit"]').click();
  await settings().getByText("保存结果尚未确认。",{exact:false}).waitFor();
  const homeOriginal=await page.evaluate(()=>window.stateQA.posts.at(-1));
  await page.reload();await loadDone();
  await settings().getByText("有一笔保存尚待核对",{exact:true}).waitFor();
  assert.equal(await settings().evaluate(node=>node.open),true);
  await settings().locator('[data-state-edit="recover"]').click();
  await settings().getByText("已核对原请求：保存成功。",{exact:false}).waitFor();
  assert.deepEqual(await page.evaluate(()=>window.stateQA.posts.at(-1)),homeOriginal);
  await settings().locator('[data-state-field="health_enabled"]').check();await save(settings());
  await settings().locator('[data-state-close-home-settings]').click();
  await open("health");await detail().locator('[data-state-field="health_enabled"]').uncheck();
  await page.evaluate(()=>{window.stateQA.dropNext=true;});
  await detail().locator('button[type="submit"]').click();
  await detail().getByText("保存结果尚未确认。",{exact:false}).waitFor();
  await page.reload();await loadDone();
  assert.equal(await settings().count(),0);
  assert.equal(await detail().getAttribute("data-state-config-feature"),"health");
  await detail().locator('[data-state-edit="recover"]').click();
  await detail().getByText("已核对原请求：保存成功。",{exact:false}).waitFor();
  await detail().locator('[data-state-field="health_enabled"]').check();await save();await close();

  const features=["energy","health","hunger","sleep","cycle","mood","busy","location","planning","weather","datetime","presentation"];
  for(const feature of features) {
    await open(feature);
    assert.equal(await detail().locator(".state-workspace-overview").count(),1,feature);
    const readonly=["sleep","busy","location"].includes(feature);
    assert.equal(await detail().locator("#state-edit-form").count(),readonly?0:1,feature);
    const inputCount=await detail().locator("[data-state-field]").count();
    assert.equal(readonly?inputCount===0:inputCount>0,true,feature);
    await screenshot(feature,1366);await screenshot(feature,390);await screenshot(feature,320);
    await page.setViewportSize({width:1366,height:980});
    previews.push({feature,title:await detail().locator("#state-feature-title").innerText(),html:await detail().evaluate(node=>node.outerHTML)});
    if(feature==="cycle") {
      await detail().locator('[data-cycle-view="expression"]').click();
      await detail().locator('[data-state-phase="pms"]').click();
      await detail().locator('[data-state-field="cycle_pms_energy"]').fill("-15");
      await detail().locator('[data-state-field="cycle_pms_prompt"]').fill("先按实际感受表达，再自然接续话题。");
      await detail().locator('[data-cycle-view="plan"]').click();
      await detail().locator('[data-state-field="cycle_menstrual_days"]').fill("6");
      assert.equal(await detail().locator("[data-cycle-total]").innerText(),"29");
      const body=await save();
      assert.equal(body.changes.cycle_pms_energy,-15);
      assert.equal(body.changes.cycle_pms_prompt,"先按实际感受表达，再自然接续话题。");
      assert.equal(body.changes.cycle_menstrual_days,6);
      await detail().locator('[data-state-edit="align"]').click();
      await detail().locator('[data-state-field="applicability"]').selectOption("applicable");
      await detail().locator('[data-state-field="day"]').fill("3");
      const aligned=await save();assert.equal(aligned.action,"cycle.align");assert.equal(aligned.data.day,3);
    }
    if(feature==="sleep")assert.equal(await detail().locator("[data-state-open-life-sleep]").count(),1);
    if(feature==="location")assert.doesNotMatch(await detail().innerText(),/\d+\s*\/\s*100/);
    if(feature==="datetime") {
      await detail().locator('[data-state-field="planning_timezone"]').fill("Asia/Tokyo");
      const body=await save();assert.deepEqual(body.changes,{planning_timezone:"Asia/Tokyo"});
      assert.match(await root.locator("#state-extra-datetime").innerText(),/Asia\/Tokyo/);
      await detail().locator('[data-state-field="planning_timezone"]').fill("Asia/Shanghai");await save();
    }
    if(feature==="weather") {
      await detail().locator('[data-state-weather-location="name"]').fill("杭州");
      assert.equal(await detail().locator("[data-state-draft-hint]").isVisible(),true);
      assert.equal(await detail().locator('[data-state-edit="reset"]').isEnabled(),true);
      await detail().locator('[data-state-field="planning_weather_enabled"]').check({force:true});
      const body=await save();assert.equal(JSON.parse(body.changes.planning_weather_location).name,"杭州");
      assert.equal(body.changes.planning_weather_enabled,true);
    }
    if(feature==="presentation") {
      assert.match(await detail().innerText(),/确认未知/);
      assert.doesNotMatch(await detail().innerText(),new RegExp(requestId));
      await detail().locator('[data-state-field="typing_refresh_seconds"]').fill("5");
      const body=await save();assert.equal(body.changes.typing_refresh_seconds,5);
    }
    await close();
  }
  await open("energy");
  const intensity=detail().locator('[data-state-field="humanized_state_intensity"]');
  await intensity.focus();await page.keyboard.press("ArrowRight");
  assert.equal(await detail().locator("#state-config-humanized_state_intensity-output").innerText(),"51 / 100");
  assert.equal(await detail().locator("[data-state-draft-hint]").isVisible(),true);
  await detail().locator(".state-feature-back").click();
  assert.equal(await detail().count(),1);
  await page.evaluate(()=>window.navigate("manage","perception"));
  assert.equal(await detail().count(),1);assert.equal(await page.evaluate(()=>location.hash),"#life/state");
  await detail().locator('[data-state-edit="reset"]').click();
  assert.equal(await intensity.inputValue(),"50");
  await intensity.focus();await page.keyboard.press("ArrowRight");
  const energySaved=await save();assert.equal(energySaved.changes.humanized_state_intensity,51);
  assert.equal(await intensity.inputValue(),"51");
  assert.equal(await detail().locator("[data-state-draft-hint]").isVisible(),false);
  await close();

  // Losing a response after commit must retain the original operation key.
  await open("health");
  await detail().locator('[data-state-field="health_expression_prompt"]').fill("按实际体感表达。");
  await page.evaluate(()=>{window.stateQA.dropNext=true;});
  await detail().locator('button[type="submit"]').click();
  await detail().getByText("保存结果尚未确认。",{exact:false}).waitFor();
  const original=await page.evaluate(()=>window.stateQA.posts.at(-1));
  const applied=await page.evaluate(()=>window.stateQA.applied);
  await detail().locator('[data-state-edit="recover"]').click();
  await detail().getByText("已核对原请求：保存成功。",{exact:false}).waitFor();
  assert.deepEqual(await page.evaluate(()=>window.stateQA.posts.at(-1)),original);
  assert.equal(await page.evaluate(()=>window.stateQA.applied),applied);
  assert.equal(await detail().locator('[data-state-field="health_expression_prompt"]').inputValue(),"按实际体感表达。");
  await close();

  // A concurrent change keeps this draft, and rebase picks up untouched fields.
  await open("presentation");
  await detail().locator('[data-state-field="typing_refresh_seconds"]').fill("7");
  await page.evaluate(first=>{
    const status=window.stateQA.values[first];
    status.settings.typing_refresh_seconds=6;status.settings.presence_enabled=false;
    status.edit_token="concurrent-version";
  },first);
  await detail().locator('#state-edit-form button[type="submit"]').click();
  await detail().getByText("配置已被更新，填写内容已保留。请读取当前版本后核对。",{exact:true}).waitFor();
  assert.equal(await detail().locator('[data-state-field="typing_refresh_seconds"]').inputValue(),"7");
  await detail().locator('[data-state-edit="rebase"]').click();
  await detail().getByText("已读取当前版本并保留你的修改，请核对后保存。",{exact:true}).waitFor();
  assert.equal(await detail().locator('[data-state-field="presence_enabled"]').isChecked(),false);
  const rebased=await save();
  assert.deepEqual(rebased.changes,{typing_refresh_seconds:7});
  assert.equal(rebased.edit_token,"concurrent-version");
  assert.equal(await page.evaluate(()=>window.stateQA.posts.at(-1).endpoint),first+"/command");
  const summary=detail().locator(".state-receipt-reference summary").first();
  await summary.focus();await page.keyboard.press("Enter");
  const history=await detail().locator(".state-receipts").innerText();
  const reads=await page.evaluate(()=>window.stateQA.loadCount);
  await page.evaluate(()=>document.getElementById("state-refresh").click());
  await page.waitForFunction(count=>window.stateQA.loadCount>count,reads);await loadDone();
  assert.equal(await summary.evaluate(node=>node.parentElement.open),true);
  assert.equal(await page.evaluate(()=>document.activeElement?.id),"state-receipt-summary-0");
  assert.equal(await detail().locator(".state-receipts").innerText(),history);
  assert.doesNotMatch(await detail().innerText(),new RegExp(requestId));
  await close();

  await page.locator("#product-role").selectOption("望舒");await loadDone();
  await root.getByText("黄体期 · 第 2 / 5 天",{exact:true}).waitFor();
  await open("presentation");
  assert.match(await detail().innerText(),/同一 QQ 账号有多个展示窗口/);
  assert.match(await detail().innerText(),/旧确认未记录时间/);
  await detail().locator(".state-receipt-reference summary").click();
  assert.equal(await detail().locator("script,.state-presentation img,.state-presentation b").count(),0);
  assert.equal(await page.evaluate(()=>window.injected),undefined);
  assert.equal(await page.evaluate(key=>window.stateQA.values[key].settings.typing_refresh_seconds,secondRole),4);
  await close();
  await page.evaluate(()=>window.CompanionProduct.choose("second","澄汐"));await loadDone();
  await root.getByText("排卵期 · 第 2 / 5 天",{exact:true}).waitFor();
  await open("presentation");
  assert.match(await detail().innerText(),/未安装 QQ 展示端口/);
  assert.equal(await page.evaluate(key=>window.stateQA.calls.includes(key),secondTarget),true);
  await close();
  await page.evaluate(()=>window.CompanionProduct.choose("group","澄汐"));await loadDone();
  assert.equal(await page.evaluate(()=>window.CompanionProduct.roleTarget().target_id),"first");
  assert.equal(await page.evaluate(()=>window.stateQA.posts.some(post=>post.endpoint.includes("targets/group/"))),false);
  await page.evaluate(()=>window.CompanionProduct.choose("first","澄汐"));await loadDone();

  await open("datetime");await detail().locator("[data-state-date-settings]").click();
  assert.equal(await page.evaluate(()=>location.hash),"#manage/perception");
  try{await page.locator("#config-models").waitFor({state:"visible",timeout:5000});}catch(problem){
    console.error(JSON.stringify({errors,state:await page.evaluate(()=>['perceptionConfigWorkspace','config-models','perception-tab-config-models','perception-detail-context'].map(id=>{
      const node=document.getElementById(id);return {id,exists:!!node,hidden:node?.hidden,open:node?.open,class:node?.className,display:node?getComputedStyle(node).display:null};
    }))}));throw problem;
  }
  assert.equal(await page.locator("#perception-detail-context").evaluate(node=>node.open),true);
  await page.evaluate(()=>window.navigate("life","state"));await loadDone();

  // Patrol keeps its working editor under maintenance, without a state overview.
  await page.evaluate(()=>window.navigate("manage","maintenance","patrol"));await loadDone();
  assert.equal(await page.evaluate(()=>location.hash),"#manage/maintenance/patrol");
  assert.equal(await root.locator(".state-dashboard,.state-extra-nav").count(),0);
  assert.equal(await detail().getAttribute("data-state-config-feature"),"patrol");
  await detail().locator('[data-state-adjust="daily_state_patrol_retention_days"][data-state-step="1"]').click();
  assert.equal(await detail().locator('[data-state-field="daily_state_patrol_retention_days"]').inputValue(),"31");
  const patrolSaved=await save();assert.equal(patrolSaved.changes.daily_state_patrol_retention_days,31);
  await screenshot("maintenance-patrol",1366);await screenshot("maintenance-patrol",390);await screenshot("maintenance-patrol",320);
  await page.setViewportSize({width:1366,height:980});
  await page.evaluate(()=>window.navigate("life","state"));await loadDone();

  await open("planning");
  await detail().locator('[data-calendar-edit="create"]').click();
  assert.equal(await detail().locator("#state-calendar-form").count(),1);
  await detail().locator('[data-calendar-edit="close"]').click();
  await close();
  await open("sleep");await detail().locator("[data-state-open-life-sleep]").click();
  assert.equal(await page.evaluate(()=>location.hash),"#life/diary/sleep");
  const styles=await page.evaluate(async()=>{
    const names=["tokens.css","styles.css","memory-page.css","state-page.css","state-config.css"];
    return (await Promise.all(names.map(name=>fetch(name).then(response=>response.text())))).join("\n");
  });
  const html=`<!doctype html>\n<html lang="zh-CN" data-theme="garden"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>状态子页 · 实施预览</title><style>${styles}\nbody{margin:0;padding:24px;background:var(--t-canvas);font-family:MiSans,"Microsoft YaHei",sans-serif}.preview-nav{position:sticky;top:0;z-index:10;display:flex;flex-wrap:wrap;gap:8px;padding:12px;background:var(--t-canvas)}.preview-nav a{color:var(--t-ok-ink);font-size:14px}.preview-main{max-width:1160px;margin:auto}.state-feature-detail{scroll-margin-top:100px}.state-feature-back,.state-feature-close{display:none!important}</style></head><body><nav class="preview-nav">${previews.map(({feature,title})=>`<a href="#preview-${feature}">${title}</a>`).join(" ")}</nav><main class="preview-main"><p>合成数据 · 配置布局预览</p>${previews.map(({feature,html})=>html.replace('id="state-feature-detail"',`id="preview-${feature}"`)).join("\n")}</main></body></html>\n`;
  await fs.writeFile(path.join(outputDir,"implementation-preview.html"),html,"utf8");
  await page.evaluate(()=>window.navigate("life","state"));await loadDone();
  await page.evaluate(()=>{window.stateQA.deny=true;});
  await root.locator("#state-refresh").click();
  await root.getByText("当前账号没有角色状态管理权限。",{exact:true}).waitFor();
  assert.equal(await root.locator("#state-edit-form,.state-dashboard,.state-receipts").count(),0);
  assert.deepEqual(errors,[]);
  return {features:features.length,viewports:[1366,390,320],checks:["title settings dialog and 8 feature switches","5 special-value display policies","modal focus, Escape, backdrop and draft guard","pending panel restoration after reload","4 prominent entries with combined time/date","patrol moved to maintenance with working save","save/reset/cancel","cycle expression and alignment","weather","QQ settings and diagnostics","draft navigation guard","lost response recovery","conflict rebase","receipt focus and history","role/target separation","XSS escaping and permission revocation","calendar and sleep navigation"],preview:path.join(outputDir,"implementation-preview.html")};
}

if(require.main===module)(async()=>{
  const browser=await require("playwright").chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{})});
  try {console.log(JSON.stringify(await run({browser,pageRoot:process.env.COMPANION_PAGE_ROOT,outputDir:process.env.COMPANION_STATE_CONFIG_OUTPUT||path.join(require("node:os").tmpdir(),"companion-state-config-"+Date.now()),inspect}),null,2));}
  finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
module.exports={inspect};
