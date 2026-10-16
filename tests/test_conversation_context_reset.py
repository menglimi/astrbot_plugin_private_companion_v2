"""Native successful resets retire only the matching window's temporary context."""

import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from tests.multi_host_support import MultiFixture
from tests.group_host_support import GroupFixture
from tests.memory_support import MemoryFixture
from tests.contact_schedule_support import ContactScheduleFixture
from tests.test_main_no_reply import ENTRY
from tests.staging_bootstrap_support import wait_for_batch
from companion_v2.conversation.reset import ConversationWindow, batch_current, boundary, reset_window
from companion_v2.execution.models import TaskContext, TaskError, stamp
from companion_v2.memory import codec
from companion_v2.memory.episodes import recent_dialogue_lines
from companion_v2.memory.models import AtomRef, Proposal
from companion_v2.memory.group.access import owner_key as group_owner
from companion_v2.conversation.group_observation import MOOD_KIND, TOPIC_KIND


def remember_confirmed_reply(app, context, batch):
    part = app.runtime.read_one("SELECT part_id FROM conversation_parts WHERE batch_id = ? AND state = 'delivered'",
                                (batch,))[0]
    reference = app.memory.query.objects.source(context, "reply", part, authoritative=True)[0]
    evidence = app.memory.writer.access.capture(context, reference)
    result = app.memory.writer.submit(context, Proposal("add", predicate="先前回复",
        object="已确认发出的内容", representation="机器人曾发送这段回复。", attribution="observed",
        evidence=(evidence,)), operation_key="confirmed-reply-fact").unwrap()
    return AtomRef(result["atom_id"], result["revision"])


def native_event_extras(event):
    extras = {}
    event.get_extra = lambda key, default=None: extras.get(key, default)
    event.set_extra = lambda key, value: extras.__setitem__(key, value)
    event.set_result = lambda result: setattr(event, "result", result)
    event.get_group_id = lambda: event.message_obj.group_id
    event.get_sender_id = lambda: event.message_obj.sender.user_id
    event.get_platform_id = lambda: event.platform_meta.id
    event.role = "member"
    return extras


class NativeContextResetTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    def plugin(self):
        plugin = ENTRY.PrivateCompanionV2StagingPlugin.__new__(ENTRY.PrivateCompanionV2StagingPlugin)
        plugin.staging = self.controller
        return plugin

    async def reset(self, *, identifier="reset-command", target="first"):
        event = self.event(target, identifier, "/reset")
        extras = native_event_extras(event)
        extras["_clean_group_context_session"] = True
        await self.plugin().observe_companion_context_reset(event)
        return event

    def remember_retention(self, app, context, batch, retention):
        row = app.runtime.read_one("SELECT event_json FROM conversation_inputs WHERE batch_id = ?", (batch,))
        source = codec.source(json.loads(row["event_json"])["source"])
        evidence = app.memory.writer.access.capture(context, source)
        item = Proposal("add", predicate=retention, object="临时话题", representation="用户正在讨论临时话题。",
            evidence=(evidence,), retention=retention,
            valid_to=self.clock.now() + timedelta(hours=1) if retention == "short" else None)
        result = app.memory.writer.submit(context, item, operation_key=retention).unwrap()
        return AtomRef(result["atom_id"], result["revision"])

    async def test_reset_with_same_native_cid_clears_recent_context_and_keeps_durable_provenance(self):
        app = await self.start_host()
        context, batch = await self.accepted(text="上个窗口一直在讨论的临时话题")
        transient = [self.remember_retention(app, context, batch, retention) for retention in ("session", "short")]
        durable = self.remember_retention(app, context, batch, "durable")
        reply_fact = remember_confirmed_reply(app, context, batch)
        old_input = app.runtime.read_one("SELECT event_key FROM conversation_inputs WHERE batch_id = ?", (batch,))[0]
        self.assertIsNotNone(app.background_history.latest_reply(context, self.clock.now(), within_minutes=5,
                                                               action="conversation.reply"))
        self.assertIsNotNone(app.memory.query.objects.source(context, "human", old_input))
        before_sources = [tuple(row) for row in app.runtime.read_all("SELECT * FROM sources", ())]

        await self.reset()

        self.assertEqual(self.native.conversations["qq-main"], "conversation-a")
        self.assertFalse(batch_current(app.runtime, batch))
        self.assertIsNone(app.background_history.latest_reply(context, self.clock.now(), within_minutes=5,
                                                            action="conversation.reply"))
        self.assertIsNone(app.background_history.interaction(context, self.clock.now())["latest_input"])
        self.assertIsNone(app.memory.query.objects.source(context, "human", old_input, authoritative=True))
        self.assertEqual(recent_dialogue_lines(app.runtime, app.memory.writer.access, context,
            {"start": stamp(self.clock.now() - timedelta(hours=1)), "end": stamp(self.clock.now() + timedelta(seconds=1))}), ())
        self.assertTrue(app.memory.writer.read(context, durable).is_success)
        self.assertTrue(app.memory.writer.read(context, reply_fact).is_success)
        self.assertTrue(all(not app.memory.writer.read(context, reference).is_success for reference in transient))
        self.assertEqual([tuple(row) for row in app.runtime.read_all("SELECT * FROM sources", ())], before_sources)
        self.clock.advance(timedelta(seconds=1))
        fresh, new_batch = await self.accepted(identifier="fresh-after-reset", text="开始新的话题")
        self.assertEqual(fresh.scope, context.scope)
        self.assertTrue(batch_current(app.runtime, new_batch))
        self.assertEqual(app.background_history.interaction(fresh, self.clock.now())["latest_input"]["event_key"],
                         app.runtime.read_one("SELECT event_key FROM conversation_inputs WHERE batch_id = ?", (new_batch,))[0])

    async def test_new_conversation_does_not_recover_old_dialogue_sources_after_restart(self):
        app = await self.start_host()
        old, batch = await self.accepted(text="新会话不应回收的近期内容")
        old_input = app.runtime.read_one("SELECT event_key FROM conversation_inputs WHERE batch_id = ?", (batch,))[0]
        self.native.conversations["qq-main"] = "new-conversation"
        await self.reset(identifier="new-command")
        await self.controller.terminate()
        self.controller = self.make_controller()
        app = await self.start_host()
        self.clock.advance(timedelta(seconds=1))
        fresh, new_batch = await self.accepted(identifier="after-restart", text="新的对话")
        self.assertNotEqual(old.scope.conversation_id, fresh.scope.conversation_id)
        self.assertIsNone(app.memory.query.objects.source(fresh, "human", old_input))
        self.assertFalse(batch_current(app.runtime, batch))
        self.assertTrue(batch_current(app.runtime, new_batch))

    async def test_other_bot_window_and_failed_or_literal_commands_are_unchanged(self):
        app = await self.start_host()
        first, first_batch = await self.accepted()
        second, second_batch = await self.accepted("second", "second-event", "另一窗口的近期内容")
        for identifier, text in (("failure", "/reset"), ("ordinary", "有人提到了 /new 和 /reset")):
            event = self.event(identifier=identifier, text=text)
            native_event_extras(event)
            await self.plugin().observe_companion_context_reset(event)
            self.assertIsNone(boundary(app.runtime, first.scope))
        await self.reset()
        self.assertFalse(batch_current(app.runtime, first_batch))
        self.assertTrue(batch_current(app.runtime, second_batch))
        self.assertIsNotNone(app.background_history.latest_reply(second, self.clock.now(), within_minutes=5,
                                                               action="conversation.reply"))

    async def test_duplicate_result_hook_cannot_clear_messages_after_the_reset(self):
        app = await self.start_host()
        context, _ = await self.accepted()
        event = await self.reset()
        self.clock.advance(timedelta(seconds=1))
        _, batch = await self.accepted(identifier="after-reset")
        await self.plugin().observe_companion_context_reset(event)
        # A replayed native event object is also idempotent across hook retries.
        replay = self.event(identifier="reset-command")
        replay.created_at = event.created_at
        native_event_extras(replay)["_clean_group_context_session"] = True
        await self.plugin().observe_companion_context_reset(replay)
        self.assertTrue(batch_current(app.runtime, batch, context.scope))

    async def test_native_commands_only_publish_the_marker_after_success(self):
        from astrbot.builtin_stars.builtin_commands.commands.conversation import ConversationCommands
        from astrbot.core.star.session_plugin_manager import sp

        reset_owner = ConversationCommands
        if not callable(getattr(reset_owner, "reset", None)):
            from astrbot.builtin_stars.builtin_commands.main import Main

            reset_owner = Main
        app = await self.start_host()
        context, batch = await self.accepted()
        self.native.get_using_provider = lambda _umo: self.native.provider
        self.native.get_config = lambda **_: {"platform_settings": {"unique_session": False},
                                             "provider_settings": {"agent_runner_type": "local"},
                                             "agent_runner": {"runner_type": "local"}}
        self.native.conversation_manager.get_conversation = AsyncMock(
            return_value=NS(persona_id="original"))
        if reset_owner is ConversationCommands:
            self.native.conversation_manager.update_conversation = AsyncMock(
                side_effect=RuntimeError("synthetic reset failure"))
        else:
            self.native.conversation_manager.new_conversation = AsyncMock(
                side_effect=RuntimeError("synthetic reset failure"))
        event = self.event(identifier="native-failure", text="/reset")
        native_event_extras(event)
        commands = ConversationCommands(self.native)
        reset_instance = commands if reset_owner is ConversationCommands else NS(
            context=self.native, conversation_c=commands)
        with patch.object(sp, "get_async", new=AsyncMock(return_value={})):
            with self.assertRaises(RuntimeError):
                await reset_owner.reset(reset_instance, event)
            await self.plugin().observe_companion_context_reset(event)
            self.assertTrue(batch_current(app.runtime, batch))
            if reset_owner is ConversationCommands:
                self.native.conversation_manager.update_conversation = AsyncMock()
            else:
                self.native.conversation_manager.new_conversation = AsyncMock(return_value="new-id")
            await reset_owner.reset(reset_instance, event)
            result = event.result
            await self.plugin().observe_companion_context_reset(event)
        self.assertIs(event.result, result)
        self.assertFalse(batch_current(app.runtime, batch, context.scope))
        self.native.conversation_manager.new_conversation = AsyncMock(return_value="new-id")
        self.native.conversation_manager.get_conversation = AsyncMock(return_value=NS(persona_id="original"))
        event = self.event(identifier="native-new", text="/new")
        native_event_extras(event)
        await commands.new_conv(event)
        self.assertTrue(event.get_extra("_clean_group_context_session"))

    async def test_third_party_native_commands_publish_the_marker_after_state_clear(self):
        from astrbot.builtin_stars.builtin_commands.commands import conversation as native
        from astrbot_host.conversation_reset import install_native_reset_marker

        reset_owner = native.ConversationCommands
        if not callable(getattr(reset_owner, "reset", None)):
            from astrbot.builtin_stars.builtin_commands.main import Main

            reset_owner = Main
        native_context = NS()
        native_context.get_config = lambda **_: {
            "platform_settings": {"unique_session": False},
            "provider_settings": {"agent_runner_type": "dify"},
            "agent_runner": {"runner_type": "dify"},
        }
        command = native.ConversationCommands(native_context)
        reset_instance = command if reset_owner is native.ConversationCommands else NS(
            context=native_context, conversation_c=command)
        clear = AsyncMock()
        original_reset, original_new = reset_owner.reset, native.ConversationCommands.new_conv
        with patch.object(native, "_clear_third_party_agent_runner_state", clear), \
                patch.object(native.active_event_registry, "stop_all", return_value=0), \
                patch.object(native.sp, "get_async", new=AsyncMock(return_value={})):
            retire = install_native_reset_marker(native_context)
            try:
                new_event = self.event(identifier="third-party-new", text="/new")
                native_event_extras(new_event)
                await command.new_conv(new_event)
                self.assertTrue(new_event.get_extra("_clean_group_context_session"))

                reset_event = self.event(identifier="third-party-reset", text="/reset")
                native_event_extras(reset_event)
                await reset_owner.reset(reset_instance, reset_event)
                self.assertTrue(reset_event.get_extra("_clean_group_context_session"))

                clear.side_effect = RuntimeError("synthetic state clear failure")
                failed = self.event(identifier="failed-third-party-reset")
                native_event_extras(failed)
                with self.assertRaises(RuntimeError):
                    await reset_owner.reset(reset_instance, failed)
                self.assertFalse(failed.get_extra("_clean_group_context_session", False))
            finally:
                retire()
            self.assertIs(native._clear_third_party_agent_runner_state, clear)
            self.assertIs(reset_owner.reset, original_reset)
            self.assertIs(native.ConversationCommands.new_conv, original_new)
        self.assertEqual(clear.await_count, 3)

    async def test_registered_hook_runs_in_native_result_decoration_and_preserves_command_reply(self):
        from astrbot.api.event import MessageEventResult
        from astrbot.core.config.default import DEFAULT_CONFIG
        from astrbot.core.pipeline.result_decorate import stage as native_stage
        from astrbot.core.star.star import star_map
        from astrbot.core.star.star_handler import EventType, StarHandlerRegistry, star_handlers_registry

        app = await self.start_host()
        context, batch = await self.accepted()
        plugin = self.plugin()
        registry = StarHandlerRegistry()
        for metadata in star_handlers_registry.get_handlers_by_module_name(ENTRY.__name__):
            if metadata.handler_name == "observe_companion_context_reset":
                self.assertIs(metadata.event_type, EventType.OnDecoratingResultEvent)
                registry.append(replace(metadata, handler=plugin.observe_companion_context_reset))
        self.assertEqual(len(registry), 1)
        config = deepcopy(DEFAULT_CONFIG)
        config["t2i"] = False
        config["content_safety"]["also_use_in_response"] = False
        config["platform_settings"].update(reply_prefix="", reply_with_mention=False, reply_with_quote=False,
                                           forward_threshold=100000)
        config["platform_settings"]["segmented_reply"]["enable"] = False
        tts_context = NS(
            get_using_tts_provider=lambda _: None,
            get_using_tts_provider_async=AsyncMock(return_value=None),
        )
        ctx = NS(astrbot_config=config, plugin_manager=NS(context=tts_context))
        stage = native_stage.ResultDecorateStage()
        await stage.initialize(ctx)
        event = self.event(identifier="native-decorated-reset", text="/reset")
        extras = native_event_extras(event)
        event.set_result(MessageEventResult().message("宿主命令结果"))
        event.get_result = lambda: event.result
        event.is_stopped = lambda: False
        event.get_platform_name = lambda: "aiocqhttp"
        event.plugins_name = None
        with patch.object(native_stage, "star_handlers_registry", registry), patch.dict(star_map, {
            ENTRY.__name__: NS(name=ENTRY.PLUGIN_NAME, activated=True, reserved=False)
        }):
            async for _ in stage.process(event):
                pass
            self.assertTrue(batch_current(app.runtime, batch, context.scope))
            extras["_clean_group_context_session"] = True
            original = event.result
            async for _ in stage.process(event):
                pass
        self.assertIs(event.result, original)
        self.assertFalse(batch_current(app.runtime, batch, context.scope))

    async def test_reset_while_generation_is_running_prevents_the_old_reply(self):
        app = await self.start_host()
        entered, release = asyncio.Event(), asyncio.Event()
        from tests.native_adapter_support import completion

        async def delayed(_payload, _tools):
            entered.set()
            await release.wait()
            return completion()

        self.native.provider.client.state.behavior = delayed
        batch = (await self.controller.receive_claimed(self.event(identifier="pending"))).unwrap()
        await asyncio.wait_for(entered.wait(), timeout=5)
        await self.reset()
        release.set()
        await asyncio.sleep(0)
        self.assertEqual(app.messages.batch(batch)["state"], "cancelled")
        self.assertEqual(app.flow.row(batch)["state"], "closed")
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])


class GroupWindowResetTests(GroupFixture, unittest.IsolatedAsyncioTestCase):
    async def receive(self, identifier, text, **changes):
        batch = (await self.controller.receive_claimed(self.group_event(identifier=identifier, text=text, **changes))).unwrap()
        await wait_for_batch(self.controller.session, batch)
        app = self.controller.session.application
        return TaskContext.restore(json.loads(app.messages.batch(batch)["context_json"])), batch

    async def test_shared_group_reset_clears_all_speakers_but_keeps_member_session(self):
        app = await self.start_host()
        first, first_batch = await self.receive("shared-first", "群聊旧话题", sender="200")
        second, second_batch = await self.receive("shared-second", "另一成员接话", sender="201")
        unique, unique_batch = await self.receive("unique-first", "成员独立窗口", sender="200", unique=True)
        admission = app.tools.group_participation.admission
        admission.observe(first, text="旧缓存", speaker_id="200", received_at=self.clock.now())
        admission.observe(unique, text="独立缓存", speaker_id="200", received_at=self.clock.now())
        with app.runtime.transaction() as connection:
            app.tools.group_participation.records.write(connection, group_owner(first), MOOD_KIND, {"old": True})
            app.tools.group_participation.records.write(connection, group_owner(first), TOPIC_KIND, {"old": True})
            app.tools.group_participation.records.write(connection, group_owner(unique), MOOD_KIND, {"separate": True})
        event = self.group_event(identifier="group-reset", text="/reset")
        native_event_extras(event)["_clean_group_context_session"] = True

        result = await self.controller.observe_context_reset(event)

        self.assertTrue(result.is_success, result.failure)
        self.assertFalse(batch_current(app.runtime, first_batch))
        self.assertFalse(batch_current(app.runtime, second_batch))
        self.assertTrue(batch_current(app.runtime, unique_batch))
        self.assertNotIn(admission._key(first), admission.observations)
        self.assertIn(admission._key(unique), admission.observations)
        self.assertIsNone(app.tools.group_participation.records.read(group_owner(first), MOOD_KIND))
        self.assertIsNone(app.tools.group_participation.records.read(group_owner(first), TOPIC_KIND))
        self.assertTrue(app.tools.group_participation.records.read(group_owner(unique), MOOD_KIND)["separate"])
        self.clock.advance(timedelta(seconds=1))
        fresh, batch = await self.receive("shared-fresh", "新的群聊话题", sender="201")
        saved = json.loads(app.messages.batch(batch)["contributions_json"])
        self.assertEqual(saved["group_context"]["references"], [])

    async def test_early_group_observations_clear_even_without_a_reply_batch(self):
        app = await self.start_host()
        event = self.group_event(identifier="only-early", text="旧群聊观察")
        self.assertTrue((await self.controller.observe_group_early(event)).is_success)
        self.assertEqual(app.runtime.read_all("SELECT batch_id FROM conversation_batches", ()), ())
        self.assertTrue(app.tools.group_participation.admission.observations)
        reset = self.group_event(identifier="early-reset", text="/reset")
        native_event_extras(reset)["_clean_group_context_session"] = True
        result = await self.controller.observe_context_reset(reset)
        self.assertTrue(result.is_success, result.failure)
        self.assertEqual(app.tools.group_participation.admission.observations, {})
        self.assertEqual(app.runtime.read_all("SELECT key FROM runtime_metadata WHERE key LIKE ?",
                                             ("conversation.group_observation.v1%",)), ())

    async def test_durable_group_statement_and_historical_proof_survive_reset(self):
        from companion_v2.adapters.astrbot.model_wire import tool_alias
        from companion_v2.execution.models import encode
        from tests.native_adapter_support import completion, final_text

        app = await self.start_host()

        async def remember(payload, _tools):
            if not any(item["role"] == "tool" for item in payload["messages"]):
                return completion(tools=[NS(id="remember-old-group", type="function", function=NS(
                    name=tool_alias("group.memory.remember"), arguments=encode(
                        {"input_handle": "group-input-1", "statement": "周六在公园集合"})))])
            return completion(final_text("已记住集合安排。"))

        self.native.provider.client.state.behavior = remember
        first, first_batch = await self.receive("group-statement", "周六在公园集合")
        receipt = json.loads(app.tools._rows(first_batch)[0]["result_json"])["payload"]
        self.native.provider.client.state.behavior = None
        second, second_batch = await self.receive("group-proof", "刚才的安排是什么", sender="201")
        saved = json.loads(app.messages.batch(second_batch)["contributions_json"])
        self.assertTrue(saved["group_context"]["references"])
        reset = self.group_event(identifier="durable-reset", text="/reset")
        native_event_extras(reset)["_clean_group_context_session"] = True
        (await self.controller.observe_context_reset(reset)).unwrap()
        self.assertEqual(app.messages.group_memory.read(second, receipt["memory_id"], receipt["revision"])[0]["statement"],
                         "周六在公园集合")
        app.messages._request(app.messages.batch(second_batch), second, self.clock.now(), historical=True)
        with self.assertRaises(TaskError):
            app.messages._request(app.messages.batch(second_batch), second, self.clock.now())


class TemporaryMemoryResetTests(MemoryFixture, unittest.IsolatedAsyncioTestCase):
    def test_only_temporary_atoms_and_pending_proposals_in_this_native_window_expire(self):
        durable = self.remember()
        session_item = replace(self.proposed(), predicate="临时", retention="session")
        session = self.remember(session_item, key="session")
        short = self.remember(replace(session_item, predicate="短期", retention="short",
            valid_to=self.clock.now() + timedelta(hours=1)), key="short")
        pending = self.memory.submit(self.context, replace(session_item, predicate="待确认", defer_until_boundary=True),
                                     operation_key="pending").unwrap()
        other = self.alternate_context(bot_id=self.context.scope.bot_id, role_id="other-role", session_selector=True)
        other_event = self.event("other-source", context=other)
        self.grant(self.important, other.scope, "text")
        self.accept(other_event, context=other)
        evidence = self.memory.access.capture(other, other_event.source)
        item = replace(session_item, predicate="另一窗口", evidence=(evidence,))
        other_result = self.memory.submit(other, item, operation_key="other").unwrap()

        result = reset_window(self.runtime, ConversationWindow.from_scope(self.context.scope), reset_id="reset", at=self.clock.now())

        self.assertEqual(result["temporary_atoms"], 2)
        self.assertTrue(self.memory.read(self.context, durable).is_success)
        self.assertFalse(self.memory.read(self.context, session).is_success)
        self.assertFalse(self.memory.read(self.context, short).is_success)
        self.assertEqual(self.runtime.read_one("SELECT state FROM memory_operations WHERE operation_id = ?",
                                              (pending["operation_id"],))[0], "discarded")
        self.assertTrue(self.memory.read(other, AtomRef(other_result["atom_id"], other_result["revision"])).is_success)
        self.assertEqual(self.memory.submit(self.context, replace(session_item, predicate="迟到临时"),
                                          operation_key="late").failure.code, "conversation_context_reset")


class BackgroundContextResetTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    async def test_long_term_reply_evidence_keeps_its_background_history_provenance(self):
        from companion_v2.conversation.flow import ConversationPolicy

        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 0)))
        app = host.application
        self.settings(app, {"enabled": True, "dedup_enabled": False}).unwrap()
        for identifier in ("original-contact", "derived-contact"):
            task = (await self.contact(app, self.opportunity(identifier))).unwrap().task
            await self.delivery_state(app, task.task_id, "delivered")
            self.advance(app, 1)
        batch = host.receive(self.event("reply-after-background")).unwrap()
        await self.done(app, batch)
        context = self.context(app, batch)
        self.assertEqual(len(json.loads(app.messages.batch(batch)["contributions_json"])
                             ["background_history"]["references"]), 2)
        durable = remember_confirmed_reply(app, context, batch)
        app.reset_conversation_window(ConversationWindow.from_scope(context.scope), reset_id="reset-proof").unwrap()
        result = app.memory.writer.read(context, durable)
        self.assertTrue(result.is_success, result.failure)
        self.assertEqual(app.background_history.recent(context).unwrap(), ())

    async def test_reset_excludes_confirmed_background_and_late_receipts_without_replaying_unknowns(self):
        app = await self.enabled()
        self.settings(app, {"dedup_enabled": False}).unwrap()
        task = (await self.contact(app, self.opportunity("confirmed"))).unwrap().task
        await self.delivery_state(app, task.task_id, "delivered")
        self.assertEqual(len(app.background_history.recent(self.contact_context()).unwrap()), 1)
        self.advance(app, 1)

        async def unknown(envelope):
            return self.receipt(envelope, "unknown")

        self.send_behavior = unknown
        task = (await self.contact(app, self.opportunity("unknown"))).unwrap().task
        await self.delivery_state(app, task.task_id, "unknown")
        envelope = self.sent[-1]
        context = self.contact_context()
        app.reset_conversation_window(ConversationWindow.from_scope(context.scope), reset_id="reset").unwrap()
        self.assertEqual(app.background_history.recent(context).unwrap(), ())
        self.assertEqual(app.background_history.interaction(context, self.clock.now())["unresolved_contacts"], 1)
        self.advance(app, 1)
        app.record_receipt(self.receipt(envelope)).unwrap()
        self.assertEqual(app.background_history.recent(context).unwrap(), ())
        self.assertEqual(len(self.sent), 2)


if __name__ == "__main__":
    unittest.main()
