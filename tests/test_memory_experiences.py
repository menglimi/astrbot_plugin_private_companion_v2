from dataclasses import replace
import unittest

from companion_v2.memory.experiences import MemoryExperiences
from companion_v2.memory.models import AtomRef
from tests.memory_support import MemoryFixture


class MemoryExperienceTests(MemoryFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.views = MemoryExperiences(self.memory)

    def test_object_navigation_returns_original_sources_and_a_correction_invalidates_it(self):
        item = self.proposed()
        ref = self.remember(item)
        args = dict(view_id="coffee-day", expected_revision=0, title="雨天在书桌旁聊天",
            statements=({"text": "聊到饮用偏好，对方说不喝咖啡。", "evidence": (), "atoms": (ref,)},), entities=("物件:书桌",))
        saved = self.views.save(self.context, operation_key="experience", **args).unwrap()
        self.assertEqual(self.views.save(self.context, operation_key="experience", **args).unwrap(), saved)
        self.assertEqual(self.views.list(self.context, entity="物件:书桌").unwrap()["items"][0]["view_id"], "coffee-day")
        result = self.query("书桌", kind="experiences", subjects=["物件:书桌"]).unwrap()
        handle = result["items"][0]["statements"][0]["sources"][0]
        self.assertIn("咖啡", self.recall.source(self.context, "query", handle=handle).unwrap()["text"])
        self.memory.submit(self.context, replace(item, operation="correct", target=ref, evidence=(self.evidence("现在喝咖啡"),),
            object="喝咖啡", representation="现在喝咖啡。"), operation_key="fix").unwrap()
        self.assertFalse(self.views.read(self.context, "coffee-day").is_success)
        self.assertEqual(self.query("书桌", kind="experiences").unwrap()["items"], [])

    def test_logical_forget_removes_direct_source_experience_from_recall(self):
        item = self.proposed()
        ref = self.remember(item)
        self.views.save(self.context, view_id="private", expected_revision=0, title="聊天片段",
            statements=({"text": "不喝咖啡。", "evidence": item.evidence, "atoms": ()},)).unwrap()
        self.query(kind="all").unwrap()
        self.memory.forget(self.context, ref, evidence=(self.evidence("忘记"),), operation_key="forget").unwrap()
        self.assertFalse(self.views.read(self.context, "private").is_success)
        self.assertEqual(self.query(kind="all").unwrap()["items"], [])
        paraphrased = replace(item, predicate="新表述", representation="平时远离咖啡")
        self.assertFalse(self.memory.submit(self.context, paraphrased, operation_key="paraphrased").is_success)

    def test_cross_person_view_and_unsourced_statement_are_rejected(self):
        evidence = self.evidence()
        self.views.save(self.context, view_id="private", expected_revision=0, title="聊天",
            statements=({"text": "偏好", "evidence": (evidence,), "atoms": ()},)).unwrap()
        self.assertFalse(self.views.read(self.context_for(self.core), "private").is_success)
        with self.assertRaises(ValueError):
            self.views.save(self.context, view_id="unsourced", expected_revision=0, title="臆测",
                statements=({"text": "无来源内容", "evidence": (), "atoms": ()},))
