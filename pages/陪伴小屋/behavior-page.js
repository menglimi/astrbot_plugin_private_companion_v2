/* 陪伴小屋 · 角色的群聊互动习惯。读真实记录，管理动作由后端确认。 */
"use strict";
window.CompanionBehaviorPage=(()=>{
  const e=value=>String(value??"").replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const assessment={welcomed:'欢迎',unwelcome:'不适',unclear:'尚不明确'};
  const delivery={planned:'尚未发送',started:'正在发送',returned:'发送调用已返回',unknown:'结果未知',failed:'发送失败'};
  const errors={group_behavior_revision_changed:'记录已变化，请重新读取。',group_behavior_habit_missing:'这条习惯已不可用，请重新读取。',
    dashboard_identity_required:'请重新登录 AstrBot。',staging_not_initialized:'角色数据尚未加载。',core_access_required:'当前账号没有管理权限。'};
  let root=null,version=0,readId=0,data={groups:[]},filter='',busy=false,loading=false,notice='',failed=false,apiBase='';
  const when=value=>Number.isFinite(Date.parse(value))?new Date(value).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}):'时间未知';
  async function api(method,route,body){
    const product=window.CompanionProduct;
    const bridge=product?.bridgeNow?.()||await product?.bridgeFor?.();
    if(!bridge?.apiGet)throw new Error('bridge_unavailable');
    let timer;
    try{
      const response=await Promise.race([method==='GET'?bridge.apiGet(route):bridge.apiPost(route,body),
        new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('bridge_timeout')),15000);})]);
      const wrapped=response?.status?response:response?.data?.status?response.data:null;
      if(wrapped?.status==='error')throw Object.assign(new Error('request_failed'),{code:wrapped.data?.code||wrapped.message});
      const value=wrapped?.status==='ok'?wrapped.data:product?.unwrap?product.unwrap(response):response;
      if(!value||typeof value!=='object')throw new Error('invalid_response');
      return value;
    }finally{clearTimeout(timer);}
  }
  const live=ticket=>ticket===version&&!!root?.isConnected;
  function row(group,item){
    const attempts=Array.isArray(item.attempts)?item.attempts:[];
    const latest=attempts[attempts.length-1];
    const feedback=Object.entries(item.member_feedback||{}).flatMap(([member,items])=>items.map(value=>({...value,member})));
    const latestFeedback=feedback.sort((a,b)=>String(b.at).localeCompare(String(a.at)))[0];
    const evidence=Array.isArray(item.evidence)?item.evidence:[];
    const memberCount=new Set(evidence.map(value=>value.speaker_id)).size;
    return `<article class="behavior-habit${item.enabled?'':' is-paused'}">
      <div class="behavior-habit-heading"><div><h3>${e(item.label)}</h3><div class="behavior-habit-meta"><span>群 ${e(group.group_id)}</span><span>${item.member_id?'成员 '+e(item.member_id):'群内互动'}</span><span>${memberCount} 位观察成员</span><time>${e(when(item.updated_at))}</time></div></div>
      <span class="behavior-state">${item.enabled?'已启用':'已停用'}</span></div>
      <dl class="behavior-habit-content"><div><dt>何时适用</dt><dd>${e(item.situation)}</dd></div><div><dt>互动动作</dt><dd>${e(item.action)}</dd></div><div><dt>对象与边界</dt><dd>${e(item.boundaries)}</dd></div></dl>
      <div class="behavior-feedback"><span>${latestFeedback?'最近反馈 · '+e(assessment[latestFeedback.assessment]||'尚不明确'):'尚无对象反馈'}</span>${latestFeedback?`<span>成员 ${e(latestFeedback.member)} · ${e(latestFeedback.reason)}</span>`:''}</div>
      <div class="behavior-habit-footer"><details><summary>观察与互动记录 <span>${evidence.length} 条证据</span></summary>
        ${evidence.slice(-3).map(value=>`<blockquote><p>${e(value.text)}</p><cite>成员 ${e(value.speaker_id)} · ${e(when(value.received_at))}</cite></blockquote>`).join('')}
        ${latest?`<div class="behavior-last-attempt"><strong>${e(delivery[latest.state]||'状态未知')}</strong><span>对象 ${e(latest.target_id)} · ${e(when(latest.returned_at||latest.planned_at))}</span><p>${e(latest.text||latest.reason)}</p></div>`:''}</details>
      <button type="button" class="button" data-behavior-toggle="${e(item.habit_id)}" data-behavior-group="${e(group.group_key)}" ${busy||loading?'disabled':''}>${item.enabled?'停用':'恢复'}</button></div>
    </article>`;
  }
  function render(){
    if(!root)return;
    const groups=(data.groups||[]).filter(group=>!filter||group.group_key===filter);
    const count=groups.reduce((sum,group)=>sum+group.habits.length,0);
    const enabled=groups.reduce((sum,group)=>sum+group.habits.filter(item=>item.enabled).length,0);
    root.innerHTML=`<header class="behavior-learning-head"><div><h2>学到的互动</h2><p>${count} 条习惯 <span>·</span> ${enabled} 条启用</p></div><div class="behavior-learning-tools"><label><span class="behavior-sr-only">筛选群聊</span><select data-behavior-filter ${busy?'disabled':''}><option value="">全部群聊</option>${(data.groups||[]).map(group=>`<option value="${e(group.group_key)}" ${filter===group.group_key?'selected':''}>群 ${e(group.group_id)}</option>`).join('')}</select></label><button type="button" class="button" data-behavior-refresh ${busy||loading?'disabled':''}>${loading?'读取中…':'重新读取'}</button></div></header>
      ${notice?`<p class="behavior-notice${failed?' is-error':''}" role="status">${e(notice)}</p>`:''}
      ${loading&&!count?'<p class="behavior-empty" role="status">正在读取互动习惯…</p>':count?`<div class="behavior-habits">${groups.map(group=>group.habits.map(item=>row(group,item)).join('')).join('')}</div>`:`<div class="behavior-empty" role="status">${failed?'互动习惯暂不可读取':'尚未学到互动习惯'}</div>`}`;
  }
  async function read(ticket){
    const current=++readId;
    loading=true;render();
    try{
      const value=await api('GET',apiBase+'/behavior');
      if(!Array.isArray(value.groups)||value.groups.some(group=>!Array.isArray(group.habits)))throw new Error('invalid_response');
      if(!live(ticket)||current!==readId)return;
      data=value;
      if(filter&&!data.groups.some(group=>group.group_key===filter))filter='';
    }catch(error){
      if(!live(ticket)||current!==readId)return;
      notice=errors[error.code]||'读取失败，请稍后重新读取。';failed=true;
    }finally{if(live(ticket)&&current===readId){loading=false;render();}}
  }
  async function toggle(group,item){
    if(busy||loading)return;
    const ticket=version;
    busy=true;notice='';failed=false;render();
    try{
      const result=await api('POST',apiBase+'/behavior/command',{group_key:group.group_key,habit_id:item.habit_id,enabled:!item.enabled,revision:item.revision});
      if(!live(ticket))return;
      if(result.saved!==true)throw new Error('invalid_response');
      notice=result.enabled?'已恢复这条互动习惯':'已停用这条互动习惯';
    }catch(error){
      if(!live(ticket))return;
      notice=errors[error.code]||'未收到保存确认，请重新读取后核对。';failed=true;
    }finally{
      if(live(ticket)){await read(ticket);busy=false;render();}
    }
  }
  function click(event){
    if(event.target.closest('[data-behavior-refresh]')){if(!busy&&!loading){notice='';failed=false;void read(version);}return;}
    const button=event.target.closest('[data-behavior-toggle]');
    if(!button)return;
    const group=(data.groups||[]).find(value=>value.group_key===button.dataset.behaviorGroup);
    const item=group?.habits.find(value=>value.habit_id===button.dataset.behaviorToggle);
    if(item)void toggle(group,item);
  }
  function change(event){if(event.target.matches('[data-behavior-filter]')){filter=event.target.value;render();}}
  function mount(host,options={}){
    unmount();root=host;data={groups:[]};filter='';busy=false;loading=false;notice='';failed=false;
    root?.addEventListener('click',click);root?.addEventListener('change',change);
    const prefix='/astrbot_plugin_private_companion/';
    apiBase=typeof options.api==='string'&&options.api.startsWith(prefix)?options.api.slice(prefix.length):'';
    if(root&&apiBase)void read(version);
    else if(root){notice='请先选择已配置的角色。';render();}
  }
  function unmount(){++version;++readId;root?.removeEventListener('click',click);root?.removeEventListener('change',change);root=null;}
  return {mount,unmount};
})();
