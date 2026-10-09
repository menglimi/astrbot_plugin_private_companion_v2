from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.foundation.refs import ScopeKind
from companion_v2.knowledge.catalog import MemberEntry
from companion_v2.relationships.group_network import (
    LINK_WINDOW_SECONDS,
    attach_member_clues,
    fold_event,
    project_document,
    route_owner_key,
)
from companion_v2.relationships.group_network import GroupRelationshipStore
from companion_v2.storage.runtime import StorageRuntime


def context():
    return SimpleNamespace(
        scope=SimpleNamespace(kind=ScopeKind.GROUP, installation_id="install", platform="onebot",
                              bot_id="bot", account_id="account", native_scope_id="300"),
        role_binding=SimpleNamespace(role=SimpleNamespace(subject_id="role-a")),
    )


def event(account, at, key):
    return SimpleNamespace(principal=SimpleNamespace(native_account_id=account),
                           received_at=at, scoped_key=key, event_id=key)


def person(account, name, *, groups=None, private=False):
    return {"native_account_id": account, "subject_id": "onebot-user:" + account,
            "display_name": name, "name_basis": "platform", "private_chat": private,
            "groups": groups or {}, "total": {"msg_count": 8, "active_days": 3,
                                                "first_seen": "2026-09-01T00:00:00+00:00",
                                                "last_seen": "2026-10-01T00:00:00+00:00"}}


class GroupRelationshipNetworkTests(unittest.TestCase):
    def test_adjacent_members_form_bounded_edge_and_duplicate_event_is_ignored(self):
        at = datetime(2026, 10, 1, tzinfo=timezone.utc)
        document = fold_event(None, context=context(), event=event("200", at, "evt-1"),
                              text="大家好")
        document = fold_event(document, context=context(), event=event("201", at + timedelta(seconds=30), "evt-2"),
                              text="哈哈")
        repeated = fold_event(document, context=context(), event=event("201", at + timedelta(seconds=30), "evt-2"),
                              text="哈哈")
        self.assertEqual(len(repeated["edges"]), 1)
        edge = next(iter(repeated["edges"].values()))
        self.assertEqual(edge["count"], 1)
        self.assertEqual(edge["tone"], "banter")
        self.assertEqual(LINK_WINDOW_SECONDS, 180)

    def test_members_outside_link_window_do_not_form_edge(self):
        at = datetime(2026, 10, 1, tzinfo=timezone.utc)
        document = fold_event(None, context=context(), event=event("200", at, "evt-1"), text="第一条")
        document = fold_event(document, context=context(), event=event("201", at + timedelta(seconds=181), "evt-2"),
                              text="第二条")
        self.assertEqual(document["edges"], {})

    def test_owner_isolated_by_bot_account_group_and_role(self):
        base = ("install", "onebot", "bot", "account", "300", "role-a")
        owner = route_owner_key(*base)
        for index, replacement in ((2, "bot-b"), (3, "account-b"), (4, "301"), (5, "role-b")):
            changed = list(base)
            changed[index] = replacement
            self.assertNotEqual(owner, route_owner_key(*changed))

    def test_acquaintance_card_adds_member_without_fabricating_graph_edge(self):
        document = {"version": "relationships.group-network.v1", "members": {
            "200": {"account_id": "200", "aliases": [], "message_count": 4, "active_days": 2,
                    "first_seen": "2026-09-01T00:00:00+00:00", "last_seen": "2026-10-01T00:00:00+00:00",
                    "recent": []}}, "edges": {}, "updated_at": "2026-10-01T00:00:00+00:00"}
        card_person = person("201", "小禾", groups={"300": {"msg_count": 5, "active_days": 2,
                                                               "last_seen": "2026-10-01T00:00:00+00:00"}},
                             private=True)
        result = project_document(document, people=[card_person], group_id="300")
        by_account = {member["native_account_id"]: member for member in result["members"]}
        self.assertEqual(set(by_account), {"200", "201"})
        self.assertEqual(by_account["201"]["group_observation"]["basis"], "acquaintance_card")
        self.assertEqual(by_account["201"]["acquaintance"]["message_count"], 8)
        self.assertEqual(result["edges"], [])

    def test_only_unique_display_clue_attaches_and_others_stay_unresolved(self):
        result = project_document(None, people=[
            person("200", "阿青", groups={"300": {"msg_count": 1}}),
            person("201", "阿青", groups={"300": {"msg_count": 1}}),
            person("202", "小禾", groups={"300": {"msg_count": 1}}),
        ], group_id="300")
        clues = [
            MemberEntry("direct", name="未命名线索", declared_account_ids=("202",), content="账号声明"),
            MemberEntry("ambiguous", name="阿青", content="同名线索"),
            MemberEntry("unmatched", name="群里新朋友", content="暂无成员对应"),
        ]
        attach_member_clues(result, clues)
        by_account = {member["native_account_id"]: member for member in result["members"]}
        self.assertEqual([item["entry_id"] for item in by_account["202"]["clues"]], ["direct"])
        self.assertEqual(by_account["200"]["clues"], [])
        self.assertEqual(by_account["201"]["clues"], [])
        unresolved = {item["entry_id"]: item for item in result["unmatched_clues"]}
        self.assertEqual(unresolved["ambiguous"]["basis"], "ambiguous_display_label")
        self.assertEqual(unresolved["ambiguous"]["candidate_account_ids"], ["200", "201"])
        self.assertEqual(unresolved["unmatched"]["basis"], "unmatched")

    def test_legacy_aggregate_import_is_idempotent_and_keeps_its_evidence_basis(self):
        with TemporaryDirectory(prefix="companion-v2-group-network-import-") as temporary:
            with StorageRuntime.open(data_root=Path(temporary), installation_id="install") as runtime:
                store = GroupRelationshipStore(runtime)
                members = {
                    "200": {"name": "小禾", "message_count": 5, "active_days": 2,
                            "first_seen": "2026-09-01T00:00:00+00:00",
                            "last_seen": "2026-10-01T00:00:00+00:00",
                            "evidence_basis": "v1_group_aggregate"},
                    "201": {"name": "阿青", "message_count": 3, "active_days": 1,
                            "first_seen": None, "last_seen": None,
                            "evidence_basis": "v1_group_aggregate"},
                }
                edges = [{"a": "200", "b": "201", "count": 2,
                          "last_seen": "2026-10-01T00:00:00+00:00", "tone": "banter",
                          "summary": "V1 历史汇总显示有玩笑或接梗",
                          "evidence_basis": "v1_group_aggregate"}]

                first = store.import_legacy_aggregate(context(), source_key="legacy-source-1",
                                                       members=members, edges=edges)
                repeated = store.import_legacy_aggregate(context(), source_key="legacy-source-1",
                                                          members=members, edges=edges)
                projection = store.projection(context())

        self.assertEqual(first["members_added"], 2)
        self.assertEqual(first["edges_added"], 1)
        self.assertTrue(repeated["duplicate"])
        by_account = {item["native_account_id"]: item for item in projection["members"]}
        self.assertEqual(by_account["200"]["group_observation"]["basis"], "legacy_aggregate")
        self.assertEqual(by_account["200"]["group_observation"]["message_count"], 5)
        self.assertEqual(projection["edges"][0]["evidence_basis"], "v1_group_aggregate")

    def test_imported_group_larger_than_previous_capacity_survives_live_observation(self):
        at = datetime(2026, 10, 1, tzinfo=timezone.utc)
        members = {str(index): {"name": f"成员{index}", "message_count": index,
                    "first_seen": at.isoformat(), "last_seen": at.isoformat(),
                    "evidence_basis": "v1_group_aggregate"} for index in range(375)}
        edges = [{"a": str(index), "b": str(index + 1), "count": index + 1,
                  "last_seen": at.isoformat(), "tone": "ordinary",
                  "summary": "V1 历史汇总", "evidence_basis": "v1_group_aggregate"}
                 for index in range(81)]
        document = {"version": "relationships.group-network.v1", "members": members,
                    "edges": {f"{item['a']}:{item['b']}": item for item in edges},
                    "last": None, "event_keys": [], "updated_at": at.isoformat()}

        observed = fold_event(document, context=context(), event=event("new", at, "new-event"),
                              text="刚进群", at=at)

        self.assertEqual(len(observed["members"]), 376)
        self.assertEqual(len(observed["edges"]), 81)


if __name__ == "__main__":
    unittest.main()
