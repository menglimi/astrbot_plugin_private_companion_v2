"use strict";
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','pages','陪伴小屋','behavior-page.js'),'utf8');
const api='/astrbot_plugin_private_companion/host/targets/first/roles/role-a/config';
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture({failure=false,late=false}={}){
  let enabled=true,resolveGet;
  const calls=[],listeners={};
  const payload=()=>({groups:[{group_key:'real-group',group_id:'300',habits:[{habit_id:'habit-one',label:'互相安慰 <img onerror=alert(1)>',
    situation:'熟悉成员刚忙完',action:'自然地摸摸',boundaries:'尊重对象边界',member_id:'',updated_at:'2026-10-15T11:00:00Z',
    enabled,revision:'revision-one',evidence:[{speaker_id:'201',text:'摸摸 <script>bad()</script>',received_at:'2026-10-15T11:00:00Z'}],
    member_feedback:{'201':[{assessment:'unwelcome',reason:'此刻在忙',at:'2026-10-15T11:01:00Z'}]},
    attempts:[{state:'unknown',target_id:'201',reason:'安慰熟悉成员',planned_at:'2026-10-15T11:00:00Z'}]}]}]});
  const bridge={apiGet:async route=>{calls.push(['GET',route]);return late?new Promise(resolve=>{resolveGet=()=>resolve({status:'ok',data:payload()});}):{status:'ok',data:payload()};},
    apiPost:async(route,body)=>{calls.push(['POST',route,body]);if(failure)return {status:'error',data:{code:'group_behavior_revision_changed'}};
      enabled=body.enabled;return {status:'ok',data:{saved:true,enabled}};}};
  const window={CompanionProduct:{bridgeNow:()=>bridge}};
  const context=vm.createContext({window,setTimeout,clearTimeout});
  vm.runInContext(source,context);
  const root={isConnected:true,innerHTML:'',addEventListener:(kind,fn)=>{listeners[kind]=fn;},removeEventListener:kind=>{delete listeners[kind];}};
  window.CompanionBehaviorPage.mount(root,{api});
  const toggle=()=>listeners.click({target:{closest:selector=>selector==='[data-behavior-toggle]'?{dataset:{behaviorToggle:'habit-one',behaviorGroup:'real-group'}}:null}});
  return {root,calls,window,toggle,resolve:()=>resolveGet()};
}
test('按所选角色读取，汉化发送与反馈状态，转义群聊证据',async()=>{
  const f=fixture();await tick();
  assert.equal(f.calls[0][1],'host/targets/first/roles/role-a/config/behavior');
  for(const text of ['学到的互动','对象与边界','不适','结果未知','201','停用'])assert.ok(f.root.innerHTML.includes(text),text);
  assert.ok(!f.root.innerHTML.includes('<script>bad()'));
  assert.ok(f.root.innerHTML.includes('&lt;script&gt;'));
  assert.ok(!f.root.innerHTML.includes('<img onerror'));
  f.window.CompanionBehaviorPage.unmount();
});
test('停用与恢复写入真实接口，等待确认后重读且阻止重复点击',async()=>{
  const f=fixture();await tick();f.toggle();f.toggle();await tick();
  const post=f.calls.find(call=>call[0]==='POST');
  assert.equal(post[1],'host/targets/first/roles/role-a/config/behavior/command');
  assert.equal(post[2].group_key,'real-group');assert.equal(post[2].habit_id,'habit-one');assert.equal(post[2].enabled,false);
  assert.equal(f.calls.filter(call=>call[0]==='POST').length,1);
  assert.ok(f.root.innerHTML.includes('已停用'));
  assert.ok(f.root.innerHTML.includes('>恢复</button>'));
  f.toggle();await tick();assert.ok(f.root.innerHTML.includes('已恢复这条互动习惯'));
  f.window.CompanionBehaviorPage.unmount();
});
test('旧版本写入被拒时显示可处理错误，保留服务端状态',async()=>{
  const f=fixture({failure:true});await tick();f.toggle();await tick();
  assert.ok(f.root.innerHTML.includes('记录已变化，请重新读取。'));
  assert.ok(f.root.innerHTML.includes('>停用</button>'));
  f.window.CompanionBehaviorPage.unmount();
});
test('离开页面后，迟到的读取不会重写页面',async()=>{
  const f=fixture({late:true});await tick();
  f.window.CompanionBehaviorPage.unmount();const before=f.root.innerHTML;
  f.resolve();await tick();assert.equal(f.root.innerHTML,before);
});
