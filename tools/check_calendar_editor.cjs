/* Role-plan management acceptance checks, exercised by check_state_page.cjs. */
const assert=require("node:assert/strict");
const path=require("node:path");

async function run({page,rootPage,loadDone,checkWidth,first,secondRole,outputDir}) {
  const root=rootPage();
  const calendarSaved=async()=>{await page.waitForFunction(()=>!document.querySelector("#state-calendar-form")&&!document.querySelector("#state-refresh")?.disabled);};
  const posts=()=>page.evaluate(()=>window.stateQA.posts);
  const bodyAt=async index=>{const rows=await posts();return rows[index]?.body;};
  const current=async()=>page.evaluate(key=>window.stateQA.values[key],first);
  const clickAction=(action,index)=>root.locator(`[data-calendar-edit="${action}"][data-index="${index}"]`);
  const fillPlan=async(title,start="2026-09-26T10:30")=>{
    await root.locator("#calendar-title").fill(title);
    await root.locator("#calendar-detail").fill("角色计划详情");
    await root.locator("#calendar-presence").fill("专注中");
    await root.locator("#calendar-start").fill(start);
    await root.locator("#calendar-timezone").fill("Asia/Shanghai");
    await root.locator("#calendar-frequency").selectOption("weekly");
    await root.locator("#calendar-interval").fill("1");
    await root.locator("#calendar-count").fill("4");
    await root.locator("#calendar-duration").fill("45");
  };

  // Automatic role access is independent from core calendar management.
  await page.evaluate(key=>{window.stateQA.values[key].settings.calendar_enabled=false;
    window.stateQA.values[key].effective.calendar_enabled={allowed:false,reason:null};},first);
  await root.locator("#state-refresh").click();await loadDone();
  await root.getByRole("button",{name:"创建角色计划",exact:true}).click();
  await fillPlan("阅读新计划","2026-09-27T10:30");
  for(const width of [320,390,1366]){
    await page.setViewportSize({width,height:width===1366?980:844});await checkWidth();
    await root.locator("#calendar-title").scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(outputDir,`calendar-create-${width}.png`)});
  }
  const beforeDraftRead=await page.evaluate(()=>window.stateQA.loadCount);
  await page.evaluate(()=>document.dispatchEvent(new Event("visibilitychange")));
  assert.equal(await page.evaluate(()=>window.stateQA.loadCount),beforeDraftRead);
  await root.locator("#calendar-fold").focus();await page.keyboard.press("Tab");
  assert.equal(await page.evaluate(()=>document.activeElement?.textContent),"创建角色计划");
  await page.evaluate(()=>{window.stateQA.dropNext=true;});
  await page.keyboard.press("Enter");
  await root.getByText("有一笔日程保存尚待核对",{exact:true}).waitFor();
  const pendingCreate=(await posts()).at(-1),createdCount=await page.evaluate(()=>window.stateQA.applied),createPosts=(await posts()).length;
  await page.reload();await root.waitFor();await loadDone();
  await root.getByText("有一笔日程保存尚待核对",{exact:true}).waitFor();
  assert.equal((await posts()).length,createPosts);
  await root.locator('[data-calendar-edit="recover"]').click();
  await calendarSaved();
  assert.deepEqual((await posts()).at(-1),pendingCreate);
  assert.equal(await page.evaluate(()=>window.stateQA.applied),createdCount);
  assert.equal((await current()).calendar.items.filter(item=>item.title==="阅读新计划").length,1);
  let requests=await posts(),created=await bodyAt(requests.length-1);
  assert.equal(created.action,"calendar.create");
  assert.equal(created.data.kind,"role_plan");
  assert.equal(created.data.title,"阅读新计划");
  assert.equal(created.data.schedule.frequency,"weekly");
  assert.equal(created.data.duration_minutes,45);
  assert.equal(created.view_token,(await current()).create_token);
  assert.equal(created.expected_revision,0);
  assert.equal(created.data.schedule.anchor,"2026-09-27T02:30:00.000Z");
  assert.equal(created.data.presence,"专注中");
  assert.match(await root.innerText(),/阅读新计划/);

  await clickAction("revise",0).click();
  await fillPlan("周末阅读改期","2026-09-28T11:00");
  await root.locator("#calendar-frequency").selectOption("monthly");
  await root.locator("#calendar-count").fill("3");
  await root.getByRole("button",{name:"保存整个日程",exact:true}).click();await calendarSaved();
  requests=await posts();let revised=await bodyAt(requests.length-1);
  assert.equal(revised.action,"calendar.revise");
  assert.deepEqual(revised.sources,[{source_id:"original"}]);
  assert.equal(revised.data.schedule.frequency,"monthly");
  const afterRevise=await current();
  const revisedRow=afterRevise.calendar.items.find(item=>item.id==="plan-a");
  assert.deepEqual(revisedRow.exceptions,{});
  assert.equal(revisedRow.reminder_id,null);
  assert.equal(revisedRow.sources[0].source_id,"original");
  assert.equal(await page.evaluate(key=>window.stateQA.cancelledReminders.some(item=>item.key===key&&item.id==="reminder-original"),first),true);

  await clickAction("exception",0).click();
  await root.locator("#calendar-sequence").fill("3");
  await root.locator("#calendar-exception-mode").selectOption("skip");
  await root.getByRole("button",{name:"保存这次修改",exact:true}).click();await calendarSaved();
  requests=await posts();let skipped=await bodyAt(requests.length-1);
  assert.equal(skipped.action,"calendar.exception");
  assert.deepEqual(skipped.data,{sequence:2,start:null});
  let afterException=await current();
  let exceptionRow=afterException.calendar.items.find(item=>item.id==="plan-a");
  assert.equal(exceptionRow.schedule.frequency,"monthly");
  assert.equal(exceptionRow.exceptions["2"],null);

  await clickAction("exception",0).click();
  await root.locator("#calendar-sequence").fill("2");
  await root.locator("#calendar-exception-start").fill("2026-12-30T11:00");
  await root.getByRole("button",{name:"保存这次修改",exact:true}).click();await calendarSaved();
  requests=await posts();let moved=await bodyAt(requests.length-1);
  assert.equal(moved.action,"calendar.exception");
  assert.equal(moved.data.sequence,1);
  assert.match(moved.data.start,/^2026-12-30T03:00:00\.000Z$/);
  afterException=await current();exceptionRow=afterException.calendar.items.find(item=>item.id==="plan-a");
  assert.equal(exceptionRow.schedule.frequency,"monthly");
  assert.match(exceptionRow.exceptions["1"],/^2026-12-30T03:00:00\.000Z$/);

  await clickAction("remind",0).click();
  await root.locator("#calendar-reminder-sequence").fill("2");
  await root.locator("#state-calendar-form").getByRole("button",{name:"安排提醒",exact:true}).click();await calendarSaved();
  requests=await posts();let reminded=await bodyAt(requests.length-1);
  assert.equal(reminded.action,"calendar.remind");assert.equal(reminded.sequence,1);
  let afterRemind=await current();
  assert.match(afterRemind.calendar.items.find(item=>item.id==="plan-a").reminder_id,/^reminder-/);

  await clickAction("cancel",0).click();
  await root.getByRole("button",{name:"确认取消",exact:true}).click();await calendarSaved();
  requests=await posts();let cancelled=await bodyAt(requests.length-1);
  assert.equal(cancelled.action,"calendar.cancel");
  const afterCancel=await current(),cancelledRow=afterCancel.calendar.items.find(item=>item.id==="plan-a");
  assert.equal(cancelledRow.state,"cancelled");assert.equal(cancelledRow.reminder_id,null);
  assert.match(await root.innerText(),/已取消/);

  // A revision conflict keeps the plan draft and requires an explicit rebase.
  await clickAction("revise",1).click();
  await root.locator("#calendar-title").fill("冲突后的计划");
  await page.evaluate(key=>{
    const item=window.stateQA.values[key].calendar.items.find(row=>row.title==="阅读新计划");
    item.revision++;item.view_token="calendar-concurrent";item.detail="另一处更新的详情";
  },first);
  await root.getByRole("button",{name:"保存整个日程",exact:true}).click();
  await root.getByText("日程已被更新，填写内容已保留。请读取当前版本后核对。",{exact:true}).waitFor();
  assert.equal(await root.locator("#calendar-title").inputValue(),"冲突后的计划");
  await root.getByRole("button",{name:"读取当前版本继续编辑",exact:true}).click();
  await root.getByText("已读取当前日程并保留你的修改，请核对后保存。",{exact:true}).waitFor();
  assert.equal(await root.locator("#calendar-title").inputValue(),"冲突后的计划");
  await root.getByRole("button",{name:"保存整个日程",exact:true}).click();await calendarSaved();
  requests=await posts();revised=await bodyAt(requests.length-1);
  assert.equal(revised.action,"calendar.revise");assert.equal(revised.expected_revision,2);assert.equal(revised.view_token,"calendar-concurrent");
  assert.equal(revised.data.detail,"另一处更新的详情");

  // Exception and cancel also require an explicit conflict refresh.
  for(const kind of ["exception","cancel"]){
    await clickAction(kind,1).click();
    if(kind==="exception")await root.locator("#calendar-sequence").fill("2");
    await page.evaluate(({key,kind})=>{const item=window.stateQA.values[key].calendar.items[1];
      item.revision++;item.view_token="concurrent-"+kind;}, {key:first,kind});
    const submit=root.locator("#state-calendar-form button[type=submit]");
    await submit.click();
    await root.getByText("日程已被更新，填写内容已保留。请读取当前版本后核对。",{exact:true}).waitFor();
    assert.equal(await submit.isDisabled(),true);
    if(kind==="exception")assert.equal(await root.locator("#calendar-sequence").inputValue(),"2");
    await root.locator('[data-calendar-edit="rebase"]').click();
    await root.getByText("已读取当前日程并保留你的修改，请核对后保存。",{exact:true}).waitFor();
    if(kind==="exception"){await submit.click();await calendarSaved();}
    else await root.locator('[data-calendar-edit="close"]').click();
  }

  // A lost response is recovered with the exact original operation and body.
  await clickAction("remind",1).click();
  await page.evaluate(()=>{window.stateQA.dropNext=true;});
  await root.locator("#state-calendar-form").getByRole("button",{name:"安排提醒",exact:true}).click();
  await root.getByText("有一笔日程保存尚待核对",{exact:true}).waitFor();
  const uncertain=await bodyAt((await posts()).length-1),appliedBefore=await page.evaluate(()=>window.stateQA.applied),sentBefore=(await posts()).length;
  assert.doesNotMatch(await root.locator(".state-pending").innerText(),/冲突后的计划|另一处更新的详情/);
  await page.reload();await root.waitFor();await loadDone();
  assert.match(await root.innerText(),/有一笔日程保存尚待核对/);
  assert.equal((await posts()).length,sentBefore);
  await root.getByRole("button",{name:"用原请求核对",exact:true}).click();await calendarSaved();
  const recovered=await bodyAt((await posts()).length-1);
  assert.deepEqual(recovered,uncertain);assert.equal(await page.evaluate(()=>window.stateQA.applied),appliedBefore);
  assert.match(await root.innerText(),/已核对原请求：日程保存成功/);

  // A delayed calendar response is scoped to the original role.
  await clickAction("revise",1).click();
  await root.locator("#calendar-title").fill("迟到的首角色计划");
  await page.evaluate(()=>{window.stateQA.holdNext=true;});
  await root.getByRole("button",{name:"保存整个日程",exact:true}).click();
  await page.waitForFunction(()=>typeof window.stateQA.release==="function");
  await page.locator("#product-role").selectOption("望舒");await loadDone();
  await page.evaluate(()=>window.stateQA.release());
  await page.waitForFunction(key=>window.stateQA.values[key].calendar.items.some(item=>item.title==="迟到的首角色计划"),first);
  assert.equal(await page.evaluate(key=>window.stateQA.values[key].calendar.items[0].title,secondRole),"周末阅读 <script>window.injected=true</script>");
  assert.doesNotMatch(await root.innerText(),/迟到的首角色计划|日程已保存/);
  await page.locator("#product-role").selectOption("澄汐");await loadDone();
  const planningTrigger=root.locator('[data-state-feature="planning"]').first();
  if(await planningTrigger.getAttribute("aria-expanded")!=="true")await planningTrigger.click();

  // Date inputs must map to the selected timezone, including both DST boundaries.
  for(const [start,fold,gap,expected] of [
    ["2026-03-08T03:30","0","reject","2026-03-08T07:30:00.000Z"],
    ["2026-11-01T01:30","0","reject","2026-11-01T05:30:00.000Z"],
    ["2026-11-01T01:30","1","reject","2026-11-01T06:30:00.000Z"],
    ["2026-03-08T02:30","0","shift_forward","2026-03-08T07:30:00.000Z"]
  ]){
    await root.locator('[data-calendar-edit="create"]').click();
    await fillPlan("时区验证",start);
    await root.locator("#calendar-timezone").fill("America/New_York");
    await root.locator("#calendar-frequency").selectOption("once");
    await root.locator("#calendar-count").fill("");
    await root.locator("#calendar-fold").selectOption(fold);
    if(gap==="shift_forward"){
      const before=(await posts()).length;
      await root.locator("#state-calendar-form button[type=submit]").click();
      await root.getByText("这个时区的本地时间不存在，请改用其他时间或选择顺延。",{exact:true}).waitFor();
      assert.equal((await posts()).length,before);
    }
    await root.locator("#calendar-gap").selectOption(gap);
    await root.locator("#state-calendar-form button[type=submit]").click();await calendarSaved();
    const request=(await posts()).at(-1).body;
    assert.equal(request.data.schedule.anchor,expected);
    assert.equal(request.data.schedule.frequency,"once");
    const latest=root.locator(".state-plan-list li").last();
    assert.equal(await latest.locator('[data-calendar-edit="exception"]').count(),0);
  }
  const exactAnchor="2026-09-27T02:30:05.123456+00:00";
  await page.evaluate(({key,anchor})=>{window.stateQA.values[key].calendar.items[1].schedule.anchor=anchor;},{key:first,anchor:exactAnchor});
  await root.locator("#state-refresh").click();await loadDone();
  await clickAction("revise",1).click();
  await root.locator("#calendar-title").fill("仅更改标题");
  await root.locator("#state-calendar-form button[type=submit]").click();await calendarSaved();
  assert.equal((await posts()).at(-1).body.data.schedule.anchor,exactAnchor);
  return {checks:"create with automatic calendar disabled, weekly/once plans, series revise and original sources/reminder cancellation, occurrence move/skip, reminder sequence, cancel, three conflict drafts with explicit rebase, exact replay across reload without automatic POST, late role response isolation, keyboard submit, 320/390/1366px, DST gap/fold and original timestamp precision",
    screenshots:[320,390,1366].map(width=>path.join(outputDir,`calendar-create-${width}.png`))};
}

module.exports={run};
