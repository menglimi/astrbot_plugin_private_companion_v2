"""C2-3 书架二期: rating-derived preference, and the gates on when the shelf speaks.

The pure units are tested directly; the parts that need a real shelf, configuration
and authorization reuse the shelf fixture so the switches are exercised through the
same patch path the page uses.
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
import unittest

from companion_v2.library import preferences as pref
from companion_v2.library import triggers as gate
from companion_v2.library.configuration import DEFAULTS as LIBRARY_DEFAULTS
from companion_v2.library.configuration import configuration_fields as library_fields
from companion_v2.library.configuration import validate as validate_library
from companion_v2.configuration.models import ConfigurationError
from companion_v2.foundation.refs import OperationRef, VersionRef
from tests.test_library_provider import NOW, ShelfFixture


def review(entry_id, rating, *, review_id=None):
    return SimpleNamespace(entry_id=entry_id, rating=rating,
                           review_id=review_id or f"review-{entry_id}-{rating}")


class PreferenceAggregationTests(unittest.TestCase):
    def test_a_rating_only_counts_once_the_floor_is_reached(self):
        few = [review("a", 5), review("b", 5)]
        self.assertEqual(pref.aggregate(few, min_ratings=3, max_terms=8), ())
        enough = [*few, review("c", 5)]
        # Three rated works, so three terms; the floor gates the whole aggregation.
        self.assertEqual(len(pref.aggregate(enough, min_ratings=3, max_terms=8)), 3)

    def test_the_floor_is_exact_on_both_sides(self):
        # The floor counts ratings, and the terms come out one per work.
        for count, expected in ((3, 0), (4, 4), (5, 5)):
            reviews = [review(f"e{index}", 4) for index in range(count)]
            self.assertEqual(len(pref.aggregate(reviews, min_ratings=4, max_terms=8)),
                             expected, count)

    def test_unrated_reviews_never_contribute(self):
        reviews = [review("a", None), review("b", None), review("c", 5), review("d", 5)]
        # Two rated works clear the floor of 2; the two unrated ones contribute nothing.
        terms = pref.aggregate(reviews, min_ratings=2, max_terms=8)
        self.assertEqual({item.term for item in terms}, {"c", "d"})

    def test_terms_are_capped_and_ordered_strongest_first(self):
        reviews = [review("weak", 3), review("love", 5), review("hate", 1),
                   review("like", 4), review("mild", 2)]
        terms = pref.aggregate(reviews, min_ratings=1, max_terms=3)
        self.assertEqual(len(terms), 3)
        # Equal strength: the fond term leads, so the block opens with what it likes.
        self.assertEqual(terms[0].term, "love")
        self.assertEqual(terms[1].term, "hate")
        scores = [abs(item.score) for item in terms]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_a_neutral_work_produces_no_term(self):
        self.assertEqual(pref.aggregate([review("flat", 3)], min_ratings=1, max_terms=8), ())

    def test_influence_text_is_a_reference_and_says_so(self):
        terms = pref.aggregate([review("love", 5), review("hate", 1)], min_ratings=1, max_terms=8)
        text = pref.influence_text(terms)
        self.assertIn(pref.PREFERENCE_HEADING, text)
        self.assertIn("不是本轮要求", text)
        self.assertIn("可以不同意", text)
        self.assertIn("love", text)
        self.assertIn("hate", text)
        self.assertEqual(pref.influence_text(()), "")


class TriggerGateTests(unittest.TestCase):
    def settings(self, **changes):
        # enabled by default here: these tests are about spacing and the draw, and
        # the disabled case has its own test below.
        return {**LIBRARY_DEFAULTS, "enabled": True, **changes}

    def test_a_zero_probability_never_fires_and_one_always_does(self):
        self.assertFalse(gate.sampled(seed_parts=["x"], probability=0.0))
        self.assertTrue(gate.sampled(seed_parts=["x"], probability=1.0))

    def test_the_draw_is_reproducible_rather_than_statistical(self):
        first = gate.sampled(seed_parts=["a", "b"], probability=0.5)
        self.assertEqual(first, gate.sampled(seed_parts=["a", "b"], probability=0.5))
        # A different seed is allowed to differ, but must still be a boolean.
        self.assertIn(gate.sampled(seed_parts=["a", "c"], probability=0.5), (True, False))

    def test_a_probability_outside_its_range_is_refused(self):
        for value in (-0.1, 1.1, "0.5", True):
            with self.assertRaises(ValueError, msg=value):
                gate.sampled(seed_parts=["x"], probability=value)

    def test_a_missing_cursor_is_due_immediately(self):
        self.assertTrue(gate.due(None, now=NOW, hours=18))

    def test_the_interval_boundary_is_exact(self):
        last = NOW - timedelta(hours=18)
        self.assertTrue(gate.due(last, now=NOW, hours=18))
        self.assertFalse(gate.due(last + timedelta(seconds=1), now=NOW, hours=18))

    def test_the_interval_is_checked_before_the_draw(self):
        # A probability of 1 must not let the shelf ignore its own spacing.
        settings = self.settings(min_interval_hours=18, share_probability=1.0)
        allowed, reason = gate.decide(settings, gate.SHARE, last_at=NOW - timedelta(minutes=5),
                                      now=NOW, seed_parts=["x"])
        self.assertFalse(allowed)
        self.assertEqual(reason, "interval_not_elapsed")

    def test_the_two_actions_keep_separate_cursors(self):
        self.assertNotEqual(gate.cursor_key(gate.SHARE), gate.cursor_key(gate.ASK))
        with self.assertRaises(ValueError):
            gate.cursor_key("sing")

    def test_a_disabled_shelf_never_speaks(self):
        allowed, reason = gate.decide(self.settings(enabled=False), gate.SHARE, last_at=None,
                                      now=NOW, seed_parts=["x"])
        self.assertFalse(allowed)
        self.assertEqual(reason, "library_disabled")

    def test_the_full_gate_allows_a_spaced_draw(self):
        # The action decides which probability applies, so pin the one under test.
        settings = self.settings(min_interval_hours=1, ask_probability=1.0)
        allowed, reason = gate.decide(settings, gate.ASK, last_at=NOW - timedelta(hours=2),
                                      now=NOW, seed_parts=["x"])
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_each_action_reads_its_own_probability(self):
        settings = self.settings(share_probability=1.0, ask_probability=0.0)
        share, _ = gate.decide(settings, gate.SHARE, last_at=None, now=NOW, seed_parts=["x"])
        ask, reason = gate.decide(settings, gate.ASK, last_at=None, now=NOW, seed_parts=["x"])
        self.assertTrue(share)
        self.assertFalse(ask)
        self.assertEqual(reason, "not_sampled")


class ExtendedLibraryConfigurationTests(unittest.TestCase):
    def test_the_new_defaults_keep_the_old_behaviour(self):
        # Both C2-3a switches default off, so an untouched installation is unchanged.
        self.assertFalse(LIBRARY_DEFAULTS["rating_enabled"])
        self.assertFalse(LIBRARY_DEFAULTS["preference_influence_enabled"])
        self.assertEqual(LIBRARY_DEFAULTS["preference_min_ratings"], 5)
        self.assertEqual(LIBRARY_DEFAULTS["preference_max_terms"], 8)
        self.assertEqual(LIBRARY_DEFAULTS["min_interval_hours"], 18)
        self.assertEqual(LIBRARY_DEFAULTS["share_probability"], 0.18)
        self.assertEqual(LIBRARY_DEFAULTS["ask_probability"], 0.16)

    def test_all_twelve_settings_still_validate(self):
        self.assertEqual(len(LIBRARY_DEFAULTS), 12)
        self.assertEqual(validate_library(dict(LIBRARY_DEFAULTS)), dict(LIBRARY_DEFAULTS))
        self.assertEqual(len(library_fields()), 12)

    def test_probabilities_are_registered_as_fractions(self):
        from companion_v2.configuration.registry import ValueKind
        fields = {field.field_id.split(".")[-1]: field for field in library_fields()}
        for name in ("share_probability", "ask_probability"):
            self.assertIs(fields[name].kind, ValueKind.PROBABILITY, name)

    def test_out_of_range_values_are_rejected(self):
        for name, value in (("preference_min_ratings", 0), ("preference_min_ratings", 65),
                            ("preference_max_terms", 0), ("preference_max_terms", 33),
                            ("min_interval_hours", 0), ("share_probability", 1.5),
                            ("ask_probability", -0.1), ("rating_enabled", 1)):
            with self.assertRaises(ConfigurationError, msg=f"{name}={value}"):
                validate_library({**LIBRARY_DEFAULTS, name: value})


class ShelfPreferenceTests(ShelfFixture):
    """The switches are exercised through the real patch path, not by faking reads."""

    def setUp(self):
        super().setUp()
        # The shelf group defaults to off, and each configure() call below replaces
        # the whole patch, so the C2-3 switches are held here and merged per call.
        self.enable_shelf()
        self.c23 = {"rating_enabled": True, "preference_influence_enabled": True}

    def rate(self, entry_id, rating):
        self.add_novel(entry_id)
        return self.archive.record_review(
            self.context, review_id=f"review-{entry_id}", entry_id=entry_id, body="读完了，说两句。",
            rating=rating, evidence=("progress:1",))

    def configure(self, **changes):
        """Patch the group with the C2-3 baseline kept in place.

        A fresh operation per call: ``enable_shelf`` reuses one fixed operation id,
        so a second call through it is an idempotent replay that ignores the new
        changes. That is correct production behaviour, so this helper issues its own
        operation rather than weakening the ledger.
        """
        self.c23.update(changes)
        return self.patch_library(self.c23)

    def patch_library(self, values):
        target = self.library_target()
        snapshot = self.configuration.read(self.core, target=target, group_id="library",
                                           observed_at=NOW).unwrap()
        self.operation_serial = getattr(self, "operation_serial", 0) + 1
        return self.configuration.patch(
            self.core, target=target, group_id="library",
            operation=OperationRef(f"c23-op-{self.operation_serial}", "library",
                                   target.authorization_scope,
                                   VersionRef("library-lineage-1", 1), f"c23-key-{self.operation_serial}"),
            expected_edit_token=snapshot.edit_token,
            changes={f"library.{name}": value for name, value in values.items()}, observed_at=NOW)

    def test_ratings_become_taste_once_the_switches_are_on(self):
        self.configure(preference_min_ratings=2, preference_max_terms=8)
        self.rate("novel-a", 5)
        self.rate("novel-b", 1)
        text = self.archive.preference_text(self.context)
        self.assertIn("novel-a", text)
        self.assertIn("novel-b", text)

    def test_the_influence_switch_off_means_no_material_at_all(self):
        self.configure(preference_influence_enabled=False, preference_min_ratings=2)
        self.rate("novel-a", 5)
        self.rate("novel-b", 5)
        self.assertEqual(self.archive.preference_terms(self.context), ())
        self.assertEqual(self.archive.preference_text(self.context), "")

    def test_below_the_declared_minimum_nothing_is_injected(self):
        self.configure(preference_min_ratings=5)
        for index in range(4):
            self.rate(f"novel-{index}", 5)
        self.assertEqual(self.archive.preference_terms(self.context), ())
        self.rate("novel-4", 5)
        self.assertTrue(self.archive.preference_terms(self.context))

    def test_the_term_ceiling_bounds_the_injected_material(self):
        self.configure(preference_min_ratings=1, preference_max_terms=3)
        for index in range(6):
            self.rate(f"novel-{index}", 5 if index % 2 else 1)
        self.assertEqual(len(self.archive.preference_terms(self.context)), 3)

    def test_the_trigger_cursor_survives_a_restart(self):
        self.configure(min_interval_hours=18, share_probability=1.0)
        first = self.archive.record_trigger(self.context, gate.SHARE, seed_parts=["s"]).unwrap()
        self.assertTrue(first["allowed"])
        # The cursor is stored, so a second call inside the interval is refused.
        again = self.archive.record_trigger(self.context, gate.SHARE, seed_parts=["s"]).unwrap()
        self.assertFalse(again["allowed"])
        self.assertEqual(again["reason"], "interval_not_elapsed")
        self.assertEqual(again["last_at"], first["last_at"])

    def test_the_two_actions_do_not_consume_each_others_budget(self):
        self.configure(min_interval_hours=18, share_probability=1.0, ask_probability=1.0)
        share = self.archive.record_trigger(self.context, gate.SHARE, seed_parts=["s"]).unwrap()
        ask = self.archive.record_trigger(self.context, gate.ASK, seed_parts=["a"]).unwrap()
        self.assertTrue(share["allowed"])
        # The share cursor is already set, so a separate action still fires at once.
        self.assertTrue(ask["allowed"])
        owner = self.archive.owner(self.context)
        self.assertIsNotNone(self.archive.entries.trigger_cursor(owner, gate.SHARE))
        self.assertIsNotNone(self.archive.entries.trigger_cursor(owner, gate.ASK))
        # And the share action is now spaced out, independently of the ask cursor.
        blocked = self.archive.record_trigger(self.context, gate.SHARE, seed_parts=["s"]).unwrap()
        self.assertEqual(blocked["reason"], "interval_not_elapsed")


if __name__ == "__main__":
    unittest.main()
