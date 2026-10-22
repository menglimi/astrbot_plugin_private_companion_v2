"""One isolated demo phase: real plugin entry and SDK HTTP dispatch, local peers."""

import argparse
import asyncio
from dataclasses import replace
import importlib.util
import json
import logging
import os
from pathlib import Path
import socket
import sys
import traceback
from types import ModuleType, SimpleNamespace as NS
from unittest.mock import patch


WRAPPER = """<!doctype html><meta charset="utf-8"><title>Companion V2 本地验收</title>
<style>body{margin:0}iframe{display:block;width:100%;height:1100px;border:0}</style>
<iframe src="/page/index.html" title="宿主管理"></iframe><script>
addEventListener('message',async event=>{
  const frame=document.querySelector('iframe'),m=event.data;
  if(event.source!==frame.contentWindow||m.channel!=='astrbot-plugin-page')return;
  const send=v=>frame.contentWindow.postMessage({channel:'astrbot-plugin-page',...v},location.origin);
  if(m.kind==='ready'){
    send({kind:'context',context:{pluginName:'astrbot_plugin_private_companion',pageName:'宿主管理'}});return;
  }
  if(m.kind!=='request')return;
  try {
    if(!['api:get','api:post'].includes(m.action)||!/^(staging|host)\\/[a-z-]+$/.test(m.endpoint))
      throw new Error('Unexpected fixture bridge request');
    const url=new URL('/api/plug/astrbot_plugin_private_companion/'+m.endpoint,location.origin);
    for(const [key,value] of Object.entries(m.params||{}))url.searchParams.set(key,value);
    const response=await fetch(url,{method:m.action==='api:get'?'GET':'POST',
      headers:{'Content-Type':'application/json'},...(m.action==='api:post'?{body:JSON.stringify(m.body||{})}:{})});
    send({kind:'response',requestId:m.requestId,ok:true,data:await response.json()});
  } catch(error) {send({kind:'response',requestId:m.requestId,ok:false,error:String(error)});}
});</script>"""


async def verify(args):
    # All SDK imports, including their global databases, are confined to this root.
    args.root.mkdir(parents=True, exist_ok=True)
    os.environ["ASTRBOT_ROOT"] = str(args.root / "sdk")
    from tests.test_astrbot_staging_host import WebContext, host_config
    from tests.multi_host_support import MultiNativeContext, multi_config
    from tests.native_adapter_support import FakeProvider, FakeReverseApi
    from tests.staging_bootstrap_support import wait_for_batch
    from tests.test_management_access import NOW
    from astrbot_host.native import installed_native_types
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
    from astrbot.core.platform.message_type import MessageType
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path
    from astrbot.api.message_components import Plain
    from astrbot.dashboard.api.plugins import _call_plugin_extension
    from fastapi import FastAPI, Request
    from fastapi.responses import FileResponse, HTMLResponse, Response
    import uvicorn

    logging.disable(logging.CRITICAL)
    assert Path(get_astrbot_data_path()).resolve() == (args.root / "sdk" / "data").resolve()
    repo = Path(__file__).resolve().parents[1]
    package = ModuleType("v2_demo_fixture")
    package.__path__ = [str(repo)]
    sys.modules[package.__name__] = package
    spec = importlib.util.spec_from_file_location(package.__name__ + ".main", repo / "main.py")
    entry = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = entry
    spec.loader.exec_module(entry)
    native = WebContext() if args.mode == "single" else MultiNativeContext()
    config = host_config() if args.mode == "single" else multi_config()
    sdk = replace(installed_native_types(), provider=FakeProvider, reverse_api=FakeReverseApi,
                  function_tool=NS, tool_set=NS)
    name = "AstrBotStagingController" if args.mode == "single" else "AstrBotMultiController"
    controller_type = getattr(entry, name)

    def controller(context, config, root):
        return controller_type(context, config, root, native_types=sdk, now=lambda: NOW)

    with patch.object(entry.StarTools, "get_data_dir", return_value=args.root / "v2"), \
            patch.object(entry, name, controller):
        plugin = entry.PrivateCompanionV2StagingPlugin(native, config)
    service = FastAPI()
    service.state.core_lifecycle = NS(star_context=native)
    api_calls = []
    server_errors = []
    disconnected = []
    platforms = [native.platform] if args.mode == "single" else list(native.platforms.values())

    def snapshot():
        ctrl = plugin.staging
        rows = [] if ctrl.runtime is None else ctrl.runtime.read_all(
            "SELECT batch_id, state, context_json FROM conversation_batches ORDER BY rowid", ())
        batches = []
        for row in rows:
            scope = json.loads(row["context_json"])["audience"]["scope"]
            target = "single" if args.mode == "single" else next(t.target_id for t in ctrl.settings.targets
                if (t.bot_id, t.account_id) == (scope["bot_id"], scope["account_id"]))
            batches.append({"batch_id": row["batch_id"], "state": row["state"], "target_id": target,
                            "bot_id": scope["bot_id"], "account_id": scope["account_id"]})
        return {"mode": args.mode, "phase": args.phase, "status": ctrl.status(), "batches": batches,
                "model_calls": len(native.provider.client.state.calls), "api_calls": list(api_calls),
                "platform_calls": sum(len(p.client._api._wsr_api.calls) for p in platforms),
                "server_errors": list(server_errors)}

    @service.middleware("http")
    async def capture_errors(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            server_errors.append(traceback.format_exc())
            raise

    @service.get("/")
    async def index():
        return HTMLResponse(WRAPPER)

    @service.get("/page/{asset}")
    async def page_asset(asset: str):
        if asset not in ("index.html", "app.js", "style.css"):
            return Response(status_code=404)
        return FileResponse(repo / "pages" / "宿主管理" / ("workspace.html" if asset == "index.html" else asset))

    @service.get("/api/plugin/page/bridge-sdk.js")
    async def bridge():
        import astrbot
        return FileResponse(Path(astrbot.__file__).parent / "dashboard" / "plugin_page_bridge.js")

    @service.api_route("/api/plug/{plugin_path:path}", methods=["GET", "POST"])
    async def plugin_api(plugin_path: str, request: Request):
        api_calls.append({"method": request.method, "path": plugin_path})
        # SDK dispatch and its real context variable; only authentication is synthetic.
        return await _call_plugin_extension(plugin_path, request, username="demo-admin")

    @service.get("/__fixture__/snapshot")
    async def inspect():
        return snapshot()

    @service.post("/__fixture__/connection/{state}")
    async def connection(state: str):
        clients = native.platform.client._wsr_api_clients
        if state == "disconnect":
            assert not disconnected
            disconnected.append(clients.pop("100"))
        elif state == "restore":
            clients["100"] = disconnected.pop()
        else:
            return Response(status_code=404)
        return {"connected": state == "restore"}

    @service.post("/__fixture__/input")
    async def input_message():
        ctrl = plugin.staging
        # This fixture-only route is never registered on the real plugin or Dashboard.
        targets = [NS(platform_id="qq-main", account_id="100", participant_id="200")]
        if args.mode == "multi":
            targets = ctrl.settings.targets
        stopped = []
        for index, target in enumerate(targets):
            platform = native.get_platform_inst(target.platform_id)
            message = AstrBotMessage()
            message.type, message.self_id = MessageType.FRIEND_MESSAGE, target.account_id
            message.group_id, message.session_id = "", target.participant_id
            message.sender = MessageMember(target.participant_id, "合成验收用户")
            message.message_id = str(5001 + index)
            message.message_str = "这是本地 Demo 验收消息。"
            message.message = [Plain(message.message_str)]
            message.raw_message = {"post_type": "message", "message_type": "private", "sub_type": "friend",
                "self_id": int(target.account_id), "user_id": int(target.participant_id),
                "sender": {"user_id": int(target.participant_id)}, "message_id": int(message.message_id),
                "message": [{"type": "text", "data": {"text": message.message_str}}]}
            event = sdk.event(message.message_str, message, platform.meta(), target.participant_id, platform.client)
            event.created_at = NOW.timestamp()
            await plugin.receive_companion_message(event)
            stopped.append(event.is_stopped())
            if event.is_stopped():
                batch = ctrl.runtime.read_all("SELECT batch_id FROM conversation_batches ORDER BY rowid", ())[-1][0]
                await wait_for_batch(ctrl.session, batch)
        return {**snapshot(), "events_claimed": stopped}

    args.output.mkdir(parents=True, exist_ok=True)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(service, log_level="error", access_log=False))
    running = None
    browser = None
    try:
        await plugin.initialize()
        assert not plugin.staging.status()["accepting"]
        assert (plugin.staging.runtime is not None) == (args.phase == "recovered")
        running = asyncio.create_task(server.serve(sockets=[sock]))

        async def wait_server():
            while not server.started:
                if running.done():
                    await running
                    raise AssertionError("demo HTTP server stopped before readiness")
                await asyncio.sleep(0.01)

        await asyncio.wait_for(wait_server(), 10)
        browser = await asyncio.create_subprocess_exec(
            args.node, str(repo / "tools" / "check_demo_host.cjs"), f"http://127.0.0.1:{port}", str(args.output),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(browser.communicate(), 75)
        print(stdout.decode("utf-8"), end="")
        assert browser.returncode == 0, "browser demo acceptance failed"
        assert server_errors == [], server_errors
        final = snapshot()
        assert final["platform_calls"] == 0
    finally:
        try:
            if browser is not None and browser.returncode is None:
                browser.kill()
                await browser.communicate()
            server.should_exit = True
            if running is not None:
                await asyncio.wait_for(running, 10)
        finally:
            sock.close()
            await plugin.terminate()
    assert plugin.staging.runtime is None and not native.registered_web_apis
    assert not any(n == "companion_v2" or n.startswith("companion_v2.") for n in sys.modules)
    report = json.loads((args.output / "browser-results.json").read_text(encoding="utf-8"))
    report.update(mode=args.mode, phase=args.phase, teardown_verified=True, model_calls=final["model_calls"],
                  platform_calls=final["platform_calls"], batches=final["batches"], server_errors=server_errors)
    (args.output / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=("single", "multi"), required=True)
    parser.add_argument("--phase", choices=("fresh", "recovered"), required=True)
    parser.add_argument("--node", default="node")
    asyncio.run(verify(parser.parse_args()))
