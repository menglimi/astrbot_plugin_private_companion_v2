/* 状态页新增配置项（周期能量/提示词、心情动力学、每日巡视、天气时效）的单元测试。
 *
 * 这些字段此前只存在于后端注册表，页面没有控件。接入时发现两个页面自身的坑，
 * 各锁一条：
 *   1. normalized()/field() 的数字下限写死为 1，而阶段能量是 −50–30，
 *      负值会被**页面自己**拦下或在浏览器层判定非法；
 *   2. cycle 分组的顺序被 form() 的 slice(0,6)/slice(6,12) 依赖，
 *      新字段插在前面会让「阶段时长」渲染到别的字段上。
 * 第三个含义是「缺字段就整套禁用」：planning 组多一项就会让旧宿主整套不可编辑，
 * 所以天气时效改挂在感知页，不在此断言范围内。
 */
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const {test}=require("node:test");

const pageRoot=path.resolve(__dirname,"../pages/陪伴小屋");
function load(){
  const context=vm.createContext({window:{},Intl,Date});
  vm.runInContext(fs.readFileSync(path.join(pageRoot,"state-maintenance.js"),"utf8"),context,
    {filename:"state-maintenance.js"});
  return context.window.CompanionStateMaintenance;
}
const PHASES=["menstrual","follicular","pre_ovulation","ovulation","luteal","pms"];
/* 一份能被 normalized 接受的完整 cycle 取值，字段名与 shape 都照后端 DEFAULTS。
   mood 三项虽不渲染控件，仍在 groups.cycle 里，必须一并提供。 */
function cycleValues(){
  return {cycle_enabled:true,cycle_mode:"basic",cycle_timezone:"Asia/Shanghai",
    cycle_initialization:"natural",cycle_variation_enabled:false,cycle_discomfort_enabled:false,
    cycle_expression_prompt:"",cycle_link_intensity:false,cycle_discomfort_chance:55,
    cycle_discomfort_types:"痛经,头痛,腰酸,乏力",
    ...Object.fromEntries(PHASES.map(phase=>[`cycle_${phase}_days`,3])),
    ...Object.fromEntries(PHASES.flatMap(phase=>[[`cycle_${phase}_energy`,0],
      [`cycle_${phase}_prompt`,"正常"],[`cycle_${phase}_mood`,"平稳"]]))};
}
/* vm 里造出来的数组是另一个 realm 的 Array，deepEqual 会因原型不同而失败。 */
const sameList=(left,right)=>{
  assert.equal(left.length,right.length);
  left.forEach((value,index)=>assert.equal(value,right[index],`第 ${index} 项`));
};

test("阶段能量接受负数，且拒绝超出 −50–30 的值",()=>{
  const m=load();
  for(const [name,value,ok] of [["cycle_menstrual_energy",-12,true],["cycle_pms_energy",-8,true],
      ["cycle_ovulation_energy",30,true],["cycle_ovulation_energy",31,false],
      ["cycle_menstrual_energy",-51,false],["cycle_menstrual_energy",1.5,false]]){
    assert.equal(m.validField(name,value),ok,`${name}=${value} 期望 ${ok}`);
  }
  /* 真实回归点：负值此前被写死的 `value>=1` 判为非法。 */
  const values={...cycleValues(),cycle_menstrual_energy:-12};
  assert.equal(m.normalized("cycle",values).cycle_menstrual_energy,-12);
});

test("六个阶段都有能量与提示词，提示词上限 512 字",()=>{
  const m=load();
  for(const phase of PHASES){
    assert.equal(m.validField(`cycle_${phase}_energy`,0),true,phase);
    assert.equal(m.validField(`cycle_${phase}_prompt`,"正常"),true,phase);
    assert.equal(m.validField(`cycle_${phase}_prompt`,"长".repeat(512)),true,phase);
    assert.equal(m.validField(`cycle_${phase}_prompt`,"长".repeat(513)),false,phase);
  }
  /* 六个 _mood 氛围词刻意不接控件，但仍必须声明后端真正用的 80 字上限：
     闭包检查会读它们，页面按默认 2048 放行会让整份周期设置被后端退回。 */
  for(const phase of PHASES){
    assert.equal(m.validField(`cycle_${phase}_mood`,"疲惫"),true,phase);
    assert.equal(m.validField(`cycle_${phase}_mood`,"长".repeat(80)),true,phase);
    assert.equal(m.validField(`cycle_${phase}_mood`,"长".repeat(81)),false,phase);
  }
});

test("周期不适概率与体感清单有界，状态强度联动可编辑",()=>{
  const m=load();
  for(const value of [0,55,100])assert.equal(m.validField("cycle_discomfort_chance",value),true,String(value));
  for(const value of [-1,101,55.5,"55"])assert.equal(m.validField("cycle_discomfort_chance",value),false,String(value));
  for(const value of ["", "痛经,腰酸", "恶心,情绪低落"])
    assert.equal(m.validField("cycle_discomfort_types",value),true,value);
  for(const value of ["胃痛", "痛经,痛经", "痛经,未知"])
    assert.equal(m.validField("cycle_discomfort_types",value),false,value);
  assert.equal(m.validField("cycle_link_intensity",true),true);
  assert.equal(m.normalized("cycle",{...cycleValues(),cycle_discomfort_chance:"72"}).cycle_discomfort_chance,72);
  assert.equal(m.normalized("cycle",{...cycleValues(),cycle_discomfort_types:"恶心,痛经"}).cycle_discomfort_types,"痛经,恶心");
  assert.equal(m.toggleChecklist("cycle_discomfort_types","痛经,头痛","恶心",true),"痛经,头痛,恶心");
  assert.equal(m.toggleChecklist("cycle_discomfort_types","痛经,头痛","痛经",false),"头痛");
});

test("cycle 分组前十二位保持开关/模式/天数/表达偏好的既有顺序",()=>{
  const m=load();
  const names=m.fields("cycle");
  sameList(names.slice(0,6),["cycle_enabled","cycle_mode","cycle_timezone","cycle_initialization",
    "cycle_variation_enabled","cycle_discomfort_enabled"]);
  sameList(names.slice(6,12),PHASES.map(phase=>`cycle_${phase}_days`));
  assert.equal(names[12],"cycle_expression_prompt");
  /* 第十二位之后：六阶段 × (能量 + 提示词 + 氛围词)。 */
  assert.equal(names.length,16+PHASES.length*3);
  sameList(names.slice(13,16),["cycle_link_intensity","cycle_discomfort_chance","cycle_discomfort_types"]);
});

test("心情动力学三项有界，概率按 0–1 判定",()=>{
  const m=load();
  assert.equal(m.validField("mood_update_probability",0.6),true);
  assert.equal(m.validField("mood_update_probability",0.6*1),true);
  for(const value of [-0.1,1.1,"0.6",null])assert.equal(m.validField("mood_update_probability",value),false,String(value));
  assert.equal(m.validField("mood_update_max_delta",1),true);
  assert.equal(m.validField("mood_update_max_delta",4),true);
  assert.equal(m.validField("mood_update_max_delta",5),false);
  assert.equal(m.validField("mood_decay_half_life_minutes",5),true);
  assert.equal(m.validField("mood_decay_half_life_minutes",1440),true);
  assert.equal(m.validField("mood_decay_half_life_minutes",4),false);
  /* 总闸必须在分组里，否则三项参数没有开关可依赖。 */
  assert.equal(m.fields("mood")[0],"mood_enabled");
});

test("每日巡视的时刻必须是 HH:MM，保留天数 3–180",()=>{
  const m=load();
  for(const value of ["04:00","23:59","00:00"])assert.equal(m.validField("daily_state_patrol_time",value),true,value);
  /* 后端的 parse_patrol_time 拒绝秒与时区后缀，页面要在本地就拦下。 */
  for(const value of ["4:00","04:00:00","24:00","04:60","","04:00Z"])assert.equal(m.validField("daily_state_patrol_time",value),false,value);
  assert.equal(m.validField("daily_state_patrol_retention_days",3),true);
  assert.equal(m.validField("daily_state_patrol_retention_days",180),true);
  assert.equal(m.validField("daily_state_patrol_retention_days",2),false);
  assert.equal(m.validField("daily_state_patrol_retention_days",181),false);
});

test("范围提示按字段下限生成，负值字段不显示成 1–30",()=>{
  const m=load();
  const values={...cycleValues(),cycle_pms_energy:99};
  assert.throws(()=>m.normalized("cycle",values),/-50–30 之间/);
});

test("新分区都注册了标题，且字段都能读出标签",()=>{
  const m=load();
  for(const kind of ["mood","patrol"])assert.equal(typeof m.titles[kind],"string",kind);
  for(const name of ["mood_update_probability","daily_state_patrol_time","cycle_ovulation_prompt"])
    assert.notEqual(m.label(name),name,`${name} 缺标签`);
});
