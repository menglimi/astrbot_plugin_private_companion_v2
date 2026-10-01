"""The config-ledger tooling edits a governance artefact, so it needs its own guards.

Every test runs against a scratch copy; none of them touch the real ledger.
"""
from __future__ import annotations

import csv
from collections.abc import Iterable
import importlib
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
REAL_LEDGER = ROOT / "docs" / "V1_V2_CONFIG_VERIFIED_20260927.csv"


def load_tool(name):
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_tool_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERDICTS = load_tool("ledger_verdicts")
DISPOSITIONS = load_tool("c2_dispositions")
GROUPS = load_tool("c2_group_verdicts")
LIBRARY = load_tool("c2_library_verdicts")
INVENTORY = load_tool("build_v2_inventory")


def read_ledger(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


class LedgerToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Path(self.temp.name) / "ledger.csv"
        shutil.copyfile(REAL_LEDGER, self.ledger)
        # Point the tool at the scratch copy before any read or write. The tool
        # resolves its target per call, so this must be set (and reset) around
        # every use; without it save_rows would overwrite the real ledger.
        DISPOSITIONS._TARGET = self.ledger
        self.addCleanup(setattr, DISPOSITIONS, "_TARGET", None)

    def by_key(self, rows):
        return {row["v1_key"]: row for row in rows}

    def test_both_tools_are_shipped_with_their_retirement_sets(self):
        # A retirement set that silently empties would look like success, so the
        # expected key counts are pinned here.
        self.assertEqual(sum(len(spec["keys"]) for spec in VERDICTS.GROUPS.values()), 47)
        self.assertEqual(sum(len(spec["keys"]) for spec in DISPOSITIONS.GROUPS.values()), 8)
        # C2-1 landed, so nothing is held back any more; each remaining owed group
        # must be recorded by its own tool rather than left floating.
        self.assertEqual(DISPOSITIONS.PENDING, ())
        self.assertEqual(len(GROUPS.ROWS), GROUPS.EXPECT_TOTAL)

    def test_the_group_verdicts_name_live_carriers(self):
        # Each landing names a V2 field that carries the setting. If a group is
        # renamed or a field dropped, the ledger's claim would be orphaned silently;
        # this is what stops that.
        self.assertEqual(GROUPS.verify_fields(), [])
        self.assertEqual(len(GROUPS.NAMED_FIELDS), 9)

    def test_the_library_verdicts_name_live_carriers(self):
        # C2-3's landings name both fields and the table the trigger cursor lives in.
        self.assertEqual(LIBRARY.verify_carriers(), [])
        self.assertEqual(len(LIBRARY.NAMED_FIELDS), 7)
        self.assertEqual(len(LIBRARY.ROWS), LIBRARY.EXPECT_TOTAL)

    def test_every_tool_agrees_with_the_shipped_ledger(self):
        _fields, rows = read_ledger(self.ledger)
        by_key = self.by_key(rows)
        for tool, mapping in ((GROUPS, GROUPS.ROWS), (LIBRARY, LIBRARY.ROWS)):
            changes, problems = tool.plan(rows)
            self.assertEqual(problems, [], tool.__name__)
            self.assertEqual(changes, [], tool.__name__)
            for key, (verdict, landing) in mapping.items():
                self.assertEqual(by_key[key]["verified_verdict"], verdict, key)
                self.assertEqual(by_key[key]["verified_landing"], landing, key)

    def test_the_verdict_tools_do_not_overlap(self):
        groups = set(GROUPS.ROWS)
        library = set(LIBRARY.ROWS)
        retired = ({key for spec in VERDICTS.GROUPS.values() for key in spec["keys"]}
                   | {key for spec in DISPOSITIONS.GROUPS.values() for key in spec["keys"]})
        self.assertEqual(groups & library, set())
        self.assertEqual((groups | library) & retired, set())

    def test_every_named_carrier_is_claimed_by_exactly_one_row(self):
        claimed = [key for key, (verdict, _landing) in GROUPS.ROWS.items()
                   if verdict == GROUPS.RENAMED]
        self.assertEqual(len(claimed), len(set(claimed)))
        for name in GROUPS.NAMED_FIELDS:
            carriers = [key for key, (_v, landing) in GROUPS.ROWS.items() if name in landing]
            self.assertEqual(len(carriers), 1, f"{name} is claimed by {carriers}")

    def test_a_group_landing_never_says_it_is_owed(self):
        for key, (verdict, landing) in GROUPS.ROWS.items():
            self.assertNotIn(verdict, ("", "owed"), key)
            self.assertGreater(len(landing), 20, key)

    def test_a_library_landing_never_says_it_is_owed(self):
        for key, (verdict, landing) in LIBRARY.ROWS.items():
            self.assertNotIn(verdict, ("", "owed"), key)
            self.assertGreater(len(landing), 20, key)

    def test_every_retired_key_exists_in_the_ledger(self):
        _fields, rows = read_ledger(self.ledger)
        known = set(self.by_key(rows))
        for spec in VERDICTS.GROUPS.values():
            for key in spec["keys"]:
                self.assertIn(key, known, key)
        for spec in DISPOSITIONS.GROUPS.values():
            for key in spec["keys"]:
                self.assertIn(key, known, key)
        for key in DISPOSITIONS.PENDING:
            self.assertIn(key, known, key)

    def test_retirement_keys_are_disjoint_between_tools(self):
        left = {key for spec in VERDICTS.GROUPS.values() for key in spec["keys"]}
        right = {key for spec in DISPOSITIONS.GROUPS.values() for key in spec["keys"]}
        self.assertEqual(left & right, set())

    def test_every_retirement_states_a_reason(self):
        for name, spec in {**VERDICTS.GROUPS, **DISPOSITIONS.GROUPS}.items():
            self.assertGreater(len(str(spec["reason"])), 20, name)

    def reopen(self, keys):
        """Put the named keys back into the owed state on the scratch copy.

        The shipped ledger has already had these dispositions applied, so a test
        that wants to watch the tool *detect* them has to reopen them first.
        """
        fieldnames, rows = read_ledger(self.ledger)
        wanted = set(keys)
        touched = 0
        for row in rows:
            if row["v1_key"] in wanted and row["verified_verdict"] == DISPOSITIONS.RETIRED:
                row["verified_verdict"] = DISPOSITIONS.OWED
                row["verified_landing"] = "（测试重开）"
                touched += 1
        self.assertEqual(touched, len(wanted), "every requested key must have been retired")
        # Write to the scratch copy explicitly: the module-level target is only a
        # convenience for the CLI, and relying on it here is how a test once wrote
        # the scratch copy over the real ledger.
        DISPOSITIONS.save_rows(fieldnames, rows, self.ledger)

    def test_disposition_tool_retires_only_its_eight(self):
        keys = [key for spec in DISPOSITIONS.GROUPS.values() for key in spec["keys"]]
        self.reopen(keys)
        changes, problems = DISPOSITIONS.plan_changes(read_ledger(self.ledger)[1])
        self.assertEqual(problems, [])
        self.assertEqual(len(changes), 8)
        self.assertEqual({key for _g, key, _row in changes}, set(keys))

    def test_an_already_retired_ledger_needs_no_changes(self):
        # The shipped ledger already carries these dispositions; a real apply pass
        # must therefore find nothing to do rather than re-listing finished work.
        changes, problems = DISPOSITIONS.plan_changes(read_ledger(self.ledger)[1])
        self.assertEqual(problems, [])
        self.assertEqual(changes, [])

    def test_pending_fields_are_held_back_not_retired(self):
        changes, _problems = DISPOSITIONS.plan_changes(read_ledger(self.ledger)[1])
        retired = {key for _g, key, _row in changes}
        for key in DISPOSITIONS.PENDING:
            self.assertNotIn(key, retired, key)
        # And they are asserted to still be owed by plan() itself.
        _todo, problems = DISPOSITIONS.plan(read_ledger(self.ledger)[1])
        self.assertEqual(problems, [])

    def run_cli(self, argv):
        """Drive the tool through its real entry point against the scratch copy."""
        import contextlib
        import io
        import sys
        buffer = io.StringIO()
        saved = sys.argv
        sys.argv = ["c2_dispositions.py", *argv, "--ledger", str(self.ledger)]
        try:
            with contextlib.redirect_stdout(buffer):
                code = DISPOSITIONS.main()
        finally:
            sys.argv = saved
        return code, buffer.getvalue()

    def test_apply_is_idempotent_and_preserves_encoding(self):
        keys = [key for spec in DISPOSITIONS.GROUPS.values() for key in spec["keys"]]
        self.reopen(keys)
        first, out1 = self.run_cli(["--apply"])
        self.assertEqual(first, 0)
        self.assertIn("retired 8 rows", out1)
        second, out2 = self.run_cli(["--apply"])
        self.assertEqual(second, 0)
        self.assertIn("retired 0 rows", out2)
        check, out3 = self.run_cli(["--check"])
        self.assertEqual(check, 0)
        self.assertIn("would retire 0 rows", out3)
        raw = self.ledger.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "ledger must stay BOM-free")
        self.assertNotIn(b"\r", raw, "ledger must stay LF-only")
        self.assertTrue(raw.endswith(b"\n"), "ledger must keep a trailing newline")

    def test_saving_never_touches_the_real_ledger(self):
        before = REAL_LEDGER.read_bytes()
        fieldnames, rows = read_ledger(self.ledger)
        DISPOSITIONS.save_rows(fieldnames, rows)
        self.assertEqual(REAL_LEDGER.read_bytes(), before,
                         "a scratch-copy save must not reach the governance artefact")

    def test_row_and_column_counts_survive_a_retirement_pass(self):
        fieldnames, rows = read_ledger(self.ledger)
        original_rows, original_columns = len(rows), len(fieldnames or ())
        self.assertEqual(original_rows, 1010)
        self.assertEqual(original_columns, 9)
        todo, _problems = DISPOSITIONS.plan(rows)
        self.assertEqual(len(todo), 0, "the shipped ledger is already retired for this group")
        for group, _key, row in todo:
            row["verified_verdict"] = DISPOSITIONS.RETIRED
            row["verified_landing"] = DISPOSITIONS.GROUPS[group]["reason"]
        DISPOSITIONS.save_rows(fieldnames, rows)
        after_fields, after_rows = read_ledger(self.ledger)
        self.assertEqual(len(after_rows), original_rows)
        self.assertEqual(len(after_fields or ()), original_columns)

    def test_a_real_ledger_row_carries_a_readable_retirement_reason(self):
        _fields, rows = read_ledger(self.ledger)
        retired = [row for row in rows if row["verified_landing"].startswith("（销号）")]
        self.assertGreater(len(retired), 0)
        for row in retired:
            self.assertEqual(row["verified_verdict"], DISPOSITIONS.RETIRED, row["v1_key"])
            self.assertGreater(len(row["verified_landing"]), 30, row["v1_key"])

    def test_tools_reject_a_ledger_missing_a_required_key(self):
        fieldnames, rows = read_ledger(self.ledger)
        pruned = [row for row in rows
                  if row["v1_key"] != "photo_action_config.photo_reference_catalog"]
        self.assertEqual(len(pruned), len(rows) - 1)
        _todo, problems = DISPOSITIONS.plan(pruned)
        self.assertTrue(any("photo_reference_catalog" in item for item in problems), problems)

    def test_verdict_tool_reports_missing_keys_instead_of_silently_passing(self):
        _fields, rows = read_ledger(self.ledger)
        pruned = [row for row in rows if row["v1_key"] != "relay_bridge_config.enable_atrelay_tools"]
        changes, missing = VERDICTS.plan(pruned)
        self.assertTrue(changes)
        self.assertTrue(any("enable_atrelay_tools" in item[1] for item in missing), missing)


class InventoryDiscoveryTests(unittest.TestCase):
    """The config-surface inventory must not lose a field to a naming accident.

    It once matched the literal ``def configuration_fields``, so when the growth module
    split its skills into ``skill_configuration_fields`` two registered fields left the
    inventory silently -- and it had undercounted by 269 the same way before that. The
    rule is now "recognised by what it returns", and these tests hold that line.
    """

    def test_every_provider_returning_field_definitions_is_in_the_inventory(self):
        from companion_v2.configuration.registry import FieldDefinition
        discovered, skipped, _duplicates = INVENTORY.load_registry()
        self.assertEqual(skipped, [], skipped)
        missing = []
        for module_name, function_name in self._providers():
            try:
                module = importlib.import_module(module_name)
                produced = getattr(module, function_name)()
            except Exception as error:                      # a provider this test cannot call
                missing.append(f"{module_name}:{function_name} call failed: {error}")
                continue
            if isinstance(produced, (str, bytes)) or not isinstance(produced, Iterable):
                continue
            rows = tuple(produced)
            if not rows or not all(isinstance(item, FieldDefinition) for item in rows):
                continue
            for definition in rows:
                if definition.field_id not in discovered:
                    missing.append(definition.field_id)
        self.assertEqual(missing, [], f"fields absent from the inventory: {missing}")
        # A sanity floor: the surface is large, so a collapse to near-zero is a bug.
        self.assertGreater(len(discovered), 500, len(discovered))

    def _providers(self):
        """Module-level bare-callable functions whose name suggests a field registry."""
        import ast
        root = ROOT
        for folder in ("companion_v2", "astrbot_host"):
            for path in sorted((root / folder).rglob("*.py")):
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8"))
                except (OSError, SyntaxError):
                    continue
                module_name = str(path.relative_to(root).with_suffix("")).replace(os.sep, ".")
                for node in tree.body:
                    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    lowered = node.name.lower()
                    if "field" not in lowered and "configuration" not in lowered:
                        continue
                    if not INVENTORY._may_be_called_bare(node):
                        continue
                    yield module_name, node.name


if __name__ == "__main__":
    unittest.main()
