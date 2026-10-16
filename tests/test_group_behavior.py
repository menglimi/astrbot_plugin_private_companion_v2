"""Real native tools learn silently; directed habits use genuine send outcomes."""

from tests import test_group_reply_admission as helpers
from tests.group_host_support import GroupFixture

from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace as NS
import unittest

from astrbot.core.agent.message import Message, ToolCall
from astrbot.core.message.components import At, Plain, Reply
from astrbot.core.message.message_event_result import MessageChain
from astrbot_host.core_reply import CORE_REPLY_CONTEXT_EXTRA
from astrbot_host.core_reply_outbound import prepare_core_reply_outbound_message
from astrbot_host.core_reply_tools import native_tool_name
from astrbot_host.management_identity import dashboard_operator
from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.conversation.behavior import GroupBehavior
from companion_v2.conversation.behavior.management import BehaviorManagement
from companion_v2.conversation.behavior.service import FEEDBACK, LEARN, PLAN
from companion_v2.conversation.behavior.store import owner_key
from companion_v2.conversation.participation import CONFIG_GROUP, GroupParticipationConfigurationOwner, configuration_fields
from companion_v2.execution.models import TaskError


class GroupBehaviorTests(GroupFixture, unittest.IsolatedAsyncioTestCase):
    asyncSetUp = helpers.GroupReplyAdmissionTests.asyncSetUp
    event = helpers.GroupReplyAdmissionTests.event
    core_turn = helpers.GroupReplyAdmissionTests.core_turn
    core_send = helpers.GroupReplyAdmissionTests.core_send
    flush_tracking = helpers.GroupReplyAdmissionTests.flush_tracking
    configure = helpers.GroupReplyAdmissionTests.configure
    configure_participation = helpers.GroupReplyAdmissionTests.configure_participation
    choose = helpers.GroupReplyAdmissionTests.choose
    candidate = helpers.GroupReplyAdmissionTests.candidate
    assert_no_v2_generation = helpers.GroupReplyAdmissionTests.assert_no_v2_generation

    @property
    def behavior(self):
        return self.app.tools.group_participation.behavior

    async def call(self, event, action, arguments, *, call_id="behavior-call"):
        call = ToolCall(id=call_id, function=ToolCall.FunctionBody(
            name=native_tool_name(action), arguments=json.dumps(arguments, ensure_ascii=False)))
        wrapper = NS(context=NS(event=event), messages=[Message(role="assistant", tool_calls=[call])])
        tool = event.core_request.func_tool.get_tool(native_tool_name(action))
        self.assertIsNotNone(tool)
        return json.loads(await tool.call(wrapper, **arguments))

    async def seed(self):
        await self.controller.observe_group_early(self.event("human-one", "忙完啦，摸摸大家", sender="201"))
        self.clock.advance(timedelta(seconds=1))
        event = self.event("human-two", "摸摸，今天大家都辛苦啦", mention=True)
        prepared = await self.core_turn(event)
        frame = self.behavior.frame(prepared["context"], prepared["native_input"])
        arguments = {"label": "互相安慰", "situation": "熟人忙完或感到累时，且当前气氛适合接话",
            "action": "自然地对熟悉成员说摸摸", "boundaries": "不要把别人之间的亲昵当作对所有人的许可，尊重对象反应",
            "cues": ["摸摸", "辛苦"], "evidence_handles": list(frame["evidence"])[-2:]}
        result = await self.call(event, LEARN, arguments)
        self.assertEqual(result["state"], "succeeded", result)
        return event, prepared, frame, arguments, result["payload"]["habit_id"]

    async def plan(self):
        event, prepared, frame, _, habit = await self.seed()
        await self.choose(event, "reply", reason="熟悉成员刚忙完，安慰自然")
        handle = next(handle for handle, account in frame["members"].items() if account == "201")
        result = await self.call(event, PLAN, {"habit_id": habit, "target_handle": handle, "reason": "回应熟悉成员的劳累"})
        self.assertEqual(result["state"], "succeeded", result)
        return event, prepared, frame, habit, result["payload"]["attempt_id"]

    async def test_learning_can_end_in_silent_listening_without_model_budget_or_send(self):
        event, prepared, _, _, _ = await self.seed()
        result = await self.choose(event, "skip")
        self.assertEqual(result["state"], "succeeded", result)
        await self.core_send(event, "不会发送的占位文字")
        self.assertEqual(event.sent, [])
        document = self.behavior.store.read(prepared["context"])
        self.assertEqual(len(document["habits"]), 1)
        self.assertEqual(document["attempts"], [])
        self.assert_no_v2_generation()

    async def test_learning_metadata_can_share_a_batch_with_skip(self):
        event, _, _, arguments, _ = await self.seed()
        note = ToolCall(id="quiet-note", function=ToolCall.FunctionBody(
            name=native_tool_name(LEARN), arguments=json.dumps(arguments, ensure_ascii=False)))
        decision = await self.choose(event, "skip", extra_calls=(note,))
        self.assertEqual(decision["state"], "succeeded", decision)
        result = await self.call(event, LEARN, arguments)
        self.assertEqual(result["state"], "succeeded", result)
        self.assertEqual(event.sent, [])

    async def test_role_scoped_review_routes_validate_login_and_persist_commands(self):
        from tests.test_configuration_api import call
        await self.seed()
        self.controller.register_routes()
        handlers = {path: handler for path, handler, _, _ in self.native.registered_web_apis}
        route = next(path for path in handlers if path.endswith("/config/behavior") and "/targets/first/" in path)
        denied = await call(handlers[route], username="api_key:external")
        self.assertEqual(denied["status"], "error")
        status = await call(handlers[route])
        self.assertEqual(status["status"], "ok", status)
        group = status["data"]["groups"][0]
        habit = group["habits"][0]
        saved = await call(handlers[route + "/command"], {"group_key": group["group_key"],
            "habit_id": habit["habit_id"], "revision": habit["revision"], "enabled": False})
        self.assertEqual(saved["status"], "ok", saved)
        self.assertFalse((await call(handlers[route]))["data"]["groups"][0]["habits"][0]["enabled"])
        malformed = await call(handlers[route + "/command"], {"group_key": group["group_key"],
            "habit_id": habit["habit_id"], "revision": habit["revision"], "enabled": "false"})
        self.assertEqual(malformed["status"], "error")

    async def test_habits_follow_role_and_group_across_member_windows_and_restart(self):
        _, prepared, _, _, _ = await self.seed()
        context = prepared["context"]
        another = (await self.controller.observe_group_early(self.group_event(
            identifier="different-native-window", sender="201", unique=True))).unwrap()
        self.assertNotEqual(context.scope.session_id, another.scope.session_id)
        self.assertEqual(owner_key(context), owner_key(another))
        restarted = GroupBehavior(self.app.messages)
        self.assertEqual(len(restarted.store.read(another)["habits"]), 1)
        other_group = (await self.controller.observe_group_early(self.group_event(
            target="group-b", identifier="another-group"))).unwrap()
        self.assertEqual(restarted.store.read(other_group)["habits"], [])
        other_role = replace(context, role_binding=replace(context.role_binding,
            role=replace(context.role_binding.role, subject_id="another-role")))
        self.assertEqual(restarted.store.read(other_role)["habits"], [])

    async def test_plan_is_not_sent_and_first_text_mentions_selected_member_only(self):
        event, prepared, _, _, attempt = await self.plan()
        document = self.behavior.store.read(prepared["context"])
        self.assertEqual(document["attempts"][0]["state"], "planned")
        self.assertNotIn("returned_at", document["attempts"][0])
        self.assertEqual(event.sent, [])
        prepared["outbound_settings"] = {**prepared["outbound_settings"], "reply_quote_enabled": True,
                                        "reply_mention_speaker_enabled": True}
        first = prepare_core_reply_outbound_message(event, prepared, MessageChain(chain=[Plain("摸摸，辛苦啦。")]))
        self.assertEqual([str(part.qq) for part in first.chain if isinstance(part, At)], ["201"])
        self.assertFalse(any(isinstance(part, Reply) for part in first.chain))
        second = prepare_core_reply_outbound_message(event, prepared, MessageChain(chain=[Plain("休息一下吧。")]), segment_index=1)
        self.assertFalse(any(isinstance(part, At) for part in second.chain))
        await self.core_send(event, "摸摸，辛苦啦。")
        saved = next(item for item in self.behavior.store.read(prepared["context"])["attempts"] if item["attempt_id"] == attempt)
        self.assertEqual(saved["state"], "returned")
        self.assertFalse(saved["platform_confirmed"])
        self.assertIn("摸摸", saved["text"])
        self.assert_no_v2_generation()

    async def test_feedback_requires_target_response_after_actual_send_and_remembers_discomfort(self):
        event, prepared, frame, habit, attempt = await self.plan()
        before = await self.call(event, FEEDBACK, {"attempt_id": attempt, "assessment": "welcomed",
            "reason": "不能把原有发言当成反馈", "evidence_handles": list(frame["evidence"])[-1:]})
        self.assertEqual(before["code"], "group_behavior_feedback_invalid")
        await self.core_send(event, "摸摸，辛苦啦。")
        self.clock.advance(timedelta(seconds=1))
        spectator = self.event("spectator", "哈哈", sender="202", mention=True)
        next_prepared = await self.core_turn(spectator)
        other_frame = self.behavior.frame(next_prepared["context"], next_prepared["native_input"])
        wrong = await self.call(spectator, FEEDBACK, {"attempt_id": attempt, "assessment": "welcomed",
            "reason": "旁人的笑声不算对象欢迎", "evidence_handles": list(other_frame["evidence"])[-1:]})
        self.assertEqual(wrong["code"], "group_behavior_feedback_invalid")
        self.clock.advance(timedelta(seconds=1))
        target = self.event("target-boundary", "不要突然摸摸我，有些不舒服", sender="201", mention=True)
        target_prepared = await self.core_turn(target)
        target_frame = self.behavior.frame(target_prepared["context"], target_prepared["native_input"])
        arguments = {"attempt_id": attempt, "assessment": "unwelcome", "reason": "对象明确说不舒服",
                     "evidence_handles": list(target_frame["evidence"])[-1:]}
        result = await self.call(target, FEEDBACK, arguments)
        self.assertEqual(result["state"], "succeeded", result)
        await self.call(target, FEEDBACK, arguments)
        document = self.behavior.store.read(prepared["context"])
        saved = next(item for item in document["habits"] if item["habit_id"] == habit)
        self.assertEqual(len(saved["member_feedback"]["201"]), 1)
        self.assertEqual(saved["member_feedback"]["201"][0]["assessment"], "unwelcome")
        self.clock.advance(timedelta(seconds=1))
        future = self.event("future-context", "今天挺忙的", mention=True)
        await self.core_turn(future)
        self.assertIn("对象明确说不舒服", "".join(part.text for part in future.core_request.extra_user_content_parts))
        self.assertNotIn("对象明确说不舒服", future.core_request.system_prompt)

    async def test_unknown_send_is_not_success_or_feedback_and_cannot_be_replayed(self):
        event, prepared, _, _, attempt = await self.plan()
        state = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
        calls = []

        async def uncertain(*args, **kwargs):
            calls.append(args)
            raise TimeoutError("send outcome unknown")

        state["_original_send"] = uncertain
        await self.plugin.guard_companion_core_delivery(event)
        with self.assertRaises(TimeoutError):
            await event.send("摸摸")
        await self.flush_tracking()
        saved = self.behavior.store.read(prepared["context"])["attempts"][0]
        self.assertEqual(saved["attempt_id"], attempt)
        self.assertEqual(saved["state"], "unknown")
        self.assertNotIn("returned_at", saved)
        try:
            await event.send("摸摸")
        except TaskError as error:
            self.assertEqual(error.code, "core_reply_delivery_unknown")
        self.assertEqual(len(calls), 1)

    async def test_forged_member_and_evidence_handles_are_rejected(self):
        event, prepared, frame, arguments, habit = await self.seed()
        invalid = await self.call(event, LEARN, {**arguments, "evidence_handles": ["invented-evidence"]})
        self.assertEqual(invalid["code"], "group_behavior_evidence_invalid")
        await self.choose(event, "reply")
        invalid = await self.call(event, PLAN, {"habit_id": habit, "target_handle": "201", "reason": "不能用原始账号伪造句柄"})
        self.assertEqual(invalid["code"], "group_behavior_target_invalid")
        self.behavior.observe(prepared["context"], text="角色自己说摸摸", speaker_id="100",
                              received_at=self.clock.now(), event_id="own-echo")
        self.assertFalse(any(item["speaker_id"] == "100" for item in self.behavior.store.observations(prepared["context"])))
        self.assertTrue(all(item["speaker_id"] in ("200", "201") for item in frame["evidence"].values()))

    async def test_personal_habit_cannot_be_applied_to_a_different_member(self):
        event, prepared, frame, arguments, _ = await self.seed()
        member = next(key for key, value in frame["members"].items() if value == "200")
        created = await self.call(event, LEARN, {**arguments, "label": "特定成员的安慰偏好", "member_handle": member})
        await self.choose(event, "reply")
        other = next(key for key, value in frame["members"].items() if value == "201")
        invalid = await self.call(event, PLAN, {"habit_id": created["payload"]["habit_id"],
            "target_handle": other, "reason": "个人习惯不能泛化给其他成员"})
        self.assertEqual(invalid["code"], "group_behavior_target_invalid")
        revised = await self.call(event, LEARN, {**arguments, "habit_id": created["payload"]["habit_id"],
            "label": "保留个人归属的安慰偏好"})
        self.assertEqual(revised["state"], "succeeded", revised)
        saved = next(item for item in self.behavior.store.read(prepared["context"])["habits"]
                     if item["habit_id"] == created["payload"]["habit_id"])
        self.assertEqual(saved["member_id"], "200")

    async def test_learned_cues_admit_judgment_including_mentions_of_other_members(self):
        await self.seed()
        await self.configure(group_wakeup_enabled=True)
        for mention_other in (False, True):
            event = self.event("learned-cue-" + str(mention_other), "今天也辛苦啦", sender="202")
            if mention_other:
                event.message_obj.message.insert(0, NS(type="At", qq="201"))
            admitted = await self.candidate(event)
            self.assertTrue(admitted["admitted"], admitted)
            self.assertEqual(admitted["reason"], "behavior", admitted)
            self.assertEqual(event.sent, [])
        await self.configure(group_wakeup_enabled=False)
        disabled = await self.candidate(self.event("no-wakeup", "今天辛苦啦", sender="202"))
        self.assertFalse(disabled["admitted"], disabled)
        self.assert_no_v2_generation()

    async def test_pausing_a_planned_habit_prevents_actual_delivery(self):
        event, prepared, _, habit, _ = await self.plan()
        manager = BehaviorManagement(self.app, prepared["context"])
        operator = dashboard_operator(self.app.runtime, "admin", at=self.clock.now())
        group = manager.status(operator)["groups"][0]
        item = next(item for item in group["habits"] if item["habit_id"] == habit)
        manager.command(operator, {"group_key": group["group_key"], "habit_id": habit,
            "revision": item["revision"], "enabled": False})
        with self.assertRaises(TaskError) as error:
            await self.core_send(event, "摸摸，辛苦啦。")
        self.assertEqual(error.exception.code, "group_behavior_habit_missing")
        self.assertEqual(event.sent, [])

    async def test_role_defaults_disable_actual_tools_in_all_groups(self):
        _, prepared, _, _, _ = await self.seed()
        context = prepared["context"]
        owner, fields = GroupParticipationConfigurationOwner(self.app.runtime), configuration_fields()
        target = ConfigTarget(context.scope.installation_id, ConfigLayer.ROLE, context.role_binding.role, bot_id=context.scope.bot_id)
        owner.write(target, fields, changes={CONFIG_GROUP + "." + name: False for name in
            ("enable_group_behavior_learning", "enable_group_behavior_imitation", "enable_group_behavior_feedback")},
            reset=(), expected_revision=owner.read(target, fields).revision, observed_at=self.clock.now())
        for group in ("group-a", "group-b"):
            other = (await self.controller.observe_group_early(self.group_event(target=group, identifier="disabled-" + group))).unwrap()
            self.assertEqual(self.behavior.catalog_for(other), ())
        with self.assertRaises(TaskError) as error:
            self.behavior.plan(context, {}, {}, turn_id="disabled", call_id="no", at=self.clock.now())
        self.assertEqual(error.exception.code, "group_behavior_disabled")

    async def test_administrator_can_pause_restore_and_detect_stale_edits(self):
        _, prepared, frame, arguments, habit = await self.seed()
        context = prepared["context"]
        manager = BehaviorManagement(self.app, context)
        operator = dashboard_operator(self.app.runtime, "admin", at=self.clock.now())
        group = manager.status(operator)["groups"][0]
        item = group["habits"][0]
        command = {"group_key": group["group_key"], "habit_id": habit, "enabled": False, "revision": item["revision"]}
        self.behavior.learn(context, frame, {**arguments, "habit_id": habit, "action": "先确认语境再自然安慰"}, at=self.clock.now())
        with self.assertRaises(TaskError) as error:
            manager.command(operator, command)
        self.assertEqual(error.exception.code, "group_behavior_revision_changed")
        fresh = manager.status(operator)["groups"][0]["habits"][0]
        manager.command(operator, {**command, "revision": fresh["revision"]})
        self.assertFalse(manager.status(operator)["groups"][0]["habits"][0]["enabled"])
        # Learning revisions cannot silently restore an administrator-paused habit.
        self.behavior.learn(context, frame, {**arguments, "habit_id": habit}, at=self.clock.now())
        self.assertFalse(manager.status(operator)["groups"][0]["habits"][0]["enabled"])
        fresh = manager.status(operator)["groups"][0]["habits"][0]
        manager.command(operator, {**command, "enabled": True, "revision": fresh["revision"]})
        self.assertTrue(manager.status(operator)["groups"][0]["habits"][0]["enabled"])
        with self.assertRaises(TaskError):
            manager.status(context.actor)


if __name__ == "__main__":
    unittest.main()
