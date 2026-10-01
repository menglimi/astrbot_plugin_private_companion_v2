/* 小屋右栏：只投影当前授权对象的状态、日历与生活确认。 */
"use strict";
window.CompanionHomeSidebar = (() => {
  const e = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const text = value => typeof value === "string" ? value.trim() : "";
  const stamp = value => typeof value === "string" && Number.isFinite(Date.parse(value)) ? Date.parse(value) : null;
  const kinds = {sleep:"睡眠休息", reading:"阅读", diary:"整理日记", dream:"梦境"};
  function zoneOf({state, life}) {
    const zone = state?.settings?.planning_timezone || life?.config?.timezone || "Asia/Shanghai";
    try { new Intl.DateTimeFormat("zh-CN", {timeZone:zone}); return zone; }
    catch { return "Asia/Shanghai"; }
  }
  function format(value, zone, options) {
    if (value == null) return "";
    return new Intl.DateTimeFormat("zh-CN", {timeZone:zone, ...options}).format(new Date(value));
  }
  const day = (value, zone) => format(value, zone, {year:"numeric", month:"numeric", day:"numeric"});
  const clock = (value, zone) => format(value, zone, {hour:"2-digit", minute:"2-digit", hourCycle:"h23"});
  function moment(value, now, zone) {
    return (day(value, zone) === day(now, zone) ? "" : format(value, zone, {month:"long", day:"numeric"}) + " ") + clock(value, zone);
  }
  function windowText(item, now, zone) {
    if (item.start == null) return "时间待定";
    const start = moment(item.start, now, zone);
    return item.end != null ? start + " – " + (day(item.start, zone) === day(item.end, zone) ? clock(item.end, zone) : moment(item.end, now, zone)) : start;
  }
  const activities = life => Array.isArray(life?.activities) ? life.activities : [];
  const sleepOf = ({state, life}) => state?.body_sleep || life?.body_sleep || state?.state?.sleep_execution;
  function vital(kind, raw, {sleeping=false, disabled=false, loading=false, unreadable=false}={}) {
    const icons = {energy:"battery",health:"heart-pulse",hunger:"utensils",sleep:"moon",
      cycle:"calendar-heart",busy:"briefcase-business",location:"map-pin"};
    const item = (visual,icon,label,tone="quiet") => ({visual,icon,label,tone});
    if (disabled) return item("disabled",icons[kind],"未启用");
    if (kind === "energy" && typeof raw === "number") {
      if (raw >= 75) return item("energy-full","battery-full","充足","ok");
      if (raw >= 40) return item("energy-medium","battery-medium","尚可","ok");
      if (raw >= 20) return item("energy-low","battery-low","偏低","warn");
      return item("energy-depleted","battery-warning","较低","risk");
    }
    if (kind === "sleep" && sleeping) return item("sleeping","moon-star","睡眠中","rest");
    if (!raw) return item("unknown",icons[kind],loading ? "读取中" : unreadable ? "待读取" : "未记录");
    if (/^(未知|不清楚|未记录|暂无|尚未记录|未设置|待确认)$/.test(raw)) return item("unknown",icons[kind],"未知");
    if (kind === "health") {
      if (/^(稳定|正常|健康|良好|状态良好|无不适|没有不适|身体无不适)$/.test(raw)) return item("well","heart-pulse","良好","ok");
      if (/恢复中|康复中|正在恢复|逐渐恢复|正在好转|有所好转/.test(raw)) return item("recovering","heart-handshake","恢复中","ok");
      const symptoms = raw.replace(/(?:没有|暂无|并无|未见|没有出现|未出现|不再|无|没|不)(?:明显|任何)?(?:不适|疼痛|头痛|发热|发烧|感冒|虚弱|生病)/g, "");
      if (/不舒服|不适|生病|发烧|发热|疼痛|头痛|感冒|虚弱|不稳定|欠佳/.test(symptoms)) return item("strained","heart-crack","不适","warn");
      if (/稳定|正常|健康|良好|(?:没有|暂无|无)(?:明显|任何)?不适/.test(raw)) return item("well","heart-pulse","良好","ok");
    } else if (kind === "hunger") {
      if (/吃撑|太饱|过饱|饱胀|有点撑/.test(raw)) return item("full","utensils-crossed","偏饱","warn");
      if (/^(不饿|没有饥饿感|已吃饱|吃饱了|饱腹|饱足|已饱|适中)$/.test(raw)) return item("sated","utensils","不饿","ok");
      if (/没吃饱|未吃饱|有点饿|饥饿|很饿|饿了|^饿$|饥肠辘辘/.test(raw)) return item("hungry","soup","饿了","warn");
    } else {
      if (/^(清醒|精神|精神饱满|不困|没有困意|已醒|醒着)$/.test(raw)) return item("awake","sun","清醒","ok");
      if (/难以入睡|无法入睡|失眠|睡不着|辗转|睡眠不足/.test(raw)) return item("restless","cloud-moon","睡不好","warn");
      if (/困倦|犯困|想睡|有些困|很困|疲惫|^困$/.test(raw)) return item("sleepy","moon","困倦","warn");
      if (/休息|入睡|睡着|睡眠中/.test(raw)) return item("rest","moon","休息感受","rest");
    }
    // 自由文字不能可靠归类时保留原文，不推断成正常或异常。
    return item("recorded",icons[kind],"有记录");
  }
  function renderVital(kind, label, raw, options) {
    const item = vital(kind, raw, options), detail = item.visual === "disabled" ? "该项维护未启用"
      : kind === "energy" && typeof raw === "number" ? `${raw} / 100` : raw || item.label;
    return `<span class="home-state-point" data-visual="${item.visual}" data-tone="${item.tone}"
      title="${e(label+" · "+detail)}"><span class="home-state-glyph" aria-hidden="true"><i data-lucide="${item.icon}"></i></span>
      <span class="home-state-label">${label}</span><strong>${e(item.label)}</strong>
      <span class="home-state-tooltip" role="tooltip"><b>${label} · ${item.label}</b><span>${e(detail)}</span>
      ${kind === "energy" && typeof raw === "number" ? `<meter min="0" max="100" value="${raw}" aria-label="能量 ${raw} / 100"></meter>` : ""}</span></span>`;
  }
  function renderState(input) {
    const {state, life, loading=false, unavailable=()=>"尚未读取"} = input;
    const now = input.now ?? Date.now(), zone = zoneOf(input);
    const values = state?.state?.values || {}, settings = state?.settings || {};
    const sleeping = sleepOf(input)?.state === "sleeping" || activities(life).some(item=>item.kind === "sleep" && item.state === "active");
    const energy = typeof values.energy === "number" && Number.isFinite(values.energy) && values.energy >= 0 && values.energy <= 100 ? values.energy : null;
    const unreadable = !state || state.state?.state === "unavailable";
    const cycleNames={menstrual:"经期",follicular:"卵泡期",pre_ovulation:"排卵前",ovulation:"排卵期",luteal:"黄体期",pms:"经前期",recovery:"恢复期"};
    const timeline=state?.state?.cycle_timeline;
    const cycle=timeline?.applicability==="not_applicable"?"不适用":timeline?.applicability==="applicable"
      ?`${cycleNames[timeline.phase]||"周期中"}${Number.isInteger(timeline.phase_day)?` · 第 ${timeline.phase_day} 天`:""}`:text(values.cycle);
    const candidates=[["energy","能量",energy,false],["health","健康",text(values.health),settings.health_enabled===false],
      ["hunger","饥饿",text(values.hunger),settings.hunger_enabled===false],
      ["sleep","睡眠",sleeping?"睡眠中 · 活动确认":text(values.sleep),false],
      ["cycle","生理期",cycle,settings.cycle_enabled===false],["busy","忙碌",text(values.busy),false],
      ["location","位置",text(values.location),false]];
    const visible=candidates.filter(([kind])=>settings["home_show_"+kind]!==false&&settings.enabled!==false
      &&(kind==="health"?settings.health_enabled!==false:kind==="hunger"?settings.hunger_enabled!==false
        :kind==="cycle"?settings.cycle_enabled!==false:true));
    const updated = stamp(state?.state?.updated_at);
    const caption = [settings.enabled === false || state?.state?.state === "disabled" ? "自动维护未启用" : "",
      updated != null ? `更新于 ${moment(updated, now, zone)}` : ""].filter(Boolean).join(" · ");
    const states=visible.map(([kind,label,raw,disabled])=>renderVital(kind,label,raw,{sleeping,disabled,loading,unreadable})).join("");
    const fallback=loading?"正在读取角色状态…":settings.enabled===false?"状态维护未启用":visible.length?"":"暂无已启用的首页状态";
    const accessible=visible.map(([kind,label,raw,disabled])=>`${label} ${disabled?"未启用":kind==="energy"&&typeof raw==="number"?`${raw} / 100`:raw||"尚未记录"}`).join("；");
    return `<button type="button" class="home-state-board" data-go="life" data-life-target="state" aria-label="打开角色状态设置。${e(accessible||fallback)}">
      ${states||`<span class="home-state-empty">${e(fallback)}</span>`}<span class="home-state-open" aria-hidden="true"><i data-lucide="arrow-up-right"></i></span></button>
      ${unreadable && !loading ? `<p class="home-side-warning" role="status">${e(state ? "暂时无法读取角色状态，请在详情中核对。" : unavailable("state"))}</p>` : ""}
      ${caption ? `<p class="home-side-caption">${e(caption)}</p>` : ""}`;
  }
  function agenda(input) {
    const {state, life} = input, now = input.now ?? Date.now(), items = [], seen = new Set();
    function add(item) { if (!seen.has(item.key)) {seen.add(item.key); items.push(item);} }
    for (const item of state?.occurrences?.items || []) {
      const start = stamp(item.start), end = stamp(item.end);
      if (item.state === "cancelled" || start == null || end == null || end <= now) continue;
      const current = start <= now && item.state === "accepted";
      const label = item.state === "proposed" ? "待确认" : current ? "当前计划时段" : "计划安排";
      const owner = item.kind === "user_report" ? "你的安排 · " : item.kind === "commitment" ? "约定 · " : "";
      add({key:`calendar:${item.id}:${item.sequence}`, title:text(item.title) || "未命名安排", start, end,
        label:owner + label, tone:current ? "current" : "planned", order:current ? 1 : 2});
    }
    for (const item of activities(life)) {
      if (!["active","planned","paused"].includes(item.state)) continue;
      const active = item.state === "active";
      add({key:`activity:${item.activity_id}`, title:text(item.title) || kinds[item.kind] || "个人活动",
        start:stamp(active ? item.started_at : item.due_at), end:active ? stamp(item.due_at) : null,
        label:active ? "当前活动 · 进行中" : item.state === "paused" ? "已暂停" : item.due_at ? "待开始 · 计划截止时间" : "待开始",
        tone:active ? "active" : item.state === "paused" ? "paused" : "planned", order:active ? 0 : 2});
    }
    const sleep = sleepOf(input), plan = state?.sleep_schedule || life?.sleep_schedule;
    if (sleep?.state === "sleeping" && !activities(life).some(item=>item.kind === "sleep" && item.state === "active")) {
      add({key:"body:sleep", title:"睡眠休息", start:stamp(sleep.started_at), end:stamp(sleep.planned_wake_at),
        label:"当前活动 · 睡眠中 · 活动确认", tone:"active", order:0});
    }
    const nextSleep = stamp(plan?.next_sleep_at);
    if (plan?.enabled && nextSleep != null && nextSleep >= now) {
      add({key:"routine:sleep", title:"睡眠休息", start:nextSleep, end:stamp(plan.next_wake_at),
        label:plan.executor_state === "available" ? "自动睡眠计划" : "睡眠计划 · 等待授权窗口", tone:"planned", order:2});
    }
    const nextDiary = stamp(life?.next_diary_at);
    if (life?.config?.diary_enabled && nextDiary != null && nextDiary >= now) {
      add({key:"routine:diary", title:"整理今日日记", start:nextDiary, end:null, label:"自动日记计划", tone:"planned", order:2});
    }
    return items.sort((a,b)=>a.order-b.order || (a.start ?? Infinity)-(b.start ?? Infinity) || a.key.localeCompare(b.key));
  }
  function renderSchedule(input) {
    const {state, life, loading=false, unavailable=()=>"尚未读取"} = input;
    const now = input.now ?? Date.now(), zone = zoneOf(input), items = agenda(input), messages = [];
    const calendarRead = Array.isArray(state?.occurrences?.items), lifeRead = Array.isArray(life?.activities);
    if (!loading) {
      if (!calendarRead) messages.push(`日历：${state ? "安排尚未读取" : unavailable("state")}`);
      if (!lifeRead) messages.push(`活动：${unavailable("life")}`);
      if (state?.occurrences?.partial) messages.push("部分日历安排未完整读取");
    }
    const emptyTitle = loading ? "正在读取日程…" : calendarRead && lifeRead ? "暂无近期安排" : "日程暂不可读取";
    return `<p class="home-agenda-date">${e(format(now, zone, {month:"long", day:"numeric", weekday:"long"}))}</p>
      ${!items.some(item=>item.order === 0) ? `<p class="home-agenda-current">${loading ? "正在读取当前活动…" : lifeRead ? "当前没有进行中的活动" : "当前活动尚未读取"}</p>` : ""}
      <ol class="home-agenda" aria-label="近期日程">${items.length ? items.slice(0,4).map(item=>`<li class="home-agenda-item" data-tone="${item.tone}"><span class="home-agenda-dot" aria-hidden="true"></span><div class="home-agenda-body">
        <time${item.start == null ? "" : ` datetime="${new Date(item.start).toISOString()}"`}>${e(windowText(item, now, zone))}</time><strong>${e(item.title)}</strong><small>${e(item.label)}</small></div></li>`).join("")
        : `<li class="home-agenda-item"><span class="home-agenda-dot" aria-hidden="true"></span><div class="home-agenda-body"><strong>${emptyTitle}</strong></div></li>`}</ol>
      ${messages.length ? `<p class="home-side-warning" role="status">${e(messages.join("；"))}</p>` : ""}
      <p class="home-side-caption">${items.length > 4 ? `另有 ${items.length-4} 项安排 · ` : ""}时间按 ${e(zone)} 显示</p>`;
  }
  return {renderState, renderSchedule};
})();
