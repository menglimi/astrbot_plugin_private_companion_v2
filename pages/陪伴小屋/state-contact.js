"use strict";
window.CompanionStateContact = (() => {
  const definitions={
    enabled:{label:"允许主动联系",type:"boolean"},automatic_enabled:{label:"启用后台自动联系",type:"boolean"},
    idle_seconds:{label:"对话结束后至少等候（秒）",type:"number",min:0,max:86400},
    interval_seconds:{label:"两次联系至少间隔（秒）",type:"number",min:60,max:604800},
    max_contacts_24h:{label:"24 小时内最多联系（次）",type:"number",min:0,max:100},
    max_attempts_24h:{label:"24 小时内最多尝试（次）",type:"number",min:0,max:1000},
    event_max_age_seconds:{label:"生活事件可接续时长（秒）",type:"number",min:60,max:86400},
    quiet_enabled:{label:"启用免打扰时段",type:"boolean"},quiet_start:{label:"免打扰开始",type:"time"},
    quiet_end:{label:"免打扰结束",type:"time"},quiet_timezone:{label:"免打扰时区",type:"timezone"},
    pause_until:{label:"暂缓全部联系至（本地时间）",type:"datetime"},note:{label:"补充联系偏好",type:"textarea"},
    silence_min_confidence:{label:"开口置信度门槛（0–1）",type:"probability"},
    silence_feedback_penalty:{label:"沉默反馈降权（0–1）",type:"probability"},
    /* 天气三条链路。数据源凭据由宿主环境变量提供，不在这里配置；
       这里只管「什么时候看天气」和「什么时候因此开口」。 */
    weather_checkin_enabled:{label:"定时天气问候",type:"boolean"},
    weather_checkin_time:{label:"问候时刻（本地时间）",type:"time"},
    weather_sample_minutes:{label:"天气采样间隔（分钟）",type:"number",min:10,max:1440},
    weather_change_enabled:{label:"天气突变时联系",type:"boolean"},
    dedup_weather_window_minutes:{label:"同内容不重复时长（分钟）",type:"number",min:0,max:2880},
    official_weather_alert_enabled:{label:"转发官方气象预警",type:"boolean"},
    official_alert_poll_minutes:{label:"预警轮询间隔（分钟）",type:"number",min:1,max:1440},
    official_alert_min_severity:{label:"最低预警级别",type:"severity"}
  };
  const purposeKey=/^[a-z][a-z0-9_]{0,63}$/;
  const purposeField=/^([a-z][a-z0-9_]{0,63})\.(enabled|weight|pause_until)$/;
  /* V2 用 CAP 五级，空值表示不过滤。这里只暴露后端接受的取值，
     不暴露 unknown——那是响应里可能出现的值，不是可以选的门槛。 */
  const severityOptions=[["","不限制（全部转发）"],["minor","蓝色 · 一般"],["moderate","黄色 · 较重"],
    ["severe","橙色 · 严重"],["extreme","红色 · 特别严重"]];
  const severityValues=new Set(severityOptions.map(([value])=>value));
  const purposeDefinitions={enabled:{label:"允许此类联系",type:"boolean"},weight:{label:"相对权重",type:"weight"},pause_until:{label:"暂缓此类联系至（本地时间）",type:"datetime"}};
  const reasons={proactive_disabled:"联系或对应目的尚未开启",proactive_paused:"当前仍在暂停期",proactive_quiet_hours:"当前处于免打扰时段",
    automatic_contact_disabled:"后台自动联系尚未开启",proactive_automatic_disabled:"后台自动联系尚未开启",contact_automatic_disabled:"后台自动联系尚未开启",
    model_task_unregistered:"主动联系模型尚未就绪",authorization_denied:"当前对象尚未获得联系授权",
    binding_revoked:"当前身份授权已撤销",role_binding_changed:"当前角色绑定已变化",host_not_running:"宿主尚未运行"};
  const purposes=value=>value?.purposes&&typeof value.purposes==="object"&&!Array.isArray(value.purposes)
    ?Object.entries(value.purposes).filter(([key,item])=>purposeKey.test(key)&&item&&typeof item.label==="string"):[];
  const fields=value=>[...Object.keys(definitions),...purposes(value).flatMap(([key])=>Object.keys(purposeDefinitions).map(suffix=>key+"."+suffix))];
  const spec=name=>Object.hasOwn(definitions,name)?definitions[name]:purposeDefinitions[purposeField.exec(name)?.[2]];
  const label=(name,value)=>(Object.hasOwn(definitions,name)?definitions[name].label:null)||((value?.purposes?.[purposeField.exec(name)?.[1]]?.label||purposeField.exec(name)?.[1]||name)+" · "+(spec(name)?.label||""));
  const zoned=value=>typeof value==="string"&&/(Z|[+-]\d{2}:\d{2})$/i.test(value)&&Number.isFinite(Date.parse(value));
  function validField(name,value) {
    const field=spec(name);if(!field)return false;
    if(field.type==="boolean")return typeof value==="boolean";
    if(field.type==="number")return Number.isInteger(value)&&value>=field.min&&value<=field.max;
    if(field.type==="probability")return typeof value==="number"&&Number.isFinite(value)&&value>=0&&value<=1
      &&Number(value.toFixed(6))===value;
    if(field.type==="weight")return typeof value==="number"&&Number.isFinite(value)&&value>0&&Number(value.toFixed(6))===value;
    if(field.type==="severity")return typeof value==="string"&&severityValues.has(value);
    if(typeof value!=="string"||[...value].length>8192)return false;
    if(field.type==="time")return /^([01]\d|2[0-3]):[0-5]\d$/.test(value);
    if(field.type==="datetime")return value===""||zoned(value);
    return field.type!=="timezone"||!!value.trim();
  }
  const supported=value=>!!value?.settings&&typeof value.edit_token==="string"&&purposes(value).length>0
    &&fields(value).every(key=>validField(key,value.settings[key]));
  function normalized(values) {
    const result={};
    for(const [name,raw] of Object.entries(values)){
      const field=spec(name);if(!field)throw new Error("当前联系设置已变化，请刷新后核对。");
      let value=raw;
      if(["number","weight","probability"].includes(field.type))value=raw===""?NaN:Number(raw);
      if(field.type==="timezone"&&typeof value==="string")value=value.trim();
      if(field.type==="datetime"&&value!==""&&!zoned(value)){
        if(typeof value!=="string"||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,3})?)?$/.test(value)||!Number.isFinite(Date.parse(value)))throw new Error("请选择有效的暂停截止时间，或留空取消当前会话的暂停。");
        value=new Date(value).toISOString();
      }
      if(!validField(name,value))throw new Error(field.type==="number"?`${field.label}请填写 ${field.min}–${field.max} 之间的整数。`
        :field.type==="probability"?`${field.label}请填写 0 到 1 之间的小数，最多 6 位。`
        :field.type==="weight"?"联系权重需为正数，最多保留 6 位小数。":`请核对${field.label}。`);
      if(field.type==="timezone"){
        try{new Intl.DateTimeFormat("zh-CN",{timeZone:value}).format();}catch{throw new Error("请填写有效的免打扰时区，例如 Asia/Shanghai。");}
      }
      result[name]=value;
    }
    return result;
  }
  function localValue(value) {
    if(!value||!zoned(value))return value||"";
    const date=new Date(value),pad=number=>String(number).padStart(2,"0");
    return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  }
  /* 数值、概率、权重、时间必须填；文本与 textarea 允许留空。
     severity 的空值（不过滤）也是合法选项，不能标 required——
     否则浏览器会拦住「全部转发」这个正当选择。 */
  const required=(definition)=>["number","probability","weight","time","timezone"].includes(definition.type);
  function field(name,values,e) {
    const definition=spec(name),id="state-contact-"+name.replaceAll(".","-"),value=values[name];
    const base=`id="${e(id)}" data-state-field="${e(name)}"`;
    if(definition.type==="boolean")return `<label class="state-checkbox"><input ${base} type="checkbox" ${value?"checked":""}>${definition.label}</label>`;
    if(definition.type==="severity")return `<label for="${e(id)}">${definition.label}<select ${base}>${severityOptions.map(([option,text])=>`<option value="${e(option)}" ${value===option?"selected":""}>${e(text)}</option>`).join("")}</select></label>`;
    const input=definition.type==="textarea"?`<textarea ${base} rows="4" placeholder="例如：忙的时候少打扰；有值得分享的事可以轻松聊几句。">${e(value)}</textarea>`
      :definition.type==="datetime"?`<input ${base} type="datetime-local" step="1" value="${e(localValue(value))}">`
      :`<input ${base} type="${definition.type==="timezone"?"text":"number"}" ${required(definition)?"required":""} ${definition.type==="number"?`min="${definition.min}" max="${definition.max}" step="1"`:definition.type==="probability"?'min="0" max="1" step="0.01"':definition.type==="weight"?'min="0.000001" step="0.000001"':definition.type==="time"?'step="60"':'autocomplete="off"'} value="${e(value)}">`;
    return `<label for="${e(id)}">${definition.label}${input}</label>`;
  }
  function form(draft,e) {
    const values=draft.values;
    return `<p class="state-edit-help">当前会话与角色 · 保存不触发发送</p>
      <h4 class="state-form-section">联系节奏</h4><div class="state-edit-fields">${["enabled","automatic_enabled","idle_seconds","interval_seconds","max_contacts_24h","max_attempts_24h","event_max_age_seconds"].map(name=>field(name,values,e)).join("")}</div>
      <p class="state-edit-help">3600 秒 = 1 小时</p>
      <h4 class="state-form-section">行为规划与沉默</h4><div class="state-edit-fields">${["silence_min_confidence","silence_feedback_penalty"].map(name=>field(name,values,e)).join("")}</div>
      <p class="state-edit-help">门槛：0 不限制，1 仅完全确定时开口。</p>
      <h4 class="state-form-section">免打扰与临时暂停</h4><div class="state-edit-fields">${["quiet_enabled","quiet_start","quiet_end","quiet_timezone","pause_until"].map(name=>field(name,values,e)).join("")}</div>
      <p class="state-edit-help">免打扰起止相同表示全天；暂停留空后继承上级设置。</p>
      <h4 class="state-form-section">可以因为什么联系</h4>
      <div class="state-contact-purposes">${draft.purposes.map(([key,item])=>`<section class="state-contact-purpose" aria-labelledby="state-contact-purpose-${e(key)}"><h5 id="state-contact-purpose-${e(key)}">${e(item.label)}</h5><div class="state-edit-fields">${Object.keys(purposeDefinitions).map(suffix=>field(key+"."+suffix,values,e)).join("")}</div></section>`).join("")}</div>
      <h4 class="state-form-section">天气</h4>
      <div class="state-edit-fields">${["weather_checkin_enabled","weather_checkin_time"].map(name=>field(name,values,e)).join("")}</div>
      <p class="state-edit-help">天气使用「感知」中的角色地点。</p>
      <div class="state-edit-fields">${["weather_change_enabled","weather_sample_minutes","dedup_weather_window_minutes"].map(name=>field(name,values,e)).join("")}</div>
      <p class="state-edit-help">去重时长为 0 时关闭内容去重。</p>
      <div class="state-edit-fields">${["official_weather_alert_enabled","official_alert_poll_minutes","official_alert_min_severity"].map(name=>field(name,values,e)).join("")}</div>
      <p class="state-edit-help">预警需要城市、区域和数据源凭据；在「感知」中检查。</p>
      <h4 class="state-form-section">表达与边界</h4>${field("note",values,e)}<p class="state-edit-help">最多 8192 字</p>`;
  }
  const reason=code=>reasons[code]||(code?"需要核对："+code:"尚未提供运行条件");
  const when=value=>value&&Number.isFinite(Date.parse(value))?new Date(value).toLocaleString("zh-CN",{hour12:false}):"未设置";
  function summary(value,e) {
    if(!supported(value))return `<header><h3>主动联系偏好</h3><p>当前宿主尚未提供完整的联系设置，请刷新或更新宿主后再查看。</p></header>`;
    const settings=value.settings,effective=value.effective||{};
    const allowance=effective.allowed===true?"当前授权通过":effective.allowed===false?reason(effective.reason):"当前授权尚未提供";
    const automatic=effective.automatic_allowed===true?"自动联系条件已满足":effective.automatic_allowed===false?reason(effective.automatic_reason):"自动联系条件尚未提供";
    const relation=Number.isInteger(settings.max_relationship_contacts_24h)&&Number.isInteger(settings.max_relationship_attempts_24h)
      ?`<p class="state-edit-help">同一关系共享上限：24 小时内最多联系 ${e(settings.max_relationship_contacts_24h)} 次、尝试 ${e(settings.max_relationship_attempts_24h)} 次。此处只读，由关系或角色层统一管理。</p>`:"";
    return `<header><h3>主动联系偏好</h3></header>
      <dl class="state-maintenance-summary"><div><dt>联系开关</dt><dd>${settings.enabled?"允许主动联系":"主动联系已关闭"} · ${settings.automatic_enabled?"后台自动联系已开启":"后台自动联系已关闭"}</dd></div>
      <div><dt>当前条件</dt><dd>${e(allowance)} · ${e(automatic)}</dd></div>
      <div><dt>联系间隔与额度</dt><dd>至少间隔 ${e(settings.interval_seconds)} 秒 · 24 小时最多 ${e(settings.max_contacts_24h)} 次</dd></div>
      <div><dt>行为规划与沉默</dt><dd>开口门槛 ${e(settings.silence_min_confidence)} · 沉默降权 ${e(settings.silence_feedback_penalty)}</dd></div>
      <div><dt>免打扰</dt><dd>${settings.quiet_enabled?`${e(settings.quiet_start)}–${e(settings.quiet_end)} · ${e(settings.quiet_timezone)}`:"未启用"}</dd></div>
      <div><dt>暂停截止（本地时间）</dt><dd>${e(when(settings.pause_until))}</dd></div><div><dt>运行与模型</dt><dd>${e(({running:"宿主运行中",new:"宿主尚未启动",stopped:"宿主已停止",closed:"宿主已关闭",faulted:"宿主运行异常"})[value.host_state]||"宿主状态待核对")} · ${effective.model_registered===true?"联系模型已登记":effective.model_registered===false?"联系模型尚未就绪":"模型状态待核对"}</dd></div></dl>${relation}
      <details class="state-receipt-reference" data-receipt="contact-purposes"><summary id="state-contact-purpose-summary">查看各类联系的当前条件</summary><ul class="state-contact-status">${purposes(value).map(([key,item])=>`<li><strong>${e(item.label)}</strong><span>${item.allowed===true?"当前允许":item.allowed===false?e(reason(item.reason)):"条件待核对"} · 权重 ${e(settings[key+".weight"])}</span></li>`).join("")}</ul></details>`;
  }
  return {fields,purposes,label,validField,supported,normalized,form,summary};
})();
