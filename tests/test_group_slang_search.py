"""Group vocabulary web reference: candidates stay inside owned samples, evidence never overrides."""

import unittest

from companion_v2.memory.group.slang import CANDIDATE_PROMPT, EXTERNAL_NOTE, GroupSlang
from companion_v2.storage.semantic import DEFAULTS


class FakeStore:
    def __init__(self, settings=None):
        self.settings_value = {**DEFAULTS, **(settings or {})}

    def settings(self):
        return dict(self.settings_value)


class FakeAccess:
    def check(self, context, action):
        return None


class FakeGateway:
    def __init__(self, port):
        self.port = port


class FakePort:
    """Two-stage stub: the candidate pass returns bare strings, the vocabulary pass returns items."""

    def __init__(self, *, candidates, meanings=(), slang_search=None):
        self.candidates, self.meanings = candidates, meanings
        self.slang_search = slang_search
        self.prompts = []

    async def analyze(self, identifier, prompt, images=()):
        self.prompts.append(prompt)
        return self.candidates if prompt.startswith(CANDIDATE_PREFIX) else list(self.meanings)


class FakeSearchPort:
    def __init__(self, results=None, *, available=True):
        self.available = available
        self.results = results if results is not None else [
            {"title": "网络词条", "summary": "外部解释", "source": "网页搜索"}]
        self.queries = []

    async def search(self, term, limit):
        self.queries.append((term, limit))
        return self.results[:limit]


CANDIDATE_PREFIX = CANDIDATE_PROMPT.split("{n}")[0]


class SlangHarness(unittest.IsolatedAsyncioTestCase):
    def build(self, *, settings=None, port=None):
        """A GroupSlang over just the pieces the reference chain touches."""
        store = FakeStore(settings)
        group_memory = type("GroupMemory", (), {"access": FakeAccess(), "runtime": None})()
        messages = type("Messages", (), {"group_memory": group_memory})()
        service = type("Service", (), {})()
        service.store = store
        service.gateway = FakeGateway(port or FakePort(candidates=["小灯"]))
        service.app = type("App", (), {"messages": messages})()
        service.owner = lambda context: "owner-1"
        return GroupSlang(service), store

    @staticmethod
    def candidates(slang, terms, *, limit=4):
        examples = [{"index": 0, "text": "今晚打小灯，老地方见"}]
        cfg = {"analysis_provider": "", "slang_web_search_candidates": limit, "timeout_seconds": 5}
        return slang._candidate_terms(cfg, examples, 5)

    @staticmethod
    def reference(slang, *, results=2):
        cfg = {"analysis_provider": "", "slang_web_search_candidates": 4,
               "slang_web_search_results": results, "timeout_seconds": 5}
        return slang._external_reference(cfg, [{"index": 0, "text": "今晚打小灯，老地方见"}], 5)


class CandidateSelectionTests(SlangHarness):
    async def test_candidates_are_limited_to_terms_present_in_owned_samples(self):
        slang, _ = self.build(port=FakePort(candidates=["小灯", "完全没出现过的词", "小灯"]))
        self.assertEqual(await self.candidates(slang, None), ["小灯"])

    async def test_candidate_count_honours_the_configured_bound(self):
        slang, _ = self.build(port=FakePort(candidates=["小灯", "老地方", "今晚"]))
        self.assertEqual(await self.candidates(slang, None, limit=2), ["小灯", "老地方"])

    async def test_non_string_and_blank_candidates_are_discarded(self):
        slang, _ = self.build(port=FakePort(candidates=[None, 3, "  ", "小灯"]))
        self.assertEqual(await self.candidates(slang, None), ["小灯"])


class ReferenceCollectionTests(SlangHarness):
    async def test_reference_is_empty_when_no_endpoint_is_configured(self):
        slang, _ = self.build(port=FakePort(candidates=["小灯"], slang_search=None))
        self.assertEqual(await self.reference(slang), [])

    async def test_reference_is_empty_when_the_endpoint_reports_itself_unavailable(self):
        slang, _ = self.build(port=FakePort(candidates=["小灯"], slang_search=FakeSearchPort(available=False)))
        self.assertEqual(await self.reference(slang), [])

    async def test_reference_records_the_term_and_its_bounded_results(self):
        search = FakeSearchPort([{"title": t, "summary": "s", "source": "网页搜索"} for t in "ABC"])
        slang, _ = self.build(port=FakePort(candidates=["小灯"], slang_search=search))
        reference = await self.reference(slang)
        self.assertEqual([item["term"] for item in reference], ["小灯"])
        self.assertEqual(len(reference[0]["results"]), 2)
        self.assertEqual(search.queries, [("小灯", 2)])

    async def test_a_failing_search_degrades_to_no_reference_without_raising(self):
        class Broken(FakeSearchPort):
            async def search(self, term, limit):
                raise RuntimeError("network down")

        slang, _ = self.build(port=FakePort(candidates=["小灯"], slang_search=Broken()))
        self.assertEqual(await self.reference(slang), [])

    async def test_an_empty_result_set_is_not_recorded_as_evidence(self):
        slang, _ = self.build(port=FakePort(candidates=["小灯"], slang_search=FakeSearchPort([])))
        self.assertEqual(await self.reference(slang), [])


class SettingsContractTests(unittest.TestCase):
    def test_new_keys_default_to_off_with_bounded_ranges(self):
        self.assertIs(DEFAULTS["slang_web_search_enabled"], False)
        self.assertEqual(DEFAULTS["slang_web_search_candidates"], 4)
        self.assertEqual(DEFAULTS["slang_web_search_results"], 2)

    def test_external_note_subordinates_web_evidence_to_in_group_samples(self):
        self.assertIn("只作参考证据", EXTERNAL_NOTE)
        self.assertIn("不得用外部解释覆盖", EXTERNAL_NOTE)
        self.assertIn("以本群样例为准", EXTERNAL_NOTE)

    def test_configure_rejects_out_of_range_search_settings(self):
        from companion_v2.storage.semantic import SemanticStore
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as root:
            store = SemanticStore(Path(root))
            revision = store.settings()["revision"]
            with self.assertRaises(ValueError):
                store.configure({"slang_web_search_candidates": 13}, revision)
            with self.assertRaises(ValueError):
                store.configure({"slang_web_search_results": 6}, revision)
            with self.assertRaises(ValueError):
                store.configure({"unknown_slang_key": True}, revision)
            updated = store.configure({"slang_web_search_enabled": True,
                                       "slang_web_search_candidates": 12,
                                       "slang_web_search_results": 5}, revision)
            self.assertIs(updated["slang_web_search_enabled"], True)
            self.assertEqual(updated["slang_web_search_candidates"], 12)
