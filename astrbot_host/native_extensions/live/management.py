"""Explicit cottage actions for VTube Studio; reads never contact devices."""

from __future__ import annotations

import asyncio

from companion_v2.execution.models import TaskError


def snapshot(service):
    return {"connected": bool(service.vts.is_connected),
            "authenticated": bool(service.vts.is_authenticated),
            "hotkeys": getattr(service, "_management_hotkeys", []),
            "error_code": getattr(service, "_management_error", None)}


async def action(service, name, payload, current):
    if name not in {"connect", "request_auth", "list_hotkeys"} or payload:
        raise ValueError("不支持的直播管理操作")
    if not hasattr(service, "_management_lock"):
        service._management_lock = asyncio.Lock()
    async with service._management_lock:
        current()
        try:
            if name in {"connect", "request_auth"}:
                host, port = await asyncio.wait_for(service._discover(), timeout=15)
                current()
                url = f'ws://{host}:{port}'
                if service.vts.url != url:
                    await asyncio.gather(service.vts.reset_connection(), service._parameter_vts.reset_connection())
                service.vts.url = service._parameter_vts.url = url
            if name == "request_auth":
                token = await asyncio.wait_for(service.vts.request_auth_token(), timeout=15)
                current()
                if not await service.vts.authenticate(token):
                    raise TaskError("native_vts_authorization_denied", "VTube Studio 没有允许此次授权")
                current()
                await service._save_token(token)
                service._connected = True
            else:
                service._connected = await service._authenticate_saved_token(service.vts)
                current()
                if not service._connected:
                    raise TaskError("native_vts_authorization_required", "请打开 VTube Studio API 并申请授权")
                if name == "list_hotkeys":
                    keys = await service.vts.get_hotkeys()
                    current()
                    service._management_hotkeys = [{key: item[key] for key in
                        ("hotkeyID", "name", "type", "file") if key in item}
                        for item in keys if type(item) is dict]
            service._management_error = None
            return {"completed": True}
        except asyncio.TimeoutError as error:
            service._management_error = "native_vts_action_timeout"
            raise TaskError("native_vts_action_timeout", "操作超时，请检查 VTube Studio 的连接和授权弹窗") from error
        except TaskError as error:
            service._management_error = error.code
            raise
        except Exception as error:
            service._management_error = "native_vts_action_failed"
            raise TaskError("native_vts_action_failed", "VTube Studio 操作未完成，请检查设备状态") from error
