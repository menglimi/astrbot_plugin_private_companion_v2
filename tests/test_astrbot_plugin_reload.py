"""Keep plugin import lifecycle checks in a separate real SDK process."""

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class AstrBotPluginReloadTests(unittest.TestCase):
    def test_disable_enable_and_hot_reload_restore_saved_profile(self):
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(prefix="companion-v2-plugin-reload-root-") as temporary:
            environment = os.environ.copy()
            environment["ASTRBOT_ROOT"] = temporary
            result = subprocess.run([sys.executable, "-X", "utf8", "-m", "tests.plugin_reload_process"],
                                    cwd=root, env=environment, text=True, encoding="utf-8",
                                    capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"startup_cycles": 5', result.stdout)
        self.assertIn('"duplicate_handlers": 0', result.stdout)
        self.assertIn('"platform_sends": 0', result.stdout)
        self.assertIn('"astrbot_root_isolated": true', result.stdout)
