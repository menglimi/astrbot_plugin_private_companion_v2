/* 状态与日程的边界：计划不能冒充执行，缺失数据不能补成生活事实。 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const window = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,"../pages/陪伴小屋/home-sidebar.js"),"utf8"), {window});
const {renderState,renderSchedule} = window.CompanionHomeSidebar;
const now = Date.parse("2026-09-30T04:00:00Z");
const status = items => ({settings:{enabled:true,planning_timezone:"Asia/Shanghai"}, state:{revision:1,values:{}},
  occurrences:{items,partial:false}, sleep_schedule:{enabled:false}});
const life = activities => ({activities,config:{diary_enabled:false}});
const event = (id,start,end,extra={}) => ({id,sequence:0,kind:"role_plan",state:"accepted",title:id,start,end,...extra});

test("结构化心情保留文字，零能量有真实读数，活动正文经过 HTML 转义", () => {
  const state=status([]);
  state.state.values={energy:0,mood:{description:"平静而专注",joy:5},location:"小屋",sleep:"清醒"};
  const input={now,state,life:life([{activity_id:"a",state:"active",kind:"reading",title:'<img src=x onerror="alert(1)">'}])};
  const html=renderState(input);
  assert.match(html,/平静而专注/);assert.match(html,/value="0"/);
  assert.match(renderSchedule(input),/&lt;img/);assert.doesNotMatch(html+renderSchedule(input),/<img|\[object Object\]|查看详情/);
});

test("当前日历计划没有执行确认时只标计划时段，待确认约定不进入当前活动", () => {
  const state=status([event("窗边读书","2026-09-30T03:30:00Z","2026-09-30T04:30:00Z")]);
  const html=renderSchedule({now,state,life:life([])});
  assert.match(html,/计划时段/);assert.match(html,/当前没有进行中的活动/);assert.doesNotMatch(html,/当前活动 · 进行中/);
  assert.doesNotMatch(renderState({now,state,life:life([])}),/窗边读书/,"当前计划已与日程合并，不占用状态区域");
  state.occurrences.items[0].state="proposed";
  assert.match(renderSchedule({now,state,life:life([])}),/待确认/);
});

test("日程先展示执行中的活动，再按时间展示计划，并排除已完成、取消和过期记录", () => {
  const state=status([
    event("傍晚安排","2026-09-30T10:00:00Z","2026-09-30T11:00:00Z"),
    event("早已过去","2026-09-30T01:00:00Z","2026-09-30T02:00:00Z"),
    event("下午安排","2026-09-30T06:00:00Z","2026-09-30T07:00:00Z"),
    event("已取消安排","2026-09-30T05:00:00Z","2026-09-30T06:00:00Z",{state:"cancelled"}),
  ]);
  const activities=[{activity_id:"done",state:"completed",title:"历史活动"},
    {activity_id:"active",state:"active",title:"正在阅读",started_at:"2026-09-30T03:00:00Z",due_at:"2026-09-30T05:00:00Z"}];
  const html=renderSchedule({now,state,life:life(activities)});
  assert(html.indexOf("正在阅读")<html.indexOf("下午安排"));
  assert(html.indexOf("下午安排")<html.indexOf("傍晚安排"));
  assert.doesNotMatch(html,/早已过去|历史活动|已取消安排/);
});

test("共享睡眠以确认标记睡眠中，跨日计划有日期，并说明缺少执行窗口", () => {
  const state=status([]);
  state.body_sleep={state:"sleeping",started_at:"2026-09-30T00:00:00Z",planned_wake_at:"2026-09-30T03:00:00Z"};
  state.sleep_schedule={enabled:true,next_sleep_at:"2026-09-30T16:30:00Z",next_wake_at:"2026-10-01T00:30:00Z",executor_state:"no_authorized_window"};
  const html=renderSchedule({now,state,life:life([])});
  assert.match(html,/睡眠中 · 活动确认/);assert.match(html,/10月1日 00:30 – 08:30/);
  assert.match(html,/等待授权窗口/);assert.doesNotMatch(html,/已完成/);
  assert.match(renderState({now,state,life:life([])}),/睡眠中/);
  const sameWindow=life([{activity_id:"sleep",state:"active",kind:"sleep",title:"睡眠休息",started_at:state.body_sleep.started_at,due_at:state.body_sleep.planned_wake_at}]);
  assert.equal((renderSchedule({now,state,life:sameWindow}).match(/<strong>睡眠休息<\/strong>/g)||[]).length,2,"实际睡眠与下次计划各出现一次");
});

test("加载、空记录、权限失败与部分读取各有独立说明，关闭的心情维护不冒出旧心情", () => {
  assert.match(renderSchedule({now,loading:true}),/正在读取日程/);
  assert.match(renderSchedule({now,state:status([]),life:life([])}),/暂无近期安排/);
  assert.match(renderSchedule({now,unavailable:()=>"当前对象没有此私聊工作区"}),/当前对象没有此私聊工作区/);
  const state=status([]);state.occurrences.partial=true;state.settings.mood_enabled=false;state.state.values.mood="旧心情";
  assert.match(renderSchedule({now,state,life:life([])}),/未完整读取/);
  assert.doesNotMatch(renderState({now,state,life:life([])}),/旧心情/);
  assert.match(renderState({now,state,life:life([])}),/未启用/);
});

test("四项图标用不同状态呈现，无法归类的自由描述原样保留在详情中", () => {
  const state=status([]);state.state.values={energy:12,health:"恢复中",hunger:"有点饿",sleep:"睡不着"};
  const html=renderState({now,state,life:life([])});
  for(const visual of ["energy-depleted","recovering","hungry","restless"])assert.match(html,new RegExp('data-visual="'+visual+'"'));
  assert.equal((html.match(/class="home-vital"/g)||[]).length,4);
  assert.match(html,/aria-label="心理能量：12 \/ 100"/);
  state.state.values={energy:88,health:"没有不适",hunger:"不饿",sleep:"不困"};
  const normal=renderState({now,state,life:life([])});
  for(const visual of ["energy-full","well","sated","awake"])assert.match(normal,new RegExp('data-visual="'+visual+'"'));
  state.state.values.health="胃部像一团小小的棉花";
  const prose=renderState({now,state,life:life([])});
  assert.match(prose,/data-visual="recorded"/);assert.match(prose,/胃部像一团小小的棉花/);
  state.state.values.health="身体状态正常，暂无明显不适";
  const noSymptoms=renderState({now,state,life:life([])}).split("</button>").find(value=>value.includes('aria-label="健康：'));
  assert.match(noSymptoms,/data-visual="well"/);assert.doesNotMatch(noSymptoms,/data-visual="strained"/);
});
