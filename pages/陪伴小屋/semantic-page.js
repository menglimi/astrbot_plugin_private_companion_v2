/* Live semantic settings and scoped catalog administration. */
"use strict";
window.CompanionSemanticPage = (() => {
  const product = window.CompanionProduct;
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const fields = {reaction:[["name","名称"],["description","画面与动作"],["visible_text","可见文字"],["tags","标签"],["emotions","情绪"],["intents","适用回应"]],slang:[["meaning","含义"],["usage","用法"]]};
  const errors = {
    staging_not_initialized:"请先在账号与会话中加载 V2 运行实例，再回到本页。",
    staging_host_terminated:"V2 宿主已停止，请重新打开插件页面。",
    dashboard_identity_required:"请从已登录的 AstrBot 管理页面打开陪伴小屋。",
    authorization_denied:"当前对象尚未授予读取语义素材所需权限，请在关系与权限页核对。",
    core_access_required:"当前管理账号没有语义素材管理权限。",
    semantic_request_invalid:"语义素材请求与当前接口不匹配，请更新页面后重试。",
    semantic_group_input_required:"当前群会话还没有可核实的成员输入；收到群消息后即可管理。",
    semantic_target_unavailable:"当前选择的对象或角色不可用，请重新选择。",
    semantic_scope_changed:"会话范围已变化，请重新选择对象后刷新。",
    semantic_stopped:"语义服务所在的后台已停止，请重新启动宿主。",
    supervisor_fenced:"当前角色后台尚未运行或已被替换。请在账号与会话页核对并启动后，再读取语义素材。",
    semantic_model_failed:"语义模型调用失败，请核对嵌入模型配置后重试。",
    semantic_conflict:"配置已变化，请刷新核对最新版本。",
    semantic_item_missing:"这条素材已不存在，请刷新列表。",
    semantic_result_changed:"结果已变化，请刷新后核对。",
    semantic_action_unavailable:"当前状态下不能执行该操作，请刷新后重试。",
    semantic_offer_conflict:"该修改与已有结果冲突，请刷新核对。",
    slang_evidence_unavailable:"群黑话缺少可用证据，暂时无法整理。",
    bridge_timeout:"连接超时，请核对连接后重试。",
    invalid_response:"配置数据不完整，请刷新核对。",
  };
  /* 后端把机器码放在信封的 message 上（页面桥只转发 message），而共享的
     CompanionProduct.labels 表不含这里用到的多数码，因此这一页要自带一张表。
     但 message 有时是可直接展示的原因句（例如「settings changed; refresh…」），
     那种情况必须原样保留，否则会丢掉后端给出的真实信息。只有形如机器码的
     值才走翻译。 */
  const isCode = value => typeof value === "string" && /^[a-z][a-z0-9_]{2,60}$/.test(value);
  const localized = (failure, fallback) => errors[failure?.code]
    || (isCode(failure?.message) ? errors[failure.message] : failure?.message)
    || fallback;
  const flags = [["enabled","启用嵌入能力"],["memory_enabled","记忆语义召回"],["reactions_enabled","表情检索"],["slang_enabled","群词义检索"],["slang_learning","自动整理群词义"],["slang_web_search_enabled","群词义联网参考（仅作参考证据）"],["vision_review","发送前视觉复核"]];
  const providerFields = [["embedding_provider","嵌入模型","embedding"],["rerank_provider","候选重排","rerank"],["analysis_provider","视觉与词义分析","analysis"]];
  const numberFields = [["timeout_seconds","模型超时 / 秒",1,30],["batch_size","索引批次",1,64],["learning_interval_seconds","群词义整理间隔 / 秒",60,86400],["slang_web_search_candidates","联网检索词数 / 个",1,12],["slang_web_search_results","每词参考条数",1,5]];
  /* 这一页发送的是全部 15 个可编辑字段（不是只发改动），而 revision 冲突后必须重读
     才能拿到新版本号。重读会把 state 换成服务端的值，所以本地草稿要单独留一份，
     否则用户刚填的 15 项会被服务端旧值覆盖。 */
  let root,scope,abort,state,kind="reaction",view="all",after="",sessionId="",busy=false,editing=null,result=null,message="",generation=0,draft=null,conflict=false;
  const visibleFlags = () => view === "expression"
    ? flags.filter(([id]) => id === "reactions_enabled")
    : view === "learning" ? flags.filter(([id]) => id !== "reactions_enabled") : flags;
  const visibleProviders = () => view === "expression" ? [] : providerFields;
  const visibleNumbers = () => view === "expression" ? [] : numberFields;
  const visibleKinds = group => view === "expression" ? ["reaction"]
    : view === "learning" ? (group ? ["slang"] : [])
      : (group ? ["reaction","slang"] : ["reaction"]);
  const selection = () => {const value=product.selection();return {target_id:value.target_id,role_id:value.role_id,...(sessionId?{session_id:sessionId}:{})};};
  const current = () => root?.isConnected && scope===product.scopeKey();
  const active = ticket => ticket===generation && current();
  async function api(method,values) {
    /* 等桥就绪，而不是当场读 window.AstrBotPluginPage。
       主页面此前不引页面桥 SDK，桥是在 product.connect() 里动态补上的；
       这一页若在它补好之前就发请求，读到的是 undefined，用户看到的是
       「未连接」——一个只在几百毫秒窗口里出现的假故障。 */
    const bridge=product.bridgeNow()||await product.bridgeFor();
    return product.unwrap(await (method==="GET"?bridge.apiGet("semantic",values):bridge.apiPost("semantic",values)));
  }
  const toggle=(id,label,value) => '<label class="semantic-toggle"><span>'+label+'</span><input type="checkbox" name="'+id+'" '+(value?"checked":"")+'></label>';
  const options=(list,value) => '<option value="">自动选择</option>'+(list||[]).map(p=>'<option value="'+escape(p.id)+'" '+(p.id===value?"selected":"")+'>'+escape(p.name||p.id)+'</option>').join("");
  function editor(item) {
    let html='<form id="semanticEditor" class="semantic-editor"><div class="semantic-heading"><h3>'+escape(item.payload.name||item.payload.term||"素材详情")+'</h3><button type="button" class="icon-button" data-semantic="close" aria-label="关闭编辑" title="关闭"><i data-lucide="x"></i></button></div>';
    if(item.image_url)html+='<img src="'+item.image_url+'" alt="'+escape(item.payload.name||"表情原图")+'" loading="lazy">';
    html+=fields[kind].map(([id,label])=>'<label>'+label+'<textarea name="'+id+'" rows="'+(id==="description"||id==="meaning"?3:2)+'" maxlength="'+(kind==="slang"?500:1500)+'">'+escape(item.payload[id]||"")+'</textarea></label>').join("");
    html+=toggle("item_enabled","允许检索使用",!!item.enabled);
    html+='<div class="semantic-actions"><button class="button primary" type="submit" '+(busy?"disabled":"")+'>保存修改</button>';
    if(kind==="reaction")html+='<button class="button" type="button" data-semantic="analyze" '+(busy?"disabled":"")+'>识别图片</button>';
    return html+'<button class="button" type="button" data-semantic="close">取消</button></div></form>';
  }
  function render() {
    if(!current())return;
    if(!product.hosted()){root.innerHTML='<div class="settings-heading"><div><h2>语义理解与素材</h2></div></div><p class="memory-notice" role="status">未读取到宿主目录。</p><div class="semantic-actions"><button class="button" type="button" data-workspace-retry>重新读取</button></div>';return;}
    if(!state){
      /* 尚未加载或运行时，先到宿主工作区处理；其他读取失败才提供重试。 */
      const blocking=[errors.staging_not_initialized,errors.staging_host_terminated,
        errors.semantic_stopped,errors.supervisor_fenced].includes(message);
      const action=busy?"":'<div class="semantic-actions">'+(blocking
        ?'<button class="button" type="button" data-go="manage" data-manage="host">打开账号与会话</button>'
        :'<button class="button" type="button" data-semantic="retry">重新读取</button>')+'</div>';
      root.innerHTML='<div class="settings-heading"><div><h2>语义理解与素材</h2></div></div>'
        +'<p class="memory-notice" role="status">'+escape(message||"正在读取实际配置…")+'</p>'+action;
      return;
    }
    const cfg=state.settings,group=product.target()?.scope_kind==="group";
    /* 有草稿时按草稿渲染：冲突重读之后用户填的值仍在。 */
    const shown=draft?{...cfg,...draft}:cfg;
    const currentViewFlags=visibleFlags(),currentViewProviders=visibleProviders(),currentViewNumbers=visibleNumbers();
    const kinds=visibleKinds(group);
    const heading=view==="expression"?"表情素材与检索":"语义理解与学习素材";
    let html='<div class="settings-heading"><div><h2>'+heading+'</h2></div><span class="semantic-state '+escape(state.state)+'">'+escape({ready:"嵌入已就绪",lexical_fallback:"关键词回退",disabled:"已停用"}[state.state]||state.state)+'</span></div>';
    html+='<p class="semantic-feedback'+(conflict?" semantic-conflict":"")+'" role="status">'+escape(message)+'</p><section class="semantic-section"><div class="semantic-heading"><h3>'+(view==="expression"?"表情检索":"语义模型与学习")+'</h3><span>配置版本 '+cfg.revision+(draft?' · <strong>草稿待核对</strong>':'')+'</span></div><form id="semanticSettings">';
    html+='<div class="semantic-flags">'+currentViewFlags.map(([id,label])=>toggle(id,label,shown[id])).join("")+'</div>';
    if(currentViewProviders.length||currentViewNumbers.length)html+='<div class="semantic-providers">';
    currentViewProviders.forEach(([id,label,type])=>html+='<label>'+label+'<select name="'+id+'">'+options(state.providers?.[type],shown[id])+'</select></label>');
    currentViewNumbers.forEach(([id,label,min,max])=>html+='<label>'+label+'<input name="'+id+'" type="number" min="'+min+'" max="'+max+'" value="'+shown[id]+'"></label>');
    if(currentViewProviders.length||currentViewNumbers.length)html+='</div>';
    if(view==="expression")html+='<p class="semantic-meta">群词义与通用语义模型设置在「学习与反思」页。</p>';
    if(view==="learning"&&!group)html+='<p class="semantic-meta">当前是私聊范围。记忆语义召回在对话中按权限读取；群词义素材只在关系网中的群会话里整理。</p>';
    html+='<div class="semantic-actions"><button class="button primary" type="submit" '+(busy?"disabled":"")+'>'+(draft?'保存草稿':'保存配置')+'</button>';
    /* 冲突时更要能放弃：否则用户只剩「按新版本再存一次」一条路。 */
    if(draft)html+='<button class="button" type="button" data-semantic="discard">放弃草稿</button>';
    html+='<button class="button" type="button" data-semantic="reindex" '+(busy||!state.selection_ready?"disabled":"")+'>重建当前索引</button></div></form>';
    html+='<p class="semantic-meta">'+(Object.keys(state.errors||{}).length?' 最近异常：'+escape(Object.values(state.errors).join("、")):"")+'</p></section>';
    if(kinds.length)html+='<section class="semantic-section"><div class="semantic-heading"><h3>'+(view==="expression"?"表情库":"群词义素材")+'</h3><span>'+(view==="expression"?'表情 '+(state.catalog?.reaction?.enabled||0)+' 项':'群词义 '+(state.catalog?.slang?.enabled||0)+' 项')+'</span></div>';
    if(group&&state.sessions?.length)html+='<label class="semantic-session">群会话<select id="semanticSession" aria-label="群会话">'+state.sessions.map(id=>'<option value="'+escape(id)+'" '+(id===state.session_id?'selected':'')+'>'+escape(id===product.target()?.group_id?'主群会话':id)+'</option>').join('')+'</select></label>';
    if(kinds.length&&!state.selection_ready)html+='<p class="memory-notice">当前群会话尚无可验证的成员输入；收到群消息后即可管理。</p>';
    else if(kinds.length) {
      if(kinds.length>1)html+='<div class="semantic-toolbar"><div class="semantic-tabs" role="tablist"><button role="tab" aria-selected="'+(kind==="reaction")+'" data-semantic-kind="reaction">表情</button><button role="tab" aria-selected="'+(kind==="slang")+'" data-semantic-kind="slang">群词义</button></div>';
      else html+='<div class="semantic-toolbar"><span class="semantic-kind-label">'+(kind==="reaction"?"表情素材":"当前群词义")+'</span>';
      html+='<form id="semanticSearch"><input name="query" type="search" maxlength="2000" placeholder="检索'+(kind==="reaction"?"表情":"群词义")+'" aria-label="检索素材"><button class="button" '+(busy?"disabled":"")+'>检索</button></form></div>';
      if(kind==="reaction")html+='<div class="semantic-import"><label>导入表情图片 / GIF<input id="semanticFile" type="file" accept="image/png,image/jpeg,image/webp,image/gif" '+(busy?"disabled":"")+'></label><span>单张不超过 5 MB，按内容去重。</span></div>';
      if(result)html+='<div class="semantic-results"><strong>检索结果 · '+(result.mode==="hybrid"?"语义与关键词":"关键词")+'</strong><span>'+(result.embedded||0)+'/'+(result.eligible||0)+' 已建索引'+(result.fallback_reason?" · 模型暂不可用":"")+'</span>'+(result.items||[]).map(item=>'<button data-semantic-open="'+escape(item.id)+'">'+escape(item.payload.name||item.payload.term||item.id)+' · '+Number(item.score).toFixed(2)+'</button>').join("")+'</div>';
      html+='<div class="semantic-list">'+(state.items||[]).map(item=>'<div class="semantic-row"><div><strong>'+escape(item.payload.name||item.payload.term||"未命名")+'</strong><p>'+escape(item.payload.description||item.payload.meaning||"待标注")+'</p><small>'+(item.enabled?"已启用":"已停用")+' · '+escape(item.payload.analysis||item.payload.source||"手动")+' · 版本 '+item.revision+(item.source_valid===false?" · 来源已失效":"")+'</small></div><button class="button small" data-semantic-open="'+escape(item.id)+'">编辑</button></div>').join("")+'</div>';
      if(!state.items?.length)html+='<p class="memory-notice">当前没有素材。</p>';
      if(state.next_after)html+='<button class="button" data-semantic="more" '+(busy?'disabled':'')+'>加载更多</button>';
      if(editing)html+=editor(editing);
    }
    if(kinds.length)html+='</section>';
    root.innerHTML=html;
    window.lucide?.createIcons({nodes:root.querySelectorAll("[data-lucide]")});
  }
  async function load(append=false){
    if(!current()||!product.hosted()||(append&&busy))return;
    const ticket=++generation;
    const old=append?state?.items||[]:[];
    if(append||!state)message="";
    busy=true;if(!append)state=null;render();
    try{let data=await api("GET",{...selection(),kind,...(append&&after?{after}:{})});
      if(!active(ticket))return;
      if(!append&&!sessionId&&!data.selection_ready&&data.sessions?.length){sessionId=data.sessions[0];data=await api("GET",{...selection(),kind});}
      if(!active(ticket))return;state={...data,items:[...old,...data.items]};after=data.next_after||"";}
    catch(error){if(active(ticket))message=localized(error,"读取失败，请重试。");}
    finally{if(active(ticket)){busy=false;render();}}
  }
  async function run(action,payload={}){
    if(busy||!current())return;
    const ticket=++generation;
    busy=true;message="正在处理…";conflict=false;render();
    try{
      const data=await api("POST",{...selection(),action,...payload});
      if(!active(ticket))return;
      if(action==="search"){result=data;message="";busy=false;render();return;}
      message={configure:"配置已保存",reindex:"索引重建已安排",import:"表情已收录",analyze:"图片识别已更新",edit:"素材已保存"}[action];
      editing=null;busy=false;
      /* 配置保存成功才清草稿；素材类操作不该动设置草稿。 */
      if(action==="configure")draft=null;
      await load();
    }catch(error){
      if(!active(ticket))return;
      busy=false;
      if(action==="configure"&&String(error.message||"").indexOf("settings changed")>=0){
        /* 版本冲突：服务端已被别处改过。把这次提交的内容留作草稿，重读拿到新版本号，
           用户填的值不被服务端旧值覆盖，也不会显示成「已保存」。 */
        conflict=true;
        draft={...(payload.changes||{})};
        message="这份配置已被别处修改。你填的值仍保留在下面，核对后再次保存即可按新版本写入。";
        try{await load();}catch(_){render();return;}
        return;
      }
      message=localized(error,"操作失败，请刷新核对。");
      render();
    }
  }
  async function open(id){
    if(busy)return;const ticket=++generation;busy=true;message="正在读取原件…";render();
    try{const data=await api("GET",{...selection(),kind,id});if(active(ticket)){editing={...data.item,image_url:data.image_url};message="";}}
    catch(error){if(active(ticket))message=localized(error,"原件暂不可用");}
    finally{if(active(ticket)){busy=false;render();root.querySelector("#semanticEditor")?.scrollIntoView({block:"nearest"});}}
  }
  function mount(node,options={}){
    unmount();root=node;scope=product.scopeKey();state=null;result=null;after="";sessionId="";editing=null;message="";busy=false;
    view=["learning","expression"].includes(options?.view)?options.view:"all";
    kind=view==="learning"&&product.target()?.scope_kind==="group"?"slang":"reaction";abort=new AbortController();
    node.addEventListener("click",event=>{
      const tab=event.target.closest("[data-semantic-kind]");if(tab){kind=tab.dataset.semanticKind;result=null;editing=null;after="";message="";load();return;}
      const item=event.target.closest("[data-semantic-open]");if(item){open(item.dataset.semanticOpen);return;}
      const command=event.target.closest("[data-semantic]")?.dataset.semantic;
      if(command==="close"){editing=null;render();}
      if(command==="retry")load();
      if(command==="more")load(true);
      if(command==="reindex")run("reindex");
      if(command==="discard"){draft=null;conflict=false;message="已放弃草稿，显示当前已保存配置。";render();}
      if(command==="analyze"&&editing)run("analyze",{id:editing.id});
    },{signal:abort.signal});
    node.addEventListener("submit",event=>{
      event.preventDefault();const form=event.target,values=new FormData(form);
      if(form.id==="semanticSettings"){
        const changes={},visibleFlagIds=new Set(visibleFlags().map(([id])=>id));
        flags.forEach(([id])=>changes[id]=visibleFlagIds.has(id)?values.has(id):shownValue(id));
        const visibleProviderIds=new Set(visibleProviders().map(([id])=>id));
        providerFields.forEach(([id])=>changes[id]=visibleProviderIds.has(id)?values.get(id)||"":shownValue(id));
        const visibleNumberIds=new Set(visibleNumbers().map(([id])=>id));
        numberFields.forEach(([id])=>changes[id]=visibleNumberIds.has(id)?Number(values.get(id)):shownValue(id));
        /* 这份内容只在版本冲突时才当作草稿保留：普通失败（类型/范围不合法）
           并没有写出任何东西，标成草稿会让人以为需要核对。 */
        run("configure",{changes,revision:state.settings.revision});
      }
      if(form.id==="semanticSearch")run("search",{kind,query:values.get("query")});
      if(form.id==="semanticEditor"&&editing){
        const changes={};fields[kind].forEach(([id])=>changes[id]=values.get(id));
        run("edit",{kind,id:editing.id,revision:editing.revision,values:changes,enabled:values.has("item_enabled")});
      }
    },{signal:abort.signal});
    node.addEventListener("change",event=>{
      if(event.target.id==="semanticSession"){sessionId=event.target.value;result=null;editing=null;after="";message="";load();return;}
      if(event.target.id!=="semanticFile"||!event.target.files?.[0])return;
      const file=event.target.files[0];if(file.size>5*1024*1024){message="单张图片不能超过 5 MB";render();return;}
      const ticket=generation,reader=new FileReader();reader.onload=()=>{if(active(ticket))run("import",{content:String(reader.result).split(",")[1],metadata:{name:file.name}});};
      reader.onerror=()=>{if(active(ticket)){message="读取图片失败";render();}};reader.readAsDataURL(file);
    },{signal:abort.signal});
    load();
  }
  function shownValue(id){return (draft?{...state.settings,...draft}:state.settings)[id];}
  function unmount(){generation++;abort?.abort();abort=null;root=null;scope=null;state=null;editing=null;busy=false;}
  return {mount,unmount};
})();
