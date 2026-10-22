"use strict";
window.CompanionLearningReviewPage = (() => {
  const PREFIX = "/astrbot_plugin_private_companion/";
  const DIMENSION = {sentence_rhythm:"句长节奏",emoji:"表情符号",punctuation:"标点",directness:"直接程度",diction:"用词",formatting:"排版",other:"其他"};
  const KIND = {growth:"进展核实",style:"风格采纳",self:"用户确认"};
  const ACTION = {accept:"确认申报",reject:"驳回",adopt:"采纳规则"};
  const ERRORS = {growth_view_stale:"记录已变化，请重新读取。",growth_progress_decided:"这条进展已经处理。",
    expression_view_stale:"候选已变化，请重新读取。",expression_decided:"这条规则已经处理。",
    self_review_view_stale:"指导已变化，请重新读取。",self_review_decided:"这条指导已经处理。",
    bridge_unavailable:"连接暂不可用，请重新读取。",staging_not_initialized:"角色数据尚未加载，请重新读取。"};
  const e = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const when = value => typeof value === "string" && Number.isFinite(Date.parse(value))
    ? new Date(value).toLocaleString("zh-CN",{hour12:false,month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"}) : "时间未知";
  const relative = value => typeof value === "string" && value.startsWith(PREFIX) ? value.slice(PREFIX.length) : "";
  let root = null, ticket = 0, readTicket = 0, sources = [], pages = [], data = null;
  const live = current => root?.isConnected && current === ticket;
  function routeFor(source, base, suffix) {
    return base + suffix;
  }

  async function api(method, route, value) {
    const product = window.CompanionProduct;
    const bridge = product?.bridgeNow?.() || await product?.bridgeFor?.();
    if (!bridge?.apiGet) throw Object.assign(new Error("bridge_unavailable"), {code:"bridge_unavailable"});
    let timer,response;
    try{
      response=await Promise.race([method === "GET" ? bridge.apiGet(route, value) : bridge.apiPost(route, value),
        new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error("bridge_timeout")),15000);})]);
    }finally{clearTimeout(timer);}
    if (response?.status === "error") throw Object.assign(new Error(response.message || "request_failed"), {code:response.data?.code || response.code || response.message});
    if (response?.status === "ok" && response.data !== undefined) return response.data;
    return product?.unwrap ? product.unwrap(response) : response?.data ?? response;
  }

  async function read(current, append = false) {
    if (!live(current) || data.writing || (append && data.loading)) return;
    const request = ++readTicket;
    const previousNotice = data?.notice || "";
    const previousError = !!data?.error;
    if (!append) {
      data = {loading:true, writing:false, items:[], selected:"", checked:new Set(), filter:data?.filter || "all",
        notice:previousNotice, error:previousError, confirming:null, errors:0};
      pages = sources.flatMap(source => {
        const growth = relative(source.growthApi || source.api), reply = relative(source.replyApi);
        return [
          growth && {source,type:"growth",path:routeFor(source,growth,"/progress"),query:{limit:20}},
          reply && {source,type:"style",path:routeFor(source,reply,"/style"),query:{state:"pending",limit:20}},
          growth && {source,type:"self",path:routeFor(source,growth,"/self-review"),query:{state:"pending",limit:20}},
        ].filter(Boolean).map(page => ({...page,items:[],next:"",loaded:false}));
      });
    } else data.loading = true;
    render();
    const requested = pages.filter(page => !page.loaded || (append && page.next));
    const fetched = await Promise.allSettled(requested.map(page => api("GET",page.path,
      {...page.query,...(page.next?{after_id:page.next}:{})})));
    if (!live(current) || request !== readTicket) return;
    data.errors = 0;
    fetched.forEach((result,index) => {
      const page = requested[index];
      if(result.status === "rejected" || !Array.isArray(result.value?.items)) { data.errors++; return; }
      const idField = {growth:"review_id",style:"signal_id",self:"item_id"}[page.type];
      const rows = result.value.items.filter(item=>page.type!=="self"||item.kind==="ask_user")
        .map(item=>({...item,_type:page.type,_source:page.source,_id:item[idField]}));
      page.items.push(...rows);page.loaded=true;
      const next = typeof result.value.next_cursor === "string" ? result.value.next_cursor : "";
      page.next = next === page.next ? "" : next;
    });
    const seen = new Set();
    data.items = pages.flatMap(page=>page.items).filter(item=>{
      const key=keyFor(item);if(seen.has(key))return false;seen.add(key);return true;
    });
    data.items.sort((a,b) => Date.parse(b.created_at || 0) - Date.parse(a.created_at || 0));
    data.items.forEach(keyFor);
    if (!data.items.some(item => keyFor(item) === data.selected)) data.selected = data.items[0]?._key || "";
    data.loading = false;
    render();
  }

  function keyFor(item) { return item._key || (item._key = `${item._source.key}::${item._type}::${item._id}`); }
  function selectedItem() { return data?.items.find(item => keyFor(item) === data.selected) || null; }
  function title(item) {
    if (item._type === "growth") return item.growth_title || "目标已不可读取";
    if (item._type === "style") return item.proposal || item.observation || "表达候选";
    return item.observation || "需要确认的指导";
  }
  function evidence(item) {
    if (Array.isArray(item.evidence)) return item.evidence;
    return [];
  }
  function actions(item) {
    if (item._type === "growth") return item.actions || [];
    if (item._type === "style") return item.actions || [];
    return item.actions || [];
  }
  function labelAction(item, action) {
    if (item._type === "self" && action === "accept") return "采纳指导";
    return ACTION[action] || "处理";
  }
  function render() {
    if (!root || !data) return;
    const visible = data.items.filter(item => data.filter === "all" || item._type === data.filter);
    if(!visible.some(item=>keyFor(item)===data.selected))data.selected=visible[0]?._key||"";
    const current = selectedItem();
    const counts = {all:data.items.length,growth:data.items.filter(item=>item._type==="growth").length,
      style:data.items.filter(item=>item._type==="style").length,self:data.items.filter(item=>item._type==="self").length};
    const list = visible.length ? visible.map(item => `<div class="lh-review-row-wrap">
      <input type="checkbox" data-review-check="${e(keyFor(item))}" aria-label="选择${e(title(item))}"${data.checked.has(keyFor(item))?" checked":""}${data.writing?" disabled":""}>
      <button type="button" class="lh-review-row${keyFor(item)===data.selected?" is-selected":""}"
      data-review-select="${e(keyFor(item))}" aria-pressed="${keyFor(item)===data.selected}">
      <span class="lh-review-type is-${item._type}">${KIND[item._type]}</span><span class="lh-review-row-copy"><strong>${e(title(item))}</strong>
      <small>记录归属 · ${e(item._source.label)} · ${e(when(item.created_at))}</small></span><i data-lucide="chevron-right" aria-hidden="true"></i></button></div>`).join("")
      : `<div class="lh-review-empty">${data.loading?"正在读取…":"没有待处理记录"}</div>`;
    let detail = `<div class="lh-review-detail-empty">选择一条记录</div>`;
    if (current) {
      const body = current._type === "growth" ? current.progress_note
        : current._type === "style" ? current.observation : current.next_action;
      const proof = evidence(current);
      const detailActions = actions(current).map(action => `<button type="button" class="lh-command${action==="accept"||action==="adopt"?" is-primary":""}"
        data-review-stage="${e(action)}" data-review-key="${e(keyFor(current))}" ${data.writing?"disabled":""}>${labelAction(current,action)}</button>`).join("");
      const confirmation = data.confirming?.key === keyFor(current)
        ? `<div class="lh-review-confirm" role="alertdialog"><span>确认${e(labelAction(current,data.confirming.action))}？</span>
          <button type="button" data-review-confirm="yes"${data.writing?" disabled":""}>确认</button><button type="button" data-review-confirm="no">取消</button></div>` : "";
      detail = `<article class="lh-review-detail"><header><span class="lh-review-type is-${current._type}">${KIND[current._type]}</span>
        <span>记录归属 · ${e(current._source.label)}</span><strong>${e(title(current))}</strong></header>
        ${body?`<section class="lh-review-observation"><small>${current._type==="growth"?"申报进展":current._type==="style"?"观察":"建议"}</small><p>${e(body)}</p></section>`:""}
        ${current._type==="style"&&current.dimension?`<p class="lh-review-meta">${e(DIMENSION[current.dimension]||current.dimension)} · ${(Number(current.confidence||0)*100).toFixed(0)}%</p>`:""}
        ${current._type==="style"&&current.source_kind==="legacy_expression"?`<p class="lh-review-meta">旧版学习成果</p>`:""}${current._type==="style"&&current.source_kind==="shared_pack"?`<p class="lh-review-meta">分享包 · ${e(current.source_title||"导入规则")}</p>`:""}
        ${current._type==="style"&&(current.positive_feedback||current.negative_feedback)?`<p class="lh-review-meta">明确反馈 · 认可 ${e(current.positive_feedback||0)} / 不喜欢 ${e(current.negative_feedback||0)}</p>`:""}
        ${current._type==="style"&&current.review_reason?`<p class="lh-review-feedback-reason">${e(current.review_reason)}</p>`:""}
        ${current.unavailable_reason?`<p class="lh-review-unavailable">依据已不可读取，只能驳回。</p>`:""}
        ${proof.length?`<details class="lh-review-evidence" open><summary>本轮依据 · ${proof.length}</summary><ol>${proof.map(text=>`<li>${e(text)}</li>`).join("")}</ol></details>`:""}
        <footer>${detailActions}</footer>${confirmation}</article>`;
    }
    const selectedVisible=visible.filter(item=>data.checked.has(keyFor(item)));
    const bulkAccept=selectedVisible.filter(item=>actions(item).includes(item._type==="style"?"adopt":"accept")).length;
    const bulkReject=selectedVisible.filter(item=>actions(item).includes("reject")).length;
    const bulkConfirm=data.confirming?.bulk?`<div class="lh-review-confirm lh-review-bulk-confirm" role="alertdialog">
      <span>确认${data.confirming.action==="accept"?"通过":"拒绝"} ${data.confirming.action==="accept"?bulkAccept:bulkReject} 条记录？</span>
      <button type="button" data-review-confirm="yes"${data.writing?" disabled":""}>确认</button><button type="button" data-review-confirm="no">取消</button></div>`:"";
    root.innerHTML = `<div class="lh-review-head"><div class="lh-review-filters" role="group" aria-label="审阅类型">
      ${[["all","全部"],["growth","进展核实"],["style","风格采纳"],["self","用户确认"]].map(([id,label])=>
        `<button type="button" data-review-filter="${id}" aria-pressed="${data.filter===id}">${label}<span>${counts[id]}</span></button>`).join("")}</div>
      <button type="button" class="lh-refresh" data-review-refresh aria-label="重新读取" title="重新读取" ${data.loading||data.writing?"disabled":""}><i data-lucide="refresh-cw"></i></button></div>
      <div class="lh-review-bulk"><label><input type="checkbox" data-review-check-all${visible.length&&selectedVisible.length===visible.length?" checked":""}${!visible.length||data.writing?" disabled":""}>全选当前结果</label>
        <span>已选 ${selectedVisible.length}</span><button type="button" data-review-bulk="accept"${!bulkAccept||data.writing?" disabled":""}>批量通过${bulkAccept?` · ${bulkAccept}`:""}</button>
        <button type="button" data-review-bulk="reject"${!bulkReject||data.writing?" disabled":""}>批量拒绝${bulkReject?` · ${bulkReject}`:""}</button></div>
      ${data.notice?`<p class="lh-inline-status ${data.error?"is-error":""}" role="status">${e(data.notice)}</p>`:""}
      ${data.errors?`<p class="lh-inline-status" role="status">部分记录归属暂时无法读取</p>`:""}
      ${bulkConfirm}<div class="lh-review-layout"><section class="lh-review-queue"><header><h3>待裁决</h3><span>${visible.length}</span></header>${list}
      ${pages.some(page=>page.next)?`<button type="button" class="lh-command" data-review-more${data.loading||data.writing?" disabled":""}>加载更多</button>`:""}</section>${detail}</div>`;
    window.lucide?.createIcons({attrs:{"aria-hidden":"true"}});
  }

  async function decide(item, action) {
    if (data.writing || !item || !actions(item).includes(action)) return;
    const current = ticket;
    data.writing = true; data.confirming = null; data.notice = ""; data.error=false; render();
    try {
      const base = item._type === "style" ? relative(item._source.replyApi) : relative(item._source.growthApi || item._source.api);
      let path, body;
      const operation_key = `learning-review-${Date.now()}-${Math.random().toString(36).slice(2,10)}`;
      if (item._type === "growth") {
        path = base + "/progress/command";
        body = {review_id:item.review_id,action,expected_revision:item.base_revision,view_token:item.view_token,operation_key};
      } else if (item._type === "style") {
        path = base + "/style/command";
        body = {signal_id:item.signal_id,action,view_token:item.view_token,operation_key};
      } else {
        path = base + "/self-review/command";
        body = {item_id:item.item_id,action,view_token:item.view_token,operation_key};
      }
      await api("POST",routeFor(item._source,"",path),body);
      if (!live(current)) return;
      data.writing = false; data.notice = action==="reject"?"已驳回。":item._type==="growth"?"已确认申报。":"已采纳。";
      await read(current);
    } catch (error) {
      if (!live(current)) return;
      data.writing = false; data.error = true; data.notice = ERRORS[error?.code] || "操作未完成，请重新读取。"; render();
    }
  }

  async function decideBatch(action) {
    if(data.writing)return;
    const visible=data.items.filter(item=>data.filter==="all"||item._type===data.filter);
    const selected=visible.filter(item=>data.checked.has(keyFor(item)));
    const requests=selected.map(item=>({item,command:item._type==="style"?(action==="accept"?"adopt":"reject"):action}))
      .filter(({item,command})=>actions(item).includes(command));
    if(!requests.length){data.notice="所选记录没有可用的对应操作。";data.error=true;render();return;}
    const current=ticket;
    data.writing=true;data.confirming=null;data.notice="";render();
    let completed=0,failed=null;
    for(const {item,command} of requests){
      if(!live(current))return;
      try{
        const base=item._type==="style"?relative(item._source.replyApi):relative(item._source.growthApi||item._source.api);
        const operation_key=`learning-review-batch-${Date.now()}-${Math.random().toString(36).slice(2,10)}`;
        if(item._type==="growth")await api("POST",routeFor(item._source,base,"/progress/command"),{
          review_id:item.review_id,action:command,expected_revision:item.base_revision,view_token:item.view_token,operation_key});
        else if(item._type==="style")await api("POST",routeFor(item._source,base,"/style/command"),{
          signal_id:item.signal_id,action:command,view_token:item.view_token,operation_key});
        else await api("POST",routeFor(item._source,base,"/self-review/command"),{
          item_id:item.item_id,action:command,view_token:item.view_token,operation_key});
        completed++;
      }catch(error){failed=error;break;}
    }
    if(!live(current))return;
    data.writing=false;data.checked.clear();data.confirming=null;
    await read(current);
    if(!live(current))return;
    data.notice=failed?`已处理 ${completed} 条，其余未提交。${ERRORS[failed?.code]||"请刷新后核对。"}`:`已处理 ${completed} 条。`;
    data.error=!!failed;render();
  }

  function onClick(event) {
    if(!data||data.writing)return;
    const filter = event.target.closest("[data-review-filter]");
    if (filter) { data.filter=filter.dataset.reviewFilter; data.confirming=null; render(); return; }
    if (event.target.closest("[data-review-refresh]")) { void read(ticket); return; }
    if (event.target.closest("[data-review-more]")) { void read(ticket,true); return; }
    const bulk=event.target.closest("[data-review-bulk]");
    if(bulk){const action=bulk.dataset.reviewBulk;data.confirming={bulk:true,action};render();return;}
    const select = event.target.closest("[data-review-select]");
    if (select) { data.selected=select.dataset.reviewSelect; data.confirming=null; render(); return; }
    const staged = event.target.closest("[data-review-stage]");
    if (staged) { data.confirming={key:staged.dataset.reviewKey,action:staged.dataset.reviewStage}; render(); return; }
    const confirm = event.target.closest("[data-review-confirm]");
    if (confirm) {
      if (confirm.dataset.reviewConfirm==="no") { data.confirming=null; render(); return; }
      if(data.confirming?.bulk){void decideBatch(data.confirming.action);return;}
      const item=selectedItem(), action=data.confirming?.action;
      if (item) void decide(item,action);
    }
  }
  function onChange(event){
    if(!data||data.writing)return;
    const checkbox=event.target.closest("[data-review-check]");
    if(checkbox){checkbox.checked?data.checked.add(checkbox.dataset.reviewCheck):data.checked.delete(checkbox.dataset.reviewCheck);render();return;}
    if(event.target.closest("[data-review-check-all]")){
      const visible=data.items.filter(item=>data.filter==="all"||item._type===data.filter);
      data.checked.clear();if(event.target.checked)visible.forEach(item=>data.checked.add(keyFor(item)));render();
    }
  }
  function mount(host, options = {}) {
    unmount(); root=host; sources=Array.isArray(options.sources)?options.sources:[];
    root?.addEventListener("click",onClick);root?.addEventListener("change",onChange);
    data={loading:false,writing:false,items:[],selected:"",checked:new Set(),filter:"all",notice:"",confirming:null,errors:0};
    const current=++ticket;
    if (sources.length) void read(current); else render();
  }
  function unmount() { ticket++;readTicket++; root?.removeEventListener("click",onClick);root?.removeEventListener("change",onChange);root=null;sources=[];pages=[];data=null; }
  return {mount,unmount,get state(){return data;}};
})();
