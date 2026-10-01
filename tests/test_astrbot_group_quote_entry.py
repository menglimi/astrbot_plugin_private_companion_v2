"""Real SDK plugin entry for group quotes, isolated from the test runner imports."""

import os
from pathlib import Path
import subprocess
import sys
import unittest


class AstrBotGroupQuoteEntryTests(unittest.TestCase):
    def test_original_quoted_and_historical_media_through_sdk_entry(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "-X", "utf8", "-c",
            "from tests.group_forward_entry_process import run; run(quoted=True)"],
            cwd=root, env=os.environ.copy(), text=True, encoding="utf-8", capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: real SDK plugin entry, group forward and quoted audio/video", result.stdout)
