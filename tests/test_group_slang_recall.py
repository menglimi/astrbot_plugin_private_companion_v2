from types import SimpleNamespace
import unittest

from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.memory.group.slang import GroupSlang


class GroupSlangRecallTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.item = {"owner": "group-owner", "kind": "slang", "id": "term",
                     "revision": 1, "enabled": 1,
                     "payload": {"term": "蚌埠住了", "text": "本群表达：蚌埠住了；含义：忍不住笑"}}
        self.store = _Store(self.item)
        self.search = _Search(self.item)
        access = SimpleNamespace(check=lambda *args, **kwargs: None)
        app = SimpleNamespace(messages=SimpleNamespace(group_memory=SimpleNamespace(access=access)))
        self.service = SimpleNamespace(app=app, store=self.store, search=self.search,
            owner=lambda context: "group-owner", check=lambda *args, **kwargs: None,
            validate_item=lambda item, context: True)
        self.slang = GroupSlang(self.service)
        self.context = SimpleNamespace(scope=SimpleNamespace(kind=ScopeKind.GROUP))

    async def test_ordinary_group_message_does_not_request_approximate_recall(self):
        result = await self.slang.search(self.context, "今晚回家后一起打游戏，等下开黑")

        self.assertEqual(self.search.calls, [])
        self.assertEqual(result["items"], [])

    async def test_new_slang_candidate_uses_cached_approximate_recall(self):
        query = "“绷不住了”是什么意思？"

        first = await self.slang.search(self.context, query)
        second = await self.slang.search(self.context, query)

        self.assertEqual(len(self.search.calls), 1)
        self.assertEqual(first["items"][0]["id"], "term")
        self.assertEqual(second["items"][0]["id"], "term")

    async def test_different_candidate_in_same_group_respects_recall_cooldown(self):
        await self.slang.search(self.context, "“好家伙”是什么意思？")
        result = await self.slang.search(self.context, "“大聪明”是什么意思？")

        self.assertEqual(len(self.search.calls), 1)
        self.assertEqual(result["fallback_reason"], "group_recall_cooldown")

    def test_learning_candidates_need_repetition_or_an_existing_meaning(self):
        examples = [
            {"index": 0, "text": "今晚“观星局”几点开始？"},
            {"index": 1, "text": "“观星局”九点开"},
            {"index": 2, "text": "“摸鱼王”上线啦"},
            {"index": 3, "text": "又是“摸鱼王”"},
            {"index": 4, "text": "周末“团建券”怎么用"},
            {"index": 5, "text": "“团建券”给谁了"},
            {"index": 6, "text": "普通晚饭安排"},
        ]

        terms, relevant = GroupSlang._promoted_learning_examples(examples)
        self.assertEqual(set(terms), {"观星局", "摸鱼王", "团建券"})
        self.assertEqual([item["index"] for item in relevant], list(range(6)))
        self.assertNotIn(6, [item["index"] for item in relevant])

        terms, relevant = GroupSlang._promoted_learning_examples(
            [{"index": 0, "text": "群里常说“已知梗”"}], known_terms={"已知梗"})
        self.assertEqual(terms, ("已知梗",))
        self.assertEqual(len(relevant), 1)

    def test_single_occurrence_terms_are_not_promoted(self):
        terms, relevant = GroupSlang._promoted_learning_examples([
            {"index": 0, "text": "今天聊到“观星局”"},
            {"index": 1, "text": "普通聊天内容"},
        ])
        self.assertEqual(terms, ())
        self.assertEqual(relevant, [])

    def test_historical_counts_promote_terms_with_current_evidence(self):
        examples = [
            {"index": 0, "text": "今晚又聊到“观星局”"},
            {"index": 1, "text": "普通聊天内容"},
        ]
        terms, relevant = GroupSlang._promoted_learning_examples(
            examples, occurrence_counts={"观星局": 7})
        self.assertEqual(terms, ("观星局",))
        self.assertEqual([item["index"] for item in relevant], [0])

    def test_candidate_frequency_owner_spans_group_member_sessions_only(self):
        install = "installation"
        role = SubjectRef(install, SubjectKind.BOT, "role-a")

        def context(group="group-a", session="member-a", selected_role=role, account="account-a"):
            scope = ScopeRef(install, "onebot", ScopeKind.GROUP, group, "bot-a", account,
                             group, session)
            return SimpleNamespace(scope=scope, role_binding=SimpleNamespace(role=selected_role))

        first = GroupSlang.candidate_owner(context(session="member-a"))
        second = GroupSlang.candidate_owner(context(session="member-b"))
        self.assertEqual(first, second)
        self.assertNotEqual(first, GroupSlang.candidate_owner(context(group="group-b")))
        self.assertNotEqual(first, GroupSlang.candidate_owner(context(
            selected_role=SubjectRef(install, SubjectKind.BOT, "role-b"))))
        self.assertNotEqual(first, GroupSlang.candidate_owner(context(account="account-b")))

    def test_inferred_meanings_require_v1_confidence_floor(self):
        self.assertTrue(GroupSlang._confident_analysis({"confidence": 0.65}))
        self.assertTrue(GroupSlang._confident_analysis({"confidence": 0.9}))
        for item in ({"confidence": 0.64}, {"confidence": True}, {}, {"confidence": float("nan")},
                     {"confidence": 10 ** 1000}):
            self.assertFalse(GroupSlang._confident_analysis(item))

    def test_repeated_candidates_can_be_separated_across_the_full_observation_window(self):
        examples = [{"index": index, "text": f"普通聊天内容 {index}"} for index in range(100)]
        examples[2]["text"] = "今晚“观星局”几点开始？"
        examples[87]["text"] = "“观星局”九点开"
        terms, relevant = GroupSlang._promoted_learning_examples(examples)
        self.assertEqual(terms, ("观星局",))
        self.assertEqual([item["index"] for item in relevant], [2, 87])


class _Store:
    def __init__(self, item):
        self.items = {item["id"]: item}

    def list(self, owner, kind, *, after="", limit=64):
        return [item for identifier, item in sorted(self.items.items())
                if identifier > after and item["owner"] == owner and item["kind"] == kind][:limit]

    def get(self, owner, kind, identifier):
        return self.items[identifier]


class _Search:
    def __init__(self, item):
        self.item = item
        self.calls = []

    async def search(self, owner, kind, text, *, context, limit):
        self.calls.append((owner, kind, text))
        return {"items": [{"id": self.item["id"], "revision": self.item["revision"],
                           "payload": self.item["payload"], "score": 0.8,
                           "similarity": 0.8, "basis": "embedding", "clusters": []}],
                "mode": "hybrid", "embedded": 1, "ranking": "blended", "eligible": 1,
                "complete": True, "fallback_reason": None}
