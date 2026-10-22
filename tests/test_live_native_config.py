"""Live helpers read the bundled schema and save only V2-owned settings."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from tests import test_astrbot_staging_host as host_support
from astrbot_host.native_extensions.live.page_config import PageConfigManager
from astrbot_host.native_extensions.live.runtime import LiveRuntime
from astrbot_host.native_extensions.settings import ExtensionSettings


class LiveNativeConfigTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="v2-live-config-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.legacy_home = self.root / "legacy-home"
        self.legacy_home.mkdir()
        self.settings = ExtensionSettings(self.root / "v2", "live")
        self.settings["auto_connect"] = False

    async def test_reachable_live_helper_reads_schema_and_persists_under_v2(self):
        live = LiveRuntime(NS(get_all_stars=lambda: ()), self.settings,
                           self.settings.root, NS(native_extensions=None, session=None, settings=None))
        self.addAsyncCleanup(live.terminate)
        self.assertIsNone(live.page_api)
        self.assertTrue(await live._persist_plugin_config_updates({"part_id": 2, "area_id": 86}))
        saved = json.loads(self.settings.path.read_text(encoding="utf-8"))
        self.assertEqual((saved["part_id"], saved["area_id"]), (2, 86))
        self.assertEqual(self.settings.path, self.root / "v2" / "extensions" / "live" / "config.json")

        helper = live._page_api_helper()
        self.assertIsNotNone(helper)
        payload = await helper.get_config_schema()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["schema"]["bilibili_room_id"]["type"], "int")
        updates = helper.config_manager.build_updates({"bilibili_room_id": "12345", "bilibili_sessdata": ""})
        self.assertEqual(updates, {"bilibili_room_id": 12345})
        self.assertTrue(await helper.config_manager.apply_updates(updates))
        self.assertEqual(ExtensionSettings(self.root / "v2", "live")["bilibili_room_id"], 12345)

    async def test_missing_or_failed_native_saver_never_creates_home_config(self):
        with patch("os.path.expanduser", return_value=str(self.legacy_home)):
            plain = PageConfigManager(NS(config={}), "astrbot_plugin_private_companion.live", Mock())
            self.assertEqual(plain.read_schema()["bilibili_room_id"]["type"], "int")
            self.assertFalse(await plain.persist())

            native = PageConfigManager(NS(config=self.settings), "astrbot_plugin_private_companion.live", Mock())
            with patch.object(self.settings, "save_config", side_effect=OSError("synthetic write failure")):
                self.assertFalse(await native.persist())
            self.assertEqual(list(self.legacy_home.rglob("*.json")), [])
            self.assertFalse(self.settings.path.exists())


if __name__ == "__main__":
    unittest.main()
