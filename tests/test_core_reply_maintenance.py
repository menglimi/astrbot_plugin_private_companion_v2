"""Native windows initialize background routines without holding ordinary replies."""

import asyncio
import json
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from companion_v2.execution.models import TaskContext
from companion_v2.memory.models import owner_key

from tests.multi_host_support import MultiFixture, multi_config
from tests.native_adapter_support import FakeEvent


class CoreReplyMaintenanceTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def _drain(self):
        pending = tuple(self.controller.session.core_reply_maintenance._pending)
        if pending:
            await asyncio.wait_for(asyncio.gather(*pending), timeout=5)

    def assert_bound(self, app, prepared):
        context = prepared["context"]
        self.assertEqual(app.life_runtime.routines[context.key].instruction, prepared["instruction"])
        self.assertEqual(app.state_maintenance.bindings[context.key][1], prepared["instruction"])
        self.assertEqual(app.contact_schedule._maintenance_contexts[context.key], context)
        self.assertEqual(app.presence.contexts[context.key], context)
        schedule = app.runtime.read_one("SELECT * FROM memory_schedules WHERE schedule_id = ?", (
            "memory-daily-" + owner_key(context),))
        self.assertIsNotNone(schedule)
        self.assertEqual(TaskContext.restore(json.loads(schedule["context_json"])).key, context.key)
        self.assertEqual(json.loads(schedule["settings_json"])["role_instruction"], prepared["instruction"])

    async def test_new_wildcard_window_initializes_all_background_owners(self):
        config = multi_config()
        config["multi_host"]["targets"][0]["participant_id"] = "*"
        self.controller = self.make_controller(config)
        app = await self.start_host()
        event = FakeEvent(NS(platform=self.native.platforms["qq-main"]), event_id="native-new-window",
                          sender="300", login="100", text="看到一件有趣的事")
        event.created_at = self.clock.now().timestamp()
        self.window_personas[event.unified_msg_origin] = "original"

        prepared = (await self.controller.prepare_core_reply(event)).unwrap()
        await self._drain()

        self.assert_bound(app, prepared)
        self.assertEqual(app.runtime.read_all("SELECT batch_id FROM conversation_batches", ()), ())
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platforms["qq-main"].client._api._wsr_api.calls, [])

    async def test_persona_switch_binds_current_window_and_retires_departed_life(self):
        app = await self.start_host()
        old = next(routine for routine in app.life_runtime.routines.values()
                   if routine.context.scope.platform == "qq-main")
        event = self.event(identifier="native-role-switch")
        self.window_personas[event.unified_msg_origin] = "second"

        prepared = (await self.controller.prepare_core_reply(event)).unwrap()
        await self._drain()

        self.assert_bound(app, prepared)
        self.assertTrue(old._retired)
        self.assertEqual(prepared["context"].role_binding.role.subject_id, "role-b")

    async def test_editing_current_persona_refreshes_life_and_memory_instructions(self):
        app = await self.start_host()
        old = next(routine for routine in app.life_runtime.routines.values()
                   if routine.context.scope.platform == "qq-main")
        self.native.persona_records["original"]["prompt"] = "同一个角色，今天更轻松自然地说话。"

        prepared = (await self.controller.prepare_core_reply(self.event(identifier="native-role-edit"))).unwrap()
        await self._drain()

        self.assert_bound(app, prepared)
        self.assertTrue(old._closed)
        self.assertTrue(old._retired)
        self.assertIsNot(app.life_runtime.routines[prepared["context"].key], old)

    async def test_slow_schedule_io_does_not_hold_preparation_or_event_loop(self):
        app = await self.start_host()
        started, release = threading.Event(), threading.Event()
        original = app.state_maintenance._bind_schedule

        def slow(*args, **kwargs):
            started.set()
            release.wait(timeout=5)
            return original(*args, **kwargs)

        try:
            with patch.object(app.state_maintenance, "_bind_schedule", side_effect=slow):
                prepared = (await asyncio.wait_for(self.controller.prepare_core_reply(
                    self.event(identifier="native-slow-bind")), timeout=1)).unwrap()
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                await asyncio.wait_for(asyncio.sleep(0), timeout=0.1)
                self.assertTrue(self.controller.session.core_reply_maintenance._pending)
                release.set()
                await self._drain()
            self.assert_bound(app, prepared)
        finally:
            release.set()

    async def test_departed_persona_does_not_bind_after_delayed_source_observation(self):
        app = await self.start_host()
        original_event = self.event(identifier="native-original-prepare")
        original_prepared = (await self.controller.prepare_core_reply(original_event)).unwrap()
        await self._drain()
        owner = self.controller.session.core_reply_maintenance
        delayed = asyncio.get_running_loop().create_future()
        departed = original_prepared["context"]
        late = owner.schedule(departed, original_prepared["instruction"], source_future=delayed)
        await asyncio.sleep(0)
        self.window_personas[original_event.unified_msg_origin] = "second"
        prepared = (await self.controller.prepare_core_reply(self.event(identifier="native-second-prepare"))).unwrap()
        delayed.set_result(None)
        await self._drain()

        self.assertTrue(late.done())
        self.assert_bound(app, prepared)
        self.assertTrue(app.life_runtime.routines[departed.key]._retired)

    async def test_one_optional_binding_failure_keeps_other_background_owners(self):
        app = await self.start_host()
        event = self.event(identifier="native-optional-bind")
        self.window_personas[event.unified_msg_origin] = "second"
        with patch.object(app.state_maintenance, "_bind_schedule", side_effect=OSError("unavailable")):
            prepared = (await self.controller.prepare_core_reply(event)).unwrap()
            await self._drain()

        self.assert_bound(app, prepared)

    async def test_stop_drains_running_schedule_threads_and_restart_recreates_bindings(self):
        app = await self.start_host()
        started, release = threading.Event(), threading.Event()
        original = app.state_maintenance._bind_schedule

        def slow(*args, **kwargs):
            started.set()
            release.wait(timeout=5)
            return original(*args, **kwargs)

        try:
            with patch.object(app.state_maintenance, "_bind_schedule", side_effect=slow):
                await self.controller.prepare_core_reply(self.event(identifier="native-bind-before-stop"))
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                stopping = asyncio.create_task(self.controller.stop())
                await asyncio.sleep(0)
                self.assertFalse(stopping.done())
                self.assertIsNotNone(self.controller.runtime._connection)
                release.set()
                stopped = await asyncio.wait_for(stopping, timeout=5)
            self.assertTrue(stopped.is_success, stopped.failure)
            self.assertFalse(self.controller.last_session.core_reply_maintenance._pending)
            restarted = await self.controller.start()
            self.assertTrue(restarted.is_success, restarted.failure)
            prepared = (await self.controller.prepare_core_reply(self.event(identifier="native-bind-after-restart"))).unwrap()
            await self._drain()
            self.assert_bound(self.controller.session.application, prepared)
        finally:
            release.set()

    async def test_memory_schedule_cancels_workers_on_host_loop(self):
        app = await self.start_host()
        prepared = (await self.controller.prepare_core_reply(self.event(identifier="native-memory-binding"))).unwrap()
        await self._drain()
        context = prepared["context"]
        schedule = app.memory_schedule
        key = "memory-daily-" + owner_key(context)
        cancel_thread = []
        schedule.workers[key] = NS(cancel=lambda: cancel_thread.append(threading.get_ident()))
        values, token = schedule.reflection.memory.settings.read(context)
        values = {**values, "memory.reflection_enabled": False}
        try:
            with patch.object(schedule.reflection.memory.settings, "read", return_value=(values, token)):
                await schedule.sync_configuration_async(context, prepared["instruction"])
            self.assertEqual(cancel_thread, [threading.get_ident()])
        finally:
            del schedule.workers[key]

    async def test_accept_queues_slow_memory_schedule_sync_after_intake(self):
        app = await self.start_host()
        schedule = app.memory_schedule
        started, release = threading.Event(), threading.Event()
        original = schedule._sync_configuration

        def slow_sync(*args, **kwargs):
            started.set()
            release.wait(timeout=5)
            return original(*args, **kwargs)

        try:
            with patch.object(schedule, "_sync_configuration", side_effect=slow_sync):
                accepted = await self.controller.receive_claimed(
                    self.event(identifier="native-memory-slow-accept"))
                self.assertTrue(accepted.is_success, accepted.failure)
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                await asyncio.wait_for(asyncio.sleep(0.01), timeout=0.1)
                stopping = asyncio.create_task(self.controller.stop())
                await asyncio.sleep(0.01)
                self.assertFalse(stopping.done())
                self.assertIsNotNone(self.controller.runtime._connection)
                release.set()
                stopped = await asyncio.wait_for(stopping, timeout=5)
                self.assertTrue(stopped.is_success, stopped.failure)
                self.assertFalse(schedule._configuration_tasks)
        finally:
            release.set()

    async def test_restart_interrupts_native_turns_without_replaying_model_or_send(self):
        from companion_v2.conversation.native_turns import NativeConversationTurns

        app = await self.start_host()
        prepared = (await self.controller.prepare_core_reply(self.event(identifier="interrupted-native"))).unwrap()
        running = (await self.controller.prepare_core_reply(self.event(identifier="running-native"))).unwrap()
        await self._drain()
        phase = self.controller.session.core_reply_observations.phase(running, "running")
        await phase
        expected = {prepared["turn_id"]: "prepared", running["turn_id"]: "running"}
        self.assertEqual({row["turn_id"]: row["generation_state"] for row in app.runtime.read_all(
            "SELECT turn_id, generation_state FROM conversation_native_turns", ())}, expected)

        (await self.controller.stop()).unwrap()
        self.assertEqual({row["turn_id"]: row["generation_state"] for row in app.runtime.read_all(
            "SELECT turn_id, generation_state FROM conversation_native_turns", ())},
            {identifier: "failed" for identifier in expected})
        calls = []
        original = NativeConversationTurns.interrupt_open

        def interrupt(owner, *, at):
            calls.append(threading.get_ident())
            return original(owner, at=at)

        with patch.object(NativeConversationTurns, "interrupt_open", interrupt):
            (await self.controller.start()).unwrap()
        self.assertEqual(len(calls), 1)
        self.assertNotEqual(calls[0], threading.get_ident())
        runtime = self.controller.session.runtime
        self.assertEqual({row["turn_id"]: row["generation_state"] for row in runtime.read_all(
            "SELECT turn_id, generation_state FROM conversation_native_turns", ())},
            {identifier: "failed" for identifier in expected})
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertTrue(all(not platform.client._api._wsr_api.calls for platform in self.native.platforms.values()))


if __name__ == "__main__":
    unittest.main()
