"""Local, read-only game facts for the current AstrBot private session."""

from __future__ import annotations

import time
import json

from astrbot_host.core_reply import CORE_REPLY_CONTEXT_EXTRA
from companion_v2.execution.models import TaskContext, encode
from companion_v2.foundation.refs import ScopeKind

from ..request_context import set_turn_context


class GameHostEvents:
    def __init__(self, runtime, current):
        self.runtime, self.current = runtime, current

    def _native_facts(self, event, sender):
        provider = getattr(self.runtime, "_native_provider", None)
        getter = getattr(event, "get_extra", None)
        state = getter(CORE_REPLY_CONTEXT_EXTRA) if callable(getter) else None
        prepared = state.get("prepared") if isinstance(state, dict) else None
        context = prepared.get("context") if isinstance(prepared, dict) else None
        if (provider is None or not self.current() or not isinstance(context, TaskContext)
                or context.scope.kind is not ScopeKind.PRIVATE
                or context.actor.principal.native_account_id != sender
                or context.scope.native_scope_id != sender
                or context.audience.recipients != (context.actor.subject,)):
            return []
        application = getattr(getattr(self.runtime.controller, "session", None), "application", None)
        external = getattr(getattr(application, "tools", None), "external", None)
        if external is None:
            return []
        available = {tool.action for tool in external.catalog_for(context)}
        if not available:
            return []
        return provider.conversation_snapshot(json.loads(encode(context)), authorized_actions=available,
            now=time.time(), result_ttl=self.runtime.recent_game_result_ttl_seconds,
            before_read=self.current)

    def request(self, event, req):
        runtime = self.runtime
        set_turn_context(req, "game")
        if not self.current() or not runtime.private_qq_game_context_enabled:
            return
        private = getattr(event, "is_private_chat", None)
        if callable(private) and not private():
            return
        sender_getter = getattr(event, "get_sender_id", None)
        sender = str(sender_getter() or "").strip() if callable(sender_getter) else ""
        session_id = str(getattr(event, "unified_msg_origin", "") or "")
        if not sender or not session_id:
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
        facts = self._native_facts(event, sender)
        if facts:
            lines.append("当前角色与当前私聊的原生网页/聊天共用对局实况：" +
                         json.dumps(facts, ensure_ascii=False, separators=(",", ":")))
        if lines:
            set_turn_context(req, "game", "\n".join([
                "以下是当前私聊用户与当前角色的游戏只读实况。player 是当前用户，bot 是你这个当前角色。"
                "已结束的 status 与真实 outcome 优先于历史中尚未开局、还在邀请或轮到谁的旧描述。"
                "用户给出简短回应时，也可结合最近对局自然承接；不需要特定词或再次询问输赢才理解实况，"
                "但不要把对局结果当作用户情绪的唯一原因。ended_at 为空表示旧记录未保存结束时间，不猜发生时刻。"
                "用户谈及当前或最近结束的游戏时自然接话；"
                "无关话题无需提起。这里没有 WebUI 对话记录，不猜测未列出的棋局细节、暗牌或海龟汤汤底。",
                *lines,
                "具体游戏操作通过已授权工具或 WebUI 完成；以实际操作结果为准，"
                "只读状态本身不代表本轮执行过落子、投降、悔棋或改变房间。",
            ]))
