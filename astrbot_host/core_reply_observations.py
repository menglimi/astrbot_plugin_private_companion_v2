"""Asynchronous local observation jobs, outside AstrBot generation and send."""

import asyncio
import logging

from companion_v2.conversation.native_observations import NativeConversationObservations


logger = logging.getLogger(__name__)


class CoreReplyObservations:
    def __init__(self, session):
        self.session = session
        self.owner = NativeConversationObservations(session.application.messages)
        from .core_reply_media import bind_native_quoted_image_sources
        self._quoted_image_guard = bind_native_quoted_image_sources(session.application)
        self._pending = set()
        self._tails = {}
        self._closed = False

    def _schedule(self, work, *, context_key=None, before=None):
        if self._closed:
            return None

        preceding = self._tails.get(context_key) if context_key is not None else None

        async def record():
            try:
                for prior in (preceding, before):
                    if prior is not None:
                        await asyncio.shield(prior)
                return await asyncio.to_thread(work)
            except Exception as error:
                logger.warning("[CompanionV2] 核心聊天后台观察失败 error_type=%s", type(error).__name__)
                return None

        task = asyncio.create_task(record(), name="companion-v2-native-observation")
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        if context_key is not None:
            self._tails[context_key] = task
            def release(done):
                if self._tails.get(context_key) is done:
                    self._tails.pop(context_key, None)
            task.add_done_callback(release)
        return task

    def submit(self, work):
        """Schedule local telemetry work with the same shutdown drain as sources."""
        return self._schedule(work)

    def input(self, context, native_input, *, turn_id, expression_signal_ids=()):
        def record():
            self.session.authorize(context)
            reference = self.owner.capture_input(context, native_input, turn_id=turn_id)
            if expression_signal_ids:
                from companion_v2.execution.models import digest
                from companion_v2.expression.feedback import stage_injection
                expression = self.session.application.messages.expression_style_context
                try:
                    with self.session.runtime.transaction() as connection:
                        stage_key = "astrbot.core-expression-stage." + digest(turn_id)
                        if connection.execute("SELECT 1 FROM runtime_metadata WHERE key = ?", (stage_key,)).fetchone() is None:
                            stage_injection(self.session.runtime, batch_id=turn_id,
                                owner_key=digest(expression.catalog.role_owner(context)), scope_key=digest(context.scope),
                                signal_ids=expression_signal_ids, at=native_input.at)
                            connection.execute("INSERT INTO runtime_metadata VALUES (?, ?)", (stage_key, "true"))
                except Exception as error:
                    logger.warning("[CompanionV2] 核心表达注入观察降级 error_type=%s", type(error).__name__)
            return reference

        pending = self._schedule(record, context_key=context.key)
        if pending is not None:
            def observed(done):
                if done.cancelled() or done.exception() is not None or done.result() is None:
                    return
                self.session.application.notify()
                semantic = getattr(self.session.application.tools, "semantic", None)
                schedule = getattr(semantic, "schedule_native_input", None)
                if callable(schedule):
                    try:
                        schedule(context, turn_id)
                    except Exception as error:
                        logger.warning("[CompanionV2] 核心聊天语义观察调度降级 error_type=%s", type(error).__name__)
            pending.add_done_callback(observed)
        return pending

    def output(self, prepared, text, *, state="output_observed"):
        context, at = prepared["context"], self.session.now()

        def record():
            self.session.authorize(context)
            return self.owner.capture_output(context, turn_id=prepared["turn_id"], event_id=prepared["event_id"],
                                            text=text, at=at, state=state)

        pending = self._schedule(record, context_key=context.key, before=prepared.get("native_source_future"))
        if pending is not None:
            pending.add_done_callback(lambda done: self.session.application.notify()
                if not done.cancelled() and done.exception() is None else None)
        return pending

    def phase(self, prepared, state):
        context, at = prepared["context"], self.session.now()

        def record():
            self.session.authorize(context)
            from companion_v2.conversation.native_turns import NativeConversationTurns
            NativeConversationTurns(self.session.runtime).mark(prepared, state, at=at)

        pending = self._schedule(record, context_key=context.key)
        if pending is not None:
            pending.add_done_callback(lambda done: self.session.application.notify()
                if not done.cancelled() and done.exception() is None else None)
        return pending

    def media(self, event, prepared):
        """Capture direct native images after admission; generation never awaits it."""
        if self._closed:
            return None
        from .core_reply_media import capture_native_input_images, frozen_image_locators
        locators = frozen_image_locators(event)
        if not locators:
            return None
        context = prepared["context"]

        async def capture():
            try:
                image_event = await capture_native_input_images(self.session.application, prepared, locators,
                    authorize=lambda: self.session.authorize(context))
                if image_event is not None:
                    semantic = getattr(self.session.application.tools, "semantic", None)
                    schedule = getattr(semantic, "schedule_native_reaction_collection", None)
                    if callable(schedule):
                        schedule(context, prepared["turn_id"], image_event)
                    self.session.application.notify()
                return image_event
            except Exception as error:
                logger.warning("[CompanionV2] 核心媒体后台观察降级 error_type=%s", type(error).__name__)
                return None

        task = asyncio.create_task(capture(), name="companion-v2-native-media-observation")
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return task

    async def close(self):
        self._closed = True
        # Thread-backed SQLite writes must finish before the application's data
        # root closes. Cancelling an asyncio wrapper would leave its thread live.
        if self._pending:
            await asyncio.gather(*tuple(self._pending), return_exceptions=True)
        from companion_v2.conversation.native_turns import NativeConversationTurns
        await asyncio.to_thread(lambda: NativeConversationTurns(self.session.runtime).interrupt_open(at=self.session.now()))
        self._quoted_image_guard.close()
