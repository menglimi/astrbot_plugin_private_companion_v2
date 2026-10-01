from dataclasses import replace
from datetime import timedelta
import json
import unittest

from companion_v2.execution.models import digest
from companion_v2.memory.models import AtomRef
from companion_v2.memory.search import SearchIndex
from tests.memory_support import MemoryFixture


class MemoryQueryTests(MemoryFixture, unittest.IsolatedAsyncioTestCase):
    def test_chinese_recall_and_original_source_paging_share_budget(self):
        ref = self.remember()
        result = self.query().unwrap()
        self.assertEqual(result["items"][0]["atom_id"], ref.atom_id)
        handle = result["items"][0]["sources"][0]
        source = self.recall.source(self.context, "query", handle=handle, max_chars=8).unwrap()
        self.assertEqual(source["text"], "private ")
        self.assertEqual(source["next_offset"], 8)
        status = self.recall.status(self.context, "query").unwrap()
        self.assertEqual(len(status["reads"]), 1)
        self.assertEqual(status["remaining_calls"], self.memory.policy.turn_calls - 3)

    def test_source_search_works_without_any_fact(self):
        self.evidence("木桌上的蓝杯已经改成绿色")
        result = self.query("蓝杯", kind="sources").unwrap()
        self.assertEqual(len(result["items"]), 1)
        self.assertIn("绿色", result["items"][0]["excerpt"])
        self.assertEqual(result["items"][0]["source_kind"], "human_message")
        self.assertEqual(self.query("不存在的词", kind="facts").unwrap()["items"], [])

    def test_cursor_rejects_changed_result_set_and_cannot_reset_budget(self):
        base = replace(self.proposed(), single_value=False)
        for i in range(3):
            self.remember(replace(base, predicate="颜色" + str(i), representation="不同的蓝色杯子 " + str(i)), key=str(i))
        result = self.query("蓝色", limit=1).unwrap()
        cursor = result["next_cursor"]
        self.assertIsNotNone(cursor)
        self.remember(replace(base, predicate="第四种颜色", representation="蓝色图画"), key="four")
        self.assertEqual(self.query("蓝色", limit=1, cursor=cursor).failure.code, "memory_cursor_stale")
        for i in range(self.memory.policy.turn_calls - 1):
            self.query("unknown-" + str(i)).unwrap()
        self.assertEqual(self.query().failure.code, "memory_query_budget_exhausted")

    def test_different_query_kinds_keep_their_indexes(self):
        self.remember()
        self.assertTrue(self.query(kind="facts").unwrap()["items"])
        self.assertTrue(self.query(kind="all").unwrap()["items"])
        self.assertTrue(self.query(kind="facts").unwrap()["items"])

    def test_old_low_rank_target_is_not_excluded_before_lexical_or_vector_ranking(self):
        index = SearchIndex(self.runtime.data_root)
        docs = [{"id": str(i), "text": "普通背景", "revision": 1} for i in range(1300)]
        docs.append({"id": "old", "text": "星际航行约定", "revision": 1})
        index.sync("owner", docs)
        ranked, mode, _ = index.rank("owner", "星际航行", allowed={d["id"] for d in docs})
        self.assertEqual(ranked[0], "old")
        index.put_vector("owner", "old", model="embedding-test@1", values=(1., 0.), expected_hash=digest(docs[-1]))
        ranked, mode, coverage = index.rank("owner", "unrelated", allowed={d["id"] for d in docs}, vector=(1., 0.), model="embedding-test@1")
        self.assertEqual(ranked[0], "old")
        self.assertEqual(mode, "hybrid")
        self.assertEqual(coverage["embedded"], 1)
        self.assertEqual(index.rank("another-owner", "星际", allowed={"old"})[0], [])
