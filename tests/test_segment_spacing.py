import unittest
from dataclasses import asdict

from companion_v2.configuration.registry import ValueKind
from companion_v2.configuration.models import ConfigurationError
from companion_v2.conversation.reply_settings import configuration_fields, validate
from companion_v2.conversation.segmentation import (
    SegmentationPolicy,
    minimum_part_gap_seconds,
    part_gap_seconds,
)


class SegmentSpacingTests(unittest.TestCase):
    def test_fixed_and_random_spacing_are_bounded_and_repeatable(self):
        fixed = {"part_gap_mode": "fixed", "part_gap_ms": 1250}
        self.assertEqual(part_gap_seconds(fixed, "第一段。", "batch:part"), 1.25)

        random = {"part_gap_mode": "random", "part_gap_min_ms": 800, "part_gap_max_ms": 2600}
        first = part_gap_seconds(random, "第一段。", "batch:part")
        self.assertEqual(first, part_gap_seconds(random, "第一段。", "batch:part"))
        self.assertGreaterEqual(first, 0.8)
        self.assertLessEqual(first, 2.6)

    def test_length_spacing_tracks_text_length_with_stable_variation(self):
        policy = {"part_gap_mode": "log", "part_gap_log_base": 1.8}
        short = part_gap_seconds(policy, "好。", "same:part")
        long = part_gap_seconds(policy, "这是明显更长的一段回复内容，用于比较停顿节奏。", "same:part")
        self.assertGreater(long, short)
        self.assertGreaterEqual(short, minimum_part_gap_seconds(policy, "好。"))
        self.assertLessEqual(long, 60)

    def test_registered_defaults_and_legacy_configuration(self):
        legacy = {**asdict(SegmentationPolicy()), "streaming": False, "part_gap_ms": 0}
        validate(legacy)
        with self.assertRaises(ConfigurationError):
            validate({**legacy, "part_gap_mode": "random"})

        fields = {field.field_id.removeprefix("conversation.presentation."): field
                  for field in configuration_fields(SegmentationPolicy(), False, 0)}
        self.assertEqual(fields["part_gap_mode"].default, "fixed")
        self.assertEqual(fields["part_gap_log_base"].kind, ValueKind.WEIGHT)
        self.assertEqual(fields["part_gap_log_base"].minimum, 1.1)
        self.assertEqual(fields["part_gap_log_base"].maximum, 5.0)

    def test_invalid_or_partial_spacing_configuration_is_rejected(self):
        legacy = {**asdict(SegmentationPolicy()), "streaming": False, "part_gap_ms": 0}
        spacing = {"part_gap_mode": "random", "part_gap_min_ms": 2400,
                   "part_gap_max_ms": 1200, "part_gap_log_base": 1.8}
        with self.assertRaises(ConfigurationError):
            validate({**legacy, **spacing})
        with self.assertRaises(ConfigurationError):
            validate({**legacy, **spacing, "part_gap_max_ms": 3000, "part_gap_mode": "unknown"})


if __name__ == "__main__":
    unittest.main()
