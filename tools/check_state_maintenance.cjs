/* Physical preferences and explicit simulated-cycle alignment through the state editor. */
const assert=require("node:assert/strict");
const path=require("node:path");

async function run({page,root,button,saved,posts,loadDone,checkWidth,first,secondRole,outputDir}) {
  const field=name=>root.locator("#state-config-"+name);
  const openFeature=async feature=>{
    const trigger=root.locator(`[data-state-feature="${feature}"]`).first();
    if(await trigger.getAttribute("aria-expanded")!=="true"){
      const active=root.locator('[data-state-feature][aria-expanded="true"]').first();
      if(await active.count())await active.click();
      await trigger.click();
    }
    if(await root.locator("#state-edit-form").count())await root.locator('[data-state-edit="cancel"]').click();
  };
  assert.match(await root.locator(".state-feature-detail").innerText(),/健康开启 · 饥饿开启 · 当前人格共享/);
  await button("maintenance").click();
  await field("health_enabled").uncheck();
  await root.getByRole("button",{name:"保存身体状态设置",exact:true}).click();await saved();
  assert.deepEqual((await posts()).at(-1).body.changes,{health_enabled:false});
  assert.equal(await page.evaluate(key=>window.stateQA.values[key].settings.health_enabled,secondRole),true);
  await button("maintenance").click();await field("health_enabled").check();
  await page.evaluate(key=>{const status=window.stateQA.values[key];status.settings.hunger_enabled=false;status.edit_token="concurrent-body";},first);
  await root.getByRole("button",{name:"保存身体状态设置",exact:true}).click();
  await root.getByText("配置已被更新，填写内容已保留。请读取当前版本后核对。",{exact:true}).waitFor();
  assert.equal(await field("health_enabled").isChecked(),true);
  await button("rebase").click();
  await root.getByText("已读取当前版本并保留你的修改，请核对后保存。",{exact:true}).waitFor();
  assert.equal(await field("hunger_enabled").isChecked(),false);
  await root.getByRole("button",{name:"保存身体状态设置",exact:true}).click();await saved();
  assert.deepEqual((await posts()).at(-1).body.changes,{health_enabled:true});

  await openFeature("cycle");
  assert.match(await root.locator(".state-feature-detail").innerText(),/当前人格共享/);
  await button("cycle").click();await field("cycle_timezone").fill("Not/A-Timezone");
  const countBefore=(await posts()).length;
  await root.getByRole("button",{name:"保存生理期参数",exact:true}).click();
  await root.getByText("请填写有效的 IANA 时区，例如 Asia/Shanghai。",{exact:true}).waitFor();
  assert.equal((await posts()).length,countBefore);
  await field("cycle_timezone").fill("Asia/Shanghai");
  await field("cycle_expression_prompt").fill("长".repeat(2049));
  await root.getByRole("button",{name:"保存生理期参数",exact:true}).click();
  await root.getByText("请核对角色表达偏好。",{exact:true}).waitFor();
  assert.equal((await posts()).length,countBefore);
  const preference='自然表达，不反复播报。 </textarea><img src=x onerror="window.injected=true">';
  await field("cycle_expression_prompt").fill(preference);
  const phasePreferences={cycle_menstrual_mood:"沉静",cycle_follicular_mood:"舒展",cycle_pre_ovulation_mood:"盼望",
    cycle_ovulation_mood:"自在",cycle_luteal_mood:"专注",cycle_pms_mood:"敏感而需要安静",
    cycle_pms_prompt:"经前可以少说一点，也可以继续倾听。"};
  await field("cycle_mode").selectOption("six_phase");await field("cycle_menstrual_days").fill("4");
  await field("cycle_variation_enabled").check();
  assert.equal(await field("cycle_discomfort_chance").isDisabled(),true);
  await field("cycle_discomfort_enabled").check();
  assert.equal(await field("cycle_discomfort_chance").isDisabled(),false);
  await field("cycle_link_intensity").check();
  await field("cycle_discomfort_chance").evaluate(el=>{el.value="72";el.dispatchEvent(new Event("input",{bubbles:true}));});
  assert.equal(await root.locator('[data-state-output-for="cycle_discomfort_chance"]').evaluate(el=>el.value),"72%");
  await root.locator('[data-state-field="cycle_discomfort_types"][value="痛经"]').uncheck();
  await root.locator('[data-state-field="cycle_discomfort_types"][value="恶心"]').check();
  assert.equal(await root.locator("[data-cycle-view]").count(),2);
  assert.equal(await root.locator("[data-state-phase]").count(),0);
  await root.locator('#state-cycle-view-plan').focus();await page.keyboard.press("ArrowRight");
  assert.equal(await root.locator('#state-cycle-view-expression').getAttribute("aria-selected"),"true");
  assert.equal(await root.locator("[data-state-phase]").count(),6);
  assert.equal(await root.locator(".state-phase-editor [data-state-field$='_prompt']").count(),1);
  assert.equal(await field("cycle_follicular_prompt").count(),0);
  await root.locator('#state-cycle-phase-menstrual').focus();await page.keyboard.press("ArrowRight");
  assert.equal(await root.locator('#state-cycle-phase-follicular').getAttribute("aria-selected"),"true");
  for(const [name,value] of Object.entries(phasePreferences)){
    const phase=name.replace(/^cycle_/ ,"").replace(/_(?:mood|prompt)$/ ,"");
    await root.locator(`[data-state-phase="${phase}"]`).click();
    await field(name).fill(value);
  }
  await root.locator('[data-cycle-view="plan"]').click();
  assert.equal(await root.locator("[data-cycle-total]").innerText(),"27");
  await root.locator('[data-cycle-view="expression"]').click();
  await root.locator('[data-state-phase="menstrual"]').click();
  await page.setViewportSize({width:320,height:720});
  await checkWidth();
  await page.screenshot({path:path.join(outputDir,"state-cycle-mobile.png"),fullPage:true});
  await page.setViewportSize({width:1366,height:980});await checkWidth();
  await page.screenshot({path:path.join(outputDir,"state-cycle-desktop.png"),fullPage:true});
  await root.getByRole("button",{name:"保存生理期参数",exact:true}).click();await saved();
  assert.deepEqual((await posts()).at(-1).body.changes,{cycle_mode:"six_phase",cycle_variation_enabled:true,
    cycle_discomfort_enabled:true,cycle_link_intensity:true,cycle_discomfort_chance:72,
    cycle_discomfort_types:"头痛,腰酸,乏力,恶心",cycle_menstrual_days:4,
    cycle_expression_prompt:preference,...phasePreferences});
  await button("cycle").click();
  assert.equal(await field("cycle_expression_prompt").inputValue(),preference);
  await root.locator('[data-cycle-view="expression"]').click();
  for(const [name,value] of Object.entries(phasePreferences)){
    const phase=name.replace(/^cycle_/ ,"").replace(/_(?:mood|prompt)$/ ,"");
    await root.locator(`[data-state-phase="${phase}"]`).click();
    assert.equal(await field(name).inputValue(),value,name);
  }
  assert.equal(await root.locator(".state-phase-editor [data-state-field$='_prompt']").count(),1);
  assert.equal(await root.locator(".state-feature-detail img").count(),0);
  assert.equal(await page.evaluate(()=>window.injected),undefined);
  await button("cancel").click();

  await page.setViewportSize({width:320,height:720});
  await button("align").click();
  assert.equal(await root.locator("#state-cycle-action").inputValue(),"");
  assert.equal(await root.locator("#state-cycle-day").isDisabled(),true);
  await root.locator("#state-cycle-action").selectOption("applicable");
  await root.locator("#state-cycle-day").fill("4");
  await page.evaluate(key=>{const status=window.stateQA.values[key];status.settings.cycle_timezone="UTC";status.cycle_settings_token="concurrent-cycle-settings";},first);
  await root.getByRole("button",{name:"确认周期校准",exact:true}).click();
  await root.getByText("周期配置已变化，填写内容已保留。请读取当前参数后核对校准。",{exact:true}).waitFor();
  assert.equal(await root.locator("#state-cycle-day").inputValue(),"4");
  await button("rebase").click();
  await root.getByText("已读取当前版本并保留你的修改，请核对后保存。",{exact:true}).waitFor();
  assert.match(await root.locator("#state-edit-form").innerText(),/时区 UTC/);
  await page.evaluate(key=>{const state=window.stateQA.values[key].state;state.revision++;state.view_token="concurrent-state";},first);
  await root.getByRole("button",{name:"确认周期校准",exact:true}).click();
  await root.getByText("角色状态已变化，填写内容已保留。请读取当前版本后核对校准。",{exact:true}).waitFor();
  await button("rebase").click();
  await root.getByText("已读取当前版本并保留你的修改，请核对后保存。",{exact:true}).waitFor();
  await page.evaluate(()=>{window.stateQA.dropNext=true;});
  await root.getByRole("button",{name:"确认周期校准",exact:true}).click();
  await root.getByText("有一笔保存尚待核对",{exact:true}).waitFor();
  const original=(await posts()).at(-1),applied=await page.evaluate(()=>window.stateQA.applied),sent=(await posts()).length;
  assert.deepEqual(original.body.data,{applicability:"applicable",day:4});
  assert.equal(original.body.settings_token,"concurrent-cycle-settings");
  assert.equal(original.body.view_token,"concurrent-state");
  await page.reload();await root.waitFor();await loadDone();
  assert.equal(await root.locator('[data-state-feature="cycle"]').getAttribute("aria-expanded"),"true");
  await root.getByText("有一笔保存尚待核对",{exact:true}).waitFor();
  assert.equal((await posts()).length,sent);
  await button("recover").click();await saved();
  assert.deepEqual((await posts()).at(-1),original);
  assert.equal(await page.evaluate(()=>window.stateQA.applied),applied);
  await button("align").click();await root.locator("#state-cycle-action").selectOption("auto");
  assert.equal(await root.locator("#state-cycle-day").isDisabled(),true);
  await root.getByRole("button",{name:"确认周期校准",exact:true}).click();await saved();
  assert.deepEqual((await posts()).at(-1).body.data,{applicability:"auto",day:null});
  await button("cycle").click();await field("cycle_enabled").uncheck();
  await root.getByRole("button",{name:"保存生理期参数",exact:true}).click();await saved();
  assert.equal(await button("align").isDisabled(),true);
  return {checks:"minimal maintenance/cycle patches, shared-scope labels, conflict rebase preserves other settings, timezone/prompt validation and escaping, settings and state guarded calibration, original receipt recovery across reload, auto release, disabled-cycle control",
    screenshots:[path.join(outputDir,"state-cycle-desktop.png"),path.join(outputDir,"state-cycle-mobile.png")]};
}
module.exports={run};
