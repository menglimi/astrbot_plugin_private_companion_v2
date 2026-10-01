/* Exercise packaged provider pages with the real SDK bridge and local fixtures.
   No provider plugin, production configuration or external operation is invoked. */
"use strict";
const fs = require("node:fs/promises");
const path = require("node:path");
const http = require("node:http");
const {chromium} = require("playwright");

function fixture(capability, endpoint) {
  const key = endpoint.replace(/^page\//, "");
  if (capability === "screen") {
    if (key === "auth/info") return {success:true,requires_auth:false,authenticated:true};
    return {success:true,settings:{},config:{presets:[]},runtime:{},windows:[],
      diaries:[],observations:[],memories:[],stats:{}};
  }
  if (capability === "reality") return {ok:true,data:{configuration:{},users:[]},integration:{}};
  let data = {};
  if (capability === "together") data = key === "status"
    ? {enabled:true,running:true,base_url:"https://example.invalid/room",tunnel:{},
       capabilities:{chat:{available:true,label:"合成模型"},vision:{},stt:{},tts:{},work:{},novel:{}}}
    : {values:{"conversation.chat_provider_id":"qa-chat"},providers:{chat:[{id:"qa-chat",label:"合成模型"}]}};
  if (capability === "game") data = key === "settings"
    ? {games:[{game_type:"tictactoe",label:"井字棋",description:"合成配置",enabled:true,fields:[]}]}
    : {rooms:[],server:{running:true},tunnel:{},enabled_games:{},xiangqi_engine:{}};
  if (capability === "live") data = key === "config/schema"
    ? {schema:{},groups:[],values:{}} : {live:{},twitch:{},items:[],events:[],viewers:[]};
  return {status:"ok",data};
}

async function run(output) {
  const inventory = JSON.parse(await fs.readFile(path.join(output,"inventory.json"),"utf8"));
  const targets = inventory.providers.flatMap(item=>item.pages.map(page=>({...page,...item,pages:undefined})));
  const bridge = await fs.readFile(inventory.bridge_path,"utf8");
  const calls = [], serverErrors = [];
  const mime = {".js":"text/javascript", ".css":"text/css", ".html":"text/html", ".svg":"image/svg+xml", ".png":"image/png"};
  const server = http.createServer(async(req,res)=>{
    try {
      const url = new URL(req.url,"http://127.0.0.1");
      if (url.pathname === "/api/plugin/page/bridge-sdk.js") {
        res.setHeader("Content-Type","text/javascript;charset=utf-8");res.end(bridge);return;
      }
      if (url.pathname === "/rpc") {
        const chunks=[];for await (const chunk of req) chunks.push(chunk);
        const input=JSON.parse(Buffer.concat(chunks).toString("utf8"));
        calls.push(input);
        const data=input.message.action === "api:get" ? fixture(input.capability,input.message.endpoint)
          : {status:"error",message:"本次检查仅允许读取"};
        res.setHeader("Content-Type","application/json;charset=utf-8");res.end(JSON.stringify(data));return;
      }
      if (url.pathname.startsWith("/inspect/")) {
        const target=targets.find(item=>item.capability===url.pathname.split("/")[2]);
        if(!target){res.writeHead(404).end();return;}
        const wrapper=`<!doctype html><meta charset="utf-8"><style>body{margin:0}iframe{width:100%;height:100vh;border:0}</style>
          <iframe id="provider" sandbox="allow-scripts allow-forms allow-downloads" src="${target.asset_prefix}"></iframe><script>
          addEventListener('message',async event=>{const frame=document.getElementById('provider'),m=event.data;
            if(event.source!==frame.contentWindow||m.channel!=='astrbot-plugin-page')return;
            const send=value=>frame.contentWindow.postMessage({channel:'astrbot-plugin-page',...value},'*');
            if(m.kind==='ready'){send({kind:'context',context:{pluginName:${JSON.stringify(target.plugin)},pageName:${JSON.stringify(target.name)}}});return;}
            if(m.kind!=='request')return;
            const r=await fetch('/rpc',{method:'POST',body:JSON.stringify({capability:${JSON.stringify(target.capability)},message:m})});
            send({kind:'response',requestId:m.requestId,ok:true,data:await r.json()});
          });</script>`;
        res.setHeader("Content-Type","text/html;charset=utf-8");res.end(wrapper);return;
      }
      const target=targets.find(item=>url.pathname.startsWith(item.asset_prefix));
      if(!target){res.writeHead(404).end();return;}
      const relative=decodeURIComponent(url.pathname.slice(target.asset_prefix.length)).replace(/^\/+/, "");
      const root=path.resolve(target.source_root),file=path.resolve(root,relative||"index.html");
      if(file!==path.join(root,"index.html")&&!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
      const body=await fs.readFile(relative ? file : target.rewritten_html);
      res.setHeader("Content-Type",(mime[path.extname(file)]||"application/octet-stream")+";charset=utf-8");res.end(body);
    } catch(error) {serverErrors.push(error.message);res.writeHead(500).end();}
  });
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH,
    args:["--disable-gpu","--disable-features=PaintHolding","--run-all-compositor-stages-before-draw"]});
  const results=[];
  try {
    for(const target of targets) {
      const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
      const errors=[],requests=[],external=[];
      page.on("pageerror",error=>errors.push(error.message));
      page.on("response",response=>{if(response.status()>=400)requests.push({url:response.url(),status:response.status()});});
      await page.route("**/*",route=>{
        const u=new URL(route.request().url());
        if(u.hostname!=="127.0.0.1"){external.push(u.origin);return route.abort();}
        return route.continue();
      });
      const start=calls.length;
      let failure=null;
      try {
        const firstReply=page.waitForResponse(response=>response.url().endsWith("/rpc"),{timeout:15000});
        await page.goto(`http://127.0.0.1:${server.address().port}/inspect/${target.capability}`);
        const frame=page.frameLocator("#provider");
        await frame.locator("body").waitFor();
        await firstReply;
        await frame.locator("body").evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        if(target.capability==="together")await frame.locator('[data-config-tab="watch"]').click();
        if(target.capability==="screen")await frame.locator('[data-section="runtime"]').click();
        if(target.capability==="game")await frame.locator('[data-panel="settings"]').click();
        if(target.capability==="reality")await frame.locator('[data-view="devices"]').click();
        const desktop=path.join(output,target.capability+"-desktop.png");
        await page.locator("#provider").screenshot({path:desktop,animations:"disabled"});
        const text=(await frame.locator("body").innerText()).trim();
        const controls=await frame.locator("button,input,select,textarea").count();
        const desktopOverflow=await frame.locator("html").evaluate(el=>el.scrollWidth>el.clientWidth+1);
        await page.setViewportSize({width:390,height:844});
        await page.locator("#provider").screenshot({path:path.join(output,target.capability+"-mobile.png"),animations:"disabled"});
        const mobileOverflow=await frame.locator("html").evaluate(el=>el.scrollWidth>el.clientWidth+1);
        results.push({capability:target.capability,page:target.name,text_length:text.length,controls,
          errors,requests,external_origins:[...new Set(external)],desktopOverflow,mobileOverflow,
          endpoints:[...new Set(calls.slice(start).map(call=>call.message.endpoint))],
          posts:calls.slice(start).filter(call=>call.message.action!=="api:get").length,
          text_excerpt:text.slice(0,650)});
      } catch(error) {failure=error.message;results.push({capability:target.capability,failure,errors,requests});}
      await page.close();
    }
  } finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
  const report={scope:"SDK bridge with synthetic read-only responses",results,serverErrors};
  await fs.writeFile(path.join(output,"browser-results.json"),JSON.stringify(report,null,2)+"\n","utf8");
  console.log(JSON.stringify(report,null,2));
  if(serverErrors.length||results.some(item=>item.failure||item.errors.length||item.requests.length
      ||item.desktopOverflow||item.mobileOverflow||item.posts||!item.text_length))process.exitCode=1;
}
if(require.main===module)run(path.resolve(process.argv[2])).catch(error=>{console.error(error);process.exitCode=1;});
