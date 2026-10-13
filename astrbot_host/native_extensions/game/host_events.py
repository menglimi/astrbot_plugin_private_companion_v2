"""Local, read-only game facts for the current AstrBot private session."""

from __future__ import annotations

import time


class GameHostEvents:
    def __init__(self, runtime, current):
        self.runtime, self.current = runtime, current

    def request(self, event, req):
        runtime = self.runtime
        if not runtime.private_qq_game_context_enabled:
            return
        private = getattr(event, "is_private_chat", None)
        if callable(private) and not private():
            return
        sender_getter = getattr(event, "get_sender_id", None)
        sender = str(sender_getter() or "").strip() if callable(sender_getter) else ""
        session_id = str(getattr(event, "unified_msg_origin", "") or "")
        if not sender or not session_id:
            return
        current = str(getattr(req, "system_prompt", "") or "")
        marker = "<game_companion_private_context>"
        if marker in current:
            return
        lines = [runtime._private_qq_room_state(room)
                 for room in runtime.manager.for_session(session_id)
                 if runtime._private_context_user(room) == sender]
        recent_results = runtime._recent_private_game_results
        recent = recent_results.get(session_id)
        if recent is not None and recent.user_qq == sender:
            if recent.expires_at and recent.expires_at <= time.time():
                recent_results.pop(session_id, None)
            else:
                lines.append(recent.summary)
        if lines:
            req.system_prompt = (current + "\n\n" + "\n".join([
                marker,
                "以下是当前私聊用户的游戏房间临时只读事实。用户谈及当前或刚结束的游戏时自然接话；"
                "无关话题无需提起。这里没有 WebUI 对话记录，不猜测未列出的棋局细节、暗牌或海龟汤汤底。",
                *lines,
                "房间操作仍通过 WebUI 完成；仅凭聊天或这些状态资料，不能声称已经落子、投降、悔棋或改变房间。",
                "</game_companion_private_context>",
            ])).strip()
