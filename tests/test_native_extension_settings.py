"""Real packaged schema saves only valid fields and preserves private settings."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from astrbot_host.native_extensions.settings import ExtensionSettings


class ExtensionSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="v2-native-settings-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_secrets_stay_blank_on_dashboard_and_blank_updates_preserve_them(self):
        settings = ExtensionSettings(self.root, "reality")
        settings.update_fields({"home": {"access_token": "synthetic-secret"}})
        self.assertEqual(settings.public()["home"]["access_token"], "")
        self.assertTrue(settings.public()["home"]["access_token_configured"])
        revision = settings.revision()
        settings.update_fields({"home": {"access_token": ""}})
        self.assertEqual(settings.revision(), revision)
        reread = ExtensionSettings(self.root, "reality")
        self.assertEqual(reread["home"]["access_token"], "synthetic-secret")

    def test_invalid_ports_lists_unknown_fields_and_failed_writes_keep_previous_settings(self):
        settings = ExtensionSettings(self.root, "live")
        before = settings.revision()
        for updates in ({"vts_port": 0}, {"vts_port": 65536}, {"vts_port": True}, {"unknown": 1}):
            with self.assertRaises(ValueError):
                settings.update_fields(updates)
            self.assertEqual(settings.revision(), before)
        with patch.object(settings, "save_config", side_effect=OSError("synthetic write failure")):
            with self.assertRaises(OSError):
                settings.update_fields({"vts_port": 8002})
        self.assertEqual(settings.revision(), before)
        reality = ExtensionSettings(self.root, "reality")
        with self.assertRaises(ValueError):
            reality.update_fields({"authorized_user_ids": [123]})

    def test_utf8_lf_and_template_hotkeys_round_trip(self):
        settings = ExtensionSettings(self.root, "live")
        templates = settings.schema["l2d_hotkeys"]["templates"]
        template, schema = next(iter(templates.items()))
        values = {name: spec.get("default", "") for name, spec in schema["items"].items()}
        settings.update_fields({"l2d_hotkeys": [{"__template_key": template, **values}]})
        self.assertEqual(ExtensionSettings(self.root, "live")["l2d_hotkeys"][0]["__template_key"], template)
        body = settings.path.read_bytes()
        body.decode("utf-8")
        self.assertFalse(body.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", body)
        self.assertTrue(body.endswith(b"\n"))
