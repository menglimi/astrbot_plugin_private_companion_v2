"""The parked first-run binding: read it back exactly, or not at all.

The failure that matters here is the quiet one. If a stored binding is read back
with a value the operator never confirmed -- a trimmed persona, a repaired account,
a field silently defaulted -- the role pins to the wrong conversation and says
nothing. So these tests lean on round-tripping equality and on refusing malformed
input rather than on producing something usable from it.

The second theme is atomicity's precondition: whatever is on disk must parse, and
a file that does not must read as "no binding" instead of crashing plugin startup.
"""

import json
import tempfile
import unittest
from pathlib import Path

from astrbot_host.binding_store import (
    BINDING_SCHEMA,
    PendingBinding,
    binding_path,
    clear_binding,
    read_binding,
    write_binding,
)


def sample(**overrides):
    values = {"platform_id": "default", "account_id": "10002",
              "participant_id": "10001", "persona_id": "晚星"}
    values.update(overrides)
    return PendingBinding(**values)


class RoundTripTests(unittest.TestCase):
    def test_a_written_binding_reads_back_identically(self):
        with tempfile.TemporaryDirectory() as folder:
            write_binding(folder, sample())
            self.assertEqual(read_binding(folder).document(), sample().document())

    def test_an_unnamed_persona_round_trips_as_empty(self):
        """Empty means 'follow the conversation'; it must not become a persona name."""
        with tempfile.TemporaryDirectory() as folder:
            write_binding(folder, sample(persona_id=""))
            self.assertEqual(read_binding(folder).persona_id, "")

    def test_reading_a_directory_without_a_binding_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(read_binding(Path(folder) / "absent"))

    def test_the_stored_document_is_the_pin_that_will_be_written(self):
        stored = PendingBinding.parse(json.dumps(sample().document()))
        pinned = stored.identity()
        self.assertEqual(pinned["platform_id"], "default")
        self.assertEqual(pinned["account_id"], "10002")
        self.assertEqual(pinned["participant_id"], "10001")
        self.assertEqual(pinned["persona_id"], "晚星")
        self.assertEqual(pinned["bot_id"], "bot-10002")
        self.assertTrue(pinned["role_id"].startswith("role-10002-"))

    def test_the_identity_and_the_document_agree_after_a_round_trip(self):
        """A persona lost in storage would pin one voice and record another."""
        with tempfile.TemporaryDirectory() as folder:
            write_binding(folder, sample())
            self.assertEqual(read_binding(folder).identity(), sample().identity())


class RefusalTests(unittest.TestCase):
    def test_a_binding_from_a_future_schema_is_refused(self):
        with self.assertRaises(ValueError):
            PendingBinding.parse(json.dumps({**sample().document(), "schema_version": BINDING_SCHEMA + 1}))

    def test_unknown_fields_are_refused_rather_than_dropped(self):
        with self.assertRaises(ValueError):
            PendingBinding.parse(json.dumps({**sample().document(), "extra": "x"}))

    def test_a_missing_or_blank_field_is_refused(self):
        for field in ("platform_id", "account_id", "participant_id"):
            for bad in ("", None, 10001):
                with self.subTest(field=field, value=bad):
                    document = {**sample().document(), field: bad}
                    with self.assertRaises(ValueError):
                        PendingBinding.parse(json.dumps(document))

    def test_a_non_object_document_is_refused(self):
        for bad in ("[]", "null", '"binding"', "123"):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    PendingBinding.parse(bad)

    def test_a_corrupt_file_reads_as_no_binding_rather_than_crashing_startup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = binding_path(folder)
            path.parent.mkdir(parents=True, exist_ok=True)
            for payload in ("{", "not json", "", json.dumps({"schema_version": 99})):
                with self.subTest(payload=payload):
                    path.write_text(payload, encoding="utf-8")
                    self.assertIsNone(read_binding(folder))

    def test_a_utf8_bom_is_treated_as_absent_like_the_pin_does(self):
        """The pinned configuration rejects a BOM; binding follows the same rule."""
        with tempfile.TemporaryDirectory() as folder:
            path = binding_path(folder)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\xef\xbb\xbf" + json.dumps(sample().document()).encode("utf-8"))
            self.assertIsNone(read_binding(folder))

    def test_clearing_reports_whether_anything_was_there(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(clear_binding(folder))
            write_binding(folder, sample())
            self.assertTrue(clear_binding(folder))
            self.assertIsNone(read_binding(folder))

    def test_writing_replaces_a_previous_binding_wholesale(self):
        """A rebind must not merge fields from the binding it replaces."""
        with tempfile.TemporaryDirectory() as folder:
            write_binding(folder, sample())
            write_binding(folder, sample(account_id="10003", persona_id=""))
            stored = read_binding(folder)
            self.assertEqual(stored.account_id, "10003")
            self.assertEqual(stored.persona_id, "")

    def test_no_temporary_files_are_left_behind(self):
        with tempfile.TemporaryDirectory() as folder:
            write_binding(folder, sample())
            leftovers = [item.name for item in Path(folder).iterdir() if item.name.endswith(".tmp")]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
