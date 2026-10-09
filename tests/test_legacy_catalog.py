from __future__ import annotations

import unittest

from companion_v2.legacy.catalog import (
    CatalogAction,
    LEGACY_COMPATIBILITY_CATALOG,
    V1_PLUGIN_ID,
    V1_SUPPORTED_VERSION,
    V1_SUPPORTED_VERSIONS,
)
from companion_v2.legacy.surface_ledger import (
    LEGACY_SURFACE_LEDGER,
    SurfaceClassification,
)


class LegacyCompatibilityCatalogTests(unittest.TestCase):
    def test_catalog_has_complete_static_source_version_and_action_metadata(self) -> None:
        catalog = LEGACY_COMPATIBILITY_CATALOG

        self.assertEqual(catalog.validate(), ())
        self.assertEqual(catalog.target_plugin_id, V1_PLUGIN_ID)
        self.assertEqual(catalog.supported_v1_versions, V1_SUPPORTED_VERSIONS)
        self.assertEqual(V1_SUPPORTED_VERSION, "6.7.0")
        self.assertGreaterEqual(len(catalog.entries), 8)
        self.assertEqual(
            catalog.entry("private.core_profiles").source_plugin_id,
            V1_PLUGIN_ID,
        )
        self.assertTrue(catalog.entries_for_plugin("astrbot_plugin_reality_companion"))
        for entry in catalog.entries:
            self.assertTrue(entry.source_paths)
            self.assertTrue(entry.source_version)
            self.assertTrue(entry.handler_id)
            self.assertIsInstance(entry.action, CatalogAction)

    def test_surface_ledger_uses_only_declared_classifications(self) -> None:
        ledger = LEGACY_SURFACE_LEDGER

        self.assertEqual(ledger.validate(), ())
        self.assertGreaterEqual(len(ledger.entries), 16)
        self.assertEqual(
            {entry.classification for entry in ledger.entries},
            set(SurfaceClassification),
        )
        for entry in ledger.entries:
            self.assertTrue(entry.v2_route)
            self.assertTrue(entry.acceptance_scope)
