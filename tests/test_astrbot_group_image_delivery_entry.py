"""Exercise real SDK import, group image send/quote and teardown in isolation."""

import os
from pathlib import Path
import subprocess
import sys
import unittest


class AstrBotGroupImageDeliveryEntryTests(unittest.TestCase):
    def test_core_images_and_cross_member_bot_quote_through_sdk_entry(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "-X", "utf8", "-c",
            "from tests.group_media_entry_process import run; run(deliver_images=True)"],
            cwd=root, env=os.environ.copy(), text=True, encoding="utf-8", capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: AstrBot core group image delivery, cross-member Bot image quote", result.stdout)
