"""Paired phones create games through the current V2 private capability."""

from __future__ import annotations

from urllib.parse import quote

from companion_v2.execution.models import TaskError
from .mobile_together import MobileTogetherBridge, REQUEST_ID

GAME_KINDS = ("tictactoe", "gomoku", "pig_dice", "blackjack", "xiangqi", "turtle_soup", "draw_guess")


class MobileGameBridge(MobileTogetherBridge):
    def status(self, session_token):
        user_id = self._mobile_user(session_token)
        resolved = self._target_context(user_id)
        if resolved is None:
            return {"matched": False, "ready": False, "games": []}
        _, application, context = resolved
        registry = self.controller.native_extensions
        service = registry.active_service("game")
        if registry.application is not application or service is None:
            return {"matched": True, "available": False, "ready": False, "games": [],
                    "reason": "mobile_game_unavailable"}
        enabled = bool(service.server_enabled)
        games = [kind for kind in GAME_KINDS if getattr(service, "native_v2_" + kind + "_enabled", False)
                 and enabled and self._admitted(registry, application, context, "game." + kind + ".create") is not None]
        return {"matched": True, "available": True, "enabled": enabled,
                "running": bool(service.room_server.running), "ready": bool(games), "games": games,
                "reason": None if games else "mobile_game_not_authorized" if enabled else "mobile_game_disabled"}

    async def create(self, session_token, request_id, kind, *, via_mobile_gateway=False):
        if type(request_id) is not str or not REQUEST_ID.fullmatch(request_id):
            raise TaskError("mobile_request_id_required", "创建游戏需要保持不变的 request_id")
        kind = str(kind or "").removeprefix("native_v2:")
        if kind not in GAME_KINDS:
            raise TaskError("mobile_game_invalid", "游戏类型不可用")
        user_id = self._mobile_user(session_token)
        resolved = self._target_context(user_id)
        if resolved is None:
            raise TaskError("mobile_v2_context_unavailable", "请先将手机用户绑定到 V2 私聊目标")
        session, application, context = resolved
        registry = self.controller.native_extensions
        service = registry.active_service("game")
        if registry.application is not application or service is None or not service.server_enabled:
            raise TaskError("mobile_game_unavailable", "V2 游戏房间服务未启用")
        declaration = self._admitted(registry, application, context, "game." + kind + ".create")
        if declaration is None:
            raise TaskError("mobile_game_not_authorized", "当前 V2 私聊目标尚未授权此游戏")
        arguments = {} if kind == "turtle_soup" else {"difficulty": "normal"}
        if kind == "xiangqi":
            arguments["human_side"] = "red"
        response = await self._invoke_native(session_token, user_id, session, application, context,
            registry, declaration, request_id, arguments)
        if response.get("state") != "succeeded":
            return response
        game = response.get("result", {}).get("game")
        if type(game) is not dict or not game.get("game_id"):
            raise TaskError("mobile_game_result_invalid", "V2 游戏回执没有可用房间")
        if via_mobile_gateway:
            if not service.room_server.running:
                await service.room_server.start()
            base = service.room_server.local_base_url
        else:
            base = await service._ensure_mobile_room_access()
        self._recheck(session_token, user_id, context, application, registry, declaration)
        if registry.active_service("game") is not service:
            raise TaskError("mobile_v2_provider_changed", "游戏模块已重新配置")
        ticket = service._native_provider.issue_web_ticket(game["game_id"])
        return {**response, "result": {"url": base.rstrip("/") + "/native/" + quote(ticket, safe=""),
            "room_id": game["game_id"], "game_type": kind, "engine": "native_v2"}}
