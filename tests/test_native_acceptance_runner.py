"""Failure reports must survive snapshot rejection, worker failure and timeout."""

import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.native_acceptance import run


class NativeAcceptanceRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="native-acceptance-runner-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "scanner" / "v2"
        self.source.mkdir(parents=True)
        for name, body in {"main.py": "pass\n", "metadata.yaml": "name: fixture\n",
                           "_conf_schema.json": "{}\n", "requirements.txt": "\n"}.items():
            (self.source / name).write_text(body, encoding="utf-8")
        self.host = self.root / "sdk"
        (self.host / "astrbot").mkdir(parents=True)
        (self.host / "astrbot" / "__init__.py").write_text("", encoding="utf-8")
        self.scratch, self.output = self.root / "scratch", self.root / "report"

    def invoke(self):
        report = run(source=self.source, host_source=self.host, output=self.output, scratch_parent=self.scratch)
        self.assertFalse(report["passed"])
        self.assertTrue(report["temporary_installation_removed"])
        self.assertEqual(list(self.scratch.iterdir()), [])
        self.assertEqual(json.loads((self.output / "native-acceptance.json").read_text(encoding="utf-8")), report)
        return report

    def test_static_legacy_dependency_prevents_worker_and_still_cleans_installation(self):
        (self.source / "main.py").write_text("import astrbot_plugin_private_companion\n", encoding="utf-8")
        with patch("tools.native_acceptance.subprocess.run") as child:
            report = self.invoke()
        child.assert_not_called()
        self.assertEqual(report["failure"]["type"], "ValueError")
        self.assertIn("legacy_import", report["failure"]["message"])

    def test_worker_timeout_records_failure_and_cleans_installation(self):
        with patch("tools.native_acceptance.subprocess.run", side_effect=subprocess.TimeoutExpired("worker", 90)):
            report = self.invoke()
        self.assertEqual(report["failure"]["type"], "timeout")

    def test_missing_report_cannot_pass_even_with_zero_exit(self):
        with patch("tools.native_acceptance.subprocess.run", return_value=subprocess.CompletedProcess([], 0)):
            report = self.invoke()
        self.assertEqual(report["failure"]["type"], "missing_worker_report")

    def test_nonzero_exit_cannot_accept_passing_child_report(self):
        def child(command, **kwargs):
            self.assertIn("-I", command)
            self.assertNotIn("PYTHONPATH", kwargs["env"])
            report_path = Path(command[command.index("--report") + 1])
            report_path.write_text('{"passed":true}', encoding="utf-8")
            return subprocess.CompletedProcess(command, 7)
        with patch("tools.native_acceptance.subprocess.run", side_effect=child):
            report = self.invoke()
        self.assertEqual(report["worker_exit"], 7)


if __name__ == "__main__":
    unittest.main()
