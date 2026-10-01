'use strict';
const product = window.CompanionProduct;
/* 房间陈设的存储键。接上宿主后按「安装 + 会话对象 + 角色」隔离——同一份
   布局不能串到另一个对象身上；目录还没读到（scopeKey 的两个字段为空）时
   退回本地暂存键，免得每次都算出一个不同的空键把陈设丢掉。 */
const layoutKey = () => product.scopeKey() || 'local-room-layout';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const escapeHTML = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const I = name => `<i data-lucide="${name}" aria-hidden="true"></i>`;
const icons = () => window.lucide?.createIcons({attrs:{'aria-hidden':'true'}});
const configSnapshot = window.companionConfigSnapshot || {
  version: 'preview-only',
  capturedAt: '',
  identity: {botName: '当前角色', personaId: '', nickname: '', multiPersona: false},
  base: {},
  capabilities: {},
};
const configuredModules = Object.fromEntries(Object.entries(configSnapshot.capabilities || {}).map(([id, config]) => [id, config.enabled === true ? 'enabled' : config.enabled === false ? 'disabled' : 'unknown']));
const KEY = 'companion-framework-ui-preview-v2-config-20260924';
const LEGACY_KEY = 'companion-framework-ui-preview-v1';
const weatherModes = [
  {id:'clear',name:'晴天',icon:'sun',note:'天空清朗 · 草地干燥'},
  {id:'cloudy',name:'多云',icon:'cloud',note:'云层遮光 · 光线柔和'},
  {id:'rain',name:'细雨',icon:'cloud-drizzle',note:'细雨轻落 · 石径湿润'},
  {id:'storm',name:'大雨',icon:'cloud-rain',note:'雨势渐密 · 庭院积水'},
  {id:'snow',name:'落雪',icon:'snowflake',note:'雪落庭院 · 草木覆雪'},
  {id:'mist',name:'薄雾',icon:'cloud-fog',note:'薄雾绕树 · 远景朦胧'},
];
const sceneTimes = [['dawn','清晨','sunrise'],['day','日间','sun'],['evening','暮色','sunset'],['night','夜晚','moon']];
const initial = {
  role:'chengxi', view:'scene', scene:'day', weather:'clear', labels:true, largeText:false, reduceMotion:false,
  roomLayouts:{},
  configSnapshotVersion:configSnapshot.version,
  modules:{content:'unknown',image:'unknown',together:'unknown',game:'unknown',screen:'unknown',reality:'unknown',live:'unknown',...configuredModules},
  notes:'下次去书店，想找一本有关植物的随笔。',
  diary:'下午的阳光落在书页上，刚好照亮了那句读了两遍的话。\n\n我把杯子挪到窗边，继续读了几页。没有急着读完，喜欢的句子就留在便签里。\n\n晚一些想出去走走。也许会路过那家还没进去过的小书店。',
  activityPaused:false,
};
let state = structuredClone(initial);
try {
  const data = JSON.parse(localStorage.getItem(KEY) || localStorage.getItem(LEGACY_KEY) || 'null');
  if(data) state={...state,...data,configSnapshotVersion:configSnapshot.version,modules:data.configSnapshotVersion===configSnapshot.version?{...state.modules,...data.modules}:state.modules};
} catch {}
delete state.preferences;
if (!['chengxi','wangshu'].includes(state.role)) state.role='chengxi';
if (!weatherModes.some(item=>item.id===state.weather)) state.weather=initial.weather;
if (!sceneTimes.some(item=>item[0]===state.scene)) state.scene=initial.scene;
if (!state.roomLayouts || typeof state.roomLayouts!=='object' || Array.isArray(state.roomLayouts)) state.roomLayouts={};
const navGroups = [
  ['小屋', [['life','home','house','小屋'],['life','diary','notebook-pen','日记与生活']]],
  ['塑造角色', [['manage','governance','user-round','自我'],['manage','identity','shield-check','关系与权限'],['manage','memory','orbit','记忆与经历'],['manage','learning','graduation-cap','学习与成长']]],
  ['互动能力', [['manage','perception','scan-eye','感知'],['manage','decision','brain','决策'],['manage','action','play','行动'],['manage','contact','heart-handshake','主动联系'],['manage','expression','message-square-more','表达'],['manage','output','shapes','产出']]],
   ['连接与运行', [['manage','setup','rocket','首次连接'],['manage','host','power','账号与会话'],['manage','models','sliders-horizontal','模型与连接'],['manage','maintenance','settings-2','运行诊断'],['manage','data','database','资料与备份'],['manage','appearance','palette','外观与设置']]],
];
const navItems = navGroups.flatMap(([,items])=>items);
const lifeTabs=[['home','house','首页'],['state','activity','状态'],['diary','notebook-pen','日记']];
let route='life', lifeTab='home', manageTab='host', selfPane='profile', libraryFilter='all', memoryView='list', memoryWorkspaceRoute='records';
let observationFilter='records', furnitureFilter='all', furnitureQuery='';
let configEditorMounts=[];
let roleProfileConfigMount=null;
let relationshipProfileConfigMount=null;
let toastTimer, arrangementDraft=null, dialogReturnFocus=null, dialogReturnFurniture='', lastDetail='', voxelController=null;
const configuredRoleName=()=>escapeHTML(configSnapshot.identity?.botName||'当前角色');
/* 角色名。有真实角色就用它，没有就用配置里的角色名——
   不再有「望舒（示例）」这种带着「示例」字样的占位，那会让真实使用中被误读成假数据。 */
const roleName=()=>{
  const live=product.role()?.role_id;
  return escapeHTML(live||configSnapshot.identity?.botName||'当前角色');
};
const capabilityConfig=id=>configSnapshot.capabilities?.[id]||{};
const capabilitySummary=id=>capabilityConfig(id).summary||'当前插件没有可展示的配置摘要。';
const HOST='astrbot_plugin_private_companion_v2';
let hostConnection={state:'checking',label:'陪伴小屋 · 正在连接',detail:'正在读取 V2 宿主…'};
let integrationSnapshot=null;
let hostProbeVersion=0;
function persist(){try{localStorage.setItem(KEY,JSON.stringify(state));return true;}catch{return false;}}
function saved(message){toast(persist()?message:`${message}；此环境仅保留至页面关闭`);}
function toast(message){clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').classList.add('show');toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),2900);}
function chip(text,type=''){return `<span class="pill ${type}">${text}</span>`;}
function button(text,attrs='',kind=''){return `<button class="button ${kind}" ${attrs}>${text}</button>`;}
function updateAppearance(){
  document.body.classList.toggle('large-text',state.largeText);
  /* 动效维度取「用户设置」与「系统偏好」中更严格的一方：关闭 / 减弱不override回完整。 */
  const dims=product.appearance();
  document.body.classList.toggle('reduce-motion',state.reduceMotion||dims.motion!=='full');
}
function navHref(next,tab='',subtab=''){
  const path='#'+next+(tab&&tab!=='home'&&tab!=='host'?'/'+tab:'');
  return next==='manage'&&tab==='governance'&&subtab==='knowledge'?path+'/knowledge':path;
}
function navLink([next,tab,icon,label],extra=''){
  const active=route===next&&(next==='life'?lifeTab===tab:next==='manage'?manageTab===tab:true);
  return `<a href="${navHref(next,tab)}" class="${extra?extra+'nav-link':'rail-link'} ${active?'active':''}" ${next==='manage'&&!extra?`data-manage-tab="${tab}"`:''} ${active?'aria-current="page"':''} title="${label}">${I(icon)}<span>${label}</span></a>`;
}
function navigationButton([next,tab,icon,label]){
  const active=route===next&&(next==='life'?lifeTab===tab:next==='manage'?manageTab===tab:true);
  return `<button data-nav-route="${next}" data-nav-tab="${tab}" class="navigation-link ${active?'active':''}" ${active?'aria-current="page"':''}>${I(icon)}<span>${label}</span></button>`;
}
function navigate(next,tab,subtab=''){
  if(next==='library'||next==='activities'){
    furnitureFilter='extensions';furnitureQuery='';navigate('life','home');goHomeSection('furniture');return;
  }
  if(next==='manage'&&tab==='capabilities'){goHomeSection('furniture');return;}
  if(next==='manage'&&tab==='semantic')tab='perception';
  if(next==='manage'&&tab==='persona'){tab='governance';subtab='questionnaire';}
  if(next==='manage'&&tab==='knowledge'){tab='governance';subtab='knowledge';}
  if(!['life','people','memories','manage'].includes(next))return;
  closeDetail();route=next;
  if(next==='life'){
    if(tab==='schedule')tab='state';/* 旧深链接 #life/schedule 别名到状态页 */
    lifeTab=lifeTabs.some(item=>item[0]===tab)?tab:'home';
    /* life 子页由外壳整页视图承载：同步 shell.view 面板才会真的切过去；
       回首页只清视图，小屋的缩略/家具状态交给 backHome 处理。 */
    window.CompanionShell?.selectView(lifeTab==='home'?null:lifeTab);
  }
  if(next==='manage'){
    manageTab=manageTabs.some(item=>item[0]===tab)?tab:'host';
    selfPane=manageTab==='governance'&&['profile','relationship','questionnaire','knowledge'].includes(subtab)?subtab:'profile';
  }
  try{history.replaceState(null,'',navHref(route,route==='life'?lifeTab:route==='manage'?manageTab:'',route==='manage'?selfPane:''));}catch{}
  render();window.scrollTo({top:0,behavior:'instant'});
}
function syncFromHash(){
  let [next,tab,subtab]=location.hash.slice(1).split('/');
  if(next==='library'||next==='activities'){navigate(next);return;}
  if(next==='manage'&&tab==='capabilities'){goHomeSection('furniture');return;}
  if(next==='manage'&&tab==='semantic'){tab='perception';history.replaceState(null,'',navHref(next,tab));}
  if(next==='manage'&&tab==='persona'){tab='governance';subtab='questionnaire';}
  if(next==='manage'&&tab==='knowledge'){tab='governance';subtab='knowledge';}
  if(!['life','people','memories','manage'].includes(next)){navigate('life','home');return;}
  closeDetail();route=next;
  if(next==='life'){
    if(tab==='schedule')tab='state';/* 旧深链接 #life/schedule 别名到状态页 */
    lifeTab=lifeTabs.some(item=>item[0]===tab)?tab:'home';
    window.CompanionShell?.selectView(lifeTab==='home'?null:lifeTab);
  }
  if(next==='manage'){
    manageTab=manageTabs.some(item=>item[0]===tab)?tab:'host';
    selfPane=manageTab==='governance'&&['profile','relationship','questionnaire','knowledge'].includes(subtab)?subtab:'profile';
  }
  render();
}
/* 角色名徽标。它原先是个下拉，用来在示例角色 chengxi/wangshu 之间切换——
   那是本地预览的遗留物。连上宿主后角色由会话对象决定，页面里再放一个
   「切换角色」按钮只会让人以为可以改。所以现在它是纯展示徽标，
   只在有真实角色（或预览示例角色）时显示名字，不提供切换。 */
function pageHeading(title,subtitle,extra='',showRole=false){return `<div class="page-heading"><div class="title-line"><h1>${title}</h1>${showRole?`<span class="role-badge">${roleName()}</span>`:''}</div>${extra}</div>`;}
function updateHostChrome(){
  hostConnection=product.connection();product.renderScope();
  const badge=$('[data-host-badge]');
  if(badge){badge.className=`preview-badge host-${hostConnection.state}`;badge.innerHTML=`<span class="host-dot"></span><span class="host-label">${escapeHTML(hostConnection.label)}</span>`;badge.title=hostConnection.detail;}
  const footer=$('[data-host-status]');
  if(footer)footer.innerHTML=`<span class="footer-dot"></span>${escapeHTML(hostConnection.detail)}`;
  updateRailBrand();
}
/* 图源合同：image 扩展可用且给出真实的 outfit_image / cover 时显示穿搭图；
   没有图片时保留陪伴小屋品牌入口。 */
function outfitImageSrc(){
  const provider=integrationProvider('image');
  if(!provider||!['connected','degraded'].includes(provider.integration_state))return null;
  const source=[provider.outfit_image,provider.cover].find(value=>typeof value==='string'&&value.trim());
  return source?.trim()||null;
}
function updateRailBrand(){
  const brand=$('#railBrand');if(!brand)return;
  const src=outfitImageSrc();
  if(src===null){
    brand.classList.remove('rail-outfit');
    brand.innerHTML=`<span class="brand-symbol">${I('house')}</span><span>陪伴小屋<small>V2.0</small></span>`;
    icons();
    return;
  }
  brand.classList.add('rail-outfit');
  brand.innerHTML=`<img src="${escapeHTML(src)}" alt="当前穿搭图">`;
  icons();
}
function integrationProvider(id){return integrationSnapshot?.providers?.find(item=>item.capability_id===id)||null;}
function integrationStateCopy(id){
  const provider=integrationProvider(id);
  if(!provider)return null;
  return ({connected:['扩展状态已读取',''],degraded:['状态待检查','amber'],installed:['已安装 · 尚未加载','amber'],missing:['未安装','gray']})[provider.integration_state]||['状态未知','amber'];
}
async function probeHost(){
  await product.connect(()=>{integrationSnapshot=product.manifest;if(!arrangementDraft)render();else updateHostChrome();});
}
function updateVoxelTour(running){const button=$('[data-voxel-tour]');if(button){button.setAttribute('aria-pressed',String(running));button.querySelector('span').textContent=running?'停止巡游':'巡游';}}
function renderEnvironment(){return `<section class="environment-controls" aria-label="小屋环境"><div class="environment-label">小屋环境</div><div class="weather-options" role="group" aria-label="切换天气">${weatherModes.map(item=>`<button class="weather-option" data-weather="${item.id}" aria-pressed="${state.weather===item.id}" title="${item.name} · ${item.note}">${I(item.icon)}<span>${item.name}</span></button>`).join('')}</div><label class="scene-time-control">${I('clock-3')}<span class="sr-only">场景时段</span><select data-scene-time aria-label="场景时段">${sceneTimes.map(([id,name])=>`<option value="${id}" ${state.scene===id?'selected':''}>${name}</option>`).join('')}</select>${I('chevron-down')}</label></section>`;}
function environmentSummary(value=state){const weather=weatherModes.find(item=>item.id===value.weather);return `${I(weather.icon)}${sceneTimes.find(item=>item[0]===value.scene)[1]} · ${weather.note}`;}
function syncEnvironment(value=state,{fromTheme=false}={}){
  const stage=$('.room-stage');if(stage){stage.className=`room-stage scene-${value.scene}`;stage.dataset.weather=value.weather;}
  const light=value.scene==='evening'?'dusk':value.scene;
  voxelController?.setLight(light);
  voxelController?.setAtmosphere({condition:value.weather});
  $$('button[data-weather]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.weather===value.weather)));
  const select=$('[data-scene-time]');if(select)select.value=value.scene;
  const summary=$('[data-weather-summary]');if(summary){summary.innerHTML=environmentSummary(value);icons();}
  /* 通知外观层：小屋光照变了。开了「跟随光照」才会切主题，
     且光照明暗真的变了才动（同一时段内反复渲染不该触发切换）。
     由主题驱动的那一跳不再回告，避免与 syncLightFromTheme 成环。 */
  if(fromTheme)return;
  const followed=product.syncLight(light);
  /* 跟随光照换了主题：让外观页自己重渲染。
     旧写法是去刷新 [data-appearance-inline] 那个内联容器，而新外观页是独立模块、
     没有那个容器，所以这一跳改成通知它。它自己会读 product.appearance() 取新值，
     不在这里重算——主题-光照的映射只有 theme.js 一份。 */
  if(followed)notifyAppearanceChanged();}
/* 反方向：用户直接换了主题，小屋跟着换光照。
   主题 → 光照的对应写在 theme.js 注册表里，页面不重复这份映射。

   注意这里传 fromTheme=true 给 syncEnvironment，让那一跳不再回告外观层。
   否则会成环：主题→场景→syncLight→主题…虽然有「已一致就返回」的守卫能收敛，
   但那是靠状态巧合，不是靠结构，改错一个守卫就会无限循环。 */
function syncLightFromTheme(theme){
  const wanted=product.lightOf(theme);
  if(!wanted||!sceneTimes.some(item=>item[0]===wanted))return;
  /* 注册表用的是 day/dusk/night/dawn，小屋的场景名是 evening 而非 dusk。 */
  const scene=wanted==='dusk'?'evening':wanted;
  if(state.scene===scene)return;
  state.scene=scene;syncEnvironment(state,{fromTheme:true});persist();
}
function showVoxelFallback(mount){mount.classList.add('voxel-scene-failed');mount.innerHTML=`<div class="voxel-fallback"><span>体素小屋暂时无法显示</span><small>可以重试加载，或从下方家具目录打开全部内容。</small><div class="voxel-fallback-actions"><button class="button" data-voxel-retry>重新加载</button><button class="button primary" data-home-section="furniture">打开家具目录</button></div></div>`;$$('.voxel-action,[data-locate-furniture]').forEach(button=>button.disabled=true);}
function openVoxelStation(id){
  const mount=$('[data-voxel-room]');if(mount){mount.tabIndex=-1;mount.focus({preventScroll:true});}
  const entry=directory.find(item=>item.station===id||item.id===id);
  if(entry){openFurniture(entry.id);return;}
  if(['wardrobe','readingLamp','stool','rug'].includes(id))toast('这件家具用于房间陈设');
}
function openFurniture(id){const entry=directory.find(item=>item.id===id);if(!entry)return;if(entry.tab)navigate('life',entry.tab);else showDetail(entry.detail);}
/* 「跳到首页某一块」。
 *
 * 旧结构里首页是一条长滚动页，三块内容各有一个 id（#home-overview /
 * #home-observation / #home-furniture），这个函数把视口滚到对应位置。
 * 新外壳里首页不再长滚，三块内容变成下方面板的三个视图——所以这里
 * 从「滚动」改成「切换面板视图」。
 *
 * 必须改而不是留着：id 已经不存在了，`$('#home-'+section)` 恒为 null，
 * 函数会静默返回。散落在深链接、搜索、家具卡片上的八处调用会全部失效，
 * 而且没有任何报错——点「能力目录」什么也不会发生。
 */
function goHomeSection(section){
  const view={overview:null,observation:'observation',furniture:'directory'}[section];
  if(section!=='overview'&&!view)return;
  closeDetail();
  const shell=window.CompanionShell;
  if(!shell)return;
  if(section==='overview'){
    /* 回小屋总览：清掉分区与视图，但不飞镜头——调用方可能正要自己 focus。 */
    shell.selectSection(null);shell.selectView(null);shell.selectFurniture(null);
  }else{
    shell.selectView(view);
  }
  route='life';lifeTab='home';
  try{history.replaceState(null,'',navHref('life','home'));}catch{}
  renderShell();
  const body=$('.shell-panel-body');
  body?.scrollIntoView({behavior:state.reduceMotion||matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
}
function syncFurnitureScene(){
  if(!voxelController)return;
  voxelController.setFurnitureCatalog(directory.filter(item=>item.model&&!['removed','planned'].includes(state.modules[item.cap])).map(item=>({id:item.station,label:item.name+' · '+capabilityStatus(item.cap)[0],model:item.model,accent:item.accent})));
  const layout=voxelController.getLayout();let changed=false;
  directory.filter(item=>item.cap&&!item.model&&item.station).forEach(item=>{
    const piece=layout.items[item.station];if(!piece)return;
    const stored=state.roomLayouts[layoutKey()]?.items?.[item.station]?.stored===true;if(Boolean(piece.stored)!==stored){piece.stored=stored;changed=true;}
  });
  if(changed)voxelController.setLayout(layout);
  voxelController.setStationLabels(Object.fromEntries(directory.filter(item=>item.station).map(item=>[item.station,item.name+(item.cap?' · '+capabilityStatus(item.cap)[0]:'')])));
}
/* === 外壳：小屋常驻 + 面板切换 ===
 *
 * 旧结构里小屋是 life/home 路由的内容，切到别的分区就会 dispose 控制器，
 * 回来再 mount 一次——相机位姿丢掉、加载成本重付。新结构把小屋提到外壳里，
 * 只有两种情况会重挂：首次进入，以及布局数据变了（state.roomLayouts 更新）。
 * 面板切换完全不动它。
 *
 * 「选中的家具」与「选中的配置分区」是两个独立维度，各自记住：
 *   点家具 → 镜头飞过去 + 右栏换成它的状态 + 下方面板换成它的用途
 *   点左栏 → 下方面板换成配置编辑器（镜头不动，用户可能还想看着小屋改设置）
 * 但两者不能同时占着下方面板，所以选中其一会清掉另一个（见 shell.js）。
 */
let stageMounted=false;              // 小屋是否已挂载（首次之后不再重挂）
let shellUnsubscribe=null;           // shell 状态订阅
let stageSignature='';               // 已挂载时的场景签名，用于判断要不要重挂
let shellRenderedView=null;
let shellViewInitialized=false;

/* 小屋场景的签名。变化时说明布局或光照变了，需要重挂。
   刻意不含「选中的家具」——那只是相机移动，不该重挂场景。 */
function stageSignatureNow(){
  return JSON.stringify({
    layout:state.roomLayouts[layoutKey()]||null,
    scene:state.scene,
    weather:state.weather,
    role:state.role,
    /* 语义是「桥可用」：陈设编辑器用它决定改动要不要落回宿主。 */
    hosted:product.hosted(),
  });
}

function mountStage(){
  const mount=$('[data-voxel-room]');
  if(!mount){
    /* 连挂载点都没有：整页不会有任何小屋，也没有人会走到 startEntrance
       去开闸门。不放行就是对着启动幕干等七秒。 */
    document.documentElement.dataset.roomReady="";
    return;
  }
  try{
    if(!window.PrivateCompanionHomeRoom3D)throw new Error('体素场景资源未加载');
    voxelController=window.PrivateCompanionHomeRoom3D.mount(mount,{
      layout:state.roomLayouts[layoutKey()],
      light:state.scene==='evening'?'dusk':state.scene,
      reducedMotion:state.reduceMotion,
      onSelect:openVoxelStation,
      onResidentSelect:()=>showDetail('profile'),
      onTourChange:updateVoxelTour,
      onEditorChange:updateRoomEditor,
      onError:message=>{if(arrangementDraft)finishRoomEditor(false);showVoxelFallback(mount);toast(message);},
    });
    syncFurnitureScene();
    voxelController.setAtmosphere({condition:state.weather});
    voxelController.setActive(true);
    updateFurnitureDirectory();
    stageMounted=true;
    stageSignature=stageSignatureNow();
    /* 配置分区深链接不播开场；首次打开完整小屋时从底部搭建。
       shell 内的状态、目录等视图切换不重新安排入口动画。 */
    /* renderShell() 在本轮 render 的末尾才填标题、家具条和状态面板。
       等同一任务的 DOM 工作完成后测量，否则会量到栅格尚未落位的矩形。 */
    const mountedController=voxelController;
    queueMicrotask(()=>{
      if(voxelController!==mountedController)return;
      const shell=window.CompanionShell;
      if(!shell?.section)startEntrance(mount,true);
      else document.documentElement.dataset.roomReady="";
    });
  }catch(error){
    showVoxelFallback(mount);
    /* 挂不上也要放行首屏：catch 分支不会走到 startEntrance，闸门就没人开，
       页面会一直停在启动幕上。降级视图（showVoxelFallback）本身是为了
       在这种时候给用户看的东西，藏在隐藏的 body 里没有意义。 */
    document.documentElement.dataset.roomReady="";
    console.warn('Voxel room preview failed to start:',error);
  }
}

/* 小屋的家具速览条：七件有机位的家具，点一下就选中并飞过去。 */
const STAGE_BAR_ITEMS=[
  ['desk','notebook-pen','日记书桌'],
  ['calendar','calendar-days','生活挂历'],
  ['shelf','library-big','创作书架'],
  ['bed','bed-double','睡眠与梦境'],
  ['radio','radio','见闻电台'],
  ['garden','sprout','成长花架'],
  ['wardrobe','door-open','衣柜陈设'],
];
function renderStageBar(){
  const host=$('#stageFurniture');
  if(!host)return;
  const selected=window.CompanionShell?.furniture||null;
  host.innerHTML=STAGE_BAR_ITEMS.map(([id,icon,label])=>
    `<button data-shell-furniture="${id}" aria-pressed="${selected===id}" title="${label}">${I(icon)}${label}</button>`
  ).join('');
}

/* 右栏。选中家具时顶部多一段「它的用途与状态」，下面仍是三块概览——
   它们提供的是跨家具的全局信息。
 *
 * 这里此前把三张 overview-card 直接拼进容器，而容器样式来自
 * shell.css 的 `.shell-side .overview-card`（带边框、圆角、内边距）。
 * 分区标题与导航由 sideBand() 给；状态图标、摘要卡片和活动时间线
 * 由 home-sidebar.js 投影当前对象的真实记录。 */
function renderShellSide(){
  const host=$('#shellSide');
  if(!host)return;
  host.setAttribute('aria-label',arrangementDraft?'布置房间工作台':'当前状态与日程');
  if(arrangementDraft)return;
  host.innerHTML=homeStateBand()+homeScheduleBand();
  icons();
}

/* 下方面板的头部。两处渲染共用，保证视觉一致。 */
function panelHead(title,subtitle,icon,extra=''){
  return `<header class="shell-panel-head">${I(icon)}<h2>${title}</h2>${extra?`<span class="panel-spacer"></span>${extra}`:''}</header>`;
}

/* 家具说明视图。速览条选中的家具，面板直接承载它的工作区（2026-09-29 设计稿）：
   日记书桌/睡眠与梦境嵌 life 工作区，生活挂历嵌状态工作台，成长花架嵌成长工作区；
   还没有真实工作区的（创作书架/见闻电台/衣柜陈设）保留说明卡与真实入口，
   不放假工作区。 */
const FURNITURE_WORKSPACES={desk:['life','archive'],bed:['life','sleep']};
function renderFurniturePanel(id){
  const entry=directory.find(item=>item.station===id);
  if(!entry)return renderHomePanel();
  const status=capabilityStatus(entry.cap)[0];
  const head=panelHead(entry.name,entry.text,entry.icon,chip(status));
  if(id==='calendar')return head+`<div class="shell-panel-body">${renderRoleState()}</div>`;
  if(id==='garden')return head+`<div class="shell-panel-body">${product.growthMarkup()}</div>`;
  const ws=FURNITURE_WORKSPACES[id]?product.workspace(...FURNITURE_WORKSPACES[id]):'';
  if(ws)return head+`<div class="shell-panel-body">${ws}</div>`;
  const actions=[];
  if(entry.tab)actions.push(`<button data-life="${entry.tab}">打开${entry.name} ${I('arrow-up-right')}</button>`);
  else if(entry.detail)actions.push(`<button class="primary" data-detail="${entry.detail}">打开${entry.name} ${I('arrow-up-right')}</button>`);
  if(entry.cap&&['screen','reality','image','together','game','live','content'].includes(entry.cap)){
    actions.push(`<button data-go="manage" data-manage="${entry.cap==='content'?'output':'action'}">相关配置 ${I('arrow-up-right')}</button>`);
  }
  actions.push(`<button data-detail="arrange">在房间里移动它 ${I('arrow-right')}</button>`);
  return head
    +`<div class="shell-panel-body">
        <div class="furniture-brief">
          <div class="furniture-brief-actions">${actions.join('')}</div>
        </div>
      </div>`;
}

/* 默认面板（没选家具也没选分区）：小屋总览。
   这是「点进页面先看到什么」的答案——小屋与它的家具，
   而不是一屏配置表。 */
function renderHomePanel(){
  return '';
}

/* 配置分区面板：把原来 renderManage() 的内容搬进面板容器。
   复用同一批渲染函数，不重写——那些函数已经和后端合同对齐过，
   重写只会引入新的字段漂移。 */
function renderSectionPanel(id){
  const label=manageTabs.find(([tid])=>tid===id)?.[2]||'配置';
  const subtitle=manageSubtitles[id]||'当前对象与角色的专题设置。';
  const renderer={perception:renderPerception,decision:renderDecision,action:renderAction,
    output:renderOutput,expression:renderExpression,governance:renderGovernance,
    identity:renderIdentityPage,contact:renderContactPage,memory:renderMemoryPage,
    models:renderModelsPage,maintenance:renderMaintenancePage,learning:renderLearningPage,
    setup:renderSetupPage,host:renderHostPage,appearance:renderAppearancePage,
    data:renderData}[id];
  if(!renderer)return renderHomePanel();
  return panelHead(label,subtitle,'settings-2',button('回到小屋','data-shell-home'))
    +`<div class="shell-panel-body">${renderer()}</div>`;
}

/* 整页视图：家具目录、生活观察、日程、日记。
   它们不属于任何一件家具、也不属于某一项配置分区，是「从小屋入口点进来的
   整页内容」。旧结构里这些内容挂在 life 路由的 renderHome() 里，
   外壳重排后 renderHome 不再被任何路由调用——内容搬到这里，
   否则家具目录与生活观察会整块消失（选择器还在、函数还在，就是不显示）。 */
function renderViewPanel(name){
  if(name==='directory'){
    return panelHead('家具与能力','每件家具都是一个入口；有固定机位的可以直接在小屋里选中。','armchair',
      button('回到小屋','data-shell-home'))
      +`<div class="shell-panel-body">${renderDirectory()}</div>`;
  }
  if(name==='observation'){
    return panelHead('生活观察','从今天的片段，看到记录、变化与来处。','scan-eye',
      button('回到小屋','data-shell-home'))
      +`<div class="shell-panel-body">${homeObservationCard()}</div>`;
  }
  if(name==='state'){
    /* 状态页正文曾被清空，理由写的是「小屋里生活挂历家具仍承载同一工作台」。
       但家具面板是**详情弹层**，而这里是一个整页视图：从侧栏「状态」进来
       只看到一句占位，等于这条路是死的。工作台本身一直是活的
       （state_api 的 /state 与 /state/command），所以接回来。
       状态工作台只在这里挂载；决策页的实时状态是只读上下文摘要。 */
    return panelHead('状态','身体与心理状态、生理期与作息，以及已定下的计划。','activity',
      button('回到小屋','data-shell-home'))
      +`<div class="shell-panel-body">${renderRoleState()}</div>`;
  }
  if(name==='diary'){
    /* 与状态页同一处理：日记工作区（life_api 的 /life 与 /life/command）
       一直是活的，只有这个整页入口被占位挡住了。
       家具面板里的「日记书桌」「睡眠与梦境」是同一套数据的另一个入口。 */
    return panelHead('日记与生活','阅读、睡眠、书写与真实执行记录。','notebook-pen',
      button('回到小屋','data-shell-home'))
      +`<div class="shell-panel-body">${renderLifeWorkspace()}<div class="life-routine-config">${configEditors('lifeConfigWorkspace',['life'],'生活例程')}${configEditors('libraryConfigWorkspace',['library'],'阅读资料与偏好')}</div></div>`;
  }
  return renderHomePanel();
}

/* 面板整体换内容。加一个轻量的入场动画，让「换页」有落点；
   小屋不参与这个动画——它常在，动了会显得整页在跳。 */
function paintPanel(){
  const host=$('#shellPanel');
  if(!host)return;
  const shell=window.CompanionShell;
  const section=shell?.section||null;
  const furniture=shell?.furniture||null;
  const view=shell?.view||null;
  host.innerHTML=furniture?renderFurniturePanel(furniture)
    :section?renderSectionPanel(section)
    :view?renderViewPanel(view)
    :renderHomePanel();
  host.hidden=!host.innerHTML.trim();
  const body=$('.shell-panel-body',host);
  if(body&&!state.reduceMotion&&!matchMedia('(prefers-reduced-motion: reduce)').matches){
    body.classList.add('is-swapping');
    setTimeout(()=>body.classList.remove('is-swapping'),400);
  }
  /* 面板里可能有需要挂载的工作区（记忆、模型、语义等）。
     这一步必须在 innerHTML 之后，否则容器还不存在。 */
  mountPanelWorkspaces();
  icons();
}

/* 面板内的动态工作区挂载。这里只挂「当前真的出现在面板里」的那些——
   逐一探测容器是否存在，与 render() 里的做法一致。
 *
 * 每个挂载点单独试错。
 *
 * 这条护栏的由来是一次真实的整页失效：config-editor 的 endpointFor 读
 * `product.role()` 时没判空，而窗口注入比脚本执行晚（正常时序），
 * 于是它在 mountConfigEditor 里抛 TypeError——mountPanelWorkspaces() 是
 * 在 paintPanel() 里同步遍历调用的，一次未捕获的异常会让**后面所有挂载点
 * 全部不执行**。表现是「好几页同时空白」，而真正出问题的只有一个模块。
 *
 * 所以：一个工作区挂了就只记它一个，其余照挂。用 console.warn 而不是静默
 * 吞掉——静默失败正是上一轮难查的原因。
 *
 * 注意每个调用点是**独立实参**：不能把 try 包在循环里靠下标取函数，
 * 那样参数形状会变（有的 mount 收 element，有的收 {environment,model,news}）。 */
function guarded(label,run){
  try{ run(); }
  catch(failure){ console.warn('[陪伴小屋] 工作区挂载失败：'+label,failure); }
}
function mountPanelWorkspaces(){
  /* 自带版式的整页模块：容器在就挂，不在就卸。
     这两页此前只挂在老的 manage 路由（下面 render() 里那两行），而外壳重排后
     左栏走的是 section 面板——于是从新版小屋点「主动与联系」只会得到一个空的
     <section id="contactWorkspace">，钟面永远不出现；「学习与反思」同理。
     卸的那一路同样不能少：面板是整块 innerHTML 替换的，切走时不卸载的话
     联系页那条 80ms 的涟漪推进链会继续往已经丢弃的节点上写。 */
  const contactHost=$('#contactWorkspace');
  guarded('主动与联系',()=>contactHost
    ?window.CompanionContactPage?.mount(contactHost)
    :window.CompanionContactPage?.unmount());
  const learningHost=$('#learningWorkspace');
  guarded('学习与反思',()=>learningHost
    ?window.CompanionLearningPage?.mount(learningHost)
    :window.CompanionLearningPage?.unmount());
  const decisionHost=$('#decisionWorkspace');
  guarded('决策页',()=>decisionHost
    ?window.CompanionDecisionPage?.mount(decisionHost,{groupSettingsMarkup:renderDecisionOriginal()})
    :window.CompanionDecisionPage?.unmount());
  const memoryHost=$('#memoryWorkspace');
  guarded('记忆与经历',()=>memoryHost
    ?window.CompanionMemoryPage?.mount(memoryHost)
    :window.CompanionMemoryPage?.unmount());
  /* 卸载对记忆页尤其重要：它有一条 8 秒的自动刷新定时器（整理与事实视图），
     面板整块替换后不卸载的话，定时器会继续往丢弃的节点上发请求。 */
  const memorySettingsHost=$('#memorySettingsHost');
  guarded('记忆策略',()=>memorySettingsHost
    ?window.CompanionMemorySettingsSection?.mount(memorySettingsHost)
    :window.CompanionMemorySettingsSection?.unmount());
  const maintenanceHost=$('#maintenanceWorkspace');
  guarded('治理与维护',()=>maintenanceHost
    ?window.CompanionMaintenancePage?.mount(maintenanceHost)
    :window.CompanionMaintenancePage?.unmount());
  const roleStateHost=$('#roleStateWorkspace');
  guarded('角色状态',()=>roleStateHost
    ?window.CompanionStatePage?.mount(roleStateHost,{section:roleStateHost.dataset.stateSection||'state'})
    :window.CompanionStatePage?.unmount());
  const replyHost=$('#replyWorkspace');
  const decisionReplyHost=$('#decisionReplyWorkspace');
  const contextImageHost=$('#contextImageWorkspace');
  if(replyHost)guarded('回复表达与投递',()=>window.CompanionReplyPage?.mount(replyHost,{view:'expression'}));
  else if(decisionReplyHost)guarded('群聊回应决策',()=>window.CompanionReplyPage?.mount(decisionReplyHost,{view:'decision'}));
  else if(contextImageHost)guarded('图片上下文理解',()=>window.CompanionReplyPage?.mount(contextImageHost,{view:'perception'}));
  else guarded('回复设置卸载',()=>window.CompanionReplyPage?.unmount());
  if($('#expressionWorkspace'))guarded('表达学习',()=>window.CompanionExpressionLearningPage?.mount($('#expressionWorkspace')));
  if($('#setupGuideHost'))guarded('首次配置引导',()=>mountSetupGuide());
  /* 备份与还原。它只在「资料与维护」与「治理与维护」两页出现，
     两道 renderData() 各自会插入挂载点，这里按容器是否存在探测，
     不存在就不挂——与上面几行同一个做法。 */
  if($('#backupWorkspace'))guarded('备份与还原',()=>window.CompanionBackupPage?.mount($('#backupWorkspace')));
  guarded('配置分区',()=>renderConfigEditors());
  const imageMaterialsHost=$('#imageMaterialsWorkspace');
  guarded('参考素材与衣柜',()=>imageMaterialsHost
    ?window.CompanionImageMaterialsPage?.mount(imageMaterialsHost)
    :window.CompanionImageMaterialsPage?.unmount());
  if($('#modelWorkspace'))guarded('模型与连接',()=>window.CompanionModelsPage?.mount($('#modelWorkspace')));
  if($('#semanticLearningWorkspace'))guarded('语义理解与群词义',()=>window.CompanionSemanticPage?.mount($('#semanticLearningWorkspace'),{view:'learning'}));
  if($('#semanticExpressionWorkspace'))guarded('表情素材',()=>window.CompanionSemanticPage?.mount($('#semanticExpressionWorkspace'),{view:'expression'}));
  if($('#perceptionProviderWorkspace'))guarded('感知扩展',()=>window.CompanionPerceptionPage?.mount($('#config-screen')));
  if($('#perceptionOverviewWorkspace'))guarded('感知上下文',()=>window.CompanionPerceptionOverviewPage?.mount($('#perceptionOverviewWorkspace')));
  if($('#nativeEnvironmentWorkspace'))guarded('原生感知',()=>window.CompanionNativePerceptionPage?.mount({
    environment:$('#nativeEnvironmentWorkspace'),model:$('#nativeModelWorkspace'),news:$('#nativeNewsWorkspace')}));
  const screenAccessHost=document.querySelector('[data-screen-access]');
  guarded('屏幕读取授权',()=>screenAccessHost
    ?window.CompanionScreenAccess?.mount(screenAccessHost)
    :window.CompanionScreenAccess?.unmount());
  /* 外观与设置。它没有后端端点，读的写的是 :root 上的 data-* 与 localStorage，
     但"容器在就挂、不在就卸"这条照样要走：不卸的话，主题切换的叠化回调
     会继续操作已经丢弃的节点。 */
  const appearanceHost=$('#appearanceWorkspace');
  guarded('外观与设置',()=>appearanceHost
    ?window.CompanionAppearancePage?.mount(appearanceHost)
    :window.CompanionAppearancePage?.unmount());
  /* QQ 空间拓展：容器在就挂。挂载只负责「该不该读一次状态」，
     真正的读写与重画都在区块自己的函数里（见 mountQzoneSection）。 */
  guarded('QQ 空间拓展',()=>{if($('#actionQzoneBody'))mountQzoneSection();});
}
/* 界面自己换了主题时通知外观页重读。
   为什么不让调用方直接重挂：重挂会走 unmount→mount，把 root 换成新节点，
   正在进行的主题叠化覆层会跟着重建，看着像闪了一下。
   外观页因此暴露 refresh()——保留节点，只重读令牌与按下态。 */
function notifyAppearanceChanged(){
  window.CompanionAppearancePage?.refresh?.();
}

/* 外壳重绘：左栏导航、小屋速览条、右栏状态、下方面板。
   小屋本身只在签名变化时重挂（见 render）。

   帧循环与尺寸在这里统一跟随「是否在首页」——放在这里而不是 render()，
   是因为 backHome() 只调 renderShell() 不调 render()：如果只在 render() 里
   恢复 setActive(true)，从小屋缩略条点回来之后 3D 会一直停着不渲染。 */
function renderShell(){
  const nav=$('#shellNav');
  if(nav)nav.innerHTML=window.CompanionShell?.railHTML()||'';
  renderStageBar();
  renderShellSide();
  paintPanel();
  /* 面板绘制后 iframe 才存在；分区和家具切换也从这里挂载。 */
  product.mountWorkspace();
  window.CompanionShell?.paint();
  const shellView=window.CompanionShell?.view||null;
  if(shellViewInitialized&&shellRenderedView==='state'&&shellView!=='state')entranceHandle?.skip();
  shellRenderedView=shellView;
  shellViewInitialized=true;
  const away=Boolean(window.CompanionShell?.section);
  voxelController?.setActive?.(!away);
  /* 缩略态下小屋是个返回按钮，所以要可聚焦、要有语义；
     首页时它是场景，不该出现在 Tab 序列里。 */
  const scene=$('#stageScene');
  if(scene){
    if(away){scene.tabIndex=0;scene.setAttribute('role','button');scene.setAttribute('aria-label','回到小屋');}
    else{scene.removeAttribute('tabindex');scene.removeAttribute('role');scene.removeAttribute('aria-label');}
  }
  /* 布局刚变（缩略 ↔ 放大），canvas 尺寸要重新量。等下一帧是因为
     data-away 刚由 paint() 写上，此刻浏览器还没算完布局，
     getBoundingClientRect 拿到的仍是旧尺寸。控制器的 ResizeObserver
     也会触发同一个 resize()，重复调用无害。 */
  if(voxelController)requestAnimationFrame(()=>voxelController?.resize?.());
  /* 小屋里选中家具时，让它也飞过去。相机移动与面板切换是同一件事的两面。 */
  if(voxelController&&window.CompanionShell?.furniture){
    voxelController.focus?.(window.CompanionShell.furniture);
  }
}

/* 选家具：改外壳状态 → 重绘右栏与面板 → 飞镜头。
   镜头由 renderShell 统一处理，避免两处各飞一次互相顶掉。 */
function chooseFurniture(id){
  const shell=window.CompanionShell;
  if(!shell)return;
  shell.selectFurniture(id);
  renderShell();
}
/* 选配置分区：换下方面板，小屋退到背景（不销毁）。 */
function chooseSection(id){
  const shell=window.CompanionShell;
  if(!shell)return;
  shell.selectSection(id);
  renderShell();
  closeDetail();
}
/* 回到首页：清掉分区选择，面板回到小屋总览。
   小屋本身没被销毁过，所以这一步不需要重建——它只是从窄条放大回来，
   取景仍是离开时的那个机位。 */
function backHome(){
  const shell=window.CompanionShell;
  if(!shell)return;
  shell.selectSection(null);
  route='life';lifeTab='home';
  try{history.replaceState(null,'',navHref('life','home'));}catch{}
  renderShell();
}
function render(){
  product.unmountWorkspace();
  window.CompanionMemoryPage?.unmount();
  window.CompanionMemorySettingsSection?.unmount();
  window.CompanionImageMaterialsPage?.unmount();
  window.CompanionStatePage?.unmount();
  window.CompanionSemanticPage?.unmount();
  window.CompanionPerceptionPage?.unmount();
  window.CompanionPerceptionOverviewPage?.unmount();
  window.CompanionNativePerceptionPage?.unmount();
  window.CompanionScreenAccess?.unmount();
  window.CompanionModelsPage?.unmount();
  window.CompanionExpressionLearningPage?.unmount();
  unmountSetupGuide();
  window.CompanionBackupPage?.unmount();
  /* Config editors own no host object: dropping their DOM drops their handlers,
     and mount() re-reads, so nothing survives a route change. */
  configEditorMounts=[];
  if(arrangementDraft)finishRoomEditor(false);
  updateAppearance();

  /* === 路由与外壳选择的同步 ===
     旧的 route/lifeTab/manageTab 仍被大量渲染函数与深链接依赖，
     所以保留；但外壳的「选中的分区」才是下方面板的主驱动。
     两者在这里对齐：走 manage 路由就等于选中那个分区。

     这一步必须在挂载小屋之前：mountStage() 要读 shell.section 决定
     播不播入场，深链接直接落到配置分区时那个值必须已经是有的。
     反过来写会让入场在小屋缩成窄条之后再播一遍。 */
  if(route==='manage'&&manageTab)window.CompanionShell?.selectSection(manageTab);

  /* === 小屋：同一个实例全程存活 ===
   *
   * 首页内的变化（点家具、看家具目录、看生活观察）完全不动它——相机位姿、
   * 巡游状态、布景全部保留。这也是它值得被放进栅格而不是 #main 的原因。
   *
   * 选了左侧某一项配置分区时它退到背景（缩成面板上方的窄条，见 shell.css），
   * 但**不销毁**：相机机位（控制器内部的 U）与布景保持着，回到首页时
   * 不需要重建、也不需要重播入场序列。
   *
   * 代价是缩略期间仍有一个 WebGL 场景在页面上。用 setActive(false) 停帧
   * 把最主要的开销掐掉（它内部是 cancelAnimationFrame），剩下的只有一个
   * 静态 canvas；这是「保留取景」与「零开销」之间刻意的取舍。
   *
   * 只有场景本身变了才重建：布局、光照、天气、角色或宿主连接状态。
   * 帧循环的开关不在这里，统一由 renderShell() 负责（它也是 backHome()
   * 唯一会走的路径）——两处各写一遍迟早会漏掉其中一条。
   */
  const signature=stageSignatureNow();
  if(stageMounted&&signature!==stageSignature){
    entranceHandle?.skip();
    entranceHandle=null;
    voxelController?.dispose();voxelController=null;
    stageMounted=false;
  }
  if(!stageMounted)mountStage();

  $('#navigationList').innerHTML=navGroups.map(([group,items])=>`<section class="navigation-group"><h2>${group}</h2>${items.map(navigationButton).join('')}</section>`).join('');
  const shell=window.CompanionShell;
  const sectionLabel=manageTabs.find(([id])=>id===shell?.section)?.[2];
  const current=shell?.section?'':navItems.find(([next,tab])=>next===route&&(next==='life'?tab===lifeTab:next==='manage'?tab===manageTab:true));
  const label=sectionLabel||current?.[3]||'陪伴小屋';
  const area=shell?.section?'插件配置':'小屋';
  $('#breadcrumb').innerHTML=`<span>${area}</span>${I('chevron-right')}<strong>${label}</strong>`;
  document.title=`${label} · 陪伴 V2`;

  /* #main 承载「记忆与经历」——它不是小屋的家具，也不是某一项分区配置，
     放面板里层级不对。其余路由（life / manage）都交给外壳面板渲染，
     所以 #main 留空并隐藏。

     「人物与关系」曾经也走这条整页分支，但它现在由 `relationships`
     工作区承担（真端点、真权限数据），那个靠 peopleEntries 常量拼出来的
     预览版本已删除，所以这里不再有 people 这一项。 */
  const fullPage={memories:renderMemories}[route];
  const main=$('#main');
  if(fullPage){
    main.hidden=false;
    main.innerHTML=fullPage();
    if(route==='memories'){const memoryHost=$('#memoryWorkspace');if(memoryHost)window.CompanionMemoryPage?.mount(memoryHost);}
    if($('#memorySettingsHost'))window.CompanionMemorySettingsSection?.mount($('#memorySettingsHost'));
    if($('#setupGuideHost'))mountSetupGuide();
    renderConfigEditors();
  }else{
    main.hidden=true;
    main.innerHTML='';
  }
  /* 主动与联系与学习与反思都是「自带版式」的整页模块，挂载统一由
     mountPanelWorkspaces() 按容器是否存在负责——它们只出现在外壳面板里，
     这里再按 manageTab 挂一遍会和面板那一次叠成两份（mount() 会先 unmount，
     于是第二次挂载顶掉第一次，请求白跑一遍、动画也重播一次）。 */
  renderShell();
  updateHostChrome();
}
/* 体素搭建只属于拓展页首次打开；切换小屋内视图不重播入口。 */
let entrancePlayed=false, entranceHandle=null, entranceRunId=0;
let entranceRegion=null;
function startEntrance(mount,buildFromBottom=false){
  if(entrancePlayed){
    document.documentElement.dataset.roomReady="";
    return;
  }
  entrancePlayed=true;
  startEntranceRun(mount,buildFromBottom);
}
function startEntranceRun(mount,buildFromBottom){
  if(!window.CompanionEntrance||!voxelController){
    /* 没有入场可播（脚本没到、控制器不在、或已经播过）。首屏闸门此时
       没有别的放行路径，直接放行，否则用户对着空屏等兜底超时。 */
    document.documentElement.dataset.roomReady="";
    return;
  }
  const stage=mount.closest('.room-stage')||mount;
  const region=stage.closest('.stage-region')||stage;
  entranceRegion=region;
  const runId=++entranceRunId;
  /* 先关闭外壳的高度过渡，再测量真正的 3D 内容框。
     栅格、标题和家具条始终占着最终位置；只有 voxel-room 脱离布局做拉远，
     所以按钮不会跟着缩小，交回布局时也不会重新挤压场景高度。 */
  document.body.classList.remove('entrance-settled');
  document.body.classList.add('is-entrance');
  const probe=buildFromBottom?null:window.CompanionEntrance.stageGeometry(mount,{width:innerWidth,height:innerHeight});
  if(!buildFromBottom&&!probe){
    /* 量不到（display:none、尺寸为 0、或小屋在缩略态）就整段略过，
       直接呈现终态。硬播会在一个 0 尺寸的容器上算出无意义的缩放。 */
    console.warn('小屋尺寸不可测，跳过入场序列');
    settleEntrance(region);
    /* 略过也要放行首屏：这条 return 之后没有任何人会走到 settleEntrance，
       不放行就等于让用户对着空屏等兜底超时。 */
    document.documentElement.dataset.roomReady="";
    return;
  }
  if(probe)probe.radius=Math.max(0,parseFloat(getComputedStyle(stage).borderTopLeftRadius)-stage.clientLeft)||0;
  if(!buildFromBottom)document.body.classList.add('is-entrance-pull');
  region.classList.add('is-entrance');
  try{
    const handle=window.CompanionEntrance.run(voxelController,mount,{
      buildFromBottom,
      /* 定格后交回当前时段的光照，别把用户选的时段冲掉。 */
      light:state.scene==='evening'?'dusk':state.scene,
      /* 首页同步缩放容器；状态页保持画布尺寸，只驱动镜头和体素建造面。 */
      stage:buildFromBottom?null:mount,
      reducedMotion:state.reduceMotion,
      /* 拉远途中改变窗口大小时，仍从占位的场景框测量目标，不能量 fixed 层。 */
      measureRest:()=>{
        const rect=stage.getBoundingClientRect(),css=getComputedStyle(stage);
        const left=parseFloat(css.borderLeftWidth)||0,top=parseFloat(css.borderTopWidth)||0;
        return {left:rect.left+left,top:rect.top+top,
          width:rect.width-left-(parseFloat(css.borderRightWidth)||0),
          height:rect.height-top-(parseFloat(css.borderBottomWidth)||0)};
      },
      /* probe 是加 .is-entrance 之前量到的静息矩形；序列不能重新读取
         fixed 全屏节点，否则最终尺寸会被误判成视口尺寸，缩放比例变成 1。 */
      geometry:probe,
      onPhase:phase=>{
        if(runId===entranceRunId){
          if(phase==='settle'){
            dockEntrance();
            document.body.classList.add('entrance-reveal');
          }
          if(phase==='done')settleEntrance(region);
        }
      },
    });
    entranceHandle=handle;
    /* 入口序列先把相机同步到中央近景，再放行首屏；下一帧才开始拉远。 */
    handle.ready?.then(()=>{if(runId===entranceRunId)document.documentElement.dataset.roomReady="";});
    /* run() 立即返回句柄；done 才是「序列结束」。失败也 resolve，
       所以这里不需要 catch——入场绝不能把页面卡住。 */
    handle.done.then(()=>{
      if(runId===entranceRunId){
        if(entranceHandle===handle)entranceHandle=null;
        settleEntrance(region);
      }
    });
  }catch(error){
    if(runId===entranceRunId){
      console.warn('入场序列未能启动，已直接呈现：',error);
      settleEntrance(region);
    }
  }
}
function dockEntrance(){
  if(!document.body.classList.contains('is-entrance-pull'))return;
  document.body.classList.remove('is-entrance-pull');
  /* 固定层与正常内容框在这一刻重合。同步重绘，不把缓冲区调整留到下一帧。 */
  voxelController?.resize?.();
}
function settleEntrance(region){
  entranceRegion=region||entranceRegion;
  dockEntrance();
  document.body.classList.remove('is-entrance','entrance-reveal');
  document.body.classList.add('entrance-settled');
  entranceRegion?.classList.remove('is-entrance');
  /* 闸门事实上已经在 startEntrance() 里放行了（小屋一挂载就放行）。
     这里再写一次是兜底：本函数覆盖「入场启动了但走到异常分支」的路径，
     写同一个值是幂等的，漏了它反而会多出一条卡在启动幕上的路径。
     真正的兜底在 index.html 的 7 秒计时器，覆盖入场根本没启动的情形。 */
  document.documentElement.dataset.roomReady="";
}
const directory=[
  {id:'desk',station:'desk',icon:'notebook-pen',name:'日记书桌',text:'书写归档与生活记录',detail:'desk',group:'base',color:'amber'},
  {id:'calendar',station:'calendar',icon:'calendar-days',name:'生活挂历',text:'当天安排与实际进展',tab:'state',group:'base'},
  {id:'bed',station:'bed',icon:'bed-double',name:'睡眠与梦境',text:'休息状态、保存的梦境',detail:'sleep',group:'base',color:'rose'},
  {id:'lounge',station:'lounge',icon:'book-open',name:'阅读角',text:'个人阅读原文、片段与进度',detail:'reading',group:'base',color:'green'},
  {id:'album',station:'art',icon:'images',name:'相框与相册',text:'查看已保存的原照片',detail:'album',group:'base'},
  {id:'garden',station:'garden',icon:'sprout',name:'成长花架',text:'个人目标、技能与来源',detail:'growth',group:'base',color:'green'},
  {id:'radio',station:'radio',icon:'radio',name:'见闻电台',text:'新闻、文章与发现',detail:'discoveries',group:'base',color:'amber'},
  {id:'content',station:'shelf',icon:'library-big',name:'创作书架',text:'原稿、作品与内容版本',detail:'books',cap:'content'},
  {id:'image',station:'image',icon:'camera',name:'画面工作室',text:'生成画面与素材设置',detail:'cap-image',cap:'image',color:'rose'},
  {id:'together',station:'together',icon:'phone',name:'共处电话',text:'通话、一起看与一起读小说',detail:'cap-together',cap:'together',color:'green'},
  {id:'game',station:'game',icon:'dices',name:'游戏棋桌',text:'共同游玩与对局',detail:'cap-game',cap:'game',color:'amber'},
  {id:'screen',station:'ext-000000000000000000000001',model:'monitor',accent:'#7e91b5',icon:'monitor',name:'屏幕台',text:'屏幕来源与观察范围',detail:'cap-screen',cap:'screen'},
  {id:'reality',station:'ext-000000000000000000000002',model:'pedestal',accent:'#84a091',icon:'radio-tower',name:'现实设备台',text:'真实设备、场所与动作结果',detail:'cap-reality',cap:'reality',color:'green'},
  {id:'live',icon:'mic-vocal',name:'直播与表演',text:'节目、场景与角色呈现',detail:'cap-live',cap:'live'},
];
/* 一件家具当前能不能用。
 *
 * 判据只有两个来源：扩展自报的状态（未安装 / 已停用 / 未上报），
 * 以及本地把它移出了房间。**不用** config-snapshot 那份快照——它是发行版
 * 的示例值，`base` 恒为 {}，拿它判「已开启 / 未启用」永远得到「未启用」，
 * 是假状态。旧版 directory 表里每件基础家具都挂着这样一条 label，
 * 还把两处写死的示例词（'示例记录' / '示例照片'）混在里面。
 *
 * 新增判据一律走这两个函数，不要在别处另写一份——两份判据漂移时，
 * 表现是「筛选说不可用、行里却显示可用」，不报错。 */
function furnitureUnavailable(item){
  if(!item.cap) return false;
  return product.provider(item.cap)?.integration_state==='missing'
    || ['removed','planned'].includes(state.modules[item.cap]);
}
function furnitureStatus(item){
  if(item.cap) return capabilityStatus(item.cap);
  /* 基础家具没有能力状态可读，标签按「它自己有没有设置」给：
     相框与相册走 Image 能力、见闻电台暂无可写设置、其余进各自的 V2 工作区。 */
  if(item.id==='album') return ['Image 能力入口','gray'];
  if(item.id==='radio') return ['暂无设置','gray'];
  return ['V2 工作区','gray'];
}
/* 家具目录。
 *
 * 旧版是四列等宽卡片网格 + 四个筛选页签。卡片每张都要重排一遍
 * 图标 + 名字 + 描述 + 归属 + 状态，扫二十张很累；而「待处理」那个页签
 * 本来就是一个分组，做成组标题后用户不用先点一下才能看到哪里出了问题。
 *
 * 现在按「能不能用」分组：待处理在最前，然后是可用与基础生活。
 * 行结构复用 home.css 的 .home-item——图标、名字与说明、归属、状态、一个动作。 */
function renderDirectory(){
  const counts={
    all:directory.length,
    base:directory.filter(item=>item.group==='base').length,
    extensions:directory.filter(item=>item.cap).length,
    attention:directory.filter(item=>item.cap&&product.provider(item.cap)?.integration_state!=='connected').length,
  };
  const toolbar=`<div class="home-tools"><div class="home-filters" role="group" aria-label="筛选家具">${furnitureFilters.map(([id,label])=>`<button data-furniture-filter="${id}" aria-pressed="${furnitureFilter===id}" class="${furnitureFilter===id?'active':''}">${label}<span>${counts[id]}</span></button>`).join('')}</div><label class="home-search">${I('search')}<input type="search" value="${escapeHTML(furnitureQuery)}" data-directory-search placeholder="搜索家具或能力" aria-label="查找家具或能力"></label></div>`;
  const shown=filteredFurniture().length;
  const foot=`<div class="home-foot"><span id="furnitureResultCount" role="status">显示 ${shown} / ${directory.length} 件</span></div>`;
  return toolbar+`<div id="directoryGrid">${directoryCards()}</div>`+foot;
}
function directoryCards(){
  const items=filteredFurniture();
  if(!items.length) return `<div class="home-empty">${I('search')}<strong>没有符合条件的家具</strong><button class="button small" data-clear-furniture>清除筛选</button></div>`;
  /* 分组只在「全部」视图下有意义：用户已经点名要看某一类时，
     再按可用性切一刀会让他看到空组标题。 */
  const attention=items.filter(item=>furnitureUnavailable(item)||(item.cap&&product.provider(item.cap)?.integration_state!=='connected'));
  const groups=furnitureFilter==='all'&&attention.length
    ? [['状态待检查','点开可以核对安装状态与管理入口。',attention],
       ['状态已读取与基础生活','拓展能否在当前对话中调用，还需要核对角色启用与会话授权。',items.filter(item=>!attention.includes(item))]]
    : [['', '', items]];
  return groups.filter(([, , list])=>list.length).map(([title, note, list])=>`
    ${title?`<div class="home-group-head"><h3>${title}</h3>${note?`<small>${note}</small>`:''}<span class="pill gray">${list.length} 件</span></div>`:''}
    <div class="home-rows">${list.map(furnitureRow).join('')}</div>`).join('');
}
function furnitureRow(item){
  const [label,type]=furnitureStatus(item);
  const unavailable=furnitureUnavailable(item);
  const stored=item.station&&(voxelController?voxelController.getState().storedFurniture.includes(item.station):state.roomLayouts[layoutKey()]?.items?.[item.station]?.stored);
  const owner=item.cap?(product.provider(item.cap)?.label||capabilityConfig(item.cap).label||'拓展能力'):'基础生活';
  const action=item.station&&!unavailable
    ? `<button data-locate-furniture="${item.id}" aria-label="${stored?'布置已收纳的':'在小屋中查看'}${item.name}">${I(stored?'archive':'focus')}<span>${stored?'布置':'定位'}</span></button>`
    : `<button data-furniture="${item.id}" aria-label="打开${item.name}"><span>打开</span></button>`;
  return `<div class="home-item ${unavailable?'unavailable':''}">
    <span class="home-item-icon">${I(item.icon)}</span>
    <span class="home-item-main">
      <span class="home-item-title"><strong>${item.name}</strong>${chip(label,type)}</span>
      <small>${item.text}</small>
    </span>
    <span class="home-item-end"><span class="home-item-owner">${owner}</span>${action}</span>
  </div>`;
}
function updateFurnitureDirectory(){
  const grid=$('#directoryGrid');if(!grid)return;grid.innerHTML=directoryCards();
  $$('[data-furniture-filter]').forEach(button=>{button.classList.toggle('active',button.dataset.furnitureFilter===furnitureFilter);button.setAttribute('aria-pressed',String(button.dataset.furnitureFilter===furnitureFilter));});
  $('#furnitureResultCount').textContent=`显示 ${filteredFurniture().length} / ${directory.length} 件`;
  if(!voxelController||$('.voxel-scene-failed'))$$('[data-locate-furniture]').forEach(button=>button.disabled=true);
  icons();
}
/* 家具能力状态变化后的重绘。
 *
 * 这个函数此前是**必然抛错**的：它按旧首页的 id 与 class 找节点
 * （`.home-capabilities` / `#home-furniture` / `.furniture-toolbar` /
 * `.furniture-grid` / `.furniture-footnote`），而外壳改版后这些都不再产出。
 * `$('.home-capabilities')` 恒为 null，下一行 `.outerHTML=` 就抛
 * TypeError——因为它在事件处理器里，用户看到的是「点了没反应」。
 *
 * 现在走外壳的重绘入口：右栏与面板都由它统一负责，不再自己拼 DOM。
 * 这也顺带解决了「两处各写一遍重绘逻辑、迟早漏掉一条」的老问题。 */
function refreshHomeCapabilities(){
  syncFurnitureScene();
  /* 用 renderShell 重绘，不是 shell.paint()——后者只同步 data-* 属性，
     不管内容；用错会「状态变了但界面没动」。 */
  renderShell();
}
/* 小屋首页右侧的几张概览卡。
 *
 * 这里原先每一张都有一个 `if(product.hosted())` 早退分支，宿主没接上时
 * 落进一份写死的示例内容（「示例日」「预览待处理」「示例记录」…）。
 * 那份示例有两个问题：一是它把「连不上 AstrBot」这件事伪装成正常内容，
 * 二是它跟真实数据长得像但字段不同，改一处要改两遍。
 *
 * 现在这些卡片**只有一条路径**：数据来自 product 读取的真实端点。
 * 读不到时由 product 的 unavailable() 给出可执行的原因（正在读取 /
 * 具体失败码 / 当前对象没有此工作区 / 尚无记录），也算一条真实答案。
 */
function scheduleCard(){return product.scheduleCard();}
function stateCard(){return product.stateCard();}
/* 右栏延续 V1 的状态摘要与日程时间线；标题和导航仍由小屋外壳负责。 */
function sideBand(title,body,action){return `<section class="home-band home-side-band"><header class="home-band-head"><h2>${title}</h2>${action}</header>${body}</section>`;}
function homeStateBand(){return sideBand('此刻的状态',stateCard(),'');}
function homeScheduleBand(){return sideBand('活动与日程',scheduleCard(),'<button type="button" class="text-button home-side-action" data-life="state">翻开日历</button>');}
const observationFilters=[['records','日记与梦境'],['timeline','生活轨迹'],['state','状态变化'],['impact','交互影响']];
/* 生活观察。
 *
 * 旧版是三张 overview-card 并排（观察 / 目标与成长 / 记忆与关系），
 * 每张自己一套内边距，屏上三个等宽框。现在收成一个分区：段内切换条选
 * 看哪一类，下面只出这一类的内容，行距统一。
 *
 * 「目标与成长」与「记忆与关系」不再是并排的卡，改成切换条里的两个
 * 选项——它们本来就是「同一批观察数据的另外两种看法」，不是并列的三件事。 */
function homeObservationCard(){return `
  <div class="home-tabs" role="group" aria-label="生活观察内容">${observationFilters.map(([id,label])=>`<button data-observation="${id}" class="${observationFilter===id?'active':''}" aria-pressed="${observationFilter===id}" aria-controls="observationBody">${label}</button>`).join('')}</div>
  <div id="observationBody" class="home-band-body" aria-live="polite">${observationContent()}</div>
  <div class="home-foot"><span><button class="text-button" data-life="state">${I('activity')}状态与日程</button> <button class="text-button" data-go="manage" data-manage="maintenance">${I('settings-2')}运行记录</button></span></div>`;}
/* 观察内容。
 *
 * 四个页签都接真实端点：
 *     records  → life.journals（日记与梦境）
 *     timeline → life.activities（已开始与已安排的活动）
 *     state    → state.values（角色状态数据）
 *     impact   → 没有对应端点，所以不编内容，只说明它要什么条件才有。
 * 「交互影响」那一支是**有意为之**的空态，不是缺控件：普通聊天不会自动
 * 推算成情绪变化，只有明确记录了来源的互动影响才会出现。 */
function observationContent(){
  const unavailable=value=>`<p class="home-note">${escapeHTML(value)}</p>`;
  if(observationFilter==='timeline'){
    const list=product.lifeActivities();
    if(!Array.isArray(list))return unavailable(product.unavailableReason('life'));
    if(!list.length)return unavailable('暂无生活活动。');
    return `<div class="home-rows">${list.map(item=>`<div class="home-row">
      <span class="home-row-main"><strong>${escapeHTML(item.title||product.stateLabel(item.kind)||item.kind||'生活活动')}</strong><small>${escapeHTML(item.progress_note||item.description||'')}</small></span>
      <span class="home-row-value"><small>${escapeHTML(product.when(item.started_at||item.due_at))}</small>${chip(escapeHTML(product.stateLabel(item.state)||item.state||''),item.state==='active'?'lavender':'gray')}</span></div>`).join('')}</div>`;
  }
  if(observationFilter==='state'){
    const values=product.stateValues();
    if(!values)return unavailable(product.unavailableReason('state'));
    const energy=values.energy;
    const rows=[['心情',values.mood],['身体',values.health],['睡眠',values.sleep],['饥饿',values.hunger],['忙碌程度',values.busy]]
      .filter(([,value])=>value!=null&&value!=='');
    const meter=Number.isFinite(Number(energy))
      ? `<div class="home-energy"><span>心理能量</span><strong>${escapeHTML(String(energy))} <small>/ 100</small></strong><meter min="0" max="100" value="${escapeHTML(String(energy))}" aria-label="心理能量 ${escapeHTML(String(energy))} / 100"></meter></div>`
      : '';
    const facts=rows.length
      ? `<dl class="home-facts">${rows.map(([name,value])=>`<div><dt>${name}</dt><dd>${escapeHTML(typeof value==='object'?'查看状态页':value)}</dd></div>`).join('')}</dl>`
      : '';
    return meter+facts+(meter||facts?'':'')
      + ``;
  }
  if(observationFilter==='impact')return `<div class="home-empty">${I('messages-square')}<strong>交互影响需要先有带来源的互动记录</strong><button class="button small" data-go="memories">查看记忆与经历</button></div>`;
  if(observationFilter==='growth')return homeAgendaCard();
  if(observationFilter==='memory')return homeMemoryCard();
  const journals=product.lifeJournals();
  if(!Array.isArray(journals))return unavailable(product.unavailableReason('life'));
  if(!journals.length)return unavailable('还没有保存的日记或梦境。在日记页可以写下今天。');
  return `<div class="home-rows">${journals.slice(0,4).map(item=>`<div class="home-row">
    <span class="home-row-icon">${I(item.kind==='dream'?'moon':'notebook-pen')}</span>
    <span class="home-row-main"><strong>${escapeHTML(item.summary||(item.kind==='dream'?'一次梦境':'生活片刻'))}</strong><small>${escapeHTML(item.unavailable_reason?'原始来源暂不可用':(item.body||'正文尚未生成'))}</small></span>
    <span class="home-row-value"><small>${escapeHTML(item.local_date||'')}</small>${chip(item.kind==='dream'?'梦境':'日记','gray')}</span></div>`).join('')}</div>
    `;
}
function homeAgendaCard(){return product.growthCard();}
function homeMemoryCard(){return product.memoryCard();}

function renderMemoriesOriginal(){return `<section id="memoryWorkspace" aria-label="记忆工作区"><p class="memory-notice" role="status">正在连接记忆工作区…</p></section>`;}
const capabilities=[
  ['content','library-big','创作书架','Content','原稿、作品与版本，留住还没写完的想法。'],
  ['image','image','画面与相册','Image','生成画面、保存原件，让照片回到相册里。'],
  ['together','coffee','一起相处','Together','通话、一起看、工作协同与一起读小说，共用一间房间。'],
  ['game','dices','共同游玩','Game','从棋桌开始，继续同一场游戏。'],
  ['screen','monitor','屏幕陪伴','Screen','连接桌面，查看授权范围内的屏幕活动。'],
  ['reality','radio','现实触及','Reality','真实设备与场所、镜头与声音覆盖，以及动作结果。'],
  ['live','mic-vocal','直播与表演','Live','节目、场景与直播中的角色呈现。'],
];
function capabilityStatus(id){const item=product.provider(id);if(item)return [product.statusLabel(item.integration_state),item.integration_state==='connected'?'':'gray'];const s=state.modules[id];const local=['paused','setup','permission','removed','planned'].includes(s);if(!local){const connected=integrationStateCopy(id);if(connected)return connected;}return ({enabled:['配置开启',''],disabled:['配置关闭','gray'],unknown:['配置未知','amber'],paused:['已暂停','gray'],setup:['待连接','amber'],permission:['待授权','amber'],removed:['已丢弃','gray'],planned:['待交付','gray']})[s]||['配置未知','amber'];}
/* 主题色卡不再硬编码色值——色值只在 tokens.css 里，这里只有注册表给的 id/名/说明。
   色卡预览靠给元素套 data-theme 真实渲染：卡里的文字、边框、强调色都是那套主题
   真正画出来的，而不是画几个假的色条。旧写法把 bg/accent/quiet 抄在数组里，
   加一套主题要同步改两处，漏改就和实际不符。 */
const themeCatalog = window.CompanionTheme;
const themeSwatches = (themeCatalog?.THEMES || [{id:'courtyard',label:'庭院',note:'默认外观',mode:'light'}]);
const themeGroups = [
  ['浅色', themeSwatches.filter(item => item.mode !== 'dark')],
  ['深色', themeSwatches.filter(item => item.mode === 'dark')],
];
const appearanceGroups=[
  ['density','显示密度',[['compact','紧凑'],['standard','标准'],['roomy','宽松']],'影响卡片内边距与区块间距'],
  ['radius','圆角',[['sharp','方正'],['standard','标准'],['round','圆润']],'影响卡片、按钮与输入框的圆角'],
  ['typeScale','字号',[['s','小'],['m','标准'],['l','大'],['xl','特大']],'整体缩放正文与说明文字'],
  ['motion','动效',[['full','完整'],['low','减弱'],['off','关闭']],'减弱或关闭过渡与滚动动画'],
];
function appearancePanel(){
  const current=product.appearance();
  /* 色卡不再传色值，只给 id。卡内的颜色由 CSS 从 tokens.css 的真实令牌取，
     所以色卡里画出来的就是那套主题的实际底色与强调色。 */
  const swatch=item=>`<button class="theme-swatch ${current.theme===item.id?'active':''}" data-appearance="theme" data-appearance-value="${item.id}" aria-pressed="${current.theme===item.id}"><span class="theme-swatch-preview" data-theme="${item.id}" aria-hidden="true"><span class="swatch-bar"></span><span class="swatch-line"></span><span class="swatch-line short"></span><span class="swatch-chip"></span></span><span class="theme-swatch-copy"><strong>${escapeHTML(item.label)}</strong><small>${escapeHTML(item.note)}</small></span>${current.theme===item.id?I('check'):''}</button>`;
  const themeSection=`<section class="appearance-block" aria-label="主题"><div class="appearance-block-head"><h3>主题</h3></div>${themeGroups.filter(([,list])=>list.length).map(([groupName,list])=>`<div class="theme-group"><span class="theme-group-label">${groupName}</span><div class="theme-swatch-grid">${list.map(swatch).join('')}</div></div>`).join('')}
  <div class="option-row"><div>跟随小屋光照<small>小屋进入夜晚时自动切到深色主题。默认关闭；开启后仍会保留你手动选择的主题，只在时段真正改变时切换。</small></div><button class="switch" role="switch" aria-checked="${product.followLight()}" data-follow-light aria-label="跟随小屋光照切换主题"></button></div></section>`;
  return `${themeSection}
  <section class="appearance-block" aria-label="显示维度">${appearanceGroups.map(([name,label,options,hint])=>`<div class="option-row appearance-row"><div>${label}<small>${hint}</small></div><div class="segmented" role="group" aria-label="${label}">${options.map(([value,text])=>`<button data-appearance="${name}" data-appearance-value="${value}" aria-pressed="${current[name]===value}" class="${current[name]===value?'active':''}">${text}</button>`).join('')}</div></div>`).join('')}</section>
  <section class="appearance-block" aria-label="文字辅助"><div class="option-row"><div>放大辅助文字<small>在所选字号基础上再提高说明与详情文字的可读性</small></div><button class="switch" role="switch" aria-checked="${state.largeText}" data-display="largeText" aria-label="放大辅助文字"></button></div><div class="option-row"><div>尊重系统减少动态效果<small>系统开启时会自动减弱动画，与上方动效设置取更严格的一方</small></div><span class="pill gray">${matchMedia('(prefers-reduced-motion: reduce)').matches?'系统已开启':'系统未开启'}</span></div></section>`;
}
function applyAppearanceControl(target){
  const name=target.dataset.appearance,value=target.dataset.appearanceValue;
  if(!name||!value)return false;
  const applied=product.setAppearance(name,value);
  /* 主题切换会整页叠化，重渲染面板会打断那次过渡；只同步按下态。 */
  $$(`[data-appearance="${name}"]`).forEach(button=>{const on=button.dataset.appearanceValue===applied;button.classList.toggle('active',on);button.setAttribute('aria-pressed',String(on));});
  /* 换主题时小屋跟着换光照，界面与场景的明暗不再各走各的。 */
  if(name==='theme')syncLightFromTheme(applied);
  const group=appearanceGroups.find(([key])=>key===name);
  const label=group?`${group[1]}：${Object.fromEntries(group[2])[applied]||applied}`:`主题：${themeCatalog?.label(applied)||applied}`;
  toast(label);
  return true;
}
function renderAppearanceSurfaces(){
  /* 维度改变后刷新仍然打开的外观面板：弹窗与设置页共用同一组件。 */
  const body=$('#dialogContent .appearance-panel');
  if(body)body.innerHTML=appearancePanel();
  const inline=$('[data-appearance-inline]');
  if(inline)inline.innerHTML=appearancePanel();
  updateAppearance();
  icons();
}
const manageTabs=[
  ['perception','scan-eye','感知'],['decision','brain','决策'],['action','play','行动'],['contact','heart-handshake','主动联系'],['expression','message-square-more','表达'],['output','shapes','产出'],['governance','user-round','自我'],
  ['identity','shield-check','关系与权限'],['memory','orbit','记忆与经历'],['learning','graduation-cap','学习与成长'],['models','sliders-horizontal','模型与连接'],['maintenance','settings-2','运行诊断'],
  ['setup','rocket','开始使用'],
  ['host','power','账号与会话'],['appearance','palette','外观与设置'],['data','database','资料与备份'],
];
/* 删除的五个无入口页签：growth / base / state / reply / preferences。
   侧栏与 configLink() 从来不指向它们，内容已归到对应领域：
     state → 小屋状态页    reply → 表达 D1    preferences → 主动与联系
     base  → 日记与生活    growth → 学习与反思 L1
   保留它们的唯一后果是旧深链接会打开一张与主页面重复的配置页。
   manageTabs 是 manage 路由的白名单（navigate 里用 manageTabs.some 校验），
   所以删掉即等于旧深链接回落到默认页，不会再渲染重复内容。 */
/* === 配置控制台外壳 ===
   十一个配置页共用。
 *
 * 五元组里的第三格（state）已经不再渲染。它原先把分区标成
 * 「已接入 / 部分接入 / 待接入」——那是**开发阶段的自查标签**，回答的是
 * 「这一块接到什么程度了」。用户不关心这个，他关心「这一块能不能用」；
 * 而能用不能用，打开就看得到，不需要一个标签先说一遍。所以标签去掉了，
 * 元组形状留着（调用点有十几处，为改一行文案动十几处不划算）。
 *
 * 这里**不**保留 CONSOLE_STATE / consoleState：它们已经没有任何调用点，
 * 留着就是下一轮「这个还能不能用」的疑问。
 */
/* 这里曾有一个 boundaryCard()。
 *
 * 它渲染「由谁保存 / 现在能做什么 / 下一步」三行合同说明，也就是用户说的
 * 「垃圾桶」：一块地方本来该放功能，放不下就放一张解释「为什么这里没有功能」
 * 的卡。全页最多时 30 处，是脚手架感的主要来源。
 *
 * 处理原则是「能接真端点就接，接不上就删」——能接的已经接上（备份工作区、
 * 关系工作区、状态工作区…），接不上的直接不渲染。调用点已全部清完，
 * 函数本身也就没有存在的理由了，连同这段说明一起删掉。
 */
/* 分区块。
 *
 * 参数仍收 [code,title,state,summary,body] 五元组——调用点有十几处，
 * 换签名要同时改十几处、还容易改错，所以保留形状。但 code 与 state
 * **不进 DOM**：它们在旧版里渲染成 A1/B2/C3 编号徽章与「已接入」状态点，
 * 那是给开发者看的实现进度表，不是用户要的东西。
 *
 * 现在只渲染：标题、一句说明、内容。编号与状态留在调用点上作为
 * 内部标识（谁在管哪一块），不再出现在界面里。 */
/* 分区。
 *
 * 旧版把标题与说明一起塞进带底色的卡头，外面再套一层带边框的卡，
 * 于是每块功能都是一张卡片、卡头三行文字（标题 / 说明 / 里面的子标题 /
 * 子说明），字号与灰度还都差不多——用户扫视时找不到可以动手的东西，
 * 这就是「一坨文字」的来源。
 *
 * 现在：**去掉卡片边框**，分区之间用一条细分隔线；标题单独一行、
 * 说得尽量短；说明收进副行（弱化小字、更窄的行宽），与标题同一行右对齐
 * 或紧贴标题下方，不再占主视线；控件紧跟在标题下面。
 *
 * 副行不是删除说明——里面确实有真信息（「保存后从下一轮评估生效」这类）。
 * 降级的是它的**层级**，不是内容。 */
function consoleSection([title,summary,body='',id='']){
  /* id 可选，用于卷首那条索引的锚点。没有 id 时分区的形状与从前完全一样——
     所以给老调用点加锚点是**叠加**的，不必逐个改。 */
  const anchor = id ? ` id="${id}"` : '';
  const note = String(summary||'').trim();
  return `<section class="console-section"${anchor}><header class="console-section-head"><div class="console-section-copy"><h2>${title}</h2>${note?`<p class="console-section-note">${escapeHTML(note)}</p>`:''}</div></header>${body?`<div class="console-section-body">${body}</div>`:''}</section>`;
}
/* 分区容器。
 *
 * 旧版本这里叫 consoleSections，会渲染一行「N 个子类：X 个已接入、Y 个部分接入、
 * Z 个待接入」的统计，配一个带 A1/B2/C3 编号的索引条。那是脚手架：
 * 用户看到的是一份「实现进度表」，而不是自己的角色在做什么。
 *
 * 现在只做两件事：给分区标题，按顺序渲染内容块。编号不进 DOM，
 * 标题里也不出现「已接入/待接入」这类词。
 *
 * 参数签名保持 [标题, 内容] 二元组，内容为 null 的分区直接跳过——
 * 这样调用点在「这一块暂时没有可接的端点」时可以传 null 整块消失，
 * 而不是塞一张解释卡。 */
function consoleSections(sections){
  /* 只渲染真的有内容的块：body 为空（或被 boundaryCard 清空）的整块跳过，
     否则会留下一个只有标题、下面空空的壳——那比不渲染更像出错了。 */
  const usable = sections.filter((section)=>
    Array.isArray(section) && typeof section[2] === 'string' && section[2].trim());
  return `<div class="console">${usable.map(consoleSection).join('')}</div>`;
}
/* 分区内的次级标题。
 *
 * 与分区标题的区别靠**排版权重**拉开，不再靠再套一层边框：
 * 分区标题大一号、带下分隔线；这里只有一行小标题，说明紧贴其下且更弱。
 * 这样一屏里能扫到「标题 → 控件」，而不是「卡片 → 卡片 → 控件」。 */
/* 挂载的工作区自带标题与生效信息，外层无需再加一遍。 */
function consoleMountHead(){return '';}
function configLink(label,tab){return button(label+' '+I('arrow-up-right'),`data-go="manage" data-manage="${tab}"`,'small');}
function providerSummary(ids){return product.providersMarkup(ids);}
function consoleLoading(text){return `<p class="console-loading" role="status">${text}</p>`;}
/* 配置编辑器挂载点。
 *
 * 旧版本在不满足条件时给一句「需要在已登录的 AstrBot 管理界面中打开才可读写」——
 * 那既是脚手架词汇，又把「连不上」当成常态。现在的行为：
 *   - 没有可用角色时返回空串（整块不渲染，由外层给出「先选对象」的一步引导）；
 *   - 有角色就渲染挂载点，真实失败由 config-editor 自己的错误码提示。 */
/* configEditors 早前的这一份以 product.role() 判空，但 role() 在目标未绑定时
   返回的是空壳对象，于是「还没初始化」被当成「已经初始化」，挂载点照渲染，
   里面的工作区各自去请求、各自失败。下面那一份改用 reply_api 是否可用来判断，
   并把「先初始化」和「重新读取」做成按钮，已取代它。 */
/* 目标未就绪时的一步引导。只保留「先选对象」这一种真实前置条件——
   连接问题由连接层自己重试并报错，不在这里充当永久状态。 */
/* pageNeedsTarget 早前在这里有过一份「看 product.role() 是否为空」的版本。
   它已经被下面那份更严的判定取代：role() 在目标还没绑定时会返回一个**空壳对象**，
   于是「还没选对象」会被判成「已经选好了」，接着四个工作区各渲染一遍空态。
   脚本生效范围里重复声明同名函数只有后者生效，留着这份等于留一个改了不生效的陷阱。
   configLink / consoleLoading / consoleMountHead / providerSummary 同名重复且内容一致，
   一并收拢——重复本身不影响行为，但会让「改了一处没生效」变得无从判断。 */
function renderRoleState(section=''){return `<section id="roleStateWorkspace" ${section?`data-state-section="${section}" `:''}aria-label="${section==='contact'?'行为规划与沉默':'角色状态维护'}">${consoleLoading(section==='contact'?'正在读取联系节奏与沉默设置…':'正在连接角色状态工作区…')}</section>`;}
/* 日记与生活的工作区容器。
 *
 * 它不是自带版式的页面模块，而是 iframe 工作区（pages/日记与生活/），
 * 由 product.workspace('life') 产出容器、product.mountWorkspace() 用 srcdoc 填。
 * 所以这里不能自己拼 iframe——那样拿不到桥的上下文转发（iframe 内的请求要经
 * product-page.js 的白名单翻译成 role.life_api 的真实路径）。
 *
 * 单独包一层的理由：日记数据由 life 工作区提供，作息配置由 role.life 工作台提供，
 * 两者共用「日记与生活」入口，但分别读写各自的接口。 */
function renderLifeWorkspace(){
  const markup=product.workspace('life');
  return markup||`<div class="page-guide">${I('info')}<div><h2>日记与生活</h2><p>未读取到宿主目录。</p></div><div class="dialog-actions"><button class="button small" type="button" data-workspace-retry>重新读取</button></div></div>`;
}
function renderReply(){return `<section id="replyWorkspace" aria-label="表达与投递设置">${consoleLoading('正在连接表达设置工作区…')}</section>`;}
const perceptionSources=[
  ['message-square-text','文字与引用','消息正文、引用原话与来源'],
  ['image','图片与动图','保留原图，动图按受限帧数理解'],
  ['audio-lines','语音','读取原始语音并交给支持音频的模型'],
  ['video','视频','提取有限画面与音频片段'],
  ['messages-square','合并转发','按原消息顺序读取有来源的内容'],
];
const perceptionProviders=[
  {id:'screen',icon:'monitor',name:'屏幕陪伴',plugin:'astrbot_plugin_screen_companion',page:'屏幕伴侣',description:'屏幕采集、识别与观察记录'},
  {id:'reality',icon:'radio',name:'现实触及',plugin:'astrbot_plugin_reality_companion',page:'reality-companion',description:'摄像头、移动端与现实设备'},
];
function perceptionAddress(spec,provider){
  if(!provider?.installed)return '';
  const route=provider.pages?.includes(spec.page)
    ?`/#/plugin-page/${encodeURIComponent(spec.plugin)}/${encodeURIComponent(spec.page)}`
    :'/#/extension/plugins';
  return new URL(route,location.href).href;
}
function renderPerceptionProvider(spec){
  const provider=product.provider(spec.id);
  const address=perceptionAddress(spec,provider);
  const status=provider?product.statusLabel(provider.integration_state):'状态尚未读取';
  const statusClass=provider?.integration_state==='connected'?'':'gray';
  const readiness=provider?.runtime_ready===true?'扩展报告已就绪':provider?.runtime_ready===false?'扩展尚未就绪':'执行状态由扩展确认';
  return `<article class="perception-provider"><div class="perception-provider-main"><span class="perception-provider-icon">${I(spec.icon)}</span><div><div class="perception-provider-title"><h3>${spec.name}</h3>${chip(escapeHTML(status),statusClass)}</div><small>${provider?`${escapeHTML(provider.reason||'状态已读取')} · ${escapeHTML(readiness)}`:'未取得扩展公开状态'}</small></div></div>${address?`<div class="perception-address"><label for="perception-url-${spec.id}">扩展配置地址</label><div><input id="perception-url-${spec.id}" readonly value="${escapeHTML(address)}" aria-label="${spec.name}配置地址"><button class="button small" data-copy-perception="${spec.id}" title="复制${spec.name}配置地址">${I('copy')}<span>复制地址</span></button></div></div>`:''}<div data-perception-provider="${spec.id}" class="perception-editor">${consoleLoading(`正在读取${spec.name}设置…`)}</div></article>`;
}
/* 感知 = 角色能获取到、并利用的信息。
   组织方式按「从哪来」分组，而不是按后端子类编号：
     身边（地点/天气/历法）→ 对话里（消息/引用/转发/语音/图片/视频）→ 屏幕与设备 → 外部资讯
   每块只保留一个真实落点，空态由该块自己给一句可执行的话，不写「为什么没有控件」。 */
/* 来源索引。四项与下面的四个分区一一对应，顺序也一致。
   它的作用不是装饰：这一页有四个分区、九个开关、两张扩展卡，
   滚到一半时需要一个能跳回去的目录。锚点指向分区的 id，
   分区自己带 scroll-margin-top（见 semantic-page.css），跳过去不会贴顶。 */
const perceptionToc=[
  ['config-environment','calendar-clock','时间与环境'],
  ['config-models','cpu','模型路线'],
  ['config-news','newspaper','外部资讯与检索'],
  ['config-screen','monitor-dot','设备与授权'],
  ['config-recall','message-square-quote','撤回记录'],
  ['config-injection','layers-3','其他注入'],
];
function activatePerceptionTab(destination,{focus=false,scroll=false}={}){
  const [id,subpanelId='']=String(destination).split(':',2);
  const tabs=$$('.perception-config-nav [data-perception-tab]');
  const target=tabs.find(tab=>tab.dataset.perceptionTab===id);
  const panel=document.getElementById(id);
  if(!target||!panel){
    /* 决策页复用感知页的只读上下文流；点击来源时先进入感知页，再定位到设置分区。 */
    if(manageTab==='decision'&&window.CompanionShell?.section==='decision'
      &&perceptionToc.some(([section])=>section===id)){
      navigate('manage','perception');
      requestAnimationFrame(()=>activatePerceptionTab(id,{focus,scroll:true}));
    }
    return;
  }
  const subpanel=subpanelId?document.getElementById(subpanelId):null;
  const anchor=subpanel&&panel.contains?.(subpanel)?subpanel:panel;
  if(subpanel&&anchor===subpanel&&subpanel.tagName==='DETAILS')subpanel.open=true;
  tabs.forEach(tab=>{
    const active=tab===target;
    tab.classList.toggle('active',active);
    tab.setAttribute('aria-selected',String(active));
    tab.tabIndex=active?0:-1;
  });
  $$('[data-perception-panel]').forEach(item=>{
    const active=item===panel;
    item.classList.toggle('active',active);
    item.hidden=!active;
  });
  if(focus)(anchor.querySelector?.('summary')||target).focus();
  if(scroll){
    const reduced=state.reduceMotion||window.matchMedia('(prefers-reduced-motion: reduce)').matches
      ||['low','off'].includes(document.documentElement.dataset.motion);
    anchor.scrollIntoView({behavior:reduced?'instant':'smooth',block:'start'});
  }
  icons();
}
function renderPerceptionOriginal(){
  /* 缺目标时整页一条引导，而不是让四个挂载点各自渲染一遍空态。 */
  const guide = pageNeedsTarget('感知设置');
  if (guide) return `<div class="perception-page">${guide}</div>`;
  const sections = perceptionToc.map(([id,icon,label])=>({id,icon,label}));
  return `<div class="perception-page">
    <div id="perceptionOverviewWorkspace" class="perception-overview-workspace">${consoleLoading('正在读取此刻可用的上下文…')}</div>
    <div class="perception-config-nav" role="tablist" aria-label="感知配置分区">${sections.map(({id,icon,label},index)=>`<button type="button" role="tab" id="perception-tab-${id}" aria-controls="${id}" class="${index===0?'active':''}" data-perception-tab="${id}" aria-selected="${index===0?'true':'false'}" tabindex="${index===0?'0':'-1'}">${I(icon)}<span>${label}</span></button>`).join('')}</div>
    <div class="perception-config-panels">
      <section class="perception-block perception-config-panel active" id="config-environment" role="tabpanel" aria-labelledby="perception-tab-config-environment" tabindex="0" data-perception-panel>
        <div class="perception-block-head">${I('calendar-clock')}<div><span class="perception-section-index">01 / TIME & PLACE</span><h2>时间、日历与环境</h2><p>时间采用角色时区；地点、天气与预警只读取已配置来源。</p></div></div>
        <details class="perception-subpanel" id="perception-detail-place">
          <summary>${I('map-pin')}<span><strong>所在地、天气与预警</strong><small>角色地点、实况来源和气象提醒</small></span>${I('chevron-down')}</summary>
          <div class="perception-subpanel-body">
            <div class="perception-source-status"><div class="perception-source-status-main"><span class="perception-source-status-icon">${I('cloud-sun')}</span><div><strong>和风天气数据源</strong><small>实况天气与官方预警共用一套宿主凭据。</small></div></div><div class="perception-source-status-actions"><span class="perception-source-badge">${I('shield-check')}由宿主管理</span><button class="button small" type="button" data-go="manage" data-manage="host">配置凭据</button></div></div>
            <div id="nativeEnvironmentWorkspace" class="perception-scope">${consoleLoading('正在读取角色环境…')}</div>
          </div>
        </details>
        <details class="perception-subpanel" id="perception-detail-calendar">
          <summary>${I('calendar-days')}<span><strong>本地日期与历法</strong><small>星期、节假日、农历、节气与黄历</small></span>${I('chevron-down')}</summary>
          <div class="perception-subpanel-body"><div id="nativeModelWorkspace" class="perception-scope">${consoleLoading('正在读取日历设置…')}</div></div>
        </details>
        <details class="perception-subpanel" id="perception-detail-important-days">
          <summary>${I('calendar-heart')}<span><strong>重要日子与天气契机</strong><small>生日、纪念日和主动天气提醒</small></span>${I('chevron-down')}</summary>
          <div class="perception-subpanel-body"><div id="perceptionDatesWeatherWorkspace" class="perception-scope">${consoleLoading('正在读取日期与天气设置…')}</div></div>
        </details>
      </section>
      <section class="perception-block perception-config-panel" id="config-models" role="tabpanel" aria-labelledby="perception-tab-config-models" tabindex="0" data-perception-panel hidden>
        <div class="perception-block-head">${I('cpu')}<div><span class="perception-section-index">02 / MODEL ROUTES</span><h2>模型路线</h2><p>对话、语音、生图和视觉任务状态汇总；在模型与连接页编辑实际路由。</p></div></div>
        <details class="perception-subpanel" id="perception-detail-model-route">
          <summary>${I('cpu')}<span><strong>当前任务模型与路由</strong><small>Provider、备用路线和任务参数</small></span>${I('chevron-down')}</summary>
          <div class="perception-subpanel-body"><div id="modelWorkspace" class="console-section" aria-label="任务模型配置">${consoleLoading('正在读取任务模型配置…')}</div><div class="perception-model-route-note"><span>后台任务预算与更多模型维护</span><button class="button small" type="button" data-manage-jump="models">打开完整模型管理 ${I('arrow-up-right')}</button></div></div>
        </details>
      </section>
      <section class="perception-block perception-config-panel" id="config-news" role="tabpanel" aria-labelledby="perception-tab-config-news" tabindex="0" data-perception-panel hidden>
        <div class="perception-block-head">${I('newspaper')}<div><span class="perception-section-index">03 / OUTSIDE SOURCES</span><h2>外部资讯与检索</h2><p>新闻来源、网络探索与外部事件关联使用同一套角色级配置。</p></div></div>
        <details class="perception-subpanel" id="perception-detail-external">
          <summary>${I('globe-2')}<span><strong>资讯来源与网络探索</strong><small>搜索开关、兴趣方向、频率与结果数</small></span>${I('chevron-down')}</summary>
          <div class="perception-subpanel-body"><div id="nativeNewsWorkspace" class="perception-scope">${consoleLoading('正在读取资讯配置…')}</div><div id="perceptionOnlineQueryWorkspace" class="perception-scope">${consoleLoading('正在读取网络探索配置…')}</div></div>
        </details>
      </section>
      <section class="perception-block perception-config-panel" id="config-screen" role="tabpanel" aria-labelledby="perception-tab-config-screen" tabindex="0" data-perception-panel hidden>
        <div class="perception-block-head">${I('monitor-dot')}<div><span class="perception-section-index">04 / DEVICES</span><h2>设备与授权</h2><p>只在获得真实输入与当前会话授权后读取屏幕、定位和摄像头信息。</p></div></div>
        <details class="perception-subpanel" id="perception-detail-device-access">
          <summary>${I('scan-eye')}<span><strong>屏幕、手机与摄像头授权</strong><small>最近输入状态与扩展设置</small></span>${I('chevron-down')}</summary>
          <div class="perception-subpanel-body">
            ${configEditors('screenConfigWorkspace',['screen'],'屏幕解读与日记素材')}
            <section class="perception-access-block" aria-labelledby="perceptionAccessTitle">
              <div class="perception-access-heading"><div><span class="perception-section-index">CONSENT / CURRENT PRIVATE SCOPE</span><h3 id="perceptionAccessTitle">对话能力授权</h3></div><p>屏幕、手机、摄像头、设备动作和回执分别授权。</p></div>
              <div data-screen-access class="reality-consent-workspace"></div>
              <div data-reality-access class="reality-consent-workspace"></div>
            </section>
            <div class="perception-provider-list perception-scope" id="perceptionProviderWorkspace">${perceptionProviders.map(renderPerceptionProvider).join('')}</div>
            <div id="contextImageWorkspace" class="perception-image-context-workspace"></div>
          </div>
        </details>
        <details class="perception-subpanel" id="perception-detail-mihome" hidden>
          <summary>${I('plug-zap')}<span><strong>米家设备状态</strong><small>已配置设备的最近同步状态</small></span>${I('chevron-down')}</summary>
          <div class="perception-subpanel-body"><div id="mihomeStatusWorkspace" class="perception-mihome-workspace" aria-live="polite"></div></div>
        </details>
      </section>
      <section class="perception-block perception-config-panel" id="config-recall" role="tabpanel" aria-labelledby="perception-tab-config-recall" tabindex="0" data-perception-panel hidden>
        <div class="perception-block-head">${I('message-square-quote')}<div><span class="perception-section-index">05 / RECALLS</span><h2>撤回记录</h2><p>仅供当前会话授权管理账号只读查看；撤回内容不会重新进入上下文。</p></div></div>
        <details class="perception-subpanel" id="perception-detail-recalls">
          <summary>${I('message-square-quote')}<span><strong>最近撤回记录</strong><small>受当前窗口授权和时间范围限制</small></span>${I('chevron-down')}</summary>
          <div class="perception-subpanel-body"><div id="perceptionRecallWorkspace" class="perception-recall-workspace" aria-live="polite"></div>${configEditors('recallConfigWorkspace',['recall'],'撤回消息转录')}</div>
        </details>
      </section>
      <section class="perception-block perception-config-panel" id="config-injection" role="tabpanel" aria-labelledby="perception-tab-config-injection" tabindex="0" data-perception-panel hidden>
        <div class="perception-block-head">${I('layers-3')}<div><span class="perception-section-index">06 / CONTEXT MATERIALS</span><h2>其他注入</h2><p>只列出本轮实际提供的其他上下文材料。</p></div></div>
        <details class="perception-subpanel" id="perception-detail-injection">
          <summary>${I('layers-3')}<span><strong>本轮上下文材料</strong><small>按来源列出实际加入的内容</small></span>${I('chevron-down')}</summary>
          <div class="perception-subpanel-body"><div id="perceptionInjectionWorkspace" class="perception-injection-list" aria-live="polite"></div></div>
        </details>
      </section>
    </div>
  </div>`;
}
/* 区块之间的指路行。有些设置按域的归属天然在另一个页里（比如联系节奏
   属于角色状态的 contact 段，控件在主动与联系页）。旧做法是放一张
   boundaryCard 解释「为什么这里没有控件」；现在只放一行入口，
   点过去就是真实控件——用户要的是到得了，不是被告知为什么到不了。 */
/* 「在别处编辑」的跳转行。
 *
 * 去掉了那枚箭头图标：它在每一行都一样，不携带任何信息，只是又一个小方块
 * 占着视线起点。去向靠末尾的按钮表达就够。 */
function settingsJump(label,tab,note=''){
  return `<div class="console-rows"><div class="console-row"><strong>${label}</strong>${button('打开',`data-go="manage" data-manage="${tab}"`,'small')}</div></div>`;
}
/* 配置页的卷首：一句主句 + 一排分区索引。
 *
 * 六个专题页（决策/行动/产出/表达/自我/关系）都是「若干分区 + 若干跳转」，
 * 有的滚过三四屏。原先它们直接以第一个分区开头，用户看不到这一页有哪几块，
 * 也回不到上面那一块。这里给一句主句和一条锚点索引。
 *
 * 索引项由调用方给 [分区 id, 图标, 名称]；分区自己带 scroll-margin-top
 * （见 console.css 的 .console-section），跳过去不会贴顶。
 * 主句只写「这一页管什么」，不写生效时机——时机是各分区自己的事，
 * 放这里会和分区副行重复一遍。 */
function pageLead(title,sentence,entries){
  const toc = entries?.length
    ? `<ul class="console-toc">${entries.map(([id,icon,label])=>
        `<li><a href="#${id}">${I(icon)}<span>${label}</span></a></li>`).join('')}</ul>`
    : '';
  return toc?`<nav class="console-lead" aria-label="分区导航">${toc}</nav>`:'';
}
/* 带卷首的分区列表。
 *
 * 存在的理由是一条**被实测抓到的布局约束**：卷首必须和分区在同一个
 * .console 里，否则两者之间没有可继承的间距——`.console` 是 flex 列，
 * 间距靠它的 gap；而第一个 `.console-section` 又去掉了上分隔线，
 * 于是卷首会紧贴第一个分区标题。当初写成 `pageLead(...) + consoleSections(...)`
 * 两个兄弟节点，看着没问题，实际视觉上挤在一起（冒烟脚本抓出来的）。
 *
 * 所以不让调用点自己拼：把拼接收进这一个函数，形状就不可能写错。
 * 参数与 consoleSections 一致，只是多了一个卷首。 */
function pageSections(title,sentence,sections,toc=[]){
  return `<div class="console">${pageLead(title,sentence,toc)}${consoleSections(sections)}</div>`;
}
/* 决策页。
 *
 * 分区说明只回答两件事：**这里管什么**、**改完什么时候生效**。
 * 早前写的是「…都有读写接口」「…有真实接口」「由各扩展负责」——
 * 那是开发自查语，回答「这块做到哪一步」，用户不关心；而且它和控件
 * 同字号同灰度地压在一起，就是「一坨文字」的主要来源。
 * 需要交代生效时机的，放在末尾一句，不放在开头。 */
function renderDecisionOriginal(){
  if(typeof product.role()?.reply_api!=='string')return pageNeedsTarget('群聊参与');
  return `<div class="decision-configs"><section id="decisionReplyWorkspace" class="decision-reply-workspace" aria-label="群聊回应决策">${consoleLoading('正在连接群聊回应设置…')}</section>
    ${consoleSections([
      ['群聊参与方式','参考群聊氛围，并管理主动插话与跟读。',
        configEditors('groupParticipationConfigWorkspace',['group_participation'],'群聊参与')],
    ])}</div>`;
}
const actionDomains=[
  {id:'together',provider:'together',code:'TOGETHER',icon:'heart-handshake',title:'共处与陪伴',
   summary:'共读、观影、通话与实时活动。',owner:'行动 · 共处与陪伴',destination:'action',destinationLabel:'共处与陪伴',destinationIcon:'heart-handshake'},
  {id:'game',provider:'game',code:'PLAY',icon:'dices',title:'游玩与棋局',
   summary:'棋类、派对与多人游戏。',owner:'主动与联系',destination:'contact',destinationLabel:'邀请与联系节奏',destinationIcon:'heart-handshake'},
  {id:'reality',provider:'reality',code:'REALITY',icon:'radio',title:'现实设备',
   summary:'摄像头、移动端与外部设备。',owner:'感知',destination:'perception',destinationLabel:'设备接入与授权',destinationIcon:'scan-eye'}
];
function actionProviderStatus(id){
  const provider=product.provider(id);
  if(!provider)return {state:Array.isArray(integrationSnapshot?.providers)?'unknown':'loading',label:Array.isArray(integrationSnapshot?.providers)?'目录未返回':'正在读取'};
  const state=provider.integration_state||'unknown';
  return {state,label:product.statusLabel(state)};
}
/* ===== QQ 空间拓展（行动页尾部区块） =====
 *
 * 把 V2 内置的 QQ 空间扩展接进行动页：安装与撤权、凭据与熔断状态、
 * 刷空间（好友动态 / 我的动态）、点赞、回复、发说说，以及这一组的开关与节流设置。
 *
 * 三条规矩写在最前面，后面的改动不要绕过：
 *   1) 三个写动作（点赞 / 回复 / 发布）每次点击都新生成一个 operation_key。
 *      后端把「结果未知」的操作留成 UNKNOWN，同一个 key 重试会被直接拒掉；
 *      换一个 key 才是安全的续做。所以 key 在点击那一刻生成、失败即作废，
 *      页面**从不**自动重发。
 *   2) accepted（已受理）不是完成。界面只显示后端返回的 message
 *      （「…等待 QQ 空间同步」），并把它标成「待同步」；这里不写「已确认 / 成功」。
 *   3) 所有接口文本一律走 escapeHTML。动态引用（post_ref）只留在内存里，
 *      DOM 上只有下标；页面上不出现凭据文件、token，也不出现 uin 原文
 *      ——后端在没有昵称时会退回号段，所以纯数字的作者名按宿主同一口径脱敏。
 */
const QZONE_ROUTE='qzone-extension';
const QZONE_SCOPES=[['friends','好友动态'],['own','我的动态']];
const QZONE_CAPABILITIES=[['qzone.feed.read','读取动态'],['qzone.post.like','点赞'],
  ['qzone.post.comment','回复'],['qzone.post.publish','发说说']];
const QZONE_COMMENT_LIMIT=120;
const QZONE_PUBLISH_LIMIT=300;
/* 日程建议的两个输入上限。结果引用走后端 source_refs 的契约（单条最长 256 字，
   超了整条请求会被判 qzone_request_invalid），所以输入框按同一数字截住；
   日历回执编号按 operation_key 同档取 160。 */
const QZONE_RECEIPT_LIMIT=160;
const QZONE_RESULT_REF_LIMIT=256;
/* 建议只是建议。这句话在每一条建议上原样出现，页面别处也不得改口说日程
   已经被修改——真正的改动发生在生活页（归日历域），这里只记录那次改动的回执。 */
const QZONE_SUGGESTION_NOTE='这只是建议，日程尚未修改；写回日程请在生活页完成，然后把回执编号填回来。';
const QZONE_CREDENTIAL_STATES={ready:'已就绪',failed:'读取失败',manual_failed:'手动凭据不可用',unknown:'尚未使用'};
/* 场景 id 的中文名。它只是**兜底**：真正的目录来自 status 的 catalogue.scenes，
   这里那份只在宿主还没升级、目录里恰好缺某个名字时不至于露出英文 id。 */
const QZONE_SCENE_NAMES={conversation:'对话',external_material:'外部资讯或材料',agenda:'日程与待办',
  role_activity:'角色活动与记录',relationship:'关系与互动',date_marker:'日期与纪念节点',
  free_expression:'自由表达'};
/* 凭据来源只说「从哪来」，不写宿主的文件名——那是实现细节，也提醒不了用户做什么。 */
const QZONE_CREDENTIAL_SOURCES={runtime:'取自当前 Bot 登录',manual:'取自手动放置的凭据',none:'没有可用来源'};
const QZONE_STATUS_REASONS={qzone_not_installed:'还没有安装',qzone_package_changed:'安装的不是内置的那个版本',
  qzone_not_active:'安装被暂停或丢弃了',qzone_role_disabled:'当前角色没有启用',
  qzone_consent_missing:'还没有授权任何能力',qzone_grant_missing:'缺少身份授权'};
/* 本地结果状态。done/replayed/already/used 都是「这一类动作已经做过了」——
 * 后端在动态引用上记了账，同一个引用再点一次必然被拒，所以按钮要停在那里，
 * 而不是让用户点出一个注定失败的请求。 */
const QZONE_OUTCOME_TONES={done:'is-ok',replayed:'is-ok',already:'is-ok',
  accepted:'is-warn',used:'is-warn',unknown:'is-warn',stale:'is-warn'};
const QZONE_OUTCOME_LABELS={like:{done:'已点赞',replayed:'已点赞',already:'此前已赞',accepted:'待同步',
  used:'已提交过',unknown:'结果未知',stale:'引用已失效'},
  comment:{done:'已回复',replayed:'已回复',accepted:'待同步',used:'已提交过',unknown:'结果未知',stale:'引用已失效'},
  publish:{done:'已发布',replayed:'此前已发布',accepted:'待同步',used:'已提交过',unknown:'结果未知',stale:'引用已失效'}};
/* 错误码翻译。本页既有的两份表（product-page.js、contact-page.js）没有这一族码，
 * 所以这里补齐；缺的码退回「需要核对：<码>」，与 contact-page 的 reason() 同口径。 */
const QZONE_ERRORS={
  qzone_not_installed:'QQ 空间扩展还没有安装。',
  qzone_package_changed:'安装的扩展包与内置版本不一致，需要先恢复内置版本。',
  qzone_not_active:'这个扩展已被暂停或丢弃，请先在能力目录里恢复。',
  qzone_role_disabled:'当前角色没有启用 QQ 空间。',
  qzone_consent_missing:'这个对象还没有授权任何 QQ 空间能力。',
  qzone_grant_missing:'当前对象缺少 QQ 空间的身份授权。',
  qzone_access_changed:'安装设置已经变化，已重新读取，请再操作一次。',
  capability_operation_unresolved:'上一次安装操作的结果还没有确认，请先核对当前状态。',
  qzone_private_required:'QQ 空间只能在私聊对象下管理。',
  qzone_unavailable:'宿主还没有可用的 QQ 空间通道。',
  qzone_disabled:'QQ 空间总开关是关的。',
  qzone_auth_blocked:'QQ 空间登录状态异常，已自动暂停：请刷新凭据后再试。',
  qzone_action_blocked:'这次动作被挡住了：可能是对应开关没开、距离上次同类动作不到间隔，或今天的额度已经用完。',
  qzone_credential_missing:'没有读到 QQ 空间的登录凭据：请先在这个 Bot 账号上登录，或放置凭据后点「刷新凭据」。',
  qzone_credential_invalid:'QQ 空间的登录凭据无效，请重新获取后点「刷新凭据」。',
  qzone_request_invalid:'这次请求的内容不被接受，请核对后重试。',
  qzone_text_invalid:'正文不符合要求，请缩短后重试。',
  qzone_scope_invalid:'刷空间只能选好友动态或我的动态。',
  qzone_post_ref_invalid:'这条动态的引用已经失效。',
  qzone_post_ref_stale:'刷空间拿到的引用已经过期，请重新刷空间。',
  qzone_post_already_done:'这条动态已经做过同类操作。',
  qzone_delivery_unknown:'结果未知：请求已经发出但没有收到确认，页面不会自动重发。请先到 QQ 空间核对实际结果，再决定要不要用新的操作重试。',
  qzone_operation_unresolved:'上一次同类操作的结果还没有确认，请先到 QQ 空间核对再重试。',
  qzone_operation_failed:'QQ 空间拒绝了这次操作。',
  qzone_response_invalid:'QQ 空间的返回无法解析。',
  qzone_configuration_invalid:'QQ 空间的设置不合法。',
  /* 主题与场景的判定：发布接口现在必须带主题判定，这一族码说的是
     「哪一步没满足」，所以每条都要指出下一步怎么做，而不是一句「被拒了」。 */
  qzone_topic_required:'发布前必须先确定主题：在「发说说」里选一个主题再发。',
  qzone_scene_required:'必须先确定发送场景：在「发说说」里选一个场景再发。',
  qzone_topic_invalid:'主题不在可用目录中：请重新读取状态，再从下拉里选一个主题。',
  qzone_scene_invalid:'主题或场景不在目录中（也可能是这个场景不适合所选主题）：请重新选择主题与场景。',
  qzone_topic_disabled:'该主题未开启：请在下面的「QQ 空间设置」里打开这个主题，或换一个主题。',
  qzone_topic_not_allowed:'该场景没有在这个主题的设置里放行：请改这个主题的「允许的场景」，或换一个场景。',
  qzone_topic_confidence_invalid:'主题判定的置信度不是 0 到 1 之间的数字，这次没有发布。',
  qzone_topic_confidence_low:'置信度不足：没有达到该主题的置信度门槛，这次没有发布。',
  qzone_topic_confirmation_required:'需要确认主题与场景：请核对下拉里的选择后再发一次。',
  qzone_topic_daily_limit:'该主题今日额度已用完：今天换一个主题，或明天再发。',
  qzone_topic_cooldown:'该主题还在冷却中：还没到该主题的最短间隔，请过一会儿再发。',
  /* 日程建议的闭环。这几条码说的是「哪一步没满足」：标记已写回要能对上
     日历域那次改动（回执编号），忽略不需要；另外两条说明这条建议已经不在
     待处理列表里了，重读一次状态即可。 */
  qzone_suggestion_receipt_required:'标记已写回时必须带上日历回执编号：请先在生活页完成日程修改，再把那次改动给出的回执编号填回来。',
  qzone_suggestion_unavailable:'这条日程建议不存在，或已经不属于当前角色：请点「重新读取」核对当前列表。',
  qzone_suggestion_state_invalid:'日程建议只能标记为已写回或已忽略，没有第三种处理方式。',
  bridge_timeout:'等待超时，没有收到结果。结果未知，页面不会自动重发；请先刷新状态并到 QQ 空间核对。',
  bridge_unavailable:'页面还没有接上 AstrBot，请刷新后重试。',
  invalid_response:'服务返回的数据不完整，请刷新核对。',
  dashboard_identity_required:'请从已登录的 AstrBot 管理界面打开陪伴小屋。',
  core_access_required:'当前账号没有管理权限。',
  staging_not_initialized:'V2 数据还没有加载，请先在账号与会话里加载运行实例。',
  staging_host_terminated:'插件已停止，重新打开插件页面即可恢复。',
};
/* 状态放在模块级：行动页的 DOM 每次渲染整块重写（面板 innerHTML），
 * 挂在节点上的状态会在切分区时丢掉。 */
const qzoneState={phase:'idle',status:null,feeds:{},scope:'friends',notice:null,
  busy:false,acting:null,loadedAt:0,replyFor:-1,replyDraft:'',replyDraftFor:-1,publishDraft:'',
  /* 发说说的主题与场景由人在界面上选，所以它们和草稿一样留在模块级状态里：
     动作结束后整块重画，选择不该跟着丢。目录本身不缓存——每份都从最近一次
     status 里取，宿主换了目录（升级、改配置）下次读取就会跟上。 */
  publishTopic:'',publishScene:'',confirmDisable:false,
  /* 日程建议的处理态。回执框一次只开在一条建议上，输入留在这里而不是留在
     节点上——动作结束后整块重画，重画时填了一半的回执不该跟着丢。
     confirmSuggestionFor 与它互斥：同一条建议上不会同时开着回执框和忽略确认。 */
  suggestionReceiptFor:'',suggestionReceiptDraft:'',suggestionResultRefDraft:'',
  suggestionConfirmFor:''};
function qzoneStatus(){const status=qzoneState.status;return status&&typeof status==='object'?status:null;}
function qzoneSettings(){
  const runtime=qzoneStatus()?.runtime;
  const settings=runtime&&typeof runtime==='object'?runtime.settings:null;
  return settings&&typeof settings==='object'?settings:{};
}
function qzoneUsable(status){
  return Boolean(status)&&status.installed===true&&status.active===true&&status.role_enabled===true;
}
/* 主题与场景的目录来自 status 的 catalogue，**不写死在页面里**：
 * 后端才是那份目录的持有者（主题、场景、每个主题放行哪些场景都随配置变），
 * 页面抄一份就会在升级后与后端对不上，而那种错的表现是「发布时被拒」。
 *
 * 读不到、或形状不对时返回 null。调用方必须把 null 当成「不能发布」并把原因
 * 说出来——**不要**退回空数组：那会渲染出一个没有选项的下拉和一个永远点不动
 * 的按钮，看起来像页面坏了，而不是像目录没读到。 */
function qzoneCatalogue(){
  const raw=qzoneStatus()?.catalogue;
  if(!raw||typeof raw!=='object'||Array.isArray(raw))return null;
  const topics=(Array.isArray(raw.topics)?raw.topics:[]).map(item=>{
    if(!item||typeof item!=='object')return null;
    const id=typeof item.id==='string'?item.id.trim():'';
    if(!id)return null;
    const scenes=(Array.isArray(item.scenes)?item.scenes:[])
      .map(scene=>String(scene).trim()).filter(Boolean);
    return {id,label:typeof item.label==='string'&&item.label.trim()?item.label:(QZONE_SCENE_NAMES[id]||id),
      scenes:[...new Set(scenes)]};
  }).filter(Boolean);
  const known=new Set(topics.map(topic=>topic.id));
  /* 主题 id 不能重复：重复会让「当前选的是哪一个」按第一份解释，选了什么说不清。 */
  if(!topics.length||known.size!==topics.length)return null;
  const scenes={};
  const source=raw.scenes&&typeof raw.scenes==='object'&&!Array.isArray(raw.scenes)?raw.scenes:{};
  /* 目录里缺某个场景名字时留空串，渲染时逐条退回页面那份兜底名：
     缺名字是显示问题，不该让整份目录作废，也不该把 id 当名字显示给用户。 */
  for(const [key,value] of Object.entries(source))
    scenes[String(key)]=typeof value==='string'?value:'';
  return {topics,scenes};
}
function qzoneSceneName(scene){
  if(!scene)return '未选';
  return qzoneCatalogue()?.scenes?.[scene]||QZONE_SCENE_NAMES[scene]||scene;
}
function qzoneTopicTopics(){
  return qzoneCatalogue()?.topics||[];
}
function qzoneTopic(){
  const id=qzoneState.publishTopic;
  return qzoneTopicTopics().find(topic=>topic.id===id)||null;
}
/* 某个主题放行的场景。目录里写的是 id，这里顺带把中文名取出来给下拉用。 */
function qzoneTopicScenes(topic){
  if(!topic)return [];
  const names=qzoneCatalogue()?.scenes||{};
  return topic.scenes.map(id=>({id,label:names[id]||QZONE_SCENE_NAMES[id]||id}));
}
/* 选择与目录对齐。宿主换了目录、或刚读完状态之后都要走这里：
 * 主题不在了就落到第一个；场景不属于当前主题时**自动选第一个**——
 * 「清空」会让下拉显示一个没选中的空态，用户得再点一次才知道缺什么。 */
function qzoneSyncPublishSelection(){
  const topics=qzoneTopicTopics();
  if(!topics.length){qzoneState.publishTopic='';qzoneState.publishScene='';return;}
  let topic=topics.find(item=>item.id===qzoneState.publishTopic);
  if(!topic&&topics.length===1)topic=topics[0];
  qzoneState.publishTopic=topic?topic.id:'';
  const scenes=topic?topic.scenes:[];
  qzoneState.publishScene=scenes.includes(qzoneState.publishScene)?qzoneState.publishScene:(scenes[0]||'');
}
/* 路由与同页的 integration/manifest、page/targets 同口径：插件相对路径，不带插件目录名。
 * 多目标模式下这一族路由挂在 targets/<id>/roles/<digest>/ 下并由目录下发
 * qzone_extension_api；目录里给了就用目录给的那条，没给（当前公开目录还没有这一项）
 * 就退回固定的这一条——单目标模式的真实路由正是它。 */
function qzoneRoute(suffix){
  const fromDirectory=product.role()?.qzone_extension_api;
  let base=null;
  if(typeof fromDirectory==='string'&&fromDirectory.startsWith('/')){
    try{base=product.relative(fromDirectory);}catch{base=null;}
  }
  return `${base||QZONE_ROUTE}/${suffix}`;
}
/* 走本页既有的桥接助手（product.request＝product-page.js 的 api()）：
 * 同一套信封解包、15 秒上限与错误码翻译，不在这里另写一份。 */
async function qzoneRequest(method,suffix,body){
  if(!product.bridgeNow())await product.bridgeFor();
  return await product.request(method,qzoneRoute(suffix),body);
}
/* 请求一律不抛：调用方拿到 {ok,data,error,text} 再决定说什么、画什么。 */
async function qzoneFetch(method,suffix,body,write){
  try{return {ok:true,data:await qzoneRequest(method,suffix,body)};}
  catch(error){
    if(!error?.code)console.warn('[陪伴小屋] QQ 空间请求失败',error);
    return {ok:false,error,text:qzoneFailureText(error,Boolean(write))};
  }
}
/* 失败要说清「有没有发出去」。读失败可以放心重试；写失败里「结果未知」
 * 和「超时」都不能说成功，也不能自动重发。 */
function qzoneFailureText(error,write){
  const code=typeof error?.code==='string'?error.code:'';
  if(write&&(code==='bridge_timeout'||code==='qzone_delivery_unknown'))return QZONE_ERRORS.qzone_delivery_unknown;
  if(code==='bridge_timeout')return '读取超时，没有拿到结果；可以重新读取。';
  if(code&&QZONE_ERRORS[code])return QZONE_ERRORS[code];
  if(!code)return write?'这次操作没有完成：没有收到明确结果，页面不会自动重发，请刷新状态后核对。'
    :'读取失败，请重新读取。';
  return '需要核对：'+code;
}
/* 一次写失败之后，这条动态还能不能再点。空串＝可以重试（什么都没发出去）。 */
function qzoneFailureState(error){
  const code=typeof error?.code==='string'?error.code:'';
  if(code==='qzone_delivery_unknown'||code==='bridge_timeout')return 'unknown';
  if(code==='qzone_post_ref_stale'||code==='qzone_post_ref_invalid')return 'stale';
  if(code==='qzone_post_already_done')return 'used';
  return '';
}
function qzoneOutcome(status,verified){
  if(status==='accepted')return 'accepted';
  if(status==='already')return 'already';
  if(status==='replayed')return 'replayed';
  if(status==='done')return verified===false?'accepted':'done';
  return 'unknown';
}
function qzoneOutcomeLabel(kind,state){
  const table=QZONE_OUTCOME_LABELS[kind]||QZONE_OUTCOME_LABELS.like;
  return table[state]||'';
}
function qzoneActing(action,index){
  const acting=qzoneState.acting;
  if(!acting)return false;
  if(typeof acting==='string')return acting===action;
  return acting.action===action&&(index===undefined||acting.index===index);
}
/* 一个动作现在能不能点，以及不能点是因为什么。判断顺序就是后端的顺序
 * （总开关 → 熔断 → 这一项开关），所以界面上那句话就是用户会遇到的那句话。 */
function qzoneGate(kind){
  const status=qzoneStatus();
  if(!status)return {ok:false,reason:'还没有读到 QQ 空间的当前状态。'};
  const runtime=status.runtime&&typeof status.runtime==='object'?status.runtime:null;
  const settings=runtime?.settings&&typeof runtime.settings==='object'?runtime.settings:{};
  if(!Object.keys(settings).length){
    return {ok:false,reason:runtime?.settings_error?`设置读取失败：${runtime.settings_error}`
      :'宿主还没有给出 QQ 空间的运行设置。'};
  }
  const blocked=typeof runtime?.blocked_reason==='string'?runtime.blocked_reason.trim():'';
  if(blocked)return {ok:false,reason:`登录状态异常，已自动暂停：${blocked}`};
  if(!settings.enabled)return {ok:false,reason:'QQ 空间总开关是关的，先在下面的「QQ 空间设置」里打开。'};
  if(kind==='like'&&!settings.like_enabled)return {ok:false,reason:'点赞开关是关的。'};
  if(kind==='comment'&&!settings.comment_enabled)return {ok:false,reason:'回复开关是关的。'};
  if(kind==='publish'&&!settings.publish_enabled)return {ok:false,reason:'发说说开关是关的。'};
  return {ok:true,reason:''};
}
function qzoneNotice(text,error=false){
  qzoneState.notice=text?{text:String(text),error:Boolean(error)}:null;
  if(text)toast(String(text));
}
/* 作者的展示名。后端在平台没给昵称时会退回账号号段，所以纯数字的
 * 「昵称」按宿主 _mask_uin 的口径脱敏（留首末，中间打星），不漏 uin 原文。 */
function qzoneAuthor(value){
  const text=String(value??'').trim();
  if(!text)return '空间用户';
  if(!/^\d{5,12}$/.test(text))return text;
  if(text.length<=4)return '*'.repeat(text.length);
  return `${text.slice(0,1)}${'*'.repeat(text.length-3)}${text.slice(-2)}`;
}
function qzoneClock(ms){
  if(!Number.isFinite(ms))return '';
  try{return new Date(ms).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});}
  catch{return '';}
}
/* 动态时间：可能是 ISO、秒级或毫秒级时间戳、平台自己的 14 位串，
 * 也可能已经是给人看的展示串。认不出来的照原样显示，不编一个时间。 */
function qzoneWhen(value){
  const text=String(value??'').trim();
  if(!text)return '';
  if(/^\d{9,10}$/.test(text))return qzoneClock(Number(text)*1000);
  if(/^\d{13}$/.test(text))return qzoneClock(Number(text));
  if(/^\d{14}$/.test(text)){
    const parsed=Date.parse(`${text.slice(0,4)}-${text.slice(4,6)}-${text.slice(6,8)}T`
      +`${text.slice(8,10)}:${text.slice(10,12)}:${text.slice(12,14)}+08:00`);
    return Number.isFinite(parsed)?qzoneClock(parsed):'';
  }
  const parsed=Date.parse(text);
  if(Number.isFinite(parsed))return qzoneClock(parsed);
  return text.length>24?`${text.slice(0,24)}…`:text;
}
function qzoneFeed(){
  const feed=qzoneState.feeds[qzoneState.scope];
  return feed&&Array.isArray(feed.items)?feed:null;
}
function qzoneFeedItem(index){
  const feed=qzoneFeed();
  return feed&&Number.isInteger(index)&&index>=0&&index<feed.items.length?feed.items[index]:null;
}
/* 待确认的日程建议：来自 status.runtime.agenda_suggestions，后端最多给 5 条。
 *
 * 只认 state === 'pending' 的记录，形状不对的整条丢掉：缺 suggestion_id 的条目
 * 点了也发不出请求，而一条永远点不动的卡片看起来像页面坏了——宁可不显示它。
 * 这些记录**不代表任何日程改动**，它们只是角色提出、还没闭合的问题。 */
function qzoneSuggestionList(){
  const raw=qzoneStatus()?.runtime?.agenda_suggestions;
  if(!Array.isArray(raw))return [];
  return raw.filter(item=>item&&typeof item==='object'&&!Array.isArray(item)
    &&item.state==='pending'&&typeof item.suggestion_id==='string'&&item.suggestion_id.trim());
}
function qzoneSuggestion(id){
  return qzoneSuggestionList().find(item=>item.suggestion_id===id)||null;
}
/* 闭合成功后把这一条从本地状态里摘掉。刷新状态是另一次请求，它可能失败；
   已经确认闭合的那一条不该等第二次请求才从界面上消失。 */
function qzoneDropSuggestion(id){
  const runtime=qzoneStatus()?.runtime;
  if(!runtime||!Array.isArray(runtime.agenda_suggestions))return;
  runtime.agenda_suggestions=runtime.agenda_suggestions
    .filter(item=>!(item&&typeof item==='object'&&item.suggestion_id===id));
}
function qzoneApplyStatus(data){
  if(!data||typeof data!=='object'||Array.isArray(data)||typeof data.installed!=='boolean'){
    qzoneNotice('服务返回的数据不完整，请刷新核对。',true);
    return false;
  }
  qzoneState.status=data;
  qzoneState.phase='ready';
  qzoneState.loadedAt=Date.now();
  /* 目录跟着状态一起换，所以选择也在这里对齐一次：上一轮选的主题可能已经
     被关掉或从目录里消失，留着它会让「发布」按钮面对一个后端不认的主题。 */
  qzoneSyncPublishSelection();
  return true;
}
/* 读一次状态。重画由调用方（qzoneRun 的 finally / mountQzoneSection）负责，
 * busyPaint 只在「用户明确点了重新读取」时先画一次在途态。 */
async function qzoneLoadStatus({busyPaint=false}={}){
  if(busyPaint){qzoneState.phase=qzoneState.status?'ready':'loading';paintQzone();}
  const result=await qzoneFetch('GET','status',undefined,false);
  if(!result.ok){
    qzoneState.phase=qzoneState.status?'ready':'error';
    qzoneNotice(result.text,true);
    return false;
  }
  if(!qzoneApplyStatus(result.data)){qzoneState.phase='error';return false;}
  return true;
}
/* 一次操作的统一外壳：在途期间整块按钮禁用（qzoneState.busy 参与渲染），
 * 结束时无论成败都重画一次。work 只负责「发请求 + 改状态」，不碰 DOM——
 * 重画是唯一的出口，这样界面永远等于状态。 */
async function qzoneRun(acting,work){
  if(qzoneState.busy)return;
  qzoneState.busy=true;
  qzoneState.acting=acting;
  paintQzone();
  try{await work();}
  catch(error){
    console.warn('[陪伴小屋] QQ 空间操作失败',error);
    qzoneNotice(qzoneFailureText(error,false),true);
  }
  finally{qzoneState.busy=false;qzoneState.acting=null;paintQzone();}
}
/* 点火即忘的入口。请求本身的失败已经被 qzoneRun 变成一句提示，这里再兜一层
 * 是为了「重画时抛出的意外」——面板挂载链上任何一次未捕获的异常都会变成
 * 一个没人处理的 promise，而那一层错误（与 guarded 同样的理由）要留在控制台。 */
function qzoneStart(acting,work){
  const run=qzoneRun(acting,work);
  if(run&&typeof run.catch==='function'){
    run.catch(error=>console.warn('[陪伴小屋] QQ 空间区块未能重画',error));
  }
}
async function qzoneScan(scope){
  const result=await qzoneFetch('GET','feed',{scope,limit:10,detail:0},false);
  if(!result.ok){qzoneNotice(result.text,true);return;}
  const data=result.data&&typeof result.data==='object'?result.data:{};
  const items=(Array.isArray(data.items)?data.items:[])
    .filter(item=>item&&typeof item==='object')
    /* 每次刷空间都是新的引用：本地结果状态跟着新的一批一起重置。 */
    .map(item=>({...item,likeState:'',commentState:''}));
  qzoneState.feeds[scope]={scope:typeof data.scope==='string'?data.scope:scope,items,scannedAt:Date.now()};
  qzoneState.scope=scope;
  qzoneState.replyFor=-1;
  /* 新一批引用意味着旧的回复框已经不属于任何一条动态：解除关联，
     下次打开时它会重新开一个空的。 */
  qzoneState.replyDraftFor=-1;
  qzoneNotice(items.length?`读到 ${items.length} 条动态。`:'这次没有读到动态。',false);
}
async function qzoneLike(index){
  const item=qzoneFeedItem(index);
  if(!item)return;
  const result=await qzoneFetch('POST','like',
    {operation_key:crypto.randomUUID(),post_ref:item.post_ref},true);
  if(!result.ok){
    const state=qzoneFailureState(result.error);
    if(state)item.likeState=state;
    qzoneNotice(result.text,true);
    return;
  }
  const data=result.data&&typeof result.data==='object'?result.data:{};
  const outcome=qzoneOutcome(data.status,data.verified);
  item.likeState=outcome;
  /* 只有「已确认」这一类才把已赞标记点亮；accepted 只是受理，尚未同步。 */
  if(['done','already','replayed'].includes(outcome))item.liked=true;
  qzoneNotice(typeof data.message==='string'&&data.message.trim()?data.message:qzoneOutcomeLabel('like',outcome),false);
}
async function qzoneComment(index){
  const item=qzoneFeedItem(index);
  if(!item)return;
  const text=qzoneState.replyDraft.trim();
  if(!text){qzoneNotice('回复正文是空的，没有发送。',true);return;}
  if(text.length>QZONE_COMMENT_LIMIT){qzoneNotice(`回复最多 ${QZONE_COMMENT_LIMIT} 字，这条没有发送。`,true);return;}
  const result=await qzoneFetch('POST','comment',
    {operation_key:crypto.randomUUID(),post_ref:item.post_ref,text},true);
  if(!result.ok){
    const state=qzoneFailureState(result.error);
    if(state)item.commentState=state;
    qzoneNotice(result.text,true);
    return;
  }
  const data=result.data&&typeof result.data==='object'?result.data:{};
  const outcome=qzoneOutcome(data.status,data.verified);
  item.commentState=outcome;
  qzoneState.replyFor=-1;
  qzoneState.replyDraft='';
  qzoneState.replyDraftFor=-1;
  qzoneNotice(typeof data.message==='string'&&data.message.trim()?data.message:qzoneOutcomeLabel('comment',outcome),false);
}
/* 日程提案只是**待确认的建议**，不是日程变更。后端把它随结果一起带回来时，
 * 结果提示里必须把这一点说出来：说成「已改日程」就是把一个未确认的提案
 * 说成了既成事实，而用户可能正是照着这句话来判断要不要去核对日程的。
 *
 * 只认 status === 'pending_confirmation' 的提案：别的取值（后端约定里目前
 * 只有这一种，将来若加「已确认」）不能拿这句话去说，宁可不提。 */
function qzoneAgendaNote(data){
  const proposal=data?.agenda_proposal;
  if(!proposal||typeof proposal!=='object'||Array.isArray(proposal))return '';
  const status=typeof proposal.status==='string'?proposal.status:'pending_confirmation';
  if(status!=='pending_confirmation')return '';
  return '这次还带回了一条日程提案，它仍待确认，尚未修改日程。';
}
async function qzonePublish(){
  const text=qzoneState.publishDraft.trim();
  if(!text){qzoneNotice('说说正文是空的，没有发布。',true);return;}
  if(text.length>QZONE_PUBLISH_LIMIT){qzoneNotice(`说说最多 ${QZONE_PUBLISH_LIMIT} 字，这条没有发布。`,true);return;}
  /* 发布接口现在必须带主题判定。没读完目录就别说「你还没选」——
     那是两回事：目录没读到是页面的问题，选没选是用户的操作。 */
  const catalogue=qzoneCatalogue();
  if(!catalogue){qzoneNotice('没有读到主题与场景目录，这次没有发布：请先点「重新读取」。',true);return;}
  const topic=qzoneState.publishTopic;
  const scene=qzoneState.publishScene;
  if(!topic){qzoneNotice(QZONE_ERRORS.qzone_topic_required,true);return;}
  if(!scene){qzoneNotice(QZONE_ERRORS.qzone_scene_required,true);return;}
  /* 人手选择就是明确判断，所以 topic_confirmed 送 true、confidence 送 1：
     界面上的选择比模型的置信度更强，而置信度门槛约束的是自动判定那一路。
     evidence_refs 留空——页面上的正文是人写的，没有「材料引用」可按。 */
  const result=await qzoneFetch('POST','publish',{operation_key:crypto.randomUUID(),text,
    topic,scene,confidence:1,topic_confirmed:true},true);
  if(!result.ok){
    /* 失败（包括结果未知）都把正文留着：要不要用新的操作重发由用户决定。 */
    qzoneNotice(result.text,true);
    return;
  }
  const data=result.data&&typeof result.data==='object'?result.data:{};
  const outcome=qzoneOutcome(data.status,data.verified);
  if(['done','accepted','replayed'].includes(outcome)){
    qzoneState.publishDraft='';
    /* 发布与受理都会推进当日计数：把状态重读一次，让上限显示对得上。
       顺序要紧——重读失败会写一条错误提示，而这条说说到底有没有发出去
       是屏幕上更重要的一句话，所以它在最后说，不被重读盖掉。 */
    await qzoneLoadStatus();
  }
  const base=typeof data.message==='string'&&data.message.trim()?data.message:qzoneOutcomeLabel('publish',outcome);
  const note=qzoneAgendaNote(data);
  qzoneNotice(note?`${base} ${note}`:base,false);
}
/* 闭合一条待确认的日程建议：applied（已写回）或 dismissed（忽略）。
 *
 * 这里**不写日程**。日程改动在生活页（日历域）完成，页面只把那次改动的日历
 * 回执编号记在这条建议上；标 applied 时后端要求编号非空（否则回
 * qzone_suggestion_receipt_required），所以空编号在本地就挡下——那不是一个
 * 「失败」，是一个不该发出去的请求。
 *
 * operation_key 每次点击新生成：结果未知时后端把这条记成 UNKNOWN，同一个 key
 * 重发会被直接拒掉，换新 key 才是安全的续做，而重发与否由用户决定——页面
 * 从不自动重试。 */
async function qzoneResolveSuggestion(id,suggestionState){
  if(!qzoneSuggestion(id)){
    qzoneNotice(QZONE_ERRORS.qzone_suggestion_unavailable,true);
    return;
  }
  const body={operation_key:crypto.randomUUID(),suggestion_id:id,state:suggestionState};
  const applied=suggestionState==='applied';
  if(applied){
    const receipt=qzoneState.suggestionReceiptDraft.trim();
    if(!receipt){qzoneNotice(QZONE_ERRORS.qzone_suggestion_receipt_required,true);return;}
    body.calendar_operation_id=receipt;
    const ref=qzoneState.suggestionResultRefDraft.trim();
    /* 结果引用是可选的第二条线索，空就不送这个字段（后端按 source_refs 校验，
       空串会被判格式无效——那等于把一个「没填」说成了「填错了」）。 */
    if(ref)body.result_refs=[ref];
  }
  const result=await qzoneFetch('POST','agenda-suggestions/resolve',body,true);
  if(!result.ok){
    qzoneNotice(result.text,true);
    /* 失败（含结果未知）把回执框与填了一半的内容都留着：要不要用新的操作
       再试一次由用户决定。焦点放回去，省得重新点一遍。 */
    if(applied)requestAnimationFrame(()=>document.querySelector('#actionQzoneBody [data-qzone-receipt]')?.focus());
    return;
  }
  /* replayed 也是「这条已经记下了」：本次点击永远用新 key，真拿到重放回执
     说明后端答的是第一次的处理结果，同样按成功收尾，不编第二句话。 */
  qzoneDropSuggestion(id);
  if(qzoneState.suggestionReceiptFor===id)qzoneState.suggestionReceiptFor='';
  if(qzoneState.suggestionConfirmFor===id)qzoneState.suggestionConfirmFor='';
  qzoneState.suggestionReceiptDraft='';
  qzoneState.suggestionResultRefDraft='';
  /* 顺序要紧：重读失败会写一条错误提示，而「回执已经记下」是屏幕上更重要
     的一句话，所以它在最后说，不被重读盖掉（与发布同一条纪律）。 */
  await qzoneLoadStatus();
  qzoneNotice(applied?'已记录写回回执。':'已忽略这条日程建议。',false);
}
async function qzoneRefreshCredentials(){
  const result=await qzoneFetch('POST','refresh-credentials',{},false);
  if(!result.ok){qzoneNotice(result.text,true);return;}
  if(qzoneApplyStatus(result.data)){qzoneNotice('凭据状态已刷新。',false);return;}
  await qzoneLoadStatus();
}
async function qzoneConfigure(enabled){
  const token=typeof qzoneStatus()?.edit_token==='string'?qzoneStatus().edit_token:'';
  if(!token){qzoneNotice('没有读到可用的安装令牌，请先重新读取状态。',true);return;}
  /* edit_token 必须是最近一次 status 返回的那一个；configure 的 body
   * 只允许 operation_key / edit_token / enabled 三个字段（后端按集合判等）。 */
  const result=await qzoneFetch('POST','configure',
    {operation_key:crypto.randomUUID(),edit_token:token,enabled},false);
  if(!result.ok){
    qzoneNotice(result.text,true);
    /* 令牌过期时先把状态读回来，下一次点击用的就是新的令牌。 */
    if(result.error?.code==='qzone_access_changed')await qzoneLoadStatus();
    return;
  }
  const data=result.data&&typeof result.data==='object'?result.data:{};
  const applied=qzoneApplyStatus(data.status);
  if(!applied)await qzoneLoadStatus();
  qzoneNotice(enabled?'QQ 空间已安装并启用。':'QQ 空间已停用：这个对象不再接入空间动态。',false);
  if(!enabled){
    qzoneState.feeds={};
    qzoneState.replyFor=-1;
    qzoneState.replyDraftFor=-1;
    qzoneState.confirmDisable=false;
  }
}
function qzoneNoticeMarkup(){
  const notice=qzoneState.notice;
  if(!notice?.text)return '';
  return `<p class="action-qzone-notice ${notice.error?'is-error':'is-done'}" role="status">`
    +`${I(notice.error?'circle-alert':'info')}<span>${escapeHTML(notice.text)}</span></p>`;
}
function qzoneBlockedMarkup(){
  const runtime=qzoneStatus()?.runtime;
  const blocked=typeof runtime?.blocked_reason==='string'?runtime.blocked_reason.trim():'';
  if(!blocked)return '';
  return `<p class="action-qzone-alert" role="alert">${I('triangle-alert')}`
    +`<span><strong>QQ 空间已自动暂停</strong>${escapeHTML(blocked)}</span></p>`;
}
function qzoneCredentialMarkup(credential){
  const row=credential&&typeof credential==='object'?credential:{};
  const state=typeof row.state==='string'?row.state:'unknown';
  const source=typeof row.source==='string'?row.source:'none';
  const masked=typeof row.uin_masked==='string'?row.uin_masked:'';
  const reason=typeof row.reason==='string'?row.reason.trim():'';
  const tone=state==='ready'?'is-ok':state==='unknown'?'is-off':'is-warn';
  return `<div class="action-qzone-status-row">
    <span class="action-qzone-status-label">凭据</span>
    <span class="action-qzone-status-value"><span class="action-qzone-chip ${tone}">${escapeHTML(QZONE_CREDENTIAL_STATES[state]||'状态未知')}</span>`
    +`<span>${escapeHTML(QZONE_CREDENTIAL_SOURCES[source]||'来源未知')}</span>`
    +`${masked?`<span>账号 ${escapeHTML(masked)}</span>`:''}`
    +`${reason?`<span class="action-qzone-reason">${escapeHTML(reason)}</span>`:''}</span>
    <button class="button small" type="button" data-qzone-action="refresh-credentials" ${qzoneState.busy?'disabled':''}>${I('key-round')}<span>刷新凭据</span></button>
  </div>`;
}
function qzoneConsentMarkup(status){
  const consented=status.consented&&typeof status.consented==='object'?status.consented:{};
  const granted=QZONE_CAPABILITIES.filter(([id])=>consented[id]===true);
  const flags=[['已安装',status.installed===true],['包版本一致',status.active===true],
    ['角色已启用',status.role_enabled===true],['身份授权',status.invoke_granted===true]];
  return `<div class="action-qzone-status-row">
    <span class="action-qzone-status-label">授权</span>
    <span class="action-qzone-status-value">${flags.map(([label,on])=>
      `<span class="action-qzone-chip ${on?'is-ok':'is-off'}">${label}</span>`).join('')}`
    +`<span>能力 ${granted.length} / ${QZONE_CAPABILITIES.length}`
    +`${granted.length?`（${escapeHTML(granted.map(([,name])=>name).join('、'))}）`:''}</span></span>
    <button class="button small" type="button" data-qzone-action="refresh-status" ${qzoneState.busy?'disabled':''}>${I('refresh-cw')}<span>重新读取</span></button>
  </div>`;
}
function qzoneSwitchMarkup(settings){
  /* 设置读不出来时（宿主还没给运行设置）这一行整块不渲染：
     一个只有标签、没有内容的空行比没有这一行更像坏了。 */
  if(!Object.keys(settings).length)return '';
  const rows=[['总开关','enabled'],['点赞','like_enabled'],['回复','comment_enabled'],['发说说','publish_enabled']];
  return `<div class="action-qzone-status-row">
    <span class="action-qzone-status-label">能力开关</span>
    <span class="action-qzone-status-value">${rows.map(([label,key])=>
      `<span class="action-qzone-chip ${settings[key]===true?'is-ok':'is-off'}">${label} · ${settings[key]===true?'开':'关'}</span>`).join('')}</span>
  </div>`;
}
function qzoneLimitsMarkup(settings){
  const parts=[['每次读取动态',settings.feed_recent_posts,'条'],
    ['同类动作最短间隔',settings.action_min_interval_minutes,'分钟'],
    ['每轮最多动作',settings.max_actions_per_tick,'个'],
    ['每日最多说说',settings.publish_max_daily,'条']].filter(([,value])=>Number.isFinite(value));
  if(!parts.length)return '';
  return `<p class="action-qzone-limits">${I('clock-3')}<span>`
    +`${parts.map(([label,value,unit])=>`${label} ${escapeHTML(String(value))} ${unit}`).join(' · ')}</span></p>`;
}
/* 主题策略：说清「谁在决定主题」，以及目录里有几个主题是开着的。
 * 措辞不能暗示「已经在自动发布」——自动发布要同时满足两项设置，光看
 * topic_auto_enabled 是不够的，所以这里只报取值，不做任何「已启用」的断言。 */
function qzoneTopicPolicyMarkup(settings){
  if(!Object.keys(settings).length)return '';
  const auto=settings.topic_auto_enabled===true;
  const confirm=settings.topic_require_confirmation!==false;
  const topics=qzoneTopicTopics();
  /* 目录没读到时不编「0 个已开启」：那是把「没读到」说成了「一个都没开」。 */
  const count=topics.length
    ? `已启用主题 ${topics.length} 个（目录里当前可用的）`
    : '主题目录还没有读到';
  return `<div class="action-qzone-status-row">
    <span class="action-qzone-status-label">主题策略</span>
    <span class="action-qzone-status-value">
      <span class="action-qzone-chip ${auto?'is-warn':'is-off'}">模型自行发布 · ${auto?'开':'关'}（默认关）</span>
      <span class="action-qzone-chip ${confirm?'is-ok':'is-warn'}">主题人工确认 · ${confirm?'开':'关'}（默认开）</span>
      <span>${escapeHTML(count)}</span></span>
  </div>`;
}
function qzoneStateText(status){
  if(status.installed!==true)return '未安装';
  if(status.active!==true)return '安装未生效';
  if(status.role_enabled!==true)return '角色未启用';
  if(status.invoke_granted!==true)return '缺少身份授权';
  const consented=status.consented&&typeof status.consented==='object'?status.consented:{};
  if(!QZONE_CAPABILITIES.some(([id])=>consented[id]===true))return '尚未授权能力';
  return '已启用';
}
function qzoneStatusMarkup(status,full){
  const blocked=typeof qzoneStatus()?.runtime?.blocked_reason==='string'&&qzoneStatus().runtime.blocked_reason.trim();
  const tone=status.installed!==true?'is-off':qzoneUsable(status)&&!blocked?'is-ok':'is-warn';
  const reason=QZONE_STATUS_REASONS[status.reason]||'';
  return `<div class="action-qzone-status">
    <p class="action-qzone-state"><span class="action-qzone-chip ${tone}">${escapeHTML(qzoneStateText(status))}</span>`
    +`${reason?`<span>${escapeHTML(reason)}</span>`:''}`
    +`<span>扩展版本 ${escapeHTML(String(status.package_version||'未知'))}</span></p>
    ${qzoneCredentialMarkup(status.credential)}
    ${full?qzoneConsentMarkup(status):''}
    ${full?qzoneSwitchMarkup(qzoneSettings()):''}
    ${full?qzoneLimitsMarkup(qzoneSettings()):''}
    ${full?qzoneTopicPolicyMarkup(qzoneSettings()):''}
  </div>`;
}
function qzoneInstallMarkup(installed){
  const reason=QZONE_STATUS_REASONS[qzoneStatus()?.reason]||'';
  return `<div class="action-qzone-empty">
    <p class="action-qzone-empty-copy">${I('plug-zap')}<span>${installed
      ?`QQ 空间已经安装，但当前还不可用${reason?`：${escapeHTML(reason)}`:''}。`
      :'还没有安装 QQ 空间扩展。装好之后，角色的空间动态才会接进小屋。'}</span></p>
    ${installed?'':`<p class="action-qzone-hint">${I('info')}<span>安装并启用后，可以在这里调整开关与节流。</span></p>`}
    <div class="action-qzone-row">
      <button class="button small primary" type="button" data-qzone-action="install" ${qzoneState.busy?'disabled':''}>${I('plug-zap')}<span>${qzoneActing('install')?'正在安装…':'安装并启用'}</span></button>
    </div>
  </div>`;
}
/* 配置分区只有「已安装」时才出现；未安装时上面那句已经说了安装后可调。 */
function qzoneConfigMarkup(){
  return `<div class="action-qzone-block">${configEditors('qzoneConfigWorkspace',['qzone'],'QQ 空间设置')}</div>`;
}
/* 一条待确认的日程建议：意图、日程项、预期版本、创建时间，加一句说清「还没有
 * 改日程」的说明，以及两个就地操作。
 *
 * 日程项（agenda_id）只当文字读，**不做成链接**：这个页面上没有任何地方能改
 * 日程，把它做成可点的东西就是在暗示点下去会发生什么。写回在生活页做，回来
 * 把回执编号填进这里——所以两个操作是「标记已写回」「忽略」，而不是「应用」。
 *
 * 操作区照本页回复框的样子写：两个操作**始终**在行里，回执输入框展开在行的下面
 * （再点一次「标记已写回」收起，也另有「取消」），忽略的二次确认同理。回执框与
 * 忽略确认互斥——同一时刻只开一个，这样「填了半条回执又去点忽略」不会留下一个
 * 说不清属于哪次操作的回执。 */
function qzoneSuggestionMarkup(item){
  const id=String(item.suggestion_id);
  const busy=qzoneState.busy;
  const receiptOpen=qzoneState.suggestionReceiptFor===id;
  /* 两个子面板互斥：处理器的每一次切换都保证只有一个为真，这里再让回执框优先，
     万一将来有别的路径同时置上，也不会同时画出两个说不清先后的操作区。 */
  const dismissOpen=!receiptOpen&&qzoneState.suggestionConfirmFor===id;
  const receipt=qzoneState.suggestionReceiptDraft;
  const intent=typeof item.intent==='string'&&item.intent.trim()?item.intent.trim():'这条建议没有留下意图说明。';
  const agenda=typeof item.agenda_id==='string'&&item.agenda_id.trim()?item.agenda_id.trim():'未知';
  const revision=Number.isInteger(item.expected_revision)?String(item.expected_revision):'未知';
  const time=qzoneWhen(item.created_at);
  const owner=`data-qzone-suggestion="${escapeHTML(id)}"`;
  const row=`<div class="action-qzone-row">
      <button class="button small${receiptOpen?'':' primary'}" type="button" data-qzone-action="suggestion-apply-open" ${owner} ${busy?'disabled':''}>${I(receiptOpen?'chevron-up':'clipboard-check')}<span>${receiptOpen?'收起回执框':'标记已写回'}</span></button>
      <button class="button small" type="button" data-qzone-action="suggestion-dismiss" ${owner} ${busy?'disabled':''}>${I('x')}<span>忽略</span></button>
      <span class="action-qzone-meta">标记已写回要填日历回执编号；忽略不需要回执。</span>
    </div>`;
  const form=receiptOpen?`<div class="action-qzone-suggestion-form">
      <label class="action-qzone-field"><span>日历回执编号（在生活页完成写回后拿到的那个编号，必填）</span>
        <input type="text" data-qzone-receipt="${escapeHTML(id)}" maxlength="${QZONE_RECEIPT_LIMIT}" value="${escapeHTML(receipt)}" placeholder="粘贴日历回执编号" aria-label="日历回执编号" ${busy?'disabled':''}></label>
      <label class="action-qzone-field"><span>结果引用（可选，最多 ${QZONE_RESULT_REF_LIMIT} 字；留给以后核对用）</span>
        <input type="text" data-qzone-result="${escapeHTML(id)}" maxlength="${QZONE_RESULT_REF_LIMIT}" value="${escapeHTML(qzoneState.suggestionResultRefDraft)}" placeholder="可以不填" aria-label="结果引用" ${busy?'disabled':''}></label>
      <div class="action-qzone-row">
        <button class="button small primary" type="button" data-qzone-action="suggestion-apply" ${owner} ${busy||!receipt.trim()?'disabled':''}>${I('clipboard-check')}<span>${qzoneActing('suggestion',id)?'正在记录…':'确认标记已写回'}</span></button>
        <button class="button small" type="button" data-qzone-action="suggestion-apply-cancel" ${owner} ${busy?'disabled':''}>取消</button>
        <span class="action-qzone-suggestion-reason" data-qzone-receipt-hint${receipt.trim()?' hidden':''}>${I('info')}<span>要填日历回执编号才能标记已写回：写回是在生活页做的，这个编号就是那次改动的凭据。</span></span>
      </div>
    </div>`:'';
  const confirm=dismissOpen?`<div class="action-qzone-suggestion-form is-confirming">
      <p class="action-qzone-suggestion-confirm">${I('triangle-alert')}<span>忽略只是把这条建议从待确认里去掉，日程本身不会被修改，也不会替你写回。确认忽略？</span></p>
      <div class="action-qzone-row">
        <button class="button small danger" type="button" data-qzone-action="suggestion-dismiss-confirm" ${owner} ${busy?'disabled':''}>${I('x')}<span>${qzoneActing('suggestion',id)?'正在忽略…':'确认忽略'}</span></button>
        <button class="button small" type="button" data-qzone-action="suggestion-dismiss-cancel" ${owner} ${busy?'disabled':''}>取消</button>
      </div>
    </div>`:'';
  return `<article class="action-qzone-suggestion">
    <header class="action-qzone-suggestion-head">
      <strong>${I('calendar-clock')}<span>${escapeHTML(intent)}</span></strong>
      ${time?`<time>${escapeHTML(time)}</time>`:''}
    </header>
    <p class="action-qzone-suggestion-meta">
      <span>日程项 <b>${escapeHTML(agenda)}</b></span>
      <span>预期版本 <b>${escapeHTML(revision)}</b></span>
    </p>
    <p class="action-qzone-suggestion-note">${I('info')}<span>${escapeHTML(QZONE_SUGGESTION_NOTE)}</span></p>
    ${row}
    ${form}
    ${confirm}
  </article>`;
}
/* 小节本体：**只在真的有 pending 建议时才渲染**，没有就整块不出现——也不放一句
 * 「暂无」占位。它读的是 status.runtime.agenda_suggestions，所以只有后端给出了
 * 运行视图（已安装）才可能有内容；调用方仍然只在已安装时拼它，避免把「没读到」
 * 和「没有建议」画成同一个空块。 */
function qzoneSuggestionBlockMarkup(){
  const items=qzoneSuggestionList();
  if(!items.length)return '';
  return `<div class="action-qzone-block action-qzone-suggestions">
    <header class="action-qzone-block-head">
      <h3>${I('calendar-clock')}<span>待确认的日程建议</span></h3>
      <span class="action-qzone-count">${items.length} 条待处理</span>
    </header>
    <div class="action-qzone-suggestion-list">${items.map(qzoneSuggestionMarkup).join('')}</div>
  </div>`;
}
function qzoneReplyMarkup(index,gate){
  const draft=qzoneState.replyDraft;
  return `<div class="action-qzone-reply">
    <label class="action-qzone-field"><span>回复内容（最多 ${QZONE_COMMENT_LIMIT} 字，公开可见）</span>
      <textarea data-qzone-draft="reply" data-qzone-post="${index}" maxlength="${QZONE_COMMENT_LIMIT}" rows="2" placeholder="写一句回复…">${escapeHTML(draft)}</textarea></label>
    <div class="action-qzone-row">
      <span class="action-qzone-count" data-qzone-count="reply">${draft.length} / ${QZONE_COMMENT_LIMIT}</span>
      <button class="button small" type="button" data-qzone-action="reply-cancel" ${qzoneState.busy?'disabled':''}>取消</button>
      <button class="button small primary" type="button" data-qzone-action="reply-send" data-qzone-post="${index}" ${qzoneState.busy||!gate.ok||!draft.trim()?'disabled':''}>${I('send')}<span>${qzoneActing('comment',index)?'发送中…':'发送回复'}</span></button>
    </div>
  </div>`;
}
function qzonePostMarkup(item,index){
  const likeGate=qzoneGate('like');
  const commentGate=qzoneGate('comment');
  const own=item.own_post===true;
  const liked=item.liked===true;
  const likeState=typeof item.likeState==='string'?item.likeState:'';
  const commentState=typeof item.commentState==='string'?item.commentState:'';
  const likeLabel=likeState?qzoneOutcomeLabel('like',likeState):(qzoneActing('like',index)?'点赞中…':'点赞');
  const commentLabel=commentState?qzoneOutcomeLabel('comment',commentState):(qzoneActing('comment',index)?'发送中…':'回复');
  const comments=Array.isArray(item.comments)?item.comments.filter(entry=>entry&&typeof entry==='object'):[];
  const time=qzoneWhen(item.at);
  return `<article class="action-qzone-post${own?' is-own':''}">
    <header class="action-qzone-post-head">
      <strong>${escapeHTML(qzoneAuthor(item.author))}</strong>
      ${own?`<span class="action-qzone-chip is-own">我的动态</span>`:''}
      ${liked?`<span class="action-qzone-chip is-ok">已赞</span>`:''}
      ${likeState==='accepted'||likeState==='unknown'?`<span class="action-qzone-chip ${QZONE_OUTCOME_TONES[likeState]}">${qzoneOutcomeLabel('like',likeState)}</span>`:''}
      ${time?`<time>${escapeHTML(time)}</time>`:''}
    </header>
    <p class="action-qzone-excerpt">${escapeHTML(item.excerpt||'这条动态没有可显示的正文。')}</p>
    ${comments.length?`<ul class="action-qzone-comments">${comments.slice(0,4).map(entry=>
      `<li><strong>${escapeHTML(qzoneAuthor(entry.author))}</strong><span>${escapeHTML(entry.text||'')}</span></li>`).join('')}</ul>`:''}
    <div class="action-qzone-post-actions">
      <button class="button small" type="button" data-qzone-action="like" data-qzone-post="${index}" ${qzoneState.busy||!likeGate.ok||liked||likeState?'disabled':''}>${I('heart')}<span>${escapeHTML(liked&&!likeState?'已赞':likeLabel)}</span></button>
      <button class="button small" type="button" data-qzone-action="reply" data-qzone-post="${index}" ${qzoneState.busy||!commentGate.ok||commentState?'disabled':''}>${I('message-circle')}<span>${escapeHTML(commentLabel)}</span></button>
    </div>
    ${qzoneState.replyFor===index&&!commentState?qzoneReplyMarkup(index,commentGate):''}
  </article>`;
}
function qzoneFeedBlockMarkup(feedGate,likeGate,commentGate){
  const scopeLabel=QZONE_SCOPES.find(([id])=>id===qzoneState.scope)?.[1]||'好友动态';
  const feed=qzoneFeed();
  const hints=[feedGate.ok?'':feedGate.reason,likeGate.ok?'':`点赞：${likeGate.reason}`,
    commentGate.ok?'':`回复：${commentGate.reason}`].filter(Boolean);
  return `<div class="action-qzone-block">
    <header class="action-qzone-block-head">
      <h3>${I('refresh-cw')}<span>刷空间</span></h3>
      <div class="action-qzone-scope" role="group" aria-label="刷空间范围">
        ${QZONE_SCOPES.map(([id,label])=>`<button class="button small${qzoneState.scope===id?' primary':''}" type="button" data-qzone-action="scope" data-qzone-scope="${id}" aria-pressed="${qzoneState.scope===id}" ${qzoneState.busy?'disabled':''}>${label}</button>`).join('')}
      </div>
      <button class="button small primary" type="button" data-qzone-action="scan" ${qzoneState.busy||!feedGate.ok?'disabled':''}>${I('refresh-cw')}<span>${qzoneActing('scan')?'正在刷空间…':'刷空间'}</span></button>
    </header>
    ${hints.map(text=>`<p class="action-qzone-hint">${I('info')}<span>${escapeHTML(text)}</span></p>`).join('')}
    ${feed?`<p class="action-qzone-meta">${escapeHTML(`${scopeLabel} · ${feed.items.length} 条 · ${qzoneClock(feed.scannedAt)} 刷新`)}</p>
      ${feed.items.length?`<div class="action-qzone-feed">${feed.items.map(qzonePostMarkup).join('')}</div>`
        :'<p class="action-qzone-empty-line">这次没有读到动态。</p>'}`
      :`<p class="action-qzone-empty-line">还没有刷过${scopeLabel}。</p>`}
  </div>`;
}
/* 发布前必须先定主题与场景，所以两个下拉排在正文前面：
 * 先决定「这条在讲什么、为什么现在值得发」，再写正文——顺序反了会让人写完
 * 一段话才发现主题要重挑。场景下拉只列当前主题放行的场景，随主题联动。
 *
 * 目录读不到时不画「空目录」：禁用发布，并把原因写在提示里（两个下拉都渲染成
 * 单个「目录未读取」选项，不给一个能点却没有任何选项的控件）。 */
function qzonePublishTopicMarkup(){
  const topics=qzoneTopicTopics();
  const scenes=qzoneTopicScenes(qzoneTopic());
  const disabled=qzoneState.busy?'disabled':'';
  const options=topics.length
    ? topics.map(topic=>`<option value="${escapeHTML(topic.id)}"${topic.id===qzoneState.publishTopic?' selected':''}>${escapeHTML(topic.label)}</option>`).join('')
    : '<option value="">主题目录没有读到</option>';
  const sceneOptions=scenes.length
    ? scenes.map(scene=>`<option value="${escapeHTML(scene.id)}"${scene.id===qzoneState.publishScene?' selected':''}>${escapeHTML(scene.label)}</option>`).join('')
    : '<option value="">没有可选场景</option>';
  return `<div class="action-qzone-scene">
    <label class="action-qzone-field"><span>主题（这条在讲什么，必选）</span>
      <select data-qzone-topic="publish" aria-label="说说主题" ${disabled||!topics.length?'disabled':''}>${options}</select></label>
    <label class="action-qzone-field"><span>场景（为什么现在值得发，只列该主题放行的场景）</span>
      <select data-qzone-scene="publish" aria-label="说说场景" ${disabled||!scenes.length?'disabled':''}>${sceneOptions}</select></label>
  </div>`;
}
/* 发布按钮现在要同时满足三件事：能力开关放行、目录读到、主题与场景都选好。
 * 提成一个函数是因为计数时（qzoneCounts）也要判同一份条件——两处各写一遍，
 * 迟早会出现「按钮看着能点、点下去被本地拦下」这种不一致。 */
function qzonePublishBlocked(){
  return Boolean(!qzoneGate('publish').ok||!qzoneCatalogue()||!qzoneState.publishTopic
    ||!qzoneState.publishScene);
}
function qzonePublishBlockMarkup(gate){
  const draft=qzoneState.publishDraft;
  const reasons=[gate.ok?'':gate.reason,
    qzoneCatalogue()?'':'没有读到主题与场景目录，读不到时不能发布：请先点上面的「重新读取」。'].filter(Boolean);
  const blocked=qzonePublishBlocked();
  return `<div class="action-qzone-block">
    <header class="action-qzone-block-head"><h3>${I('send')}<span>发说说</span></h3>
      <span class="action-qzone-count" data-qzone-count="publish">${draft.length} / ${QZONE_PUBLISH_LIMIT}</span></header>
    ${reasons.map(text=>`<p class="action-qzone-hint">${I('info')}<span>${escapeHTML(text)}</span></p>`).join('')}
    ${qzonePublishTopicMarkup()}
    <label class="action-qzone-field"><span>以角色的口吻写一条说说</span>
      <textarea data-qzone-draft="publish" maxlength="${QZONE_PUBLISH_LIMIT}" rows="3" placeholder="今天想说点什么…" aria-label="说说正文">${escapeHTML(draft)}</textarea></label>
    <div class="action-qzone-row">
      <button class="button small primary" type="button" data-qzone-action="publish" ${qzoneState.busy||blocked||!draft.trim()?'disabled':''}>${I('send')}<span>${qzoneActing('publish')?'正在发布…':'发布说说'}</span></button>
      <span class="action-qzone-meta">发布是公开动作：只有确认过的结果才算成功，未确认的结果不会自动重发。主题与场景按这里的选报送，并受该主题自己的开关、置信度门槛、每日上限与冷却约束。</span>
    </div>
  </div>`;
}
function qzoneDangerMarkup(){
  if(!qzoneState.confirmDisable){
    return `<div class="action-qzone-danger">
      <div class="action-qzone-row">
        <button class="button small" type="button" data-qzone-action="disable" ${qzoneState.busy?'disabled':''}>${I('power')}<span>停用</span></button>
        <span class="action-qzone-meta">停用只撤销这个对象的四项能力授权；扩展包与角色开关保留。</span>
      </div>
    </div>`;
  }
  return `<div class="action-qzone-danger is-confirming">
    <p class="action-qzone-danger-text">${I('triangle-alert')}<span>停用后这个对象不再接入空间动态，已授权的四项能力会被撤销。确认停用？</span></p>
    <div class="action-qzone-row">
      <button class="button small danger" type="button" data-qzone-action="disable-confirm" ${qzoneState.busy?'disabled':''}>确认停用</button>
      <button class="button small" type="button" data-qzone-action="disable-cancel" ${qzoneState.busy?'disabled':''}>取消</button>
    </div>
  </div>`;
}
function qzoneBody(){
  const status=qzoneStatus();
  if(!status){
    /* 还没有状态：要么在读，要么读失败。两种必须说得不一样——
       「正在读取…」停在一次失败之后是最容易骗人的界面。 */
    const failed=qzoneState.phase==='error';
    return `${failed?'':'<p class="action-qzone-loading" role="status">正在读取 QQ 空间的当前状态…</p>'}
      ${qzoneNoticeMarkup()}
      ${failed?`<div class="action-qzone-row">${button('重新读取','data-qzone-action="refresh-status"','small')}</div>`:''}`;
  }
  const installed=status.installed===true;
  const usable=qzoneUsable(status);
  return `${qzoneNoticeMarkup()}
    ${qzoneBlockedMarkup()}
    ${qzoneStatusMarkup(status,usable||installed)}
    ${usable?'':qzoneInstallMarkup(installed)}
    ${installed?qzoneSuggestionBlockMarkup():''}
    ${installed?qzoneConfigMarkup():''}
    ${usable?qzoneFeedBlockMarkup(qzoneGate('feed'),qzoneGate('like'),qzoneGate('comment')):''}
    ${usable?qzonePublishBlockMarkup(qzoneGate('publish')):''}
    ${usable?qzoneDangerMarkup():''}`;
}
function renderQzoneSection(){
  return `<section class="action-qzone" id="action-qzone" aria-labelledby="action-qzone-title">
    <header class="action-qzone-head">
      <span class="action-qzone-mark">${I('star')}</span>
      <div class="action-qzone-copy"><p class="action-kicker action-kicker-light">QZONE EXTENSION</p>
        <h2 id="action-qzone-title">QQ 空间</h2>
        <p>把角色的空间动态接进小屋：刷空间、点赞、回复、发空间。</p></div>
    </header>
    <div class="action-qzone-body" id="actionQzoneBody">${qzoneBody()}</div>
  </section>`;
}
/* 只重画这一块：面板的其余部分由 renderSectionPanel 负责，动作结果不该
 * 让整块行动矩阵跟着重建（那会丢焦点，也会重播入场动画）。 */
function paintQzone(){
  const host=document.getElementById('actionQzoneBody');
  if(!host)return;
  host.innerHTML=qzoneBody();
  icons();
}
/* 挂载：面板每次重画都会走这里，所以这里不无条件重读——只有第一次、
 * 上次读失败、或上次读已超过一分钟才拉一次状态，免得来回切分区时反复请求。 */
function mountQzoneSection(){
  if(!document.getElementById('actionQzoneBody'))return;
  const stale=qzoneState.phase==='ready'&&Date.now()-qzoneState.loadedAt>60000;
  if(qzoneState.phase==='idle'||qzoneState.phase==='error'||stale){
    qzoneStart('status',()=>qzoneLoadStatus({busyPaint:true}));
  }
}
/* 配置工作台还没有声明 qzone 分区时，configEditors 的容器会永远停在
 * 「正在读取设置…」——那是在撒谎（并没有在读取）。这时换成一句实话，
 * 并指回上面的状态行：那里的四个开关与节流就是当前生效的值。 */
function qzoneConfigUnavailable(host){
  if(!host?.isConnected)return;
  host.innerHTML=`<p class="config-editors-hint">${I('info')}<span>QQ 空间的开关与节流还没有接到配置工作台，暂时不能在这里修改；上面的状态行显示的是当前生效的值。</span></p>`;
  icons();
}
/* 字数只更新计数，不重画：重画会把光标位置丢掉。顺带把发送按钮的可用态
 * 跟着正文走，空正文不会点出一个必然失败的请求。 */
function qzoneCounts(){
  const publish=document.querySelector('#actionQzoneBody [data-qzone-draft="publish"]');
  if(publish){
    const counter=document.querySelector('#actionQzoneBody [data-qzone-count="publish"]');
    if(counter)counter.textContent=`${publish.value.length} / ${QZONE_PUBLISH_LIMIT}`;
    const button=document.querySelector('#actionQzoneBody [data-qzone-action="publish"]');
    if(button)button.disabled=qzoneState.busy||qzonePublishBlocked()||!publish.value.trim();
  }
  const reply=document.querySelector('#actionQzoneBody [data-qzone-draft="reply"]');
  if(reply){
    const counter=document.querySelector('#actionQzoneBody [data-qzone-count="reply"]');
    if(counter)counter.textContent=`${reply.value.length} / ${QZONE_COMMENT_LIMIT}`;
    const button=document.querySelector('#actionQzoneBody [data-qzone-action="reply-send"]');
    if(button)button.disabled=qzoneState.busy||!qzoneGate('comment').ok||!reply.value.trim();
  }
}
/* 回执框的即时反馈，同样不重画（重画会把光标从输入框里挪走）：只把确认按钮的
 * 可用态和那句原因跟着输入走。空编号时按钮停着并把原因写出来——后端对空编号
 * 必然回 qzone_suggestion_receipt_required，那种请求不该发出去。 */
function qzoneSuggestionInput(){
  const field=document.querySelector('#actionQzoneBody [data-qzone-receipt]');
  if(!field)return;
  const filled=Boolean(field.value.trim());
  const button=document.querySelector('#actionQzoneBody [data-qzone-action="suggestion-apply"]');
  if(button)button.disabled=qzoneState.busy||!filled;
  const hint=document.querySelector('#actionQzoneBody [data-qzone-receipt-hint]');
  if(hint)hint.hidden=filled;
}
function qzoneClick(el){
  /* 在途期间不接第二次点击：这样 operation_key 也绝不可能被同一个动作复用。 */
  if(qzoneState.busy)return;
  const action=el.dataset.qzoneAction;
  if(action==='install'){qzoneStart('install',()=>qzoneConfigure(true));return;}
  if(action==='disable'){qzoneState.confirmDisable=true;paintQzone();return;}
  if(action==='disable-cancel'){qzoneState.confirmDisable=false;paintQzone();return;}
  if(action==='disable-confirm'){qzoneStart('disable',()=>qzoneConfigure(false));return;}
  if(action==='refresh-status'){qzoneStart('status',()=>qzoneLoadStatus({busyPaint:true}));return;}
  if(action==='refresh-credentials'){qzoneStart('credentials',()=>qzoneRefreshCredentials());return;}
  if(action==='scope'){
    const scope=el.dataset.qzoneScope;
    if(QZONE_SCOPES.some(([id])=>id===scope)&&qzoneState.scope!==scope){
      qzoneState.scope=scope;
      qzoneState.replyFor=-1;
      qzoneState.replyDraftFor=-1;
      paintQzone();
    }
    return;
  }
  if(action==='scan'){qzoneStart('scan',()=>qzoneScan(qzoneState.scope));return;}
  if(action==='like'){
    const index=Number(el.dataset.qzonePost);
    if(Number.isInteger(index))qzoneStart({action:'like',index},()=>qzoneLike(index));
    return;
  }
  if(action==='reply'){
    const index=Number(el.dataset.qzonePost);
    if(!Number.isInteger(index))return;
    if(qzoneState.replyFor===index){qzoneState.replyFor=-1;paintQzone();return;}
    /* 换一条动态就换一个回复框：把上一条写了一半的正文带过去，
       等于让用户有机会把它发到另一条动态下面。 */
    if(qzoneState.replyDraftFor!==index){qzoneState.replyDraft='';qzoneState.replyDraftFor=index;}
    qzoneState.replyFor=index;
    paintQzone();
    requestAnimationFrame(()=>document.querySelector(`#actionQzoneBody [data-qzone-draft="reply"][data-qzone-post="${index}"]`)?.focus());
    return;
  }
  if(action==='reply-cancel'){
    qzoneState.replyFor=-1;
    paintQzone();
    return;
  }
  if(action==='reply-send'){
    const index=Number(el.dataset.qzonePost);
    if(Number.isInteger(index))qzoneStart({action:'comment',index},()=>qzoneComment(index));
    return;
  }
  if(action==='publish'){qzoneStart('publish',()=>qzonePublish());return;}
  /* 日程建议。开回执框与开忽略确认都是纯界面状态，直接重画；真正发请求的两条
     走 qzoneStart，在途期间整块按钮禁用（qzoneState.busy 参与渲染）。 */
  if(action==='suggestion-apply-open'){
    const id=el.dataset.qzoneSuggestion;
    if(!id)return;
    if(qzoneState.suggestionReceiptFor===id){qzoneState.suggestionReceiptFor='';paintQzone();return;}
    /* 换一条建议就清空输入：把上一条的回执编号带到另一条上，等于把回执记到
       别人的问题上，那是会写错账的。 */
    qzoneState.suggestionReceiptDraft='';
    qzoneState.suggestionResultRefDraft='';
    qzoneState.suggestionReceiptFor=id;
    qzoneState.suggestionConfirmFor='';
    paintQzone();
    requestAnimationFrame(()=>document.querySelector('#actionQzoneBody [data-qzone-receipt]')?.focus());
    return;
  }
  if(action==='suggestion-apply-cancel'){
    qzoneState.suggestionReceiptFor='';
    paintQzone();
    return;
  }
  if(action==='suggestion-apply'){
    const id=el.dataset.qzoneSuggestion;
    if(!id)return;
    /* 提交前以屏幕上的输入为准再同步一次状态：按钮的可用态是跟着输入框走的，
       送出去的正文也得是同一个值，免得两边各读一份、哪天读岔了。 */
    const receiptField=document.querySelector('#actionQzoneBody [data-qzone-receipt]');
    if(receiptField)qzoneState.suggestionReceiptDraft=receiptField.value;
    const refField=document.querySelector('#actionQzoneBody [data-qzone-result]');
    if(refField)qzoneState.suggestionResultRefDraft=refField.value;
    /* 按钮在空编号时就是禁用的，这里再挡一次：键盘或程序触发也不能绕过，
       空编号发出去必然被后端拒（qzone_suggestion_receipt_required）。 */
    if(!qzoneState.suggestionReceiptDraft.trim()){
      qzoneNotice(QZONE_ERRORS.qzone_suggestion_receipt_required,true);
      return;
    }
    qzoneStart({action:'suggestion',index:id},()=>qzoneResolveSuggestion(id,'applied'));
    return;
  }
  if(action==='suggestion-dismiss'){
    const id=el.dataset.qzoneSuggestion;
    if(!id)return;
    qzoneState.suggestionReceiptFor='';
    qzoneState.suggestionConfirmFor=qzoneState.suggestionConfirmFor===id?'':id;
    paintQzone();
    return;
  }
  if(action==='suggestion-dismiss-cancel'){
    qzoneState.suggestionConfirmFor='';
    paintQzone();
    return;
  }
  if(action==='suggestion-dismiss-confirm'){
    const id=el.dataset.qzoneSuggestion;
    if(id)qzoneStart({action:'suggestion',index:id},()=>qzoneResolveSuggestion(id,'dismissed'));
    return;
  }
}
function renderActionOriginal(){
  const manifestReady=Array.isArray(integrationSnapshot?.providers);
  const statuses=actionDomains.map(item=>actionProviderStatus(item.provider));
  const connected=statuses.filter(item=>item.state==='connected').length;
  const needsCheck=statuses.filter(item=>item.state!=='connected'&&item.state!=='loading').length;
  const meter=manifestReady?Math.round(connected/actionDomains.length*100):0;
  const summary=manifestReady?(needsCheck?`${needsCheck} 项需要留意`:'状态全部正常'):'正在同步能力状态';
  return `<div class="action-page" data-manifest-ready="${manifestReady}">
    <section class="action-overview" aria-labelledby="action-matrix-title">
      <div class="action-overview-copy">
        <p class="action-kicker"><span class="action-live-mark" aria-hidden="true"></span> ACTION MATRIX</p>
        <h2 id="action-matrix-title">行动矩阵</h2>
        <p class="action-overview-role">当前人格 <strong>${roleName()}</strong></p>
        <div class="action-overview-count" role="status" aria-live="polite">
          <strong>${manifestReady?String(connected).padStart(2,'0'):'--'}<span> / ${actionDomains.length.toString().padStart(2,'0')}</span></strong>
          <span>已连接能力链</span>
        </div>
        <div class="action-meter" role="meter" aria-label="已连接能力链" aria-valuemin="0" aria-valuemax="${actionDomains.length}" aria-valuenow="${connected}" aria-valuetext="${manifestReady?`${connected} / ${actionDomains.length} 条已连接`:'正在读取'}">
          <span style="width:${meter}%"></span>
        </div>
        <p class="action-overview-summary" aria-live="polite">${escapeHTML(summary)}</p>
      </div>
      <div class="action-overview-map" role="group" aria-label="行动能力状态与配置定位">
        <div class="action-map-line" aria-hidden="true"></div>
        ${actionDomains.map((item,index)=>{
          const status=statuses[index];
          return `<button class="action-route-node action-domain--${item.id}" type="button" data-action-focus="${item.id}" data-state="${escapeHTML(status.state)}" aria-label="${escapeHTML(`${item.title}，${status.label}，定位配置入口`)}">
            <span class="action-route-index">${String(index+1).padStart(2,'0')}</span>
            <span class="action-route-icon">${I(item.icon)}</span>
            <span class="action-route-copy"><strong>${item.title}</strong><small>${escapeHTML(status.label)}</small></span>
            <span class="action-route-indicator" aria-hidden="true"></span>
          </button>`;
        }).join('')}
      </div>
    </section>
    <section class="action-configuration" aria-labelledby="action-config-title">
      <header class="action-config-heading">
        <div><p class="action-kicker action-kicker-light">CONTROL DECK</p><h2 id="action-config-title">配置入口</h2></div>
        <span class="action-config-count">${String(actionDomains.length).padStart(2,'0')} 个行动分区</span>
      </header>
      <div class="action-config-grid">
        ${actionDomains.map((item,index)=>{
          const status=statuses[index];
          return `<article class="action-config-card action-domain--${item.id}" id="action-config-${item.id}" style="--action-index:${index}" aria-labelledby="action-title-${item.id}">
            <header class="action-config-card-head">
              <span class="action-config-icon">${I(item.icon)}</span>
              <div><p>${item.code} <span>${String(index+1).padStart(2,'0')}</span></p><h3 id="action-title-${item.id}">${item.title}</h3></div>
              <span class="action-card-status action-status--${escapeHTML(status.state)}" title="${escapeHTML(status.label)}"><i aria-hidden="true"></i>${escapeHTML(status.label)}</span>
            </header>
            <p class="action-config-summary">${item.summary}</p>
            <div class="action-config-owner"><span>配置归属</span><strong>${item.owner}</strong></div>
            <div class="action-config-actions">
              <button class="button small action-provider-button" type="button" data-product-provider="${item.provider}" aria-label="查看${item.title}拓展详情">${I('blocks')}<span>拓展详情</span></button>
              <button class="button small primary action-settings-button" type="button" data-manage-jump="${item.destination}">${I(item.destinationIcon)}<span>${item.destinationLabel}</span>${I('arrow-right')}</button>
            </div>
          </article>`;
        }).join('')}
      </div>
    </section>
    ${renderQzoneSection()}
  </div>`;
}
function renderOutputOriginal(){
  const previewTab=(id,label,icon,index)=>`<button type="button" role="tab" id="output-mode-${id}" aria-controls="output-preview-${id}" aria-selected="${index===0?'true':'false'}" tabindex="${index===0?'0':'-1'}" class="output-mode-tab" data-output-mode="${id}">${I(icon)}<span>${label}</span></button>`;
  const configTab=(id,label,icon,index)=>`<button type="button" role="tab" id="output-tab-${id}" aria-controls="output-panel-${id}" aria-selected="${index===0?'true':'false'}" tabindex="${index===0?'0':'-1'}" class="output-config-tab" data-output-tab="${id}">${I(icon)}<strong>${label}</strong></button>`;
  return `<div class="output-page">
    <section class="output-showcase" aria-label="作品预览">
      <div class="output-showcase-topline"><span>${I('sparkles')}作品预览</span><span class="output-preview-badge">示例</span></div>
      <div class="output-showcase-grid">
        <div class="output-showcase-intro">
          <div class="output-mode-tabs" role="tablist" aria-label="切换产出预览">
            ${previewTab('image','图像生成','image',0)}
            ${previewTab('story','文字创作','book-open',1)}
          </div>
        </div>
        <div class="output-preview-stage">
          <section class="output-preview-view" id="output-preview-image" role="tabpanel" aria-labelledby="output-mode-image" tabindex="0" data-output-view>
            <figure class="output-image-frame">
              <img src="assets/chengxi.jpg" alt="角色视觉样例立绘" loading="lazy">
              <span class="output-image-tag">角色视觉</span>
              <span class="output-image-orbit" aria-hidden="true"></span>
            </figure>
            <div class="output-preview-copy">
              <h3>图像生成</h3>
              <button type="button" class="output-preview-action" data-output-open="visual">生图设置 ${I('arrow-down-right')}</button>
            </div>
          </section>
          <section class="output-preview-view" id="output-preview-story" role="tabpanel" aria-labelledby="output-mode-story" tabindex="0" data-output-view hidden>
            <article class="output-manuscript">
              <div class="output-manuscript-top"><span>文字作品</span><span aria-hidden="true">${I('sparkles')}</span></div>
              <h3>把雨声留在窗边</h3>
              <p class="output-manuscript-body">窗外的雨慢下来时，灯还亮着。她把没说完的话收进一本薄薄的册子，等下一次想起，再接着写。</p>
              <div class="output-manuscript-footer"><span>Content 作品</span><span>角色创作</span></div>
            </article>
            <div class="output-preview-copy">
              <h3>文字创作</h3>
              <button type="button" class="output-preview-action" data-output-open="creation">创作设置 ${I('arrow-down-right')}</button>
            </div>
          </section>
        </div>
      </div>
      <div class="output-signal-line" aria-hidden="true"><span></span></div>
    </section>

    <section class="output-config" id="output-config" aria-label="产出配置">
      <header class="output-config-heading"><h2>配置</h2></header>
      <div class="output-config-tabs" role="tablist" aria-label="产出配置分区">
        ${configTab('visual','生图与审核','image',0)}
        ${configTab('materials','参考素材','images',1)}
        ${configTab('creation','创作与作品','notebook-pen',2)}
      </div>
      <div class="output-config-panels">
        <section class="output-config-panel" id="output-panel-visual" role="tabpanel" aria-labelledby="output-tab-visual" tabindex="0" data-output-panel>
          <div class="output-panel-content">
            <div class="output-editor-block">${configEditors('imageControlWorkspace',['quota','image_review'],'生图额度与审核')}</div>
            <div class="output-provider-block"><div class="output-provider-heading"><h4>生成能力</h4><button type="button" class="output-inline-link" data-go="manage" data-manage="models">模型路线 ${I('arrow-up-right')}</button></div>${providerSummary(['image'])}</div>
          </div>
        </section>
        <section class="output-config-panel" id="output-panel-materials" role="tabpanel" aria-labelledby="output-tab-materials" tabindex="0" data-output-panel hidden>
          <div class="output-panel-heading"><span class="output-panel-mark">${I('images')}角色级 · 默认关闭</span></div>
          <div class="output-panel-content output-material-content"><div class="output-editor-block"><div class="output-config-material-settings">${configEditors('materialControlWorkspace',['photo.reference','wardrobe'],'参考图与衣柜')}</div><div id="imageMaterialsWorkspace" class="image-materials-workspace" aria-label="参考素材与衣柜工作区"></div></div></div>
        </section>
        <section class="output-config-panel" id="output-panel-creation" role="tabpanel" aria-labelledby="output-tab-creation" tabindex="0" data-output-panel hidden>
          <div class="output-panel-content output-creation-content"><div class="output-editor-block"><div class="output-provider-heading"><h4>Content 作品库</h4></div>${providerSummary(['content'])}<div class="output-editor-block"><div class="output-provider-heading"><h4>原生创作</h4><button type="button" class="output-inline-link" data-go="manage" data-manage="models">创作模型 ${I('arrow-up-right')}</button></div>${configEditors('contentAuthoringWorkspace',['content.authoring'],'原生创作与方向')}</div></div><aside class="output-route-note"><div><strong>模型路线</strong><button type="button" class="output-inline-link" data-go="manage" data-manage="models">模型与连接 ${I('arrow-up-right')}</button></div></aside></div>
        </section>
      </div>
    </section>
  </div>`;
}

function activateOutputPreview(id,{focus=false}={}){
  const tabs=$$('[data-output-mode]');
  const target=tabs.find(tab=>tab.dataset.outputMode===id);
  const panel=document.getElementById('output-preview-'+id);
  if(!target||!panel)return;
  tabs.forEach(tab=>{const active=tab===target;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;});
  $$('[data-output-view]').forEach(view=>{const active=view===panel;view.hidden=!active;});
  if(focus)target.focus();
}

function activateOutputTab(id,{focus=false,scroll=false}={}){
  const tabs=$$('[data-output-tab]');
  const target=tabs.find(tab=>tab.dataset.outputTab===id);
  const panel=document.getElementById('output-panel-'+id);
  if(!target||!panel)return;
  tabs.forEach(tab=>{const active=tab===target;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;});
  $$('[data-output-panel]').forEach(view=>{const active=view===panel;view.hidden=!active;});
  if(focus)target.focus();
  if(scroll){
    const reduced=state.reduceMotion||window.matchMedia('(prefers-reduced-motion: reduce)').matches
      ||['low','off'].includes(document.documentElement.dataset.motion);
    document.getElementById('output-config')?.scrollIntoView({behavior:reduced?'instant':'smooth',block:'start'});
  }
}
function replySectionJump(label,section,icon='settings-2'){
  return `<button class="expression-route-button" type="button" data-reply-section="${section}">${I(icon)}<span>${label}</span>${I('arrow-right')}</button>`;
}
function expressionLifeJump(label,tab,icon='arrow-up-right'){
  return `<button class="expression-route-button" type="button" data-expression-life-tab="${tab}">${I(icon)}<span>${label}</span>${I('arrow-right')}</button>`;
}
function expressionPerceptionJump(label,tab='recall',icon='message-square-quote'){
  return `<button class="expression-route-button" type="button" data-perception-config="${tab}">${I(icon)}<span>${label}</span>${I('arrow-right')}</button>`;
}
function renderExpressionOriginal(){
  const modules=[
    ['expression-text','message-square-more','D1','文字与风格','分句 · 语气 · 文字整理'],
    ['expression-voice','volume-2','D2','语音回复','触发 · 语种 · TTS'],
    ['expression-reaction','smile','D3','表情与配图','检索 · 语义 · 素材'],
    ['expression-platform','send','D4','平台组件与动作','引用 · @ · 平台动作'],
    ['expression-timing','clock-3','D5','节奏与时机','分段等待 · 休息 · 联系'],
    ['expression-group','speech','D6','群聊语气','保留角色声线 · 表达去噪'],
  ];
  return `<div class="expression-page">
    <nav class="expression-module-nav" aria-label="表达配置模块">
      ${modules.map(([id,icon,code,title,detail])=>`<a href="#${id}" aria-label="${code} ${title}：${detail}">
        <span class="expression-module-code">${code}</span><span class="expression-module-copy"><strong>${title}</strong><small>${detail}</small></span>
        <span class="expression-module-arrow" aria-hidden="true">${I('arrow-down')}</span></a>`).join('')}
    </nav>
    ${consoleSections([
      ['文字形态与风格','分句、文字风格、发送前整理与表达学习；字段按回复工作台分区呈现。',`${renderReply()}${settingsJump('表达学习与规则审核','learning')}`,'expression-text'],
      ['语音与朗读','控制语音触发、语种、朗读内容、TTS 提供方与投递方式。',`${replySectionJump('打开语音与朗读设置','voice','volume-2')}`,'expression-voice'],
      ['表情与配图','管理表情检索、语义权重、候选池与素材复核。',`${configEditors('reactionConfigWorkspace',['reaction'],'表情检索')}
        <div id="semanticExpressionWorkspace" class="expression-semantic-workspace">${consoleLoading('正在读取表情素材…')}</div>`,'expression-reaction'],
      ['平台组件与动作','控制引用、@ 发言者、消息组件顺序与发送前检查；撤回原文转写在感知页维护。',`<div class="expression-capability-note" role="note"><strong>V2 当前范围</strong><p>本轮回复引用、群聊 @ 与组件顺序已有设置；跨会话转述和主动引用触发暂未接入。命中词在 V2 中用于发送前拦截。</p></div>
        ${replySectionJump('打开引用与消息组件','components','messages-square')}
        ${replySectionJump('打开发送前检查','checks','shield-check')}
        ${expressionPerceptionJump('管理撤回原文转写（感知页）')}
        ${settingsJump('主动语音与戳一戳','contact')}
        ${expressionLifeJump('QQ 自定义短状态','state','activity')}`,'expression-platform'],
      ['节奏与时机','调整分段等待、休息时段、醒后补看和主动联系时机。',`${replySectionJump('调整分段发送间隔','timing','timer')}
        ${expressionLifeJump('休息时段与醒后补看','diary','moon-star')}
        ${settingsJump('主动联系与忙碌时的回复','contact')}`,'expression-timing'],
      ['群聊表达与人格保留','只影响群聊回复的语气，不改变回应判断、角色身份或授权。',
        configEditors('groupDenoiseWorkspace',['group_participation'],'群聊表达去噪'),'expression-group'],
    ])}
  </div>`;
}
const SELF_PROFILE_SECTIONS=[
  ['identity','user-round','身份',['name','species','birthday','age','gender','occupation','identity','key_lore','character_extra']],
  ['appearance','scan-face','外貌',['appearance_points','hair','eyes','clothing','image_identity_hint','appearance']],
  ['personality','sparkles','性格',['personality','daily_habits']],
  ['voice','audio-lines','口吻',['first_person','speech_style','emotional_style','social_distance','reaction_patterns','voice_examples','signature_phrases']],
  ['motivations','compass','动机',['motivations','core_values','desire','hobbies']],
  ['boundaries','shield-check','边界',['boundaries','taboos']],
  ['world','globe-2','世界',['world_name','era','tone','rules','scenes','network','world_extra','world','world_adaptation_mode','world_adaptation']],
  ['platform_names','messages-square','称呼',['platform_group_chat','platform_screen','platform_bilibili','platform_qzone','platform_library','platform_names']],
];
function renderGovernanceOriginal(){
  const role=product.role();
  const target=product.target();
  const connection=product.connection();
  const roleValue=typeof role?.role_id==='string'?role.role_id.trim():'';
  const roleLabel=roleValue|| (connection.state==='checking'?'正在识别角色':'尚未读取角色');
  const targetKind=target?.scope_kind==='group'?'群聊':'私聊';
  const targetLabel=target
    ?`${targetKind} · ${target.participant_id||target.group_id||target.target_id}`
    :'尚未读取会话对象';
  const connectionLabel=(connection.label||'连接状态未知').replace(/^小屋\s*·\s*/,'');
  const emblem=roleValue
    ?`<span>${escapeHTML(Array.from(roleValue)[0]||'')}</span>`
    :I('user-round');
  const canonNav=SELF_PROFILE_SECTIONS.map(([id,icon,label,fields])=>`<button type="button" class="self-canon-jump" data-profile-field="${id}" data-profile-fields='${escapeHTML(JSON.stringify(fields))}' data-profile-label="${label}" data-self-focus="${id}" data-complete="false" aria-label="${label}，待补充，打开对应设定"><span class="self-canon-jump-icon">${I(icon)}</span><span>${label}</span><i aria-hidden="true"></i></button>`).join('');
  const privateTarget=target?.scope_kind==='private';
  const relationshipEditor=privateTarget
    ?configEditors('relationshipProfileConfigWorkspace',['relationship_profile'],'当前关系资料')
    :`<div class="self-relationship-scope-note" role="status"><strong>关系资料只对私聊用户生效</strong><span>切换到一个已初始化的私聊对象后，可以分别设置称呼、关系和相处方式；群聊成员不会读取这份资料。</span>${button('选择私聊对象','data-go="manage" data-manage="host"','small')}</div>`;
  const relationshipDraftAction=privateTarget
    ?button(I('sparkles')+'<span>整理本关系</span>','data-role-profile-draft-open="relationship_profile"','small primary')
    :'<span class="self-relationship-disabled">请先选择私聊对象</span>';
  const showcase=`<section class="self-atlas" aria-label="当前角色身份展示" data-self-ready="${role?'true':'false'}">
    <div class="self-atlas-main">
      <div class="self-profile">
        <div class="self-emblem" aria-hidden="true">
          <span class="self-orbit self-orbit-a"></span><span class="self-orbit self-orbit-b"></span>
          <span class="self-emblem-core" data-profile-emblem data-profile-fallback="${escapeHTML(roleValue?Array.from(roleValue)[0]||'':'设')}">${roleValue?escapeHTML(Array.from(roleValue)[0]||''):I('user-round')}</span>
        </div>
        <div class="self-profile-copy">
          <p class="self-kicker"><span>SELF / PROFILE</span><i></i><span>ROLE STUDIO</span></p>
          <h2 data-profile-name data-profile-fallback="${escapeHTML(roleLabel)}">${escapeHTML(roleLabel)}</h2>
          <p class="self-profile-note">角色底色、生活细节与世界设定会共同塑造它的回应</p>
          <div class="self-live-state" data-state="${escapeHTML(connection.state||'unknown')}">
            <span class="self-live-dot" aria-hidden="true"></span>
            <span>${escapeHTML(role?'已识别当前角色':connectionLabel)}</span>
          </div>
        </div>
      </div>
      <dl class="self-coordinates">
        <div><dt>人格</dt><dd title="${escapeHTML(role?.persona_id||'未识别')}">${escapeHTML(role?.persona_id||'未识别')}</dd></div>
        <div><dt>会话</dt><dd title="${escapeHTML(targetLabel)}">${escapeHTML(targetLabel)}</dd></div>
        <div><dt>连接</dt><dd>${escapeHTML(connectionLabel)}</dd></div>
      </dl>
    </div>
    <div class="self-atlas-bottom" aria-label="角色速览">
      <div class="self-map-heading"><span>角色速览</span><span>从已保存档案实时整理</span></div>
      <div class="self-profile-signals">
        <button type="button" data-self-focus="identity"><span>身份</span><strong data-profile-signal="identity">正在读取…</strong>${I('arrow-up-right')}</button>
        <button type="button" data-self-focus="appearance"><span>识别点</span><strong data-profile-signal="appearance">正在读取…</strong>${I('arrow-up-right')}</button>
        <button type="button" data-self-focus="personality"><span>性格</span><strong data-profile-signal="personality">正在读取…</strong>${I('arrow-up-right')}</button>
        <button type="button" data-self-focus="voice"><span>口吻</span><strong data-profile-signal="voice">正在读取…</strong>${I('arrow-up-right')}</button>
        <button type="button" data-self-focus="world"><span>所在世界</span><strong data-profile-signal="world">正在读取…</strong>${I('arrow-up-right')}</button>
      </div>
    </div>
    <div class="self-canon-deck">
      <div class="self-canon-meter-head"><div><span>ROLE CANON / 01—08</span><strong>角色稳定档案</strong></div><div class="self-canon-summary"><b data-profile-count>— / —</b><small data-profile-status>正在读取设定状态</small></div></div>
      <div class="self-canon-progress" data-profile-progress role="progressbar" aria-label="已有角色档案资料项" aria-valuemin="0" aria-valuemax="1" aria-valuenow="0"><i data-profile-fill></i></div>
      <nav class="self-canon-map" aria-label="角色设定快捷入口">${canonNav}</nav>
    </div>
  </section>`;
  const tabs=[['profile','user-round-pen','角色档案','身份、外貌、性格、口吻与世界蓝图'],['relationship','heart-handshake','相处资料','当前角色与这位私聊用户'],['questionnaire','notebook-pen','人格底稿','读取 AstrBot 原文、编辑补充稿并保留版本'],['knowledge','book-open-text','世界知识','世界书与知识库引用来源']];
  return `<div class="self-page">${showcase}<section class="self-config" aria-label="自我设定">
    <header class="self-config-heading"><div><span>CHARACTER / 01—02</span><h2>角色设定</h2></div>
      <p>角色档案进入新对话；AstrBot 人格底稿与外部知识来源分别管理。</p></header>
    <nav class="self-workspace-tabs" role="tablist" aria-label="自我设定分区">${tabs.map(([id,icon,label,detail])=>`<button type="button" role="tab" id="self-tab-${id}" aria-controls="self-panel-${id}" aria-selected="${selfPane===id}" tabindex="${selfPane===id?'0':'-1'}" data-self-pane="${id}" class="self-workspace-tab${selfPane===id?' is-active':''}"><span class="self-workspace-tab-icon">${I(icon)}</span><span class="self-workspace-tab-copy"><strong>${label}</strong><small>${detail}</small></span>${I('arrow-up-right')}</button>`).join('')}</nav>
    <section class="self-workspace-panel self-profile-panel" id="self-panel-profile" role="tabpanel" aria-labelledby="self-tab-profile"${selfPane==='profile'?'':' hidden'}>
      <section class="self-draft-launch" aria-labelledby="selfDraftLaunchTitle">
        <span class="self-draft-launch-icon">${I('sparkles')}</span>
        <div><span>PERSONA → ROLE CANON</span><h3 id="selfDraftLaunchTitle">从人格底稿整理角色资料</h3>
          <p>把身份、外貌、性格、口吻、目标与世界设定整理成草稿，也可补充原文没有的确定设定。</p></div>
        <button class="button small primary" type="button" data-role-profile-draft-open>${I('sparkles')}<span>整理资料</span></button>
      </section>
      <div class="self-profile-editor-heading"><div><span>CHARACTER / CANON</span><h3>把“它是谁”写得具体</h3></div><p>角色档案跨会话共享；称呼与当前用户的关系单独保存。</p><div class="self-profile-editor-actions">${button('编辑相处资料','data-self-pane="relationship"','small')}${button(I('shirt')+'<span>打开衣柜</span>','data-go="manage" data-manage="output"','small')}</div></div>
      ${configEditors('roleProfileConfigWorkspace',['role_profile'],'角色稳定档案')}
    </section>
    <section class="self-workspace-panel self-relationship-panel" id="self-panel-relationship" role="tabpanel" aria-labelledby="self-tab-relationship"${selfPane==='relationship'?'':' hidden'}>
      <div class="self-relationship-heading"><div><span>RELATIONSHIP / ${privateTarget?'PRIVATE':'SCOPE'}</span><h3>这段关系，有自己的资料</h3></div><p>${privateTarget?escapeHTML(targetLabel):'当前是群聊对象，关系资料不会在群聊中启用。'}</p></div>
      <section class="self-draft-launch self-relationship-draft" aria-labelledby="selfRelationshipDraftTitle">
        <span class="self-draft-launch-icon">${I('heart-handshake')}</span>
        <div><span>PERSONA → RELATIONSHIP</span><h3 id="selfRelationshipDraftTitle">从人格底稿整理相处资料</h3>
          <p>只提取原文明确写出的称呼、用户信息、关系和互动方式；不确定的内容留空，生成后逐项检查。</p></div>
        ${relationshipDraftAction}
      </section>
      ${relationshipEditor}
      ${settingsJump('查看关系理解与人工审阅','identity')}
    </section>
    <section class="self-workspace-panel" id="self-panel-questionnaire" role="tabpanel" aria-labelledby="self-tab-questionnaire"${selfPane==='questionnaire'?'':' hidden'}>${renderPersonaPage()}</section>
    <section class="self-workspace-panel self-knowledge-panel" id="self-panel-knowledge" role="tabpanel" aria-labelledby="self-tab-knowledge"${selfPane==='knowledge'?'':' hidden'}>
      <div class="self-knowledge-heading"><div><span>WORLD / SOURCES</span><h3>世界知识与来源</h3></div><p>导入可引用资料，并控制它在对话中的使用范围。</p></div>
      ${configEditors('knowledgeConfigWorkspace',['knowledge'],'世界知识与来源')}
    </section>
  </section>${window.CompanionRoleProfileDraft?.markup?.()||''}</div>`;
}
function renderIdentityPageOriginal(){
  return pageSections('谁是谁，谁被允许',
    '相识目录按人沉淀，群与私聊是同一个人的不同窗口；待确认的关系理解要先过你这一关才生效。',
    [
    ['关系与权限','相识目录按人沉淀，群与私聊是同一个人的不同窗口。角色与人格绑定只读。',`${renderIdentity()}<section class="identity-member-clues" aria-labelledby="member-clues-heading"><div><h3 id="member-clues-heading">群聊成员线索</h3><p>为关系网中的成员补充可核实线索，供群聊识别成员时使用。</p></div>${configEditors('memberClueWorkspace',['knowledge'],'群聊成员线索')}</section>${configEditors('privateAccessWorkspace',['private_access'],'私聊默认权限')}`,
     'identity-directory'],
    ['熟人卡','为已经认识的对象维护一张简要卡片，帮助角色记住相处背景。',configEditors('personConfigWorkspace',['person'],'熟人卡'),
     'identity-person'],
    ['关系与情感','它对你和对别人的理解，以及它自己的感觉。待确认的先过你这一关才生效。',product.workspace('relationships'),
     'identity-feelings'],
    ],
    [['identity-directory','shield-check','关系与权限'],
     ['identity-person','contact-round','熟人卡'],
     ['identity-feelings','heart-handshake','关系与情感']]);
}
/* 主动与联系。
 *
 * 这一页此前是废的：正文里调了一个**从未定义**的 renderPreferences()，
 * 一执行就抛 ReferenceError，整页渲染中断——用户看到的是空白与错误。
 * 那个函数要挂的是 proactive.contact 这个 158 字段的大组（联系节奏、
 * 免打扰、各类主动契机、去重与配额），它四层都缺：后端没有 GroupEditor
 * 子类、SECTIONS 注册表没有条目、前端没有 spec 分区、页面没有挂载点。
 *
 * 四个触点现已补齐，158 项按 22 段渲染。上面那块「联系节奏」是现状与快速修改：
 * 它回答「此刻为什么没来找你」，也是唯一会随总开关签发主动联系授权的地方；
 * 下面那张卡是完整的设置面。同一个组只在这一页可写——决策页与表达页只留入口。 */
function renderContactPageOriginal(){return consoleSections([
  ['联系节奏','它什么时候来找你、什么时候不打扰。',
   `${consoleMountHead('安静时段与沉默门槛','改动从下一轮主动评估开始生效；开启总开关时会一并签发这个对象的主动联系授权。')}${renderRoleState('contact')}`],
  ['主动联系偏好','联系节奏、各类契机、外部事件源与每日额度；按本对象与角色的这一段关系保存。',
   `${consoleMountHead('四层继承','默认写入窗口层，安装 / 角色 / 关系层的值会被继承；两个关系级配额只能在安装 / 角色 / 关系层设置。')}${configEditors('contactPreferencesWorkspace',['proactive.contact'],'主动联系偏好')}`],
]);}
function renderMemoryPageOriginal(){return consoleSections([
  ['认知与记忆','它记得的事实、整理进度、来源与冷归档，以及按范围清理。',`${consoleMountHead('记忆与经历','整理与修复、事实治理、来源与经历、冷归档、迁移、范围清理。整理与事实视图每 8 秒自动刷新。')}${renderMemories()}`],
]);}
/* 模型页自带页头、页签与刷新控件；不再套配置控制台的子类统计与边界卡，
   避免「模型分配」说明块与真实工作区重复占据首屏。只保留分区卡片容器。 */
function renderModelsPage(){return `<div class="models-management-page"><section id="modelWorkspace" class="console-section" aria-label="任务模型配置">${consoleLoading('正在读取任务模型配置…')}</section><section class="models-budget-section" aria-labelledby="models-budget-heading"><div><h2 id="models-budget-heading">后台任务预算</h2><p>达到限额后暂停启动新的可选任务；已运行的任务会完成，交互回复不受影响。</p></div>${configEditors('budgetConfigWorkspace',['budget'],'后台任务预算')}</section></div>`;}
/* 治理与维护 = 账号与会话运行状态 + 备份与还原。风控与用量那两块本来就没有可写端点，
   旧版各放一张 boundaryCard 解释「为什么没有开关」；按「接不上就删」直接去掉。 */
function renderMaintenancePageOriginal(){
  return `<div class="maintenance-page"><section id="maintenanceWorkspace" aria-label="运行诊断与排障"></section></div>`;
}
function renderExpressionLearning(){
  return `<section id="expressionWorkspace" aria-label="表达学习设置">${consoleLoading('正在读取表达学习设置…')}</section>`;
}
/* 学习与反思。旧版这一页有 10 张 boundaryCard，全部是「某能力属于哪个子系统」
   的归属说明——用户在这里找不到任何可操作的东西。现在只留三块有真实端点的：
   表达学习（按对象或按群保存）、成长与技能、书架；
   其余归属说明全部删掉，改成指向真实页面的入口行。 */
function renderLearningPageOriginal(){
  return consoleSections([
    ['表达与说话习惯学习','从它已送达的回复里取样，学成规则前先给你过目；同一份设置按对象或按群分别保存。',`${consoleMountHead('取样与轮换','从角色自己已确认送达的回复里取样，转成待审候选；只有人工采纳的规则才会注入，且用过之后会被降权，让学到的规则轮流被用上。')}${renderExpressionLearning()}${configEditors('growthConfigWorkspace',['role_growth','role.growth.skills'],'成长与技能')}${settingsJump('风格提示词与表达规则','expression','候选的采纳、驳回与退役，以及每条已采纳规则被用过多少次。')}`],
    ['记忆沉淀与每日反思','反思按时间到点或手动续接，把来源提炼为事实与经历摘要。',`${consoleMountHead('记忆反思','来源 → 新记忆条目；增量、重复安全，不回写改写已成型记忆。')}${settingsJump('反思结果与记忆治理','memory','查看沉淀下来的事实、经历与整理进度。')}`],
  ]);
}
/* 需要一个具体对象与角色的配置组：后端按会话或按安装/角色保存。
   没有可用对象时不渲染假控件，只说明到哪里改。 */
/* 配置编辑器要么给出真实控件，要么给一句简短的行内提示。
   这里**不再**退回 boundaryCard——那是给开发看的合同说明，
   放进内容块里就是用户说的「垃圾桶」。缺条件时只说明去哪儿补。 */
function configEditors(id,kinds,title,note){
  void note;
  const hint = (text,retry) => `<p class="config-editors-hint">${I('info')}<span>${text}</span></p>${retry?'<div class="dialog-actions"><button class="button small" type="button" data-workspace-retry>重新读取</button></div>':''}`;
  if(typeof product.role()?.reply_api!=='string')return hint(`先在账号与会话中初始化一个对象与角色，${title}才会出现。`,true);
  return `<section id="${id}" class="config-editors" aria-label="${title}">${consoleLoading('正在读取设置…')}</section>`;
}
/* 目标未选时的整页引导：替代让每个挂载点各渲染一遍自己的空态。
   「桥还没到」不再是一句「请从管理界面打开」——宿主注入连接晚于脚本执行
   是正常时序，所以这里只说明还没读到，并给一个重新读取的入口。 */
function pageNeedsTarget(what){
  if(typeof product.role()?.reply_api!=='string')return `<div class="page-guide">${I('info')}<div><h2>先选一个会话对象和角色</h2><p>请先选择已初始化的私聊对象与角色。</p></div><div class="dialog-actions"><button class="button small" type="button" data-workspace-retry>重新读取</button><button class="button small" type="button" data-go="manage" data-manage="host">账号与会话</button></div></div>`;
  return "";
}
function mountConfigEditor(id,kinds,views){
  const mount=window.CompanionConfigEditors?.create(kinds,()=>document.getElementById(id),views);
  if(!mount)return null;
  mount.restore();mount.paint();mount.read();
  return mount;
}
function renderConfigEditors(){
  configEditorMounts.length=0;
  roleProfileConfigMount=null;
  relationshipProfileConfigMount=null;
  if($('#imageControlWorkspace'))configEditorMounts.push(mountConfigEditor('imageControlWorkspace',['quota','image_review']));
  if($('#reactionConfigWorkspace'))configEditorMounts.push(mountConfigEditor('reactionConfigWorkspace',['reaction']));
  if($('#budgetConfigWorkspace'))configEditorMounts.push(mountConfigEditor('budgetConfigWorkspace',['budget']));
  if($('#busyGateWorkspace'))configEditorMounts.push(mountConfigEditor('busyGateWorkspace',['busy_gate']));
  if($('#recallConfigWorkspace'))configEditorMounts.push(mountConfigEditor('recallConfigWorkspace',['recall']));
  if($('#screenConfigWorkspace'))configEditorMounts.push(mountConfigEditor('screenConfigWorkspace',['screen']));
  if($('#perceptionDatesWeatherWorkspace'))configEditorMounts.push(mountConfigEditor('perceptionDatesWeatherWorkspace',['proactive.contact'],{
    'proactive.contact':{sectionIds:['date','weather']}
  }));
  if($('#perceptionOnlineQueryWorkspace'))configEditorMounts.push(mountConfigEditor('perceptionOnlineQueryWorkspace',['proactive.contact'],{
    'proactive.contact':{sectionIds:['news','web','selflink']}
  }));
  if($('#personConfigWorkspace'))configEditorMounts.push(mountConfigEditor('personConfigWorkspace',['person']));
  /* 熟人卡与新用户默认权限统一在「关系与权限」页编辑。 */
  if($('#privateAccessWorkspace'))configEditorMounts.push(mountConfigEditor('privateAccessWorkspace',['private_access']));
  if($('#growthConfigWorkspace'))configEditorMounts.push(mountConfigEditor('growthConfigWorkspace',['role_growth','role.growth.skills']));
  if($('#knowledgeConfigWorkspace'))configEditorMounts.push(mountConfigEditor('knowledgeConfigWorkspace',['knowledge'],{
    knowledge:{sectionIds:['import','inject']}
  }));
  if($('#memberClueWorkspace'))configEditorMounts.push(mountConfigEditor('memberClueWorkspace',['knowledge'],{
    knowledge:{sectionIds:['members'],title:'群聊成员线索',note:'只在群聊输入中提供已登记的成员线索。'}
  }));
  if($('#roleProfileConfigWorkspace')){
    roleProfileConfigMount=mountConfigEditor('roleProfileConfigWorkspace',['role_profile']);
    configEditorMounts.push(roleProfileConfigMount);
  }
  if($('#relationshipProfileConfigWorkspace')){
    relationshipProfileConfigMount=mountConfigEditor('relationshipProfileConfigWorkspace',['relationship_profile']);
    configEditorMounts.push(relationshipProfileConfigMount);
  }
  if($('#lifeConfigWorkspace'))configEditorMounts.push(mountConfigEditor('lifeConfigWorkspace',['life']));
  if($('#libraryConfigWorkspace'))configEditorMounts.push(mountConfigEditor('libraryConfigWorkspace',['library']));
  if($('#contentAuthoringWorkspace'))configEditorMounts.push(mountConfigEditor('contentAuthoringWorkspace',['content.authoring']));
  if($('#materialControlWorkspace'))configEditorMounts.push(mountConfigEditor('materialControlWorkspace',['photo.reference','wardrobe']));
  if($('#groupParticipationConfigWorkspace'))configEditorMounts.push(mountConfigEditor('groupParticipationConfigWorkspace',['group_participation'],{
    group_participation:{sectionIds:['atmosphere','interjection','repeat']}
  }));
  if($('#groupDenoiseWorkspace'))configEditorMounts.push(mountConfigEditor('groupDenoiseWorkspace',['group_participation'],{
    group_participation:{sectionIds:['denoise'],title:'群聊表达去噪',note:'只影响群聊回复的表达腔调。'}
  }));
  /* proactive.contact（158 项、四层）同样长期是「编辑器与声明都在、却没有挂载点」
     的缺口——它连编辑器与声明都没有。落主动与联系页，全页只有这一处可写。 */
  if($('#contactPreferencesWorkspace'))configEditorMounts.push(mountConfigEditor('contactPreferencesWorkspace',['proactive.contact']));
  /* QQ 空间的开关与节流（qzone 组）只挂在行动页的 QQ 空间区块里。
     挂不上时不留一个永远转圈的「正在读取设置…」——换成一句实话，
     见 qzoneConfigUnavailable。 */
  const qzoneConfigHost=$('#qzoneConfigWorkspace');
  if(qzoneConfigHost){
    const mount=mountConfigEditor('qzoneConfigWorkspace',['qzone']);
    if(mount)configEditorMounts.push(mount);else qzoneConfigUnavailable(qzoneConfigHost);
  }
}
document.addEventListener('companion:role-profile-updated',()=>roleProfileConfigMount?.read?.());
document.addEventListener('companion:relationship-profile-updated',()=>relationshipProfileConfigMount?.read?.());
function renderPersonaPage(){return product.workspace("persona");}
function renderHostWorkspace(){return product.workspace("host");}
function renderAppearancePageOriginal(){
  return `<div class="settings-heading"><div><h2>外观与设置</h2><p>拓展页自身的显示方式；主题与显示维度保存在当前浏览器，并同步到已打开的宿主工作区。</p></div>${chip('仅影响拓展页','lavender')}</div><section class="panel content-panel appearance-card"><div data-appearance-inline>${appearancePanel()}</div></section><div class="settings-note">${I('info')}这里不修改插件业务配置。主题只改变拓展页配色与排版，不写入角色资料，也不影响消息发送。</div>`;
}
/* 每页一句用户语言说明它管什么；不再用「配置子类/读写合同」这类内部词汇。 */
const manageSubtitles={
  perception:'角色能看到、听到、读到的信息。',
  decision:'群聊中判断何时回应、如何参与并守住边界。',
  action:'除回复以外的行为：生活、游玩与现实设备。',
  contact:'角色何时主动联系，以及如何安排联系节奏。',
  output:'角色产出的内容：画面、作品与文本。',
  expression:'角色怎么说话：文字风格、语音、表情与投递方式。',
  governance:'角色人格草稿与它可以引用的世界资料。',
  identity:'管理相识的人、关系记录与私聊默认权限。',
  memory:'查看记忆事实、经历、来源与整理状态。',
  learning:'审核表达学习，并管理角色成长与技能。',
  models:'分配各类任务使用的模型与后台工作预算。',
  setup:'把角色接上你指定的会话对象。做完这一步它才能开始工作。',
  host:'发现 Bot 账号、人格和会话窗口，并管理它们的绑定与运行。',
  maintenance:'查看运行诊断与排障状态。',
  data:'管理资料来源、备份与还原。',
  appearance:'调整陪伴小屋页面的主题与显示偏好。',
};
/* 分发表只保留 manageTabs 里的十六个页签。
   growth/base/state/reply/preferences 五个死键已删——它们既不在侧栏、
   也不被 configLink() 指向，留着只会让旧深链接渲染出重复页。
   renderRoleState 由状态页、生活挂历与主动联系页挂载；renderReply 由表达页挂载，
   其中的群聊回应分区通过同一适配器单独挂到决策页。
   它们的宿主仍在使用，不要随已清理的旧路由入口一起删除。 */
/* 2026-09-29 整理：除「首页」与「模型与连接」外，各页内容暂时清空，
   等待按新设计稿逐页重排。原实现整份备份于
   data/companion_v2_page_backups/20260929-before-page-clear/（插件扫描目录之外）。
   清空方式：原渲染函数整体更名保留（*Original），页签、manageSubtitles、
   mountConfigEditor 挂载链与页面模块原样保留——恢复时把函数名换回即可。 */
function clearedConsole(label){
  return consoleSections([[label,'这一页的内容已暂时清空，等待按新设计稿重排。',
    `<div class="console-note-inline">${I('info')}<span>原功能已完整备份，可随时恢复；当前请使用小屋首页与模型与连接页。</span></div>`]]);
}
function clearedNote(){
  return `<div class="console-note-inline" style="margin:18px 0">${I('info')}<span>这一页的内容已暂时清空，等待按新设计稿重排；原功能已完整备份，可随时恢复。</span></div>`;
}
/* 2026-09-30 接回：内容清空期间这一页只渲染一句占位，实现整体保留在 renderPerceptionOriginal。挂载点与挂载链从未动过，所以换回名字即可恢复。 */
function renderPerception(){return renderPerceptionOriginal();}
/* 2026-09-30 接回：内容清空期间这一页只渲染一句占位，实现整体保留在 renderDecisionOriginal。挂载点与挂载链从未动过，所以换回名字即可恢复。 */
function renderDecision(){return `<section id="decisionWorkspace" class="decision-workspace" aria-label="决策与对话上下文">${consoleLoading('正在读取当前角色…')}</section>`;}
/* 2026-09-30 接回：内容清空期间这一页只渲染一句占位，实现整体保留在 renderActionOriginal。挂载点与挂载链从未动过，所以换回名字即可恢复。 */
function renderAction(){return renderActionOriginal();}
/* 2026-09-30 接回：内容清空期间这一页只渲染一句占位，实现整体保留在 renderOutputOriginal。挂载点与挂载链从未动过，所以换回名字即可恢复。 */
function renderOutput(){return renderOutputOriginal();}
/* 2026-09-30 接回：内容清空期间这一页只渲染一句占位，实现整体保留在 renderExpressionOriginal。挂载点与挂载链从未动过，所以换回名字即可恢复。 */
function renderExpression(){return renderExpressionOriginal();}
/* 2026-09-30 接回：内容清空期间这一页只渲染一句占位，实现整体保留在 renderGovernanceOriginal。挂载点与挂载链从未动过，所以换回名字即可恢复。 */
function renderGovernance(){return renderGovernanceOriginal();}
/* 2026-09-30 接回：内容清空期间这一页只渲染一句占位，实现整体保留在 renderIdentityPageOriginal。挂载点与挂载链从未动过，所以换回名字即可恢复。 */
function renderIdentityPage(){return renderIdentityPageOriginal();}
/* 主动与联系。整页交给 contact-page.js：它的主体是一个钟面（一天 24 格的节律），
   套进配置控制台的分区卡片会把钟面压成一张卡里的图，所以它自带页头与轨道。
   挂载点在 render() 的 manage 分支里，与记忆与经历同一套处理。 */
function renderContactPage(){return `<section id="contactWorkspace" class="contact-workspace" aria-label="主动与联系工作区"></section>`
  +consoleSections([['忙碌时的回复与联系','角色忙碌时，私聊回复会顺延，普通主动联系会暂停并等待恢复缓冲。',
    configEditors('busyGateWorkspace',['busy_gate'],'忙碌处理')]]);}
/* 记忆与经历。与主动与联系同一套处理：整页交给 memory-page.js
   （左侧视图轨道 + 右侧档案库，自带页头，套进配置控制台的分区卡片
   会把它压成卡里的一张图），这里只渲染挂载容器，
   mount/unmount 由 mountPanelWorkspaces() 统一负责。 */
function renderMemoryPage(){
  const records=memoryWorkspaceRoute==='records';
  return `<div class="memory-route">
    <div class="memory-route-tabs" role="tablist" aria-label="记忆页面">
      <button id="memory-route-records" type="button" role="tab" class="memory-route-tab${records?' is-active':''}" data-memory-route="records" aria-selected="${records}" aria-controls="memoryWorkspace" tabindex="${records?'0':'-1'}">记忆与经历</button>
      <button id="memory-route-settings" type="button" role="tab" class="memory-route-tab${records?'':' is-active'}" data-memory-route="settings" aria-selected="${!records}" aria-controls="memorySettingsHost" tabindex="${records?'-1':'0'}">记忆策略</button>
    </div>
    ${records
      ? '<section id="memoryWorkspace" class="memory-workspace" aria-label="记忆与经历工作区"></section>'
      : `<section id="memorySettingsHost" class="memory-settings-workspace" aria-label="记忆策略设置">${consoleLoading('正在读取记忆策略…')}</section>`}
  </div>`;
}
/* 学习与反思。旧版这一页有 10 张 boundaryCard，全是「某能力属于哪个子系统」
   的归属说明——用户在这里找不到任何可操作的东西。现在分两半：
   上半是成长的培育轨道（learning-page.js，自带页头与分区轨道），
   下半保留三块确实有端点、但归属别处的设置：表达学习、成长与技能、书架。
   轨道不能像联系页那样整页交出去，因为那三块是这一页的既有内容。 */
function renderLearningPage(){
  return pageNeedsTarget('成长记录')
    + `<section id="learningWorkspace" class="learning-workspace" aria-label="学习与反思工作区"></section>`
    + consoleSections([
      ['语义理解与群词义','管理语义召回、群聊词义整理和学习素材；表情素材与表情检索已移到表达页。',`<div id="semanticLearningWorkspace" class="learning-semantic-workspace">${consoleLoading('正在读取语义配置…')}</div>`],
      ['表达与说话习惯学习','从它已送达的回复里取样，学成规则前先给你过目；同一份设置按对象或按群分别保存。',`${renderExpressionLearning()}${configEditors('growthConfigWorkspace',['role_growth','role.growth.skills'],'成长与技能')}${settingsJump('风格提示词与表达规则','expression','候选的采纳、驳回与退役，以及每条已采纳规则被用过多少次。')}`],
      ['记忆沉淀与每日反思','反思按时间到点或手动续接，把来源提炼为事实与经历摘要。',`${settingsJump('反思结果与记忆治理','memory','查看沉淀下来的事实、经历与整理进度。')}`],
    ]);
}
/* 2026-09-30 接回：内容清空期间这一页只渲染一句占位，实现整体保留在 renderMaintenancePageOriginal。挂载点与挂载链从未动过，所以换回名字即可恢复。 */
function renderMaintenancePage(){return renderMaintenancePageOriginal();}
/* 2026-09-30 接回：内容清空期间这一页只渲染一句占位，实现整体保留在 renderSetupPageOriginal。挂载点与挂载链从未动过，所以换回名字即可恢复。 */
function renderSetupPage(){return renderSetupPageOriginal();}
/* 2026-09-30 接回：内容清空期间这一页只渲染一句占位，实现整体保留在 renderHostPageOriginal。挂载点与挂载链从未动过，所以换回名字即可恢复。 */
function renderHostPage(){return renderHostPageOriginal();}
function renderAppearancePage(){
  /* 容器 + 挂载点。真正的界面在 appearance-page.js。
     与旧内联面板的差别：那一版把六个主题平铺成两列，选了之后除了色卡上
     的小方块变色，屏幕上没有任何别的反馈——密度、圆角、字号三项更是完全
     看不到效果。新页用一块"预览窗"承载四个维度，改一下就能看见。 */
  return `<section id="appearanceWorkspace" class="appearance-workspace" aria-label="外观与设置"></section>`;
}
/* 2026-09-30 接回：内容清空期间这一页只渲染一句占位，实现整体保留在 renderDataOriginal。挂载点与挂载链从未动过，所以换回名字即可恢复。 */
function renderData(){return renderDataOriginal();}
/* 旧路由 memories 的整页视图（生活观察里的「查看记忆与经历」按钮仍指向它）：
   与 renderMemoryPage 同一个容器，挂载逻辑在 render() 的 fullPage 分支。 */
function renderMemories(){
  return renderMemoryPage();
}
function renderManage(){const label=manageTabs.find(([id])=>id===manageTab)?.[2]||'账号与会话';const subtitle=manageSubtitles[manageTab]||'当前对象与角色的专题设置。';return pageHeading(label,subtitle,`<div class="page-actions">${button(I('house')+' 回到小屋','data-go="life"')}</div>`)+`<div class="workspace">${({perception:renderPerception,decision:renderDecision,action:renderAction,output:renderOutput,expression:renderExpression,governance:renderGovernance,identity:renderIdentityPage,contact:renderContactPage,memory:renderMemoryPage,models:renderModelsPage,maintenance:renderMaintenancePage,learning:renderLearningPage,setup:renderSetupPage,host:renderHostPage,appearance:renderAppearancePage,data:renderData}[manageTab])()}</div>`;}
/* 首次使用：渲染壳，真正的步骤由 setup-guide.js 在挂载后填进来。
 *
 * 这里原先有一个 product 的 hosted 早退分支，会渲染「从管理界面打开就能开始设置 /
 * 当前是静态预览」。那句话描述的是页面自己没接上，而不是用户需要做什么——
 * 而桥只是注入得比脚本晚，所以它在正经的拓展页里也出现过。
 * 现在直接渲染外壳：setup-guide 自己会去等桥、并在真的等不到时给出重试，
 * 那是这个页面唯一该说的话。 */
function renderSetupPageOriginal(){
  return `<div id="setupGuideHost" class="setup-guide-host">${consoleLoading('正在读取设置状态…')}</div>`;
}
function mountSetupGuide(){
  const node=$('#setupGuideHost');
  if(node&&window.CompanionSetup)window.CompanionSetup.mount(node);
}
function unmountSetupGuide(){window.CompanionSetup?.unmount();}
function renderHostPageOriginal(){
  /* 缺宿主目录时 renderHostWorkspace 自己会给一条引导，不再用
     consoleSections 在外面再包一层——那会渲染出「分区里套分区」。
     两套宿主模式（单目标 staging / 多目标共享宿主）的选择权在后端，
     页面按 product.targetsMode() 只读呈现，不自己做分支。 */
  return renderHostWorkspace();
}
/* 资料与维护 = 三件事：各处记录的去向（入口汇集）、账号与会话运行状态、备份与还原。
 *
 * 备份那一块曾经只是一张 boundaryCard 解释「为什么没有入口」——但后端
 * backup_api.py 有六条真实路由和一台两阶段状态机，从来没被任何页面调过。
 * 属于「能接却没接」，所以接上：真实工作区在 backup-page.js。
 *
 * 备份曾经只在单目标模式下给入口：那时多目标不注册 BackupWebAPI，给了就是
 * 必然失败的按钮。现在两种模式都注册，多目标的加载路径也在开库前应用暂存还原
 * （`multi_controller._open`），所以入口不再按模式分支——范围由还原预览里
 * 那句「会影响 N 个目标 / M 个角色」说清（后端随预览一并下发）。 */
function renderDataOriginal(){
  /* 「宿主目录还没读到」不是一种模式，只是一次还没返回的读取。
     原先这里落进一套「预览数据」管理（导出预览设置 / 恢复初始预览），
     那是本地示例数据的操作台，在真实宿主里也会出现。现在只说明状态
     并给重新读取的入口。 */
  if(!product.scopeKey())return pageSections('资料与维护',
    '宿主目录还没有读到。宿主注入连接通常比页面脚本晚几秒，重新读取一次即可。',
    [['读取宿主目录','',
      `<div class="dialog-actions"><button class="button small" type="button" data-workspace-retry>重新读取</button><button class="button small" type="button" data-go="manage" data-manage="host">账号与会话</button></div>`,
      'data-directory']]);
  /* 「记忆与生活」那一组跳转行搬去治理与维护页——两页都画同一组入口，
     会出现两处说法。这里只留资料本身的去向（备份与还原）与各处记录的入口。 */
  return pageSections('资料放在哪里',
    '快照覆盖整个安装，不与旧版共用数据根。这里也汇集各处记录的入口。',
    [
    ['备份与还原','快照覆盖整个安装。还原是两阶段的：先暂存，重启宿主后才生效，暂存前会自动留一份安全副本。',
     `<div id="backupWorkspace">${consoleLoading('正在读取快照列表…')}</div>`,
     'data-backup'],
    ['各处记录的入口','它记下的东西分散在几处，这里是统一入口。',
     `<div class="console-rows"><div class="console-row"><span class="console-row-icon">${I('orbit')}</span><span class="console-row-main"><strong>记忆整理与遗忘</strong><small>事实纠错、修订审阅、范围清理与来源检索。</small></span>${button('打开记忆与经历','data-go="memories"','small')}</div><div class="console-row"><span class="console-row-icon">${I('notebook-pen')}</span><span class="console-row-main"><strong>日记与生活</strong><small>作息、日记、阅读与执行记录。</small></span>${button('打开日记与生活','data-life="diary"','small')}</div><div class="console-row"><span class="console-row-icon">${I('sparkles')}</span><span class="console-row-main"><strong>学习与反思</strong><small>表达学习、成长与技能、每日反思。</small></span>${button('打开学习与成长','data-manage-jump="learning"','small')}</div></div>`,
     'data-records'],
    ],
    [['data-backup','database','备份与还原'],
     ['data-records','archive','各处记录的入口']]);
}

function renderIdentity(){
  /* 身份与权限的实际数据在 identity 工作区（role_work 的真实端点）。
     这里原先有一份用 config-snapshot.js 读出来的静态摘要兜底，
     它写的是「配置中的角色 · 当前预览空间」「操作者权限尚未读取」——
     在真实宿主里也会出现。现在只保留工作区本身，读不到就说明读不到。 */
  const workspace=product.identityMarkup()+product.workspace('identity');
  return workspace||`<div class="page-guide">${I('info')}<div><h2>身份与权限</h2><p>未读取到宿主目录。</p></div><div class="dialog-actions"><button class="button small" type="button" data-workspace-retry>重新读取</button></div></div>`;
}
/* 这里曾有第二份 renderData 定义（settings-heading 风格，与上面那一份同名）。
   同名顶层函数声明不报错，后声明的静默覆盖先声明的——两份都在时上面那份
   是死代码，页面实际渲染的是旧风格。已删除，只保留上面 consoleSections 那一份。 */

/* 设备目录、房间与动作记录由扩展页面读取；V2 手机摘要的会话授权在本页管理。 */
const providerEntries={
  reality:{name:'现实触及',plugin:'astrbot_plugin_reality_companion',page:'reality-companion',note:'设备、场所、镜头与声音的授权和动作记录都在现实触及页面。'},
  together:{name:'一起房间',plugin:'astrbot_plugin_together_companion',page:'一起房间',note:'房间正本由 Together 管理；V2 负责身份授权与邀请编排。'},
};
function providerEntryAddress(id){
  const spec=providerEntries[id],provider=product.provider(id);
  if(!spec||!provider?.installed)return '';
  const route=provider.pages?.includes(spec.page)?`/#/plugin-page/${encodeURIComponent(spec.plugin)}/${encodeURIComponent(spec.page)}`:'/#/extension/plugins';
  return new URL(route,location.href).href;
}
function providerEntryMarkup(id,entries,closing){
  const spec=providerEntries[id];if(!spec)return '';
  const address=providerEntryAddress(id);
  /* 拿不到地址时不放 disabled 按钮——那会变成一排永远点不动的控件，
     用户看不出是「还没读到」还是「不能用」。改成一句说明。 */
  if(!address)return `<p>未读取到页面入口。</p><div class="dialog-actions"><button class="button small" type="button" data-workspace-retry>重新读取</button>${button('能力目录','data-home-section="furniture"','small')}</div>`;
  const links=entries.map(label=>`<a class="button small" href="${escapeHTML(address)}" target="_blank" rel="noopener noreferrer" title="在${spec.name}页面${label}">${label} ${I('arrow-up-right')}</a>`).join('');
  const field=`<div class="perception-address" style="margin:12px 0 0"><label for="provider-url-${id}">${spec.name}页面地址</label><div><input id="provider-url-${id}" readonly value="${escapeHTML(address)}" aria-label="${spec.name}页面地址"><button class="button small" data-copy-address="provider-url-${id}" title="复制${spec.name}页面地址">${I('copy')}<span>复制地址</span></button></div></div>`;
  const scopeNote=id==='reality'?'本页的手机摘要读取授权作用于所选 V2 私聊窗口；设备动作与采集设置在现实触及页面管理。':'本页提供房间入口，通话与房间授权在一起房间页面管理。';
  return `${field}<div class="dialog-actions">${links}</div>`;
}
/* Reality / Together 的能力面。
 *
 * 这两个扩展的真实清单（设备、场所、镜头与声音覆盖、最近动作、房间、
 * 成员、素材、进度）都在各自的插件页面里，本页拿不到。原先的写法是给
 * 每一项配一个「示例 · 客厅主灯」这样的假值，宿主在读时也照显示——于是
 * 用户在自己家里看到的是别人家的客厅。现在只写**口径**（一件事怎么算数、
 * 什么情况下不会被自动重发），具体值一律指向扩展页面。
 */
function capabilitySurface(key){
  if(!['reality','together'].includes(key))return '';
  const open=(label,attrs)=>`<a class="button small" ${attrs}>${label} ${I('arrow-up-right')}</a>`;
  const address=providerEntryAddress(key);
  const goto=label=>address?open(label,`href="${escapeHTML(address)}" target="_blank" rel="noopener noreferrer"`):button(label,'data-workspace-retry');
  const provider=product.provider(key)||{};
  const stateLabel=product.statusLabel(provider.integration_state||'unknown');
  const statusClass=provider.integration_state==='connected'?'ready':provider.integration_state==='degraded'?'warn':'idle';
  const hero=`<section class="extension-status-hero ${statusClass}"><div class="extension-status-icon">${I(key==='reality'?'radio':'heart-handshake')}</div><div class="extension-status-copy"><span class="section-kicker">EXTENSION STATUS</span><h3>${escapeHTML(provider.label||provider.title||key)}</h3><p>${escapeHTML(provider.reason||'状态来自扩展公开目录。')}</p></div><span class="extension-status-chip">${escapeHTML(stateLabel)}</span></section>`;
  const steps=[['01','扩展','已发现'],['02','页面','真实入口'],['03','会话','按目标授权']];
  const flow=`<div class="extension-flow" aria-label="拓展连接阶段">${steps.map((step,index)=>`<div class="extension-flow-step ${index<2?'done':''}"><b>${step[0]}</b><span>${step[1]}</span><small>${step[2]}</small></div>${index<steps.length-1?'<i class="extension-flow-line"></i>':''}`).join('')}</div>`;
  const actions=`<div class="extension-actions"><div><strong>下一步</strong><p>${address?'打开扩展页面管理真实资源与权限。':'等待扩展页面被宿主发现。'}</p></div><div class="dialog-actions">${goto(address?'打开拓展页面':'重新读取')}${button('回到能力目录','data-home-section="furniture"','small')}</div></div>`;
  if(key==='reality')return hero+flow+`<section class="extension-live-panel"><h3>当前会话能力授权</h3><p>八项手机、摄像头、设备读取与动作回执能力按项授权。</p>${button('管理会话授权','data-perception-config="screen"','small')}</section><h3>原生能力</h3>`
    +definitions([
      ['手机摘要','读取已配对手机的位置、终端状态、活动与健康摘要。'],
      ['摄像头单帧','仅按本轮明确请求读取一帧并返回识别摘要。'],
      ['设备读取','分开开放设备目录与单设备状态查询，仅返回设备档案允许公开的字段。'],
      ['设备动作','电源控制和可写属性动作分开授权，并继续遵守 Reality 的设备白名单与管理设置。'],
      ['操作回执','查询原操作或取消尚未派发的操作；不会重放已派发或结果未知的动作。'],
    ])
    +`<h3>授权范围</h3>`
    +definitions([
      ['当前对象','每项授权只作用于已选择的 Bot、角色和绑定私聊窗口。'],
      ['提供方设置','V2 会话授权不会替代 Reality 自身的启用状态、设备映射、白名单或用户确认。'],
      ['动作结果','只有提供方返回确认才显示成功；结果未知时保留原操作并查询，不自动重发。'],
    ])
    +providerEntryMarkup('reality',['查看设置','查看操作记录','管理设备映射'],'提供方设置与设备映射在现实触及页面管理');
  return hero+flow+`<h3>当前房间与模式</h3>`
    +definitions([
      ['当前房间',`当前房间在一起房间页面查看 ${goto('打开一起房间')}`],
      ['可用模式','通话 / 一起看 / 工作协同 / 一起读小说'],
      ['正在使用',`以房间实际使用的模式为准 ${goto('查看房间模式')}`],
      ['参与者',`房间成员与各自身份在一起房间页面查看 ${goto('查看成员')}`],
    ])
    +`<h3>素材与进度</h3>`
    +definitions([
      ['素材',`当前素材与来源在一起房间页面查看 ${goto('查看素材')}`],
      ['进度',`以房间实际显示的进度为准 ${goto('查看进度')}`],
      ['进度口径','进度由房间自己记录；本页不推算，也不用一个数字代表文字与语音都已完整送达'],
    ])
    +`<h3>邀请与加入</h3><p>在 V2 陪伴对话中创建或接受邀请码。受邀成员进入同一实时房间；各自身份与摄像头输入分开，私人聊天和历史不会随房间共享。</p>`
    +providerEntryMarkup('together',['查看房间成员'],'成员、模式和房间素材由一起房间管理')+actions;
}
function definitions(rows){return `<dl class="definition-list">${rows.map(([label,value])=>`<div class="definition-row"><dt>${label}</dt><dd>${value}</dd></div>`).join('')}</dl>`;}
function closeDetail(){const d=$('#detailDialog');if(d.open)d.close();}
function showDetail(id){
  if(id==='arrange'){openRoomEditor();return;}
  /* 详情弹窗的**两种去向**，没有第三种：
       1. 这件事有真实工作区（life / identity / memory / 各扩展页面）
          → 关掉弹窗、跳到那一页，把标签也带上。
       2. 本页只有一个入口（「去哪儿做这件事」）
          → 说清去哪儿，链接就是那个入口。

     这里原先是一大串 if/else，每个分支渲染一份写死的示例内容：示例日记
     「阳光落在书页上」、示例原稿、两张示例照片、「望 Shu（示例）」角色、
     「仅保存到此预览」的编辑表单……宿主接上之后它们照样显示，用户分不清
     哪些是真实记录。现在凡是能接的都跳真实工作区，接不上的直接不到位。 */
  const lifeEntries={desk:'archive',diary:'archive','diary-edit':'archive',sleep:'sleep',bed:'sleep',reading:'reading',lounge:'reading'};
  const openLife=tab=>{
    closeDetail();route='life';lifeTab='diary';render();
    const frame=document.querySelector('.product-workspace');
    if(frame)frame.dataset.workspaceTab=tab;
    product.mountWorkspace();
  };
  /* 工作区还没挂上（宿主目录没读到）时，不弹一份假的，只说清状态。 */
  const waiting=(what,tab='')=>{
    const address=tab?product.workspaceAddress('life',tab):'';
    return {title:what,body:`<p>宿主目录还没有读到，${what}需要它才能加载。</p><div class="dialog-actions"><button class="button small" type="button" data-workspace-retry>重新读取</button><button class="button small" type="button" data-go="manage" data-manage="host">账号与会话</button></div>${address?`<p class="muted-text">也可以直接打开工作区：<a href="${escapeHTML(address)}" target="_blank" rel="noopener noreferrer">${escapeHTML(address)}</a></p>`:''}`};
  };
  if(lifeEntries[id]){
    if(product.workspace('life',lifeEntries[id])){openLife(lifeEntries[id]);return;}
    const detail=waiting(({desk:'日记与便签',diary:'日记与生活','diary-edit':'日记与生活',sleep:'睡眠与梦境',bed:'睡眠与梦境',reading:'阅读记录',lounge:'阅读记录'})[id],lifeEntries[id]);
    openDetailDialog(detail.title,detail.body);return;
  }
  if(id==='growth'){navigate('manage','growth');return;}
  if(id==='profile'||id==='roles'||id==='world'||id==='person-self'||id==='permissions'||id.startsWith('person-')){
    /* 角色、权限与人物关系都由 identity / relationships 工作区承担。 */
    navigate('manage',id==='person-self'||id.startsWith('person-')?'identity':'identity');return;
  }
  const cap=id==='books'?'content':id==='album'?'image':id==='discoveries'?'news':id.startsWith('cap-')?id.slice(4):null;
  if(cap&&![].includes(cap)){
    const provider=product.providerDetail(cap);
    if(provider){openDetailDialog(provider.title,provider.body+capabilitySurface(cap));return;}
  }
  /* 兜底：说清这件事在哪做，而不是编一段内容。 */
  openDetailDialog('这件事在别处',`<p>这个入口指向的工作区还没有读到。可以先去下面这几处：</p><div class="dialog-actions">${button('日记与生活','data-life="diary"')}${button('记忆与经历','data-go="memories"')}${button('能力目录','data-home-section="furniture"')}</div>`);
}
/* 弹窗的统一出口。所有分支都从这里渲染，免得每条分支各写一遍头部。 */
function openDetailDialog(title,body){
  const dialog=$('#detailDialog');
  if(!dialog.open){dialogReturnFocus=document.activeElement;dialogReturnFurniture=dialogReturnFocus?.dataset?.furniture||'';}
  lastDetail=title;
  $('#dialogContent').innerHTML=`<header class="dialog-head"><h2 id="dialogTitle">${escapeHTML(title)}</h2><button class="icon-button" data-close-detail aria-label="关闭详情">${I('x')}</button></header><div class="dialog-body">${body}</div>`;
  icons();if(!dialog.open)dialog.showModal();dialog.scrollTop=0;
}

const searchIndex=[
  ['生活观察','日记、梦境、生活轨迹、状态与交互影响','scan-eye','home-section','observation'],['家具与能力','基础生活与拓展家具，启用状态和连接','armchair','home-section','furniture'],
  ['首页与小屋','生活总览、观察与家具能力','house','life','home'],['日记与生活','日记、睡眠、阅读与作息配置','notebook-pen','life','diary'],['人物与关系','当前对象的关系与情绪片段','users-round','manage','identity'],['共同经历','记录、原话、来源与记忆策略','orbit','manage','memory'],['作品与相册','原稿、照片与收藏','images','home-section','furniture'],['一起活动','共读、棋桌与通话','coffee','home-section','furniture'],['能力目录','可选拓展当前能不能用','blocks','home-section','furniture'],
  ['感知','环境、消息与媒体来源','scan-eye','manage','perception'],['决策','本轮上下文与群聊参与判断','brain','manage','decision'],['行动','生活行为与社交发布','play','manage','action'],['产出','图像生成与创作作品','shapes','manage','output'],['表达','文本、语音、表情与投递','message-square-more','manage','expression'],['自我','世界知识、角色设定与自身档案','user-round','manage','governance'],
  ['开始使用','首次连接、选择对象与决定是否发送','rocket','manage','setup'],['人格问卷','结构化整理角色设定并保存多个版本','notebook-pen','manage','persona'],['关系与权限','角色、人物、群与授权','shield-check','manage','identity'],['外观与设置','主题、密度、圆角、字号与动效','palette','manage','appearance'],['主动联系','主动契机、联系节奏与免打扰','heart-handshake','manage','contact'],['记忆与经历','事实、原话与群词义','orbit','manage','memory'],['模型与连接','公共模型与任务路由','sliders-horizontal','manage','models'],['运行诊断','运行状态与排障','settings-2','manage','maintenance'],['便签','下次去书店，找一本植物随笔','sticky-note',null,'notes'],['窗边的一页','照片与相关经历','image',null,'photo-window'],['创作书架','Content 能力状态','library-big',null,'cap-content'],['现实触及','Reality 设备与授权','radio','manage','perception'],
];
function renderSearch(){const query=$('#globalSearch').value.trim().toLowerCase();const results=searchIndex.map((data,index)=>({data,index})).filter(({data})=>(data[3]!==null||String(data[4]).startsWith('cap-'))&&data.slice(0,2).join(' ').toLowerCase().includes(query));$('#searchResults').innerHTML=results.length?results.map(({data,index})=>`<button class="search-result" data-search-result="${index}">${I(data[2])}<span><strong>${data[0]}</strong><small>${data[1]}</small></span></button>`).join(''):'<div class="search-empty">没有找到相关内容，试试“日记”或“能力”。</div>';icons();}
function openSearch(){if($('#detailDialog').open)closeDetail();$('#globalSearch').value='';renderSearch();$('#searchDialog').showModal();$('#globalSearch').focus();}
document.addEventListener('click',event=>{
  const el=event.target.closest('button,a');if(!el)return;
  if(handleRoomEditorClick(el))return;
  if(el.dataset.selfPane){
    const pane=el.dataset.selfPane;
    if(!['profile','relationship','questionnaire','knowledge'].includes(pane))return;
    if(route==='manage'&&manageTab==='governance'&&selfPane===pane){el.focus({preventScroll:true});return;}
    navigate('manage','governance',pane);
    requestAnimationFrame(()=>document.getElementById('self-tab-'+pane)?.focus({preventScroll:true}));
    return;
  }
  if(el.dataset.selfFocus){
    const section=el.dataset.selfFocus;
    if(!SELF_PROFILE_SECTIONS.some(([id])=>id===section))return;
    navigate('manage','governance','profile');
    requestAnimationFrame(()=>{
      const tab=document.querySelector(`#roleProfileConfigWorkspace [data-wb-section="${section}"]`);
      if(tab){tab.click();tab.focus({preventScroll:true});}
      document.getElementById('roleProfileConfigWorkspace')?.scrollIntoView({block:'start',behavior:'smooth'});
    });
    return;
  }
  if(el.dataset.perceptionConfig){
    const id=`config-${el.dataset.perceptionConfig}`;
    if(!perceptionToc.some(([section])=>section===id))return;
    closeDetail();navigate('manage','perception');
    requestAnimationFrame(()=>activatePerceptionTab(id,{scroll:true}));
    return;
  }
  if(el.dataset.memoryRoute){
    if(['records','settings'].includes(el.dataset.memoryRoute)&&el.dataset.memoryRoute!==memoryWorkspaceRoute){
      memoryWorkspaceRoute=el.dataset.memoryRoute;
      if(route==='memories')render();else renderShell();
      document.querySelector(`[data-memory-route="${memoryWorkspaceRoute}"]`)?.focus({preventScroll:true});
    }
    return;
  }
  if(el.dataset.outputMode){activateOutputPreview(el.dataset.outputMode);return;}
  if(el.dataset.outputTab){activateOutputTab(el.dataset.outputTab);return;}
  if(el.dataset.outputOpen){activateOutputTab(el.dataset.outputOpen,{focus:true,scroll:true});return;}
  if(el.dataset.actionFocus){
    const card=document.getElementById("action-config-"+el.dataset.actionFocus);
    if(!card)return;
    $$('.action-config-card.is-focused').forEach(item=>item.classList.remove('is-focused'));
    card.classList.add('is-focused');
    const reduced=document.body.classList.contains('reduce-motion')
      ||window.matchMedia('(prefers-reduced-motion: reduce)').matches
      ||['low','off'].includes(document.documentElement.dataset.motion);
    card.scrollIntoView({behavior:reduced?'instant':'smooth',block:'center'});
    card.querySelector('.action-settings-button')?.focus({preventScroll:true});
    setTimeout(()=>card.classList.remove('is-focused'),reduced?850:1500);
    return;
  }
  /* QQ 空间拓展区块。它有自己的在途与重画逻辑（见 qzoneRun），
     所以这里只做转发，不在这里判断状态。 */
  if(el.dataset.qzoneAction){qzoneClick(el);return;}
  if(el.dataset.manageJump){closeDetail();navigate('manage',el.dataset.manageJump);return;}
  if(el.dataset.expressionLifeTab){
    if(!['state','diary'].includes(el.dataset.expressionLifeTab))return;
    closeDetail();navigate('life',el.dataset.expressionLifeTab);return;
  }
  if(el.dataset.replySection){
    if(!window.CompanionReplyPage?.selectSection?.(el.dataset.replySection))toast('回复设置尚未就绪，请稍后重试。');
    return;
  }
  if(el.dataset.configSection){document.getElementById('config-'+el.dataset.configSection)?.scrollIntoView({behavior:state.reduceMotion?'instant':'smooth',block:'start'});return;}
  if(el.dataset.perceptionSection){document.getElementById('perception-'+el.dataset.perceptionSection)?.scrollIntoView({behavior:state.reduceMotion?'instant':'smooth',block:'start'});return;}
  if(el.dataset.perceptionFocus || el.dataset.perceptionTab){
    const id=el.dataset.perceptionFocus||el.dataset.perceptionTab;
    activatePerceptionTab(id,{scroll:true});return;
  }
  if(el.dataset.copyPerception||el.dataset.copyAddress){const input=document.getElementById(el.dataset.copyPerception?'perception-url-'+el.dataset.copyPerception:el.dataset.copyAddress);if(!input)return;const message=el.dataset.copyPerception?'配置地址已复制':'页面地址已复制';const copy=async()=>{try{await navigator.clipboard.writeText(input.value);toast(message);}catch{input.focus();input.select();toast('地址已选中，请手动复制');}};copy();return;}
  if(el.dataset.productProvider){showDetail('cap-'+el.dataset.productProvider);return;}
  if(el.dataset.productLife){showDetail(el.dataset.productLife==='sleep'?'sleep':'reading');return;}
  /* 各工作区的「重新读取」。这些按钮出现在「宿主还没接上」的提示旁边，
     点它就是重走一遍连接 + 重挂工作区，而不是刷新整页——
     刷新整页会连小屋的入场序列一起重播。 */
  if(el.dataset.workspaceRetry!==undefined){
    closeDetail();
    product.connect(()=>{updateHostChrome();if(route==='manage')renderManage();else if(route==='life')render();});
    toast('正在重新读取…');
    return;
  }
  if(el.dataset.openNavigation!==undefined){$('#navigationDialog').showModal();return;}
  if(el.dataset.closeNavigation!==undefined){$('#navigationDialog').close();return;}
  if(el.dataset.navRoute){$('#navigationDialog').close();navigate(el.dataset.navRoute,el.dataset.navTab);return;}
  if(el.matches('.rail-link,.mobile-nav-link,.brand')){event.preventDefault();const [next,tab,subtab]=el.getAttribute('href').slice(1).split('/');navigate(next,tab,subtab);return;}
  if(el.dataset.closeDetail!==undefined){closeDetail();return;}
  if(el.dataset.closeSearch!==undefined){$('#searchDialog').close();return;}
  if(el.dataset.homeSection){goHomeSection(el.dataset.homeSection);return;}
  if(el.dataset.furniture){openFurniture(el.dataset.furniture);return;}
  if(el.dataset.locateFurniture){
    const item=directory.find(item=>item.id===el.dataset.locateFurniture);if(!item?.station||!voxelController)return;
    if(voxelController.getState().storedFurniture.includes(item.station)){openRoomEditor();voxelController.selectFurniture(item.station);return;}
    goHomeSection('overview');voxelController.focus(item.station);toast('正在查看'+item.name+'，点击家具打开内容');return;
  }
  if(el.dataset.observation){
    if(!observationFilters.some(([id])=>id===el.dataset.observation))return;
    observationFilter=el.dataset.observation;$('#observationBody').innerHTML=observationContent();
    $$('[data-observation]').forEach(button=>{const active=button.dataset.observation===observationFilter;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});icons();return;
  }
  if(el.dataset.furnitureFilter){furnitureFilter=el.dataset.furnitureFilter;updateFurnitureDirectory();return;}
  if(el.dataset.clearFurniture!==undefined){furnitureFilter='all';furnitureQuery='';$('[data-directory-search]').value='';updateFurnitureDirectory();return;}
  if(el.dataset.detail){showDetail(el.dataset.detail);return;}
  if(el.dataset.go){navigate(el.dataset.go,el.dataset.lifeTarget||el.dataset.manage);return;}
  if(el.dataset.life){navigate('life',el.dataset.life);return;}
  if(el.dataset.role){return;}
  if(el.dataset.weather){if(!weatherModes.some(item=>item.id===el.dataset.weather))return;state.weather=el.dataset.weather;syncEnvironment();if(!persist())toast('天气已切换；此环境仅保留至页面关闭');return;}
  if(el.dataset.voxelReset!==undefined){voxelController?.reset();return;}
  if(el.dataset.voxelRetry!==undefined){render();return;}
  if(el.dataset.voxelTour!==undefined){if(state.reduceMotion||window.matchMedia('(prefers-reduced-motion: reduce)').matches){toast('已开启减少动态效果，可手动旋转和点选家具');return;}voxelController?.toggleTour();return;}
  if(el.dataset.display){const key=el.dataset.display;if(!['largeText','reduceMotion'].includes(key))return;state[key]=!state[key];el.setAttribute('aria-checked',String(state[key]));updateAppearance();if(key==='reduceMotion')voxelController?.setReducedMotion(state.reduceMotion);persist();return;}
  /* 跟随光照是外观维度，存在 product 侧（与主题同组键），不进 state。 */
  if(el.dataset.followLight!==undefined){const on=product.setFollowLight(!product.followLight());el.setAttribute('aria-checked',String(on));toast(on?'已开启：小屋进入夜晚时会自动切到深色主题':'已关闭：主题不再自动跟随');return;}
  if(el.dataset.libraryFilter){libraryFilter=el.dataset.libraryFilter;render();return;}
  if(el.dataset.memoryView){memoryView=el.dataset.memoryView;render();return;}
  /* === 外壳交互 ===
     点家具：面板换成它的说明、右栏换成它的状态、镜头飞过去。
     点左栏分区：面板换成配置编辑器，镜头不动。
     两者的状态都在 shell.js 里，这里只做转发。 */
  if(el.dataset.shellFurniture){
    /* 再点一次同一件 = 取消选中，回到全景与总览面板。 */
    const same=window.CompanionShell?.furniture===el.dataset.shellFurniture;
    chooseFurniture(same?null:el.dataset.shellFurniture);
    if(same)voxelController?.focus?.('overview');
    return;
  }
  if(el.dataset.shellView){
    /* 状态/日记是 life 子页：同步路由与 lifeTab，面包屑、深链接和
       「全部功能」对话框里的活动态才一致。 */
    const view=el.dataset.shellView;
    if(lifeTabs.some(item=>item[0]===view)){
      route='life';lifeTab=view;
      try{history.replaceState(null,'',navHref('life',view));}catch{}
    }
    window.CompanionShell?.selectView(view);
    renderShell();
    return;
  }
  /* 小屋退到背景时点它 = 回到首页。缩略态下整个小屋区都是返回入口，
     不要求用户去点那个小按钮。 */
  if(el.closest('#stageScene')&&window.CompanionShell?.section){
    backHome();
    return;
  }
  if(el.dataset.shellHome!==undefined){backHome();voxelController?.focus?.('overview');return;}
  if(el.dataset.shellSection){
    /* 同时更新旧的 manageTab，让深链接与既有渲染函数保持一致；
       但不走 navigate()——那会触发整页 render()，把小屋白白重挂一遍。 */
    const section=el.dataset.shellSection;
    if(manageTabs.some(([id])=>id===section)){manageTab=section;route='manage';}
    chooseSection(section);
    try{history.replaceState(null,'',navHref('manage',section));}catch{}
    return;
  }
  if(el.dataset.manageTab){navigate('manage',el.dataset.manageTab);return;}
  if(el.dataset.albumPage!==undefined){showDetail('cap-image');return;}
  if(el.dataset.capAction){const [key,action]=el.dataset.capAction.split(':');if(!capabilities.some(c=>c[0]===key)||state.modules[key]==='planned')return;state.modules[key]=({pause:'paused',enable:initial.modules[key],restore:initial.modules[key],remove:'removed'})[action]||state.modules[key];saved('本地预览状态已更新，真实插件配置未改变');refreshHomeCapabilities();showDetail('cap-'+key);return;}
  if(el.dataset.toggleActivity!==undefined){state.activityPaused=!state.activityPaused;saved(state.activityPaused?'示例活动已暂停，阅读位置保留':'示例活动已继续');render();showDetail('activity-reading');return;}
  if(el.dataset.searchResult!==undefined){const data=searchIndex[Number(el.dataset.searchResult)];$('#searchDialog').close();if(data[3]==='home-section')goHomeSection(data[4]);else if(data[3])navigate(data[3],data[4]);else showDetail(data[4]);return;}
  if(el.dataset.confirmReset!==undefined){state=structuredClone(initial);persist();libraryFilter='all';memoryView='list';observationFilter='records';furnitureFilter='all';furnitureQuery='';navigate('life');toast('已恢复初始预览');return;}
  if(el.dataset.export!==undefined){const blob=new Blob([JSON.stringify({kind:'ui-preview-only',version:2,configSnapshotVersion:configSnapshot.version,configSource:configSnapshot.source,settings:state},null,2)],{type:'application/json;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='陪伴拓展页V2-脱敏设置.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出预览设置');}
});
document.addEventListener('change',event=>{
  const el=event.target;
  if(handleRoomEditorChange(el))return;
  /* 发说说的主题与场景：都是「选择」而不是「输入」，所以走 change。
     换主题后当前场景可能不属于新主题，这里重新对齐一次（不合法就自动选第一个），
     再重画——重画是这个页面唯一的出口，界面必须等于状态。 */
  if(el.dataset.qzoneTopic==='publish'){
    const topic=qzoneTopicTopics().find(item=>item.id===el.value);
    if(topic){
      qzoneState.publishTopic=topic.id;
      qzoneSyncPublishSelection();
      paintQzone();
    }
    return;
  }
  if(el.dataset.qzoneScene==='publish'){
    const scenes=qzoneTopicScenes(qzoneTopic()).map(scene=>scene.id);
    if(scenes.includes(el.value))qzoneState.publishScene=el.value;
    paintQzone();
    return;
  }
  if(el.matches('[data-scene-time]')&&sceneTimes.some(item=>item[0]===el.value)){
    state.scene=el.value;syncEnvironment();if(!persist())toast('时段已切换；此环境仅保留至页面关闭');
  }
});
document.addEventListener('input',event=>{
  const el=event.target;
  /* QQ 空间的草稿只在这里同步进状态：动作结束后整块重画，正文才不会丢。 */
  if(el.dataset.qzoneDraft==='publish'){qzoneState.publishDraft=el.value;qzoneCounts();}
  if(el.dataset.qzoneDraft==='reply'){qzoneState.replyDraft=el.value;qzoneState.replyDraftFor=Number(el.dataset.qzonePost);qzoneCounts();}
  /* 日程建议的回执框：输入同步进状态（重画后还在），并即时更新确认按钮。 */
  if(el.dataset.qzoneReceipt!==undefined){qzoneState.suggestionReceiptDraft=el.value;qzoneSuggestionInput();}
  if(el.dataset.qzoneResult!==undefined){qzoneState.suggestionResultRefDraft=el.value;qzoneSuggestionInput();}
  if(el.dataset.directorySearch!==undefined){furnitureQuery=el.value.trim();updateFurnitureDirectory();}
  if(el.dataset.memorySearch!==undefined){
    /* 记忆检索原来打在一个已删除的 #memoryList 上——那是示例记录列表。
       现在转发给记忆工作区自己的检索框，由它去查真实端点。 */
    const target=$('#memoryWorkspace input[type="search"]');
    if(target){target.value=el.value;target.dispatchEvent(new Event('input',{bubbles:true}));}
  }
});
document.addEventListener('submit',event=>{
  /* 这里原先有三个「保存到预览」的表单处理器：示例日记、示例便签、示例
     反馈，都写进 localStorage 并提示「已保存」。真实内容的保存走各工作区
     （life 工作区的日记、记忆工作区的修订），所以这三个已随示例一起删除。
     弹窗里现在不会有 data-form 表单，保留这条兜底防止未捕获的提交刷新页面。 */
  const form=event.target;if(!form.dataset.form)return;event.preventDefault();
});
$('#detailDialog').addEventListener('close',()=>{if(dialogReturnFocus?.isConnected)dialogReturnFocus.focus({preventScroll:true});else if(dialogReturnFurniture)document.querySelector('[data-furniture="'+dialogReturnFurniture+'"]')?.focus({preventScroll:true});else document.querySelector('[data-detail="'+lastDetail+'"]')?.focus({preventScroll:true});});
$('#detailDialog').addEventListener('click',event=>{if(event.target!==event.currentTarget)return;const r=event.currentTarget.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeDetail();});
$('#searchDialog').addEventListener('click',event=>{if(event.target===event.currentTarget){const r=event.currentTarget.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)event.currentTarget.close();}});
$('#searchButton').addEventListener('click',openSearch);
$('#appearanceButton').addEventListener('click',()=>navigate('manage','appearance'));
/* 缩略态下点小屋 = 回到首页。单独绑一个监听而不是靠 document 上的委托：
   委托那层开头会 closest('button,a') 过滤，而小屋区里没有按钮，
   落在 .room-stage 上的点击在那里就被丢掉了。 */
$('#stageScene')?.addEventListener('click',()=>{
  if(window.CompanionShell?.section)backHome();
});
/* 键盘可达：缩略态的小屋要能 Tab 到并按 Enter 返回。
   canvas 本身不可聚焦，所以给容器加 tabindex 与键盘处理。 */
$('#stageScene')?.addEventListener('keydown',event=>{
  if(!window.CompanionShell?.section)return;
  if(event.key==='Enter'||event.key===' '){event.preventDefault();backHome();}
});
/* 重置入口随页脚一起去掉了，但 data-confirmReset 的委托处理还在
   （详情弹窗里仍会走到）。这里只在按钮存在时才绑，不硬取节点——
   硬取一个不存在的节点会在启动时抛错，整个页面脚本都不再执行。 */
$('#resetButton')?.addEventListener('click',()=>showDetail('reset'));
$('#globalSearch').addEventListener('input',renderSearch);
$('#globalSearch').addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();$('#searchDialog').close();}else if(event.key==='Enter'){$('.search-result')?.click();event.preventDefault();}});
document.addEventListener('keydown',event=>{
  if(handleRoomEditorKey(event))return;
  const selfTab=event.target.closest?.('[role="tab"][data-self-pane]');
  if(selfTab&&['ArrowRight','ArrowLeft','Home','End'].includes(event.key)){
    const tabs=$$('.self-workspace-tabs [data-self-pane]');
    const index=tabs.indexOf(selfTab);
    if(index>=0&&tabs.length){
      event.preventDefault();
      const next=event.key==='Home'?0:event.key==='End'?tabs.length-1
        :(index+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length;
      const pane=tabs[next].dataset.selfPane;
      navigate('manage','governance',pane);
      requestAnimationFrame(()=>document.getElementById('self-tab-'+pane)?.focus({preventScroll:true}));
    }
    return;
  }
  const outputTab=event.target.closest?.('[data-output-mode],[data-output-tab]');
  if(outputTab&&['ArrowRight','ArrowLeft','Home','End'].includes(event.key)){
    const preview=outputTab.hasAttribute('data-output-mode');
    const tabs=preview?$$('[data-output-mode]'):$$('[data-output-tab]');
    const index=tabs.indexOf(outputTab);
    if(index>=0&&tabs.length){
      event.preventDefault();
      const next=event.key==='Home'?0:event.key==='End'?tabs.length-1
        :(index+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length;
      if(preview)activateOutputPreview(tabs[next].dataset.outputMode,{focus:true});
      else activateOutputTab(tabs[next].dataset.outputTab,{focus:true});
    }
    return;
  }
  const perceptionTab=event.target.closest?.('[role="tab"][data-perception-tab]');
  if(perceptionTab&&['ArrowRight','ArrowLeft','Home','End'].includes(event.key)){
    const tabs=$$('.perception-config-nav [data-perception-tab]');
    const index=tabs.indexOf(perceptionTab);
    if(index>=0&&tabs.length){
      event.preventDefault();
      const next=event.key==='Home'?0:event.key==='End'?tabs.length-1
        :(index+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length;
      activatePerceptionTab(tabs[next].dataset.perceptionTab,{focus:true});
    }
    return;
  }
  const memoryTab=event.target.closest?.('[role="tab"][data-memory-route]');
  if(memoryTab&&['ArrowRight','ArrowLeft','Home','End'].includes(event.key)){
    const tabs=$$('.memory-route-tabs [data-memory-route]');
    const index=tabs.indexOf(memoryTab);
    if(index>=0&&tabs.length){
      event.preventDefault();
      const next=event.key==='Home'?0:event.key==='End'?tabs.length-1
        :(index+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length;
      memoryWorkspaceRoute=tabs[next].dataset.memoryRoute;
      if(route==='memories')render();else renderShell();
      document.querySelector(`[data-memory-route="${memoryWorkspaceRoute}"]`)?.focus({preventScroll:true});
    }
    return;
  }
  /* Esc：从配置分区回到小屋。只在没有弹窗打开时接管——
     搜索与详情弹窗自己的 Esc 关闭优先，否则用户按 Esc 想关弹窗，
     结果连配置页一起退掉。 */
  if(event.key==='Escape'&&window.CompanionShell?.section
     &&!$('#searchDialog')?.open&&!$('#detailDialog')?.open&&!$('#navigationDialog')?.open){
    event.preventDefault();backHome();return;
  }
  if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'){event.preventDefault();if(!$('#searchDialog').open)openSearch();}
});
window.addEventListener('hashchange',syncFromHash);
/* 切标签页回来时重启帧循环——但只有在首页才重启。
   无条件写 setActive(!document.hidden) 会在小屋已退到缩略态时
   把它重新唤醒，等于白付一场渲染。 */
document.addEventListener('visibilitychange',()=>{
  const away=Boolean(window.CompanionShell?.section);
  voxelController?.setActive?.(!document.hidden&&!away);
});
/* 先接桥，再渲染。
 *
 * 反过来的话，首次 render() → renderShell() → paintPanel() → mountPanelWorkspaces()
 * 会在 probeHost() 之前就把当前路由的子页面挂上，它们立刻发请求、于是在桥
 * 还没就位时各自去拉一次 SDK。虽然各页现在都会等桥，但那样每个子页面都要
 * 自己经历一次「等」，而且等待窗口里界面上是「正在读取…」。
 *
 * probeHost() 不 await：它内部是异步的，这里不能阻塞首屏渲染。它先跑只是
 * 为了尽早启动 whenBridgeReady()，让 SDK 的加载与 render 的 DOM 工作在
 * 同一段时间里并行。桥到位后它自己会回调 render() 重画一遍。 */
probeHost();
syncFromHash();
