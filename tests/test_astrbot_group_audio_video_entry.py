"""Subprocess-isolated real main.py group voice/video admission and shutdown."""

import os
from pathlib import Path
import subprocess
import sys
import unittest


class AstrBotGroupAudioVideoEntryTests(unittest.TestCase):
    def test_plugin_entry_group_voice_video_and_teardown(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "-X", "utf8", "-m", "tests.group_audio_video_entry_process"],
            cwd=root, env=os.environ.copy(), text=True, encoding="utf-8", capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: main.py group voice/video entry", result.stdout)
