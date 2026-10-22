"""Per-person acquaintance cards: counting, platform names, prompt card and recall tool."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from companion_v2.adapters.astrbot.model_wire import tool_alias
from companion_v2.execution.models import TaskContext, encode
from companion_v2.foundation.refs import ScopeKind
from companion_v2.memory.person.access import owner_key
from companion_v2.memory.person.admin_names import PersonAcquaintanceNameManagement
from companion_v2.memory.person.configuration import AcquaintanceSettings
from companion_v2.memory.person.management import PersonAcquaintanceDirectory
from companion_v2.memory.person.models import KIND, MAX_CONTEXTS, count_input, display_name, empty_document
from astrbot_host.management_identity import dashboard_operator
from tests.group_host_support import GroupFixture
from tests.native_adapter_support import completion, final_text
from tests.staging_bootstrap_support import wait_for_batch


class StubSettings:
    def __init__(self, values):
        self.values = values

    def read(self, context):
        return dict(self.values)


def group_scope(group_id):
    return NS(kind=ScopeKind.GROUP, native_scope_id=group_id)


class PersonAcquaintanceTests(GroupFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.sequence = 0

    async def receive(self, text="大家好", *, sender="200", commands=(), nickname=None, card=None, **options):
        async def respond(payload, tools):
            done = len([m for m in payload["messages"] if m["role"] == "tool"])
            if done < len(commands):
                action, arguments = commands[done]
                return completion(tools=[NS(id="command-" + str(done), type="function",
                    function=NS(name=tool_alias(action), arguments=encode(arguments)))])
            return completion(final_text("收到。"))
        self.native.provider.client.state.behavior = respond
        self.sequence += 1
        event = self.group_event(sender=sender, identifier="person-" + str(self.sequence), text=text, **options)
        if nickname is not None or card is not None:
            sender_document = dict(event.message_obj.raw_message["sender"])
            if nickname is not None:
                sender_document["nickname"] = nickname
            if card is not None:
                sender_document["card"] = card
            event.message_obj.raw_message["sender"] = sender_document
        result = await self.controller.receive_claimed(event)
        self.assertTrue(result.is_success, result.failure)
        batch_id = result.unwrap()
        await wait_for_batch(self.controller.session, batch_id)
        app = self.controller.session.application
        context = TaskContext.restore(json.loads(app.messages.batch(batch_id)["context_json"]))
        return context, batch_id

    @property
    def app(self):
        return self.controller.session.application

    def card(self, context):
        return self.app.messages.acquaintance.row(owner_key(context))

    def materials(self, context, batch):
        return self.app.messages._request(self.app.messages.batch(batch), context, self.clock.now()).context.materials

    async def test_group_inputs_accumulate_in_one_per_person_card(self):
        await self.start_host()
        first, _ = await self.receive(sender="200")
        second, _ = await self.receive(sender="200")
        other, _ = await self.receive(sender="201")
        row = self.card(first)
        self.assertIsNotNone(row)
        self.assertEqual(row["kind"], KIND)
        document = json.loads(row["document_json"])
        self.assertEqual(document["contexts"]["group:300"],
                         {**document["contexts"]["group:300"], "msg_count": 2, "active_days": 1})
        self.assertEqual(json.loads(self.card(other)["document_json"])["contexts"]["group:300"]["msg_count"], 1)
        self.assertEqual(owner_key(first), owner_key(second))
        # Replaying an already admitted input must not count twice.
        replay = self.group_event(sender="200", identifier="person-1", text="大家好")
        result = await self.controller.receive_claimed(replay)
        self.assertTrue(result.is_success, result.failure)
        document = json.loads(self.card(first)["document_json"])
        self.assertEqual(document["contexts"]["group:300"]["msg_count"], 2)

    async def test_same_person_spans_groups_but_not_companions(self):
        await self.start_host()
        in_a, _ = await self.receive(sender="200", target="group-a")
        in_b, _ = await self.receive(sender="200", target="group-b")
        in_c, _ = await self.receive(sender="200", target="group-c")
        self.assertEqual(owner_key(in_a), owner_key(in_b))
        self.assertNotEqual(owner_key(in_a), owner_key(in_c))
        document = json.loads(self.card(in_a)["document_json"])
        self.assertEqual(sorted(document["contexts"]), ["group:300", "group:301"])

    async def test_platform_names_come_from_the_authenticated_event(self):
        await self.start_host()
        context, batch = await self.receive(sender="200", nickname="  小明 ", card="明哥")
        document = json.loads(self.card(context)["document_json"])
        self.assertEqual(document["platform_nickname"], "小明")
        self.assertEqual(document["group_cards"]["300"]["card"], "明哥")
        material = next(m for m in self.materials(context, batch) if m.purpose == "current_person_card")
        payload = json.loads(material.payload)
        # The group card wins over the account nickname; both stay platform views.
        self.assertEqual((payload["display_name"], payload["name_basis"]), ("明哥", "platform"))
        self.assertEqual(payload["msg_count"], 1)

    async def test_card_is_injected_for_private_owners_too(self):
        await self.start_host()
        context, batch = await self.accepted(identifier="person-private-1", text="晚上好")
        row = self.card(context)
        self.assertIsNotNone(row)
        document = json.loads(row["document_json"])
        self.assertEqual(document["contexts"]["private"]["msg_count"], 1)
        material = next(m for m in self.materials(context, batch) if m.purpose == "current_person_card")
        self.assertEqual(json.loads(material.payload)["msg_count"], 1)

    async def test_recall_tool_covers_self_known_and_unknown_members(self):
        await self.start_host()
        speaker, _ = await self.receive(sender="200", nickname="小明")
        # 201 speaks while the feature is disabled: a trusted binding exists, but no card row.
        self.app.messages.acquaintance.settings = StubSettings(
            {"person.acquaintance_enabled": False, "person.acquaintance_card_chars": 1024})
        await self.receive(sender="201", text="默默潜水")
        self.app.messages.acquaintance.settings = self.app.acquaintance_settings
        asker, batch = await self.receive(sender="202", text="你们聊",
            commands=[("acquaintance.recall", {"speaker_id": "201"}),
                      ("acquaintance.recall", {"speaker_id": "200"}),
                      ("acquaintance.recall", {"speaker_id": "999"})])
        results = [json.loads(row["result_json"]) for row in self.app.tools._rows(batch)]
        self.assertEqual(results[0]["state"], "succeeded")
        self.assertEqual((results[0]["payload"]["speaker_id"], results[0]["payload"]["state"]), ("201", "unacquainted"))
        self.assertEqual(results[1]["state"], "succeeded")
        self.assertEqual((results[1]["payload"]["speaker_id"], results[1]["payload"]["display_name"]), ("200", "小明"))
        self.assertEqual(results[1]["payload"]["contexts"]["group:300"]["msg_count"], 1)
        self.assertEqual(results[2]["state"], "failed")
        for context in (speaker, asker):
            actions = {tool.action for tool in self.app.tools.catalog_for(context)}
            self.assertIn("acquaintance.recall", actions)

    async def test_disabled_or_unwired_feature_stays_out_of_intake_and_catalog(self):
        await self.start_host()
        context, _ = await self.receive(sender="200")
        self.assertIsNotNone(self.card(context))
        self.app.messages.acquaintance.settings = StubSettings(
            {"person.acquaintance_enabled": False, "person.acquaintance_card_chars": 1024})
        try:
            disabled, batch = await self.receive(sender="200")
            document = json.loads(self.card(context)["document_json"])
            self.assertEqual(document["contexts"]["group:300"]["msg_count"], 1)  # counting stopped
            self.assertNotIn("acquaintance.recall", {tool.action for tool in self.app.tools.catalog_for(disabled)})
            self.assertFalse(any(m.purpose == "current_person_card" for m in self.materials(disabled, batch)))
        finally:
            self.app.messages.acquaintance.settings = self.app.acquaintance_settings

    async def test_directory_lists_cards_for_authorized_routes_only(self):
        await self.start_host()
        context, _ = await self.receive(sender="200")
        await self.receive(sender="201", target="group-c")  # another companion's card
        role_id = context.role_binding.role.subject_id
        routes = [{"platform": "qq-main", "bot_id": "bot-a", "account_id": "100", "role_id": role_id}]
        directory = PersonAcquaintanceDirectory(self.app.runtime)
        result = directory.directory(routes)
        self.assertEqual({person["native_account_id"] for person in result["persons"]}, {"200"})
        person = result["persons"][0]
        self.assertEqual(person["groups"]["300"]["msg_count"], 1)
        self.assertFalse(person["private_chat"])
        self.assertTrue(person["group_member"], "在群里出现过的人就是群友")
        self.assertEqual(result["counts"], {"total": 1, "private_chat": 0, "group_member": 1,
                                            "both": 0, "private_only": 0, "group_only": 1})
        private_context, _ = await self.accepted(identifier="directory-private", text="晚上好")
        result = directory.directory(routes)
        self.assertEqual(result["counts"]["private_chat"], 1)
        owner = next(person for person in result["persons"] if person["private_chat"])
        self.assertEqual(owner["native_account_id"], private_context.actor.principal.native_account_id)
        self.assertEqual(owner["display_name"] or "", owner["display_name"] or "")  # name may be unset

    async def test_private_user_and_group_friend_are_two_independent_dimensions(self):
        """同一个人可以既私聊过、又是某个群的成员。

        旧口径按"有没有私聊"二选一：这样的人只出现在私聊用户里，群友视图看不见他，
        而他确实还在那些群里。这条锁住两个维度各自独立、三个计数各按各的口径。
        """
        await self.start_host()
        context, _ = await self.receive(sender="200")          # 群 300 里的成员
        private_context, _ = await self.accepted(identifier="directory-both", text="晚上好")  # 同一个人私聊
        role_id = context.role_binding.role.subject_id
        routes = [{"platform": "qq-main", "bot_id": "bot-a", "account_id": "100", "role_id": role_id}]

        result = PersonAcquaintanceDirectory(self.app.runtime).directory(routes)
        both = [person for person in result["persons"] if person["private_chat"] and person["group_member"]]
        self.assertTrue(both, "既私聊过又在群里的人应当在两个维度上都为真")
        self.assertEqual(both[0]["native_account_id"], private_context.actor.principal.native_account_id)
        counts = result["counts"]
        self.assertEqual(counts["both"], len(both))
        self.assertEqual(counts["private_only"], counts["private_chat"] - counts["both"])
        self.assertEqual(counts["group_only"], counts["group_member"] - counts["both"])
        self.assertGreaterEqual(counts["group_member"], 1)

    async def test_administrator_name_priority_clear_revision_and_operation_replay(self):
        await self.start_host()
        context, _ = await self.receive(sender="200", nickname="平台昵称", card="群名片")
        row = self.card(context)
        manager = PersonAcquaintanceNameManagement(self.app.runtime)
        operator = dashboard_operator(self.app.runtime, "admin", at=self.clock.now())
        route = {"platform": context.scope.platform, "bot_id": context.scope.bot_id,
                 "account_id": context.scope.account_id, "role_id": context.role_binding.role.subject_id}
        command = dict(subject_id=context.actor.subject.subject_id, platform=route["platform"],
            bot_id=route["bot_id"], account_id=route["account_id"], role_id=route["role_id"],
            native_account_id=context.actor.principal.native_account_id, nickname="  管理员 称呼  ",
            expected_revision=row["revision"], operation_key="name-save-1")

        saved = manager.set_nickname(operator, routes=(route,), observed_at=self.clock.now(), **command).unwrap()
        self.assertEqual((saved["admin_nickname"], saved["name_basis"], saved["revision"]),
                         ("管理员 称呼", "administrator", row["revision"] + 1))
        document = json.loads(self.card(context)["document_json"])
        self.assertEqual(document["admin_nickname_updated_at"], saved["updated_at"])
        self.assertEqual((display_name(document, context.scope)), ("管理员 称呼", "administrator"))

        replayed = manager.set_nickname(operator, routes=(route,), observed_at=self.clock.now(), **command).unwrap()
        self.assertTrue(replayed["replayed"])
        self.assertEqual(self.card(context)["revision"], row["revision"] + 1)

        stale = dict(command, operation_key="name-save-stale", nickname="旧称呼")
        self.assertEqual(manager.set_nickname(operator, routes=(route,), observed_at=self.clock.now(),
            **stale).failure.code, "person_nickname_revision_conflict")
        forged = dict(command, operation_key="name-save-forged", expected_revision=self.card(context)["revision"])
        self.assertEqual(manager.set_nickname(operator, routes=(dict(route, bot_id="other-bot"),),
            observed_at=self.clock.now(), **forged).failure.code, "acquaintance_person_unknown")

        cleared = manager.set_nickname(operator, routes=(route,), subject_id=command["subject_id"],
            platform=command["platform"], bot_id=command["bot_id"], account_id=command["account_id"],
            role_id=command["role_id"], native_account_id=command["native_account_id"], nickname="",
            expected_revision=self.card(context)["revision"], operation_key="name-clear-1",
            observed_at=self.clock.now()).unwrap()
        self.assertIsNone(cleared["admin_nickname"])
        self.assertEqual((cleared["display_name"], cleared["name_basis"]), ("平台昵称", "platform"))
        self.assertEqual(cleared["revision"], row["revision"] + 2)

    async def test_person_configuration_group_is_registered_with_defaults(self):
        await self.start_host()
        fields = {field.field_id: field for field in self.app.configuration.registry.group("person")}
        self.assertEqual(fields["person.acquaintance_enabled"].default, True)
        self.assertEqual(fields["person.acquaintance_card_chars"].default, 1024)
        self.assertEqual(fields["person.cross_window_awareness_enabled"].default, True)
        self.assertEqual(fields["person.cross_window_attention_wait_seconds"].default, 3)
        self.assertEqual(fields["person.cross_window_peer_minutes"].default, 5)
        self.assertEqual(fields["person.cross_window_peer_reply_minutes"].default, 60)
        context, _ = await self.receive(sender="200")
        values = AcquaintanceSettings(self.app.configuration).read(context)
        self.assertEqual(values["person.acquaintance_enabled"], True)
        self.assertEqual(values["person.cross_window_max_items"], 4)
        self.assertEqual(values["person.cross_window_peer_reply_minutes"], 60)


class PersonCardModelTests(unittest.TestCase):
    def test_distinct_day_counting_per_context(self):
        document = {"contexts": {}}
        count_input(document, group_scope("300"), "t1", "2026-09-26")
        count_input(document, group_scope("300"), "t2", "2026-09-26")
        entry = document["contexts"]["group:300"]
        self.assertEqual((entry["msg_count"], entry["active_days"]), (2, 1))
        count_input(document, group_scope("300"), "t3", "2026-09-27")
        self.assertEqual((entry["msg_count"], entry["active_days"]), (3, 2))
        count_input(document, NS(kind=ScopeKind.PRIVATE, native_scope_id="200"), "t4", "2026-09-27")
        self.assertIn("private", document["contexts"])

    def test_pruning_keeps_the_card_bounded(self):
        document = empty_document()
        for index in range(MAX_CONTEXTS + 4):
            count_input(document, group_scope(str(index)), "t" + str(index), "2026-09-26")
        self.assertEqual(len(document["contexts"]), MAX_CONTEXTS)
        self.assertIn("group:" + str(MAX_CONTEXTS + 3), document["contexts"])

    def test_memory_group_and_top_level_do_not_import_person(self):
        offenders = [path for root in (Path("companion_v2/memory"), Path("companion_v2/memory/group"))
                     for path in sorted(root.glob("*.py"))
                     if "memory.person" in path.read_text(encoding="utf-8")]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
