"""Bind native private windows to optional routines outside the reply path."""

import asyncio
import logging

from companion_v2.foundation.refs import ScopeKind


logger = logging.getLogger(__name__)


class CoreReplyMaintenance:
    def __init__(self, session):
        self.session = session
        self._pending = set()
        self._locks = {}
        self._latest = {}
        self._closed = False

    def schedule(self, context, instruction, *, source_future=None):
        if self._closed or context.scope.kind is not ScopeKind.PRIVATE:
            return None
        scope = context.scope
        route = (scope.platform, scope.account_id, scope.bot_id, scope.native_scope_id)
        ticket = object()
        self._latest[route] = ticket
        lock = self._locks.setdefault(route, asyncio.Lock())

        async def bind():
            async with lock:
                if self._closed or self._latest.get(route) is not ticket:
                    return
                try:
                    if source_future is not None:
                        await asyncio.shield(source_future)
                    if self._closed or self._latest.get(route) is not ticket:
                        return
                    await self.session.bridge.verify_role(context.scope, context.role_binding, instruction)
                    await asyncio.to_thread(self.session.authorize, context)
                    if self._closed or self._latest.get(route) is not ticket:
                        return
                except Exception as error:
                    logger.warning("[CompanionV2] 私聊后台绑定未采用 error_type=%s", type(error).__name__)
                    return

                app = self.session.application
                operations = (
                    ("life", lambda: app.life_runtime.rebind(context, instruction,
                        guard=self.session.bridge.verify_role)),
                    ("state", lambda: app.state_maintenance.bind_async(context, instruction,
                        guard=self.session.bridge.verify_role)),
                    ("contact", lambda: app.contact_schedule.bind_context(context)),
                    ("presence", lambda: app.presence.bind(context) if app.presence is not None else None),
                    ("memory", lambda: app.memory_schedule.sync_configuration_async(context, instruction)),
                )
                for name, operation in operations:
                    if self._closed or self._latest.get(route) is not ticket:
                        break
                    try:
                        result = operation()
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as error:
                        logger.warning("[CompanionV2] 私聊后台绑定降级 section=%s error_type=%s",
                                       name, type(error).__name__)
                app.notify()

        task = asyncio.create_task(bind(), name="companion-v2-native-maintenance")
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return task

    async def close(self):
        self._closed = True
        if self._pending:
            # A schedule may own thread-backed storage preparation. Its thread
            # must finish before the host releases the shared application store.
            await asyncio.gather(*tuple(self._pending), return_exceptions=True)
