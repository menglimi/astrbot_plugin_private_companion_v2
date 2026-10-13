"""Reaction retrieval performance and installation configuration (T48 / B1+B2+B4).

One file covers the whole slice: the registered ``expression.reaction`` group,
V1's two vector modes, the local synonym clusters, the post-use penalty with the
duplicate window, the low-latency lookup cache, the visual review tri-state and
the throttled vector backfill.  Retrieval ranking is exercised directly on
``CatalogSearch`` with a recording embedding port, so a cosine per asset can be
dictated instead of hoped for.
"""

import asyncio
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest

from companion_v2.configuration.models import ConfigLayer, ConfigTarget, ConfigurationError
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.configuration.registry import FieldRegistry
from companion_v2.conversation.media.models import ImageDescriptor
from companion_v2.expression import reaction_lexicon
from companion_v2.expression.reaction_configuration import (DEFAULTS, GROUP, OWNER as CONFIG_OWNER,
    ReactionConfigurationOwner, ReactionSettings, configuration_fields, migrate_window_values,
    read_settings, read_snapshot)
from companion_v2.expression.reactions import (DUPLICATE_WINDOW_FLOOR, MINIMUM_RELEVANCE,
    RELEVANCE_FLOOR_DELTA, ReactionLibrary)
from companion_v2.expression.semantic_service import REACTION_BACKFILL_KEY, SemanticService
from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.model_gateway.embedding import EmbeddingGateway
from companion_v2.model_gateway.semantic_search import (VECTOR_LED_MIN_CANDIDATES, CatalogSearch)
from companion_v2.storage.runtime import StorageRuntime
from companion_v2.storage.semantic import SemanticStore
from tests.test_host_application import HostFixture
from tests.test_management_access import ROLE as HOST_ROLE, SCOPE as HOST_SCOPE


INSTALLATION = "reaction-installation"
NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
SCOPE = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "native-a", "bot-a", "login-a",
                 "conversation-a", "session-a")
ROLE = SubjectRef(INSTALLATION, SubjectKind.BOT, "persona-a")
OWNER = "reaction-owner"
CONTEXT = SimpleNamespace(scope=SCOPE, role_binding=SimpleNamespace(role=ROLE))
TARGET = ConfigTarget(INSTALLATION, ConfigLayer.INSTALLATION)
COSINE = re.compile(r"cos:([0-9.]+)")
CONTENT = b"\x89PNG\r\n\x1a\nreaction-original"
DESCRIPTOR = asdict(ImageDescriptor(0, "image/png", 1, 1, len(CONTENT),
                                    hashlib.sha256(CONTENT).hexdigest()))


def payload(text, *, name="表情"):
    return {"name": name, "description": text, "text": text, "descriptor": DESCRIPTOR}


class CatalogPort:
    """Recording semantic port; a ``cos:`` marker inside a text dictates its cosine."""

    def __init__(self):
        self.version = "model-1"
        self.texts, self.analyzed, self.fits = [], [], []
        self.failing = False

    def binding(self, identifier, kind):
        return kind + self.version

    def inventory(self):
        return {"embedding": [], "rerank": [], "analysis": []}

    @staticmethod
    def vector(text):
        match = COSINE.search(text)
        cosine = float(match.group(1)) if match else 1.0
        return [cosine, (1.0 - cosine * cosine) ** 0.5, 0.0]

    async def embed(self, identifier, texts):
        self.texts.extend(texts)
        if self.failing:
            raise RuntimeError("unavailable")
        return [self.vector(text) for text in texts]

    async def analyze(self, identifier, prompt, images=()):
        self.analyzed.append((prompt, tuple(images)))
        return {"fit": self.fits.pop(0) if self.fits else True, "reason": "测试复核"}

    async def rerank(self, identifier, query, documents):
        return None


def catalog(root, port=None):
    """An independent catalog plus its search engine and recording port."""
    port = port or CatalogPort()
    root.mkdir(parents=True, exist_ok=True)
    store = SemanticStore(root)
    return store, CatalogSearch(store, EmbeddingGateway(port, timeout=5), lambda item, context: True), port


class ReactionConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-reaction-config-")
        self.addCleanup(temporary.cleanup)
        self.runtime = StorageRuntime.open(data_root=Path(temporary.name) / "data",
                                           installation_id=INSTALLATION)
        self.addCleanup(self.runtime.close)

    def test_registered_fields_match_the_documented_defaults(self):
        fields = {field.field_id: field for field in configuration_fields()}
        self.assertEqual(set(fields), {GROUP + "." + name for name in DEFAULTS})
        self.assertEqual({field.default for field in fields.values()
                          if field.field_id.endswith("enabled")}, {True})
        self.assertEqual((fields[GROUP + ".candidate_limit"].default,
                          fields[GROUP + ".embedding_candidate_limit"].default,
                          fields[GROUP + ".embedding_backfill_batch_size"].default,
                          fields[GROUP + ".embedding_backfill_interval_seconds"].default),
                         (6, 1200, 24, 300))
        self.assertEqual((fields[GROUP + ".embedding_weight"].default,
                          fields[GROUP + ".embedding_score_threshold"].default,
                          fields[GROUP + ".vision_verify_mode"].default), (1.0, 0.42, "embedding"))
        for field in fields.values():
            self.assertEqual((field.group_id, field.consumer_id, field.owner_id, field.layers),
                             (GROUP, GROUP, GROUP, (ConfigLayer.INSTALLATION,)))
        self.assertEqual(fields[GROUP + ".embedding_weight"].maximum, 3.0)
        registry = FieldRegistry(version="reaction.v1", fields=configuration_fields())
        self.assertEqual(len(registry.group(GROUP)), len(DEFAULTS))

    def test_settings_boundaries(self):
        for name, value in (("candidate_limit", 0), ("candidate_limit", 25), ("candidate_limit", True),
                            ("embedding_weight", 0.0), ("embedding_weight", 4.0),
                            ("embedding_score_threshold", 1.5), ("embedding_candidate_limit", 19),
                            ("embedding_backfill_batch_size", 101),
                            ("embedding_backfill_interval_seconds", -1),
                            ("vision_verify_mode", "sometimes"), ("low_latency_enabled", 1)):
            with self.subTest(name=name, value=value), self.assertRaises(ConfigurationError):
                ReactionSettings.from_values({**DEFAULTS, name: value})
        self.assertEqual(ReactionSettings.from_values({}), ReactionSettings.from_values(DEFAULTS))

    def test_installation_roundtrip_and_enum_guard(self):
        fields = configuration_fields()
        self.assertEqual(read_settings(self.runtime, CONTEXT), ReactionSettings.from_values(DEFAULTS))
        with self.assertRaises(ConfigurationError):
            ReactionConfigurationOwner(self.runtime).write(TARGET, fields,
                changes={GROUP + ".vision_verify_mode": "alwayss"}, reset=(),
                expected_revision=0, observed_at=NOW)
        ReactionConfigurationOwner(self.runtime).write(TARGET, fields, changes={
            GROUP + ".candidate_limit": 9, GROUP + ".low_latency_enabled": False,
            GROUP + ".vision_verify_mode": "always"}, reset=(), expected_revision=0, observed_at=NOW)
        settings, revision = read_snapshot(self.runtime, CONTEXT)
        self.assertEqual((settings.candidate_limit, settings.low_latency_enabled,
                          settings.vision_verify_mode), (9, False, "always"))
        self.assertEqual(revision, 1)
        # The generic loader path has no enum check, which is exactly why the owner
        # above re-validates: a malformed stored value degrades to defaults instead
        # of silently switching the review gate.
        SparseConfigurationOwner(self.runtime).write(TARGET, fields,
            changes={GROUP + ".vision_verify_mode": "sometimes"}, reset=(),
            expected_revision=1, observed_at=NOW)
        self.assertEqual(read_settings(self.runtime, CONTEXT).vision_verify_mode, "embedding")

    def test_legacy_window_values_are_copied_to_installation_scope(self):
        legacy_fields = tuple(replace(field, layers=(ConfigLayer.WINDOW,))
                              for field in configuration_fields())
        other_scope = replace(SCOPE, native_scope_id="native-b", conversation_id="conversation-b",
                              session_id="session-b")
        targets = (ConfigTarget(INSTALLATION, ConfigLayer.WINDOW, ROLE, SCOPE),
                   ConfigTarget(INSTALLATION, ConfigLayer.WINDOW, ROLE, other_scope))
        legacy = SparseConfigurationOwner(self.runtime)
        legacy.write(targets[0], legacy_fields,
            changes={GROUP + ".candidate_limit": 8}, reset=(), expected_revision=0,
            observed_at=NOW)
        legacy.write(targets[1], legacy_fields,
            changes={GROUP + ".candidate_limit": 11}, reset=(), expected_revision=0,
            observed_at=NOW + timedelta(minutes=1))

        with self.runtime.read_snapshot():
            ReactionConfigurationOwner(self.runtime)
            self.assertEqual(read_settings(self.runtime, CONTEXT).candidate_limit, DEFAULTS["candidate_limit"])
        migrate_window_values(self.runtime)
        settings, revision = read_snapshot(self.runtime, CONTEXT)
        self.assertEqual(settings.candidate_limit, 11)
        self.assertEqual(revision, 1)
        legacy_rows = self.runtime.read_all("""SELECT v.target_key FROM configuration_values v
            JOIN configuration_targets t ON t.target_key=v.target_key
            WHERE v.field_id=? AND json_extract(t.target_json,'$.layer')='window'""",
            (GROUP + ".candidate_limit",))
        self.assertEqual(len(legacy_rows), 2)

        before = tuple(tuple(row) for row in self.runtime.read_all(
            "SELECT * FROM configuration_values ORDER BY target_key,field_id", ()))
        migrate_window_values(self.runtime)
        with self.runtime.read_snapshot():
            ReactionConfigurationOwner(self.runtime)
            self.assertEqual(read_snapshot(self.runtime, CONTEXT)[1], revision)
        after = tuple(tuple(row) for row in self.runtime.read_all(
            "SELECT * FROM configuration_values ORDER BY target_key,field_id", ()))
        self.assertEqual(after, before)

    def test_legacy_preparation_preserves_installation_overrides(self):
        fields = configuration_fields()
        legacy_fields = tuple(replace(field, layers=(ConfigLayer.WINDOW,)) for field in fields)
        legacy_target = ConfigTarget(INSTALLATION, ConfigLayer.WINDOW, ROLE, SCOPE)
        SparseConfigurationOwner(self.runtime).write(legacy_target, legacy_fields,
            changes={GROUP + ".candidate_limit": 11, GROUP + ".vision_verify_mode": "always"},
            reset=(), expected_revision=0, observed_at=NOW)
        ReactionConfigurationOwner(self.runtime).write(TARGET, fields,
            changes={GROUP + ".candidate_limit": 9}, reset=(), expected_revision=0, observed_at=NOW)

        migrate_window_values(self.runtime)

        settings, revision = read_snapshot(self.runtime, CONTEXT)
        self.assertEqual((settings.candidate_limit, settings.vision_verify_mode, revision), (9, "always", 2))


class LexiconTests(unittest.TestCase):
    def test_shared_clusters_avoid_double_scoring(self):
        self.assertEqual(reaction_lexicon.shared_clusters("高兴", "开心"), ("开心喜悦",))
        self.assertEqual(reaction_lexicon.shared_clusters("开心", "开心"), ())
        self.assertEqual(reaction_lexicon.shared_clusters("安慰", "抱抱"), ("安慰陪伴",))
        self.assertEqual(reaction_lexicon.shared_clusters("今天天气不错", "抱抱"), ())

    def test_negation_blocks_the_alias_and_its_bigrams(self):
        self.assertEqual(reaction_lexicon.blocked_aliases("我并不开心"), frozenset({"开心"}))
        self.assertNotIn("开心喜悦", reaction_lexicon.clusters("我并不开心"))
        self.assertEqual(reaction_lexicon.shared_clusters("不开心", "开心"), ())
        positive = "t" + "开心".encode("utf-8").hex()
        self.assertNotIn(positive, reaction_lexicon.query_terms("不开心"))
        self.assertIn(positive, reaction_lexicon.query_terms("开心"))


class RankingTests(unittest.IsolatedAsyncioTestCase):
    """CatalogSearch with the reaction parameters and with the memory defaults."""

    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-reaction-ranking-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.catalogs = 0
        self.engine()

    def engine(self):
        self.catalogs += 1
        self.store, self.search, self.port = catalog(self.root / f"catalog{self.catalogs}")
        return self.search

    def add(self, identifier, text, *, enabled=True):
        self.store.put(OWNER, "reaction", identifier, payload(text, name=identifier), enabled=enabled)

    def query(self, text, *, engine=None, **kwargs):
        return (engine or self.search).search(OWNER, "reaction", text, context=None, limit=10, **kwargs)

    async def test_vector_led_mode_ranks_against_the_query_distribution(self):
        for index, cosine in enumerate((0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6)):
            self.add(f"a{index}", f"无关素材 cos:{cosine}")
        result = await self.query("安慰", embedding_score_threshold=0.42, embedding_weight=1.0,
                                  vector_led_min_candidates=VECTOR_LED_MIN_CANDIDATES,
                                  lexical_fallback_weight=0.0)
        self.assertEqual(result["ranking"], "vector_led")
        scores = {item["id"]: item["score"] for item in result["items"]}
        # Best earns the full weight, the median earns nothing, and a candidate
        # far below the median is demoted by the same amount (V1 :1306-1327).
        self.assertAlmostEqual(scores["a0"], 1.0, places=4)
        self.assertAlmostEqual(scores["a3"], (0.8 - 0.775) / 0.175, places=4)
        self.assertAlmostEqual(scores["a7"], -1.0, places=4)

    async def test_vector_led_needs_enough_candidates(self):
        for index, cosine in enumerate((0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65)):
            self.add(f"a{index}", f"无关素材 cos:{cosine}")
        result = await self.query("安慰", embedding_score_threshold=0.42,
                                  vector_led_min_candidates=VECTOR_LED_MIN_CANDIDATES,
                                  lexical_fallback_weight=0.0)
        self.assertEqual(result["ranking"], "blended")
        self.assertAlmostEqual({item["id"]: item["score"] for item in result["items"]}["a0"],
                               (0.95 - 0.42) / 0.58, places=4)

    async def test_blended_mode_only_rewards_cosines_above_the_threshold(self):
        self.add("above", "安慰 cos:0.71")
        self.add("below", "安慰 cos:0.41")
        result = await self.query("安慰", embedding_score_threshold=0.42, lexical_fallback_weight=0.0)
        items = {item["id"]: item for item in result["items"]}
        self.assertAlmostEqual(items["above"]["score"], 0.25 + (0.71 - 0.42) / 0.58, places=4)
        self.assertAlmostEqual(items["below"]["score"], 0.25, places=4)
        self.assertEqual(items["above"]["basis"], "embedding")
        self.assertEqual(items["below"]["basis"], "keyword")

    async def test_vector_led_caps_the_lexical_contribution(self):
        for index, cosine in enumerate((0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6)):
            self.add(f"a{index}", f"安慰 cos:{cosine}")
        result = await self.query("安慰", embedding_score_threshold=0.42, lexical_weight=2.0,
                                  vector_led_min_candidates=VECTOR_LED_MIN_CANDIDATES,
                                  lexical_fallback_weight=0.0)
        # 2.0 * 1.0 of lexical would drown the vector layer; V1 caps it at 0.5.
        self.assertAlmostEqual({item["id"]: item["score"] for item in result["items"]}["a0"],
                               1.5, places=4)

    async def test_default_parameters_keep_the_shared_memory_blend(self):
        self.add("vector", "无关素材 cos:0.5")
        self.add("keyword", "安慰 cos:0.25")
        result = await self.query("安慰")
        scores = {item["id"]: item["score"] for item in result["items"]}
        self.assertAlmostEqual(scores["vector"], 0.5, places=4)
        self.assertAlmostEqual(scores["keyword"], 0.25 + 0.25, places=4)
        # With no usable provider the legacy blend falls back to the raw lexical
        # score: V2 scored a vector-less candidate ``lexical * 0.25 + lexical``.
        engine = self.engine()
        self.port.failing = True
        self.add("keyword", "安慰 cos:0.25")
        lexical = await self.query("安慰", engine=engine)
        self.assertEqual(lexical["mode"], "lexical")
        self.assertAlmostEqual({item["id"]: item["score"] for item in lexical["items"]}["keyword"],
                               1.25, places=4)

    async def test_relevance_floor_rejects_weak_matches(self):
        self.add("best", "安慰 cos:1.0")
        self.add("weak", "安慰 cos:0.5")
        result = await self.query("安慰", embedding_score_threshold=0.42, admission_similarity=0.42,
                                  relevance_floor_delta=RELEVANCE_FLOOR_DELTA,
                                  minimum_relevance=MINIMUM_RELEVANCE, lexical_fallback_weight=0.0)
        self.assertEqual([item["id"] for item in result["items"]], ["best"])
        # A catalog whose own best candidate is below the absolute minimum returns
        # nothing instead of forcing an unrelated image into the reply.
        lone = self.engine()
        self.add("faint", "无关素材 cos:0.425")
        empty = await self.query("安慰", engine=lone, embedding_score_threshold=0.42,
                                 admission_similarity=0.42, relevance_floor_delta=RELEVANCE_FLOOR_DELTA,
                                 minimum_relevance=MINIMUM_RELEVANCE, lexical_fallback_weight=0.0)
        self.assertEqual(empty["items"], [])
        self.assertTrue(empty["complete"])

    async def test_embedding_scan_cap_keeps_later_items_neutral(self):
        self.add("a1", "安慰 cos:1.0")
        self.add("a2", "安慰 cos:1.0")
        result = await self.query("安慰", embedding_candidate_limit=1, lexical_fallback_weight=0.0)
        items = {item["id"]: item for item in result["items"]}
        self.assertEqual(result["embedded"], 1)
        self.assertIsNotNone(items["a1"]["similarity"])
        self.assertIsNone(items["a2"]["similarity"])
        self.assertAlmostEqual(items["a2"]["score"], 0.25, places=4)

    async def test_synonym_clusters_admit_a_keyword_only_match(self):
        self.port.failing = True
        self.add("hug", "抱抱")
        self.add("literal", "安慰")
        result = await self.query("安慰", shared_clusters=reaction_lexicon.shared_clusters,
                                  lexical_fallback_weight=0.0)
        items = {item["id"]: item for item in result["items"]}
        self.assertEqual(set(items), {"hug", "literal"})
        self.assertAlmostEqual(items["hug"]["score"], 0.4, places=4)
        self.assertEqual(items["hug"]["basis"], "keyword_semantic")
        self.assertEqual(items["hug"]["clusters"], ["安慰陪伴"])
        self.assertEqual(items["literal"]["clusters"], [])

    async def test_negated_emotion_does_not_retrieve_positive_emotion_assets(self):
        self.port.failing = True
        self.add("positive", "开心")
        negative = await self.query("我不开心", shared_clusters=reaction_lexicon.shared_clusters,
                                    query_terms_fn=reaction_lexicon.query_terms,
                                    lexical_fallback_weight=0.0)
        positive = await self.query("我很开心", shared_clusters=reaction_lexicon.shared_clusters,
                                    query_terms_fn=reaction_lexicon.query_terms,
                                    lexical_fallback_weight=0.0)
        self.assertEqual(negative["items"], [])
        self.assertEqual([item["id"] for item in positive["items"]], ["positive"])


class LookupStub:
    def __init__(self):
        self.items, self.calls = [], []

    async def search(self, owner, kind, text, **kwargs):
        self.calls.append((owner, kind, text, kwargs))
        return {"items": [dict(item) for item in self.items], "mode": "hybrid", "ranking": "blended"}


class Selection:
    """ReactionLibrary over a real catalog store with a canned retrieval result."""

    def __init__(self, root, *, settings=None, items=(), affinity=None):
        root.mkdir(parents=True, exist_ok=True)
        self.store = SemanticStore(root)
        self.port = CatalogPort()
        self.gateway = SimpleNamespace(port=self.port, timeout=5)
        self.settings = settings or ReactionSettings.from_values(DEFAULTS)
        self.configuration_revision = 0
        self.timestamp = NOW.timestamp()
        self.affinity = dict(affinity or {})
        self.lookup = LookupStub()
        self.scheduled = []
        service = SimpleNamespace(
            store=self.store, gateway=self.gateway, search=self.lookup,
            app=SimpleNamespace(messages=None,
                now=lambda: datetime.fromtimestamp(self.timestamp, timezone.utc)),
            owner=lambda context: OWNER,
            ensure_reaction_catalog=lambda context: OWNER,
            reaction_preferences=SimpleNamespace(scores=lambda context: dict(self.affinity)),
            reaction_settings=lambda context: (self.settings, self.configuration_revision),
            schedule_reaction_backfill=lambda context, settings=None: self.scheduled.append(settings),
            validate_item=lambda item, context: True,
            check=lambda context, action="conversation.reply": None)
        self.library = ReactionLibrary(service)
        for identifier, text in items:
            self.store.put(OWNER, "reaction", identifier, payload(text, name=identifier),
                           content=CONTENT)

    def offers(self, *identifiers, basis="keyword", score=1.0):
        self.lookup.items = [{"id": identifier, "revision": 1, "score": score, "basis": basis}
                             for identifier in identifiers]

    def used(self, identifier, at, *, batch="b"):
        with self.store.db() as db:
            db.execute("INSERT OR IGNORE INTO uses VALUES (?,?,?,?)", (OWNER, identifier, batch, at))

    def use_count(self, identifier, count, last):
        with self.store.db() as db:
            for index in range(count):
                db.execute("INSERT OR IGNORE INTO uses VALUES (?,?,?,?)",
                           (OWNER, identifier, f"b{index}", last))

    async def select(self, intent="安慰"):
        return await self.library._select(CONTEXT, intent, lambda item, current: True,
                                          lambda current: None)


class SelectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-reaction-selection-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.catalogs = 0

    def harness(self, **kwargs):
        self.catalogs += 1
        root = self.root / f"catalog{self.catalogs}"
        root.mkdir(parents=True, exist_ok=True)
        return Selection(root, **kwargs)

    async def test_configuration_reaches_the_retrieval_call(self):
        selection = self.harness(items=(("a", "安慰"),), settings=ReactionSettings.from_values({
            **DEFAULTS, "candidate_limit": 4, "embedding_weight": 0.8,
            "embedding_score_threshold": 0.5, "embedding_candidate_limit": 64}))
        selection.offers("a")
        await selection.select()
        self.assertEqual(len(selection.lookup.calls), 1)
        _owner, kind, text, kwargs = selection.lookup.calls[0]
        self.assertEqual((kind, text), ("reaction", "安慰"))
        self.assertEqual(kwargs["limit"], 4)
        self.assertEqual(kwargs["embedding_weight"], 0.8)
        self.assertEqual(kwargs["embedding_score_threshold"], 0.5)
        self.assertEqual(kwargs["admission_similarity"], 0.5)
        self.assertEqual(kwargs["embedding_candidate_limit"], 64)
        self.assertEqual(kwargs["vector_led_min_candidates"], VECTOR_LED_MIN_CANDIDATES)
        self.assertEqual(kwargs["relevance_floor_delta"], RELEVANCE_FLOOR_DELTA)
        self.assertEqual(kwargs["minimum_relevance"], MINIMUM_RELEVANCE)
        self.assertEqual(kwargs["lexical_fallback_weight"], 0.0)
        self.assertIs(kwargs["shared_clusters"], reaction_lexicon.shared_clusters)
        self.assertEqual([settings.candidate_limit for settings in selection.scheduled], [4])

    async def test_usage_penalty_components(self):
        candidate, now = {"id": "a", "score": 1.0}, 10_000_000.0
        self.assertAlmostEqual(ReactionLibrary._rank(candidate, {"a": (20, 0.0)}, {}, now), 0.92, places=4)
        self.assertAlmostEqual(ReactionLibrary._rank(candidate, {"a": (0, now - 3 * 3600)}, {}, now),
                               0.45, places=4)
        self.assertAlmostEqual(ReactionLibrary._rank(candidate, {"a": (0, now - 12 * 3600)}, {}, now),
                               0.88, places=4)
        self.assertAlmostEqual(ReactionLibrary._rank(candidate, {"a": (0, now - 25 * 3600)}, {}, now),
                               1.0, places=4)
        self.assertAlmostEqual(ReactionLibrary._rank(candidate, {"a": (0, 0.0)}, {"a": -3}, now),
                               0.76, places=4)

    async def test_rotation_prefers_the_less_recently_used_original(self):
        history = self.harness(items=(("a", "安慰"), ("b", "安慰")))
        history.offers("a", "b")
        history.use_count("a", 20, history.timestamp - 30 * 3600)
        self.assertEqual((await history.select())[0][0]["id"], "b")
        recent = self.harness(items=(("a", "安慰"), ("b", "安慰")))
        recent.offers("a", "b")
        recent.used("a", recent.timestamp - 3 * 3600)
        self.assertEqual((await recent.select())[0][0]["id"], "b")
        flat = self.harness(items=(("a", "安慰"), ("b", "安慰")))
        flat.offers("b", "a")
        self.assertEqual((await flat.select())[0][0]["id"], "b")

    async def test_duplicate_window_excludes_recent_use_but_never_silences(self):
        now = 5_000_000.0
        items = [{"id": "a", "score": 1.0}, {"id": "b", "score": 1.0}]
        ranked = ReactionLibrary._ranked(items, {"a": (1, now - DUPLICATE_WINDOW_FLOOR + 1)}, {}, now,
                                         DUPLICATE_WINDOW_FLOOR)
        self.assertEqual([candidate["id"] for candidate in ranked], ["b"])
        ranked = ReactionLibrary._ranked(items, {"a": (1, now - DUPLICATE_WINDOW_FLOOR - 1)}, {}, now,
                                         DUPLICATE_WINDOW_FLOOR)
        self.assertEqual([candidate["id"] for candidate in ranked], ["b", "a"])
        ranked = ReactionLibrary._ranked(items, {"a": (1, now - 60)}, {}, now, DUPLICATE_WINDOW_FLOOR)
        self.assertEqual([candidate["id"] for candidate in ranked], ["b"])
        ranked = ReactionLibrary._ranked(items, {"a": (1, now - 60), "b": (1, now - 60)}, {}, now,
                                         DUPLICATE_WINDOW_FLOOR)
        self.assertEqual(len(ranked), 2)
        selection = self.harness(items=(("a", "安慰"), ("b", "安慰")))
        selection.offers("a", "b")
        selection.used("a", selection.timestamp - 60)
        self.assertEqual((await selection.select())[0][0]["id"], "b")
        single = self.harness(items=(("a", "安慰"),))
        single.offers("a")
        single.used("a", single.timestamp - 60)
        self.assertEqual((await single.select())[0][0]["id"], "a")

    async def test_low_latency_cache_hits_and_invalidates(self):
        selection = self.harness(items=(("a", "安慰"),))
        selection.offers("a")
        await selection.select()
        selection.used("a", selection.timestamp - 30 * 3600)
        await selection.select()
        self.assertEqual(len(selection.lookup.calls), 1)
        # A catalog edit changes the revision component of the key.
        selection.store.put(OWNER, "reaction", "b", payload("安慰", name="b"), content=CONTENT)
        await selection.select()
        self.assertEqual(len(selection.lookup.calls), 2)
        # So does an operator change on either settings surface.
        selection.configuration_revision += 1
        await selection.select()
        self.assertEqual(len(selection.lookup.calls), 3)
        settings = selection.store.settings()
        selection.store.configure({"reactions_cooldown_seconds": 240}, settings["revision"])
        await selection.select()
        self.assertEqual(len(selection.lookup.calls), 4)
        selection.settings = ReactionSettings.from_values({**DEFAULTS, "low_latency_enabled": False})
        await selection.select()
        await selection.select()
        self.assertEqual(len(selection.lookup.calls), 6)

    async def test_vision_review_tri_state(self):
        # Each step uses its own intent: the low-latency cache is keyed by intent,
        # so the canned retrieval result is only replaced for a new question.
        selection = self.harness(items=(("a", "安慰"), ("b", "安慰")))
        selection.offers("a", basis="embedding")
        fixed = {**DEFAULTS, "vision_verify_mode": "off"}
        selection.settings = ReactionSettings.from_values(fixed)
        self.assertEqual((await selection.select("安慰"))[0][0]["review"]["state"], "not_requested")
        self.assertEqual(selection.port.analyzed, [])

        selection.settings = ReactionSettings.from_values({**fixed, "vision_verify_mode": "embedding"})
        accepted, _ = await selection.select("安慰")
        self.assertEqual((accepted[0]["review"]["state"], len(selection.port.analyzed)), ("passed", 1))

        selection.offers("b", basis="keyword")
        accepted, _ = await selection.select("吐槽")
        self.assertEqual((accepted[0]["review"]["state"], len(selection.port.analyzed)),
                         ("not_requested", 1))

        selection.settings = ReactionSettings.from_values({**fixed, "vision_verify_mode": "always"})
        accepted, _ = await selection.select("庆祝")
        self.assertEqual((accepted[0]["review"]["state"], len(selection.port.analyzed)), ("passed", 2))

        # The existing boolean stays the master switch over the new mode key.
        current = selection.store.settings()
        selection.store.configure({"vision_review": False}, current["revision"])
        accepted, _ = await selection.select("抱歉")
        self.assertEqual((accepted[0]["review"]["state"], len(selection.port.analyzed)),
                         ("not_requested", 2))

    async def test_rejected_review_advances_to_the_next_candidate(self):
        selection = self.harness(items=(("a", "安慰"), ("b", "安慰")),
            settings=ReactionSettings.from_values({**DEFAULTS, "vision_verify_mode": "always"}))
        selection.offers("a", "b")
        selection.port.fits = [False]
        accepted, _ = await selection.select()
        self.assertEqual((accepted[0]["id"], accepted[0]["review"]["state"]), ("b", "passed"))
        self.assertEqual(len(selection.port.analyzed), 2)


class AssembledRegistrationTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    """The group is wired into the real assembly, not only declared in its module."""

    async def test_registered_group_is_read_by_the_live_semantic_service(self):
        host = self.host()
        app = host.application
        service = app.attach_semantics(CatalogPort())
        installation = app.runtime.installation_id
        scope = replace(HOST_SCOPE, installation_id=installation)
        role = SubjectRef(installation, SubjectKind.BOT, HOST_ROLE.subject_id)
        context = SimpleNamespace(scope=scope, role_binding=SimpleNamespace(role=role))
        definitions = app.configuration.registry.group(GROUP)
        self.assertEqual({field.field_id for field in definitions},
                         {GROUP + "." + name for name in DEFAULTS})
        self.assertIsInstance(app.configuration._owners[CONFIG_OWNER], ReactionConfigurationOwner)
        self.assertEqual(service.reaction_settings(context),
                         (ReactionSettings.from_values(DEFAULTS), 0))
        app.configuration._owners[CONFIG_OWNER].write(
            ConfigTarget(installation, ConfigLayer.INSTALLATION), definitions,
            changes={GROUP + ".candidate_limit": 8, GROUP + ".vision_verify_mode": "always"},
            reset=(), expected_revision=0, observed_at=app.now())
        settings, revision = service.reaction_settings(context)
        self.assertEqual((settings.candidate_limit, settings.vision_verify_mode, revision),
                         (8, "always", 1))
        another_scope = replace(scope, native_scope_id="native-other", conversation_id="conversation-other",
                                session_id="session-other")
        another_context = SimpleNamespace(scope=another_scope, role_binding=SimpleNamespace(role=role))
        self.assertEqual(service.reaction_settings(another_context), (settings, revision))


class BackfillTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-reaction-backfill-")
        self.addCleanup(temporary.cleanup)
        self.runtime = StorageRuntime.open(data_root=Path(temporary.name) / "data",
                                           installation_id=INSTALLATION)
        self.addCleanup(self.runtime.close)
        self.port = CatalogPort()
        self.service = SemanticService(
            SimpleNamespace(runtime=self.runtime, memory=None,
                            messages=SimpleNamespace(group_memory=None),
                            proactive=SimpleNamespace(sources=None)), self.port)
        self.owner = self.service.reaction_owner(CONTEXT)
        for index in range(5):
            self.service.store.put(self.owner, "reaction", f"i{index}",
                                   payload(f"表情素材 {index}", name=str(index)))

    def write(self, **changes):
        ReactionConfigurationOwner(self.runtime).write(TARGET, configuration_fields(),
            changes={GROUP + "." + name: value for name, value in changes.items()}, reset=(),
            expected_revision=self.service.reaction_settings(CONTEXT)[1], observed_at=NOW)

    def vectors(self):
        with self.service.store.db() as db:
            return db.execute("SELECT COUNT(*) FROM vectors WHERE owner=? AND kind='reaction'",
                              (self.owner,)).fetchone()[0]

    async def drain(self):
        tasks = tuple(self.service.background.values())
        if tasks:
            await asyncio.gather(*tasks)

    async def test_backfill_respects_the_batch_size(self):
        self.write(embedding_backfill_batch_size=3, embedding_backfill_interval_seconds=0)
        self.service.schedule_reaction_backfill(CONTEXT)
        await self.drain()
        self.assertEqual(self.vectors(), 3)
        self.service.schedule_reaction_backfill(CONTEXT)
        await self.drain()
        self.assertEqual(self.vectors(), 5)
        self.assertNotIn("reaction_backfill", self.service.errors)

    async def test_backfill_is_throttled_and_single_flight(self):
        self.write(embedding_backfill_batch_size=5, embedding_backfill_interval_seconds=300)
        self.service.schedule_reaction_backfill(CONTEXT)
        self.service.schedule_reaction_backfill(CONTEXT)
        self.assertEqual(len(self.service.background), 1)
        await self.drain()
        self.assertEqual(self.vectors(), 5)
        embedded = len(self.port.texts)
        self.service.store.put(self.owner, "reaction", "extra", payload("新素材", name="extra"))
        self.service.schedule_reaction_backfill(CONTEXT)
        await self.drain()
        self.assertEqual((len(self.port.texts), self.vectors()), (embedded, 5))
        self.service.backfill_runs[REACTION_BACKFILL_KEY + self.owner] = time.monotonic() - 301
        self.service.schedule_reaction_backfill(CONTEXT)
        await self.drain()
        self.assertEqual(self.vectors(), 6)

    async def test_backfill_switch_and_failure_reporting(self):
        self.write(embedding_backfill_enabled=False, embedding_backfill_interval_seconds=0)
        self.service.schedule_reaction_backfill(CONTEXT)
        await self.drain()
        self.assertEqual((self.service.background, self.vectors()), ({}, 0))
        self.write(embedding_backfill_enabled=True, embedding_backfill_interval_seconds=0)
        self.port.failing = True
        self.service.schedule_reaction_backfill(CONTEXT)
        await self.drain()
        self.assertEqual((self.vectors(), self.service.errors["reaction_backfill"]), (0, "RuntimeError"))
        self.assertEqual(self.service.background, {})

    async def test_reconfigure_drops_the_throttle_and_the_cached_lookups(self):
        self.write(embedding_backfill_batch_size=5, embedding_backfill_interval_seconds=300)
        self.service.schedule_reaction_backfill(CONTEXT)
        await self.drain()
        self.service.reactions.lookups["key"] = (0.0, {"items": []})
        self.service.backfill_runs["key"] = 1.0
        settings = self.service.store.settings()
        await self.service.configure({"reactions_cooldown_seconds": 300}, settings["revision"])
        self.assertEqual((self.service.reactions.lookups, self.service.backfill_runs), ({}, {}))


if __name__ == "__main__":
    unittest.main()
