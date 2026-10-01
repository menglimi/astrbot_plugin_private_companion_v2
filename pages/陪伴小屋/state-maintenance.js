"use strict";
window.CompanionStateMaintenance = (() => {
  const phases={menstrual:"经期",follicular:"卵泡期",pre_ovulation:"排卵前",ovulation:"排卵期",luteal:"黄体期",pms:"经前期"};
  const phaseDescriptions={menstrual:"节奏可以放慢，按实际感受表达",follicular:"精力逐步回升，保持自然变化",pre_ovulation:"逐渐轻盈，不要求突然改变性格",ovulation:"可以更明朗，不自动推断亲密或生育",luteal:"整体趋于平稳，保留个体差异",pms:"可以更想安静，也可以照常相处"};
  let selectedPhase="menstrual";
  let selectedCycleView="plan";
  const modes={basic:"基础三阶段",six_phase:"六阶段"};
  const initialization={natural:"自然定位",unknown:"暂不定位",first_day:"从第 1 天开始"};
  const applicability={applicable:"指定当前周期日",not_applicable:"该角色不适用",unknown:"保持尚未确定",auto:"交回角色判断"};
  const discomfortChoices=Object.fromEntries(["痛经","头痛","腰酸","乏力","情绪低落","恶心"].map(value=>[value,value]));
  const definitions={
    enabled:{label:"启用后台状态维护",type:"boolean"},
    maintenance_minutes:{label:"维护间隔（分钟）",type:"number",max:1440},
    calendar_enabled:{label:"启用此会话的日程读写",type:"boolean"},
    home_show_energy:{label:"能量",type:"boolean"},
    home_show_health:{label:"健康",type:"boolean"},
    home_show_hunger:{label:"饥饿",type:"boolean"},
    home_show_sleep:{label:"睡眠",type:"boolean"},
    home_show_cycle:{label:"生理期",type:"boolean"},
    home_show_busy:{label:"忙碌",type:"boolean"},
    home_show_location:{label:"位置",type:"boolean"},
    humanized_state_intensity:{label:"状态表达强度",type:"number",min:0,max:100},
    planning_enabled:{label:"启用自动规划",type:"boolean"},
    planning_timezone:{label:"规划时区",type:"text"},
    planning_horizon_days:{label:"长期规划范围（天）",type:"number",max:366},
    planning_refine_minutes:{label:"提前细化时间（分钟）",type:"number",max:1440},
    planning_max_items:{label:"每次最多安排（项）",type:"number",max:32},
    planning_prompt:{label:"规划偏好",type:"textarea",maxLength:4096,placeholder:"例如：平日留出阅读时间，周末适当放松；已有约定优先，给临时变化留出余地。"},
    hunger_enabled:{label:"模拟饥饿感受",type:"boolean"},
    health_enabled:{label:"模拟健康感受",type:"boolean"},
    cycle_enabled:{label:"启用生理期模拟",type:"boolean"},
    cycle_mode:{label:"阶段模式",type:"select",choices:modes},
    cycle_timezone:{label:"周期时区",type:"text"},
    cycle_initialization:{label:"首次定位方式",type:"select",choices:initialization},
    cycle_variation_enabled:{label:"允许阶段天数轻微波动",type:"boolean"},
    cycle_discomfort_enabled:{label:"允许模拟不适感受",type:"boolean"},
    cycle_link_intensity:{label:"精力趋势随状态强度缩放",type:"boolean"},
    cycle_discomfort_chance:{label:"参考概率",type:"range",min:0,max:100},
    cycle_discomfort_types:{label:"可选体感",type:"checklist",choices:discomfortChoices},
    cycle_expression_prompt:{label:"角色表达偏好",type:"textarea"},
    /* 心情动力学的三项主参数。mood_enabled 是总闸，这三项决定它怎么动：
       概率控制“这一轮情绪到底动没动”，步长控制“一次最多动多少”，
       半衰期控制“多久回归基线”。*/
    mood_update_probability:{label:"每轮更新心情的概率",type:"probability"},
    mood_update_max_delta:{label:"单轮最大变化幅度",type:"number",min:1,max:4},
    mood_decay_half_life_minutes:{label:"回归基线半衰期（分钟）",type:"number",min:5,max:1440},
    /* 每日巡视：V1 的日检节奏与保留天数，V2 由 humanized.py 消费。*/
    daily_state_patrol_enabled:{label:"启用每日状态巡视",type:"boolean"},
    daily_state_patrol_time:{label:"巡视时刻（HH:MM，本地时间）",type:"time"},
    daily_state_patrol_retention_days:{label:"巡视记录保留天数",type:"number",min:3,max:180},
    ...Object.fromEntries(Object.entries(phases).map(([key,label])=>["cycle_"+key+"_days",{label:label+"天数",type:"number",max:30}])),
    /* 六阶段的能量与提示词。能量是 -50–30 的偏移量（负值表示该阶段精力偏低），
       提示词是角色在该阶段实际读到的表达引导，上限 512 字。
       六个 _mood 氛围词刻意不接控件：默认「疲惫/轻快/敏感」这类词已够用，
       接上只是多六个低价值输入框。但它们仍要声明**正确的上限 80**——
       闭包检查会读它们，页面若按默认 2048 放行，值到后端才被拒，
       整个周期设置会连带存不进去。*/
    ...Object.fromEntries(Object.entries(phases).flatMap(([key,label])=>[
      ["cycle_"+key+"_energy",{label:label+"精力偏移",type:"number",min:-50,max:30}],
      ["cycle_"+key+"_prompt",{label:label+"表达引导",type:"textarea",maxLength:512,
        placeholder:"例如：处于"+label+"，身体更容易疲倦，情绪感受稍敏锐。"}],
      ["cycle_"+key+"_mood",{label:label+"氛围词",type:"text",maxLength:80}]])),
  };
  /* cycle 的前十二位顺序被 form() 的 slice(0,6)/slice(6,12) 依赖：
     前六项是开关与模式，接着六项是阶段天数。新字段一律追加在第十二位之后，
     否则「阶段时长」那一块会串到别的字段上。 */
  const groups={home:["enabled","maintenance_minutes","home_show_energy","home_show_health","home_show_hunger",
      "home_show_sleep","home_show_cycle","home_show_busy","home_show_location"],
    intensity:["humanized_state_intensity"],
    maintenance:["hunger_enabled","health_enabled"],
    calendar:["calendar_enabled"],
    planning:["planning_enabled","planning_timezone","planning_horizon_days","planning_refine_minutes","planning_max_items","planning_prompt"],
    cycle:["cycle_enabled","cycle_mode","cycle_timezone","cycle_initialization","cycle_variation_enabled","cycle_discomfort_enabled",
      ...Object.keys(phases).map(key=>"cycle_"+key+"_days"),"cycle_expression_prompt","cycle_link_intensity","cycle_discomfort_chance","cycle_discomfort_types",
      ...Object.keys(phases).flatMap(key=>["cycle_"+key+"_energy","cycle_"+key+"_prompt","cycle_"+key+"_mood"])],
    mood:["mood_enabled","mood_update_probability","mood_update_max_delta","mood_decay_half_life_minutes"],
    patrol:["daily_state_patrol_enabled","daily_state_patrol_time","daily_state_patrol_retention_days"]};
  const fields=kind=>groups[kind]||[];
  const isTimezone=name=>name==="cycle_timezone"||name==="planning_timezone";
  const label=name=>definitions[name]?.label||name;
  const length=settings=>Object.keys(phases).reduce((total,key)=>total+Number(settings["cycle_"+key+"_days"]),0);
  /* 数值字段的下限不能写死成 1：阶段能量是 -50–30，负值表示该阶段精力偏低。
     没声明 min 的沿用旧行为（1），声明了的按声明来。 */
  const minimumOf=field=>field.min??1;
  const rangeText=field=>field.min!=null&&field.min<0?`${field.min}–${field.max} 之间`:`${minimumOf(field)}–${field.max} 之间`;
  /* 后端的 parse_patrol_time 要求恰好 HH:MM、无秒、无时区后缀。
     type="time" 的控件值也是这个形状，但手工输入或旧快照可能带秒，所以仍要判。 */
  const isClock=value=>/^([01]\d|2[0-3]):[0-5]\d$/.test(value);
  function validField(name,value) {
    const field=definitions[name];if(!field)return false;
    if(field.type==="boolean")return typeof value==="boolean";
    if(field.type==="number"||field.type==="range")return Number.isInteger(value)&&value>=minimumOf(field)&&value<=field.max;
    if(field.type==="checklist") {
      if(typeof value!=="string")return false;
      const selected=value?value.split(",").map(item=>item.trim()):[];
      return selected.length===new Set(selected).size&&selected.every(item=>Object.hasOwn(field.choices,item));
    }
    if(field.type==="probability")return typeof value==="number"&&Number.isFinite(value)&&value>=0&&value<=1;
    if(field.type==="time")return typeof value==="string"&&isClock(value);
    if(field.type==="select")return typeof value==="string"&&Object.hasOwn(field.choices,value);
    return typeof value==="string"&&(isTimezone(name)?value.length>0&&value.length<=256:[...value].length<=(field.maxLength||2048));
  }
  function normalized(kind,values) {
    const result={};
    for(const name of fields(kind)){
      const field=definitions[name];let value=values[name];
      if(field.type==="number"||field.type==="range")value=Number(value);
      if(field.type==="probability")value=Number(value);
      if(field.type==="checklist") {
        const selected=new Set(typeof value==="string"?value.split(",").map(item=>item.trim()).filter(Boolean):[]);
        value=Object.keys(field.choices).filter(item=>selected.has(item)).join(",");
      }
      if(isTimezone(name)&&typeof value==="string")value=value.trim();
      if(!validField(name,value))throw new Error(field.type==="number"?`${field.label}请填写 ${rangeText(field)}的整数。`
        :field.type==="probability"?`${field.label}请填写 0 到 1 之间的小数。`
        :field.type==="time"?`${field.label}请填写 24 小时制的 HH:MM，例如 04:00。`
        :`请核对${field.label}。`);
      if(isTimezone(name)){
        try{new Intl.DateTimeFormat("zh-CN",{timeZone:value}).format();}catch{throw new Error("请填写有效的 IANA 时区，例如 Asia/Shanghai。");}
      }
      result[name]=value;
    }
    return result;
  }
  function field(name,values,e) {
    const spec=definitions[name],id="state-config-"+name,value=values[name];
    const base=`id="${id}" data-state-field="${name}"`;
    if(spec.type==="boolean")return `<label class="state-checkbox"><input ${base} type="checkbox" ${value?"checked":""}>${spec.label}</label>`;
    if(spec.type==="checklist") {
      const selected=new Set((value||"").split(",").map(item=>item.trim()));
      return `<fieldset class="state-checklist-field"><legend>${spec.label}</legend><div class="state-checklist">${Object.entries(spec.choices).map(([key,text])=>
        `<label><input type="checkbox" data-state-field="${name}" value="${e(key)}" ${selected.has(key)?"checked":""}><span>${e(text)}</span></label>`).join("")}</div></fieldset>`;
    }
    if(spec.type==="range")return `<label class="state-range-field" for="${id}"><span>${spec.label}</span><span class="state-range-control"><input ${base} type="range" min="${minimumOf(spec)}" max="${spec.max}" step="1" value="${e(value)}"><output id="${id}-output" for="${id}" data-state-output-for="${name}">${e(value)}%</output></span></label>`;
    const input=spec.type==="select"?`<select ${base}>${Object.entries(spec.choices).map(([key,text])=>`<option value="${key}" ${value===key?"selected":""}>${text}</option>`).join("")}</select>`
      :spec.type==="textarea"?`<textarea ${base} rows="3" placeholder="${e(spec.placeholder||"例如：自然表达，不反复播报阶段；不适时可以安静陪伴。")}">${e(value)}</textarea>`
      /* number 必须显式渲染 min：写死 min="1" 会把阶段能量的负值挡在浏览器层，
         用户看到的是「值非法」而不知道原因。probability 用 0–1 的小数框。 */
      :spec.type==="number"?`<input ${base} type="number" min="${minimumOf(spec)}" max="${spec.max}" step="1" required value="${e(value)}">`
      :spec.type==="probability"?`<input ${base} type="number" min="0" max="1" step="0.01" required value="${e(value)}">`
      :spec.type==="time"?`<input ${base} type="time" required value="${e(value)}">`
      :`<input ${base} type="text" autocomplete="off" required value="${e(value)}">`;
    return `<label for="${id}">${spec.label}${input}</label>`;
  }
  function snapshot(status) {
    return {revision:status.state.revision,view_token:status.state.view_token,settings_token:status.cycle_settings_token,
      settings:structuredClone(status.settings),timeline:structuredClone(status.state.cycle_timeline||null)};
  }
  function canAlign(status) {
    return !!status?.settings?.cycle_enabled&&status.state?.state!=="unavailable"
      &&typeof status.state?.view_token==="string"&&typeof status.cycle_settings_token==="string";
  }
  function alignment(draft) {
    const mode=draft.values.applicability;
    if(!Object.hasOwn(applicability,mode))throw new Error("请选择这次周期校准的方式。");
    const day=mode==="applicable"?Number(draft.values.day):null;
    const max=length(draft.base.settings);
    if(mode==="applicable"&&(!Number.isInteger(day)||day<1||day>max))throw new Error(`当前配置的周期为 ${max} 天，请填写 1–${max} 之间的周期日。`);
    return {action:"cycle.align",expected_revision:draft.base.revision,view_token:draft.base.view_token,
      settings_token:draft.base.settings_token,data:{applicability:mode,day}};
  }
  function form(draft,e) {
    const values=draft.values;
    if(draft.kind==="home")return `<div class="state-home-switches">${fields("home").slice(0,2).map(name=>field(name,values,e)).join("")}</div>
      <h4 class="state-form-section">首页状态看板</h4><div class="state-home-display-grid">${fields("home").slice(2).map(name=>field(name,values,e)).join("")}</div>`;
    if(draft.kind==="intensity")return `<div class="state-intensity-control">${field("humanized_state_intensity",values,e)}
      <p class="state-edit-help">0 表示不注入状态表达；数值越高，身体与情绪余波越容易自然影响回复语气。</p></div>`;
    if(draft.kind==="planning")return `<p class="state-edit-help">当前会话与角色</p>
      <div class="state-edit-fields">${fields("planning").slice(0,5).map(name=>field(name,values,e)).join("")}</div>
      <h4 class="state-form-section">怎样安排生活</h4>${field("planning_prompt",values,e)}
      <p class="state-edit-help">最多 4096 字；留空使用默认规划。</p>
      <p class="state-edit-help">需启用当前会话的日程读写权限。</p>`;
    if(draft.kind==="maintenance")return `<h4 class="state-form-section">角色状态模拟</h4>
      <p class="state-edit-help">这些偏好跟随当前人格，在它已授权的会话中保持一致。</p>
      <div class="state-edit-fields">${fields("maintenance").map(name=>field(name,values,e)).join("")}</div>`;
    if(draft.kind==="calendar")return `<h4 class="state-form-section">当前窗口权限</h4>
      <p class="state-edit-help">日程读写会访问当前会话中的安排，按窗口单独授权。</p>
      <div class="state-edit-fields">${fields("calendar").map(name=>field(name,values,e)).join("")}</div>`;
    if(draft.kind==="cycle") {
      const phase=Object.hasOwn(phases,selectedPhase)?selectedPhase:"menstrual";
      const phaseLabel=phases[phase], phaseDays=values["cycle_"+phase+"_days"];
      const phaseTabs=Object.entries(phases).map(([key,text])=>`<button type="button" id="state-cycle-phase-${key}" class="state-phase-tab${key===phase?" is-active":""}" role="tab" aria-selected="${key===phase}" aria-controls="state-phase-editor" data-state-phase="${key}" tabindex="${key===phase?"0":"-1"}"><span>${text}</span><small>${e(values["cycle_"+key+"_days"])} 天</small></button>`).join("");
      const total=length(values);
      const durationSegments=Object.entries(phases).map(([key,text])=>`<span data-cycle-segment="${key}" style="--phase-share:${total?Number(values["cycle_"+key+"_days"])/total*100:0}%" title="${text} · ${e(values["cycle_"+key+"_days"])} 天"></span>`).join("");
      const viewTabs=`<div class="state-cycle-view-tabs" role="tablist" aria-label="周期配置视图">
        <button type="button" id="state-cycle-view-plan" class="state-cycle-view-tab${selectedCycleView==="plan"?" is-active":""}" role="tab" aria-selected="${selectedCycleView==="plan"}" aria-controls="state-cycle-view-panel" data-cycle-view="plan" tabindex="${selectedCycleView==="plan"?"0":"-1"}"><span>周期方案</span><small>模拟方式、时区与阶段时长</small></button>
        <button type="button" id="state-cycle-view-expression" class="state-cycle-view-tab${selectedCycleView==="expression"?" is-active":""}" role="tab" aria-selected="${selectedCycleView==="expression"}" aria-controls="state-cycle-view-panel" data-cycle-view="expression" tabindex="${selectedCycleView==="expression"?"0":"-1"}"><span>阶段表达</span><small>按阶段编辑精力与语气参考</small></button>
      </div>`;
      const planView=`<section class="state-cycle-setup" aria-label="周期方案">
        <div class="state-cycle-general"><div class="state-form-section-row"><div><h4 class="state-form-section">通用设置</h4><p class="state-edit-help">阶段时长与波动从下一轮周期起采用；定位设置不会重写已有起点。</p></div><span class="state-section-mark">01</span></div>
          <div class="state-edit-fields">${fields("cycle").slice(0,6).map(name=>field(name,values,e)).join("")}${field("cycle_link_intensity",values,e)}</div>
          <fieldset class="state-cycle-discomfort" data-cycle-discomfort-fields ${values.cycle_discomfort_enabled?"":"disabled"}>
            <legend>不适模拟</legend><div class="state-edit-fields">${field("cycle_discomfort_chance",values,e)}</div>
            ${field("cycle_discomfort_types",values,e)}<p class="state-edit-help">概率与体感类型作为柔性提示，不保证精确命中。</p>
          </fieldset>
        </div>
        <div class="state-cycle-duration"><div class="state-form-section-row"><div><h4 class="state-form-section">阶段时长</h4><p class="state-edit-help">六阶段合计 <strong data-cycle-total>${e(total)}</strong> 天；基础模式会将中间阶段合并展示。</p></div><span class="state-section-mark">02</span></div>
          <div class="state-cycle-duration-overview"><span>周期分布</span><div class="state-cycle-meter" role="img" aria-label="六阶段时长分布">${durationSegments}</div></div>
          <div class="state-phase-fields">${fields("cycle").slice(6,12).map(name=>field(name,values,e)).join("")}</div>
        </div>
        <div class="state-cycle-preference"><div class="state-form-section-row"><div><h4 class="state-form-section">整体表达偏好</h4><p class="state-edit-help">这是所有阶段共用的柔性提示，不会覆盖角色原人格。</p></div><span class="state-section-mark">03</span></div>
          ${field("cycle_expression_prompt",values,e)}<p class="state-edit-help">最多 2048 字，可留空使用默认表达。</p>
        </div>
      </section>`;
      const expressionView=`<section class="state-phase-editor-shell" aria-label="阶段表达参数"><div class="state-form-section-row"><div><h4 class="state-form-section">编辑一个阶段</h4><p class="state-edit-help">只显示选中阶段；精力是趋势参考，氛围词是语气线索，表达引导提供可选方向。</p></div><span class="state-section-mark">04</span></div>
        <div class="state-phase-tabs" role="tablist" aria-label="选择周期阶段">${phaseTabs}</div>
        <fieldset id="state-phase-editor" class="state-phase-editor" role="tabpanel" aria-labelledby="state-cycle-phase-${phase}"><legend><span>${phaseLabel}</span><small>本阶段设为 ${e(phaseDays)} 天</small></legend>
          <p class="state-phase-help">${e(phaseDescriptions[phase])}。氛围词不是情绪结论，实际表达仍以角色当下感受和话题为准。</p>
          <div class="state-phase-fields">${field("cycle_"+phase+"_energy",values,e)}${field("cycle_"+phase+"_mood",values,e)}</div>
          ${field("cycle_"+phase+"_prompt",values,e)}
        </fieldset>
      </section>`;
      return `${viewTabs}<div id="state-cycle-view-panel" class="state-cycle-view-panel" role="tabpanel" tabindex="0" aria-labelledby="state-cycle-view-${selectedCycleView}">${selectedCycleView==="expression"?expressionView:planView}</div>`;
    }
    if(draft.kind==="mood")return `<p class="state-edit-help">仅当前会话生效</p>
      <div class="state-edit-fields">${field("mood_enabled",values,e)}</div>
      
      <div class="state-edit-fields">${["mood_update_probability","mood_update_max_delta","mood_decay_half_life_minutes"].map(name=>field(name,values,e)).join("")}</div>
      <p class="state-edit-help">半衰期越短，越快回归基线。</p>`;
    if(draft.kind==="patrol")return `
      <div class="state-edit-fields">${fields("patrol").map(name=>field(name,values,e)).join("")}</div>
      <p class="state-edit-help">使用角色本地时区；超过保留天数的报告会清除。</p>`;
    const base=draft.base,current=base.timeline,dayEnabled=values.applicability==="applicable";
    const observed=current?.cycle_day?`第 ${current.cycle_day} / ${current.cycle_days} 天`:
      ({not_applicable:"不适用",unknown:"尚未定位"}[current?.applicability]||"尚未定位");
    return `<p class="state-edit-help">当前记录：${e(observed)}。本次采用周期 ${e(length(base.settings))} 天、时区 ${e(base.settings.cycle_timezone)}；同一角色的其他已授权会话会采用校准后的时间线。</p>
      <div class="state-edit-fields"><label for="state-cycle-action">校准方式<select id="state-cycle-action" data-state-field="applicability" required><option value="">请选择</option>${Object.entries(applicability).map(([key,text])=>`<option value="${key}" ${key===values.applicability?"selected":""}>${text}</option>`).join("")}</select></label>
      <label for="state-cycle-day">今天是第几天<input id="state-cycle-day" type="number" min="1" max="${e(length(base.settings))}" step="1" data-state-field="day" value="${e(values.day)}" ${dayEnabled?"required":"disabled"}></label></div>
      <p class="state-edit-help">保存会重建周期定位并清除旧周期感受；“交回角色判断”在下次维护采纳。</p>`;
  }
  function summary(status,e) {
    const plan=status.state?.cycle_timeline?.pending_plan;
    return `<header class="state-maintenance-heading"><div><h3>身体与心情配置</h3><p>每项显示生效范围和当前值，点右侧操作直接调整。</p></div><div class="state-scope-legend" aria-label="设置范围"><span>当前会话</span><span>同一 Bot 下的角色共享</span><span>当前角色校准</span></div></header>
      ${plan?`<p class="state-edit-help">已排定的新周期参数从 ${e(plan.effective_date)} 开始采用。</p>`:""}`;
  }
  function planningSummary(status,e) {
    const settings=status.settings||{},planning=status.planning;
    const supported=fields("planning").every(key=>validField(key,settings[key]));
    const heading=`<header><h3>自动规划</h3></header>`;
    if(!supported)return heading+`<p class="state-edit-help">当前宿主尚未提供完整的自动规划设置，刷新或更新宿主后再查看。</p>`;
    const enabled=typeof planning?.enabled==="boolean"?planning.enabled:settings.planning_enabled;
    const calendar=typeof planning?.calendar_enabled==="boolean"?planning.calendar_enabled:settings.calendar_enabled;
    const state=!enabled?"已关闭":!calendar?"已开启 · 日程读写关闭，暂不规划":planning?.running?"正在规划":planning?"已开启 · 等待下次检查":"已开启 · 运行状态尚未提供";
    const mode={daily:"当天安排",horizon:"长期节点",refine:"临近细化"};
    const result=planning?.last_result;
    const resultState={succeeded:"已完成",blocked:"条件未满足",failed:"本次未完成",cancelled:"已取消",interrupted:"已中断"};
    const last=result?[mode[result.mode]||"规划任务",resultState[result.state]||"已有处理记录"].join(" · "):"尚无规划记录";
    const rejected=Array.isArray(result?.rejected)?result.rejected.length:result?.rejected;
    const counts=result?[Number.isInteger(result.saved)&&result.saved>=0?`保存 ${result.saved} 项`:null,
      Number.isInteger(rejected)&&rejected>=0?`未采用 ${rejected} 项`:null].filter(Boolean).join(" · "):"";
    const next=typeof planning?.next_check==="string"?new Date(planning.next_check):null;
    const nextText=next&&!Number.isNaN(next.valueOf())?next.toLocaleString("zh-CN",{hour12:false}):next?"检查时间暂不可用":"尚未排程";
    return heading+`<dl class="state-maintenance-summary"><div><dt>当前会话</dt><dd>${e(state)}</dd></div>
      <div><dt>安排节奏</dt><dd>每天安排 · 每周补充长期节点 · 提前 ${e(settings.planning_refine_minutes)} 分钟细化</dd></div>
      <div><dt>规划范围</dt><dd>${e(settings.planning_horizon_days)} 天 · 每次最多 ${e(settings.planning_max_items)} 项 · ${e(settings.planning_timezone)}</dd></div>
      <div><dt>最近一次</dt><dd>${e(last)}${counts?` · ${e(counts)}`:""}</dd></div><div><dt>下次检查（本地时间）</dt><dd>${e(nextText)}</dd></div></dl>
      ${result?.code||result?.task_id?`<details class="state-receipt-reference" data-receipt="${e("planning:"+(result.task_id||result.mode||"latest"))}"><summary id="state-planning-receipt-summary">查看规划处理记录</summary>${result.task_id?`<p>任务：${e(result.task_id)}</p>`:""}${result.code?`<p>原因：${e(result.code)}</p>`:""}</details>`:""}
      ${!calendar?`<p class="state-edit-help">此会话的日程读写尚未开启，可在状态维护设置中启用；仅开启自动规划不会改变日程权限。</p>`:""}`;
  }
  const titles={home:"状态与首页展示",intensity:"能量与状态表达",maintenance:"身体状态设置",
    calendar:"日程读写",planning:"自动规划设置",cycle:"生理期参数",align:"周期校准",
    mood:"心情动力学",patrol:"每日状态巡视"};
  function pendingText(command) {
    if(command.action!=="cycle.align")return null;
    return `周期校准：${applicability[command.data.applicability]}${command.data.day!==null?` · 第 ${command.data.day} 天`:""}`;
  }
  function actionSummary(kind,status,e) {
    const settings=status.settings||{},days=length(settings),timeline=status.state?.cycle_timeline;
    if(kind==="maintenance")return `${settings.health_enabled?"健康开启":"健康关闭"} · ${settings.hunger_enabled?"饥饿开启":"饥饿关闭"} · 当前人格共享`;
    if(kind==="home")return `${settings.enabled?"状态维护已开启":"状态维护已关闭"} · 每 ${e(settings.maintenance_minutes??"未提供")} 分钟更新`;
    if(kind==="intensity")return `${e(settings.humanized_state_intensity??"未提供")} / 100 · 当前人格共享`;
    if(kind==="cycle")return `${settings.cycle_enabled?"已开启":"未启用"} · ${e(modes[settings.cycle_mode]||"阶段模式待核对")} · ${e(Number.isFinite(days)?days:"未提供")} 天 · 当前人格共享`;
    if(kind==="align")return timeline?.cycle_day?`当前第 ${e(timeline.cycle_day)} / ${e(timeline.cycle_days)} 天 · 按实际设定校准`:
      timeline?.applicability==="not_applicable"?"当前角色标记为不适用":timeline?.applicability==="unknown"?"当前周期尚未定位":"校准当前角色的周期位置";
    if(kind==="mood")return `${settings.mood_enabled?"已开启":"已关闭"} · 每轮概率 ${e(settings.mood_update_probability??"未提供")} · 单次幅度 ${e(settings.mood_update_max_delta??"未提供")} · 当前会话`;
    if(kind==="patrol")return `${settings.daily_state_patrol_enabled?"已开启":"已关闭"} · ${e(settings.daily_state_patrol_time||"时刻待提供")} · 保留 ${e(settings.daily_state_patrol_retention_days??"未提供")} 天 · 当前会话`;
    return "查看并调整当前设置";
  }
  function syncDurationPreview(root) {
    if(!root)return;
    const values=Object.fromEntries(Object.keys(phases).map(key=>[key,Number(root.querySelector(`#state-config-cycle_${key}_days`)?.value)]));
    const total=Object.values(values).reduce((sum,value)=>sum+(Number.isFinite(value)&&value>0?value:0),0);
    const display=root.querySelector("[data-cycle-total]");if(display)display.textContent=String(total);
    for(const key of Object.keys(phases)) {
      const segment=root.querySelector(`[data-cycle-segment="${key}"]`),value=values[key];
      if(segment)segment.style.setProperty("--phase-share",`${total&&Number.isFinite(value)&&value>0?value/total*100:0}%`);
    }
  }
  function selectPhase(key) {if(Object.hasOwn(phases,key))selectedPhase=key;}
  function selectCycleView(view) {if(view==="plan"||view==="expression")selectedCycleView=view;}
  function resetPhase() {selectedPhase="menstrual";selectedCycleView="plan";}
  function toggleChecklist(name,current,value,checked) {
    const spec=definitions[name];if(spec?.type!=="checklist")return current;
    const selected=new Set(String(current||"").split(",").map(item=>item.trim()).filter(Boolean));
    if(checked)selected.add(value);else selected.delete(value);
    return Object.keys(spec.choices).filter(item=>selected.has(item)).join(",");
  }
  return {fields,label,validField,normalized,toggleChecklist,snapshot,canAlign,alignment,form,summary,planningSummary,titles,pendingText,phases,actionSummary,syncDurationPreview,selectPhase,selectCycleView,resetPhase};
})();
