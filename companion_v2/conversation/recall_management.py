"""Authorized management view over this window's withdrawn originals.

V1 answered a chat command or a natural-language question here. V2 keeps the same
bounded read but exposes it as an authenticated Dashboard view: the operator is
authorized with the existing core-only memory-management action, the window switch
must be on, and the answer is a read-only list that never becomes context.
"""

from companion_v2.conversation.perception_settings import GROUP as PERCEPTION_GROUP
from companion_v2.execution.models import TaskError, require
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import ScopeKind

from .recall_settings import RecallSettings


class RecallManagement:
    def __init__(self, app, context):
        if (context is None or not hasattr(context, "scope")
                or context.scope.kind not in (ScopeKind.PRIVATE, ScopeKind.GROUP)):
            raise ValueError("recall management requires one resolved private or group window")
        self.app, self.context = app, context

    def _settings(self):
        settings = RecallSettings(self.app.configuration).read(self.context, self.app.now())
        timezone = self.app.perception_settings.snapshot(
            self.context.actor, self.context, self.app.now()).values.get(
                PERCEPTION_GROUP + ".calendar_timezone", "Asia/Shanghai")
        return {**settings, "timezone": timezone}

    @outcome
    def status(self, operator):
        with self.app.runtime.read_snapshot():
            settings = self._settings()
            require(self.app.tasks.identity.authorize(
                operator, self.context.scope, "memory.manage", observed_at=self.app.now()))
            return {"state": "ok", "enabled": settings["transcribe_enabled"],
                    "max_items": settings["transcribe_max_items"],
                    "text_chars": settings["transcribe_text_chars"],
                    "window_minutes": settings["transcribe_window_minutes"]}

    @outcome
    def transcribe(self, operator, *, limit=None):
        if limit is not None and (type(limit) is not int or not 1 <= limit <= 20):
            raise TaskError("recall_request_invalid", "transcript page size must be an integer from 1 to 20")
        with self.app.runtime.read_snapshot():
            settings = self._settings()
            if limit is not None:
                settings = {**settings, "transcribe_max_items": min(limit, settings["transcribe_max_items"])}
            result = self.app.messages.recalls.transcribe(self.context, operator, settings,
                                                          at=self.app.now())
            return {**result, "enabled": settings["transcribe_enabled"],
                    "note": "撤回内容只作管理查询，不会重新变成聊天上下文，也不会重新发布来源。"}


__all__ = ["RecallManagement"]
